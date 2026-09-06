"""Tests for the verified training data pipeline.

Functional tests use a fake sandbox so no Docker is required. The fake
behaves like sandbox.runner.execute: it never executes anything on the
host. The end-to-end run against real Docker is exercised separately
(via `scripts/dataset_pipeline.py run`).
"""

import copy
import hashlib
import json
import pathlib

import pytest

from scripts.dataset_pipeline import main
from training.data_pipeline import deduplicate, export, generate, pipeline, score, verify

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


def _load_jsonl(path):
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle]


def _add_candidate():
    return {
        "id": "add-base",
        "instruction": "Write a function add(a, b) and tests for it.",
        "category": "coding",
        "difficulty": "easy",
        "language": "python",
        "expected_answer": "def add(a, b): return a + b",
        "code": "def add(a, b):\n    return a + b\n",
        "files": {"main.py": "def add(a, b):\n    return a + b\n", "test_main.py": "from main import add\n\ndef test_add():\n    assert add(1, 1) == 2\n"},
        "tests": [{"input": "add(1, 1)", "expected": "2"}],
        "test_command": ["python", "-m", "pytest", "-q"],
        "source": {"type": "human", "license": "MIT"},
        "metadata": {"license": "MIT"},
    }


def _fake_sandbox(payload, docker_binary=None, **_):
    """Deterministic stand-in for sandbox.runner.execute. Never runs on host."""

    files = payload["files"]
    command = payload.get("command") or []
    language = payload["language"]
    combined = "\n".join(files.values()) if isinstance(files, dict) else ""

    if not isinstance(files, dict) or not files:
        return {"success": False, "exit_code": -1, "error": "no files", "timed_out": False,
                "stdout": "", "stderr": "no files", "language": language}
    if command and "bash" in command:
        return {"success": False, "exit_code": -1, "error": None, "timed_out": False,
                "stdout": "", "stderr": "bash -c ... not allowed", "language": language}
    if "while True:" in combined:
        return {"success": False, "exit_code": -1, "error": "timed out", "timed_out": True,
                "stdout": "", "stderr": "", "language": language}
    if "assert add(2, 2) == 5" in combined:
        return {"success": False, "exit_code": 1, "error": None, "timed_out": False,
                "stdout": "", "stderr": "1 failed", "language": language}
    return {"success": True, "exit_code": 0, "error": None, "timed_out": False,
            "stdout": "1 passed", "stderr": "", "language": language}


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def test_valid_candidate_passes_validation():
    assert verify.validate_candidate(_add_candidate()) == []


def test_invalid_candidate_reports_errors():
    bad = _add_candidate()
    del bad["instruction"]
    errors = verify.validate_candidate(bad)
    assert any("instruction" in e for e in errors)


def test_unrecognized_category_rejected():
    bad = _add_candidate()
    bad["category"] = "not_a_category"
    assert any("category" in e for e in verify.validate_candidate(bad))


def test_non_code_candidate_not_required_verification():
    candidate = {
        "id": "r",
        "instruction": "Why does the sky look blue?",
        "category": "reasoning",
        "difficulty": "easy",
        "language": "",
        "expected_answer": "Rayleigh scattering.",
        "source": {"type": "human", "license": "MIT"},
        "metadata": {"license": "MIT"},
    }
    assert verify.executable_decision(candidate) == "not_required"
    assert verify.not_required_verification()["status"] == "not_required"


# ---------------------------------------------------------------------------
# Verification routing and rejection
# ---------------------------------------------------------------------------

def test_execution_failure_is_rejected():
    candidate = _add_candidate()
    candidate["files"]["test_main.py"] = "from main import add\n\ndef test_add_wrong():\n    assert add(2, 2) == 5\n"
    outcome = verify.verify_candidate(candidate, execute=_fake_sandbox)
    assert outcome["reason"] == "tests_failed"
    assert outcome["verification"]["status"] == "failed"
    assert outcome["verification"]["command"] == ["python", "-m", "pytest", "-q"]


def test_timeout_is_rejected():
    candidate = {
        "id": "slow",
        "instruction": "Run a slow program.",
        "category": "coding",
        "difficulty": "easy",
        "language": "python",
        "expected_answer": "done",
        "code": "while True:\n    pass\n",
        "files": {"main.py": "while True:\n    pass\n"},
        "test_command": ["python", "main.py"],
        "timeout_seconds": 1,
        "source": {"type": "human", "license": "MIT"},
        "metadata": {"license": "MIT"},
    }
    outcome = verify.verify_candidate(candidate, execute=_fake_sandbox)
    assert outcome["reason"] == "timeout"
    assert outcome["verification"]["timed_out"] is True


