#!/usr/bin/env python3
"""Build the category-balance seed pack.

Writes `datasets/candidates/seed_core_categories.jsonl`: records for every
category the pipeline recognises, so a fine-tune sees a balanced mix rather
than a coding-only diet.

Executable records ship a correct implementation and a passing pytest suite and
are verified by the Docker pipeline. Reasoning, agentic and chat records are
non-executable by design (`language: ""`, no code) and route to
`not_required`.

    python scripts/build_seed_categories.py
"""

import json
from pathlib import Path

RECORDS: list[dict] = []


def rec(**kw) -> None:
    base = {
        "category": "coding",
        "difficulty": "medium",
        "language": "python",
        "source": {"type": "human", "license": "MIT"},
        "metadata": {
            "license": "MIT",
            "notes": "Curated category-balance seed for Pari.",
        },
    }
    base.update(kw)
    base.setdefault("id", "seed-category-unknown")
    RECORDS.append(base)


def code_rec(rid, instruction, category, difficulty, code, tests_text, expected, notes):
    rec(
        id=rid,
        instruction=instruction,
        category=category,
        difficulty=difficulty,
        expected_answer=expected,
        code=code,
        files={"main.py": code, "test_main.py": tests_text},
        tests=[{"input": "python -m pytest -q", "expected": "all tests pass"}],
        test_command=["python", "-m", "pytest", "-q"],
        metadata={"license": "MIT", "notes": notes},
    )


def prose(rid, instruction, category, difficulty, answer, notes):
    rec(
        id=rid,
        instruction=instruction,
        category=category,
        difficulty=difficulty,
        language="",
        expected_answer=answer,
        metadata={"license": "MIT", "notes": notes},
    )


# ---------------------------------------------------------------------------
# coding
# ---------------------------------------------------------------------------

MERGE = '''def merge_intervals(
    intervals: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    """Merge overlapping or touching closed intervals.

    Sorted sweep: keep the current merged interval and extend it when the next
    start is at or before its end, otherwise emit it and start a new one.
    O(n log n) for the sort, O(n) for the sweep.
    """
    if not intervals:
        return []

    ordered = sorted(intervals, key=lambda pair: pair[0])
    merged: list[list[float]] = [[ordered[0][0], ordered[0][1]]]

    for start, end in ordered[1:]:
        if start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])

    return [(start, end) for start, end in merged]
'''

MERGE_T = '''from main import merge_intervals


def test_empty_input():
    assert merge_intervals([]) == []


def test_single_interval_unchanged():
    assert merge_intervals([(1, 3)]) == [(1, 3)]


def test_overlapping_intervals_merge():
    assert merge_intervals([(1, 3), (2, 6), (8, 10)]) == [(1, 6), (8, 10)]


def test_touching_intervals_merge():
    assert merge_intervals([(1, 2), (2, 3)]) == [(1, 3)]


def test_unsorted_input_is_ordered():
    assert merge_intervals([(8, 10), (1, 3), (2, 6)]) == [(1, 6), (8, 10)]


def test_contained_interval_does_not_shrink_the_merge():
    assert merge_intervals([(1, 10), (2, 3)]) == [(1, 10)]
'''

code_rec(
    "seed-category-merge-4001",
    "Implement merge_intervals(intervals) that merges overlapping or touching "
    "closed intervals and returns them sorted. Handle an empty list, "
    "unsorted input, and an interval fully contained in another.",
    "coding", "medium", MERGE, MERGE_T,
    "Sort by start, then sweep while extending the current interval when the "
    "next start is at or before its end. Returns a list of tuples. Tests cover "
    "empty input, a single interval, overlap, touching endpoints, unsorted "
    "input and containment.",
    "Balanced coding record: sorting plus a linear sweep.",
)

# ---------------------------------------------------------------------------
# debugging
# ---------------------------------------------------------------------------

BSEARCH = '''def index_of(items: list[int], target: int) -> int:
    """Return the index of target in a sorted list, or -1 when absent.

    Binary search over the half-open range [low, high]. The classic bug is
    testing ``low < high`` (which misses the final element) or updating a bound
    to ``mid`` instead of ``mid +- 1`` (which loops forever).
    """
    low, high = 0, len(items) - 1
    while low <= high:
        mid = (low + high) // 2
        if items[mid] == target:
            return mid
        if items[mid] < target:
            low = mid + 1
        else:
            high = mid - 1
    return -1
'''

