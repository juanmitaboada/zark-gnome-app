# zark-gnome-app - development and packaging targets.
#
# The tests need zark's reader and fixtures: ZARK_SRC is a zark checkout
# (CI checks out zark's tag). They run on the system's Python with its
# PyGObject, under Xvfb.

PKG := zark-gnome-app
VERSION := $(shell python3 -I -c "import re; print(re.search(r'VERSION = \"([^\"]+)\"', open('zark_app/__init__.py').read()).group(1))")
ZARK_SRC ?= ../zark
PYTHON ?= python3
VENV ?= build/venv
SERIES ?= noble resolute stonking
MIRROR ?= http://archive.ubuntu.com/ubuntu
POT := po/$(PKG).pot
APP_ID := com.juanmitaboada.Zark
LINGUAS := $(shell sed -e 's/\#.*//' po/LINGUAS)
I18N := build/i18n
# The desktop file's translated keys; Name is the product's, kept as is.
DESKTOP_KEYS := --keyword= --keyword=GenericName --keyword=Comment --keyword=Keywords

.PHONY: test screenshots lint venv pot po-risk i18n run dist deb deb-check deb-series deb-all release-guard deb-ppa clean

## test: the suite under Xvfb, on the system's Python and PyGObject
test:
	ZARK_SRC=$(ZARK_SRC) TZ=Europe/Madrid xvfb-run -a env GSK_RENDERER=cairo \
	    $(PYTHON) -m pytest -q -p no:cacheprovider

## screenshots: one PNG per state of the fixtures, in build/screenshots
screenshots:
	ZARK_SRC=$(ZARK_SRC) TZ=Europe/Madrid xvfb-run -a env GSK_RENDERER=cairo \
	    $(PYTHON) -m tests.screenshots build/screenshots

## venv: the pinned lint tools (pyproject's dependency groups)
venv:
	$(PYTHON) -m venv --system-site-packages $(VENV)
	@# --group needs pip 25.1; noble's venv brings 24.0.
	$(VENV)/bin/pip install -q --upgrade pip
	$(VENV)/bin/pip install -q --group dev
	$(VENV)/bin/pip install -q --no-deps --group stubs

## lint: ruff (check and format), mypy, pylint (after make venv)
lint:
	$(VENV)/bin/ruff check zark_app tests zark-gnome-app dev/run
	$(VENV)/bin/ruff format --check zark_app tests zark-gnome-app dev/run
	$(VENV)/bin/python -m mypy
	$(VENV)/bin/python -m pylint zark_app tests

## pot: the translation template from the sources listed in po/POTFILES.in
# One xgettext run for every kind: Python by its keywords, the desktop file's
# GenericName, Comment and Keywords (not Name: the product's), the metainfo by
# gettext's own rules, the polkit policy by po/its (the elements carrying
# gettext-domain). The template's creation date is dropped so it only changes
# with its strings.
pot:
	GETTEXTDATADIRS=po xgettext --from-code=UTF-8 --add-comments=TRANSLATORS: \
	    --keyword= --keyword=_ --keyword=N_ --keyword=ngettext:1,2 \
	    $(filter-out --keyword=,$(DESKTOP_KEYS)) \
	    --package-name=$(PKG) --package-version=$(VERSION) \
	    --msgid-bugs-address=https://github.com/juanmitaboada/zark-gnome-app/issues \
	    --files-from=po/POTFILES.in --output=$(POT)
	sed -i '/^"POT-Creation-Date: /d' $(POT)

## po-risk: the template's msgids that match po/RISK-WORDS, with their review in po/RISK-REVIEWED
po-risk:
	$(PYTHON) -I tests/potools.py risk

## i18n: the catalogues of po/LINGUAS, the desktop file and the metainfo with their translations, in build/i18n
i18n:
	@mkdir -p $(I18N)
	@for lang in $(LINGUAS); do \
	    mkdir -p $(I18N)/locale/$$lang/LC_MESSAGES; \
	    msgfmt -c -o $(I18N)/locale/$$lang/LC_MESSAGES/$(PKG).mo po/$$lang.po || exit 1; \
	done
	msgfmt --desktop $(DESKTOP_KEYS) --template data/$(APP_ID).desktop.in -d po -o $(I18N)/$(APP_ID).desktop
	msgfmt --xml --template data/$(APP_ID).metainfo.xml.in -d po -o $(I18N)/$(APP_ID).metainfo.xml

## run: the app from this tree against a fixture case (CASE=app:connected)
run:
	ZARK_SRC=$(ZARK_SRC) $(PYTHON) -I dev/run $(CASE)

