# Build the Linder-Walberg dictionary for macOS Dictionary.app.
#   make          generate the XML and compile the bundle
#   make install  copy it to ~/Library/Dictionaries
#   make release  zip the bundle for a GitHub release (../../dist/LinderWalberg-macOS.zip)
#   make dmg      a disk image to install it by dragging (../../dist/LinderWalberg-macOS.dmg)
# Needs Apple's Dictionary Development Kit ("Additional Tools for Xcode").

DICT_NAME      = LinderWalberg
DICT_SRC       = LinderWalberg.xml
DICT_CSS       = LinderWalberg.css
DICT_PLIST     = LinderWalberg.plist
DDK            ?= /Applications/Utilities/Dictionary Development Kit
BUILD_DICT     = "$(DDK)/bin/build_dict.sh"
INSTALL_DIR    = $(HOME)/Library/Dictionaries
export MACOSX_DEPLOYMENT_TARGET = 10.13
# build_dict.sh fetches the plist DTD over the network; use the local copy
export XML_CATALOG_FILES = $(CURDIR)/xml-catalog.xml

.PHONY: all xml install release dmg clean

all: xml
	$(BUILD_DICT) $(DICT_NAME) $(DICT_SRC) $(DICT_CSS) $(DICT_PLIST)
	rm -rf $(DICT_NAME).dictionary
	cp -R objects/$(DICT_NAME).dictionary ./

xml:
	python3 ../build_xml.py

install: all
	mkdir -p "$(INSTALL_DIR)"
	rm -rf "$(INSTALL_DIR)/$(DICT_NAME).dictionary"
	cp -R $(DICT_NAME).dictionary "$(INSTALL_DIR)/"
	@echo "Installed. Enable 'Svenskt-grekiskt lexikon' in Dictionary > Settings."

# ditto, not zip: it packs a bundle so that it unpacks intact on another Mac
release: all
	mkdir -p ../../dist
	rm -f ../../dist/$(DICT_NAME)-macOS.zip
	ditto -c -k --keepParent $(DICT_NAME).dictionary ../../dist/$(DICT_NAME)-macOS.zip
	@echo "Written: dist/$(DICT_NAME)-macOS.zip"

# for those who would rather drag than type: the lexicon, with the web app's LW as its
# icon, over a background that says how to install it (dmg/background.png, from
# ../dmg_background.py). No link to a dictionaries folder: each user has their own
# (~/Library/Dictionaries), which Ordbok's File menu opens. create-dmg (brew install
# create-dmg) lays out the window; without it the image holds the lexicon alone.
ICON = $(CURDIR)/../../app/src/icons/icon-512.png
dmg: all
	rm -rf dmg-root dmg-background.tiff ../../dist/$(DICT_NAME)-macOS.dmg
	mkdir -p dmg-root ../../dist
	cp -R $(DICT_NAME).dictionary dmg-root/
	osascript -l JavaScript -e 'ObjC.import("AppKit"); $$.NSWorkspace.sharedWorkspace.setIconForFileOptions($$.NSImage.alloc.initWithContentsOfFile("$(ICON)"), "$(CURDIR)/dmg-root/$(DICT_NAME).dictionary", 0)'
	if command -v create-dmg >/dev/null; then \
	    tiffutil -cathidpicheck dmg/background.png dmg/background@2x.png -out dmg-background.tiff && \
	    create-dmg --volname "Svenskt-grekiskt lexikon" --background dmg-background.tiff \
	        --window-size 640 400 --icon-size 128 --text-size 13 \
	        --icon $(DICT_NAME).dictionary 150 215 --hide-extension $(DICT_NAME).dictionary \
	        --no-internet-enable ../../dist/$(DICT_NAME)-macOS.dmg dmg-root; \
	else \
	    hdiutil create -volname "Svenskt-grekiskt lexikon" -srcfolder dmg-root -format UDZO \
	        ../../dist/$(DICT_NAME)-macOS.dmg; \
	fi
	rm -rf dmg-root dmg-background.tiff
	@echo "Written: dist/$(DICT_NAME)-macOS.dmg"

clean:
	rm -rf objects $(DICT_NAME).dictionary $(DICT_SRC) dmg-root dmg-background.tiff
