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
    origin: str = "kb_derived"  # provenienza domanda: kb_derived | external (indipendente da KB)

    def attesa_json(self) -> str:
        """Serializza i campi non-colonna in attesa_json (schema eval_cases)."""
        return json.dumps(
            {
                "difficolta": self.difficolta,
                "hops": self.hops,
                "answerable": self.answerable,
                "expected_target": self.expected_target,
                "must_include": self.must_include,
                "origin": self.origin,
            },
            ensure_ascii=False,
        )


def _origin_from_name(path: Path) -> str:
    """Inferisce l'origine dal nome file: 'external' -> indipendente, altrimenti KB-derivata."""
    return "external" if "external" in path.stem else "kb_derived"


def load_cases(path: Path, origin: str | None = None) -> list[EvalCase]:
    """Carica i casi dal YAML. origin esplicito > campo `origin:` nel file > inferenza da nome."""
    import yaml

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    resolved = origin or data.get("origin") or _origin_from_name(path)
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
                origin=resolved,
            )
        )
    return out


def load_all(dir_path: Path) -> list[EvalCase]:
    """Carica e unisce tutti i golden set (config/eval/*.yaml), taggando l'origine per file."""
    cases: list[EvalCase] = []
    for f in sorted(dir_path.glob("*.yaml")):
        cases.extend(load_cases(f))
    return cases


def stratification(cases: list[EvalCase]) -> dict[str, Counter]:
    """Conteggi per dimensione di stratificazione (per leggere la copertura del dataset)."""
    return {
        "categoria": Counter(c.categoria for c in cases),
        "difficolta": Counter(c.difficolta for c in cases),
        "hops": Counter(c.hops for c in cases),
        "answerable": Counter("si" if c.answerable else "no" for c in cases),
        "origin": Counter(c.origin for c in cases),
    }


def cross_tab(cases: list[EvalCase], row: str, col: str) -> dict[str, Counter]:
    """Tabella incrociata row x col (es. origin x difficolta) per confrontare i sottogruppi."""
    out: dict[str, Counter] = {}
    for c in cases:
        out.setdefault(getattr(c, row), Counter())[getattr(c, col)] += 1
    return out
