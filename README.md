<p align="center">
  <img src="docs/screenshots.png" alt="The web app: the 1862 title page, and the entry Mörker" width="640">
</p>

# Svenskt-grekiskt lexikon

> _Nyttan, eller rättare nödvändigheten, af Grekiska Skriföfningar har under de sednare åren äfven hos oss blifvit allmänt insedd och erkänd._
>
> — C. W. Linder och C. A. Walberg, *Förord*, 1862

Carl Wilhelm Linder och Carl August Walbergs klassiska skrivövningslexikon från 1862 skannades in av Johan Winge 2013 och lades till på Projekt Runeberg, men OCR-teknologin var då långt från redo för 
textens utmanande blandning av polytonisk grekiska, gammelstavad svenska och idiosynkratiska förkortningar, 
och i princip bara de tjugosextusen huvudorden gjordes maskinläsbara och alltså sökbara. 
På tretton år korrlästes bara de första fem sidorna på Projekt Runeberg.

Två huvudsakliga tekniska framsteg gjorde det möjligt att relativt enkelt för en person att genomföra en komplett OCR och korrläsning av hela texten år 2026. För det första så har det kommit öppna OCR-modeller som är finetunade för antik grekiska ([Angleraud et al 2026](https://arxiv.org/abs/2603.02803)), och för det andra så kan man förhållandevis snabbt dubbelkolla den öppna modellens resulterande OCR-text från alla 536 sidor mot källbilderna med en svärm av Claude-agenter.

 The text was read afresh from the page
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

## Acknowledgments

Computational resources were provided by the National Academic Infrastructure for Supercomputing in Sweden (NAISS), funded by the Swedish Research Council.

The _Index locorum_ was built referencing texts from the Perseus Digital Library and First1KGreek.
The font GFS Porson is due to The Greek Font Society; Gentium Book Plus to SIL.

## Licence

The book is in the public domain. The transcription and corrections are released under
[CC0](https://creativecommons.org/publicdomain/zero/1.0/).

This digital edition is a project by [Albin Thörn Cleland](https://albinthorncleland.com), doctoral student in the Swedish Graduate School of Digital Philology at [Lund University](https://www.sol.lu.se/person/AlbinThornCleland/).
