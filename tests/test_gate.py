"""Tests for the evaluation regression gate."""

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from evaluation.gate import compare_reports, load_report, main


def report(rows):
    return {
        "meta": {"model": "pari"},
        "summary": {},
        "results": [
            {"id": f"t{index}", "category": category, "pass": passed}
            for index, (category, passed) in enumerate(rows)
        ],
    }


BASE = [
    ("coding", True), ("coding", True), ("coding", False), ("coding", False),
    ("debugging", True), ("debugging", False),
]


def test_equal_run_passes():
    result = compare_reports(report(BASE), report(BASE))
    assert result.passed is True
    assert result.overall_delta == pytest.approx(0.0)
    assert result.reasons == []


def test_better_run_passes_and_reports_delta():
    better = BASE[:-1] + [("debugging", True)]
    result = compare_reports(report(BASE), report(better))
    assert result.passed is True
    assert result.overall_delta > 0
    assert result.categories["debugging"].delta > 0


def test_worse_overall_run_fails():
    worse = [("coding", True), ("coding", False), ("coding", False), ("coding", False),
             ("debugging", True), ("debugging", False)]
    result = compare_reports(report(BASE), report(worse))
    assert result.passed is False
    assert any("overall pass rate" in reason for reason in result.reasons)


def test_category_regression_fails_even_when_overall_improves():
    # debugging improves by one, coding loses one: overall flat, category down.
    candidate = [("coding", True), ("coding", False), ("coding", False), ("coding", False),
                 ("debugging", True), ("debugging", True)]
    result = compare_reports(report(BASE), report(candidate))
    assert result.overall_delta == pytest.approx(0.0)
    assert result.passed is False
    assert any("coding" in reason and "regressed" in reason for reason in result.reasons)


def test_category_regression_can_be_allowed():
    candidate = [("coding", True), ("coding", False), ("coding", False), ("coding", False),
                 ("debugging", True), ("debugging", True)]
    result = compare_reports(
        report(BASE), report(candidate), max_category_regression=0.25
    )
    assert result.passed is True


def test_min_delta_is_enforced():
    better = BASE[:-1] + [("debugging", True)]
    result = compare_reports(report(BASE), report(better), min_overall_delta=0.5)
    assert result.passed is False
    assert any("target" in reason for reason in result.reasons)


def test_missing_category_fails():
    candidate = [row for row in BASE if row[0] != "debugging"]
    result = compare_reports(report(BASE), report(candidate))
    assert result.passed is False
    assert any("missing" in reason for reason in result.reasons)


def test_unscored_tasks_are_ignored():
    base = report(BASE + [("coding", None), ("security", None)])
    cand = report(BASE + [("coding", None)])
    result = compare_reports(base, cand)
    assert result.passed is True
    assert result.overall_delta == pytest.approx(0.0)


def test_no_scored_tasks_fails():
    result = compare_reports(report([("coding", None)]), report([("coding", None)]))
    assert result.passed is False
    assert any("no scored tasks" in reason for reason in result.reasons)


def test_load_report_from_directory(tmp_path):
    (tmp_path / "report.json").write_text(json.dumps(report(BASE)), encoding="utf-8")
    loaded = load_report(tmp_path)
    assert len(loaded["results"]) == len(BASE)


def test_load_report_rejects_non_report(tmp_path):
    path = tmp_path / "report.json"
    path.write_text(json.dumps({"results": "nope"}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_report(path)


def test_cli_exit_codes_and_markdown(tmp_path):
    base_dir = tmp_path / "base"
    cand_dir = tmp_path / "cand"
    base_dir.mkdir()
    cand_dir.mkdir()
    (base_dir / "report.json").write_text(json.dumps(report(BASE)), encoding="utf-8")
    better = BASE[:-1] + [("debugging", True)]
    (cand_dir / "report.json").write_text(json.dumps(report(better)), encoding="utf-8")
    summary = tmp_path / "gate.md"

    assert main([
        "--baseline", str(base_dir),
        "--candidate", str(cand_dir),
        "--write", str(summary),
    ]) == 0
    assert "PASS" in summary.read_text(encoding="utf-8")

    (cand_dir / "report.json").write_text(
        json.dumps(report([("coding", False)] * 6)), encoding="utf-8"
    )
    assert main(["--baseline", str(base_dir), "--candidate", str(cand_dir)]) == 1
    assert main(["--baseline", str(tmp_path / "nope"), "--candidate", str(cand_dir)]) == 2
