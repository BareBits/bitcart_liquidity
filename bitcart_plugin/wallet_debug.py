"""HTTP endpoints for the dashboard's Debug tab.

Three endpoints, all gated on the same server_management auth as the
rest of the plugin:

  GET /plugins/liquidityhelper/wallet_debug/wallets
    List of liquidityhelper-named wallets with their store
    associations and the timestamp of the most recent transaction
    (max across on-chain + LN history).

  GET /plugins/liquidityhelper/wallet_debug/wallet/{id}/csv
    Streams a CSV export of ALL transactions for the wallet — on-
    chain + Lightning unified into one sparse-columns table. The
    backend streams row-by-row via a StreamingResponse so a wallet
    with thousands of txs doesn't materialize a multi-MB string in
    memory.

  GET /plugins/liquidityhelper/wallet_debug/wallet/{id}/backup
    Returns a zip containing the wallet's seed + LN disaster-recovery
    artifacts. Two flavors:
      btclnd : seed.txt + channel.backup (LND's SCB via gRPC
               ExportAllChannelBackups).
      btc    : seed.txt + channel_backups.json (per-channel SCBs via
               Electrum's export_channel_backup RPC) + wallet_info.json.
    Both flavors recover on-chain funds from the seed and recover LN
    channel funds via force-close on import. Symmetrical disaster-
    recovery guarantee.

Security: every endpoint requires server_management auth. The UI
shows an extra confirmation modal before triggering CSV/backup — but
that's UI-side belt-and-suspenders; the auth scope is what actually
protects the seed phrase from being exposed.
"""

from __future__ import annotations

import csv
import datetime
import io
import json
import logging
import traceback
import zipfile
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException, Security
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

logger = logging.getLogger("liquidityhelper.wallet_debug")


# ---------------------------------------------------------------------------
# Response shapes
# ---------------------------------------------------------------------------

class DebugWalletRow(BaseModel):
    """One row in the Debug-tab wallet table."""
    wallet_id: str
    wallet_short: str                 # first 8 chars for inline display
    wallet_name: str                  # always "liquidityhelper" today
    currency: str                     # "btc" | "btclnd"
    stores: List[str]                 # store names; multiple if shared
    # Most recent tx timestamp (unix seconds), max(onchain, lightning).
    # 0 means we couldn't find any tx for this wallet — UI renders '—'.
    last_tx_unix: int
    last_tx_iso: str                  # ISO 'YYYY-MM-DD HH:MM:SS' or '—'


class DebugWalletsResponse(BaseModel):
    wallets: List[DebugWalletRow]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _iso_or_dash(ts: int) -> str:
    """Mirror of dashboard._iso — duplicated here to keep this module
    free of a hard dependency on dashboard.py."""
    if not ts:
        return "—"
    try:
        return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, OSError, OverflowError):
        return "—"


async def _list_debug_wallets(api: Any) -> List[DebugWalletRow]:
    """Enumerate every liquidityhelper-named wallet and build a
    DebugWalletRow per wallet, including:
      - the store name(s) using it (a wallet can be shared by N stores)
      - the timestamp of the most recent tx across on-chain + LN
    """
    # Lazy imports — keeps this module importable in focused unit tests.
    from liquidityhelper import list_onchain_history, list_ln_payments_with_labels

    try:
        wallets = await api.get_wallets() or []
    except Exception as e:
        logger.warning(f"_list_debug_wallets: get_wallets failed: {e} {traceback.format_exc()}")
        return []
    try:
        stores = await api.get_stores() or []
    except Exception as e:
        logger.warning(f"_list_debug_wallets: get_stores failed: {e} {traceback.format_exc()}")
        stores = []

    # Map wallet_id -> [store_name, ...]. Walk every store's wallet
    # list rather than relying on best_ln_wallet, so a wallet
    # referenced from a store row but not the active LN wallet still
    # shows up associated with the store.
    wallet_to_stores: Dict[str, List[str]] = {}
    for s in stores:
        sname = s.get("name") or s.get("id") or ""
        for wid in s.get("wallets", []) or []:
            wallet_to_stores.setdefault(wid, []).append(sname)

    rows: List[DebugWalletRow] = []
    for w in wallets:
        if w.get("name") != "liquidityhelper":
            continue
        wid = w.get("id") or ""

        # Most-recent timestamp. Cheap: we walk both histories and
        # take the max of all `timestamp` fields. Either history may
        # be empty (or the rpc fail) — we just take whatever we get.
        latest = 0
        try:
            onchain = await list_onchain_history(wallet=w, api=api)
            for tx in onchain or []:
                ts = int(tx.get("timestamp") or 0)
                if ts > latest:
                    latest = ts
        except Exception as e:
            logger.warning(
                f"_list_debug_wallets: list_onchain_history failed for "
                f"wallet {wid}: {e} {traceback.format_exc()}"
            )
        try:
            ln = await list_ln_payments_with_labels(wallet=w, api=api)
            for tx in ln or []:
                ts = int(tx.get("timestamp") or 0)
                if ts > latest:
                    latest = ts
        except Exception as e:
            logger.warning(
                f"_list_debug_wallets: list_ln_payments_with_labels failed for "
                f"wallet {wid}: {e} {traceback.format_exc()}"
            )

        rows.append(DebugWalletRow(
            wallet_id=wid,
            wallet_short=wid[:8],
            wallet_name=w.get("name") or "",
            currency=w.get("currency") or "",
            stores=wallet_to_stores.get(wid, []),
            last_tx_unix=latest,
            last_tx_iso=_iso_or_dash(latest),
        ))

    rows.sort(key=lambda r: r.wallet_id)
    return rows


