"""Integration tests for the gossip-readiness gate against a real
regtest LND.

The unit tests in tests/gossip_readiness_tests.py exercise the
DECISION logic of evaluate_gossip_readiness using hand-built proto
objects and a fake stub. These are fast (<1s) and cover edge cases
that would be hard to reproduce on a real LND. But they share one
weakness: they trust our assumptions about LND's proto. If a future
LND version renames or removes `synced_to_graph` or `chains[0].network`,
the unit tests still pass because they construct the proto themselves.

This file closes that gap by running against a real regtest LND from
the existing `lnd_pair` fixture (in tests/conftest.py). The fixture
spins up bitcoind + 2 LND nodes + channels — slow (~30-60s) but the
proto-shape assertions guarantee that the fields the readiness gate
depends on are actually populated by LND in production.

Run explicitly:
    pytest tests/lnd_gossip_readiness_integration_tests.py

These tests intentionally are NOT part of the code-only suite — they
download bitcoind + lnd binaries, spawn subprocesses, and take real
time. The unit tests in gossip_readiness_tests.py keep covering the
fast-feedback case.
"""

from __future__ import annotations

import asyncio
import datetime
import sys
import time
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import liquidityhelper
import lnd_graph_pull
from lnd_proto import lightning_pb2


# Every test in this file is read-only against the LND rig — they only
# query GetInfo / DescribeGraph / GetNodeInfo and never close channels
# or shift balances. The engine-side LightningNode DB rows ARE
# mutated, but those reset cleanly between tests via the
# `reset_engine_db_state` autouse below. Sharing one rig per module
# turns 6 × ~30s setup into 1 × ~30s setup — about 150 seconds saved.
pytestmark = pytest.mark.usefixtures("reset_engine_db_state")


@pytest.fixture(scope="module")
def lnd_pair(lnd_pair_shared):
    """Alias the shared module-scoped rig under the same name every
    test in this file already expects, so test bodies don't change."""
    return lnd_pair_shared


# ---------------------------------------------------------------------------
# End-to-end gate evaluation against a real regtest LND
# ---------------------------------------------------------------------------
#
# The proto-shape smoke tests previously here (get_info / describe_graph
# field assertions) were removed: they only ran to prove that the fields
# evaluate_gossip_readiness reads exist on a real response, but the
# end-to-end gate test below necessarily walks the same fields — if any
# of them disappear or rename, the gate test fails with AttributeError
# instead of returning the wrong decision. The standalone smokes were
# pure cost (~60s each of regtest LND boot) with no marginal coverage.

async def _wait_for_synced_to_graph(stub, timeout: float = 30.0) -> lightning_pb2.GetInfoResponse:
    """Poll GetInfo until synced_to_graph flips true OR we time out.
    Returns whatever response we got at the last poll regardless of
    success — callers assert on the returned object themselves."""
    deadline = time.time() + timeout
    info = None
    while time.time() < deadline:
        info = await lnd_graph_pull.fetch_get_info(stub)
        if info.synced_to_graph:
            return info
        await asyncio.sleep(0.5)
    return info


def test_evaluate_gossip_readiness_against_real_lnd_passes_on_regtest(
    lnd_pair, event_loop,
):
    """End-to-end on regtest:
      - synced_to_graph should converge to True
      - network == 'regtest' bypasses the node-count check
      - we pass uptime_seconds=60 (synthesized — we don't wait the
        15s default just for the test) and min_uptime_seconds=0
      - therefore the gate must say ok=True

    If this fails, either the proto-field assumption is wrong (caught
    by the test above) or evaluate_gossip_readiness has regressed."""
    info = event_loop.run_until_complete(_wait_for_synced_to_graph(lnd_pair.a._stub))
    graph = event_loop.run_until_complete(
        lnd_graph_pull.fetch_channel_graph(lnd_pair.a._stub)
    )
    ok, reason, details = lnd_graph_pull.evaluate_gossip_readiness(
        info, graph,
        uptime_seconds=60,
        min_node_count=250,         # would block mainnet with tiny graph
        min_uptime_seconds=0,       # don't make the test wait 15s
    )
    assert ok is True, (
        f"readiness gate should pass on a synced-to-graph regtest LND "
        f"(network=regtest skips node-count check); reason={reason!r}, "
        f"details={details}"
    )
    assert details["network"] == "regtest"
    assert details["min_node_count_required"] == 0, (
        "regtest must trigger the non-mainnet bypass of node-count"
    )


