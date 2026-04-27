CHECKMAKE_FILES := $(shell find . \
	-path ./.git -prune -o \
	-path ./.venv -prune -o \
	-path ./node_modules -prune -o \
	-path ./quartz -prune -o \
	\( -name Makefile -o -name '*.mk' -o -name '*.make' \) -print | sort)
CHECKMAKE := go run github.com/checkmake/checkmake/cmd/checkmake@latest

.PHONY: checkmake

checkmake:
	$(CHECKMAKE) $(CHECKMAKE_FILES)
