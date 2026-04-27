.PHONY: docs-readme-sync docs-commands docs-wiki-stage docs-generated-check

docs-readme-sync:
	cp README.md docs/README.md

docs-commands: venv
	$(PYTHON_TOOL) write-commands-doc

docs-wiki-stage: venv
	$(PYTHON_TOOL) stage-wiki-docs

docs-generated-check:
	@if ! git diff --quiet -- docs; then \
		printf '%s\n' \
			'Generated docs changed during pre-commit.' \
			'Stage the updated docs and recommit.'; \
		exit 1; \
	fi
