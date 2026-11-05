"""Manual Superhuman Docs -> MOSAIC Learn staging adapter.

Never performs DB writes or runs during learner-page rendering. Page IDs, not
mutable titles, are used as durable keys. Always review before saving drafts.
"""
from __future__ import annotations

import hashlib
import html as html_lib
import re
from urllib.parse import urlparse, unquote

from bs4 import BeautifulSoup
from sh_api_client import export_page_html, list_pages, list_table_rows, list_tables, _request
from sh_parser import parse_units

BLOCK_NAMES = {"discover": "Understand", "understand": "Understand", "apply": "Apply", "convince": "Convince", "share": "Convince", "communicate": "Convince", "communication": "Convince"}
RESOURCE_COLUMNS = {
    "title": ("title", "resource name", "name"),
    "resource_type": ("resource type", "type"),
    "authors": ("authors / creators", "authors", "author", "creator"),
    "year": ("publication year", "year"),
    "description": ("short description", "description", "summary"),
    "detailed_description": ("detailed description",),
    "useful_for": ("useful for",),
    "target_audience": ("target audience", "target users"),
    "publication_url": ("doi / zenodo link", "doi", "zenodo link", "main url", "main link"),
    "source_page_url": ("main url", "main link", "record url"),
    "download_url": ("download url", "file url", "pdf url"),
    "license": ("license",),
    "language": ("language",),
    "keywords": ("keywords", "tags"),
}
TOOL_COLUMNS = {
    "title": ("title", "tool name", "name"),
    "format": ("tool type", "type", "format"),
    "developer": ("developer / owner", "developer", "owner"),
    "description": ("short description", "description"),
    "purpose": ("purpose / useful for", "purpose", "useful for"),
    "target_users": ("target users", "target audience"),
    "steps": ("how to use", "steps"),
    "inputs": ("required inputs",),
    "outputs": ("expected outputs",),
    "policy_relevance": ("policy relevance",),
    "duration": ("time required", "duration"),
    "requirements": ("technical requirements",),
    "website_url": ("access link", "main url", "url"),
    "access_conditions": ("access conditions",),
    "license": ("license",),
    "version": ("version / update date", "version"),
    "supporting_materials": ("supporting materials",),
    "keywords": ("keywords",),
}


def stable_id(prefix: str, doc_id: str, item_id: str) -> str:
    """Immutable slug. Source ID changes only if the page/row is recreated."""
    key = f"{doc_id}:{item_id}"
    return f"sh-{prefix}-{hashlib.sha256(key.encode()).hexdigest()[:20]}"


def _parent_id(page: dict) -> str:
    parent = page.get("parent")
    return str(parent.get("id", "") if isinstance(parent, dict) else parent or "")


def _explicit_children(page: dict) -> list[str]:
    """Ordered child IDs exposed by the Superhuman Docs Pages API."""
    result = []
    for child in page.get("children") or []:
        cid = str(child.get("id") if isinstance(child, dict) else child or "")
        if cid and cid not in result:
            result.append(cid)
    return result


def _ordered_page_hierarchy(pages: list[dict]) -> tuple[dict, dict, dict]:
    """Construct one coherent tree, preferring a parent's explicit children.

    Occasionally list-page responses and individual parent references can
    disagree (for example after a page is moved/renamed). Explicit ordered
    children are authoritative: a phase page listed as a direct module child
    must not also be treated as a Discover lesson. A page is assigned exactly
    one parent and appears exactly once.
    """
    by_id = {str(p.get("id")): p for p in pages if p.get("id")}
    inferred_parent = {pid: _parent_id(page) for pid, page in by_id.items()}
    for parent_id, page in by_id.items():
        for child_id in _explicit_children(page):
            if child_id in by_id and child_id != parent_id:
                inferred_parent[child_id] = parent_id
    groups: dict[str, list[dict]] = {}
    for pid, page in by_id.items():
        parent_id = inferred_parent.get(pid, "")
        if parent_id != pid:
            groups.setdefault(parent_id, []).append(page)
    api_order = {pid: pos for pos, pid in enumerate(by_id)}
    for parent_id, siblings in groups.items():
        refs = _explicit_children(by_id.get(parent_id, {}))
        ranking = {cid: idx for idx, cid in enumerate(refs)}
        siblings.sort(key=lambda p: (
            ranking.get(str(p["id"]), len(refs) + api_order[str(p["id"])]),
            api_order[str(p["id"])],
        ))
    return by_id, inferred_parent, groups