# ---------------------------------------------------------------------------
# CSV export — unified table with sparse columns
# ---------------------------------------------------------------------------

# Column order is stable across exports — operators sometimes script
# against this. New columns get appended at the end so an existing
# parser doesn't shift columns when we add a field.
_CSV_COLUMNS: List[str] = [
    # Basics
    "timestamp_unix",
    "timestamp_iso",
    "method",              # "onchain" | "lightning"
    "direction",           # "incoming" | "outgoing"
    "amount_sat",
    "fee_sat",
    "label",
    # On-chain specific
    "txid",
    "block_height",
    "num_confirmations",
    "dest_address",
    # Lightning specific
    "payment_hash",
    "ln_type",             # "payment" | "invoice" | other strings the daemon emits
    "ln_preimage",
    "ln_status",
    # Engine-side metadata. raw_tx_json captures every field the
    # wallet daemon emitted that didn't get its own column — the
    # operator can post-process if they need an obscure LND field.
    "raw_tx_json",
]


def _direction_for_onchain(tx: Dict[str, Any]) -> str:
    """Outgoing if amount_sat < 0 OR incoming flag is False. Defensive
    — both signals exist in different daemon outputs."""
    if tx.get("incoming") is True:
        return "incoming"
    a = tx.get("amount_sat")
    try:
        a = float(a) if a is not None else 0
    except (TypeError, ValueError):
        a = 0
    if a < 0:
        return "outgoing"
    return "incoming"


def _direction_for_ln(tx: Dict[str, Any]) -> str:
    """LN: negative amount_msat means we sent, positive means we
    received. Zero is unusual but defaults to 'incoming' for safety."""
    a = tx.get("amount_msat")
    try:
        a = float(a) if a is not None else 0
    except (TypeError, ValueError):
        a = 0
    return "outgoing" if a < 0 else "incoming"


def _onchain_to_csv_row(tx: Dict[str, Any]) -> Dict[str, Any]:
    ts = int(tx.get("timestamp") or 0)
    amount_sat = tx.get("amount_sat")
    try:
        amount_sat = int(abs(float(amount_sat))) if amount_sat is not None else None
    except (TypeError, ValueError):
        amount_sat = None
    fee_sat = tx.get("fee_sat")
    try:
        fee_sat = int(abs(float(fee_sat))) if fee_sat is not None else None
    except (TypeError, ValueError):
        fee_sat = None
    return {
        "timestamp_unix": ts,
        "timestamp_iso": _iso_or_dash(ts),
        "method": "onchain",
        "direction": _direction_for_onchain(tx),
        "amount_sat": amount_sat if amount_sat is not None else "",
        "fee_sat": fee_sat if fee_sat is not None else "",
        "label": tx.get("label") or "",
        "txid": tx.get("txid") or "",
        "block_height": tx.get("block_height", "") or "",
        "num_confirmations": tx.get("num_confirmations", "") or "",
        "dest_address": tx.get("dest_address") or "",
        "payment_hash": "",
        "ln_type": "",
        "ln_preimage": "",
        "ln_status": "",
        # Preserve every field the daemon emitted in case the operator
        # needs something we didn't surface as a column.
        "raw_tx_json": json.dumps(tx, default=str, sort_keys=True),
    }


