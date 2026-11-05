"""Read-only Superhuman Docs HTML parser. No horizontal dividers required.

Recognizes actual Superhuman Docs export patterns:
* Paragraphs are generally <div><span>text</span></div>, not <p>.
* H3 headings start cards, even with no <hr>.
* Semantic callouts may export as ordinary bold labels ('Reflection', etc.).
* Images remain with their learning card. Native tables start a new table card, with optional adjacent title/intro.

This parses a SINGLE exported class page. It does not write to the MOSAIC database.
"""
from __future__ import annotations
import re
from collections import Counter
from typing import Any, Iterable
from bs4 import BeautifulSoup, Tag
from urllib.parse import urlparse

RESERVED = {
    "case study": "case_study", "case studies": "case_study",
    "key takeaways": "takeaways", "takeaways": "takeaways",
    "further reading": "further_reading", "what you will learn": "objectives",
    "learning objectives": "objectives", "objectives": "objectives",
    "sources": "sources", "references": "sources", "resources": "sources",
    "tool": "tools", "tools": "tools", "tools used": "tools",
    "explore more": "further_reading", "continue exploring": "further_reading",
    "quiz": "quiz", "reflection": "reflection", "reflection question": "reflection",
}
CALLOUT_TYPES = {
    "quiz": "quiz", "reflection": "reflection", "reflection question": "reflection",
    "sources": "sources", "references": "sources", "resources": "sources", "quote": "quote",
    "tool": "tools", "tools used": "tools", "tools": "tools",
    "further reading": "further_reading", "explore more": "further_reading", "continue exploring": "further_reading",
    "tip": "callout",
    "important": "callout", "warning": "callout", "policy insight": "callout",
}
CALLOUT_ICONS = {"❓": "quiz", "💡": "reflection", "📚": "sources",
                 "💬": "quote", "📣": "callout", "🛠️": "tools", "🛠": "tools",
                 "🔧": "tools", "🧰": "tools", "⚠️": "callout", "❝": "quote", "❗": "callout"}
# The white-flag note has a free-form title (e.g., "Nature-positive future").
# Superhuman Docs sometimes omits the native callout icon in exported HTML.
# Explicit Unicode flags are reliable; invisible/omitted icons require a title
# selected by a reviewer instead of guessing from arbitrary bold text.
FLAG_ICONS = ("🏳️", "🏳", "⚐", "⚑")
# A deliberate, readable prefix is a stable alternative when Coda removes its
# decorative flag icon on export. The prefix is a CONTENT AUTHORING cue, not the
# title shown to learners: "Note: Nature-positive future" -> "Nature-positive future".
# "Tip:" is supported for action-oriented notes using the same white-flag styling.
NOTE_TITLE_RE = re.compile(r"^\s*(Note|Tip)\s*:\s*(.+?)\s*$", re.I | re.S)


def _prefixed_note_title(value: str) -> tuple[str, str] | None:
    """Recognize an intentional Note:/Tip: title without guessing bold headings.

    Do not classify a whole prose paragraph as a title; the convention is a
    short callout heading followed by its explanatory paragraph.
    """
    value = re.sub(r"\s+", " ", str(value or "")).strip()
    match = NOTE_TITLE_RE.fullmatch(value)
    if not match:
        return None
    label, title = match.group(1).casefold(), match.group(2).strip(" :|–—")
    if not title or len(title) > 90 or len(title.split()) > 12:
        return None
    return title, label



# A library item is a link to a canonical Resources/Tools table row, not a
# new slide or an independently maintained bibliographic description.
LIBRARY_TYPES = {"sources", "further_reading", "tools"}
TABLE_REFERENCE_TYPES = {"sources", "tools"}  # Further reading uses ordinary links; no @ row lookup.
_PLACEHOLDER_RE = re.compile(r"(?:type\s*[‘'\"]?@|enter name of|\[tool|\[resource|\[publication|\[link|\[url)", re.I)
_URL_RE = re.compile(r"https?://[^\s<>\"']+", re.I)
_ROW_ID_RE = re.compile(r"(?:^|[/?#&=])(i-[A-Za-z0-9_-]{4,}|row-[A-Za-z0-9_-]{4,})(?=$|[/?#&])")


