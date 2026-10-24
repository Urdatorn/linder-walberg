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
- the preface and the list of abbreviations as front matter
