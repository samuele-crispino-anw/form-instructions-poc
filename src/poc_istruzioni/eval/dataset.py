"""Golden set di evaluation (FR-E): caricamento e statistiche di stratificazione."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class EvalCase:
    """Un caso del golden set, con i metadati di stratificazione."""

    id: str
    categoria: str
    difficolta: str
    hops: int
    answerable: bool
    domanda: str
    expected_target: str | None
    must_include: list[str]

    def attesa_json(self) -> str:
        """Serializza i campi non-colonna in attesa_json (schema eval_cases)."""
        return json.dumps(
            {
                "difficolta": self.difficolta,
                "hops": self.hops,
                "answerable": self.answerable,
                "expected_target": self.expected_target,
                "must_include": self.must_include,
            },
            ensure_ascii=False,
        )


def load_cases(path: Path) -> list[EvalCase]:
    """Carica i casi dal YAML del golden set."""
    import yaml

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out: list[EvalCase] = []
    for c in data.get("cases", []):
        out.append(
            EvalCase(
                id=c["id"],
                categoria=c["categoria"],
                difficolta=c.get("difficolta", "media"),
                hops=int(c.get("hops", 1)),
                answerable=bool(c.get("answerable", True)),
                domanda=c["domanda"],
                expected_target=c.get("expected_target"),
                must_include=list(c.get("must_include", [])),
            )
        )
    return out


def stratification(cases: list[EvalCase]) -> dict[str, Counter]:
    """Conteggi per dimensione di stratificazione (per leggere la copertura del dataset)."""
    return {
        "categoria": Counter(c.categoria for c in cases),
        "difficolta": Counter(c.difficolta for c in cases),
        "hops": Counter(c.hops for c in cases),
        "answerable": Counter("si" if c.answerable else "no" for c in cases),
    }
