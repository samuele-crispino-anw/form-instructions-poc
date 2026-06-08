"""Log .md strutturato e leggibile di un'interrogazione Q&A end-to-end (FR-T1).

Dal momento in cui l'utente pone una query, si registra in un unico file markdown: la query, ogni
passaggio del retrieval, le parti recuperate, ciò che viene passato all'LLM e la sua risposta (con
eventuale ragionamento). Sezioni numerate, così un umano capisce esattamente cosa è successo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


def fence(text: str, lang: str = "") -> str:
    """Avvolge il testo in un blocco di codice markdown (preserva la formattazione)."""
    return f"```{lang}\n{text}\n```"


@dataclass
class QaLog:
    """Accumulatore di sezioni ordinate, reso come unico file markdown."""

    query_id: str
    ts: str
    doc_id: str
    query: str
    _sections: list[tuple[str, str]] = field(default_factory=list)

    def section(self, title: str, body: str) -> None:
        self._sections.append((title, body))

    def render(self) -> str:
        head = (
            f"# Q&A log — {self.query_id}\n\n"
            f"- **timestamp:** {self.ts}\n"
            f"- **documento:** {self.doc_id}\n"
            f"- **query:** {self.query}\n"
        )
        parts = [head]
        for i, (title, body) in enumerate(self._sections, start=1):
            parts.append(f"\n---\n\n## {i}. {title}\n\n{body}\n")
        return "".join(parts)

    def write(self, dir_path: Path) -> Path:
        dir_path.mkdir(parents=True, exist_ok=True)
        out = dir_path / f"qa_{self.query_id}.md"
        out.write_text(self.render(), encoding="utf-8")
        return out