def _valid_href(value: str) -> str:
    """Only keep browser-safe links. Relative Coda links are retained for review."""
    href = str(value or "").strip()
    if not href:
        return ""
    parsed = urlparse(href)
    if parsed.scheme in ("https", "http") and parsed.netloc:
        return href
    if not parsed.scheme and href.startswith(("/", "#")):
        return href
    return ""


def _block_links(tag: Tag) -> list[dict]:
    """Preserve exported hyperlinks and any explicit Coda row metadata.

    This cannot recover @-references if their hyperlink and row attributes have
    both been stripped by page export. Such entries remain unresolved.
    """
    links = []
    for item in tag.find_all(True):
        attrs = {k: str(v) for k, v in item.attrs.items()
                 if k.startswith("data-coda") or k.startswith("data-row")}
        href = _valid_href(item.get("href", "") or item.get("data-href", ""))
        row_attr = next((v for k, v in attrs.items()
                         if re.search(r"(?:row[-_]?id|reference[-_]?id)", k, re.I) and v), "")
        label = _string(item)
        if not href and not row_attr:
            continue
        if not label or len(label) > 300:
            continue
        row_match = _ROW_ID_RE.search(href)
        row_id = row_attr or (row_match.group(1) if row_match else "")
        entry = {"title": label, "url": href, "row_id": row_id,
                 "source": "html_link" if href else "coda_row_attribute"}
        if entry not in links:
            links.append(entry)
    # An <a> can contain nested spans with the same text. Avoid duplicates by URL+title.
    deduped = []
    seen = set()
    for entry in links:
        key = (entry["title"], entry["url"], entry["row_id"])
        if key not in seen:
            deduped.append(entry)
            seen.add(key)
    return deduped


def _library_items(segment: list[dict], typ: str) -> list[dict]:
    """Return a compact library-reference list with source URLs preserved."""
    items = []
    for block in segment:
        if block["kind"] not in ("text", "callout"):
            continue
        value = str(block.get("text", "")).strip()
        if not value:
            continue
        # Skip the heading or the top-of-callout label.
        clean = re.sub(r"^[•\-\s]+", "", value).strip()
        clean = re.sub(r"^@\s*", "", clean)
        if _flattened_callout_label(block) or clean.casefold().strip(" :") in CALLOUT_TYPES or clean.casefold().strip(" :") in RESERVED:
            continue
        if _PLACEHOLDER_RE.search(value):
            items.append({"title": value, "url": "", "row_id": "", "status": "placeholder"})
            continue
        links = block.get("links", [])
        if links:
            for link in links:
                items.append({"title": link["title"], "url": link["url"],
                              "row_id": link["row_id"], "status": "linked" if link["url"] else "row_id_only"})
            # Preserve any trailing explanation as context but don't treat it as
            # a separate library item. Additional text isn't canonical metadata.
            continue
        if block["kind"] == "callout":
            # Native box might contain a label and multiple rows; conservatively
            # parse line by line, skipping heading and blank lines.
            candidate_lines = [line.strip() for line in value.splitlines() if line.strip()]
        else:
            candidate_lines = [value]
        for line in candidate_lines:
            line = re.sub(r"^[-•]\s*", "", line).strip()
            if not line or line.casefold().strip(" :") in CALLOUT_TYPES:
                continue
            link_match = _URL_RE.search(line)
            href = _valid_href(link_match.group(0).rstrip(').,') if link_match else "")
            title = line[:link_match.start()].strip(" :-") if link_match else line
            title = title.lstrip("@").strip()
            if not title and href:
                title = href
            if title:
                items.append({"title": title, "url": href, "row_id": "",
                              "status": "linked" if href else "unresolved"})
    # Deduplicate entries when the same link appears in multiple nested spans.
    result = []
    seen = set()
    for item in items:
        key = (item["title"].casefold(), item["url"], item["row_id"])
        if key not in seen:
            result.append(item)
            seen.add(key)
    return result

MEDIA_TAGS = {"img", "video", "iframe", "table", "hr"}
BLOCK_TAGS = {"div", "p", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6",
              "table", "img", "video", "iframe", "aside", "hr", "pre", "blockquote"}


def _string(element: Tag) -> str:
    return re.sub(r"\s+", " ", element.get_text(separator=" ", strip=True)).strip()


