UV := UV_CACHE_DIR=/tmp/uv-cache UV_LINK_MODE=copy uv
PYTHON_ENV := . .venv/bin/activate && PYTHONPATH=dev/scripts

.PHONY: venv ruff yamllint pytests

venv:
	$(UV) venv --python 3.13 --allow-existing .venv
	$(UV) sync --all-groups


pytests: venv
	$(PYTHON_ENV) $(UV) run pytest
