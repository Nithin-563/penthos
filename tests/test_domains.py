"""Tests for domain routing and the web/game/3D playbooks."""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from inference.codegen import generate_project
from inference.prompt import (
    DOMAIN_PLAYBOOKS,
    build_code_prompt,
    detect_domain,
    domain_playbook,
)


def test_detects_web_requests():
    assert detect_domain("Build a responsive landing page in HTML and CSS") == "web"
    assert detect_domain("Make an accessible React component for a pricing table") == "web"


def test_detects_game_requests():
    assert detect_domain("Make a 2D platformer game with a player, enemies and collision") == "game"
    assert detect_domain("write a pygame game loop with sprites") == "game"


def test_detects_3d_requests():
    assert detect_domain("Render a rotating 3D cube with WebGL and a camera") == "graphics3d"
    assert detect_domain("write a shader using a perspective projection matrix") == "graphics3d"


def test_general_fallback():
    assert detect_domain("parse a CSV of invoices") == "general"
    assert detect_domain("") == "general"


def test_every_playbook_has_content():
    for name, text in DOMAIN_PLAYBOOKS.items():
        assert len(text) > 100, name


def test_domain_playbook_falls_back_to_general():
    assert domain_playbook("nope") == DOMAIN_PLAYBOOKS["general"]
    assert domain_playbook(None) == DOMAIN_PLAYBOOKS["general"]


def test_code_prompt_includes_detected_domain_notes():
    prompt = build_code_prompt("Build a responsive landing page with a hero section")
    assert "DOMAIN NOTES:" in prompt
    assert "TASK: Build a responsive landing page" in prompt
    # The web checklist, not the game one.
    assert "Breakpoints at 640" in prompt
    assert "fixed-timestep" not in prompt


def test_code_prompt_honours_explicit_domain():
    prompt = build_code_prompt("make a thing", domain="game")
    assert "fixed-timestep" in prompt


def test_build_pipeline_injects_playbook(tmp_path):
    seen = []

    def generate(messages):
        seen.append(messages[-1]["content"])
        if "Break this build request" in messages[-1]["content"]:
            return json.dumps({
                "project": "demo",
                "language": "python",
                "entrypoint": "app.py",
                "files": [{"path": "app.py", "purpose": "entry point"}],
            })
        return "print('hi')"

    generate_project(
        "build a 3D renderer demo with a camera",
        generate,
        tmp_path,
        review=False,
    )
    assert any("DOMAIN NOTES:" in prompt and "model -> world -> view" in prompt for prompt in seen)
