"""Tests for the Debug-tab wallet-backup + CSV endpoints
(bitcart_plugin/wallet_debug.py).

Coverage focus is the BACKUP path per spec — verify the zip contains
the expected files and that the seed phrase round-trips for each
wallet. CSV tests are best-effort sanity (header row + a few sample
rows); the unified-sparse-columns layout is plain enough that we
don't pin every column individually.
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import zipfile
from typing import Any, Dict, List, Optional

import pytest

from bitcart_plugin import wallet_debug
from tests._fakes import FakeBitcartAPI


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _run(coro):
    """Drive a coroutine to completion on a fresh event loop."""
    return asyncio.new_event_loop().run_until_complete(coro)


def _setup_engine_dispatch(monkeypatch, api: FakeBitcartAPI):
    """Match the dashboard_tests pattern: patch the engine helpers
    the wallet_debug module calls so they read from the fake's
    in-memory dicts rather than expecting a real LND/Electrum.

    Patches in this file:
      - liquidityhelper.list_onchain_history  → reads fake.onchain_history_by_wallet
      - liquidityhelper.list_ln_payments_with_labels → reads fake.ln_history_by_wallet
      - liquidityhelper.lnd_rpc → returns whatever was stored in fake.lnd_rpc_responses
      - liquidityhelper.electrum_rpc → returns whatever was stored in fake.electrum_rpc_responses
      - liquidityhelper._get_dashboard_api → returns our fake
    """
    import liquidityhelper

    async def fake_onchain(*, wallet, api=None):
        return list(api.onchain_history_by_wallet.get(wallet["id"], []))

    async def fake_ln(*, wallet, api=None):
        return list(api.ln_history_by_wallet.get(wallet["id"], []))

    async def fake_lnd_rpc(api_obj, wallet_id, method, params, service):
        # Cooperative lookup table on the fake.
        key = (wallet_id, method)
        return getattr(api_obj, "lnd_rpc_responses", {}).get(key)

    async def fake_electrum_rpc(method, xpub, params=None):
        key = (xpub, method, json.dumps(params, sort_keys=True) if params else "")
        # Allow lookup by (xpub, method) only first — most callers
        # don't care about the params variant.
        table = getattr(api, "electrum_rpc_responses", {})
        if key in table:
            return table[key]
        return table.get((xpub, method, ""), None)

    async def fake_get_dashboard_api():
        return api

    monkeypatch.setattr(liquidityhelper, "list_onchain_history", fake_onchain)
    monkeypatch.setattr(liquidityhelper, "list_ln_payments_with_labels", fake_ln)
    monkeypatch.setattr(liquidityhelper, "lnd_rpc", fake_lnd_rpc)
    monkeypatch.setattr(liquidityhelper, "electrum_rpc", fake_electrum_rpc)
    monkeypatch.setattr(liquidityhelper, "_get_dashboard_api", fake_get_dashboard_api)


# ---------------------------------------------------------------------------
# Backup — btclnd
# ---------------------------------------------------------------------------

def test_backup_btclnd_zip_contains_seed_and_channel_backup(monkeypatch):
    """The btclnd backup zip MUST contain:
      - seed.txt with the seed phrase from wallet.xpub
      - channel.backup with the raw SCB bytes from
        ExportAllChannelBackups.multi_chan_backup.multi_chan_backup

    Pins the disaster-recovery guarantee: an operator with this zip
    has everything LND officially needs to restore a wallet."""
    api = FakeBitcartAPI()
    seed = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"
    api.add_wallet("w-lnd", name="liquidityhelper", currency="btclnd", xpub=seed)
    # Mock the gRPC response shape. lnd_rpc returns dict with the
    # field names from the LND proto; bytes fields are base64.
    scb_raw = b"this-is-the-channel-dot-backup-payload-bytes"
    scb_b64 = base64.b64encode(scb_raw).decode("ascii")
    api.lnd_rpc_responses = {
        ("w-lnd", "ExportAllChannelBackups"): {
            "multi_chan_backup": {"multi_chan_backup": scb_b64},
        },
    }
    _setup_engine_dispatch(monkeypatch, api)

    wallet = _run(api.get_wallet("w-lnd"))
    zip_bytes, filename = _run(wallet_debug._build_btclnd_backup(api, wallet))

    assert filename.startswith("liquidityhelper-btclnd-w-lnd")
    assert filename.endswith(".zip")

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        names = set(z.namelist())
        assert "seed.txt" in names, f"missing seed.txt in {names}"
        assert "channel.backup" in names, f"missing channel.backup in {names}"
        # No error.txt on the happy path.
        assert "error.txt" not in names, (
            f"error.txt should not appear when the gRPC call succeeded; "
            f"got files {names}"
        )

        # Seed contents — must round-trip exactly, with a trailing
        # newline so the file ends cleanly when an operator `cat`s it.
        with z.open("seed.txt") as f:
            recovered = f.read().decode("utf-8")
        assert recovered.rstrip("\n") == seed, (
            f"seed mismatch: stored {seed!r}, recovered {recovered!r}"
        )

        # channel.backup must be the raw bytes (decoded from the
        # base64 the daemon emits) — not the base64 string itself.
        with z.open("channel.backup") as f:
            assert f.read() == scb_raw


def test_backup_btclnd_partial_when_grpc_fails(monkeypatch):
    """If ExportAllChannelBackups gRPC fails (network blip, LND
    spinning up, etc), the backup still emits seed.txt plus an
    error.txt explaining why channel.backup is missing. Partial
    backup beats no backup — the operator at least gets the seed."""
    api = FakeBitcartAPI()
    seed = "twelve word seed example phrase here for the test never use this on mainnet please"
    api.add_wallet("w-lnd", name="liquidityhelper", currency="btclnd", xpub=seed)
    # No lnd_rpc_responses entry → fake_lnd_rpc returns None → the
    # builder treats that as "couldn't get a backup" and goes to the
    # error path.
    api.lnd_rpc_responses = {}
    # But monkey-patch lnd_rpc itself to raise, simulating gRPC error.
    import liquidityhelper

    async def raising_lnd_rpc(*a, **kw):
        raise RuntimeError("simulated gRPC failure: LND not ready")
    monkeypatch.setattr(liquidityhelper, "lnd_rpc", raising_lnd_rpc)
    # Other patches still needed
    async def fake_get_dashboard_api():
        return api
    monkeypatch.setattr(liquidityhelper, "_get_dashboard_api", fake_get_dashboard_api)

    wallet = _run(api.get_wallet("w-lnd"))
    zip_bytes, filename = _run(wallet_debug._build_btclnd_backup(api, wallet))

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        names = set(z.namelist())
        assert "seed.txt" in names
        assert "error.txt" in names, (
            "partial backup must surface the failure in error.txt so "
            "the operator knows channel.backup is missing"
        )
        assert "channel.backup" not in names
        with z.open("error.txt") as f:
            err = f.read().decode("utf-8")
        assert "ExportAllChannelBackups failed" in err
        assert "LND not ready" in err
        # Seed still recoverable.
        with z.open("seed.txt") as f:
            assert f.read().decode("utf-8").rstrip("\n") == seed


# ---------------------------------------------------------------------------
# Backup — Electrum
# ---------------------------------------------------------------------------

def test_backup_electrum_zip_contains_seed_channel_backups_and_wallet_info(monkeypatch):
    """The Electrum backup zip MUST contain:
      - seed.txt with the seed phrase
      - channel_backups.json with one entry per open channel from
        export_channel_backup
      - wallet_info.json with currency / name / id metadata

    Pins the SCB-parity guarantee for Electrum: each channel's
    encrypted backup is captured so the operator can import_channel_backup
    on a restored Electrum wallet and force-close to recover funds."""
    api = FakeBitcartAPI()
    seed = "another twelve word example seed for an electrum wallet test only example"
    api.add_wallet("w-elec", name="liquidityhelper", currency="btc", xpub=seed)
    # Mock the Electrum RPC responses. list_channels returns 2 channels;
    # each export_channel_backup returns a distinct encrypted string.
    api.electrum_rpc_responses = {
        (seed, "list_channels", ""): {
            "result": [
                {"channel_point": "aabb:0"},
                {"channel_point": "ccdd:1"},
            ],
        },
        (seed, "export_channel_backup", json.dumps({"channel_point": "aabb:0"}, sort_keys=True)): {
            "result": "channel-backup-encrypted-string-1",
        },
        (seed, "export_channel_backup", json.dumps({"channel_point": "ccdd:1"}, sort_keys=True)): {
            "result": "channel-backup-encrypted-string-2",
        },
    }
    _setup_engine_dispatch(monkeypatch, api)

    wallet = _run(api.get_wallet("w-elec"))
    zip_bytes, filename = _run(wallet_debug._build_electrum_backup(api, wallet))

    assert filename.startswith("liquidityhelper-electrum-w-elec")
    assert filename.endswith(".zip")

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        names = set(z.namelist())
        assert names >= {"seed.txt", "channel_backups.json", "wallet_info.json"}
        assert "error.txt" not in names

        with z.open("seed.txt") as f:
            assert f.read().decode("utf-8").rstrip("\n") == seed

        with z.open("channel_backups.json") as f:
            backups = json.loads(f.read().decode("utf-8"))
        assert len(backups) == 2
        cps = {b["channel_point"] for b in backups}
        assert cps == {"aabb:0", "ccdd:1"}
        encs = {b["encrypted_backup"] for b in backups}
        assert encs == {
            "channel-backup-encrypted-string-1",
            "channel-backup-encrypted-string-2",
        }

        with z.open("wallet_info.json") as f:
            info = json.loads(f.read().decode("utf-8"))
        assert info["currency"] == "btc"
        assert info["name"] == "liquidityhelper"
        assert info["id"] == "w-elec"
        assert "exported_at" in info


def test_backup_electrum_empty_channels_still_produces_zip(monkeypatch):
    """A fresh Electrum wallet with zero channels must still produce
    a backup — the seed is the important piece. channel_backups.json
    will just be an empty array."""
    api = FakeBitcartAPI()
    seed = "seed-for-electrum-with-no-channels yet only on-chain funds and a single seed"
    api.add_wallet("w-elec-empty", name="liquidityhelper", currency="btc", xpub=seed)
    api.electrum_rpc_responses = {
        (seed, "list_channels", ""): {"result": []},
    }
    _setup_engine_dispatch(monkeypatch, api)

    wallet = _run(api.get_wallet("w-elec-empty"))
    zip_bytes, _ = _run(wallet_debug._build_electrum_backup(api, wallet))

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        assert "seed.txt" in z.namelist()
        with z.open("channel_backups.json") as f:
            assert json.loads(f.read().decode("utf-8")) == []


def test_backup_seed_matches_wallet_xpub_per_wallet(monkeypatch):
    """Per the spec's explicit ask: 'seed phrase matches for each
    wallet'. Two wallets, two distinct seeds — neither leaks into
    the other's backup."""
    api = FakeBitcartAPI()
    seed_a = "wallet-A seed phrase example never use this on mainnet for testing only ok"
    seed_b = "wallet-B totally different example phrase do not use this real funds words"
    api.add_wallet("w-A", name="liquidityhelper", currency="btclnd", xpub=seed_a)
    api.add_wallet("w-B", name="liquidityhelper", currency="btclnd", xpub=seed_b)
    api.lnd_rpc_responses = {
        ("w-A", "ExportAllChannelBackups"): {
            "multi_chan_backup": {"multi_chan_backup": base64.b64encode(b"A-scb").decode()},
        },
        ("w-B", "ExportAllChannelBackups"): {
            "multi_chan_backup": {"multi_chan_backup": base64.b64encode(b"B-scb").decode()},
        },
    }
    _setup_engine_dispatch(monkeypatch, api)

    for wid, expected_seed, expected_scb in [
        ("w-A", seed_a, b"A-scb"),
        ("w-B", seed_b, b"B-scb"),
    ]:
        wallet = _run(api.get_wallet(wid))
        zip_bytes, _ = _run(wallet_debug._build_btclnd_backup(api, wallet))
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
            with z.open("seed.txt") as f:
                got_seed = f.read().decode("utf-8").rstrip("\n")
            with z.open("channel.backup") as f:
                got_scb = f.read()
        assert got_seed == expected_seed, (
            f"wallet {wid} seed mismatch: expected {expected_seed!r}, got {got_seed!r}"
        )
        assert got_scb == expected_scb


