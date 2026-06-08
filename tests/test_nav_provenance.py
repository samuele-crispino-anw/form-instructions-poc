"""Test della tracciabilità A+B: provenienza del summary e record di build dell'albero."""

import pytest

from poc_istruzioni.db.connection import connect, init_db
from poc_istruzioni.db.repositories import (
    get_nodes,
    insert_nav_build,
    insert_nodes,
    update_node_summary,
)
from poc_istruzioni.serving.nodes import Node, patterns_version


@pytest.fixture
def conn(tmp_path):
    c = connect(tmp_path / "test.db")
    init_db(c)
    return c


def _nodes():
    return [
        Node(id=1, parent_id=None, kind="quadro", level=1, title="QUADRO RP",
             page_start=69, page_end=90, ord=1),
        Node(id=2, parent_id=1, kind="rigo", level=3, title="Rigo RP1",
             page_start=75, page_end=75, ord=2),
    ]


def test_insert_nodes_lega_built_run_id(conn) -> None:
    insert_nodes(conn, "PF1-2026", _nodes(), run_id="run_abc")
    rows = {r["id"]: r for r in get_nodes(conn, "PF1-2026")}
    assert rows[1]["built_run_id"] == "run_abc"
    assert rows[2]["built_run_id"] == "run_abc"


def test_update_node_summary_scrive_provenienza(conn) -> None:
    insert_nodes(conn, "PF1-2026", _nodes(), run_id="run_abc")
    update_node_summary(
        conn, "PF1-2026", 2, "Spese sanitarie detraibili.",
        model="claude-opus-4-8", prompt_sha="deadbeef", ts="2026-06-08T00:00:00Z", call_id=42,
    )
    r = {x["id"]: x for x in get_nodes(conn, "PF1-2026")}[2]
    assert r["summary"] == "Spese sanitarie detraibili."
    assert r["summary_model"] == "claude-opus-4-8"
    assert r["summary_prompt_sha"] == "deadbeef"
    assert r["summary_call_id"] == 42


def test_nav_build_round_trip(conn) -> None:
    insert_nav_build(conn, run_id="run_abc", doc_id="PF1-2026", page_from=69, page_to=133,
                     n_nodes=96, pattern_version=patterns_version(), ts="2026-06-08T00:00:00Z")
    b = conn.execute("SELECT * FROM nav_builds WHERE run_id='run_abc'").fetchone()
    assert b["doc_id"] == "PF1-2026" and b["n_nodes"] == 96
    assert b["page_from"] == 69 and b["page_to"] == 133


def test_patterns_version_deterministica() -> None:
    assert patterns_version() == patterns_version()  # stabile a parità di pattern
    assert len(patterns_version()) == 12
