.PHONY: python-tools provision-auth provision-drive-access provision-act-vars provision-github-vars provision-discord-webhook-file provision-github-secrets provision-act-drive-token provision-act-files

python-tools:
	$(PYTHON_ENV) $(UV) run python -m public_diary_tools.cli print-tool-help

provision-auth:
	$(PYTHON_ENV) $(UV) run python -m public_diary_tools.cli provision-auth

provision-drive-access:
	$(PYTHON_ENV) $(UV) run python -m public_diary_tools.cli configure-drive-access

provision-act-vars:
	$(PYTHON_ENV) $(UV) run python -m public_diary_tools.cli write-act-vars

provision-github-vars:
	$(PYTHON_ENV) $(UV) run python -m public_diary_tools.cli upload-github-vars

provision-discord-webhook-file:
	$(PYTHON_ENV) $(UV) run python -m public_diary_tools.cli write-discord-webhook

provision-github-secrets:
	$(PYTHON_ENV) $(UV) run python -m public_diary_tools.cli upload-github-secrets

provision-act-drive-token:
	$(PYTHON_ENV) $(UV) run python -m public_diary_tools.cli write-act-drive-token

provision-act-files:
	$(PYTHON_ENV) $(UV) run python -m public_diary_tools.cli write-act-files