# ---------------------------------------------------------------------------
# Debug-tab wallet listing
# ---------------------------------------------------------------------------

def test_debug_wallets_list_filters_to_liquidityhelper_named(monkeypatch):
    """Wallets not named 'liquidityhelper' are excluded — same filter
    rule the dashboard uses."""
    api = FakeBitcartAPI()
    api.add_wallet("w-lh", name="liquidityhelper", currency="btclnd")
    api.add_wallet("w-other", name="some-other-wallet", currency="btc")
    api.add_store("s1", wallets=["w-lh"], created="2025-01-01")
    _setup_engine_dispatch(monkeypatch, api)

    rows = _run(wallet_debug._list_debug_wallets(api))
    assert len(rows) == 1
    assert rows[0].wallet_id == "w-lh"


def test_debug_wallets_last_tx_takes_max_across_onchain_and_ln(monkeypatch):
    """last_tx_unix = max(latest_onchain_ts, latest_ln_ts). Pin the
    cross-rail max rather than picking just one source."""
    api = FakeBitcartAPI()
    api.add_wallet("w1", name="liquidityhelper", currency="btclnd")
    api.add_store("s1", wallets=["w1"], created="2025-01-01")
    api.add_onchain_tx("w1", label="x", amount_sat=100, fee_sat=10, txid="aa" * 32, timestamp=1700000000)
    api.add_ln_tx("w1", label="x", amount_msat=-1000, fee_msat=10, payment_hash="bb", timestamp=1800000000)
    _setup_engine_dispatch(monkeypatch, api)

    rows = _run(wallet_debug._list_debug_wallets(api))
    assert len(rows) == 1
    assert rows[0].last_tx_unix == 1800000000