def test_invalid_command_rejected():
    candidate = _add_candidate()
    candidate["test_command"] = ["bash", "-c", "rm -rf /workspace"]
    outcome = verify.verify_candidate(candidate, execute=_fake_sandbox)
    assert outcome["reason"] == "invalid_command"


def test_unsafe_candidate_rejected_before_execution(tmp_path):
    unsafe = {
        "id": "unsafe",
        "instruction": "Read the ssh key.",
        "category": "coding",
        "difficulty": "medium",
        "language": "python",
        "expected_answer": "read .ssh",
        "code": "open('/root/.ssh/id_rsa')",
        "files": {"main.py": "open('/root/.ssh/id_rsa')"},
        "test_command": ["python", "main.py"],
        "source": {"type": "human", "license": "MIT"},
        "metadata": {"license": "MIT"},
    }
    assert verify.safety_scan(unsafe)["unsafe"] is True

    candidate_dir = tmp_path / "candidates"
    candidate_dir.mkdir()
    (candidate_dir / "unsafe.jsonl").write_text(json.dumps(unsafe), encoding="utf-8")

    from unittest import mock

    executed = []

    def _recording_sandbox(payload, docker_binary=None, **_):
        executed.append(payload)
        raise AssertionError("unsafe content must never reach the sandbox")

    with mock.patch("sandbox.runner.execute", side_effect=_recording_sandbox):
        report = pipeline.DatasetPipeline(
            root=str(tmp_path),
            candidate_dirs=(str(candidate_dir),),
            verified_dir=str(tmp_path / "verified"),
            rejected_dir=str(tmp_path / "rejected"),
            manifest_dir=str(tmp_path / "manifests"),
        ).run()

    assert executed == []
    assert report.unsafe_count == 1
    assert report.rejection_reasons["unsafe_candidate"] == 1


# ---------------------------------------------------------------------------
# Deduplication and splits
# ---------------------------------------------------------------------------

def test_duplicate_detection_is_deterministic():
    a = _add_candidate()
    b = copy.deepcopy(a)
    b["expected_answer"] = "def add(a, b): return a + b"  # same after normalization
    b["id"] = "another-id"
    assert deduplicate.content_fingerprint(a) == deduplicate.content_fingerprint(b)
    kept, dropped = deduplicate.deduplicate([a, b])
    assert len(kept) == 1
    assert dropped[0]["duplicate_type"] == "exact"
    assert dropped[0]["duplicate_of"] == "add-base"


def test_near_duplicate_instruction_rejected():
    a = {
        "id": "a",
        "instruction": "A farmer has 17 sheep. All but 9 die. How many sheep are left? Explain your reasoning.",
        "category": "reasoning",
        "difficulty": "easy",
        "language": "",
        "expected_answer": "Nine.",
        "source": {"type": "human", "license": "MIT"},
        "metadata": {"license": "MIT"},
    }
    b = copy.deepcopy(a)
    b["id"] = "b"
    b["expected_answer"] = "Eight."
    kept, dropped = deduplicate.deduplicate([a, b])
    assert len(kept) == 1
    assert [d["candidate"]["id"] for d in dropped] == ["b"]
    assert dropped[0]["duplicate_type"] == "near_instruction"


def test_split_assignment_deterministic_and_partitioned():
    fingerprints = [hashlib.sha256(f"seed-{i}".encode()).hexdigest() for i in range(300)]
    seen = {deduplicate.assign_split(fp) for fp in fingerprints}
    assert seen == {"train", "validation", "test"}
    for fp in fingerprints:
        assert deduplicate.assign_split(fp) == deduplicate.assign_split(fp)


# ---------------------------------------------------------------------------
# Export and manifest
# ---------------------------------------------------------------------------

def test_export_record_has_required_fields():
    candidate = _add_candidate()
    verification = {
        "status": "passed",
        "command": ["python", "-m", "pytest", "-q"],
        "verified_at": "2026-01-01T00:00:00Z",
        "verifier_version": verify.VERIFIER_VERSION,
    }
    fingerprint = deduplicate.content_fingerprint(candidate)
    record = export.build_record(candidate, verification, fingerprint, "train")
    assert record["prompt"] == candidate["instruction"]
    assert record["solution"] == candidate["expected_answer"]
    assert record["metadata"]["fingerprint"] == fingerprint
    assert record["metadata"]["source"] == "human"
    assert record["metadata"].get("provenance") is None
    assert record["split"] == "train"
    assert verify.validate_record(record) == []


