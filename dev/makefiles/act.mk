ACT_PLATFORM_UBUNTU_24_04 := catthehacker/ubuntu:act-latest
ACT_DEPLOY_FLAGS := -P ubuntu-24.04=$(ACT_PLATFORM_UBUNTU_24_04)
ACT_DIR := dev/act
ACT_VAR_FILE := $(ACT_DIR)/vars.env
ACT_SECRET_FILE := $(ACT_DIR)/secrets.env

.PHONY: act-files act-test-publish act-test-sync-wiki act-run-publish

act-files: provision-act-files

act-test-publish: act-files
	act push -W .github/workflows/deploy-pages.yml -j build -n $(ACT_DEPLOY_FLAGS) --var-file $(ACT_VAR_FILE) --secret-file $(ACT_SECRET_FILE)

act-test-sync-wiki: act-files
	act push -W .github/workflows/sync-wiki.yml -j publish-wiki -n --secret-file $(ACT_SECRET_FILE)

act-run-publish: act-files
	act push -W .github/workflows/deploy-pages.yml -j build $(ACT_DEPLOY_FLAGS) --var-file $(ACT_VAR_FILE) --secret-file $(ACT_SECRET_FILE)
