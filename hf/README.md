---
language:
- sv
- grc
license: cc0-1.0
task_categories:
- image-to-text
tags:
- ocr
- htr
- ancient-greek
- polytonic-greek
- swedish
- lexicography
- dictionary
- critical-edition
- multilingual
pretty_name: Linder & Walberg, Svenskt-grekiskt lexikon (1862)
size_categories:
- 1K<n<10K
configs:
- config_name: pages
  default: true
  data_files:
  - split: train
    path: pages/train-*
- config_name: strips
  data_files:
  - split: train
    path: strips/train-*
- config_name: entries
  data_files:
  - split: train
    path: entries/train-*
- config_name: corrections
  data_files:
  - split: train
    path: corrections/train-*
---

# Linder & Walberg, *Svenskt-grekiskt lexikon* (1862)

Page images and a proofread transcription of Carl Linder and Carl Walberg's
Swedish–Ancient Greek dictionary (Uppsala 1862, 535 printed pages + front
matter): Swedish headwords in 1862 spelling, polytonic Greek equivalents in
an italic Greek face, roman and spaced type, sense numbering, dense
abbreviation. A hard, real-world test of multilingual, mixed-script OCR of
critical and lexicographic printing, with two layers of text for every page:

- **diplomatic**: what the page prints, letter for letter, accents and
  breathings included, the printer's misprints kept;
- **corrected**: the same text with the editorial corrections applied (the
  book's own *Tryckfel* list, misprints found in proofreading, and
  orthographic fixes of the Greek), aligned strip by strip with the
  diplomatic text.

## Configurations

| config | rows | one row per |
|---|---|---|
| `pages` (default) | 540 | scanned page: image, raw OCR, diplomatic and corrected text |
| `strips` | 3,267 | strip (a column section or heading) with its box and crop |
| `entries` | 26,237 | dictionary entry (pages 5–539), diplomatic and corrected |
| `corrections` | 9,791 | finding from proofreading and the formal checks, with its decision |

`pages`: `page` (scan number, `0001`–`0540`), `printed_page` (scan − 4 for the
dictionary pages), `section` (`front_matter`, `dictionary`, `back_matter`),
`image` (600 dpi bilevel PNG, from the Group 4 TIFF), `text_diplomatic`,
`text_corrected`, `text_ocr_raw` (the vision model's output before any
cleaning, in its pseudo-Markdown), `proofreading_corrections` (how many
changes the proofreader made on the page).

`strips`: `strip` (`NNNN_SS`), `kind` (`col`, `span`, `page`), `column`
(1, 2, or 0 for full width), `box` (left, top, right, bottom in scan pixels),
`image` (the crop), `continues` (the strip opens mid-entry), `text_diplomatic`,
`text_corrected`. This is the unit the text was proofread in, so image and
text match exactly; the strips are the natural training pairs.

`entries`: `headword`, `page`, `strips` (where the entry was read),
`text_diplomatic`, `text_corrected`.

`corrections`: `category` (`errata`: the book's Tryckfel list; `auto`:
mechanical fixes; `misprint`: reported by the proofreaders; `diacritic`,
`rules`, `letter`: formal checks of the Greek; `headword`, `uncertain`,
`unknown`: recorded, not changed), `printed`, `proposal`, `decision`,
`status` (`applied`, `kept`, `overlap`, `not_found`), `page`, `strip`,
`entry`, `note`, `context`.

## Text conventions

- One paragraph per dictionary entry, the whole entry on one line; entries
  separated by a blank line. In `strips`, `continues` marks a strip whose first
  paragraph continues the entry above it.
- Words hyphenated at line ends are joined; real hyphens (prefixes and endings
  cited as such, `ἀπο-, ἐκ-`; Swedish suspended compounds) are kept.
- Letterspaced type is written without the spaces; no markup for italics,
  bold or spacing. Unicode NFC.
- Running heads and page numbers are not transcribed.

## How it was made

1. **OCR**: each page was cut into strips at blank rows (`ocr/segment.py`)
   and read by [CLLG/Qwen3VL-8B-synth_real](https://huggingface.co/CLLG/Qwen3VL-8B-synth_real),
   a Qwen3-VL model fine-tuned for Greek and Latin critical editions, with a
   prompt naming the book's Swedish and a logits constraint that forbids
   Greek letters in headwords (the model otherwise read the bold Swedish
   headwords as Greek, "Ηάρφιν" for *Hårfin*). That is `text_ocr_raw`.
2. **Cleaning**: markup removed, and a word-by-word alignment with Project
   Runeberg's 2013 OCR of the same scans, which reads Swedish and punctuation
   well and Greek badly, restored Swedish words read as Greek, the 1862
   spellings the model modernised, and the book's `.:` separator.
3. **Proofreading**: every strip of every page was compared with the scan at
   450 dpi by an AI agent (Claude), word by word and accent by accent, with
   hints from a lexicon check of the Greek. On the five pages that have a
   human-verified reference (0005–0009) the character error rate fell from
   1.86% (raw OCR) to 1.03% (cleaned) to 0.14% (proofread); doubtful readings
   on those pages were settled against a physical copy.
4. **Corrections**: formal checks of the Greek (breathings, accents, the grave
   rule, accent position, attestation in a 6.5-million-form Ancient Greek
   corpus and in LSJ) and the proofreaders' misprint reports gave the
   editorial layer; the `corrections` config records every finding.

The diplomatic text has been read once against the scans and is not free of
errors: residual rates are of the order of the 0.14% measured on the
reference pages, mostly accents and breathings. The `uncertain` rows in
`corrections` list readings the proofreaders could not settle from the scan.

## Source and licence

The book is in the public domain. The scans are Project Runeberg's
([runeberg.org/svegrek](https://runeberg.org/svegrek/)), released there
without restriction. The transcription, corrections and this packaging are
dedicated to the public domain (CC0 1.0).

Prepared by Albin Thörn Cleland (Lund University) for a macOS Dictionary.app
edition of the lexicon; code at
[github.com/Urdatorn/linder-walberg](https://github.com/Urdatorn/linder-walberg).
