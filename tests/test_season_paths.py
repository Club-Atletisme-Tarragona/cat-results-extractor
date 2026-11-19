#!/usr/bin/env python3
"""Roll-over safety: a new season must work with no code change.

These tests exist because the pipeline writes into seasons/<year>/json/ and
the question "will next year create its folder or fail?" must have an
asserted answer, not a remembered one. Everything here uses a temporary
seasons/ root, so no real season is touched.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import season_paths  # noqa: E402


class TestSeasonParsing(unittest.TestCase):
    def test_season_comes_from_event_date(self):
        self.assertEqual(season_paths.season_of("14/3/2026"), "2026")
        self.assertEqual(season_paths.season_of("2/1/2027"), "2027")
        self.assertEqual(season_paths.season_of("2027-05-02"), "2027")

    def test_two_digit_years(self):
        self.assertEqual(season_paths.season_of("01/12/05"), "2005")
        self.assertEqual(season_paths.season_of("01/12/99"), "1999")

    def test_missing_date_falls_back(self):
        self.assertEqual(season_paths.season_of("", fallback="2031"), "2031")
        self.assertEqual(season_paths.season_of("not a date", fallback="2019"), "2019")
        self.assertEqual(season_paths.season_of(None), season_paths.current_season())

    def test_catt_season_pin(self):
        old = os.environ.get("CATT_SEASON")
        try:
            os.environ["CATT_SEASON"] = "2032"
            self.assertEqual(season_paths.current_season(), "2032")
            os.environ["CATT_SEASON"] = "not-a-year"
            with self.assertRaises(ValueError):
                season_paths.current_season()
        finally:
            if old is None:
                os.environ.pop("CATT_SEASON", None)
            else:
                os.environ["CATT_SEASON"] = old


class TestNewSeasonFolder(unittest.TestCase):
    """A future season must be created on demand, not assumed to exist."""

    def test_future_season_paths(self):
        with tempfile.TemporaryDirectory() as root:
            json_dir = season_paths.season_json_dir("2031", root=root)
            # root is the seasons/ directory itself
            self.assertTrue(json_dir.endswith(os.path.join("2031", "json")))
            self.assertFalse(os.path.exists(json_dir), "path helper must not create anything")
            self.assertTrue(season_paths.season_imported_dir("2031", root=root).endswith("imported"))
            self.assertEqual(season_paths.known_seasons(root=root), [])

    def _run_move(self, tmp, argv_extra=()):
        """Run the helper in-process so the temp root really is used."""
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "move_json_to_season", REPO_ROOT / "scripts" / "move_json_to_season.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        import contextlib
        import io

        old_root = mod.season_paths.SEASONS_DIR
        old_argv = sys.argv
        mod.season_paths.SEASONS_DIR = tmp
        try:
            sys.argv = ["move_json_to_season.py", *argv_extra]
            with contextlib.redirect_stdout(io.StringIO()):
                mod.main()
        finally:
            mod.season_paths.SEASONS_DIR = old_root
            sys.argv = old_argv

    def test_move_json_creates_the_future_season_folder(self):
        """The write path used by make/CI creates seasons/<year> when missing."""
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp, "event.json")
            src.write_text(json.dumps({"event_date": "04/06/2031", "results": []}), encoding="utf-8")
            self._run_move(tmp, [str(src)])
            dest = Path(tmp, "2031", "json", "event.json")
            self.assertTrue(dest.exists(), "the 2031 season folder was not created")
            self.assertFalse(src.exists(), "the JSON should have been moved, not copied")

    def test_move_json_dry_run_does_not_create(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp, "event.json")
            src.write_text(json.dumps({"event_date": "04/06/2031"}), encoding="utf-8")
            self._run_move(tmp, ["--dry-run", str(src)])
            self.assertFalse(Path(tmp, "2031").exists(), "dry run must not create the season folder")
            self.assertTrue(src.exists(), "dry run must not move the file")


class TestPipelineDiscoversNewSeason(unittest.TestCase):
    """Tools must pick up a season directory they were never told about."""

    def test_known_seasons_includes_a_new_year(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "2031" / "json").mkdir(parents=True)
            (Path(tmp) / "2026" / "json").mkdir(parents=True)
            self.assertEqual(season_paths.known_seasons(root=tmp), ["2026", "2031"])

    def test_checker_and_validator_glob_every_season(self):
        for script in ("scripts/check_plausibility.py", "scripts/validate_performance.py"):
            src = (REPO_ROOT / script).read_text(encoding="utf-8")
            self.assertIn('"seasons"', src, f"{script} no longer scans seasons/")
            self.assertNotIn("range(2005", src, f"{script} still hard-codes a season range")

    def test_no_live_literal_year_in_output_paths(self):
        """Guard: no code string may hard-code a season directory.

        Implemented with AST so comments and docstrings are ignored by
        construction (they legitimately mention seasons for history).
        """
        import ast

        offenders = []
        for path in sorted(REPO_ROOT.glob("*.py")) + sorted((REPO_ROOT / "scripts").glob("*.py")):
            if path.name.startswith(("process_2005", "process_2008", "process_2010",
                                     "process_2011", "process_2013", "process_2014")):
                continue  # historical one-off season processors
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
            docstrings = set()
            for node in ast.walk(tree):
                if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                    doc = ast.get_docstring(node, clean=False)
                    if doc:
                        docstrings.add(doc)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                    continue
                value = node.value
                if value in docstrings:
                    continue
                if re.search(r"seasons/20\d{2}/json", value) and not value.endswith(".json"):
                    offenders.append(f"{path.name}:{node.lineno}: {value!r}")
        self.assertEqual(offenders, [], "hard-coded season directory(s):\n" + "\n".join(offenders))


if __name__ == "__main__":
    unittest.main()
