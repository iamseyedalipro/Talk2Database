"""Tests for the prompt store's rendering fallback and combo validation."""

from __future__ import annotations

import pytest
from app.services.ai.prompts import DEFAULT_PROMPTS
from app.services.app_settings import validate_combos
from app.services.clarity.fetcher import plan_combos
from app.services.prompt_store import render_ask_system


def test_default_ask_template_renders_label() -> None:
    rendered = render_ask_system(DEFAULT_PROMPTS["ask_system_template"], "PostgreSQL")
    assert "PostgreSQL" in rendered
    assert "{label}" not in rendered


def test_custom_template_renders() -> None:
    assert render_ask_system("Write {label} SQL.", "MySQL") == "Write MySQL SQL."


def test_bad_placeholder_falls_back_to_default() -> None:
    rendered = render_ask_system("Broken {labl} template", "MariaDB")
    assert rendered == DEFAULT_PROMPTS["ask_system_template"].format(label="MariaDB")


def test_stray_brace_falls_back_to_default() -> None:
    rendered = render_ask_system("Return {sql, explanation}", "PostgreSQL")
    assert rendered == DEFAULT_PROMPTS["ask_system_template"].format(label="PostgreSQL")


def test_validate_combos_accepts_defaults() -> None:
    validate_combos([[], ["URL"], ["URL", "Device"]])


@pytest.mark.parametrize(
    "combos",
    [
        [
            ["URL"],
            ["Device"],
            ["OS"],
            ["Browser"],
            ["Source"],
            ["Medium"],
            ["Campaign"],
            ["Channel"],
            [],
            ["URL", "Device"],
            ["URL", "OS"],
        ],  # 11 combos > 10/day budget
        [["URL", "Device", "OS", "Browser"]],  # >3 dimensions
        [["Bogus"]],  # unknown dimension
        [["URL", "URL"]],  # repeated dimension
        [["URL"], ["URL"]],  # duplicate combo
    ],
)
def test_validate_combos_rejects_invalid(combos: list[list[str]]) -> None:
    with pytest.raises(ValueError):
        validate_combos(combos)


def test_plan_combos_truncates_to_remaining_budget() -> None:
    combos = [[], ["URL"], ["Device"]]
    assert plan_combos(combos, requests_used=0) == combos
    assert plan_combos(combos, requests_used=8) == [[], ["URL"]]
    assert plan_combos(combos, requests_used=10) == []
    assert plan_combos(combos, requests_used=12) == []