def _kind_from_callout(value: str) -> str | None:
    value = value.strip()
    for icon, kind in CALLOUT_ICONS.items():
        if value.startswith(icon):
            return kind
    cleaned = re.sub(r"^[^\w]*", "", value, flags=re.UNICODE).lower()
    for prefix, kind in CALLOUT_TYPES.items():
        if re.match(r"^" + re.escape(prefix) + r"(?:\s|:|\||$)", cleaned):
            return kind
    return None


def _is_callout(tag: Tag) -> bool:
    class_name = " ".join(tag.get("class", [])).lower()
    markers = " ".join(str(tag.get(a, "")) for a in
                       ("data-type", "data-block-type", "data-coda-type", "role")).lower()
    return "callout" in class_name or "callout" in markers or tag.name == "aside"


def _flattened_callout_label(block: dict) -> tuple[str, str] | None:
    """Recognize a clearly labelled callout even if the export flattens its box.

    We cannot infer an unlabelled callout from HTML that contains only a
    normal paragraph. A standalone reserved label or a dedicated emoji + label
    is therefore required. Bold is required when the label has no emoji.
    """
    if block["kind"] != "text":
        return None
    label = re.sub(r"\s+", " ", block["text"].strip()).rstrip(":").strip()
    has_emoji = False
    for icon in sorted(CALLOUT_ICONS, key=len, reverse=True):
        if label.startswith(icon):
            label = label[len(icon):].strip().rstrip(":").strip()
            has_emoji = True
            break
    # Also accept a warning icon with/without its variation selector.
    if label.startswith("⚠"):
        label = label.lstrip("⚠️ ").strip().rstrip(":").strip()
        has_emoji = True
    kind = CALLOUT_TYPES.get(label.casefold())
    if kind is None:
        return None
    fragment = BeautifulSoup(block.get("html", ""), "html.parser")
    bold = bool(fragment.find(["b", "strong"]) or fragment.find(
        attrs={"style": re.compile(r"font-weight\s*:\s*(bold|[6-9]00)", re.I)}))
    if not (has_emoji or bold):
        return None
    return kind, label




def _flag_title(text: str) -> str | None:
    """Return the free-form title from a text-based flag (if present)."""
    normalized = str(text or "").strip()
    for icon in sorted(FLAG_ICONS, key=len, reverse=True):
        if normalized.startswith(icon):
            title = normalized[len(icon):].strip().strip(" :|")
            return title or None
    return None


def _bold_title(block: dict) -> str | None:
    """Find standalone bold titles that COULD have been a flattened note.

    Titles by themselves are ambiguous: the Coda HTML does not say if they were
    an informational callout, glossary entry, or ordinary bold subheading.
    """
    if block.get("kind") != "text":
        return None
    text = str(block.get("text", "")).strip()
    if not text or len(text) > 90 or len(text.split()) > 12:
        return None
    if text[-1:] in (".", "!", "?", ";") or text.endswith(":"):
        return None
    if _flag_title(text) or _prefixed_note_title(text) or _kind_from_callout(text):
        return None
    fragment = BeautifulSoup(block.get("html", ""), "html.parser")
    bold_parts = []
    for part in fragment.find_all(["b", "strong", "span"]):
        styled = (part.name in ("b", "strong") or bool(re.search(
            r"font-weight\s*:\s*(bold|[6-9]00)", part.get("style", ""), re.I)))
        if styled:
            bold_parts.append(part.get_text(" ", strip=True))
    # Require the entire substantive paragraph to be bold, not merely a prefix
    # such as "Question:" or "Interpretation:".
    if any(re.sub(r"\s+", " ", part).strip() == text for part in bold_parts):
        return text
    return None


def flag_note_candidates(html_document: str) -> list[str]:
    """Ambiguous bold headings that can be selected as white-flag notes.

    This avoids wrongly guessing that every bold subtitle is a native callout.
    """
    blocks = _blocks(html_document)
    found: list[str] = []
    for i, block in enumerate(blocks[:-1]):
        title = _bold_title(block)
        if title and blocks[i + 1]["kind"] == "text" and title not in found:
            found.append(title)
    return found