BSEARCH_T = '''from main import index_of


def test_finds_each_element():
    items = [1, 3, 5, 7, 9]
    for expected, value in enumerate(items):
        assert index_of(items, value) == expected


def test_missing_value_returns_minus_one():
    assert index_of([1, 3, 5, 7, 9], 4) == -1


def test_empty_list_returns_minus_one():
    assert index_of([], 1) == -1


def test_single_element_found():
    assert index_of([42], 42) == 0


def test_single_element_missing():
    assert index_of([42], 7) == -1


def test_duplicates_return_a_valid_index():
    items = [1, 2, 2, 2, 3]
    index = index_of(items, 2)
    assert items[index] == 2
'''

code_rec(
    "seed-category-bsearch-4002",
    "This binary search is wrong: it skips the last element and can hang on "
    "some inputs. Fix it so index_of(sorted_items, target) returns the index "
    "or -1, and keep it O(log n).",
    "debugging", "medium", BSEARCH, BSEARCH_T,
    "The loop must use low <= high over the inclusive range, and each bound "
    "update must move past mid (low = mid + 1, high = mid - 1). Tests cover "
    "every element, a missing value, empty input, a single element and "
    "duplicates.",
    "Debugging record: boundary condition and loop-progress bug.",
)

CONFIG = '''def required_int(config: dict, key: str) -> int:
    """Read a required non-negative integer from a config mapping.

    Missing keys, booleans (which are ints in Python), wrong types and negative
    values are all rejected with a message that names the key, so a bad config
    fails loudly at startup instead of producing a confusing error later.
    """
    if key not in config:
        raise KeyError(f"missing key: {key}")

    value = config[key]

    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{key} must be an int")
    if value < 0:
        raise ValueError(f"{key} must be non-negative")

    return value
'''

CONFIG_T = '''import pytest

from main import required_int


def test_reads_value():
    assert required_int({"workers": 4}, "workers") == 4


def test_missing_key_names_the_key():
    with pytest.raises(KeyError, match="workers"):
        required_int({}, "workers")


def test_string_value_is_a_type_error():
    with pytest.raises(TypeError):
        required_int({"workers": "4"}, "workers")


def test_bool_is_rejected_even_though_it_is_an_int():
    with pytest.raises(TypeError):
        required_int({"workers": True}, "workers")


def test_negative_value_is_rejected():
    with pytest.raises(ValueError):
        required_int({"workers": -1}, "workers")


def test_zero_is_allowed():
    assert required_int({"workers": 0}, "workers") == 0
'''

code_rec(
    "seed-category-config-4003",
    "Write required_int(config, key) that validates a required non-negative "
    "integer setting. Missing keys, wrong types, booleans and negative values "
    "must fail with a clear error that names the key.",
    "debugging", "medium", CONFIG, CONFIG_T,
    "Checks key presence, rejects bool explicitly (bool subclasses int), "
    "requires int, rejects negatives, and returns the value. Tests cover the "
    "happy path, missing key, string, bool, negative and zero.",
    "Debugging record: input validation and failure messages.",
)

# ---------------------------------------------------------------------------
# security
# ---------------------------------------------------------------------------

TOKENS = '''import hmac


def tokens_equal(provided: object, expected: str) -> bool:
    """Compare a submitted token with the expected one in constant time.

    ``==`` returns early on the first differing byte, which leaks the length of
    a matching prefix through timing. hmac.compare_digest does not. Non-string
    input is rejected rather than coerced.
    """
    if not isinstance(provided, str) or not isinstance(expected, str):
        return False
    return hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8"))


def is_allowed(user: object, allowlist: list[str]) -> bool:
    """Exact-match allowlist check; unknown or non-string users are denied."""
    if not isinstance(user, str) or not user:
        return False
    return user in set(allowlist)
'''

TOKENS_T = '''from main import is_allowed, tokens_equal


def test_matching_tokens():
    assert tokens_equal("abc123", "abc123") is True


def test_different_tokens():
    assert tokens_equal("abc123", "abc124") is False


def test_non_string_token_is_rejected():
    assert tokens_equal(None, "abc") is False
    assert tokens_equal(123, "123") is False


def test_empty_token_matches_only_empty_expected():
    assert tokens_equal("", "") is True
    assert tokens_equal("", "x") is False


def test_allowlist_membership():
    assert is_allowed("alice", ["alice", "bob"]) is True
    assert is_allowed("eve", ["alice", "bob"]) is False


def test_allowlist_denies_empty_and_non_string():
    assert is_allowed("", ["alice"]) is False
    assert is_allowed(None, ["alice"]) is False
'''

