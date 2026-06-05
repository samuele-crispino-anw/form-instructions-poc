"""Check automatici di qualità sulla trascrizione VLM (FR-B2, livello A).

Funzioni pure su (markdown_vlm, testo_pdf_riferimento). Confrontano l'output del VLM
con il text-layer del PDF (seconda estrazione indipendente) e segnalano le pagine da
rivedere. La priorità del dominio è la PRESERVAZIONE DEI NUMERI (codici, limiti, franchigie).
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

# Token numerico: cifra seguita da cifre/separatori (importi, codici, percentuali, pagine).
_NUM_RE = re.compile(r"\d[\d.,]*")
# Parola di contenuto (>=3 caratteri) per l'overlap testuale.
_WORD_RE = re.compile(r"[a-zàèéìòù0-9]{3,}", re.IGNORECASE)
# Marcatori di rifiuto/meta (multi-parola per evitare falsi positivi come "non possono").
_REFUSAL_MARKERS = (
    "non posso aiutart",
    "non sono in grado di",
    "mi dispiace, ma",
    "i'm sorry",
    "i am sorry",
    "i cannot assist",
    "as an ai",
    "non posso fornire",
)


def _normalize_number(tok: str) -> str:
    """Normalizza un token numerico: '1.234,56' -> '1234.56', '129,11' -> '129.11'."""
    t = tok.strip(".,")
    if "." in t and "," in t:  # punto = migliaia, virgola = decimali (convenzione IT)
        t = t.replace(".", "").replace(",", ".")
    elif "," in t:
        t = t.replace(",", ".")
    return t


def extract_numbers(text: str) -> set[str]:
    """Insieme dei token numerici normalizzati presenti nel testo."""
    return {_normalize_number(m.group()) for m in _NUM_RE.finditer(text) if m.group().strip(".,")}


def _tokens(text: str) -> set[str]:
    return {m.group().lower() for m in _WORD_RE.finditer(text)}


def token_overlap(vlm_md: str, pdf_text: str) -> float:
    """Frazione dei token di contenuto del PDF presenti anche nel markdown VLM."""
    pdf = _tokens(pdf_text)
    if not pdf:
        return 1.0
    return len(pdf & _tokens(vlm_md)) / len(pdf)


def coverage_ratio(vlm_md: str, pdf_text: str) -> float:
    """Rapporto di lunghezza (caratteri) tra markdown VLM e testo PDF di riferimento."""
    pdf_len = len(pdf_text.strip())
    if pdf_len == 0:
        return 1.0
    return len(vlm_md.strip()) / pdf_len


def has_repetition(text: str, *, n: int = 10, max_repeats: int = 3) -> bool:
    """True se un n-gramma di parole si ripete più di max_repeats volte (degenerazione)."""
    words = text.split()
    if len(words) < n:
        return False
    grams = Counter(tuple(words[i : i + n]) for i in range(len(words) - n + 1))
    return any(c > max_repeats for c in grams.values())


def is_empty_or_refusal(text: str) -> bool:
    """True se l'output è vuoto o contiene un rifiuto/meta-commento del modello."""
    t = text.strip().lower()
    if not t:
        return True
    return any(marker in t for marker in _REFUSAL_MARKERS)


def lint_headings(md: str) -> list[str]:
    """Problemi di gerarchia heading (es. ### rigo prima di un ## quadro)."""
    issues: list[str] = []
    seen_quadro = False
    for line in md.splitlines():
        if line.startswith("### "):
            if not seen_quadro:
                issues.append("rigo (###) prima di un quadro (##)")
        elif line.startswith("## "):
            seen_quadro = True
    return issues


def find_artifacts(text: str, artifacts: tuple[str, ...]) -> list[str]:
    """Artefatti noti (es. testo-fantasma) che NON devono comparire nel markdown."""
    low = text.lower()
    return [a for a in artifacts if a.lower() in low]


# Artefatto noto del corpus PF1 2026 (testo-fantasma su almeno una pagina).
DEFAULT_ARTIFACTS = ("REDDITI SC 2023",)


@dataclass
class CheckReport:
    """Esito aggregato dei check automatici su una pagina.

    `reasons` = problemi bloccanti (decidono needs_review e l'escalation).
    `warnings` = segnali informativi non bloccanti (gerarchia heading, copertura).
    """

    overlap: float
    number_recall: float
    missing_numbers: list[str]
    extra_numbers: list[str]
    coverage: float
    repetition: bool
    empty_or_refusal: bool
    heading_issues: list[str]
    artifacts: list[str]
    needs_review: bool
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def run_checks(
    vlm_md: str,
    pdf_text: str,
    *,
    overlap_threshold: float = 0.6,
    number_recall_threshold: float = 0.95,
    coverage_min: float = 0.5,
    coverage_max: float = 2.0,
    artifacts: tuple[str, ...] = DEFAULT_ARTIFACTS,
) -> CheckReport:
    """Esegue tutti i check A) e decide needs_review con le motivazioni.

    `pdf_text` dovrebbe essere già ripulito da header/footer (vedi textlayer.strip_lines).
    Gli artefatti noti vengono rimossi dal riferimento prima del confronto: una loro
    corretta omissione nel markdown non deve risultare come "numero/contenuto mancante".
    """
    # Riferimento ripulito dagli artefatti noti (es. testo-fantasma "REDDITI SC 2023").
    pdf_clean = pdf_text
    for a in artifacts:
        pdf_clean = pdf_clean.replace(a, "")

    pdf_nums = extract_numbers(pdf_clean)
    vlm_nums = extract_numbers(vlm_md)
    missing = sorted(pdf_nums - vlm_nums)
    extra = sorted(vlm_nums - pdf_nums)
    number_recall = 1.0 if not pdf_nums else len(pdf_nums & vlm_nums) / len(pdf_nums)

    overlap = token_overlap(vlm_md, pdf_clean)
    coverage = coverage_ratio(vlm_md, pdf_clean)
    repetition = has_repetition(vlm_md)
    empty = is_empty_or_refusal(vlm_md)
    heading_issues = lint_headings(vlm_md)
    found_artifacts = find_artifacts(vlm_md, artifacts)

    # Bloccanti: veri segnali di fedeltà (decidono needs_review/escalation).
    reasons: list[str] = []
    if empty:
        reasons.append("output vuoto o rifiuto")
    if overlap < overlap_threshold:
        reasons.append(f"overlap basso ({overlap:.2f} < {overlap_threshold})")
    if number_recall < number_recall_threshold:
        reasons.append(f"numeri mancanti (recall {number_recall:.2f}): {missing[:10]}")
    if repetition:
        reasons.append("ripetizione/degenerazione")
    if found_artifacts:
        reasons.append(f"artefatti nel markdown: {found_artifacts}")

    # Non bloccanti: indizi informativi (rumorosi su questo corpus).
    warnings: list[str] = []
    if not (coverage_min <= coverage <= coverage_max):
        warnings.append(f"copertura anomala ({coverage:.2f})")
    if heading_issues:
        warnings.append(f"gerarchia heading: {heading_issues}")

    return CheckReport(
        overlap=overlap,
        number_recall=number_recall,
        missing_numbers=missing,
        extra_numbers=extra,
        coverage=coverage,
        repetition=repetition,
        empty_or_refusal=empty,
        heading_issues=heading_issues,
        artifacts=found_artifacts,
        needs_review=bool(reasons),
        reasons=reasons,
        warnings=warnings,
    )
