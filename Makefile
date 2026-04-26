SHELL := /usr/bin/env bash

include dev/makefiles/repo.mk
include dev/makefiles/quartz.mk
include dev/makefiles/drive.mk
include dev/makefiles/docs.mk
include dev/makefiles/act.mk

.PHONY: setup pre-commit build serve

setup: repo-setup quartz-bootstrap quartz-deps quartz-configure

pre-commit: docs-readme-sync

test: act-test-publish act-test-sync-wiki

build: notes-clone quartz-build

serve: notes-clone quartz-serve
