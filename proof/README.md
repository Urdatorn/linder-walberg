Proofreading of the cleaned OCR against the scans (see ocr/proof_kit.py).

- `strips/NNNN_SS.txt`: the text of each strip, one paragraph per entry; a
  first paragraph starting with "~ " continues the entry before it.
- `reports/NNNN.json`: the proofreader's report for page NNNN: corrections
  made, misprints kept as printed, and readings it could not settle. A page
  is proofread when its report exists; strips of other pages are the
  cleaned OCR as yet unchecked.