def page_tree(pages: list[dict], root_id: str) -> list[dict]:
    """Return modules and classes in actual sidebar order and hierarchy.

    The internal Convince level supports legacy bookmarks; page names Share
    and Communicate are equivalent aliases of that level. Phase pages never
    become lessons themselves, even after a rename.
    """
    by_id, parent_of, children = _ordered_page_hierarchy(pages)
    if root_id not in by_id:
        raise ValueError("Learning-environment page is not in the selected document")
    modules = []
    for page in children.get(root_id, []):
        if str(page.get("name", "")).strip().casefold() in {
            "resources", "tools", "house of tools", "our story", "unit templates", "units_template", "glossary"
        }:
            continue
        module_id = str(page["id"])
        lessons = []
        block_pages = []
        seen_lesson_ids = set()
        direct_children = list(children.get(module_id, []))
        # A renamed/moved phase can temporarily appear as a child of another
        # phase when Coda's parent metadata is stale and no ordered parent
        # reference was returned. A reserved phase title is never a lesson.
        nested_phases = []
        for phase in direct_children:
            if str(phase.get("name") or "").strip().casefold() not in BLOCK_NAMES:
                continue
            nested_phases.extend(
                grandchild for grandchild in children.get(str(phase["id"]), [])
                if str(grandchild.get("name") or "").strip().casefold() in BLOCK_NAMES
            )
        direct_ids = {str(child["id"]) for child in direct_children}
        direct_children.extend(phase for phase in nested_phases if str(phase["id"]) not in direct_ids)
        for child in direct_children:
            child_id = str(child["id"])
            name = str(child.get("name", "")).strip()
            block = BLOCK_NAMES.get(name.casefold())
            if block:
                block_pages.append({"page": child, "level": block})
                for lesson in children.get(child_id, []):
                    if str(lesson.get("name") or "").strip().casefold() in BLOCK_NAMES:
                        continue  # This is another phase, not a Discover/Apply class.
                    lid = str(lesson["id"])
                    if lid not in seen_lesson_ids:
                        lessons.append({"page": lesson, "level": block, "block_page": child})
                        seen_lesson_ids.add(lid)
            else:
                level = next((v for k, v in BLOCK_NAMES.items()
                              if name.casefold().startswith(k + " -")), "Understand")
                if child_id not in seen_lesson_ids:
                    lessons.append({"page": child, "level": level, "block_page": None})
                    seen_lesson_ids.add(child_id)
        modules.append({"page": page, "lessons": lessons, "block_pages": block_pages})
    return modules


def unverified_sibling_order(pages: list[dict], root_id: str) -> list[str]:
    """Warn only where sibling order truly lacks an ordered children list."""
    by_id, _parents, groups = _ordered_page_hierarchy(pages)
    visited = set()
    queue = [root_id]
    uncertain = []
    while queue:
        page_id = queue.pop(0)
        if page_id in visited:
            continue
        visited.add(page_id)
        child_pages = groups.get(page_id) or []
        references = set(_explicit_children(by_id.get(page_id, {})))
        # A partial child list also leaves some siblings unordered.
        if len(child_pages) > 1 and any(str(child["id"]) not in references for child in child_pages):
            uncertain.append(str(by_id.get(page_id, {}).get("name") or page_id))
        queue.extend(str(child["id"]) for child in child_pages)
    return uncertain


def page_intro_and_objectives(exported_html: str) -> tuple[str, list[str]]:
    soup = BeautifulSoup(exported_html, "html.parser")
    h = soup.find(lambda x: getattr(x, "name", "") in {"h2", "h3"} and
                  x.get_text(" ", strip=True).casefold() in {"what you will learn", "learning objectives", "objectives"})
    objectives = []
    if h:
        for e in h.next_elements:
            if getattr(e, "name", "") in {"h2", "h3"}:
                break
            if getattr(e, "name", "") not in {"li", "div", "p"}:
                continue
            # Check only leaf paragraph nodes, so lists aren't repeated.
            if e.find(["div", "p", "li"]):
                continue
            value = re.sub(r"^[\s·•\-]+", "", e.get_text(" ", strip=True)).strip()
            if 5 <= len(value) <= 220 and value not in objectives:
                objectives.append(value)
            if len(objectives) >= 5:
                break
    intro = []
    start = soup.find(["h1", "h2", "h3"])
    elements = list(start.next_elements) if start else list(soup.descendants)
    for e in elements:
        if getattr(e, "name", "") in {"h2", "h3"}:
            break
        if getattr(e, "name", "") not in {"div", "p"} or e.find(["div", "p", "li", "table"]):
            continue
        value = e.get_text(" ", strip=True)
        if value and len(value) > 20:
            intro.append(value)
    if not intro:
        # A heading-3 starting lesson is not a landing-page intro.
        intro = []
    return " ".join(intro)[:1200], objectives


def _escape(text: str) -> str:
    return html_lib.escape(str(text or ""), quote=True)


def _safe_link(value: str) -> str:
    u = urlparse(str(value or ""))
    return value if u.scheme == "https" and u.hostname else ""


def _page_cover_url(page: dict) -> str:
    image = page.get("image") or {}
    return _safe_link(str(image.get("browserLink") or "")) if isinstance(image, dict) else ""