def test_evaluate_gossip_readiness_blocks_real_lnd_at_low_uptime(
    lnd_pair, event_loop,
):
    """Pinning the uptime gate against a real LND: if we pass
    uptime_seconds=5 with min_uptime_seconds=15, the gate must block
    regardless of how healthy the rest of LND looks. This catches a
    regression where the uptime gate somehow stops applying when
    other signals are green."""
    info = event_loop.run_until_complete(_wait_for_synced_to_graph(lnd_pair.a._stub))
    graph = event_loop.run_until_complete(
        lnd_graph_pull.fetch_channel_graph(lnd_pair.a._stub)
    )
    ok, reason, _ = lnd_graph_pull.evaluate_gossip_readiness(
        info, graph,
        uptime_seconds=5, min_node_count=250, min_uptime_seconds=15,
    )
    assert ok is False
    assert "uptime 5s" in reason


# ---------------------------------------------------------------------------
# Full pull_and_upsert against a real regtest LND
# ---------------------------------------------------------------------------

def test_pull_and_upsert_end_to_end_against_real_lnd(lnd_pair, event_loop):
    """Run the actual pull pipeline against a real LND. With
    relaxed criteria (any capacity, any channel count, any age) and
    the gossip gate dialed down for regtest, the pull should produce
    `skipped=False` and walk however many candidates fit the filter
    in this 2-node test network.

    We don't assert on a specific upserted count because regtest
    gossip propagation timing is non-deterministic — sometimes both
    nodes are visible, sometimes neither has fully gossiped. We only
    assert that the pull RAN (didn't skip) and that the stats dict
    has the expected shape."""
    from node_database import LightningNode
    LightningNode.delete().execute()

    info = event_loop.run_until_complete(_wait_for_synced_to_graph(lnd_pair.a._stub))
    # If LND hasn't actually synced its graph yet, skip cleanly — the
    # gate would block this pull and the test would not be a useful
    # verification of the pipeline.
    if not info.synced_to_graph:
        pytest.skip(
            "regtest LND never reached synced_to_graph=True within 30s; "
            "real-LND test fixture is not ready for this assertion"
        )

    stats = event_loop.run_until_complete(lnd_graph_pull.pull_and_upsert(
        lnd_pair.a._stub,
        min_capacity_sat=1,         # accept any channel size
        min_channel_count=0,        # accept any number of channels
        min_age_days=0,             # accept any age (regtest is brand new)
        max_node_announcement_age_days=365 * 100,   # don't filter on freshness
        gossip_min_node_count=0,    # regtest path doesn't apply this anyway
        gossip_min_uptime_seconds=0,
        lnd_uptime_seconds=60,
    ))

    # The pipeline ran (didn't short-circuit on readiness).
    assert stats["skipped"] is False, (
        f"pull_and_upsert should NOT skip on a healthy regtest LND; "
        f"got skip_reason={stats.get('skip_reason')!r}, stats={stats}"
    )
    # Stats dict has the documented shape.
    for key in (
        "total_graph_nodes", "candidates_after_lightweight_filter",
        "upserted", "skipped_get_node_info", "skipped_validation",
    ):
        assert key in stats, f"stats missing expected key {key!r}; got {stats}"
    # Readiness details should reflect the regtest network.
    assert stats["readiness"]["network"] == "regtest"


# Note: `test_lnd_uptime_self_tracker_against_real_lnd` previously
# lived here but was removed — the tracker is a pure in-process
# dict-mutation, already covered comprehensively by
# gossip_readiness_tests.py::TestLndUptimeTracker against mocks.
# Booting a real LND just to mutate a Python dict was ~60s of
# zero-marginal coverage.
