import pytest
from pydantic import ValidationError

from app.config import load_settings


def test_missing_file_gives_defaults(tmp_path):
    s = load_settings(tmp_path / "brak.toml")
    assert s.llm.model == "deepseek-chat" and s.llm.api_key == ""


def test_load_and_validate(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('[llm]\nbase_url = "http://localhost:11434/v1"\nmodel = "qwen"\n')
    s = load_settings(p)
    assert s.llm.base_url.startswith("http://localhost") and s.llm.timeout == 120

    p.write_text("[llm]\ntimeout = -5\n")
    with pytest.raises(ValidationError):
        load_settings(p)


def test_example_config_is_valid():
    from pathlib import Path

    load_settings(Path(__file__).parent.parent / "config.example.toml")
