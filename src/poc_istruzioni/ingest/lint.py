"""Lint d'igiene sul markdown generato (Nota consolidata §B.2).

Difende dalla classe "spazzatura del text-layer riprodotta fedelmente": è invisibile al
checksum (se la spazzatura è anche nel riferimento, l'overlap passa). I `fail` bloccano la
pagina (entrambe le rotte); i `warnings` sono informativi.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Riga di corpo che inizia con un bullet dingbat NON mappato ("n " + minuscola).
_UNMAPPED_DINGBAT = re.compile(r"(?m)^\s*n\s+[a-zàèéìòù]")
# Valore con simbolo doppio (es. "1,73%%", "€€").
_DOUBLE_SYMBOL = re.compile(r"\d\s*%\s*%|%%|€€")


@dataclass
class LintResult:
    fails: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.fails


def lint_markdown(
    md: str,
    *,
    boilerplate: frozenset[str] | set[str] = frozenset(),
    page_number: int | None = None,
    orphan_warn_strings: tuple[str, ...] = (),
) -> LintResult:
    """Esegue il lint d'igiene. fail = blocca la pagina, warning = informativo."""
    res = LintResult()

    if _UNMAPPED_DINGBAT.search(md):
        res.fails.append("bullet dingbat non mappato (riga '^n ...')")
    if _DOUBLE_SYMBOL.search(md):
        res.fails.append("valore con simbolo doppio (es. 1,73%%)")

    lines = [ln.strip() for ln in md.splitlines()]
    for b in boilerplate:
        if b and b in md:
            res.fails.append(f"header/footer nel corpo: {b[:40]!r}")
            break
    if page_number is not None and str(page_number) in lines:
        res.fails.append("numero di pagina orfano nel corpo")

    headings = [ln for ln in lines if ln.startswith("#")]
    if len(headings) != len(set(headings)):
        res.warnings.append("heading duplicati impilati")
    for s in orphan_warn_strings:
        if s in md:
            res.warnings.append(f"stringa orfana: {s!r}")
    return res