def test_debug_wallets_stores_lists_all_associations(monkeypatch):
    """Two stores sharing one wallet → both names appear in
    stores[]. Pin the multi-store-per-wallet case."""
    api = FakeBitcartAPI()
    api.add_wallet("w-shared", name="liquidityhelper", currency="btclnd")
    api.add_store("s-A", name="Cafe A", wallets=["w-shared"], created="2025-01-01")
    api.add_store("s-B", name="Cafe B", wallets=["w-shared"], created="2025-01-01")
    _setup_engine_dispatch(monkeypatch, api)

    rows = _run(wallet_debug._list_debug_wallets(api))
    assert len(rows) == 1
    assert set(rows[0].stores) == {"Cafe A", "Cafe B"}


# ---------------------------------------------------------------------------
# CSV export (smoke test — pin shape, not every column)
# ---------------------------------------------------------------------------

def test_csv_header_columns_match_spec(monkeypatch):
    """First emitted line is the header; column list is the
    spec'd union. Pin against accidental column reorder /
    rename, which would silently break operator parsing scripts."""
    api = FakeBitcartAPI()
    api.add_wallet("w1", name="liquidityhelper", currency="btclnd")
    api.add_store("s1", wallets=["w1"], created="2025-01-01")
    _setup_engine_dispatch(monkeypatch, api)
    wallet = _run(api.get_wallet("w1"))

    async def collect():
        chunks = []
        async for chunk in wallet_debug._csv_row_stream(api, wallet):
            chunks.append(chunk)
        return chunks

    chunks = _run(collect())
    assert chunks, "stream must yield at least the header row"
    header = chunks[0].rstrip("\r\n")
    assert header == ",".join(wallet_debug._CSV_COLUMNS)