def _inline_flag_notes(segment: list[dict], chosen_titles: set[str]) -> list[dict]:
    """Recognize flag titles while preserving their place within the text card."""
    notes: list[dict] = []
    for i, block in enumerate(segment[:-1]):
        if block.get("kind") != "text":
            continue
        title = _flag_title(block.get("text", ""))
        detection = "visible_flag_symbol" if title else ""
        note_style = "note"
        if not title:
            prefixed = _prefixed_note_title(block.get("text", ""))
            if prefixed:
                title, note_style = prefixed
                detection = "explicit_note_prefix"
        if not title:
            candidate = _bold_title(block)
            if candidate and candidate.casefold() in chosen_titles:
                title, detection = candidate, "reviewer_selected_title"
        if not title or segment[i + 1].get("kind") != "text":
            continue
        body = segment[i + 1]["text"]
        if not body:
            continue
        notes.append({"title": title, "text": body, "icon": "white_flag",
                      "kind": note_style, "detection_method": detection,
                      "position_in_unit": i})
    return notes

def _is_standalone_label(block: dict) -> bool:
    return _flattened_callout_label(block) is not None


def _blocks(html_document: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html_document, "html.parser")
    root = soup.body or soup
    blocks: list[dict[str, Any]] = []

    def walk(e: Any) -> None:
        if not isinstance(e, Tag):
            return
        n = e.name.lower()
        if n in {"script", "style", "head", "noscript", "svg", "button", "h1", "h2"}:
            return
        if n == "hr":
            blocks.append({"kind": "divider"}); return
        if n == "h3":
            blocks.append({"kind": "heading", "text": _string(e)}); return
        if _is_callout(e):
            blocks.append({"kind": "callout", "text": e.get_text("\n", strip=True), "html": str(e), "links": _block_links(e)}); return
        if n == "table":
            rows = [[_string(c) for c in tr.find_all(["th", "td"], recursive=False)]
                    for tr in e.find_all("tr")]
            blocks.append({"kind": "table", "rows": [r for r in rows if r], "html": str(e)}); return
        if n == "img":
            blocks.append({"kind": "image", "src": e.get("src", ""),
                           "alt": e.get("alt", ""), "html": str(e)}); return
        if n in {"video", "iframe"}:
            src = e.get("src", "")
            if not src and n == "video":
                source = e.find("source")
                src = source.get("src", "") if source else ""
            blocks.append({"kind": "video", "src": src, "html": str(e)}); return
        if n in {"div", "p", "li", "h4", "h5", "h6", "pre", "blockquote"}:
            # A Superhuman Docs paragraph is a div containing inline spans.
            # If any nested structural item exists, recurse instead of taking its
            # combined text (which otherwise duplicates table cells, captions...).
            if not any(isinstance(c, Tag) and c.name.lower() in BLOCK_TAGS for c in e.descendants):
                text = e.get_text(" ", strip=True)
                text = re.sub(r"[ \t]+", " ", text).strip()
                if text:
                    blocks.append({"kind": "text", "text": text, "html": str(e), "links": _block_links(e)})
                return
        for child in e.children:
            walk(child)

    for child in root.children:
        walk(child)
    return blocks


def _heading_type(heading: str) -> str:
    norm = re.sub(r"\s+", " ", heading.casefold()).strip(" :|")
    if norm in RESERVED:
        return RESERVED[norm]
    if re.search(r"\bquiz\b", norm) and len(norm.split()) <= 5:
        return "quiz"
    return "text"


def _label_line(lines: list[str], label: str) -> str:
    m = re.compile(r"^" + re.escape(label) + r"\s*:\s*(.*)$", re.I)
    for i, line in enumerate(lines):
        match = m.match(line.strip())
        if match:
            return match.group(1).strip() or (lines[i + 1].strip() if i + 1 < len(lines) else "")
    return ""


def extract_quiz(text: str) -> dict:
    lines = [s.strip() for s in text.splitlines() if s.strip()]
    options = []
    for line in lines:
        m = re.match(r"^(?:[-•]\s*)?([A-D])\s*[.\):]\s*(.+)$", line, re.I)
        if m:
            options.append({"letter": m.group(1).upper(), "text": m.group(2).strip()})
    raw_answer = _label_line(lines, "Correct answer")
    match = re.fullmatch(r"\s*([A-D])\s*[.)]?\s*", raw_answer, re.I)
    letter = match.group(1).upper() if match else None
    index = next((i for i, o in enumerate(options) if o["letter"] == letter), None)
    return {"question": _label_line(lines, "Question"),
            "options": [o["text"] for o in options], "answer": index,
            "explanation": _label_line(lines, "Feedback")}


