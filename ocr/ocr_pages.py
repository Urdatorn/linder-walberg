"""OCR the Linder-Walberg page scans with CLLG/Qwen3VL-8B-synth_real.

Each page is cut into strips (see segment.py), every strip is transcribed
with greedy decoding, and the page is written as soon as all its strips are
done, so an interrupted run resumes where it stopped:

    <out>/pages/NNNN.json   per-strip boxes, image sizes, raw output, token counts
    <out>/pages/NNNN.txt    the strips' raw output joined in reading order
    <out>/strips/NNNN_SS.png  the images the model saw (with --save-strips)

--dry-run segments and renders without loading the model, so the layout can
be checked on the login node.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import sys
import time
from pathlib import Path

from segment import Strip, load_grey, render, segment

# Ported verbatim from the CLLG scanner (src/main/ipc/ocr.ts), which in turn
# ports it from cllg_pipeline.py; this is the prompt the CLLG models are run with.
CLLG_PROMPT = """You are an OCR system for ancient Greek and Latin printed scholarly texts.

Transcribe the page exactly in pseudo-Markdown.

RULES:
- Copy text exactly: keep all characters, accents, ligatures, punctuation, spacing.
- Do NOT normalize, correct, or translate.
- Follow visual reading order.
- Each paragraph = ONE line.
- If a paragraph continues one from the previous page, wrap that first line in <continued>...</continued>.
- Join words split by line-break hyphens.
- Wrap section markers as <ref>X</ref>.
- Major headers: # <ref>X</ref> or # <ref>X</ref> TITLE
- Standalone title: # TITLE
- Inline section markers and section markers in the margin are encoded inline.
- Margin notes: <note>TEXT</note>.
- Ignore running heads, footers, page numbers, line numbers, printer marks, footnote markers.

