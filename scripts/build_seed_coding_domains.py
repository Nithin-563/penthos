#!/usr/bin/env python3
"""Build the curated coding-domain seed pack.

Writes `datasets/candidates/seed_coding_domains.jsonl`: hand-authored records
covering web/UI work, 2D and 3D game and graphics code, the 1D/2D math those
domains lean on, and general engineering practice. Executable records ship a
correct implementation plus a passing pytest suite; knowledge records are
non-executable prose (`language: ""`, no code) so the pipeline routes them to
`not_required` instead of rejecting them for having nothing to run.

The output is committed as source data; rerun this script only when editing the
records here.

    python scripts/build_seed_coding_domains.py
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
            "notes": "Curated domain seed for Pari coding training.",
        },
    }
    base.update(kw)
    base.setdefault("id", "seed-domain-unknown")
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
# Executable records
# ---------------------------------------------------------------------------

VEC2 = '''from math import hypot


def normalize(x: float, y: float) -> tuple[float, float]:
    """Return the unit vector in the direction of (x, y).

    A zero-length vector has no direction; returning (0.0, 0.0) keeps callers
    from dividing by zero or emitting NaN into a physics step.
    """
    length = hypot(x, y)
    if length == 0.0:
        return (0.0, 0.0)
    return (x / length, y / length)


def dot(ax: float, ay: float, bx: float, by: float) -> float:
    return ax * bx + ay * by


def reflect(dx: float, dy: float, nx: float, ny: float) -> tuple[float, float]:
    """Reflect a direction around a unit normal (bounce off a wall)."""
    scale = 2.0 * dot(dx, dy, nx, ny)
    return (dx - scale * nx, dy - scale * ny)
'''

VEC2_T = '''import pytest

from main import dot, normalize, reflect


def test_normalize_unit_length():
    x, y = normalize(3.0, 4.0)
    assert x == pytest.approx(0.6)
    assert y == pytest.approx(0.8)


def test_normalize_zero_vector():
    assert normalize(0.0, 0.0) == (0.0, 0.0)


def test_normalize_negative_direction():
    x, y = normalize(-1.0, 0.0)
    assert x == pytest.approx(-1.0)
    assert y == pytest.approx(0.0)


def test_dot_orthogonal_is_zero():
    assert dot(1.0, 0.0, 0.0, 1.0) == 0.0


def test_reflect_off_horizontal_floor():
    assert reflect(1.0, -1.0, 0.0, 1.0) == pytest.approx((1.0, 1.0))
'''

code_rec(
    "seed-domain-vec2-2001",
    "Implement 2D vector helpers for a game physics step: normalize(x, y), "
    "dot(ax, ay, bx, by) and reflect(dx, dy, nx, ny). Normalizing a zero vector "
    "must not divide by zero.",
    "coding", "easy", VEC2, VEC2_T,
    "normalize divides by hypot and returns (0.0, 0.0) for a zero vector; dot "
    "is the scalar product; reflect subtracts twice the projection along a unit "
    "normal, giving a correct bounce. Tests cover unit length, zero input, "
    "negative directions and a floor bounce.",
    "2D math foundation for games and graphics.",
)

AABB = '''def overlaps(a: tuple[float, float, float, float],
             b: tuple[float, float, float, float]) -> bool:
    """True when two (x, y, width, height) boxes intersect.

    Edges that merely touch do not count as an overlap, which stops a resting
    player from being reported as colliding with the floor every frame.
    """
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return (
        ax < bx + bw
        and bx < ax + aw
        and ay < by + bh
        and by < ay + ah
    )


def penetration(a: tuple[float, float, float, float],
                b: tuple[float, float, float, float]) -> tuple[float, float]:
    """Return the smallest (dx, dy) that moves box a out of box b."""
    if not overlaps(a, b):
        return (0.0, 0.0)

    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    a_cx, a_cy = ax + aw / 2.0, ay + ah / 2.0
    b_cx, b_cy = bx + bw / 2.0, by + bh / 2.0

    overlap_x = (aw + bw) / 2.0 - abs(a_cx - b_cx)
    overlap_y = (ah + bh) / 2.0 - abs(a_cy - b_cy)

    if overlap_x < overlap_y:
        return (overlap_x if a_cx > b_cx else -overlap_x, 0.0)
    # Screen space: +y points down, so a box above b is pushed up (-y).
    return (0.0, -overlap_y if a_cy < b_cy else overlap_y)
'''

AABB_T = '''from main import overlaps, penetration


def test_overlapping_boxes():
    assert overlaps((0, 0, 10, 10), (5, 5, 10, 10)) is True


def test_touching_edges_are_not_overlap():
    assert overlaps((0, 0, 10, 10), (10, 0, 10, 10)) is False


def test_separated_boxes():
    assert overlaps((0, 0, 5, 5), (100, 100, 5, 5)) is False


def test_no_penetration_when_separate():
    assert penetration((0, 0, 10, 10), (50, 50, 10, 10)) == (0.0, 0.0)


def test_push_out_along_smallest_axis():
    dx, dy = penetration((0, 0, 10, 10), (8, 1, 10, 10))
    assert dx == -2
    assert dy == 0


def test_push_out_vertically_when_that_is_smaller():
    dx, dy = penetration((0, 0, 10, 10), (1, 9, 10, 10))
    assert dx == 0
    assert dy == -1
'''

code_rec(
    "seed-domain-aabb-2002",
    "Write axis-aligned bounding box helpers: overlaps(a, b) where each box is "
    "(x, y, width, height), and penetration(a, b) returning the smallest "
    "(dx, dy) that separates a from b.",
    "coding", "medium", AABB, AABB_T,
    "overlaps uses strict inequalities so touching edges do not collide. "
    "penetration compares the overlap on each axis and returns the smaller "
    "displacement with the correct sign, so a player slides along a wall "
    "instead of being teleported. Tests cover separated boxes, touching edges, "
    "and horizontal versus vertical separation.",
    "Collision core used by 2D games and UI hit-testing.",
)

STEP = '''class FixedStep:
    """Fixed-timestep accumulator for a game loop.

    Physics must advance in constant increments to stay stable and
    reproducible; rendering can happen at whatever rate the display allows.
    """

    def __init__(self, step: float = 1 / 60, max_steps: int = 5) -> None:
        if step <= 0:
            raise ValueError("step must be positive")
        if max_steps < 1:
            raise ValueError("max_steps must be at least 1")
        self.step = step
        self.max_steps = max_steps
        self.accumulator = 0.0

    def advance(self, delta_seconds: float) -> int:
        """Feed elapsed time in; return how many fixed updates to run."""
        if delta_seconds < 0:
            delta_seconds = 0.0
        # A long stall (debugger, tab switch) must not freeze the game while
        # hundreds of catch-up steps run.
        self.accumulator += min(delta_seconds, 0.25)

        steps = 0
        while self.accumulator >= self.step and steps < self.max_steps:
            self.accumulator -= self.step
            steps += 1
        return steps

    def alpha(self) -> float:
        """Interpolation factor between the last two physics states."""
        return self.accumulator / self.step
'''

STEP_T = '''import pytest

from main import FixedStep


def test_returns_expected_step_count():
    loop = FixedStep(step=1 / 60)
    assert loop.advance(1 / 60) == 1
    assert loop.advance(3 / 60) == 3


def test_accumulates_partial_time():
    loop = FixedStep(step=0.1)
    assert loop.advance(0.05) == 0
    assert loop.advance(0.05) == 1


def test_caps_catch_up_steps():
    loop = FixedStep(step=0.01, max_steps=3)
    assert loop.advance(10.0) == 3


def test_negative_delta_is_ignored():
    loop = FixedStep(step=0.1)
    assert loop.advance(-5.0) == 0


def test_invalid_configuration_raises():
    with pytest.raises(ValueError):
        FixedStep(step=0)
    with pytest.raises(ValueError):
        FixedStep(max_steps=0)


def test_alpha_is_between_zero_and_one():
    loop = FixedStep(step=0.1)
    loop.advance(0.15)
    assert 0.0 <= loop.alpha() < 1.0
'''

code_rec(
    "seed-domain-fixedstep-2003",
    "Implement a fixed-timestep accumulator for a game loop: "
    "advance(delta_seconds) returns how many fixed updates to run, clamps "
    "pathological deltas, and exposes alpha() for render interpolation.",
    "coding", "medium", STEP, STEP_T,
    "FixedStep adds clamped delta to an accumulator, emits at most max_steps "
    "updates, and keeps the remainder for interpolated rendering. Negative "
    "deltas and invalid configuration are rejected. Tests cover exact steps, "
    "partial accumulation, catch-up capping and alpha bounds.",
    "Deterministic game loop, the backbone of stable 2D/3D physics.",
)

PROJ = '''import math


def project_point(
    x: float,
    y: float,
    z: float,
    *,
    fov_degrees: float = 60.0,
    width: int = 800,
    height: int = 600,
    near: float = 0.1,
) -> tuple[float, float]:
    """Project a camera-space point to screen pixels.

    Camera space: +x right, +y up, -z forward (right-handed). Points at or
    behind the near plane cannot be projected and raise instead of returning
    garbage coordinates.
    """
    if width <= 0 or height <= 0:
        raise ValueError("viewport must be positive")
    if not 0.0 < fov_degrees < 180.0:
        raise ValueError("fov must be between 0 and 180")
    if z >= -near:
        raise ValueError("point is at or behind the near plane")

    depth = -z
    f = 1.0 / math.tan(math.radians(fov_degrees) / 2.0)
    aspect = width / height

    ndc_x = (x * f / aspect) / depth
    ndc_y = (y * f) / depth

    screen_x = (ndc_x * 0.5 + 0.5) * width
    screen_y = (1.0 - (ndc_y * 0.5 + 0.5)) * height
    return (screen_x, screen_y)
'''

PROJ_T = '''import pytest

from main import project_point


def test_point_on_axis_projects_to_center():
    x, y = project_point(0.0, 0.0, -1.0)
    assert x == pytest.approx(400.0)
    assert y == pytest.approx(300.0)


def test_point_right_of_axis_projects_right_of_center():
    x, _ = project_point(1.0, 0.0, -5.0)
    assert x > 400.0


def test_further_point_is_closer_to_center():
    near_x, _ = project_point(1.0, 0.0, -2.0)
    far_x, _ = project_point(1.0, 0.0, -20.0)
    assert abs(near_x - 400.0) > abs(far_x - 400.0)


def test_behind_camera_raises():
    with pytest.raises(ValueError):
        project_point(0.0, 0.0, 1.0)


def test_invalid_viewport_raises():
    with pytest.raises(ValueError):
        project_point(0.0, 0.0, -1.0, width=0)
'''

code_rec(
    "seed-domain-projection-2004",
    "Implement camera-space perspective projection to screen pixels with a "
    "vertical FOV, aspect ratio from the viewport, and a near plane. Reject "
    "points at or behind the near plane and invalid viewports.",
    "coding", "medium", PROJ, PROJ_T,
    "The projection divides camera x and y by depth, scales by the focal term "
    "1/tan(fov/2), applies aspect to x, then maps NDC to pixels with y flipped "
    "for screen coordinates. Tests pin the centre, the horizontal direction, "
    "distance shrinking and the near-plane guard.",
    "Core 3D projection math behind every renderer.",
)

DDA = '''def cast(
    grid: list[list[int]],
    origin: tuple[float, float],
    direction: tuple[float, float],
    max_distance: float = 32.0,
) -> dict | None:
    """Cast a ray through a tile grid with a DDA traversal.

    grid[y][x] is truthy for a solid tile. Returns {"cell": (x, y),
    "distance": float} for the first solid tile, or None within range.
    """
    if not grid or max_distance <= 0:
        return None

    dx, dy = direction
    length = (dx * dx + dy * dy) ** 0.5
    if length == 0.0:
        return None
    dx, dy = dx / length, dy / length

    x, y = origin
    cell_x, cell_y = int(x // 1), int(y // 1)

    delta_x = abs(1.0 / dx) if dx else float("inf")
    delta_y = abs(1.0 / dy) if dy else float("inf")
    step_x = 1 if dx > 0 else -1
    step_y = 1 if dy > 0 else -1

    next_x = ((cell_x + (1 if dx > 0 else 0)) - x) / dx if dx else float("inf")
    next_y = ((cell_y + (1 if dy > 0 else 0)) - y) / dy if dy else float("inf")

    distance = 0.0
    while distance <= max_distance:
        if 0 <= cell_y < len(grid) and 0 <= cell_x < len(grid[cell_y]):
            if grid[cell_y][cell_x]:
                return {"cell": (cell_x, cell_y), "distance": max(0.0, distance)}
        if next_x < next_y:
            distance, next_x = next_x, next_x + delta_x
            cell_x += step_x
        else:
            distance, next_y = next_y, next_y + delta_y
            cell_y += step_y
        if distance == float("inf"):
            return None
    return None
'''

DDA_T = '''from main import cast


def test_hits_neighbouring_wall():
    grid = [[0, 1]]
    hit = cast(grid, (0.5, 0.5), (1.0, 0.0))
    assert hit is not None
    assert hit["cell"] == (1, 0)
    assert abs(hit["distance"] - 0.5) < 1e-9


def test_reports_starting_tile_when_solid():
    grid = [[1]]
    hit = cast(grid, (0.5, 0.5), (1.0, 0.0))
    assert hit == {"cell": (0, 0), "distance": 0.0}


def test_misses_when_nothing_in_range():
    grid = [[0, 0, 0]]
    assert cast(grid, (0.5, 0.5), (1.0, 0.0), max_distance=2.0) is None


def test_zero_direction_returns_none():
    assert cast([[1]], (0.5, 0.5), (0.0, 0.0)) is None


def test_empty_grid_returns_none():
    assert cast([], (0.0, 0.0), (1.0, 0.0)) is None
'''

code_rec(
    "seed-domain-raycast-2005",
    "Implement a DDA grid raycast: cast(grid, origin, direction, "
    "max_distance) returns the first solid cell and the distance to it, or "
    "None. Handle a zero direction, an empty grid, and starting inside a solid "
    "tile.",
    "coding", "hard", DDA, DDA_T,
    "The implementation normalizes the direction, initializes the next x/y grid "
    "crossings and per-cell deltas, then advances whichever crossing is nearer "
    "until a solid tile or max_distance. Tests cover a neighbouring wall hit at "
    "0.5, starting inside a solid tile, an out-of-range miss, a zero direction "
    "and an empty grid.",
    "2D visibility, lighting and shooting rays for games.",
)

CONTRAST = '''def _linear(channel: int) -> float:
    value = channel / 255.0
    if value <= 0.03928:
        return value / 12.92
    return ((value + 0.055) / 1.055) ** 2.4


def relative_luminance(rgb: tuple[int, int, int]) -> float:
    """WCAG relative luminance of an sRGB triple."""
    r, g, b = rgb
    for channel in (r, g, b):
        if not 0 <= channel <= 255:
            raise ValueError("channels must be in 0..255")
    return 0.2126 * _linear(r) + 0.7152 * _linear(g) + 0.0722 * _linear(b)


def contrast_ratio(fg: tuple[int, int, int], bg: tuple[int, int, int]) -> float:
    """WCAG contrast ratio between two colours, from 1.0 to 21.0."""
    lighter, darker = sorted(
        (relative_luminance(fg), relative_luminance(bg)), reverse=True
    )
    return round((lighter + 0.05) / (darker + 0.05), 2)


def passes_wcag(
    fg: tuple[int, int, int],
    bg: tuple[int, int, int],
    large_text: bool = False,
) -> bool:
    """AA threshold: 4.5:1 for body text, 3:1 for large text."""
    return contrast_ratio(fg, bg) >= (3.0 if large_text else 4.5)
'''

CONTRAST_T = '''import pytest

from main import contrast_ratio, passes_wcag, relative_luminance


def test_black_on_white_is_maximum():
    assert contrast_ratio((0, 0, 0), (255, 255, 255)) == 21.0


def test_same_colour_is_one():
    assert contrast_ratio((120, 120, 120), (120, 120, 120)) == 1.0


def test_ratio_is_symmetric():
    a = contrast_ratio((10, 20, 30), (250, 250, 250))
    b = contrast_ratio((250, 250, 250), (10, 20, 30))
    assert a == b


def test_white_on_white_fails_body_text():
    assert passes_wcag((255, 255, 255), (255, 255, 255)) is False


def test_large_text_threshold_is_lower():
    fg, bg = (130, 130, 130), (255, 255, 255)
    assert passes_wcag(fg, bg) is False
    assert passes_wcag(fg, bg, large_text=True) is True


def test_white_has_full_luminance():
    assert relative_luminance((255, 255, 255)) == pytest.approx(1.0)


def test_out_of_range_channel_raises():
    with pytest.raises(ValueError):
        relative_luminance((300, 0, 0))
'''

code_rec(
    "seed-domain-contrast-2006",
    "Implement a WCAG contrast checker for UI work: relative_luminance(rgb), "
    "contrast_ratio(fg, bg), and passes_wcag(fg, bg, large_text=False). "
    "Validate channel ranges and use the AA thresholds 4.5:1 and 3:1.",
    "coding", "medium", CONTRAST, CONTRAST_T,
    "Channels are linearized with the sRGB transfer function, weighted by "
    "luminance coefficients, and compared as (lighter+0.05)/(darker+0.05). AA "
    "thresholds are 4.5 for body text and 3.0 for large text. Tests cover the "
    "21:1 maximum, identical colours, symmetry, the 4.5/3 boundary and invalid "
    "channels.",
    "Accessible colour decisions in web and app UI.",
)

STATE = '''TRANSITIONS: dict[str, dict[str, str]] = {
    "idle": {"move": "run", "attack": "attack", "hurt": "hurt"},
    "run": {"stop": "idle", "attack": "attack", "hurt": "hurt"},
    "attack": {"finish": "idle", "hurt": "hurt"},
    "hurt": {"finish": "idle"},
}


def next_state(state: str, event: str) -> str:
    """Advance a sprite animation state machine by one event.

    Unknown events are ignored rather than crashing: animation events arrive
    from async sources and a stray one must not kill the entity update.
    """
    if state not in TRANSITIONS:
        raise ValueError(f"unknown state: {state}")
    return TRANSITIONS[state].get(event, state)


def frames_for(state: str, frame_ms: int = 100) -> int:
    """How many frames a state needs before it can finish naturally."""
    if frame_ms <= 0:
        raise ValueError("frame_ms must be positive")
    durations = {"idle": 4, "run": 6, "attack": 3, "hurt": 2}
    if state not in durations:
        raise ValueError(f"unknown state: {state}")
    return durations[state]
'''

STATE_T = '''import pytest

from main import frames_for, next_state


def test_idle_to_run_and_back():
    assert next_state("idle", "move") == "run"
    assert next_state("run", "stop") == "idle"


def test_attack_finishes_back_to_idle():
    assert next_state("attack", "finish") == "idle"


def test_unknown_event_is_ignored():
    assert next_state("run", "teleport") == "run"


def test_attack_from_any_locomotion_state():
    assert next_state("idle", "attack") == "attack"
    assert next_state("run", "attack") == "attack"


def test_unknown_state_raises():
    with pytest.raises(ValueError):
        next_state("dance", "move")


def test_frame_counts_and_validation():
    assert frames_for("attack") == 3
    with pytest.raises(ValueError):
        frames_for("attack", frame_ms=0)
'''

code_rec(
    "seed-domain-sprite-states-2007",
    "Implement a sprite animation state machine for a 2D game: "
    "next_state(state, event) following idle -> run -> attack -> hurt "
    "transitions, ignoring unknown events, plus frames_for(state) frame counts "
    "with validation.",
    "coding", "easy", STATE, STATE_T,
    "A transition table maps state to event to next state; unknown events "
    "return the current state so async animation events cannot crash the update "
    "loop, while an unknown state raises immediately. frames_for returns "
    "per-state lengths and validates input. Tests cover locomotion, attack, "
    "hurt, unknown events/states and frame counts.",
    "Animation state handling for 2D games.",
)

MAT = '''def identity() -> list[list[float]]:
    return [
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]


def multiply(a: list[list[float]], b: list[list[float]]) -> list[list[float]]:
    """Row-major 4x4 matrix product a * b."""
    return [
        [sum(a[row][k] * b[k][col] for k in range(4)) for col in range(4)]
        for row in range(4)
    ]


def translation(tx: float, ty: float, tz: float) -> list[list[float]]:
    matrix = identity()
    matrix[0][3], matrix[1][3], matrix[2][3] = tx, ty, tz
    return matrix


def rotation_y(angle_radians: float) -> list[list[float]]:
    import math

    c, s = math.cos(angle_radians), math.sin(angle_radians)
    return [
        [c, 0.0, s, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [-s, 0.0, c, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]


def transform_point(matrix: list[list[float]],
                    point: tuple[float, float, float]) -> tuple[float, float, float]:
    x, y, z = point
    return (
        matrix[0][0] * x + matrix[0][1] * y + matrix[0][2] * z + matrix[0][3],
        matrix[1][0] * x + matrix[1][1] * y + matrix[1][2] * z + matrix[1][3],
        matrix[2][0] * x + matrix[2][1] * y + matrix[2][2] * z + matrix[2][3],
    )
'''

MAT_T = '''import math

import pytest

from main import identity, multiply, rotation_y, transform_point, translation


def test_identity_leaves_points_alone():
    assert transform_point(identity(), (1.0, 2.0, 3.0)) == (1.0, 2.0, 3.0)


def test_translation_moves_points():
    moved = transform_point(translation(1.0, 2.0, 3.0), (0.0, 0.0, 0.0))
    assert moved == (1.0, 2.0, 3.0)


def test_rotation_y_quarter_turn_maps_x_to_minus_z():
    x, y, z = transform_point(rotation_y(math.pi / 2), (1.0, 0.0, 0.0))
    assert x == pytest.approx(0.0, abs=1e-9)
    assert y == pytest.approx(0.0)
    assert z == pytest.approx(-1.0)


def test_compose_translates_then_rotates():
    # translate * rotate: rotate the point, then move it.
    composed = multiply(translation(10.0, 0.0, 0.0), rotation_y(math.pi / 2))
    x, y, z = transform_point(composed, (1.0, 0.0, 0.0))
    assert x == pytest.approx(10.0)
    assert z == pytest.approx(-1.0)


def test_multiplying_by_identity_is_a_no_op():
    m = multiply(identity(), translation(3.0, 4.0, 5.0))
    assert transform_point(m, (0.0, 0.0, 0.0)) == (3.0, 4.0, 5.0)
'''

code_rec(
    "seed-domain-mat4-2008",
    "Implement row-major 4x4 transform helpers for a 3D engine: identity, "
    "multiply, translation, rotation_y and transform_point. Composition order "
    "must be readable from the multiplication order.",
    "coding", "hard", MAT, MAT_T,
    "Matrices are row-major, multiply is the standard triple loop, translation "
    "writes the last column, rotation_y uses cos/sin in the XZ plane, and "
    "transform_point applies rotation and translation. Tests verify identity, "
    "translation, a quarter turn mapping +x to -z, translate-after-rotate "
    "composition and identity multiplication.",
    "Foundation for 3D object transforms and cameras.",
)

# ---------------------------------------------------------------------------
# Knowledge records (design, engines, math, engineering practice)
# ---------------------------------------------------------------------------

prose(
    "seed-domain-web-system-3001",
    "Explain how to design a clean web UI system for a product page: spacing, "
    "type scale, colour tokens, responsive breakpoints and component states.",
    "general_chat", "medium",
    "Start with three scales and never invent a value outside them. Spacing: 4, "
    "8, 16, 24, 32, 48, 64px. Type: body 16px, small 14px, h3 20px, h2 28px, "
    "h1 40px, scaled fluidly with clamp() so headings adapt to the viewport. "
    "Radius: 6px controls, 12px cards. Colour tokens as CSS custom properties: "
    "surface, surface-raised, text, text-muted, border, accent, "
    "accent-contrast, danger, success. Body text needs 4.5:1 contrast against "
    "its surface; UI borders and large text need 3:1. Never encode state in hue "
    "alone: pair colour with an icon or label.\n\n"
    "Layout: mobile-first, CSS Grid for the page and Flexbox inside one axis. A "
    "container max-width near 1100px with 16px inline padding on small screens "
    "and 32px from 768px up. Breakpoints at 640, 768, 1024 and 1280px, checked "
    "at 320px and at 200% browser zoom. One vertical rhythm: sections get "
    "48-96px of block padding, not per-element margins.\n\n"
    "Every interactive component defines hover, focus-visible, active, "
    "disabled, loading, empty and error states. Focus rings are visible and "
    "never removed. Transitions run 150-250ms ease-out and honour "
    "prefers-reduced-motion. Build from variables and components so a theme "
    "change is one file, and write realistic copy instead of lorem ipsum so the "
    "layout is tested against real content lengths.",
    "Web design system knowledge for UI generation.",
)

prose(
    "seed-domain-web-perf-a11y-3002",
    "What makes a web page fast and accessible in practice? Give a concrete "
    "checklist a coding model can apply while generating a page.",
    "general_chat", "medium",
    "Accessibility: semantic elements first (button, nav, main, label), one h1 "
    "and a logical heading order, every input bound to a label, alt text that "
    "describes purpose, and keyboard operability for anything clickable. "
    "Announce dynamic changes with aria-live, keep focus order matching visual "
    "order, and never trap focus except in a modal that also provides a way "
    "out. Respect prefers-reduced-motion and prefers-color-scheme. Verify with "
    "keyboard only, not just with an automated audit.\n\n"
    "Performance: set explicit width and height on images and video to avoid "
    "layout shift; lazy-load below-the-fold media; use responsive srcset and "
    "modern formats. Use one variable font or a system font stack and preload "
    "only the critical face. Keep first-viewport CSS small and defer the rest. "
    "Avoid layout thrash: batch DOM reads and writes, animate transform and "
    "opacity rather than width or top. Ship JavaScript only where interaction "
    "needs it; a static page needs none. Compress text, cache immutable hashed "
    "assets, and set a content security policy that disallows inline script.\n\n"
    "Budget: LCP under 2.5s on a mid-range phone, CLS under 0.1, INP under "
    "200ms. Measure in the browser's performance panel on a throttled "
    "connection and report the numbers actually observed.",
    "Performance and accessibility checklist for generated web pages.",
)

prose(
    "seed-domain-game-feel-3003",
    "How do you make a small 2D game feel good to play? Cover the core loop, "
    "timing, feedback and difficulty curve with concrete numbers.",
    "general_chat", "medium",
    "Game feel is mostly latency, feedback and forgiveness. Run physics on a "
    "fixed 60Hz update and render between steps so motion is smooth; never "
    "multiply velocity by a raw frame delta. Poll held input every frame but "
    "treat actions as edge-triggered, buffer a jump press for about 120ms, and "
    "allow coyote time of about 100ms after leaving a ledge. Acceleration beats "
    "instant velocity: reach top speed in 100-150ms on the ground, slower in "
    "the air, with more gravity on descent than on ascent.\n\n"
    "Every meaningful event needs at least two feedback channels: visual "
    "(squash and stretch, flash, particle burst), audio (short, dry, "
    "pitch-shifted) and camera (2-4px shake decaying in about 100ms, plus a "
    "50-100ms hit-stop on a solid hit). Follow with a camera lerp around 0.1 "
    "per frame and a deadzone so small movements do not jitter the view.\n\n"
    "Design the loop in layers: a 10-second action loop (move, hit, reward), a "
    "2-minute goal loop (clear the room, unlock the door) and a session goal "
    "(finish the level). Teach one mechanic per level, then combine two, then "
    "test them under pressure. Keep tuning numbers in one config table, expose "
    "them live, and playtest with someone new: where they get stuck is the "
    "design problem, not their skill.",
    "Game feel and pacing knowledge for 2D game generation.",
)

prose(
    "seed-domain-game-2d-3004",
    "Explain how to build a 2D game world: tilemaps, collision layers, sprite "
    "sorting, camera and save data. Include the data structures.",
    "general_chat", "hard",
    "Represent the world as a tilemap: a 2D array of tile ids plus a parallel "
    "collision array, with a tileset atlas indexed by id. Tiles of 16 or 32px, "
    "chunked into regions (for example 32x32 tiles) so large levels load "
    "lazily. Keep entities as plain structs: id, position, velocity, size, "
    "collider layer and mask, sprite, animation state, health. Systems iterate "
    "arrays rather than nested object graphs; updates stay predictable and "
    "cache-friendly.\n\n"
    "Collision has two phases. Broad phase uses a uniform grid or a sweep over "
    "the tilemap to find candidate pairs; narrow phase uses AABB overlap and "
    "resolves one axis at a time so movement slides along walls instead of "
    "sticking. Use layers and masks (player, enemy, world, trigger, projectile) "
    "with explicit interactions, not boolean flags. Triggers fire events and do "
    "not block movement.\n\n"
    "Render order: background layers, tile layers, entities sorted by a sort "
    "key (y for top-down, layer then y for side-scrollers), then UI. Use one "
    "texture atlas and batch draw calls; keep a pixel-perfect camera for pixel "
    "art with integer scaling and a resolution-independent virtual viewport. "
    "The camera follows the player with a lerp, clamps to level bounds, and "
    "looks ahead in the facing direction.\n\n"
    "Save data is a versioned JSON document: version, level id, player "
    "position, inventory, flags, RNG seed, playtime. Migrate on load rather "
    "than trusting old shapes, and never serialize live object references.",
    "2D world architecture: tilemaps, collision layers, rendering order, camera, saves.",
)

prose(
    "seed-domain-3d-pipeline-3005",
    "Describe the 3D rendering pipeline from a mesh in a file to pixels on "
    "screen, naming every coordinate space and matrix.",
    "reasoning", "hard",
    "A vertex starts in model space. The model matrix places it in world space. "
    "The view matrix moves world space into camera space and is the inverse of "
    "the camera's own transform. The projection matrix maps camera space into "
    "clip space using field of view, aspect ratio and near/far planes. "
    "Perspective division by w yields normalized device coordinates in -1..1, "
    "and the viewport transform maps those to pixels, flipping y for screen "
    "coordinates. Every stage is a 4x4 matrix multiplication applied in that "
    "order: projection * view * model * position. Keep one convention, "
    "row-major or column-major, right-handed or left-handed, and state it.\n\n"
    "After the vertex stage, clipping removes geometry outside the frustum, "
    "then rasterization turns triangles into fragments with interpolated "
    "attributes (position, normal, uv). The depth buffer keeps the nearest "
    "fragment per pixel; backface culling discards triangles facing away based "
    "on winding order. Fragment shading computes lighting and texture colour, "
    "then the result is written, with blending for transparent surfaces drawn "
    "back to front.\n\n"
    "Practical rules: the near plane must be strictly greater than zero, aspect "
    "never zero, and depth precision improves with a larger near plane relative "
    "to far. Draw opaque geometry front-to-back for early depth rejection and "
    "transparent last. Batch by material and use instancing for repeated "
    "meshes. If something is invisible, check matrix order, winding, culling "
    "and the near plane before suspecting the shader.",
    "3D graphics pipeline and coordinate space knowledge.",
)

prose(
    "seed-domain-3d-lighting-3006",
    "Explain lighting for a small real-time 3D renderer: normals, diffuse and "
    "specular terms, gamma, and the common bugs.",
    "reasoning", "hard",
    "Lighting needs a unit surface normal per fragment. Transform normals with "
    "the inverse transpose of the model matrix, not the model matrix itself, or "
    "non-uniform scale will skew them; normalize again after interpolation. For "
    "a directional light, diffuse is max(dot(normal, light_direction), 0) times "
    "light colour times albedo. A specular term uses the half vector between "
    "light and view directions raised to a shininess exponent, scaled by a "
    "specular strength. Add a small ambient term so shadowed faces stay "
    "readable rather than pure black.\n\n"
    "Work in linear colour space and convert to sRGB only at the end: textures "
    "are usually authored in sRGB, so decode on sample, light in linear, then "
    "encode the final pixel. Skipping this blows out highlights and muddies "
    "gradients. Clamp before quantizing to 8 bits, and guard normalization so a "
    "zero-length normal cannot produce NaN.\n\n"
    "Common bugs: lighting that moves with the camera (normals in the wrong "
    "space), a hard black half (normal sign flipped or winding reversed), "
    "banding from poor depth precision (increase the near plane), and flat "
    "metal (no specular or environment term). Debug by rendering normals as "
    "RGB, then diffuse only, then specular only, before combining.",
    "Real-time lighting and shading knowledge for 3D generation.",
)

prose(
    "seed-domain-math-1d-2d-3007",
    "Explain the 1D and 2D math a coding model should reach for in animation, "
    "cameras and procedural content: interpolation, easing, springs, noise and "
    "raycasting.",
    "reasoning", "medium",
    "Interpolation is the backbone. lerp(a, b, t) = a + (b - a) * t with t "
    "clamped to 0..1. smoothstep applies 3t^2 - 2t^3 between two edges for "
    "eased motion. For cameras and UI follow, a critically damped spring avoids "
    "overshoot: keep a velocity, compute displacement to the target, apply "
    "stiffness and damping, and integrate on the fixed timestep; expose "
    "smoothTime in seconds rather than raw constants. Exponential smoothing "
    "(alpha = 1 - exp(-k * dt)) is the cheap frame-rate-independent alternative "
    "to naive lerp-per-frame.\n\n"
    "For movement feel, use easing per action: ease-out for arrivals, ease-in "
    "for departures, short overshoot only for playful UI. For aiming and "
    "rotation, wrap the shortest angle into -pi..pi before interpolating, or a "
    "sprite spins the long way round.\n\n"
    "For procedural variation, seeded value noise interpolates hashed lattice "
    "values; fractal sums layer octaves at halved amplitude and doubled "
    "frequency for terrain, clouds and texture. Always derive randomness from "
    "an explicit seed so runs reproduce. For 2D visibility, DDA raycasting "
    "walks grid cells along a ray, and a fan of rays builds a light polygon. "
    "For 3D picking, unproject the pointer through the inverse "
    "view-projection matrix and intersect a plane or AABB.",
    "1D/2D math toolkit: lerp, smoothstep, springs, noise, raycasting, angle wrapping.",
)

prose(
    "seed-domain-general-debug-3008",
    "Give a rigorous debugging method for a failing program, including how to "
    "bisect, form hypotheses, and prove a fix without introducing regressions.",
    "general_chat", "medium",
    "Reproduce first, deterministically. Capture the exact command, input, "
    "environment and commit. If it is intermittent, find the variable that "
    "makes it deterministic (seed, timing, ordering) before changing code. Read "
    "the actual error and the first stack frame that belongs to your code; do "
    "not start by editing the last line of the traceback.\n\n"
    "Reduce the failing case until removing anything makes it pass. That "
    "minimal reproducer is the specification for the bug. Then form one "
    "hypothesis that explains all observed symptoms and design a test that "
    "distinguishes it from the alternatives. Change one thing at a time; if the "
    "hypothesis is wrong, revert the probe instead of stacking guesses.\n\n"
    "For regressions, binary search history: git bisect with a script that "
    "exits non-zero on failure turns a week of guessing into minutes. Mark a "
    "known-good and a known-bad commit, let it run unattended, and inspect only "
    "the first bad commit instead of diffing everything by eye.\n\n"
    "Fix the root cause, not the symptom: a null check at the top of a function "
    "is fine only when null is a legitimate input. Add a regression test that "
    "fails on the old code and passes on the new code, then run the surrounding "
    "suite. Report what you verified and what you did not; a fix without a "
    "failing-then-passing test is still a guess.",
    "Debugging methodology knowledge for coding agents.",
)

prose(
    "seed-domain-general-api-3009",
    "How should a small HTTP API be designed so it stays usable? Cover "
    "resources, status codes, validation, errors, versioning and pagination.",
    "general_chat", "medium",
    "Model resources, not actions: /projects, /projects/{id}, "
    "/projects/{id}/tasks. Use nouns and plural segments, keep nesting shallow, "
    "and let query parameters filter rather than creating a route per filter. "
    "GET reads, POST creates, PATCH partially updates, PUT replaces, DELETE "
    "removes; make mutations idempotent or document explicitly when they are "
    "not.\n\n"
    "Status codes carry meaning: 200 for a read, 201 with a Location header for "
    "a create, 204 for a delete with no body, 400 for a malformed request, 401 "
    "for missing credentials, 403 for insufficient permission, 404 for a "
    "missing resource, 409 for a conflict, 422 for semantically invalid input, "
    "429 with Retry-After for rate limits, and 500 only for genuine server "
    "faults. Never return 200 with an error inside the body.\n\n"
    "Validate at the boundary and return field-level errors: {\"error\": "
    "{\"code\": \"validation_error\", \"message\": \"...\", \"fields\": "
    "{\"email\": \"invalid\"}}}. Keep error codes stable, messages "
    "human-readable, and never leak stack traces or secrets. Authenticate with "
    "a header token, authorize per resource, and scope every query by the "
    "authenticated owner instead of trusting an id from the client.\n\n"
    "Version the surface (/v1) and avoid breaking changes inside a version. "
    "Paginate lists with a cursor and a limit, defaulting small and documenting "
    "the maximum. Set explicit timeouts, cap request body size, and log request "
    "ids rather than bodies so production issues can be traced.",
    "HTTP API design knowledge for backend generation.",
)

prose(
    "seed-domain-general-tests-3010",
    "Explain how to write tests that actually protect a codebase, including "
    "what to test, what not to test, and how to keep them fast and trustworthy.",
    "general_chat", "medium",
    "Test behavior at the boundary you control, not implementation details. A "
    "good test names the scenario, sets up the smallest possible state, calls "
    "one public function, and asserts the observable result. One logical "
    "assertion per test keeps failures diagnostic. Cover the happy path, a "
    "boundary (empty, zero, maximum) and an error path for every non-trivial "
    "function; add an integration test for module wiring and one end-to-end "
    "test for the user-visible flow that matters most.\n\n"
    "Avoid asserting on private helpers, internal call order or log strings: "
    "those tests break on every refactor and teach nothing. Avoid sleeps; use "
    "deterministic clocks, seeded randomness and injected fakes. Use a "
    "temporary directory, an in-memory database or a stub server instead of "
    "production-like infrastructure when the point is logic. Keep the suite "
    "fast enough to run on every save; a test that takes minutes gets skipped, "
    "and a skipped test protects nothing.\n\n"
    "For bugs, write the failing test first, watch it fail for the right "
    "reason, then fix it. A test that passes before the fix is testing the "
    "wrong thing. Treat flaky tests as broken: find the shared state, ordering "
    "dependency or timing assumption and remove it rather than retrying. Use "
    "coverage as a hint, not a goal; a high number with no assertions is worse "
    "than a lower number with meaningful ones.",
    "Testing strategy knowledge for coding models.",
)


def main() -> int:
    out = Path(__file__).resolve().parent.parent / "datasets" / "candidates" / "seed_coding_domains.jsonl"
    with out.open("w", encoding="utf-8") as handle:
        for record in RECORDS:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"wrote {len(RECORDS)} records to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