def test_csv_emits_both_onchain_and_ln_rows(monkeypatch):
    """One on-chain tx + one LN tx → header + 2 rows, each tagged
    with its method ('onchain' or 'lightning')."""
    api = FakeBitcartAPI()
    api.add_wallet("w1", name="liquidityhelper", currency="btclnd")
    api.add_store("s1", wallets=["w1"], created="2025-01-01")
    api.add_onchain_tx(
        "w1", label="OPEN CHANNEL",
        amount_sat=100_000, fee_sat=300,
        txid="aa" * 32, timestamp=1700000000,
    )
    api.add_ln_tx(
        "w1", label="lnhelper_cashout",
        amount_msat=-5_000_000, fee_msat=15_000,
        payment_hash="cafe", timestamp=1700001000,
    )
    _setup_engine_dispatch(monkeypatch, api)
    wallet = _run(api.get_wallet("w1"))

    async def collect():
        text = ""
        async for chunk in wallet_debug._csv_row_stream(api, wallet):
            text += chunk
        return text

    text = _run(collect())
    lines = text.strip().splitlines()
    # header + 1 on-chain + 1 lightning = 3 lines
    assert len(lines) == 3, f"expected 3 lines, got {len(lines)}:\n{text}"
    assert "onchain" in lines[1]
    assert "lightning" in lines[2]
