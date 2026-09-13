"""PolicyClarity poller worker for Railway.

Each cycle:
    1. asks Supabase for rows in SOURCE_TABLE that are not processed yet
    2. downloads the referenced file from Supabase Storage
    3. runs process_file() over the raw bytes
    4. inserts normalized records into TARGET_TABLE
    5. flags the source row as processed (recording errors)
"""

from __future__ import annotations

import os
import signal
import time
import traceback
from typing import Any, Dict, List, Optional

import requests

from processor import process_file

_STOP = False


def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    value = os.environ.get(name)
    if value is None or not value.strip():
        return default
    return value.strip()


SUPABASE_URL = (_env("SUPABASE_URL") or "").rstrip("/")
SUPABASE_KEY = _env("SUPABASE_KEY") or _env("SUPABASE_SERVICE_KEY") or ""
SOURCE_TABLE = _env("SOURCE_TABLE", "documents")
TARGET_TABLE = _env("TARGET_TABLE", "policy_records")
STORAGE_BUCKET = _env("STORAGE_BUCKET", "policies")
POLL_INTERVAL = float(_env("POLL_INTERVAL", "60") or "60")
BATCH_SIZE = int(_env("BATCH_SIZE", "10") or "10")


def _log(message: str) -> None:
    print("[policyclarity] %s" % message, flush=True)


def _headers(extra=None):
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": "Bearer %s" % SUPABASE_KEY,
        "Content-Type": "application/json",
    }
    if extra:
        headers.update(extra)
    return headers


def _table_url(table: str) -> str:
    return "%s/rest/v1/%s" % (SUPABASE_URL, table)


def _fetch_pending():
    params = {
        "processed": "eq.false",
        "select": "*",
        "limit": str(BATCH_SIZE),
        "order": "created_at.asc",
    }
    response = requests.get(
        _table_url(SOURCE_TABLE), headers=_headers(), params=params, timeout=30
    )
    response.raise_for_status()
    rows = response.json()
    return rows if isinstance(rows, list) else []


def _download_file(row):
    path = (
        row.get("storage_path")
        or row.get("file_path")
        or row.get("path")
        or row.get("filename")
    )
    if not path:
        return None
    url = "%s/storage/v1/object/%s/%s" % (
        SUPABASE_URL,
        STORAGE_BUCKET,
        str(path).lstrip("/"),
    )
    response = requests.get(url, headers=_headers(), timeout=60)
    response.raise_for_status()
    return response.content


def _insert_records(records, row):
    if not records:
        return 0
    payload = []
    for record in records:
        payload.append(
            {
                "source_id": row.get("id"),
                "source_path": row.get("storage_path")
                or row.get("file_path")
                or row.get("path"),
                "title": record.get("title"),
                "status": record.get("status"),
                "details": record.get("details") or {},
                "due_date": record.get("due_date"),
            }
        )
    response = requests.post(
        _table_url(TARGET_TABLE),
        headers=_headers({"Prefer": "return=minimal"}),
        json=payload,
        timeout=30,
    )
    response.raise_for_status()
    return len(payload)


def _mark_processed(row, error=None):
    body = {"processed": True, "error": error}
    response = requests.patch(
        _table_url(SOURCE_TABLE),
        headers=_headers({"Prefer": "return=minimal"}),
        params={"id": "eq.%s" % row.get("id")},
        json=body,
        timeout=30,
    )
    response.raise_for_status()


def run_once() -> int:
    if not SUPABASE_URL or not SUPABASE_KEY:
        _log("SUPABASE_URL and SUPABASE_KEY are required")
        return 0
    try:
        rows = _fetch_pending()
    except Exception as exc:
        _log("fetch failed: %s" % exc)
        return 0
    if not rows:
        return 0

    written = 0
    for row in rows:
        try:
            data = _download_file(row)
            if not data:
                _mark_processed(row, "no file found for row")
                continue
            records = process_file(data)
            written += _insert_records(records, row)
            _mark_processed(row, None)
            _log("row %s -> %d records" % (row.get("id"), len(records)))
        except Exception as exc:
            _log("row %s failed: %s" % (row.get("id"), exc))
            traceback.print_exc()
            try:
                _mark_processed(row, str(exc)[:500])
            except Exception:
                pass
    return written