def extract_reflection(text: str) -> dict:
    lines = [s.strip() for s in text.splitlines() if s.strip()]
    return {"question": _label_line(lines, "Question"),
            "example_response": _label_line(lines, "Example response")}


def _table_intro_start(blocks: list[dict]) -> int | None:
    """Find a nearby human-friendly title/intro to move into a table card.

    This is intentionally conservative: do not move a whole theory card or
    any notes/media merely because it precedes a table. An adjacent H3 or a
    short standalone bold title with at most two intro paragraphs qualifies.
    """
    if not blocks:
        return None
    if (blocks[0].get("kind") == "heading"
            and _heading_type(blocks[0].get("text", "")) == "text"
            and all(b.get("kind") == "text" for b in blocks[1:])
            and len(blocks) <= 3
            and sum(len(b.get("text", "")) for b in blocks[1:]) <= 260):
        return 0
    for i in range(len(blocks) - 1, -1, -1):
        title = _bold_title(blocks[i])
        tail = blocks[i:]
        if (title and len(tail) <= 3
                and all(b.get("kind") == "text" for b in tail)
                and sum(len(b.get("text", "")) for b in tail[1:]) <= 260):
            return i
    return None


def _fallback_table_title(rows: list[list[str]]) -> str:
    if rows:
        headers = [str(cell).strip() for cell in rows[0] if str(cell).strip()]
        if len(headers) == 2 and sum(map(len, headers)) <= 54:
            return f"{headers[0]} versus {headers[1]}"
        if len(headers) == 1 and len(headers[0]) <= 50:
            return headers[0]
    return "Comparison table"


