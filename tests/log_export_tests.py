"""Tests for the dashboard's log-export endpoints
(bitcart_plugin/log_export.py).

Coverage:
  - Known-seed scrubber: literal-string replacement of every seed
    stored in a wallet's `xpub` field.
  - BIP39-regex scrubber: 12+ consecutive BIP39 words → redaction.
  - Negative case for the regex: a long ordinary English passage
    that doesn't happen to all be BIP39 words is left alone.
  - Zip assembly: engine variant has plugin logs only, all variant
    is a strict superset that also includes /datadir/logs files.
  - README.txt presence + scope-aware content.
"""

from __future__ import annotations

import asyncio
import io
import zipfile
from pathlib import Path
from typing import Any, Dict, List

import pytest

from bitcart_plugin import log_export
from tests._fakes import FakeBitcartAPI


def _run(coro):
    # See lnd_fee_controls_tests._run for the rationale.
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# Helpers — point the module at a temp directory so we don't depend on
# /datadir actually existing (or worse, a stale /datadir from a prior
# integration run leaking into these tests).
# ---------------------------------------------------------------------------

def _redirect_log_dirs(monkeypatch, plugin_dir: Path, bitcart_dir: Path):
    monkeypatch.setattr(log_export, "_PLUGIN_LOG_DIR", str(plugin_dir))
    monkeypatch.setattr(log_export, "_BITCART_LOG_DIR", str(bitcart_dir))


def _zip_files(zip_bytes: bytes) -> Dict[str, str]:
    out: Dict[str, str] = {}
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        for name in z.namelist():
            out[name] = z.read(name).decode("utf-8", errors="replace")
    return out


# ---------------------------------------------------------------------------
# BIP39 wordlist load smoke test — if this fails everything else is
# moot because the regex scrubber is a no-op.
# ---------------------------------------------------------------------------

def test_bip39_wordlist_loaded():
    assert len(log_export._BIP39_WORDS) == 2048, (
        f"expected 2048 BIP39 words, got {len(log_export._BIP39_WORDS)}"
    )
    for sample in ["abandon", "ability", "zoo", "yellow", "diamond"]:
        assert sample in log_export._BIP39_WORDS


# ---------------------------------------------------------------------------
# Scrubber unit tests
# ---------------------------------------------------------------------------

def test_known_seed_replaced_literal():
    seed = "abandon ability able about above absent absorb abstract absurd abuse access accident"
    text = f"some log line here\nwallet seed: {seed}\nanother line"
    out = log_export._scrub_secrets(text, [seed])
    assert seed not in out
    assert "[REDACTED-WALLET-SEED-0]" in out
    # Surrounding text preserved.
    assert "some log line here" in out
    assert "another line" in out


def test_unknown_mnemonic_caught_by_regex():
    # Same 12 words but the operator hasn't registered this wallet
    # with Bitcart — known_seeds list is empty. The trailing word is
    # deliberately non-BIP39 so we can verify the boundary cleanly
    # (BIP39 has 2048 entries including many common short words like
    # "end" and "act", so picking a sentinel matters).
    seed = "abandon ability able about above absent absorb abstract absurd abuse access accident"
    text = f"leak: {seed} xyzzy"
    out = log_export._scrub_secrets(text, known_seeds=[])
    assert seed not in out
    assert "[REDACTED-MNEMONIC]" in out
    assert "leak:" in out
    assert "xyzzy" in out


def test_24_word_mnemonic_caught_by_regex():
    seed = (
        "abandon ability able about above absent absorb abstract "
        "absurd abuse access accident account accuse achieve acid "
        "acoustic acquire across act action actor actress actual"
    )
    out = log_export._scrub_secrets(f"prefix {seed} suffix", known_seeds=[])
    assert "[REDACTED-MNEMONIC]" in out
    assert "abandon" not in out
    assert "actual" not in out


def test_short_run_not_redacted():
    # 11 consecutive BIP39 words is below threshold — must NOT redact.
    eleven = "abandon ability able about above absent absorb abstract absurd abuse access"
    out = log_export._scrub_secrets(eleven, known_seeds=[])
    assert "[REDACTED-MNEMONIC]" not in out
    assert eleven in out


