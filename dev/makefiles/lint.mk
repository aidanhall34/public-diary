UV := UV_CACHE_DIR=/tmp/uv-cache UV_LINK_MODE=copy uv
PYTHON_ENV := . .venv/bin/activate && PYTHONPATH=dev/scripts

ruff: venv
	$(PYTHON_ENV) $(UV) run ruff check .

yamllint: venv
	$(PYTHON_ENV) $(UV) run yamllint .

.PHONY: ruff yamllint markdownlint

markdownlint:
	npx markdownlint --dot .
