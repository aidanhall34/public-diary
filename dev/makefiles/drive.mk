LOCK_FILE := $(HOME)/.cache/public-diary-notes-clone.lock
GOOGLE_DRIVE_REMOTE ?= obsidian-gdrive
GOOGLE_DRIVE_PATH ?= obs-notes/obs-notes/

.PHONY: notes-clone

notes-clone: repo-setup
	mkdir -p "$(VAULT_DIR)" "$(dir $(LOCK_FILE))"
	flock -n "$(LOCK_FILE)" rclone copy \
			"$(GOOGLE_DRIVE_REMOTE):$(GOOGLE_DRIVE_PATH)" \
			"$(VAULT_DIR)/" \
			--drive-skip-gdocs \
			--create-empty-src-dirs \
			--log-level "INFO" \
			--exclude ".obsidian/**" \
			--exclude ".trash/**"
