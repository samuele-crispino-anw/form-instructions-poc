"""Explorer HTML statico dell'albero di navigazione (D1/D2).

Un solo file autoconsistente: a sinistra la struttura (cliccabile), a destra — per il nodo
scelto — l'INPUT inviato al modello, le PAGINE markdown associate e l'OUTPUT (summary).
Pensato per ispezionare il path senza lanciare comandi: si genera una volta e si apre nel browser.
"""

from __future__ import annotations

import html
import json

from poc_istruzioni.serving.nodes import _FRONTMATTER_RE, Node
from poc_istruzioni.serving.summaries import ScopeInput, build_user_message


def _pages_markdown(md_by_page: dict[int, str], start: int, end: int) -> str:
    parts = []
    for p in range(start, end + 1):
        raw = md_by_page.get(p)
        if raw is None:
            continue
        parts.append(f"───── p.{p} ─────\n{_FRONTMATTER_RE.sub('', raw).strip()}")
    return "\n\n".join(parts)


def build_explorer_html(
    nodes: list[Node],
    scopes: dict[int, ScopeInput],
    summaries: dict[int, str | None],
    md_by_page: dict[int, str],
    *,
    doc_id: str,
    provenance: dict[int, dict] | None = None,
) -> str:
    """Serializza l'albero in un singolo HTML navigabile (dati JSON embeddati)."""
    provenance = provenance or {}
    data = []
    for n in nodes:
        scope = scopes.get(n.id)
        data.append(
            {
                "id": n.id,
                "parent_id": n.parent_id,
                "kind": n.kind,
                "level": n.level,
                "title": n.title,
                "pages": f"{n.page_start}-{n.page_end}",
                "is_leaf": bool(scope and scope.is_leaf),
                "input": build_user_message(scope) if scope else "",
                "summary": summaries.get(n.id) or "",
                "prov": provenance.get(n.id) or {},
                "pages_md": _pages_markdown(md_by_page, n.page_start, n.page_end),
            }
        )
    payload = json.dumps(data, ensure_ascii=False)
    title = html.escape(f"Explorer navigazione — {doc_id}")
    # Il JS è minimale: rendering albero + pannello dettaglio on-click. Nessun server.
    return _TEMPLATE.replace("__TITLE__", title).replace("__DATA__", payload)


_TEMPLATE = """<!DOCTYPE html>
<html lang="it"><head><meta charset="utf-8"><title>__TITLE__</title>
<style>
 body{margin:0;font:14px/1.45 -apple-system,Segoe UI,Roboto,sans-serif;color:#1a1a1a}
 #wrap{display:flex;height:100vh}
 #tree{width:38%;overflow:auto;border-right:1px solid #ddd;padding:8px 4px;background:#fafafa}
 #detail{flex:1;overflow:auto;padding:16px 22px}
 .node{cursor:pointer;padding:2px 6px;border-radius:4px;white-space:nowrap;overflow:hidden;
       text-overflow:ellipsis}
 .node:hover{background:#eef}
 .node.sel{background:#dbe7ff;font-weight:600}
 .k{display:inline-block;min-width:58px;font-size:11px;color:#fff;border-radius:3px;
    padding:0 5px;margin-right:6px;text-align:center}
 .quadro{background:#7b1fa2}.sezione{background:#1565c0}.rigo{background:#2e7d32}.codice{background:#ef6c00}
 h2{margin:0 0 2px}.muted{color:#777;font-size:12px;margin-bottom:14px}
 .lbl{font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:#888;margin:18px 0 4px}
 pre{background:#f5f5f7;border:1px solid #e2e2e6;border-radius:6px;padding:10px 12px;
     white-space:pre-wrap;word-break:break-word;margin:0}
 .summary{background:#fff7e6;border:1px solid #f0d090;border-radius:6px;padding:10px 12px}
 .prov{background:#eef6ee;border:1px solid #cfe3cf;border-radius:6px;padding:8px 12px;
       font-size:12px;color:#345;font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
 .empty{color:#aaa;font-style:italic}
</style></head><body><div id="wrap">
 <div id="tree"></div>
 <div id="detail"><p class="empty">Seleziona un nodo a sinistra.</p></div>
</div>
<script>
const DATA = __DATA__;
const byId = Object.fromEntries(DATA.map(d => [d.id, d]));
const tree = document.getElementById('tree'), detail = document.getElementById('detail');
function esc(s){const e=document.createElement('div');e.textContent=s||'';return e.innerHTML;}
DATA.forEach(d => {
  const el = document.createElement('div');
  el.className = 'node'; el.style.paddingLeft = (4 + (d.level-1)*18) + 'px';
  el.innerHTML = `<span class="k ${d.kind}">${d.kind}</span>${esc(d.title)}`;
  el.onclick = () => select(d.id, el);
  el.dataset.id = d.id; tree.appendChild(el);
});
function select(id, el){
  document.querySelectorAll('.node.sel').forEach(n=>n.classList.remove('sel'));
  if(el) el.classList.add('sel');
  const d = byId[id];
  const summary = d.summary ? `<div class="summary">${esc(d.summary)}</div>`
                            : `<p class="empty">(summary non ancora generato)</p>`;
  const p = d.prov || {};
  const prov = (p.summary_model || p.built_run_id)
    ? `<div class="prov">build run: ${esc(p.built_run_id)||'—'}`
      + ` · summary: ${esc(p.summary_model)||'—'}`
      + ` · prompt ${esc(p.summary_prompt_sha)||'—'} · ${esc(p.summary_ts)||'—'}`
      + ` · ledger #${p.summary_call_id||'—'}</div>`
    : `<p class="empty">(provenienza non registrata)</p>`;
  detail.innerHTML = `
    <h2><span class="k ${d.kind}">${d.kind}</span>${esc(d.title)}</h2>
    <div class="muted">pagine ${d.pages} · ${d.is_leaf?'foglia':'ramo'} · id ${d.id}</div>
    <div class="lbl">Output — summary (etichetta di navigazione)</div>${summary}
    <div class="lbl">Provenienza</div>${prov}
    <div class="lbl">Input inviato al modello</div><pre>${esc(d.input)}</pre>
    <div class="lbl">Pagine markdown associate</div><pre>${esc(d.pages_md)}</pre>`;
  detail.scrollTop = 0;
}
</script></body></html>"""
