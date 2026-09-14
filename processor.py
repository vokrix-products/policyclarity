"""PolicyClarity processor.

    process_file(file_bytes: bytes) -> list[dict]

Extraction order: PDF -> Excel -> UTF-8 text/CSV fallback.
DeepSeek is used when DEEPSEEK_API_KEY is set, else rules.
Every record has: title, status, details, due_date.
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
import urllib.request
from datetime import date, datetime, timedelta, timezone

try:
    from pypdf import PdfReader
except Exception:
    try:
        from PyPDF2 import PdfReader
    except Exception:
        PdfReader = None

try:
    import openpyxl
except Exception:
    openpyxl = None

try:
    import xlrd
except Exception:
    xlrd = None

DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"

FIELD_ALIASES = {
    "title": ["title", "policy", "policy name", "policyholder", "insured",
              "named insured", "company", "carrier"],
    "policy_number": ["policy number", "policy no", "policy #", "policyno",
                      "policy_number", "certificate number", "cert no"],
    "insurer": ["insurer", "carrier", "insurance company", "company",
                "issuer", "underwriter"],
    "insured": ["insured", "named insured", "policyholder",
                "certificate holder", "policy holder"],
    "coverage_type": ["coverage", "coverage type", "type of insurance",
                      "line of business", "lob"],
    "effective_date": ["effective date", "eff date", "effective", "start date",
                       "period start", "from"],
    "expiration_date": ["expiration date", "expiry", "exp date", "expiry date",
                        "end date", "period end", "to", "due date", "due_date",
                        "renewal date"],
    "limits": ["limits", "limit", "coverage limit", "policy limit",
               "aggregate", "amount"],
    "premium": ["premium", "annual premium", "annualized premium", "cost"],
    "status": ["status", "policy status", "state"],
    "details": ["details", "notes", "description", "remarks"],
}

DATE_FORMATS = [
    "%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%d/%m/%Y", "%d-%m-%Y",
    "%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y", "%Y/%m/%d",
    "%m-%d-%Y", "%m.%d.%Y", "%Y.%m.%d",
]

# The statuses the dashboard renders (badge colour + status filter option).
# Longest-first so that "PENDING RENEWAL QUOTE" is preferred over "PENDING".
CANONICAL_STATUSES = (
    "EXPIRING SOON",
    "PENDING RENEWAL QUOTE",
    "PENDING VERIFICATION",
    "EXPIRED",
    "PENDING",
    "VALID",
    "ACTIVE",
)

# Fields lifted into the structured details object, in display order.
DETAIL_LABELS = (
    ("insurer", "Insurer"),
    ("insured", "Insured"),
    ("policy_number", "Policy #"),
    ("coverage_type", "Coverage"),
    ("effective_date", "Effective"),
    ("expiration_date", "Expiration"),
    ("limits", "Limits"),
    ("premium", "Premium"),
)


def _decode_bytes(file_bytes):
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return file_bytes.decode(enc)
        except Exception:
            continue
    return file_bytes.decode("utf-8", errors="replace")


def _looks_like_pdf(b):
    return b[:5] == b"%PDF-"


def _looks_like_zip(b):
    return b[:2] == b"PK"


def _looks_like_xls(b):
    return b[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


def _extract_pdf_text(file_bytes):
    if PdfReader is None:
        return ""
    try:
        reader = PdfReader(io.BytesIO(file_bytes))
        chunks = []
        for page in reader.pages:
            try:
                chunks.append(page.extract_text() or "")
            except Exception:
                continue
        return "\n".join(chunks).strip()
    except Exception:
        return ""


def _extract_xlsx_text(file_bytes):
    if openpyxl is None:
        return ""
    try:
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True,
                                    data_only=True)
    except Exception:
        return ""
    lines = []
    try:
        for ws in wb.worksheets:
            lines.append("# Sheet: %s" % ws.title)
            for row in ws.iter_rows(values_only=True):
                cells = ["" if c is None else str(c) for c in row]
                if any(c.strip() for c in cells):
                    lines.append(" | ".join(cells).strip())
    finally:
        try:
            wb.close()
        except Exception:
            pass
    return "\n".join(lines).strip()


def _extract_xls_text(file_bytes):
    if xlrd is None:
        return ""
    try:
        book = xlrd.open_workbook(file_contents=file_bytes)
    except Exception:
        return ""
    lines = []
    for sheet in book.sheets():
        lines.append("# Sheet: %s" % sheet.name)
        for r in range(sheet.nrows):
            cells = ["" if v is None else str(v) for v in sheet.row_values(r)]
            if any(c.strip() for c in cells):
                lines.append(" | ".join(cells).strip())
    return "\n".join(lines).strip()


def _extract_raw_text(file_bytes):
    if not file_bytes:
        return ""
    if _looks_like_pdf(file_bytes):
        text = _extract_pdf_text(file_bytes)
        if text:
            return text
    if _looks_like_zip(file_bytes):
        text = _extract_xlsx_text(file_bytes)
        if text:
            return text
    if _looks_like_xls(file_bytes):
        text = _extract_xls_text(file_bytes)
        if text:
            return text
    # Last-resort fallback for bytes whose magic number we did not recognise.
    # pypdf is deliberately NOT retried here: on non-PDF bytes it logs
    # "invalid pdf header" and "EOF marker not found" to stderr on every
    # upload, which is what filled the poller logs.
    text = _extract_xlsx_text(file_bytes)
    if text:
        return text
    return _decode_bytes(file_bytes)


def _parse_date(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    cleaned = re.sub(r"(?<=\d)(st|nd|rd|th)\b", "", text, flags=re.I).strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt).date()
        except Exception:
            continue
    try:
        serial = float(cleaned)
        if 20000 < serial < 80000:
            return (datetime(1899, 12, 30) + timedelta(days=serial)).date()
    except Exception:
        pass
    return None


def _iso(value):
    d = _parse_date(value)
    return d.isoformat() if d else ""


def _split_lines(text):
    return [ln.strip() for ln in text.replace("\r\n", "\n").split("\n")
            if ln.strip()]


def _detect_delimiter(head):
    best, best_count = ",", 0
    for delim in (",", ";", "\t", "|"):
        c = head.count(delim)
        if c > best_count:
            best, best_count = delim, c
    return best


def _is_delimited(text):
    lines = _split_lines(text)
    if not lines:
        return False
    return _detect_delimiter(lines[0]) in (",", ";", "\t", "|") and \
        max(lines[0].count(d) for d in (",", ";", "\t", "|")) >= 1


def _synth_status(expiration_iso):
    d = _parse_date(expiration_iso)
    if d is None:
        return "ACTIVE"
    today = datetime.now(timezone.utc).date()
    if d < today:
        return "EXPIRED"
    if d <= today + timedelta(days=30):
        return "EXPIRING SOON"
    return "VALID"


def _canonical_status(raw_status, expiration_iso):
    """Clamp a free-form status onto the set the dashboard can render.

    The model returns sentences such as "EXPIRED - RENEWAL PENDING UNDERWRITING
    REVIEW", which map to no badge colour and no filter option. Keep the
    leading token when it is one we know, else fall back to the due date.
    """
    text = str(raw_status or "").strip().upper()
    text = text.replace("\u2014", "-").replace("\u2013", "-")
    text = re.sub(r"\s+", " ", text).strip()
    if text.endswith("."):
        text = text[:-1].strip()
    for status in CANONICAL_STATUSES:
        if text == status or text.startswith(status + " ") or \
                text.startswith(status + "-"):
            return status
    return _synth_status(expiration_iso)


def _norm_key(key):
    return re.sub(r"[^a-z0-9]+", " ", str(key).strip().lower()).strip()


def _match_field(field, key):
    nk = _norm_key(key)
    for alias in FIELD_ALIASES.get(field, []):
        na = _norm_key(alias)
        if nk == na or (len(na) > 3 and na in nk) or (len(nk) > 3 and nk in na):
            return True
    return False


def _row_to_record(row):
    extras = {}
    out = {"title": "", "status": "", "details": ""}
    for key, value in row.items():
        if key is None:
            continue
        val = "" if value is None else str(value).strip()
        matched = False
        for field in ("title", "policy_number", "insurer", "insured",
                      "coverage_type", "effective_date", "expiration_date",
                      "limits", "premium", "status", "details"):
            if _match_field(field, key):
                if field in ("effective_date", "expiration_date"):
                    extras[field] = _iso(val) or val
                elif field in ("title", "status", "details"):
                    if not out.get(field):
                        out[field] = val
                else:
                    extras[field] = val
                matched = True
                break
        if not matched:
            flat = _norm_key(key).replace(" ", "_") or "field"
            extras[flat] = val

    title = out.get("title") or ""
    if not title:
        title = (extras.get("insured") or extras.get("insurer")
                 or extras.get("policy_number") or "Insurance Policy")

    due_date = _iso(extras.get("expiration_date", ""))
    status = out.get("status") or _synth_status(due_date)

    # Only the raw notes column rides along as prose. The individual fields are
    # assembled into the structured details object by _normalize_record.
    rec = dict(extras)
    rec.update({
        "title": title.strip(),
        "status": status.strip(),
        "details": (out.get("details") or "").strip(),
        "due_date": due_date,
    })
    return rec


def _csv_to_records(text):
    lines = _split_lines(text)
    if not lines:
        return []
    delim = _detect_delimiter(lines[0])
    reader = csv.DictReader(io.StringIO("\n".join(lines)), delimiter=delim)
    records = []
    for row in reader:
        if not any((v or "").strip() for v in row.values() if v is not None):
            continue
        records.append(_row_to_record(row))
    return records


def _key_value_to_records(text):
    lines = _split_lines(text)
    if not lines:
        return []
    blocks = []
    current = {}
    for ln in lines:
        if "|" in ln and ":" not in ln:
            parts = [p.strip() for p in ln.split("|")]
            if len(parts) == 2:
                current[parts[0]] = parts[1]
                continue
        if "=" in ln and ":" not in ln:
            k, _, v = ln.partition("=")
            if k.strip():
                current[k.strip()] = v.strip()
                continue
        k, _, v = ln.partition(":")
        k, v = k.strip(), v.strip()
        if k and v:
            current[k] = v
    if current:
        blocks.append(current)
    if not blocks:
        return []
    return [_row_to_record(b) for b in blocks]


def _rule_extract(raw_text):
    if not raw_text.strip():
        return []
    lines = raw_text.splitlines()
    if lines and _is_delimited(lines[0]):
        records = _csv_to_records(raw_text)
        if records:
            return records
    if _is_delimited(raw_text):
        records = _csv_to_records(raw_text)
        if records:
            return records
    records = _key_value_to_records(raw_text)
    if records and any(r.get("title") for r in records):
        return records
    first = _split_lines(raw_text)
    title = first[0][:120] if first else "Insurance Policy"
    dates = re.findall(r"\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4}",
                       raw_text)
    due = ""
    for d in reversed(dates):
        iso = _iso(d)
        if iso:
            due = iso
            break
    return [{
        "title": title,
        "status": _synth_status(due),
        "details": raw_text.strip()[:1000],
        "due_date": due,
    }]


DEEPSEEK_SYSTEM = (
    "You extract insurance policy / certificate of insurance (COI) data. "
    "Return STRICT JSON: {\"records\": [ {\"title\": str, \"status\": str, "
    "\"details\": str, \"due_date\": str, \"policy_number\": str, "
    "\"insurer\": str, \"insured\": str, \"coverage_type\": str, "
    "\"effective_date\": str, \"expiration_date\": str, \"limits\": str, "
    "\"premium\": str} ]}. due_date must be an ISO date (YYYY-MM-DD) or "
    "empty string. title must be non-empty. status must be one of "
    "VALID, ACTIVE, EXPIRING SOON, PENDING, PENDING VERIFICATION, "
    "PENDING RENEWAL QUOTE, EXPIRED. Output JSON only."
)


def _deepseek_extract(raw_text):
    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not key or not raw_text.strip():
        return None
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": DEEPSEEK_SYSTEM},
            {"role": "user", "content": raw_text[:12000]},
        ],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    req = urllib.request.Request(
        DEEPSEEK_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": "Bearer %s" % key,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None
    try:
        content = body["choices"][0]["message"]["content"]
        parsed = json.loads(content)
    except Exception:
        return None
    records = parsed.get("records") if isinstance(parsed, dict) else None
    if not isinstance(records, list):
        return None
    out = []
    for rec in records:
        if not isinstance(rec, dict):
            continue
        # Left un-normalised on purpose: process_file normalises every record
        # exactly once, and normalising twice re-wrapped the details object.
        out.append(rec)
    return out or None


def _detail_fields(values):
    """Only the structured fields we actually managed to extract."""
    fields = {}
    for key, label in DETAIL_LABELS:
        value = values.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            fields[label] = text
    return fields


def _build_details(raw_record, stringified):
    """Build records.details as a flat object.

    Idempotent: if details is already an object (the record was normalised
    earlier in the pipeline) it is passed through unchanged.
    """
    existing = raw_record.get("details")
    if isinstance(existing, dict):
        carried = {}
        for key, value in existing.items():
            text = "" if value is None else str(value).strip()
            if text:
                carried[str(key)] = text
        return carried or {"Summary": "No additional details extracted."}

    details = {}
    prose = stringified.get("details", "").strip()
    if prose:
        details["Summary"] = prose
    details.update(_detail_fields(stringified))
    if not details:
        details["Summary"] = "No additional details extracted."
    return details


def _normalize_record(rec):
    out = {}
    for k, v in rec.items():
        if isinstance(v, (dict, list)):
            out[str(k)] = json.dumps(v)
        else:
            out[str(k)] = "" if v is None else str(v)
    title = out.get("title", "").strip() or "Insurance Policy"
    due = _iso(out.get("due_date") or out.get("expiration_date") or "")
    status = _canonical_status(out.get("status"), due)
    out.update({
        "title": title,
        "status": status,
        "details": _build_details(rec, out),
        # None rather than "": the column is a date, and an empty string is not
        # a valid date literal.
        "due_date": due or None,
    })
    return out


def process_file(file_bytes):
    """Extract policy/COI records from raw file bytes."""
    if file_bytes is None:
        return []
    if isinstance(file_bytes, str):
        file_bytes = file_bytes.encode("utf-8")
    if not isinstance(file_bytes, (bytes, bytearray)):
        return []
    file_bytes = bytes(file_bytes)

    raw = ""
    try:
        raw = _extract_raw_text(file_bytes)
    except Exception:
        raw = ""

    records = None
    if os.environ.get("DEEPSEEK_API_KEY", "").strip():
        try:
            records = _deepseek_extract(raw)
        except Exception:
            records = None

    if not records:
        try:
            records = _rule_extract(raw)
        except Exception:
            records = []

    cleaned = []
    for rec in records or []:
        if not isinstance(rec, dict):
            continue
        merged = _normalize_record(rec)
        if not merged.get("title"):
            merged["title"] = "Insurance Policy"
        cleaned.append(merged)
    return cleaned
