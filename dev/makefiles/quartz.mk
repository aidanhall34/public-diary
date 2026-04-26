QUARTZ_DIR := quartz
QUARTZ_REPO := https://github.com/jackyzha0/quartz.git
QUARTZ_REF := v4
CONTENT_DIR := $(QUARTZ_DIR)/content
PUBLIC_DIR := $(QUARTZ_DIR)/public
PACKAGE_JSON := $(QUARTZ_DIR)/package.json
PACKAGE_LOCK := $(QUARTZ_DIR)/package-lock.json
RSYNC_EXCLUDES := \
	--exclude='.obsidian/' \
	--exclude='.trash/' \
	--exclude='.DS_Store'

.PHONY: quartz-bootstrap quartz-configure quartz-deps quartz-stage quartz-build quartz-serve quartz-clean

quartz-bootstrap:
	@if [ -f "$(PACKAGE_JSON)" ]; then \
		mkdir -p "$(CONTENT_DIR)"; \
	elif [ ! -e "$(QUARTZ_DIR)" ]; then \
		git clone --branch "$(QUARTZ_REF)" --single-branch "$(QUARTZ_REPO)" "$(QUARTZ_DIR)"; \
	else \
		echo "$(QUARTZ_DIR) exists but is not an initialized Quartz checkout."; \
		echo "Remove it or populate it with Quartz before continuing."; \
		exit 1; \
	fi

quartz-configure: quartz-bootstrap
	node scripts/configure-quartz.mjs

quartz-deps: quartz-bootstrap repo-root-deps
	@if [ -f "$(PACKAGE_LOCK)" ]; then \
		cd "$(QUARTZ_DIR)" && npm ci; \
	elif [ -f "$(PACKAGE_JSON)" ]; then \
		cd "$(QUARTZ_DIR)" && npm install; \
	else \
		echo "Missing $(PACKAGE_JSON)."; \
		exit 1; \
	fi

quartz-stage: quartz-bootstrap repo-setup
	test -d "$(VAULT_DIR)"
	rm -rf "$(CONTENT_DIR)"
	mkdir -p "$(CONTENT_DIR)"
	rsync -a --delete $(RSYNC_EXCLUDES) "$(VAULT_DIR)/" "$(CONTENT_DIR)/"

quartz-build: quartz-stage quartz-deps quartz-configure
	cd "$(QUARTZ_DIR)" && npx quartz build

quartz-serve: quartz-stage quartz-deps quartz-configure
	cd "$(QUARTZ_DIR)" && npx quartz build --serve

quartz-clean:
	rm -rf "$(CONTENT_DIR)" "$(PUBLIC_DIR)"
