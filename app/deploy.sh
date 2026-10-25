#!/bin/sh
# Build the app and publish it at both its addresses:
#   https://albinthorncleland.com/linder-walberg/   GitHub Pages, branch gh-pages of this repository
#   https://urdatorn-linder-walberg.static.hf.space  the Hugging Face Space Urdatorn/linder-walberg
set -e
cd "$(dirname "$0")/.."
PY=.venv-x86/bin/python
$PY app/build_app.py

$PY -c "
from huggingface_hub import HfApi
HfApi().upload_folder(folder_path='app/dist', repo_id='Urdatorn/linder-walberg', repo_type='space',
                      commit_message='Build from $(git rev-parse --short HEAD)')"

PAGES=$(mktemp -d)
cp -r app/dist/. "$PAGES"
rm "$PAGES/README.md"                     # the Space's card
touch "$PAGES/.nojekyll"
git -C "$PAGES" init -q -b gh-pages
git -C "$PAGES" -c user.email="al1808th-s@student.lu.se" -c user.name="Albin Thörn Cleland" add -A
git -C "$PAGES" -c user.email="al1808th-s@student.lu.se" -c user.name="Albin Thörn Cleland" \
    commit -q -m "Build from $(git rev-parse --short HEAD)"
git -C "$PAGES" push -q -f git@github.com:Urdatorn/linder-walberg.git gh-pages
rm -rf "$PAGES"
echo "deployed to the Space and to gh-pages"
