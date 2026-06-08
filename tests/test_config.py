"""Test caricamento config. Caricano i file reali: validano anche config/*.toml."""

import pytest

from poc_istruzioni.config import load_prices, load_settings


def test_settings_model_per_scopo() -> None:
    s = load_settings()
    # Opus-class per i compiti one-time, Haiku-class per router/runtime.
    assert s.model_for("conversion") == "claude-opus-4-8"
    assert s.model_for("compile") == "claude-opus-4-8"
    assert s.model_for("router") == "claude-haiku-4-5"
    assert s.model_for("answer") == "claude-opus-4-8"  # baseline B: risposta con Opus


def test_settings_scope_sconosciuto_solleva() -> None:
    s = load_settings()
    with pytest.raises(KeyError):
        s.model_for("non_esiste")


def test_settings_parametri_operativi() -> None:
    s = load_settings()
    assert s.llm.max_tokens > 0
    assert 150 <= s.rendering.dpi <= 200  # FR-B1
    assert 0.0 < s.crosscheck.overlap_threshold < 1.0


def test_prices_tariffe_note() -> None:
    p = load_prices()
    opus = p.for_model("claude-opus-4-8")
    assert opus.input_per_mtok == 5.00
    assert opus.output_per_mtok == 25.00
    haiku = p.for_model("claude-haiku-4-5")
    assert haiku.input_per_mtok == 1.00
    assert haiku.output_per_mtok == 5.00


def test_prices_cache_multipliers() -> None:
    p = load_prices()
    assert p.cache.read_multiplier == 0.10
    assert p.cache.write_5m_multiplier == 1.25
    assert p.cache.write_1h_multiplier == 2.00


def test_prices_modello_sconosciuto_solleva() -> None:
    p = load_prices()
    with pytest.raises(KeyError):
        p.for_model("modello-inesistente")
