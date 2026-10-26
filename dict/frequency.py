"""How common each headword is in Swedish today, for picking the day's word: the
Zipf frequency (log10 of occurrences per thousand million words) of its modern
spelling, as looked up for parts_of_speech.tsv, in wordfreq's Swedish data
(Wikipedia, subtitles, news, the web; https://github.com/rspeer/wordfreq).
Writes dict/frequency.tsv, read by app/build_app.py:

    pip install wordfreq
    python dict/frequency.py
"""

from __future__ import annotations

import csv
from pathlib import Path

from wordfreq import zipf_frequency

HERE = Path(__file__).resolve().parent


def main() -> None:
    rows = list(csv.DictReader((HERE / "parts_of_speech.tsv").open(encoding="utf-8"), delimiter="\t"))
    out = ["id\tmodern\tzipf\n"]
    for r in rows:
        out.append(f"{r['id']}\t{r['looked_up']}\t{zipf_frequency(r['looked_up'].lower(), 'sv'):.2f}\n")
    (HERE / "frequency.tsv").write_text("".join(out), encoding="utf-8")
    print(len(rows), "headwords ->", HERE / "frequency.tsv")


if __name__ == "__main__":
    main()