# Debian package (PPA), as zark's and the extension's: the .orig is the
# tracked tree without debian/ and .github/; the binary is built from the
# source package as Launchpad gets it.
ORIG_TARBALL := ../$(PKG)_$(VERSION).orig.tar.gz
PPA_TABLE := noble:24.04 resolute:26.04 stonking:26.10
PPA_DPUT_TGT := zark-ppa
# deb-ppa's per-series revision -1~ubuntuXX.YY.1 reads to lintian as an old-style
# binary NMU; the app makes none. Suppressed here, not overridden in the package,
# so the plain -1 builds print no unused-override.
LINTIAN_SUPPRESS_TAGS := bad-distribution-in-changes-file,binary-nmu-debian-revision-in-source
DPUT ?= dput

## dist: the upstream tarball, tracked files without debian/ and .github/, at the commit's time
dist:
	git archive --format=tar --prefix=$(PKG)-$(VERSION)/ HEAD -- . ':(exclude)debian' ':(exclude).github' | gzip -n > $(ORIG_TARBALL)
	@echo "  $(ORIG_TARBALL)"

## deb: the unsigned .deb on this machine's series, from the source package, with lintian on both
deb: dist
	@command -v debuild >/dev/null || { echo "  debuild not installed: sudo apt install devscripts debhelper"; exit 1; }
	@set -e; tmp=$$(mktemp -d); trap 'rm -rf "$$tmp"' EXIT INT TERM; \
	cp $(ORIG_TARBALL) "$$tmp/"; \
	mkdir "$$tmp/src"; \
	tar -xzf $(ORIG_TARBALL) -C "$$tmp/src" --strip-components=1; \
	git ls-files -z debian | tar --null -T - -cf - | tar -xf - -C "$$tmp/src"; \
	(cd "$$tmp/src" && dpkg-source -b .); \
	dpkg-source -x "$$tmp"/$(PKG)_$(VERSION)-*.dsc "$$tmp/build"; \
	(cd "$$tmp/build" && debuild -us -uc -b --lintian-opts --suppress-tags $(LINTIAN_SUPPRESS_TAGS)); \
	lintian --suppress-tags $(LINTIAN_SUPPRESS_TAGS) "$$tmp"/$(PKG)_$(VERSION)-*.dsc; \
	cp "$$tmp"/$(PKG)_$(VERSION)-*_all.deb ..
	@echo "  Built: $$(ls -1t ../$(PKG)_$(VERSION)-*_all.deb | head -1)"
	@$(MAKE) --no-print-directory deb-check DEB="$$(ls -1t ../$(PKG)_$(VERSION)-*_all.deb | head -1)"

## deb-check: the launcher in a built .deb (DEB=...) kept its isolated-mode shebang
deb-check:
	@line=$$(dpkg-deb --fsys-tarfile "$(DEB)" | tar -xOf - ./usr/share/$(PKG)/$(PKG) | head -n 1); \
	test "$$line" = '#!/usr/bin/python3 -I' || { echo "  $(DEB): the launcher's shebang is '$$line'"; exit 1; }; \
	echo "  Shebang: $$line"

## deb-all: the .deb built in a clean chroot of each series (mmdebstrap, as root), into build/deb/<series>
deb-all: dist
	@for series in $(SERIES); do $(MAKE) --no-print-directory deb-series S=$$series || exit 1; done

deb-series:
	@set -e; root=build/chroot-$(S); out=build/deb/$(S); mkdir -p $$out; \
	test -d $$root || mmdebstrap --variant=buildd --components=main,universe \
	    --include=debhelper,dh-python,python3,desktop-file-utils,appstream,gettext,lintian,devscripts \
	    $(S) $$root "deb $(MIRROR) $(S) main universe"; \
	rm -rf $$root/build && mkdir -p $$root/build/src; \
	cp $(ORIG_TARBALL) $$root/build/; \
	tar -xzf $(ORIG_TARBALL) -C $$root/build/src --strip-components=1; \
	git ls-files -z debian | tar --null -T - -cf - | tar -xf - -C $$root/build/src; \
	chroot $$root sh -c 'cd /build/src && dpkg-source -b . >/dev/null && cd /build && dpkg-source -x $(PKG)_$(VERSION)-*.dsc pkg >/dev/null && cd pkg && dpkg-buildpackage -us -uc -b >/build/build.log 2>&1 || { tail -40 /build/build.log; exit 1; }; cd /build && lintian --suppress-tags $(LINTIAN_SUPPRESS_TAGS) $(PKG)_$(VERSION)-*_all.deb $(PKG)_$(VERSION)-*.dsc'; \
	cp $$root/build/$(PKG)_$(VERSION)-*_all.deb $$out/; \
	echo "  $(S): $$(ls $$out)"; \
	$(MAKE) --no-print-directory deb-check DEB="$$(ls -1t $$out/$(PKG)_$(VERSION)-*_all.deb | head -1)"

