"""Tests for the LOOPD_NETWORK / LOOPD_SERVER_HOST / LOOPD_SERVER_NOTLS
config knobs and the LoopdManager network-mismatch pre-flight check.

Background
----------
Lightning Labs' loopd:
  - mainnet/testnet/signet have built-in default server URLs;
  - regtest/simnet refuse to start without an explicit --server.host;
  - loopd and LND will refuse to interoperate if their networks differ.

Before this work the script hardcoded `LoopdManager(network="mainnet")`
in _swap_provider_registry. That meant the production loop path only
worked on mainnet — and it would fail at swap time with an opaque gRPC
chain-hash error if the LND was on testnet/regtest/signet, with no
clear pointer at config. These tests pin:

  1. _swap_provider_registry now reads the three config knobs and
     passes them through to LoopdManager unchanged.
  2. Defaults preserve current behavior: mainnet, no server override.
  3. The network-mismatch check in get_loopd_for_wallet fires when
     LND's actual network differs from the configured one, with a
     clear error message pointing at LOOPD_NETWORK.
  4. The check is forgiving when LND doesn't report a network field
     (older bitcart-fork builds): warning, not raise.

All tests stub out the actual loopd subprocess + binary download so
they run in <1s with no docker / network access.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

import pytest

import liquidityhelper
import swap_providers


# ---------------------------------------------------------------------------
# _swap_provider_registry wires config → LoopdManager
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_registry(monkeypatch):
    """Clear module-level state between tests so each test starts from
    a clean registry (otherwise the first test's manager persists)."""
    monkeypatch.setattr(liquidityhelper, "_LOOPD_MANAGER", None)
    monkeypatch.setattr(liquidityhelper, "SWAP_PROVIDERS", [])
    yield


@pytest.mark.parametrize("network", ["mainnet", "testnet", "signet"])
def test_registry_passes_network_through_with_no_server_override(network, monkeypatch):
    """Default deploy on a public network: LOOPD_NETWORK is forwarded
    to LoopdManager and the server host stays empty (loopd resolves
    {test,signet}.swap.lightning.today:11010 internally). Pins the
    config-passthrough for all three production-public networks in
    one shot.

    Regtest needs an explicit server override (see the dedicated
    test below) so it's not included here."""
    monkeypatch.setattr(liquidityhelper, "LOOPD_NETWORK", network)
    monkeypatch.setattr(liquidityhelper, "LOOPD_SERVER_HOST", "")
    monkeypatch.setattr(liquidityhelper, "LOOPD_SERVER_NOTLS", False)

    providers = liquidityhelper._swap_provider_registry()
    assert len(providers) == 1
    mgr = providers[0].manager
    assert mgr.network == network
    assert mgr.server_host is None    # empty string → None (loopd auto-picks)
    assert mgr.server_notls is False


def test_registry_passes_regtest_with_server_override(monkeypatch):
    """Regtest path: LOOPD_NETWORK=regtest is meaningless without an
    explicit server override (loopd has no default for regtest). Pin
    that the registry passes BOTH knobs through together."""
    monkeypatch.setattr(liquidityhelper, "LOOPD_NETWORK", "regtest")
    monkeypatch.setattr(
        liquidityhelper, "LOOPD_SERVER_HOST", "127.0.0.1:11010",
    )
    monkeypatch.setattr(liquidityhelper, "LOOPD_SERVER_NOTLS", True)

    providers = liquidityhelper._swap_provider_registry()
    mgr = providers[0].manager
    assert mgr.network == "regtest"
    assert mgr.server_host == "127.0.0.1:11010"
    assert mgr.server_notls is True


def test_registry_caches_manager(monkeypatch):
    """Second call returns the SAME manager (loopd is expensive to
    spin up; we don't want a registry call to constantly rebuild)."""
    monkeypatch.setattr(liquidityhelper, "LOOPD_NETWORK", "mainnet")
    monkeypatch.setattr(liquidityhelper, "LOOPD_SERVER_HOST", "")
    monkeypatch.setattr(liquidityhelper, "LOOPD_SERVER_NOTLS", False)

    a = liquidityhelper._swap_provider_registry()
    b = liquidityhelper._swap_provider_registry()
    assert a is b
    assert a[0].manager is b[0].manager


# ---------------------------------------------------------------------------
# Network-mismatch pre-flight check in LoopdManager.get_loopd_for_wallet
# ---------------------------------------------------------------------------

class _FakeApi:
    """Just enough of BitcartAPI to satisfy get_loopd_for_wallet's
    info-fetch step. Tests pre-load the desired /lndinfo response."""
    def __init__(self, info: Optional[Dict[str, Any]]) -> None:
        self._info = info
    async def get_lnd_info(self, walletid: str) -> Optional[Dict[str, Any]]:
        return self._info


def _make_manager(network: str, tmp_path) -> swap_providers.LoopdManager:
    """Construct a manager with paths pointed at tmp_path so the
    on-disk bits (bin_dir / data_root) don't collide between tests."""
    return swap_providers.LoopdManager(
        bin_dir=tmp_path / "bin",
        data_root=tmp_path / "data",
        network=network,
    )


def _patch_loopd_subprocess(monkeypatch):
    """Stub out the expensive bits of get_loopd_for_wallet so we can
    exercise its early-return + raise paths without actually starting
    loopd:
      - ensure_loop_binaries: do nothing (pretend binaries exist).
      - LoopdInstance.start: no-op (don't spawn a subprocess).
    """
    async def fake_ensure(*a, **kw):
        return {"loop": tmp_path_stub, "loopd": tmp_path_stub}
    monkeypatch.setattr(swap_providers, "ensure_loop_binaries", fake_ensure)

    async def fake_start(self):
        # Don't actually launch loopd. The manager will still add the
        # instance to its registry, which is what we want to assert on.
        return None
    monkeypatch.setattr(swap_providers.LoopdInstance, "start", fake_start)


# tmp_path_stub captured at module level for the fake_ensure return
# value. Tests don't care what it points at; the fake_start no-op
# means we never actually look for the binary.
import pathlib as _pathlib
tmp_path_stub = _pathlib.Path("/tmp/loopd-stub")


def test_mismatch_raises_with_clear_message(tmp_path, monkeypatch, event_loop):
    """The headline pin: LoopdManager configured for mainnet but the
    LND wallet reports testnet → RuntimeError with the LOOPD_NETWORK
    hint in the message."""
    _patch_loopd_subprocess(monkeypatch)
    mgr = _make_manager("mainnet", tmp_path)
    api = _FakeApi({
        "tls_cert": "AA==", "macaroon": "AA==",
        "host": "127.0.0.1", "grpc_port": 10009,
        "network": "testnet",
    })

    with pytest.raises(RuntimeError) as excinfo:
        event_loop.run_until_complete(
            mgr.get_loopd_for_wallet({"id": "w1"}, api)
        )
    msg = str(excinfo.value)
    assert "network mismatch" in msg
    assert "mainnet" in msg
    assert "testnet" in msg
    assert "LOOPD_NETWORK" in msg, (
        "error message must point the operator at the config knob"
    )


@pytest.mark.parametrize("reported_network", ["mainnet", "MAINNET", "Mainnet"])
def test_match_proceeds(reported_network, tmp_path, monkeypatch, event_loop):
    """Configured mainnet, LND reports mainnet in any case-form →
    no exception, instance is registered. Case-insensitive matching
    is a deliberate footgun-avoidance: real LND builds across
    versions have varied between lowercase and titlecase. Lowercase
    is the only case that should ever appear in production today;
    the upper/title variants are pinned here so a future tightening
    that breaks them is loud."""
    _patch_loopd_subprocess(monkeypatch)
    mgr = _make_manager("mainnet", tmp_path)
    api = _FakeApi({
        "tls_cert": "AA==", "macaroon": "AA==",
        "host": "127.0.0.1", "grpc_port": 10009,
        "network": reported_network,
    })

    inst = event_loop.run_until_complete(
        mgr.get_loopd_for_wallet({"id": "w1"}, api)
    )
    assert inst.wallet_id == "w1"
    assert "w1" in mgr._instances


@pytest.mark.parametrize(
    "lndinfo_extra,case_id",
    [
        ({}, "missing-field"),
        ({"network": ""}, "empty-string"),
    ],
    ids=lambda v: v if isinstance(v, str) else None,
)
def test_missing_or_empty_network_does_not_raise(
    lndinfo_extra, case_id, tmp_path, monkeypatch, event_loop, caplog,
):
    """Older or oddly-shaped bitcart-fork /lndinfo responses may
    omit the `network` field entirely OR return it as empty string.
    Both must be tolerated (warn + proceed); the chain-hash check at
    swap time catches a real mismatch later. Covers both shapes in
    one test — the rejection path was identical between them."""
    import logging
    _patch_loopd_subprocess(monkeypatch)
    mgr = _make_manager("mainnet", tmp_path)
    api = _FakeApi({
        "tls_cert": "AA==", "macaroon": "AA==",
        "host": "127.0.0.1", "grpc_port": 10009,
        **lndinfo_extra,
    })

    with caplog.at_level(logging.WARNING, logger="swap_providers"):
        inst = event_loop.run_until_complete(
            mgr.get_loopd_for_wallet({"id": "w1"}, api)
        )
    assert inst.wallet_id == "w1"
    # Warning text should mention we can't pre-flight so operators
    # debugging a later chain-hash error can find this entry.
    assert any(
        "did not report a network field" in r.getMessage()
        for r in caplog.records
    ), f"case={case_id}: missing warning"


def test_no_info_at_all_still_raises_original_error(tmp_path, monkeypatch, event_loop):
    """If /lndinfo returns None (404 / auth failure), the original
    'could not get LND info' error must still fire — our new check
    must NOT mask it."""
    _patch_loopd_subprocess(monkeypatch)
    mgr = _make_manager("mainnet", tmp_path)
    api = _FakeApi(None)

    with pytest.raises(RuntimeError, match="could not get LND info"):
        event_loop.run_until_complete(
            mgr.get_loopd_for_wallet({"id": "w1"}, api)
        )


def test_regtest_with_regtest_lnd_matches(tmp_path, monkeypatch, event_loop):
    """The test rig's path: regtest manager, regtest LND. Must match
    even though there's no built-in loopd server for regtest — server
    matching is a separate concern (and the manager has server_host
    set in that case)."""
    _patch_loopd_subprocess(monkeypatch)
    mgr = swap_providers.LoopdManager(
        bin_dir=tmp_path / "bin",
        data_root=tmp_path / "data",
        network="regtest",
        server_host="127.0.0.1:11010",
        server_notls=True,
    )
    api = _FakeApi({
        "tls_cert": "AA==", "macaroon": "AA==",
        "host": "127.0.0.1", "grpc_port": 10009,
        "network": "regtest",
    })

    inst = event_loop.run_until_complete(
        mgr.get_loopd_for_wallet({"id": "w1"}, api)
    )
    assert inst.server_host == "127.0.0.1:11010"
    assert inst.server_notls is True
    assert inst.network == "regtest"
