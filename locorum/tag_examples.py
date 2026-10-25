"""Part-of-speech tags for every Greek example, from Stoicheia's joint tagger and
parser (Ericu950/Stoicheia-tagger-parser): one forward pass per batch, the
universal tag (UPOS) and lemma of each word.

  locorum/example_pos.jsonl   n, and per word: form, lemma, upos

    python tag_examples.py [--batch 64]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = "Ericu950/Stoicheia-tagger-parser"
TOKEN = re.compile(r"[\ẁ-ͯ’'ʼ᾽]+|[^\w\s]")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--batch", type=int, default=64)
    args = ap.parse_args()
    import torch
    from huggingface_hub import snapshot_download
    from transformers import AutoModel
    local = snapshot_download(REPO, allow_patterns=["*.json", "*.txt", "*.py", "*.model"])
    sys.path.insert(0, local)
    from processing_char_bert_joint import CharBertJointProcessor
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = AutoModel.from_pretrained(REPO, trust_remote_code=True).eval().to(device)
    proc = CharBertJointProcessor.from_pretrained(local)
    examples = [json.loads(l) for l in (HERE / "examples.jsonl").read_text(encoding="utf-8").splitlines()]
    print(f"examples {len(examples)} device {device}", flush=True)
    t0 = time.time()
    with open(HERE / "example_pos.jsonl", "w", encoding="utf-8") as out:
        for i in range(0, len(examples), args.batch):
            chunk = examples[i:i + args.batch]
            words = [TOKEN.findall(e["greek"]) or ["."] for e in chunk]
            batch = proc(words)
            batch = {k: v.to(device) if hasattr(v, "to") else v for k, v in batch.items()}
            with torch.no_grad():
                res = model(**batch)
            for e, ws in zip(chunk, proc.decode(res, batch, ud=True)):
                out.write(json.dumps({"n": e["n"], "words": [{"form": w["form"], "lemma": w["lemma"], "upos": w["upos"]}
                                                             for w in ws]}, ensure_ascii=False) + "\n")
            if (i // args.batch) % 20 == 0:
                print(f"progress {i + len(chunk)}/{len(examples)} elapsed={time.time() - t0:.0f}s", flush=True)
    print(f"done seconds={time.time() - t0:.0f}", flush=True)


if __name__ == "__main__":
    main()
