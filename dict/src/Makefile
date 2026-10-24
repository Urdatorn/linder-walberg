# Build the Linder-Walberg dictionary for macOS Dictionary.app.
#   make          generate the XML and compile the bundle
#   make install  copy it to ~/Library/Dictionaries
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

.PHONY: all xml install clean

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

clean:
	rm -rf objects $(DICT_NAME).dictionary $(DICT_SRC)
