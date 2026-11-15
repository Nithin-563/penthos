"""Regression gate for a new adapter or training run.

Fine-tuning small models is where good checkpoints quietly get worse: the
history in this repo shows adapters scoring 14-16/26 where the base scored
23/26. A gate makes that failure loud instead of shipping it.

Compares two `evaluation/results/**/report.json` runs and exits non-zero when
the candidate loses overall or gives up a category.

    python -m evaluation.gate --baseline results/b --candidate results/e3_lora
    python -m evaluation.gate --baseline B --candidate C --min-delta 0.02
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path

EPSILON = 1e-9


@dataclass
class CategoryDelta:
    category: str
    baseline: float | None
    candidate: float | None
    delta: float | None
    scored: int


@dataclass
class GateResult:
    passed: bool
    overall_delta: float | None
    reasons: list[str] = field(default_factory=list)
    categories: dict[str, CategoryDelta] = field(default_factory=dict)

    def markdown(self) -> str:
        lines = [
            "# Evaluation gate",
            "",
            f"- result: **{'PASS' if self.passed else 'FAIL'}**",
            f"- overall delta: {self.overall_delta:+.2%}" if self.overall_delta is not None
            else "- overall delta: n/a",
            "",
            "| category | baseline | candidate | delta | scored |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
        for name in sorted(self.categories):
            entry = self.categories[name]
            base = f"{entry.baseline:.0%}" if entry.baseline is not None else "—"
            cand = f"{entry.candidate:.0%}" if entry.candidate is not None else "—"
            delta = f"{entry.delta:+.0%}" if entry.delta is not None else "—"
            lines.append(f"| {name} | {base} | {cand} | {delta} | {entry.scored} |")
        if self.reasons:
            lines += ["", "## Failures", ""] + [f"- {reason}" for reason in self.reasons]
        return "\n".join(lines) + "\n"


def load_report(source: str | Path) -> dict:
    """Load a benchmark report from a report.json path or a results directory."""
    path = Path(source)
    if path.is_dir():
        path = path / "report.json"
    if not path.is_file():
        raise FileNotFoundError(f"no benchmark report at {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("results"), list):
        raise ValueError(f"{path} is not a benchmark report (missing results list)")
    return data


def _rates(report: dict) -> dict[str, tuple[int, int]]:
    """Return {category: (passed, scored)} ignoring unscored tasks."""
    counts: dict[str, list[int]] = {}
    for result in report.get("results", []):
        passed = result.get("pass")
        if passed is None:
            continue
        category = str(result.get("category") or "unknown")
        entry = counts.setdefault(category, [0, 0])
        entry[1] += 1
        if passed:
            entry[0] += 1
    return {category: (passed, total) for category, (passed, total) in counts.items()}


def compare_reports(
    baseline: dict,
    candidate: dict,
    *,
    min_overall_delta: float = 0.0,
    max_category_regression: float = 0.0,
) -> GateResult:
    """Decide whether the candidate is at least as good as the baseline.

    Args:
        baseline: the run to beat (usually the current shipping config).
        candidate: the run being considered (a new adapter or prompt change).
        min_overall_delta: required improvement, as a fraction of tasks
            (0.02 means two percentage points better than baseline).
        max_category_regression: how much a single category may drop before
            the gate fails. Default 0 — no category may get worse.
    """
    base = _rates(baseline)
    cand = _rates(candidate)

    base_passed = sum(passed for passed, _ in base.values())
    base_total = sum(total for _, total in base.values())
    cand_passed = sum(passed for passed, _ in cand.values())
    cand_total = sum(total for _, total in cand.values())

    overall_delta: float | None = None
    if base_total and cand_total:
        overall_delta = cand_passed / cand_total - base_passed / base_total

    reasons: list[str] = []
    if overall_delta is None:
        reasons.append("no scored tasks in one of the reports")
    elif overall_delta < min_overall_delta - EPSILON:
        reasons.append(
            f"overall pass rate fell or missed the target: "
            f"{overall_delta:+.2%} (required {min_overall_delta:+.2%})"
        )

    categories: dict[str, CategoryDelta] = {}
    for name in sorted(set(base) | set(cand)):
        base_rate = base[name][0] / base[name][1] if name in base and base[name][1] else None
        cand_rate = cand[name][0] / cand[name][1] if name in cand and cand[name][1] else None
        delta = (
            cand_rate - base_rate
            if base_rate is not None and cand_rate is not None
            else None
        )
        scored = (cand.get(name) or (0, 0))[1]
        categories[name] = CategoryDelta(name, base_rate, cand_rate, delta, scored)

        if name in base and name not in cand:
            reasons.append(f"category missing from candidate: {name}")
        elif base_rate is not None and cand_rate is None:
            reasons.append(f"category has no scored tasks in candidate: {name}")
        elif delta is not None and delta < -max_category_regression - EPSILON:
            reasons.append(
                f"category regressed: {name} {delta:+.0%} "
                f"(allowed {max_category_regression:.0%} drop)"
            )

    return GateResult(
        passed=not reasons,
        overall_delta=overall_delta,
        reasons=reasons,
        categories=categories,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fail when a candidate benchmark run is worse than the baseline."
    )
    parser.add_argument("--baseline", required=True, help="report.json or results dir")
    parser.add_argument("--candidate", required=True, help="report.json or results dir")
    parser.add_argument("--min-delta", type=float, default=0.0,
                        help="required overall improvement (fraction, default 0)")
    parser.add_argument("--max-category-drop", type=float, default=0.0,
                        help="allowed per-category decrease (fraction, default 0)")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--write", default=None,
                        help="write the markdown summary to this path")
    args = parser.parse_args(argv)

    try:
        baseline = load_report(args.baseline)
        candidate = load_report(args.candidate)
    except (FileNotFoundError, ValueError) as exc:
        print(f"gate error: {exc}")
        return 2

    result = compare_reports(
        baseline,
        candidate,
        min_overall_delta=args.min_delta,
        max_category_regression=args.max_category_drop,
    )

    if args.json:
        print(json.dumps({
            "passed": result.passed,
            "overall_delta": result.overall_delta,
            "reasons": result.reasons,
            "categories": {
                name: {
                    "baseline": entry.baseline,
                    "candidate": entry.candidate,
                    "delta": entry.delta,
                    "scored": entry.scored,
                }
                for name, entry in result.categories.items()
            },
        }, indent=2))
    else:
        print(result.markdown())

    if args.write:
        Path(args.write).write_text(result.markdown(), encoding="utf-8")

    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