def test_ordinary_english_not_redacted():
    # A long sentence in normal English. Some words happen to be BIP39
    # words (a, the, day, etc.) but interspersed with non-BIP39 words
    # so no 12-run forms.
    text = (
        "The quick brown fox jumps over the lazy dog. "
        "Operators sometimes paste long messages into commit notes, "
        "which can produce streams of words that look unusual without "
        "actually constituting a wallet seed phrase. "
        "Connection refused while contacting peer; retrying shortly."
    )
    out = log_export._scrub_secrets(text, known_seeds=[])
    assert "[REDACTED-MNEMONIC]" not in out
    assert out == text


def test_multiple_known_seeds_distinct_redaction_tags():
    seed_a = "abandon ability able about above absent absorb abstract absurd abuse access accident"
    seed_b = "zoo yellow diamond crystal sphere ocean mountain forest river desert valley island"
    # The second one is intentionally NOT a BIP39-aligned set, mostly
    # synthetic — so we know the literal-replace branch is what
    # caught it, not the regex.
    text = f"first: {seed_a} | second: {seed_b}"
    out = log_export._scrub_secrets(text, known_seeds=[seed_a, seed_b])
    assert "[REDACTED-WALLET-SEED-0]" in out
    assert "[REDACTED-WALLET-SEED-1]" in out
    assert seed_a not in out
    assert seed_b not in out


# ---------------------------------------------------------------------------
# Known-seed collection from the Bitcart API
# ---------------------------------------------------------------------------

def test_collect_known_seeds_includes_only_mnemonic_xpubs():
    api = FakeBitcartAPI()
    # Add three wallets: one 12-word seed, one 24-word, one
    # genuine-xpub (watch-only — must NOT be scrubbed; xpub is not a
    # secret and scrubbing the xpub would corrupt every log line that
    # references the wallet by xpub).
    seed12 = "abandon ability able about above absent absorb abstract absurd abuse access accident"
    seed24 = (
        "abandon ability able about above absent absorb abstract "
        "absurd abuse access accident account accuse achieve acid "
        "acoustic acquire across act action actor actress actual"
    )
    real_xpub = "xpub6CUGRUonZSQ4TWtTMmzXdrXDtypWKiKrhko4egpiMZbpiaQL2jkwSB1icqYh2cfDfVxdx4df189oLKnC5fSwqPfgyP3hooxujYzAu3fDVmz"
    api.add_wallet("w1", currency="btclnd", xpub=seed12, name="lnd-hot", lightning_enabled=True)
    api.add_wallet("w2", currency="btc",    xpub=seed24, name="btc-hot", lightning_enabled=False)
    api.add_wallet("w3", currency="btc",    xpub=real_xpub, name="watch", lightning_enabled=False)
    seeds = _run(log_export._collect_known_seeds(api))
    assert seed12 in seeds
    assert seed24 in seeds
    assert real_xpub not in seeds


# ---------------------------------------------------------------------------
# End-to-end zip assembly
# ---------------------------------------------------------------------------

def _make_logs(plugin_dir: Path, bitcart_dir: Path, *, seed: str):
    plugin_dir.mkdir(parents=True, exist_ok=True)
    bitcart_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "liquidityhelper.log").write_text(
        f"INFO routine startup\nINFO loaded wallet seed={seed}\nINFO tick complete\n"
    )
    (plugin_dir / "liquidityhelper.log.1").write_text("INFO older rotated entry\n")
    (plugin_dir / "decisions.log").write_text("DECISION: cashed out 1000 sats\n")
    (bitcart_dir / "bitcart.log").write_text("INFO bitcart app start\n")
    (bitcart_dir / "bitcart20260527.log").write_text("INFO bitcart daily-rotated entry\n")