code_rec(
    "seed-category-tokens-4004",
    "Implement token verification that is safe against timing attacks: "
    "tokens_equal(provided, expected) using a constant-time comparison, and "
    "is_allowed(user, allowlist) with exact-match semantics. Non-string input "
    "must be denied, not coerced.",
    "security", "medium", TOKENS, TOKENS_T,
    "tokens_equal uses hmac.compare_digest over UTF-8 bytes, with type checks "
    "before comparison; is_allowed checks membership against a set and denies "
    "empty or non-string users. Tests cover match, mismatch, non-strings, empty "
    "strings and allowlist denial.",
    "Security record: constant-time secret comparison and allowlists.",
)

SAFE_JOIN = '''from pathlib import Path


def safe_join(root: str, name: str) -> Path:
    """Resolve name beneath root, refusing anything that escapes it.

    Rejects absolute paths, empty names, and any resolved target outside the
    root, which covers "..", encoded traversal, and symlink escapes after
    resolution.
    """
    if not isinstance(name, str) or not name.strip():
        raise ValueError("name must be a non-empty string")
    if name.startswith(("/", "\\\\")):
        raise ValueError("name must be relative")

    root_path = Path(root).resolve()
    target = (root_path / name).resolve()

    if target != root_path and root_path not in target.parents:
        raise ValueError("path escapes the root directory")

    return target
'''

SAFE_JOIN_T = '''import pytest

from main import safe_join


def test_joins_a_normal_file(tmp_path):
    result = safe_join(str(tmp_path), "notes.txt")
    assert result.name == "notes.txt"
    assert result.parent == tmp_path.resolve()


def test_joins_nested_path(tmp_path):
    result = safe_join(str(tmp_path), "a/b/c.txt")
    assert result == (tmp_path / "a/b/c.txt").resolve()


def test_rejects_parent_traversal(tmp_path):
    with pytest.raises(ValueError):
        safe_join(str(tmp_path), "../secret.txt")


def test_rejects_deep_traversal(tmp_path):
    with pytest.raises(ValueError):
        safe_join(str(tmp_path), "a/../../secret.txt")


def test_rejects_absolute_path(tmp_path):
    with pytest.raises(ValueError):
        safe_join(str(tmp_path), "/etc/hosts")


def test_rejects_empty_name(tmp_path):
    with pytest.raises(ValueError):
        safe_join(str(tmp_path), "")
'''

code_rec(
    "seed-category-safepath-4005",
    "Implement safe_join(root, name) for user-supplied file names: reject "
    "absolute paths, empty names and any target that resolves outside root "
    "(traversal, including nested ..).",
    "security", "medium", SAFE_JOIN, SAFE_JOIN_T,
    "Resolves the root and the candidate path, then requires the target to be "
    "the root itself or have the root as a parent. Tests cover a normal file, a "
    "nested path, ../ traversal, deep traversal, an absolute path and an empty "
    "name.",
    "Security record: path traversal containment.",
)

# ---------------------------------------------------------------------------
# software_engineering
# ---------------------------------------------------------------------------

DISCOUNT = '''def discount(price: float, percent: float) -> float:
    """Apply a percentage discount to a price, rounded to cents."""
    if price < 0:
        raise ValueError("price must be non-negative")
    if not 0 <= percent <= 100:
        raise ValueError("percent must be between 0 and 100")
    return round(price * (100 - percent) / 100, 2)


def cart_total(items: list[tuple[float, int]], percent: float) -> float:
    """Total for [(unit_price, quantity), ...] after one discount rate."""
    return round(sum(discount(price, percent) * quantity for price, quantity in items), 2)


def invoice_total(
    items: list[tuple[float, int]],
    percent: float,
    shipping: float = 0.0,
) -> float:
    """Cart total plus shipping; one implementation of the discount rule."""
    if shipping < 0:
        raise ValueError("shipping must be non-negative")
    return round(cart_total(items, percent) + shipping, 2)
'''