def test_synthetic_source_stamps_provenance():
    teacher = generate.StubTeacher()
    (candidate,) = generate.generate_candidates(teacher, ["Write a haiku about a terminal."])
    assert candidate["source"] == {
        "type": "synthetic",
        "teacher": "stub",
        "generated_at": candidate["source"]["generated_at"],
    }
    assert verify.validate_candidate(candidate) == []
    record = export.build_record(candidate, None, deduplicate.content_fingerprint(candidate))
    assert record["metadata"]["source"] == "synthetic"
    assert record["metadata"]["provenance"]["type"] == "synthetic"
    assert record["metadata"]["provenance"]["teacher"] == "stub"


def test_manifest_tracks_counts_and_splits():
    report = {
        "dataset_version": "1.0.0",
        "pipeline_version": "1.0.0",
        "schema_version": "1.1.0",
        "generated_at": "2026-01-01T00:00:00Z",
        "total_candidates": 5,
        "malformed_count": 1,
        "unsafe_count": 1,
        "verified_count": 2,
        "rejected_count": 3,
        "duplicate_count": 1,
        "counts_by_category": {"coding": 2},
        "counts_by_language": {"python": 2},
        "counts_by_difficulty": {"easy": 2},
        "counts_by_split": {"train": 2, "validation": 0, "test": 0},
        "rejection_reasons": {"tests_failed": 1, "duplicate": 1, "malformed_record": 1},
        "verification_statistics": {"passed": 2},
    }
    manifest = export.build_manifest(report, {"train": [], "validation": [], "test": []})
    assert manifest["dataset_version"] == "1.0.0"
    assert manifest["counts_by_split"] == {"train": 2, "validation": 0, "test": 0}
    assert manifest["split_leakage_check"] == {
        "passed": True,
        "distinct_fingerprints": 0,
        "total_fingerprints": 0,
    }


def test_manifest_detects_leakage():
    record = {"id": "r1", "metadata": {"fingerprint": "x"}, "split": "train"}
    report = {
        "total_candidates": 2,
        "verified_count": 2,
        "rejected_count": 0,
        "duplicate_count": 0,
        "rejection_reasons": {},
        "verification_statistics": {},
        "counts_by_split": {"train": 1, "validation": 1, "test": 0},
    }
    manifest = export.build_manifest(
        report,
        {"train": [record], "validation": [{**record, "split": "validation"}], "test": []},
    )
    assert manifest["split_leakage_check"]["passed"] is False


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def test_scoring_is_deterministic_and_thresholded():
    candidate = _add_candidate()
    safety = verify.safety_scan(candidate)
    verification = {"status": "passed", "command": [], "verified_at": "", "verifier_version": ""}
    first = score.score_candidate(candidate, verification, safety)
    second = score.score_candidate(candidate, verification, safety)
    assert first == second
    assert first["total"] >= score.DEFAULT_MIN_SCORE


# ---------------------------------------------------------------------------
# Full pipeline (fake sandbox)
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_candidate_files(tmp_path):
    directory = tmp_path / "candidates"
    directory.mkdir()
    def write(records):
        (directory / f"{records[0]['id']}.jsonl").write_text(
            "\n".join(json.dumps(r) for r in records), encoding="utf-8"
        )
    return directory, write