def _ln_to_csv_row(tx: Dict[str, Any]) -> Dict[str, Any]:
    ts = int(tx.get("timestamp") or 0)
    amount_msat = tx.get("amount_msat")
    try:
        amount_msat = int(amount_msat) if amount_msat is not None else 0
    except (TypeError, ValueError):
        amount_msat = 0
    fee_msat = tx.get("fee_msat")
    try:
        fee_msat = int(fee_msat) if fee_msat is not None else 0
    except (TypeError, ValueError):
        fee_msat = 0
    return {
        "timestamp_unix": ts,
        "timestamp_iso": _iso_or_dash(ts),
        "method": "lightning",
        "direction": _direction_for_ln(tx),
        "amount_sat": abs(amount_msat) // 1000,
        "fee_sat": abs(fee_msat) // 1000,
        "label": tx.get("label") or "",
        "txid": "",
        "block_height": "",
        "num_confirmations": "",
        "dest_address": "",
        "payment_hash": tx.get("payment_hash") or "",
        "ln_type": tx.get("type") or "",
        "ln_preimage": tx.get("preimage") or tx.get("payment_preimage") or "",
        "ln_status": tx.get("status") or "",
        "raw_tx_json": json.dumps(tx, default=str, sort_keys=True),
    }


async def _csv_row_stream(api: Any, wallet: Dict[str, Any]) -> AsyncIterator[str]:
    """Async generator yielding CSV lines (each terminated by \\r\\n).
    First yield is the header row; subsequent yields are data rows.
    StreamingResponse pipes these straight to the wire so a 5k-tx
    wallet doesn't materialize a multi-MB string in memory."""
    from liquidityhelper import list_onchain_history, list_ln_payments_with_labels

    # Reusable writer-on-buffer pattern: csv.DictWriter writes to a
    # StringIO we drain and reset between rows. This is what gets us
    # proper escaping/quoting without writing our own escaper.
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_CSV_COLUMNS, lineterminator="\r\n")
    writer.writeheader()
    yield buf.getvalue()
    buf.seek(0)
    buf.truncate(0)

    # On-chain rows first. If the rpc itself fails we yield a comment
    # row and continue — the operator gets a partial CSV with an
    # explanation rather than a 500 mid-stream.
    try:
        onchain = await list_onchain_history(wallet=wallet, api=api)
    except Exception as e:
        logger.warning(
            f"csv_row_stream: list_onchain_history failed for "
            f"wallet {wallet.get('id')}: {e} {traceback.format_exc()}"
        )
        onchain = []
        yield f"# error fetching on-chain history: {e}\r\n"
    for tx in onchain or []:
        try:
            writer.writerow(_onchain_to_csv_row(tx))
        except Exception as e:
            logger.warning(
                f"csv_row_stream: skipping malformed on-chain tx "
                f"{tx.get('txid')}: {e} {traceback.format_exc()}"
            )
            continue
        yield buf.getvalue()
        buf.seek(0)
        buf.truncate(0)

    try:
        ln = await list_ln_payments_with_labels(wallet=wallet, api=api)
    except Exception as e:
        logger.warning(
            f"csv_row_stream: list_ln_payments_with_labels failed for "
            f"wallet {wallet.get('id')}: {e} {traceback.format_exc()}"
        )
        ln = []
        yield f"# error fetching LN history: {e}\r\n"
    for tx in ln or []:
        try:
            writer.writerow(_ln_to_csv_row(tx))
        except Exception as e:
            logger.warning(
                f"csv_row_stream: skipping malformed LN tx "
                f"{tx.get('payment_hash')}: {e} {traceback.format_exc()}"
            )
            continue
        yield buf.getvalue()
        buf.seek(0)
        buf.truncate(0)


# ---------------------------------------------------------------------------
# Backup zip — btclnd vs btc flavors
# ---------------------------------------------------------------------------