DISCOUNT_T = '''import pytest

from main import cart_total, discount, invoice_total


def test_no_discount():
    assert discount(10.0, 0) == 10.0


def test_half_price():
    assert discount(10.0, 50) == 5.0


def test_rounds_to_cents():
    assert discount(9.99, 33) == 6.69


def test_cart_multiplies_quantities():
    assert cart_total([(10.0, 2), (5.0, 1)], 10) == 22.5


def test_invoice_adds_shipping():
    assert invoice_total([(10.0, 1)], 10, shipping=4.0) == 13.0


def test_invalid_percent_rejected():
    with pytest.raises(ValueError):
        discount(10.0, 101)


def test_negative_price_rejected():
    with pytest.raises(ValueError):
        discount(-1.0, 10)


def test_negative_shipping_rejected():
    with pytest.raises(ValueError):
        invoice_total([(10.0, 1)], 0, shipping=-2)
'''

code_rec(
    "seed-category-discount-4006",
    "A checkout module duplicated its discount maths in three places. Refactor "
    "it into one discount(price, percent) helper used by cart_total and "
    "invoice_total, with validation, and cover the behaviour with tests.",
    "software_engineering", "medium", DISCOUNT, DISCOUNT_T,
    "One discount helper validates price and percent and rounds to cents; "
    "cart_total sums discounted unit prices times quantity; invoice_total adds "
    "shipping on top of the same path. Tests cover no discount, 50%, rounding, "
    "quantities, shipping and each validation error.",
    "Engineering record: de-duplicate logic behind one validated helper.",
)

# ---------------------------------------------------------------------------
# reasoning
# ---------------------------------------------------------------------------

prose(
    "seed-category-reasoning-ev-4007",
    "A game offers a 1 in 6 chance to win 10 coins for a 2 coin entry fee. "
    "Is the game profitable for the player? Compute the expected value and "
    "explain what changes if the prize is 15 coins.",
    "reasoning", "medium",
    "Expected value is the sum of each outcome's value times its probability. "
    "Winning contributes (1/6) * 10 = 1.666..., and losing contributes "
    "(5/6) * 0 = 0. The expected payout is about 1.67 coins per play. The player "
    "pays 2 coins, so the expected net is 1.67 - 2 = -0.33 coins per play: the "
    "game is not profitable for the player. Over 60 plays the expected loss is "
    "about 20 coins.\n\n"
    "With a 15-coin prize the expected payout becomes (1/6) * 15 = 2.5 coins, "
    "so the expected net is 2.5 - 2 = +0.5 coins per play and the player now "
    "has a positive edge. The break-even prize solves p/6 = 2, so p = 12 coins: "
    "below 12 the house is ahead, above 12 the player is. Note that expected "
    "value says nothing about variance: a positive-edge game can still lose "
    "money in a short session, which is why bankroll and risk of ruin are "
    "separate questions from EV.",
    "Reasoning record: expected value with a break-even derivation.",
)

prose(
    "seed-category-reasoning-topk-4008",
    "You need the 10 highest scores from a stream of 1,000,000 integers. "
    "Compare sorting everything, maintaining a heap, and a quickselect. Which "
    "do you choose and why? Give the complexity of each.",
    "reasoning", "medium",
    "Sorting everything is O(n log n) time and O(n) extra memory for a copy: "
    "about 20 million comparisons for a million items, plus the allocation, to "
    "answer a question that needs only ten values. It is the simplest code and "
    "acceptable when n is small or the array is already needed sorted, but it "
    "does the most work here.\n\n"
    "A min-heap of size k is the standard streaming answer. Push each item, and "
    "when the heap exceeds k, pop the smallest: O(n log k) time and O(k) extra "
    "memory. For n = 10^6 and k = 10 that is roughly 3.3 million comparisons, "
    "and it works when the input arrives over a network or does not fit in "
    "memory. The heap's contents are the answer set at any moment, which also "
    "makes it the right choice for a live leaderboard.\n\n"
    "Quickselect finds the k-th largest in expected O(n) time with O(1) extra "
    "memory, then one pass collects the top k. It is asymptotically fastest for "
    "a fixed in-memory array, but it needs random access, has a worst case of "
    "O(n^2) without a good pivot strategy (median-of-medians fixes that with a "
    "constant-factor cost), and it mutates or copies the array.\n\n"
    "Choice: use the heap for streams, unknown or unbounded input, and k much "
    "smaller than n; use quickselect for a fixed in-memory array where the "
    "extra comparisons matter; sort only when n is small or the sorted order is "
    "wanted anyway.",
    "Reasoning record: algorithm selection with complexity trade-offs.",
)

# ---------------------------------------------------------------------------
# agentic
# ---------------------------------------------------------------------------

