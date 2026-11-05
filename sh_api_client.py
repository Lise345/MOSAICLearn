"""Read-only Superhuman Docs page HTML API client (standard v1, NOT admin/v1)."""
from __future__ import annotations
import re
import time
import threading
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse, quote
import requests

BASE = "https://coda.io/apis/v1"


def doc_id_from_url_or_id(value: str) -> str:
    value = value.strip()
    m = re.search(r"_d([A-Za-z0-9_-]+)(?=[/?#]|$)", value)
    if m: return m.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]+", value): return value
    raise ValueError("Enter a Superhuman Docs document URL containing '_d...' or the document ID")


# Coda has a particularly strict write/content-write allowance. Export uses
# POST even though the exported content is read-only. Pace export requests
# across threads, imports and preview calls within this Python process.
_EXPORT_POST_MIN_INTERVAL_SECONDS = 3.7
_POST_LOCK = threading.Lock()
_NEXT_POST_AT = 0.0


def _pace_export_post(url: str) -> None:
    global _NEXT_POST_AT
    if not url.rstrip("/").endswith("/export"):
        return
    with _POST_LOCK:
        now = time.monotonic()
        wait = max(0.0, _NEXT_POST_AT - now)
        if wait:
            time.sleep(wait)
        _NEXT_POST_AT = time.monotonic() + _EXPORT_POST_MIN_INTERVAL_SECONDS