def parse_units(html_document: str, flag_titles: Iterable[str] | None = None) -> dict:
    """Parse one class; flag_titles marks callouts whose flag icon was lost.

    Explicit Unicode flag symbols and short Note:/Tip: titles need no hint.
    Bare bold subtitles are ambiguous when Coda removes its callout icon.
    """
    selected_flag_titles = {t.strip().casefold() for t in (flag_titles or []) if t.strip()}
    blocks = _blocks(html_document)
    segments: list[list[dict]] = []
    current: list[dict] = []

    def flush() -> None:
        nonlocal current
        if current:
            segments.append(current)
            current = []

    for b in blocks:
        if b["kind"] == "divider":
            flush()
        elif b["kind"] == "heading":
            flush()
            current = [b]
        elif b["kind"] == "callout":
            flush()
            segments.append([b])
        elif b["kind"] == "table":
            # A native table starts a NEW learning card. Reuse an immediately
            # preceding H3 or short bold subtitle (and short introduction) as
            # its title, without forcing contributors to author an H3.
            cut = _table_intro_start(current)
            table_intro = current[cut:] if cut is not None else []
            if cut is not None:
                current = current[:cut]
            flush()
            current = table_intro + [b]
        elif _is_standalone_label(b):
            # Extracted bold Reflection/Quiz/Sources label as a unit boundary.
            flush()
            current = [b]
        else:
            current.append(b)
    flush()

    units, warnings = [], []
    for segment in segments:
        heading = next((b["text"] for b in segment if b["kind"] == "heading"), "")
        first = segment[0]
        if any(b["kind"] == "table" for b in segment):
            # Table cards keep their own semantic type even when an H3 gives
            # the table its title. Otherwise a normal H3 would hide the table
            # inside a plain text card again.
            typ = "table"
            authored_title = _bold_title(first) if first["kind"] == "text" else None
            table_rows = next(b["rows"] for b in segment if b["kind"] == "table")
            title = heading or authored_title or _fallback_table_title(table_rows)
        elif heading:
            typ, title = _heading_type(heading), heading
        elif first["kind"] in {"callout", "text"} and _kind_from_callout(first["text"]):
            typ = _kind_from_callout(first["text"]) or "callout"
            title = first["text"].split("\n", 1)[0].strip()[:100]
        elif any(b["kind"] == "video" for b in segment):
            typ, title = "video", "Video"
        elif any(b["kind"] == "table" for b in segment):
            typ, title = "table", "Table"
        elif any(b["kind"] == "image" for b in segment):
            typ, title = "image", "Image"
        else:
            typ, title = "unclassified", "Unclassified content"
        texts = [b["text"] for b in segment if b["kind"] in {"text", "callout"}]
        images = [{"src": b.get("src", ""), "alt": b.get("alt", "")}
                  for b in segment if b["kind"] == "image"]
        videos = [b.get("src", "") for b in segment if b["kind"] == "video"]
        tables = [b["rows"] for b in segment if b["kind"] == "table"]
        fulltext = "\n".join(texts).strip()
        inline_notes = _inline_flag_notes(segment, selected_flag_titles)
        # The preview can render this ordered stream without exposing the "Note:"
        # authoring prefix or duplicating the note text as ordinary prose.
        note_at = {note["position_in_unit"]: note for note in inline_notes}
        content_parts = []
        suppressed_indexes = set()
        for index, block in enumerate(segment):
            if index in suppressed_indexes:
                continue
            if index in note_at:
                note = note_at[index]
                content_parts.append({"type": "inline_note", "title": note["title"],
                                      "text": note["text"], "icon": note["icon"],
                                      "kind": note["kind"]})
                suppressed_indexes.add(index + 1)
            elif block["kind"] == "text":
                if typ == "table" and index == 0 and _bold_title(block) == title:
                    # The title is rendered as the card heading, not a second
                    # paragraph within the comparison table card.
                    continue
                content_parts.append({"type": "text", "text": block["text"]})
            elif block["kind"] in {"image", "video", "table"}:
                content_parts.append({"type": block["kind"],
                                      **({"rows": block["rows"]} if block["kind"] == "table"
                                         else {"src": block.get("src", "")})})
        plain_text_without_notes = "\n".join(part["text"] for part in content_parts
                                             if part["type"] == "text")
        detection = (
            "native_html_callout" if first["kind"] == "callout" else
            "inferred_from_label" if _is_standalone_label(first) else
            "heading_3" if first["kind"] == "heading" else
            "media_or_content"
        )
        # Callout is a functional unit type in the learning app, even if its
        # original visual box did not survive the HTML export.
        is_callout_activity = typ in {"quiz", "reflection", "sources", "tools", "further_reading", "quote", "callout"}
        unit = {"preview_id": f"unit-{len(units)+1:02d}", "type": typ,
                "title": title, "text": fulltext,
                "images": images, "videos": videos, "tables": tables,
                "inline_notes": inline_notes, "content_parts": content_parts,
                "text_without_inline_notes": plain_text_without_notes,
                "word_count": len(fulltext.split()),
                "is_callout_activity": is_callout_activity,
                "detection_method": detection}
        if typ in LIBRARY_TYPES:
            unit["linked_items"] = _library_items(segment, typ)
            if not unit["linked_items"]:
                if typ == "further_reading":
                    warnings.append(f"{unit['preview_id']}: Further reading heading found, but no bullet links were exported; add clickable links below this heading")
                else:
                    warnings.append(f"{unit['preview_id']}: {typ} callout has no items; add @ row mentions to the library table")
            for item in unit["linked_items"]:
                if item["status"] == "placeholder":
                    warnings.append(f"{unit['preview_id']}: placeholder in {typ}: {item['title']}")
                elif typ == "further_reading" and not item.get("url"):
                    warnings.append(f"{unit['preview_id']}: Further reading entry '{item['title']}' is not a clickable link in the exported HTML")
                elif typ in TABLE_REFERENCE_TYPES and item["status"] == "unresolved":
                    warnings.append(f"{unit['preview_id']}: '{item['title']}' has no exported link or row ID; verify its @ reference")
        if typ == "quiz":
            unit["quiz"] = extract_quiz(fulltext)
            q = unit["quiz"]
            if len(q["options"]) < 2 or q["answer"] is None or not q["question"]:
                warnings.append(f"{unit['preview_id']}: quiz incomplete or contains placeholders; not import-ready")
        if typ == "reflection":
            unit["reflection"] = extract_reflection(fulltext)
            if not unit["reflection"]["question"]:
                warnings.append(f"{unit['preview_id']}: reflection question not clearly labelled")
        if typ == "text" and unit["word_count"] > 150:
            warnings.append(f"{unit['preview_id']}: text exceeds 150 words; consider splitting into two H3 cards")
        if typ == "unclassified":
            warnings.append(f"{unit['preview_id']}: not recognized; inspect original HTML")
        units.append(unit)
    return {"units": units,
            "counts": dict(Counter(u["type"] for u in units)), "warnings": warnings,
            "diagnostics": {"raw_blocks": len(blocks), "segments": len(segments),
                            "dividers_detected": sum(b["kind"] == "divider" for b in blocks),
                            "headings_detected": sum(b["kind"] == "heading" for b in blocks),
                            "callouts_detected": sum(b["kind"] == "callout" for b in blocks),
                            "flattened_callout_labels": sum(_is_standalone_label(b) for b in blocks),
                            "recognized_callout_units": sum(u["is_callout_activity"] for u in units),
                            "inferred_callouts": sum(u["detection_method"] == "inferred_from_label" for u in units),
                            "white_flag_notes": sum(len(u["inline_notes"]) for u in units),
                            "library_callouts": sum(u["type"] in LIBRARY_TYPES for u in units),
                            "library_linked_items": sum(sum(bool(x.get("url") or x.get("row_id")) for x in u.get("linked_items", [])) for u in units),
                            "library_unresolved_items": sum(sum(x.get("status") in ("unresolved", "placeholder") for x in u.get("linked_items", [])) for u in units if u["type"] in TABLE_REFERENCE_TYPES),
                            "further_reading_sections": sum(u["type"] == "further_reading" for u in units),
                            "further_reading_links": sum(sum(bool(i.get("url")) for i in u.get("linked_items", [])) for u in units if u["type"] == "further_reading"),
                            "flag_note_candidates": len(flag_note_candidates(html_document)),
                            "images_detected": sum(b["kind"] == "image" for b in blocks),
                            "tables_detected": sum(b["kind"] == "table" for b in blocks)}}


