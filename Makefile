.PHONY: help process/all extract/remote extract

help:
	@echo "Cat Results Extractor - Makefile Utilities"
	@echo ""
	@echo "Targets:"
	@echo "  make process/all              Process all PDFs from federació XLS"
	@echo "  make extract/remote URL=<>     Download and extract a remote PDF"
	@echo "  make extract file=<>           Extract from a local PDF"

process/all:
	python3 process_all.py

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
	$(error Usage: make extract file=<local_pdf_path>)
endif
	python3 extract_catt.py "$(FILE)" && \
	JSON=$$(echo "$(FILE)" | sed 's/\.pdf$$/.json/') && \
	if [ -f "$$JSON" ]; then \
		mv "$$JSON" json/$$(basename $$JSON); \
		echo "JSON saved to: json/$$(basename $$JSON)"; \
	fi