def _safe_zip_filename(wallet_short: str, kind: str) -> str:
    """Filename for Content-Disposition. Use the wallet short id so an
    operator backing up multiple wallets ends up with distinct files.
    Sanitize anything weird the wallet id might somehow contain."""
    safe = "".join(c for c in wallet_short if c.isalnum() or c in "-_")
    if not safe:
        safe = "wallet"
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"liquidityhelper-{kind}-{safe}-{ts}.zip"


async def _build_btclnd_backup(api: Any, wallet: Dict[str, Any]) -> Tuple[bytes, str]:
    """Build a btclnd backup zip. Returns (zip_bytes, filename).

    Contents:
      seed.txt        — the aezeed phrase Bitcart stored in the
                        wallet's xpub field at creation time. Sufficient
                        for `lnd --restore` after recreating the wallet.
      channel.backup  — LND's Static Channel Backup (SCB), fetched via
                        gRPC ExportAllChannelBackups. The standard
                        LND-recommended disaster-recovery artifact.

    On gRPC failure we still emit the zip with seed.txt only and an
    `error.txt` describing what failed — partial backup > no backup.
    """
    from liquidityhelper import lnd_rpc

    wid = wallet.get("id") or ""
    seed = (wallet.get("xpub") or "").strip()

    channel_backup_bytes: Optional[bytes] = None
    error_text: Optional[str] = None
    try:
        resp = await lnd_rpc(api, wid, "ExportAllChannelBackups", {}, "Lightning")
        if isinstance(resp, dict):
            multi = resp.get("multi_chan_backup") or {}
            raw = multi.get("multi_chan_backup")
            if raw:
                # lnd_rpc returns bytes fields as base64 strings (the
                # JSON-over-grpc default). Decode back to raw bytes.
                import base64
                channel_backup_bytes = base64.b64decode(raw)
    except Exception as e:
        error_text = f"ExportAllChannelBackups failed: {e}\n{traceback.format_exc()}"
        logger.warning(f"backup btclnd wallet {wid}: {error_text}")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("seed.txt", seed + "\n" if seed else "")
        if channel_backup_bytes is not None:
            z.writestr("channel.backup", channel_backup_bytes)
        if error_text:
            z.writestr("error.txt", error_text)
    return (buf.getvalue(), _safe_zip_filename(wid[:8], "btclnd"))


async def _build_electrum_backup(api: Any, wallet: Dict[str, Any]) -> Tuple[bytes, str]:
    """Build an Electrum backup zip. Returns (zip_bytes, filename).

    Contents:
      seed.txt              — wallet seed (the value Bitcart stored in
                              wallet.xpub at creation).
      channel_backups.json  — list of {channel_point, encrypted_backup}
                              for each open channel, fetched via
                              Electrum's export_channel_backup RPC.
                              These are the Electrum-side equivalent of
                              LND's per-channel SCB entries.
      wallet_info.json      — currency, name, network metadata; useful
                              on restore to confirm "I'm importing into
                              the right wallet type".

    Same partial-backup-on-error semantics as btclnd: any rpc failure
    is captured in an error.txt entry so the operator can re-run
    later or escalate.
    """
    from liquidityhelper import electrum_rpc

    wid = wallet.get("id") or ""
    seed = (wallet.get("xpub") or "").strip()

    channel_backups: List[Dict[str, Any]] = []
    error_text: Optional[str] = None
    try:
        channels_resp = await electrum_rpc("list_channels", seed)
        channels = (channels_resp or {}).get("result", []) or []
        for ch in channels:
            cp = ch.get("channel_point") or ch.get("channel_id")
            if not cp:
                continue
            try:
                resp = await electrum_rpc(
                    "export_channel_backup", seed,
                    {"channel_point": cp},
                )
                enc = (resp or {}).get("result")
                if enc:
                    channel_backups.append({
                        "channel_point": cp,
                        "encrypted_backup": enc,
                    })
            except Exception as e:
                logger.warning(
                    f"backup electrum wallet {wid}: export_channel_backup "
                    f"failed for channel {cp}: {e} {traceback.format_exc()}"
                )
    except Exception as e:
        error_text = f"list_channels failed: {e}\n{traceback.format_exc()}"
        logger.warning(f"backup electrum wallet {wid}: {error_text}")

    wallet_info = {
        "currency": wallet.get("currency") or "",
        "name": wallet.get("name") or "",
        "id": wid,
        # Network detection is best-effort; we don't have a clean
        # Electrum equivalent of GetInfo.network, so just propagate
        # whatever Bitcart's wallet record carried.
        "lightning_enabled": wallet.get("lightning_enabled", True),
        "exported_at": datetime.datetime.now().isoformat(),
    }

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("seed.txt", seed + "\n" if seed else "")
        z.writestr(
            "channel_backups.json",
            json.dumps(channel_backups, indent=2, sort_keys=True),
        )
        z.writestr(
            "wallet_info.json",
            json.dumps(wallet_info, indent=2, sort_keys=True),
        )
        if error_text:
            z.writestr("error.txt", error_text)
    return (buf.getvalue(), _safe_zip_filename(wid[:8], "electrum"))