def _retry_after_seconds(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except (ValueError, TypeError):
        try:
            delta = (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds()
            return max(0.0, delta)
        except (ValueError, TypeError, OverflowError):
            return None


def _request(method: str, url: str, token: str, **kwargs) -> requests.Response:
    # Retry only transient 429 / 5xx responses. Do not retry authentication,
    # permission errors or invalid document IDs.
    for attempt in range(5):
        if method.upper() == "POST":
            _pace_export_post(url)
        response = requests.request(method, url, headers={
            "Authorization": f"Bearer {token}", "Accept": "application/json",
        }, timeout=25, **kwargs)
        if response.ok:
            return response
        if (response.status_code == 429 or response.status_code in {500, 502, 503, 504}) and attempt < 4:
            retry_after = _retry_after_seconds(response.headers.get("Retry-After"))
            backoff = min(60.0, 2.0 * (2 ** attempt))
            time.sleep(min(90.0, retry_after if retry_after is not None else backoff))
            continue
        msg = {401: "Token rejected (401)", 403: "Permission denied for this document (403)",
               404: "Document or page not found (404)", 429: "API rate limit (429) even after retries"}.get(
                   response.status_code, f"HTTP {response.status_code}")
        raise RuntimeError(msg + ": " + response.text[:350])
    raise RuntimeError("API request failed after retry budget")


def list_pages(doc_id: str, token: str) -> list[dict]:
    """Return all pages, including pages under modules, following pagination."""
    url = f"{BASE}/docs/{quote(doc_id, safe='')}/pages"
    pages, page_token = [], None
    for _ in range(100):
        params = {"limit": 100}
        if page_token: params["pageToken"] = page_token
        payload = _request("GET", url, token, params=params).json()
        pages.extend(payload.get("items") or [])
        page_token = payload.get("nextPageToken")
        if not page_token: return pages
    raise RuntimeError("Too many page list batches; export a smaller document")


def export_page_html(doc_id: str, page_id: str, token: str) -> str:
    doc, page = quote(doc_id, safe=""), quote(page_id, safe="")
    endpoint = f"{BASE}/docs/{doc}/pages/{page}/export"
    payload = _request("POST", endpoint, token, json={"outputFormat":"html"}).json()
    request_id = payload.get("id")
    if not request_id: raise RuntimeError(f"Export did not return request ID: {payload}")
    status_url = f"{endpoint}/{quote(request_id,safe='')}"
    for _ in range(18):
        status = _request("GET", status_url, token).json()
        state = str(status.get("status", "")).lower()
        link = status.get("downloadLink")
        if state in {"complete", "completed"} and link:
            parsed = urlparse(link)
            if parsed.scheme != "https" or not parsed.hostname:
                raise RuntimeError("Unexpected download URL scheme/host")
            # URL is returned by the trusted Coda API; refuse local/private endpoints.
            host = parsed.hostname.lower()
            allowed = ("coda.io", "superhuman.com", "amazonaws.com", "cloudfront.net")
            if not any(host == root or host.endswith("." + root) for root in allowed):
                raise RuntimeError(f"Unrecognized export download host: {host}")
            download = requests.get(link, timeout=30, allow_redirects=False)
            if not download.ok: raise RuntimeError(f"Download HTTP {download.status_code}")
            return download.content.decode("utf-8-sig", errors="replace")
        if state in {"failed", "error", "cancelled"}:
            raise RuntimeError(status.get("error") or f"Export {state}")
        time.sleep(1.5)
    raise TimeoutError("Export still processing; retry the export request later")


def list_tables(doc_id: str, token: str) -> list[dict]:
    """List accessible tables and views. Read only; follows pagination."""
    url = f"{BASE}/docs/{quote(doc_id, safe='')}/tables"
    tables, page_token = [], None
    for _ in range(100):
        params = {"limit": 100}
        if page_token:
            params["pageToken"] = page_token
        payload = _request("GET", url, token, params=params).json()
        tables.extend(payload.get("items") or [])
        page_token = payload.get("nextPageToken")
        if not page_token:
            return tables
    raise RuntimeError("Too many table batches; narrow the document")


def list_table_rows(doc_id: str, table_id: str, token: str) -> list[dict]:
    """Fetch row IDs, browser links and display names for library cross-checking.

    Does not import or change tables. The canonical row's other columns remain
    in Superhuman Docs; they are not duplicated in lesson JSON.
    """
    url = f"{BASE}/docs/{quote(doc_id, safe='')}/tables/{quote(table_id, safe='')}/rows"
    rows, page_token = [], None
    for _ in range(100):
        params = {"limit": 100, "valueFormat": "simple"}
        if page_token:
            params["pageToken"] = page_token
        payload = _request("GET", url, token, params=params).json()
        rows.extend({"id": r.get("id", ""), "name": r.get("name", ""),
                     "browserLink": r.get("browserLink", "")}
                    for r in payload.get("items") or [])
        page_token = payload.get("nextPageToken")
        if not page_token:
            return rows
    raise RuntimeError("Too many table rows; check table filters")


def enrich_page_hierarchy(doc_id: str, pages: list[dict], token: str, *, max_lookups: int = 50) -> tuple[list[dict], list[str]]:
    """Confirm sidebar order using GET /pages/{id} for ambiguous parents.

    The list endpoint can omit/partially provide `children` on some responses.
    Only during an explicit editor import, check those parents with multiple
    listed children. No extra calls are made during normal learner visits.
    """
    by_id = {str(p.get("id")): dict(p) for p in pages if p.get("id")}
    raw_children: dict[str, list[str]] = {}
    for page in pages:
        parent = page.get("parent")
        pid = str(parent.get("id") if isinstance(parent, dict) else parent or "")
        if pid in by_id:
            raw_children.setdefault(pid, []).append(str(page["id"]))
    candidates = []
    for pid, listed in raw_children.items():
        direct_refs = {
            str(ref.get("id") if isinstance(ref, dict) else ref)
            for ref in by_id[pid].get("children") or []
        }
        if len(listed) > 1 and not set(listed).issubset(direct_refs):
            candidates.append(pid)
    # Always check an apparent module when one of its child phase names has
    # contradictory parent metadata; a freshly moved page may be stale.
    phase_names = {"discover", "understand", "apply", "convince", "share", "communicate", "communication"}
    for page in pages:
        if str(page.get("name") or "").strip().casefold() not in phase_names:
            continue
        parent = page.get("parent")
        parent_id = str(parent.get("id") if isinstance(parent, dict) else parent or "")
        if parent_id not in by_id:
            continue
        # A named phase nested directly below another named phase is suspicious.
        if str(by_id[parent_id].get("name") or "").strip().casefold() in phase_names:
            grandparent = by_id[parent_id].get("parent")
            module_id = str(grandparent.get("id") if isinstance(grandparent, dict) else grandparent or "")
            if module_id in by_id and module_id not in candidates:
                candidates.append(module_id)
    warnings = []
    if len(candidates) > max_lookups:
        warnings.append(f"More than {max_lookups} ambiguous page groups; only the first {max_lookups} were verified")
    for page_id in candidates[:max_lookups]:
        try:
            endpoint = f"{BASE}/docs/{quote(doc_id, safe='')}/pages/{quote(page_id, safe='')}"
            latest = _request("GET", endpoint, token).json()
            if "children" in latest and isinstance(latest["children"], list):
                by_id[page_id]["children"] = latest["children"]
            else:
                warnings.append(f"No explicit child order returned for {by_id[page_id].get('name') or page_id}")
        except Exception as ex:
            warnings.append(f"Could not verify page order for {by_id[page_id].get('name') or page_id}: {str(ex)[:110]}")
    return [by_id[str(p["id"])] for p in pages if p.get("id")], warnings
