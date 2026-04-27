UV := UV_CACHE_DIR=/tmp/uv-cache UV_LINK_MODE=copy uv
PYTHON_ENV := . .venv/bin/activate && PYTHONPATH=dev/scripts
PYTHON_TOOL := $(PYTHON_ENV) $(UV) run python -m public_diary_tools.cli

.PHONY: venv ruff mypy yamllint jsonlint pytests coverage-badge

venv:
	$(UV) venv --python 3.13 --allow-existing .venv
	$(UV) sync --all-groups


pytests: venv
	$(PYTHON_ENV) $(UV) run pytest

coverage-badge: venv
	$(PYTHON_TOOL) coverage-badge
