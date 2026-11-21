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


def test_limity_llm_z_konfiguracji(tmp_path, monkeypatch):
    from app import anonimizacja
    from app.config import settings
    from app.sprawy import analiza

    p = tmp_path / "config.toml"
    p.write_text("[llm.limity]\nprzedmiot_max = 30\nanonimizacja_fragment = 500\nanonimizacja_fragmenty = 2\n")
    limity = load_settings(p).llm.limity
    assert (limity.przedmiot_max, limity.projekt_wzor) == (30, 2500)  # reszta domyślna

    monkeypatch.setattr(settings.llm, "limity", limity)
    assert len(analiza._pierwsza_linia("Proszę o wykaz " + "bardzo " * 20 + "długi")) == 30
    czesci = anonimizacja._czesci("akapit\n" * 400)
    assert len(czesci) == 2 and all(len(c) <= 500 for _, c in czesci)

    p.write_text("[llm.limity]\nanonimizacja_fragmenty = 0\n")
    with pytest.raises(ValidationError):
        load_settings(p)


def test_temperatury_z_konfiguracji(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text("[llm.temperatury]\nprojekt = 0.7\n")
    t = load_settings(p).llm.temperatury
    assert (t.projekt, t.analiza, t.wydzialy, t.anonimizacja) == (0.7, 0, 0, 0)

    p.write_text("[llm.temperatury]\nprojekt = 3\n")
    with pytest.raises(ValidationError):
        load_settings(p)
