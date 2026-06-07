"""B.5 — estrazione e validazione dell'identità documentale dal frontespizio.

Dalla prima pagina (via VLM, perché il text-layer contiene il testo-fantasma) si ricava
un record strutturato {modello, edizione, periodo_imposta, agg_data} e lo si confronta con
le attese del documento. Un mismatch è un errore bloccante: previene risposte che citerebbero
l'anno/edizione sbagliati. Step 0-bis riusabile per ogni documento futuro.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from poc_istruzioni.ingest.transcribe import _image_block
from poc_istruzioni.llm.client import LlmClient, LlmResult

# Schema dell'output strutturato (JSON vincolato lato API).
_IDENTITY_SCHEMA = {
    "type": "object",
    "properties": {
        "modello": {"type": "string"},
        "edizione": {"type": "string"},
        "periodo_imposta": {"type": "string"},
        "agg_data": {"type": "string"},
    },
    "required": ["modello", "edizione", "periodo_imposta", "agg_data"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class IdentityRecord:
    modello: str
    edizione: str
    periodo_imposta: str
    agg_data: str = ""


def extract_identity(
    llm: LlmClient,
    image_path: Path | str,
    *,
    model: str,
    prompt: str,
) -> tuple[IdentityRecord, LlmResult]:
    """Estrae l'identità dall'immagine del frontespizio via VLM (structured output)."""
    res = llm.complete(
        scopo="identity",
        model=model,
        system=prompt,
        messages=[{"role": "user", "content": [_image_block(image_path)]}],
        max_tokens=512,
        output_config={"format": {"type": "json_schema", "schema": _IDENTITY_SCHEMA}},
    )
    data = json.loads(res.text)
    return IdentityRecord(**data), res


def validate_identity(
    rec: IdentityRecord,
    *,
    expected_edizione: str,
    expected_periodo: str,
    expected_modello_hint: str | None = None,
) -> list[str]:
    """Confronta l'identità estratta con le attese; ritorna la lista dei mismatch (vuota = ok)."""
    issues: list[str] = []
    if rec.edizione.strip() != expected_edizione:
        issues.append(f"edizione estratta {rec.edizione!r} != attesa {expected_edizione!r}")
    if rec.periodo_imposta.strip() != expected_periodo:
        issues.append(
            f"periodo_imposta estratto {rec.periodo_imposta!r} != atteso {expected_periodo!r}"
        )
    if expected_modello_hint and expected_modello_hint.lower() not in rec.modello.lower():
        issues.append(
            f"modello estratto {rec.modello!r} non contiene l'atteso {expected_modello_hint!r}"
        )
    return issues
