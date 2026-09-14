"""Golden extraction tests: run the real extractor on committed fixture PDFs
and compare the output against committed golden JSONs.

Each fixture PDF covers a documented input format (AGENTS.md):

  resultat-20260426-cat10000marxamastergava.pdf    marcha (via extract_catt)
  resultat-20260502-controlvelocitatmaigtarragona.pdf  'metres' track format
  resultat-20260322-controltorredembarra.pdf       current format, llançament
                                                   multi-attempt + wind lines
  resultat-20260418-territorialpromociovalls.pdf   relay events
  resultat-2026050203-territorialcombinadestarragona.pdf  combined events
  resulcataleviprevia21511.pdf                     2011 tabular format —
                                                   NOT handled by extract_catt
                                                   (pinned as no-export)

Any extractor change that alters output shows up as a golden diff: review it,
then regenerate with UPDATE_GOLDEN=1 after confirming the change is intended.

Run: python3 -m unittest tests.test_golden_extraction -v
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "tests" / "fixtures"
GOLDEN = REPO_ROOT / "tests" / "golden"

# fixture PDF -> source JSON providing the real provenance URL
CASES = {
    "resultat-20260426-cat10000marxamastergava.pdf":
        "json/resultat-20260426-cat10000marxamastergava.json",
    "resultat-20260502-controlvelocitatmaigtarragona.pdf":
        "json/resultat-20260502-controlvelocitatmaigtarragona.json",
    "resultat-20260322-controltorredembarra.pdf":
        "json/resultat-20260322-controltorredembarra.json",
    "resultat-20260418-territorialpromociovalls.pdf":
        "json/resultat-20260418-territorialpromociovalls.json",
    "resultat-2026050203-territorialcombinadestarragona.pdf":
        "json/resultat-2026050203-territorialcombinadestarragona.json",
}

# PDFs that extract_catt.py must NOT export (handled by season-specific
# processors per AGENTS.md Season Format Detection) — pinned as behavior.
NO_EXPORT_CASES = [
    "resulcataleviprevia21511.pdf",  # 2011 tabular (SÈRIE/LLOC/CARRER/...)
]


def run_extraction(pdf_name: str) -> tuple[dict | None, str]:
    """Extract one fixture PDF in a temp dir; return (output dict|None, log)."""
    src_url = json.load(open(REPO_ROOT / CASES[pdf_name], encoding="utf-8"))["event_src"]
    with tempfile.TemporaryDirectory() as tmp:
        pdf = Path(tmp, pdf_name)
        pdf.write_bytes((FIXTURES / pdf_name).read_bytes())
        proc = subprocess.run(
            [sys.executable, "extract_catt.py", str(pdf), src_url, "--quiet"],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=300,
        )
        out_json = pdf.with_suffix(".json")
        if not out_json.exists():
            return None, proc.stdout + proc.stderr
        return json.load(open(out_json, encoding="utf-8")), proc.stdout + proc.stderr


class GoldenExtraction(unittest.TestCase):
    maxDiff = None

    def test_golden_extraction_matches(self):
        for pdf_name in sorted(CASES):
            with self.subTest(pdf=pdf_name):
                output, log = run_extraction(pdf_name)
                self.assertIsNotNone(output, f"no JSON produced for {pdf_name}\n{log}")
                golden_path = GOLDEN / f"{Path(pdf_name).stem}.json"
                if os.environ.get("UPDATE_GOLDEN") == "1":
                    golden_path.write_text(
                        json.dumps(output, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8",
                    )
                    continue
                self.assertTrue(golden_path.exists(), f"missing golden {golden_path}")
                expected = json.load(open(golden_path, encoding="utf-8"))
                self.assertEqual(
                    output, expected,
                    f"extraction output changed for {pdf_name}. If intentional, "
                    "regenerate with UPDATE_GOLDEN=1 and review the diff.",
                )

    def test_unhandled_formats_produce_no_export(self):
        """extract_catt finds no CATT athletes in season-specific formats; the
        pipeline order (AGENTS.md) then falls back to the dedicated extractor.
        Pin the no-export behavior so a silent change in detection is noticed."""
        for pdf_name in NO_EXPORT_CASES:
            with self.subTest(pdf=pdf_name):
                src_url = f"https://old.fcatletisme.cat/test/{pdf_name}"
                with tempfile.TemporaryDirectory() as tmp:
                    pdf = Path(tmp, pdf_name)
                    pdf.write_bytes((FIXTURES / pdf_name).read_bytes())
                    proc = subprocess.run(
                        [sys.executable, "extract_catt.py", str(pdf), src_url, "--quiet"],
                        cwd=REPO_ROOT, capture_output=True, text=True, timeout=300,
                    )
                    self.assertEqual(proc.returncode, 0, proc.stderr)
                    self.assertFalse(
                        pdf.with_suffix(".json").exists(),
                        f"unexpected JSON export for {pdf_name}",
                    )


if __name__ == "__main__":
    unittest.main()
