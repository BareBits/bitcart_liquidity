"""Pin the decisions.log noise-suppression rules for health warnings.

Three rules being verified, each one corresponds to a specific
operator complaint about decisions.log clutter:

  1. compute_health_warnings is PURE — calling it never emits a
     decisions-log entry. The dashboard endpoint (which runs in any
     of N gunicorn workers, each with its own dedupe state) must
     not be able to spam decisions.log.

  2. emit_health_warning_transitions skips the "never-been-active →
     still-not-active" case. ~95% of decisions.log clutter came
     from emitting one "cleared" line per known warning ID per call,
     even when the warning had never been active. Only true
     True→False transitions emit.

  3. When a real True→False transition does fire, it emits at DEBUG
     on the operational logger — NOT at INFO on the decisions
     logger. decisions.log stays focused on currently-active
     warnings.

These rules together turn a flood of identical lines into a single
WARNING entry per active condition + a DEBUG breadcrumb on its
eventual resolution.
"""

from __future__ import annotations

import asyncio
import logging
from typing import List

import pytest

import liquidityhelper


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


@pytest.fixture(autouse=True)
def _reset_dedupe_state():
    """Each test starts with a clean _last_decision_state so the
    transition assertions don't leak between tests."""
    snapshot = dict(liquidityhelper._last_decision_state)
    liquidityhelper._last_decision_state.clear()
    yield
    liquidityhelper._last_decision_state.clear()
    liquidityhelper._last_decision_state.update(snapshot)


def _capture_logs():
    """Attach in-memory handlers to both the decisions logger and
    the operational logger so a test can assert which one received
    which messages."""
    decisions_records: List[logging.LogRecord] = []
    operational_records: List[logging.LogRecord] = []

    class _Cap(logging.Handler):
        def __init__(self, sink):
            super().__init__(level=logging.DEBUG)
            self.sink = sink
        def emit(self, record):
            self.sink.append(record)

    dec_handler = _Cap(decisions_records)
    op_handler = _Cap(operational_records)
    liquidityhelper.decisions_logger.addHandler(dec_handler)
    liquidityhelper.logger.addHandler(op_handler)
    # Force levels so DEBUG records propagate even if the test
    # environment ships with WARNING-only defaults.
    prior_dec_level = liquidityhelper.decisions_logger.level
    prior_op_level = liquidityhelper.logger.level
    liquidityhelper.decisions_logger.setLevel(logging.DEBUG)
    liquidityhelper.logger.setLevel(logging.DEBUG)

    def cleanup():
        liquidityhelper.decisions_logger.removeHandler(dec_handler)
        liquidityhelper.logger.removeHandler(op_handler)
        liquidityhelper.decisions_logger.setLevel(prior_dec_level)
        liquidityhelper.logger.setLevel(prior_op_level)

    return decisions_records, operational_records, cleanup


# ---------------------------------------------------------------------------
# Rule 1: compute_health_warnings is silent
# ---------------------------------------------------------------------------

def test_compute_health_warnings_does_not_emit_decisions_log():
    """The dashboard endpoint calls compute_health_warnings. It must
    not write anything to decisions.log — otherwise N workers × M
    cache-misses × K warning IDs floods the stream."""
    dec, op, cleanup = _capture_logs()
    try:
        _run(liquidityhelper.compute_health_warnings(api=None))
    finally:
        cleanup()
    decisions_lines = [r.getMessage() for r in dec]
    health_lines = [m for m in decisions_lines if "Health warning" in m]
    assert health_lines == [], (
        "compute_health_warnings emitted decisions-log entries; it "
        f"must stay pure. Got: {health_lines}"
    )


# ---------------------------------------------------------------------------
# Rule 2: cleared events for never-active warnings are skipped
# ---------------------------------------------------------------------------

def test_emit_transitions_skips_never_active_clears():
    """A first-time call to emit_health_warning_transitions with an
    empty `active` list emits ZERO 'cleared' lines. Previously this
    fired ~30 INFO lines per call — one per known warning ID."""
    dec, op, cleanup = _capture_logs()
    try:
        liquidityhelper.emit_health_warning_transitions(active=[])
    finally:
        cleanup()
    cleared_in_decisions = [
        r for r in dec
        if "cleared" in r.getMessage() and "Health warning" in r.getMessage()
    ]
    cleared_in_op = [
        r for r in op
        if "cleared" in r.getMessage() and "Health warning" in r.getMessage()
    ]
    assert cleared_in_decisions == [], (
        f"never-active warnings must not log to decisions; got {len(cleared_in_decisions)} entries"
    )
    assert cleared_in_op == [], (
        f"never-active warnings must not log to operational either; got {len(cleared_in_op)} entries"
    )


