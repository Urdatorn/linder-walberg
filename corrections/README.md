The editorial layer. The text in `text/` and `proof/` is diplomatic (as
printed, misprints included); these files say what to change, and where,
when the dictionary is built.

- `errata.tsv`: the book's own Tryckfel list (page 535) anchored to its
  entries, and misprints confirmed in a physical copy.
- `auto.tsv`: obvious fixes from `ocr/errata.py`: an acute before another
  Greek word made grave, and forms one diacritic away from a form attested
  at least 1000 times (and 100 times as often) in the AncientGreek corpus.
- `review.json`: everything else, for a person to decide: proofreaders'
  misprint reports, rarer diacritic and one-letter suspects, accent-rule
  breaches, headwords out of order, uncertain readings, unattested words.
  It is reviewed in the "Linder–Walberg errata" artifact, whose decisions
  are read back into this directory.