Output ONLY the transcription."""

# The wording printed in the paper's appendix (arXiv 2603.02803, Figure 3).
PAPER_PROMPT = (
    "You are an OCR system for Ancient Greek and Latin printed scholarly texts.\n"
    "Transcribe the page exactly in pseudo-Markdown.\n"
    "Rules: Copy text exactly (retain all characters, accents, ligatures, punctuation, spacing). "
    "Do not normalize, correct, or translate. Follow visual reading order. "
    "Each paragraph must be output as one line. Add <tab/> at the start of paragraphs that clearly "
    "begin on this page; do not add it if the paragraph continues from a previous page. "
    "Join words split by line-break hyphens. Wrap section markers as <ref>X</ref>. "
    "Major headers use: # <ref>X</ref> or # <ref>X</ref> TITLE. Standalone titles use # TITLE. "
    "Inline and marginal section markers are encoded inline. Margin notes are encoded as <note>TEXT</note>. "
    "Ignore running heads, footers, page numbers, line numbers, printer marks, and footnote markers. "
    "Output only the transcription."
)

# The paper's prompt plus what this book is. Without it the model, trained on
# Greek and Latin only, writes many Swedish headwords in Greek letters
# ("Σκρίφβαρε" for Skrifvare, "Κατεχεσ" for Katekes), most often under K, M, N, S.
SWEDISH_NOTE = (
    "\nThis page is from a Swedish–Ancient Greek dictionary. The Swedish words (headwords, "
    "explanations, abbreviations such as ngt, ngn, t. ex., l.) are in the Latin alphabet with å, ä, ö: "
    "always transcribe them in Latin letters, never in Greek letters. Only the Greek equivalents are in Greek."
)

PROMPTS = {"cllg": CLLG_PROMPT, "paper": PAPER_PROMPT, "paper_sv": PAPER_PROMPT + SWEDISH_NOTE}


def log(msg: str) -> None:
    print(f"[{time.strftime('%Y-%m-%dT%H:%M:%S')}] {msg}", flush=True)


def parse_pages(spec: str | None, available: list[str]) -> list[str]:
    """'0005-0009,0050' (or '0005-0009+0050') -> page ids present in the image directory."""
    if not spec:
        return available
    wanted: set[str] = set()
    for part in re.split(r"[,+\s]+", spec):   # '+' survives sbatch --export
        if "-" in part:
            a, b = part.split("-")
            wanted.update(f"{n:04d}" for n in range(int(a), int(b) + 1))
        elif part:
            wanted.add(f"{int(part):04d}")
    return [p for p in available if p in wanted]


def settings_of(args) -> dict:
    return {
        "model": args.model, "prompt": args.prompt, "scale": args.scale, "max_side": args.max_side,
        "max_new_tokens": args.max_new_tokens, "ocr_heads": args.ocr_heads,
        "front_matter": args.front_matter, "latin_heads": args.latin_heads,
    }


def page_strips(args, page: str, front: set[str]):
    grey = load_grey(str(Path(args.images) / f"{page}.tif"))
    strips = segment(grey, args.scale, args.max_side, columns=page not in front)
    if not args.ocr_heads:
        strips = [s for s in strips if s.kind != "head"]
    return grey, strips


def join_page(strips: list[dict]) -> str:
    """Raw strip outputs in reading order; a blank line between columns and sections."""
    out, prev = [], None
    for s in strips:
        key = (s["section"], s["column"])
        if prev is not None and key != prev:
            out.append("")
        out.append(s["text"].strip())
        prev = key
    return "\n".join(out).strip() + "\n"


def find_loop(tokens: list[int], max_period: int = 64, min_reps: int = 8, min_span: int = 32) -> int | None:
    """Start of a cycle repeating at the end of tokens, if there is one.

    Greedy decoding sometimes falls into "οἷον, οἷον, οἷον, ..." until the
    token limit; a block of p tokens repeated min_reps times (and at least
    min_span tokens) at the tail is taken as such a loop. Blocks longer than
    24 tokens ("Φορνίδιον, οἷον φορνίδιον ἐν τῷ φορνίδιον.") need only 4.
    """
    for p in range(1, max_period + 1):
        reps = max(min_reps if p <= 24 else 4, -(-min_span // p))
        if len(tokens) < p * reps:
            continue
        tail = tokens[-p:]
        if all(tokens[-(k + 1) * p: len(tokens) - k * p] == tail for k in range(1, reps)):
            start = len(tokens) - reps * p
            while start >= p and tokens[start - p:start] == tail:
                start -= p
            return start
    return None


# An entry line as the model writes it: "<tab/> " (indented entry) or "# "
# (bold heading) and then the headword, which ends at the first comma.
HEADWORD_OPEN = re.compile(r"^\s*(?:<tab/>|#+)\s*[^,\n]{0,40}$")


def in_headword(tail: str) -> bool:
    """Whether generation is inside a Swedish headword, given the text so far."""
    return bool(HEADWORD_OPEN.match(tail.rsplit("\n", 1)[-1])) and "\n" in tail


def greek_token_ids(tokenizer) -> list[int]:
    """Tokens whose bytes can start or contain a Greek letter.

    The tokenizer is byte-level, so a Greek letter may be split across
    tokens; any token holding a lead byte of the Greek blocks (0xCD-0xCF for
    U+0340-03FF, 0xE1 for U+1F00-1FFF) is counted, which costs no Swedish
    letter (å ä ö é ü are 0xC3).
    """
    from transformers.models.gpt2.tokenization_gpt2 import bytes_to_unicode
    to_byte = {c: b for b, c in bytes_to_unicode().items()}
    ids = []
    for i, tok in enumerate(tokenizer.convert_ids_to_tokens(list(range(len(tokenizer))))):
        if tok and any(to_byte.get(c) in (0xCD, 0xCE, 0xCF, 0xE1) for c in tok):
            ids.append(i)
    return ids


class Model:
    def __init__(self, args):
        import torch
        from transformers import AutoProcessor, Qwen3VLForConditionalGeneration

        self.torch = torch
        self.args = args
        t0 = time.time()
        self.processor = AutoProcessor.from_pretrained(args.model)
        self.processor.tokenizer.padding_side = "left"
        self.model = Qwen3VLForConditionalGeneration.from_pretrained(
            args.model, dtype=torch.bfloat16, attn_implementation="sdpa"
        ).to("cuda").eval()
        self.chats = {
            name: self.processor.apply_chat_template(
                [{"role": "user", "content": [{"type": "image"}, {"type": "text", "text": text}]}],
                tokenize=False, add_generation_prompt=True)
            for name, text in PROMPTS.items()
        }
        self.eos = {self.processor.tokenizer.eos_token_id, self.processor.tokenizer.pad_token_id}
        from transformers import StoppingCriteria, StoppingCriteriaList

        class LoopStop(StoppingCriteria):
            """Stop each sequence on its own once it starts cycling."""
            def __init__(self, prompt_len: int):
                self.prompt_len = prompt_len

            def __call__(self, input_ids, scores, **kwargs):
                if input_ids.shape[1] - self.prompt_len < 32:
                    return torch.zeros(input_ids.shape[0], dtype=torch.bool, device=input_ids.device)
                tails = input_ids[:, -400:].tolist()
                return torch.tensor([find_loop(row) is not None for row in tails], device=input_ids.device)

        self.stopping = lambda prompt_len: StoppingCriteriaList([LoopStop(prompt_len)])

        from transformers import LogitsProcessor, LogitsProcessorList
        tokenizer = self.processor.tokenizer
        newline_ids = {i for i, t in enumerate(tokenizer.convert_ids_to_tokens(list(range(len(tokenizer)))))
                       if t and "\u010a" in t}           # byte-level "\n"
        greek = torch.tensor(greek_token_ids(tokenizer), device="cuda")

        class LatinHeadwords(LogitsProcessor):
            """Forbid Greek letters between an entry marker and the first comma.

            Every headword in the dictionary is Swedish, but on some pages the
            bold headword face is read as Greek ("Ηάρφιν" for Hårfin).
            """
            def __init__(self, prompt_len: int):
                self.prompt_len = prompt_len

            def __call__(self, input_ids, scores):
                start = max(self.prompt_len, input_ids.shape[1] - 24)
                for b, row in enumerate(input_ids[:, start:].tolist()):
                    nl = max((i for i, t in enumerate(row) if t in newline_ids), default=None)
                    if nl is not None:
                        tail = tokenizer.decode(row[nl:])
                    elif start == self.prompt_len:          # the strip's first line
                        tail = "\n" + tokenizer.decode(row)
                    else:
                        continue
                    if in_headword(tail):
                        scores[b, greek] = -float("inf")
                return scores

        self.processors = (lambda prompt_len: LogitsProcessorList([LatinHeadwords(prompt_len)])) \
            if args.latin_heads else (lambda prompt_len: None)
        log(f"latin_heads={args.latin_heads} greek_tokens={len(greek)} newline_tokens={len(newline_ids)}")
        log(f"model_loaded seconds={time.time() - t0:.1f} gpu_mem_gb={torch.cuda.memory_allocated() / 2**30:.1f}")

    def transcribe(self, images, prompt: str | None = None) -> list[dict]:
        torch = self.torch
        inputs = self.processor(
            text=[self.chats[prompt or self.args.prompt]] * len(images), images=images, padding=True, return_tensors="pt"
        ).to("cuda")
        with torch.inference_mode():
            out = self.model.generate(
                **inputs, max_new_tokens=self.args.max_new_tokens, do_sample=False,
                stopping_criteria=self.stopping(inputs["input_ids"].shape[1]),
                logits_processor=self.processors(inputs["input_ids"].shape[1]),
            )
        new = out[:, inputs["input_ids"].shape[1]:].tolist()
        results = []
        for row in new:
            n = next((i for i, t in enumerate(row) if t in self.eos), len(row))
            loop = find_loop(row[:n])
            keep = row[:loop] if loop is not None else row[:n]
            results.append({
                "text": self.processor.tokenizer.decode(keep, skip_special_tokens=True),
                "new_tokens": n,
                "hit_limit": n >= self.args.max_new_tokens,
                "loop": loop is not None,
            })
        return results


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--images", required=True, help="directory of NNNN.tif scans")
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default="CLLG/Qwen3VL-8B-synth_real")
    ap.add_argument("--pages", help="e.g. 0005-0009,0050; default all")
    ap.add_argument("--shard", type=int, default=0)
    ap.add_argument("--num-shards", type=int, default=1)
    ap.add_argument("--prompt", choices=sorted(PROMPTS), default="paper_sv")
    ap.add_argument("--scale", type=float, default=0.5, help="scan pixels to model pixels")
    ap.add_argument("--max-side", type=int, default=1024, help="longest side of a strip image")
    ap.add_argument("--max-new-tokens", type=int, default=2048, help="a strip needs about 500-900")
    ap.add_argument("--batch-size", type=int, default=16, help="strips per generate() call")
    ap.add_argument("--front-matter", default="0001-0004", help="pages read as one column")
    ap.add_argument("--ocr-heads", action="store_true", help="also transcribe running heads")
    ap.add_argument("--latin-heads", action=argparse.BooleanOptionalAction, default=True,
                    help="forbid Greek letters in headwords (after <tab/> or # up to the first comma)")
    ap.add_argument("--save-strips", action="store_true")
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="segment and render only")
    args = ap.parse_args()

    available = sorted(p.stem for p in Path(args.images).glob("*.tif"))
    pages = parse_pages(args.pages, available)[args.shard::args.num_shards]
    front = set(parse_pages(args.front_matter, available))
    out = Path(args.out)
    (out / "pages").mkdir(parents=True, exist_ok=True)
    if args.save_strips or args.dry_run:
        (out / "strips").mkdir(parents=True, exist_ok=True)
    settings = settings_of(args)

    def done(page: str) -> bool:
        f = out / "pages" / f"{page}.json"
        if args.overwrite or not f.exists():
            return False
        return json.loads(f.read_text())["settings"] == settings

    todo = [p for p in pages if not done(p)]
    log(f"job host={platform.node()} python={sys.version.split()[0]} shard={args.shard}/{args.num_shards} "
        f"pages={len(pages)} already_done={len(pages) - len(todo)} todo={len(todo)}")
    log(f"settings {json.dumps(settings)} batch_size={args.batch_size}")
    if not todo:
        log("nothing_to_do")
        return 0

    model = None
    if not args.dry_run:
        import torch, transformers
        log(f"versions torch={torch.__version__} transformers={transformers.__version__} "
            f"cuda={torch.cuda.is_available()} device={torch.cuda.get_device_name(0) if torch.cuda.is_available() else '-'}")
        model = Model(args)

    t_start = time.time()
    totals = {"pages": 0, "strips": 0, "tokens": 0, "hit_limit": 0}
    queue: list[tuple[str, int, Strip, object]] = []   # page, strip number, strip, image
    pending: dict[str, dict] = {}

    def flush_pages():
        for page in [p for p, rec in pending.items() if rec["left"] == 0]:
            rec = pending.pop(page)
            strips = rec["strips"]
            totals["pages"] += 1
            if args.dry_run:
                continue
            payload = {"page": page, "settings": settings, "strips": strips,
                       "seconds": round(time.time() - rec["t0"], 1)}
            (out / "pages" / f"{page}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1))
            text = join_page([s for s in strips if s["kind"] != "head"])
            (out / "pages" / f"{page}.txt").write_text(text)
            limits = [s["n"] for s in strips if s.get("hit_limit") or s.get("loop")]
            log(f"page_done {page} strips={len(strips)} chars={len(text)} "
                f"tokens={sum(s.get('new_tokens', 0) for s in strips)}"
                + (f" retried={[s['n'] for s in strips if s.get('retried')]}" if any(s.get("retried") for s in strips) else "")
                + (f" WARNING looping strips={limits}" if limits else ""))

    def run_batch():
        if not queue:
            return
        t0 = time.time()
        results = model.transcribe([q[3] for q in queue]) if model else [
            {"text": "", "new_tokens": 0, "hit_limit": False, "loop": False} for _ in queue]
        dt = time.time() - t0
        n_tok = sum(r["new_tokens"] for r in results)
        retry = [(q, r) for q, r in zip(queue, results) if r["loop"] or r["hit_limit"]]
        if retry:
            # A strip that loops is read again, whole, at other scales and with
            # the other prompt: in tests a looping strip read cleanly at a
            # neighbouring scale or under the other prompt, while halving it
            # made the model hallucinate. The first clean reading is kept; if
            # none is clean, the longest text before a loop is, flagged, but
            # never one that ran to the token limit when another did not:
            # those are invented text the loop guard could not see as a cycle.
            t_retry = time.time()
            other = "cllg" if args.prompt != "cllg" else "paper"
            for r in (r for _, r in retry):
                r["first_try"] = {"text": r["text"], "new_tokens": r["new_tokens"]}
                r["attempts"] = []
                r["retried"] = True
            left = list(retry)
            for prompt, scale in [(other, 0.55), (args.prompt, 0.6), (other, 0.45), (args.prompt, 0.4)]:
                if not left:
                    break
                images = [render(pending[page]["grey"], strip, scale, args.max_side) for (page, _, strip, _), _ in left]
                outs = model.transcribe(images, prompt)
                n_tok += sum(o["new_tokens"] for o in outs)
                still = []
                for (q, r), o in zip(left, outs):
                    bad = o["loop"] or o["hit_limit"]
                    r["attempts"].append({"prompt": prompt, "scale": scale, "new_tokens": o["new_tokens"],
                                          "loop": bad, "text": o["text"]})
                    if bad:
                        still.append((q, r))
                    else:
                        r.update(text=o["text"], new_tokens=o["new_tokens"], loop=False, hit_limit=False,
                                 prompt=prompt, scale=scale)
                left = still
            for _, r in left:
                tries = r["attempts"] + [{**r["first_try"], "prompt": args.prompt, "scale": args.scale}]
                best = max(tries, key=lambda a: (a["new_tokens"] < args.max_new_tokens, len(a["text"])))
                r.update(text=best["text"], prompt=best["prompt"], scale=best["scale"], loop=True, hit_limit=False)
            log(f"retry strips={len(retry)} seconds={time.time() - t_retry:.1f} still_looping={len(left)} "
                + " ".join(f"{q[0]}:{q[1]}->{r.get('prompt')}@{r.get('scale')}" for q, r in retry))
        for (page, n, strip, image), r in zip(queue, results):
            rec = pending[page]
            rec["strips"][n].update(r)
            rec["left"] -= 1
        totals["strips"] += len(queue)
        totals["tokens"] += n_tok
        totals["hit_limit"] += sum(r["hit_limit"] or r["loop"] for r in results)
        queue.clear()
        flush_pages()
        elapsed = time.time() - t_start
        rate = totals["pages"] / elapsed if elapsed else 0
        eta = (len(todo) - totals["pages"]) / rate if rate else float("nan")
        mem = ""
        if model:
            mem = f" gpu_peak_gb={model.torch.cuda.max_memory_allocated() / 2**30:.1f}"
        log(f"progress pages={totals['pages']}/{len(todo)} strips={totals['strips']} batch_s={dt:.1f} "
            f"batch_tok_s={n_tok / dt if dt else 0:.0f} total_tokens={totals['tokens']} "
            f"looping={totals['hit_limit']} elapsed_min={elapsed / 60:.1f} eta_min={eta / 60:.1f}{mem}")

    for page in todo:
        grey, strips = page_strips(args, page, front)
        pending[page] = {"t0": time.time(), "left": len(strips), "strips": [], "grey": grey}
        for n, strip in enumerate(strips):
            image = render(grey, strip, args.scale, args.max_side)
            pending[page]["strips"].append({"n": n, **strip.as_dict(), "size": list(image.size)})
            if args.save_strips or args.dry_run:
                image.save(out / "strips" / f"{page}_{n:02d}.png")
            queue.append((page, n, strip, image))
            if len(queue) >= args.batch_size:
                run_batch()
        if not strips:
            log(f"page_empty {page}")
            flush_pages()
    run_batch()

    log(f"job_complete pages={totals['pages']} strips={totals['strips']} tokens={totals['tokens']} "
        f"looping={totals['hit_limit']} minutes={(time.time() - t_start) / 60:.1f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