def first_module_figure_url(exported_html: str) -> str:
    """First figure embedded on *this module page* (not on any subpage).

    Superhuman Docs HTML exports may include small icons. Ignore only clearly
    icon-sized images when exported dimensions are available. Preserve the
    document order and accept only HTTPS image URLs. No remote fetch here.
    """
    if not exported_html:
        return ""
    soup = BeautifulSoup(exported_html, "html.parser")
    for figure in soup.find_all("img"):
        # A displayed Coda table can contain row thumbnails; it is not a
        # module's editorial figure and should not become its cover.
        if figure.find_parent("table") is not None:
            continue
        # Some exports emit a lazy image URL rather than an ordinary src.
        # Prefer the actual rendered src; fall back to alternative source
        # attributes only when the rendered src is missing.
        candidates = [figure.get("src"), figure.get("data-src"),
                      figure.get("data-original"), figure.get("data-coda-src")]
        for attr in ("srcset", "data-srcset"):
            srcset = str(figure.get(attr) or "")
            if srcset:
                candidates.extend(part.strip().split()[0] for part in srcset.split(",") if part.strip())
        url = next((_safe_link(str(raw or "")) for raw in candidates
                    if _safe_link(str(raw or ""))), "")
        if not url:
            continue
        def dimension(attribute: str) -> int:
            match = re.match(r"\s*(\d+)", str(figure.get(attribute) or ""))
            return int(match.group(1)) if match else 0
        width, height = dimension("width"), dimension("height")
        if (width and width < 100) or (height and height < 70):
            continue
        return url
    return ""


def _rich_html(unit: dict) -> str:
    """Safely render ordered Coda unit parts to app-allowed HTML plus safe notes/table.

    Images are handled separately by the app to keep figures below paragraphs.
    """
    pieces = []
    for part in unit.get("content_parts") or []:
        typ = part.get("type")
        if typ == "text":
            value = str(part.get("text") or "").strip()
            if not value:
                continue
            if value.startswith(("·", "•", "- ")):
                pieces.append("<p>" + _escape(value.lstrip(" ·•-")) + "</p>")
            else:
                pieces.append("<p>" + _escape(value) + "</p>")
        elif typ == "inline_note":
            title = _escape(part.get("title", ""))
            content = _escape(part.get("text", ""))
            pieces.append(f'<blockquote><strong>⚑ {title}</strong><p>{content}</p></blockquote>')
        elif typ == "table":
            rows = part.get("rows") or []
            if rows:
                # Native semantic HTML is preserved end-to-end. The first
                # exported row is the table header; keep ALL body rows and
                # their original columns (no bullet-list flattening).
                ncols = max((len(r) for r in rows), default=0)
                header = rows[0]
                head_html = "".join(
                    f'<th scope="col">{_escape(header[i] if i < len(header) else "")}</th>'
                    for i in range(ncols)
                )
                body_html = "".join(
                    "<tr>" + "".join(
                        f'<td>{_escape(row[i] if i < len(row) else "")}</td>'
                        for i in range(ncols)
                    ) + "</tr>"
                    for row in rows[1:]
                )
                table_label = _escape(unit.get("title") or "Comparison table")
                pieces.append('<div class="m-import-table-wrap">'
                              f'<table class="m-import-table" aria-label="{table_label}">'
                              f'<thead><tr>{head_html}</tr></thead><tbody>{body_html}</tbody>'
                              '</table></div>')
        elif typ == "video":
            url = _safe_link(part.get("src", ""))
            if url:
                pieces.append(f'<p><a href="{_escape(url)}">Watch the video</a></p>')
    return "".join(pieces)


def _list_items(text: str) -> list[str]:
    return [re.sub(r"^[\s·•\-]+", "", s).strip() for s in str(text or "").splitlines() if s.strip()]


def _first_nonempty(items: list[dict], typ: str) -> dict | None:
    return next((u for u in items if u.get("type") == typ), None)


def lesson_payload(doc_id: str, page: dict, level: str, parsed: dict) -> dict:
    """Map parser units to existing CMS lesson schema. Never discard questions."""
    units = parsed.get("units") or []
    lesson_id = stable_id("lesson", doc_id, str(page["id"]))
    outcome = _first_nonempty(units, "objectives")
    cards = []
    references, further, tools = [], [], []
    for idx, u in enumerate(units):
        typ = u.get("type")
        if typ in {"quiz", "reflection"}:
            continue
        if typ in {"sources", "further_reading", "tools"}:
            target = {"sources": references, "further_reading": further, "tools": tools}[typ]
            target.extend(u.get("linked_items") or [])
            continue
        if typ == "takeaways":
            continue
        if typ not in {"objectives", "text", "case_study", "image", "table", "video", "callout", "quote"}:
            continue
        card_id = f"sh-card-{idx+1:02d}-{hashlib.sha256((str(page['id'])+':'+str(idx)).encode()).hexdigest()[:8]}"
        image = next((v for v in u.get("images") or [] if _safe_link(v.get("src", ""))), None)
        cards.append({
            "title": str(u.get("title") or "Learning card"),
            "label": "Discover" if typ == "objectives" else typ.replace("_", " ").title(),
            "editor_id": card_id,
            "body_html": ("<blockquote>" + _rich_html(u) + "</blockquote>"
                          if typ in {"callout", "quote"} else _rich_html(u)),
            "image_resource_id": "", "image_src_import": image["src"] if image else "",
            "image_src_imports": [im["src"] for im in u.get("images") or [] if _safe_link(im.get("src", ""))],
            "image_resource_ids": [],
            "image_alt": str(image.get("alt") or u.get("title") or "Illustration") if image else "",
        })
    quiz = _first_nonempty(units, "quiz")
    quiz_data = quiz.get("quiz") if quiz else None
    incomplete_quiz = bool(quiz_data and (
        quiz_data.get("answer") is None or len(quiz_data.get("options") or []) < 2
        or not str(quiz_data.get("question") or "").strip()
        or not str(quiz_data.get("explanation") or "").strip()
        or any("[" in str(value) and "]" in str(value) for value in
               [quiz_data.get("question"), quiz_data.get("explanation"), *(quiz_data.get("options") or [])])
    ))
    if incomplete_quiz:
        quiz_data = None
    reflection = _first_nonempty(units, "reflection")
    takeaways = _first_nonempty(units, "takeaways")
    description = next((u.get("text_without_inline_notes") for u in units if u.get("type") == "text"), "") or ""
    payload = {
        "id": lesson_id, "title": str(page.get("name") or "Untitled class"),
        "summary": description[:230], "body": description[:1000],
        "level": level, "minutes": max(3, min(40, 3 * len(cards))),
        "theory_cards": cards,
        "takeaway": "\n".join(_list_items(takeaways.get("text", ""))) if takeaways else "",
        "prompt": (reflection or {}).get("reflection", {}).get("question", ""),
        "reflection_example": (reflection or {}).get("reflection", {}).get("example_response", ""),
        "quiz": quiz_data, "_incomplete_quiz": incomplete_quiz, "self_check": [],
        "resource_references": references, "tool_references": tools,
        "further_reading": further, "sources": [], "resource_ids": [],
        "source_doc_id": doc_id, "source_page_id": str(page["id"]),
        "source_page_url": str(page.get("browserLink") or ""),
        "source_digest": "", "source_system": "superhuman_docs",
        "learning_objectives": _list_items(outcome.get("text", "")) if outcome else [],
    }
    return payload


