HOOKS_DIR := .githooks
ROOT_PACKAGE_JSON := package.json
ROOT_PACKAGE_LOCK := package-lock.json
VAULT_DIR := vault

.PHONY: repo-setup repo-root-deps

repo-setup:
	mkdir -p "$(VAULT_DIR)" "$(HOOKS_DIR)" docs .github/workflows
	chmod +x "$(HOOKS_DIR)/pre-commit" "$(HOOKS_DIR)/commit-msg"
	git config core.hooksPath "$(HOOKS_DIR)"
	@$(MAKE) repo-root-deps

repo-root-deps:
	@if [ -f "$(ROOT_PACKAGE_LOCK)" ]; then \
		npm ci; \
	elif [ -f "$(ROOT_PACKAGE_JSON)" ]; then \
		npm install; \
	fi
