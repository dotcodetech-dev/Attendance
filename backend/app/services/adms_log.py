"""
Persistent log of what biometric readers send to (and receive from) the ADMS / push endpoints.

Why it exists: AI-face readers speak several dialects of the push protocol, and "the command was
Executed" only means the reader answered with a non-negative code. To work out why a face or
fingerprint template did not arrive we need the real traffic: the handshake parameters, the exact
command text we sent, the acknowledgement codes, and whatever tables the reader uploaded.

Template and photo payloads are long base64 values, so they are shortened (first 40 characters + length)
before being stored: enough to see the record layout, without keeping biometric data in a log.
Logging must never break device traffic, so every failure here is swallowed.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from sqlalchemy import text

from app.database import SessionLocal
from app.models.entities import AdmsLog

MAX_BODY_CHARS = 6000
KEEP_ROWS = 800   # newest rows kept; older ones are deleted as new ones arrive
_PRUNE_EVERY = 40

# key=<long value>: template / photo / content payloads
_LONG_VALUE = re.compile(r"((?:tmp|template|content|photo|photodata|image|base64)\s*=\s*)([^\t\r\n&]{60,})", re.IGNORECASE)


def mask(value: Optional[str]) -> str:
    if not value:
        return ""
    return _LONG_VALUE.sub(lambda m: f"{m.group(1)}{m.group(2)[:40]}...[{len(m.group(2))} chars]", value)


def record(serial: str, direction: str, kind: str, query: Optional[str] = None, body: Optional[str] = None) -> None:
    """direction: 'in' (reader -> server) or 'out' (server -> reader)."""
    try:
        full = body or ""
        shown = mask(full)
        if len(shown) > MAX_BODY_CHARS:
            shown = shown[:MAX_BODY_CHARS] + f"\n...[truncated, {len(shown)} chars]"
        with SessionLocal() as s:
            row = AdmsLog(
                SerialNumber=(serial or "?")[:50], LoggedAt=datetime.utcnow(), Direction=direction[:3],
                Kind=kind[:60], Query=(query or "")[:500] or None, Body=shown or None, BodyLength=len(full),
            )
            s.add(row)
            s.commit()
            if row.AdmsLogId % _PRUNE_EVERY == 0:
                s.execute(text("DELETE FROM adms_log WHERE AdmsLogId <= (SELECT MAX(AdmsLogId) FROM adms_log) - :keep"),
                          {"keep": KEEP_ROWS})
                s.commit()
    except Exception:  # noqa: BLE001 - diagnostics only
        pass


def recent(serial: str, limit: int = 200) -> list[dict]:
    limit = max(1, min(limit, 500))
    with SessionLocal() as s:
        rows = (
            s.query(AdmsLog).filter(AdmsLog.SerialNumber == serial)
            .order_by(AdmsLog.AdmsLogId.desc()).limit(limit).all()
        )
        return [
            {"id": r.AdmsLogId, "at": r.LoggedAt.isoformat(timespec="seconds") + "Z", "direction": r.Direction,
             "kind": r.Kind, "query": r.Query or "", "body": r.Body or "", "length": r.BodyLength}
            for r in rows
        ]
