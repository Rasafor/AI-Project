"""
Tests for token_adapter (the Anthropic token-count adapter).

Covers the non-negotiables without needing a network:
  * bad inputs -> TokenAdapterError("ValidationError")
  * missing ANTHROPIC_BASE_URL / ANTHROPIC_API_KEY -> TokenAdapterError
    ("Unavailable") naming the variables, never their values
  * an explicit timeout that actually fires -> TokenAdapterError("Timeout")
    (against a local socket that accepts but never answers)
  * the httpx client is pooled/reused across calls

If ANTHROPIC_API_KEY and ANTHROPIC_BASE_URL are both set, it also does one real
call and prints the count.

Run from the mcp-server/ folder:
    python src/test_token_adapter.py
"""

import os
import socket
import sys
import threading
import time

import token_adapter as ta


_CFG_KEYS = ("ANTHROPIC_BASE_URL", "ANTHROPIC_API_KEY")


def _clean_cfg_env():
    """Snapshot the two config vars and remove them; restore on exit."""
    import contextlib

    @contextlib.contextmanager
    def _ctx():
        saved = {k: os.environ.pop(k, None) for k in _CFG_KEYS}
        try:
            yield
        finally:
            for k in _CFG_KEYS:
                os.environ.pop(k, None)
            for k, v in saved.items():
                if v is not None:
                    os.environ[k] = v

    return _ctx()


def _expect(error_class: str, fn) -> ta.TokenAdapterError:
    try:
        fn()
    except ta.TokenAdapterError as exc:
        assert exc.error_class == error_class, f"got {exc.error_class!r}, want {error_class!r}: {exc}"
        return exc
    raise AssertionError(f"expected TokenAdapterError({error_class}) — nothing raised")


def test_validation() -> None:
    # Validation runs before any config lookup — set both so we're sure it's the
    # input that's rejected, not the env.
    with _clean_cfg_env():
        os.environ["ANTHROPIC_BASE_URL"] = "https://example.invalid"
        os.environ["ANTHROPIC_API_KEY"] = "unused-in-this-test"
        _expect("ValidationError", lambda: ta.count_tokens("", model="claude-sonnet-4-5"))
        _expect("ValidationError", lambda: ta.count_tokens("   ", model="claude-sonnet-4-5"))
        _expect("ValidationError", lambda: ta.count_tokens("x" * (ta.MAX_TEXT_CHARS + 1), model="m"))
        _expect("ValidationError", lambda: ta.count_tokens("hi", model="bad model!"))
        _expect("ValidationError", lambda: ta.count_tokens("hi", model="m", timeout_s=0))
        _expect("ValidationError", lambda: ta.count_tokens("hi", model="m", timeout_s=999))
    print("PASS: validation rejects empty/oversized text, bad model id, bad timeout.")


def test_missing_config() -> None:
    with _clean_cfg_env():
        exc = _expect("Unavailable", lambda: ta.count_tokens("hi", model="m"))
        msg = str(exc)
        assert "ANTHROPIC_BASE_URL" in msg and "ANTHROPIC_API_KEY" in msg, msg
        os.environ["ANTHROPIC_BASE_URL"] = "https://example.invalid"
        exc = _expect("Unavailable", lambda: ta.count_tokens("hi", model="m"))
        assert "ANTHROPIC_API_KEY" in str(exc) and "ANTHROPIC_BASE_URL" not in str(exc), str(exc)
    print("PASS: missing ANTHROPIC_BASE_URL / ANTHROPIC_API_KEY -> Unavailable, names only.")


def test_timeout_fires() -> None:
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]

    def _accept_and_stall() -> None:
        try:
            conn, _ = srv.accept()
            time.sleep(5)  # accept, then never answer
            conn.close()
        except OSError:
            pass

    threading.Thread(target=_accept_and_stall, daemon=True).start()
    try:
        with _clean_cfg_env():
            os.environ["ANTHROPIC_BASE_URL"] = f"http://127.0.0.1:{port}"
            os.environ["ANTHROPIC_API_KEY"] = "test-key-not-a-real-secret"
            started = time.monotonic()
            exc = _expect("Timeout", lambda: ta.count_tokens("hello", model="m", timeout_s=0.5))
            elapsed = time.monotonic() - started
            assert elapsed < 3, f"timeout took {elapsed:.1f}s, should abort near 0.5s"
            assert "0.5s timeout" in str(exc), str(exc)
            # the pooled client survived the timeout (connection was released)
            assert not ta._pool().is_closed, "pool must stay usable after a timeout"
    finally:
        srv.close()
    print("PASS: explicit timeout fires -> Timeout error, aborts fast, pool intact.")


def test_pool_is_reused() -> None:
    a = ta._pool()
    b = ta._pool()
    assert a is b, "count_tokens must reuse one pooled httpx client"
    print("PASS: one pooled httpx client is reused across calls.")


def test_real_call_optional() -> None:
    if not (os.environ.get("ANTHROPIC_API_KEY") and os.environ.get("ANTHROPIC_BASE_URL")):
        print("SKIP: real call — ANTHROPIC_API_KEY / ANTHROPIC_BASE_URL not set.")
        return
    n = ta.count_tokens("The orders_load job failed at 02:14 with a null amount error.",
                        model="claude-sonnet-4-5", timeout_s=15)
    assert isinstance(n, int) and n > 0, n
    print(f"PASS: real call -> input_tokens={n}")


if __name__ == "__main__":
    try:
        test_validation()
        test_missing_config()
        test_timeout_fires()
        test_pool_is_reused()
        test_real_call_optional()
        print("ALL PASS: token_adapter validates, fails safe, times out, pools, (optionally) calls real.")
    except Exception as exc:  # noqa: BLE001 - top-level test entry point
        print(f"FAIL: {exc}", file=sys.stderr)
        sys.exit(1)
