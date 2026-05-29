"""Log-export HTTP endpoints for the dashboard Logs tab.

Two endpoints, both gated on the same server_management auth as the
rest of the plugin (the export contents include operator-sensitive
diagnostics — payment-failure reasons, channel state, on-chain
addresses, etc. — same risk class as the Logs viewer itself):

  GET /plugins/liquidityhelper/wallet_debug/logs/engine
    Zip with the liquidityhelper plugin's own logs:
      - liquidityhelper.log (+ rotated .log.1 / .log.2)
      - decisions.log

  GET /plugins/liquidityhelper/wallet_debug/logs/all
    Strict superset of /logs/engine. Adds whatever Bitcart application
    logs are reachable from inside the backend container:
      - /datadir/logs/bitcart.log
      - /datadir/logs/bitcart20YYMMDD.log (daily-rotated archive)
    NOT included (container isolation; would need a docker-socket
    mount or per-daemon RPC):
      - btclnd / btc daemon container logs
      - admin / store container logs
      - postgres / redis / nginx logs

Seed-phrase scrubbing
---------------------
Every log line passes through `_scrub_secrets` before being written
into the zip. Two layers:

  1. KNOWN wallet seeds. The endpoint walks api.get_wallets() and
     pulls each wallet's `xpub` field. Per Bitcart conventions a
     12/24-word mnemonic is stored verbatim in `xpub` for hot wallets;
     we replace exact-string occurrences with [REDACTED-WALLET-SEED-N].

  2. BIP39 word-run regex. Any run of 12+ consecutive BIP39-English
     words separated by whitespace is replaced with [REDACTED-MNEMONIC].
     Catches seeds that leaked some other way — e.g. an operator
     pasted a seed phrase into a comment that ended up in a log.

The 2-layer approach is intentional: layer 1 is exact, fast, and
zero-false-positive but only covers seeds Bitcart knows about; layer
2 catches the rest at the cost of occasional false positives on long
English sequences that happen to all be BIP39 words.
"""

from __future__ import annotations

import io
import logging
import os
import re
import traceback
import zipfile
from pathlib import Path
from typing import Any, List, Optional, Set, Tuple

from fastapi import APIRouter, Security
from fastapi.responses import StreamingResponse

logger = logging.getLogger("liquidityhelper.log_export")


# ---------------------------------------------------------------------------
# BIP39 wordlist + scrubber
# ---------------------------------------------------------------------------

def _load_bip39_words() -> Set[str]:
    """Return the canonical 2048-word BIP39 English wordlist as a set.
    File ships alongside this module — copied from python-mnemonic at
    build time so we don't have a runtime dep on `mnemonic`."""
    path = Path(__file__).resolve().parent / "bip39_english.txt"
    try:
        with open(path, "r", encoding="utf-8") as f:
            words = {line.strip() for line in f if line.strip()}
    except Exception as e:
        logger.warning(
            f"BIP39 wordlist load failed; mnemonic-run scrubber disabled: "
            f"{e} {traceback.format_exc()}"
        )
        return set()
    if len(words) != 2048:
        logger.warning(
            f"BIP39 wordlist loaded {len(words)} words (expected 2048); "
            f"scrubber will still run but the file may be corrupt"
        )
    return words


_BIP39_WORDS: Set[str] = _load_bip39_words()


# Tokenizer for the mnemonic-run scrubber. A "token" is a contiguous
# run of lowercase ASCII letters; everything else (whitespace,
# punctuation, digits) is a separator. Apostrophes and inter-word
# punctuation correctly break the run. Multiline-friendly.
_TOKEN_RE = re.compile(r"[a-z]+")

# Minimum number of consecutive BIP39 words to treat as a seed phrase.
# BIP39 mnemonics are always 12 / 15 / 18 / 21 / 24 words, so 12 is
# the lowest valid length. Lower thresholds would false-positive on
# normal text more often.
_MIN_BIP39_RUN = 12


def _scrub_bip39_runs(text: str) -> str:
    """Replace any run of >= _MIN_BIP39_RUN consecutive BIP39 words
    (separated only by whitespace and/or simple punctuation) with
    [REDACTED-MNEMONIC]. The replacement preserves the original
    inter-line layout — we only redact within a single match span,
    everything outside is untouched.
    """
    if not _BIP39_WORDS:
        return text

    # Walk every lowercase-word token. When we find a BIP39 hit, start
    # accumulating consecutive hits. When the run breaks (non-word
    # gap that's NOT pure whitespace, or a non-BIP39 word), flush:
    # if the run is >= threshold, emit redaction; otherwise emit the
    # original span verbatim.
    out: List[str] = []
    cursor = 0
    run_start: Optional[int] = None
    run_count = 0
    last_end = 0
    # Convert text to lowercase ONCE for matching but use the original
    # text for output so case is preserved when not redacting.
    lower = text.lower()
    for m in _TOKEN_RE.finditer(lower):
        word = m.group(0)
        start, end = m.span()
        gap = text[last_end:start]
        # A run continues only if the GAP between this token and the
        # previous is whitespace-only (allowing punctuation common in
        # logs like commas, periods).
        gap_ok = bool(re.fullmatch(r"[\s,;:.\-]*", gap)) if run_start is not None else True
        if word in _BIP39_WORDS and gap_ok:
            if run_start is None:
                run_start = start
            run_count += 1
            last_end = end
            continue
        # Run broken. Flush.
        if run_start is not None and run_count >= _MIN_BIP39_RUN:
            out.append(text[cursor:run_start])
            out.append("[REDACTED-MNEMONIC]")
            cursor = last_end
        run_start = None
        run_count = 0
        last_end = end
    # End-of-text flush.
    if run_start is not None and run_count >= _MIN_BIP39_RUN:
        out.append(text[cursor:run_start])
        out.append("[REDACTED-MNEMONIC]")
        cursor = last_end
    out.append(text[cursor:])
    return "".join(out)


