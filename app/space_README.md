---
title: Svenskt-grekiskt lexikon
emoji: 📖
colorFrom: yellow
colorTo: red
sdk: static
app_file: index.html
pinned: false
hf_oauth: true
hf_oauth_scopes:
  - contribute-repos
hf_oauth_expiration_minutes: 43200
license: cc0-1.0
short_description: Linder & Walberg, Svenskt-grekiskt lexikon (1862)
---

C. W. Linder och C. A. Walberg, *Svenskt-grekiskt lexikon* (Upsala 1862), as a web app for the
iPhone: open it in Safari and choose "Lägg till på hemskärmen". It works offline once installed.

Built from https://github.com/Urdatorn/linder-walberg (`app/build_app.py`); the text and page
images are at https://huggingface.co/datasets/Urdatorn/linder-walberg. Greek in GFS Porson
(Greek Font Society) and Swedish in Gentium Book Plus (SIL), both under the SIL Open Font License.

Favourites are kept on the device. Signing in with Hugging Face (under Om) is optional: the app then
keeps them in a private dataset it creates in the reader's account (`<user>/linder-walberg-favoriter`),
so that they follow between devices; the scope `contribute-repos` reaches only repositories the app created.
