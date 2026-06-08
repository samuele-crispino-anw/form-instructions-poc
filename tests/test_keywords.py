"""Test del core deterministico del keyword index (D3)."""

from poc_istruzioni.serving.keywords import (
    build_index,
    expand_query,
    normalize,
    score_nodes,
    tokens,
)


def test_normalize_e_token() -> None:
    assert normalize("Società à È") == "societa a e"
    toks = tokens("Spese sanitarie del rigo RP1")
    assert "spese" in toks and "sanitarie" in toks
    assert "spese sanitarie" in toks       # bigramma
    assert "rigo" not in toks and "del" not in toks  # stopword/strutturali


def test_idf_downpesa_i_termini_ubiqui() -> None:
    # a parita' di frequenza nel nodo, il termine raro (df basso) pesa piu' di quello ubiquo.
    items = [
        (1, "dentista farmaco", ""),
        (2, "farmaco", ""),
        (3, "farmaco", ""),
    ]
    idx = build_index(items)
    w = {(e.term, e.node_id): e.weight for e in idx}
    assert w[("dentista", 1)] > w[("farmaco", 1)]


def test_match_instrada_sul_nodo_giusto() -> None:
    items = [
        (1, "Rigo RP1 Spese sanitarie", "spese mediche, visite, medicinali"),
        (2, "Rigo RP7 Interessi mutuo", "interessi su mutui ipotecari abitazione"),
    ]
    idx = build_index(items)
    top = score_nodes("ho pagato interessi sul mutuo", idx)
    assert top[0][0] == 2  # nodo mutuo primo


def test_alias_colma_il_gap_di_vocabolario() -> None:
    items = [(1, "Rigo RP1 Spese sanitarie", "spese mediche e visite")]
    idx = build_index(items)
    aliases = {"dentista": ["spese sanitarie", "spese mediche"]}
    # senza alias "dentista" non e' nell'indice -> nessun match
    assert score_nodes("sono andato dal dentista", idx) == []
    # con alias la query si espande e instrada al nodo 1
    assert score_nodes("sono andato dal dentista", idx, aliases)[0][0] == 1


def test_expand_query_aggiunge_solo_alias_pertinenti() -> None:
    aliases = {"occhiali": ["spese sanitarie"], "f24": ["versamenti"]}
    exp = expand_query("ho comprato gli occhiali", aliases)
    assert "spese sanitarie" in exp and "versamenti" not in exp


def test_keyword_repo_round_trip(tmp_path) -> None:
    from poc_istruzioni.db.connection import connect, init_db
    from poc_istruzioni.db.repositories import get_keywords, replace_keywords

    c = connect(tmp_path / "k.db")
    init_db(c)
    idx = build_index([(1, "Spese sanitarie", "dentista e medicinali")])
    replace_keywords(c, "DOC", idx)
    terms = {r["term"] for r in get_keywords(c, "DOC")}
    assert "dentista" in terms and "spese sanitarie" in terms
    replace_keywords(c, "DOC", build_index([(2, "Interessi mutuo", "")]))  # sostituzione pulita
    terms2 = {r["term"] for r in get_keywords(c, "DOC")}
    assert "dentista" not in terms2 and "mutuo" in terms2