prose(
    "seed-category-agentic-fix-4009",
    "A repository has one failing test. Describe the exact agent loop you would "
    "run with file, search, shell and sandbox tools to fix it, including what "
    "you would do when the first attempt does not pass.",
    "agentic", "hard",
    "1. Observe. Read the task, then the project context and README so the "
    "conventions and test command are known. Do not edit anything yet.\n\n"
    "2. Locate. Run the failing test to capture the exact command and output. "
    "Use search to find the assertion, then read the implementation file it "
    "exercises and the test file. Read the whole function, not just the line "
    "from the traceback.\n\n"
    "3. Hypothesize. State one cause that explains the failure. Example: 'the "
    "parser drops the last token because the loop stops at len - 1'. Design the "
    "smallest change that would disprove or confirm it.\n\n"
    "4. Act. Make the smallest edit with write_file (show the diff intent), then "
    "run the single failing test in the sandbox, not the whole suite, so the "
    "feedback is fast.\n\n"
    "5. Verify. If it passes, run the full suite. If it fails, read the new "
    "output: a different error means the hypothesis was wrong, so revert the "
    "edit and go back to step 3; the same error means the fix was incomplete. "
    "Never apply a second speculative change on top of an unverified one.\n\n"
    "6. Guard. Add a regression test that fails without the fix. Check that no "
    "other test changed status.\n\n"
    "7. Report. Say what file changed, why, which command was run, and the "
    "result. Mention anything not verified. Do not claim the suite passes "
    "without having run it.",
    "Agentic record: observe-act-verify loop with failure recovery.",
)

# ---------------------------------------------------------------------------
# general_chat
# ---------------------------------------------------------------------------

prose(
    "seed-category-chat-codebase-4010",
    "How do you get productive in an unfamiliar codebase quickly? Give a "
    "concrete first-day plan.",
    "general_chat", "easy",
    "Start from the entry points, not from the file tree. Read the README and "
    "the build/run config, then find the process that starts the app (main, "
    "server, CLI) and follow one request or command through it end to end. "
    "Reading one real path teaches more than browsing fifty files.\n\n"
    "Next, find the boundaries: where input enters, where data is persisted, "
    "and where the code talks to other systems. Those seams are where bugs and "
    "changes concentrate. Note the test command and run it once to see the "
    "baseline; a failing test on day one is information, not a crisis.\n\n"
    "Then make a tiny, safe change and ship it through the full loop: edit, "
    "test, commit. That teaches the tooling and the review conventions faster "
    "than any document. While doing it, keep a scratch file of names: the "
    "modules, the key types, the commands, and the people who own each area. "
    "Ask one specific question per unknown rather than a broad 'how does this "
    "work'.\n\n"
    "Finally, write down what you learned in the repo itself (a short note in "
    "the docs or a comment where it belongs). You will forget the details in a "
    "week, and the next person will start from your map instead of the file "
    "tree.",
    "General chat record: onboarding method.",
)

prose(
    "seed-category-chat-estimate-4011",
    "How should an engineer estimate a task and communicate the estimate "
    "honestly, without either sandbagging or over-promising?",
    "general_chat", "easy",
    "Break the task into the smallest pieces you can actually reason about — "
    "ideally half a day or less each — and estimate the pieces rather than the "
    "whole. For each piece, identify the assumption that could make it twice as "
    "long: an unclear interface, a migration, an external dependency, "
    "unfamiliar code. Those are the risks worth naming out loud.\n\n"
    "Give a range and a confidence level, not a single number: 'two to four "
    "days, I'm confident about the lower bound and the upper end depends on "
    "whether the legacy table needs a backfill'. Say which part is uncertain "
    "and what would resolve it. A range with a named risk is more useful than a "
    "precise guess, and it invites the right question instead of false "
    "certainty.\n\n"
    "Add the cost you are not counting: review time, tests, rollout, "
    "documentation, and the interruption budget. Update the estimate as soon as "
    "new information arrives, before the deadline, and say what changed. "
    "Missing an estimate quietly is worse than revising it early.\n\n"
    "Finally, separate estimate from commitment. An estimate is a forecast; a "
    "commitment is a promise with a trade-off attached. If the date is fixed, "
    "state what scope moves instead of silently absorbing the difference.",
    "General chat record: estimation and risk communication.",
)


def main() -> int:
    out = Path(__file__).resolve().parent.parent / "datasets" / "candidates" / "seed_core_categories.jsonl"
    with out.open("w", encoding="utf-8") as handle:
        for record in RECORDS:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"wrote {len(RECORDS)} records to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
