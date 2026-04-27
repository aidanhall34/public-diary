SHELL := /usr/bin/env bash

include dev/makefiles/repo.mk
include dev/makefiles/quartz.mk
include dev/makefiles/drive.mk
include dev/makefiles/docs.mk
include dev/makefiles/python.mk
include dev/makefiles/checkmake.mk
include dev/makefiles/lint.mk
include dev/makefiles/act.mk
include dev/makefiles/provisioning.mk

.PHONY: setup pre-commit lint test build serve

setup: repo-setup quartz-bootstrap quartz-deps quartz-configure

pre-commit: pytests lint docs-commands coverage-badge docs-readme-sync docs-generated-check

lint: ruff mypy yamllint jsonlint checkmake markdownlint

test: pytests checkmake act-test-pr-validation act-test-publish act-test-sync-wiki

build: notes-clone quartz-build

serve: notes-clone quartz-serve