def page_library_references(exported_html: str) -> dict:
    """Read generic Resources / Tools / Continue exploring units on ANY page.

    Library sections are metadata, not learning-card content. No specialised
    heading or file unit is required for a particular Streamlit screen.
    """
    result = {"resource_references": [], "tool_references": [],
              "further_reading": [], "resource_ids": []}
    if not exported_html:
        return result
    for unit in parse_units(exported_html).get("units", []):
        key = {"sources": "resource_references", "tools": "tool_references",
               "further_reading": "further_reading"}.get(unit.get("type"))
        if key:
            result[key].extend(unit.get("linked_items") or [])
    for key in ("resource_references", "tool_references", "further_reading"):
        unique = []
        seen = set()
        for value in result[key]:
            signature = (str(value.get("url") or "").casefold(),
                         str(value.get("row_id") or "").casefold(),
                         str(value.get("title") or "").casefold().strip())
            if signature not in seen:
                unique.append(value)
                seen.add(signature)
        result[key] = unique
    return result


def _row_link_locator(value: str) -> tuple[str, str]:
    """Get Coda table-view and row markers, e.g. #Tools_tuBs_gOX/r2.

    Coda's row URL often uses r1/r2 rather than its API row's i-* ID.
    The pair can be compared to a row's browserLink when available.
    """
    raw = unquote(str(value or "")).split("#", 1)
    if len(raw) != 2:
        return ("", "")
    location = raw[1].split("?", 1)[0].split("&", 1)[0]
    bits = [b for b in location.split("/") if b]
    if len(bits) < 2:
        return ("", "")
    return (bits[0].casefold(), bits[1].casefold())


def normalized_column(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(name).casefold()).strip()


def _column_values(row: dict) -> dict[str, object]:
    return {normalized_column(k): v for k, v in (row.get("values") or {}).items()}


def _cell(value) -> str:
    if isinstance(value, list):
        return "; ".join(_cell(v) for v in value)
    if isinstance(value, dict):
        return str(value.get("name") or value.get("display") or value.get("value") or "")
    return str(value or "").strip()


def _lookup(values: dict, names: tuple[str, ...]) -> str:
    for name in names:
        v = values.get(normalized_column(name))
        if v not in (None, "", []):
            return _cell(v)
    return ""


def _extract_attachment_links(value) -> list[dict]:
    """Coda table attachment cells can be URLs, markdown text or object lists.

    Store HTTPS links rather than downloading arbitrary external resources in
    the parser. Only the manual import step can fetch Coda-hosted bytes.
    """
    links = []
    if isinstance(value, list):
        for child in value:
            links.extend(_extract_attachment_links(child))
    elif isinstance(value, dict):
        url = next((str(value.get(k) or "") for k in
                    ("url", "downloadUrl", "browserLink", "href", "link") if value.get(k)), "")
        if _safe_link(url):
            links.append({"title": str(value.get("name") or value.get("title") or url.split("/")[-1] or "File"), "url":url})
        else:
            for item in value.values():
                if isinstance(item, (dict, list, str)):
                    links.extend(_extract_attachment_links(item))
    else:
        txt = str(value or "")
        markdown_links = list(re.finditer(r"\[([^\]]+)\]\((https://[^\s)]+)\)", txt))
        for item in markdown_links:
            links.append({"title":item.group(1).strip(), "url":item.group(2)})
        for url in re.findall(r"https://[^\s<>)\]\"']+", txt):
            if _safe_link(url) and url not in {item["url"] for item in links}:
                links.append({"title":url.split("/")[-1].split("?")[0] or "Supporting file", "url":url})
    return links


