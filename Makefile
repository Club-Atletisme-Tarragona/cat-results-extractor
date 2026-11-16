.PHONY: help venv process/all extract/remote extract athletes test

# Prefer the repo-local venv (it carries xlrd) and fall back to the system
# interpreter when the venv has not been created yet.
PYTHON := $(shell test -x .venv/bin/python && echo .venv/bin/python || echo python3)

help:
	@echo "Cat Results Extractor - Makefile Utilities"
	@echo ""
	@echo "Targets:"
	@echo "  make venv                     Create .venv and install requirements.txt"
	@echo "  make process/all              Process all PDFs from federació XLS"
	@echo "  make extract/remote URL=<>     Download and extract a remote PDF"
	@echo "  make extract FILE=<>           Extract from a local PDF"
	@echo "  make athletes                  Aggregate all athlete results into per-athlete JSONs"
	@echo "  make test                      Run the test suite (unittest discover)"

venv:
	python3 -m venv .venv
	.venv/bin/pip install -r requirements.txt

# Uses $(PYTHON): .venv/bin/python when present, else python3.
# process_all.py needs xlrd, which only the venv provides on PEP 668 systems.
test:
	python3 -m unittest discover -s tests -v

process/all:
	$(PYTHON) process_all.py

athletes:
	python3 scripts/aggregate_athletes.py

extract/remote:
ifndef URL
	$(error Usage: make extract/remote URL=<pdf_url>)
endif
	@TMPDIR=$$(mktemp -d) && \
	PDF=$$TMPDIR/$$(basename $(URL)) && \
	curl -sL "$(URL)" -o "$$PDF" && \
	python3 extract_catt.py "$$PDF" && \
	JSON=$$(echo "$$PDF" | sed 's/\.pdf$$/.json/') && \
	if [ -f "$$JSON" ]; then \
		mv "$$JSON" json/$$(basename "$$JSON"); \
		echo "JSON saved to: json/$$(basename $$JSON)"; \
	else \
		echo "No JSON generated (no CATT athletes found or extraction error)"; \
	fi && \
	rm -rf $$TMPDIR

extract:
ifndef FILE
	$(error Usage: make extract FILE=<local_pdf_path>)
endif
	python3 extract_catt.py "$(FILE)" && \
	JSON=$$(echo "$(FILE)" | sed 's/\.pdf$$/.json/') && \
	if [ -f "$$JSON" ]; then \
		mv "$$JSON" json/$$(basename $$JSON); \
		echo "JSON saved to: json/$$(basename $$JSON)"; \
	fi
