"""Caricamento tipizzato della configurazione (settings.toml, prices.toml).

I parametri operativi e le tariffe sono dati di configurazione, mai hardcoded (FR-T2).
La validazione pydantic fa fallire presto su chiavi mancanti o valori non parsabili.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from pydantic import BaseModel, ConfigDict


def _config_dir() -> Path:
    """Cartella `config/` alla radice del repo (parents[2] da src/poc_istruzioni/)."""
    return Path(__file__).resolve().parents[2] / "config"


# --- settings.toml ---------------------------------------------------------


class Paths(BaseModel):
    model_config = ConfigDict(extra="forbid")
    data_dir: Path
    raw_dir: Path
    pages_dir: Path
    markdown_dir: Path
    db_path: Path


class LlmSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_tokens: int


class Rendering(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dpi: int


class Crosscheck(BaseModel):
    model_config = ConfigDict(extra="forbid")
    overlap_threshold: float


class Routing(BaseModel):
    """Regola di routing per-pagina (Rotta A=text-layer default, B=VLM). Soglie per documento."""

    model_config = ConfigDict(extra="forbid")
    min_words_text_route: int  # sotto questa soglia il text-layer è inutile -> VLM
    table_rects_force_vlm: int | None = None  # omesso = disattivato


class Gate(BaseModel):
    """Rafforzamenti del checksum (Nota raffinamento §M2). Configurabili per documento."""

    model_config = ConfigDict(extra="forbid")
    critical_words: list[str]  # parole la cui perdita è bloccante (negazioni, vincoli)
    code_label_overlap_min: float  # overlap minimo etichetta per coppia codice (anti-scambio)


class Lint(BaseModel):
    """Lint d'igiene sul markdown generato (Nota consolidata §B.2). Per documento."""

    model_config = ConfigDict(extra="forbid")
    orphan_warn_strings: list[str]  # stringhe orfane note -> warning (es. "Agenzia Entrate")


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    paths: Paths
    models: dict[str, str]  # scope -> model id Anthropic
    llm: LlmSettings
    rendering: Rendering
    crosscheck: Crosscheck
    routing: Routing
    gate: Gate
    lint: Lint

    def model_for(self, scope: str) -> str:
        """Model id Anthropic per uno scopo (es. 'router', 'conversion')."""
        try:
            return self.models[scope]
        except KeyError:
            raise KeyError(f"scope sconosciuto in [models]: {scope!r}") from None


# --- prices.toml -----------------------------------------------------------


class ModelPrice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    input_per_mtok: float
    output_per_mtok: float


class CachePricing(BaseModel):
    model_config = ConfigDict(extra="forbid")
    read_multiplier: float
    write_5m_multiplier: float
    write_1h_multiplier: float


class Currency(BaseModel):
    model_config = ConfigDict(extra="forbid")
    usd_to_eur: float


class Prices(BaseModel):
    model_config = ConfigDict(extra="forbid")
    updated: str
    models: dict[str, ModelPrice]
    cache: CachePricing
    currency: Currency

    def for_model(self, model_id: str) -> ModelPrice:
        try:
            return self.models[model_id]
        except KeyError:
            raise KeyError(f"prezzo non configurato per il modello {model_id!r}") from None


# --- loader ----------------------------------------------------------------


def _load_toml(path: Path) -> dict:
    with path.open("rb") as f:
        return tomllib.load(f)


def load_settings(path: Path | None = None) -> Settings:
    return Settings.model_validate(_load_toml(path or _config_dir() / "settings.toml"))


def load_prices(path: Path | None = None) -> Prices:
    return Prices.model_validate(_load_toml(path or _config_dir() / "prices.toml"))


def load_prompt(name: str) -> str:
    """Carica un prompt versionato da config/prompts/<name>.md (es. 'conversion')."""
    return (_config_dir() / "prompts" / f"{name}.md").read_text(encoding="utf-8")