# ---------------------------------------------------------------------------
# Rule 3: real transitions emit, and "cleared" goes to operational DEBUG
# ---------------------------------------------------------------------------

def test_active_warning_emits_at_warning_to_decisions():
    """A real HIGH-severity active warning fires a WARNING line on
    the decisions logger. Pin against an accidental level downgrade."""
    fake_active = [{
        "id": "loopd-regtest-no-host",
        "severity": "HIGH",
        "category": "loop",
        "title": "Loop regtest needs LOOPD_SERVER_HOST",
        "message": "test message body",
    }]
    dec, op, cleanup = _capture_logs()
    try:
        liquidityhelper.emit_health_warning_transitions(active=fake_active)
    finally:
        cleanup()
    matches = [r for r in dec if "loopd-regtest-no-host" in r.getMessage()]
    assert len(matches) == 1, f"expected exactly one decisions emission; got {len(matches)}"
    assert matches[0].levelno == logging.WARNING, (
        f"HIGH severity must emit WARNING; got level {matches[0].levelname}"
    )


def test_real_cleared_transition_emits_debug_to_operational_only():
    """Active first, then cleared. The cleared transition MUST land
    on the operational logger at DEBUG, never on decisions.log.
    Operators watching decisions.log see active problems only."""
    fake_active = [{
        "id": "smtp-tls-and-ssl",
        "severity": "MEDIUM",
        "category": "smtp",
        "title": "SMTP TLS and SSL both on",
        "message": "test",
    }]
    # First call: warning is active. Drains the WARNING/INFO emission.
    dec, op, cleanup = _capture_logs()
    try:
        liquidityhelper.emit_health_warning_transitions(active=fake_active)
    finally:
        cleanup()

    # Second call: warning is gone. Should fire the cleared transition.
    dec, op, cleanup = _capture_logs()
    try:
        liquidityhelper.emit_health_warning_transitions(active=[])
    finally:
        cleanup()
    dec_health = [r for r in dec if "smtp-tls-and-ssl" in r.getMessage()]
    op_health = [r for r in op if "smtp-tls-and-ssl" in r.getMessage()]
    assert dec_health == [], (
        f"cleared transition must not appear in decisions.log; got {[r.getMessage() for r in dec_health]}"
    )
    assert len(op_health) == 1, (
        f"cleared transition must appear once in operational log; got {len(op_health)}"
    )
    assert op_health[0].levelno == logging.DEBUG, (
        f"cleared transition must be DEBUG level; got {op_health[0].levelname}"
    )


def test_active_warning_dedupes_across_repeated_calls():
    """Three consecutive calls with the same active warning emit only
    ONCE — log_decision's existing dedupe behavior. Pin so a future
    refactor doesn't accidentally re-emit on every tick."""
    fake_active = [{
        "id": "smtp-partial-config",
        "severity": "MEDIUM",
        "category": "smtp",
        "title": "Partial SMTP",
        "message": "test",
    }]
    dec, op, cleanup = _capture_logs()
    try:
        for _ in range(3):
            liquidityhelper.emit_health_warning_transitions(active=fake_active)
    finally:
        cleanup()
    matches = [r for r in dec if "smtp-partial-config" in r.getMessage()]
    assert len(matches) == 1, (
        f"repeated calls with same active set must dedupe; got {len(matches)} emissions"
    )


def test_collect_health_warnings_still_works_for_tick_loop():
    """The tick loop calls collect_health_warnings (which composes
    compute + emit). Pin that this single-call path still functions
    after the refactor — the tick loop didn't change and we don't
    want to break it."""
    import inspect
    sig = inspect.signature(liquidityhelper.collect_health_warnings)
    assert "api" in sig.parameters, (
        "collect_health_warnings must keep its (api) signature so the tick loop call site continues to work"
    )
    # Empty smoke: returns a list of dicts, no exception.
    result = _run(liquidityhelper.collect_health_warnings(api=None))
    assert isinstance(result, list)
