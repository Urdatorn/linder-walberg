<p align="center">
  <img src="docs/screenshots.png" alt="The web app: the 1862 title page, and the entry Mörker" width="640">
</p>

> Nyttan, eller rättare nödvändigheten, af Grekiska Skriföfningar har under de sednare åren äfven hos oss blifvit allmänt insedd och erkänd.
>
> — C. W. Linder och C. A. Walberg, *Förord*, 1862

# Svenskt-grekiskt lexikon

A new digital edition of Carl Wilhelm Linder and Carl August Walberg's *Svenskt-grekiskt lexikon*
(Upsala 1862), the Swedish–Ancient Greek dictionary. It has some 26,000 entries, with Swedish
headwords in 1862 spelling and their Greek renderings. The text was read afresh from the page
images, proofread against them page by page, and corrected after the book's own list of misprints
and a systematic check of the Greek.

- **Web app**: [albinthorncleland.com/linder-walberg](https://albinthorncleland.com/linder-walberg/).
  - Search in Swedish (1862 or modern spelling) or Greek, with or without accents.
  - Favourites, a word of the day, the Index locorum, and the abbreviations explained on a tap.
  - Install it on an iPhone with Safari's *Lägg till på hemskärmen*; it then works offline.
- **macOS Dictionary.app**: see [`dict/`](dict/). StarDict and MDict editions, for dictionary apps
  on iOS, Android and Windows, are built by `dict/build_other.py`.
- **Dataset**: [huggingface.co/datasets/Urdatorn/linder-walberg](https://huggingface.co/datasets/Urdatorn/linder-walberg).
  It holds every page image with its diplomatic and corrected transcription, the text strip by
  strip and entry by entry, and every correction with its reason.
- **First electronic edition**: [runeberg.org/svegrek](https://runeberg.org/svegrek/), scanned by
  Johan Winge for Project Runeberg in January 2013 and given a first OCR in October that year.

## The text

Every page exists in two layers, aligned strip by strip:

- **diplomatic**: what the page prints, letter for letter, with accents, breathings and the
  printer's misprints;
- **corrected**: the same text with the editorial corrections applied, from three sources:
  - the book's own *Tryckfel* list;
  - misprints found in proofreading;
  - accent, breathing and spelling fixes to the Greek that formal rules or the attested corpus of
    Greek forms leave no doubt about.

The 1862 spelling is kept (*hvar*, *af*, *qvinna*). The search finds modern spellings too. The
book's abbreviations are explained where they occur, from its own list on p. 540.

## How it was made

| step | where | |
|---|---|---|
| OCR | [`ocr/`](ocr/) | Each page cut into strips and read by a vision-language model fine-tuned for Greek and Latin print ([CLLG/Qwen3VL-8B-synth_real](https://huggingface.co/CLLG/Qwen3VL-8B-synth_real)). Decoding was constrained so that Swedish headwords cannot come out in Greek letters. |
| cleaning | [`ocr/clean.py`](ocr/clean.py) | Word-level alignment with Runeberg's 2013 OCR, to settle the Swedish |
| proofreading | [`proof/`](proof/) | All 540 pages proofread strip by strip by language-model agents (Claude), each comparing the text with the page image |
| the Greek | [`ocr/greek_checks.py`](ocr/greek_checks.py), [`corrections/`](corrections/) | Checks of breathings, accents and their place, grave before a following word, enclitics, and attestation of every form in a 6.5-million-form lexicon and in LSJ |
| corrections | [`ocr/apply_corrections.py`](ocr/apply_corrections.py) | Each correction checked in context, and rejected if it adds a problem elsewhere |
| Index locorum | [`locorum/`](locorum/) | The Greek quotations traced to their sources by searching the Perseus and First1KGreek texts. They are cited by LSJ's names and abbreviations, and a quotation counts only if it has at least two nouns or verbs, as tagged by [Stoicheia](https://huggingface.co/Ericu950/Stoicheia-tagger-parser). There are 77 authors. |
| editions | [`dict/`](dict/), [`app/`](app/), [`hf/`](hf/) | Dictionary.app, StarDict, MDict, the web app and the dataset, all built from `text/corrected` |

The two authors have entries of their own, from *Svenskt biografiskt handlexikon* (1906), with
their portraits.

## Building

```sh
python dict/build_xml.py           # the Dictionary.app source; then `make install` in dict/src on a Mac
python dict/build_other.py         # StarDict and MDict
app/deploy.sh                      # build the web app and publish it (GitHub Pages, branch gh-pages)
python hf/build_dataset.py         # the Hugging Face dataset
```

## Thanks

- Johan Winge and Project Runeberg, for the first electronic edition and the page images.
- The Perseus Digital Library and First1KGreek, for the Greek texts behind the Index locorum.
- The Greek Font Society, for GFS Porson; SIL, for Gentium Book Plus.

The book is in the public domain. The transcription and corrections are released under
[CC0](https://creativecommons.org/publicdomain/zero/1.0/), as in the dataset.

Albin Thörn Cleland, Lund University ([albinthorncleland.com](https://albinthorncleland.com)).