async def _fetch_wallet_or_404(api: Any, wallet_id: str) -> Dict[str, Any]:
    """Common preflight for the per-wallet endpoints: fetch the wallet,
    refuse if it isn't a liquidityhelper-named one. 404 keeps the
    endpoints from leaking info about unrelated wallets to a clumsy
    request."""
    try:
        wallet = await api.get_wallet(wallet_id)
    except Exception as e:
        logger.warning(
            f"_fetch_wallet_or_404: get_wallet failed for {wallet_id}: "
            f"{e} {traceback.format_exc()}"
        )
        raise HTTPException(404, "wallet not found")
    if not wallet:
        raise HTTPException(404, "wallet not found")
    if wallet.get("name") != "liquidityhelper":
        # Not strictly a 404 — wallet exists — but the plugin's
        # debug surface only operates on its own wallets.
        raise HTTPException(404, "wallet not a liquidityhelper wallet")
    return wallet


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

def build_wallet_debug_router(auth_dependency: Any | None = None) -> APIRouter:
    """Mount the wallet-debug endpoints under
    /plugins/liquidityhelper/wallet_debug. Auth scope matches the
    other plugin endpoints (server_management) — exposing seed
    phrases and SCBs is operator-only territory."""
    router = APIRouter(prefix="/plugins/liquidityhelper/wallet_debug")
    deps = (
        [Security(auth_dependency, scopes=["server_management"])]
        if auth_dependency is not None else []
    )

    @router.get("/wallets", response_model=DebugWalletsResponse, dependencies=deps)
    async def wallets_endpoint() -> DebugWalletsResponse:
        from liquidityhelper import _get_dashboard_api
        api = await _get_dashboard_api()
        try:
            rows = await _list_debug_wallets(api)
        finally:
            try:
                await api.close()
            except Exception as e:
                logger.debug(f"wallets endpoint: api.close cleanup: {e}")
        return DebugWalletsResponse(wallets=rows)

    @router.get("/wallet/{wallet_id}/csv", dependencies=deps)
    async def export_csv_endpoint(wallet_id: str) -> StreamingResponse:
        from liquidityhelper import _get_dashboard_api
        api = await _get_dashboard_api()
        wallet = await _fetch_wallet_or_404(api, wallet_id)
        filename = f"liquidityhelper-{wallet_id[:8]}-transactions-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}.csv"

        async def stream() -> AsyncIterator[bytes]:
            try:
                async for chunk in _csv_row_stream(api, wallet):
                    yield chunk.encode("utf-8")
            finally:
                try:
                    await api.close()
                except Exception as e:
                    logger.debug(f"csv endpoint: api.close cleanup: {e}")

        return StreamingResponse(
            stream(),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @router.get("/wallet/{wallet_id}/backup", dependencies=deps)
    async def backup_endpoint(wallet_id: str) -> StreamingResponse:
        from liquidityhelper import _get_dashboard_api
        api = await _get_dashboard_api()
        try:
            wallet = await _fetch_wallet_or_404(api, wallet_id)
            currency = wallet.get("currency") or ""
            if currency == "btclnd":
                zip_bytes, filename = await _build_btclnd_backup(api, wallet)
            else:
                # Default to the Electrum flavor for "btc" and anything
                # else — symmetric coverage, lets a future currency
                # work without code changes (it'll get seed.txt at
                # minimum).
                zip_bytes, filename = await _build_electrum_backup(api, wallet)
        finally:
            try:
                await api.close()
            except Exception as e:
                logger.debug(f"backup endpoint: api.close cleanup: {e}")

        return StreamingResponse(
            io.BytesIO(zip_bytes),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    return router
