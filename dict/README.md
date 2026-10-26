# Svenskt-grekiskt lexikon for Dictionary.app

Linder & Walberg's Swedish–Ancient Greek dictionary (Upsala 1862) as a macOS
dictionary, built from the proofread and corrected text in `../text/corrected`.

On a Mac with Apple's Dictionary Development Kit (from "Additional Tools for
Xcode"):

    cd dict/src
    make install          # or: make DDK="/path/to/Dictionary Development Kit" install

then enable "Svenskt-grekiskt lexikon" in Dictionary > Settings. `make`
first runs `build_xml.py` (Python 3, standard library only) to write
`LinderWalberg.xml`.

What the build does with the book's conventions:

- headwords as entries, with variant forms indexed ("Nedanför(e)",
  "Nedanifrån, -igenom"); every Greek equivalent is indexed too, so a Greek
  word finds the Swedish entries that render it
- sense numbers I) 1) a) α) as nested, numbered blocks
- the book's ".:" phrase separator as one phrase per line
- "— glödande, …" derivatives as run-in sub-entries
- Greek in a polytonic serif; grammatical abbreviations in italics, every
  abbreviation expanded on hover from the book's own list (`abbreviations.tsv`)
- the headword's initial standing for the headword ("göra a.") marked and expanded
- "se X", "Jfr X" as links; "se Föreg.", "se Följ." to the neighbouring entries
- the preface, the list of abbreviations, the Index locorum and the two authors (from Svenskt biografiskt handlexikon, with portraits) as front matter

`contractions.tsv` adds the contracted forms the book uses beyond its own list of
abbreviations, mostly built on the list's stems: *smnsättning* (smn = samman), *mskrs*
(mskr = menniskor), *sdnt* (sdn = sådan), *ngns*, *fhdt*, *begrpt* (begreppet), *hkn*
(hvilken), *hd* (hvad). They get the same note as the listed abbreviations; the
*Förkortningar* page shows the book's list alone. "hr" as the first part of a word
(hrifrån, hrandra) is expanded by rule in `build_xml.py`.

`parts_of_speech.tsv` (from `parts_of_speech.py`, with SALDO's morphology) gives each
headword its part of speech, for the *Partes orationis* pages. `frequency.tsv` (from
`frequency.py`, with [wordfreq](https://github.com/rspeer/wordfreq)'s Swedish data) gives
how common each headword is in modern spelling today; the web app takes its *Dagens ord*
from the rare ones.