def app_topic_preview(parsed: dict) -> dict:
    """Illustrative mapping only. Never writes learner progress or content."""
    cards = []
    result = {"theory_cards": cards, "quiz": None, "prompt": "",
              "takeaway": "", "sources": [], "resource_references": [],
              "further_reading": [], "tool_references": [], "_import_warnings": []}
    for u in parsed["units"]:
        typ = u["type"]
        if typ == "quiz":
            q = u.get("quiz", {})
            if q.get("question") and q.get("answer") is not None and len(q.get("options", [])) >= 2:
                result["quiz"] = q
            else:
                result["_import_warnings"].append("Quiz has placeholders/incomplete fields and was not imported")
        elif typ == "reflection":
            result["prompt"] = u.get("reflection", {}).get("question", "")
        elif typ == "takeaways":
            result["takeaway"] = u["text"]
        elif typ in LIBRARY_TYPES:
            destination = ("tool_references" if typ == "tools" else
                           "further_reading" if typ == "further_reading" else "resource_references")
            result[destination].extend(u.get("linked_items", []))
            if typ == "sources":
                result["sources"].extend(u.get("linked_items", []))
            if typ in TABLE_REFERENCE_TYPES and any(x["status"] != "linked" for x in u.get("linked_items", [])):
                result["_import_warnings"].append(
                    f"{typ}: some references lack a verifiable hyperlink/row reference; review against Superhuman Docs table")
            elif typ == "further_reading" and any(not x.get("url") for x in u.get("linked_items", [])):
                result["_import_warnings"].append(
                    "Further reading: some bullets have no clickable destination; fix the links in Superhuman Docs")
        elif typ in {"text", "case_study", "image", "table", "video", "callout", "quote", "objectives"}:
            cards.append({"title": u["title"], "label": typ.replace("_", " ").title(),
                          "text": u.get("text_without_inline_notes", u["text"]),
                          "content_parts_for_review": u.get("content_parts", []),
                          "inline_notes_for_review": u.get("inline_notes", []),
                          "image_src_for_review": [im["src"] for im in u["images"]]})
            if u.get("inline_notes"):
                result["_import_warnings"].append(
                    "Informational note detected. Use content_parts_for_review to preserve "
                    "the note's exact position during production import.")
            if u["images"]:
                result["_import_warnings"].append("Images must be stored/linked as app image_resource_id before publishing")
            if u["videos"]:
                result["_import_warnings"].append("Video detected; current carousel needs a video renderer")
    return result
