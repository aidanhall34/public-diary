.PHONY: python-help python-tool

python-help: venv
	@if [ -n "$(TOOL)" ]; then \
		$(PYTHON_TOOL) "$(TOOL)" --help; \
	else \
		$(PYTHON_TOOL) --help; \
	fi

python-tool: venv
	$(PYTHON_TOOL) $(ARGS)
