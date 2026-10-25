#!/bin/sh
# Build the app and publish it at https://albinthorncleland.com/linder-walberg/
# (GitHub Pages: the branch gh-pages of this repository, under the site's domain).
set -e
cd "$(dirname "$0")/.."
.venv-x86/bin/python app/build_app.py
PAGES=$(mktemp -d)
cp -r app/dist/. "$PAGES"
git -C "$PAGES" init -q -b gh-pages
git -C "$PAGES" -c user.email="al1808th-s@student.lu.se" -c user.name="Albin Thörn Cleland" add -A
git -C "$PAGES" -c user.email="al1808th-s@student.lu.se" -c user.name="Albin Thörn Cleland" \
    commit -q -m "Build from $(git rev-parse --short HEAD)"
git -C "$PAGES" push -q -f git@github.com:Urdatorn/linder-walberg.git gh-pages
rm -rf "$PAGES"
echo "deployed: https://albinthorncleland.com/linder-walberg/"
