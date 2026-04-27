.PHONY: docs-readme-sync docs-commands docs-generated-check

docs-readme-sync:
	cp README.md docs/README.md

docs-commands: venv
	$(PYTHON_ENV) $(UV) run python -m public_diary_tools.cli write-commands-doc

docs-generated-check:
	@if ! git diff --quiet -- docs; then \
		printf '%s\n' \
			'Generated docs changed during pre-commit.' \
			'Stage the updated docs and recommit.'; \
		exit 1; \
	fi