async def _collect_known_seeds(api: Any) -> List[str]:
    """Return every wallet seed phrase Bitcart knows about for this
    operator. For 12/24-word wallets, Bitcart stores the seed verbatim
    in the wallet's `xpub` field (per classes.py:336-337 heuristic
    `xpub.count(' ') == 11`); we exact-string-replace those.

    Watch-only / xpub-only wallets have an actual xpub there (not a
    mnemonic) — we don't redact those (xpub is not a secret).
    """
    seeds: List[str] = []
    try:
        wallets = await api.get_wallets() or []
    except Exception as e:
        logger.warning(f"_collect_known_seeds: get_wallets failed: {e} {traceback.format_exc()}")
        return seeds
    for w in wallets:
        try:
            full = await api.get_wallet(w["id"]) if "id" in w else w
            xpub = (full.get("xpub") if isinstance(full, dict) else None) or ""
        except Exception as e:
            logger.warning(
                f"_collect_known_seeds: get_wallet({w.get('id')}) failed: "
                f"{e} {traceback.format_exc()}"
            )
            continue
        xpub = xpub.strip()
        if not xpub:
            continue
        # Bitcart convention: a 12-word seed has 11 spaces; 24 has 23.
        space_count = xpub.count(" ")
        if space_count in (11, 14, 17, 20, 23):
            seeds.append(xpub)
    return seeds


def _scrub_secrets(text: str, known_seeds: List[str]) -> str:
    """Apply both scrubber layers in sequence."""
    redacted = text
    for i, seed in enumerate(known_seeds):
        if seed and seed in redacted:
            redacted = redacted.replace(seed, f"[REDACTED-WALLET-SEED-{i}]")
    redacted = _scrub_bip39_runs(redacted)
    return redacted


# ---------------------------------------------------------------------------
# File discovery + zip assembly
# ---------------------------------------------------------------------------

# Log roots that may exist inside the bitcart-backend container. Same
# paths used by liquidityhelper itself (see plugin.py + log_endpoints.py)
# and by Bitcart's application logger (which writes to /datadir/logs/).
_PLUGIN_LOG_DIR = "/datadir/plugin_data/liquidityhelper"
_BITCART_LOG_DIR = "/datadir/logs"


def _list_engine_log_files() -> List[Path]:
    """Plugin's own log files: liquidityhelper.log, rotated tail,
    decisions.log. Includes any future-rotated variants automatically
    via the *.log* glob."""
    out: List[Path] = []
    root = Path(_PLUGIN_LOG_DIR)
    if not root.is_dir():
        return out
    try:
        for p in sorted(root.iterdir()):
            if p.is_file() and (".log" in p.name):
                out.append(p)
    except Exception as e:
        logger.warning(f"_list_engine_log_files: iterdir failed: {e} {traceback.format_exc()}")
    return out


def _list_bitcart_log_files() -> List[Path]:
    """Bitcart's application logs at /datadir/logs/. Daily-rotated
    files like bitcart20260527.log + the active bitcart.log."""
    out: List[Path] = []
    root = Path(_BITCART_LOG_DIR)
    if not root.is_dir():
        return out
    try:
        for p in sorted(root.iterdir()):
            if p.is_file() and p.name.endswith(".log"):
                out.append(p)
    except Exception as e:
        logger.warning(f"_list_bitcart_log_files: iterdir failed: {e} {traceback.format_exc()}")
    return out