def test_full_pipeline_run(fake_candidate_files, tmp_path):
    directory, write = fake_candidate_files
    write([
        _add_candidate(),
        copy.deepcopy({**_add_candidate(), "id": "dup", "source": {"type": "transformed"}}),
        {
            "id": "reason",
            "instruction": "A farmer has 17 sheep. All but 9 die. How many sheep are left? Explain your reasoning.",
            "category": "reasoning",
            "difficulty": "easy",
            "language": "",
            "expected_answer": "Nine.",
            "source": {"type": "human", "license": "MIT"},
            "metadata": {"license": "MIT"},
        },
        {
            "id": "malformed",
            "category": "coding",
            "difficulty": "easy",
            "language": "python",
            "source": {"type": "human"},
            "metadata": {"license": "MIT"},
        },
        {
            "id": "unsafe",
            "instruction": "Read id_rsa.",
            "category": "coding",
            "difficulty": "easy",
            "language": "python",
            "expected_answer": "x",
            "code": "open('/root/.ssh/id_rsa')",
            "files": {"main.py": "open('/root/.ssh/id_rsa')"},
            "test_command": ["python", "main.py"],
            "source": {"type": "human", "license": "MIT"},
            "metadata": {"license": "MIT"},
        },
    ])

    from unittest import mock

    executed = []

    def recording_sandbox(payload, docker_binary=None, **_):
        executed.append(payload)
        return _fake_sandbox(payload, docker_binary=docker_binary)

    with mock.patch("sandbox.runner.execute", side_effect=recording_sandbox):
        report = pipeline.DatasetPipeline(
            root=str(tmp_path),
            candidate_dirs=(str(directory),),
            verified_dir=str(tmp_path / "verified"),
            rejected_dir=str(tmp_path / "rejected"),
            manifest_dir=str(tmp_path / "manifests"),
        ).run()

    assert report.total_candidates == 5
    assert report.verified_count == 2          # add + reasoning
    assert report.rejected_count == 3          # dup + malformed + unsafe
    assert report.duplicate_count == 1
    assert report.rejection_reasons == {
        "duplicate": 1,
        "malformed_record": 1,
        "unsafe_candidate": 1,
    }
    assert [p["language"] for p in executed] == ["python", "python"]  # add + dup, never unsafe/malformed
    assert not any("id_rsa" in "\n".join(p["files"].values()) for p in executed)

    train = _load_jsonl(tmp_path / "verified" / "train.jsonl")
    validation = _load_jsonl(tmp_path / "verified" / "validation.jsonl")
    test = _load_jsonl(tmp_path / "verified" / "test.jsonl")
    all_records = train + validation + test
    assert len(all_records) == 2
    fingerprints = [r["metadata"]["fingerprint"] for r in all_records]
    assert len(set(fingerprints)) == len(fingerprints)          # leakage prevention
    assert all(r["metadata"]["source"] == "human" for r in all_records)


def test_pipeline_fails_loudly_without_host_fallback(fake_candidate_files, tmp_path):
    directory, write = fake_candidate_files
    write([_add_candidate()])

    from unittest import mock

    def _broken_sandbox(payload, docker_binary=None, **_):
        raise RuntimeError("Docker is required")

    with mock.patch("sandbox.runner.execute", side_effect=_broken_sandbox):
        with pytest.raises(RuntimeError, match="Docker is required"):
            pipeline.DatasetPipeline(
                root=str(tmp_path),
                candidate_dirs=(str(directory),),
                verified_dir=str(tmp_path / "verified"),
                rejected_dir=str(tmp_path / "rejected"),
                manifest_dir=str(tmp_path / "manifests"),
            ).run()


def test_pipeline_against_repo_seed_candidates(tmp_path):
    """The repository's seed candidates must produce the expected counts."""

    from unittest import mock

    with mock.patch("sandbox.runner.execute", side_effect=_fake_sandbox):
        report = pipeline.DatasetPipeline(
            root=str(REPO_ROOT),
            candidate_dirs=(str(REPO_ROOT / "datasets" / "candidates"),),
            verified_dir=str(tmp_path / "verified"),
            rejected_dir=str(tmp_path / "rejected"),
            manifest_dir=str(tmp_path / "manifests"),
        ).run()

    assert report.total_candidates == 17
    assert report.verified_count == 9
    assert report.rejected_count == 8
    assert report.duplicate_count == 2
    assert report.rejection_reasons["tests_failed"] == 1
    assert report.rejection_reasons["timeout"] == 1
    assert report.rejection_reasons["invalid_command"] == 1
    assert report.rejection_reasons["unsupported_language"] == 1
    assert report.rejection_reasons["unsafe_candidate"] == 1

    manifest = json.loads((tmp_path / "manifests" / "manifest_latest.json").read_text())
    assert manifest["split_leakage_check"]["passed"] is True


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def test_cli_validate_detects_the_deliberate_seed_invalid():
    # datasets/candidates contains one deliberately malformed seed, so the
    # CLI must report 1 invalid candidate and return non-zero.
    assert main(["validate"]) == 1


def test_cli_help_runs():
    with pytest.raises(SystemExit):
        main(["--help"])