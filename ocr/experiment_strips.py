"""Read chosen strips under several scales and prompts, to pick a retry policy.

    python experiment_strips.py --images ../svegrek --out exp.json --cases 0006:4,0008:2

Writes every variant's text and loop flag; score them with eval_runeberg.py
by substituting a variant into the page text (see --pilot).
"""

import argparse
import json
import time
from types import SimpleNamespace

from ocr_pages import PROMPTS, Model, log
from segment import load_grey, render, segment

ap = argparse.ArgumentParser()
ap.add_argument("--images", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--cases", required=True, help="PAGE:STRIP,... as numbered in a run's page JSON")
ap.add_argument("--scales", default="0.4,0.45,0.5,0.55,0.6")
ap.add_argument("--max-new-tokens", type=int, default=2048)
a = ap.parse_args()

model = Model(SimpleNamespace(model="CLLG/Qwen3VL-8B-synth_real", prompt="cllg", max_new_tokens=a.max_new_tokens))
results = []
for case in a.cases.split(","):
    page, n = case.split(":")
    grey = load_grey(f"{a.images}/{page}.tif")
    strip = [s for s in segment(grey, 0.5, 1024) if s.kind != "head"][int(n)]
    for prompt in PROMPTS:
        scales = [float(x) for x in a.scales.split(",")]
        images = [render(grey, strip, sc, 1024) for sc in scales]
        t0 = time.time()
        outs = model.transcribe(images, prompt)
        log(f"case {case} prompt={prompt} seconds={time.time() - t0:.1f} "
            + " ".join(f"{sc}:{'LOOP' if o['loop'] or o['hit_limit'] else 'ok'}/{o['new_tokens']}" for sc, o in zip(scales, outs)))
        for sc, im, o in zip(scales, images, outs):
            results.append({"page": page, "strip": int(n), "prompt": prompt, "scale": sc, "size": list(im.size), **o})
json.dump(results, open(a.out, "w"), ensure_ascii=False, indent=1)
log(f"wrote {len(results)} variants to {a.out}")