def table_record_payload(doc_id: str, table_id: str, row: dict, kind: str) -> dict:
    """Copy table columns using their actual names, including extras as source_columns."""
    values = _column_values(row)
    spec = RESOURCE_COLUMNS if kind == "resource" else TOOL_COLUMNS
    mapping = {key: _lookup(values, aliases) for key, aliases in spec.items()}
    rid = stable_id("resource" if kind == "resource" else "tool", doc_id, f"{table_id}:{row['id']}")
    mapping.update({"id": rid,
        "title": mapping.get("title") or str(row.get("name") or rid),
        "source_system": "superhuman_docs", "source_doc_id": doc_id,
        "source_table_id": table_id, "source_row_id": str(row["id"]),
        "source_row_url": str(row.get("browserLink") or ""),
        "source_columns": {str(k): _cell(v) for k, v in (row.get("values") or {}).items()}})
    if kind == "resource":
        mapping["origin"] = "MOSAIC content"
        mapping["tags"] = [x.strip() for x in mapping.pop("keywords", "").replace(";", ",").split(",") if x.strip()]
        mapping["source_page_url"] = mapping.get("source_page_url") or str(row.get("browserLink") or "")
        mapping["related_modules"] = []
        # Optional field; linking a row from a page is sufficient without it.
        mapping["learning_phases"] = [p.strip().casefold() for p in re.split(
            r"[,;\n]", _lookup(values, ("Learning phase", "Learning phases", "Phase"))) if p.strip()]
        attachment_cells = {"download url", "file url", "pdf url", "files", "file", "pdf",
                            "attachments", "attachment", "downloadable file"}
        attachments = []
        for heading, raw in (row.get("values") or {}).items():
            if normalized_column(heading) in attachment_cells:
                attachments.extend(_extract_attachment_links(raw))
        seen = set()
        mapping["attachment_links"] = [link for link in attachments if not
                                       (link["url"] in seen or seen.add(link["url"]))]
        mapping["_unresolved_attachments"] = bool(
            any(str(v or "").strip() for k, v in (row.get("values") or {}).items()
                if normalized_column(k) in attachment_cells)
            and not mapping["attachment_links"])
    else:
        attachment_cells = ("supporting materials", "download url", "file", "files", "attachments", "pdf")
        attachments = []
        for heading, raw_value in (row.get("values") or {}).items():
            if normalized_column(heading) not in attachment_cells:
                continue
            attachments.extend(_extract_attachment_links(raw_value))
        seen = set()
        mapping["attachment_links"] = [link for link in attachments if not
                                       (link["url"] in seen or seen.add(link["url"]))]
        mapping["_unresolved_attachments"] = bool(
            any(str(raw_value or "").strip() for heading, raw_value in (row.get("values") or {}).items()
                if normalized_column(heading) in attachment_cells)
            and not mapping["attachment_links"]
        )
        typ = mapping.get("format", "").lower()
        mapping["tool_type"] = mapping.get("format") or "Tool"
        mapping["format"] = ("Model" if "model" in typ else "Digital tool" if any(x in typ for x in ("software", "digital"))
                             else "Website" if "website" in typ else "Workshop")
        mapping["keywords"] = [x.strip() for x in mapping.get("keywords", "").replace(";", ",").split(",") if x.strip()]
        mapping["steps"] = [s.strip() for s in mapping.get("steps", "").splitlines() if s.strip()]
        mapping["status"] = "Available"
    return mapping


def resolve_linked_references(page: dict, resources: list[dict], tools: list[dict], *,
                              check_resource: bool = True, check_tool: bool = True) -> list[str]:
    """Resolve Coda @row links to canonical local records, without inventing IDs.

    Prefer API row ID, then the original row URL, then a unique exact title.
    Never choose an arbitrary record when titles are ambiguous. Unmatched
    references preserve the original HTTPS link as a safe fallback.
    """
    warnings = []
    page.setdefault("resource_ids", [])
    for key, catalogue in (("resource_references", resources), ("tool_references", tools)):
        if key == "resource_references" and not check_resource:
            continue
        if key == "tool_references" and not check_tool:
            continue
        by_row = {str(r.get("source_row_id")): r for r in catalogue if r.get("source_row_id")}
        by_name = {}
        by_link = {}
        by_locator = {}
        for record in catalogue:
            by_name.setdefault(str(record.get("title", "")).casefold().strip(), []).append(record)
            url = str(record.get("source_row_url") or "").strip()
            if url:
                by_link.setdefault(url.split("&view=", 1)[0].rstrip("/"), []).append(record)
                locator = _row_link_locator(url)
                if all(locator):
                    by_locator.setdefault(locator, []).append(record)
        for ref in page.get(key) or []:
            title = str(ref.get("title") or "").lstrip("@").strip()
            row_id = str(ref.get("row_id") or "")
            url = str(ref.get("url") or "")
            target = by_row.get(row_id) if row_id else None
            if not target and url:
                candidates = by_link.get(url.split("&view=", 1)[0].rstrip("/"), [])
                if len(candidates) == 1:
                    target = candidates[0]
            if not target and url:
                candidates = by_locator.get(_row_link_locator(url), [])
                if len(candidates) == 1:
                    target = candidates[0]
            if not target:
                candidates = by_name.get(title.casefold(), [])
                if len(candidates) == 1:
                    target = candidates[0]
            if target:
                ref["app_id"] = target["id"]
                # Display the authoritative title rather than @ mention artifacts.
                ref["title"] = target["title"]
                if key == "resource_references":
                    page["resource_ids"].append(target["id"])
            elif ref.get("status") != "placeholder":
                warnings.append(f"{page.get('title') or 'Page'}: {key} item '{title}' could not be matched to a table row; original link retained when available")
    page["resource_ids"] = list(dict.fromkeys(page["resource_ids"]))
    return warnings


