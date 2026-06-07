"""Signed run-page links: sign/verify round-trip, tamper resistance, fail-closed defaults."""

from __future__ import annotations

from app.security.run_links import run_page_url, sign_thread, verify_thread


def test_sign_verify_round_trip() -> None:
    token = sign_thread("thread-1", "secret")
    assert verify_thread("thread-1", token, "secret") is True


def test_token_is_scoped_to_one_thread() -> None:
    token = sign_thread("thread-1", "secret")
    assert verify_thread("thread-2", token, "secret") is False


def test_tampered_token_fails() -> None:
    token = sign_thread("thread-1", "secret")
    bad = ("A" if token[0] != "A" else "B") + token[1:]
    assert verify_thread("thread-1", bad, "secret") is False


def test_wrong_secret_fails() -> None:
    token = sign_thread("thread-1", "secret")
    assert verify_thread("thread-1", token, "other") is False


def test_empty_secret_or_token_never_verifies() -> None:
    # Fail closed: an unset secret must not turn every (or any) token valid.
    assert verify_thread("thread-1", "anything", "") is False
    assert verify_thread("thread-1", "", "secret") is False


def test_token_is_url_safe() -> None:
    token = sign_thread("thread-1", "secret")
    assert all(c.isalnum() or c in "-_" for c in token)


def test_run_page_url_shape() -> None:
    url = run_page_url("https://court.example.com/", "t1", "secret")
    assert url == f"https://court.example.com/runs/t1?t={sign_thread('t1', 'secret')}"


def test_run_page_url_falls_back_to_local_origin() -> None:
    assert run_page_url("", "t1", "secret").startswith("http://localhost:8000/runs/t1?t=")
