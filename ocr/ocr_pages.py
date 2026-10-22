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

from segment import Strip, load_grey, render, segment, split_strip

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

PROMPTS = {"cllg": CLLG_PROMPT, "paper": PAPER_PROMPT}


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
        "front_matter": args.front_matter,
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


def find_loop(tokens: list[int], max_period: int = 24, min_reps: int = 8, min_span: int = 32) -> int | None:
    """Start of a cycle repeating at the end of tokens, if there is one.

    Greedy decoding sometimes falls into "οἷον, οἷον, οἷον, ..." until the
    token limit; a block of p tokens repeated min_reps times (and at least
    min_span tokens) at the tail is taken as such a loop.
    """
    for p in range(1, max_period + 1):
        reps = max(min_reps, -(-min_span // p))
        if len(tokens) < p * reps:
            continue
        tail = tokens[-p:]
        if all(tokens[-(k + 1) * p: len(tokens) - k * p] == tail for k in range(1, reps)):
            start = len(tokens) - reps * p
            while start >= p and tokens[start - p:start] == tail:
                start -= p
            return start
    return None


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
        messages = [{"role": "user", "content": [{"type": "image"}, {"type": "text", "text": PROMPTS[args.prompt]}]}]
        self.chat = self.processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
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
        log(f"model_loaded seconds={time.time() - t0:.1f} gpu_mem_gb={torch.cuda.memory_allocated() / 2**30:.1f}")

    def transcribe(self, images) -> list[dict]:
        torch = self.torch
        inputs = self.processor(
            text=[self.chat] * len(images), images=images, padding=True, return_tensors="pt"
        ).to("cuda")
        with torch.inference_mode():
            out = self.model.generate(
                **inputs, max_new_tokens=self.args.max_new_tokens, do_sample=False,
                stopping_criteria=self.stopping(inputs["input_ids"].shape[1]),
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
    ap.add_argument("--prompt", choices=sorted(PROMPTS), default="cllg")
    ap.add_argument("--scale", type=float, default=0.5, help="scan pixels to model pixels")
    ap.add_argument("--max-side", type=int, default=1024, help="longest side of a strip image")
    ap.add_argument("--max-new-tokens", type=int, default=2048, help="a strip needs about 500-900")
    ap.add_argument("--batch-size", type=int, default=16, help="strips per generate() call")
    ap.add_argument("--front-matter", default="0001-0004", help="pages read as one column")
    ap.add_argument("--ocr-heads", action="store_true", help="also transcribe running heads")
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
            # A strip that loops is read again as two halves; a smaller image
            # usually decodes cleanly. Halves that loop again keep their text
            # up to the loop, and the strip stays flagged.
            halves, owners = [], []
            for (page, n, strip, _), r in retry:
                for half in split_strip(pending[page]["grey"], strip):
                    halves.append(render(pending[page]["grey"], half, args.scale, args.max_side))
                    owners.append(r)
            t_retry = time.time()
            half_results = model.transcribe(halves)
            for r in {id(r): r for r in owners}.values():
                parts = [h for o, h in zip(owners, half_results) if o is r]
                r["first_try"] = {"text": r["text"], "new_tokens": r["new_tokens"]}
                r["text"] = "\n".join(h["text"].strip() for h in parts)
                r["new_tokens"] = sum(h["new_tokens"] for h in parts)
                r["loop"] = any(h["loop"] or h["hit_limit"] for h in parts)
                r["hit_limit"] = False
                r["retried"] = True
            n_tok += sum(h["new_tokens"] for h in half_results)
            log(f"retry strips={len(retry)} halves={len(halves)} seconds={time.time() - t_retry:.1f} "
                f"still_looping={sum(r['loop'] for _, r in retry)}")
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