def build_preview(doc_id: str, root_page: dict, pages: list[dict], token: str,
                  resource_table_id: str = "", tool_table_id: str = "", *, max_lessons: int = 60,
                  module_page_ids: set[str] | None = None,
                  lesson_page_ids: set[str] | None = None,
                  include_module_records: bool = True,
                  include_environment_page: bool = True,
                  resource_row_offset: int = 0, resource_row_limit: int | None = None,
                  tool_row_offset: int = 0, tool_row_limit: int | None = None) -> dict:
    """Manual, read-only preview of the learning-environment page tree.

    Every module/phase/class page can contain generic linked library units.
    All HTML is exported only on editor request; learner pages use the CMS.
    """
    # Select the exact documents *before* starting any export. Do not export
    # the entire environment when an editor asks for one class or library batch.
    all_modules = page_tree(pages, str(root_page["id"]))
    included_modules = (set(module_page_ids) if module_page_ids is not None else None)
    included_lessons = (set(lesson_page_ids) if lesson_page_ids is not None else None)
    modules = [m for m in all_modules if included_modules is None or
               str(m["page"]["id"]) in included_modules]
    lesson_pages = [(m, item) for m in modules for item in m["lessons"]
                    if included_lessons is None or str(item["page"]["id"]) in included_lessons]
    phantom_candidates = [
        {"module_id": stable_id("module", doc_id, str(m["page"]["id"])),
         "lesson_id": stable_id("lesson", doc_id, str(phase["page"]["id"])),
         "source_doc_id": doc_id, "source_page_id": str(phase["page"]["id"]),
         "title": str(phase["page"].get("name") or "Phase page")}
        for m in modules for phase in m["block_pages"]
    ]
    if len(lesson_pages) > max_lessons:
        raise ValueError(f"This batch contains {len(lesson_pages)} classes; choose a smaller batch (max {max_lessons}).")
    unique_pages = {}
    if include_environment_page and (modules or lesson_pages):
        unique_pages[str(root_page["id"])] = root_page
    if include_module_records:
        for module in modules:
            unique_pages[str(module["page"]["id"])] = module["page"]
            for group in module["block_pages"]:
                unique_pages[str(group["page"]["id"])] = group["page"]
    for _, item in lesson_pages:
        unique_pages[str(item["page"]["id"])] = item["page"]
    exports, errors = {}, []
    # Coda export starts with POST and shares a strict write rate limit. A
    # sequential queue, combined with the API client's POST pacing and 429
    # backoff, avoids the uncontrolled 3-worker export burst used previously.
    for page_id, page in unique_pages.items():
        try:
            exports[page_id] = export_page_html(doc_id, page_id, token)
        except Exception as ex:
            errors.append(f"Could not export {page.get('name')}: {str(ex)[:180]}")
    root_html = exports.get(str(root_page["id"]), "")
    environment_intro, _ = page_intro_and_objectives(root_html)
    header = (BeautifulSoup(root_html, "html.parser").find("h1") if root_html else None)
    candidate_title = header.get_text(" ", strip=True) if header else ""
    environment = {
        "title": candidate_title if candidate_title and "[" not in candidate_title else str(root_page.get("name") or "Learning environment"),
        "source_doc_id": doc_id, "source_page_id": str(root_page["id"]),
        "intro": environment_intro, "url": str(root_page.get("browserLink") or ""),
    }
    entries, warnings = [], list(errors)
    uncertain = set(unverified_sibling_order(pages, str(root_page["id"])))
    selected_names = {str(root_page.get("name") or "")} | {
        str(p["page"].get("name") or "") for p in modules
    }
    selected_names.update(str(g["page"].get("name") or "") for m in modules for g in m["block_pages"])
    for parent_name in sorted(uncertain & selected_names):
        warnings.append(f"Page order could not be verified under '{parent_name}': check class order before publishing.")
    module_positions = {str(m["page"]["id"]): i for i, m in enumerate(all_modules, start=1)}
    for module_spec in modules:
        mi = module_positions[str(module_spec["page"]["id"])]
        page = module_spec["page"]
        page_id = str(page["id"])
        module_id = stable_id("module", doc_id, page_id)
        exported = exports.get(page_id, "")
        # A class-only batch must never create an empty module record.
        if not include_module_records:
            exported = ""
        intro, objectives = page_intro_and_objectives(exported)
        if not objectives and exported:
            objective_unit = _first_nonempty(parse_units(exported).get("units", []), "objectives")
            if objective_unit:
                objectives = _list_items(objective_unit.get("text", ""))[:5]
        module_links = page_library_references(exported)
        inline_cover = first_module_figure_url(exported)
        metadata_cover = _page_cover_url(page)
        block_intros, phase_links, phase_digests = {}, {}, []
        phase_export_failed = False
        for block in (module_spec["block_pages"] if include_module_records else []):
            block_page_id = str(block["page"]["id"])
            block_html = exports.get(block_page_id, "")
            block_intro, _ = page_intro_and_objectives(block_html)
            if block_intro:
                block_intros[block["level"]] = block_intro
            phase = page_library_references(block_html)
            phase["title"] = str(block["page"].get("name") or block["level"])
            phase_links[block["level"]] = phase
            phase_digests.append(f"{block['level']}:{block_html}")
            if block_page_id not in exports:
                phase_export_failed = True
                warnings.append(f"{page.get('name')}: a phase page could not be exported. "
                                "Do not overwrite this module until all its page links can be read.")
        payload = {
            "id": module_id, "title": str(page.get("name") or "Untitled module"),
            "short_title": str(page.get("name") or "Untitled module"),
            "description": intro[:500], "learning_outcomes": objectives,
            "cover_image_url": inline_cover or metadata_cover,
            # If a body figure is unavailable when explicitly importing,
            # a Superhuman Docs page cover may still be usable.
            "cover_image_fallback_url": metadata_cover if inline_cover and metadata_cover != inline_cover else "",
            "cover_image_source": "first_module_figure" if inline_cover else ("page_cover" if metadata_cover else "none"),
            "block_intros": block_intros,
            "resource_references": module_links["resource_references"],
            "tool_references": module_links["tool_references"],
            "further_reading": module_links["further_reading"],
            "resource_ids": [], "phase_references": phase_links,
            "convince": {"linked_files": []},
            "_convince_export_failed": phase_export_failed,
            "estimated_minutes": max(5, len(module_spec["lessons"]) * 8),
            "status": "Available", "track": "Learning", "eyebrow": "Learning module",
            "source_note": "", "source_system": "superhuman_docs",
            "source_doc_id": doc_id, "source_page_id": page_id,
            "source_page_url": str(page.get("browserLink") or ""),
            "source_digest": hashlib.sha256(
                (exported + str(page.get("image") or "") + str(page.get("name") or "") +
                 ":position:" + str(mi) + ":group_pages:" + "|".join(phase_digests)).encode()
            ).hexdigest() if exported else "",
        }
        if include_module_records:
            if not exported:
                warnings.append(f"Module page '{payload['title']}' could not be exported; module update was excluded, but selected classes may still import.")
            else:
                if not objectives:
                    warnings.append(f"Module '{payload['title']}' has no detectable 'What you will learn' list")
                entries.append({"kind": "module", "id": module_id, "module_id": module_id,
                                "payload": payload, "sort_order": mi * 10})
        for li, item in enumerate(module_spec["lessons"], start=1):
            lesson_page = item["page"]
            if included_lessons is not None and str(lesson_page["id"]) not in included_lessons:
                continue
            lesson_html = exports.get(str(lesson_page["id"]))
            if lesson_html is None:
                continue
            parsed = parse_units(lesson_html)
            lesson = lesson_payload(doc_id, lesson_page, item["level"], parsed)
            lesson["source_digest"] = hashlib.sha256(
                (lesson_html + str(lesson_page.get("name") or "") +
                 ":level:" + str(item["level"]) + ":position:" + str(li)).encode()
            ).hexdigest()
            entries.append({"kind": "lesson", "id": lesson["id"], "module_id": module_id,
                            "payload": lesson, "sort_order": li * 10, "warnings": parsed.get("warnings", [])})
            warnings.extend(f"{lesson['title']}: {warning}" for warning in parsed.get("warnings", []))

    library = {"resource": [], "tool": []}
    for kind, table_id in (("resource", resource_table_id), ("tool", tool_table_id)):
        if not table_id:
            continue
        try:
            offset = resource_row_offset if kind == "resource" else tool_row_offset
            row_limit = resource_row_limit if kind == "resource" else tool_row_limit
            records = list_rows_with_values(doc_id, table_id, token, offset=offset, max_rows=row_limit)
            library[kind] = [table_record_payload(doc_id, table_id, record, kind) for record in records]
            for idx, record in enumerate(library[kind], start=offset + 1):
                record["_source_sort_order"] = idx * 10
            # Coda simple-format attachment cells sometimes contain only a
            # filename. A rich-format reread can expose an actual file link.
            # Only do this extra request in manual preview if needed.
            if any(record.get("_unresolved_attachments") for record in library[kind]):
                try:
                    rich = {str(r.get("id")): r for r in list_rows_with_values(
                        doc_id, table_id, token, value_format="rich", offset=offset, max_rows=row_limit)}
                    for record in library[kind]:
                        source = rich.get(str(record.get("source_row_id"))) or {}
                        links = list(record.get("attachment_links") or [])
                        for name, value in (source.get("values") or {}).items():
                            if normalized_column(name) in {
                                "download url", "file url", "pdf url", "files", "file", "pdf",
                                "attachments", "attachment", "downloadable file", "supporting materials",
                            }:
                                links.extend(_extract_attachment_links(value))
                        seen = set()
                        record["attachment_links"] = [link for link in links if not
                                                     (link["url"] in seen or seen.add(link["url"]))]
                        if record["attachment_links"]:
                            record["_unresolved_attachments"] = False
                except Exception as ex:
                    warnings.append(f"{kind.title()} file links could not be checked in rich API format: {str(ex)[:140]}")
            for record in library[kind]:
                if record.get("_unresolved_attachments"):
                    warnings.append(f"{kind.title()} '{record['title']}' has an attachment field "
                                    "but no file URL was returned; add a working link in the table.")
        except Exception as ex:
            warnings.append(f"Could not read {kind} table: {str(ex)[:160]}")

    # Library imports are optional. When skipped, retain original @row URLs
    # without flooding the preview with misleading unmatched-link warnings.
    for entry in entries:
        if resource_table_id or tool_table_id:
            warnings.extend(resolve_linked_references(
                entry["payload"], library["resource"], library["tool"],
                check_resource=bool(resource_table_id and resource_row_limit is None),
                check_tool=bool(tool_table_id and tool_row_limit is None)))
            if entry["kind"] == "module":
                for group in (entry["payload"].get("phase_references") or {}).values():
                    warnings.extend(resolve_linked_references(
                        group, library["resource"], library["tool"],
                        check_resource=bool(resource_table_id and resource_row_limit is None),
                        check_tool=bool(tool_table_id and tool_row_limit is None)))
    modules_by_title = {str(m["page"].get("name") or "").casefold().strip():
                        stable_id("module", doc_id, str(m["page"]["id"]))
                        for m in all_modules}
    for record in library["resource"]:
        linked_modules = _lookup(_column_values({"values": record.get("source_columns") or {}}),
                                 ("Related module(s)", "Related modules"))
        record["related_modules"] = [mid for title, mid in modules_by_title.items()
                                      if title and title in linked_modules.casefold()]
    # Optional table phase metadata can supplement, but not replace, @ links.
    for entry in entries:
        if entry["kind"] != "module":
            continue
        group_map = entry["payload"].setdefault("phase_references", {})
        for record in library["resource"]:
            phase_names = set(record.get("learning_phases") or [])
            if entry["id"] not in record.get("related_modules", []) or not (phase_names & {"share", "convince"}):
                continue
            group = group_map.setdefault("Convince", {
                "title": "Communicate", "resource_references": [], "tool_references": [],
                "further_reading": [], "resource_ids": [],
            })
            if not any(ref.get("app_id") == record["id"] for ref in group["resource_references"]):
                group["resource_references"].append({
                    "title": record["title"], "app_id": record["id"],
                    "url": record.get("source_row_url", ""), "row_id": record.get("source_row_id", ""),
                })
                group["resource_ids"].append(record["id"])
    tools_by_id = {record["id"]: record for record in library["tool"]}
    for entry in entries:
        if entry["kind"] not in {"lesson", "module"}:
            continue
        page = entry["payload"]
        for ref in page.get("tool_references") or []:
            tool = tools_by_id.get(ref.get("app_id"))
            if not tool:
                continue
            links = tool.setdefault("lesson_links", [])
            link = {"module_id": entry["module_id"],
                    "lesson_id": page["id"] if entry["kind"] == "lesson" else ""}
            if link not in links:
                links.append(link)
    return {"environment": environment, "environment_verified": bool(root_html),
            "entries": entries, "obsolete_phase_lesson_candidates": phantom_candidates, "libraries": library,
            "warnings": warnings, "count": {"modules": sum(e["kind"] == "module" for e in entries),
                "classes": sum(e["kind"] == "lesson" for e in entries),
                "resources": len(library["resource"]), "tools": len(library["tool"])},
            "scope": {"module_page_ids": sorted(included_modules) if included_modules is not None else None,
                      "lesson_page_ids": sorted(included_lessons) if included_lessons is not None else None,
                      "resource_row_offset": resource_row_offset, "tool_row_offset": tool_row_offset}}


def list_rows_with_values(doc_id: str, table_id: str, token: str, *, value_format: str = "simple",
                          offset: int = 0, max_rows: int | None = None) -> list[dict]:
    """Read every row's named columns (not only display name). No writes to Coda."""
    import requests
    from urllib.parse import quote
    api = f"https://coda.io/apis/v1/docs/{quote(doc_id, safe='')}/tables/{quote(table_id, safe='')}/rows"
    if offset < 0 or (max_rows is not None and max_rows < 1):
        raise ValueError("Library row offset must be >=0, and batch size must be positive")
    rows, next_token, seen_count = [], None, 0
    for _ in range(100):
        params = {"limit": 100, "valueFormat": value_format, "useColumnNames": "true"}
        if next_token:
            params["pageToken"] = next_token
        data = _request("GET", api, token, params=params).json()
        page_rows = data.get("items") or []
        for row in page_rows:
            seen_count += 1
            if seen_count <= offset:
                continue
            rows.append(row)
            if max_rows is not None and len(rows) >= max_rows:
                return rows
        next_token = data.get("nextPageToken")
        if not next_token:
            return rows
    raise RuntimeError("Too many paginated table rows")
