.PHONY: ruff mypy yamllint jsonlint markdownlint

ruff: venv
	$(PYTHON_ENV) $(UV) run ruff check --preview .

mypy: venv
	mkdir -p dev/scripts/test_out
	$(PYTHON_ENV) $(UV) run mypy --html-report dev/scripts/test_out/mypy_html_report --linecoverage-report dev/scripts/test_out/mypy_linecoverage_report

yamllint: venv
	$(PYTHON_ENV) $(UV) run yamllint --strict .

jsonlint: venv
	$(PYTHON_TOOL) check-json

markdownlint:
	npx markdownlint --dot .
