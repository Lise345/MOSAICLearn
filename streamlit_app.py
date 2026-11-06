from __future__ import annotations

import base64
import copy
import hashlib
import io
import json
import re
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from uuid import uuid4
from pathlib import Path
from html import escape, unescape
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urljoin, urlparse
from urllib.request import Request, urlopen

import streamlit as st
import streamlit.components.v1 as components

try:
    import bleach
except ImportError:  # The plain-text local fallback remains usable without optional UI packages.
    bleach = None

try:
    from streamlit_quill import st_quill
except ImportError:  # requirements.txt installs this in production.
    st_quill = None

from superhuman_sync import build_preview as sh_build_preview, page_tree as sh_page_tree, stable_id as sh_stable_id
from sh_api_client import doc_id_from_url_or_id as sh_doc_id, list_pages as sh_list_pages, list_tables as sh_list_tables, enrich_page_hierarchy as sh_enrich_hierarchy

from content import (
    LEVEL_META,
    MODULES,
    ROLE_CALLOUTS,
    TOOL_DEFINITIONS,
    TOOL_DOWNLOAD_FILES,
)
from db import (
    assert_postgres_security_hardened,
    configure_database,
    create_community_comment,
    create_community_post,
    create_share,
    database_backend,
    delete_user_account,
    ensure_user,
    get_carousel_content,
    get_cms_lesson,
    get_cms_resource_file,
    get_cms_module,
    get_active_learning_environment,
    save_active_learning_environment,
    get_cms_story,
    get_cms_library_resource,
    get_cms_tool,
    get_community_activity,
    get_mycelium_state,
    get_progress,
    get_quiz_results,
    get_share,
    get_user,
    init_db,
    join_mycelium,
    leave_mycelium,
    list_community_notifications,
    list_community_posts,
    list_content_revisions,
    list_cms_lessons,
    list_cms_modules,
    list_cms_stories,
    list_cms_library_resources,
    list_cms_resource_files,
    list_cms_tools,
    list_published_carousels,
    list_users,
    mark_community_notifications_read,
    publish_carousel_content,
    publish_cms_lesson,
    publish_cms_module,
    publish_cms_story,
    publish_cms_library_resource,
    publish_cms_tool,
    record_privacy_acceptance,
    request_mycelium_connection,
    respond_mycelium_connection,
    save_quiz_result,
    save_carousel_draft,
    save_cms_lesson_draft,
    save_cms_module_draft,
    save_cms_story_draft,
    save_cms_library_resource_draft,
    save_cms_resource_file,
    save_cms_tool_draft,
    save_topic_progress,
    set_account_role,
    set_cms_lesson_archived,
    set_cms_module_archived,
    set_cms_story_archived,
    set_cms_library_resource_archived,
    set_cms_resource_archived,
    set_cms_tool_archived,
    toggle_community_reaction,
    unread_community_notification_count,
    update_user_profile,
)

APP_DIR = Path(__file__).resolve().parent
MYCELIUM_COMPONENT_DIR = APP_DIR / "mycelium_component"
_mycelium_network = components.declare_component(
    "mosaic_mycelium_network",
    path=str(MYCELIUM_COMPONENT_DIR),
)
ASSETS_DIR = APP_DIR / "assets"
APPROVED_LOGO = ASSETS_DIR / "mosaic-logo.png"
PAGE_ICON_FILE = ASSETS_DIR / "page-icon.png"
TOOL_FILES_DIR = ASSETS_DIR / "tools"
# Bump this value whenever the notice text changes. Existing accounts will be
# shown the non-dismissible re-consent dialog before they can continue.
PRIVACY_POLICY_VERSION = "2026-09-21"
PRIVACY_POLICY_EFFECTIVE_DATE = "21 September 2026"
# Change this value whenever init_db() gains a migration. It is passed into the
# cached initializer so Streamlit Cloud cannot reuse a pre-migration cache entry
# after a hot deployment.
DATABASE_SCHEMA_VERSION = "2026-10-26-superhuman-sync-v2"
MOSAIC_NEWSLETTER_URL = "https://mosaic-europe.eu/mosaic/sign-up"
MOSAIC_RESOURCE_REPOSITORY_URL = "https://mosaic-europe.eu/mosaic/mosaic-knowledge-repository"
MOSAIC_RESOURCE_HOSTS = {"mosaic-europe.eu", "www.mosaic-europe.eu"}
# Last-resort manifest of the resources currently published in the MOSAIC
# Knowledge Repository. It is used only when Drupal serves too little listing
# markup to discover the catalogue dynamically. Normal discovery (page markup,
# pagination and sitemap) is still attempted first, so future resources can be
# picked up without changing this list when the site exposes them normally.
MOSAIC_RESOURCE_FALLBACK_PATHS = (
    "/mosaic/resource/identifying-drivers-land-use-change",
    "/mosaic/resource/solar-sprawl-in-rural-areas%3F-a-comparative-study-between-andalusia-and-alentejo-regions.",
    "/mosaic/resource/systematic-review-digital-tools-systematic-review-available-digital-land-use-decision",
    "/mosaic/resource/digital-land-use-decision-support-tools-in-europe%3A-a-systematic-review-using-the-prisma-method",
    "/mosaic/resource/pathway-narratives-towards-a-nature-positive-european-union-land-system%3A-operationalising-the-nature-futures-framework-for-policy-objectives",
    "/mosaic/resource/what-is-private-land-conservation%3F",
    "/mosaic/resource/comprehensive-set-normative-policy-and-exploratory-scenarios-case-studies",
    "/mosaic/resource/guideline-establishment-policy-lab",
    "/mosaic/resource/introducing-mosaic",
    "/mosaic/resource/co-designing-policy-lab",
)
MOSAIC_IMPORT_MAX_BYTES = 25 * 1024 * 1024
TOOL_FORMATS = ("Workshop", "Website", "Model", "Digital tool")
TOOL_FORMAT_ICONS = {"Workshop": "◫", "Website": "↗", "Model": "⌁", "Digital tool": "◇"}
LANDING_STORY_VIDEO_URL = "https://www.youtube.com/watch?v=ppWj_rbRfxw"
APP_BUILD_ID = "2026-11-06-mosaic-search-tool-filter-performance-v21"


DEFAULT_STORIES = {
    "portugal-alentejo-two-speed-landscape": {
        "title": "When access to water changes a landscape",
        "place": "Portugal · Alentejo",
        "intro": "In Portugal's Alentejo, access to irrigation has changed what many farmers can grow and invest in. Around the Alqueva irrigation system, intensive olive and almond production expanded. In neighbouring rainfed areas, smaller and traditional farms face different pressures, including labour shortages and uncertainty about their future.",
        "case_body": "MOSAIC researchers investigated this 'two-speed' landscape through interviews with seven land users and six organisations, together with maps, regional statistics and policy analysis. Water access emerged as a major difference between available land-use options. But decisions were also influenced by markets, administrative barriers, soil and biodiversity, and people's attachment to inherited landscapes. Beekeepers and other ecosystem-dependent users can be affected by changes on land they do not control.",
        "response_heading": "What can policy makers learn from this?",
        "response_body": "Measures that seem appropriate for a region as a whole may affect irrigated, rainfed and ecosystem-dependent land users very differently. By studying drivers and listening to people making decisions on the ground, MOSAIC identifies practical constraints that policies and future pathways need to take into account. These findings inform policy design; the report does not evaluate a completed policy intervention.",
        "lesson": "Useful land-use policy starts with the conditions and motivations that shape real decisions. The same intervention may have very different effects across neighbouring landscapes.",
        "source_label": "MOSAIC · The two-speed landscape of the Alentejo region (Annex 3)",
        "source_url": "",
        "video_url": "",
        "image_asset": "stories/alentejo-landscapes.jpg",
        "image_caption": "Land-use landscapes in Alentejo. Images from the MOSAIC Portugal research report, Figure 1.",
    },
    "belgium-grassland-flexibility": {
        "title": "What if protecting grassland gives farmers a reason to plough it?",
        "place": "Belgium · Flemish Ardennes",
        "intro": "Imagine a farmer looking at a four-year-old meadow. Keeping it as grassland seems good for nature, but the farmer also needs flexibility. What if the farm changes, the land needs another use, or a future generation wants to farm differently?",
        "case_body": "In the Flemish Ardennes, MOSAIC found that some farmers plough temporary grassland before it acquires permanent status after five years. The associated restrictions make them worried about losing future options. A measure intended to protect grassland can therefore encourage its conversion.",
        "response_heading": "But what if the policy started with understanding that decision?",
        "response_body": "By interviewing farmers, mapping the incentives influencing their choices, and bringing landowners and policymakers together, the MOSAIC Policy Lab can reveal unintended consequences before new measures are designed. Future pathways can help explore alternatives that protect grassland while better accounting for agricultural flexibility.",
        "lesson": "Protecting nature requires understanding the decisions of those managing it.",
        "source_label": "Belgian Policy Lab · MOSAIC",
        "source_url": "https://mosaic-europe.eu/mosaic/belgium-policy-lab",
        "video_url": "",
        "image_asset": "stories/landscape-belgium.jpg",
        "image_caption": "Illustrative agricultural landscape with fields, hedgerows and grazing animals.",
    }
}

# Prefer a dedicated square favicon, then the approved MOSAIC logo. The globe
# is retained only as a last-resort fallback when neither image is installed.
PAGE_ICON = (
    PAGE_ICON_FILE
    if PAGE_ICON_FILE.is_file()
    else APPROVED_LOGO
    if APPROVED_LOGO.is_file()
    else "🌍"
)

st.set_page_config(
    page_title="MOSAIC Learn",
    page_icon=str(PAGE_ICON) if isinstance(PAGE_ICON, Path) else PAGE_ICON,
    layout="wide",
    initial_sidebar_state="expanded",
)

# Use PostgreSQL/Supabase in production when DATABASE_URL is configured.
# Local development automatically falls back to SQLite. Schema creation and
# migrations only need to run once per app process, rather than after every
# Streamlit widget interaction.
try:
    configure_database(st.secrets.get("DATABASE_URL", ""))
except Exception:
    configure_database()


@st.cache_resource(show_spinner=False)
def _initialise_database_once(schema_version: str) -> bool:
    # schema_version is intentionally part of the cache key. init_db() also
    # applies PostgreSQL RLS/PostgREST hardening for server-only app tables.
    init_db()
    if database_backend() == "postgres":
        assert_postgres_security_hardened()
    return True


try:
    _initialise_database_once(DATABASE_SCHEMA_VERSION)
except Exception:
    # Fail closed in production rather than serving the app with an exposed
    # public-schema table. Keep database details out of the browser response.
    st.error(
        "Database initialization or security hardening failed. "
        "Verify that DATABASE_URL uses the server-side PostgreSQL owner role "
        "and redeploy the app."
    )
    st.stop()


# Short-lived read caches keep navigation responsive when Streamlit reruns the
# script. Every write below clears its related cache immediately, so learners
# still see their own updates without waiting for the TTL.
@st.cache_data(ttl=30, show_spinner=False)
def _cached_user_record(
    user_id: str,
    email: str,
    name: str,
    auth_issuer: str,
    auth_subject: str,
) -> dict:
    return ensure_user(
        user_id,
        email,
        name,
        auth_issuer=auth_issuer,
        auth_subject=auth_subject,
    )


@st.cache_data(ttl=30, show_spinner=False)
def _cached_progress(user_id: str, module_id: str) -> dict[str, dict]:
    return get_progress(user_id, module_id)


@st.cache_data(ttl=30, show_spinner=False)
def _cached_quiz_results(user_id: str, module_id: str) -> dict[str, dict]:
    return get_quiz_results(user_id, module_id)


@st.cache_data(ttl=30, show_spinner=False)
def _cached_community_posts(limit: int = 30) -> list[dict]:
    return list_community_posts(limit)


@st.cache_data(ttl=20, show_spinner=False)
def _cached_community_activity(post_ids: tuple[int, ...], user_id: str) -> dict:
    return get_community_activity(post_ids, user_id)


@st.cache_data(ttl=20, show_spinner=False)
def _cached_unread_community_notifications(user_id: str) -> int:
    return unread_community_notification_count(user_id)


@st.cache_data(ttl=20, show_spinner=False)
def _cached_community_notifications(user_id: str, limit: int = 30) -> list[dict]:
    return list_community_notifications(user_id, limit)


@st.cache_data(ttl=20, show_spinner=False)
def _cached_mycelium_state(user_id: str) -> dict:
    return get_mycelium_state(user_id)


def _clear_community_interaction_caches() -> None:
    _cached_community_activity.clear()
    _cached_unread_community_notifications.clear()
    _cached_community_notifications.clear()
    _cached_mycelium_state.clear()


@st.cache_resource(show_spinner=False)
def _content_py_baseline() -> dict:
    """Keep an immutable copy of content.py across Streamlit reruns."""
    return copy.deepcopy(MODULES)


@st.cache_resource(show_spinner=False)
def _tool_definitions_baseline() -> dict:
    """Keep an immutable copy of the tools shipped in content.py."""
    return copy.deepcopy(TOOL_DEFINITIONS)


@st.cache_data(ttl=30, show_spinner=False)
def _cached_users() -> list[dict]:
    return list_users()


@st.cache_data(ttl=45, show_spinner=False)
def _cached_cms_modules() -> list[dict]:
    return list_cms_modules()


@st.cache_data(ttl=60, show_spinner=False)
def _cached_learning_environment() -> dict | None:
    return get_active_learning_environment()


@st.cache_data(ttl=45, show_spinner=False)
def _cached_cms_lessons() -> list[dict]:
    return list_cms_lessons()


@st.cache_data(ttl=45, show_spinner=False)
def _cached_cms_tools() -> list[dict]:
    return list_cms_tools()


@st.cache_data(ttl=45, show_spinner=False)
def _cached_cms_stories() -> list[dict]:
    return list_cms_stories()


@st.cache_data(ttl=45, show_spinner=False)
def _cached_cms_library_resources() -> list[dict]:
    return list_cms_library_resources()


@st.cache_data(ttl=60, show_spinner=False)
def _cached_resource_files(scope_type: str | None = None, scope_id: str | None = None, include_archived: bool = False) -> list[dict]:
    return list_cms_resource_files(scope_type, scope_id, include_archived=include_archived)


@st.cache_data(ttl=300, show_spinner=False)
def _cached_resource_file(resource_id: str) -> dict | None:
    return get_cms_resource_file(resource_id)


@st.cache_data(ttl=45, show_spinner=False)
def _cached_content_revisions() -> list[dict]:
    return list_content_revisions(120)


def _clear_content_studio_caches() -> None:
    _cached_cms_modules.clear()
    _cached_learning_environment.clear()
    _cached_cms_lessons.clear()
    _cached_cms_tools.clear()
    _cached_cms_stories.clear()
    _cached_cms_library_resources.clear()
    _cached_resource_files.clear()
    _cached_resource_file.clear()
    _cached_content_revisions.clear()
    _published_carousels.clear()
    try:
        _all_tools_zip_cached.clear()
    except NameError:
        pass


def _save_progress(*args, **kwargs) -> None:
    save_topic_progress(*args, **kwargs)
    _cached_progress.clear()


def _save_quiz(*args, **kwargs) -> None:
    save_quiz_result(*args, **kwargs)
    _cached_quiz_results.clear()


def _save_profile(*args, **kwargs) -> None:
    update_user_profile(*args, **kwargs)
    _cached_user_record.clear()


def _save_account_role(user_id: str, account_role: str) -> None:
    set_account_role(user_id, account_role)
    _cached_user_record.clear()
    _cached_users.clear()


def _record_privacy_acceptance(user_id: str) -> None:
    record_privacy_acceptance(user_id, PRIVACY_POLICY_VERSION)
    _cached_user_record.clear()
    _cached_users.clear()


def _delete_account_data(user_id: str) -> None:
    delete_user_account(user_id)
    _cached_user_record.clear()
    _cached_progress.clear()
    _cached_quiz_results.clear()
    _cached_community_posts.clear()
    _clear_community_interaction_caches()
    _cached_users.clear()

st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Poppins:ital,wght@0,400;0,500;0,600;0,700;1,400&display=swap');

:root {
    --m-grey: #3c3c3b;
    --m-blue: #0d4f9e;
    --m-cyan: #88cdd3;
    --m-green: #156950;
    --m-lime: #a2ab20;
    --m-ochre: #bc8a27;
    --m-wine: #9c2438;
    --m-paper: #ffffff;
    --m-soft: #f6f6f4;
    --m-line: #deded9;
    --m-muted: #666663;
    --m-blue-10: #edf2f8;
    --m-cyan-10: #f1fafb;
    --m-green-10: #edf5f2;
    --m-lime-10: #f6f7eb;
    --m-ochre-10: #faf5ea;
    --m-wine-10: #f8eef0;
}

html, body, [class*="css"] { font-family: Poppins, "Segoe UI", Arial, sans-serif; color: var(--m-grey); }
[data-testid="stHeader"] {
    background: rgba(255,255,255,.97);
    border-bottom: 1px solid #ecece8;
}
[data-testid="stHeader"] [data-testid="stToolbar"] { visibility: visible; }
.block-container {
    width: min(100%, 1520px);
    max-width: 1520px;
    padding: 5.25rem clamp(1.25rem, 3.2vw, 3.75rem) 5rem;
}
[data-testid="stSidebar"] { border-right: 1px solid var(--m-line); background:#fbfbfa; }
[data-testid="stSidebar"] [data-testid="stButton"] button { justify-content: flex-start; }

/* MOSAIC interaction system: wine for every clickable action; green remains reserved for success/completion. */
.stButton, [data-testid="stFormSubmitButton"], [data-testid="stLinkButton"], .stDownloadButton { margin:.38rem 0 .72rem; }
.stButton > button,
[data-testid="stFormSubmitButton"] > button,
[data-testid="stLinkButton"] > a,
.stDownloadButton > button {
    border-radius:999px !important;
    font-family:inherit !important;
    font-weight:600 !important;
    min-height:2.75rem;
    transition:background-color .16s ease, border-color .16s ease, color .16s ease, transform .16s ease;
}
.stButton > button[kind="primary"],
[data-testid="stFormSubmitButton"] > button[kind="primary"] {
    background:var(--m-wine) !important;
    border-color:var(--m-wine) !important;
    color:#fff !important;
}
.stButton > button[kind="primary"]:hover,
[data-testid="stFormSubmitButton"] > button[kind="primary"]:hover {
    background:#7e1d2e !important;
    border-color:#7e1d2e !important;
}
.stButton > button[kind="secondary"],
[data-testid="stFormSubmitButton"] > button[kind="secondary"] {
    background:#fff !important;
    border-color:var(--m-wine) !important;
    color:var(--m-wine) !important;
}
.stButton > button[kind="secondary"]:hover,
[data-testid="stFormSubmitButton"] > button[kind="secondary"]:hover {
    background:var(--m-wine-10) !important;
    border-color:var(--m-wine) !important;
    color:var(--m-wine) !important;
}
.stButton > button:focus-visible,
[data-testid="stFormSubmitButton"] > button:focus-visible,
[data-testid="stLinkButton"] > a:focus-visible,
.stDownloadButton > button:focus-visible {
    outline:3px solid rgba(156,36,56,.24) !important;
    outline-offset:2px;
}
.stButton > button:disabled, [data-testid="stFormSubmitButton"] > button:disabled {
    background:#f0f0ed !important; border-color:#deded9 !important; color:#8b8b87 !important; opacity:1 !important;
}
[data-testid="stLinkButton"] > a, .stDownloadButton > button {
    background:#fff !important; border:1px solid var(--m-wine) !important; color:var(--m-wine) !important; text-decoration:none !important;
}
[data-testid="stLinkButton"] > a:hover, .stDownloadButton > button:hover {
    background:var(--m-wine-10) !important; color:var(--m-wine) !important;
}
/* Keep native Streamlit selection states in the MOSAIC palette instead of the default pink/red. */
[data-baseweb="tab"][aria-selected="true"] { color:var(--m-wine) !important; }
[data-baseweb="tab-highlight"] { background-color:var(--m-wine) !important; }
[data-testid="stSegmentedControl"] button[aria-pressed="true"] { background:var(--m-wine-10) !important; color:var(--m-wine) !important; border-color:var(--m-wine) !important; }
[data-testid="stProgress"] [role="progressbar"] > div {background-color: var(--m-blue-10) !important;}
[data-testid="stProgress"] [role="progressbar"] > div > div {background-color: var(--m-blue) !important;}
[data-baseweb="tab-list"] { gap:.25rem; }
[data-baseweb="tab"] { font-family:inherit; font-weight:600; }

.m-kicker { text-transform:uppercase; letter-spacing:.11em; font-size:.72rem; color:var(--m-wine); font-weight:700; }
.m-muted { color:var(--m-muted); }
.m-small { font-size:.86rem; }

.m-brandbar { display:flex; align-items:center; justify-content:space-between; gap:1rem; border-bottom:1px solid var(--m-grey); padding:.2rem 0 .75rem; margin-bottom:1.2rem; }
.m-brand-home { display:inline-flex; align-items:center; gap:.7rem; min-height:44px; padding:.2rem .35rem .2rem 0; border-radius:10px; color:var(--m-grey) !important; text-decoration:none !important; font-weight:700; font-size:1.02rem; letter-spacing:.01em; }
.m-brand-home:hover { color:var(--m-wine) !important; }
.m-brand-home:focus-visible { outline:3px solid rgba(156,36,56,.24); outline-offset:3px; }
.m-brand-logo { display:block; width:auto; height:42px; max-width:190px; object-fit:contain; object-position:left center; }
.m-brand-learn { padding-left:.7rem; border-left:1px solid var(--m-line); font-weight:400; white-space:nowrap; }
.m-brand-home.sidebar { margin:.1rem 0 .4rem; padding-right:.2rem; }
.m-brand-home.sidebar .m-brand-logo { height:auto; max-height:52px; max-width:178px; }
.m-brandtag { color:var(--m-muted); font-size:.78rem; text-align:right; }
.m-mini-mark { width:34px; height:34px; display:grid; grid-template-columns:repeat(3,1fr); grid-template-rows:repeat(3,1fr); gap:2px; border-radius:7px; overflow:hidden; transform:rotate(-1deg); }
.m-mini-mark i:nth-child(1){background:var(--m-grey)} .m-mini-mark i:nth-child(2){background:var(--m-ochre)} .m-mini-mark i:nth-child(3){background:var(--m-cyan)}
.m-mini-mark i:nth-child(4){background:var(--m-blue)} .m-mini-mark i:nth-child(5){background:var(--m-lime)} .m-mini-mark i:nth-child(6){background:var(--m-green)}
.m-mini-mark i:nth-child(7){background:var(--m-green)} .m-mini-mark i:nth-child(8){background:var(--m-wine)} .m-mini-mark i:nth-child(9){background:var(--m-lime)}
.m-sidebar-wordmark { display:flex; align-items:center; gap:.65rem; margin:.15rem 0 .3rem; }
.m-sidebar-wordmark strong { letter-spacing:.02em; font-size:1.08rem; }
.m-sidebar-wordmark span { font-weight:400; }

.m-hero { border:1px solid var(--m-line); border-radius:24px; overflow:hidden; background:white; display:grid; grid-template-columns:minmax(0,1.35fr) minmax(260px,.65fr); margin-bottom:1.4rem; }
.m-hero-copy { padding:clamp(1.6rem,4vw,3.4rem); }
.m-hero h1 { max-width:760px; margin:.45rem 0 .8rem; font-size:clamp(2.15rem,5vw,4rem); line-height:1.02; letter-spacing:-.035em; color:var(--m-grey); }
.m-hero p { max-width:730px; color:#565653; font-size:1.03rem; line-height:1.72; }
.m-hero-meta { display:flex; flex-wrap:wrap; gap:.5rem; margin-top:1.15rem; }
.m-chip { display:inline-flex; align-items:center; border:1px solid var(--m-line); border-radius:999px; padding:.32rem .7rem; background:#fff; font-size:.78rem; font-weight:600; }
.m-hero-art { position:relative; min-height:330px; background:var(--m-soft); overflow:hidden; }
.m-shard { position:absolute; border-radius:18px; }
.m-shard.s1 { background:var(--m-cyan); width:46%; height:29%; left:4%; top:6%; clip-path:polygon(7% 0,100% 0,91% 86%,34% 100%,0 57%); }
.m-shard.s2 { background:var(--m-blue); width:36%; height:42%; right:3%; top:4%; clip-path:polygon(18% 0,100% 9%,94% 100%,0 86%,10% 35%); }
.m-shard.s3 { background:var(--m-green); width:54%; height:31%; left:1%; bottom:8%; clip-path:polygon(0 16%,84% 0,100% 71%,63% 100%,10% 88%); }
.m-shard.s4 { background:var(--m-ochre); width:30%; height:47%; left:42%; top:36%; clip-path:polygon(17% 0,100% 10%,83% 100%,0 86%); }
.m-shard.s5 { background:var(--m-lime); width:29%; height:24%; right:2%; bottom:4%; clip-path:polygon(0 6%,100% 0,89% 100%,15% 86%); }
.m-shard.s6 { background:var(--m-wine); width:18%; height:28%; left:61%; bottom:0; clip-path:polygon(11% 0,100% 17%,63% 100%,0 76%); }
.m-shard.s7 { background:var(--m-grey); width:20%; height:18%; left:1%; top:0; clip-path:polygon(0 0,100% 0,61% 100%,0 67%); }

[class*="st-key-ground_story"] { margin:1.65rem 0 2.35rem; padding:clamp(1.2rem,3vw,2rem); border:1px solid #d7dfda; border-radius:24px; background:linear-gradient(135deg,#f2f7f4 0%,#fff 58%,#faf5ea 100%); box-shadow:0 8px 24px rgba(33,72,58,.05); overflow:hidden; }
[class*="st-key-ground_story"] [data-testid="stHorizontalBlock"] { align-items:center; }
.m-ground-story-copy { padding:.2rem .2rem .2rem 0; }
.m-ground-story-copy h2 { margin:.42rem 0 .7rem; font-size:clamp(1.6rem,3vw,2.35rem); line-height:1.08; letter-spacing:-.025em; }
.m-ground-story-copy p { margin:.35rem 0; color:#555b57; line-height:1.7; font-size:.96rem; }
.m-ground-story-note { display:inline-flex; align-items:center; gap:.4rem; margin-top:.85rem; padding:.3rem .65rem; border:1px solid #d5dfd9; border-radius:999px; background:rgba(255,255,255,.84); color:var(--m-green); font-size:.74rem; font-weight:700; }

.m-ground-story-action { margin-top:.85rem; }
.m-story-hero { max-width:850px; margin:.45rem 0 1.35rem; }
.m-story-hero h1 { margin:.35rem 0 .55rem; font-size:clamp(2rem,4vw,3.25rem); line-height:1.05; letter-spacing:-.035em; }
.m-story-hero p { margin:0; max-width:70ch; color:var(--m-muted); line-height:1.65; }
.m-story-card { border:1px solid var(--m-line); border-radius:20px; background:#fff; padding:1.1rem 1.15rem; height:100%; box-sizing:border-box; }
.m-story-card .place { color:var(--m-green); font-size:.7rem; font-weight:800; text-transform:uppercase; letter-spacing:.08em; }
.m-story-card h3 { margin:.45rem 0 .45rem; font-size:1.08rem; line-height:1.3; }
.m-story-card p { margin:0; color:var(--m-muted); font-size:.86rem; line-height:1.55; }
/* Story previews occupy equal-height tiles even though each has a separate Streamlit button. */
.m-story-card {
    height: 235px !important;
    min-height: 235px;
    padding: 1.3rem 1.4rem;
    display: flex;
    flex-direction: column;
    gap: .45rem;
    overflow: hidden;
}
.m-story-card h3 {
    margin: .1rem 0 .1rem;
    line-height: 1.32;
    display: -webkit-box;
    -webkit-line-clamp: 3;
    -webkit-box-orient: vertical;
    overflow: hidden;
}
.m-story-card p {
    display: -webkit-box;
    -webkit-line-clamp: 5;
    -webkit-box-orient: vertical;
    overflow: hidden;
    line-height: 1.55;
}
@media (max-width: 740px) {
    .m-story-card { height: 250px !important; min-height: 250px; }
}
.m-story-detail { margin:1.4rem 0 2rem; padding:clamp(1.2rem,3vw,2rem); border:1px solid var(--m-line); border-radius:22px; background:linear-gradient(180deg,#fff 0%,#fbfbf8 100%); }
.m-story-detail .place { color:var(--m-green); font-size:.72rem; font-weight:800; text-transform:uppercase; letter-spacing:.085em; }
.m-story-detail h2 { margin:.45rem 0 1rem; max-width:31ch; font-size:clamp(1.65rem,3vw,2.35rem); line-height:1.12; letter-spacing:-.025em; }
.m-story-detail h3 { margin:1.35rem 0 .45rem; font-size:1.2rem; }
.m-story-detail p { max-width:76ch; color:#4f5550; line-height:1.72; }
.m-story-lesson { margin:1.35rem 0 .7rem; padding:1rem 1.1rem; border-left:4px solid var(--m-green); background:var(--m-green-10); border-radius:0 14px 14px 0; font-weight:700; line-height:1.55; }
.m-story-source { margin-top:.75rem; font-size:.8rem; color:var(--m-muted); }
.m-story-source a { color:var(--m-blue) !important; text-decoration:none !important; font-weight:700; }
.m-story-source a:hover { text-decoration:underline !important; }

[class*="st-key-catalogue_starting_guide"] { margin:2.8rem 0 1.2rem; padding:clamp(1.25rem,3vw,2.25rem); border:1px solid var(--m-line); border-radius:24px; background:linear-gradient(145deg,#fbfbf8 0%,#f4f5ef 100%); }
[class*="st-key-catalogue_starting_guide"] .m-start-question { margin:1.8rem 0 .8rem; padding-top:1.3rem; border-top:1px solid var(--m-line); text-align:left; max-width:none; }
[class*="st-key-catalogue_starting_guide"] .m-start-question h3 { font-size:1.45rem; }
[class*="st-key-catalogue_start_choice_"] { height:100%; padding:1rem; border:1px solid var(--m-line); border-radius:17px; background:#fff; display:flex; flex-direction:column; }
[class*="st-key-catalogue_start_choice_"] .m-start-choice { min-height:138px; padding:0; margin:0 0 .65rem; border:0; border-radius:0; background:transparent; }
[class*="st-key-catalogue_start_choice_"] [data-testid="stButton"] { margin-top:auto; }
[class*="st-key-catalogue_start_choice_drivers"] { border-top:5px solid var(--m-blue); }
[class*="st-key-catalogue_start_choice_policy-lab"] { border-top:5px solid var(--m-green); }
[class*="st-key-catalogue_start_choice_future-pathways"] { border-top:5px solid var(--m-ochre); }
[class*="st-key-ground_story"] [data-testid="stVideo"] { border-radius:18px; overflow:hidden; box-shadow:0 10px 28px rgba(31,55,46,.12); background:#111; }

.m-section-title { margin:2.1rem 0 .8rem; }
.m-section-title h2 { margin:0; font-size:1.48rem; letter-spacing:-.02em; }
.m-section-title p { margin:.3rem 0 0; color:var(--m-muted); }

.m-track-card, .m-module-card, .m-mode-card, .m-resource-card, .m-example-card, .m-evidence-card { border:1px solid var(--m-line); background:#fff; }
.m-track-card { border-radius:18px; padding:1.25rem; min-height:205px; border-top:5px solid var(--m-blue); margin-bottom:.7rem; display:flex; flex-direction:column; box-sizing:border-box; }
.m-track-card.community { border-top-color:var(--m-green); } .m-track-card.learning { border-top-color:var(--m-blue); } .m-track-card.empowerment { border-top-color:var(--m-ochre); }
.m-track-icon { width:42px; height:42px; display:flex; align-items:center; justify-content:center; border-radius:13px; font-size:1.35rem; margin-bottom:1rem; background:var(--m-blue-10); color:var(--m-blue); }
.m-track-card.community .m-track-icon { background:var(--m-green-10); color:var(--m-green); } .m-track-card.empowerment .m-track-icon { background:var(--m-ochre-10); color:#8f671a; }
.m-track-card h3 { margin:.05rem 0 .5rem; font-size:1.18rem; letter-spacing:-.015em; }
.m-track-card p { color:var(--m-muted); margin:0; line-height:1.58; font-size:.9rem; flex:1; }

.m-module-card { border-radius:20px; overflow:hidden; height:420px; margin-bottom:.7rem; display:flex; flex-direction:column; box-sizing:border-box; }
.m-module-card .m-module-art { flex:0 0 145px; }
.m-module-art.has-cover { border-top:0; background:#e8eff0; }
.m-module-art.has-cover:before,.m-module-art.has-cover:after { display:none; }
.m-module-art.has-cover img { width:100%; height:100%; display:block; object-fit:cover; object-position:center; }
.m-module-card .m-module-body { flex:1; display:flex; flex-direction:column; min-height:0; }
.m-module-art { height:145px; position:relative; overflow:hidden; background:#f6f6f3; }
.m-module-art:before, .m-module-art:after { content:""; position:absolute; border-radius:15px; transform:rotate(-8deg); }
.m-module-art:before { width:42%; height:120%; right:11%; top:-30%; }
.m-module-art:after { width:31%; height:80%; right:-4%; bottom:-20%; }
.m-module-art.learning { border-top:7px solid var(--m-blue); } .m-module-art.learning:before{background:var(--m-cyan)} .m-module-art.learning:after{background:var(--m-blue)}
.m-module-art.community { border-top:7px solid var(--m-green); } .m-module-art.community:before{background:var(--m-green)} .m-module-art.community:after{background:var(--m-lime)}
.m-module-art.empowerment { border-top:7px solid var(--m-ochre); } .m-module-art.empowerment:before{background:var(--m-ochre)} .m-module-art.empowerment:after{background:var(--m-wine)}
.m-module-body { padding:1.05rem 1.1rem 1rem; }
.m-module-body h3 { margin:.45rem 0; font-size:1.2rem; line-height:1.23; }
.m-module-body p { color:var(--m-muted); font-size:.88rem; line-height:1.55; min-height:68px; flex:1; }
.m-module-meta { display:flex; gap:.45rem; flex-wrap:wrap; margin-top:auto; padding-top:.65rem; color:var(--m-muted); font-size:.78rem; }
.m-status { display:inline-block; font-size:.7rem; padding:.22rem .55rem; border-radius:999px; font-weight:700; }
.m-status.available { background:var(--m-green-10); color:var(--m-green); } .m-status.soon { background:#efefec; color:#73736f; }

.m-start-guide { margin:2.8rem 0 1.2rem; padding:clamp(1.25rem,3vw,2.25rem); border:1px solid var(--m-line); border-radius:24px; background:linear-gradient(145deg,#fbfbf8 0%,#f4f5ef 100%); }
.m-start-intro { display:grid; grid-template-columns:minmax(0,1.05fr) minmax(250px,.95fr); gap:clamp(1rem,3vw,2.5rem); align-items:center; }
.m-start-copy h2 { margin:.4rem 0 .65rem; font-size:clamp(1.65rem,3vw,2.35rem); line-height:1.08; letter-spacing:-.025em; }
.m-start-copy p { margin:.45rem 0; max-width:680px; color:#555552; line-height:1.68; }
.m-start-copy .m-start-reflection { margin-top:1rem; color:var(--m-grey); font-weight:600; }
.m-start-image { display:flex; align-items:center; justify-content:center; min-height:220px; }
.m-start-image img { display:block; width:100%; max-width:520px; max-height:270px; object-fit:contain; }
.m-start-question { max-width:760px; margin:1.8rem auto 1rem; text-align:center; }
.m-start-question h3 { margin:0 0 .35rem; font-size:1.35rem; letter-spacing:-.015em; }
.m-start-question p { margin:0; color:var(--m-muted); line-height:1.55; }
.m-start-choice { min-height:168px; box-sizing:border-box; display:flex; flex-direction:column; padding:1.1rem; margin-bottom:.65rem; border:1px solid var(--m-line); border-top:5px solid var(--m-blue); border-radius:17px; background:#fff; }
.m-start-choice.community { border-top-color:var(--m-green); }
.m-start-choice.learning { border-top-color:var(--m-blue); }
.m-start-choice.empowerment { border-top-color:var(--m-ochre); }
.m-start-choice .m-start-icon { margin-bottom:.65rem; color:var(--m-wine); font-size:1.15rem; }
.m-start-choice h4 { margin:0 0 .4rem; font-size:1rem; line-height:1.4; }
.m-start-choice p { flex:1; margin:0; color:var(--m-muted); font-size:.84rem; line-height:1.5; }
.m-start-recommendation { margin:1.35rem 0 .8rem; padding:1.25rem 1.35rem; border:1px solid #c7d8e9; border-left:5px solid var(--m-blue); border-radius:18px; background:var(--m-blue-10); }
.m-start-recommendation h3 { margin:.25rem 0 .4rem; font-size:1.35rem; }
.m-start-recommendation p { margin:.25rem 0; max-width:880px; line-height:1.6; }
.m-start-recommendation .m-module-meta { margin-top:.7rem; }

.m-reference-intro { max-width:900px; margin:.35rem 0 1.35rem; color:var(--m-muted); line-height:1.65; }
.m-glossary-card { box-sizing:border-box; min-height:205px; margin:0 0 .8rem; padding:1.05rem 1.1rem; border:1px solid var(--m-line); border-top:4px solid var(--m-blue); border-radius:16px; background:#fff; }
.m-glossary-card h3 { margin:.05rem 0 .55rem; font-size:1.03rem; line-height:1.35; }
.m-glossary-card .label { margin-bottom:.35rem; color:var(--m-wine); font-size:.67rem; font-weight:700; letter-spacing:.09em; text-transform:uppercase; }
.m-glossary-card p { margin:0; color:#555552; font-size:.86rem; line-height:1.58; }
.m-contact-card { box-sizing:border-box; min-height:100%; padding:1.25rem; border:1px solid var(--m-line); border-radius:18px; background:#fff; }
.m-contact-card h2 { margin:.05rem 0 .55rem; font-size:1.3rem; }
.m-contact-card > p { margin:.2rem 0 1rem; color:var(--m-muted); line-height:1.6; }
.m-contact-group { margin-top:1.1rem; padding-top:1rem; border-top:1px solid var(--m-line); }
.m-contact-group:first-of-type { margin-top:.7rem; }
.m-contact-group h3 { margin:0 0 .55rem; font-size:.98rem; }
.m-contact-person { margin:.55rem 0; }
.m-contact-person strong { display:block; }
.m-contact-person a { color:var(--m-blue) !important; text-decoration:none; }
.m-contact-person a:hover { text-decoration:underline; }
.m-contact-person span { color:var(--m-muted); font-size:.83rem; }
.m-credits { margin:1.6rem 0 .5rem; padding:1.2rem 1.3rem; border-left:5px solid var(--m-ochre); border-radius:0 16px 16px 0; background:var(--m-ochre-10); }
.m-credits h2 { margin:.1rem 0 .65rem; font-size:1.25rem; }
.m-credits h3 { margin:1rem 0 .25rem; font-size:.95rem; }
.m-credits p { margin:.25rem 0; line-height:1.6; }

.m-progress-shell { height:8px; border-radius:999px; background:#ededE8; overflow:hidden; margin:.55rem 0 .15rem; }
.m-progress-fill { height:100%; border-radius:999px; background:var(--m-green); }

.m-module-hero { position:relative; overflow:hidden; border-radius:22px; border:1px solid var(--m-line); background:white; padding:clamp(1.45rem,4vw,2.8rem); margin:.35rem 0 1.2rem; }
.m-module-hero:after { content:""; position:absolute; width:260px; height:260px; right:-88px; top:-98px; border-radius:42% 58% 61% 39% / 35% 44% 56% 65%; opacity:.13; }
.m-module-hero.community:after{background:var(--m-green)} .m-module-hero.learning:after{background:var(--m-blue)} .m-module-hero.empowerment:after{background:var(--m-ochre)}
.m-module-hero h1 { max-width:850px; margin:.4rem 0 .65rem; font-size:clamp(1.85rem,4vw,3.1rem); line-height:1.07; letter-spacing:-.03em; }
.m-module-hero p { max-width:790px; color:#555552; line-height:1.68; }

.m-mode-card { border-radius:18px; padding:1.05rem; min-height:176px; margin-bottom:.7rem; }
.m-mode-card.understand { border-top:5px solid var(--m-blue); } .m-mode-card.apply { border-top:5px solid var(--m-green); } .m-mode-card.convince { border-top:5px solid var(--m-wine); background:linear-gradient(180deg,#fff,var(--m-wine-10)); }
.m-mode-num { color:var(--m-muted); font-size:.7rem; letter-spacing:.1em; }
.m-mode-card h3 { margin:.35rem 0 .35rem; font-size:1.13rem; }
.m-mode-card p { color:var(--m-muted); font-size:.87rem; line-height:1.55; margin:0; }
.m-mode-note { display:inline-block; margin-top:.7rem; padding:.23rem .5rem; border-radius:999px; background:#f1f1ee; font-size:.7rem; font-weight:600; }

.m-phase-header { display:grid; grid-template-columns:52px minmax(0,1fr) auto; gap:1rem; align-items:center; margin:.25rem 0 1rem; padding-bottom:.9rem; border-bottom:1px solid var(--m-line); }
.m-phase-number { width:46px; height:46px; border-radius:14px; display:flex; align-items:center; justify-content:center; font-size:.74rem; font-weight:700; color:var(--m-wine); letter-spacing:.08em; background:var(--m-wine-10); }
.m-phase-header h3 { margin:0; font-size:1.3rem; letter-spacing:-.015em; }
.m-phase-header p { margin:.22rem 0 0; color:var(--m-muted); font-size:.87rem; }
.m-phase-progress { white-space:nowrap; border:1px solid var(--m-line); border-radius:999px; padding:.3rem .65rem; color:var(--m-muted); background:#fff; font-size:.73rem; font-weight:600; }
[class*="st-key-path_phase_"] { border:1px solid var(--m-line); border-radius:22px; padding:1.2rem 1.25rem .9rem; margin:1rem 0 1.25rem; background:linear-gradient(180deg,#fbfbfa 0%,#f7f7f4 100%); }
[class*="st-key-path_step_"] { border:1px solid var(--m-line) !important; border-radius:17px !important; padding:.78rem .9rem !important; background:#fff !important; margin:.65rem 0 !important; box-shadow:0 2px 7px rgba(60,60,59,.025); }
[class*="st-key-path_step_"] [data-testid="stHorizontalBlock"] { align-items:center; min-height:76px; }
[class*="st-key-path_step_"] [data-testid="stMarkdown"] { margin:0; }
[class*="st-key-path_step_"] [data-testid="stButton"] { margin:0; }
[class*="st-key-path_step_"] [data-testid="stButton"] button { margin:0; white-space:nowrap; }
.m-path-copy { min-height:68px; display:flex; flex-direction:column; justify-content:center; gap:.22rem; padding:.1rem 0; box-sizing:border-box; }
.m-path-copy .meta { color:var(--m-wine); text-transform:uppercase; letter-spacing:.08em; font-size:.67rem; line-height:1.3; font-weight:700; margin:0 !important; }
.m-path-copy h4 { margin:0 !important; font-size:1rem; line-height:1.35; }
.m-path-copy p { margin:0 !important; color:var(--m-muted); font-size:.82rem; line-height:1.48; }
.m-lesson-row { display:grid; grid-template-columns:44px minmax(0,1fr) auto; gap:.85rem; align-items:center; border:1px solid var(--m-line); border-radius:15px; padding:.86rem .95rem; background:#fff; margin:.5rem 0; }
.m-lesson-state { width:34px; height:34px; border-radius:999px; display:flex; align-items:center; justify-content:center; border:1px solid var(--m-line); font-weight:700; }
.m-lesson-state.done { background:var(--m-green-10); border-color:#b9d5c9; color:var(--m-green); }
.m-lesson-row h4 { margin:0 0 .12rem; font-size:.98rem; } .m-lesson-row p { margin:0; color:var(--m-muted); font-size:.82rem; line-height:1.45; } .m-lesson-time { color:var(--m-muted); font-size:.78rem; white-space:nowrap; }

.m-outcomes { border-left:4px solid var(--m-wine); padding:.1rem 0 .1rem 1rem; margin:1rem 0; } .m-outcomes li { margin:.33rem 0; }
.m-role-callout { border-radius:15px; border:1px solid #c7d8e9; background:var(--m-blue-10); padding:.95rem 1rem; margin:1rem 0; } .m-role-callout strong { color:var(--m-blue); }
.m-building-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:.65rem; margin:1rem 0 1.35rem; }
.m-building-card { border:1px solid var(--m-line); border-radius:15px; padding:.95rem; background:white; min-height:116px; border-top:4px solid var(--m-green); }
.m-building-card .num { font-size:.7rem; letter-spacing:.08em; color:var(--m-wine); font-weight:700; } .m-building-card b { display:block; margin:.3rem 0 .2rem; } .m-building-card span { font-size:.81rem; color:var(--m-muted); line-height:1.45; }
.m-route-card { border:1px solid var(--m-line); border-radius:15px; padding:.95rem 1rem; background:#fff; margin:.65rem 0; } .m-route-card h4 { margin:.1rem 0 .2rem; } .m-route-card p { margin:0; color:var(--m-muted); font-size:.87rem; line-height:1.5; }

.m-lesson-hero { width:100%; max-width:1360px; margin:1rem auto .9rem; padding:.8rem 0 .45rem; }
.m-lesson-hero h1 { max-width:980px; font-size:clamp(1.9rem,3.5vw,3rem); line-height:1.1; letter-spacing:-.03em; margin:.4rem 0 .6rem; }
.m-lesson-hero p { max-width:78ch; color:var(--m-muted); font-size:1rem; line-height:1.72; }
.m-reading { width:100%; max-width:1360px; margin:0 auto; font-size:1.03rem; line-height:1.8; }
.m-reading-intro { width:100%; max-width:1360px; margin:1.2rem auto .75rem; }
.m-reading-intro h3 { margin:0 0 .28rem; font-size:1.18rem; letter-spacing:-.015em; }
.m-reading-intro p { max-width:76ch; margin:0; color:var(--m-muted); font-size:.91rem; line-height:1.62; }

/* Wide visual stage, narrow readable text: the panel fills the page while line length remains comfortable. */
.m-theory-wrap { width:100%; max-width:none; margin:.45rem 0 0; }
.m-theory-card {
    width:100%; box-sizing:border-box; border:1px solid var(--m-line); border-radius:24px;
    padding:clamp(1.7rem,3.2vw,3rem) clamp(1.4rem,3.8vw,3.5rem);
    background:linear-gradient(180deg,#fff 0%,#fcfcfb 100%); min-height:300px;
    display:flex; align-items:center; border-top:7px solid var(--m-blue);
    box-shadow:0 2px 8px rgba(60,60,59,.035);
}
.m-theory-inner { width:100%; max-width:920px; margin:0 auto; }
/* A figure is stacked UNDER its text, within the same bordered card. */
.m-theory-card.has-idea-image { display:flex; flex-direction:column; align-items:stretch; min-height:0; }
.m-theory-card.has-idea-image .m-theory-inner { max-width:920px; width:100%; margin:0 auto; padding:0; }
.m-idea-media { background:var(--m-soft); overflow:hidden; }
.m-image-below-card { width:100%; max-width:920px; margin:1.35rem auto 0; min-height:0; padding:0; border-radius:14px; }
.m-image-below-card img { width:100%; height:auto; max-height:560px; min-height:0; object-fit:contain; display:block; border-radius:14px; }
.m-rich-text blockquote { margin:1rem 0; padding:1rem 1.2rem; background:#f6f7f8; border-left:3px solid var(--m-cyan); border-radius:9px; }
.m-theory-label { text-transform:uppercase; letter-spacing:.11em; font-size:.72rem; color:var(--m-wine); font-weight:700; }
.m-theory-card h3 { max-width:30ch; margin:.72rem 0 .9rem; font-size:clamp(1.65rem,2.7vw,2.3rem); line-height:1.2; letter-spacing:-.025em; }
.m-theory-card p { max-width:76ch; margin:0; font-size:1.05rem; line-height:1.82; color:#4b4b48; }
.m-theory-card ul { max-width:74ch; margin:1rem 0 0 1.2rem; color:#4b4b48; line-height:1.7; }
.m-theory-card li { margin:.42rem 0; }
.m-rich-text p + p { margin-top:.8rem; }
.m-rich-text blockquote { max-width:72ch; margin:1rem 0; padding:.25rem 0 .25rem 1rem; border-left:4px solid var(--m-cyan); color:#535b5e; }
.m-rich-text a { color:var(--m-blue); text-underline-offset:2px; }
/* Native Superhuman Docs tables: readable, accessible, and scrollable on phones. */
.m-rich-text .m-import-table-wrap {
    width:100%; max-width:100%; overflow-x:auto; margin:1.2rem 0 1.35rem;
    border:1px solid #dedfdf; border-radius:12px;
    scrollbar-width:thin;
}
.m-rich-text .m-import-table {
    border-collapse:collapse; width:100%; min-width:440px;
    font-size:.97rem; line-height:1.5; color:#373e43;
}
.m-rich-text .m-import-table th,
.m-rich-text .m-import-table td {
    padding:.85rem 1rem; text-align:left; vertical-align:top;
    border-bottom:1px solid #e5e7e7; overflow-wrap:anywhere;
}
.m-rich-text .m-import-table th {
    color:var(--m-blue); font-weight:650; background:#eef4fa;
}
.m-rich-text .m-import-table tr:nth-child(even) td { background:#fafbfb; }
.m-rich-text .m-import-table tbody tr:last-child td { border-bottom:0; }
@media (max-width:650px) {
    .m-rich-text .m-import-table th,
    .m-rich-text .m-import-table td { padding:.7rem .8rem; }
}
.m-theory-progress { display:flex; gap:.42rem; width:min(380px,58%); margin:0 auto .95rem; }
.m-theory-dot { height:6px; flex:1; border-radius:999px; background:#e5e5e0; }
.m-theory-dot.active { background:var(--m-blue); }
.m-theory-card.synthesis { align-items:stretch; min-height:380px; }
.m-synthesis-inner { width:100%; max-width:1040px; margin:0 auto; }
.m-key-idea-panel { border-left:5px solid var(--m-lime); border-radius:0 16px 16px 0; background:var(--m-lime-10); padding:1rem 1.15rem; margin:.8rem 0 1.05rem; }
.m-key-idea-panel p { margin:.3rem 0 0; font-size:1.02rem; line-height:1.65; color:#424a3d; }
.m-takeaway-list ul { padding-left:1.3rem; margin:.6rem 0; font-size:1.03rem; line-height:1.8; }
.m-practice-feature { display:grid; grid-template-columns:minmax(0,1fr) minmax(210px,34%); border:1px solid #e0cea9; border-radius:18px; overflow:hidden; background:var(--m-ochre-10); }
.m-practice-feature-copy { padding:1.15rem 1.25rem; align-self:center; }
.m-practice-feature-copy .label { color:#8f671a; font-size:.7rem; font-weight:700; letter-spacing:.1em; text-transform:uppercase; }
.m-practice-feature-copy p { margin:.45rem 0 0; font-size:.94rem; line-height:1.65; color:#554d3f; }
.m-practice-media { width:100%; min-height:180px; height:100%; object-fit:cover; display:block; }
.m-practice-pattern { position:relative; overflow:hidden; background:linear-gradient(145deg,var(--m-cyan),var(--m-blue)); }
.m-practice-pattern:before { content:""; position:absolute; width:72%; height:70%; right:-18%; top:-20%; border-radius:38% 62% 52% 48%; background:var(--m-ochre); transform:rotate(13deg); }
.m-practice-pattern:after { content:""; position:absolute; width:62%; height:66%; left:-18%; bottom:-28%; border-radius:58% 42% 37% 63%; background:var(--m-green); transform:rotate(-16deg); }
.m-practice-pattern span { position:absolute; z-index:1; left:1rem; bottom:.9rem; color:#fff; font-size:.72rem; font-weight:700; letter-spacing:.09em; text-transform:uppercase; }

.m-takeaway, .m-reflection, .m-practice-note, .m-tool-card, .m-driver-grid { width:100%; max-width:1360px; box-sizing:border-box; }
.m-takeaway { border-radius:18px; background:var(--m-lime-10); padding:1.2rem 1.4rem; margin:2rem auto 1.55rem; border:1px solid #dfe2bd; }
.m-takeaway strong { color:var(--m-green); }
.m-reflection { border-radius:18px; padding:1.2rem 1.35rem; border:1px solid var(--m-line); background:#fff; margin:2rem auto 1rem; }
.m-reflection .label { font-size:.7rem; text-transform:uppercase; letter-spacing:.1em; color:var(--m-wine); font-weight:700; }
.m-reflection p { max-width:78ch; margin:.45rem 0 0; font-weight:600; line-height:1.62; }
.m-practice-note { border-left:5px solid var(--m-ochre); border-radius:0 18px 18px 0; background:var(--m-ochre-10); padding:1.15rem 1.3rem; margin:1.65rem auto; }
.m-practice-note .label { text-transform:uppercase; letter-spacing:.09em; font-size:.68rem; font-weight:700; color:#8f671a; }
.m-practice-note p { max-width:80ch; margin:.45rem 0 0; line-height:1.67; }
.m-tool-card { border:1px solid #bfd6cc; border-radius:18px; background:var(--m-green-10); padding:1.15rem 1.3rem; margin:1.65rem auto; }
.m-tool-card .label { text-transform:uppercase; letter-spacing:.09em; font-size:.68rem; font-weight:700; color:var(--m-green); }
.m-tool-card h4 { margin:.42rem 0 .32rem; }
.m-tool-card p { max-width:80ch; margin:0; color:#4f5b56; line-height:1.62; }
.st-key-tool_action { width:100%; max-width:1360px; margin:-1rem auto 1.65rem; }
.m-tools-hero { border:1px solid #bfd6cc; border-radius:24px; padding:clamp(1.5rem,4vw,2.8rem); background:linear-gradient(120deg,var(--m-green-10),#fff 58%,var(--m-cyan-10)); border-top:7px solid var(--m-green); margin:.3rem 0 1.5rem; }
.m-tools-hero h1 { margin:.42rem 0 .65rem; font-size:clamp(2rem,4vw,3.25rem); line-height:1.08; letter-spacing:-.035em; }
.m-tools-hero p { max-width:780px; margin:0; color:var(--m-muted); line-height:1.7; }
.m-tool-library-card { border:1px solid var(--m-line); border-radius:19px; padding:1.2rem; background:#fff; min-height:225px; border-top:5px solid var(--m-green); }
.m-tool-library-card.drivers { border-top-color:var(--m-blue); }
.m-tool-library-card h3 { margin:.35rem 0 .45rem; font-size:1.12rem; letter-spacing:-.015em; }
.m-tool-library-card p { color:var(--m-muted); font-size:.87rem; line-height:1.58; min-height:4.15rem; }
.m-tool-meta { display:flex; flex-wrap:wrap; gap:.4rem; margin-top:.75rem; }
.m-tool-meta span { border:1px solid var(--m-line); border-radius:999px; padding:.28rem .58rem; font-size:.72rem; color:#575754; background:var(--m-soft); }
.m-tool-steps { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:.7rem; margin:1rem 0 1.4rem; }
.m-tool-step { border:1px solid var(--m-line); border-radius:16px; padding:1rem; background:#fff; }
.m-tool-step .num { color:var(--m-wine); font-weight:700; font-size:.78rem; letter-spacing:.08em; }
.m-tool-step p { color:var(--m-muted); font-size:.86rem; line-height:1.55; margin:.45rem 0 0; }
.m-tool-output { border-left:5px solid var(--m-lime); background:var(--m-lime-10); border-radius:0 16px 16px 0; padding:1rem 1.15rem; margin:.8rem 0 1.35rem; }
.m-tool-output strong { color:var(--m-green); }

[class*="st-key-quiz_card_"] { width:100%; max-width:1360px; box-sizing:border-box; border:1px solid #c7d8e9 !important; border-radius:22px !important; padding:1.25rem 1.35rem 1rem !important; margin:1.9rem auto 1.5rem !important; background:linear-gradient(135deg,var(--m-blue-10),#fff 62%) !important; box-shadow:0 4px 15px rgba(13,79,158,.045); }
.m-quiz-header { display:grid; grid-template-columns:44px minmax(0,1fr); gap:.85rem; align-items:center; margin-bottom:.75rem; }
.m-quiz-icon { width:42px; height:42px; border-radius:13px; display:flex; align-items:center; justify-content:center; background:var(--m-blue); color:#fff; font-size:1rem; font-weight:700; }
.m-quiz-header h3 { margin:.08rem 0 .18rem; font-size:1.18rem; letter-spacing:-.015em; }
.m-quiz-header p { margin:0; color:var(--m-muted); font-size:.82rem; line-height:1.45; }
[class*="st-key-quiz_card_"] [data-testid="stRadio"] { background:#fff; border:1px solid #d9e2eb; border-radius:15px; padding:.85rem 1rem; }
[class*="st-key-quiz_card_"] [data-testid="stRadio"] > label { margin-bottom:.35rem; }
[class*="st-key-quiz_card_"] [data-testid="stRadio"] > label p { font-size:.96rem; font-weight:600; line-height:1.5; }
.m-quiz-status { display:inline-flex; align-items:center; gap:.35rem; border-radius:999px; padding:.34rem .68rem; margin:.3rem 0 .15rem; font-size:.76rem; font-weight:700; }
.m-quiz-status.pass { color:var(--m-green); background:var(--m-green-10); border:1px solid #bfd6cc; }
.m-quiz-status.retry { color:#8f671a; background:var(--m-ochre-10); border:1px solid #e0cea9; }
.m-self-check-intro { border-top:1px solid #d9e2eb; margin:1rem 0 .55rem; padding-top:1rem; }
.m-self-check-intro h4 { margin:0 0 .2rem; font-size:.98rem; }
.m-self-check-intro p { margin:0; color:var(--m-muted); font-size:.82rem; line-height:1.5; }
.m-driver-system { width:100%; max-width:1360px; margin:.55rem auto 0; }
.m-driver-system .m-reading-intro { margin:0 0 .75rem; }
.m-driver-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:.8rem; margin:.75rem auto 1rem; }

/* Keyed layout zones prevent Streamlit controls from visually sticking to adjacent cards. */
.st-key-theory_navigation { width:100% !important; max-width:none; box-sizing:border-box; margin:.55rem 0 .4rem; }
.st-key-theory_navigation [data-testid="stHorizontalBlock"] { width:100%; align-items:center; }
.st-key-theory_navigation [data-testid="stColumn"]:last-child [data-testid="stButton"] { display:flex; justify-content:flex-end; }
.st-key-theory_navigation [data-testid="stColumn"]:last-child [data-testid="stButton"] button { margin-left:auto; }
.st-key-theory_navigation [data-testid="stButton"] { margin:0; }
.st-key-theory_navigation [data-testid="stButton"] button { width:100%; min-width:0; padding:.44rem .55rem; border-radius:12px; }
/* A single native container wraps the prompt, editable answer, save action,
   notebook reminder and optional example response; no floating elements. */
[class*="st-key-context_notebook_"] { max-width:1120px; margin:1.1rem auto 1.4rem; padding:1.35rem 1.45rem !important; border:1px solid var(--m-line) !important; border-left:5px solid var(--m-ochre) !important; border-radius:18px !important; background:#fffdfb; }
[class*="st-key-context_notebook_"] h3 { margin:.1rem 0 .55rem; }
[class*="st-key-context_notebook_"] [data-testid="stTextArea"] { margin:.55rem 0 .35rem; }
[class*="st-key-context_notebook_"] [data-testid="stExpander"] { margin:.7rem 0 0; }
.st-key-lesson_footer { max-width:1360px; margin:1.65rem auto 0; padding-top:1.25rem; border-top:1px solid var(--m-line); }
.st-key-lesson_footer [data-testid="stButton"] { margin:.35rem 0 .55rem; }
.m-driver { border-radius:15px; padding:.95rem; border:1px solid rgba(60,60,59,.14); min-height:105px; }
.m-driver:nth-child(1){background:var(--m-ochre-10);border-top:4px solid var(--m-ochre)} .m-driver:nth-child(2){background:var(--m-blue-10);border-top:4px solid var(--m-blue)} .m-driver:nth-child(3){background:var(--m-cyan-10);border-top:4px solid var(--m-cyan)} .m-driver:nth-child(4){background:var(--m-green-10);border-top:4px solid var(--m-green)} .m-driver b{display:block;margin-bottom:.22rem}.m-driver span{font-size:.82rem;color:#545450}

.m-convince-hero { border:1px solid var(--m-line); border-radius:22px; overflow:hidden; display:grid; grid-template-columns:minmax(0,1fr) 250px; background:#fff; margin:.35rem 0 1.2rem; }
.m-convince-copy { padding:clamp(1.4rem,4vw,2.5rem); } .m-convince-copy h1 { margin:.4rem 0 .65rem; font-size:clamp(1.9rem,4vw,3rem); line-height:1.08; letter-spacing:-.03em; } .m-convince-copy p { color:var(--m-muted); line-height:1.65; }
.m-convince-art { background:var(--m-wine); position:relative; overflow:hidden; min-height:235px; } .m-convince-art:before{content:"";position:absolute;width:185px;height:185px;border-radius:35% 65% 55% 45%;background:var(--m-ochre);right:-30px;top:-35px;transform:rotate(18deg)} .m-convince-art:after{content:"";position:absolute;width:145px;height:190px;border-radius:58% 42% 37% 63%;background:var(--m-cyan);left:-25px;bottom:-60px;transform:rotate(-21deg)}
.m-hub-note { padding:.85rem 1rem; border-left:4px solid var(--m-wine); background:var(--m-wine-10); border-radius:0 13px 13px 0; color:#55514f; margin:.85rem 0 1.2rem; }
.m-evidence-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:.7rem; margin:.8rem 0 1rem; } .m-evidence-card { border-radius:16px; padding:1rem; min-height:165px; } .m-evidence-card.green{border-top:5px solid var(--m-green)} .m-evidence-card.blue{border-top:5px solid var(--m-blue)} .m-evidence-card.ochre{border-top:5px solid var(--m-ochre)} .m-evidence-card h3{font-size:1.05rem;margin:.15rem 0 .4rem}.m-evidence-card p{font-size:.86rem;color:var(--m-muted);line-height:1.55;margin:0}
.m-example-card { border-radius:16px; padding:1rem; margin:.65rem 0; } .m-example-place { color:var(--m-wine); font-size:.7rem; text-transform:uppercase; letter-spacing:.1em; font-weight:700; } .m-example-card h3 { margin:.25rem 0 .4rem; font-size:1.05rem; } .m-example-card p { color:var(--m-muted); font-size:.87rem; line-height:1.57; } .m-example-lesson { border-top:1px solid var(--m-line); padding-top:.6rem; margin-top:.65rem; font-size:.83rem; font-weight:600; color:var(--m-green); }
.m-audience-card { border:1px solid #c8d7e7; background:var(--m-blue-10); border-radius:17px; padding:1.1rem; margin:.7rem 0; } .m-audience-card h3{margin:.2rem 0 .4rem}.m-audience-card p{color:#525b64;line-height:1.6}.m-audience-tags{display:flex;gap:.4rem;flex-wrap:wrap;margin-top:.7rem}.m-audience-tags span{background:#fff;border:1px solid #d5dce4;border-radius:999px;padding:.25rem .55rem;font-size:.75rem}
.m-resource-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:.7rem; margin:.8rem 0; } .m-resource-card { border-radius:16px; padding:1rem; min-height:165px; } .m-resource-type { color:var(--m-wine); text-transform:uppercase; letter-spacing:.09em; font-size:.68rem; font-weight:700; } .m-resource-card h3 { font-size:1.03rem; margin:.3rem 0 .4rem; } .m-resource-card p { color:var(--m-muted); font-size:.85rem; line-height:1.55; } .m-resource-status { font-size:.75rem; font-weight:600; color:var(--m-green); }
.m-pitch { border:1px solid #d9dcb7; background:var(--m-lime-10); border-radius:16px; padding:1rem; margin:.8rem 0 1.1rem; } .m-pitch .label{font-size:.68rem;text-transform:uppercase;letter-spacing:.09em;font-weight:700;color:var(--m-green)} .m-pitch p{font-size:1rem;line-height:1.65;margin:.4rem 0 0}

.m-stat { border:1px solid var(--m-line); border-radius:15px; padding:.95rem; background:#fff; } .m-stat .value { font-size:1.6rem; font-weight:700; line-height:1; } .m-stat .label { color:var(--m-muted); font-size:.79rem; margin-top:.33rem; }
.m-admin-note { border-left:5px solid var(--m-blue); border-radius:0 16px 16px 0; background:var(--m-blue-10); padding:1rem 1.15rem; margin:.8rem 0 1.2rem; }
.m-admin-note p { margin:.3rem 0 0; color:#4f5965; line-height:1.6; }
.m-share-card { max-width:760px; border:1px solid var(--m-line); border-radius:18px; padding:1.25rem; background:var(--m-soft); }
.m-community-hero { position:relative; overflow:hidden; margin:0 0 1rem; border:1px solid #d7dfda; border-radius:24px; background:linear-gradient(135deg,#f2f7f4 0%,#fff 55%,#f8f7ee 100%); box-shadow:0 8px 24px rgba(33,72,58,.05); }
.m-community-hero:after { content:""; position:absolute; width:260px; height:260px; right:-86px; top:-112px; border-radius:46% 54% 58% 42%; background:var(--m-green); opacity:.055; }
.m-community-hero-grid { display:grid; grid-template-columns:minmax(0,1.3fr) minmax(290px,.7fr); align-items:stretch; position:relative; z-index:1; }
.m-community-hero-copy { padding:clamp(1.35rem,3vw,2.35rem); }
.m-community-hero h1 { max-width:760px; margin:.34rem 0 .5rem; font-size:clamp(1.85rem,3.5vw,2.75rem); line-height:1.08; letter-spacing:-.03em; }
.m-community-hero p { max-width:720px; margin:0; color:#555b57; line-height:1.65; }
.m-community-snapshot { border-left:1px solid #dce5df; padding:1.25rem; display:flex; flex-direction:column; justify-content:center; gap:.55rem; background:rgba(255,255,255,.46); }
.m-community-snapshot .label { color:var(--m-wine); text-transform:uppercase; letter-spacing:.1em; font-size:.67rem; font-weight:700; }
.m-community-snapshot-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:.45rem; }
.m-community-snapshot-item { padding:.68rem .72rem; border:1px solid #e1e5e1; border-radius:14px; background:rgba(255,255,255,.86); }
.m-community-snapshot-item strong { display:block; font-size:1.05rem; color:var(--m-green); }
.m-community-snapshot-item span { display:block; margin-top:.08rem; color:var(--m-muted); font-size:.68rem; line-height:1.25; }
.m-community-invitation { margin:0 0 1.25rem; }
[class*="st-key-community_navigation"] { margin:.45rem 0 1.2rem; padding:.72rem .82rem .32rem; border:1px solid var(--m-line); border-radius:16px; background:#fbfbfa; }
[class*="st-key-community_navigation"] [data-testid="stSegmentedControl"] { margin:0; }
[class*="st-key-community_navigation"] [data-testid="stCaptionContainer"] { margin-top:.2rem; }
.m-community-section-lead.compact { margin:1rem 0 .55rem; }
.m-community-section-lead { margin:1.35rem 0 .65rem; display:flex; gap:1rem; align-items:flex-end; justify-content:space-between; }
.m-community-section-lead h2 { margin:.15rem 0 .15rem; font-size:1.38rem; letter-spacing:-.02em; }
.m-community-section-lead p { margin:0; color:var(--m-muted); font-size:.88rem; line-height:1.55; max-width:760px; }
.m-community-nav-row { margin:.15rem 0 1.2rem; }
[class*="st-key-community-nav-button-"] [data-testid="stButton"] { height:100%; margin:.15rem 0 1.2rem; }
[class*="st-key-community-nav-button-"] [data-testid="stButton"] > div { height:100%; }
[class*="st-key-community-nav-button-"] [data-testid="stButton"] button {
    width:100% !important;
    min-height:190px !important;
    height:100% !important;
    padding:1.05rem 1.08rem .95rem !important;
    border:1px solid var(--m-line) !important;
    border-radius:20px !important;
    background:#fff !important;
    box-shadow:0 5px 18px rgba(20,38,31,.045) !important;
    color:var(--m-text) !important;
    display:flex !important;
    align-items:flex-start !important;
    justify-content:flex-start !important;
    text-align:left !important;
    transition:transform .16s ease,border-color .16s ease,box-shadow .16s ease,background .16s ease !important;
}
[class*="st-key-community-nav-button-"] [data-testid="stButton"] button:hover {
    transform:translateY(-2px);
    border-color:#b7c9c0 !important;
    box-shadow:0 10px 24px rgba(20,38,31,.075) !important;
}
[class*="st-key-community-nav-button-"] [data-testid="stButton"] button:focus-visible { outline:3px solid rgba(156,36,56,.24) !important; outline-offset:3px; }
[class*="st-key-community-nav-button-"] [data-testid="stButton"] button p {
    margin:0 !important;
    width:100%;
    white-space:pre-line !important;
    text-align:left !important;
    color:#555b57 !important;
    font-size:.84rem !important;
    line-height:1.58 !important;
}
[class*="st-key-community-nav-button-"] [data-testid="stButton"] button p strong {
    display:block;
    margin:.5rem 0 .45rem;
    color:var(--m-text);
    font-size:1.08rem;
    letter-spacing:-.015em;
}
[class*="st-key-community-nav-button-"] [data-testid="stButton"] button[kind="primary"],
[class*="st-key-community-nav-button-"] [data-testid="stBaseButton-primary"] {
    border-color:#a9c7b9 !important;
    background:linear-gradient(145deg,#fff 0%,#f3f8f5 100%) !important;
    box-shadow:0 7px 22px rgba(21,105,80,.08) !important;
}
[class*="st-key-community_post_"] { margin:.8rem 0 1rem; padding:1rem 1.05rem .9rem; border:1px solid #e1e2de; border-radius:17px; background:#fff; box-shadow:0 2px 9px rgba(60,60,59,.025); }
[class*="st-key-community_post_"] .m-post { margin:0 0 .55rem; padding:0; border:0; border-radius:0; }
.m-post-meta { color:var(--m-muted); font-size:.73rem; margin-bottom:.48rem; }
.m-post p { margin:0; white-space:pre-wrap; line-height:1.6; color:#444441; }
.m-reaction-summary { color:var(--m-muted); font-size:.76rem; line-height:2.5; text-align:right; }
.m-comment { margin:.55rem 0; padding:.76rem .85rem; border-left:3px solid var(--m-cyan); border-radius:0 12px 12px 0; background:var(--m-cyan-10); }
.m-comment-meta { margin-bottom:.25rem; color:var(--m-muted); font-size:.72rem; }
.m-comment p { margin:0; font-size:.86rem; line-height:1.52; white-space:pre-wrap; }
.m-community-share-shell { margin:1.5rem 0 .7rem; padding:1.15rem 1.2rem; border:1px solid #c9dcd3; border-radius:18px; background:linear-gradient(135deg,var(--m-green-10),#fff 76%); box-shadow:0 4px 14px rgba(21,105,80,.035); }
.m-community-share-shell h3 { margin:.2rem 0 .32rem; font-size:1.18rem; }
.m-community-share-shell p { margin:0; color:var(--m-muted); font-size:.86rem; line-height:1.55; }
.m-notification { margin:.58rem 0; padding:.9rem 1rem; border:1px solid var(--m-line); border-left:4px solid #c9c9c4; border-radius:0 14px 14px 0; background:#fff; box-shadow:0 2px 8px rgba(60,60,59,.025); }
.m-notification.unread { border-left-color:#d6283f; background:#fff9f9; }
.m-notification p { margin:0 0 .22rem; line-height:1.5; }
.m-notification a { color:var(--m-blue) !important; font-weight:600; text-decoration:none; }
.m-notification a:hover { text-decoration:underline; }
.m-notification .meta { color:var(--m-muted); font-size:.72rem; }
.m-mycelium-optin { margin:.85rem 0 1.1rem; padding:1.1rem 1.2rem; border:1px solid #c9dcd3; border-radius:18px; background:linear-gradient(135deg,var(--m-green-10),#fff 75%); }
.m-mycelium-optin h3 { margin:.25rem 0 .35rem; }
.m-mycelium-optin p { margin:0; color:var(--m-muted); line-height:1.6; }
.m-mycelium-intro { margin:0 0 .75rem; padding:1rem 1.05rem; border:1px solid #bfd6cc; border-radius:18px; background:linear-gradient(135deg,var(--m-green-10),#fff 74%); box-shadow:0 3px 12px rgba(21,105,80,.035); }
.m-mycelium-intro h3 { margin:.18rem 0 .35rem; font-size:1.08rem; }
.m-mycelium-intro p { margin:0; color:var(--m-muted); font-size:.82rem; line-height:1.55; }
.m-mycelium-metrics { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:.45rem; margin:.75rem 0 .1rem; }
.m-mycelium-metric { padding:.62rem .66rem; border:1px solid var(--m-line); border-radius:13px; background:#fff; }
.m-mycelium-metric strong { display:block; color:var(--m-green); font-size:1rem; }
.m-mycelium-metric span { display:block; margin-top:.1rem; color:var(--m-muted); font-size:.68rem; line-height:1.3; }
.m-mycelium-section-label { margin:.1rem 0 .55rem; color:var(--m-wine); font-size:.7rem; font-weight:700; letter-spacing:.08em; text-transform:uppercase; }
.m-mycelium-person { margin:.45rem 0; padding:.66rem .72rem; border:1px solid var(--m-line); border-radius:13px; background:#fff; }
.m-mycelium-person strong { display:block; font-size:.86rem; }
.m-mycelium-person span { display:block; margin-top:.12rem; color:var(--m-muted); font-size:.72rem; line-height:1.35; }
.m-mycelium-map-heading { margin:.08rem 0 .65rem; padding:.1rem .05rem; }
.m-mycelium-map-heading strong { display:block; font-size:1.08rem; }
.m-mycelium-map-heading span { display:block; margin-top:.18rem; color:var(--m-muted); font-size:.78rem; line-height:1.45; }
[class*="st-key-mycelium_sidebar_"] { border:1px solid var(--m-line); border-radius:18px; padding:.9rem .95rem .6rem; background:#fbfbfa; margin-bottom:.75rem; box-shadow:0 3px 10px rgba(60,60,59,.025); }

@media (max-width: 820px) {
    .block-container{padding-left:1.25rem;padding-right:1.25rem}
    .m-hero{grid-template-columns:1fr}.m-hero-art{min-height:220px}.m-convince-hero{grid-template-columns:1fr}.m-convince-art{min-height:150px}
    .m-building-grid,.m-evidence-grid,.m-tool-steps{grid-template-columns:repeat(2,minmax(0,1fr));}.m-brandtag{display:none}
    .m-theory-card{min-height:290px}.m-theory-inner{max-width:none}.m-theory-card.has-idea-image{display:flex;flex-direction:column;min-height:0}.m-idea-media,.m-idea-media img{min-height:0}
    .m-practice-feature{grid-template-columns:1fr}.m-practice-media{min-height:145px;max-height:210px}.m-community-hero-grid{grid-template-columns:1fr}.m-community-snapshot{border-left:0;border-top:1px solid #dce5df}.m-community-snapshot-grid{max-width:520px}
}
@media (max-width: 620px) {
    .block-container{padding-top:4.75rem;padding-left:1rem;padding-right:1rem}
    .m-building-grid,.m-evidence-grid,.m-resource-grid,.m-driver-grid,.m-tool-steps,.m-mycelium-metrics,.m-community-snapshot-grid{grid-template-columns:1fr}
    .m-track-card{min-height:0}.m-module-card{height:auto;min-height:0}.m-start-intro{grid-template-columns:1fr}.m-start-image{min-height:150px}.m-start-choice,.m-glossary-card{min-height:0}.m-phase-header{grid-template-columns:44px minmax(0,1fr)}.m-phase-progress{grid-column:2;justify-self:start}.m-lesson-row{grid-template-columns:38px minmax(0,1fr)}.m-lesson-time{grid-column:2}
    [class*="st-key-path_step_"] [data-testid="stHorizontalBlock"]{gap:.55rem}.m-path-copy .meta{font-size:.63rem}
    .m-theory-card{min-height:0;padding:1.5rem 1.25rem;border-radius:19px}.m-theory-card.has-idea-image{display:flex;flex-direction:column}.m-theory-card.has-idea-image .m-theory-inner{padding:0}.m-image-below-card{margin-top:1rem}.m-image-below-card img{max-height:320px}.m-theory-progress{width:78%;margin-bottom:.75rem}
    .st-key-theory_navigation [data-testid="stButton"] button{min-width:0;width:100%;font-size:.86rem}
    .m-mini-mark{width:30px;height:30px}.m-brandbar{margin-bottom:.8rem}.m-brand-logo{height:36px;max-width:150px}.m-brand-learn{padding-left:.5rem}.m-brand-home{gap:.5rem}
}


/* Learning hub, resource library and repository-style tools. */
.m-learning-hub-hero { margin:.25rem 0 1rem; padding:1.25rem 1.35rem; border:1px solid var(--m-line); border-radius:20px; background:linear-gradient(135deg,#fbfbf8 0%,#f3f7f4 100%); }
.m-learning-hub-hero h1 { margin:.25rem 0 .45rem; font-size:clamp(1.9rem,4vw,3rem); letter-spacing:-.03em; }
.m-learning-hub-hero p { max-width:820px; margin:0; color:var(--m-muted); line-height:1.6; }
.m-learning-summary { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:.7rem; margin:.8rem 0 1.1rem; }
.m-learning-summary > div { padding:.8rem .9rem; border:1px solid var(--m-line); border-radius:14px; background:#fff; }
.m-learning-summary strong { display:block; font-size:1.35rem; }
.m-learning-summary span { color:var(--m-muted); font-size:.78rem; }
.m-reflection-card { margin:.65rem 0; padding:.9rem 1rem; border:1px solid var(--m-line); border-left:4px solid var(--m-ochre); border-radius:0 14px 14px 0; background:#fff; }
.m-reflection-card .meta { color:var(--m-muted); font-size:.72rem; margin-bottom:.32rem; }
.m-reflection-card h4 { margin:0 0 .3rem; }
.m-reflection-card p { margin:0; color:#4f544f; line-height:1.58; white-space:pre-wrap; }
.m-library-hero, .m-tools-repo-hero { margin:.25rem 0 1rem; padding:1.3rem 1.4rem; border:1px solid var(--m-line); border-radius:20px; background:linear-gradient(135deg,#fff 0%,#f5f7f3 100%); }
.m-library-hero h1, .m-tools-repo-hero h1 { margin:.25rem 0 .4rem; font-size:clamp(1.9rem,4vw,3rem); letter-spacing:-.03em; }
.m-library-hero p, .m-tools-repo-hero p { max-width:850px; margin:0; color:var(--m-muted); line-height:1.6; }
.m-resource-library-card { height:320px; box-sizing:border-box; padding:1rem 1.05rem; margin:0 0 1.25rem; border:1px solid var(--m-line); border-radius:16px; background:#fff; display:flex; flex-direction:column; overflow:hidden; }
.m-tool-repo-card { height:445px; box-sizing:border-box; border:1px solid var(--m-line); border-top:5px solid var(--m-ochre); border-radius:18px; background:#fff; overflow:hidden; display:flex; flex-direction:column; }
.m-tool-repo-card.workshop { border-top-color:var(--m-ochre); }
.m-tool-repo-card.website { border-top-color:var(--m-blue); }
.m-tool-repo-card.model { border-top-color:var(--m-green); }
.m-tool-repo-card.digital-tool { border-top-color:var(--m-wine); }
.m-tool-card-media { height:150px; flex:0 0 150px; background:#f5f5f2; overflow:hidden; }
.m-tool-card-media img { width:100%; height:100%; object-fit:cover; display:block; }
.m-tool-card-placeholder { display:flex; align-items:center; justify-content:center; background:linear-gradient(135deg,#f7f7f4,#eceee9); }
.m-tool-card-placeholder span { font-size:3rem; color:#9a9b95; }
.m-tool-card-body { padding:1rem 1.05rem 1.05rem; display:flex; flex-direction:column; flex:1; min-height:0; }
.m-tool-format-line { display:flex; align-items:center; gap:.42rem; margin:0 0 .45rem; font-size:.72rem; font-weight:800; letter-spacing:.055em; text-transform:uppercase; color:var(--m-grey); }
.m-tool-format-icon { display:inline-flex; width:26px; height:26px; align-items:center; justify-content:center; border-radius:8px; background:#f0f1ed; font-size:.88rem; }
.m-resource-library-card h3, .m-tool-repo-card h3 { margin:.42rem 0 .4rem; font-size:1.08rem; line-height:1.28; display:-webkit-box; -webkit-box-orient:vertical; overflow:hidden; }
.m-resource-library-card h3 { -webkit-line-clamp:2; min-height:2.75em; }
.m-tool-repo-card h3 { -webkit-line-clamp:2; min-height:2.75em; }
.m-resource-library-card p, .m-tool-repo-card p { margin:.2rem 0 .7rem; color:var(--m-muted); font-size:.85rem; line-height:1.52; display:-webkit-box; -webkit-box-orient:vertical; overflow:hidden; }
.m-resource-library-card p { -webkit-line-clamp:4; }
.m-tool-repo-card p { -webkit-line-clamp:4; }
.m-resource-card-author { color:var(--m-muted); font-size:.75rem; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; margin:.05rem 0 .45rem; }
.m-resource-badges, .m-tool-filter-tags { display:flex; gap:.35rem; flex-wrap:wrap; margin:.35rem 0 .45rem; overflow:hidden; max-height:3.1rem; }
.m-resource-badge, .m-tool-filter-tag { display:inline-flex; align-items:center; padding:.2rem .5rem; border-radius:999px; font-size:.68rem; font-weight:700; background:#f0f1ed; color:#5c625d; }
.m-resource-badge.mosaic { background:var(--m-green-10); color:var(--m-green); }
.m-resource-badge.external { background:var(--m-blue-10); color:var(--m-blue); }
.m-resource-library-card a { color:#1769aa !important; text-decoration:none !important; font-weight:700; }
.m-resource-library-card a:hover { text-decoration:underline !important; }
.m-resource-card-action { margin-top:auto; padding-top:.6rem; border-top:1px solid #ecece8; }
.m-resource-card-action a { display:inline-flex; align-items:center; gap:.25rem; }
.m-resource-detail { margin:.25rem 0 1.25rem; padding:clamp(1.25rem,3vw,2rem); border:1px solid var(--m-line); border-radius:22px; background:linear-gradient(135deg,#fff 0%,#f7f8f4 100%); }
.m-resource-detail h1 { margin:.35rem 0 .65rem; max-width:980px; font-size:clamp(1.8rem,3.7vw,2.9rem); line-height:1.08; letter-spacing:-.03em; }
.m-resource-detail p { max-width:940px; color:var(--m-muted); line-height:1.7; }
.m-resource-detail-meta { display:flex; gap:.4rem; flex-wrap:wrap; margin:.75rem 0 0; }
.m-resource-detail-meta span { padding:.25rem .55rem; border-radius:999px; background:#fff; border:1px solid var(--m-line); font-size:.72rem; font-weight:650; }
.m-resource-download-shell { margin:1rem 0 1.4rem; padding:1.05rem 1.1rem .45rem; border:1px solid var(--m-line); border-radius:18px; background:#fff; }
.m-resource-download-shell h2 { margin:.05rem 0 .3rem; font-size:1.25rem; }
.m-resource-download-shell p { margin:0 0 .6rem; color:var(--m-muted); font-size:.86rem; }
.st-key-resources_class_finder, .st-key-catalogue_class_finder {background:linear-gradient(135deg,#f2f7fd 0%,#fff 75%) !important;border-color:#d6e1ef !important;border-radius:20px !important;margin:.95rem 0 1.2rem;box-shadow:0 5px 16px rgba(13,79,158,.025)}
.m-class-finder-heading {display:flex;align-items:center;gap:.8rem;margin-bottom:.7rem}
.m-class-finder-heading h2 {font-family:Georgia,Cambria,serif !important;font-weight:400 !important;color:#303b45 !important;font-size:1.48rem !important;margin:0 0 .12rem !important;padding:0 !important}
.m-class-finder-heading p {font-size:.85rem;margin:0;color:var(--m-muted)}
.m-class-finder-icon {display:flex;align-items:center;justify-content:center;width:38px;height:38px;border-radius:12px;color:#fff;background:var(--m-blue);font-size:1.4rem;flex-shrink:0}
.m-agent-shell { margin:1rem 0 1.35rem; padding:1rem 1.05rem; border:1px solid #c8d9d1; border-radius:20px; background:linear-gradient(135deg,#edf5f2 0%,#ffffff 62%,#f1fafb 100%); box-shadow:0 7px 20px rgba(21,105,80,.045); }
.m-agent-head { display:flex; align-items:center; justify-content:space-between; gap:1rem; margin-bottom:.8rem; }
.m-agent-identity { display:flex; align-items:center; gap:.7rem; }
.m-agent-avatar { width:42px; height:42px; border-radius:14px; display:flex; align-items:center; justify-content:center; background:var(--m-green); color:#fff; font-size:1.05rem; font-weight:800; box-shadow:inset 0 0 0 1px rgba(255,255,255,.25); }
.m-agent-title strong { display:block; font-size:1rem; }
.m-agent-title span { color:var(--m-muted); font-size:.76rem; }
.m-agent-soon { flex:0 0 auto; padding:.25rem .55rem; border-radius:999px; background:#fff; border:1px solid #c8d9d1; color:var(--m-green); font-size:.68rem; font-weight:800; letter-spacing:.05em; text-transform:uppercase; }
.m-agent-message { max-width:780px; margin:.2rem 0 .8rem 3rem; padding:.75rem .85rem; border-radius:4px 14px 14px 14px; background:#fff; border:1px solid #dce7e1; color:#4d5752; font-size:.86rem; line-height:1.55; }
.m-agent-compose { display:grid; grid-template-columns:minmax(0,1fr) auto; gap:.55rem; align-items:center; padding:.45rem; border:1px solid #d6dfda; border-radius:15px; background:#fff; }
.m-agent-placeholder { min-height:42px; display:flex; align-items:center; padding:0 .7rem; color:#8a8f8b; font-size:.84rem; }
.m-agent-send { min-width:42px; height:42px; border-radius:12px; display:flex; align-items:center; justify-content:center; background:#e7ece9; color:#9aa09c; font-weight:800; }
.m-tool-detail { margin:.3rem 0 1rem; padding:1.35rem 1.45rem; border:1px solid var(--m-line); border-radius:22px; background:#fff; }
.m-tool-detail h1 { margin:.35rem 0 .55rem; font-size:clamp(1.9rem,4vw,3rem); letter-spacing:-.03em; }
.m-tool-detail p { max-width:850px; color:var(--m-muted); line-height:1.65; }
.m-tool-detail-meta { display:flex; gap:.45rem; flex-wrap:wrap; margin:.75rem 0 0; }
.m-tool-detail-meta span { padding:.28rem .58rem; border-radius:999px; background:#f1f2ee; font-size:.72rem; font-weight:650; }
.m-tool-detail.workshop { border-top:6px solid var(--m-ochre); }
.m-tool-detail.website { border-top:6px solid var(--m-blue); }
.m-tool-detail.model { border-top:6px solid var(--m-green); }
.m-tool-detail.digital-tool { border-top:6px solid var(--m-wine); }
.m-tool-detail-placeholder { min-height:230px; border:1px solid var(--m-line); border-radius:20px; display:flex; flex-direction:column; gap:.5rem; align-items:center; justify-content:center; background:#f6f6f4; color:var(--m-muted); }
.m-tool-detail-placeholder span { font-size:4rem; line-height:1; }
.m-tool-detail-placeholder strong { font-size:.8rem; letter-spacing:.08em; text-transform:uppercase; }
.m-tool-detail-placeholder.workshop { background:var(--m-ochre-10); color:var(--m-ochre); }
.m-tool-detail-placeholder.website { background:var(--m-blue-10); color:var(--m-blue); }
.m-tool-detail-placeholder.model { background:var(--m-green-10); color:var(--m-green); }
.m-tool-detail-placeholder.digital-tool { background:var(--m-wine-10); color:var(--m-wine); }
.m-linked-resource { margin:.55rem 0; padding:.7rem .8rem; border-left:3px solid var(--m-blue); background:var(--m-blue-10); border-radius:0 10px 10px 0; }
.m-linked-resource a { color:#1769aa !important; font-weight:700; text-decoration:none !important; }
/* Support material rows: quiet, full-width, no double Streamlit border. */
[class*="st-key-compact_link_"] {
    width:100%; box-sizing:border-box; margin:.34rem 0 !important;
    padding:.6rem .95rem !important; border:1px solid #e5eae8;
    border-radius:11px; background:#f9faf9;
}
[class*="st-key-try_tool_"] {
    width:100%; box-sizing:border-box; margin:.42rem 0 !important;
    padding:.82rem 1.05rem !important; border:1px solid #dbe7df;
    border-left:4px solid #397963; border-radius:12px; background:#f3f8f5;
}
[class*="st-key-compact_link_"] [data-testid="stVerticalBlock"],
[class*="st-key-try_tool_"] [data-testid="stVerticalBlock"] { gap:.1rem !important; }
[class*="st-key-compact_link_"] [data-testid="stButton"],
[class*="st-key-compact_link_"] [data-testid="stLinkButton"],
[class*="st-key-try_tool_"] [data-testid="stButton"],
[class*="st-key-try_tool_"] [data-testid="stLinkButton"] { margin:0 !important; }
.m-wide-link-copy { width:100%; line-height:1.36; min-width:0; }
.m-wide-link-title { color:#333a37; font-weight:700; font-size:.97rem; overflow-wrap:anywhere; }
.m-wide-link-meta { display:block; color:#67716c; font-size:.73rem; margin-top:.22rem; }
.m-wide-link-copy p { color:#515d56; font-size:.81rem; line-height:1.36; margin:.21rem 0 .1rem !important;
    display:-webkit-box; -webkit-box-orient:vertical; -webkit-line-clamp:2; overflow:hidden; }
@media (max-width:640px) {
    [class*="st-key-compact_link_"], [class*="st-key-try_tool_"] { padding:.67rem .75rem !important; }
    .m-wide-link-title { font-size:.89rem; }
}
@media (max-width:900px){ .m-learning-summary{grid-template-columns:1fr;} }


/* V12: set breathing room for the last line, not just the first line. */
[class*="st-key-compact_link_"] {
    padding: .93rem 1.12rem 1.04rem !important;
    min-height: 88px;
    box-sizing: border-box;
}
[class*="st-key-try_tool_"] { padding: 1.03rem 1.12rem 1.12rem !important; }
.m-wide-link-copy { padding: .12rem 0 .2rem; line-height: 1.5; }
.m-wide-link-copy p { margin: .3rem 0 .28rem !important; line-height: 1.48; }
.m-wide-link-meta { margin: .26rem 0 .08rem; line-height: 1.5; }
[class*="st-key-path_step_"] {
    padding: 1.08rem 1.12rem 1.14rem !important;
    box-sizing: border-box;
}
.m-path-copy { padding: .28rem 0 .4rem; gap: .3rem; min-height: 76px; }
.m-path-copy p { line-height: 1.6; padding-bottom: .18rem; }
/* Readable case studies preserve the imported evidence but not editorial prompts. */
.m-theory-card .m-case-study-lesson {
    margin: 1.2rem 0 .25rem; padding: .85rem 1.05rem;
    border-left: 3px solid var(--m-green); background: #f1f7f2;
    border-radius: 0 10px 10px 0; line-height: 1.65;
}
.m-theory-card .m-case-study-lesson strong { font-size: .9rem; }
.m-theory-card .m-case-study-lesson p { margin: .32rem 0 .05rem; }
.m-theory-card .m-case-study-source { font-size: .85rem; overflow-wrap: anywhere; }
/* Our Story: use the whole content width and balance it with original case imagery. */
.m-story-hero { max-width: 100%; margin-bottom: 1rem; }
.m-story-hero p { max-width: 92ch; }
.m-story-introduction {
    display: flex; justify-content: space-between; align-items: flex-start; gap: 2rem;
    padding: 1.15rem 1.35rem; background: #f5f8f5;
    border: 1px solid #e0e8e2; border-radius: 18px; margin: 0 0 1.5rem;
}
.m-story-introduction > div:first-child { flex: 1; max-width: 86ch; }
.m-story-introduction strong { font-size: 1rem; }
.m-story-introduction p { margin: .4rem 0 0; color: #4d5b53; line-height: 1.65; }
.m-story-methods { flex: 0 1 260px; display: flex; flex-wrap: wrap; gap: .35rem; }
.m-story-methods span { display: inline-block; background: #fff; border: 1px solid #dbe4dd;
    color: #3d6252; border-radius: 999px; padding: .25rem .55rem; font-size: .74rem; }
.m-story-detail-grid.has-photo { display: grid; grid-template-columns: minmax(0,1.45fr) minmax(260px,1fr);
    align-items: start; gap: clamp(1.2rem, 3vw, 2.5rem); }
.m-story-detail-grid .m-story-main { min-width:0; }
.m-story-detail-grid .m-story-main p { max-width: none; }
.m-story-photo { margin: .15rem 0 0; min-width:0; }
.m-story-photo-image { width: 100%; height: auto; display: block; border-radius: 14px;
    aspect-ratio: 4 / 3; object-fit: cover; }
.m-story-photo figcaption { font-size: .73rem; color: #616b64; line-height: 1.45; margin-top: .5rem; }
@media(max-width: 920px){
    .m-story-detail-grid.has-photo { grid-template-columns: 1fr; }
    .m-story-introduction { flex-direction: column; gap: .7rem; }
    .m-story-methods { flex: initial; }
    .m-story-photo-image { aspect-ratio: 16 / 9; }
}
@media(max-width: 620px){
    [class*="st-key-compact_link_"] { padding: .86rem .85rem 1rem !important; }
    [class*="st-key-path_step_"] { padding: 1rem .85rem 1.08rem !important; }
}


/* MOSAIC illustrated field guide: the approved blue, green, wine, cyan,
   ochre and lime variables above remain untouched. This layer is purely visual. */
.m-hero.m-illustrated-home { grid-template-columns:minmax(0,1.05fr) minmax(330px,.95fr); background:#fff; border:1px solid #e0e1dc; border-radius:20px; box-shadow:none; }
.m-illustrated-home .m-hero-copy { padding:clamp(2rem,4vw,3.65rem); }
.m-illustrated-home .m-hero-copy h1 { font-family:Georgia,Cambria,serif; font-weight:500; font-size:clamp(2.3rem,4.65vw,4.15rem); line-height:1.08; max-width:19ch; }
.m-illustrated-home .m-hero-copy h1 em { color:var(--m-blue); font-style:italic; font-weight:400; }
.m-illustrated-home .m-hero-copy p { max-width:63ch; font-size:1.01rem; line-height:1.75; }
.m-tools-pager-label { text-align:center; padding:.55rem 0; color:var(--m-muted); font-family:Poppins, sans-serif; font-size:.9rem; }
.m-illustrated-home .m-hero-drawn { background:#fbfcfa; min-height:350px; display:flex; align-items:center; justify-content:center; padding:clamp(1rem,3vw,2rem); }
.m-hero-loop-image { display:block; width:100%; height:auto; max-height:390px; object-fit:contain; }
.m-drawing-placeholder { display:flex; flex-direction:column; justify-content:center; align-items:center; gap:.6rem; min-height:230px; border:1px dashed #ccd6d1; border-radius:16px; background:#f7faf8; text-align:center; padding:1.2rem; }
.m-drawing-placeholder span { font-size:1.05rem; font-weight:600; color:var(--m-blue); }
.m-drawing-placeholder small { color:var(--m-muted); font-size:.8rem; }
.m-module-hero.m-module-illustrated { padding:0; display:grid; grid-template-columns:minmax(0,1.25fr) minmax(220px,.75fr); align-items:stretch; border-radius:20px; background:#fff; }
.m-module-hero.m-module-illustrated:after { content:none; }
.m-module-hero-copy { padding:clamp(1.65rem,3vw,2.9rem); }
.m-module-hero.m-module-illustrated h1 { font-family:Georgia,Cambria,serif; font-weight:500; font-size:clamp(2rem,3.8vw,3.15rem); }
.m-module-hero-art { display:flex; justify-content:center; align-items:center; background:#f8faf8; padding:clamp(1rem,2.2vw,2rem); border-left:1px solid #e9ece8; }
.m-field-guide-drawing { display:block; width:100%; max-height:260px; height:auto; object-fit:contain; }
/* Readable information over large decorative panels. */
.m-module-card .m-module-art:not(.has-cover) { background:#f6faf8; }
.m-module-card .m-module-art:not(.has-cover):before,.m-module-card .m-module-art:not(.has-cover):after { opacity:.28; }
.m-mode-card { background:#fff; min-height:158px; border-radius:16px; box-shadow:none; }
.m-mode-top { display:flex; align-items:flex-start; justify-content:space-between; gap:.5rem; min-height:28px; }
.m-mode-doodle { max-width:110px; max-height:65px; width:auto; height:auto; object-fit:contain; }
.m-mode-card.understand { border-top:5px solid var(--m-blue); }
.m-mode-card.apply { border-top:5px solid var(--m-green); }
.m-mode-card.convince { border-top:5px solid var(--m-wine); background:#fff; }
.m-mode-card.understand .m-mode-num { color:var(--m-blue); font-size:1.45rem; font-weight:700; }
.m-mode-card.apply .m-mode-num { color:var(--m-green); font-size:1.45rem; font-weight:700; }
.m-mode-card.convince .m-mode-num { color:var(--m-wine); font-size:1.45rem; font-weight:700; }
.m-mode-note { background:#f6f6f3; font-weight:500; }
.m-phase-header.understand .m-phase-number { color:var(--m-blue); background:var(--m-blue-10); }
.m-phase-header.apply .m-phase-number { color:var(--m-green); background:var(--m-green-10); }
.m-communicate-heading h2 { color:var(--m-wine); }
/* Softer editorial flow instead of repeated floating dashboards. */
.m-section-title { margin:2.1rem 0 1.05rem; }
.m-section-title h2 { font-size:clamp(1.4rem,2.4vw,1.9rem); line-height:1.25; }
[class*="st-key-path_phase_"] { background:#fff; border:1px solid #e4e6e0; box-shadow:none; }
[class*="st-key-path_step_"] { box-shadow:none; border:1px solid #e5e6e1 !important; }
.m-module-illustrated .m-hero-meta { gap:.45rem; }
.m-lesson-hero h1 { font-family:Georgia,Cambria,serif; font-weight:500; max-width:24ch; font-size:clamp(2.05rem,3.7vw,3.25rem); }
.m-theory-card { background:#fff; box-shadow:none; }
/* Editorial headings: normal-weight serif for page and section headings,
   and for titles within learning, module and library cards. Body copy,
   buttons, progress labels and eyebrow/kicker text stay in Poppins. */
[data-testid="stMain"] h1,
[data-testid="stMain"] h2,
[data-testid="stMain"] h3,
[data-testid="stMainBlockContainer"] h1,
[data-testid="stMainBlockContainer"] h2,
[data-testid="stMainBlockContainer"] h3,
.m-hero h1,
.m-section-title h2,
.m-module-hero h1,
.m-module-body h3,
.m-track-card h3,
.m-mode-card h3,
.m-phase-header h3,
.m-path-copy h4,
.m-theory-card h3,
.m-resource-library-card h3,
.m-tool-repo-card h3,
.m-resource-card h3,
.m-example-card h3,
.m-story-card h3,
.m-evidence-card h3,
.m-reading-intro h3,
.m-card-title,
.m-wide-link-title {
    font-family: Georgia, Cambria, "Times New Roman", serif !important;
    font-weight: 400 !important;
    letter-spacing: -.018em;
}
/* Card titles stay legible in the calmer editorial face. */
.m-card-title {font-size:1.22rem; line-height:1.25; margin:.15rem 0 .4rem;}
.m-module-body h3 {font-size:1.36rem;}
.m-mode-card h3 {font-size:1.3rem;}
.m-phase-header h3 {font-size:1.45rem;}
.m-path-copy h4 {font-size:1.12rem;}
.m-wide-link-title {font-size:1.11rem; line-height:1.35;}
.m-illustrated-home .m-hero-copy h1,
.m-module-hero.m-module-illustrated h1,
.m-lesson-hero h1 { font-weight: 400 !important; }
/* Imported landing-page figures are module imagery, not cropped decorations.
   'contain' keeps diagrams and explanatory figures fully legible. */
.m-module-hero-art.has-cover { padding:0; background:#f5f7f3; min-height:220px; }
.m-module-hero-cover { display:block; width:100%; height:100%; max-height:350px;
                       object-fit:contain; object-position:center; }
/* Native Streamlit widgets remain native (no scripts, iframe or new page router). */
@media (max-width:860px) {
    .m-hero.m-illustrated-home,.m-module-hero.m-module-illustrated { grid-template-columns:1fr; }
    .m-illustrated-home .m-hero-drawn { min-height:185px; }
    .m-hero-loop-image { max-height:255px; }
    .m-module-hero-art { border-left:0; border-top:1px solid #e9ece8; }
    .m-field-guide-drawing { max-height:175px; }
}

</style>
""",
    unsafe_allow_html=True,
)


def brand_mark_html() -> str:
    return "<span class='m-mini-mark' aria-hidden='true'>" + "".join("<i></i>" for _ in range(9)) + "</span>"


def brand_home_html(*, sidebar: bool = False) -> str:
    """Render the approved logo as an accessible link to the app home page."""
    if APPROVED_LOGO.exists():
        encoded = base64.b64encode(APPROVED_LOGO.read_bytes()).decode("ascii")
        logo = f"<img class='m-brand-logo' src='data:image/png;base64,{encoded}' alt='MOSAIC'>"
    else:
        # Keep the app usable in a bare code checkout; production should provide
        # assets/mosaic-logo.png so the approved mark is always shown.
        logo = f"{brand_mark_html()}<strong>MOSAIC</strong>"
    css_class = "m-brand-home sidebar" if sidebar else "m-brand-home"
    return (
        f"<a class='{css_class}' href='?page=home' target='_self' aria-label='Go to MOSAIC Learn home'>"
        f"{logo}<span class='m-brand-learn'>Learn</span></a>"
    )


def render_brandbar():
    st.markdown(
        f"<div class='m-brandbar'>{brand_home_html()}<div class='m-brandtag'>Developing innovative and effective policies for sustainable land use</div></div>",
        unsafe_allow_html=True,
    )


def asset_image_html(relative_name: str | None, *, alt: str, css_class: str) -> str:
    """Embed an optional image while keeping configured paths inside assets/."""
    if not relative_name:
        return ""
    asset_root = ASSETS_DIR.resolve()
    asset_path = (ASSETS_DIR / relative_name).resolve()
    try:
        asset_path.relative_to(asset_root)
    except ValueError:
        return ""
    mime_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }
    mime_type = mime_types.get(asset_path.suffix.lower())
    if not mime_type or not asset_path.is_file():
        return ""
    encoded = base64.b64encode(asset_path.read_bytes()).decode("ascii")
    return f"<img class='{css_class}' src='data:{mime_type};base64,{encoded}' alt='{escape(alt)}'>"


# Illustrated field-guide assets are optional, and never required for an import.
# To replace a drawing, overwrite the corresponding file under assets/illustrations/.
# Superhuman Docs cover images still take priority in published module catalogue cards.
ILLUSTRATION_SLOTS = {
    "home": "illustrations/mosaic-learning-loop.png",
    "drivers": "illustrations/drivers-of-change.png",
    "future-pathways": "illustrations/future-pathways.png",
    "policy-labs": "illustrations/policy-labs.png",
    "discover": "illustrations/discover.png",
    "apply": "illustrations/apply.png",
    "communicate": "illustrations/communicate.png",
}


def _module_drawing(module_id: str) -> str:
    """Pick a named, replaceable drawing; do not depend on imported content."""
    chosen = ILLUSTRATION_SLOTS.get(module_id, "illustrations/module-generic.png")
    markup = asset_image_html(chosen, alt="Hand-drawn MOSAIC learning illustration", css_class="m-field-guide-drawing")
    return markup or ("<div class='m-drawing-placeholder' aria-hidden='true'>"
                       "<span>Place-based learning</span><small>Illustration slot</small></div>")


def learning_topics(module):
    """Topics that count toward course progress. Convince is a resource hub."""
    return [topic for topic in module.get("topics", []) if topic.get("level") != "Convince"]


def _secret(name: str, default=""):
    try:
        return st.secrets.get(name, default)
    except Exception:
        return default


ALLOWED_RICH_TEXT_TAGS = [
    "p", "br", "strong", "em", "u", "s", "blockquote", "ul", "ol", "li", "a",
    # Preserve semantic tables imported from Superhuman Docs instead of
    # stripping them on CMS save/load or on learner-page rendering.
    "div", "table", "thead", "tbody", "tr", "th", "td"
]

def _safe_import_table_class(tag, name, value):
    return value in {"m-import-table", "m-import-table-wrap"}

ALLOWED_RICH_TEXT_ATTRIBUTES = {
    "a": ["href", "title", "target", "rel"],
    "div": {"class": _safe_import_table_class},
    "table": {"class": _safe_import_table_class, "aria-label": True},
    "th": ["scope"],
}


def sanitize_rich_text(value: str | None) -> str:
    """Allow useful editor formatting without allowing executable page content."""
    value = str(value or "").strip()
    if not value:
        return ""
    if bleach is None:
        return "<p>" + escape(value).replace("\n", "<br>") + "</p>"
    return bleach.clean(
        value,
        tags=ALLOWED_RICH_TEXT_TAGS,
        attributes=ALLOWED_RICH_TEXT_ATTRIBUTES,
        protocols=["http", "https", "mailto"],
        strip=True,
    )


def _valid_external_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme == "https" and bool(parsed.hostname)


def plain_text_as_html(value: str | None) -> str:
    text = escape(str(value or "").strip())
    return f"<p>{text}</p>" if text else ""


def carousel_card_editor_id(card_item: dict, position: int) -> str:
    """Return a stable widget identity that follows an idea when it is reordered."""
    existing = str(card_item.get("editor_id") or "").strip()
    if existing:
        return existing
    seed = "|".join(
        [
            str(position),
            str(card_item.get("label", "")),
            str(card_item.get("title", "")),
            str(card_item.get("body_html") or card_item.get("text_html") or card_item.get("text", "")),
        ]
    )
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def default_carousel_payload(topic: dict) -> dict:
    """Convert content.py values into the editor's portable JSON structure."""
    cards = []
    for card_index, card_item in enumerate(topic.get("theory_cards") or []):
        cards.append(
            {
                "editor_id": carousel_card_editor_id(card_item, card_index),
                "label": str(card_item.get("label", "Core idea")),
                "title": str(card_item.get("title", "")),
                "body_html": sanitize_rich_text(
                    card_item.get("body_html")
                    or card_item.get("text_html")
                    or plain_text_as_html(card_item.get("text", ""))
                ),
                "image_resource_id": str(card_item.get("image_resource_id") or "").strip(),
                "image_resource_ids": list(card_item.get("image_resource_ids") or []),
                "image_alt": str(card_item.get("image_alt") or card_item.get("title") or "Idea image").strip(),
            }
        )
    return {
        "cards": cards,
        "takeaway_html": sanitize_rich_text(
            topic.get("takeaway_html") or plain_text_as_html(topic.get("takeaway", ""))
        ),
        "practice_note_html": sanitize_rich_text(
            topic.get("practice_note_html") or plain_text_as_html(topic.get("practice_note", ""))
        ),
        "practice_image": str(topic.get("practice_image", "")),
        "practice_image_alt": str(topic.get("practice_image_alt", "MOSAIC practice")),
    }


def normalize_carousel_payload(payload: dict, fallback_topic: dict) -> dict:
    """Validate database content before it enters the learner-facing page."""
    fallback = default_carousel_payload(fallback_topic)
    source_cards = payload.get("cards") if isinstance(payload, dict) else None
    cards = []
    for card_index, card_item in enumerate(
        source_cards if isinstance(source_cards, list) else fallback["cards"]
    ):
        if not isinstance(card_item, dict):
            continue
        title = str(card_item.get("title", "")).strip()
        if not title:
            continue
        cards.append(
            {
                "editor_id": carousel_card_editor_id(card_item, card_index),
                "label": str(card_item.get("label", "Core idea")).strip() or "Core idea",
                "title": title,
                "body_html": sanitize_rich_text(card_item.get("body_html", "")),
                "image_resource_id": str(card_item.get("image_resource_id") or "").strip(),
                "image_resource_ids": list(card_item.get("image_resource_ids") or []),
                "image_alt": str(card_item.get("image_alt") or title or "Idea image").strip(),
            }
        )
    return {
        "cards": cards if isinstance(source_cards, list) else fallback["cards"],
        "takeaway_html": sanitize_rich_text(payload.get("takeaway_html", fallback["takeaway_html"])),
        "practice_note_html": sanitize_rich_text(payload.get("practice_note_html", fallback["practice_note_html"])),
        "practice_image": str(payload.get("practice_image", fallback["practice_image"])),
        "practice_image_alt": str(payload.get("practice_image_alt", fallback["practice_image_alt"])),
    }


@st.cache_data(ttl=60, show_spinner=False)
def _published_carousels() -> list[dict]:
    """Avoid a Supabase round trip on every Streamlit rerun."""
    return list_published_carousels()



def _normalise_story_payload(story_id: str, payload: dict | None) -> dict:
    data = copy.deepcopy(payload or {})
    data["id"] = story_id
    data["title"] = str(data.get("title") or "Untitled story").strip()
    data["place"] = str(data.get("place") or "").strip()
    data["intro"] = str(data.get("intro") or "").strip()
    data["case_body"] = str(data.get("case_body") or "").strip()
    data["response_heading"] = str(data.get("response_heading") or "What changed when the decision was understood?").strip()
    data["response_body"] = str(data.get("response_body") or "").strip()
    data["lesson"] = str(data.get("lesson") or "").strip()
    data["source_label"] = str(data.get("source_label") or "Source").strip()
    data["source_url"] = str(data.get("source_url") or "").strip()
    data["video_url"] = str(data.get("video_url") or "").strip()
    data["image_asset"] = str(data.get("image_asset") or "").strip()
    data["image_caption"] = str(data.get("image_caption") or "").strip()
    return data


def _published_stories() -> list[dict]:
    defaults = {story_id: _normalise_story_payload(story_id, payload) for story_id, payload in DEFAULT_STORIES.items()}
    order = {story_id: index for index, story_id in enumerate(DEFAULT_STORIES, start=1)}
    for row in _cached_cms_stories():
        story_id = str(row.get("story_id") or "").strip()
        if not story_id:
            continue
        if row.get("archived"):
            defaults.pop(story_id, None)
            continue
        if row.get("published"):
            published_story = dict(row["published"])
            # Older CMS stories predate image fields: use the new built-in
            # illustration without overwriting any existing editorial text.
            built_in = DEFAULT_STORIES.get(story_id) or {}
            for field in ("image_asset", "image_caption"):
                if not published_story.get(field) and built_in.get(field):
                    published_story[field] = built_in[field]
            defaults[story_id] = _normalise_story_payload(story_id, published_story)
            order[story_id] = int(row.get("sort_order") or order.get(story_id, 999))
    return sorted(defaults.values(), key=lambda item: (order.get(item["id"], 999), item["title"].casefold()))


def _story_admin_snapshot() -> dict[str, dict]:
    snapshot = {
        story_id: {
            "story_id": story_id,
            "draft": copy.deepcopy(payload),
            "published": copy.deepcopy(payload),
            "sort_order": index,
            "archived": False,
            "updated_at": "",
            "published_at": "",
            "_builtin": True,
        }
        for index, (story_id, payload) in enumerate(DEFAULT_STORIES.items(), start=1)
    }
    for row in _cached_cms_stories():
        story_id = str(row.get("story_id") or "").strip()
        if not story_id:
            continue
        base = snapshot.get(story_id, {})
        merged = dict(base)
        merged.update(row)
        merged["_builtin"] = bool(base.get("_builtin"))
        if not merged.get("draft"):
            merged["draft"] = copy.deepcopy(base.get("draft") or merged.get("published") or {})
        snapshot[story_id] = merged
    return snapshot

def _module_content_payload(module_id: str, module: dict) -> dict:
    payload = copy.deepcopy(module or {})
    payload.pop("topics", None)
    for key in list(payload):
        if str(key).startswith("_cms_"):
            payload.pop(key, None)
    payload["id"] = module_id
    return payload


def _lesson_content_payload(lesson: dict) -> dict:
    payload = copy.deepcopy(lesson or {})
    for key in list(payload):
        if str(key).startswith("_cms_"):
            payload.pop(key, None)
    return payload


def _is_under_construction(item: dict | None) -> bool:
    """Handle explicit status and already-imported Coda placeholder tools."""
    item = item or {}
    if str(item.get("status") or "").strip().casefold() == "under construction":
        return True
    if item.get("source_system") == "superhuman_docs" and any(
        str(item.get(field) or "").strip().casefold() == "under construction"
        for field in ("description", "description_rich")
    ):
        return True
    return False


def _normalise_module_payload(module_id: str, payload: dict | None) -> dict:
    data = copy.deepcopy(payload or {})
    data.pop("topics", None)
    data["id"] = module_id
    data["title"] = str(data.get("title") or data.get("short_title") or module_id).strip()
    data["short_title"] = str(data.get("short_title") or data["title"]).strip()
    data["track"] = str(data.get("track") or "Learning").strip()
    data["track_icon"] = str(data.get("track_icon") or "◎").strip()
    data["description"] = str(data.get("description") or "").strip()
    data["status"] = str(data.get("status") or "Available").strip()
    data["eyebrow"] = str(data.get("eyebrow") or "Learning journey").strip()
    data["source_note"] = str(data.get("source_note") or "").strip()
    try:
        data["estimated_minutes"] = max(0, int(data.get("estimated_minutes") or 0))
    except (TypeError, ValueError):
        data["estimated_minutes"] = 0
    outcomes = data.get("learning_outcomes") or []
    if isinstance(outcomes, str):
        outcomes = [line.strip() for line in outcomes.splitlines() if line.strip()]
    data["learning_outcomes"] = [str(item).strip() for item in outcomes if str(item).strip()]
    if not isinstance(data.get("building_blocks"), list):
        data["building_blocks"] = []
    return data


def _normalise_lesson_payload(lesson_id: str, payload: dict | None) -> dict:
    data = copy.deepcopy(payload or {})
    data["id"] = lesson_id
    data["title"] = str(data.get("title") or lesson_id).strip()
    level = str(data.get("level") or "Understand").strip()
    data["level"] = level if level in {"Understand", "Apply", "Convince"} else "Understand"
    try:
        data["minutes"] = max(0, int(data.get("minutes") or 0))
    except (TypeError, ValueError):
        data["minutes"] = 0
    data["summary"] = str(data.get("summary") or "").strip()
    data["body"] = str(data.get("body") or "").strip()
    data["prompt"] = str(data.get("prompt") or "").strip()
    sources = data.get("sources") or []
    if isinstance(sources, str):
        sources = [line.strip() for line in sources.splitlines() if line.strip()]
    data["sources"] = [str(item).strip() for item in sources if str(item).strip()]
    resource_ids = data.get("resource_ids") or []
    if isinstance(resource_ids, str):
        resource_ids = [item.strip() for item in re.split(r"[,\n]", resource_ids) if item.strip()]
    data["resource_ids"] = list(dict.fromkeys(str(item).strip() for item in resource_ids if str(item).strip()))
    if not isinstance(data.get("theory_cards"), list):
        data["theory_cards"] = []
    checks = data.get("self_check") or []
    if isinstance(checks, str):
        checks = [line.strip() for line in checks.splitlines() if line.strip()]
    data["self_check"] = [str(item).strip() for item in checks if str(item).strip()]
    quiz = data.get("quiz")
    if quiz is not None and not isinstance(quiz, dict):
        data["quiz"] = None
    return data


def _normalise_tool_payload(tool_id: str, payload: dict | None) -> dict:
    data = copy.deepcopy(payload or {})
    data["id"] = tool_id
    data["title"] = str(data.get("title") or tool_id).strip()
    data["module_id"] = str(data.get("module_id") or "").strip()
    data["topic_id"] = str(data.get("topic_id") or "").strip()

    raw_links = data.get("lesson_links") or []
    links: list[dict[str, str]] = []
    if isinstance(raw_links, list):
        for item in raw_links:
            if isinstance(item, dict):
                module_id = str(item.get("module_id") or "").strip()
                lesson_id = str(item.get("lesson_id") or item.get("topic_id") or "").strip()
            elif isinstance(item, str) and "::" in item:
                module_id, lesson_id = [part.strip() for part in item.split("::", 1)]
            else:
                continue
            if module_id and lesson_id and {"module_id": module_id, "lesson_id": lesson_id} not in links:
                links.append({"module_id": module_id, "lesson_id": lesson_id})
    if not links and data["module_id"] and data["topic_id"]:
        links.append({"module_id": data["module_id"], "lesson_id": data["topic_id"]})
    data["lesson_links"] = links
    if links:
        # Keep the legacy fields populated for older templates and deep links.
        data["module_id"] = links[0]["module_id"]
        data["topic_id"] = links[0]["lesson_id"]

    data["duration"] = str(data.get("duration") or "").strip()
    # Older tool definitions used labels such as "worksheet" or "canvas".
    # In the learner repository these are all workshop methods unless an admin
    # explicitly publishes one of the other supported output formats.
    raw_format = str(data.get("format") or data.get("tool_type") or "Workshop").strip()
    format_lookup = {value.casefold(): value for value in TOOL_FORMATS}
    data["format"] = format_lookup.get(raw_format.casefold(), "Workshop")
    data["description"] = str(data.get("description") or data.get("outcome") or "").strip()
    data["status"] = str(data.get("status") or "Available").strip()
    data["website_url"] = str(data.get("website_url") or data.get("url") or "").strip()
    data["preview_url"] = str(data.get("preview_url") or "").strip()
    keywords = data.get("keywords") or []
    if isinstance(keywords, str):
        keywords = [item.strip() for item in re.split(r"[,\n]", keywords) if item.strip()]
    data["keywords"] = list(dict.fromkeys(str(item).strip() for item in keywords if str(item).strip()))
    steps = data.get("steps") or []
    if isinstance(steps, str):
        steps = [line.strip() for line in steps.splitlines() if line.strip()]
    data["steps"] = [str(item).strip() for item in steps if str(item).strip()]
    if not isinstance(data.get("prompts"), list):
        data["prompts"] = []
    return data


def _admin_tools_snapshot() -> dict[str, dict]:
    baseline = {
        tool_id: _normalise_tool_payload(tool_id, payload)
        for tool_id, payload in copy.deepcopy(_tool_definitions_baseline()).items()
    }
    rows = {row["tool_id"]: row for row in _cached_cms_tools()}
    tool_ids = list(baseline)
    for tool_id in rows:
        if tool_id not in tool_ids:
            tool_ids.append(tool_id)
    result = {}
    for index, tool_id in enumerate(tool_ids, start=1):
        row = rows.get(tool_id, {})
        source = row.get("draft") or row.get("published") or baseline.get(tool_id, {})
        tool = _normalise_tool_payload(tool_id, source)
        tool["_cms_archived"] = bool(row.get("archived"))
        tool["_cms_has_draft"] = bool(row.get("draft"))
        tool["_cms_has_published"] = bool(row.get("published"))
        tool["_cms_sort_order"] = int(row.get("sort_order") or index * 10)
        tool["_cms_updated_at"] = row.get("updated_at") or ""
        tool["_cms_published_at"] = row.get("published_at") or ""
        result[tool_id] = tool
    return dict(sorted(result.items(), key=lambda item: (int(item[1].get("_cms_sort_order") or 0), item[0])))



class _MosaicRepositoryHtmlParser(HTMLParser):
    """Small dependency-free HTML parser for the public MOSAIC repository."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tokens: list[dict[str, str]] = []
        self._current_href = ""
        self._current_heading = ""

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = str(tag or "").lower()
        attrs_dict = dict(attrs or [])
        if tag == "a":
            self._current_href = str(attrs_dict.get("href") or "")
        if tag in {"h1", "h2", "h3", "h4"}:
            self._current_heading = tag

    def handle_endtag(self, tag: str) -> None:
        tag = str(tag or "").lower()
        if tag == "a":
            self._current_href = ""
        if tag in {"h1", "h2", "h3", "h4"}:
            self._current_heading = ""

    def handle_data(self, data: str) -> None:
        text = " ".join(unescape(str(data or "")).split())
        if text:
            self.tokens.append({
                "text": text,
                "href": self._current_href,
                "heading": self._current_heading,
            })


def _mosaic_repository_url_allowed(url: str) -> bool:
    try:
        parsed = urlparse(str(url or "").strip())
    except ValueError:
        return False
    return parsed.scheme == "https" and parsed.hostname in MOSAIC_RESOURCE_HOSTS


def _mosaic_repository_request(url: str, *, max_bytes: int = 5 * 1024 * 1024, timeout: int = 25) -> tuple[bytes, str, str]:
    """Fetch one trusted MOSAIC page/file with a strict size and host guard."""
    if not _mosaic_repository_url_allowed(url):
        raise ValueError("The importer only follows HTTPS links on mosaic-europe.eu.")
    request = Request(
        url,
        headers={
            "User-Agent": "MOSAIC-Learn-resource-importer/1.0 (+https://mosaic-europe.eu/)",
            "Accept": "text/html,application/pdf;q=0.9,*/*;q=0.5",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            final_url = str(response.geturl() or url)
            if not _mosaic_repository_url_allowed(final_url):
                raise ValueError("The MOSAIC website redirected to a host the importer does not trust.")
            content_length = response.headers.get("Content-Length")
            if content_length:
                try:
                    if int(content_length) > max_bytes:
                        raise ValueError(f"Remote file is larger than the {round(max_bytes / (1024 * 1024))} MB import limit.")
                except ValueError as exc:
                    if "larger than" in str(exc):
                        raise
            data = response.read(max_bytes + 1)
            if len(data) > max_bytes:
                raise ValueError(f"Remote file is larger than the {round(max_bytes / (1024 * 1024))} MB import limit.")
            content_type = str(response.headers.get_content_type() or "application/octet-stream")
            return data, content_type, final_url
    except (HTTPError, URLError, TimeoutError) as exc:
        raise RuntimeError(f"Could not fetch {url}: {exc}") from exc


def _mosaic_repository_document(url: str) -> tuple[list[dict[str, str]], str, str]:
    """Return parsed text tokens plus raw HTML for discovery fallbacks."""
    data, content_type, final_url = _mosaic_repository_request(url)
    if content_type not in {"text/html", "application/xhtml+xml"}:
        raise RuntimeError(f"Expected a web page at {url}, but received {content_type}.")
    html_text = data.decode("utf-8", errors="replace")
    parser = _MosaicRepositoryHtmlParser()
    parser.feed(html_text)
    return parser.tokens, final_url, html_text


def _mosaic_repository_html(url: str) -> tuple[list[dict[str, str]], str]:
    tokens, final_url, _html_text = _mosaic_repository_document(url)
    return tokens, final_url


def _mosaic_canonical_resource_url(value: str, *, base_url: str) -> str:
    """Normalize one same-site /mosaic/resource/... URL and discard everything else."""
    candidate = unescape(str(value or "").strip()).replace("\\/", "/").replace("\\u002F", "/")
    if not candidate:
        return ""
    candidate = urljoin(base_url, candidate)
    try:
        parsed = urlparse(candidate)
    except ValueError:
        return ""
    if parsed.hostname not in MOSAIC_RESOURCE_HOSTS or not parsed.path.startswith("/mosaic/resource/"):
        return ""
    return f"https://{parsed.hostname}{parsed.path.rstrip('/')}"


def _mosaic_resource_urls_from_document(
    tokens: list[dict[str, str]],
    html_text: str,
    *,
    base_url: str,
) -> list[str]:
    """Discover resource links from visible anchors and Drupal/JS-embedded markup."""
    values: list[str] = []
    seen: set[str] = set()

    def add(raw_value: str) -> None:
        canonical = _mosaic_canonical_resource_url(raw_value, base_url=base_url)
        if canonical and canonical not in seen:
            seen.add(canonical)
            values.append(canonical)

    for token in tokens:
        add(str(token.get("href") or ""))

    normalized_markup = unescape(str(html_text or "")).replace("\\/", "/").replace("\\u002F", "/")
    pattern = r"(?:https://(?:www\.)?mosaic-europe\.eu)?/mosaic/resource/[^\s\"'<>\\#]+"
    for match in re.findall(pattern, normalized_markup, flags=re.IGNORECASE):
        add(match.rstrip(",;)]}"))
    return values


def _mosaic_resource_urls_from_sitemaps() -> list[str]:
    """Fallback discovery for repositories whose cards are loaded dynamically."""
    candidates = [
        "https://mosaic-europe.eu/sitemap.xml",
        "https://mosaic-europe.eu/sitemap_index.xml",
        "https://www.mosaic-europe.eu/sitemap.xml",
    ]
    queue = list(candidates)
    visited: set[str] = set()
    resources: list[str] = []
    resource_seen: set[str] = set()

    while queue and len(visited) < 24:
        sitemap_url = queue.pop(0)
        if sitemap_url in visited:
            continue
        visited.add(sitemap_url)
        try:
            data, content_type, final_url = _mosaic_repository_request(
                sitemap_url,
                max_bytes=8 * 1024 * 1024,
                timeout=18,
            )
        except Exception:
            continue
        if content_type not in {"application/xml", "text/xml", "text/plain", "application/octet-stream", "text/html"}:
            continue
        xml_text = data.decode("utf-8", errors="replace")
        probe = xml_text[:600].casefold()
        if "<urlset" not in probe and "<sitemapindex" not in probe:
            continue
        for raw_loc in re.findall(r"<loc[^>]*>(.*?)</loc>", xml_text, flags=re.IGNORECASE | re.DOTALL):
            loc = unescape(re.sub(r"\s+", "", raw_loc)).strip()
            resource_url = _mosaic_canonical_resource_url(loc, base_url=final_url)
            if resource_url:
                if resource_url not in resource_seen:
                    resource_seen.add(resource_url)
                    resources.append(resource_url)
                continue
            try:
                parsed = urlparse(loc)
            except ValueError:
                continue
            if (
                parsed.scheme == "https"
                and parsed.hostname in MOSAIC_RESOURCE_HOSTS
                and (parsed.path.endswith(".xml") or "sitemap" in parsed.path.casefold())
                and loc not in visited
                and loc not in queue
            ):
                queue.append(loc)
    return resources


def _mosaic_label(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().rstrip(":").casefold()


def _mosaic_section_text(
    tokens: list[dict[str, str]],
    start_labels: set[str],
    stop_labels: set[str],
    *,
    max_tokens: int = 80,
) -> str:
    starts = {_mosaic_label(label) for label in start_labels}
    stops = {_mosaic_label(label) for label in stop_labels}
    collecting = False
    collected: list[str] = []
    for token in tokens:
        text = str(token.get("text") or "").strip()
        label = _mosaic_label(text)
        if not collecting:
            if label in starts:
                collecting = True
            continue
        if label in stops:
            break
        if not text or label in starts:
            continue
        if not collected or collected[-1] != text:
            collected.append(text)
        if len(collected) >= max_tokens:
            break
    return " ".join(collected).strip()



def _mosaic_section_values(
    tokens: list[dict[str, str]],
    start_labels: set[str],
    stop_labels: set[str],
    *,
    max_tokens: int = 30,
) -> list[str]:
    starts = {_mosaic_label(label) for label in start_labels}
    stops = {_mosaic_label(label) for label in stop_labels}
    collecting = False
    values: list[str] = []
    for token in tokens:
        text = str(token.get("text") or "").strip()
        label = _mosaic_label(text)
        if not collecting:
            if label in starts:
                collecting = True
            continue
        if label in stops:
            break
        if text and label not in starts and (not values or values[-1] != text):
            values.append(text)
        if len(values) >= max_tokens:
            break
    return values


def _mosaic_section_link(
    tokens: list[dict[str, str]],
    start_labels: set[str],
    stop_labels: set[str],
    *,
    base_url: str,
) -> str:
    starts = {_mosaic_label(label) for label in start_labels}
    stops = {_mosaic_label(label) for label in stop_labels}
    collecting = False
    for token in tokens:
        text = str(token.get("text") or "").strip()
        label = _mosaic_label(text)
        if not collecting:
            if label in starts:
                collecting = True
            continue
        if label in stops:
            break
        href = str(token.get("href") or "").strip()
        if href:
            candidate = urljoin(base_url, href)
            try:
                parsed = urlparse(candidate)
            except ValueError:
                continue
            if parsed.scheme in {"http", "https"} and parsed.netloc:
                return candidate
    return ""



def _mosaic_section_links(
    tokens: list[dict[str, str]],
    start_labels: set[str],
    stop_labels: set[str],
    *,
    base_url: str,
) -> list[str]:
    starts = {_mosaic_label(label) for label in start_labels}
    stops = {_mosaic_label(label) for label in stop_labels}
    collecting = False
    links: list[str] = []
    for token in tokens:
        text = str(token.get("text") or "").strip()
        label = _mosaic_label(text)
        if not collecting:
            if label in starts:
                collecting = True
            continue
        if label in stops:
            break
        href = str(token.get("href") or "").strip()
        if not href:
            continue
        candidate = urljoin(base_url, href)
        try:
            parsed = urlparse(candidate)
        except ValueError:
            continue
        if parsed.scheme in {"http", "https"} and parsed.netloc and candidate not in links:
            links.append(candidate)
    return links


def _mosaic_guess_resource_type(title: str, description: str, pdf_url: str) -> str:
    haystack = f"{title} {description}".casefold()
    if any(term in haystack for term in ("systematic review", "journal article", "paper", "publication")):
        return "Paper"
    if any(term in haystack for term in ("deliverable", "report", "guideline", "guidelines")) or pdf_url:
        return "Report"
    return "Resource"


def _mosaic_resource_fingerprint(item: dict) -> str:
    fields = {
        key: item.get(key) or ([] if key == "tags" else "")
        for key in (
            "title", "description", "authors", "publication_date", "year",
            "resource_type", "source_page_url", "publication_url", "pdf_url", "pdf_urls", "tags",
        )
    }
    return hashlib.sha256(
        json.dumps(fields, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _mosaic_parse_resource_detail(source_url: str) -> dict:
    tokens, final_url = _mosaic_repository_html(source_url)
    title = next(
        (
            str(token.get("text") or "").strip()
            for token in tokens
            if token.get("heading") == "h1" and str(token.get("text") or "").strip()
        ),
        "",
    )
    stop_labels = {
        "Author/Contact", "Author/Contact:", "Publication date", "Publication date:",
        "Resource link", "Resource link:", "Resource download", "Resource download:",
        "Keywords", "Keywords:", "Resource type", "Resource type:", "Details",
    }
    description = _mosaic_section_text(
        tokens,
        {"Resource description", "Resource description:"},
        stop_labels,
    )
    authors = _mosaic_section_text(
        tokens,
        {"Author/Contact", "Author/Contact:"},
        {"Publication date", "Publication date:", "Resource link", "Resource link:", "Resource download", "Resource download:"},
        max_tokens=12,
    )
    publication_date = _mosaic_section_text(
        tokens,
        {"Publication date", "Publication date:"},
        {"Quality assurance", "Quality assurance:", "Resource link", "Resource link:", "Resource download", "Resource download:", "Keywords", "Keywords:"},
        max_tokens=4,
    )
    year_match = re.search(r"\b(?:19|20)\d{2}\b", publication_date)
    year = year_match.group(0) if year_match else ""
    publication_url = _mosaic_section_link(
        tokens,
        {"Resource link", "Resource link:"},
        {"Resource download", "Resource download:", "Keywords", "Keywords:", "Resource type", "Resource type:"},
        base_url=final_url,
    )
    pdf_urls = _mosaic_section_links(
        tokens,
        {"Resource download", "Resource download:"},
        {"Keywords", "Keywords:", "Resource type", "Resource type:", "Scale", "Scale:", "Project", "Project:", "Details", "Mosaic footer"},
        base_url=final_url,
    )
    pdf_url = pdf_urls[0] if pdf_urls else ""
    keyword_values = _mosaic_section_values(
        tokens,
        {"Keywords", "Keywords:"},
        {"Resource type", "Resource type:", "Scale", "Scale:", "Project", "Project:", "Details", "Funding"},
        max_tokens=20,
    )
    tags: list[str] = []
    for value in keyword_values:
        for item in re.split(r"[,;|]", value):
            item = item.strip()
            if item and len(item) <= 80 and item not in tags:
                tags.append(item)
    resource_type = _mosaic_section_text(
        tokens,
        {"Resource type", "Resource type:"},
        {"Scale", "Scale:", "Project", "Project:", "Details", "Funding", "Keywords", "Keywords:"},
        max_tokens=3,
    )
    if not resource_type or len(resource_type) > 80:
        resource_type = _mosaic_guess_resource_type(title, description, pdf_url)
    source_id = unquote(urlparse(final_url).path.rstrip("/").split("/")[-1]).strip().casefold()
    item = {
        "source_id": source_id,
        "title": title or source_id.replace("-", " ").title(),
        "description": description,
        "authors": authors,
        "publication_date": publication_date,
        "year": year,
        "resource_type": resource_type,
        "source_page_url": final_url,
        "publication_url": publication_url,
        "pdf_url": pdf_url,
        "pdf_urls": pdf_urls,
        "tags": list(dict.fromkeys(tags)),
    }
    item["fingerprint"] = _mosaic_resource_fingerprint(item)
    return item


@st.cache_data(ttl=900, show_spinner=False)
def _fetch_mosaic_repository_items() -> dict:
    """Read the public MOSAIC repository and return normalized resource metadata.

    Drupal can expose different amounts of repository markup to different
    clients, so discovery combines direct anchors, embedded raw URLs,
    pagination variants, and the site's XML sitemap.
    """
    resource_urls: list[str] = []
    seen: set[str] = set()
    discovery = {"repository": 0, "pagination": 0, "sitemap": 0, "fallback": 0}
    repository_url = MOSAIC_RESOURCE_REPOSITORY_URL

    def add_many(urls: list[str], source: str) -> int:
        added = 0
        for candidate in urls:
            canonical = _mosaic_canonical_resource_url(candidate, base_url=repository_url)
            if canonical and canonical not in seen:
                seen.add(canonical)
                resource_urls.append(canonical)
                added += 1
        discovery[source] = discovery.get(source, 0) + added
        return added

    tokens, repository_url, html_text = _mosaic_repository_document(MOSAIC_RESOURCE_REPOSITORY_URL)
    add_many(
        _mosaic_resource_urls_from_document(tokens, html_text, base_url=repository_url),
        "repository",
    )

    no_new_pages = 0
    page_candidates = ["https://mosaic-europe.eu/mosaic/mosaic-resources"] + [
        f"{MOSAIC_RESOURCE_REPOSITORY_URL}?page={page}" for page in range(0, 12)
    ]
    for page_url in page_candidates:
        try:
            page_tokens, page_final_url, page_html = _mosaic_repository_document(page_url)
        except Exception:
            continue
        added = add_many(
            _mosaic_resource_urls_from_document(page_tokens, page_html, base_url=page_final_url),
            "pagination",
        )
        no_new_pages = 0 if added else no_new_pages + 1
        if no_new_pages >= 4 and len(resource_urls) >= 2:
            break

    add_many(_mosaic_resource_urls_from_sitemaps(), "sitemap")

    # Some Streamlit Cloud requests receive a minimally rendered Drupal view
    # even though the browser-visible repository contains many cards. If all
    # dynamic discovery layers still yield fewer than two items, seed the known
    # current catalogue so the importer remains useful. These URLs are then
    # validated by fetching their individual resource pages below.
    if len(resource_urls) < 2:
        add_many(
            [urljoin(MOSAIC_RESOURCE_REPOSITORY_URL, path) for path in MOSAIC_RESOURCE_FALLBACK_PATHS],
            "fallback",
        )

    if not resource_urls:
        raise RuntimeError("No resource pages were found on the MOSAIC repository page or site sitemap.")

    items: list[dict] = []
    errors: list[str] = []
    max_workers = min(6, max(1, len(resource_urls)))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_mosaic_parse_resource_detail, url): url for url in resource_urls}
        for future in as_completed(futures):
            url = futures[future]
            try:
                items.append(future.result())
            except Exception as exc:
                errors.append(f"{url}: {exc}")
    order = {url: idx for idx, url in enumerate(resource_urls)}
    items.sort(
        key=lambda item: order.get(
            _mosaic_canonical_resource_url(item.get("source_page_url", ""), base_url=repository_url),
            9999,
        )
    )
    return {
        "repository_url": repository_url,
        "found": len(resource_urls),
        "items": items,
        "errors": errors,
        "discovery": discovery,
    }


def _normalised_external_url(value: str | None) -> str:
    try:
        parsed = urlparse(str(value or "").strip())
    except ValueError:
        return ""
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    path = unquote(parsed.path or "").rstrip("/")
    return f"{parsed.netloc.casefold()}{path}?{parsed.query}".rstrip("?")


def _mosaic_import_match(resources: dict[str, dict], remote: dict) -> str:
    remote_source = _normalised_external_url(remote.get("source_page_url"))
    source_id = str(remote.get("source_id") or "").strip().casefold()
    for resource_id, local in resources.items():
        if source_id and str(local.get("import_source_id") or "").strip().casefold() == source_id:
            return resource_id
        if remote_source and _normalised_external_url(local.get("source_page_url")) == remote_source:
            return resource_id
    # Conservative fallback for resources added manually before the importer existed.
    remote_publication = _normalised_external_url(remote.get("publication_url"))
    remote_title = str(remote.get("title") or "").strip().casefold()
    for resource_id, local in resources.items():
        if str(local.get("origin") or "") != "MOSAIC content":
            continue
        if remote_title and str(local.get("title") or "").strip().casefold() != remote_title:
            continue
        local_publication = _normalised_external_url(local.get("publication_url") or local.get("source_url"))
        if not remote_publication or not local_publication or remote_publication == local_publication:
            return resource_id
    return ""


def _mosaic_import_state(resources: dict[str, dict], remote: dict) -> tuple[str, str]:
    resource_id = _mosaic_import_match(resources, remote)
    if not resource_id:
        return "New", ""
    local = resources[resource_id]
    previous_fingerprint = str(local.get("import_fingerprint") or "")
    if not previous_fingerprint:
        return "Needs review", resource_id
    if previous_fingerprint != str(remote.get("fingerprint") or ""):
        return "Source changed", resource_id
    return "Already in library", resource_id


def _mosaic_resource_id(source_id: str, resources: dict[str, dict]) -> str:
    slug = re.sub(r"[^a-z0-9-]+", "-", str(source_id or "resource").casefold()).strip("-")
    slug = re.sub(r"-+", "-", slug) or "resource"
    base = f"mosaic-{slug}"[:63].rstrip("-")
    if len(base) < 2:
        base = "mosaic-resource"
    candidate = base
    suffix = 2
    while candidate in resources:
        candidate = f"{base[:58].rstrip('-')}-{suffix}"
        suffix += 1
    return candidate


def _mosaic_payload_from_remote(remote: dict, *, existing: dict | None = None) -> dict:
    existing = copy.deepcopy(existing or {})
    payload = {
        key: value
        for key, value in existing.items()
        if not str(key).startswith("_cms_") and key != "_sort_order"
    }
    existing_tags = [str(item).strip() for item in payload.get("tags") or [] if str(item).strip()]
    remote_tags = [str(item).strip() for item in remote.get("tags") or [] if str(item).strip()]
    payload.update({
        "title": str(remote.get("title") or payload.get("title") or "MOSAIC resource").strip(),
        "origin": "MOSAIC content",
        "resource_type": str(payload.get("resource_type") or remote.get("resource_type") or "Resource").strip(),
        "authors": str(remote.get("authors") or "").strip(),
        "year": str(remote.get("year") or "").strip(),
        "publication_date": str(remote.get("publication_date") or "").strip(),
        "description": str(remote.get("description") or "").strip(),
        "source_page_url": str(remote.get("source_page_url") or "").strip(),
        "publication_url": str(remote.get("publication_url") or "").strip(),
        # source_url is retained as a backwards-compatible alias used by older builds.
        "source_url": str(remote.get("publication_url") or "").strip(),
        "tags": list(dict.fromkeys(existing_tags + remote_tags)),
        "related_modules": list(payload.get("related_modules") or []),
        "import_source": "MOSAIC Knowledge Repository",
        "import_source_id": str(remote.get("source_id") or "").strip(),
        "import_fingerprint": str(remote.get("fingerprint") or "").strip(),
    })
    return payload


def _download_mosaic_pdf(pdf_url: str) -> tuple[str, str, bytes]:
    if not pdf_url:
        raise ValueError("No PDF download is listed for this resource.")
    data, mime_type, final_url = _mosaic_repository_request(
        pdf_url,
        max_bytes=MOSAIC_IMPORT_MAX_BYTES,
        timeout=45,
    )
    path_name = unquote(Path(urlparse(final_url).path).name).strip()
    if not path_name:
        path_name = "mosaic-resource.pdf"
    if not path_name.lower().endswith(".pdf") and mime_type == "application/pdf":
        path_name += ".pdf"
    if mime_type != "application/pdf" and not path_name.lower().endswith(".pdf"):
        raise ValueError(f"The download is not a PDF ({mime_type}).")
    return _safe_resource_filename(path_name), "application/pdf", data


def _attach_imported_pdfs(user: dict, resource_id: str, remote: dict) -> dict[str, object]:
    active_files = [row for row in _resource_files_for("library", resource_id) if not row.get("archived")]
    existing_ids = {str(row.get("resource_id") or "") for row in active_files}
    existing_pdf_rows = [
        row for row in active_files
        if str(row.get("mime_type") or "").casefold() == "application/pdf"
        or str(row.get("file_name") or "").lower().endswith(".pdf")
    ]
    pdf_urls = [str(url).strip() for url in (remote.get("pdf_urls") or []) if str(url).strip()]
    if not pdf_urls and remote.get("pdf_url"):
        pdf_urls = [str(remote.get("pdf_url") or "").strip()]
    pdf_urls = list(dict.fromkeys(pdf_urls))
    if not pdf_urls:
        return {"attached": 0, "skipped": 0, "errors": []}

    # If an older/manual record already has a PDF but none of the deterministic
    # importer IDs, avoid creating a likely duplicate. New importer-created
    # records have no files yet, while subsequent imports can identify their own
    # files by stable IDs and add newly-listed PDFs safely.
    imported_ids = {
        hashlib.sha256(f"mosaic-import:{resource_id}:{url}".encode("utf-8")).hexdigest()[:32]
        for url in pdf_urls
    }
    if existing_pdf_rows and not (existing_ids & imported_ids):
        return {"attached": 0, "skipped": len(pdf_urls), "errors": []}

    attached = 0
    skipped = 0
    errors: list[str] = []
    for sort_index, pdf_url in enumerate(pdf_urls, start=1):
        stable_file_id = hashlib.sha256(f"mosaic-import:{resource_id}:{pdf_url}".encode("utf-8")).hexdigest()[:32]
        if stable_file_id in existing_ids:
            skipped += 1
            continue
        try:
            file_name, mime_type, file_data = _download_mosaic_pdf(pdf_url)
        except Exception as exc:
            errors.append(f"{pdf_url}: {exc}")
            continue
        save_cms_resource_file(
            stable_file_id,
            scope_type="library",
            scope_id=resource_id,
            resource_kind="PDF",
            title=str(remote.get("title") or file_name),
            description="Imported from the MOSAIC Knowledge Repository.",
            file_name=file_name,
            mime_type=mime_type,
            file_data=file_data,
            sort_order=sort_index * 10,
            updated_by=user["user_id"],
        )
        existing_ids.add(stable_file_id)
        attached += 1
    return {"attached": attached, "skipped": skipped, "errors": errors}


def _render_mosaic_repository_importer(user: dict, resources: dict[str, dict]) -> None:
    preview_key = "mosaic-repository-import-preview"
    with st.expander("↻ Import from the MOSAIC website", expanded=bool(st.session_state.get(preview_key))):
        st.caption(
            "Scan the public MOSAIC Knowledge Repository, compare it with this library and create only new items as drafts. Existing records are never overwritten automatically."
        )
        fetch_col, source_col = st.columns([1, 2.2], vertical_alignment="center")
        with fetch_col:
            if st.button("Check MOSAIC repository", key="studio-mosaic-import-check", type="primary", width="stretch"):
                try:
                    _fetch_mosaic_repository_items.clear()
                    with st.spinner("Reading the MOSAIC repository…"):
                        st.session_state[preview_key] = _fetch_mosaic_repository_items()
                except Exception as exc:
                    st.session_state.pop(preview_key, None)
                    st.error(f"The repository could not be checked: {exc}")
        with source_col:
            st.markdown(
                f"Source: [{MOSAIC_RESOURCE_REPOSITORY_URL}]({MOSAIC_RESOURCE_REPOSITORY_URL})"
            )

        preview = st.session_state.get(preview_key)
        if not preview:
            return
        remote_items = list(preview.get("items") or [])
        classified: list[dict] = []
        for remote in remote_items:
            status, match_id = _mosaic_import_state(resources, remote)
            classified.append({"remote": remote, "status": status, "match_id": match_id})
        new_items = [item for item in classified if item["status"] == "New"]
        changed_items = [item for item in classified if item["status"] in {"Source changed", "Needs review"}]
        existing_items = [item for item in classified if item["status"] == "Already in library"]

        a, b, c, d = st.columns(4)
        a.metric("Found", int(preview.get("found") or len(remote_items)))
        b.metric("New", len(new_items))
        c.metric("Already here", len(existing_items))
        d.metric("Review", len(changed_items))

        discovery = preview.get("discovery") or {}
        if discovery:
            st.caption(
                "Discovery: "
                f"{int(discovery.get('repository') or 0)} from repository markup · "
                f"{int(discovery.get('pagination') or 0)} from page variants · "
                f"{int(discovery.get('sitemap') or 0)} from sitemap · "
                f"{int(discovery.get('fallback') or 0)} from current-repository fallback"
            )

        if preview.get("errors"):
            with st.expander(f"{len(preview['errors'])} source page(s) could not be read"):
                for error in preview["errors"]:
                    st.caption(error)

        table_rows = []
        for entry in classified:
            remote = entry["remote"]
            table_rows.append({
                "Status": entry["status"],
                "Title": remote.get("title", ""),
                "Year": remote.get("year", ""),
                "Type": remote.get("resource_type", "Resource"),
                "PDFs": len(remote.get("pdf_urls") or ([remote.get("pdf_url")] if remote.get("pdf_url") else [])),
            })
        if table_rows:
            st.dataframe(table_rows, width="stretch", hide_index=True)

        download_pdfs = st.checkbox(
            "Download available PDFs into the protected MOSAIC Learn database",
            value=True,
            key="studio-mosaic-import-pdfs",
            help="Files larger than 25 MB are skipped and the source link is still kept.",
        )
        if new_items:
            if st.button(
                f"Import {len(new_items)} new resource{'s' if len(new_items) != 1 else ''} as drafts",
                key="studio-mosaic-import-new",
                type="primary",
            ):
                max_sort = max([int(item.get("_cms_sort_order") or 0) for item in resources.values()] or [0])
                imported = 0
                pdf_attached = 0
                pdf_errors: list[str] = []
                working_resources = dict(resources)
                for offset, entry in enumerate(new_items, start=1):
                    remote = entry["remote"]
                    resource_id = _mosaic_resource_id(str(remote.get("source_id") or "resource"), working_resources)
                    payload = _mosaic_payload_from_remote(remote)
                    payload["id"] = resource_id
                    save_cms_library_resource_draft(
                        resource_id,
                        payload,
                        max_sort + offset * 10,
                        user["user_id"],
                    )
                    working_resources[resource_id] = payload
                    imported += 1
                    if download_pdfs:
                        pdf_result = _attach_imported_pdfs(user, resource_id, remote)
                        pdf_attached += int(pdf_result.get("attached") or 0)
                        pdf_errors.extend(
                            f"{remote.get('title')}: {message}"
                            for message in (pdf_result.get("errors") or [])
                        )
                _clear_content_studio_caches()
                st.session_state.pop(preview_key, None)
                message = f"Imported {imported} new MOSAIC resource{'s' if imported != 1 else ''} as drafts."
                if download_pdfs:
                    message += f" Attached {pdf_attached} PDF{'s' if pdf_attached != 1 else ''}."
                if pdf_errors:
                    message += f" {len(pdf_errors)} PDF download{'s' if len(pdf_errors) != 1 else ''} could not be stored; their source links were kept."
                _content_studio_flash(message)
                st.rerun()
        else:
            st.success("No new repository items to import.")

        if changed_items:
            st.markdown("#### Matches and source updates to review")
            st.caption(
                "These records either match an older manually-added item or were imported before and changed on the MOSAIC website. Nothing is overwritten until you explicitly apply the website metadata to its draft. Published content stays unchanged until you publish it again."
            )
            changed_options = list(range(len(changed_items)))
            selected_idx = st.selectbox(
                "Resource with an update",
                changed_options,
                format_func=lambda idx: changed_items[idx]["remote"].get("title", "MOSAIC resource"),
                key="studio-mosaic-update-select",
            )
            selected = changed_items[int(selected_idx)]
            remote = selected["remote"]
            local = resources[selected["match_id"]]
            left, right = st.columns(2, gap="large")
            with left:
                st.markdown("**Current draft / local record**")
                st.caption(f"Year: {local.get('year') or '—'}")
                st.write(local.get("authors") or "No authors recorded")
                st.write(local.get("description") or "No description recorded")
            with right:
                st.markdown("**Current MOSAIC website**")
                st.caption(f"Year: {remote.get('year') or '—'}")
                st.write(remote.get("authors") or "No authors listed")
                st.write(remote.get("description") or "No description listed")
            if st.button("Apply website metadata to this draft", key="studio-mosaic-apply-update", type="secondary"):
                resource_id = selected["match_id"]
                payload = _mosaic_payload_from_remote(remote, existing=local)
                payload["id"] = resource_id
                save_cms_library_resource_draft(
                    resource_id,
                    payload,
                    int(local.get("_cms_sort_order") or 0),
                    user["user_id"],
                )
                if download_pdfs:
                    _attach_imported_pdfs(user, resource_id, remote)
                _clear_content_studio_caches()
                st.session_state.pop(preview_key, None)
                _content_studio_flash("The updated MOSAIC metadata was applied to the draft for review. The published resource was not changed.")
                st.rerun()

def _normalise_library_resource_payload(resource_id: str, payload: dict | None) -> dict:
    data = copy.deepcopy(payload or {})
    data["id"] = resource_id
    data["title"] = str(data.get("title") or resource_id).strip()
    data["description"] = str(data.get("description") or "").strip()
    origin = str(data.get("origin") or "MOSAIC content").strip()
    data["origin"] = origin if origin in {"MOSAIC content", "External content"} else "MOSAIC content"
    data["resource_type"] = str(data.get("resource_type") or "Report").strip()
    data["authors"] = str(data.get("authors") or "").strip()
    data["year"] = str(data.get("year") or "").strip()
    data["publication_date"] = str(data.get("publication_date") or "").strip()
    data["source_page_url"] = str(data.get("source_page_url") or "").strip()
    publication_url = str(data.get("publication_url") or data.get("source_url") or "").strip()
    data["publication_url"] = publication_url
    # Keep source_url for compatibility with deployments from before the importer.
    data["source_url"] = publication_url
    data["import_source"] = str(data.get("import_source") or "").strip()
    data["import_source_id"] = str(data.get("import_source_id") or "").strip()
    data["import_fingerprint"] = str(data.get("import_fingerprint") or "").strip()
    tags = data.get("tags") or []
    if isinstance(tags, str):
        tags = [item.strip() for item in re.split(r"[,\n]", tags) if item.strip()]
    data["tags"] = list(dict.fromkeys(str(item).strip() for item in tags if str(item).strip()))
    related = data.get("related_modules") or []
    if isinstance(related, str):
        related = [item.strip() for item in re.split(r"[,\n]", related) if item.strip()]
    data["related_modules"] = list(dict.fromkeys(str(item).strip() for item in related if str(item).strip()))
    return data


def _admin_library_resource_snapshot() -> dict[str, dict]:
    result: dict[str, dict] = {}
    for index, row in enumerate(_cached_cms_library_resources(), start=1):
        resource_id = str(row.get("resource_id") or "")
        source = row.get("draft") or row.get("published") or {}
        item = _normalise_library_resource_payload(resource_id, source)
        item["_cms_archived"] = bool(row.get("archived"))
        item["_cms_has_draft"] = bool(row.get("draft"))
        item["_cms_has_published"] = bool(row.get("published"))
        item["_cms_sort_order"] = int(row.get("sort_order") or index * 10)
        item["_cms_updated_at"] = row.get("updated_at") or ""
        item["_cms_published_at"] = row.get("published_at") or ""
        result[resource_id] = item
    return dict(sorted(result.items(), key=lambda kv: (int(kv[1].get("_cms_sort_order") or 0), kv[1].get("title", "").casefold())))


def _published_library_resources() -> dict[str, dict]:
    result: dict[str, dict] = {}
    for row in _cached_cms_library_resources():
        if row.get("archived") or not row.get("published"):
            continue
        resource_id = str(row.get("resource_id") or "")
        item = _normalise_library_resource_payload(resource_id, row.get("published"))
        item["_sort_order"] = int(row.get("sort_order") or 0)
        result[resource_id] = item
    return dict(sorted(result.items(), key=lambda kv: (int(kv[1].get("_sort_order") or 0), kv[1].get("title", "").casefold())))


def _resource_files_for(scope_type: str, scope_id: str, *, include_archived: bool = False) -> list[dict]:
    return _cached_resource_files(scope_type, scope_id, include_archived)


def _resource_image_data_uri(resource_id: str | None) -> str:
    if not resource_id:
        return ""
    record = _cached_resource_file(str(resource_id))
    if not record or record.get("archived") or not record.get("file_data"):
        return ""
    mime_type = str(record.get("mime_type") or "").lower()
    if not mime_type.startswith("image/"):
        return ""
    encoded = base64.b64encode(record["file_data"]).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _module_cover_uri(module: dict) -> str:
    """Read a published module image from the existing file store or a safe URL.

    The manual Superhuman Docs importer persists this once at publication;
    learner visits never call the Superhuman Docs API.
    """
    resource_id = str(module.get("cover_image_resource_id") or "")
    if resource_id:
        uri = _resource_image_data_uri(resource_id)
        if uri:
            return uri
    url = str(module.get("cover_image_url") or "")
    return url if _valid_external_url(url) else ""


def _idea_image_scope_id(module_id: str, lesson_id: str, card_id: str) -> str:
    return f"{module_id}:{lesson_id}:{card_id}"


def _tool_lesson_links(tool: dict) -> list[tuple[str, str]]:
    links = []
    for item in tool.get("lesson_links") or []:
        if not isinstance(item, dict):
            continue
        module_id = str(item.get("module_id") or "").strip()
        lesson_id = str(item.get("lesson_id") or item.get("topic_id") or "").strip()
        if module_id and lesson_id and (module_id, lesson_id) not in links:
            links.append((module_id, lesson_id))
    if not links:
        module_id = str(tool.get("module_id") or "").strip()
        lesson_id = str(tool.get("topic_id") or "").strip()
        if module_id and lesson_id:
            links.append((module_id, lesson_id))
    return links


def _tools_for_learning_step(module_id: str, lesson_id: str) -> list[tuple[str, dict]]:
    return [
        (tool_id, tool)
        for tool_id, tool in TOOL_DEFINITIONS.items()
        if (module_id, lesson_id) in _tool_lesson_links(tool)
    ]


def _tool_module_label(tool: dict) -> str:
    module_ids = []
    for module_id, _ in _tool_lesson_links(tool):
        if module_id not in module_ids:
            module_ids.append(module_id)
    if not module_ids and tool.get("module_id"):
        module_ids.append(str(tool.get("module_id")))
    labels = [MODULES[mid]["short_title"] for mid in module_ids if mid in MODULES]
    if not labels:
        return "MOSAIC Learn"
    if len(labels) <= 2:
        return " · ".join(labels)
    return f"{labels[0]} + {len(labels) - 1} more"


def _tool_download_payload(tool_id: str, tool: dict) -> tuple[bytes, str, str, int]:
    files: list[tuple[str, bytes, str]] = []
    used_names: set[str] = set()
    for meta in _resource_files_for("tool", tool_id):
        record = _cached_resource_file(meta["resource_id"])
        if not record or record.get("archived") or not record.get("file_data"):
            continue
        name = _safe_resource_filename(record.get("file_name"))
        base_name = name
        counter = 2
        while name in used_names:
            stem = Path(base_name).stem
            suffix = Path(base_name).suffix
            name = f"{stem}-{counter}{suffix}"
            counter += 1
        used_names.add(name)
        files.append((name, record["file_data"], str(record.get("mime_type") or "application/octet-stream")))
    for file_name in TOOL_DOWNLOAD_FILES.get(tool_id, []):
        file_path, file_type, error = configured_tool_file(file_name)
        if not file_path or error:
            continue
        name = _safe_resource_filename(file_name)
        if name in used_names:
            continue
        used_names.add(name)
        files.append((name, file_path.read_bytes(), file_type[1]))

    if not files:
        data = tool_template_markdown(tool_id, tool).encode("utf-8")
        return data, f"{tool_id}-resources.md", "text/markdown", 1
    if len(files) == 1:
        name, data, mime_type = files[0]
        return data, name, mime_type, 1

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data, _mime_type in files:
            archive.writestr(name, data)
    return buffer.getvalue(), f"{tool_id}-resources.zip", "application/zip", len(files)


def _format_file_size(size_bytes: int | None) -> str:
    size = max(0, int(size_bytes or 0))
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def _valid_content_id(value: str) -> bool:
    return bool(re.fullmatch(r"[a-z0-9][a-z0-9-]{1,63}", str(value or "").strip().lower()))


def _admin_catalogue_snapshot() -> dict[str, dict]:
    """Merge content.py with CMS drafts for the editor without changing learner pages."""
    baseline = copy.deepcopy(_content_py_baseline())
    module_rows = {row["module_id"]: row for row in _cached_cms_modules()}
    lesson_rows: dict[str, dict[str, dict]] = {}
    for row in _cached_cms_lessons():
        lesson_rows.setdefault(row["module_id"], {})[row["lesson_id"]] = row

    module_ids = list(baseline)
    for module_id in module_rows:
        if module_id not in module_ids:
            module_ids.append(module_id)

    result: dict[str, dict] = {}
    for base_index, module_id in enumerate(module_ids, start=1):
        base_module = baseline.get(module_id, {})
        row = module_rows.get(module_id, {})
        source = row.get("draft") or row.get("published") or _module_content_payload(module_id, base_module)
        module = _normalise_module_payload(module_id, source)
        module["_cms_archived"] = bool(row.get("archived"))
        module["_cms_has_draft"] = bool(row.get("draft"))
        module["_cms_has_published"] = bool(row.get("published")) or bool(base_module)
        module["_cms_updated_at"] = row.get("updated_at") or ""
        module["_cms_published_at"] = row.get("published_at") or ""
        module["_cms_sort_order"] = int(row.get("sort_order") or base_index * 10)

        base_topics = {
            str(item.get("id")): item
            for item in base_module.get("topics", [])
            if item.get("id")
        }
        all_lesson_ids = list(base_topics)
        for lesson_id in lesson_rows.get(module_id, {}):
            if lesson_id not in all_lesson_ids:
                all_lesson_ids.append(lesson_id)
        lessons = []
        for lesson_index, lesson_id in enumerate(all_lesson_ids, start=1):
            base_lesson = base_topics.get(lesson_id, {})
            lesson_row = lesson_rows.get(module_id, {}).get(lesson_id, {})
            lesson_source = lesson_row.get("draft") or lesson_row.get("published") or base_lesson
            lesson = _normalise_lesson_payload(lesson_id, lesson_source)
            lesson["_cms_archived"] = bool(lesson_row.get("archived"))
            lesson["_cms_has_draft"] = bool(lesson_row.get("draft"))
            lesson["_cms_has_published"] = bool(lesson_row.get("published")) or bool(base_lesson)
            lesson["_cms_updated_at"] = lesson_row.get("updated_at") or ""
            lesson["_cms_published_at"] = lesson_row.get("published_at") or ""
            lesson["_cms_sort_order"] = int(lesson_row.get("sort_order") or lesson_index * 10)
            lessons.append(lesson)
        lessons.sort(key=lambda item: (int(item.get("_cms_sort_order") or 0), item["id"]))
        module["topics"] = lessons
        result[module_id] = module

    return dict(
        sorted(
            result.items(),
            key=lambda item: (int(item[1].get("_cms_sort_order") or 0), item[0]),
        )
    )


def apply_published_carousel_overrides() -> None:
    """Overlay administrator-published idea/carousel content on the active catalogue."""
    for record in _published_carousels():
        module = MODULES.get(record.get("module_id"))
        if not module:
            continue
        topic = next(
            (item for item in module.get("topics", []) if item.get("id") == record.get("topic_id")),
            None,
        )
        if not topic:
            continue
        # Superhuman Docs is authoritative for imported cards. A legacy
        # carousel override must never hide a newly published page update.
        if topic.get("source_system") == "superhuman_docs":
            continue
        payload = normalize_carousel_payload(record.get("content") or {}, topic)
        topic["theory_cards"] = payload["cards"]
        topic["takeaway_html"] = payload["takeaway_html"]
        topic["practice_note_html"] = payload["practice_note_html"]
        topic["practice_image"] = payload["practice_image"]
        topic["practice_image_alt"] = payload["practice_image_alt"]


def apply_published_tool_content() -> None:
    """Overlay published tool metadata while keeping content.py as the safe fallback."""
    baseline = {
        tool_id: _normalise_tool_payload(tool_id, payload)
        for tool_id, payload in copy.deepcopy(_tool_definitions_baseline()).items()
    }
    rows = {row["tool_id"]: row for row in _cached_cms_tools()}
    tool_order = {tool_id: (index + 1) * 10 for index, tool_id in enumerate(baseline)}
    catalogue = baseline
    for tool_id, row in rows.items():
        if row.get("archived"):
            catalogue.pop(tool_id, None)
            continue
        if row.get("published"):
            catalogue[tool_id] = _normalise_tool_payload(tool_id, row["published"])
        if tool_id in catalogue:
            tool_order[tool_id] = int(row.get("sort_order") or tool_order.get(tool_id, 9990))
    ordered = dict(sorted(catalogue.items(), key=lambda item: (tool_order.get(item[0], 9990), item[0])))
    TOOL_DEFINITIONS.clear()
    TOOL_DEFINITIONS.update(ordered)


def apply_published_learning_content() -> None:
    """Rebuild modules and tools from content.py plus published CMS overrides."""
    baseline = copy.deepcopy(_content_py_baseline())
    module_rows = {row["module_id"]: row for row in _cached_cms_modules()}
    lesson_rows: dict[str, list[dict]] = {}
    for row in _cached_cms_lessons():
        lesson_rows.setdefault(row["module_id"], []).append(row)

    catalogue = baseline
    base_module_order = {module_id: (index + 1) * 10 for index, module_id in enumerate(baseline)}

    for module_id, row in module_rows.items():
        if row.get("archived"):
            catalogue.pop(module_id, None)
            continue
        published = row.get("published")
        if not published:
            continue
        existing_topics = copy.deepcopy(catalogue.get(module_id, {}).get("topics", []))
        module = _normalise_module_payload(module_id, published)
        module["topics"] = existing_topics
        catalogue[module_id] = module

    for module_id, module in list(catalogue.items()):
        base_topics = [copy.deepcopy(item) for item in module.get("topics", [])]
        topic_map = {str(item.get("id")): item for item in base_topics if item.get("id")}
        topic_order = {str(item.get("id")): (index + 1) * 10 for index, item in enumerate(base_topics) if item.get("id")}
        for row in lesson_rows.get(module_id, []):
            lesson_id = row["lesson_id"]
            if row.get("archived"):
                topic_map.pop(lesson_id, None)
                topic_order.pop(lesson_id, None)
                continue
            published = row.get("published")
            if published:
                published_lesson = _normalise_lesson_payload(lesson_id, published)
                topic_map[lesson_id] = published_lesson
            if lesson_id in topic_map:
                topic_order[lesson_id] = int(row.get("sort_order") or topic_order.get(lesson_id, 9990))
        module["topics"] = [
            topic_map[lesson_id]
            for lesson_id in sorted(topic_map, key=lambda lesson_id: (topic_order.get(lesson_id, 9990), lesson_id))
        ]

    module_order = dict(base_module_order)
    for module_id, row in module_rows.items():
        if module_id in catalogue:
            module_order[module_id] = int(row.get("sort_order") or module_order.get(module_id, 9990))
    ordered = dict(
        sorted(catalogue.items(), key=lambda item: (module_order.get(item[0], 9990), item[0]))
    )
    MODULES.clear()
    MODULES.update(ordered)
    apply_published_tool_content()
    apply_published_carousel_overrides()


def _configured_admin_emails() -> set[str]:
    raw = _secret("ADMIN_EMAILS", [])
    if isinstance(raw, str):
        values = raw.split(",")
    else:
        values = list(raw or [])
    return {str(value).strip().lower() for value in values if str(value).strip()}


def is_administrator(user: dict) -> bool:
    return user.get("account_role") == "administrator"


def is_content_editor(user: dict) -> bool:
    return user.get("account_role") in {"editor", "administrator"}


def is_production_environment() -> bool:
    """Production is explicit, with PostgreSQL also treated as production-safe intent."""
    environment = str(_secret("APP_ENV", "")).strip().lower()
    if environment == "local":
        return False
    return environment == "production" or database_backend() == "postgres"


def validate_runtime_configuration() -> None:
    """Fail closed when a production deployment is missing persistent storage."""
    if str(_secret("APP_ENV", "")).strip().lower() == "production" and database_backend() != "postgres":
        st.error(
            "Production database is not configured. Add a valid Supabase DATABASE_URL "
            "to Streamlit Secrets before launching this deployment."
        )
        st.stop()


def auth_is_configured() -> bool:
    try:
        return "auth" in st.secrets
    except Exception:
        return False


def navigate(
    route: str,
    module_id: str | None = None,
    topic_id: str | None = None,
    tool_id: str | None = None,
    phase: str | None = None,
    *,
    _rerun: bool = True,
):
    """Update route and URL. Widget callbacks use _rerun=False for one render.

    Calling st.rerun() from a normal button body aborts the already-started
    widget-triggered run and can strand the previous route as stale elements.
    Navigation buttons therefore call this in on_click, before the new run.
    _rerun=True is reserved for programmatic route validation.
    """
    st.session_state.route = route
    if module_id is not None:
        if str(module_id).strip():
            st.session_state.module_id = module_id
        else:
            st.session_state.pop("module_id", None)
    if topic_id is not None:
        if str(topic_id).strip():
            st.session_state.topic_id = topic_id
        else:
            st.session_state.pop("topic_id", None)
    elif route != "topic":
        st.session_state.pop("topic_id", None)
    if tool_id is not None:
        if str(tool_id).strip():
            st.session_state.tool_id = tool_id
        else:
            st.session_state.pop("tool_id", None)
    elif route == "tools":
        st.session_state.pop("tool_id", None)
    elif route != "tools":
        st.session_state.pop("tool_id", None)

    if route == "phase":
        st.session_state["phase"] = str(phase or st.session_state.get("phase") or "discover").lower()
    else:
        st.session_state.pop("phase", None)
    if route == "topic" and module_id and topic_id:
        st.session_state[f"theory-step-{module_id}-{topic_id}"] = 1
    _write_route_query(route, module_id=module_id, topic_id=topic_id, tool_id=tool_id)
    if _rerun:
        st.rerun()


def _auth_provider_names() -> list[str]:
    """Return named OIDC providers configured under [auth.<provider>]."""
    if not auth_is_configured():
        return []
    try:
        auth = st.secrets["auth"]
        names = []
        for key in auth.keys():
            try:
                value = auth[key]
            except Exception:
                continue
            if hasattr(value, "keys") and key not in {"client_kwargs"}:
                names.append(str(key))
        return names
    except Exception:
        return []


def _provider_label(provider: str) -> str:
    labels = {
        "microsoft": "Microsoft",
        "google": "Google",
        "entra": "Microsoft",
        "auth0": "Auth0",
        "okta": "Okta",
    }
    return labels.get(provider.lower(), provider.replace("-", " ").title())


def _render_sign_in_prompt():
    """Explain the shared Google sign-in/registration flow and start OIDC."""
    st.markdown(
        """
        <div class="m-module-hero learning">
            <div class="m-kicker">MOSAIC Learn</div>
            <h1>Sign in to continue</h1>
            <p>Sign in when you are ready to learn, join Community or save your progress. The same Google button works for new and returning learners.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    providers = _auth_provider_names()
    if providers:
        cols = st.columns(min(len(providers), 2))
        for idx, provider in enumerate(providers):
            with cols[idx % len(cols)]:
                if st.button(
                    f"Continue with {_provider_label(provider)}",
                    key=f"login-{provider}",
                    type="primary",
                    width="stretch",
                ):
                    st.login(provider)
    else:
        if st.button("Sign in to MOSAIC Learn", type="primary", width="stretch"):
            st.login()
    st.caption(
        "First-time users create a MOSAIC learner profile after Google returns them to the app. "
        "Returning users resume the profile and progress already linked to their Google identity."
    )


def get_current_user(required: bool = True) -> dict | None:
    """Return the current identity, prompting only when a protected page requires it.

    In production, configure [auth] in Streamlit Secrets. Identity is keyed from
    the OIDC issuer + subject, not from email, so a changed email does not create
    a second learning profile.
    """
    if auth_is_configured():
        if not st.user.is_logged_in:
            if not required:
                return None
            _render_sign_in_prompt()
            st.stop()

        claims = st.user.to_dict() if hasattr(st.user, "to_dict") else dict(st.user)
        email = claims.get("email") or claims.get("preferred_username") or ""
        subject = str(claims.get("sub") or claims.get("oid") or email or "learner")
        issuer = str(claims.get("iss") or "oidc")
        name = claims.get("name") or claims.get("given_name") or (str(email).split("@")[0] if email else "Learner")
        user_id = hashlib.sha256(f"{issuer}|{subject}".encode("utf-8")).hexdigest()[:32]
        return {
            "user_id": user_id,
            "email": str(email),
            "name": str(name),
            "auth_issuer": issuer,
            "auth_subject": subject,
            "demo": False,
        }

    # Local development fallback. A hosted/PostgreSQL deployment must configure
    # OIDC; otherwise an unauthenticated visitor could obtain local admin access.
    if is_production_environment():
        if not required:
            return None
        st.error(
            "Google sign-in is not configured. Add the [auth] settings in your "
            "Streamlit Cloud Secrets before using the hosted app."
        )
        st.stop()

    st.session_state.setdefault("demo_user", None)
    if not st.session_state.demo_user:
        if not required:
            return None
        st.markdown(
            """
            <div class="m-module-hero learning">
                <div class="m-kicker">MOSAIC Learn · local development</div>
                <h1>Local development sign-in</h1>
                <p>OIDC and PostgreSQL are not configured, so this computer uses SQLite and a local administrator identity for testing.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        with st.form("demo_login", border=True):
            name = st.text_input("Name", value="Alex Learner")
            email = st.text_input("Email", value="alex@example.org")
            submitted = st.form_submit_button("Enter local preview", type="primary")
        if submitted:
            if "@" not in email:
                st.error("Enter a plausible email address for the local preview.")
                st.stop()
            subject = email.strip().lower()
            user_id = hashlib.sha256(f"demo|{subject}".encode("utf-8")).hexdigest()[:32]
            st.session_state.demo_user = {
                "user_id": user_id,
                "email": subject,
                "name": name.strip() or "Learner",
                "auth_issuer": "demo",
                "auth_subject": subject,
                "account_role": "administrator",
                "demo": True,
            }
            st.rerun()
        st.stop()

    return st.session_state.demo_user


def render_privacy_notice(*, compact: bool = False) -> None:
    """Render the current privacy notice in onboarding, the modal and its page."""
    if not compact:
        st.markdown("<div class='m-kicker'>Account & data</div>", unsafe_allow_html=True)
        st.title("Privacy notice")
    st.caption(
        f"Version {PRIVACY_POLICY_VERSION} · effective {PRIVACY_POLICY_EFFECTIVE_DATE}"
    )
    st.markdown(
        """
        **Who is responsible**

        MOSAIC Learn is operated within the MOSAIC project and coordinated through VITO Nexus. Questions about this notice or the use of your personal data can be sent to [dieter.cuypers@vito.be](mailto:dieter.cuypers@vito.be).

        **What information is stored**

        - Basic identity information received from Google sign-in: name, email address and a provider-specific account identifier.
        - Profile information you choose to provide: professional role, organisation, country or region, and learning interests.
        - Learning activity: completed steps, quick-check results, confidence ratings and private reflections.
        - Content you actively share, such as Community posts and public result summaries.
        - Optional Mycelium data when you choose to join: membership, connection requests and accepted connections, plus whether you chose to share your email with a specific connection request.
        - Account permissions and, for editors or administrators, content-editing activity.
        - The privacy-notice version you accepted and the time of acceptance.

        **Why the information is used**

        The information is used to authenticate your account, save your learning record, tailor the learning experience, support Community features, provide result sharing that you initiate, and keep the service secure and operational. MOSAIC Learn does not sell personal data, use it for advertising or make decisions with legal or similarly significant effects through automated profiling.

        **Services involved**

        Google provides sign-in, Streamlit Community Cloud hosts the application, and Supabase/PostgreSQL stores production application data. These providers process information according to their own terms and the configuration selected by the MOSAIC Learn operators.

        **Visibility and sharing**

        Profile details, progress, quick-check results and reflections are private to your account and authorised administrators. A Community post becomes visible to other signed-in learners only when you publish it. Joining **Our mycelium** is optional; if you join, your name, organisation and country or region are visible to other opted-in Mycelium members. A connection request is visible only to the requester and intended recipient until it is accepted. Your email address is shared with that recipient only when you explicitly select the email-sharing option for the request. A result summary becomes accessible to anyone with its generated link, but private reflections are excluded.

        **Retention and deletion**

        Account-linked information is kept while your account remains active. You can permanently delete the live account and its linked learning data from **My profile**. Temporary infrastructure backups may remain for a limited period according to the hosting and database providers' backup schedules.

        **Your choices and rights**

        You can view and edit your profile, withdraw consent by deleting your account, and contact the address above to ask about access, correction, restriction, portability, objection or deletion. You may also have the right to lodge a complaint with your national data-protection authority.

        **Changes to this notice**

        The current version is recorded with your account. If `PRIVACY_POLICY_VERSION` is changed in the application, MOSAIC Learn will show a blocking notice and require you to review and accept the new version before continuing. You are not asked to agree in advance to unknown future changes.
        """
    )


@st.dialog("Privacy notice updated", width="large", dismissible=False)
def privacy_reconsent_dialog(user_id: str) -> None:
    st.write(
        "The MOSAIC Learn privacy notice has changed. Review the current version before continuing."
    )
    with st.expander("Read the complete privacy notice", expanded=True):
        render_privacy_notice(compact=True)
    accepted = st.checkbox(
        f"I have read and agree to privacy notice version {PRIVACY_POLICY_VERSION}."
    )
    if st.button(
        "Accept and continue",
        type="primary",
        width="stretch",
        disabled=not accepted,
    ):
        _record_privacy_acceptance(user_id)
        st.rerun()


def page_privacy() -> None:
    render_privacy_notice()
    st.info(
        "This is an operational privacy notice for the current MOSAIC Learn prototype. "
        "The project owner should have the final text, controller details, retention periods "
        "and processor arrangements reviewed by the responsible privacy or legal contact before public launch."
    )


def ensure_profile(user: dict) -> dict:
    """Create the account record and show one-time learner onboarding."""
    stored = _cached_user_record(
        user["user_id"],
        user.get("email", ""),
        user.get("name", "Learner"),
        user.get("auth_issuer", ""),
        user.get("auth_subject", ""),
    )
    bootstrap_admin = bool(user.get("demo")) or user.get("email", "").strip().lower() in _configured_admin_emails()
    if bootstrap_admin and stored.get("account_role") != "administrator":
        _save_account_role(user["user_id"], "administrator")
        stored = get_user(user["user_id"]) or stored
    user["account_role"] = stored.get("account_role") or "learner"
    if stored.get("profile_complete"):
        if stored.get("privacy_policy_version") != PRIVACY_POLICY_VERSION:
            privacy_reconsent_dialog(user["user_id"])
            st.stop()
        user["role"] = stored.get("role", "")
        user["organisation"] = stored.get("organisation", "")
        user["country"] = stored.get("country", "")
        user["interests"] = stored.get("interests", [])
        user["privacy_policy_version"] = stored.get("privacy_policy_version", "")
        user["privacy_accepted_at"] = stored.get("privacy_accepted_at", "")
        return user

    st.markdown(
        """
        <div class="m-module-hero community">
            <div class="m-kicker">Welcome to MOSAIC Learn</div>
            <h1>Create your learner profile</h1>
            <p>A few details help us make module recommendations and keep your learning record meaningful. You can edit them later.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    available_modules = [
        (module_id, module)
        for module_id, module in MODULES.items()
        if module.get("status") == "Available"
    ]
    interest_labels = [module["short_title"] for _, module in available_modules]
    label_to_id = {module["short_title"]: module_id for module_id, module in available_modules}

    with st.form("profile-onboarding", border=True):
        st.markdown(f"**Signed in as:** {escape(user.get('name', 'Learner'))}")
        role = st.selectbox("What best describes your work?", list(ROLE_CALLOUTS))
        organisation = st.text_input("Organisation (optional)", placeholder="University, municipality, NGO, company…")
        country = st.text_input("Country or region (optional)", placeholder="Belgium, Portugal, EU-wide…")
        chosen = st.multiselect(
            "What would you like to explore?",
            interest_labels,
            default=interest_labels[:1],
        )
        st.caption("Your private reflections are not shown in Community unless you explicitly publish a separate community post.")
        with st.expander("Read the privacy notice"):
            render_privacy_notice(compact=True)
        privacy_accepted = st.checkbox(
            f"I have read and agree to privacy notice version {PRIVACY_POLICY_VERSION}."
        )
        update_acknowledged = st.checkbox(
            "I understand that MOSAIC Learn will ask me to review and accept a new version before I can continue if this notice changes."
        )
        submitted = st.form_submit_button("Create my profile", type="primary", width="stretch")
    if submitted:
        if not privacy_accepted or not update_acknowledged:
            st.error("Accept the current privacy notice and confirm the update process to create your profile.")
        else:
            _save_profile(
                user["user_id"],
                role=role,
                organisation=organisation,
                country=country,
                interests=[label_to_id[label] for label in chosen],
                profile_complete=True,
            )
            _record_privacy_acceptance(user["user_id"])
            navigate("home")
    st.stop()

def module_completion(user_id: str, module_id: str):
    module = MODULES[module_id]
    topics = learning_topics(module)
    if not topics:
        return 0.0, 0, 0
    progress = _cached_progress(user_id, module_id)
    completed = sum(1 for topic in topics if progress.get(topic["id"], {}).get("completed"))
    return completed / len(topics), completed, len(topics)


def first_incomplete_topic(user_id: str, module_id: str) -> str | None:
    module = MODULES[module_id]
    topics = learning_topics(module)
    progress = _cached_progress(user_id, module_id)
    for topic in topics:
        if not progress.get(topic["id"], {}).get("completed"):
            return topic["id"]
    return topics[-1]["id"] if topics else None


def topic_by_id(module_id: str, topic_id: str):
    return next((t for t in MODULES[module_id]["topics"] if t["id"] == topic_id), None)


def progress_bar_html(ratio: float) -> str:
    pct = max(0, min(100, round(ratio * 100)))
    return (
        f'<div class="m-progress-shell"><div class="m-progress-fill" style="width:{pct}%"></div></div>'
    )


def _module_card_excerpt(description: str, max_words: int = 40) -> str:
    """Limit only overview-card copy; preserve complete text elsewhere."""
    words = re.findall(r"\S+", str(description or ""))
    return " ".join(words[:max_words]) + ("…" if len(words) > max_words else "")


def module_card_html(module_id: str, user_id: str | None = None) -> str:
    module = MODULES[module_id]
    topics = learning_topics(module)
    if user_id:
        ratio, done, total = module_completion(user_id, module_id)
        progress = progress_bar_html(ratio) if total else ""
        topic_meta = f"{done}/{total} learning steps" if total else "Module structure coming soon"
    else:
        total = len(topics)
        progress = ""
        topic_meta = f"{total} learning steps" if total else "Module structure coming soon"
    track_class = module["track"].lower()
    cover_uri = _module_cover_uri(module)
    status_text = str(module.get("status") or "")
    status_html = (
        ""
        if status_text == "Available"
        else f'<span class="m-status soon">{escape(status_text)}</span>'
    )
    kicker_margin = ".65rem" if status_html else "0"
    return (
        f'<div class="m-module-card">'
        f'<div class="m-module-art {track_class}{" has-cover" if cover_uri else ""}">'
        f'{"<img loading=\"lazy\" decoding=\"async\" alt=\"\" src=\"" + escape(cover_uri, quote=True) + "\">" if cover_uri else ""}'
        f'</div>'
        f'<div class="m-module-body">'
        f'{status_html}'
        f'<div class="m-kicker" style="margin-top:{kicker_margin}">{escape(module["track"])}</div>'
        f'<h3>{escape(module["short_title"])}</h3>'
        f'<p>{escape(_module_card_excerpt(module["description"]))}</p>'
        f'{progress}<div class="m-module-meta"><span>{escape(topic_meta)}</span><span>•</span><span>{module["estimated_minutes"]} min</span></div>'
        f'</div></div>'
    )


def render_sidebar(user: dict | None):
    route = st.session_state.get("route", "home")
    unread_community = (
        _cached_unread_community_notifications(user["user_id"]) if user else 0
    )
    with st.sidebar:
        st.markdown(brand_home_html(sidebar=True), unsafe_allow_html=True)
        if user:
            st.caption(f"{user['name']} · {user.get('email', '')}")
        else:
            st.caption("Browse freely. Sign in when you start learning or join Community.")
        st.markdown("---")

        items = [
            ("home", "⌂  Home"),
            ("our-story", "◌  Our story"),
            ("catalogue", "▦  Learning"),
            ("resources", "▤  Resources"),
            ("tools", "◇  Tools"),
            ("community", "✣  Community"),
        ]
        for key, label in items:
            button_type = "primary" if route == key else "secondary"
            st.button(label, key=f"nav-{key}", width="stretch", type=button_type, on_click=navigate, args=(key, None, None, None, None), kwargs={"_rerun": False})

        if unread_community:
            badge_text = "9+" if unread_community > 9 else str(unread_community)
            st.markdown(
                f"""
                <style>
                .st-key-nav-community button::after {{
                    content:"{badge_text}";
                    position:absolute;
                    right:.62rem;
                    top:50%;
                    transform:translateY(-50%);
                    display:flex;
                    align-items:center;
                    justify-content:center;
                    min-width:1.15rem;
                    height:1.15rem;
                    padding:0 .22rem;
                    border-radius:999px;
                    background:#d6283f;
                    color:#fff;
                    font-size:.64rem;
                    font-weight:700;
                    line-height:1;
                    box-shadow:0 0 0 2px #fff;
                }}
                </style>
                """,
                unsafe_allow_html=True,
            )

        # Keep reference and legal pages together beneath a quiet divider.
        st.markdown("---")
        reference_items = []
        if user:
            reference_items.append(("profile", "○  My profile"))
        reference_items.extend([
            ("privacy", "Privacy notice"),
            ("glossary", "A–Z  Glossary"),
            ("contact", "✉  Contact"),
        ])
        for key, label in reference_items:
            button_type = "primary" if route == key else "secondary"
            st.button(label, key=f"nav-{key}", width="stretch", type=button_type, on_click=navigate, args=(key, None, None, None, None), kwargs={"_rerun": False})
        if user and is_content_editor(user):
            st.caption("CONTENT")
            st.button(
                "✎  Content studio",
                key="nav-admin",
                width="stretch",
                type="primary" if route == "admin" else "secondary",
             on_click=navigate, args=("admin", None, None, None, None), kwargs={"_rerun": False})

        if user and route in {"module", "topic", "convince"}:
            st.markdown("---")
            module_id = st.session_state.get("module_id", "drivers")
            module = MODULES.get(module_id) or next(iter(MODULES.values()), None)
            if module is not None:
                if module_id not in MODULES:
                    module_id = next(iter(MODULES))
                st.caption("OPEN MODULE")
                st.markdown(f"**{module['short_title']}**")
                ratio, done, total = module_completion(user["user_id"], module_id)
                st.progress(ratio, text=f"{done}/{total} learning steps")
                st.button("Module overview", width="stretch", on_click=navigate, args=("module", module_id, None, None, None), kwargs={"_rerun": False})
            if module is not None and module.get("status") == "Available":
                st.button("Communicate: briefs & resources", key=f"side-convince-{module_id}", width="stretch", type="primary" if route == "convince" else "secondary", on_click=navigate, args=("convince", module_id, None, None, None), kwargs={"_rerun": False})

            if route == "topic":
                topic_id = st.session_state.get("topic_id")
                progress = _cached_progress(user["user_id"], module_id)
                for idx, topic in enumerate(learning_topics(module), start=1):
                    marker = "✓" if progress.get(topic["id"], {}).get("completed") else str(idx)
                    prefix = "→" if topic["id"] == topic_id else marker
                    st.button(f"{prefix}  {topic['title']}", key=f"side-topic-{topic['id']}", width="stretch", on_click=navigate, args=("topic", module_id, topic["id"], None, None), kwargs={"_rerun": False})


def page_home(user: dict | None):
    loop_art = asset_image_html(
        ILLUSTRATION_SLOTS["home"],
        alt="Hand-drawn MOSAIC learning loop: drivers of change, policy labs and future pathways",
        css_class="m-hero-loop-image",
    ) or "<div class='m-drawing-placeholder' aria-hidden='true'><span>Drivers · Policy Labs · Future Pathways</span><small>Place your learning-loop drawing here</small></div>"
    st.markdown(
        f"""
        <div class="m-hero m-illustrated-home">
            <div class="m-hero-copy">
                <div class="m-kicker">MOSAIC Learn</div>
                <h1>MOSAIC Learn:  <em>Land Use Change</em> and <em>Management</em> in Europe</h1>
                <p>MOSAIC brings practitioners, research partners and policy makers together to understand and influence how land across Europe can be managed more sustainably. Learn turns the project's research and Policy Lab experience into practical journeys, tools and evidence.</p>
                <div class="m-hero-meta"><span class="m-chip">Self-paced</span><span class="m-chip">Practice-oriented</span><span class="m-chip">Progress saved</span><span class="m-chip">Evidence you can reuse</span></div>
            </div>
            <div class="m-hero-art m-hero-drawn">{loop_art}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.container(key="ground_story"):
        story_copy, story_media = st.columns([0.9, 1.35], gap="large", vertical_alignment="center")
        with story_copy:
            st.markdown(
                """
                <div class="m-ground-story-copy">
                    <div class="m-kicker">Story from on the ground</div>
                    <h2>See the learning in a real-world context</h2>
                    <p>MOSAIC Learn is rooted in the realities of land-use decisions. This featured story brings the people, places and practical challenges behind the learning into view.</p>
                    <div class="m-ground-story-note">Field perspective · featured story</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.button("Read our stories →", key="home-open-our-story", type="primary", on_click=navigate, args=("our-story", None, None, None, None), kwargs={"_rerun": False})
        with story_media:
            st.video(LANDING_STORY_VIDEO_URL)

    st.markdown("<div class='m-section-title'><h2>Find your starting point</h2><p>The MOSAIC learning loop can move between collaboration, understanding and future action.</p></div>", unsafe_allow_html=True)
    cols = st.columns(3)
    tracks = [
        (
            "Community",
            "◫",
            "Share experiences, questions and reflections with other MOSAIC learners.",
            "community",
            None,
            "community",
        ),
        (
            "Learning",
            "◎",
            "Understand the deeper drivers behind current land-use decisions.",
            "catalogue",
            None,
            "learning",
        ),
        (
            "MOSAIC Learn Agent",
            "✦",
            "Discuss your project with our agent.",
            "resources",
            None,
            "empowerment",
        ),
    ]
    for col, (title, icon, text, target_type, target_id, style_class) in zip(cols, tracks):
        with col:
            st.markdown(
                f"<div class='m-track-card {style_class}'><div class='m-track-icon' aria-hidden='true'>{icon}</div><h3>{title}</h3><p>{text}</p></div>",
                unsafe_allow_html=True,
            )

            if target_type == "community":
                button_label = "Open community →"
            elif target_type == "catalogue":
                button_label = "Explore learning modules →"
            elif target_type == "learning":
                button_label = "Open my learning →"
            elif target_type == "resources":
                button_label = "Explore the agent →"
            else:
                button_label = "Open →"

            st.button(
                button_label,
                key=f"home-track-{target_type}",
                width="stretch",
             on_click=navigate, args=(target_type, target_id, None, None, None), kwargs={"_rerun": False})

    learning_heading = "Where do you want to start?"
    learning_intro = "Explore all MOSAIC Learn modules. Start an available module now, or subscribe for updates when a module is still under construction."

    st.markdown(
        f"<div class='m-section-title'><h2>{learning_heading}</h2><p>{learning_intro}</p></div>",
        unsafe_allow_html=True,
    )
    home_modules = list(MODULES.items())
    if not home_modules:
        st.info("No learning modules are currently published.")
    else:
        column_count = min(3, len(home_modules))
        cols = st.columns(column_count)
        for idx, (module_id, module) in enumerate(home_modules):
            with cols[idx % column_count]:
                user_id = user["user_id"] if user else None
                st.markdown(module_card_html(module_id, user_id), unsafe_allow_html=True)
                if module.get("status") == "Available":
                    st.button(
                        "Get started →",
                        key=f"home-continue-{module_id}",
                        type="primary",
                        width="stretch",
                     on_click=navigate, args=("module", module_id, None, None, None), kwargs={"_rerun": False})
                elif _is_under_construction(module):
                    st.link_button(
                        "Under construction · subscribe for updates →",
                        MOSAIC_NEWSLETTER_URL,
                        type="secondary",
                        width="stretch",
                    )
                else:
                    st.button(
                        str(module.get("status") or "Coming soon"),
                        key=f"home-soon-{module_id}",
                        disabled=True,
                        width="stretch",
                    )


def _learning_reflection_items(user: dict) -> list[dict]:
    reflections: list[dict] = []
    for module_id, module in MODULES.items():
        if module.get("status") != "Available":
            continue
        module_progress = _cached_progress(user["user_id"], module_id)
        for topic in module.get("topics", []):
            saved = module_progress.get(topic["id"], {})
            text = (saved.get("reflection") or "").strip()
            if text:
                reflections.append({
                    "module_id": module_id,
                    "module": module,
                    "topic": topic,
                    "text": text,
                    "updated_at": saved.get("updated_at") or "",
                })
    reflections.sort(key=lambda item: item["updated_at"], reverse=True)
    return reflections


def render_learning_overview(user: dict) -> None:
    available = [(mid, m) for mid, m in MODULES.items() if m.get("status") == "Available"]
    if not available:
        st.info("No modules are available yet.")
        return
    st.markdown("<div class='m-section-title'><h2>My learning</h2><p>Continue active modules and see what is next without leaving the learning hub.</p></div>", unsafe_allow_html=True)
    for module_id, module in available:
        ratio, done, total = module_completion(user["user_id"], module_id)
        next_topic_id = first_incomplete_topic(user["user_id"], module_id)
        next_topic = topic_by_id(module_id, next_topic_id) if next_topic_id else None
        with st.container(border=True):
            a, b = st.columns([3.4, 1], vertical_alignment="center")
            with a:
                st.markdown(f"<div class='m-kicker'>{escape(module['track'])} · {module['estimated_minutes']} min</div>", unsafe_allow_html=True)
                st.subheader(module["title"])
                st.progress(ratio, text=f"{round(ratio * 100)}% complete · {done}/{total} learning steps")
                if next_topic:
                    st.caption(f"Next: {next_topic['level']} · {next_topic['title']} · {next_topic['minutes']} min")
            with b:
                if next_topic:
                    st.button("Continue →", key=f"hub-continue-{module_id}", type="primary", width="stretch", on_click=navigate, args=("topic", module_id, next_topic_id, None, None), kwargs={"_rerun": False})
                st.button("Module overview", key=f"hub-overview-{module_id}", width="stretch", on_click=navigate, args=("module", module_id, None, None, None), kwargs={"_rerun": False})


def render_reflection_notebook(user: dict) -> None:
    st.markdown("<div class='m-section-title'><h2>Reflection notebook</h2><p>Everything you save while learning, together in one place and still private to you.</p></div>", unsafe_allow_html=True)
    reflections = _learning_reflection_items(user)
    if not reflections:
        st.info("You have not saved any reflections yet. Add one from a learning step and it will appear here.")
        return
    module_choices = ["All modules"] + list(dict.fromkeys(item["module"]["short_title"] for item in reflections))
    selected_module = st.selectbox("Show reflections from", module_choices, key="learning-reflection-filter")
    shown = [item for item in reflections if selected_module == "All modules" or item["module"]["short_title"] == selected_module]
    for idx, item in enumerate(shown):
        date_text = str(item["updated_at"])[:10]
        st.markdown(
            f"<div class='m-reflection-card'><div class='meta'><strong>{escape(item['module']['short_title'])}</strong> · {escape(item['topic']['level'])} · {escape(date_text)}</div><h4>{escape(item['topic']['title'])}</h4><p>{escape(item['text'])}</p></div>",
            unsafe_allow_html=True,
        )
        st.button("Open learning step →", key=f"learning-reflection-open-{item['module_id']}-{item['topic']['id']}-{idx}", on_click=navigate, args=("topic", item["module_id"], item["topic"]["id"], None, None), kwargs={"_rerun": False})


def _future_scenarios_first_class(modules: dict) -> tuple[str, str] | None:
    """Open the first Discover class of the published Future Scenarios module.

    Manual Superhuman imports may use a stable page ID rather than the old
    'future-pathways' slug. Resolve by module title, then by stable legacy ID.
    """
    candidates = []
    for module_id, module in modules.items():
        title = " ".join(str(module.get(field) or "") for field in ("title", "short_title"))
        lowered = title.casefold()
        score = 0
        if "future scenario" in lowered: score = 5
        elif "future pathway" in lowered or "modelling future" in lowered: score = 4
        elif module_id == "future-pathways": score = 3
        if score and module.get("status") == "Available":
            candidates.append((score, module_id, module))
    for _score, module_id, module in sorted(candidates, key=lambda x: -x[0]):
        discover = [topic for topic in (module.get("topics") or [])
                    if topic.get("level") in {"Understand", "Discover"}]
        if not discover:
            continue
        preferred = next((topic for topic in discover
                          if "vision" in str(topic.get("title") or "").lower()
                          and ("scenario" in str(topic.get("title") or "").lower()
                               or "pathway" in str(topic.get("title") or "").lower())), None)
        return module_id, str((preferred or discover[0])["id"])
    return None


def _start_module_for_question(modules: dict, kind: str) -> str | None:
    """Resolve a published module after Superhuman Docs has assigned a stable ID.

    Prefer the imported module over old content.py defaults. Keep fallbacks
    for sites that have not yet imported that module.
    """
    tokens = {
        "drivers": ("drivers research", "drivers of change", "driver research", "identifying drivers", "drivers"),
        "policy-lab": ("policy labs", "policy lab", "participatory policy"),
        "future-pathways": ("future scenarios", "future pathways", "modelling future"),
    }.get(kind, ())
    candidates = []
    for module_id, module in modules.items():
        if str(module.get("status") or "Available").casefold() != "available":
            continue
        searchable = " ".join(str(module.get(field) or "") for field in ("title", "short_title")).casefold()
        matching = next((index for index, name in enumerate(tokens) if name in searchable), None)
        if matching is None and module_id != kind:
            continue
        imported = str(module.get("source_system") or "") == "superhuman_docs" or module_id.startswith("sh-")
        # A newer imported module takes priority over the legacy hardcoded slug.
        candidates.append((0 if imported else 1, matching if matching is not None else len(tokens), module_id))
    return min(candidates)[2] if candidates else None


def _render_starting_point_guide_catalogue() -> None:
    guide_image = asset_image_html(
        "starting-point-heron.png",
        alt="A heron standing among reeds and their reflections in the water",
        css_class="m-start-illustration",
    )
    with st.container(key="catalogue_starting_guide"):
        st.markdown(
            f"""
            <div class="m-start-intro">
                <div class="m-start-copy">
                    <div class="m-kicker">Find your starting point</div>
                    <h2>Not sure where to start?</h2>
                    <p>Take a moment. Think about a piece of land you care about: a field, a forest, a neighbourhood, a nature reserve or a farm.</p>
                    <p class="m-start-reflection">Take away or add one element - a plant or animal, a person or community, soil or water. What changes? Who would notice this change first?</p>
                </div>
                <div class="m-start-image">{guide_image}</div>
            </div>
            <div class="m-start-question">
                <h3>What brought you here today?</h3>
                <p>Choose the question that comes closest. Each choice points you to a useful starting module.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        starting_paths = [
            ("drivers", "◎", "Learning", "Why is this happening?", "Discover the drivers, relationships and feedbacks shaping the system."),
            ("policy-lab", "◫", "Community", "How can people move forward together?", "Bring together people, organisations and perspectives around a shared challenge."),
            ("future-pathways", "↝", "Empowerment", "What future do we want to create?", "Explore desirable futures and practical pathways towards them."),
        ]
        choice_cols = st.columns(3, gap="medium")
        for col, (module_id, icon, track, question, description) in zip(choice_cols, starting_paths):
            with col:
                with st.container(key=f"catalogue_start_choice_{module_id}"):
                    st.markdown(
                        f"<div class='m-start-choice {track.lower()}'><div class='m-start-icon' aria-hidden='true'>{icon}</div><h4>{escape(question)}</h4><p>{escape(description)}</p></div>",
                        unsafe_allow_html=True,
                    )
                    if module_id == "future-pathways" and _future_scenarios_first_class(MODULES):
                        target_module, target_class = _future_scenarios_first_class(MODULES)
                        st.button("Explore this class →", key="starting-point-future-scenarios", width="stretch",
                                  on_click=navigate, args=("topic", target_module, target_class, None, None),
                                  kwargs={"_rerun": False})
                    else:
                        target_module = _start_module_for_question(MODULES, module_id)
                        if target_module:
                            st.button("Explore this module →", key=f"starting-point-{module_id}", width="stretch",
                                      on_click=navigate, args=("module", target_module, None, None, None),
                                      kwargs={"_rerun": False})
                        else:
                            st.caption("This module is not published yet.")
        recommendation_id = st.session_state.get("catalogue_recommendation")
        if recommendation_id in {"drivers", "policy-lab", "future-pathways"}:
            recommendation_id = _start_module_for_question(MODULES, recommendation_id) or recommendation_id
        if recommendation_id in MODULES:
            recommended = MODULES[recommendation_id]
            st.markdown(
                f"<div class='m-start-recommendation'><div class='m-kicker'>Your suggested starting point</div><h3>{escape(recommended['short_title'])}</h3><p>{escape(recommended['description'])}</p><div class='m-module-meta'><span>{escape(recommended['track'])}</span><span>•</span><span>{recommended['estimated_minutes']} min</span></div></div>",
                unsafe_allow_html=True,
            )
            open_col, reset_col = st.columns([1, 1])
            with open_col:
                st.button("Open module →", key="open-recommended-module", type="primary", width="stretch", on_click=navigate, args=("module", recommendation_id, None, None, None), kwargs={"_rerun": False})
            with reset_col:
                if st.button("Choose a different question", key="reset-recommendation", width="stretch"):
                    st.session_state.pop("catalogue_recommendation", None)
                    st.rerun()


def _class_search_passages(module: dict, lesson: dict) -> list[str]:
    """Visible learner-facing text; no API calls or database search at typing time."""
    passages = [str(module.get("title") or ""), str(lesson.get("title") or ""),
                str(lesson.get("summary") or ""), str(lesson.get("body") or ""),
                str(lesson.get("takeaway") or ""), str(lesson.get("prompt") or ""),
                str(lesson.get("reflection_example") or "")]
    for card in lesson.get("theory_cards") or []:
        passages.extend([str(card.get("title") or ""), str(card.get("body_html") or ""),
                         " ".join(str(x) for x in card.get("bullets") or [])])
    quiz = lesson.get("quiz") or {}
    if isinstance(quiz, dict):
        passages.append(str(quiz.get("question") or ""))
        passages.extend(str(o) for o in quiz.get("options") or [])
    clean = []
    for item in passages:
        # Imported card bodies contain safe HTML; use plain text for searching.
        value = unescape(re.sub(r"<[^>]*>", " ", item))
        value = re.sub(r"\s+", " ", value).strip()
        if value:
            clean.append(value)
    return clean


def render_class_search(*, key: str = "catalogue-class-search") -> None:
    """Find text inside any published class and open that class directly."""
    query = st.text_input("Search all classes", key=key,
                          placeholder="Try biodiversity, scenarios, policy labs, workshops…",
                          help="Searches published class titles, summaries, learning cards, notes, takeaways, quizzes and reflections.").strip()
    if not query:
        return
    words = [word.casefold() for word in re.findall(r"\w+", query) if len(word) > 1]
    if not words:
        st.caption("Enter at least two characters to search.")
        return
    hits = []
    for module_id, module in MODULES.items():
        if module.get("status") != "Available":
            continue
        for lesson in module.get("topics") or []:
            passages = _class_search_passages(module, lesson)
            searchable = " ".join(passages).casefold()
            if not all(word in searchable for word in words):
                continue
            title_match = all(word in str(lesson.get("title", "")).casefold() for word in words)
            summary_match = all(word in str(lesson.get("summary", "")).casefold() for word in words)
            matching_passage = next((text for text in passages[2:] if any(word in text.casefold() for word in words)), "")
            snippet = matching_passage or str(lesson.get("summary") or "")
            if len(snippet) > 185:
                low = snippet.casefold()
                start = next((max(0, low.find(w) - 55) for w in words if w in low), 0)
                snippet = ("…" if start else "") + snippet[start:start + 185].strip() + "…"
            score = (3 if title_match else 0) + (2 if summary_match else 0)
            hits.append((score, module_id, module, lesson, snippet))
    hits.sort(key=lambda row: -row[0])  # Stable sort keeps module/class order.
    st.caption(f"{len(hits)} matching class{'es' if len(hits) != 1 else ''}")
    if not hits:
        st.info("No published classes match these terms. Try a broader search.")
        return
    for _, module_id, module, lesson, snippet in hits[:20]:
        with st.container(border=True, key=f"search_hit_{module_id}_{lesson['id']}"):
            body, action = st.columns([5, 1.2], vertical_alignment="center")
            with body:
                level = "Discover" if lesson.get("level") == "Understand" else ("Communicate" if lesson.get("level") == "Convince" else lesson.get("level", "Class"))
                st.caption(f"{module['short_title']} · {level}")
                st.markdown(f"<div class='m-card-title'>{escape(str(lesson.get('title') or 'Class'))}</div>", unsafe_allow_html=True)
                if snippet:
                    st.write(snippet)
            with action:
                st.button("Open class →", key=f"search_open_{module_id}_{lesson['id']}", width="stretch", on_click=navigate, args=("topic", module_id, lesson["id"], None, None), kwargs={"_rerun": False})
    if len(hits) > 20:
        st.caption("Showing the first 20 results. Refine your search to narrow the list.")


def page_catalogue(user: dict | None):
    environment = _cached_learning_environment()
    st.markdown(
        """
        <div class='m-learning-hub-hero'>
            <div class='m-kicker'>MOSAIC Learn</div>
            <h1>Learning</h1>
            <p>Explore practical learning modules on sustainable land-use management in Europe.
               Find relevant classes, continue where you left off and revisit your saved reflections.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if environment:
        st.markdown(f"### {escape(environment.get('title') or 'Learning environment')}")
        if environment.get('intro'):
            st.write(environment['intro'])
    if user:
        available = [(mid, m) for mid, m in MODULES.items() if m.get("status") == "Available"]
        completed_steps = total_steps = 0
        for module_id, _module in available:
            _ratio, done, total = module_completion(user["user_id"], module_id)
            completed_steps += done
            total_steps += total
        reflection_count = len(_learning_reflection_items(user))
        st.markdown(
            f"<div class='m-learning-summary'><div><strong>{len(MODULES)}</strong><span>modules in the catalogue</span></div><div><strong>{completed_steps}/{total_steps}</strong><span>learning steps completed</span></div><div><strong>{reflection_count}</strong><span>saved reflections</span></div></div>",
            unsafe_allow_html=True,
        )
        options = ["Modules", "My learning", "Reflection notebook", "Results & sharing"]
        if st.session_state.get("learning-hub-section") not in options:
            st.session_state["learning-hub-section"] = "Modules"
        section = st.segmented_control("Learning section", options, key="learning-hub-section", label_visibility="collapsed", width="stretch") or "Modules"
        if section == "My learning":
            render_learning_overview(user)
            return
        if section == "Reflection notebook":
            render_reflection_notebook(user)
            return
        if section == "Results & sharing":
            page_results(user, embedded=True)
            return
    else:
        st.info("You can browse every module without signing in. Sign in when you want to save progress, reflections or results.")

    with st.container(border=True, key="catalogue_class_finder"):
        st.markdown("<div class='m-class-finder-heading'><span class='m-class-finder-icon'>⌕</span><div><h2>Find a class or topic</h2><p>Search directly inside published lessons, activities and quizzes.</p></div></div>", unsafe_allow_html=True)
        render_class_search()
    st.markdown("<div class='m-section-title'><h2>All learning modules</h2><p>Start anywhere. Available modules open directly; modules under construction remain visible so you can see what is coming.</p></div>", unsafe_allow_html=True)
    cols = st.columns(3)
    for idx, (module_id, module) in enumerate(MODULES.items()):
        with cols[idx % 3]:
            st.markdown(module_card_html(module_id, user["user_id"] if user else None), unsafe_allow_html=True)
            if module["status"] == "Available":
                st.button("Open module →", key=f"open-{module_id}", type="primary", width="stretch", on_click=navigate, args=("module", module_id, None, None, None), kwargs={"_rerun": False})
            elif _is_under_construction(module):
                st.link_button(f"{module.get('short_title', 'Module')} · under construction · subscribe →", MOSAIC_NEWSLETTER_URL, type="secondary", width="stretch")
            else:
                st.button(str(module.get("status") or "Coming soon"), key=f"soon-{module_id}", disabled=True, width="stretch")
    _render_starting_point_guide_catalogue()


GLOSSARY_TERMS = [
    (
        "Systems Thinking",
        "An approach that considers the complexity and interdependencies of policy challenges by examining relationships, feedback loops and the wider system rather than isolated components.",
    ),
    (
        "Design Thinking",
        "A human-centered, creative problem-solving method that emphasizes empathy, ideation, prototyping and testing.",
    ),
    (
        "Policy Innovation",
        "The development and application of novel policy tools, processes or ideas to address emerging or persistent societal challenges.",
    ),
    (
        "Policy Evaluation",
        "A structured assessment of a policy's design, implementation and impact to determine its effectiveness, efficiency, relevance and sustainability.",
    ),
    (
        "Evidence-Informed Policy",
        "Policymaking guided by systematically collected and analyzed research evidence, together with professional expertise, stakeholder knowledge and contextual understanding.",
    ),
    (
        "Policy Experimentation",
        "The testing of new or alternative policy approaches in controlled or pilot settings to assess their feasibility, effects and potential for wider use.",
    ),
    (
        "Policy Lab",
        "A collaborative space where researchers, policymakers and stakeholders co-create, test and refine solutions to complex policy challenges.",
    ),
    (
        "Knowledge Broker",
        "A member of the Policy Lab team who facilitates connections among research stakeholders at the science-policy interface and supports the exchange and use of knowledge.",
    ),
    (
        "Policy Lead",
        "A Policy Lab representative responsible for linking the lab to current and emerging policy processes, priorities and decision-making opportunities.",
    ),
    (
        "Living Lab",
        "An open innovation environment where stakeholders, including users and citizens, co-create and test solutions in real-life contexts.",
    ),
    (
        "Knowledge Exchange",
        "The mutual sharing of ideas, expertise and information between researchers, policymakers and other stakeholders.",
    ),
    (
        "Co-creation",
        "A collaborative process in which researchers, policymakers and other stakeholders jointly develop knowledge, policies or solutions.",
    ),
    (
        "Stakeholder Engagement",
        "The active involvement of relevant actors throughout the policy process to incorporate different knowledge, interests and perspectives.",
    ),
    (
        "Knowledge Translation",
        "The synthesis and adaptation of research findings into accessible formats and language to support understanding and decision-making.",
    ),
    (
        "Iterative Design",
        "A cyclical process of developing, testing and refining policy interventions through continuous learning and feedback.",
    ),
    (
        "Action Research",
        "A participatory research method in which researchers engage directly in the policy process to generate knowledge while supporting practical change.",
    ),
]


def page_glossary():
    st.markdown("<div class='m-kicker'>Reference</div>", unsafe_allow_html=True)
    st.title("Glossary")
    st.markdown(
        """
        <p class="m-reference-intro">This glossary provides a foundational understanding of key concepts relevant to the setup and operation of Policy Labs within the MOSAIC research project. A shared understanding supports interregional, interdisciplinary and transdisciplinary learning.</p>
        """,
        unsafe_allow_html=True,
    )
    query = st.text_input(
        "Search the glossary",
        placeholder="Search for systems thinking, co-creation, Policy Lab...",
    ).strip().lower()
    filtered = [
        (term, definition)
        for term, definition in GLOSSARY_TERMS
        if not query or query in term.lower() or query in definition.lower()
    ]
    st.caption(f"{len(filtered)} of {len(GLOSSARY_TERMS)} concepts shown")
    if not filtered:
        st.info("No concepts match that search. Try a broader word or clear the search field.")
        return
    cols = st.columns(3)
    for index, (term, definition) in enumerate(filtered):
        with cols[index % 3]:
            st.markdown(
                f"""
                <article class="m-glossary-card">
                    <div class="label">Definition</div>
                    <h3>{escape(term)}</h3>
                    <p>{escape(definition)}</p>
                </article>
                """,
                unsafe_allow_html=True,
            )


def page_contact():
    st.markdown("<div class='m-kicker'>About MOSAIC Learn</div>", unsafe_allow_html=True)
    st.title("Contact details")
    st.markdown(
        "<p class='m-reference-intro'>MOSAIC Learn brings together coordination by VITO Nexus and contributions from the MOSAIC work package leaders who developed the module content.</p>",
        unsafe_allow_html=True,
    )
    nexus_col, contributors_col = st.columns(2)
    with nexus_col:
        st.markdown(
            """
            <section class="m-contact-card">
                <h2>VITO Nexus</h2>
                <p>VITO Nexus coordinates the MOSAIC program. Within VITO, Nexus offers an open think and do space in which anything is possible, as long as it contributes to deep sustainability and leads to actionable knowledge.</p>
                <div class="m-contact-group">
                    <h3>Collaborated on this platform</h3>
                    <div class="m-contact-person"><strong>Dieter Cuypers</strong><a href="mailto:dieter.cuypers@vito.be">dieter.cuypers@vito.be</a></div>
                    <div class="m-contact-person"><strong>Lise Vermeersch</strong><a href="mailto:lise.vermeersch@vito.be">lise.vermeersch@vito.be</a></div>
                    <div class="m-contact-person"><strong>Maria Caballero Pons</strong></div>
                </div>
            </section>
            """,
            unsafe_allow_html=True,
        )
    with contributors_col:
        st.markdown(
            """
            <section class="m-contact-card">
                <h2>MOSAIC work package leaders</h2>
                <p>The work package leaders of the MOSAIC project provided the content of the modules on this website.</p>
                <div class="m-contact-group">
                    <h3>Drivers of Change</h3>
                    <div class="m-contact-person"><strong>Inge Liekens</strong><a href="mailto:inge.liekens@vito.be">inge.liekens@vito.be</a></div>
                </div>
                <div class="m-contact-group">
                    <h3>Policy Labs</h3>
                    <div class="m-contact-person"><strong>Boldizsar Megyesi, Hanna Acsady and Katalin Varsanyi</strong><a href="mailto:megyesi.boldizsar@essrg.hu">megyesi.boldizsar@essrg.hu</a></div>
                </div>
                <div class="m-contact-group">
                    <h3>Future Pathways</h3>
                    <div class="m-contact-person"><strong>Thomas Schmitt and Max Tscholl</strong><a href="mailto:thomas.schmitt@kit.edu">thomas.schmitt@kit.edu</a></div>
                </div>
            </section>
            """,
            unsafe_allow_html=True,
        )

    st.markdown(
        """
        <section class="m-credits">
            <h2>Acknowledgements</h2>
            <p>Developed within the MOSAIC project (Horizon Europe, Grant Agreement 101081238).</p>
            <p>We thank Policy Lab coordinators and local stakeholders for their time and expertise.</p>
            <h3>References</h3>
            <p>Full references are available on the <a href="https://mosaic-europe.eu/mosaic/mosaic-resources" target="_blank" rel="noopener noreferrer">MOSAIC website</a>.</p>
            <h3>Disclaimer</h3>
            <p>This page reflects the views of the MOSAIC contributors. The European Commission is not responsible for any use of the information provided.</p>
            <p>Content is under development - share feedback via <a href="mailto:dieter.cuypers@vito.be">dieter.cuypers@vito.be</a>.</p>
            <p>Unless stated otherwise, materials are shared under CC BY-NC-ND 4.0: credit required, non-commercial and no derivatives.</p>
        </section>
        """,
        unsafe_allow_html=True,
    )


TOOL_FILE_TYPES = {
    ".docx": (
        "Word",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ),
    ".pdf": ("PDF", "application/pdf"),
}

RESOURCE_UPLOAD_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".csv": "text/csv",
    ".txt": "text/plain",
    ".zip": "application/zip",
}
IMAGE_UPLOAD_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}
MAX_CMS_RESOURCE_BYTES = 25 * 1024 * 1024
MAX_CMS_IMAGE_BYTES = 8 * 1024 * 1024


def configured_tool_file(file_name: str):
    """Resolve one filename from content.py without allowing paths outside assets/tools."""
    if not file_name or Path(file_name).name != file_name:
        return None, None, "Use a filename only, without folders."
    file_type = TOOL_FILE_TYPES.get(Path(file_name).suffix.lower())
    if not file_type:
        return None, None, "Only .docx and .pdf templates are supported."
    file_path = TOOL_FILES_DIR / file_name
    if not file_path.is_file():
        return None, file_type, f"File not found in assets/tools: {file_name}"
    return file_path, file_type, None


def tool_template_markdown(tool_id: str, tool: dict) -> str:
    """Build a simple dependency-free note for workshop tools when explicitly needed."""
    module = MODULES.get(tool.get("module_id")) or {"title": "MOSAIC Learn"}
    lines = [
        f"# {tool['title']}",
        "",
        f"**MOSAIC Learn module:** {module['title']}",
        f"**Format:** {tool.get('format') or 'Workshop'}",
    ]
    if tool.get("duration"):
        lines.extend([f"**Suggested time:** {tool['duration']}", ""])
    if tool.get("description"):
        lines.extend(["## Description", "", tool["description"], ""])
    if tool.get("steps"):
        lines.extend(["## How to use it", ""])
        lines.extend(f"{idx}. {step}" for idx, step in enumerate(tool.get("steps") or [], start=1))

    if tool.get("kind") == "cld":
        lines.extend(
            [
                "",
                "## 1. Frame the system",
                "",
                "**Land-use decision or outcome:**  ",
                "",
                "**Actor(s):**  ",
                "",
                "**Place and system boundary:**  ",
                "",
                "**Time horizon:**  ",
                "",
                "## 2. List variables",
                "",
                "Use variable names that can increase or decrease (for example, `trust in the programme`, not `trust`).",
                "",
                "| Variable | Why it matters | Evidence or assumption |",
                "| --- | --- | --- |",
            ]
        )
        lines.extend("|  |  |  |" for _ in range(8))
        lines.extend(
            [
                "",
                "## 3. Connect variables",
                "",
                "`+` means the effect moves in the same direction as the cause. `-` means it moves in the opposite direction. Add a delay where an effect is not immediate.",
                "",
                "| Cause | Effect | Polarity (+/-) | Delay? | Explanation |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        lines.extend("|  |  |  |  |  |" for _ in range(10))
        lines.extend(
            [
                "",
                "## 4. Read the loops",
                "",
                "**Reinforcing loop(s):**  ",
                "",
                "**Balancing loop(s):**  ",
                "",
                "**Important delays or uncertainties:**  ",
                "",
                "## 5. Identify leverage",
                "",
                "**Where could policy, research, or field action interrupt an unwanted loop or strengthen a helpful one?**  ",
                "",
                "**What should be tested with the actors represented in the diagram?**  ",
            ]
        )
    else:
        lines.extend(["", "## Worksheet", ""])
        for title, prompt in tool.get("prompts", []):
            lines.extend([f"### {title}", "", prompt, "", "_Your notes:_", "", "", ""])
        lines.extend(
            [
                "## Next actions",
                "",
                "| Action | Owner | By when |",
                "| --- | --- | --- |",
                "|  |  |  |",
                "|  |  |  |",
                "|  |  |  |",
            ]
        )

    lines.extend(
        [
            "",
            "---",
            "Developed within the MOSAIC project (Horizon Europe, Grant Agreement 101081238).",
        ]
    )
    return "\n".join(lines) + "\n"


def _safe_resource_filename(file_name: str) -> str:
    name = Path(str(file_name or "")).name.strip()
    return name or "mosaic-resource.bin"


def _render_resource_download(meta: dict, *, key: str, button_type: str = "secondary", label: str | None = None) -> bool:
    record = _cached_resource_file(str(meta.get("resource_id") or ""))
    if not record or record.get("archived") or not record.get("file_data"):
        st.caption("This file is currently unavailable.")
        return False
    file_name = _safe_resource_filename(record.get("file_name"))
    st.download_button(
        label or f"Download {file_name} ↓",
        data=record["file_data"],
        file_name=file_name,
        mime=str(record.get("mime_type") or "application/octet-stream"),
        key=key,
        type=button_type,
        width="stretch",
    )
    return True


@st.cache_data(ttl=120, show_spinner=False)
def _all_tools_zip_cached() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for tool_id, tool in TOOL_DEFINITIONS.items():
            if _is_under_construction(tool):
                continue
            added_file = False
            for meta in _resource_files_for("tool", tool_id):
                record = _cached_resource_file(meta["resource_id"])
                if not record or record.get("archived") or not record.get("file_data"):
                    continue
                archive.writestr(
                    f"{tool_id}/{_safe_resource_filename(record.get('file_name'))}",
                    record["file_data"],
                )
                added_file = True
            for file_name in TOOL_DOWNLOAD_FILES.get(tool_id, []):
                file_path, _, error = configured_tool_file(file_name)
                if file_path and not error:
                    archive.write(file_path, arcname=f"{tool_id}/{file_name}")
                    added_file = True
            # Resources are optional; tools without files add nothing to the archive.
    return buffer.getvalue()


def all_tools_zip() -> bytes:
    return _all_tools_zip_cached()


def _render_mosaic_learn_agent_placeholder() -> None:
    """Visual placeholder for the future project-aware MOSAIC Learn Agent."""
    st.markdown(
        """
        <section class="m-agent-shell" aria-label="MOSAIC Learn Agent preview">
            <div class="m-agent-head">
                <div class="m-agent-identity">
                    <div class="m-agent-avatar" aria-hidden="true">M</div>
                    <div class="m-agent-title"><strong>MOSAIC Learn Agent</strong><span>Project-aware guidance across MOSAIC methods, tools and evidence</span></div>
                </div>
                <span class="m-agent-soon">Coming soon</span>
            </div>
            <div class="m-agent-message">Hi — I will soon help you connect questions from your own project to relevant MOSAIC learning modules, tools and evidence.</div>
            <div class="m-agent-compose" aria-disabled="true">
                <div class="m-agent-placeholder">Ask a question about your project…</div>
                <div class="m-agent-send" aria-hidden="true">→</div>
            </div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def _navigate_resource_detail(resource_id: str, *, _rerun: bool = True) -> None:
    """Open a resource through the existing query-backed router.

    A raw relative HTML anchor can append the query to the current lesson
    pathname (especially on Streamlit Community Cloud / custom page paths).
    """
    _replace_query_params({"page": "resources", "resource": str(resource_id)})
    st.session_state["route"] = "resources"
    if _rerun:
        st.rerun()


def _record_field_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(key or "").casefold()).strip()


def _record_value(columns: dict, *names: str) -> str:
    normalised = {_record_field_key(k): str(v).strip() for k, v in columns.items()}
    return next((normalised[_record_field_key(name)] for name in names
                 if normalised.get(_record_field_key(name))), "")


def _record_field(label: str, value: str, *, list_style: bool = False) -> None:
    """Display an imported Coda cell without printing Python-list representations.

    Streamlit's Markdown renderer safely handles line breaks, bold text and
    embedded links while HTML execution is disabled.
    """
    raw = str(value or "").strip()
    if not raw:
        return
    st.markdown(f"**{label}**")
    if _valid_external_url(raw):
        st.link_button("Open link ↗", raw, width="content")
        return
    lines = [x.strip() for x in re.split(r"[\r\n]+", raw) if x.strip()]
    if list_style and len(lines) == 1 and ";" in raw:
        lines = [x.strip() for x in raw.split(";") if x.strip()]
    if list_style and len(lines) > 1:
        for line in lines:
            clean = re.sub(r"^[-*•·]\s*", "", line)
            st.markdown(f"- {clean}")
    else:
        # Preserve author paragraphs and markdown lists from Superhuman Docs.
        st.markdown(raw)


def _render_source_record(columns: dict, *, kind: str) -> None:
    """Use the complete stored table record, grouped by meaning.

    Editorial changes in Coda are reflected by manual republish. Unknown
    columns remain accessible under More details, not silently discarded.
    """
    if not isinstance(columns, dict) or not columns:
        return
    is_tool = kind == "tool"
    st.markdown("### Full tool record" if is_tool else "### Full resource record")
    if is_tool:
        groups = (
            ("Purpose and application", (("Useful for", ("Purpose / useful for", "Purpose", "Useful for"), False),
                                          ("Target users", ("Target users", "Target audience"), True),
                                          ("Expected outputs", ("Expected outputs",), False),
                                          ("Policy relevance", ("Policy relevance",), False))),
            ("Practical requirements", (("Required inputs", ("Required inputs",), True),
                                         ("Technical requirements", ("Technical requirements",), True),
                                         ("Time required", ("Time required",), False),
                                         ("Access conditions", ("Access conditions",), False))),
            ("About this tool", (("Developer / owner", ("Developer / owner",), False),
                                 ("Version / update date", ("Version / update date",), False),
                                 ("Licence", ("License", "Licence"), False))),
        )
        excluded = {"title", "tool name", "name", "short description", "description", "how to use", "steps",
                    "tool type", "type", "format", "access link", "main url", "url", "supporting materials",
                    "download url", "pdf", "file", "files", "attachments", "keywords", "related module s", "related resource s"}
        urls = (("Open tool", ("Access link", "Main URL")), ("Supporting materials", ("Supporting materials", "Download URL")))
    else:
        groups = (
            ("About this resource", (("Detailed description", ("Detailed description",), False),
                                     ("Useful for", ("Useful for",), False),
                                     ("Target audience", ("Target audience",), True))),
            ("Publication details", (("Publisher / venue", ("Publisher / venue", "Publisher", "Venue"), False),
                                     ("Publication year", ("Publication year", "Year"), False),
                                     ("Language", ("Language",), False),
                                     ("Licence", ("License", "Licence"), False))),
        )
        excluded = {"title", "resource name", "name", "short description", "description", "authors creators", "authors",
                    "author", "creator", "keywords", "tags", "resource type", "type", "related module s"}
        urls = (("Open publication / DOI", ("DOI / Zenodo link", "DOI", "Zenodo link")),
                ("Open original resource", ("Main URL", "Main link")),
                ("Open download", ("Download URL",)))
    handled = set(excluded)
    for heading, fields in groups:
        present = [(label, _record_value(columns, *aliases), use_list)
                   for label, aliases, use_list in fields]
        if any(value for _, value, _ in present):
            st.markdown(f"#### {heading}")
            for label, value, use_list in present:
                _record_field(label, value, list_style=use_list)
        for _, aliases, _ in fields:
            handled.update(_record_field_key(alias) for alias in aliases)
    access = []
    for label, aliases in urls:
        handled.update(_record_field_key(alias) for alias in aliases)
        link = _record_value(columns, *aliases)
        if _valid_external_url(link):
            access.append((label, link))
    if access:
        st.markdown("#### Access and links")
        for label, link in access:
            st.link_button(f"{label} ↗", link, width="content")
    more = [(str(name), str(value)) for name, value in columns.items()
            if _record_field_key(name) not in handled and str(value).strip()]
    if more:
        st.markdown("#### Additional details")
        for name, value in more:
            _record_field(name, value, list_style=("keyword" in name.casefold() or "materials" in name.casefold()))


def _render_resource_detail(resource_id: str, item: dict) -> None:
    st.button("← All resources", key=f"resource-detail-back-{resource_id}", on_click=navigate, args=("resources", None, None, None, None), kwargs={"_rerun": False})

    origin_class = "mosaic" if item.get("origin") == "MOSAIC content" else "external"
    meta = [str(item.get("resource_type") or "Resource")]
    if item.get("year"):
        meta.append(str(item["year"]))
    if item.get("publication_date") and item.get("publication_date") != item.get("year"):
        meta.append(str(item["publication_date"]))
    meta_html = "".join(f"<span>{escape(value)}</span>" for value in meta if value)
    st.markdown(
        f"""
        <section class="m-resource-detail">
            <div class="m-resource-badges"><span class="m-resource-badge {origin_class}">{escape(item.get('origin') or '')}</span></div>
            <h1>{escape(item.get('title') or resource_id)}</h1>
            {f"<p>{escape(item.get('description') or '')}</p>" if item.get('description') else ""}
            <div class="m-resource-detail-meta">{meta_html}</div>
        </section>
        """,
        unsafe_allow_html=True,
    )

    detail_left, detail_right = st.columns([1.35, 1], gap="large")
    with detail_left:
        if item.get("authors"):
            st.markdown("### Author / organisation")
            st.write(item["authors"])
        module_names = [MODULES[mid]["short_title"] for mid in item.get("related_modules") or [] if mid in MODULES]
        if module_names:
            st.markdown("### Used in MOSAIC Learn")
            st.write(" · ".join(module_names))
        tags = item.get("tags") or []
        if tags:
            st.markdown("### Keywords")
            st.markdown(" ".join(f"`{tag}`" for tag in tags))
    with detail_right:
        publication_url = str(item.get("publication_url") or item.get("source_url") or "").strip()
        if _valid_external_url(publication_url):
            st.link_button("Open publication / external source ↗", publication_url, width="stretch")

    if item.get("source_system") == "superhuman_docs" and item.get("source_columns"):
        _render_source_record(item["source_columns"], kind="resource")
    # External attachments remain accessible even if not stored in the DB.
    for index, attachment in enumerate(item.get("attachment_links") or []):
        if isinstance(attachment, dict) and _valid_external_url(str(attachment.get("url") or "")):
            st.link_button(f"Open file: {attachment.get('title') or 'Download'} ↗",
                           attachment["url"], width="content")
    files = [meta for meta in _resource_files_for("library", resource_id) if not meta.get("archived")]
    if files:
        st.markdown(
            "<div class='m-resource-download-shell'><h2>Download resources</h2><p>Download the files stored with this resource.</p></div>",
            unsafe_allow_html=True,
        )
        download_cols = st.columns(min(2, len(files)), gap="medium")
        for idx, meta in enumerate(files):
            with download_cols[idx % len(download_cols)]:
                _render_resource_download(
                    meta,
                    key=f"resource-detail-download-{resource_id}-{idx}",
                    button_type="primary" if idx == 0 else "secondary",
                    label=f"Download {meta.get('title') or meta.get('file_name')} ↓",
                )
    else:
        download_url = _record_value(item.get("source_columns") or {}, "Download URL")
        if not _valid_external_url(download_url):
            st.caption("No downloadable file is stored with this resource.")
        if _valid_external_url(str(item.get("source_page_url") or "")):
            st.link_button("Open repository record ↗", item["source_page_url"], width="content")


def page_resources(user: dict | None):
    resources = _published_library_resources()
    st.markdown(
        """
        <div class='m-library-hero'>
            <div class='m-kicker'>Evidence & further reading</div>
            <h1>Resources</h1>
            <p>Search the reports, papers, PDFs and external sources used across MOSAIC Learn. Every item is clearly marked as MOSAIC content or external content.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    selected_id = _query_param_text("resource")
    if selected_id in resources:
        _render_resource_detail(selected_id, resources[selected_id])
        return

    with st.container(border=True, key="resources_class_finder"):
        st.markdown("<div class='m-class-finder-heading'><span class='m-class-finder-icon'>⌕</span><div><h2>Find a class or topic</h2><p>Looking for something specific? Search the learning modules first.</p></div></div>", unsafe_allow_html=True)
        render_class_search(key="resources-class-search")
    _render_mosaic_learn_agent_placeholder()

    if not resources:
        st.info("No resources have been published in the library yet. Administrators can add PDFs and source links from the Content Studio.")
        st.markdown("Browse the wider [MOSAIC Knowledge Repository](https://mosaic-europe.eu/mosaic/mosaic-knowledge-repository) while this library is being populated.")
        return

    search_col, origin_col, type_col, module_col = st.columns([2.2, 1, 1, 1.2])
    with search_col:
        query = st.text_input("Search resources", placeholder="Search title, author, keyword or description…", key="resource-library-search").strip()
    origins = ["All origins"] + sorted({item.get("origin", "MOSAIC content") for item in resources.values()})
    with origin_col:
        origin_filter = st.selectbox("Origin", origins, key="resource-library-origin")
    types = ["All types"] + sorted({item.get("resource_type", "Resource") for item in resources.values()})
    with type_col:
        type_filter = st.selectbox("Type", types, key="resource-library-type")
    module_options = ["All modules"] + [module["short_title"] for module in MODULES.values()]
    with module_col:
        module_filter = st.selectbox("Used in", module_options, key="resource-library-module")

    module_label_to_id = {module["short_title"]: module_id for module_id, module in MODULES.items()}
    needle = query.casefold()
    shown: list[tuple[str, dict]] = []
    for resource_id, item in resources.items():
        searchable = " ".join([
            item.get("title", ""), item.get("description", ""), item.get("authors", ""), item.get("year", ""),
            item.get("resource_type", ""), item.get("origin", ""), " ".join(item.get("tags") or []),
        ]).casefold()
        if needle and needle not in searchable:
            continue
        if origin_filter != "All origins" and item.get("origin") != origin_filter:
            continue
        if type_filter != "All types" and item.get("resource_type") != type_filter:
            continue
        if module_filter != "All modules" and module_label_to_id.get(module_filter) not in (item.get("related_modules") or []):
            continue
        shown.append((resource_id, item))
    shown.sort(key=lambda pair: (int(pair[1].get("_sort_order") or 0), pair[1].get("title", "").casefold()))

    st.caption(f"{len(shown)} of {len(resources)} resources")
    if not shown:
        st.info("No resources match these filters.")
        return

    cols = st.columns(2, gap="large")
    for idx, (resource_id, item) in enumerate(shown):
        with cols[idx % 2]:
            origin_class = "mosaic" if item.get("origin") == "MOSAIC content" else "external"
            module_names = [MODULES[mid]["short_title"] for mid in item.get("related_modules") or [] if mid in MODULES]
            tags = item.get("tags") or []
            meta_bits = [item.get("resource_type", "Resource")]
            if item.get("year"):
                meta_bits.append(item["year"])
            tag_html = "".join(f"<span class='m-tool-filter-tag'>{escape(tag)}</span>" for tag in tags[:4])
            module_html = "".join(f"<span class='m-tool-filter-tag'>{escape(name)}</span>" for name in module_names[:2])
            author_html = f"<div class='m-resource-card-author'>{escape(item.get('authors') or '')}</div>" if item.get("authors") else ""
            st.markdown(
                f"""
                <div class='m-resource-library-card'>
                    <div class='m-resource-badges'><span class='m-resource-badge {origin_class}'>{escape(item.get('origin') or '')}</span><span class='m-resource-badge'>{escape(' · '.join(meta_bits))}</span></div>
                    <h3>{escape(item['title'])}</h3>
                    {author_html}
                    <p>{escape(item.get('description') or '')}</p>
                    <div class='m-tool-filter-tags'>{module_html}{tag_html}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.button("Read more →", key=f"resource-open-{resource_id}", width="stretch",
                      on_click=_navigate_resource_detail, args=(resource_id,),
                      kwargs={"_rerun": False})

def _tool_mosaic_membership(tool: dict) -> bool | None:
    """Exact Coda 'Part of Mosaic' field; blank/legacy records are unknown."""
    value = tool.get("part_of_mosaic")
    if value is None or str(value).strip() == "":
        value = _record_value(tool.get("source_columns") or {}, "Part of Mosaic", "Part of MOSAIC")
    if isinstance(value, bool):
        return value
    normalised = str(value or "").strip().casefold()
    if normalised in {"yes", "true", "1", "y"}:
        return True
    if normalised in {"no", "false", "0", "n"}:
        return False
    return None


def _tool_matches_filters(tool: dict, *, query: str, module_filter: str, format_filter: str,
                          keyword_filter: str, mosaic_filter: str = "All") -> bool:
    links = _tool_lesson_links(tool)
    searchable = " ".join([
        str(tool.get("title") or ""), str(tool.get("description") or ""),
        str(tool.get("format") or ""), str(tool.get("duration") or ""), str(tool.get("website_url") or ""),
        " ".join(tool.get("keywords") or []), _tool_module_label(tool),
        " ".join(f"{mid} {tid}" for mid, tid in links),
    ]).casefold()
    if query and query.casefold() not in searchable:
        return False
    if module_filter != "All modules":
        module_id = next((mid for mid, module in MODULES.items() if module["short_title"] == module_filter), "")
        if module_id and module_id not in {mid for mid, _tid in links} and str(tool.get("module_id") or "") != module_id:
            return False
    if format_filter != "All formats" and str(tool.get("format") or "") != format_filter:
        return False
    if keyword_filter != "All keywords" and keyword_filter not in (tool.get("keywords") or []):
        return False
    if mosaic_filter in {"Yes", "No"}:
        membership = _tool_mosaic_membership(tool)
        if membership is None or membership != (mosaic_filter == "Yes"):
            return False
    return True



def _tool_format_class(format_label: str | None) -> str:
    return {
        "Workshop": "workshop",
        "Website": "website",
        "Model": "model",
        "Digital tool": "digital-tool",
    }.get(str(format_label or "Workshop"), "workshop")


def _safe_embed_url(value: str | None) -> str:
    url = str(value or "").strip()
    if not url:
        return ""
    try:
        parsed = urlparse(url)
    except ValueError:
        return ""
    return url if parsed.scheme in {"http", "https"} and parsed.netloc else ""


def _tool_image_id(tool_id: str, tool: dict) -> str:
    """Prefer an imported Image-column photo, then a manually uploaded one."""
    imported_id = str(tool.get("image_resource_id") or "")
    if imported_id:
        record = _cached_resource_file(imported_id)
        if (record and not record.get("archived") and record.get("file_data")
                and str(record.get("mime_type") or "").startswith("image/")):
            return imported_id
    rows = _resource_files_for("tool_image", tool_id)
    return str(rows[0].get("resource_id") or "") if rows else ""


def _tool_card_media_html(tool_id: str, tool: dict) -> str:
    image_id = _tool_image_id(tool_id, tool)
    if image_id:
        uri = _resource_image_data_uri(image_id)
        if uri:
            alt = escape(str(tool.get("image_name") or tool.get("title") or "Tool image"))
            return f"<div class='m-tool-card-media'><img src='{uri}' alt='{alt}'></div>"
    format_label = str(tool.get("format") or "Workshop")
    icon = TOOL_FORMAT_ICONS.get(format_label, "◫")
    return f"<div class='m-tool-card-media m-tool-card-placeholder'><span aria-hidden='true'>{escape(icon)}</span></div>"


def _render_tool_gallery(tool_id: str) -> None:
    rows = [row for row in _resource_files_for("tool_gallery", tool_id) if not row.get("archived")]
    slides = []
    for row in rows:
        uri = _resource_image_data_uri(row.get("resource_id"))
        if uri:
            slides.append({
                "src": uri,
                "caption": str(row.get("description") or row.get("title") or ""),
            })
    if not slides:
        return
    slides_json = json.dumps(slides).replace("</", "<\\/")
    component = f"""
    <div id="mosaic-slider" class="slider-shell">
      <div class="slider-stage"><img id="slider-img" alt="Tool example preview"><div id="slider-caption" class="slider-caption"></div></div>
      <button class="slider-btn prev" type="button" aria-label="Previous image">&#8592;</button>
      <button class="slider-btn next" type="button" aria-label="Next image">&#8594;</button>
      <div id="slider-count" class="slider-count"></div>
    </div>
    <style>
      *{{box-sizing:border-box}} body{{margin:0;font-family:Poppins,'Segoe UI',Arial,sans-serif;background:transparent;color:#3c3c3b}}
      .slider-shell{{position:relative;border:1px solid #deded9;border-radius:18px;overflow:hidden;background:#f6f6f4}}
      .slider-stage{{height:470px;display:flex;align-items:center;justify-content:center;position:relative;background:#f6f6f4}}
      .slider-stage img{{width:100%;height:100%;object-fit:contain;display:block}}
      .slider-caption{{position:absolute;left:16px;right:16px;bottom:14px;padding:9px 12px;border-radius:11px;background:rgba(255,255,255,.92);font-size:13px;line-height:1.4;box-shadow:0 3px 14px rgba(0,0,0,.08)}}
      .slider-caption:empty{{display:none}}
      .slider-btn{{position:absolute;top:50%;transform:translateY(-50%);width:42px;height:42px;border-radius:999px;border:1px solid #deded9;background:rgba(255,255,255,.95);color:#9c2438;font-size:20px;cursor:pointer}}
      .slider-btn:hover{{background:#f8eef0}} .prev{{left:12px}} .next{{right:12px}}
      .slider-count{{position:absolute;right:14px;top:14px;padding:5px 9px;border-radius:999px;background:rgba(255,255,255,.92);font-size:12px;font-weight:600}}
    </style>
    <script>
      const slides={slides_json}; let i=0;
      const img=document.getElementById('slider-img'), cap=document.getElementById('slider-caption'), count=document.getElementById('slider-count');
      function show(){{ const s=slides[i]; img.src=s.src; cap.textContent=s.caption||''; count.textContent=(i+1)+' / '+slides.length; }}
      document.querySelector('.prev').onclick=()=>{{i=(i-1+slides.length)%slides.length;show();}};
      document.querySelector('.next').onclick=()=>{{i=(i+1)%slides.length;show();}};
      show();
    </script>
    """
    components.html(component, height=500, scrolling=False)


def _render_tool_preview(tool_id: str, tool: dict) -> None:
    preview_url = _safe_embed_url(tool.get("preview_url"))
    gallery_rows = [row for row in _resource_files_for("tool_gallery", tool_id) if not row.get("archived")]
    if not preview_url and not gallery_rows:
        return
    st.markdown("<div class='m-section-title'><h2>Preview</h2><p>Explore the tool, model output or example screens before opening the external site or downloading resources.</p></div>", unsafe_allow_html=True)
    if preview_url:
        src = escape(preview_url, quote=True)
        components.html(
            f"""<style>body{{margin:0;background:#fff}}iframe{{width:100%;height:540px;border:1px solid #deded9;border-radius:18px;background:#fff}}</style><iframe src=\"{src}\" loading=\"lazy\" sandbox=\"allow-scripts allow-same-origin allow-forms allow-popups allow-downloads\" referrerpolicy=\"no-referrer-when-downgrade\"></iframe>""",
            height=555,
            scrolling=False,
        )
        st.caption("If the embedded preview is blocked by the source website, use the external website link instead.")
    if gallery_rows:
        _render_tool_gallery(tool_id)

def _tool_rich_markdown(value: str | None) -> str:
    """Markdown from the rich Coda API is rendered by Streamlit safely.

    Do not use unsafe_allow_html: rich text is author-authored, not trusted HTML.
    """
    raw = str(value or "").strip()
    if raw.startswith("```") and raw.endswith("```") and raw.count("```") == 2:
        raw = raw[3:-3].strip("\n")
    return raw


def _render_tool_detail(tool_id: str, tool: dict) -> None:
    """Two-column editorial tool page; only reveal metadata after main guidance."""
    source_module_id = str(st.session_state.get("module_id") or "")
    source_topic_id = str(st.session_state.get("topic_id") or "")
    came_from_lesson = bool(source_module_id in MODULES and source_topic_id and topic_by_id(source_module_id, source_topic_id))
    st.button("← All tools", key=f"tool-detail-back-{tool_id}", on_click=navigate,
              args=("tools", "", "", "", None), kwargs={"_rerun": False})

    format_label = str(tool.get("format") or "Workshop")
    format_class = _tool_format_class(format_label)
    format_icon = TOOL_FORMAT_ICONS.get(format_label, "◫")
    hero_left, hero_right = st.columns([1.45, 1], gap="large", vertical_alignment="center")
    with hero_left:
        st.markdown(
            f"""
            <div class='m-tool-detail {format_class}'>
                <div class='m-tool-format-line'><span class='m-tool-format-icon' aria-hidden='true'>{escape(format_icon)}</span><span>{escape(format_label)}</span></div>
                <div class='m-kicker'>{escape(_tool_module_label(tool))}</div>
                <h1>{escape(tool.get('title') or tool_id)}</h1>
                <div class='m-tool-detail-meta'>{f"<span>{escape(tool.get('duration'))}</span>" if tool.get('duration') else ""}{"<span>Under construction</span>" if _is_under_construction(tool) else ""}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with hero_right:
        image_id = _tool_image_id(tool_id, tool)
        image = _cached_resource_file(image_id) if image_id else None
        if image and image.get("file_data") and not image.get("archived"):
            st.image(image["file_data"], width="stretch")
        else:
            st.markdown(f"<div class='m-tool-detail-placeholder {format_class}'><span>{escape(format_icon)}</span><strong>{escape(format_label)}</strong></div>", unsafe_allow_html=True)

    if _is_under_construction(tool):
        st.warning("This tool is under construction and is not yet available.")
        st.link_button("Subscribe to the MOSAIC newsletter for updates →", MOSAIC_NEWSLETTER_URL, type="primary")
        return
    if came_from_lesson:
        source_module = MODULES[source_module_id]
        st.info(f"You opened this tool from **{source_module['short_title']}**.")
        st.button("← Return to the learning step", key=f"tool-detail-return-{tool_id}",
                  on_click=navigate, args=("topic", source_module_id, source_topic_id, None, None),
                  kwargs={"_rerun": False})

    # Primary content: always two columns. Rich Coda Markdown preserves
    # links, bold text, subheadings, numbered steps, lists and paragraphs.
    description = _tool_rich_markdown(tool.get("description_rich") or tool.get("description"))
    instructions = _tool_rich_markdown(tool.get("steps_rich") or tool.get("steps_text"))
    howto_col, description_col = st.columns([1.25, 1], gap="large")
    with howto_col:
        st.markdown("### How to use it")
        if instructions:
            st.markdown(instructions)
        elif tool.get("steps"):
            for idx, step in enumerate(tool.get("steps") or [], start=1):
                st.markdown(f"**{idx}.** {escape(str(step))}")
        else:
            st.caption("Instructions to be added.")
    with description_col:
        st.markdown("### Description")
        if description:
            st.markdown(description)
        else:
            st.caption("Description to be added.")

    # Access links and files immediately follow the core guidance, not buried
    # below a duplicate imported raw-record section.
    managed_files = [meta for meta in _resource_files_for("tool", tool_id) if not meta.get("archived")]
    shipped_files = []
    for file_name in TOOL_DOWNLOAD_FILES.get(tool_id, []):
        file_path, file_type, error = configured_tool_file(file_name)
        if file_path and not error:
            shipped_files.append((file_name, file_path, file_type))
    attachment_links = [item for item in tool.get("attachment_links") or []
                        if isinstance(item, dict) and _valid_external_url(str(item.get("url") or ""))]
    website = str(tool.get("website_url") or "")
    has_website = _valid_external_url(website)
    if has_website or managed_files or shipped_files or attachment_links:
        st.markdown("### Open or download")
        action_cols = st.columns(2, gap="large")
        with action_cols[0]:
            if has_website:
                st.link_button("Open website / tool ↗", website, type="primary", width="stretch")
            for idx, item in enumerate(attachment_links):
                st.link_button(f"Open {item.get('title') or 'supporting file'} ↗",
                               str(item["url"]), key=f"sh-tool-source-link-{tool_id}-{idx}", width="stretch")
        with action_cols[1]:
            for idx, meta in enumerate(managed_files):
                _render_resource_download(meta, key=f"tool-detail-managed-{tool_id}-{idx}",
                                          button_type="secondary", label=f"Download {meta.get('title') or meta.get('file_name')} ↓")
            for idx, (file_name, file_path, file_type) in enumerate(shipped_files):
                st.download_button(f"Download {file_name} ↓", data=file_path.read_bytes(),
                                   file_name=file_name, mime=file_type[1],
                                   key=f"tool-detail-shipped-{tool_id}-{idx}", width="stretch")
            if len(managed_files) + len(shipped_files) > 1:
                data, name, mime_type, count = _tool_download_payload(tool_id, tool)
                st.download_button(f"Download all {count} resources (.zip) ↓",
                                   data=data, file_name=name, mime=mime_type,
                                   key=f"tool-detail-all-{tool_id}", width="stretch")

    columns = tool.get("source_columns") or {}
    audience = _record_value(columns, "Target users", "Target audience") or str(tool.get("target_users") or "")
    purpose = _record_value(columns, "Purpose / useful for", "Purpose", "Useful for") or str(tool.get("purpose") or "")
    if audience or purpose:
        audience_col, purpose_col = st.columns(2, gap="large")
        with audience_col:
            if audience:
                st.markdown("### Target audience")
                st.markdown(audience)
        with purpose_col:
            if purpose:
                st.markdown("### Purpose")
                st.markdown(purpose)

    # Secondary metadata deliberately comes last. Keep the full range of
    # source fields without printing duplicate Description / How-to / Image.
    owner = _record_value(columns, "Developer / owner", "Developer", "Owner") or str(tool.get("developer") or "")
    requirements = _record_value(columns, "Technical requirements") or str(tool.get("requirements") or "")
    inputs = _record_value(columns, "Required inputs") or str(tool.get("inputs") or "")
    if owner or requirements or inputs:
        owner_col, practical_col = st.columns(2, gap="large")
        with owner_col:
            if owner:
                st.markdown("### Developer / owner")
                st.markdown(owner)
        with practical_col:
            if requirements or inputs:
                st.markdown("### Practical requirements")
                if requirements:
                    st.markdown(requirements)
                if inputs:
                    _record_field("Required inputs", inputs, list_style=True)

    shown_keys = {
        "title", "tool name", "name", "image", "image url", "tool image", "thumbnail",
        "short description", "description", "how to use", "steps", "tool type", "type", "format",
        "access link", "main url", "url", "supporting materials", "download url", "pdf", "file",
        "files", "attachments", "keywords", "related modules", "related resources", "part of mosaic",
        "target users", "target audience", "purpose useful for", "purpose", "useful for",
        "developer owner", "developer", "owner", "technical requirements", "required inputs",
    }
    additional = [(str(name), str(value)) for name, value in columns.items()
                  if _record_field_key(name) not in shown_keys and str(value).strip()]
    if additional:
        with st.expander("Additional details"):
            for label, value in additional:
                _record_field(label, value)

    links = _tool_lesson_links(tool)
    if links:
        st.markdown("### Used in the learning modules")
        link_cols = st.columns(min(2, len(links)))
        for idx, (module_id, lesson_id) in enumerate(links):
            module = MODULES.get(module_id)
            lesson = topic_by_id(module_id, lesson_id) if module else None
            if module and lesson:
                with link_cols[idx % len(link_cols)]:
                    st.button(f"{module['short_title']} · {lesson['title']} →",
                              key=f"tool-learning-link-{tool_id}-{module_id}-{lesson_id}",
                              width="stretch", on_click=navigate,
                              args=("topic", module_id, lesson_id, None, None), kwargs={"_rerun": False})
    _render_tool_preview(tool_id, tool)


def _change_tools_library_page(delta: int, page_count: int) -> None:
    """Move to the neighboring page without touching filter or tool state."""
    count = max(1, int(page_count))
    current = int(st.session_state.get("tools-library-page") or 1)
    st.session_state["tools-library-page"] = max(1, min(count, current + int(delta)))


def _render_tools_pager(page: int, page_count: int, *, position: str) -> None:
    """Compact accessible arrow navigation, displayed above and below results."""
    if page_count <= 1:
        return
    left, indicator, right = st.columns([1, 1.4, 1], gap="small", vertical_alignment="center")
    with left:
        st.button(
            "\u2190 Previous", key=f"tools-page-prev-{position}",
            disabled=page <= 1, width="stretch",
            on_click=_change_tools_library_page, args=(-1, page_count),
        )
    with indicator:
        st.markdown(
            f"<div class='m-tools-pager-label' aria-label='Tools results page {page} of {page_count}'>"
            f"Page {page} of {page_count}</div>",
            unsafe_allow_html=True,
        )
    with right:
        st.button(
            "Next \u2192", key=f"tools-page-next-{position}",
            disabled=page >= page_count, width="stretch",
            on_click=_change_tools_library_page, args=(1, page_count),
        )


def page_tools(user):
    selected_tool_id = st.session_state.get("tool_id")
    selected_tool = TOOL_DEFINITIONS.get(selected_tool_id)
    if selected_tool:
        _render_tool_detail(selected_tool_id, selected_tool)
        return

    st.markdown(
        """
        <div class='m-tools-repo-hero'>
            <div class='m-kicker'>MOSAIC Learn</div>
            <h1>Tools</h1>
            <p>Find practical methods, worksheets and external tools for land-use decision making. Search the repository, filter it, then open a tool to see its purpose, linked learning steps and downloadable resources.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("Not sure which tool fits? Start in [Learning](?page=modules), where lessons point to relevant tools in context.")
    search_col, module_col, format_col, keyword_col, mosaic_col = st.columns([2, 1.1, 1, 1.05, 1.1])
    with search_col:
        query = st.text_input("Search tools", placeholder="Search by name, description or keyword…", key="tools-search-query").strip()
    module_options = ["All modules"] + [module["short_title"] for module in MODULES.values()]
    with module_col:
        module_filter = st.selectbox("Module", module_options, key="tools-module-filter")
    format_options = ["All formats"] + sorted({str(tool.get("format") or "Tool") for tool in TOOL_DEFINITIONS.values()})
    with format_col:
        format_filter = st.selectbox("Format", format_options, key="tools-format-filter")
    keyword_options = ["All keywords"] + sorted({word for tool in TOOL_DEFINITIONS.values() for word in (tool.get("keywords") or [])})
    with keyword_col:
        keyword_filter = st.selectbox("Keyword", keyword_options, key="tools-keyword-filter")
    with mosaic_col:
        mosaic_filter = st.selectbox("Part of MOSAIC", ["All", "Yes", "No"],
                                     key="tools-mosaic-filter",
                                     help="Uses the Yes/No value imported from the Coda Tools table. Tools without a value appear under All only.")

    tool_items = [
        (tool_id, tool) for tool_id, tool in TOOL_DEFINITIONS.items()
        if _tool_matches_filters(tool, query=query, module_filter=module_filter,
                                 format_filter=format_filter, keyword_filter=keyword_filter,
                                 mosaic_filter=mosaic_filter)
    ]
    tool_items.sort(key=lambda item: str(item[1].get("title") or item[0]).casefold())
    st.caption(f"{len(tool_items)} of {len(TOOL_DEFINITIONS)} tools")
    if not tool_items:
        st.info("No tools match these filters.")
        return
    # Do not decode and embed every imported image in the library on each rerun.
    # Only the visible page's images are fetched from the existing cached store.
    page_size = 12
    page_count = (len(tool_items) + page_size - 1) // page_size
    # Changing filters resets the listing to the first page, but leaving a
    # Tool detail and returning keeps the user's current results page.
    filters = (query, module_filter, format_filter, keyword_filter, mosaic_filter)
    if st.session_state.get("tools-library-filter-signature") != filters:
        st.session_state["tools-library-filter-signature"] = filters
        st.session_state["tools-library-page"] = 1
    page = max(1, min(page_count, int(st.session_state.get("tools-library-page") or 1)))
    st.session_state["tools-library-page"] = page
    visible = tool_items[(page - 1) * page_size:page * page_size]
    first_result = ((page - 1) * page_size) + 1
    last_result = ((page - 1) * page_size) + len(visible)
    st.caption(f"Showing {first_result}–{last_result} of {len(tool_items)} matching tools")
    _render_tools_pager(page, page_count, position="top")
    cols = st.columns(3, gap="medium")
    for idx, (tool_id, tool) in enumerate(visible):
        with cols[idx % 3]:
            keywords = tool.get("keywords") or []
            keyword_html = "".join(f"<span class='m-tool-filter-tag'>{escape(word)}</span>" for word in keywords[:4])
            format_label = str(tool.get("format") or "Workshop")
            format_class = _tool_format_class(format_label)
            format_icon = TOOL_FORMAT_ICONS.get(format_label, "◫")
            media_html = _tool_card_media_html(tool_id, tool)
            duration_tag = f"<span class='m-tool-filter-tag'>{escape(tool.get('duration'))}</span>" if tool.get("duration") else ""
            st.markdown(
                f"""
                <div class='m-tool-repo-card {format_class}'>
                    {media_html}
                    <div class='m-tool-card-body'>
                        <div class='m-tool-format-line'><span class='m-tool-format-icon' aria-hidden='true'>{escape(format_icon)}</span><span>{escape(format_label)}</span></div>
                        <div class='m-kicker'>{escape(_tool_module_label(tool))}</div>
                        <h3>{escape(tool.get('title') or tool_id)}</h3>
                        <p>{escape(tool.get('description') or '')}</p>
                        <div class='m-tool-filter-tags'>{duration_tag}{keyword_html}</div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if _is_under_construction(tool):
                st.link_button("Under construction · subscribe →", MOSAIC_NEWSLETTER_URL, width="stretch")
            else:
                st.button("Open tool →", key=f"tool-open-{tool_id}", type="primary", width="stretch", on_click=navigate, args=("tools", "", "", tool_id, None), kwargs={"_rerun": False})
    _render_tools_pager(page, page_count, position="bottom")


def page_learning(user):
    """Backwards-compatible entry point: My learning now lives inside Learning."""
    st.session_state["learning-hub-section"] = "My learning"
    page_catalogue(user)


def render_module_path(user, module_id: str):
    module = MODULES[module_id]
    progress = _cached_progress(user["user_id"], module_id)
    all_topics = learning_topics(module)

    for level in ["Understand", "Apply"]:
        phase_topics = [t for t in all_topics if t["level"] == level]
        if not phase_topics:
            continue
        meta = LEVEL_META[level]
        phase_done = sum(
            1 for topic in phase_topics if progress.get(topic["id"], {}).get("completed")
        )

        with st.container(key=f"path_phase_{module_id}_{level.lower()}"):
            st.markdown(
                f"""
                <div class="m-phase-header {escape(level.lower())}">
                    <div class="m-phase-number">{meta['number']}</div>
                    <div><h3>{meta['verb']}</h3><p>{meta['tagline']}</p></div>
                    <div class="m-phase-progress">{phase_done}/{len(phase_topics)} complete</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            phase_intro = str((module.get("block_intros") or {}).get(level) or "").strip()
            if phase_intro:
                st.write(phase_intro)

            for topic in phase_topics:
                saved = progress.get(topic["id"], {})
                done = bool(saved.get("completed"))
                state_class = "done" if done else ""
                marker = "✓" if done else meta["icon"]
                step_number = all_topics.index(topic) + 1

                with st.container(
                    key=f"path_step_{module_id}_{topic['id']}",
                    border=True,
                ):
                    state_col, copy_col, action_col = st.columns(
                        [0.28, 4.7, 0.9],
                        vertical_alignment="center",
                        gap="small",
                    )
                    with state_col:
                        st.markdown(
                            f"<div class='m-lesson-state {state_class}'>{marker}</div>",
                            unsafe_allow_html=True,
                        )
                    with copy_col:
                        st.markdown(
                            f"<div class='m-path-copy'><div class='meta'>Step {step_number} of {len(all_topics)} · {topic['minutes']} min</div><h4>{escape(topic['title'])}</h4><p>{escape(topic['summary'])}</p></div>",
                            unsafe_allow_html=True,
                        )
                    with action_col:
                        st.button(
                            "Review →" if done else "Start →",
                            key=f"module-topic-{topic['id']}",
                            width="stretch",
                            type="primary" if not done else "secondary",
                         on_click=navigate, args=("topic", module_id, topic["id"], None, None), kwargs={"_rerun": False})


def render_module_modes(user, module_id: str):
    module = MODULES[module_id]
    topics = learning_topics(module)
    understand = [t for t in topics if t.get("level") == "Understand"]
    apply_steps = [t for t in topics if t.get("level") == "Apply"]
    convince_lessons = [t for t in module.get("topics", []) if t.get("level") == "Convince"]
    convince_has_content = bool(convince_lessons or module.get("convince") or _resource_files_for("convince", module_id))
    cols = st.columns(3)
    cards = [
        ("understand", "01", "Discover", "Read the concepts in short, easy-to-scan steps and check your understanding.", f"{len(understand)} learning step{'s' if len(understand) != 1 else ''}"),
        ("apply", "02", "Apply", "Move from concepts to methods, decisions and reflections in your own context.", f"{len(apply_steps)} practical step{'s' if len(apply_steps) != 1 else ''}"),
        (
            "convince",
            "03",
            "Communicate",
            "Find briefs, presentations and examples to share the value of a method with colleagues and decision makers."
            if convince_has_content
            else "Find useful materials for conversations, proposals and sharing your work.",
            f"{len(convince_lessons)} classes · resources to communicate",
        ),
    ]
    for col, (cls, num, title, text, note) in zip(cols, cards):
        with col:
            phase_slot = {"understand": "discover", "apply": "apply", "convince": "communicate"}[cls]
            phase_art = asset_image_html(
                ILLUSTRATION_SLOTS[phase_slot],
                alt="",  # purely decorative; the phase name is already visible
                css_class="m-mode-doodle",
            )
            st.markdown(
                f"<div class='m-mode-card {cls}'><div class='m-mode-top'>"
                f"<div class='m-mode-num'>{num}</div>{phase_art}</div>"
                f"<h3>{title}</h3><p>{text}</p><span class='m-mode-note'>{note}</span></div>",
                unsafe_allow_html=True,
            )
            if cls == "convince":
                st.button("Explore communication resources →", key=f"mode-convince-{module_id}", width="stretch", type="secondary", on_click=navigate, args=("convince", module_id, None, None, None), kwargs={"_rerun": False})
            else:
                candidates = understand if cls == "understand" else apply_steps
                if candidates:
                    st.button(f"Go to {title.lower()} →", key=f"mode-{cls}-{module_id}", width="stretch", on_click=navigate, args=("phase", module_id, None, None, "discover" if cls == "understand" else "apply"), kwargs={"_rerun": False})


def page_phase(user):
    """Overview of the classes in Discover or Apply before opening a lesson."""
    module_id = str(st.session_state.get("module_id") or "")
    if module_id not in MODULES:
        navigate("catalogue")
        return
    module = MODULES[module_id]
    if _is_under_construction(module):
        st.info("This module is under construction.")
        return
    phase = str(st.session_state.get("phase") or "discover").lower()
    phase = phase if phase in {"discover", "apply"} else "discover"
    level = "Understand" if phase == "discover" else "Apply"
    title = "Discover" if phase == "discover" else "Apply"
    classes = [item for item in learning_topics(module) if item.get("level") == level]
    st.button("← Module overview", key=f"phase-back-{module_id}-{phase}", on_click=navigate, args=("module", module_id, None, None, None), kwargs={"_rerun": False})
    st.markdown(f"<div class='m-kicker'>{escape(module['short_title'])} · {title}</div>", unsafe_allow_html=True)
    st.title(f"{title} classes")
    intro = str((module.get("block_intros") or {}).get(level) or "").strip()
    st.write(intro or ("Explore the concepts in order, or open a class you want to revisit."
                       if phase == "discover" else
                       "Explore the practical activities, or go directly to a class you need."))
    if not classes:
        st.info("No classes have been published in this section yet.")
        return
    progress = _cached_progress(user["user_id"], module_id)
    completed = sum(bool(progress.get(c["id"], {}).get("completed")) for c in classes)
    st.progress(completed / len(classes), text=f"{completed}/{len(classes)} classes completed")
    for idx, lesson in enumerate(classes, 1):
        done = bool(progress.get(lesson["id"], {}).get("completed"))
        with st.container(border=True, key=f"phase_class_{module_id}_{phase}_{lesson['id']}"):
            detail, action = st.columns([5, 1.2], vertical_alignment="center")
            with detail:
                st.caption(f"Class {idx} of {len(classes)} · {lesson.get('minutes', 8)} min · {'Completed' if done else 'Not yet completed'}")
                st.markdown(f"<div class='m-card-title'>{escape(str(lesson.get('title') or 'Class'))}</div>", unsafe_allow_html=True)
                if lesson.get("summary"):
                    st.write(str(lesson["summary"]))
            with action:
                st.button("Review →" if done else "Open class →",
                             key=f"phase_open_{module_id}_{lesson['id']}", width="stretch", on_click=navigate, args=("topic", module_id, lesson["id"], None, None), kwargs={"_rerun": False})
    _render_linked_page_sections((module.get("phase_references") or {}).get(level) or {},
                                  key=f"phase_{module_id}_{phase}")


def render_building_blocks(module):
    blocks = module.get("building_blocks") or []
    if not blocks:
        return
    cards = "".join(
        f"<div class='m-building-card'><div class='num'>{idx:02d}</div><b>{escape(title)}</b><span>{escape(text)}</span></div>"
        for idx, (title, text) in enumerate(blocks, start=1)
    )
    st.markdown("<div class='m-section-title'><h2>Six building blocks</h2><p>Use them as a sequence or start where your uncertainty is highest.</p></div>", unsafe_allow_html=True)
    st.markdown(f"<div class='m-building-grid'>{cards}</div>", unsafe_allow_html=True)


def render_module_routes(user, module_id: str):
    module = MODULES[module_id]
    entry_points = module.get("entry_points") or []
    if not entry_points:
        return

    st.markdown("<div class='m-section-title'><h2>Choose your route</h2><p>You do not have to use the module in exactly the same way every time.</p></div>", unsafe_allow_html=True)
    route_key = f"route-mode-{module_id}"
    route_mode = st.segmented_control(
        "Route through this module",
        ["Quick route", "Full route", "Check-up route"],
        default="Quick route",
        key=route_key,
        label_visibility="collapsed",
    )

    if route_mode == "Full route":
        st.markdown("<div class='m-route-card'><h4>Full route</h4><p>Work through the introduction and all building blocks in sequence.</p></div>", unsafe_allow_html=True)
        st.button("Start from the beginning →", key=f"full-route-{module_id}", type="primary", on_click=navigate, args=("topic", module_id, module["topics"][0]["id"], None, None), kwargs={"_rerun": False})
    elif route_mode == "Check-up route":
        st.markdown("<div class='m-route-card'><h4>Check-up route</h4><p>Rate how clear each part currently feels. The app suggests the block with the lowest confidence as your starting point.</p></div>", unsafe_allow_html=True)
        scores = {}
        cols = st.columns(2)
        for idx, (topic_id, label) in enumerate(entry_points):
            short = label.split(" — ", 1)[0]
            with cols[idx % 2]:
                scores[topic_id] = st.select_slider(
                    short,
                    options=[1, 2, 3, 4, 5],
                    value=3,
                    key=f"checkup-{module_id}-{topic_id}",
                    help="1 = very uncertain, 5 = very clear",
                )
        lowest = min(scores, key=scores.get)
        suggestion = next(label for tid, label in entry_points if tid == lowest)
        st.info(f"Suggested starting point: {suggestion}")
        st.button("Start suggested block →", key=f"checkup-start-{module_id}", type="primary", on_click=navigate, args=("topic", module_id, lowest, None, None), kwargs={"_rerun": False})
    else:
        st.markdown("<div class='m-route-card'><h4>Quick route</h4><p>Choose the question where you hesitate most. That is your most useful starting block.</p></div>", unsafe_allow_html=True)
        labels = [label for _, label in entry_points]
        choice = st.selectbox("Where are you least certain?", labels, key=f"quick-route-select-{module_id}")
        chosen_id = next(tid for tid, label in entry_points if label == choice)
        st.button("Jump to this block →", key=f"quick-route-start-{module_id}", type="primary", on_click=navigate, args=("topic", module_id, chosen_id, None, None), kwargs={"_rerun": False})


def _page_links_for_share(module: dict) -> dict:
    """Assemble references placed on the Communicate phase page or its classes.

    The persisted level remains 'Convince' so existing progress and URLs work.
    Resource rows with a related module + Communicate/Communicate/Share/Convince phase are included by
    the manual import; no bespoke downloadable-file unit is required.
    """
    group = dict((module.get("phase_references") or {}).get("Convince") or {})
    output = {"resource_references": list(group.get("resource_references") or []),
              "tool_references": list(group.get("tool_references") or []),
              "further_reading": list(group.get("further_reading") or []),
              "resource_ids": list(group.get("resource_ids") or [])}
    for lesson in module.get("topics") or []:
        if lesson.get("level") == "Convince":
            for key in output:
                output[key].extend(lesson.get(key) or [])
    return output


def _render_linked_page_sections(page: dict, *, key: str, extra_tool_refs: list[dict] | None = None) -> None:
    """Small, accessible local library cards at the BOTTOM of a page.

    Look up canonical published records locally, not via the Coda API.
    Preserve the original HTTPS URL as a safe fallback if a table record has
    not been published, and never create a duplicated standalone record.
    """
    resource_refs = [r for r in page.get("resource_references") or [] if isinstance(r, dict)]
    resource_ids = [str(rid) for rid in page.get("resource_ids") or [] if str(rid)]
    tool_refs = [r for r in page.get("tool_references") or [] if isinstance(r, dict)]
    tool_refs.extend(r for r in (extra_tool_refs or []) if isinstance(r, dict))
    further_refs = [r for r in page.get("further_reading") or [] if isinstance(r, dict)]
    if not (resource_refs or resource_ids or tool_refs or further_refs):
        return
    published_resources = _published_library_resources() if (resource_refs or resource_ids) else {}

    def render_wide_link_card(*, card_key: str, title: str, meta: str,
                              description: str = "", rid: str = "", url: str = "",
                              kind: str = "Further reading", record: dict | None = None) -> None:
        """Accessible full-width item: quiet row for reading, green action for tools."""
        record = record or {}
        excerpt = re.sub(r"\s+", " ", description).strip()
        if len(excerpt) > 125:
            excerpt = excerpt[:122].rsplit(" ", 1)[0] + "…"
        tool_row = kind == "Tool"
        row_key = ("try_tool_" if tool_row else "compact_link_") + card_key
        # Removing the heavy Streamlit bordered container also avoids the
        # apparent double-outline and uneven description overflow.
        with st.container(border=False, key=row_key):
            copy_col, action_col = st.columns([5.6, 1.4], gap="small", vertical_alignment="center")
            with copy_col:
                content = ("<div class='m-wide-link-copy'>"
                           f"<div class='m-wide-link-title'>{escape(title)}</div>"
                           + (f"<p>{escape(excerpt)}</p>" if excerpt else "")
                           + (f"<span class='m-wide-link-meta'>{escape(meta)}</span>" if meta else "")
                           + "</div>")
                st.markdown(content, unsafe_allow_html=True)
            with action_col:
                if rid and record and kind == "Resource":
                    st.button("Read more →", help=f"Open resource: {title}",
                              key=f"open_{card_key}", width="stretch",
                              on_click=_navigate_resource_detail, args=(rid,),
                              kwargs={"_rerun": False})
                elif rid and record and tool_row:
                    st.button("Try tool →", help=f"Open tool: {title}",
                              key=f"open_{card_key}", width="stretch",
                              on_click=navigate, args=("tools", "", "", rid, None),
                              kwargs={"_rerun": False})
                elif _valid_external_url(url):
                    st.link_button("Open tool ↗" if tool_row else "Open ↗", url,
                                   help=f"Open {title}", width="stretch")
                else:
                    st.caption("Not yet available")

    def compact_cards(kind: str, references: list[dict]) -> None:
        if not references:
            return
        seen = set()
        cards = []
        for ref in references:
            rid = str(ref.get("app_id") or "")
            name = re.sub(r"^[\s@•·*\-]+", "", str(ref.get("title") or kind)).strip() or kind
            url = str(ref.get("url") or "")
            signature = rid or url or name.casefold()
            if signature in seen or ref.get("status") == "placeholder":
                continue
            seen.add(signature)
            record = (published_resources if kind == "Resource" else TOOL_DEFINITIONS).get(rid) or {}
            if not record and ref.get("description"):
                record = {"description": str(ref.get("description"))}
            cards.append((rid, name, url, record))
        if not cards:
            return
        if kind == "Tool":
            st.markdown("### Try our tools")
            st.caption("Explore practical tools and materials you can use in your own work.")
        else:
            st.markdown("### Resources")
        for index, (rid, name, url, record) in enumerate(cards):
            title = str(record.get("title") or name)
            typ = str((record.get("resource_type") if kind == "Resource" else
                       record.get("tool_type") or record.get("format")) or kind)
            description = str(record.get("description") or record.get("purpose") or "").strip()
            render_wide_link_card(card_key=f"{key}_{kind.lower()}_{index}", title=title,
                                  meta=typ, description=description,
                                  rid=rid, url=url, kind=kind, record=record)

    # Support legacy manually linked resource_ids in the same area.
    for rid in resource_ids:
        if rid in published_resources and not any(str(r.get("app_id") or "") == rid for r in resource_refs):
            resource_refs.append({"title": published_resources[rid]["title"], "app_id": rid})
    compact_cards("Resource", resource_refs)
    compact_cards("Tool", tool_refs)
    read_more = []
    seen_urls = set()
    for ref in further_refs:
        url = str(ref.get("url") or "")
        if not _valid_external_url(url) or url in seen_urls:
            continue
        seen_urls.add(url)
        title = re.sub(r"^[\s@•·*\-]+", "", str(ref.get("title") or "Further reading")).strip()
        read_more.append((title, url))
    if read_more:
        st.markdown("### Continue exploring")
        for idx, (title, url) in enumerate(read_more):
            render_wide_link_card(card_key=f"{key}_reading_{idx}", title=title,
                                  meta="Further reading", url=url)


def page_module(user):
    module_id = st.session_state.get("module_id", "drivers")
    if module_id not in MODULES:
        module_id = "drivers"
        st.session_state.module_id = module_id
    module = MODULES[module_id]
    ratio, done, total = module_completion(user["user_id"], module_id)

    st.button("← All modules", on_click=navigate, args=("catalogue", None, None, None, None), kwargs={"_rerun": False})

    hero_class = module["track"].lower()
    # A figure from the module landing page takes priority over generic
    # drawings, just as it does on the module catalogue card.
    imported_cover = _module_cover_uri(module)
    module_art = (f'<img class="m-module-hero-cover" loading="lazy" '
                  f'src="{escape(imported_cover, quote=True)}" '
                  f'alt="Illustration for {escape(str(module.get("title") or "learning module"), quote=True)}">'
                  if imported_cover else _module_drawing(module_id))
    module_art_class = " has-cover" if imported_cover else ""
    st.markdown(
        f"""
        <div class="m-module-hero m-module-illustrated {hero_class}">
            <div class="m-module-hero-copy">
                <div class="m-kicker">{escape(module['track'])} · {escape(module['eyebrow'])}</div>
                <h1>{escape(module['title'])}</h1>
                <p>{escape(module['description'])}</p>
                <div class="m-hero-meta"><span class="m-chip">{module['estimated_minutes']} min learning path</span><span class="m-chip">{total} tracked steps</span><span class="m-chip">Self-paced</span></div>
            </div>
            <div class="m-module-hero-art{module_art_class}">{module_art}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if module["status"] != "Available":
        if _is_under_construction(module):
            st.warning("This module is under construction and is not yet available for learners.")
            st.link_button(
                "Subscribe to the MOSAIC newsletter for updates →",
                MOSAIC_NEWSLETTER_URL,
                type="primary",
                width="content",
            )
        else:
            st.info("This module is not available yet.")
        return

    st.markdown("<div class='m-section-title'><h2>Three ways to use this module</h2><p>Discover and Apply form the core learning journey. Communicate offers briefs, presentations and messages to help others understand and use the methods.</p></div>", unsafe_allow_html=True)
    render_module_modes(user, module_id)

    top_left, top_right = st.columns([2.25, 1])
    with top_left:
        st.markdown("### What you'll get from this module")
        outcomes_html = "".join(f"<li>{escape(item)}</li>" for item in module["learning_outcomes"])
        st.markdown(f"<div class='m-outcomes'><ul>{outcomes_html}</ul></div>", unsafe_allow_html=True)
    with top_right:
        st.markdown("### Your learning progress")
        st.markdown(progress_bar_html(ratio), unsafe_allow_html=True)
        st.markdown(f"**{round(ratio * 100)}% complete**")
        st.caption(f"{done} of {total} learning steps completed")
        st.caption("Progress tracks Discover and Apply.")
        next_topic_id = first_incomplete_topic(user["user_id"], module_id)
        if next_topic_id:
            st.button("Continue learning →", key=f"module-continue-{module_id}", type="primary", width="stretch", on_click=navigate, args=("topic", module_id, next_topic_id, None, None), kwargs={"_rerun": False})

    role_name = user.get("role") or "Research"
    if role_name in ROLE_CALLOUTS:
        st.markdown(f"<div class='m-role-callout'><strong>For your role</strong><br>{escape(ROLE_CALLOUTS[role_name])}</div>", unsafe_allow_html=True)

    st.markdown("<div class='m-section-title'><h2>Discover & Apply</h2><p>This is the tracked learning path. Discover builds background knowledge; Apply develops practical skills.</p></div>", unsafe_allow_html=True)
    render_module_path(user, module_id)

    # Communication classes are visible in the module journey, but are not
    # included in the Discover/Apply progress numerator or denominator.
    communicate_classes = [t for t in module.get("topics", []) if t.get("level") == "Convince"]
    if communicate_classes:
        st.markdown(
            "<div class='m-section-title m-communicate-heading'><h2>Communicate classes</h2>"
            "<p>Use the research in a brief, proposal or conversation with colleagues.</p></div>",
            unsafe_allow_html=True,
        )
        for idx, lesson in enumerate(communicate_classes, 1):
            with st.container(key=f"communicate_class_{module_id}_{lesson['id']}", border=True):
                copy_col, action_col = st.columns([5, 1.1], vertical_alignment="center")
                with copy_col:
                    st.caption(f"Class {idx} · {lesson.get('minutes', 8)} min")
                    st.markdown(f"<div class='m-card-title'>{escape(str(lesson.get('title') or 'Class'))}</div>", unsafe_allow_html=True)
                    if lesson.get('summary'):
                        st.write(str(lesson['summary']))
                with action_col:
                    st.button("Open class →", key=f"communicate_open_{module_id}_{lesson['id']}",
                              width="stretch", on_click=navigate,
                              args=("topic", module_id, lesson["id"], None, None),
                              kwargs={"_rerun": False})

    # Orientation content follows the lesson list so learners see the learning path first.
    render_building_blocks(module)
    render_module_routes(user, module_id)

    st.markdown("<div class='m-section-title'><h2>Need to bring someone else with you?</h2><p>Find briefs, presentations and examples you can share in meetings and proposals.</p></div>", unsafe_allow_html=True)
    st.button("Explore communication resources →", key=f"module-convince-bottom-{module_id}", type="secondary", on_click=navigate, args=("convince", module_id, None, None, None), kwargs={"_rerun": False})
    _render_linked_page_sections(module, key=f"module_{module_id}")
    if module.get("source_note"):
        st.caption(module["source_note"])


def render_driver_visual(module):
    groups = module.get("driver_groups") or []
    if not groups:
        return
    cards = "".join(
        f"<div class='m-driver'><b>{escape(title)}</b><span>{escape(detail)}</span></div>" for title, detail in groups
    )
    st.markdown(
        f"<section class='m-driver-system'><div class='m-reading-intro'><h3>The driver system</h3></div><div class='m-driver-grid'>{cards}</div><p class='m-muted m-small'>The point is not to choose one box. Ask how these forces interact in place and for a specific actor.</p></section>",
        unsafe_allow_html=True,
    )


def _case_study_reading_copy(item: dict, body_html: str) -> tuple[str, str]:
    """Make structured research notes read as a short case narrative.

    The Context/Approach/Result/Lesson fields remain untouched in SHD and the
    import database. This only changes their presentation to the learner.
    """
    label = str(item.get("label") or "").casefold().strip()
    title = str(item.get("title") or "Case study").strip()
    if "case study" not in label and title.casefold() != "case study":
        return title, body_html
    paragraphs = re.findall(r"(?is)<p\b[^>]*>(.*?)</p>", body_html)
    if not paragraphs:
        return title, body_html
    cleaned = []
    detected = 0
    for html_part in paragraphs:
        part = html_part.strip()
        plain = re.sub(r"<[^>]+>", "", part).strip()
        # The generic source title may be placed as the first line of the text.
        if title.casefold() == "case study" and not cleaned and plain and not re.match(
                r"(?i)^(context|approach|result|lesson|figure|source)\s*:", plain):
            title = unescape(plain)
            continue
        match = re.match(r"(?is)^\s*(?:<strong>)?\s*(context|approach|result|lesson)\s*:\s*(?:</strong>)?\s*", part)
        if match:
            detected += 1
            narrative = part[match.end():].strip()
            if match.group(1).lower() == "lesson":
                cleaned.append("<div class='m-case-study-lesson'><strong>What this shows</strong>"
                               f"<p>{narrative}</p></div>")
            elif narrative:
                cleaned.append(f"<p>{narrative}</p>")
        elif re.match(r"(?is)^\s*(?:<strong>)?\s*figure\s*:", part) and "image from the original" in plain.casefold():
            # Don't show an editorial placeholder as though it were a caption.
            continue
        elif re.match(r"(?is)^\s*(?:<strong>)?\s*source\s*:", part):
            # Keep references visible; convert a bare HTTPS link to a real anchor.
            url = re.search(r"https://[^\s<]+", plain)
            if url:
                safe_url = escape(url.group(0), quote=True)
                cleaned.append(f"<p class='m-case-study-source'>Source: <a href='{safe_url}' target='_blank' rel='noopener noreferrer'>{escape(url.group(0))}</a></p>")
            else:
                cleaned.append(f"<p class='m-case-study-source'>{part}</p>")
        else:
            cleaned.append(f"<p>{part}</p>")
    if detected < 2:
        return str(item.get("title") or "Case study"), body_html
    return title, "".join(cleaned)


@st.fragment
# Only the learning card rerenders when Previous / Next is pressed.
# This avoids rebuilding the lesson header and its other widgets, which used
# to cause grey "stale" remnants and unintended scroll jumps.
def render_theory_story(module_id: str, topic):
    cards = list(topic.get("theory_cards") or [])
    if not cards:
        st.markdown(f"<div class='m-reading'>{escape(topic.get('body', ''))}</div>", unsafe_allow_html=True)
        return False

    # Every lesson with a Key idea or MOSAIC practice note gets one final
    # synthesis screen. This uses existing content fields, so no content.py flag
    # is required and the same material is not repeated below the carousel.
    embed_summary = bool(
        topic.get("takeaway_html")
        or topic.get("practice_note_html")
        or topic.get("takeaway")
        or topic.get("practice_note")
    )
    is_imported = topic.get("source_system") == "superhuman_docs"
    # A native key idea may still use the old synthesis layout. Imported
    # Takeaways are a clean list without the Key idea/green-highlight heading.
    slides = cards + ([{"summary_slide": True}] if embed_summary else [])

    state_key = f"theory-step-{module_id}-{topic['id']}"
    st.session_state.setdefault(state_key, 1)
    step = int(st.session_state[state_key])
    step = max(1, min(len(slides), step))
    st.session_state[state_key] = step

    st.markdown(
        "<div class='m-reading-intro'><h3>Read the theory one idea at a time</h3>"
        "<p>Use Previous and Next to explore the ideas in this class.</p></div>",
        unsafe_allow_html=True,
    )

    def _set_story_step(target: int):
        st.session_state[state_key] = max(1, min(len(slides), target))

    # A compact, stable two-button row ABOVE the card: no idea counter or
    # extra scroll action. Fragment reruns leave the browser position alone.
    with st.container(key="theory_navigation"):
        # The spacer occupies the middle of the FULL card width. In a 2-column
        # layout Streamlit positions Next at the start of the right half.
        prev_col, _, next_col = st.columns([1.35, 7, 1.35], gap="small", vertical_alignment="center")
        with prev_col:
            st.button("← Previous", key=f"theory-prev-{module_id}-{topic['id']}",
                      disabled=step <= 1, width="stretch", on_click=_set_story_step,
                      args=(step - 1,))
        with next_col:
            st.button("Next →", key=f"theory-next-{module_id}-{topic['id']}",
                      disabled=step >= len(slides), width="stretch", on_click=_set_story_step,
                      args=(step + 1,))

    item = slides[step - 1]
    bullets = ""
    if item.get("bullets"):
        bullets = "<ul>" + "".join(f"<li>{escape(b)}</li>" for b in item["bullets"]) + "</ul>"

    # Keep this HTML on one logical line. Indented closing tags can be parsed as
    # Markdown code blocks by some Streamlit/Markdown combinations.
    if item.get("summary_slide"):
        takeaway_html = sanitize_rich_text(
            topic.get("takeaway_html") or plain_text_as_html(topic.get("takeaway", ""))
        )
        practice_note_html = sanitize_rich_text(
            topic.get("practice_note_html") or plain_text_as_html(topic.get("practice_note", ""))
        )
        practice_image = asset_image_html(
            topic.get("practice_image"),
            alt=topic.get("practice_image_alt", "MOSAIC practice"),
            css_class="m-practice-media",
        )
        practice_media = practice_image or (
            "<div class='m-practice-media m-practice-pattern' aria-hidden='true'><span>MOSAIC practice</span></div>"
        )
        practice_feature = ""
        if practice_note_html:
            practice_feature = (
                "<div class='m-practice-feature'><div class='m-practice-feature-copy'>"
                "<div class='label'>From MOSAIC practice</div>"
                f"<div class='m-rich-text'>{practice_note_html}</div></div>{practice_media}</div>"
            )
        if is_imported and topic.get("takeaway"):
            points = [re.sub(r"^[\s•·*-]+", "", x).strip() for x in topic["takeaway"].splitlines() if x.strip()]
            takeaway_html = "<ul>" + "".join(f"<li>{escape(x)}</li>" for x in points) + "</ul>"
            heading = "Key takeaways"
            feature_html = ""  # Imported takeaways need no extra practice panel.
        else:
            heading = "Key idea"
            feature_html = f"<div class='m-key-idea-panel'><div class='m-rich-text'>{takeaway_html}</div></div>{practice_feature}"
        card_html = (
            "<div class='m-theory-wrap'>"
            "<div class='m-theory-card synthesis'><div class='m-synthesis-inner'>"
            "<div class='m-theory-label'>Summary</div>"
            f"<h3>{heading}</h3>"
            + (f"<div class='m-rich-text m-takeaway-list'>{takeaway_html}</div>" if is_imported and topic.get("takeaway") else feature_html) +
            "</div></div></div>"
        )
    else:
        body_html = sanitize_rich_text(
            item.get("body_html")
            or item.get("text_html")
            or plain_text_as_html(item.get("text", ""))
        )
        image_ids = list(dict.fromkeys([str(item.get("image_resource_id") or "")] +
                                            [str(x) for x in (item.get("image_resource_ids") or [])]))
        idea_image_uris = [_resource_image_data_uri(rid) for rid in image_ids if rid]
        idea_image_uris = [uri for uri in idea_image_uris if uri]
        idea_image_html = ""
        card_class = "m-theory-card"
        if idea_image_uris:
            idea_image_html = "".join(
                "<figure class='m-idea-media m-image-below-card'>"
                f"<img src='{uri}' alt='{escape(str(item.get('image_alt') or item.get('title') or 'Idea image'))}'>"
                "</figure>" for uri in idea_image_uris
            )
        # Ordinary ideas do not need case-study parsing.
        if str(item.get("label") or "").strip().casefold() == "case study" or str(item.get("title") or "").strip().casefold() == "case study":
            display_title, body_html = _case_study_reading_copy(item, body_html)
        else:
            display_title = str(item.get("title") or "")
        label = str(item.get("label") or "").strip()
        label_html = (f"<div class='m-theory-label'>{escape(label)}</div>"
                      if label and label.casefold() not in {"text", "core idea", "table"} else "")
        if idea_image_html:
            card_class += " has-idea-image"
        card_html = (
            "<div class='m-theory-wrap'>"
            f"<div class='{card_class}'><div class='m-theory-inner'>"
            f"{label_html}"
            f"<h3>{escape(display_title)}</h3>"
            f"<div class='m-rich-text'>{body_html}</div>"
            f"{bullets}"
            # The image is a child of the card, not a sibling outside it.
            f"</div>{idea_image_html}</div></div>"
        )
    st.markdown(card_html, unsafe_allow_html=True)

    return embed_summary


def render_learning_extras(module_id: str, topic, *, include_practice: bool = True):
    """Render contextual practice text; tool actions now live in Try our tools.

    Older versions rendered each linked tool above the reflection, then
    rendered the Superhuman Tools callout again at the bottom. Both sources
    now feed one unified, deduplicated section after the lesson activities.
    """
    if include_practice and topic.get("practice_note"):
        st.markdown(
            f"<div class='m-practice-note'><div class='label'>From MOSAIC practice</div><p>{escape(topic['practice_note'])}</p></div>",
            unsafe_allow_html=True,
        )


def _lesson_tool_references(module_id: str, topic: dict) -> list[dict]:
    """Combine legacy lesson-tool relations with Superhuman row references.

    This function only returns references; publishing, downloading and detail
    pages remain owned by the existing Tools library.
    """
    refs = []
    for tool_id, tool in _tools_for_learning_step(module_id, str(topic.get("id") or "")):
        refs.append({"app_id": str(tool_id),
                     "title": str(tool.get("title") or tool.get("name") or tool_id)})
    legacy = topic.get("tool") if isinstance(topic.get("tool"), dict) else None
    if legacy:
        legacy_id = str(legacy.get("id") or "").strip()
        if legacy_id and legacy_id in TOOL_DEFINITIONS:
            refs.append({"app_id": legacy_id,
                         "title": str(legacy.get("title") or legacy.get("name") or legacy_id)})
        else:
            # Preserve older authored tool suggestions even when no local ID
            # or public URL is available yet; do not silently drop content.
            refs.append({"title": str(legacy.get("title") or legacy.get("name") or "Tool"),
                         "description": str(legacy.get("description") or ""),
                         "url": str(legacy.get("url") or legacy.get("access_link") or "")})
    return refs


def render_quiz(user, module_id: str, topic):
    quiz = topic.get("quiz")
    questions = topic.get("self_check") or []
    if not quiz and not questions:
        return

    with st.container(key=f"quiz_card_{module_id}_{topic['id']}", border=True):
        description = (
            "Check your understanding, then use the prompts to reflect on your own context."
            if quiz and questions
            else "Choose the best answer, then check your reasoning."
            if quiz
            else "Use these prompts to reflect on your own context."
        )
        st.markdown(
            f"<div id='quick-check' class='m-quiz-header'><div class='m-quiz-icon'>?</div><div><div class='m-kicker'>3-minute self-check</div><h3>A quick check</h3><p>{description}</p></div></div>",
            unsafe_allow_html=True,
        )
        if quiz:
            previous = _cached_quiz_results(user["user_id"], module_id).get(topic["id"])
            prior_index = int(previous["selected_index"]) if previous else None
            choice = st.radio(
                quiz["question"],
                quiz["options"],
                index=prior_index,
                key=f"quiz-{module_id}-{topic['id']}",
            )
            if st.button(
                "Check answer",
                key=f"check-{module_id}-{topic['id']}",
                type="primary", disabled=(choice is None),
            ):
                selected = quiz["options"].index(choice)
                correct = selected == quiz["answer"]
                _save_quiz(user["user_id"], module_id, topic["id"], selected, correct)
                if correct:
                    st.success("Correct. " + quiz["explanation"])
                else:
                    st.error("Not quite. " + quiz["explanation"])

            previous = _cached_quiz_results(user["user_id"], module_id).get(topic["id"])
            if previous:
                if previous["is_correct"]:
                    st.markdown(
                        "<div class='m-quiz-status pass'>✓ Quick check completed correctly</div>",
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown(
                        "<div class='m-quiz-status retry'>↻ Ready for another attempt</div>",
                        unsafe_allow_html=True,
                    )

        if questions:
            st.markdown(
                "<div class='m-self-check-intro'><h4>Review before you continue</h4><p>Select the prompts you have considered. Revisit your reflection above if the check reveals something useful.</p></div>",
                unsafe_allow_html=True,
            )
            for idx, question in enumerate(questions, start=1):
                st.checkbox(question, key=f"selfcheck-{topic['id']}-{idx}")


def _lesson_navigation(module: dict, topic: dict) -> dict:
    """Class sequence stays within its phase; phase changes use overviews.

    The app's progress sequence (Discover + Apply) is not the UI's Next lesson
    sequence. This distinction avoids jumping unexpectedly into Apply.
    """
    level = str(topic.get("level") or "Understand")
    phase_topics = [t for t in module.get("topics", []) if t.get("level") == level]
    current_index = next((i for i, t in enumerate(phase_topics)
                          if t.get("id") == topic.get("id")), -1)
    if current_index < 0:
        return {"topics": [topic], "index": 0, "previous": None, "next": None,
                "destination": ("module", None), "button_label": "Module overview →"}
    previous = phase_topics[current_index - 1] if current_index else None
    following = phase_topics[current_index + 1] if current_index < len(phase_topics)-1 else None
    if following:
        destination = ("topic", following["id"])
        label = "Next lesson →"
    elif level == "Understand" and any(t.get("level") == "Apply" for t in module.get("topics", [])):
        destination = ("phase", "apply")
        label = "Continue to Apply overview →"
    elif level == "Convince":
        destination = ("convince", None)
        label = "Back to Communicate overview →"
    else:
        destination = ("module", None)
        label = "Back to module overview →"
    return {"topics": phase_topics, "index": current_index, "previous": previous,
            "next": following, "destination": destination, "button_label": label}


def _navigate_lesson_destination(
    module_id: str, destination: tuple[str, str | None], *, _rerun: bool = True
) -> None:
    route, target = destination
    if route == "phase":
        navigate("phase", module_id, phase=target, _rerun=_rerun)
    elif route == "topic":
        navigate("topic", module_id, target, _rerun=_rerun)
    else:
        navigate(route, module_id, _rerun=_rerun)


def _leave_local_preview() -> None:
    st.session_state.demo_user = None
    navigate("home", _rerun=False)


def _navigate_with_context(
    route: str, module_id: str | None = None, *,
    state_updates: dict[str, str] | None = None,
) -> None:
    """Write auxiliary UI state and navigate during a button callback."""
    for key, value in (state_updates or {}).items():
        st.session_state[key] = value
    navigate(route, module_id, _rerun=False)


def _complete_and_continue(
    user_id: str, module_id: str, topic_id: str, already_completed: bool,
    destination: tuple[str, str | None],
) -> None:
    """Complete and navigate in a single widget-triggered rerun.

    The reflection widget may live inside a fragment; read its Session State
    value at click time rather than a response captured by a prior full run.
    """
    if not already_completed:
        reflection = str(st.session_state.get(f"reflection-{module_id}-{topic_id}") or "")
        _save_progress(user_id, module_id, topic_id,
                       completed=True, reflection=reflection)
    _navigate_lesson_destination(module_id, destination, _rerun=False)


@st.fragment
def render_context_notebook(user: dict, module_id: str, topic: dict, saved: dict) -> str:
    """Keep every notebook-related control inside one accessible visual card.

    The fragment means typing or saving does not rerender the entire class.
    On Complete & continue, Streamlit reruns the full page and reads the
    current text_area value to persist any unsaved response with progress.
    """
    initial = str(saved.get("reflection") or "")
    with st.container(border=True, key=f"context_notebook_{module_id}_{topic['id']}"):
        st.markdown("### Apply it to your context")
        st.markdown(str(topic["prompt"]))
        response = st.text_area(
            "Your reflection",
            value=initial,
            key=f"reflection-{module_id}-{topic['id']}",
            placeholder="Capture a short observation or example you want to remember.",
            height=140,
        )
        if st.button("Save to reflection notebook", key=f"save-{module_id}-{topic['id']}",
                     width="content"):
            _save_progress(user["user_id"], module_id, topic["id"], reflection=response)
            st.success("Saved to your private reflection notebook.")
        st.caption("Your answer is private and available under Learning → Reflection notebook.")
        if topic.get("reflection_example"):
            with st.expander("Example response"):
                st.write(topic["reflection_example"])
    return response


def page_topic(user):
    module_id = st.session_state.get("module_id", "drivers")
    topic_id = st.session_state.get("topic_id")
    if module_id not in MODULES:
        navigate("catalogue")
        return
    module = MODULES[module_id]
    if _is_under_construction(module):
        st.warning("This module is under construction and is not yet available for learners.")
        st.link_button(
            "Subscribe to the MOSAIC newsletter for updates →",
            MOSAIC_NEWSLETTER_URL,
            type="primary",
            width="content",
        )
        return
    topic = topic_by_id(module_id, topic_id) if topic_id else None
    if not topic:
        navigate("module", module_id)
        return

    lesson_flow = _lesson_navigation(module, topic)
    topics = lesson_flow["topics"]
    index = lesson_flow["index"]
    previous_topic = lesson_flow["previous"]
    next_topic = lesson_flow["next"]
    saved = _cached_progress(user["user_id"], module_id).get(topic["id"], {})
    ratio, done, total = module_completion(user["user_id"], module_id)

    back_col, prog_col = st.columns([1, 2.5], vertical_alignment="center")
    with back_col:
        back_phase = "discover" if topic.get("level") == "Understand" else "apply"
        back_label = "← Discover classes" if back_phase == "discover" else "← Apply classes"
        st.button("← Communicate overview" if topic.get("level") == "Convince" else back_label,
                  width="stretch", key=f"lesson-header-back-{module_id}-{topic['id']}",
                  on_click=navigate,
                  args=(("convince" if topic.get("level") == "Convince" else "phase"),
                        module_id, None, None,
                        (None if topic.get("level") == "Convince" else back_phase)),
                  kwargs={"_rerun": False})
    with prog_col:
        st.progress(ratio, text=f"Learning progress · {done}/{total} steps")

    st.markdown(
        f"""
        <div class="m-lesson-hero">
            <div class="m-kicker">{escape('Discover' if topic['level'] == 'Understand' else 'Communicate' if topic['level'] == 'Convince' else topic['level'])} · Class {index + 1} of {len(topics)} · {topic['minutes']} min</div>
            <h1>{escape(topic['title'])}</h1>
            <p>{escape(topic['summary'])}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    summary_embedded = render_theory_story(module_id, topic)

    if topic["id"] == "drivers-as-system":
        render_driver_visual(module)

    if not summary_embedded and topic.get("takeaway"):
        if topic.get("source_system") == "superhuman_docs":
            points = [re.sub(r"^[\s•·*-]+", "", x).strip() for x in topic["takeaway"].splitlines() if x.strip()]
            st.markdown("### Key takeaways")
            for point in points:
                st.markdown(f"- {escape(point)}")
        else:
            st.markdown(
                f"<div class='m-takeaway'><strong>Key idea</strong><br>{escape(topic['takeaway'])}</div>",
                unsafe_allow_html=True,
            )

    render_learning_extras(module_id, topic, include_practice=not summary_embedded)

    reflection = str(saved.get("reflection") or "")
    if topic.get("prompt"):
        reflection = render_context_notebook(user, module_id, topic, saved)

    # The quiz stays BELOW the self-contained reflection/notebook card.
    render_quiz(user, module_id, topic)

    # All linked Resources, Tools and Continue exploring items are placed
    # consistently after cards, reflection and quiz, before lesson navigation.
    _render_linked_page_sections(topic, key=f"lesson_{module_id}_{topic['id']}",
                                  extra_tool_refs=_lesson_tool_references(module_id, topic))
    if topic.get("sources"):
        with st.expander("Additional source notes"):
            for source in topic["sources"]:
                st.write(str(source))

    # One primary action at the actual END of the lesson. Readers encounter
    # its linked Resources, Tools and Continue exploring items BEFORE deciding
    # to complete/continue. Completing also saves the notebook reflection.
    with st.container(key="lesson_footer"):
        dest_route, _ = lesson_flow["destination"]
        if next_topic:
            action_text = "Next lesson →" if saved.get("completed") else "Complete & continue →"
        elif dest_route == "phase":
            action_text = "Apply overview →" if saved.get("completed") else "Complete Discover → Apply overview"
        elif dest_route == "convince":
            action_text = "Communicate overview →" if saved.get("completed") else "Complete & return to Communicate"
        else:
            action_text = "Module overview →" if saved.get("completed") else "Complete & return to module"
        st.markdown("### Ready to continue?")
        if saved.get("completed"):
            st.caption("✓ This lesson is already completed. You can revisit it at any time.")
        st.button(
            action_text,
            key=f"lesson-next-{topic['id']}",
            type="primary", width="stretch",
            on_click=_complete_and_continue,
            args=(user["user_id"], module_id, topic["id"],
                  bool(saved.get("completed")), lesson_flow["destination"]),
        )

        prev_col, overview_col = st.columns(2, gap="medium")
        with prev_col:
            if previous_topic:
                st.button("← Previous lesson", key=f"previous-lesson-{topic['id']}", width="stretch", on_click=navigate, args=("topic", module_id, previous_topic["id"], None, None), kwargs={"_rerun": False})
            else:
                phase_back = "discover" if topic.get("level") == "Understand" else "apply"
                st.button("← Class overview", key=f"lesson-phase-back-{topic['id']}",
                          width="stretch", on_click=navigate,
                          args=(("convince" if topic.get("level") == "Convince" else "phase"),
                                module_id, None, None,
                                (None if topic.get("level") == "Convince" else phase_back)),
                          kwargs={"_rerun": False})
        with overview_col:
            st.button("Module overview", key=f"lesson-module-back-{topic['id']}", width="stretch", on_click=navigate, args=("module", module_id, None, None, None), kwargs={"_rerun": False})
        if saved.get("completed"):
            with st.expander("Lesson completion status"):
                if st.button("Mark as not completed", key=f"incomplete-{module_id}-{topic['id']}"):
                    _save_progress(user["user_id"], module_id, topic["id"], completed=False)
                    st.rerun()


def page_convince(user):
    module_id = st.session_state.get("module_id", "drivers")
    if module_id not in MODULES:
        navigate("catalogue")
        return
    module = MODULES[module_id]
    if _is_under_construction(module):
        st.warning("This module is under construction and is not yet available for learners.")
        st.link_button(
            "Subscribe to the MOSAIC newsletter for updates →",
            MOSAIC_NEWSLETTER_URL,
            type="primary",
            width="content",
        )
        return
    resource_files = _resource_files_for("convince", module_id)
    convince_lessons = [t for t in module.get("topics", []) if t.get("level") == "Convince"]
    hub = module.get("convince") or {}
    linked_convince_files = [x for x in hub.get("linked_files") or []
                             if isinstance(x, dict) and _valid_external_url(str(x.get("url") or ""))]

    hub_title = str(hub.get("title") or f"Communicate resources for {module['short_title']}")
    for old_phase_title in ("Convince", "Share"):
        if hub_title.strip().casefold().startswith(old_phase_title.casefold()):
            hub_title = "Communicate" + hub_title.strip()[len(old_phase_title):]
            break
    hub_intro = str(
        hub.get("intro")
        or "Download the approved briefs, decks, evidence sheets and other files prepared for this learning journey."
    )

    st.button("← Module overview", on_click=navigate, args=("module", module_id, None, None, None), kwargs={"_rerun": False})

    st.markdown(
        f"""
        <div class='m-convince-hero'>
            <div class='m-convince-copy'>
                <div class='m-kicker'>03 · Communicate · {escape(module['short_title'])}</div>
                <h1>{escape(hub_title)}</h1>
                <p>{escape(hub_intro)}</p>
            </div>
            <div class='m-convince-art' aria-hidden='true'></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    convince_intro = str((module.get("block_intros") or {}).get("Convince") or "").strip()
    if convince_intro:
        st.write(convince_intro)
    if convince_lessons:
        st.markdown("### Communicate classes")
        for lesson in convince_lessons:
            with st.container(border=True):
                c_text, c_link = st.columns([4, 1], vertical_alignment="center")
                with c_text:
                    st.markdown(f"<div class='m-card-title'>{escape(lesson['title'])}</div>", unsafe_allow_html=True)
                    st.caption(str(lesson.get("summary") or "Explore how to share methods and supporting evidence."))
                with c_link:
                    st.button("Open class →", key=f"convince-class-{lesson['id']}", width="stretch", on_click=navigate, args=("topic", module_id, lesson["id"], None, None), kwargs={"_rerun": False})

    tab_specs = []
    if hub.get("why") or hub.get("pitch"):
        tab_specs.append("Why it matters")
    if hub.get("examples"):
        tab_specs.append("MOSAIC examples")
    if hub.get("audiences"):
        tab_specs.append("For different audiences")
    if resource_files or linked_convince_files or hub.get("resources"):
        tab_specs.append("Uploaded files")
    tabs = st.tabs(tab_specs) if tab_specs else []
    tab_map = dict(zip(tab_specs, tabs))

    if "Why it matters" in tab_map:
        with tab_map["Why it matters"]:
            st.markdown("### A useful starting point")
            cards = "".join(
                f"<div class='m-evidence-card {escape(item.get('accent','blue'))}'><h3>{escape(item['title'])}</h3><p>{escape(item['text'])}</p></div>"
                for item in hub.get("why", [])
            )
            if cards:
                st.markdown(f"<div class='m-evidence-grid'>{cards}</div>", unsafe_allow_html=True)
            if hub.get("pitch"):
                st.markdown(f"<div class='m-pitch'><div class='label'>30-second starting point</div><p>{escape(hub['pitch'])}</p></div>", unsafe_allow_html=True)
                st.caption("Use this as a starting point and adapt it to your audience and context.")

    if "MOSAIC examples" in tab_map:
        with tab_map["MOSAIC examples"]:
            st.markdown("### What this looked like in MOSAIC")
            st.caption("Short practice examples are easier to reuse in meetings, briefs and presentations than a long theory recap.")
            for item in hub.get("examples", []):
                st.markdown(
                    f"<div class='m-example-card'><div class='m-example-place'>{escape(item['place'])}</div><h3>{escape(item['title'])}</h3><p>{escape(item['text'])}</p><div class='m-example-lesson'>What this helps you say · {escape(item['lesson'])}</div></div>",
                    unsafe_allow_html=True,
                )

    if "For different audiences" in tab_map:
        with tab_map["For different audiences"]:
            audiences = list(hub.get("audiences", {}))
            if audiences:
                choice = st.segmented_control("Who are you sharing this with?", audiences, default=audiences[0], key=f"convince-audience-{module_id}")
                item = hub["audiences"][choice]
                tags = "".join(f"<span>{escape(x)}</span>" for x in item.get("use", []))
                st.markdown(f"<div class='m-audience-card'><div class='m-kicker'>{escape(choice)}</div><h3>{escape(item['headline'])}</h3><p>{escape(item['text'])}</p><div class='m-audience-tags'>{tags}</div></div>", unsafe_allow_html=True)
                st.markdown("#### Adapt for your audience")
                st.text_area("Your message or talking points", key=f"convince-notes-{module_id}-{choice}", placeholder="Adapt the case to the person, organisation or decision in front of you...", height=140)

    if "Uploaded files" in tab_map:
        with tab_map["Uploaded files"]:
            st.markdown("### Files uploaded by your team")
            if resource_files or linked_convince_files:
                for meta in resource_files:
                    with st.container(border=True):
                        left, right = st.columns([3, 1], vertical_alignment="center")
                        with left:
                            st.markdown(f"**{escape(str(meta.get('title') or meta.get('file_name') or 'Resource'))}**")
                            detail = str(meta.get("description") or "").strip()
                            if detail:
                                st.caption(detail)
                            st.caption(
                                f"{meta.get('resource_kind') or 'File'} · {_format_file_size(meta.get('size_bytes'))} · {_safe_resource_filename(meta.get('file_name'))}"
                            )
                        with right:
                            _render_resource_download(
                                meta,
                                key=f"convince-download-{module_id}-{meta['resource_id']}",
                                button_type="primary", label="Download ↓",
                            )
                for idx, entry in enumerate(linked_convince_files):
                    title = str(entry.get("title") or "Document").strip()
                    stored_id = str(entry.get("resource_id") or "")
                    with st.container(border=True, key=f"convince-source-file-{module_id}-{idx}"):
                        description, action = st.columns([3, 1], vertical_alignment="center")
                        with description:
                            st.markdown(f"**{escape(title)}**")
                            st.caption("From Superhuman Docs · " +
                                       ("Stored PDF / document" if stored_id else "External file link"))
                        with action:
                            if stored_id and (_cached_resource_file(stored_id) or {}).get("file_data"):
                                _render_resource_download({"resource_id": stored_id},
                                                          key=f"sh-convince-download-{module_id}-{idx}",
                                                          button_type="primary", label="Download ↓")
                            else:
                                st.link_button("Open file ↗", entry["url"], width="stretch")
            else:
                st.info("No files have been uploaded directly. Related library resources appear below.")
                resources = hub.get("resources", [])
                if resources:
                    st.caption("Planned resources from the original content are shown below until approved files are uploaded.")
                    cards = "".join(
                        f"<div class='m-resource-card'><div class='m-resource-type'>{escape(item['type'])}</div><h3>{escape(item['title'])}</h3><p>{escape(item['description'])}</p><div class='m-resource-status'>{escape(item['status'])}</div></div>"
                        for item in resources
                    )
                    st.markdown(f"<div class='m-resource-grid'>{cards}</div>", unsafe_allow_html=True)
            source_url = hub.get("author_source_url")
            if source_url:
                st.link_button("Open Communicate source page in Superhuman Docs ↗", source_url)

    _render_linked_page_sections(_page_links_for_share(module), key=f"share_{module_id}")
    st.divider()
    left, right = st.columns(2)
    with left:
        st.button("Back to learning path", key=f"convince-back-{module_id}", width="stretch", on_click=navigate, args=("module", module_id, None, None, None), kwargs={"_rerun": False})
    with right:
        st.button("Share an experience with the community →", key=f"convince-community-{module_id}",
                  type="primary", width="stretch", on_click=_navigate_with_context,
                  args=("community",), kwargs={"state_updates": {"community_module": module_id}})


def page_results(user, *, embedded: bool = False):
    if embedded:
        st.markdown(
            "<div class='m-section-title'><h2>Results & sharing</h2><p>Review one module's learning record and create a public summary without exposing private reflections.</p></div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown("<div class='m-kicker'>Progress</div>", unsafe_allow_html=True)
        st.title("Results & sharing")
    available_ids = [mid for mid, m in MODULES.items() if m["status"] == "Available"]
    if not available_ids:
        st.info("No published learning modules are currently available for results.")
        return
    module_id = st.selectbox(
        "Module",
        available_ids,
        format_func=lambda mid: MODULES[mid]["short_title"],
        key="results-module-select",
    )
    module = MODULES[module_id]
    ratio, done, total = module_completion(user["user_id"], module_id)
    progress = _cached_progress(user["user_id"], module_id)
    quizzes = _cached_quiz_results(user["user_id"], module_id)

    quiz_topic_ids = {t["id"] for t in learning_topics(module) if t.get("quiz")}
    quiz_count = len(quiz_topic_ids)
    quiz_correct = sum(
        1
        for topic_id, result in quizzes.items()
        if topic_id in quiz_topic_ids and result["is_correct"]
    )

    a, b, c = st.columns(3)
    with a:
        st.markdown(f"<div class='m-stat'><div class='value'>{round(ratio * 100)}%</div><div class='label'>Module progress</div></div>", unsafe_allow_html=True)
    with b:
        st.markdown(f"<div class='m-stat'><div class='value'>{done}/{total}</div><div class='label'>Learning steps completed</div></div>", unsafe_allow_html=True)
    with c:
        quiz_text = f"{quiz_correct}/{quiz_count}" if quiz_count else "—"
        st.markdown(f"<div class='m-stat'><div class='value'>{quiz_text}</div><div class='label'>Quick checks correct</div></div>", unsafe_allow_html=True)

    st.markdown("<div class='m-section-title'><h2>Learning record</h2><p>Your results stay here; your private reflections are gathered in the Reflection notebook on this Learning page.</p></div>", unsafe_allow_html=True)
    for topic in learning_topics(module):
        p = progress.get(topic["id"], {})
        status = "✓ Completed" if p.get("completed") else "Not completed"
        st.markdown(f"**{topic['level']} · {topic['title']}**  \n{status}")
    if st.button("Open reflection notebook →", key=f"results-profile-{module_id}"):
        st.session_state["learning-hub-section"] = "Reflection notebook"
        st.rerun()

    st.markdown("<div class='m-section-title'><h2>Share your result</h2><p>Create a public summary without exposing private reflections.</p></div>", unsafe_allow_html=True)
    snapshot = {
        "learner": user["name"],
        "module": module["title"],
        "progress_percent": round(ratio * 100),
        "topics_completed": done,
        "topics_total": total,
        "knowledge_checks_correct": quiz_correct,
        "knowledge_checks_total": quiz_count,
    }
    st.markdown(
        f"""
        <div class="m-share-card">
            <div class="m-kicker">MOSAIC Learn · result summary</div>
            <h3>{escape(module['short_title'])}</h3>
            <p><strong>{escape(user['name'])}</strong> has completed <strong>{done} of {total}</strong> learning steps ({round(ratio * 100)}%).</p>
            <p class="m-muted m-small">Quick checks: {quiz_correct}/{quiz_count if quiz_count else '—'}. Private reflections are not included.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    share_col, community_col = st.columns(2)
    with share_col:
        if st.button("Generate public result link", key=f"share-{module_id}", type="primary", width="stretch"):
            token = create_share(user["user_id"], module_id, snapshot)
            base_url = _secret("PUBLIC_APP_URL", "")
            share_link = f"{base_url.rstrip('/')}?share={quote(token)}" if base_url else f"?share={quote(token)}"
            st.session_state.last_share_link = share_link
    with community_col:
        st.button("Share a reflection with the community →", key=f"community-from-results-{module_id}",
                  width="stretch", on_click=_navigate_with_context,
                  args=("community",), kwargs={"state_updates": {"community_module": module_id}})
    if st.session_state.get("last_share_link"):
        st.code(st.session_state.last_share_link)
        if not _secret("PUBLIC_APP_URL", ""):
            st.caption("Set PUBLIC_APP_URL in secrets.toml to generate the full deployment URL.")


def page_community(user):
    user_id = user["user_id"]
    posts = _cached_community_posts(40)
    post_ids = tuple(int(post["post_id"]) for post in posts)
    activity = _cached_community_activity(post_ids, user_id)
    unread_on_entry = _cached_unread_community_notifications(user_id)
    notifications = _cached_community_notifications(user_id, 30)

    mycelium_state = _cached_mycelium_state(user_id)

    post_count = len(posts)
    reflection_label = "reflection" if post_count == 1 else "reflections"
    mycelium_is_member = bool(mycelium_state.get("is_member"))
    mycelium_member_count = len(mycelium_state.get("members", [])) if mycelium_is_member else 0
    mycelium_request_count = len(mycelium_state.get("incoming", [])) if mycelium_is_member else 0
    mycelium_member_value = str(mycelium_member_count) if mycelium_is_member else "—"
    mycelium_member_label = "Mycelium members" if mycelium_is_member else "Mycelium network"

    st.markdown(
        f"""
        <div class="m-community-hero">
            <div class="m-community-hero-grid">
                <div class="m-community-hero-copy">
                    <div class="m-kicker">Community · the MOSAIC mycelium</div>
                    <h1>Learn with other people working on land-use change</h1>
                    <p>Join the discussion, find people in the Mycelium, or check updates from your community activity.</p>
                </div>
                <div class="m-community-snapshot">
                    <div class="label">Community at a glance</div>
                    <div class="m-community-snapshot-grid">
                        <div class="m-community-snapshot-item"><strong>{post_count}</strong><span>{reflection_label}</span></div>
                        <div class="m-community-snapshot-item"><strong>{mycelium_member_value}</strong><span>{mycelium_member_label}</span></div>
                        <div class="m-community-snapshot-item"><strong>{unread_on_entry}</strong><span>unread updates</span></div>
                    </div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    valid_community_sections = {"explore", "mycelium", "notifications"}
    if st.session_state.get("community-section") not in valid_community_sections:
        st.session_state["community-section"] = "explore"
    section = st.session_state.get("community-section", "explore")

    section_to_label = {
        "explore": "Discussion",
        "mycelium": "Our mycelium",
        "notifications": "Notifications",
    }
    label_to_section = {label: key for key, label in section_to_label.items()}
    with st.container(key="community_navigation"):
        selected_space = st.segmented_control(
            "Community space",
            list(label_to_section),
            default=section_to_label[section],
            key="community-space-picker",
            label_visibility="collapsed",
            width="stretch",
        ) or section_to_label[section]
        section = label_to_section[selected_space]
        st.session_state["community-section"] = section
        status_bits = [f"{post_count} {reflection_label}"]
        if mycelium_is_member:
            status_bits.append(f"{mycelium_request_count} connection request{'s' if mycelium_request_count != 1 else ''}")
        else:
            status_bits.append("Mycelium is optional")
        status_bits.append(f"{unread_on_entry} unread update{'s' if unread_on_entry != 1 else ''}")
        st.caption("  ·  ".join(status_bits))

    def render_share_perspective() -> None:
        available_ids = [
            module_id
            for module_id, module in MODULES.items()
            if module["status"] == "Available"
        ]
        if not available_ids:
            return

        default_id = (
            st.session_state.get("community_module")
            if st.session_state.get("community_module") in available_ids
            else available_ids[0]
        )
        default_index = available_ids.index(default_id)

        with st.expander("＋ Share a perspective", expanded=False):
            st.caption("Add a short reflection, field observation or question. It will be visible to other signed-in MOSAIC learners.")
            context_left, context_right = st.columns(2, gap="medium")
            with context_left:
                module_id = st.selectbox(
                    "Related module",
                    available_ids,
                    index=default_index,
                    format_func=lambda mid: MODULES[mid]["short_title"],
                    key="community-post-module",
                )
            topic_options = [None] + [
                topic["id"] for topic in learning_topics(MODULES[module_id])
            ]
            with context_right:
                topic_id = st.selectbox(
                    "Related lesson (optional)",
                    topic_options,
                    format_func=lambda tid: (
                        "Whole module / general"
                        if tid is None
                        else topic_by_id(module_id, tid)["title"]
                    ),
                    key="community-post-topic",
                )
            with st.form("community-post-form", border=False):
                perspective_text = st.text_area(
                    "What would you like to share?",
                    placeholder="A result you tried, something that surprised you, a question for others, or a short field reflection...",
                    height=120,
                    max_chars=1200,
                )
                submitted = st.form_submit_button("Publish to community", type="primary")
        if submitted:
            cleaned = perspective_text.strip()
            if not cleaned:
                st.error("Write something before publishing.")
            else:
                create_community_post(
                    user_id,
                    user["name"],
                    cleaned,
                    module_id,
                    topic_id,
                )
                _cached_community_posts.clear()
                st.session_state.pop("community_module", None)
                st.success("Published to the MOSAIC learning community.")
                st.rerun()

    reaction_choices = [
        ("like", "👍", "Like"),
        ("insightful", "💡", "Insightful"),
        ("support", "💚", "Support"),
    ]

    if section == "explore":
        st.markdown(
            """
            <div class="m-community-section-lead compact">
                <div>
                    <div class="m-kicker">Discussion</div>
                    <h2>Reflections from the community</h2>
                    <p>Compare contexts, react to an idea or open the comments when you want to continue the conversation.</p>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        render_share_perspective()
        if not posts:
            st.info(
                "No reflections have been shared yet. Start the conversation with "
                "a field observation, question or lesson learned."
            )
        for post in posts:
            post_id = int(post["post_id"])
            module = MODULES.get(post.get("module_id"))
            module_label = module["short_title"] if module else "General reflection"
            topic = (
                topic_by_id(post.get("module_id"), post.get("topic_id"))
                if post.get("module_id") in MODULES and post.get("topic_id")
                else None
            )
            context = module_label + (f" · {topic['title']}" if topic else "")
            date_text = str(post.get("created_at", ""))[:10]
            reaction_counts = activity["reaction_counts"].get(post_id, {})
            viewer_reaction = activity["viewer_reactions"].get(post_id)
            comments = activity["comments"].get(post_id, [])

            with st.container(key=f"community_post_{post_id}"):
                st.markdown(
                    f"""
                    <article class="m-post" id="community-post-{post_id}">
                        <div class="m-post-meta">
                            <strong>{escape(post['author_name'])}</strong>
                            · {escape(context)} · {escape(date_text)}
                        </div>
                        <p>{escape(post['post_text'])}</p>
                    </article>
                    """,
                    unsafe_allow_html=True,
                )

                reaction_cols = st.columns([1, 1, 1, 2.2])
                for reaction_col, (reaction_key, icon, label) in zip(
                    reaction_cols[:3], reaction_choices
                ):
                    with reaction_col:
                        count = int(reaction_counts.get(reaction_key, 0))
                        if st.button(
                            f"{icon} {label} · {count}",
                            key=f"react-{reaction_key}-{post_id}",
                            type="primary" if viewer_reaction == reaction_key else "secondary",
                            width="stretch",
                        ):
                            toggle_community_reaction(
                                post_id,
                                user_id,
                                user["name"],
                                reaction_key,
                            )
                            _clear_community_interaction_caches()
                            st.rerun()
                with reaction_cols[3]:
                    total_reactions = sum(
                        int(value) for value in reaction_counts.values()
                    )
                    st.markdown(
                        f"<div class='m-reaction-summary'>{total_reactions} reactions · {len(comments)} comments</div>",
                        unsafe_allow_html=True,
                    )

                with st.expander(f"Comments ({len(comments)})"):
                    if comments:
                        for comment in comments:
                            comment_date = str(comment.get("created_at", ""))[:10]
                            st.markdown(
                                f"""
                                <div class="m-comment">
                                    <div class="m-comment-meta">
                                        <strong>{escape(comment['author_name'])}</strong>
                                        · {escape(comment_date)}
                                    </div>
                                    <p>{escape(comment['comment_text'])}</p>
                                </div>
                                """,
                                unsafe_allow_html=True,
                            )
                    else:
                        st.caption("No comments yet. Add the first response.")

                    with st.form(f"community-comment-form-{post_id}", border=False):
                        comment_text = st.text_input(
                            "Add a comment",
                            placeholder="Respond with a question, comparison or practical suggestion…",
                            max_chars=600,
                            label_visibility="collapsed",
                        )
                        comment_submitted = st.form_submit_button(
                            "Comment",
                            width="stretch",
                        )
                    if comment_submitted:
                        cleaned_comment = comment_text.strip()
                        if not cleaned_comment:
                            st.error("Write a comment before submitting.")
                        else:
                            create_community_comment(
                                post_id,
                                user_id,
                                user["name"],
                                cleaned_comment,
                            )
                            _clear_community_interaction_caches()
                            st.rerun()

    elif section == "mycelium":
        st.markdown(
            """
            <div class="m-community-section-lead">
                <div>
                    <div class="m-kicker">Our mycelium</div>
                    <h2>Grow your learner network</h2>
                    <p>Explore who is here, connect with peers, and keep invitations private until both people choose to connect.</p>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        state = mycelium_state
        if not state.get("is_member"):
            st.markdown(
                """
                <div class="m-mycelium-optin">
                    <div class="m-kicker">Optional network</div>
                    <h3>Join Our mycelium</h3>
                    <p>Join the learner network to discover people working in other places and contexts. Your name, organisation and country/region become visible to other Mycelium members. Every connection still requires an invitation and acceptance, and your email is only shared when you explicitly choose to share it.</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button(
                "Join Our mycelium",
                type="primary",
                key="mycelium-join",
            ):
                join_mycelium(user_id)
                _clear_community_interaction_caches()
                st.rerun()
        else:
            members = state.get("members", [])
            incoming = state.get("incoming", [])
            outgoing = state.get("outgoing", [])
            connected = state.get("connected", [])
            blocked = set(state.get("blocked_user_ids", []))

            pending_edges = [
                {"source": user_id, "target": row["recipient_user_id"]}
                for row in outgoing
            ] + [
                {"source": row["requester_user_id"], "target": user_id}
                for row in incoming
            ]

            network_col, sidebar_col = st.columns([2.15, 1], gap="large")

            with network_col:
                st.markdown(
                    """
                    <div class="m-mycelium-map-heading">
                        <strong>Explore the network</strong>
                        <span>Drag cards to rearrange the map, zoom in or out, and drag the + handle on your card onto another learner to invite them.</span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                network_event = _mycelium_network(
                    members=members,
                    connections=state.get("connections", []),
                    pending=pending_edges,
                    current_user_id=user_id,
                    blocked_user_ids=state.get("blocked_user_ids", []),
                    default=None,
                    key="mycelium-network",
                )

            with sidebar_col:
                st.markdown(
                    f"""
                    <div class="m-mycelium-intro">
                        <div class="m-kicker">Your network</div>
                        <h3>Make a connection</h3>
                        <p>The map shows the wider Mycelium. Accepted links are visible in the network; invitations stay private to the two learners involved.</p>
                        <div class="m-mycelium-metrics">
                            <div class="m-mycelium-metric"><strong>{len(members)}</strong><span>members</span></div>
                            <div class="m-mycelium-metric"><strong>{len(connected)}</strong><span>connections</span></div>
                            <div class="m-mycelium-metric"><strong>{len(incoming)}</strong><span>requests</span></div>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                if incoming:
                    with st.container(border=True, key="mycelium_sidebar_requests"):
                        st.markdown(
                            '<div class="m-mycelium-section-label">New connection requests</div>',
                            unsafe_allow_html=True,
                        )
                        for invitation in incoming:
                            connection_id = int(invitation["connection_id"])
                            invitation_name = invitation.get("requester_name") or "Learner"
                            invitation_context = " · ".join(
                                value
                                for value in (
                                    invitation.get("organisation") or "",
                                    invitation.get("country") or "",
                                )
                                if value
                            )
                            st.markdown(
                                f"""
                                <div class="m-mycelium-person">
                                    <strong>{escape(invitation_name)}</strong>
                                    <span>{escape(invitation_context) if invitation_context else 'MOSAIC learner'}</span>
                                </div>
                                """,
                                unsafe_allow_html=True,
                            )
                            if invitation.get("requester_email"):
                                st.caption(
                                    f"Shared with this request: {invitation['requester_email']}"
                                )
                            accept_col, decline_col = st.columns(2)
                            with accept_col:
                                if st.button(
                                    "Accept",
                                    key=f"mycelium-accept-{connection_id}",
                                    type="primary",
                                    width="stretch",
                                ):
                                    try:
                                        respond_mycelium_connection(
                                            connection_id,
                                            user_id,
                                            user["name"],
                                            accept=True,
                                        )
                                    except (ValueError, PermissionError) as exc:
                                        st.error(str(exc))
                                    else:
                                        _clear_community_interaction_caches()
                                        st.rerun()
                            with decline_col:
                                if st.button(
                                    "Decline",
                                    key=f"mycelium-decline-{connection_id}",
                                    width="stretch",
                                ):
                                    try:
                                        respond_mycelium_connection(
                                            connection_id,
                                            user_id,
                                            user["name"],
                                            accept=False,
                                        )
                                    except (ValueError, PermissionError) as exc:
                                        st.error(str(exc))
                                    else:
                                        _clear_community_interaction_caches()
                                        st.rerun()

                eligible_members = [
                    member
                    for member in members
                    if member["user_id"] not in blocked
                ]
                with st.container(border=True, key="mycelium_sidebar_invite"):
                    st.markdown(
                        '<div class="m-mycelium-section-label">Invite a learner</div>',
                        unsafe_allow_html=True,
                    )
                    if not eligible_members:
                        st.caption(
                            "Everyone currently visible is already connected with you or has a pending request."
                        )
                    else:
                        member_by_id = {
                            member["user_id"]: member for member in eligible_members
                        }
                        with st.form("mycelium-accessible-request", border=False):
                            target_user_id = st.selectbox(
                                "Learner",
                                list(member_by_id),
                                format_func=lambda uid: member_by_id[uid].get("name")
                                or "Learner",
                            )
                            share_email = st.checkbox(
                                "Share my email with this learner."
                            )
                            send_request = st.form_submit_button(
                                "Send connection request",
                                type="primary",
                                width="stretch",
                            )
                        if send_request:
                            try:
                                request_mycelium_connection(
                                    user_id,
                                    user["name"],
                                    user.get("email", ""),
                                    target_user_id,
                                    share_email=share_email,
                                )
                            except (ValueError, PermissionError) as exc:
                                st.error(str(exc))
                            else:
                                _clear_community_interaction_caches()
                                st.rerun()

                with st.container(border=True, key="mycelium_sidebar_network"):
                    st.markdown(
                        '<div class="m-mycelium-section-label">Connections</div>',
                        unsafe_allow_html=True,
                    )
                    if not connected:
                        st.caption("No accepted connections yet.")
                    for connection in connected:
                        context = " · ".join(
                            value
                            for value in (
                                connection.get("organisation") or "",
                                connection.get("country") or "",
                            )
                            if value
                        )
                        email_note = (
                            f" · {connection['shared_email']}"
                            if connection.get("shared_email")
                            else ""
                        )
                        st.markdown(
                            f"""
                            <div class="m-mycelium-person">
                                <strong>{escape(connection.get('name') or 'Learner')}</strong>
                                <span>{escape(context) if context else 'MOSAIC learner'}{escape(email_note)}</span>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )

                    if outgoing:
                        st.markdown(
                            '<div class="m-mycelium-section-label" style="margin-top:.8rem">Waiting for a response</div>',
                            unsafe_allow_html=True,
                        )
                        for request in outgoing:
                            st.markdown(
                                f"""
                                <div class="m-mycelium-person">
                                    <strong>{escape(request.get('recipient_name') or 'Learner')}</strong>
                                    <span>Request sent {escape(str(request.get('created_at') or '')[:10])}</span>
                                </div>
                                """,
                                unsafe_allow_html=True,
                            )

                with st.expander("Membership & privacy"):
                    st.write(
                        "Leaving removes you from the Mycelium directory and removes your Mycelium connections and pending invitations. It does not delete your MOSAIC Learn account, learning progress or Community posts."
                    )
                    confirm_leave = st.checkbox(
                        "I understand that leaving removes my Mycelium connections.",
                        key="mycelium-leave-confirm",
                    )
                    if st.button(
                        "Leave Our mycelium",
                        key="mycelium-leave",
                        disabled=not confirm_leave,
                    ):
                        leave_mycelium(user_id)
                        _clear_community_interaction_caches()
                        st.rerun()

            if isinstance(network_event, dict) and network_event.get("type") == "request":
                nonce = str(network_event.get("nonce") or "")
                last_nonce_key = "mycelium-last-component-event"
                if nonce and st.session_state.get(last_nonce_key) != nonce:
                    st.session_state[last_nonce_key] = nonce
                    try:
                        request_mycelium_connection(
                            user_id,
                            user["name"],
                            user.get("email", ""),
                            str(network_event.get("target_user_id") or ""),
                            share_email=bool(network_event.get("share_email")),
                        )
                    except (ValueError, PermissionError) as exc:
                        st.error(str(exc))
                    else:
                        _clear_community_interaction_caches()
                        st.rerun()

    elif section == "notifications":
        st.markdown(
            """
            <div class="m-community-section-lead">
                <div>
                    <div class="m-kicker">Notifications</div>
                    <h2>Your community activity</h2>
                    <p>Replies, reactions, and Mycelium invitations appear here so you can quickly see what needs your attention.</p>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if not notifications:
            st.info(
                "No interactions yet. Reactions, comments and Mycelium invitations will appear here."
            )
        for notification in notifications:
            is_unread = not str(notification.get("read_at") or "").strip()
            event_type = notification.get("event_type")
            detail = notification.get("event_detail")
            notification_date = str(notification.get("created_at", ""))[:10]
            notification_class = (
                "m-notification unread" if is_unread else "m-notification"
            )

            if event_type == "mycelium_request":
                st.markdown(
                    f"""
                    <div class="{notification_class}">
                        <p><strong>{escape(notification['actor_name'])}</strong> sent you a Mycelium connection request.</p>
                        <div class="meta">{escape(notification_date)} · Open <strong>Our mycelium</strong> to respond.</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                continue
            if event_type == "mycelium_accepted":
                st.markdown(
                    f"""
                    <div class="{notification_class}">
                        <p><strong>{escape(notification['actor_name'])}</strong> accepted your Mycelium connection request.</p>
                        <div class="meta">{escape(notification_date)}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                continue

            if event_type == "comment":
                action_text = "commented on your reflection"
            else:
                reaction_icons = {
                    "like": "👍",
                    "insightful": "💡",
                    "support": "💚",
                }
                reaction_icon = reaction_icons.get(detail, "•")
                action_text = f"reacted {reaction_icon} to your reflection"
            post_text = str(notification.get("post_text") or "Reflection unavailable")
            snippet = (
                post_text
                if len(post_text) <= 135
                else post_text[:132].rstrip() + "…"
            )
            post_id = notification.get("post_id")
            if post_id is None:
                continue
            st.markdown(
                f"""
                <div class="{notification_class}">
                    <p><strong>{escape(notification['actor_name'])}</strong> {escape(action_text)}.</p>
                    <a href="#community-post-{int(post_id)}">
                        {escape(snippet)}
                    </a>
                    <div class="meta">{escape(notification_date)}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        # Crucial difference from current main: merely browsing Community/Mycelium
        # does not acknowledge invitations. Opening Notifications does.
        if unread_on_entry:
            mark_community_notifications_read(user_id)
            _cached_unread_community_notifications.clear()
            _cached_community_notifications.clear()
            st.rerun()


def page_profile(user):
    # ensure_profile already loaded these fields; avoid another transatlantic
    # round trip simply to render this page.
    stored = user
    st.markdown("<div class='m-kicker'>Account</div>", unsafe_allow_html=True)
    st.title("My profile")

    top_a, top_b = st.columns([1.2, 1], gap="large")
    with top_a:
        st.markdown(f"### {escape(stored.get('name') or user.get('name', 'Learner'))}")
        if stored.get("email"):
            st.caption(stored.get("email", ""))
        if stored.get("organisation"):
            st.write(f"**Organisation:** {stored['organisation']}")
        if stored.get("country"):
            st.write(f"**Country / region:** {stored['country']}")
    with top_b:
        backend_label = "Persistent PostgreSQL" if database_backend() == "postgres" else "Local SQLite preview"
        st.markdown(
            f"<div class='m-keyidea'><strong>Learning record</strong><br><span class='m-small'>{escape(backend_label)}</span></div>",
            unsafe_allow_html=True,
        )

    st.markdown("<div class='m-section-title'><h2>Profile details</h2><p>Used to tailor examples and module recommendations. Identity details come from your sign-in provider.</p></div>", unsafe_allow_html=True)
    available_modules = [
        (module_id, module)
        for module_id, module in MODULES.items()
        if module.get("status") == "Available"
    ]
    labels = [module["short_title"] for _, module in available_modules]
    label_to_id = {module["short_title"]: module_id for module_id, module in available_modules}
    id_to_label = {module_id: module["short_title"] for module_id, module in available_modules}
    current_interest_labels = [id_to_label[mid] for mid in stored.get("interests", []) if mid in id_to_label]
    role_options = list(ROLE_CALLOUTS)
    current_role = stored.get("role") if stored.get("role") in role_options else role_options[0]

    with st.form("edit-profile", border=True):
        role = st.selectbox("I mainly work in", role_options, index=role_options.index(current_role))
        organisation = st.text_input("Organisation", value=stored.get("organisation", ""))
        country = st.text_input("Country or region", value=stored.get("country", ""))
        interests = st.multiselect("Learning interests", labels, default=current_interest_labels)
        save_profile = st.form_submit_button("Save profile", type="primary")
    if save_profile:
        _save_profile(
            user["user_id"],
            role=role,
            organisation=organisation,
            country=country,
            interests=[label_to_id[label] for label in interests],
            profile_complete=True,
        )
        if user.get("demo"):
            st.session_state.demo_user["role"] = role
        st.success("Profile updated")
        st.rerun()

    st.markdown(
        "<div class='m-section-title'><h2>Privacy & consent</h2><p>See which privacy-notice version is linked to this account.</p></div>",
        unsafe_allow_html=True,
    )
    privacy_col, notice_col = st.columns([1.6, 1])
    with privacy_col:
        accepted_at = str(stored.get("privacy_accepted_at") or "")[:10]
        accepted_text = accepted_at or "Not recorded"
        st.markdown(
            f"**Accepted version:** {escape(stored.get('privacy_policy_version') or 'Not recorded')}  \n"
            f"**Accepted on:** {escape(accepted_text)}"
        )
    with notice_col:
        st.button("Read privacy notice →", width="stretch", on_click=navigate, args=("privacy", None, None, None, None), kwargs={"_rerun": False})

    st.markdown(
        "<div class='m-section-title'><h2>Learning & reflections</h2><p>Your progress, results and reflection notebook now live together on the Learning page.</p></div>",
        unsafe_allow_html=True,
    )
    st.button("Open Learning →", key="profile-open-learning", type="primary",
              on_click=_navigate_with_context, args=("catalogue",),
              kwargs={"state_updates": {"learning-hub-section": "My learning"}})

    st.markdown(
        "<div class='m-section-title'><h2>Delete my account</h2><p>Permanently remove this profile and its linked MOSAIC Learn data.</p></div>",
        unsafe_allow_html=True,
    )
    with st.expander("Delete account and learning data"):
        st.warning(
            "This permanently deletes your profile, progress, quick-check results, private reflections, "
            "Community posts, public share links and privacy-consent history. It does not delete your Google account."
        )
        deletion_understood = st.checkbox(
            "I understand that this action cannot be undone.",
            key="delete-account-understood",
        )
        deletion_phrase = st.text_input(
            "Type DELETE to confirm",
            key="delete-account-confirmation",
        )
        if st.button(
            "Permanently delete my account",
            key="delete-account",
            type="primary",
            disabled=not deletion_understood or deletion_phrase.strip() != "DELETE",
        ):
            _delete_account_data(user["user_id"])
            if user.get("demo"):
                st.session_state.demo_user = None
                navigate("home")
            else:
                _write_route_query("home")
                st.logout()

    st.divider()
    if user.get("demo"):
        st.caption("Local preview mode: configure Streamlit OIDC to test production authentication.")
        st.button("Leave local preview", on_click=_leave_local_preview)
    else:
        if st.button("Sign out"):
            _write_route_query("home")
            st.logout()


def _rich_text_editor(label: str, initial_html: str, *, key: str) -> str:
    """Render Quill when installed, with a safe HTML textarea fallback."""
    st.markdown(f"**{escape(label)}**")
    if st_quill is not None:
        value = st_quill(
            value=initial_html,
            html=True,
            key=key,
            placeholder="Write the learner-facing text here…",
        )
        return str(value if value is not None else initial_html)

    st.warning(
        "The visual editor is not installed in this environment. You can still edit "
        "safe HTML below; install requirements.txt to enable the formatting toolbar."
    )
    return st.text_area(label, value=initial_html, height=220, key=key)


def _content_studio_flash(message: str) -> None:
    st.session_state["content-studio-flash"] = message


def _content_studio_save_module(module_id: str, payload: dict, sort_order: int, user_id: str) -> None:
    save_cms_module_draft(module_id, _normalise_module_payload(module_id, payload), sort_order, user_id)
    _clear_content_studio_caches()


def _content_studio_publish_module(module_id: str, payload: dict, sort_order: int, user_id: str) -> None:
    publish_cms_module(module_id, _normalise_module_payload(module_id, payload), sort_order, user_id)
    _clear_content_studio_caches()


def _content_studio_save_lesson(module_id: str, lesson_id: str, payload: dict, sort_order: int, user_id: str) -> None:
    normalised = _normalise_lesson_payload(lesson_id, payload)
    save_cms_lesson_draft(module_id, lesson_id, normalised, sort_order, user_id)
    _clear_content_studio_caches()


def _content_studio_publish_lesson(module_id: str, lesson_id: str, payload: dict, sort_order: int, user_id: str) -> None:
    normalised = _normalise_lesson_payload(lesson_id, payload)
    publish_cms_lesson(module_id, lesson_id, normalised, sort_order, user_id)
    _clear_content_studio_caches()


def _content_studio_save_tool(tool_id: str, payload: dict, sort_order: int, user_id: str) -> None:
    save_cms_tool_draft(tool_id, _normalise_tool_payload(tool_id, payload), sort_order, user_id)
    _clear_content_studio_caches()


def _content_studio_publish_tool(tool_id: str, payload: dict, sort_order: int, user_id: str) -> None:
    publish_cms_tool(tool_id, _normalise_tool_payload(tool_id, payload), sort_order, user_id)
    _clear_content_studio_caches()


def _render_content_studio_modules(user: dict, snapshot: dict[str, dict]) -> None:
    is_admin = is_administrator(user)
    st.markdown("### Modules")
    st.caption(
        "Editors can change existing module metadata and save drafts. Administrators can also create, publish, archive and restore modules. "
        "Archiving removes a module from learner pages without deleting learner progress."
    )

    module_ids = list(snapshot)
    if module_ids:
        module_id = st.selectbox(
            "Module to edit",
            module_ids,
            format_func=lambda value: (
                f"{snapshot[value]['short_title']} · archived"
                if snapshot[value].get("_cms_archived")
                else snapshot[value]["short_title"]
            ),
            key="studio-module-select",
        )
        module = snapshot[module_id]
        archived = bool(module.get("_cms_archived"))
        status_bits = []
        if module.get("_cms_has_draft"):
            status_bits.append("draft saved")
        if module.get("_cms_has_published"):
            status_bits.append("published/base version available")
        if archived:
            status_bits.append("archived")
        st.markdown(
            f"<div class='m-admin-note'><strong>{escape(module['short_title'])}</strong>"
            f"<p>{escape(' · '.join(status_bits) or 'content.py base version')}</p></div>",
            unsafe_allow_html=True,
        )

        with st.form(f"studio-module-form-{module_id}"):
            a, b = st.columns([2, 1])
            with a:
                title = st.text_input("Full title", value=module.get("title", ""), key=f"studio-module-title-{module_id}")
                short_title = st.text_input("Short title", value=module.get("short_title", ""), key=f"studio-module-short-{module_id}")
            with b:
                track_options = ["Learning", "Community", "Empowerment"]
                if module.get("track") not in track_options:
                    track_options.append(str(module.get("track") or "Learning"))
                track = st.selectbox(
                    "Color",
                    track_options,
                    index=track_options.index(module.get("track") or "Learning"),
                    format_func=lambda value: {"Learning": "Blue", "Community": "Green", "Empowerment": "Ochre"}.get(value, value),
                    help="This only controls the module's visual color. The legacy value is kept internally for compatibility.",
                    key=f"studio-module-track-{module_id}",
                )
                track_icon = st.text_input("Module icon", value=module.get("track_icon", "◎"), max_chars=4, key=f"studio-module-icon-{module_id}")
            description = st.text_area("Description", value=module.get("description", ""), height=100, key=f"studio-module-description-{module_id}")
            c, d, e = st.columns(3)
            with c:
                estimated_minutes = st.number_input(
                    "Estimated minutes",
                    min_value=0,
                    max_value=5000,
                    value=int(module.get("estimated_minutes") or 0),
                    step=1,
                    key=f"studio-module-minutes-{module_id}",
                )
            with d:
                status_options = ["Available", "Under construction", "Coming soon"]
                if module.get("status") not in status_options:
                    status_options.append(str(module.get("status") or "Available"))
                status = st.selectbox(
                    "Learner status",
                    status_options,
                    index=status_options.index(module.get("status") or "Available"),
                    key=f"studio-module-status-{module_id}",
                )
            with e:
                sort_order = st.number_input(
                    "Sort order",
                    min_value=0,
                    max_value=10000,
                    value=int(module.get("_cms_sort_order") or 0),
                    step=10,
                    key=f"studio-module-sort-{module_id}",
                )
            eyebrow = st.text_input("Eyebrow", value=module.get("eyebrow", "Learning journey"), key=f"studio-module-eyebrow-{module_id}")
            source_note = st.text_area("Source note", value=module.get("source_note", ""), height=90, key=f"studio-module-source-{module_id}")
            learning_outcomes = st.text_area(
                "Learning outcomes · one per line",
                value="\n".join(module.get("learning_outcomes") or []),
                height=130,
                key=f"studio-module-outcomes-{module_id}",
            )
            payload = _module_content_payload(module_id, module)
            payload.update(
                {
                    "title": title.strip(),
                    "short_title": short_title.strip(),
                    "track": track,
                    "track_icon": track_icon.strip() or "◎",
                    "description": description.strip(),
                    "estimated_minutes": int(estimated_minutes),
                    "status": status,
                    "eyebrow": eyebrow.strip(),
                    "source_note": source_note.strip(),
                    "learning_outcomes": [line.strip() for line in learning_outcomes.splitlines() if line.strip()],
                }
            )
            save_col, publish_col = st.columns(2)
            with save_col:
                save_pressed = st.form_submit_button("Save module draft", width="stretch")
            with publish_col:
                publish_pressed = st.form_submit_button(
                    "Publish module",
                    type="primary",
                    width="stretch",
                    disabled=not is_admin or archived,
                )
        if save_pressed:
            _content_studio_save_module(module_id, payload, int(sort_order), user["user_id"])
            _content_studio_flash("Module draft saved. Learners still see the published version.")
            st.rerun()
        if publish_pressed and is_admin:
            _content_studio_publish_module(module_id, payload, int(sort_order), user["user_id"])
            _content_studio_flash("Module published.")
            st.rerun()

        if is_admin:
            with st.expander("Archive / restore module"):
                if archived:
                    st.info("Restoring makes the last published version available again. A draft-only new module still needs to be published.")
                    if st.button("Restore module", key=f"restore-module-{module_id}", type="primary"):
                        set_cms_module_archived(
                            module_id,
                            False,
                            user["user_id"],
                            sort_order=int(module.get("_cms_sort_order") or 0),
                        )
                        _clear_content_studio_caches()
                        _content_studio_flash("Module restored.")
                        st.rerun()
                else:
                    confirm = st.checkbox(
                        "I understand that this removes the module from learner-facing pages but keeps progress and content records.",
                        key=f"confirm-archive-module-{module_id}",
                    )
                    last_live_module = module_id in MODULES and len(MODULES) <= 1
                    if last_live_module:
                        st.caption("At least one learner-facing module must remain. Publish another module before archiving this one.")
                    if st.button(
                        "Archive module",
                        key=f"archive-module-{module_id}",
                        disabled=not confirm or last_live_module,
                    ):
                        set_cms_module_archived(
                            module_id,
                            True,
                            user["user_id"],
                            sort_order=int(module.get("_cms_sort_order") or 0),
                        )
                        _clear_content_studio_caches()
                        _content_studio_flash("Module archived. Existing learner progress was kept.")
                        st.rerun()
    else:
        st.info("No modules are available yet.")

    if is_admin:
        with st.expander("＋ Add module"):
            with st.form("studio-add-module-form", clear_on_submit=False):
                new_id = st.text_input("Module ID", placeholder="new-module-id", key="studio-new-module-id").strip().lower()
                new_title = st.text_input("Title", placeholder="New learning module", key="studio-new-module-title")
                new_short = st.text_input("Short title", placeholder="New module", key="studio-new-module-short")
                new_track = st.selectbox(
                    "Color",
                    ["Learning", "Community", "Empowerment"],
                    format_func=lambda value: {"Learning": "Blue", "Community": "Green", "Empowerment": "Ochre"}.get(value, value),
                    help="This only controls the module's visual color.",
                    key="new-module-track",
                )
                new_description = st.text_area("Description", height=90, key="studio-new-module-description")
                new_status = st.selectbox(
                    "Learner status",
                    ["Available", "Under construction", "Coming soon"],
                    key="studio-new-module-status",
                )
                new_minutes = st.number_input("Estimated minutes", min_value=0, max_value=5000, value=30, key="studio-new-module-minutes")
                new_sort = st.number_input("Sort order", min_value=0, max_value=10000, value=(len(snapshot) + 1) * 10, step=10, key="studio-new-module-sort")
                add_module = st.form_submit_button("Create module draft", type="primary")
            if add_module:
                if not _valid_content_id(new_id):
                    st.error("Use a lowercase ID with letters, numbers and hyphens, for example `soil-health`.")
                elif new_id in snapshot:
                    st.error("That module ID already exists.")
                elif not new_title.strip():
                    st.error("Add a module title.")
                else:
                    icon_map = {"Learning": "◎", "Community": "◫", "Empowerment": "↝"}
                    payload = {
                        "id": new_id,
                        "title": new_title.strip(),
                        "short_title": new_short.strip() or new_title.strip(),
                        "track": new_track,
                        "track_icon": icon_map[new_track],
                        "description": new_description.strip(),
                        "estimated_minutes": int(new_minutes),
                        "status": new_status,
                        "eyebrow": "Learning journey",
                        "source_note": "",
                        "learning_outcomes": [],
                        "building_blocks": [],
                    }
                    _content_studio_save_module(new_id, payload, int(new_sort), user["user_id"])
                    _content_studio_flash("New module draft created. Add lessons, then publish it when ready.")
                    st.rerun()


def _render_content_studio_lessons(user: dict, snapshot: dict[str, dict]) -> None:
    is_admin = is_administrator(user)
    st.markdown("### Lessons")
    st.caption(
        "Editors can update existing lesson metadata and save drafts. Administrators can add, publish, archive and restore lessons. "
        "Lesson IDs stay stable so learner progress remains linked correctly."
    )

    module_ids = [module_id for module_id, module in snapshot.items() if not module.get("_cms_archived")]
    if not module_ids:
        st.info("Create or restore a module before managing lessons.")
        return
    module_id = st.selectbox(
        "Module",
        module_ids,
        format_func=lambda value: snapshot[value]["short_title"],
        key="studio-lessons-module",
    )
    module = snapshot[module_id]
    lessons = [
        lesson
        for lesson in module.get("topics", [])
    ]
    lesson_ids = [lesson["id"] for lesson in lessons]
    library_snapshot = _admin_library_resource_snapshot()
    library_options = [rid for rid, item in library_snapshot.items() if not item.get("_cms_archived")]

    if lesson_ids:
        lesson_id = st.selectbox(
            "Lesson to edit",
            lesson_ids,
            format_func=lambda value: next(
                (
                    f"{lesson['title']} · archived"
                    if lesson.get("_cms_archived")
                    else lesson["title"]
                )
                for lesson in lessons
                if lesson["id"] == value
            ),
            key="studio-lesson-select",
        )
        lesson = next(item for item in lessons if item["id"] == lesson_id)
        archived = bool(lesson.get("_cms_archived"))
        with st.form(f"studio-lesson-form-{module_id}-{lesson_id}"):
            title = st.text_input("Lesson title", value=lesson.get("title", ""), key=f"studio-lesson-title-{module_id}-{lesson_id}")
            a, b, c = st.columns(3)
            with a:
                level = st.selectbox(
                    "Level",
                    ["Understand", "Apply", "Convince"],
                    index=["Understand", "Apply", "Convince"].index(lesson.get("level", "Understand")),
                    format_func=lambda value: "Discover" if value == "Understand" else "Communicate" if value == "Convince" else value,
                    key=f"studio-lesson-level-{module_id}-{lesson_id}",
                )
            with b:
                minutes = st.number_input("Minutes", min_value=0, max_value=1000, value=int(lesson.get("minutes") or 0), key=f"studio-lesson-minutes-{module_id}-{lesson_id}")
            with c:
                sort_order = st.number_input(
                    "Sort order",
                    min_value=0,
                    max_value=10000,
                    value=int(lesson.get("_cms_sort_order") or 0),
                    step=10,
                    key=f"studio-lesson-sort-{module_id}-{lesson_id}",
                )
            summary = st.text_area("Summary", value=lesson.get("summary", ""), height=90, key=f"studio-lesson-summary-{module_id}-{lesson_id}")
            body = st.text_area("Intro / body text", value=lesson.get("body", ""), height=150, key=f"studio-lesson-body-{module_id}-{lesson_id}")
            prompt = st.text_area("Reflection prompt", value=lesson.get("prompt", ""), height=90, key=f"studio-lesson-prompt-{module_id}-{lesson_id}")
            linked_resource_ids = st.multiselect(
                "Linked Resources page items",
                library_options,
                default=[rid for rid in lesson.get("resource_ids") or [] if rid in library_options],
                format_func=lambda rid: f"{library_snapshot[rid]['title']} · {library_snapshot[rid]['origin']}",
                help="These appear as clickable sources in the lesson and open the searchable Resources page.",
                key=f"studio-lesson-resource-links-{module_id}-{lesson_id}",
            )
            sources_text = st.text_area(
                "Additional / legacy references · one per line",
                value="\n".join(lesson.get("sources") or []),
                height=110,
                help="Use this for references that have not yet been added to the Resources page.",
                key=f"studio-lesson-sources-{module_id}-{lesson_id}",
            )
            payload = _lesson_content_payload(lesson)
            payload.update(
                {
                    "id": lesson_id,
                    "title": title.strip(),
                    "level": level,
                    "minutes": int(minutes),
                    "summary": summary.strip(),
                    "body": body.strip(),
                    "prompt": prompt.strip(),
                    "resource_ids": linked_resource_ids,
                    "sources": [line.strip() for line in sources_text.splitlines() if line.strip()],
                }
            )
            save_col, publish_col = st.columns(2)
            with save_col:
                save_pressed = st.form_submit_button("Save lesson draft", width="stretch")
            with publish_col:
                publish_pressed = st.form_submit_button(
                    "Publish lesson",
                    type="primary",
                    width="stretch",
                    disabled=not is_admin or archived,
                )
        if save_pressed:
            _content_studio_save_lesson(module_id, lesson_id, payload, int(sort_order), user["user_id"])
            _content_studio_flash("Lesson draft saved.")
            st.rerun()
        if publish_pressed and is_admin:
            _content_studio_publish_lesson(module_id, lesson_id, payload, int(sort_order), user["user_id"])
            _content_studio_flash("Lesson published.")
            st.rerun()

        if is_admin:
            with st.expander("Archive / restore lesson"):
                if archived:
                    if st.button("Restore lesson", key=f"restore-lesson-{module_id}-{lesson_id}", type="primary"):
                        set_cms_lesson_archived(
                            module_id,
                            lesson_id,
                            False,
                            user["user_id"],
                            sort_order=int(lesson.get("_cms_sort_order") or 0),
                        )
                        _clear_content_studio_caches()
                        _content_studio_flash("Lesson restored.")
                        st.rerun()
                else:
                    confirm = st.checkbox(
                        "I understand that this removes the lesson from learner-facing pages but keeps existing progress and quiz results.",
                        key=f"confirm-archive-lesson-{module_id}-{lesson_id}",
                    )
                    if st.button(
                        "Archive lesson",
                        key=f"archive-lesson-{module_id}-{lesson_id}",
                        disabled=not confirm,
                    ):
                        set_cms_lesson_archived(
                            module_id,
                            lesson_id,
                            True,
                            user["user_id"],
                            sort_order=int(lesson.get("_cms_sort_order") or 0),
                        )
                        _clear_content_studio_caches()
                        _content_studio_flash("Lesson archived. Existing learner data was kept.")
                        st.rerun()
    else:
        st.info("This module has no lessons yet.")

    if is_admin:
        with st.expander("＋ Add lesson"):
            with st.form(f"studio-add-lesson-{module_id}"):
                new_id = st.text_input("Lesson ID", placeholder="new-lesson-id", key=f"studio-new-lesson-id-{module_id}").strip().lower()
                new_title = st.text_input("Lesson title", placeholder="New lesson", key=f"studio-new-lesson-title-{module_id}")
                new_level = st.selectbox("Level", ["Understand", "Apply", "Convince"],
                                         format_func=lambda value: "Discover" if value == "Understand" else "Communicate" if value == "Convince" else value,
                                         key=f"new-lesson-level-{module_id}")
                new_minutes = st.number_input("Minutes", min_value=0, max_value=1000, value=10, key=f"new-lesson-minutes-{module_id}")
                new_summary = st.text_area("Summary", height=80, key=f"new-lesson-summary-{module_id}")
                new_resource_ids = st.multiselect(
                    "Linked Resources page items",
                    library_options,
                    format_func=lambda rid: f"{library_snapshot[rid]['title']} · {library_snapshot[rid]['origin']}",
                    key=f"new-lesson-resource-links-{module_id}",
                )
                new_sources = st.text_area(
                    "Additional / legacy references · one per line",
                    height=100,
                    key=f"new-lesson-sources-{module_id}",
                )
                new_sort = st.number_input(
                    "Sort order",
                    min_value=0,
                    max_value=10000,
                    value=(len(lessons) + 1) * 10,
                    step=10,
                    key=f"new-lesson-sort-{module_id}",
                )
                add_lesson = st.form_submit_button("Create lesson draft", type="primary")
            if add_lesson:
                if not _valid_content_id(new_id):
                    st.error("Use a lowercase lesson ID with letters, numbers and hyphens.")
                elif new_id in lesson_ids:
                    st.error("That lesson ID already exists in this module.")
                elif not new_title.strip():
                    st.error("Add a lesson title.")
                else:
                    payload = {
                        "id": new_id,
                        "title": new_title.strip(),
                        "level": new_level,
                        "minutes": int(new_minutes),
                        "summary": new_summary.strip(),
                        "body": "",
                        "prompt": "",
                        "resource_ids": new_resource_ids,
                        "sources": [line.strip() for line in new_sources.splitlines() if line.strip()],
                        "theory_cards": [
                            {
                                "label": "Core idea",
                                "title": "New idea",
                                "text": "Add the learner-facing explanation in the Ideas & content tab.",
                            }
                        ],
                        "takeaway": "",
                        "practice_note": "",
                        "quiz": None,
                        "self_check": [],
                    }
                    _content_studio_save_lesson(module_id, new_id, payload, int(new_sort), user["user_id"])
                    _content_studio_flash("New lesson draft created. Add ideas or checks before publishing it.")
                    st.rerun()


def _render_content_studio_ideas(user: dict, snapshot: dict[str, dict]) -> None:
    st.caption("Imported Superhuman Docs cards are edited in their source pages and updated through Superhuman Docs import. This editor is for native MOSAIC Learn content.")
    is_admin = is_administrator(user)
    st.markdown("### Ideas & learner-facing content")
    st.caption(
        "Editors can revise existing idea cards and synthesis text. Only administrators can add or remove idea cards and publish changes."
    )
    editable_modules = {
        module_id: module
        for module_id, module in snapshot.items()
        if not module.get("_cms_archived")
        and any(
            not topic.get("_cms_archived") and topic.get("source_system") != "superhuman_docs"
            for topic in module.get("topics", [])
        )
    }
    if not editable_modules:
        st.info("Add a lesson before editing ideas.")
        return

    select_a, select_b = st.columns(2)
    with select_a:
        module_id = st.selectbox(
            "Module",
            list(editable_modules),
            format_func=lambda value: editable_modules[value]["short_title"],
            key="studio-carousel-module",
        )
    editable_topics = [
        topic
        for topic in editable_modules[module_id].get("topics", [])
        if not topic.get("_cms_archived") and topic.get("source_system") != "superhuman_docs"
    ]
    topic_ids = [topic["id"] for topic in editable_topics]
    with select_b:
        topic_id = st.selectbox(
            "Lesson",
            topic_ids,
            format_func=lambda value: next(topic["title"] for topic in editable_topics if topic["id"] == value),
            key="studio-carousel-topic",
        )
    topic = next(topic for topic in editable_topics if topic["id"] == topic_id)
    record = get_carousel_content(module_id, topic_id) or {}
    working_key = f"studio-working-{module_id}-{topic_id}"
    if working_key not in st.session_state:
        stored_payload = record.get("draft") or record.get("published") or default_carousel_payload(topic)
        st.session_state[working_key] = normalize_carousel_payload(stored_payload, topic)
    payload = normalize_carousel_payload(copy.deepcopy(st.session_state[working_key]), topic)
    st.session_state[working_key] = copy.deepcopy(payload)

    published_at = record.get("published_at") or "Not published from the idea editor yet"
    updated_at = record.get("updated_at") or "No saved draft yet"
    st.markdown(
        f"<div class='m-admin-note'><strong>{escape(topic['title'])}</strong>"
        f"<p>Draft saved: {escape(str(updated_at))}<br>Published: {escape(str(published_at))}</p></div>",
        unsafe_allow_html=True,
    )

    screen_key = f"studio-carousel-screen-{module_id}-{topic_id}"
    if not payload["cards"]:
        st.info("This lesson currently has no idea cards. It will fall back to the lesson body text for learners.")
        if is_admin and st.button("＋ Add first idea", key=f"studio-first-idea-{module_id}-{topic_id}", type="primary"):
            payload["cards"] = [
                {
                    "editor_id": uuid4().hex[:16],
                    "label": "Core idea",
                    "title": "New idea",
                    "body_html": "<p>Add the text here.</p>",
                    "image_resource_id": "",
                    "image_alt": "Idea image",
                }
            ]
            _persist_idea_draft_if_valid(module_id, topic_id, payload, topic, user["user_id"], working_key)
            first_card_id = payload["cards"][0]["editor_id"]
            _queue_widget_selection(screen_key, first_card_id)
            st.rerun()
        selected_block = "synthesis"
    else:
        block_options = [card["editor_id"] for card in payload["cards"]] + ["synthesis"]
        _apply_queued_widget_selection(screen_key, block_options)
        if st.session_state.get(screen_key) not in block_options:
            st.session_state[screen_key] = block_options[0]

        selected_block = st.selectbox(
            "Carousel screen",
            block_options,
            format_func=lambda value: (
                "Synthesis · Key idea & MOSAIC practice"
                if value == "synthesis"
                else next(
                    f"Idea {index + 1} · {card['title']}"
                    for index, card in enumerate(payload["cards"])
                    if card["editor_id"] == value
                )
            ),
            key=screen_key,
        )

    if selected_block == "synthesis":
        takeaway_html = _rich_text_editor(
            "Key idea (HTML)",
            payload.get("takeaway_html", ""),
            key=f"studio-takeaway-{module_id}-{topic_id}",
        )
        practice_note_html = _rich_text_editor(
            "From MOSAIC practice (HTML)",
            payload.get("practice_note_html", ""),
            key=f"studio-practice-{module_id}-{topic_id}",
        )
        image_col, alt_col = st.columns(2)
        with image_col:
            practice_image = st.text_input(
                "Practice image filename (inside assets/)",
                value=payload.get("practice_image", ""),
                placeholder="policy-lab-example.jpg",
                key=f"studio-image-{module_id}-{topic_id}",
            )
        with alt_col:
            practice_image_alt = st.text_input(
                "Image description",
                value=payload.get("practice_image_alt", "MOSAIC practice"),
                key=f"studio-image-alt-{module_id}-{topic_id}",
            )
        payload["takeaway_html"] = takeaway_html
        payload["practice_note_html"] = practice_note_html
        payload["practice_image"] = practice_image.strip()
        payload["practice_image_alt"] = practice_image_alt.strip()
    else:
        card_id = str(selected_block)
        card_index = next(index for index, card in enumerate(payload["cards"]) if card["editor_id"] == card_id)
        current_card = payload["cards"][card_index]
        heading_a, heading_b = st.columns([1, 2])
        with heading_a:
            label = st.text_input(
                "Small label",
                value=current_card.get("label", "Core idea"),
                key=f"studio-label-{module_id}-{topic_id}-{card_id}",
            )
        with heading_b:
            title = st.text_input(
                "Title",
                value=current_card.get("title", ""),
                key=f"studio-title-{module_id}-{topic_id}-{card_id}",
            )
        body_html = _rich_text_editor(
            "Body (HTML)",
            current_card.get("body_html", ""),
            key=f"studio-body-{module_id}-{topic_id}-{card_id}",
        )
        image_resource_id = str(current_card.get("image_resource_id") or "").strip()
        image_alt = st.text_input(
            "Idea image description",
            value=str(current_card.get("image_alt") or current_card.get("title") or "Idea image"),
            key=f"studio-idea-image-alt-{module_id}-{topic_id}-{card_id}",
        )
        payload["cards"][card_index] = {
            "editor_id": card_id,
            "label": label.strip() or "Core idea",
            "title": title.strip(),
            "body_html": body_html,
            "image_resource_id": image_resource_id,
            "image_alt": image_alt.strip() or title.strip() or "Idea image",
        }

        if image_resource_id:
            image_record = _cached_resource_file(image_resource_id)
            if image_record and image_record.get("file_data") and not image_record.get("archived"):
                st.image(image_record["file_data"], caption="Current idea image", width=320)
        if is_admin:
            st.caption("Optional PNG. When published, the image occupies roughly one third of the idea card on larger screens.")
            idea_upload = st.file_uploader(
                "Add or replace idea PNG",
                type=["png"],
                key=f"studio-idea-image-upload-{module_id}-{topic_id}-{card_id}",
            )
            image_add_col, image_remove_col = st.columns(2)
            with image_add_col:
                if st.button(
                    "Attach PNG",
                    key=f"studio-idea-image-attach-{module_id}-{topic_id}-{card_id}",
                    disabled=idea_upload is None,
                    width="stretch",
                ):
                    file_name, mime_type, file_bytes = _validate_uploaded_image(idea_upload, png_only=True)
                    if file_bytes is not None:
                        new_resource_id = uuid4().hex
                        save_cms_resource_file(
                            new_resource_id,
                            scope_type="idea",
                            scope_id=_idea_image_scope_id(module_id, topic_id, card_id),
                            module_id=module_id,
                            resource_kind="Idea image",
                            title=title.strip() or "Idea image",
                            description=image_alt.strip() or title.strip() or "Idea image",
                            file_name=file_name,
                            mime_type=mime_type,
                            file_data=file_bytes,
                            sort_order=10,
                            updated_by=user["user_id"],
                        )
                        payload["cards"][card_index]["image_resource_id"] = new_resource_id
                        _persist_idea_draft_if_valid(
                            module_id, topic_id, payload, topic, user["user_id"], working_key
                        )
                        _queue_widget_selection(screen_key, card_id)
                        _content_studio_flash(
                            "PNG attached and the idea draft was saved. Use ‘Publish ideas’ when you want learners to see it."
                        )
                        st.rerun()
            with image_remove_col:
                if st.button(
                    "Remove image from draft",
                    key=f"studio-idea-image-remove-{module_id}-{topic_id}-{card_id}",
                    disabled=not image_resource_id,
                    width="stretch",
                ):
                    payload["cards"][card_index]["image_resource_id"] = ""
                    _persist_idea_draft_if_valid(
                        module_id, topic_id, payload, topic, user["user_id"], working_key
                    )
                    _queue_widget_selection(screen_key, card_id)
                    _content_studio_flash("Image removed and the idea draft was saved. Publish the ideas to remove it for learners.")
                    st.rerun()

        move_col, add_col, remove_col = st.columns([1.3, 1, 1])
        with move_col:
            target_position = st.selectbox(
                "Position",
                list(range(1, len(payload["cards"]) + 1)),
                index=card_index,
                key=f"studio-position-{module_id}-{topic_id}-{card_id}",
            )
            if st.button(
                "Move idea",
                key=f"studio-move-{module_id}-{topic_id}-{card_id}",
                disabled=target_position - 1 == card_index,
                width="stretch",
            ):
                moved = payload["cards"].pop(card_index)
                payload["cards"].insert(target_position - 1, moved)
                _persist_idea_draft_if_valid(
                    module_id, topic_id, payload, topic, user["user_id"], working_key
                )
                _queue_widget_selection(screen_key, card_id)
                st.rerun()
        with add_col:
            if st.button(
                "＋ Add idea",
                key=f"studio-add-idea-{module_id}-{topic_id}-{card_id}",
                disabled=not is_admin,
                width="stretch",
            ):
                new_card_id = uuid4().hex[:16]
                payload["cards"].insert(
                    card_index + 1,
                    {
                        "editor_id": new_card_id,
                        "label": "Core idea",
                        "title": "New idea",
                        "body_html": "<p>Add the text here.</p>",
                        "image_resource_id": "",
                        "image_alt": "Idea image",
                    },
                )
                _persist_idea_draft_if_valid(
                    module_id, topic_id, payload, topic, user["user_id"], working_key
                )
                _queue_widget_selection(screen_key, new_card_id)
                st.rerun()
        with remove_col:
            if st.button(
                "Remove idea",
                key=f"studio-remove-idea-{module_id}-{topic_id}-{card_id}",
                disabled=not is_admin,
                width="stretch",
            ):
                payload["cards"].pop(card_index)
                _persist_idea_draft_if_valid(
                    module_id, topic_id, payload, topic, user["user_id"], working_key
                )
                next_screen = (
                    payload["cards"][min(card_index, len(payload["cards"]) - 1)]["editor_id"]
                    if payload["cards"]
                    else "synthesis"
                )
                _queue_widget_selection(screen_key, next_screen)
                st.rerun()

    st.session_state[working_key] = payload
    cleaned_payload = normalize_carousel_payload(payload, topic)
    content_valid = len(cleaned_payload["cards"]) == len(payload["cards"])
    if not content_valid:
        st.error("Every idea needs a title before the draft can be saved.")

    st.divider()
    save_col, publish_col, reload_col, open_col = st.columns(4)
    with save_col:
        if st.button("Save draft", key=f"studio-save-ideas-{module_id}-{topic_id}", disabled=not content_valid, width="stretch"):
            save_carousel_draft(module_id, topic_id, cleaned_payload, user["user_id"])
            _clear_content_studio_caches()
            st.session_state[working_key] = cleaned_payload
            _queue_widget_selection(screen_key, str(selected_block))
            _content_studio_flash("Idea draft saved.")
            st.rerun()
    with publish_col:
        if st.button(
            "Publish ideas",
            key=f"studio-publish-ideas-{module_id}-{topic_id}",
            type="primary",
            disabled=not is_admin or not content_valid,
            width="stretch",
        ):
            publish_carousel_content(module_id, topic_id, cleaned_payload, user["user_id"])
            _clear_content_studio_caches()
            st.session_state[working_key] = cleaned_payload
            _queue_widget_selection(screen_key, str(selected_block))
            _content_studio_flash("Ideas published. The learner-facing carousel now includes the current idea images.")
            st.rerun()
    with reload_col:
        if st.button("Reload saved", key=f"studio-reload-ideas-{module_id}-{topic_id}", width="stretch"):
            latest = get_carousel_content(module_id, topic_id) or {}
            source = latest.get("draft") or latest.get("published") or default_carousel_payload(topic)
            reloaded = normalize_carousel_payload(source, topic)
            st.session_state[working_key] = reloaded
            reloaded_options = [card["editor_id"] for card in reloaded.get("cards", [])] + ["synthesis"]
            next_screen = str(selected_block) if str(selected_block) in reloaded_options else reloaded_options[0]
            _queue_widget_selection(screen_key, next_screen)
            st.rerun()
    with open_col:
        is_live = module_id in MODULES and any(item.get("id") == topic_id for item in MODULES[module_id].get("topics", []))
        st.button("Open lesson →", key=f"studio-open-lesson-{module_id}-{topic_id}", disabled=not is_live, width="stretch", on_click=navigate, args=("topic", module_id, topic_id, None, None), kwargs={"_rerun": False})


def _render_content_studio_checks(user: dict, snapshot: dict[str, dict]) -> None:
    is_admin = is_administrator(user)
    st.markdown("### Checks & quizzes")
    st.caption(
        "Editors can add, remove and edit a lesson's quick quiz and reflection checks in a draft. Administrators publish the draft to learners."
    )
    modules = {
        module_id: module
        for module_id, module in snapshot.items()
        if not module.get("_cms_archived")
        and any(
            not lesson.get("_cms_archived")
            for lesson in module.get("topics", [])
        )
    }
    if not modules:
        st.info("Add a lesson before creating checks.")
        return
    a, b = st.columns(2)
    with a:
        module_id = st.selectbox(
            "Module",
            list(modules),
            format_func=lambda value: modules[value]["short_title"],
            key="studio-check-module",
        )
    lessons = [
        lesson
        for lesson in modules[module_id].get("topics", [])
        if not lesson.get("_cms_archived")
    ]
    with b:
        lesson_id = st.selectbox(
            "Lesson",
            [lesson["id"] for lesson in lessons],
            format_func=lambda value: next(lesson["title"] for lesson in lessons if lesson["id"] == value),
            key="studio-check-lesson",
        )
    lesson = next(item for item in lessons if item["id"] == lesson_id)
    quiz = lesson.get("quiz") if isinstance(lesson.get("quiz"), dict) else None
    options = list(quiz.get("options") or []) if quiz else []
    options = (options + ["", "", "", ""])[:4]
    answer_index = int(quiz.get("answer") or 0) if quiz else 0
    answer_index = max(0, min(answer_index, 3))

    with st.form(f"studio-check-form-{module_id}-{lesson_id}"):
        enable_quiz = st.checkbox("Include a multiple-choice quick quiz", value=bool(quiz))
        question = st.text_area(
            "Quiz question",
            value=str(quiz.get("question") or "") if quiz else "",
            height=90,
            disabled=not enable_quiz,
        )
        option_cols = st.columns(2)
        edited_options = []
        for idx in range(4):
            with option_cols[idx % 2]:
                edited_options.append(
                    st.text_input(
                        f"Option {chr(65 + idx)}",
                        value=str(options[idx]),
                        key=f"studio-check-option-{module_id}-{lesson_id}-{idx}",
                        disabled=not enable_quiz,
                    )
                )
        correct_answer = st.selectbox(
            "Correct answer",
            list(range(4)),
            index=answer_index,
            format_func=lambda value: f"Option {chr(65 + value)}",
            disabled=not enable_quiz,
        )
        explanation = st.text_area(
            "Explanation shown after answering",
            value=str(quiz.get("explanation") or "") if quiz else "",
            height=100,
            disabled=not enable_quiz,
        )
        checks_text = st.text_area(
            "Reflection/self-check prompts · one per line",
            value="\n".join(lesson.get("self_check") or []),
            height=150,
        )
        save_col, publish_col = st.columns(2)
        with save_col:
            save_pressed = st.form_submit_button("Save checks draft", width="stretch")
        with publish_col:
            publish_pressed = st.form_submit_button(
                "Publish checks",
                type="primary",
                width="stretch",
                disabled=not is_admin,
            )

    quiz_valid = True
    new_quiz = None
    if enable_quiz:
        quiz_valid = bool(question.strip()) and all(option.strip() for option in edited_options)
        new_quiz = {
            "question": question.strip(),
            "options": [option.strip() for option in edited_options],
            "answer": int(correct_answer),
            "explanation": explanation.strip(),
        }
    lesson_payload = _lesson_content_payload(lesson)
    lesson_payload["quiz"] = new_quiz
    lesson_payload["self_check"] = [line.strip() for line in checks_text.splitlines() if line.strip()]
    sort_order = int(lesson.get("_cms_sort_order") or 0)
    if (save_pressed or publish_pressed) and not quiz_valid:
        st.error("A quiz needs a question and four non-empty answer options.")
    elif save_pressed:
        _content_studio_save_lesson(module_id, lesson_id, lesson_payload, sort_order, user["user_id"])
        _content_studio_flash("Checks and quiz draft saved.")
        st.rerun()
    elif publish_pressed and is_admin:
        _content_studio_publish_lesson(module_id, lesson_id, lesson_payload, sort_order, user["user_id"])
        _content_studio_flash("Checks and quiz published.")
        st.rerun()


def _validate_uploaded_resource(uploaded_file) -> tuple[str, str, bytes] | tuple[None, None, None]:
    if uploaded_file is None:
        return None, None, None
    file_name = _safe_resource_filename(uploaded_file.name)
    extension = Path(file_name).suffix.lower()
    if extension not in RESOURCE_UPLOAD_TYPES:
        st.error("Supported files: PDF, Word, PowerPoint, Excel, CSV, TXT and ZIP.")
        return None, None, None
    file_bytes = uploaded_file.getvalue()
    if len(file_bytes) > MAX_CMS_RESOURCE_BYTES:
        st.error("This file is larger than 25 MB. Use a smaller file or an external document link instead.")
        return None, None, None
    mime_type = str(uploaded_file.type or RESOURCE_UPLOAD_TYPES[extension])
    return file_name, mime_type, file_bytes


def _validate_uploaded_image(uploaded_file, *, png_only: bool = False) -> tuple[str, str, bytes] | tuple[None, None, None]:
    if uploaded_file is None:
        return None, None, None
    file_name = _safe_resource_filename(uploaded_file.name)
    extension = Path(file_name).suffix.lower()
    allowed = {".png": "image/png"} if png_only else IMAGE_UPLOAD_TYPES
    if extension not in allowed:
        st.error("Only PNG images are supported here." if png_only else "Supported images: PNG, JPG/JPEG and WebP.")
        return None, None, None
    file_bytes = uploaded_file.getvalue()
    if len(file_bytes) > MAX_CMS_IMAGE_BYTES:
        st.error("This image is larger than 8 MB. Use a smaller image.")
        return None, None, None
    mime_type = str(uploaded_file.type or allowed[extension])
    return file_name, mime_type, file_bytes


def _render_content_studio_resource_manager(
    user: dict,
    *,
    scope_type: str,
    scope_id: str,
    module_id: str = "",
    heading: str,
    default_kind: str,
) -> None:
    if not is_administrator(user):
        st.info("Only administrators can add, replace, archive or restore downloadable files.")
        return

    st.markdown(f"#### {heading}")
    st.caption(
        "Files are stored in the protected application database rather than the deployment filesystem, so they persist across GitHub/Streamlit redeployments. Maximum upload size here is 25 MB per file."
    )
    resources = _resource_files_for(scope_type, scope_id, include_archived=True)
    if resources:
        for meta in resources:
            status = "archived" if meta.get("archived") else "available"
            label = f"{meta.get('title') or meta.get('file_name')} · {status}"
            with st.expander(label):
                st.caption(
                    f"{meta.get('resource_kind') or 'File'} · {_format_file_size(meta.get('size_bytes'))} · {_safe_resource_filename(meta.get('file_name'))}"
                )
                if not meta.get("archived"):
                    _render_resource_download(
                        meta,
                        key=f"studio-resource-download-{scope_type}-{scope_id}-{meta['resource_id']}",
                        label="Download current file ↓",
                    )
                with st.form(f"studio-resource-edit-{meta['resource_id']}"):
                    a, b = st.columns([1, 2])
                    with a:
                        resource_kind = st.text_input(
                            "Type / label",
                            value=str(meta.get("resource_kind") or default_kind),
                            key=f"studio-resource-kind-{meta['resource_id']}",
                        )
                        sort_order = st.number_input(
                            "Sort order",
                            min_value=0,
                            max_value=10000,
                            value=int(meta.get("sort_order") or 0),
                            step=10,
                            key=f"studio-resource-sort-{meta['resource_id']}",
                        )
                    with b:
                        title = st.text_input(
                            "Title",
                            value=str(meta.get("title") or ""),
                            key=f"studio-resource-title-{meta['resource_id']}",
                        )
                    description = st.text_area(
                        "Description",
                        value=str(meta.get("description") or ""),
                        height=80,
                        key=f"studio-resource-description-{meta['resource_id']}",
                    )
                    replacement = st.file_uploader(
                        "Replace file (optional)",
                        type=[ext.lstrip(".") for ext in RESOURCE_UPLOAD_TYPES],
                        key=f"studio-resource-replace-{meta['resource_id']}",
                    )
                    save_meta = st.form_submit_button("Save file details", type="primary")
                if save_meta:
                    if not title.strip():
                        st.error("Add a title for the file.")
                    else:
                        file_name = mime_type = file_bytes = None
                        if replacement is not None:
                            file_name, mime_type, file_bytes = _validate_uploaded_resource(replacement)
                            if file_bytes is None:
                                st.stop()
                        save_cms_resource_file(
                            meta["resource_id"],
                            scope_type=scope_type,
                            scope_id=scope_id,
                            module_id=module_id,
                            resource_kind=resource_kind.strip() or default_kind,
                            title=title.strip(),
                            description=description.strip(),
                            file_name=file_name,
                            mime_type=mime_type,
                            file_data=file_bytes,
                            sort_order=int(sort_order),
                            updated_by=user["user_id"],
                        )
                        _clear_content_studio_caches()
                        _content_studio_flash("File details updated.")
                        st.rerun()

                if meta.get("archived"):
                    if st.button(
                        "Restore file",
                        key=f"studio-resource-restore-{meta['resource_id']}",
                        type="primary",
                    ):
                        set_cms_resource_archived(meta["resource_id"], False, user["user_id"])
                        _clear_content_studio_caches()
                        _content_studio_flash("File restored.")
                        st.rerun()
                else:
                    if st.button(
                        "Archive file",
                        key=f"studio-resource-archive-{meta['resource_id']}",
                    ):
                        set_cms_resource_archived(meta["resource_id"], True, user["user_id"])
                        _clear_content_studio_caches()
                        _content_studio_flash("File archived. It is no longer shown to learners.")
                        st.rerun()
    else:
        st.info("No files have been uploaded here yet.")

    allow_multiple = scope_type == "tool"
    with st.expander("＋ Add files" if allow_multiple else "＋ Add file"):
        with st.form(f"studio-resource-add-{scope_type}-{scope_id}"):
            a, b = st.columns([1, 2])
            with a:
                new_kind = st.text_input("Type / label", value=default_kind, key=f"studio-new-resource-kind-{scope_type}-{scope_id}")
                new_sort = st.number_input(
                    "Starting sort order",
                    min_value=0,
                    max_value=10000,
                    value=(len(resources) + 1) * 10,
                    step=10,
                    key=f"studio-new-resource-sort-{scope_type}-{scope_id}",
                )
            with b:
                new_title = st.text_input(
                    "Title" + (" (optional for multiple files)" if allow_multiple else ""),
                    key=f"studio-new-resource-title-{scope_type}-{scope_id}",
                )
            new_description = st.text_area("Description", height=80, key=f"studio-new-resource-description-{scope_type}-{scope_id}")
            upload = st.file_uploader(
                "Files" if allow_multiple else "File",
                type=[ext.lstrip(".") for ext in RESOURCE_UPLOAD_TYPES],
                accept_multiple_files=allow_multiple,
                key=f"studio-new-resource-upload-{scope_type}-{scope_id}",
            )
            add_file = st.form_submit_button("Upload resources" if allow_multiple else "Upload file", type="primary")
        if add_file:
            uploads = list(upload or []) if allow_multiple else ([upload] if upload is not None else [])
            if not uploads:
                st.error("Choose at least one file to upload.")
            elif len(uploads) == 1 and not new_title.strip():
                st.error("Add a title for the file.")
            else:
                prepared = []
                for offset, uploaded in enumerate(uploads):
                    file_name, mime_type, file_bytes = _validate_uploaded_resource(uploaded)
                    if file_bytes is None:
                        prepared = []
                        break
                    title_value = (
                        new_title.strip()
                        if len(uploads) == 1
                        else Path(file_name).stem.replace("-", " ").replace("_", " ").strip().title()
                    )
                    prepared.append((file_name, mime_type, file_bytes, title_value, int(new_sort) + offset * 10))
                if prepared:
                    for file_name, mime_type, file_bytes, title_value, sort_value in prepared:
                        save_cms_resource_file(
                            uuid4().hex,
                            scope_type=scope_type,
                            scope_id=scope_id,
                            module_id=module_id,
                            resource_kind=new_kind.strip() or default_kind,
                            title=title_value,
                            description=new_description.strip(),
                            file_name=file_name,
                            mime_type=mime_type,
                            file_data=file_bytes,
                            sort_order=sort_value,
                            updated_by=user["user_id"],
                        )
                    _clear_content_studio_caches()
                    _content_studio_flash(
                        f"{len(prepared)} resource{'s' if len(prepared) != 1 else ''} uploaded and made available to learners."
                    )
                    st.rerun()


def _render_content_studio_convince_files(user: dict, snapshot: dict[str, dict]) -> None:
    st.markdown("### Communicate: uploaded files")
    st.caption(
        "For reusable documents, add each PDF, brief or slide deck once to the Superhuman Docs Resources table, "
        "then reference its row from a Communicate page, module or class. You can still upload legacy files here."
    )
    module_ids = [module_id for module_id, module in snapshot.items() if not module.get("_cms_archived")]
    if not module_ids:
        st.info("Create or restore a module before uploading files.")
        return
    module_id = st.selectbox(
        "Module",
        module_ids,
        format_func=lambda value: snapshot[value]["short_title"],
        key="studio-convince-resource-module",
    )
    existing_hub = bool(snapshot[module_id].get("convince"))
    if not existing_hub:
        st.info("This module uses the standard Communicate introduction. You can still upload additional files here.")
    _render_content_studio_resource_manager(
        user,
        scope_type="convince",
        scope_id=module_id,
        module_id=module_id,
        heading=f"Files for {snapshot[module_id]['short_title']}",
        default_kind="Resource",
    )


def _render_content_studio_tool_image_manager(user: dict, tool_id: str, tool: dict) -> None:
    st.markdown("#### Tool image")
    st.caption("Optional. This is the main image shown on the tool card and tool detail page.")
    image_rows = _resource_files_for("tool_image", tool_id, include_archived=True)
    active = next((row for row in image_rows if not row.get("archived")), None)
    if active:
        record = _cached_resource_file(active["resource_id"])
        if record and record.get("file_data"):
            st.image(record["file_data"], caption=str(record.get("description") or record.get("title") or "Tool image"), width=420)
    # Keep the uploader outside a form. In Streamlit forms, file-uploader values
    # are submitted in the same batch as the submit button, so deriving the
    # button's disabled state from `upload is None` can leave the button disabled
    # on Streamlit Cloud even after a file was selected.
    alt_text = st.text_input(
        "Image description",
        value=str(active.get("description") or tool.get("title") or "Tool image") if active else str(tool.get("title") or "Tool image"),
        key=f"studio-tool-image-alt-{tool_id}",
    )
    upload = st.file_uploader(
        "Add or replace image",
        type=["png", "jpg", "jpeg", "webp"],
        key=f"studio-tool-image-upload-{tool_id}",
    )
    save_image = st.button(
        "Save tool image",
        key=f"studio-tool-image-save-{tool_id}",
        type="primary",
        disabled=upload is None,
        width="stretch",
    )
    if save_image:
        if upload is None:
            st.error("Choose an image before saving.")
        else:
            file_name, mime_type, file_bytes = _validate_uploaded_image(upload)
            if file_bytes is not None:
                resource_id = active["resource_id"] if active else uuid4().hex
                links = _tool_lesson_links(tool)
                module_id = links[0][0] if links else str(tool.get("module_id") or "")
                save_cms_resource_file(
                    resource_id,
                    scope_type="tool_image",
                    scope_id=tool_id,
                    module_id=module_id,
                    resource_kind="Tool image",
                    title=str(tool.get("title") or tool_id),
                    description=alt_text.strip() or str(tool.get("title") or "Tool image"),
                    file_name=file_name,
                    mime_type=mime_type,
                    file_data=file_bytes,
                    sort_order=10,
                    updated_by=user["user_id"],
                )
                _clear_content_studio_caches()
                _set_query_param("admin", "tools")
                _content_studio_flash("Tool image saved.")
                st.rerun()
    if active and st.button("Remove tool image", key=f"studio-tool-image-remove-{tool_id}"):
        set_cms_resource_archived(active["resource_id"], True, user["user_id"])
        _clear_content_studio_caches()
        _content_studio_flash("Tool image removed.")
        st.rerun()



def _render_content_studio_tool_gallery_manager(user: dict, tool_id: str, tool: dict) -> None:
    st.markdown("#### Preview image slider")
    st.caption("Optional. Upload screenshots, model outputs or example images. Learners see them as a slider on the tool page.")
    rows = _resource_files_for("tool_gallery", tool_id, include_archived=True)
    for meta in rows:
        status = "archived" if meta.get("archived") else "shown"
        with st.expander(f"{meta.get('title') or meta.get('file_name')} · {status}"):
            record = _cached_resource_file(meta["resource_id"])
            if record and record.get("file_data"):
                st.image(record["file_data"], caption=str(meta.get("description") or ""), width=360)
            with st.form(f"studio-tool-gallery-edit-{meta['resource_id']}"):
                caption = st.text_input("Caption", value=str(meta.get("description") or ""), key=f"studio-gallery-caption-{meta['resource_id']}")
                sort_order = st.number_input("Order", min_value=0, max_value=10000, value=int(meta.get("sort_order") or 0), step=10, key=f"studio-gallery-order-{meta['resource_id']}")
                save_meta = st.form_submit_button("Save image details", type="primary")
            if save_meta:
                save_cms_resource_file(
                    meta["resource_id"], scope_type="tool_gallery", scope_id=tool_id,
                    module_id=str(tool.get("module_id") or ""), resource_kind="Preview image",
                    title=str(meta.get("title") or meta.get("file_name") or "Preview image"), description=caption.strip(),
                    sort_order=int(sort_order), updated_by=user["user_id"],
                )
                _clear_content_studio_caches(); _content_studio_flash("Preview image details saved."); st.rerun()
            if meta.get("archived"):
                if st.button("Restore image", key=f"studio-gallery-restore-{meta['resource_id']}"):
                    set_cms_resource_archived(meta["resource_id"], False, user["user_id"]); _clear_content_studio_caches(); st.rerun()
            else:
                if st.button("Remove image", key=f"studio-gallery-remove-{meta['resource_id']}"):
                    set_cms_resource_archived(meta["resource_id"], True, user["user_id"]); _clear_content_studio_caches(); st.rerun()

    uploads = st.file_uploader(
        "Add preview images",
        type=["png", "jpg", "jpeg", "webp"],
        accept_multiple_files=True,
        key=f"studio-tool-gallery-upload-{tool_id}",
    )
    if st.button("Upload preview images", key=f"studio-tool-gallery-save-{tool_id}", type="primary", disabled=not bool(uploads)):
        prepared = []
        for offset, upload in enumerate(uploads or []):
            file_name, mime_type, file_bytes = _validate_uploaded_image(upload)
            if file_bytes is None:
                prepared = []
                break
            prepared.append((file_name, mime_type, file_bytes, (len(rows) + offset + 1) * 10))
        for file_name, mime_type, file_bytes, order in prepared:
            save_cms_resource_file(
                uuid4().hex, scope_type="tool_gallery", scope_id=tool_id,
                module_id=str(tool.get("module_id") or ""), resource_kind="Preview image",
                title=Path(file_name).stem.replace("-", " ").replace("_", " ").strip().title() or "Preview image",
                description="", file_name=file_name, mime_type=mime_type, file_data=file_bytes,
                sort_order=order, updated_by=user["user_id"],
            )
        if prepared:
            _clear_content_studio_caches(); _content_studio_flash(f"{len(prepared)} preview image{'s' if len(prepared) != 1 else ''} uploaded."); st.rerun()

def _render_content_studio_library_resources(user: dict, snapshot: dict[str, dict]) -> None:
    if not is_administrator(user):
        st.info("Only administrators can manage the Resources library.")
        return
    st.markdown("### Resources")
    st.caption("Publish searchable source records for papers, reports, websites and PDFs. Import MOSAIC repository entries as drafts or add resources manually, then link them to learning modules.")
    resources = _admin_library_resource_snapshot()
    _render_mosaic_repository_importer(user, resources)
    resource_ids = list(resources)
    module_ids = [mid for mid, module in snapshot.items() if not module.get("_cms_archived")]
    if resource_ids:
        resource_id = st.selectbox(
            "Resource to edit",
            resource_ids,
            format_func=lambda rid: f"{resources[rid]['title']} · {resources[rid]['origin']}" + (" · archived" if resources[rid].get("_cms_archived") else ""),
            key="studio-library-resource-select",
        )
        item = resources[resource_id]
        archived = bool(item.get("_cms_archived"))
        with st.form(f"studio-library-resource-form-{resource_id}"):
            title = st.text_input("Title", value=item.get("title", ""), key=f"studio-library-title-{resource_id}")
            a, b, c = st.columns([1, 1, 1])
            with a:
                origin = st.selectbox("Origin", ["MOSAIC content", "External content"], index=["MOSAIC content", "External content"].index(item.get("origin", "MOSAIC content")), key=f"studio-library-origin-{resource_id}")
            with b:
                resource_type = st.text_input("Type", value=item.get("resource_type", "Report"), key=f"studio-library-type-{resource_id}")
            with c:
                year = st.text_input("Year", value=item.get("year", ""), key=f"studio-library-year-{resource_id}")
            authors = st.text_input("Author(s) / organisation", value=item.get("authors", ""), key=f"studio-library-authors-{resource_id}")
            source_page_url = st.text_input(
                "Source page URL",
                value=item.get("source_page_url", ""),
                placeholder="https://mosaic-europe.eu/mosaic/resource/…",
                help="For imported MOSAIC records this is the original page in the MOSAIC Knowledge Repository.",
                key=f"studio-library-source-page-{resource_id}",
            )
            publication_url = st.text_input(
                "Publication / external URL",
                value=item.get("publication_url") or item.get("source_url", ""),
                placeholder="https://doi.org/… or https://zenodo.org/…",
                help="Optional link to the publication, DOI, Zenodo record or another authoritative external source.",
                key=f"studio-library-publication-url-{resource_id}",
            )
            description = st.text_area("Description", value=item.get("description", ""), height=100, key=f"studio-library-description-{resource_id}")
            tags_text = st.text_input("Keywords / tags", value=", ".join(item.get("tags") or []), key=f"studio-library-tags-{resource_id}")
            related_modules = st.multiselect(
                "Related learning modules",
                module_ids,
                default=[mid for mid in item.get("related_modules") or [] if mid in module_ids],
                format_func=lambda mid: snapshot[mid]["short_title"],
                key=f"studio-library-modules-{resource_id}",
            )
            sort_order = st.number_input("Sort order", min_value=0, max_value=10000, value=int(item.get("_cms_sort_order") or 0), step=10, key=f"studio-library-sort-{resource_id}")
            payload = {
                "id": resource_id,
                "title": title.strip(),
                "origin": origin,
                "resource_type": resource_type.strip() or "Resource",
                "authors": authors.strip(),
                "year": year.strip(),
                "publication_date": item.get("publication_date", ""),
                "source_page_url": source_page_url.strip(),
                "publication_url": publication_url.strip(),
                "source_url": publication_url.strip(),
                "description": description.strip(),
                "tags": [part.strip() for part in tags_text.split(",") if part.strip()],
                "related_modules": related_modules,
                "import_source": item.get("import_source", ""),
                "import_source_id": item.get("import_source_id", ""),
                "import_fingerprint": item.get("import_fingerprint", ""),
                "source_system": item.get("source_system", ""),
                "source_doc_id": item.get("source_doc_id", ""),
                "source_table_id": item.get("source_table_id", ""),
                "source_row_id": item.get("source_row_id", ""),
                "source_row_url": item.get("source_row_url", ""),
                "source_columns": item.get("source_columns", {}),
            }
            save_col, publish_col = st.columns(2)
            with save_col:
                save_resource = st.form_submit_button("Save resource draft", width="stretch")
            with publish_col:
                publish_resource = st.form_submit_button("Publish resource", type="primary", width="stretch", disabled=archived)
        if save_resource:
            if not title.strip():
                st.error("Add a resource title.")
            else:
                save_cms_library_resource_draft(resource_id, payload, int(sort_order), user["user_id"])
                _clear_content_studio_caches()
                _content_studio_flash("Resource draft saved.")
                st.rerun()
        if publish_resource:
            if not title.strip():
                st.error("Add a resource title.")
            else:
                publish_cms_library_resource(resource_id, payload, int(sort_order), user["user_id"])
                _clear_content_studio_caches()
                _content_studio_flash("Resource published to the searchable Resources page.")
                st.rerun()
        with st.expander("Archive / restore resource"):
            if archived:
                if st.button("Restore resource", key=f"studio-library-restore-{resource_id}", type="primary"):
                    set_cms_library_resource_archived(resource_id, False, user["user_id"], sort_order=int(item.get("_cms_sort_order") or 0))
                    _clear_content_studio_caches(); _content_studio_flash("Resource restored."); st.rerun()
            else:
                if st.button("Archive resource", key=f"studio-library-archive-{resource_id}"):
                    set_cms_library_resource_archived(resource_id, True, user["user_id"], sort_order=int(item.get("_cms_sort_order") or 0))
                    _clear_content_studio_caches(); _content_studio_flash("Resource archived."); st.rerun()
        _render_content_studio_resource_manager(
            user, scope_type="library", scope_id=resource_id, heading=f"PDF / attached files for {item['title']}", default_kind="PDF",
        )
    else:
        st.info("No Resources-page items exist yet.")

    with st.expander("＋ Add resource"):
        with st.form("studio-add-library-resource"):
            new_id = st.text_input("Resource ID", placeholder="drivers-d31", key="studio-new-library-id").strip().lower()
            new_title = st.text_input("Title", key="studio-new-library-title")
            a, b = st.columns(2)
            with a:
                new_origin = st.selectbox("Origin", ["MOSAIC content", "External content"], key="studio-new-library-origin")
            with b:
                new_type = st.text_input("Type", value="Report", key="studio-new-library-type")
            add_resource = st.form_submit_button("Create resource draft", type="primary")
        if add_resource:
            if not _valid_content_id(new_id):
                st.error("Use a lowercase resource ID with letters, numbers and hyphens.")
            elif new_id in resources:
                st.error("That resource ID already exists.")
            elif not new_title.strip():
                st.error("Add a resource title.")
            else:
                payload = {
                    "id": new_id,
                    "title": new_title.strip(),
                    "origin": new_origin,
                    "resource_type": new_type.strip() or "Resource",
                    "authors": "",
                    "year": "",
                    "publication_date": "",
                    "source_page_url": "",
                    "publication_url": "",
                    "source_url": "",
                    "description": "",
                    "tags": [],
                    "related_modules": [],
                    "import_source": "",
                    "import_source_id": "",
                    "import_fingerprint": "",
                }
                save_cms_library_resource_draft(new_id, payload, (len(resources) + 1) * 10, user["user_id"])
                _clear_content_studio_caches(); _content_studio_flash("Resource draft created. Add its source link and optional PDF before publishing."); st.rerun()


def _render_content_studio_tools(user: dict, snapshot: dict[str, dict]) -> None:
    if not is_administrator(user):
        st.info("Only administrators can manage tools and tool files.")
        return
    st.markdown("### Tools & files")
    st.caption(
        "Edit tool metadata and format, optionally link it to learning steps, add a card/detail image, attach resources, embed an external preview, or upload example images for a slider."
    )
    tools = _admin_tools_snapshot()
    tool_ids = sorted(tools, key=lambda value: str(tools[value].get("title") or value).casefold())

    lesson_choices: dict[str, str] = {}
    for module_id, module in snapshot.items():
        if module.get("_cms_archived"):
            continue
        for lesson in module.get("topics", []):
            if lesson.get("_cms_archived") or lesson.get("level") == "Convince":
                continue
            key = f"{module_id}::{lesson['id']}"
            lesson_choices[key] = f"{module.get('short_title', module_id)} · {lesson.get('level', '')} · {lesson.get('title', lesson['id'])}"

    if tool_ids:
        tool_id = st.selectbox(
            "Tool to edit",
            tool_ids,
            format_func=lambda value: (
                f"{tools[value]['title']} · archived" if tools[value].get("_cms_archived") else tools[value]["title"]
            ),
            key="studio-tool-select",
        )
        tool = tools[tool_id]
        archived = bool(tool.get("_cms_archived"))
        current_keys = [f"{module_id}::{lesson_id}" for module_id, lesson_id in _tool_lesson_links(tool)]
        for key in current_keys:
            if key not in lesson_choices:
                module_id, lesson_id = key.split("::", 1)
                lesson_choices[key] = f"{module_id} · {lesson_id} · unavailable/archived"

        with st.form(f"studio-tool-form-{tool_id}"):
            title = st.text_input("Tool title", value=tool.get("title", ""), key=f"studio-tool-title-{tool_id}")
            linked_keys = st.multiselect(
                "Linked learning step(s)",
                list(lesson_choices),
                default=[key for key in current_keys if key in lesson_choices],
                format_func=lambda value: lesson_choices.get(value, value),
                help="A learning step can have several tools, and the same tool may be linked to several steps.",
                key=f"studio-tool-links-{tool_id}",
            )
            status = st.selectbox(
                "Learner status",
                ["Available", "Under construction"],
                index=["Available", "Under construction"].index(
                    str(tool.get("status") or "Available")
                    if str(tool.get("status") or "Available") in {"Available", "Under construction"}
                    else "Available"
                ),
                help="Under-construction tools cannot be opened or downloaded by learners; they are directed to the MOSAIC newsletter sign-up instead.",
                key=f"studio-tool-status-{tool_id}",
            )
            sort_order = int(tool.get("_cms_sort_order") or 0)
            d, e = st.columns(2)
            with d:
                duration = st.text_input("Suggested time (optional)", value=tool.get("duration", ""), key=f"studio-tool-duration-{tool_id}")
            with e:
                current_format = tool.get("format", "Workshop") if tool.get("format", "Workshop") in TOOL_FORMATS else "Workshop"
                format_label = st.selectbox("Format", list(TOOL_FORMATS), index=list(TOOL_FORMATS).index(current_format), key=f"studio-tool-format-{tool_id}")
            website_url = st.text_input(
                "Website / external URL (optional)",
                value=tool.get("website_url", ""),
                placeholder="https://…",
                help="Use this for the main website, online model or digital tool learners should open.",
                key=f"studio-tool-website-{tool_id}",
            )
            preview_url = st.text_input(
                "Embedded preview URL (optional)",
                value=tool.get("preview_url", ""),
                placeholder="https://…",
                help="If the source allows iframe embedding, it will appear as a live preview on the tool page. Otherwise learners can still use the main website link.",
                key=f"studio-tool-preview-{tool_id}",
            )
            keywords_text = st.text_input(
                "Keywords",
                value=", ".join(tool.get("keywords") or []),
                help="Comma-separated terms used by the Tools search and filters.",
                key=f"studio-tool-keywords-{tool_id}",
            )
            description = st.text_area("Description", value=tool.get("description", ""), height=150, help="Free text. Explain what this item is, what it shows, or why it is useful. It does not need to produce an output.", key=f"studio-tool-description-{tool_id}")
            steps = st.text_area(
                "How to use it · one step per line (optional)",
                value="\n".join(tool.get("steps") or []),
                height=140,
                key=f"studio-tool-steps-{tool_id}",
            )
            selected_links = [
                {"module_id": key.split("::", 1)[0], "lesson_id": key.split("::", 1)[1]}
                for key in linked_keys
            ]
            primary_module = selected_links[0]["module_id"] if selected_links else ""
            primary_lesson = selected_links[0]["lesson_id"] if selected_links else ""
            payload = copy.deepcopy(tool)
            for key in list(payload):
                if str(key).startswith("_cms_"):
                    payload.pop(key, None)
            payload.update(
                {
                    "id": tool_id,
                    "title": title.strip(),
                    "module_id": primary_module,
                    "topic_id": primary_lesson,
                    "lesson_links": selected_links,
                    "status": status,
                    "duration": duration.strip(),
                    "format": format_label.strip(),
                    "description": description.strip(),
                    "website_url": website_url.strip(),
                    "preview_url": preview_url.strip(),
                    "keywords": [item.strip() for item in keywords_text.split(",") if item.strip()],
                    "steps": [line.strip() for line in steps.splitlines() if line.strip()],
                }
            )
            save_col, publish_col = st.columns(2)
            with save_col:
                save_tool = st.form_submit_button("Save tool draft", width="stretch")
            with publish_col:
                publish_tool = st.form_submit_button(
                    "Publish tool",
                    type="primary",
                    width="stretch",
                    disabled=archived,
                )
        if save_tool:
            if not title.strip():
                st.error("Add a tool title.")
            else:
                _content_studio_save_tool(tool_id, payload, int(sort_order), user["user_id"])
                _content_studio_flash("Tool draft saved.")
                st.rerun()
        if publish_tool:
            if not title.strip():
                st.error("Add a tool title.")
            else:
                _content_studio_publish_tool(tool_id, payload, int(sort_order), user["user_id"])
                _content_studio_flash("Tool published. Its learning-step links are now live.")
                st.rerun()

        with st.expander("Archive / restore tool"):
            if archived:
                if st.button("Restore tool", key=f"studio-tool-restore-{tool_id}", type="primary"):
                    set_cms_tool_archived(tool_id, False, user["user_id"], sort_order=int(tool.get("_cms_sort_order") or 0))
                    _clear_content_studio_caches()
                    _content_studio_flash("Tool restored.")
                    st.rerun()
            else:
                if st.button("Archive tool", key=f"studio-tool-archive-{tool_id}"):
                    set_cms_tool_archived(tool_id, True, user["user_id"], sort_order=int(tool.get("_cms_sort_order") or 0))
                    _clear_content_studio_caches()
                    _content_studio_flash("Tool archived. It is no longer shown in the House of Tools or linked learning steps.")
                    st.rerun()

        _render_content_studio_tool_image_manager(user, tool_id, tool)
        _render_content_studio_tool_gallery_manager(user, tool_id, tool)
        links = _tool_lesson_links(tool)
        resource_module_id = links[0][0] if links else str(tool.get("module_id") or "")
        _render_content_studio_resource_manager(
            user,
            scope_type="tool",
            scope_id=tool_id,
            module_id=resource_module_id,
            heading=f"Resources for {tool['title']} · multiple files allowed",
            default_kind="Resource",
        )
    else:
        st.info("No tools exist yet.")

    with st.expander("＋ Add tool"):
        with st.form("studio-add-tool"):
            new_tool_id = st.text_input("Tool ID", placeholder="new-tool", key="studio-new-tool-id").strip().lower()
            new_tool_title = st.text_input("Tool title", placeholder="New tool", key="studio-new-tool-title")
            new_tool_links = st.multiselect(
                "Linked learning step(s)",
                list(lesson_choices),
                format_func=lambda value: lesson_choices.get(value, value),
                help="Optional. You can publish an unlinked House of Tools item and link it later.",
                key="studio-new-tool-links",
            )
            new_tool_format = st.selectbox("Format", list(TOOL_FORMATS), key="studio-new-tool-format")
            new_tool_status = st.selectbox(
                "Learner status",
                ["Available", "Under construction"],
                key="studio-new-tool-status",
            )
            add_tool = st.form_submit_button("Create tool draft", type="primary")
        if add_tool:
            if not _valid_content_id(new_tool_id):
                st.error("Use a lowercase tool ID with letters, numbers and hyphens.")
            elif new_tool_id in tools:
                st.error("That tool ID already exists.")
            elif not new_tool_title.strip():
                st.error("Add a tool title.")
            else:
                links = [
                    {"module_id": key.split("::", 1)[0], "lesson_id": key.split("::", 1)[1]}
                    for key in new_tool_links
                ]
                payload = {
                    "id": new_tool_id,
                    "title": new_tool_title.strip(),
                    "module_id": links[0]["module_id"] if links else "",
                    "topic_id": links[0]["lesson_id"] if links else "",
                    "lesson_links": links,
                    "status": new_tool_status,
                    "duration": "",
                    "format": new_tool_format,
                    "description": "",
                    "website_url": "",
                    "preview_url": "",
                    "keywords": [],
                    "steps": [],
                }
                _content_studio_save_tool(new_tool_id, payload, (len(tools) + 1) * 10, user["user_id"])
                _content_studio_flash("New tool draft created. Add its description, optional links/previews, images and resources before publishing it.")
                st.rerun()


def _render_content_studio_people(user: dict) -> None:
    st.markdown("### Users & roles")
    st.caption(
        "Learners use published content. Editors can edit existing Understand/Apply lesson content and checks in drafts. Administrators can add/archive modules and lessons, publish content, manage communication/tool files, edit tools and manage roles."
    )
    users = _cached_users()
    if not users:
        st.info("No user accounts have been created yet.")
        return
    selected_user = st.selectbox(
        "Account",
        users,
        format_func=lambda item: f"{item.get('name') or 'Unnamed'} · {item.get('email') or item['user_id']}",
        key="studio-user-account",
    )
    role_options = ["learner", "editor", "administrator"]
    current_permission = selected_user.get("account_role") or "learner"
    if current_permission not in role_options:
        current_permission = "learner"
    selected_permission = st.selectbox(
        "Account permission",
        role_options,
        index=role_options.index(current_permission),
        format_func=lambda value: value.title(),
        key=f"studio-user-role-{selected_user['user_id']}",
    )
    if st.button("Update permission", type="primary", key="studio-update-role"):
        selected_email = str(selected_user.get("email") or "").strip().lower()
        if selected_permission != "administrator" and selected_email in _configured_admin_emails():
            st.error("Remove this email from ADMIN_EMAILS in Streamlit Secrets before demoting the account.")
        elif selected_user["user_id"] == user["user_id"] and selected_permission != "administrator":
            st.error("You cannot remove your own administrator access while signed in.")
        else:
            _save_account_role(selected_user["user_id"], selected_permission)
            _content_studio_flash("Account permission updated.")
            st.rerun()


def _render_content_studio_revisions() -> None:
    st.markdown("### Revision history")
    st.caption("Previous published module, lesson, idea and tool versions are kept for audit and future rollback tooling.")
    revisions = _cached_content_revisions()
    if not revisions:
        st.info("No publication revisions have been recorded yet. A revision is created when an already-published item is published again.")
        return
    rows = [
        {
            "Type": item.get("content_type", ""),
            "Module": item.get("module_id", ""),
            "Item": item.get("lesson_id", "") or item.get("module_id", ""),
            "Published by": item.get("published_by", ""),
            "Published at": item.get("published_at", ""),
        }
        for item in revisions
    ]
    st.dataframe(rows, width="stretch", hide_index=True)


def _render_content_studio_status(snapshot: dict[str, dict]) -> None:
    backend_name = "Supabase / PostgreSQL" if database_backend() == "postgres" else "local SQLite"
    auth_name = "OIDC configured" if auth_is_configured() else "local fallback"
    lesson_count = sum(
        1
        for module in snapshot.values()
        for lesson in module.get("topics", [])
        if lesson.get("level") != "Convince"
    )
    resource_count = len(_cached_resource_files(None, None, False))
    tool_count = sum(1 for tool in _admin_tools_snapshot().values() if not tool.get("_cms_archived"))
    metric_a, metric_b, metric_c, metric_d = st.columns(4)
    metric_a.metric("Database", backend_name)
    metric_b.metric("Authentication", auth_name)
    metric_c.metric("Learning structure", f"{len(snapshot)} modules · {lesson_count} lessons")
    metric_d.metric("Resources", f"{tool_count} tools · {resource_count} files")
    st.caption("Discover, Apply and Communicate classes can be imported. Linked library records appear at the bottom of their pages; existing team uploads remain available.")
    if database_backend() == "sqlite":
        st.info("Local mode stores users, progress, CMS drafts and uploaded resource files in mosaic_learn.db beside the app.")
    else:
        st.success("Production content, uploaded resources and learner data are stored in PostgreSQL. CMS tables are protected by the same server-only RLS/PostgREST hardening as the rest of the app.")



# Canonical route URLs. This remains a single-file Streamlit app, but each
# top-level view gets a stable query-string URL so links can be bookmarked and
# browser Back/Forward can restore the previous view.
URL_ROUTE_ALIASES = {
    "home": "home",
    "our-story": "our-story",
    "story": "our-story",
    "catalogue": "catalogue",
    "modules": "catalogue",
    "learning": "learning",
    "my-learning": "learning",
    "resources": "resources",
    "tools": "tools",
    "glossary": "glossary",
    "contact": "contact",
    "privacy": "privacy",
    "community": "community",
    "module": "module",
    "phase": "phase",
    "discover": "phase",
    "apply": "phase",
    "topic": "topic",
    "lesson": "topic",
    "convince": "convince",
    "profile": "profile",
    "admin": "admin",
    "results": "results",
}
ROUTE_TO_URL_PAGE = {
    "home": "home",
    "our-story": "our-story",
    "catalogue": "modules",
    "learning": "my-learning",
    "resources": "resources",
    "tools": "tools",
    "glossary": "glossary",
    "contact": "contact",
    "privacy": "privacy",
    "community": "community",
    "module": "module",
    "phase": "phase",
    "topic": "lesson",
    "convince": "convince",
    "profile": "profile",
    "admin": "admin",
    "results": "results",
}


def _query_params_dict() -> dict[str, str]:
    result: dict[str, str] = {}
    try:
        for key in st.query_params:
            value = st.query_params.get(key, "")
            if isinstance(value, (list, tuple)):
                value = value[-1] if value else ""
            result[str(key)] = str(value or "")
    except Exception:
        pass
    return result


def _replace_query_params(values: dict[str, str]) -> None:
    """Replace URL query state only when it actually changed.

    Avoiding no-op writes matters for browser history: recent Streamlit versions
    intentionally skip duplicate history entries when the query string is
    unchanged.
    """
    desired = {str(k): str(v) for k, v in values.items() if str(v) != ""}
    current = _query_params_dict()
    if current == desired:
        return
    try:
        if hasattr(st.query_params, "from_dict"):
            st.query_params.from_dict(desired)
        else:
            st.query_params.clear()
            for key, value in desired.items():
                st.query_params[key] = value
    except Exception:
        # Session State still provides functional navigation on an older runtime.
        pass


def _write_route_query(
    route: str,
    *,
    module_id: str | None = None,
    topic_id: str | None = None,
    tool_id: str | None = None,
) -> None:
    page = ROUTE_TO_URL_PAGE.get(str(route), str(route))
    params: dict[str, str] = {"page": page}

    # Preserve Content Studio sub-navigation when staying inside admin.
    if route == "admin":
        admin_section = _query_param_text("admin")
        admin_view = _query_param_text("admin_view")
        if admin_section:
            params["admin"] = admin_section
        if admin_view:
            params["admin_view"] = admin_view

    if route in {"module", "phase", "topic", "convince", "tools"}:
        module_value = str(module_id or st.session_state.get("module_id") or "").strip()
        if module_value:
            params["module"] = module_value
    if route == "phase":
        phase_value = str(st.session_state.get("phase") or "discover").lower()
        params["phase"] = phase_value if phase_value in {"discover", "apply"} else "discover"
    if route in {"topic", "tools"}:
        topic_value = str(topic_id or st.session_state.get("topic_id") or "").strip()
        if topic_value:
            params["topic"] = topic_value
    if route == "tools":
        tool_value = str(tool_id or st.session_state.get("tool_id") or "").strip()
        if tool_value:
            params["tool"] = tool_value

    _replace_query_params(params)


def _apply_route_from_query() -> str:
    """Load the current browser URL into Session State.

    The URL is authoritative for top-level navigation. This is what makes a
    browser Back/Forward action restore the previous MOSAIC Learn page instead
    of leaving Session State on the newer page.
    """
    page = _query_param_text("page").lower()
    if not page and _query_param_text("admin"):
        page = "admin"  # upgrade existing Content Studio URLs from v4
    if not page and _query_param_text("home"):
        page = "home"  # backwards compatibility with older wordmark links
    route = URL_ROUTE_ALIASES.get(page, "home") if page else "home"
    st.session_state["route"] = route

    module_value = _query_param_text("module")
    topic_value = _query_param_text("topic") or _query_param_text("lesson")
    tool_value = _query_param_text("tool")

    if module_value:
        st.session_state["module_id"] = module_value
    elif route in {"module", "phase", "topic", "convince"}:
        # A bookmarked page without ?module= must not inherit the previous
        # class's module from Session State.
        st.session_state.pop("module_id", None)
    if route == "phase":
        phase_value = _query_param_text("phase").lower()
        st.session_state["phase"] = (phase_value if phase_value in {"discover", "apply"}
                                     else "apply" if page == "apply" else "discover")
    else:
        st.session_state.pop("phase", None)
    if route in {"topic", "tools"} and topic_value:
        st.session_state["topic_id"] = topic_value
    else:
        # Prevent an incomplete URL from opening an unrelated previous class.
        st.session_state.pop("topic_id", None)
    if route == "tools" and tool_value:
        st.session_state["tool_id"] = tool_value
    else:
        st.session_state.pop("tool_id", None)

    return route


CONTENT_STUDIO_SECTION_SLUGS = {
    "Modules & lessons": "structure",
    "Ideas & content": "ideas",
    "Checks & quizzes": "checks",
    "Communicate: uploaded files": "convince",
    "Tools & files": "tools",
    "Resources": "resources",
    "Our stories": "stories",
    "Users & roles": "users",
    "Revision history": "revisions",
    "Deployment": "deployment",
    "Superhuman Docs import": "superhuman",
}
CONTENT_STUDIO_SLUG_SECTIONS = {value: key for key, value in CONTENT_STUDIO_SECTION_SLUGS.items()}


def _query_param_text(name: str) -> str:
    try:
        value = st.query_params.get(name, "")
    except Exception:
        return ""
    if isinstance(value, (list, tuple)):
        value = value[-1] if value else ""
    return str(value or "").strip()


def _set_query_param(name: str, value: str | None) -> None:
    params = _query_params_dict()
    clean_value = str(value or "").strip()
    if clean_value:
        params[name] = clean_value
    else:
        params.pop(name, None)
    _replace_query_params(params)


def _sync_content_studio_section_query() -> None:
    section = str(st.session_state.get("content-studio-section") or "")
    _set_query_param("admin", CONTENT_STUDIO_SECTION_SLUGS.get(section))


def _sync_content_studio_structure_query() -> None:
    view = str(st.session_state.get("content-studio-structure") or "Modules")
    _set_query_param("admin_view", "lessons" if view == "Lessons" else "modules")


def _queue_widget_selection(widget_key: str, value: str) -> None:
    """Queue a widget value for the next rerun.

    Streamlit does not allow Session State for an already-instantiated widget to
    be changed later in the same run. Structural idea actions therefore queue
    the next carousel screen instead of mutating the selectbox key directly.
    """
    st.session_state[f"_pending-widget::{widget_key}"] = value


def _apply_queued_widget_selection(widget_key: str, valid_values: list[str]) -> bool:
    pending_key = f"_pending-widget::{widget_key}"
    if pending_key not in st.session_state:
        return False
    value = str(st.session_state.pop(pending_key) or "")
    if value in valid_values:
        st.session_state[widget_key] = value
        return True
    return False


def _persist_idea_draft_if_valid(
    module_id: str,
    topic_id: str,
    payload: dict,
    topic: dict,
    user_id: str,
    working_key: str,
) -> bool:
    """Persist structural/image changes immediately without publishing them."""
    cards = payload.get("cards") if isinstance(payload, dict) else []
    if not isinstance(cards, list) or any(not str(card.get("title") or "").strip() for card in cards if isinstance(card, dict)):
        return False
    cleaned = normalize_carousel_payload(payload, topic)
    if len(cleaned.get("cards") or []) != len(cards):
        return False
    save_carousel_draft(module_id, topic_id, cleaned, user_id)
    st.session_state[working_key] = cleaned
    _clear_content_studio_caches()
    return True


def page_our_story(user: dict | None):
    stories = _published_stories()
    st.markdown(
        """
        <div class="m-story-hero">
            <div class="m-kicker">Our story</div>
            <h1>Land-use decisions, told from the ground</h1>
            <p>MOSAIC explores how to manage land more sustainably by bringing researchers,
               policy makers, practitioners and land users together in Policy Labs across Europe.
               Interviews and research on the drivers of land-use change, collaborative future
               pathways and land-use models help connect what people need with what policy can do.</p>
        </div>
        <section class="m-story-introduction" aria-label="From MOSAIC research to practical lessons">
            <div><strong>From research to practical lessons</strong>
            <p>Our Policy Labs bring different perspectives into the same conversation.
               The stories below show what the project learned about decisions made on real land,
               and what policy makers, practitioners and academics can take into their own work.
               They are examples to learn from, not claims that every proposed response was already tested.</p></div>
            <div class="m-story-methods" aria-label="MOSAIC approaches"><span>Policy Labs</span><span>Drivers research</span><span>Future pathways</span><span>Land-use models</span></div>
        </section>
        """,
        unsafe_allow_html=True,
    )
    if not stories:
        st.info("No stories are published yet.")
        return

    selected_id = str(st.session_state.get("our-story-selected") or stories[0]["id"])
    if selected_id not in {story["id"] for story in stories}:
        selected_id = stories[0]["id"]

    if len(stories) > 1:
        cols = st.columns(min(3, len(stories)), gap="medium")
        for index, story in enumerate(stories):
            with cols[index % len(cols)]:
                st.markdown(
                    f"""
                    <div class="m-story-card">
                        <div class="place">{escape(story['place'])}</div>
                        <h3>{escape(story['title'])}</h3>
                        <p>{escape(story['intro'][:180] + ('…' if len(story['intro']) > 180 else ''))}</p>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                if st.button("Read story →", key=f"read-story-{story['id']}", width="stretch"):
                    st.session_state["our-story-selected"] = story["id"]
                    st.rerun()

    story = next(item for item in stories if item["id"] == selected_id)
    source_html = ""
    if story.get("source_url") and _valid_external_url(story["source_url"]):
        source_html = (f'<div class="m-story-source">Source: <a href="{escape(story["source_url"], quote=True)}" '
                       f'target="_blank" rel="noopener noreferrer">{escape(story.get("source_label") or "MOSAIC research")}</a></div>')
    elif story.get("source_label"):
        source_html = f'<div class="m-story-source">Source: {escape(story["source_label"])}</div>'
    photo = asset_image_html(story.get("image_asset"),
                             alt=f"Landscape photographs illustrating {story['place']}",
                             css_class="m-story-photo-image")
    visual = (f'<figure class="m-story-photo">{photo}'
              f'<figcaption>{escape(story.get("image_caption") or story["place"])}</figcaption></figure>') if photo else ""
    st.markdown(
        f"""
        <article class="m-story-detail m-story-detail-grid{' has-photo' if visual else ''}">
            <div class="m-story-main">
                <div class="place">{escape(story['place'])}</div>
                <h2>{escape(story['title'])}</h2>
                <p>{escape(story['intro'])}</p>
                <p>{escape(story['case_body'])}</p>
                <h3>{escape(story['response_heading'])}</h3>
                <p>{escape(story['response_body'])}</p>
                <div class="m-story-lesson">The lesson: {escape(story['lesson'])}</div>
                {source_html}
            </div>
            {visual}
        </article>
        """,
        unsafe_allow_html=True,
    )
    if story.get("video_url"):
        st.video(story["video_url"])


def _render_content_studio_stories(user: dict) -> None:
    """Administrator story editor. Built-in stories become CMS records when saved."""
    st.subheader("Our stories")
    st.caption("Create, edit, publish and archive stories shown on the public Our story page.")
    snapshot = _story_admin_snapshot()
    active_ids = [story_id for story_id, row in snapshot.items() if not row.get("archived")]
    archived_ids = [story_id for story_id, row in snapshot.items() if row.get("archived")]

    create_col, archive_col = st.columns([2, 1])
    with create_col:
        new_title = st.text_input("New story title", key="story-new-title", placeholder="e.g. When water changes what a farm can become")
        if st.button("Add story", key="story-add", type="primary", disabled=not new_title.strip()):
            base = re.sub(r"[^a-z0-9]+", "-", new_title.casefold()).strip("-") or f"story-{uuid4().hex[:8]}"
            story_id = base
            suffix = 2
            while story_id in snapshot:
                story_id = f"{base}-{suffix}"
                suffix += 1
            payload = _normalise_story_payload(story_id, {"title": new_title.strip()})
            sort_order = max([int(row.get("sort_order") or 0) for row in snapshot.values()] + [0]) + 10
            save_cms_story_draft(story_id, payload, sort_order, user["user_id"])
            _clear_content_studio_caches()
            st.session_state["story-admin-select"] = story_id
            st.session_state["content-studio-flash"] = "Story draft created."
            st.rerun()
    with archive_col:
        st.metric("Published / active", len(active_ids))

    if not snapshot:
        st.info("Create the first story above.")
        return

    ordered_ids = sorted(snapshot, key=lambda story_id: (int(snapshot[story_id].get("sort_order") or 0), story_id))
    labels = {
        story_id: f"{(snapshot[story_id].get('draft') or snapshot[story_id].get('published') or DEFAULT_STORIES.get(story_id, {})).get('title', story_id)}{' · archived' if snapshot[story_id].get('archived') else ''}"
        for story_id in ordered_ids
    }
    selected_id = st.selectbox(
        "Story",
        ordered_ids,
        format_func=lambda story_id: labels[story_id],
        key="story-admin-select",
    )
    row = snapshot[selected_id]
    content = _normalise_story_payload(selected_id, row.get("draft") or row.get("published") or DEFAULT_STORIES.get(selected_id, {}))

    with st.form(f"story-editor-{selected_id}"):
        title = st.text_input("Title / opening question", value=content["title"])
        place = st.text_input("Place", value=content["place"], placeholder="Belgium · Flemish Ardennes")
        intro = st.text_area("Opening", value=content["intro"], height=120)
        case_body = st.text_area("What happens on the ground", value=content["case_body"], height=150)
        response_heading = st.text_input("Response heading", value=content["response_heading"])
        response_body = st.text_area("How MOSAIC methods help", value=content["response_body"], height=150)
        lesson = st.text_area("Lesson", value=content["lesson"], height=90)
        source_label = st.text_input("Source label", value=content["source_label"])
        source_url = st.text_input("Source URL", value=content["source_url"])
        video_url = st.text_input("Optional video URL", value=content["video_url"])
        image_asset = st.text_input("Optional image in assets/ (e.g. stories/alentejo-landscapes.jpg)",
                                    value=content["image_asset"])
        image_caption = st.text_input("Image caption / credit", value=content["image_caption"])
        sort_order = st.number_input("Order", min_value=0, value=int(row.get("sort_order") or 0), step=10)
        save_draft = st.form_submit_button("Save draft", type="primary")
        publish_story = st.form_submit_button("Publish story")

    payload = _normalise_story_payload(
        selected_id,
        {
            "title": title,
            "place": place,
            "intro": intro,
            "case_body": case_body,
            "response_heading": response_heading,
            "response_body": response_body,
            "lesson": lesson,
            "source_label": source_label,
            "source_url": source_url,
            "video_url": video_url,
            "image_asset": image_asset,
            "image_caption": image_caption,
        },
    )
    if save_draft:
        save_cms_story_draft(selected_id, payload, int(sort_order), user["user_id"])
        _clear_content_studio_caches()
        st.session_state["content-studio-flash"] = "Story draft saved."
        st.rerun()
    if publish_story:
        publish_cms_story(selected_id, payload, int(sort_order), user["user_id"])
        _clear_content_studio_caches()
        st.session_state["content-studio-flash"] = "Story published."
        st.rerun()

    action_a, action_b = st.columns(2)
    with action_a:
        if row.get("archived") and st.button("Restore story", key=f"story-restore-{selected_id}"):
            set_cms_story_archived(selected_id, False, user["user_id"], sort_order=int(sort_order))
            _clear_content_studio_caches()
            st.rerun()
    with action_b:
        if not row.get("archived") and st.button("Archive story", key=f"story-archive-{selected_id}"):
            set_cms_story_archived(selected_id, True, user["user_id"], sort_order=int(sort_order))
            _clear_content_studio_caches()
            st.rerun()

    if archived_ids:
        st.caption(f"Archived stories: {len(archived_ids)}")

# Import controls are loaded with the rest of the studio, never on public pages.
# _render_superhuman_import is defined directly above page_admin.


def _sh_download_image(url: str, *, max_bytes: int = 8 * 1024 * 1024) -> tuple[bytes, str, str]:
    """Download an image from a trusted Coda host during a manual import.

    Module covers can use a higher input limit because their pixels are
    downsized to a small WEBP before persisting. The same function is used
    for lesson figures with the existing stricter default limit.
    """
    import requests
    parsed = urlparse(str(url or ""))
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not any(
        host == root or host.endswith("." + root)
        for root in ("codahosted.io", "coda.io")
    ):
        raise ValueError("Image host not supported for persisted imports")
    response = requests.get(url, timeout=25, allow_redirects=False, stream=True)
    try:
        response.raise_for_status()
        if response.is_redirect:
            raise ValueError("Image URL redirected; add a direct Superhuman Docs image URL")
        header_size = response.headers.get("Content-Length")
        if header_size:
            try:
                if int(header_size) > max_bytes:
                    raise ValueError(f"Image exceeds the {max_bytes // (1024 * 1024)} MB import limit")
            except (TypeError, ValueError) as exc:
                if "exceeds" in str(exc):
                    raise
        data = bytearray()
        for chunk in response.iter_content(chunk_size=65536):
            data.extend(chunk)
            if len(data) > max_bytes:
                raise ValueError(f"Image exceeds the {max_bytes // (1024 * 1024)} MB import limit")
    finally:
        response.close()
    mime = str(response.headers.get("Content-Type") or "").split(";")[0].strip().lower()
    recognized = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp", "image/gif": ".gif"}
    # Coda's asset CDN can serve an image as application/octet-stream.
    # Only accept it after verifying the actual image format in the bytes.
    if mime not in recognized:
        if mime not in {"application/octet-stream", "binary/octet-stream", ""}:
            raise ValueError(f"Unexpected image content type: {mime or 'unknown'}")
        try:
            from PIL import Image
            image = Image.open(io.BytesIO(data))
            detected = str(image.format or "").upper()
            image.verify()
            mime = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp", "GIF": "image/gif"}.get(detected, "")
        except Exception as exc:
            raise ValueError("Downloaded file is not a supported image") from exc
        if not mime:
            raise ValueError("Downloaded file is not a supported image")
    return bytes(data), mime, recognized[mime]


def _sh_trusted_download_url(url: str) -> bool:
    parsed = urlparse(str(url or ""))
    if parsed.scheme != "https" or not parsed.hostname:
        return False
    host = parsed.hostname.lower()
    return any(host == allowed or host.endswith("." + allowed)
               for allowed in ("codahosted.io", "coda.io", "superhuman.com"))


def _sh_download_tool_attachment(url: str) -> tuple[bytes, str, str]:
    """Download Coda-hosted attachments once at manual import, not on page views."""
    if not _sh_trusted_download_url(url):
        raise ValueError("Only Superhuman Docs-hosted file URLs are imported")
    import requests
    response = requests.get(url, stream=True, timeout=20, allow_redirects=False)
    response.raise_for_status()
    mime = str(response.headers.get("Content-Type") or "").split(";")[0].strip().lower()
    extensions = {"application/pdf": ".pdf", "application/zip": ".zip",
                  "text/csv": ".csv", "text/plain": ".txt",
                  "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
                  "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
                  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
                  "image/png": ".png", "image/jpeg": ".jpg"}
    if mime not in extensions and mime not in {"application/octet-stream", "binary/octet-stream"}:
        raise ValueError(f"Unsupported attachment MIME type: {mime or 'unknown'}")
    content = bytearray()
    for chunk in response.iter_content(chunk_size=65536):
        content.extend(chunk)
        if len(content) > 15 * 1024 * 1024:
            raise ValueError("Attachment exceeds 15 MB limit")
    if mime in {"application/octet-stream", "binary/octet-stream"}:
        if bytes(content).startswith(b"%PDF-"):
            mime = "application/pdf"
        else:
            raise ValueError("Unknown attachment format")
    if mime == "application/pdf" and not bytes(content).startswith(b"%PDF-"):
        raise ValueError("PDF download did not contain a PDF")
    return bytes(content), mime, extensions[mime]


def _sh_commit_preview(preview: dict, selection: list[str], *, publish: bool, user_id: str, archive_phase_pages: bool = False) -> dict:
    """Import only reviewer-selected records; keep IDs stable to retain progress.

    Per-record CMS saves are already transactional. A failed record is reported;
    previous published records are not removed or archived automatically.
    """
    selected = set(selection)
    results = {"saved": 0, "published": 0, "skipped": 0, "images": 0,
               "images_skipped": 0, "module_covers": [], "archived_phase_duplicates": 0,
               "warnings": [], "errors": []}
    docs = preview.get("environment") or {}
    for entry in preview.get("entries") or []:
        tag = f"{entry['kind']}:{entry['module_id']}:{entry['id']}"
        if tag not in selected:
            results["skipped"] += 1
            continue
        item = copy.deepcopy(entry["payload"])
        mid, lid = entry["module_id"], entry["id"]
        try:
            if entry["kind"] == "module":
                if item.pop("_convince_export_failed", False):
                    results["errors"].append(
                        f"Module '{item.get('title')}': a phase page could not be exported; "
                        "module update was skipped to protect existing download links."
                    )
                    results["skipped"] += 1
                    continue
                cover_url = str(item.get("cover_image_url") or "")
                backup_cover = str(item.pop("cover_image_fallback_url", "") or "")
                item.pop("cover_image_source", None)  # Preview-only metadata.
                cover_candidates = list(dict.fromkeys(u for u in (cover_url, backup_cover)
                                                      if u and _sh_trusted_download_url(u)))
                cover_stored = False
                for candidate_url in cover_candidates:
                    cover_id = "sh-cover-" + hashlib.sha256(
                        f"{docs.get('source_doc_id')}:{mid}:{candidate_url}".encode()
                    ).hexdigest()[:24]
                    existing_cover = get_cms_resource_file(cover_id)
                    try:
                        if not existing_cover or not existing_cover.get("file_data"):
                            cover_bytes, mime, ext = _sh_download_image(candidate_url, max_bytes=24 * 1024 * 1024)
                            try:
                                from PIL import Image, ImageOps
                                image = ImageOps.exif_transpose(Image.open(io.BytesIO(cover_bytes)))
                                image.thumbnail((1600, 1200))
                                output = io.BytesIO()
                                image.save(output, format="WEBP", quality=82, method=4)
                                cover_bytes, mime, ext = output.getvalue(), "image/webp", ".webp"
                            except Exception:
                                pass  # Keep the original verified image bytes.
                            save_cms_resource_file(
                                cover_id, scope_type="library", scope_id=mid,
                                module_id=mid, resource_kind="Image", title="Module cover image",
                                file_name=cover_id + ext, mime_type=mime,
                                file_data=cover_bytes, updated_by=user_id,
                            )
                            results["images"] += 1
                        # Verify the stored bytes are readable before promising a cover.
                        saved_cover = get_cms_resource_file(cover_id)
                        if not saved_cover or not saved_cover.get("file_data"):
                            raise ValueError("Cover was not returned by the file store after saving")
                        item["cover_image_resource_id"] = cover_id
                        item["cover_image_url"] = candidate_url
                        cover_stored = True
                        results["module_covers"].append(f"{item['title']}: image stored and attached to module")
                        break
                    except Exception as ex:
                        # A broken/oversized image must not prevent the module
                        # text, class ordering or linked resources from importing.
                        results["images_skipped"] += 1
                        results["warnings"].append(
                            f"Module '{item['title']}': image skipped ({str(ex)[:120]}). "
                            "The module content was still imported."
                        )
                if not cover_stored:
                    # A missing or unexportable source image must not erase a
                    # previously imported cover or prevent text from publishing.
                    old_module = get_cms_module(mid) or {}
                    old_content = old_module.get("published") or old_module.get("draft") or {}
                    prior_id = str(old_content.get("cover_image_resource_id") or "")
                    if prior_id and (get_cms_resource_file(prior_id) or {}).get("file_data"):
                        item["cover_image_resource_id"] = prior_id
                        item["cover_image_url"] = str(old_content.get("cover_image_url") or "")
                        results["module_covers"].append(f"{item['title']}: previous cover retained")
                    else:
                        item["cover_image_resource_id"] = ""
                        item["cover_image_url"] = ""
                        results["module_covers"].append(f"{item['title']}: no usable cover; illustration fallback")
                        if not cover_candidates:
                            results["warnings"].append(
                                f"Module '{item['title']}': no image was found in the exported module landing page. "
                                "Check the module image preview and confirm you selected/published the module page."
                            )
                missing_native_attachment = False
                for file_entry in (item.get("convince") or {}).get("linked_files") or []:
                    url = str(file_entry.get("url") or "")
                    if not publish or not _sh_trusted_download_url(url):
                        continue  # Drafts are metadata-only; external links remain links.
                    resource_id = "sh-convince-file-" + hashlib.sha256(
                        f"{mid}:{url}".encode()).hexdigest()[:24]
                    existing_file = get_cms_resource_file(resource_id)
                    try:
                        if not existing_file or not existing_file.get("file_data"):
                            data, mime, ext = _sh_download_tool_attachment(url)
                            title = str(file_entry.get("title") or "Document").strip()
                            file_name = _safe_resource_filename(title)
                            known_exts = {".pdf", ".docx", ".pptx", ".xlsx", ".zip", ".csv", ".txt"}
                            if Path(file_name).suffix.casefold() not in known_exts:
                                file_name += ext
                            save_cms_resource_file(
                                resource_id, scope_type="library", scope_id=mid,
                                module_id=mid, resource_kind="Convince document",
                                title=title, file_name=file_name, mime_type=mime,
                                file_data=data, updated_by=user_id,
                            )
                            results["convince_files"] = results.get("convince_files", 0) + 1
                        file_entry["resource_id"] = resource_id
                    except Exception as ex:
                        if file_entry.get("source") == "attachment":
                            missing_native_attachment = True
                            results["errors"].append(
                                f"Convince attachment '{file_entry.get('title')}': {str(ex)[:120]}. "
                                "Module was not published; a local download is required for native Coda files."
                            )
                        else:
                            results["errors"].append(
                                f"Convince file link '{file_entry.get('title')}': could not store a copy "
                                f"({str(ex)[:120]}). The link will remain available to open."
                            )
                if publish and missing_native_attachment:
                    results["skipped"] += 1
                    continue
                if publish:
                    _content_studio_publish_module(mid, item, entry["sort_order"], user_id)
                    results["published"] += 1
                else:
                    _content_studio_save_module(mid, item, entry["sort_order"], user_id)
                results["saved"] += 1
            elif entry["kind"] == "lesson":
                if publish and item.get("_incomplete_quiz"):
                    results["errors"].append(f"{item['title']}: quiz is incomplete in Superhuman Docs. Fill in its answer and feedback, then re-preview before publishing.")
                    results["skipped"] += 1
                    continue
                missing_images = []
                for card in item.get("theory_cards") or []:
                    image_urls = list(dict.fromkeys(card.get("image_src_imports") or
                                                 ([card["image_src_import"]] if card.get("image_src_import") else [])))
                    stored_ids = []
                    for url in image_urls:
                        resource_id = "sh-image-" + hashlib.sha256(
                            f"{docs.get('source_doc_id')}:{lid}:{card['editor_id']}:{url}".encode()
                        ).hexdigest()[:24]
                        existing = get_cms_resource_file(resource_id)
                        if not existing or not existing.get("file_data"):
                            try:
                                data, mime, ext = _sh_download_image(url)
                                save_cms_resource_file(
                                    resource_id, scope_type="idea",
                                    scope_id=_idea_image_scope_id(mid, lid, card["editor_id"]),
                                    module_id=mid, resource_kind="Image",
                                    title=str(card.get("title") or "Class figure"),
                                    file_name=resource_id + ext, mime_type=mime,
                                    file_data=data, updated_by=user_id,
                                )
                                results["images"] += 1
                            except Exception as ex:
                                missing_images.append(f"{card.get('title')}: {str(ex)[:110]}")
                                continue
                        stored_ids.append(resource_id)
                    card["image_resource_ids"] = stored_ids
                    card["image_resource_id"] = stored_ids[0] if stored_ids else ""
                if missing_images:
                    results["images_skipped"] += len(missing_images)
                    results["warnings"].append(
                        f"{item['title']}: {len(missing_images)} image(s) omitted — "
                        f"{' ; '.join(missing_images)}. "
                        "The class text, activities and links were still imported."
                    )
                if publish:
                    _content_studio_publish_lesson(mid, lid, item, entry["sort_order"], user_id)
                    results["published"] += 1
                else:
                    _content_studio_save_lesson(mid, lid, item, entry["sort_order"], user_id)
                results["saved"] += 1
        except Exception as ex:
            results["errors"].append(f"{entry.get('kind')} {item.get('title')}: {str(ex)[:140]}")
    for kind in ("resource", "tool"):
        for index, item in enumerate((preview.get("libraries") or {}).get(kind) or [], start=1):
            tag = f"{kind}:{item['id']}"
            if tag not in selected:
                results["skipped"] += 1
                continue
            try:
                if kind in {"resource", "tool"}:
                    for link in item.get("attachment_links") or []:
                        url = str(link.get("url") or "")
                        if not _sh_trusted_download_url(url):
                            continue  # Retain the external link; do not fetch arbitrary URLs.
                        resource_id = f"sh-{kind}-file-" + hashlib.sha256(f"{item['id']}:{url}".encode()).hexdigest()[:24]
                        existing_file = get_cms_resource_file(resource_id)
                        if existing_file and existing_file.get("file_data"):
                            continue
                        try:
                            data, mime, ext = _sh_download_tool_attachment(url)
                            safe_title = str(link.get("title") or "Supporting file")[:100]
                            name = _safe_resource_filename(safe_title)
                            if not Path(name).suffix:
                                name += ext
                            save_cms_resource_file(resource_id, scope_type="library" if kind == "resource" else "tool",
                                                   scope_id=item["id"], module_id="", resource_kind="File", title=safe_title,
                                                   file_name=name, mime_type=mime, file_data=data,
                                                   updated_by=user_id)
                            results["attachments"] = results.get("attachments", 0) + 1
                        except Exception as ex:
                            results["errors"].append(f"{item['title']} attachment {link.get('title')}: {str(ex)[:125]}")
                if kind == "tool":
                    # Image-column cells use an actual Coda-hosted URL from the
                    # rich API; the simple API exposes only 'Europe.png'.
                    # Persist bytes once so learner pages never need the API.
                    previous = get_cms_tool(item["id"])
                    previous_payload = ((previous or {}).get("published") or
                                        (previous or {}).get("draft") or {})
                    if previous_payload.get("image_resource_id"):
                        item["image_resource_id"] = previous_payload["image_resource_id"]
                    image_url = str(item.get("image_url") or "")
                    if image_url:
                        image_resource_id = "sh-tool-image-" + hashlib.sha256(
                            f"{item['id']}:{image_url}".encode()).hexdigest()[:24]
                        cached_image = get_cms_resource_file(image_resource_id)
                        if cached_image and cached_image.get("file_data"):
                            item["image_resource_id"] = image_resource_id
                        else:
                            try:
                                image_data, image_mime, image_ext = _sh_download_image(
                                    image_url, max_bytes=24 * 1024 * 1024)
                                # Resize source figures to avoid excessive DB
                                # storage and long page downloads.
                                from PIL import Image, ImageOps
                                picture = ImageOps.exif_transpose(Image.open(io.BytesIO(image_data)))
                                picture.thumbnail((1800, 1300))
                                image_out = io.BytesIO()
                                picture.save(image_out, format="WEBP", quality=88, method=6)
                                image_data, image_mime, image_ext = (
                                    image_out.getvalue(), "image/webp", ".webp")
                                save_cms_resource_file(
                                    image_resource_id, scope_type="tool_image",
                                    scope_id=item["id"], resource_kind="Image",
                                    title=str(item.get("title") or "Tool") + " illustration",
                                    description=str(item.get("image_name") or ""),
                                    file_name=image_resource_id + image_ext,
                                    mime_type=image_mime, file_data=image_data,
                                    sort_order=-100, updated_by=user_id,
                                )
                                item["image_resource_id"] = image_resource_id
                                results["images"] += 1
                            except Exception as ex:
                                results["images_skipped"] += 1
                                results["warnings"].append(
                                    f"Tool '{item['title']}': image could not be saved "
                                    f"({str(ex)[:140]}). Existing illustration, if any, was retained.")
                    elif item.get("_unresolved_image"):
                        results["warnings"].append(
                            f"Tool '{item['title']}': only the filename "
                            f"'{item.get('image_name')}' was returned, not an image URL. "
                            "Existing illustration was retained if available.")
                if kind == "resource":
                    if publish:
                        publish_cms_library_resource(item["id"], _normalise_library_resource_payload(item["id"], item), item.get("_source_sort_order", index * 10), user_id)
                    else:
                        save_cms_library_resource_draft(item["id"], _normalise_library_resource_payload(item["id"], item), item.get("_source_sort_order", index * 10), user_id)
                else:
                    if publish:
                        _content_studio_publish_tool(item["id"], item, item.get("_source_sort_order", index * 10), user_id)
                    else:
                        _content_studio_save_tool(item["id"], item, item.get("_source_sort_order", index * 10), user_id)
                results["saved"] += 1
                if publish:
                    results["published"] += 1
            except Exception as ex:
                results["errors"].append(f"{kind} '{item.get('title')}': {str(ex)[:130]}")
    if publish and results["published"] and preview.get("environment_verified"):
        try:
            save_active_learning_environment(docs)
        except Exception as ex:
            results["errors"].append(f"Environment title could not be saved: {str(ex)[:140]}")
    _clear_content_studio_caches()
    if publish and archive_phase_pages:
        for candidate in preview.get("obsolete_phase_lesson_candidates") or []:
            mid, lid = candidate["module_id"], candidate["lesson_id"]
            existing = get_cms_lesson(mid, lid)
            if not existing or existing.get("archived"):
                continue
            source = existing.get("published") or existing.get("draft") or {}
            # Never archive a manually authored class or a similarly named
            # page: the original, immutable Coda page ID must match exactly.
            if (source.get("source_system") != "superhuman_docs"
                or str(source.get("source_page_id")) != candidate["source_page_id"]
                or str(source.get("source_doc_id")) != candidate["source_doc_id"]):
                continue
            try:
                set_cms_lesson_archived(mid, lid, True, user_id,
                                        sort_order=int(existing.get("sort_order") or 0))
                results["archived_phase_duplicates"] += 1
            except Exception as ex:
                results["errors"].append(f"Could not archive obsolete phase-page class: {str(ex)[:150]}")
        if results["archived_phase_duplicates"]:
            _clear_content_studio_caches()
    return results


def _render_superhuman_import(user: dict) -> None:
    """Editor-only, manual Superhuman Docs import; no background sync."""
    st.subheader("Import / update from Superhuman Docs")
    st.caption("Choose one module, a small class batch, or independent Resources/Tools rows. Only selected pages are exported; nothing changes until you explicitly save or publish.")
    st.info("Structure: learning environment → modules → optional Discover / Apply / Communicate phase pages → classes. A page may contain Resources, Tools and Continue exploring link sections. Page IDs remain stable across manual updates.")
    doc_input = st.text_input("Superhuman Docs document URL or ID", key="sh-doc-url", placeholder="https://coda.io/d/…_d…")
    token = st.text_input("API token (used only for this import session)", type="password", key="sh-api-token")
    if st.button("Connect and list pages", key="sh-connect", disabled=not doc_input.strip() or not token.strip()):
        try:
            doc_id = sh_doc_id(doc_input)
            with st.spinner("Loading page titles and library tables…"):
                pages = sh_list_pages(doc_id, token)
                pages, hierarchy_notes = sh_enrich_hierarchy(doc_id, pages, token)
                tables = sh_list_tables(doc_id, token)
            st.session_state["sh-source-selection"] = {"doc_id": doc_id, "pages": pages, "tables": tables, "hierarchy_notes": hierarchy_notes}
            st.session_state.pop("sh-import-preview", None)
            st.session_state.pop("sh-import-chosen", None)
            st.session_state.pop("sh-last-report", None)
            st.success(f"Connected: {len(pages)} pages and {len(tables)} tables found.")
        except Exception as ex:
            st.error(f"Connection failed: {str(ex)[:250]}")
    selection = st.session_state.get("sh-source-selection")
    if not selection:
        st.caption("Use a read-only Coda token with access to the test document. In production, a token may also be configured as Streamlit Secrets instead of typing it repeatedly.")
        return
    doc_id = selection["doc_id"]
    for note in selection.get("hierarchy_notes") or []:
        st.warning(note)
    pages = selection["pages"]
    tables = selection["tables"]
    pages_by_id = {str(p.get("id")): p for p in pages}
    roots = [str(p["id"]) for p in pages if p.get("id") and not p.get("parent")]
    if not roots:
        st.error("No top-level learning-environment pages were returned by Superhuman Docs. Check the document and reconnect.")
        return
    # Do not offer modules, phase headings or classes as a root: this creates
    # a wrong import hierarchy and unstable mapping.
    saved_root = str(st.session_state.get("sh-root-page") or "")
    if saved_root and saved_root not in roots:
        st.session_state.pop("sh-root-page", None)
    root_id = st.selectbox("Learning environment (top-level main page only)", roots,
                           key="sh-root-page",
                           format_func=lambda pid: pages_by_id[pid].get("name", pid))
    try:
        tree = sh_page_tree(pages, root_id)
        st.caption(f"Hierarchy preview: {len(tree)} module pages and {sum(len(m['lessons']) for m in tree)} class pages. Modules without classes will still be imported as module records.")
        with st.expander("Check detected page hierarchy (Superhuman Docs page order)"):
            for module_index, module in enumerate(tree, 1):
                st.markdown(f"**{module_index}. {module['page'].get('name')}**")
                for class_index, entry in enumerate(module["lessons"], 1):
                    level = "Discover" if entry["level"] == "Understand" else entry["level"]
                    st.markdown(f"{class_index}. {level} · {entry['page'].get('name')}")
        from superhuman_sync import unverified_sibling_order
        uncertain = unverified_sibling_order(pages, root_id)
        if uncertain:
            st.warning("The API did not provide explicit child order under: " + ", ".join(uncertain[:6]) +
                       ". Current list order is used as a fallback; verify the preview before publishing.")
    except Exception as ex:
        st.error(f"Page hierarchy could not be read: {ex}")
        return
    st.markdown("#### Choose what to read")
    mode = st.radio("Import scope", ["One module / class batch", "Libraries only"],
                    key="sh-import-mode", horizontal=True)
    chosen_module_id = ""
    selected_class_ids: set[str] = set()
    include_module_record = False
    if mode == "One module / class batch":
        if not tree:
            st.warning("No modules found. You can still choose Libraries only.")
            return
        module_choices = [str(m["page"]["id"]) for m in tree]
        chosen_module_id = st.selectbox(
            "Module to import (one at a time)", module_choices,
            format_func=lambda mid: next(str(m["page"].get("name") or mid)
                                         for m in tree if str(m["page"]["id"]) == mid),
            key="sh-batch-module")
        module_spec = next(m for m in tree if str(m["page"]["id"]) == chosen_module_id)
        module_exists = bool(get_cms_module(sh_stable_id("module", doc_id, chosen_module_id)))
        include_module_record = st.checkbox(
            "Include module landing page, learning objectives and phase introductions",
            value=not module_exists, key="sh-batch-module-record")
        include_classes = st.checkbox("Include class pages", value=True, key="sh-batch-classes")
        if include_classes:
            phase_labels = {"Understand": "Discover", "Apply": "Apply", "Convince": "Communicate"}
            phase = st.selectbox("Learning phase", ["All phases", "Discover", "Apply", "Communicate"],
                                 key="sh-batch-phase")
            eligible = [item for item in module_spec["lessons"]
                        if phase == "All phases" or phase_labels.get(item["level"]) == phase]
            batch_size = st.selectbox("Classes per batch", [1, 2, 3, 5, 10], index=2,
                                      key="sh-class-batch-size")
            if eligible:
                batches = [eligible[i:i + batch_size] for i in range(0, len(eligible), batch_size)]
                batch_index = st.selectbox(
                    "Batch to preview", list(range(len(batches))),
                    format_func=lambda n: f"Batch {n + 1} of {len(batches)} · " +
                    " / ".join(str(item["page"].get("name")) for item in batches[n]),
                    key="sh-class-batch-index")
                selected_class_ids = {str(item["page"]["id"]) for item in batches[batch_index]}
                st.caption(f"Only {len(selected_class_ids)} selected class page(s) will be exported, "
                           "in their original Superhuman Docs order. Choose the next batch later.")
            else:
                st.info("No classes in this phase. You may still import the module landing page.")
        st.caption("For the fewest API requests, untick the module landing page when updating only "
                   "existing classes. Class IDs and their full sequence positions stay unchanged.")
    st.markdown("#### Library tables — optional, separate batches")
    st.caption("**Neither library is read unless you opt in.** Importing classes does not require "
               "refreshing your Tools or Resources. Already published records remain available.")
    table_ids = [""] + [str(t["id"]) for t in tables if t.get("id")]
    table_labels = {str(t.get("id")): str(t.get("name") or t.get("id")) for t in tables}
    resource_guess = next((tid for tid in table_ids if "resource" in table_labels.get(tid, "").casefold()), "")
    tool_guess = next((tid for tid in table_ids if "tool" in table_labels.get(tid, "").casefold()), "")
    rcol, tcol = st.columns(2)
    with rcol:
        do_resources = st.checkbox("Include Resources", value=False, key="sh-include-resources")
        resource_id = st.selectbox("Resources table", table_ids,
                                   index=table_ids.index(resource_guess),
                                   format_func=lambda tid: table_labels.get(tid) or "No table",
                                   disabled=not do_resources, key="sh-resource-table") if do_resources else ""
        resource_batch_size = st.selectbox("Resources per batch", [10, 25, 50, 100], index=1,
                                           key="sh-resource-batch-size", disabled=not do_resources)
        resource_start = st.number_input("Start from resource row", min_value=1, value=1, step=resource_batch_size,
                                         disabled=not do_resources, key="sh-resource-start")
    with tcol:
        do_tools = st.checkbox("Include Tools", value=False, key="sh-include-tools")
        tool_id = st.selectbox("Tools table", table_ids, index=table_ids.index(tool_guess),
                               format_func=lambda tid: table_labels.get(tid) or "No table",
                               disabled=not do_tools, key="sh-tool-table") if do_tools else ""
        tool_batch_size = st.selectbox("Tools per batch", [10, 25, 50, 100], index=1,
                                       key="sh-tool-batch-size", disabled=not do_tools)
        tool_start = st.number_input("Start from tool row", min_value=1, value=1, step=tool_batch_size,
                                     disabled=not do_tools, key="sh-tool-start")
    current_scope = (
        doc_id, root_id, mode, chosen_module_id, include_module_record,
        tuple(sorted(selected_class_ids)), resource_id, tool_id,
        int(resource_start) if resource_id else 0,
        int(resource_batch_size) if resource_id else 0,
        int(tool_start) if tool_id else 0,
        int(tool_batch_size) if tool_id else 0,
    )
    has_work = bool(selected_class_ids or include_module_record or resource_id or tool_id)
    if st.button("Preview selected batch", key="sh-preview", type="primary",
                 disabled=not token.strip() or not has_work):
        try:
            with st.spinner("Reading this batch from Superhuman Docs (with API rate-limit pacing)…"):
                preview = sh_build_preview(
                    doc_id, pages_by_id[root_id], pages, token, resource_id, tool_id,
                    module_page_ids={chosen_module_id} if chosen_module_id else set(),
                    lesson_page_ids=selected_class_ids,
                    include_module_records=include_module_record,
                    include_environment_page=False,
                    resource_row_offset=int(resource_start) - 1 if resource_id else 0,
                    resource_row_limit=int(resource_batch_size) if resource_id else None,
                    tool_row_offset=int(tool_start) - 1 if tool_id else 0,
                    tool_row_limit=int(tool_batch_size) if tool_id else None,
                )
            # Match @row links against the existing local CMS catalogue, not
            # only the library rows fetched in this preview. Class-only batches
            # must preserve working Streamlit Resource/Tool links.
            from superhuman_sync import resolve_linked_references as _sh_resolve_links
            def _stored_catalogue(rows: list[dict], id_key: str) -> list[dict]:
                matched = []
                for row in rows:
                    if row.get("archived"):
                        continue
                    published = row.get("published") or row.get("draft") or {}
                    if published.get("source_system") != "superhuman_docs":
                        continue
                    if str(published.get("source_doc_id")) != doc_id:
                        continue
                    matched.append({"id": row.get(id_key),
                                    "title": published.get("title") or "",
                                    "source_row_id": published.get("source_row_id") or "",
                                    "source_row_url": published.get("source_row_url") or ""})
                return matched
            local_resources = _stored_catalogue(list_cms_library_resources(), "resource_id")
            local_tools = _stored_catalogue(list_cms_tools(), "tool_id")
            for kind, extra in (("resource", local_resources), ("tool", local_tools)):
                known = {r["id"] for r in (preview.get("libraries") or {}).get(kind) or []}
                extra[:] = [r for r in extra if r["id"] not in known]
            resource_catalogue = (preview.get("libraries") or {}).get("resource", []) + local_resources
            tool_catalogue = (preview.get("libraries") or {}).get("tool", []) + local_tools
            for record in preview.get("entries") or []:
                _sh_resolve_links(record["payload"], resource_catalogue, tool_catalogue,
                                  check_resource=True, check_tool=True)
                if record["kind"] == "module":
                    for group in (record["payload"].get("phase_references") or {}).values():
                        _sh_resolve_links(group, resource_catalogue, tool_catalogue,
                                          check_resource=True, check_tool=True)
            st.session_state["sh-import-preview"] = preview
            st.session_state.pop("sh-import-chosen", None)
            st.session_state.pop("sh-last-report", None)
            st.session_state["sh-import-source"] = current_scope
        except Exception as ex:
            st.error(f"Batch preview failed: {str(ex)[:350]}")
    preview = st.session_state.get("sh-import-preview")
    if not preview:
        return
    if st.session_state.get("sh-import-source") != current_scope:
        st.warning("Source selection changed. Preview again before saving; previous results are not eligible for import.")
        return
    counts = preview.get("count") or {}
    with st.expander("Linked Resources, Tools and Continue exploring on imported pages"):
        for entry in preview.get("entries") or []:
            payload = entry.get("payload") or {}
            pages = [(payload.get("title") or "Page", payload)]
            if entry.get("kind") == "module":
                pages.extend((f"{payload.get('title')} / {level}", linked)
                             for level, linked in (payload.get("phase_references") or {}).items())
            for page_title, linked in pages:
                n_resource = len(linked.get("resource_references") or [])
                n_tools = len(linked.get("tool_references") or [])
                n_read = len(linked.get("further_reading") or [])
                if n_resource or n_tools or n_read:
                    st.write(f"{page_title}: {n_resource} resources · {n_tools} tools · {n_read} further links")
        st.caption("Use a Resources or Tool(s) callout with @ table-row links on a module, phase or class page. "
                   "Further reading / Continue exploring uses ordinary clickable bullet links. "
                   "Unresolved links are flagged before you publish; no dedicated phase-specific download heading is needed.")
    with st.expander("Module images selected from Superhuman Docs"):
        for entry in preview.get("entries") or []:
            if entry.get("kind") != "module":
                continue
            payload = entry.get("payload") or {}
            origin = payload.get("cover_image_source")
            origin_label = {"first_module_figure": "First figure on the module page",
                            "page_cover": "Page cover (fallback)",
                            "none": "No image detected"}.get(origin, "No image detected")
            st.markdown(f"**{payload.get('title') or 'Module'}** — {origin_label}")
            if payload.get("cover_image_url"):
                st.caption("Image URL: " + str(payload["cover_image_url"])[:220])
                st.caption("This is only the detected source. Select and publish the MODULE record below "
                           "to download and attach this image; publishing lessons alone will not update a module cover.")
                with st.container():
                    try:
                        st.image(str(payload["cover_image_url"]), width=360)
                    except Exception:
                        st.caption("The source image cannot be previewed here. It will be checked during import.")
            else:
                st.warning("No module image found in this export. Verify you placed the picture on the "
                           "module landing page itself, then re-preview the correct learning environment.")
        st.caption("The first large figure in each module landing page takes priority. "
                   "Child lesson images are imported separately. A failed image never blocks its text import.")
    duplicate_phase_lessons = []
    for candidate in preview.get("obsolete_phase_lesson_candidates") or []:
        existing = get_cms_lesson(candidate["module_id"], candidate["lesson_id"])
        if not existing or existing.get("archived"):
            continue
        source = existing.get("published") or existing.get("draft") or {}
        if (source.get("source_system") == "superhuman_docs"
            and str(source.get("source_page_id")) == candidate["source_page_id"]
            and str(source.get("source_doc_id")) == candidate["source_doc_id"]):
            duplicate_phase_lessons.append(candidate)
    archive_phase_pages = False
    if duplicate_phase_lessons:
        st.warning("Some phase pages were previously imported as Discover classes. "
                   "Their obsolete lesson entries can be archived without removing progress or reflections.")
        for candidate in duplicate_phase_lessons:
            st.caption("• " + candidate["title"] + " (previously imported as a class)")
        archive_phase_pages = st.checkbox(
            "On publish, archive the obsolete phase-page classes above (keep learner data)",
            value=True, key="sh-fix-phantom-phase-pages")
    a, b, c, d = st.columns(4)
    a.metric("Modules", counts.get("modules", 0))
    b.metric("Classes", counts.get("classes", 0))
    c.metric("Resources", counts.get("resources", 0))
    d.metric("Tools", counts.get("tools", 0))
    warnings = preview.get("warnings") or []
    if warnings:
        with st.expander(f"Validation notes ({len(warnings)})", expanded=True):
            for w in warnings[:80]:
                st.caption("• " + str(w))
    st.markdown("#### Preview and choose records")
    st.caption("Only records read in this batch appear below. Other published classes, tools, resources, "
               "learner progress and notebook entries remain untouched.")
    tags, defaults = [], []
    for entry in preview.get("entries") or []:
        tag = f"{entry['kind']}:{entry['module_id']}:{entry['id']}"
        existing = get_cms_module(entry["id"]) if entry["kind"] == "module" else get_cms_lesson(entry["module_id"], entry["id"])
        last = (existing or {}).get("draft") or (existing or {}).get("published") or {}
        old_digest = last.get("source_digest")
        new_digest = entry["payload"].get("source_digest")
        status = "NEW" if not existing else ("UNCHANGED" if old_digest and new_digest == old_digest else "CHANGED")
        parent_title = next((e["payload"]["title"] for e in preview.get("entries") or []
                             if e["kind"] == "module" and e["id"] == entry["module_id"]), "")
        label = (f"Module {entry['sort_order'] // 10:02d} · {entry['payload']['title']} · {status}"
                 if entry["kind"] == "module" else
                 f"{parent_title} / {('Discover' if entry['payload'].get('level') == 'Understand' else 'Communicate' if entry['payload'].get('level') == 'Convince' else entry['payload'].get('level'))} "
                 f"{entry['sort_order'] // 10:02d} · {entry['payload']['title']} · {status}")
        tags.append((tag, label))
        if status != "UNCHANGED": defaults.append(tag)
    for kind in ("resource", "tool"):
        for item in (preview.get("libraries") or {}).get(kind) or []:
            tag = f"{kind}:{item['id']}"
            tags.append((tag, f"{kind.title()} · {item['title']}"))
            # Table rows can change independently; propose review on every manual scan.
            defaults.append(tag)
    if not tags:
        st.warning("No records found under this root. Select the learning environment main page and inspect its subpages.")
        return
    choices = {tag: label for tag, label in tags}
    chosen = st.multiselect("Import these records", list(choices), default=defaults,
                            format_func=lambda k: choices[k], key="sh-import-chosen",
                            help="For a Tools batch, remove any tool you do not want to update. "
                                 "Only the names left selected are saved/published.")
    selected_lesson = next((e for e in preview["entries"] if e["kind"] == "lesson"), None)
    if selected_lesson:
        with st.expander("Preview a parsed class and its learning cards"):
            lesson_choices = [e for e in preview["entries"] if e["kind"] == "lesson"]
            chosen_lesson_id = st.selectbox("Class", [e["id"] for e in lesson_choices],
                                           format_func=lambda lid: next(e["payload"]["title"] for e in lesson_choices if e["id"] == lid),
                                           key="sh-inspect-lesson")
            detail = next(e for e in lesson_choices if e["id"] == chosen_lesson_id)
            lp = detail["payload"]
            st.write(f"{len(lp['theory_cards'])} cards · level: {lp['level']} · quiz: {'Incomplete — publication blocked' if lp.get('_incomplete_quiz') else ('Ready' if lp.get('quiz') else 'None')} · reflection: {bool(lp['prompt'])}")
            if lp.get("_incomplete_quiz"):
                st.warning("The quiz is present in Superhuman Docs but lacks a valid correct answer, options or feedback. Replace placeholders before publishing this class.")
            for card in lp["theory_cards"][:8]:
                st.markdown(f"**{card['title']}**")
                st.markdown(sanitize_rich_text(card["body_html"]), unsafe_allow_html=True)
                if card.get("image_src_import") or card.get("image_src_imports"):
                    st.caption("Images will be imported when available (8 MB maximum per image). "
                               "An oversized or inaccessible figure is skipped without blocking the class text.")
    tools_in_preview = (preview.get("libraries") or {}).get("tool") or []
    if tools_in_preview:
        with st.expander("Preview a tool's formatted text and image before publishing"):
            selected_tool_id = st.selectbox(
                "Tool to inspect", [item["id"] for item in tools_in_preview],
                format_func=lambda tid: next(item["title"] for item in tools_in_preview if item["id"] == tid),
                key="sh-preview-tool")
            example = next(item for item in tools_in_preview if item["id"] == selected_tool_id)
            st.markdown("**Description**")
            st.markdown(str(example.get("description_rich") or example.get("description") or "No description"))
            st.markdown("**How to use**")
            st.markdown(str(example.get("steps_rich") or example.get("steps_text") or "No instructions"))
            if example.get("image_url"):
                st.success("Image URL detected. The image will be downloaded and stored when you import this tool.")
                st.caption("Image: " + str(example.get("image_name") or example["image_url"]))
            elif example.get("image_name"):
                st.warning(f"Image '{example['image_name']}' was found, but the API returned no downloadable URL. "
                           "The tool will import without replacing an existing image.")
            else:
                st.caption("No image in the Tools table for this row.")
    if not chosen:
        st.info("Choose at least one item to import.")
        return
    # Never silently publish: editors can create drafts; only administrators can publish.
    confirmed = st.checkbox("I have reviewed the preview and understand that importing replaces the selected CMS draft/published content. Learner reflections and progress are not deleted.", key="sh-confirm")
    c_draft, c_publish = st.columns(2)
    with c_draft:
        if st.button("Save selected as drafts", key="sh-save", disabled=not confirmed, width="stretch"):
            report = _sh_commit_preview(preview, chosen, publish=False, user_id=user["user_id"])
            st.session_state["sh-last-report"] = report
            st.success(f"Saved {report['saved']} records as drafts. Existing published content remains live.")
    with c_publish:
        can_publish = is_administrator(user)
        if st.button("Publish selected updates", key="sh-publish", disabled=not confirmed or not can_publish, type="primary", width="stretch"):
            report = _sh_commit_preview(preview, chosen, publish=True, user_id=user["user_id"], archive_phase_pages=archive_phase_pages)
            st.session_state["sh-last-report"] = report
            st.success(f"Published {report['published']} records. Stable source-page IDs preserve existing learning links and progress.")
    if st.session_state.get("sh-last-report"):
        report = st.session_state["sh-last-report"]
        if report.get("warnings"):
            with st.expander(f"Imported with optional content omitted ({len(report['warnings'])})", expanded=True):
                for issue in report["warnings"]:
                    st.warning(issue)
        if report.get("errors"):
            with st.expander(f"Import errors / files not available ({len(report['errors'])})", expanded=True):
                for issue in report["errors"]:
                    st.error(issue)
        for cover_note in report.get("module_covers") or []:
            st.info(cover_note)
        st.caption(f"Obsolete phase classes archived: {report.get('archived_phase_duplicates', 0)} · Images stored: {report.get('images', 0)} · Images omitted: {report.get('images_skipped', 0)} · legacy uploaded communication files: {report.get('convince_files', 0)} · library/tool attachments stored: {report.get('attachments', 0)} · unchanged/unselected records left untouched: {report.get('skipped', 0)}")


def page_admin(user):
    """Content studio for editors plus administrator-only publishing and resource management."""
    if not is_content_editor(user):
        st.error("Editor or administrator access is required for this page.")
        st.button("Return home", on_click=navigate, args=("home", None, None, None, None), kwargs={"_rerun": False})
        return

    role_label = "Administrator" if is_administrator(user) else "Editor"
    st.markdown(
        f"""
        <div class="m-module-hero learning">
            <div class="m-kicker">MOSAIC Learn · content studio · {escape(role_label)}</div>
            <h1>Content studio</h1>
            <p>Manage learning modules and classes, including Communicate classes, or manually import updates from Superhuman Docs.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    flash = st.session_state.pop("content-studio-flash", None)
    if flash:
        st.success(flash)
    if not is_administrator(user):
        st.info("Editor access: you can save drafts and preview Superhuman Docs updates. Administrators publish and manage libraries, structure, and account roles.")

    snapshot = _admin_catalogue_snapshot()
    active_modules = sum(1 for module in snapshot.values() if not module.get("_cms_archived"))
    lesson_count = sum(
        1 for module in snapshot.values() for lesson in module.get("topics", [])
        if not lesson.get("_cms_archived")
    )
    idea_count = sum(
        len(lesson.get("theory_cards") or [])
        for module in snapshot.values()
        for lesson in module.get("topics", [])
        if not lesson.get("_cms_archived") and lesson.get("level") != "Convince"
    )
    resource_count = len(_cached_resource_files(None, None, False))
    a, b, c, d = st.columns(4)
    a.metric("Active modules", active_modules)
    b.metric("Classes", lesson_count)
    c.metric("Idea cards", idea_count)
    d.metric("Managed files", resource_count)

    section_options = ["Modules & lessons", "Ideas & content", "Checks & quizzes", "Superhuman Docs import"]
    if is_administrator(user):
        section_options.extend(["Communicate: uploaded files", "Tools & files", "Resources", "Our stories", "Users & roles", "Revision history", "Deployment"])

    # Keep the Content Studio on the section the user is actually working in.
    # st.tabs always jumps back to its first tab after many reruns and computes
    # hidden tabs as well; a stateful segmented navigation is more predictable
    # for editors and avoids unnecessary database/UI work.
    url_section = CONTENT_STUDIO_SLUG_SECTIONS.get(_query_param_text("admin"))
    if url_section in section_options:
        st.session_state["content-studio-section"] = url_section
    elif st.session_state.get("content-studio-section") not in section_options:
        st.session_state["content-studio-section"] = section_options[0]

    active_section = st.segmented_control(
        "Content studio section",
        section_options,
        key="content-studio-section",
        on_change=_sync_content_studio_section_query,
        width="stretch",
        label_visibility="collapsed",
    ) or section_options[0]

    if active_section == "Superhuman Docs import":
        _render_superhuman_import(user)
    elif active_section == "Modules & lessons":
        structure_options = ["Modules", "Lessons"]
        url_view = _query_param_text("admin_view")
        desired_view = "Lessons" if url_view == "lessons" else "Modules" if url_view == "modules" else ""
        if desired_view in structure_options:
            st.session_state["content-studio-structure"] = desired_view
        elif st.session_state.get("content-studio-structure") not in structure_options:
            st.session_state["content-studio-structure"] = "Modules"
        structure_view = st.segmented_control(
            "Structure section",
            structure_options,
            key="content-studio-structure",
            on_change=_sync_content_studio_structure_query,
            label_visibility="collapsed",
        ) or "Modules"
        if structure_view == "Lessons":
            _render_content_studio_lessons(user, snapshot)
        else:
            _render_content_studio_modules(user, snapshot)
    elif active_section == "Ideas & content":
        _render_content_studio_ideas(user, snapshot)
    elif active_section == "Checks & quizzes":
        _render_content_studio_checks(user, snapshot)
    elif active_section == "Communicate: uploaded files" and is_administrator(user):
        _render_content_studio_convince_files(user, snapshot)
    elif active_section == "Tools & files" and is_administrator(user):
        _render_content_studio_tools(user, snapshot)
    elif active_section == "Resources" and is_administrator(user):
        _render_content_studio_library_resources(user, snapshot)
    elif active_section == "Our stories" and is_administrator(user):
        _render_content_studio_stories(user)
    elif active_section == "Users & roles" and is_administrator(user):
        _render_content_studio_people(user)
    elif active_section == "Revision history" and is_administrator(user):
        _render_content_studio_revisions()
    elif active_section == "Deployment" and is_administrator(user):
        _render_content_studio_status(snapshot)


def page_public_result(token: str):
    share = get_share(token)
    st.markdown("<div class='m-kicker'>MOSAIC Learn · shared result</div>", unsafe_allow_html=True)
    if not share:
        st.error("This shared result does not exist or is no longer available.")
        return
    s = share["snapshot"]
    st.title(s["module"])
    st.write(f"Learning summary shared by **{s['learner']}**")
    a, b, c = st.columns(3)
    a.metric("Progress", f"{s['progress_percent']}%")
    b.metric("Learning steps", f"{s['topics_completed']}/{s['topics_total']}")
    c.metric("Quick checks", f"{s['knowledge_checks_correct']}/{s['knowledge_checks_total']}")
    st.caption("Private reflections and notes are not included in this shared view.")


# Validate persistent storage before serving any production route. Public result
# links bypass account login, but they must not bypass production configuration.
validate_runtime_configuration()
share_token = st.query_params.get("share")
if share_token:
    render_brandbar()
    page_public_result(str(share_token))
    st.stop()

# URL-backed router. Session State still holds widget/page state, while the
# browser URL identifies the current top-level view. This makes pages bookmarkable
# and lets browser Back/Forward restore previous navigation.
st.session_state.setdefault("module_id", "drivers")
route = _apply_route_from_query()
# Remove obsolete router state from earlier prototypes if the app hot-reloads in
# an existing session.
st.session_state.pop("goto", None)
st.session_state.pop("selected_module", None)
st.session_state.pop("selected_topic", None)

def _render_scroll_to_top_on_route_change(route_key: str) -> None:
    """Scroll only when the URL page/lesson identity actually changes.

    A carousel, reflection edit, quiz answer, filter or other widget rerun
    must NEVER scroll the page. Scroll once on entry, with a short follow-up
    for DOM mount timing; no 1-second timeout that can hijack later clicks.
    """
    if st.session_state.get("_mosaic_last_route_key") == route_key:
        return
    st.session_state["_mosaic_last_route_key"] = route_key
    route_token = hashlib.sha1(route_key.encode("utf-8")).hexdigest()
    script = """<script>
    (() => {
      const doc = window.document;
      const route = __TOKEN__;
      doc.documentElement.dataset.mosaicScrollRoute = route;
      const reset = () => {
        if (doc.documentElement.dataset.mosaicScrollRoute !== route) return;
        const targets = [
          doc.querySelector('[data-testid="stMain"]'),
          doc.querySelector('[data-testid="stAppViewContainer"]'),
          doc.scrollingElement,
        ];
        targets.forEach(node => {
          if (node) node.scrollTop = 0;
        });
        window.scrollTo(0, 0);
      };
      reset();
      window.requestAnimationFrame(reset);
      // One short retry for initial mount. No late scroll retries.
      window.setTimeout(reset, 90);
    })();
    </script>""".replace("__TOKEN__", json.dumps(route_token))
    st.html(script, unsafe_allow_javascript=True)


apply_published_learning_content()
if route == "results":
    st.session_state["learning-hub-section"] = "Results & sharing"
    st.session_state.route = "catalogue"
    route = "catalogue"
    _write_route_query("catalogue")
elif route == "learning":
    st.session_state["learning-hub-section"] = "My learning"
    st.session_state.route = "catalogue"
    route = "catalogue"
    _write_route_query("catalogue")
protected_routes = {
    "learning",
    "community",
    "module",
    "phase",
    "topic",
    "convince",
    "profile",
    "admin",
}
user = get_current_user(required=route in protected_routes)
if user:
    user = ensure_profile(user)

route_fingerprint = "|".join((
    str(route),
    str(st.session_state.get("module_id", "")) if route in {"module", "phase", "topic", "convince", "tools"} else "",
    str(st.session_state.get("topic_id", "")) if route == "topic" else "",
    str(st.session_state.get("phase", "")) if route == "phase" else "",
    str(st.session_state.get("tool_id", "")) if route == "tools" else "",
    _query_param_text("resource") if route == "resources" else "",
    _query_param_text("admin") if route == "admin" else "",
))
# Reopen every entered lesson at its first card, including browser history.
# Carousel widget reruns keep the same fingerprint and do not reset the card.
if st.session_state.get("_mosaic_mounted_route_key") != route_fingerprint:
    if route == "topic":
        active_module = str(st.session_state.get("module_id") or "")
        active_lesson = str(st.session_state.get("topic_id") or "")
        if active_module and active_lesson:
            st.session_state[f"theory-step-{active_module}-{active_lesson}"] = 1
    st.session_state["_mosaic_mounted_route_key"] = route_fingerprint
render_sidebar(user)
render_brandbar()
# Mount the route-specific scroll reset before the new body. This prevents a
# footer iframe on a long lesson from becoming the browser's scroll target.
_render_scroll_to_top_on_route_change(route_fingerprint)

# Reconcile successive pages into ONE stable parent tree. A route-derived
# container key remounts the root on every navigation, leaving the previous
# entire page visible as a faded, stale sibling while reruns are interrupted.
# Combined with the single-rerun on_click navigation above, this is the
# underlying lifecycle correction; no CSS concealment of old pages is needed.
with st.container(key="mosaic_active_page"):
    if route == "home":
        page_home(user)
    elif route == "our-story":
        page_our_story(user)
    elif route == "learning":
        page_learning(user)
    elif route == "catalogue":
        page_catalogue(user)
    elif route == "resources":
        page_resources(user)
    elif route == "tools":
        page_tools(user)
    elif route == "glossary":
        page_glossary()
    elif route == "contact":
        page_contact()
    elif route == "privacy":
        page_privacy()
    elif route == "community":
        page_community(user)
    elif route == "module":
        page_module(user)
    elif route == "phase":
        page_phase(user)
    elif route == "topic":
        page_topic(user)
    elif route == "convince":
        page_convince(user)
    elif route == "profile":
        page_profile(user)
    elif route == "admin":
        page_admin(user)
    else:
        navigate("home")

