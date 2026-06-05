"""Test delle primitive di tracciabilità."""

from datetime import datetime

from poc_istruzioni.provenance import (
    new_run_id,
    sha256_bytes,
    sha256_file,
    sha256_text,
    utc_now_iso,
)

# Vettori di test noti per sha256.
SHA256_EMPTY = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
SHA256_ABC = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_sha256_bytes_vettore_noto() -> None:
    assert sha256_bytes(b"") == SHA256_EMPTY


def test_sha256_text_vettore_noto() -> None:
    assert sha256_text("abc") == SHA256_ABC


def test_sha256_file_coincide_con_bytes(tmp_path) -> None:
    content = b"contenuto di prova\n"
    p = tmp_path / "f.bin"
    p.write_bytes(content)
    assert sha256_file(p) == sha256_bytes(content)


def test_run_id_formato_e_unicita() -> None:
    a, b = new_run_id(), new_run_id()
    assert a.startswith("run_")
    assert a != b  # ogni esecuzione ha id distinto


def test_utc_now_iso_timezone_aware() -> None:
    ts = utc_now_iso()
    parsed = datetime.fromisoformat(ts)
    assert parsed.tzinfo is not None
    assert parsed.utcoffset().total_seconds() == 0