def test_zip_engine_variant_contents(monkeypatch, tmp_path):
    plugin_dir = tmp_path / "plugin_data" / "liquidityhelper"
    bitcart_dir = tmp_path / "datadir_logs"
    seed = "abandon ability able about above absent absorb abstract absurd abuse access accident"
    _make_logs(plugin_dir, bitcart_dir, seed=seed)
    _redirect_log_dirs(monkeypatch, plugin_dir, bitcart_dir)

    api = FakeBitcartAPI()
    api.add_wallet("w1", currency="btclnd", xpub=seed, name="hot", lightning_enabled=True)

    zip_bytes, filename = _run(log_export._build_log_zip(api, include_bitcart=False))
    files = _zip_files(zip_bytes)

    assert filename.startswith("liquidityhelper-logs-engine-")
    assert filename.endswith(".zip")
    assert "README.txt" in files
    assert "engine/liquidityhelper.log" in files
    assert "engine/liquidityhelper.log.1" in files
    assert "engine/decisions.log" in files
    # Strict NEGATIVE: bitcart/ files absent in engine variant.
    assert not any(name.startswith("bitcart/") for name in files), (
        f"engine variant must not include bitcart/ files; got: {list(files)}"
    )
    # Scrubbing happened.
    assert seed not in files["engine/liquidityhelper.log"]
    assert "[REDACTED-WALLET-SEED-0]" in files["engine/liquidityhelper.log"]


def test_zip_all_variant_is_strict_superset(monkeypatch, tmp_path):
    plugin_dir = tmp_path / "plugin_data" / "liquidityhelper"
    bitcart_dir = tmp_path / "datadir_logs"
    seed = "abandon ability able about above absent absorb abstract absurd abuse access accident"
    _make_logs(plugin_dir, bitcart_dir, seed=seed)
    _redirect_log_dirs(monkeypatch, plugin_dir, bitcart_dir)

    api = FakeBitcartAPI()
    api.add_wallet("w1", currency="btclnd", xpub=seed, name="hot", lightning_enabled=True)

    engine_zip, _ = _run(log_export._build_log_zip(api, include_bitcart=False))
    all_zip, all_filename = _run(log_export._build_log_zip(api, include_bitcart=True))

    engine_files = _zip_files(engine_zip)
    all_files = _zip_files(all_zip)

    assert all_filename.startswith("liquidityhelper-logs-all-")

    # Strict superset: every engine/ entry exists in all/ with the
    # same content.
    for name, content in engine_files.items():
        if name == "README.txt":
            # README content legitimately differs (it mentions
            # bitcart/ in the all variant).
            continue
        assert name in all_files, f"all-variant missing engine entry: {name}"
        assert all_files[name] == content, f"content drift on {name}"

    # Plus the bitcart entries.
    assert "bitcart/bitcart.log" in all_files
    assert "bitcart/bitcart20260527.log" in all_files
    # Scrubbed there too (the seed wasn't in those files, but the
    # check that we passed through the scrubber path is the seed
    # absence below).
    for content in all_files.values():
        assert seed not in content


def test_missing_log_dirs_still_yield_zip_with_readme(monkeypatch, tmp_path):
    # Operator may export logs before any have been written, or on a
    # fresh install. The endpoint should return a valid zip with at
    # least the README — not 500.
    plugin_dir = tmp_path / "nonexistent_plugin"
    bitcart_dir = tmp_path / "nonexistent_bitcart"
    # Note: NOT calling _make_logs — directories don't exist.
    _redirect_log_dirs(monkeypatch, plugin_dir, bitcart_dir)

    api = FakeBitcartAPI()
    # No wallets registered.
    zip_bytes, _ = _run(log_export._build_log_zip(api, include_bitcart=True))
    files = _zip_files(zip_bytes)
    assert "README.txt" in files
    # Only the README — no log files exist.
    assert list(files.keys()) == ["README.txt"]


def test_readme_mentions_bitcart_scope_only_when_applicable(monkeypatch, tmp_path):
    plugin_dir = tmp_path / "p"
    bitcart_dir = tmp_path / "b"
    _make_logs(plugin_dir, bitcart_dir, seed="zzz")
    _redirect_log_dirs(monkeypatch, plugin_dir, bitcart_dir)

    api = FakeBitcartAPI()
    # No wallets registered.

    engine_zip, _ = _run(log_export._build_log_zip(api, include_bitcart=False))
    all_zip, _ = _run(log_export._build_log_zip(api, include_bitcart=True))
    engine_readme = _zip_files(engine_zip)["README.txt"]
    all_readme = _zip_files(all_zip)["README.txt"]

    assert "bitcart/" not in engine_readme
    assert "bitcart/" in all_readme
    # Both warn about funds.
    assert "fund" in engine_readme.lower() or "trust" in engine_readme.lower()
    assert "fund" in all_readme.lower() or "trust" in all_readme.lower()