## release-guard: refuse a tree that is dirty, not at a signed tag v$(VERSION), or whose changelog is not this version's
release-guard:
	@test -z "$$(git status --porcelain)" || { echo "  The tree has uncommitted or untracked files"; git status --short; exit 1; }
	@test "$$(git describe --exact-match --tags HEAD 2>/dev/null)" = "v$(VERSION)" || { echo "  HEAD is not the tag v$(VERSION)"; exit 1; }
	@git verify-tag "v$(VERSION)" >/dev/null 2>&1 || { echo "  The tag v$(VERSION) has no valid signature: git tag -s"; exit 1; }
	@head -1 debian/changelog | grep -qv ' UNRELEASED;' || { echo "  debian/changelog's top entry is UNRELEASED"; exit 1; }
	@top=$$(head -1 debian/changelog | sed -nE 's/^[^ ]+ \(([^)]+)\).*/\1/p'); \
	test "$${top%-*}" = "$(VERSION)" || { echo "  debian/changelog's top entry is $$top, not $(VERSION)-<revision>"; exit 1; }

## deb-ppa: a signed source package per series, uploaded to the PPA (from the signed tag only; on the maintainer's machine)
deb-ppa: release-guard dist
	@command -v $(DPUT) >/dev/null || { echo "  $(DPUT) not installed: sudo apt install dput-ng"; exit 1; }
	$(eval GPG_KEYID := $(shell gpg --list-secret-keys --with-colons juanmi@juanmitaboada.com 2>/dev/null | awk -F: 'BEGIN{want=0;u="";v=""} $$1=="sec" {want=($$2=="u")?1:(($$2=="-")?2:0); next} $$1=="fpr" && want==1 && !u {u=$$10} $$1=="fpr" && want==2 && !v {v=$$10} END{print (u ? u : v)}'))
	@test -n "$(GPG_KEYID)" || { echo "  No usable GPG secret key for juanmi@juanmitaboada.com"; exit 1; }
	@echo "  This builds and uploads $(PKG) $(VERSION) for: $(PPA_TABLE) to $(PPA_DPUT_TGT) with $(DPUT)."
	@read -r -p "  Continue? [y/N] " ans && [ "$$ans" = "y" ] || { echo "  Aborted."; exit 1; }
	@# The changelog backup lives outside the tree: dh_clean deletes *.bak.
	@set -e; \
	backup=$$(mktemp -t $(PKG)-changelog-XXXXXX); \
	cp debian/changelog "$$backup"; \
	trap 'cp -f "$$backup" debian/changelog 2>/dev/null || true; rm -f "$$backup" debian/files' EXIT INT TERM; \
	for entry in $(PPA_TABLE); do \
		series="$${entry%%:*}"; release="$${entry#*:}"; \
		version="$(VERSION)-1~ubuntu$$release.1"; \
		echo ""; echo "  -- $$series ($$version) --"; \
		cp "$$backup" debian/changelog; \
		DEBEMAIL="juanmi@juanmitaboada.com" DEBFULLNAME="Juanmi Taboada" \
		    dch --newversion "$$version" --distribution "$$series" \
		        --force-distribution --force-bad-version "Build for Ubuntu $$series."; \
		head -6 debian/changelog; \
		debuild -S -sa -us -uc --lintian-opts --suppress-tags $(LINTIAN_SUPPRESS_TAGS); \
		rm -f debian/files; \
		debsign -k$(GPG_KEYID) "../$(PKG)_$${version}_source.changes"; \
		head -1 "../$(PKG)_$${version}_source.changes" | grep -q "BEGIN PGP SIGNED MESSAGE" \
		    || { echo "  ERROR: the .changes is not signed"; exit 1; }; \
		rm -f "../$(PKG)_$${version}_source.$(PPA_DPUT_TGT).upload"; \
		$(DPUT) -c dput.cf $(PPA_DPUT_TGT) "../$(PKG)_$${version}_source.changes"; \
	done

## clean: what the targets above leave in build/ (the chroots included)
clean:
	rm -rf build