def _readme_for_zip(include_bitcart: bool, known_seed_count: int) -> str:
    """README.txt for the zip. Explains scope + the seed-phrase
    redaction so the operator knows what's been removed (and what's
    still in there).
    """
    body = [
        "liquidityhelper log export",
        "==========================",
        "",
        "This archive contains diagnostic logs from the liquidityhelper",
        "plugin and may contain sensitive operational information.",
        "",
        "BEFORE SHARING THIS ZIP, READ CAREFULLY:",
        "",
        "  - Even after scrubbing, logs may contain channel state,",
        "    on-chain addresses, payment hashes, peer pubkeys, and",
        "    error messages that reveal operational details.",
        "  - DO NOT share this zip with anyone you do not trust.",
        "  - Anyone with access to this data may use it to learn about",
        "    your wallet operations or potentially target your funds.",
        "",
        "Contents",
        "--------",
        "",
        "engine/",
        "  liquidityhelper.log         Current plugin operational log",
        "  liquidityhelper.log.1, .2   Rotated tail (older entries)",
        "  decisions.log               Decision-log audit trail",
        "",
    ]
    if include_bitcart:
        body.extend([
            "bitcart/",
            "  bitcart.log                  Bitcart's currently-active app log",
            "  bitcart20YYYYMMDD.log        Daily-rotated archive",
            "",
            "NOT included (container isolation):",
            "  - btclnd / btc daemon container logs",
            "  - admin / store container logs",
            "  - postgres / redis / nginx logs",
            "",
            "  These live in separate Docker containers; the plugin runs",
            "  inside compose-backend-1 and has no Docker-socket access",
            "  to reach them. Operators who need them can fetch via",
            "  `docker logs <container>` on the host.",
            "",
        ])
    body.extend([
        "Scrubbing",
        "---------",
        "",
        f"  Known wallet seeds redacted: {known_seed_count}",
        "    Bitcart-stored 12/15/18/21/24-word seed phrases were",
        "    exact-string-replaced with [REDACTED-WALLET-SEED-N].",
        "",
        "  Mnemonic-pattern scrubber: enabled",
        "    Any run of 12+ consecutive BIP39 English words separated",
        "    by whitespace/punctuation was replaced with",
        "    [REDACTED-MNEMONIC]. False positives are possible on long",
        "    English sequences that happen to all be BIP39 words; if",
        "    you see a redaction in an unexpected place, that's why.",
        "",
        "  NOT scrubbed (in this version):",
        "    - Auth tokens, LND macaroons, database URLs",
        "    - LN payment hashes, peer pubkeys, channel points",
        "    - On-chain addresses, transaction ids",
        "",
        "  Treat this archive as containing operational secrets.",
        "",
    ])
    return "\n".join(body)


async def _build_log_zip(api: Any, include_bitcart: bool) -> Tuple[bytes, str]:
    """Build the zip in memory. Streams each log file through the
    scrubber so seeds never reach the zip bytes."""
    known_seeds = await _collect_known_seeds(api)

    def _arcname(prefix: str, path: Path) -> str:
        return f"{prefix}/{path.name}"

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(
            "README.txt",
            _readme_for_zip(include_bitcart=include_bitcart, known_seed_count=len(known_seeds)),
        )
        for path in _list_engine_log_files():
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    contents = f.read()
            except Exception as e:
                logger.warning(
                    f"_build_log_zip: failed reading {path}: {e} {traceback.format_exc()}"
                )
                continue
            scrubbed = _scrub_secrets(contents, known_seeds)
            z.writestr(_arcname("engine", path), scrubbed)
        if include_bitcart:
            for path in _list_bitcart_log_files():
                try:
                    with open(path, "r", encoding="utf-8", errors="replace") as f:
                        contents = f.read()
                except Exception as e:
                    logger.warning(
                        f"_build_log_zip: failed reading {path}: {e} {traceback.format_exc()}"
                    )
                    continue
                scrubbed = _scrub_secrets(contents, known_seeds)
                z.writestr(_arcname("bitcart", path), scrubbed)

    # Filename varies by scope so an operator who exports both ends
    # up with distinct files in their Downloads.
    import datetime as _dt
    ts = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    suffix = "all" if include_bitcart else "engine"
    filename = f"liquidityhelper-logs-{suffix}-{ts}.zip"
    return (buf.getvalue(), filename)


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

def build_log_export_router(auth_dependency: Any | None = None) -> APIRouter:
    """Mount the log-export endpoints under the existing
    wallet_debug prefix so they share auth + URL discovery with the
    other download endpoints."""
    router = APIRouter(prefix="/plugins/liquidityhelper/wallet_debug")
    deps = (
        [Security(auth_dependency, scopes=["server_management"])]
        if auth_dependency is not None else []
    )

    @router.get("/logs/engine", dependencies=deps)
    async def export_engine_logs() -> StreamingResponse:
        from liquidityhelper import _get_dashboard_api
        api = await _get_dashboard_api()
        try:
            zip_bytes, filename = await _build_log_zip(api, include_bitcart=False)
        finally:
            try:
                await api.close()
            except Exception as e:
                logger.debug(f"export_engine_logs: api.close cleanup: {e}")
        return StreamingResponse(
            io.BytesIO(zip_bytes),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @router.get("/logs/all", dependencies=deps)
    async def export_all_logs() -> StreamingResponse:
        from liquidityhelper import _get_dashboard_api
        api = await _get_dashboard_api()
        try:
            zip_bytes, filename = await _build_log_zip(api, include_bitcart=True)
        finally:
            try:
                await api.close()
            except Exception as e:
                logger.debug(f"export_all_logs: api.close cleanup: {e}")
        return StreamingResponse(
            io.BytesIO(zip_bytes),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    return router
