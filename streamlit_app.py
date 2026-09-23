from __future__ import annotations

import base64
import copy
import hashlib
import io
import re
import zipfile
from uuid import uuid4
from pathlib import Path
from html import escape
from urllib.parse import quote

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
    get_cms_module,
    get_cms_resource_file,
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
    list_cms_resource_files,
    list_cms_tools,
    list_published_carousels,
    list_users,
    mark_community_notifications_read,
    publish_carousel_content,
    publish_cms_lesson,
    publish_cms_module,
    publish_cms_tool,
    record_privacy_acceptance,
    request_mycelium_connection,
    respond_mycelium_connection,
    save_quiz_result,
    save_carousel_draft,
    save_cms_lesson_draft,
    save_cms_module_draft,
    save_cms_resource_file,
    save_cms_tool_draft,
    save_topic_progress,
    set_account_role,
    set_cms_lesson_archived,
    set_cms_module_archived,
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
DATABASE_SCHEMA_VERSION = "2026-09-23-content-studio-resources-v2"

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
    initial_sidebar_state="collapsed",
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


@st.cache_data(ttl=45, show_spinner=False)
def _cached_cms_lessons() -> list[dict]:
    return list_cms_lessons()


@st.cache_data(ttl=45, show_spinner=False)
def _cached_cms_tools() -> list[dict]:
    return list_cms_tools()


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
    _cached_cms_lessons.clear()
    _cached_cms_tools.clear()
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
.m-module-card .m-module-art { flex:0 0 88px; }
.m-module-card .m-module-body { flex:1; display:flex; flex-direction:column; min-height:0; }
.m-module-art { height:88px; position:relative; overflow:hidden; background:#f6f6f3; }
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
.m-theory-wrap { width:100%; max-width:1360px; margin:.45rem auto 0; }
.m-theory-card {
    width:100%; box-sizing:border-box; border:1px solid var(--m-line); border-radius:24px;
    padding:clamp(2rem,4vw,3.6rem) clamp(1.6rem,4.6vw,4rem);
    background:linear-gradient(180deg,#fff 0%,#fcfcfb 100%); min-height:330px;
    display:flex; align-items:center; border-top:7px solid var(--m-blue);
    box-shadow:0 2px 8px rgba(60,60,59,.035);
}
.m-theory-inner { width:100%; max-width:920px; margin:0 auto; }
.m-theory-label { text-transform:uppercase; letter-spacing:.11em; font-size:.72rem; color:var(--m-wine); font-weight:700; }
.m-theory-card h3 { max-width:30ch; margin:.72rem 0 .9rem; font-size:clamp(1.65rem,2.7vw,2.3rem); line-height:1.2; letter-spacing:-.025em; }
.m-theory-card p { max-width:76ch; margin:0; font-size:1.05rem; line-height:1.82; color:#4b4b48; }
.m-theory-card ul { max-width:74ch; margin:1rem 0 0 1.2rem; color:#4b4b48; line-height:1.7; }
.m-theory-card li { margin:.42rem 0; }
.m-rich-text p + p { margin-top:.8rem; }
.m-rich-text blockquote { max-width:72ch; margin:1rem 0; padding:.25rem 0 .25rem 1rem; border-left:4px solid var(--m-cyan); color:#535b5e; }
.m-rich-text a { color:var(--m-blue); text-underline-offset:2px; }
.m-theory-progress { display:flex; gap:.42rem; width:min(380px,58%); margin:0 auto .95rem; }
.m-theory-dot { height:6px; flex:1; border-radius:999px; background:#e5e5e0; }
.m-theory-dot.active { background:var(--m-blue); }
.m-theory-card.synthesis { align-items:stretch; min-height:380px; }
.m-synthesis-inner { width:100%; max-width:1040px; margin:0 auto; }
.m-key-idea-panel { border-left:5px solid var(--m-lime); border-radius:0 16px 16px 0; background:var(--m-lime-10); padding:1rem 1.15rem; margin:.8rem 0 1.05rem; }
.m-key-idea-panel p { margin:.3rem 0 0; font-size:1.02rem; line-height:1.65; color:#424a3d; }
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
.st-key-theory_navigation { max-width:1360px; margin:.75rem auto .65rem; }
.st-key-theory_navigation [data-testid="stHorizontalBlock"] { align-items:center; }
.st-key-theory_navigation [data-testid="stColumn"]:last-child [data-testid="stButton"] { display:flex; justify-content:flex-end; }
.st-key-theory_navigation [data-testid="stButton"] { margin:.25rem 0 .45rem; }
.st-key-theory_navigation [data-testid="stButton"] button { min-width:188px; width:auto; padding-left:1.1rem; padding-right:1.1rem; }
.st-key-reflection_form { max-width:1120px; margin:1rem auto 1.3rem; }
.st-key-reflection_actions { max-width:1120px; margin:.45rem auto 1.75rem; }
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
[class*="st-key-community_post_"] { margin:.75rem 0; padding:1.05rem 1.1rem .95rem; border:1px solid #e1e2de; border-radius:19px; background:#fff; box-shadow:0 3px 12px rgba(60,60,59,.035); }
[class*="st-key-community_post_"] .m-post { margin:0 0 .55rem; padding:0; border:0; border-radius:0; }
.m-post-meta { color:var(--m-muted); font-size:.75rem; margin-bottom:.55rem; }
.m-post p { margin:0; white-space:pre-wrap; line-height:1.65; color:#444441; }
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
    .m-theory-card{min-height:290px}.m-theory-inner{max-width:none}
    .m-practice-feature{grid-template-columns:1fr}.m-practice-media{min-height:145px;max-height:210px}.m-community-hero-grid{grid-template-columns:1fr}.m-community-snapshot{border-left:0;border-top:1px solid #dce5df}.m-community-snapshot-grid{max-width:520px}
}
@media (max-width: 620px) {
    .block-container{padding-top:4.75rem;padding-left:1rem;padding-right:1rem}
    .m-building-grid,.m-evidence-grid,.m-resource-grid,.m-driver-grid,.m-tool-steps,.m-mycelium-metrics,.m-community-snapshot-grid{grid-template-columns:1fr}
    .m-track-card{min-height:0}.m-module-card{height:auto;min-height:0}.m-start-intro{grid-template-columns:1fr}.m-start-image{min-height:150px}.m-start-choice,.m-glossary-card{min-height:0}.m-phase-header{grid-template-columns:44px minmax(0,1fr)}.m-phase-progress{grid-column:2;justify-self:start}.m-lesson-row{grid-template-columns:38px minmax(0,1fr)}.m-lesson-time{grid-column:2}
    [class*="st-key-path_step_"] [data-testid="stHorizontalBlock"]{gap:.55rem}.m-path-copy .meta{font-size:.63rem}
    .m-theory-card{min-height:0;padding:1.5rem 1.25rem;border-radius:19px}.m-theory-progress{width:78%;margin-bottom:.75rem}
    .st-key-theory_navigation [data-testid="stButton"] button{min-width:0;width:100%;font-size:.86rem}
    .m-mini-mark{width:30px;height:30px}.m-brandbar{margin-bottom:.8rem}.m-brand-logo{height:36px;max-width:150px}.m-brand-learn{padding-left:.5rem}.m-brand-home{gap:.5rem}
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
        f"<a class='{css_class}' href='?home=1' target='_self' aria-label='Go to MOSAIC Learn home'>"
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


def learning_topics(module):
    """Topics that count toward course progress. Convince is a resource hub."""
    return [topic for topic in module.get("topics", []) if topic.get("level") != "Convince"]


def _secret(name: str, default=""):
    try:
        return st.secrets.get(name, default)
    except Exception:
        return default


ALLOWED_RICH_TEXT_TAGS = [
    "p", "br", "strong", "em", "u", "s", "blockquote", "ul", "ol", "li", "a"
]
ALLOWED_RICH_TEXT_ATTRIBUTES = {"a": ["href", "title", "target", "rel"]}


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
    data["duration"] = str(data.get("duration") or "").strip()
    data["format"] = str(data.get("format") or "Downloadable resource").strip()
    data["description"] = str(data.get("description") or "").strip()
    data["outcome"] = str(data.get("outcome") or "").strip()
    steps = data.get("steps") or []
    if isinstance(steps, str):
        steps = [line.strip() for line in steps.splitlines() if line.strip()]
    data["steps"] = [str(item).strip() for item in steps if str(item).strip()]
    if not isinstance(data.get("prompts"), list):
        data["prompts"] = []
    return data


def _admin_tools_snapshot() -> dict[str, dict]:
    baseline = copy.deepcopy(_tool_definitions_baseline())
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


def _resource_files_for(scope_type: str, scope_id: str, *, include_archived: bool = False) -> list[dict]:
    return _cached_resource_files(scope_type, scope_id, include_archived)


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
            if item.get("id") and item.get("level") != "Convince"
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
            if lesson.get("level") == "Convince":
                continue
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
        payload = normalize_carousel_payload(record.get("content") or {}, topic)
        topic["theory_cards"] = payload["cards"]
        topic["takeaway_html"] = payload["takeaway_html"]
        topic["practice_note_html"] = payload["practice_note_html"]
        topic["practice_image"] = payload["practice_image"]
        topic["practice_image_alt"] = payload["practice_image_alt"]


def apply_published_tool_content() -> None:
    """Overlay published tool metadata while keeping content.py as the safe fallback."""
    baseline = copy.deepcopy(_tool_definitions_baseline())
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
        base_topics = [
            copy.deepcopy(item)
            for item in module.get("topics", [])
            if item.get("level") != "Convince"
        ]
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
                if published_lesson.get("level") == "Convince":
                    topic_map.pop(lesson_id, None)
                    topic_order.pop(lesson_id, None)
                    continue
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
):
    """Single source of truth for navigation.

    The first draft used a sidebar radio that overwrote button-triggered routes on
    every rerun. This explicit router avoids that loop: only a navigation action
    changes the route.
    """
    st.session_state.route = route
    if module_id is not None:
        st.session_state.module_id = module_id
    if topic_id is not None:
        st.session_state.topic_id = topic_id
    elif route != "topic":
        st.session_state.pop("topic_id", None)
    if tool_id is not None:
        st.session_state.tool_id = tool_id
    elif route != "tool":
        st.session_state.pop("tool_id", None)
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
                    use_container_width=True,
                ):
                    st.login(provider)
    else:
        if st.button("Sign in to MOSAIC Learn", type="primary", use_container_width=True):
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
        use_container_width=True,
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
        submitted = st.form_submit_button("Create my profile", type="primary", use_container_width=True)
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
            st.session_state.route = "home"
            st.rerun()
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
    status_text = str(module.get("status") or "")
    status_html = (
        ""
        if status_text == "Available"
        else f'<span class="m-status soon">{escape(status_text)}</span>'
    )
    kicker_margin = ".65rem" if status_html else "0"
    return (
        f'<div class="m-module-card">'
        f'<div class="m-module-art {track_class}"></div>'
        f'<div class="m-module-body">'
        f'{status_html}'
        f'<div class="m-kicker" style="margin-top:{kicker_margin}">{escape(module["track"])}</div>'
        f'<h3>{escape(module["short_title"])}</h3>'
        f'<p>{escape(module["description"])}</p>'
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
            ("catalogue", "▦  Modules"),
            ("learning", "◔  My learning"),
            ("tools", "◇  Tools"),
            ("community", "✣  Community"),
        ]
        if user:
            items.append(("profile", "○  My profile"))
        for key, label in items:
            button_type = "primary" if route == key else "secondary"
            if st.button(label, key=f"nav-{key}", use_container_width=True, type=button_type):
                navigate(key)

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
        reference_items = [
            ("privacy", "Privacy notice"),
            ("glossary", "A–Z  Glossary"),
            ("contact", "✉  Contact"),
        ]
        for key, label in reference_items:
            button_type = "primary" if route == key else "secondary"
            if st.button(label, key=f"nav-{key}", use_container_width=True, type=button_type):
                navigate(key)
        if user and is_content_editor(user):
            st.caption("CONTENT")
            if st.button(
                "✎  Content studio",
                key="nav-admin",
                use_container_width=True,
                type="primary" if route == "admin" else "secondary",
            ):
                navigate("admin")

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
                if st.button("Module overview", use_container_width=True):
                    navigate("module", module_id)
            if module.get("convince") or _resource_files_for("convince", module_id):
                if st.button("Convince: evidence & resources", key=f"side-convince-{module_id}", use_container_width=True, type="primary" if route == "convince" else "secondary"):
                    navigate("convince", module_id)

            if route == "topic":
                topic_id = st.session_state.get("topic_id")
                progress = _cached_progress(user["user_id"], module_id)
                for idx, topic in enumerate(learning_topics(module), start=1):
                    marker = "✓" if progress.get(topic["id"], {}).get("completed") else str(idx)
                    prefix = "→" if topic["id"] == topic_id else marker
                    if st.button(f"{prefix}  {topic['title']}", key=f"side-topic-{topic['id']}", use_container_width=True):
                        navigate("topic", module_id, topic["id"])


def page_home(user: dict | None):
    st.markdown(
        f"""
        <div class="m-hero">
            <div class="m-hero-copy">
                <div class="m-kicker">MOSAIC Learn</div>
                <h1>Real lessons from Europe's land, ready to put to work</h1>
                <p>MOSAIC brings practitioners, research partners and policy makers together to understand and influence how land across Europe can be managed more sustainably. Learn turns the project's research and Policy Lab experience into practical journeys, tools and evidence.</p>
                <div class="m-hero-meta"><span class="m-chip">Self-paced</span><span class="m-chip">Practice-oriented</span><span class="m-chip">Progress saved</span><span class="m-chip">Evidence you can reuse</span></div>
            </div>
            <div class="m-hero-art" aria-hidden="true"><span class="m-shard s1"></span><span class="m-shard s2"></span><span class="m-shard s3"></span><span class="m-shard s4"></span><span class="m-shard s5"></span><span class="m-shard s6"></span><span class="m-shard s7"></span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

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
            "Your trajectory",
            "↝",
            "Follow your progress and share it with others.",
            "learning",
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
            else:
                button_label = "Open →"

            if st.button(
                button_label,
                key=f"home-track-{target_type}",
                use_container_width=True,
            ):
                navigate(target_type, target_id)

    learning_heading = "Continue learning" if user else "Explore the learning modules"
    learning_intro = (
        "Pick up the learning journey that is most useful right now."
        if user
        else "You can browse the catalogue and tools without an account. Sign in when you open a learning journey so your progress can be saved."
    )
    st.markdown(
        f"<div class='m-section-title'><h2>{learning_heading}</h2><p>{learning_intro}</p></div>",
        unsafe_allow_html=True,
    )
    available = [(mid, m) for mid, m in MODULES.items() if m["status"] == "Available"]
    if not available:
        st.info("No learning modules are currently published as available.")
    else:
        cols = st.columns(min(2, len(available)))
        for col, (module_id, module) in zip(cols, available):
            with col:
                user_id = user["user_id"] if user else None
                st.markdown(module_card_html(module_id, user_id), unsafe_allow_html=True)
                if user:
                    ratio, done, total = module_completion(user_id, module_id)
                    topic_id = first_incomplete_topic(user_id, module_id)
                    label = "Continue →" if done else "Start module →"
                    if topic_id and st.button(label, key=f"home-continue-{module_id}", type="primary", use_container_width=True):
                        navigate("topic", module_id, topic_id)
                elif st.button("Open learning journey →", key=f"home-continue-{module_id}", type="primary", use_container_width=True):
                    navigate("module", module_id)


def page_catalogue(user: dict | None):
    st.markdown("<div class='m-kicker'>Catalogue</div>", unsafe_allow_html=True)
    st.title("MOSAIC Learn modules")
    st.caption("Follow the learning loop or open a module on its own when you need a specific method or explanation.")

    cols = st.columns(3)
    for idx, (module_id, module) in enumerate(MODULES.items()):
        with cols[idx % 3]:
            st.markdown(module_card_html(module_id, user["user_id"] if user else None), unsafe_allow_html=True)
            if module["status"] == "Available":
                if st.button("Open module →", key=f"open-{module_id}", type="primary", use_container_width=True):
                    navigate("module", module_id)
            else:
                st.button("Coming soon", key=f"soon-{module_id}", disabled=True, use_container_width=True)

    guide_image = asset_image_html(
        "starting-point-heron.png",
        alt="A heron standing among reeds and their reflections in the water",
        css_class="m-start-illustration",
    )
    st.markdown(
        f"""
        <section class="m-start-guide">
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
                <p>Choose the question that comes closest. You can review the recommendation before opening a module.</p>
            </div>
        </section>
        """,
        unsafe_allow_html=True,
    )

    starting_paths = [
        (
            "drivers",
            "◎",
            "Learning",
            "Why is this happening?",
            "Discover the drivers, relationships and feedbacks shaping the system.",
        ),
        (
            "policy-lab",
            "◫",
            "Community",
            "How can people move forward together?",
            "Bring together people, organisations and perspectives around a shared challenge.",
        ),
        (
            "future-pathways",
            "↝",
            "Empowerment",
            "What future do we want to create?",
            "Explore desirable futures and practical pathways towards them.",
        ),
    ]
    choice_cols = st.columns(3)
    for col, (module_id, icon, track, question, description) in zip(choice_cols, starting_paths):
        with col:
            st.markdown(
                f"""
                <div class="m-start-choice {track.lower()}">
                    <div class="m-start-icon" aria-hidden="true">{icon}</div>
                    <h4>{escape(question)}</h4>
                    <p>{escape(description)}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button(
                "This sounds like me",
                key=f"starting-point-{module_id}",
                use_container_width=True,
            ):
                st.session_state.catalogue_recommendation = module_id

    recommendation_id = st.session_state.get("catalogue_recommendation")
    if recommendation_id in MODULES:
        recommended = MODULES[recommendation_id]
        st.markdown(
            f"""
            <div class="m-start-recommendation">
                <div class="m-kicker">Your suggested starting point</div>
                <h3>{escape(recommended['short_title'])}</h3>
                <p>{escape(recommended['description'])}</p>
                <div class="m-module-meta">
                    <span>{escape(recommended['track'])}</span><span>•</span><span>{recommended['estimated_minutes']} min</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        open_col, reset_col = st.columns([1, 1])
        with open_col:
            if st.button(
                "Open module →",
                key="open-recommended-module",
                type="primary",
                use_container_width=True,
            ):
                navigate("module", recommendation_id)
        with reset_col:
            if st.button(
                "Choose a different question",
                key="reset-recommendation",
                use_container_width=True,
            ):
                st.session_state.pop("catalogue_recommendation", None)
                st.rerun()


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
MAX_CMS_RESOURCE_BYTES = 25 * 1024 * 1024


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
    """Build a dependency-free worksheet learners can download and edit."""
    module = MODULES.get(tool.get("module_id")) or {"title": "MOSAIC Learn"}
    lines = [
        f"# {tool['title']}",
        "",
        f"**MOSAIC Learn module:** {module['title']}",
        f"**Suggested time:** {tool['duration']}",
        "",
        tool["description"],
        "",
        "## What you will produce",
        "",
        tool["outcome"],
        "",
        "## How to use this template",
        "",
    ]
    lines.extend(f"{idx}. {step}" for idx, step in enumerate(tool["steps"], start=1))

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
        use_container_width=True,
    )
    return True


@st.cache_data(ttl=120, show_spinner=False)
def _all_tools_zip_cached() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for tool_id, tool in TOOL_DEFINITIONS.items():
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
            if not added_file:
                archive.writestr(f"{tool_id}/{tool_id}.md", tool_template_markdown(tool_id, tool))
    return buffer.getvalue()


def all_tools_zip() -> bytes:
    return _all_tools_zip_cached()


def page_tools(user):
    selected_tool_id = st.session_state.get("tool_id")
    selected_tool = TOOL_DEFINITIONS.get(selected_tool_id)

    st.markdown(
        """
        <div class='m-tools-hero'>
            <div class='m-kicker'>MOSAIC Learn</div>
            <h1>House of Tools</h1>
            <p>All the tools in one place - ready to help you reflect, plan, facilitate and move your land use decisions forward.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    intro_col, download_col = st.columns([2.4, 1], vertical_alignment="center")
    with intro_col:
        st.markdown("### Download a template and make it yours")
        st.caption("Administrators can manage tool descriptions and attach downloadable files in the Content Studio. Repository templates remain available as a fallback.")
    with download_col:
        st.download_button(
            "Download all templates (.zip)",
            data=all_tools_zip(),
            file_name="mosaic-house-of-tools.zip",
            mime="application/zip",
            type="primary",
            use_container_width=True,
        )

    if selected_tool:
        module = MODULES.get(selected_tool.get("module_id"))
        if module:
            st.info(f"You came here from **{module['short_title']}**. The **{selected_tool['title']}** template is shown first.")
        topic_id = st.session_state.get("topic_id")
        if module and topic_id and topic_by_id(selected_tool["module_id"], topic_id):
            if st.button("← Return to the Apply step", key="tools-return-to-topic"):
                navigate("topic", selected_tool["module_id"], topic_id)

    tool_items = list(TOOL_DEFINITIONS.items())
    if selected_tool:
        tool_items.sort(key=lambda item: item[0] != selected_tool_id)
    if not tool_items:
        st.info("No published tools are available yet.")
        return

    cols = st.columns(2, gap="large")
    for idx, (tool_id, tool) in enumerate(tool_items):
        module = MODULES.get(tool.get("module_id"))
        module_label = module.get("short_title") if module else "MOSAIC Learn"
        card_class = "drivers" if tool.get("module_id") == "drivers" else "policy-lab"
        with cols[idx % 2]:
            st.markdown(
                f"""
                <div class='m-tool-library-card {card_class}'>
                    <div class='m-kicker'>{escape(str(module_label))}</div>
                    <h3>{escape(tool['title'])}</h3>
                    <p>{escape(tool['description'])}</p>
                    <div class='m-tool-meta'><span>{escape(tool.get('format',''))}</span><span>{escape(tool.get('duration',''))}</span></div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            with st.expander("What is inside"):
                if tool.get("outcome"):
                    st.markdown(f"**Output:** {tool['outcome']}")
                for step_index, step in enumerate(tool.get("steps") or [], start=1):
                    st.markdown(f"{step_index}. {step}")

            available_files = 0
            for meta in _resource_files_for("tool", tool_id):
                if meta.get("archived"):
                    continue
                kind = str(meta.get("resource_kind") or "Template")
                title = str(meta.get("title") or meta.get("file_name") or "Tool file")
                if meta.get("description"):
                    st.caption(meta["description"])
                if _render_resource_download(
                    meta,
                    key=f"download-db-tool-{tool_id}-{meta['resource_id']}",
                    button_type="primary" if tool_id == selected_tool_id else "secondary",
                    label=f"Download {kind}: {title} ↓",
                ):
                    available_files += 1

            for file_name in TOOL_DOWNLOAD_FILES.get(tool_id, []):
                file_path, file_type, error = configured_tool_file(file_name)
                if error:
                    st.caption(f"⚠ {error}")
                    continue
                label, mime_type = file_type
                st.download_button(
                    f"Download {label} template ↓",
                    data=file_path.read_bytes(),
                    file_name=file_name,
                    mime=mime_type,
                    key=f"download-tool-{tool_id}-{file_name}",
                    type="primary" if tool_id == selected_tool_id and not available_files else "secondary",
                    use_container_width=True,
                )
                available_files += 1

            if not available_files:
                st.download_button(
                    "Download editable template (.md) ↓",
                    data=tool_template_markdown(tool_id, tool),
                    file_name=f"{tool_id}.md",
                    mime="text/markdown",
                    key=f"download-tool-{tool_id}-markdown",
                    type="primary" if tool_id == selected_tool_id else "secondary",
                    use_container_width=True,
                )


def page_learning(user):
    st.markdown("<div class='m-kicker'>Your dashboard</div>", unsafe_allow_html=True)
    st.title("My learning")
    st.caption("Your active modules, progress, learning record and shareable results in one place.")

    section = st.segmented_control(
        "My learning section",
        ["Learning overview", "Results & sharing"],
        default="Learning overview",
        key="learning-section",
        label_visibility="collapsed",
    )
    if section == "Results & sharing":
        page_results(user, embedded=True)
        return

    available = [(mid, m) for mid, m in MODULES.items() if m["status"] == "Available"]
    if not available:
        st.info("No modules are available yet.")
        return

    for module_id, module in available:
        ratio, done, total = module_completion(user["user_id"], module_id)
        next_topic_id = first_incomplete_topic(user["user_id"], module_id)
        next_topic = topic_by_id(module_id, next_topic_id) if next_topic_id else None
        with st.container(border=True):
            a, b = st.columns([3.4, 1], vertical_alignment="center")
            with a:
                st.markdown(f"<div class='m-kicker'>{module['track']} · {module['estimated_minutes']} min</div>", unsafe_allow_html=True)
                st.subheader(module["title"])
                st.progress(ratio, text=f"{round(ratio * 100)}% complete · {done}/{total} learning steps")
                if next_topic:
                    st.caption(f"Next: {next_topic['level']} · {next_topic['title']} · {next_topic['minutes']} min")
            with b:
                if next_topic and st.button("Continue →", key=f"continue-{module_id}", type="primary", use_container_width=True):
                    navigate("topic", module_id, next_topic_id)
                if st.button("Module overview", key=f"overview-{module_id}", use_container_width=True):
                    navigate("module", module_id)


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
                <div class="m-phase-header">
                    <div class="m-phase-number">{meta['number']}</div>
                    <div><h3>{meta['verb']}</h3><p>{meta['tagline']}</p></div>
                    <div class="m-phase-progress">{phase_done}/{len(phase_topics)} complete</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

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
                        if st.button(
                            "Review →" if done else "Start →",
                            key=f"module-topic-{topic['id']}",
                            use_container_width=True,
                            type="primary" if not done else "secondary",
                        ):
                            navigate("topic", module_id, topic["id"])


def render_module_modes(user, module_id: str):
    module = MODULES[module_id]
    topics = learning_topics(module)
    understand = [t for t in topics if t.get("level") == "Understand"]
    apply_steps = [t for t in topics if t.get("level") == "Apply"]
    convince_available = bool(module.get("convince") or _resource_files_for("convince", module_id))
    cols = st.columns(3)
    cards = [
        ("understand", "01", "Understand", "Read the concepts in short, easy-to-scan steps and check your understanding.", f"{len(understand)} learning step{'s' if len(understand) != 1 else ''}"),
        ("apply", "02", "Apply", "Move from concepts to methods, decisions and reflections in your own context.", f"{len(apply_steps)} practical step{'s' if len(apply_steps) != 1 else ''}"),
        (
            "convince",
            "03",
            "Convince",
            "Browse examples, arguments, policy briefs and evidence you can reuse with other people."
            if convince_available
            else "This part of the source material is still under construction.",
            "Resource hub · not graded" if convince_available else "Under construction",
        ),
    ]
    for col, (cls, num, title, text, note) in zip(cols, cards):
        with col:
            st.markdown(f"<div class='m-mode-card {cls}'><div class='m-mode-num'>{num}</div><h3>{title}</h3><p>{text}</p><span class='m-mode-note'>{note}</span></div>", unsafe_allow_html=True)
            if cls == "convince":
                if convince_available:
                    if st.button("Open evidence & resources →", key=f"mode-convince-{module_id}", use_container_width=True, type="secondary"):
                        navigate("convince", module_id)
                else:
                    st.caption("Available after the source section is completed.")
            else:
                candidates = understand if cls == "understand" else apply_steps
                if candidates and st.button(f"Go to {title.lower()} →", key=f"mode-{cls}-{module_id}", use_container_width=True):
                    navigate("topic", module_id, candidates[0]["id"])


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
        if st.button("Start from the beginning →", key=f"full-route-{module_id}", type="primary"):
            navigate("topic", module_id, module["topics"][0]["id"])
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
        if st.button("Start suggested block →", key=f"checkup-start-{module_id}", type="primary"):
            navigate("topic", module_id, lowest)
    else:
        st.markdown("<div class='m-route-card'><h4>Quick route</h4><p>Choose the question where you hesitate most. That is your most useful starting block.</p></div>", unsafe_allow_html=True)
        labels = [label for _, label in entry_points]
        choice = st.selectbox("Where are you least certain?", labels, key=f"quick-route-select-{module_id}")
        chosen_id = next(tid for tid, label in entry_points if label == choice)
        if st.button("Jump to this block →", key=f"quick-route-start-{module_id}", type="primary"):
            navigate("topic", module_id, chosen_id)


def page_module(user):
    module_id = st.session_state.get("module_id", "drivers")
    if module_id not in MODULES:
        module_id = "drivers"
        st.session_state.module_id = module_id
    module = MODULES[module_id]
    ratio, done, total = module_completion(user["user_id"], module_id)

    if st.button("← All modules"):
        navigate("catalogue")

    hero_class = module["track"].lower()
    st.markdown(
        f"""
        <div class="m-module-hero {hero_class}">
            <div class="m-kicker">{escape(module['track'])} · {escape(module['eyebrow'])}</div>
            <h1>{escape(module['title'])}</h1>
            <p>{escape(module['description'])}</p>
            <div class="m-hero-meta"><span class="m-chip">{module['estimated_minutes']} min learning path</span><span class="m-chip">{total} tracked steps</span><span class="m-chip">Self-paced</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if module["status"] != "Available":
        st.info("This module is a catalogue placeholder in the current draft; lesson content has not been migrated.")
        return

    st.markdown("<div class='m-section-title'><h2>Three ways to use this module</h2><p>Understand and Apply form the learning journey. Convince is intentionally different: it is an evidence and communication shelf you can open whenever you need it.</p></div>", unsafe_allow_html=True)
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
        st.caption("Convince resources do not affect completion.")
        next_topic_id = first_incomplete_topic(user["user_id"], module_id)
        if next_topic_id and st.button("Continue learning →", key=f"module-continue-{module_id}", type="primary", use_container_width=True):
            navigate("topic", module_id, next_topic_id)

    role_name = user.get("role") or "Research"
    if role_name in ROLE_CALLOUTS:
        st.markdown(f"<div class='m-role-callout'><strong>For your role</strong><br>{escape(ROLE_CALLOUTS[role_name])}</div>", unsafe_allow_html=True)

    render_building_blocks(module)
    render_module_routes(user, module_id)

    st.markdown("<div class='m-section-title'><h2>Understand & apply</h2><p>This is the tracked learning path. Theory is broken into short cards; practical steps add tools, examples, self-checks and reflections.</p></div>", unsafe_allow_html=True)
    render_module_path(user, module_id)

    if module.get("convince") or _resource_files_for("convince", module_id):
        st.markdown("<div class='m-section-title'><h2>Need to bring someone else with you?</h2><p>Open Convince for downloadable briefs, decks, evidence and communication resources rather than another lesson.</p></div>", unsafe_allow_html=True)
        if st.button("Open Convince: files & resources →", key=f"module-convince-bottom-{module_id}", type="secondary"):
            navigate("convince", module_id)
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
    slides = cards + ([{"summary_slide": True}] if embed_summary else [])

    state_key = f"theory-step-{module_id}-{topic['id']}"
    st.session_state.setdefault(state_key, 1)
    step = int(st.session_state[state_key])
    step = max(1, min(len(slides), step))
    st.session_state[state_key] = step

    st.markdown(
        "<div class='m-reading-intro'><h3>Read the theory one idea at a time</h3>"
        "<p>Move with the arrows. Each screen keeps one idea in focus, while the text itself stays at a comfortable reading width.</p></div>",
        unsafe_allow_html=True,
    )

    item = slides[step - 1]
    bullets = ""
    if item.get("bullets"):
        bullets = "<ul>" + "".join(f"<li>{escape(b)}</li>" for b in item["bullets"]) + "</ul>"
    dots = "".join(
        f"<span class='m-theory-dot {'active' if idx == step else ''}'></span>" for idx in range(1, len(slides) + 1)
    )

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
        card_html = (
            "<div class='m-theory-wrap'>"
            f"<div class='m-theory-progress' aria-label='Theory progress: step {step} of {len(slides)}'>{dots}</div>"
            "<div class='m-theory-card synthesis'><div class='m-synthesis-inner'>"
            f"<div class='m-theory-label'>Synthesis · {step}/{len(slides)}</div>"
            "<h3>Key idea</h3>"
            f"<div class='m-key-idea-panel'><div class='m-rich-text'>{takeaway_html}</div></div>"
            f"{practice_feature}</div></div></div>"
        )
    else:
        body_html = sanitize_rich_text(
            item.get("body_html")
            or item.get("text_html")
            or plain_text_as_html(item.get("text", ""))
        )
        card_html = (
            "<div class='m-theory-wrap'>"
            f"<div class='m-theory-progress' aria-label='Theory progress: step {step} of {len(slides)}'>{dots}</div>"
            "<div class='m-theory-card'><div class='m-theory-inner'>"
            f"<div class='m-theory-label'>{escape(item.get('label', 'Core idea'))} · {step}/{len(slides)}</div>"
            f"<h3>{escape(item['title'])}</h3>"
            f"<div class='m-rich-text'>{body_html}</div>"
            f"{bullets}"
            "</div></div></div>"
        )
    st.markdown(card_html, unsafe_allow_html=True)

    def _set_story_step(target: int):
        st.session_state[state_key] = max(1, min(len(slides), target))

    # A dedicated navigation row keeps controls aligned with the theory panel and gives them breathing room.
    with st.container(key="theory_navigation"):
        prev_col, next_col = st.columns(2, gap="large")
        with prev_col:
            st.button(
                "← Previous idea",
                key=f"theory-prev-{module_id}-{topic['id']}",
                disabled=step <= 1,
                on_click=_set_story_step,
                args=(step - 1,),
            )
        with next_col:
            st.button(
                "Next idea →",
                key=f"theory-next-{module_id}-{topic['id']}",
                disabled=step >= len(slides),
                on_click=_set_story_step,
                args=(step + 1,),
            )
    return embed_summary


def render_learning_extras(module_id: str, topic, *, include_practice: bool = True):
    if include_practice and topic.get("practice_note"):
        st.markdown(
            f"<div class='m-practice-note'><div class='label'>From MOSAIC practice</div><p>{escape(topic['practice_note'])}</p></div>",
            unsafe_allow_html=True,
        )
    tool = topic.get("tool")
    if tool:
        st.markdown(
            f"<div class='m-tool-card'><div class='label'>Try it yourself</div><h4>{escape(tool['name'])}</h4><p>{escape(tool['description'])}</p></div>",
            unsafe_allow_html=True,
        )
        tool_id = tool.get("id")
        if tool_id in TOOL_DEFINITIONS:
            with st.container(key="tool_action"):
                if st.button(
                    f"Open {tool['name']} template →",
                    key=f"open-tool-{module_id}-{topic['id']}",
                    type="primary",
                ):
                    navigate("tools", module_id, topic["id"], tool_id)


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
                type="primary",
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


def page_topic(user):
    module_id = st.session_state.get("module_id", "drivers")
    topic_id = st.session_state.get("topic_id")
    if module_id not in MODULES:
        navigate("catalogue")
        return
    module = MODULES[module_id]
    topic = topic_by_id(module_id, topic_id) if topic_id else None
    if not topic:
        navigate("module", module_id)
        return

    if topic.get("level") == "Convince":
        navigate("convince", module_id)
        return

    topics = learning_topics(module)
    index = next(i for i, t in enumerate(topics) if t["id"] == topic["id"])
    previous_topic = topics[index - 1] if index > 0 else None
    next_topic = topics[index + 1] if index < len(topics) - 1 else None
    saved = _cached_progress(user["user_id"], module_id).get(topic["id"], {})
    ratio, done, total = module_completion(user["user_id"], module_id)

    back_col, prog_col = st.columns([1, 2.5], vertical_alignment="center")
    with back_col:
        if st.button("← Module overview", use_container_width=True):
            navigate("module", module_id)
    with prog_col:
        st.progress(ratio, text=f"Learning progress · {done}/{total} steps")

    st.markdown(
        f"""
        <div class="m-lesson-hero">
            <div class="m-kicker">{escape(topic['level'])} · Step {index + 1} of {len(topics)} · {topic['minutes']} min</div>
            <h1>{escape(topic['title'])}</h1>
            <p>{escape(topic['summary'])}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    summary_embedded = render_theory_story(module_id, topic)

    if topic["id"] == "drivers-as-system":
        render_driver_visual(module)

    if not summary_embedded:
        st.markdown(
            f"<div class='m-takeaway'><strong>Key idea</strong><br>{escape(topic['takeaway'])}</div>",
            unsafe_allow_html=True,
        )

    render_learning_extras(module_id, topic, include_practice=not summary_embedded)

    st.markdown(
        f"<div class='m-reflection'><div class='label'>Apply it to your context</div><p>{escape(topic['prompt'])}</p></div>",
        unsafe_allow_html=True,
    )
    with st.container(key="reflection_form"):
        reflection = st.text_area(
            "Your reflection",
            value=saved.get("reflection", "") or "",
            key=f"reflection-{module_id}-{topic['id']}",
            placeholder="Capture a short observation, example or question you want to remember.",
            height=130,
        )
        st.caption("Saved reflections are collected in your Profile under My reflection notebook.")

    # Keep the quick check at the bottom of the learning content, after the
    # reflection question, so learners first connect the idea to their context.
    render_quiz(user, module_id, topic)

    with st.container(key="reflection_actions"):
        action1, action2 = st.columns([1, 1], gap="medium")
        with action1:
            if st.button("Save reflection", key=f"save-{module_id}-{topic['id']}", use_container_width=True):
                _save_progress(
                    user["user_id"],
                    module_id,
                    topic["id"],
                    reflection=reflection,
                )
                st.success("Reflection saved to your profile")
        with action2:
            if not saved.get("completed"):
                complete_label = "Complete & continue →" if next_topic else "Complete learning path ✓"
                if st.button(complete_label, key=f"complete-{module_id}-{topic['id']}", type="primary", use_container_width=True):
                    _save_progress(
                        user["user_id"],
                        module_id,
                        topic["id"],
                        completed=True,
                        reflection=reflection,
                    )
                    if next_topic:
                        navigate("topic", module_id, next_topic["id"])
                    else:
                        navigate("module", module_id)
            else:
                st.success("✓ Lesson completed")
                if st.button("Mark incomplete", key=f"incomplete-{module_id}-{topic['id']}", use_container_width=True):
                    _save_progress(user["user_id"], module_id, topic["id"], completed=False)
                    st.rerun()

    with st.container(key="lesson_footer"):
        prev_col, mid_col, next_col = st.columns([1, 1, 1], gap="medium")
        with prev_col:
            if previous_topic and st.button("← Previous lesson", use_container_width=True):
                navigate("topic", module_id, previous_topic["id"])
        with mid_col:
            if st.button("Learning path", use_container_width=True):
                navigate("module", module_id)
        with next_col:
            if next_topic and st.button("Next lesson →", use_container_width=True):
                navigate("topic", module_id, next_topic["id"])


def page_convince(user):
    module_id = st.session_state.get("module_id", "drivers")
    if module_id not in MODULES:
        navigate("catalogue")
        return
    module = MODULES[module_id]
    resource_files = _resource_files_for("convince", module_id)
    hub = module.get("convince") or {}
    if not hub and not resource_files:
        navigate("module", module_id)
        return

    hub_title = str(hub.get("title") or f"Convince resources for {module['short_title']}")
    hub_intro = str(
        hub.get("intro")
        or "Download the approved briefs, decks, evidence sheets and other files prepared for this learning journey."
    )

    if st.button("← Module overview"):
        navigate("module", module_id)

    st.markdown(
        f"""
        <div class='m-convince-hero'>
            <div class='m-convince-copy'>
                <div class='m-kicker'>03 · Convince · {escape(module['short_title'])}</div>
                <h1>{escape(hub_title)}</h1>
                <p>{escape(hub_intro)}</p>
            </div>
            <div class='m-convince-art' aria-hidden='true'></div>
        </div>
        <div class='m-hub-note'><strong>This is not another lesson.</strong> Convince is a reusable evidence and communications space. Files here do not affect course completion and are managed separately from Understand and Apply lessons.</div>
        """,
        unsafe_allow_html=True,
    )

    tab_specs = []
    if hub.get("why") or hub.get("pitch"):
        tab_specs.append("Why it matters")
    if hub.get("examples"):
        tab_specs.append("MOSAIC examples")
    if hub.get("audiences"):
        tab_specs.append("Arguments by audience")
    tab_specs.append("Files & resources")
    tabs = st.tabs(tab_specs)
    tab_map = dict(zip(tab_specs, tabs))

    if "Why it matters" in tab_map:
        with tab_map["Why it matters"]:
            st.markdown("### A case you can make quickly")
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

    if "Arguments by audience" in tab_map:
        with tab_map["Arguments by audience"]:
            audiences = list(hub.get("audiences", {}))
            if audiences:
                choice = st.segmented_control("Who are you trying to convince?", audiences, default=audiences[0], key=f"convince-audience-{module_id}")
                item = hub["audiences"][choice]
                tags = "".join(f"<span>{escape(x)}</span>" for x in item.get("use", []))
                st.markdown(f"<div class='m-audience-card'><div class='m-kicker'>{escape(choice)}</div><h3>{escape(item['headline'])}</h3><p>{escape(item['text'])}</p><div class='m-audience-tags'>{tags}</div></div>", unsafe_allow_html=True)
                st.markdown("#### Build your own version")
                st.text_area("Your message or talking points", key=f"convince-notes-{module_id}-{choice}", placeholder="Adapt the case to the person, organisation or decision in front of you...", height=140)

    with tab_map["Files & resources"]:
        st.markdown("### Downloadable Convince resources")
        if resource_files:
            st.caption("These files are managed by MOSAIC Learn administrators and stored in the protected application database.")
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
                            button_type="primary",
                            label="Download ↓",
                        )
        else:
            st.info("No downloadable Convince files have been published for this module yet.")
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
            st.link_button("Open current Convince source page in Coda ↗", source_url)

    st.divider()
    left, right = st.columns(2)
    with left:
        if st.button("Back to learning path", key=f"convince-back-{module_id}", use_container_width=True):
            navigate("module", module_id)
    with right:
        if st.button("Share an experience with the community →", key=f"convince-community-{module_id}", type="primary", use_container_width=True):
            st.session_state.community_module = module_id
            navigate("community")


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

    st.markdown("<div class='m-section-title'><h2>Learning record</h2><p>Your results stay here; your private reflections are gathered in your profile notebook.</p></div>", unsafe_allow_html=True)
    for topic in learning_topics(module):
        p = progress.get(topic["id"], {})
        status = "✓ Completed" if p.get("completed") else "Not completed"
        st.markdown(f"**{topic['level']} · {topic['title']}**  \n{status}")
    if st.button("Open my reflection notebook →", key=f"results-profile-{module_id}"):
        navigate("profile")

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
        if st.button("Generate public result link", key=f"share-{module_id}", type="primary", use_container_width=True):
            token = create_share(user["user_id"], module_id, snapshot)
            base_url = _secret("PUBLIC_APP_URL", "")
            share_link = f"{base_url.rstrip('/')}?share={quote(token)}" if base_url else f"?share={quote(token)}"
            st.session_state.last_share_link = share_link
    with community_col:
        if st.button("Share a reflection with the community →", key=f"community-from-results-{module_id}", use_container_width=True):
            st.session_state.community_module = module_id
            navigate("community")
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
    mycelium_member_count = len(mycelium_state.get("members", [])) if mycelium_state.get("is_member") else 0
    mycelium_request_count = len(mycelium_state.get("incoming", [])) if mycelium_state.get("is_member") else 0

    st.markdown(
        f"""
        <div class="m-community-hero">
            <div class="m-community-hero-grid">
                <div class="m-community-hero-copy">
                    <div class="m-kicker">Community · the MOSAIC mycelium</div>
                    <h1>Turn individual learning into shared knowledge</h1>
                    <p>Read reflections from other learners, compare contexts, add your own experience, and grow your network across the MOSAIC community.</p>
                </div>
                <div class="m-community-snapshot">
                    <div class="label">Community at a glance</div>
                    <div class="m-community-snapshot-grid">
                        <div class="m-community-snapshot-item"><strong>{post_count}</strong><span>{reflection_label}</span></div>
                        <div class="m-community-snapshot-item"><strong>{mycelium_member_count}</strong><span>Mycelium members</span></div>
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

    st.markdown(
        """
        <div class="m-community-section-lead">
            <div>
                <div class="m-kicker">Choose a space</div>
                <h2>Community hub</h2>
                <p>Move between the discussion, the learner network and your private activity updates.</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    nav_cards = [
        (
            "explore",
            "◎",
            "Comments & reflections",
            "Read what others are trying, compare contexts, and join the discussion.",
            f"{post_count} {reflection_label}",
        ),
        (
            "mycelium",
            "✣",
            "Our mycelium",
            "Explore the learner network, make connections, and respond to invitations.",
            (
                f"{mycelium_member_count} members · {mycelium_request_count} requests"
                if mycelium_state.get("is_member")
                else "Optional learner network"
            ),
        ),
        (
            "notifications",
            "🔔",
            "Notifications",
            "Check replies, reactions, and private Mycelium updates that need your attention.",
            f"{unread_on_entry} unread" if unread_on_entry else "All caught up",
        ),
    ]
    nav_cols = st.columns(3, gap="large")
    for nav_col, (target_section, icon, title, description, meta) in zip(nav_cols, nav_cards):
        with nav_col:
            active = section == target_section
            state_label = "OPEN" if active else "VIEW"
            button_label = (
                f"{icon}   {state_label}\n\n"
                f"**{title}**\n\n"
                f"{description}\n\n"
                f"• {meta}"
            )
            if st.button(
                button_label,
                key=f"community-nav-button-{target_section}",
                type="primary" if active else "secondary",
                use_container_width=True,
                help=f"Open {title}",
            ):
                st.session_state["community-section"] = target_section
                st.rerun()

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

        st.markdown(
            """
            <div class="m-community-share-shell">
                <div class="m-kicker">Add to the conversation</div>
                <h3>Share your perspective</h3>
                <p>After reading and responding to others, add your own short reflection, field observation or question to the community.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

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
        with st.form("community-post-form", border=True):
            perspective_text = st.text_area(
                "What would you like to share?",
                placeholder="A result you tried, something that surprised you, a question for others, or a short field reflection...",
                height=135,
                max_chars=1200,
            )
            st.caption("Visible to other learners in the MOSAIC community.")
            submitted = st.form_submit_button("Publish", type="primary")
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
            <div class="m-community-section-lead">
                <div>
                    <div class="m-kicker">Comments & reflections</div>
                    <h2>See what the community is learning</h2>
                    <p>React, ask a follow-up question, compare experiences, or add a practical suggestion to another learner's reflection.</p>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
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
                            use_container_width=True,
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
                            use_container_width=True,
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

        render_share_perspective()

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
                                    use_container_width=True,
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
                                    use_container_width=True,
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
                                use_container_width=True,
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
        if st.button("Read privacy notice →", use_container_width=True):
            navigate("privacy")

    st.markdown("<div class='m-section-title'><h2>My reflection notebook</h2><p>Everything you save while learning is gathered here, across all modules.</p></div>", unsafe_allow_html=True)
    reflections = []
    for module_id, module in MODULES.items():
        if module.get("status") != "Available":
            continue
        module_progress = _cached_progress(user["user_id"], module_id)
        for topic in learning_topics(module):
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

    if not reflections:
        st.info("You have not saved any reflections yet. Add one from a learning step and it will appear here.")
    else:
        module_choices = ["All modules"] + list(dict.fromkeys(item["module"]["short_title"] for item in reflections))
        selected_module = st.selectbox("Show reflections from", module_choices, key="profile-reflection-filter")
        shown = [item for item in reflections if selected_module == "All modules" or item["module"]["short_title"] == selected_module]
        for idx, item in enumerate(shown):
            date_text = str(item["updated_at"])[:10]
            st.markdown(
                f"<div class='m-post'><div class='m-post-meta'><strong>{escape(item['module']['short_title'])}</strong> · {escape(item['topic']['level'])} · {escape(date_text)}</div><p><strong>{escape(item['topic']['title'])}</strong></p><p>{escape(item['text'])}</p></div>",
                unsafe_allow_html=True,
            )
            if st.button("Open learning step →", key=f"profile-reflection-open-{item['module_id']}-{item['topic']['id']}-{idx}"):
                navigate("topic", item["module_id"], item["topic"]["id"])

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
                st.session_state.route = "home"
                st.rerun()
            else:
                st.logout()

    st.divider()
    if user.get("demo"):
        st.caption("Local preview mode: configure Streamlit OIDC to test production authentication.")
        if st.button("Leave local preview"):
            st.session_state.demo_user = None
            st.session_state.route = "home"
            st.rerun()
    else:
        if st.button("Sign out"):
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
    if normalised.get("level") == "Convince":
        raise ValueError("Convince is a resource hub, not a lesson level. Use Convince files instead.")
    save_cms_lesson_draft(module_id, lesson_id, normalised, sort_order, user_id)
    _clear_content_studio_caches()


def _content_studio_publish_lesson(module_id: str, lesson_id: str, payload: dict, sort_order: int, user_id: str) -> None:
    normalised = _normalise_lesson_payload(lesson_id, payload)
    if normalised.get("level") == "Convince":
        raise ValueError("Convince is a resource hub, not a lesson level. Use Convince files instead.")
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
                    "Track",
                    track_options,
                    index=track_options.index(module.get("track") or "Learning"),
                    key=f"studio-module-track-{module_id}",
                )
                track_icon = st.text_input("Track icon", value=module.get("track_icon", "◎"), max_chars=4, key=f"studio-module-icon-{module_id}")
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
                status_options = ["Available", "Coming soon"]
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
                save_pressed = st.form_submit_button("Save module draft", use_container_width=True)
            with publish_col:
                publish_pressed = st.form_submit_button(
                    "Publish module",
                    type="primary",
                    use_container_width=True,
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
                new_track = st.selectbox("Track", ["Learning", "Community", "Empowerment"], key="new-module-track")
                new_description = st.text_area("Description", height=90, key="studio-new-module-description")
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
                        "status": "Available",
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
        if lesson.get("level") != "Convince"
    ]
    lesson_ids = [lesson["id"] for lesson in lessons]

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
                    ["Understand", "Apply"],
                    index=["Understand", "Apply"].index(lesson.get("level", "Understand")),
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
                }
            )
            save_col, publish_col = st.columns(2)
            with save_col:
                save_pressed = st.form_submit_button("Save lesson draft", use_container_width=True)
            with publish_col:
                publish_pressed = st.form_submit_button(
                    "Publish lesson",
                    type="primary",
                    use_container_width=True,
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
                new_level = st.selectbox("Level", ["Understand", "Apply"], key=f"new-lesson-level-{module_id}")
                new_minutes = st.number_input("Minutes", min_value=0, max_value=1000, value=10, key=f"new-lesson-minutes-{module_id}")
                new_summary = st.text_area("Summary", height=80, key=f"new-lesson-summary-{module_id}")
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
            not topic.get("_cms_archived") and topic.get("level") != "Convince"
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
        if not topic.get("_cms_archived") and topic.get("level") != "Convince"
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
                }
            ]
            st.session_state[working_key] = payload
            st.rerun()
        selected_block = "synthesis"
    else:
        block_options = [card["editor_id"] for card in payload["cards"]] + ["synthesis"]
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
        payload["cards"][card_index] = {
            "editor_id": card_id,
            "label": label.strip() or "Core idea",
            "title": title.strip(),
            "body_html": body_html,
        }
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
                use_container_width=True,
            ):
                moved = payload["cards"].pop(card_index)
                payload["cards"].insert(target_position - 1, moved)
                st.session_state[working_key] = payload
                st.rerun()
        with add_col:
            if st.button(
                "＋ Add idea",
                key=f"studio-add-idea-{module_id}-{topic_id}-{card_id}",
                disabled=not is_admin,
                use_container_width=True,
            ):
                new_card_id = uuid4().hex[:16]
                payload["cards"].insert(
                    card_index + 1,
                    {
                        "editor_id": new_card_id,
                        "label": "Core idea",
                        "title": "New idea",
                        "body_html": "<p>Add the text here.</p>",
                    },
                )
                st.session_state[working_key] = payload
                st.session_state[screen_key] = new_card_id
                st.rerun()
        with remove_col:
            if st.button(
                "Remove idea",
                key=f"studio-remove-idea-{module_id}-{topic_id}-{card_id}",
                disabled=not is_admin,
                use_container_width=True,
            ):
                payload["cards"].pop(card_index)
                st.session_state[working_key] = payload
                if payload["cards"]:
                    st.session_state[screen_key] = payload["cards"][min(card_index, len(payload["cards"]) - 1)]["editor_id"]
                else:
                    st.session_state.pop(screen_key, None)
                st.rerun()

    st.session_state[working_key] = payload
    cleaned_payload = normalize_carousel_payload(payload, topic)
    content_valid = len(cleaned_payload["cards"]) == len(payload["cards"])
    if not content_valid:
        st.error("Every idea needs a title before the draft can be saved.")

    st.divider()
    save_col, publish_col, reload_col, open_col = st.columns(4)
    with save_col:
        if st.button("Save draft", key=f"studio-save-ideas-{module_id}-{topic_id}", disabled=not content_valid, use_container_width=True):
            save_carousel_draft(module_id, topic_id, cleaned_payload, user["user_id"])
            _clear_content_studio_caches()
            st.session_state[working_key] = cleaned_payload
            _content_studio_flash("Idea draft saved.")
            st.rerun()
    with publish_col:
        if st.button(
            "Publish ideas",
            key=f"studio-publish-ideas-{module_id}-{topic_id}",
            type="primary",
            disabled=not is_admin or not content_valid,
            use_container_width=True,
        ):
            publish_carousel_content(module_id, topic_id, cleaned_payload, user["user_id"])
            _clear_content_studio_caches()
            st.session_state[working_key] = cleaned_payload
            _content_studio_flash("Ideas published.")
            st.rerun()
    with reload_col:
        if st.button("Reload saved", key=f"studio-reload-ideas-{module_id}-{topic_id}", use_container_width=True):
            latest = get_carousel_content(module_id, topic_id) or {}
            source = latest.get("draft") or latest.get("published") or default_carousel_payload(topic)
            st.session_state[working_key] = normalize_carousel_payload(source, topic)
            st.session_state.pop(screen_key, None)
            st.rerun()
    with open_col:
        is_live = module_id in MODULES and any(item.get("id") == topic_id for item in MODULES[module_id].get("topics", []))
        if st.button("Open lesson →", key=f"studio-open-lesson-{module_id}-{topic_id}", disabled=not is_live, use_container_width=True):
            navigate("topic", module_id, topic_id)


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
            not lesson.get("_cms_archived") and lesson.get("level") != "Convince"
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
        if not lesson.get("_cms_archived") and lesson.get("level") != "Convince"
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
            save_pressed = st.form_submit_button("Save checks draft", use_container_width=True)
        with publish_col:
            publish_pressed = st.form_submit_button(
                "Publish checks",
                type="primary",
                use_container_width=True,
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

    with st.expander("＋ Add file"):
        with st.form(f"studio-resource-add-{scope_type}-{scope_id}"):
            a, b = st.columns([1, 2])
            with a:
                new_kind = st.text_input("Type / label", value=default_kind, key=f"studio-new-resource-kind-{scope_type}-{scope_id}")
                new_sort = st.number_input(
                    "Sort order",
                    min_value=0,
                    max_value=10000,
                    value=(len(resources) + 1) * 10,
                    step=10,
                    key=f"studio-new-resource-sort-{scope_type}-{scope_id}",
                )
            with b:
                new_title = st.text_input("Title", key=f"studio-new-resource-title-{scope_type}-{scope_id}")
            new_description = st.text_area("Description", height=80, key=f"studio-new-resource-description-{scope_type}-{scope_id}")
            upload = st.file_uploader(
                "File",
                type=[ext.lstrip(".") for ext in RESOURCE_UPLOAD_TYPES],
                key=f"studio-new-resource-upload-{scope_type}-{scope_id}",
            )
            add_file = st.form_submit_button("Upload file", type="primary")
        if add_file:
            if not new_title.strip():
                st.error("Add a title for the file.")
            elif upload is None:
                st.error("Choose a file to upload.")
            else:
                file_name, mime_type, file_bytes = _validate_uploaded_resource(upload)
                if file_bytes is not None:
                    save_cms_resource_file(
                        uuid4().hex,
                        scope_type=scope_type,
                        scope_id=scope_id,
                        module_id=module_id,
                        resource_kind=new_kind.strip() or default_kind,
                        title=new_title.strip(),
                        description=new_description.strip(),
                        file_name=file_name,
                        mime_type=mime_type,
                        file_data=file_bytes,
                        sort_order=int(new_sort),
                        updated_by=user["user_id"],
                    )
                    _clear_content_studio_caches()
                    _content_studio_flash("File uploaded and made available to learners.")
                    st.rerun()


def _render_content_studio_convince_files(user: dict, snapshot: dict[str, dict]) -> None:
    st.markdown("### Convince files")
    st.caption(
        "Convince is a resource hub, not a lesson level. Administrators attach briefs, decks, evidence sheets and other approved files directly to a module."
    )
    module_ids = [module_id for module_id, module in snapshot.items() if not module.get("_cms_archived")]
    if not module_ids:
        st.info("Create or restore a module before adding Convince resources.")
        return
    module_id = st.selectbox(
        "Module",
        module_ids,
        format_func=lambda value: snapshot[value]["short_title"],
        key="studio-convince-resource-module",
    )
    existing_hub = bool(snapshot[module_id].get("convince"))
    if not existing_hub:
        st.info("This module has no Convince text section in content.py. Uploading a file will still enable a simple Convince resource hub for the module.")
    _render_content_studio_resource_manager(
        user,
        scope_type="convince",
        scope_id=module_id,
        module_id=module_id,
        heading=f"Files for {snapshot[module_id]['short_title']}",
        default_kind="Resource",
    )


def _render_content_studio_tools(user: dict, snapshot: dict[str, dict]) -> None:
    if not is_administrator(user):
        st.info("Only administrators can manage tools and tool files.")
        return
    st.markdown("### Tools & files")
    st.caption(
        "Edit House of Tools metadata here. Tool definitions use drafts and publishing; downloadable files are managed separately and become available immediately when uploaded."
    )
    tools = _admin_tools_snapshot()
    tool_ids = list(tools)
    active_module_ids = [module_id for module_id, module in snapshot.items() if not module.get("_cms_archived")]

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
        module_options = list(active_module_ids)
        current_module = str(tool.get("module_id") or "")
        if current_module and current_module not in module_options:
            module_options.append(current_module)
        if not module_options:
            module_options = [""]

        with st.form(f"studio-tool-form-{tool_id}"):
            title = st.text_input("Tool title", value=tool.get("title", ""), key=f"studio-tool-title-{tool_id}")
            a, b, c = st.columns(3)
            with a:
                module_id = st.selectbox(
                    "Module",
                    module_options,
                    index=module_options.index(current_module) if current_module in module_options else 0,
                    format_func=lambda value: snapshot.get(value, {}).get("short_title", value or "No module"),
                    key=f"studio-tool-module-{tool_id}",
                )
            with b:
                topic_id = st.text_input(
                    "Related lesson ID (optional)",
                    value=str(tool.get("topic_id") or ""),
                    key=f"studio-tool-topic-{tool_id}",
                )
            with c:
                sort_order = st.number_input(
                    "Sort order",
                    min_value=0,
                    max_value=10000,
                    value=int(tool.get("_cms_sort_order") or 0),
                    step=10,
                    key=f"studio-tool-sort-{tool_id}",
                )
            d, e = st.columns(2)
            with d:
                duration = st.text_input("Suggested time", value=tool.get("duration", ""), key=f"studio-tool-duration-{tool_id}")
            with e:
                format_label = st.text_input("Format", value=tool.get("format", ""), key=f"studio-tool-format-{tool_id}")
            description = st.text_area("Description", value=tool.get("description", ""), height=100, key=f"studio-tool-description-{tool_id}")
            outcome = st.text_area("Expected output", value=tool.get("outcome", ""), height=80, key=f"studio-tool-outcome-{tool_id}")
            steps = st.text_area(
                "How to use it · one step per line",
                value="\n".join(tool.get("steps") or []),
                height=140,
                key=f"studio-tool-steps-{tool_id}",
            )
            payload = copy.deepcopy(tool)
            for key in list(payload):
                if str(key).startswith("_cms_"):
                    payload.pop(key, None)
            payload.update(
                {
                    "id": tool_id,
                    "title": title.strip(),
                    "module_id": module_id,
                    "topic_id": topic_id.strip(),
                    "duration": duration.strip(),
                    "format": format_label.strip(),
                    "description": description.strip(),
                    "outcome": outcome.strip(),
                    "steps": [line.strip() for line in steps.splitlines() if line.strip()],
                }
            )
            save_col, publish_col = st.columns(2)
            with save_col:
                save_tool = st.form_submit_button("Save tool draft", use_container_width=True)
            with publish_col:
                publish_tool = st.form_submit_button(
                    "Publish tool",
                    type="primary",
                    use_container_width=True,
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
                _content_studio_flash("Tool published.")
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
                    _content_studio_flash("Tool archived. It is no longer shown in the House of Tools.")
                    st.rerun()

        _render_content_studio_resource_manager(
            user,
            scope_type="tool",
            scope_id=tool_id,
            module_id=str(tool.get("module_id") or ""),
            heading=f"Files for {tool['title']}",
            default_kind="Template",
        )
    else:
        st.info("No tools exist yet.")

    with st.expander("＋ Add tool"):
        if not active_module_ids:
            st.info("Create a module before adding a tool.")
        else:
            with st.form("studio-add-tool"):
                new_tool_id = st.text_input("Tool ID", placeholder="new-tool", key="studio-new-tool-id").strip().lower()
                new_tool_title = st.text_input("Tool title", placeholder="New tool", key="studio-new-tool-title")
                new_tool_module = st.selectbox(
                    "Module",
                    active_module_ids,
                    format_func=lambda value: snapshot[value]["short_title"],
                    key="studio-new-tool-module",
                )
                new_tool_sort = st.number_input(
                    "Sort order",
                    min_value=0,
                    max_value=10000,
                    value=(len(tools) + 1) * 10,
                    step=10,
                    key="studio-new-tool-sort",
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
                    payload = {
                        "id": new_tool_id,
                        "title": new_tool_title.strip(),
                        "module_id": new_tool_module,
                        "topic_id": "",
                        "duration": "",
                        "format": "Downloadable resource",
                        "description": "",
                        "outcome": "",
                        "steps": [],
                    }
                    _content_studio_save_tool(new_tool_id, payload, int(new_tool_sort), user["user_id"])
                    _content_studio_flash("New tool draft created. Add details and files before publishing it.")
                    st.rerun()


def _render_content_studio_people(user: dict) -> None:
    st.markdown("### Users & roles")
    st.caption(
        "Learners use published content. Editors can edit existing Understand/Apply lesson content and checks in drafts. Administrators can add/archive modules and lessons, publish content, manage Convince/tool files, edit tools and manage roles."
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
    st.dataframe(rows, use_container_width=True, hide_index=True)


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
    st.caption("Understand and Apply are lesson-based. Convince and House of Tools use separately managed downloadable resources.")
    if database_backend() == "sqlite":
        st.info("Local mode stores users, progress, CMS drafts and uploaded resource files in mosaic_learn.db beside the app.")
    else:
        st.success("Production content, uploaded resources and learner data are stored in PostgreSQL. CMS tables are protected by the same server-only RLS/PostgREST hardening as the rest of the app.")


def page_admin(user):
    """Content studio for editors plus administrator-only publishing and resource management."""
    if not is_content_editor(user):
        st.error("Editor or administrator access is required for this page.")
        if st.button("Return home"):
            navigate("home")
        return

    role_label = "Administrator" if is_administrator(user) else "Editor"
    st.markdown(
        f"""
        <div class="m-module-hero learning">
            <div class="m-kicker">MOSAIC Learn · content studio · {escape(role_label)}</div>
            <h1>Content studio</h1>
            <p>Manage Understand and Apply lessons, idea cards and checks. Convince and House of Tools are managed separately as resource/file areas.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    flash = st.session_state.pop("content-studio-flash", None)
    if flash:
        st.success(flash)
    if not is_administrator(user):
        st.info("Editor access: you can edit existing Understand/Apply lesson content, ideas and checks and save drafts. Administrators publish, change structure, manage files and tools, and manage account roles.")

    snapshot = _admin_catalogue_snapshot()
    active_modules = sum(1 for module in snapshot.values() if not module.get("_cms_archived"))
    lesson_count = sum(
        1
        for module in snapshot.values()
        for lesson in module.get("topics", [])
        if not lesson.get("_cms_archived") and lesson.get("level") != "Convince"
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
    b.metric("Understand/Apply lessons", lesson_count)
    c.metric("Idea cards", idea_count)
    d.metric("Managed files", resource_count)

    tab_names = ["Modules & lessons", "Ideas & content", "Checks & quizzes"]
    if is_administrator(user):
        tab_names.extend(["Convince files", "Tools & files", "Users & roles", "Revision history", "Deployment"])
    tabs = st.tabs(tab_names)

    with tabs[0]:
        module_tab, lesson_tab = st.tabs(["Modules", "Lessons"])
        with module_tab:
            _render_content_studio_modules(user, snapshot)
        with lesson_tab:
            _render_content_studio_lessons(user, snapshot)
    with tabs[1]:
        _render_content_studio_ideas(user, snapshot)
    with tabs[2]:
        _render_content_studio_checks(user, snapshot)

    if is_administrator(user):
        with tabs[3]:
            _render_content_studio_convince_files(user, snapshot)
        with tabs[4]:
            _render_content_studio_tools(user, snapshot)
        with tabs[5]:
            _render_content_studio_people(user)
        with tabs[6]:
            _render_content_studio_revisions()
        with tabs[7]:
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

# Route state is intentionally independent from the sidebar. This fixes the
# previous "open module -> home -> open module" rerun loop.
st.session_state.setdefault("route", "home")
st.session_state.setdefault("module_id", "drivers")
# The wordmark uses a normal link so it works even when the sidebar is collapsed.
# Convert that query parameter back into the app's session-state router.
if st.query_params.get("home"):
    st.session_state.route = "home"
    st.session_state.pop("topic_id", None)
    st.session_state.pop("tool_id", None)
    del st.query_params["home"]
# Remove obsolete router state from v1 if the app hot-reloads in an existing session.
st.session_state.pop("goto", None)
st.session_state.pop("selected_module", None)
st.session_state.pop("selected_topic", None)

apply_published_learning_content()
route = st.session_state.route
if route == "results":
    # Keep old sessions and bookmarks working after Results moved under My learning.
    st.session_state["learning-section"] = "Results & sharing"
    st.session_state.route = "learning"
    route = "learning"
protected_routes = {
    "learning",
    "community",
    "module",
    "topic",
    "convince",
    "profile",
    "admin",
}
user = get_current_user(required=route in protected_routes)
if user:
    user = ensure_profile(user)

render_sidebar(user)
render_brandbar()

if route == "home":
    page_home(user)
elif route == "learning":
    page_learning(user)
elif route == "catalogue":
    page_catalogue(user)
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
elif route == "topic":
    page_topic(user)
elif route == "convince":
    page_convince(user)
elif route == "profile":
    page_profile(user)
elif route == "admin":
    page_admin(user)
else:
    st.session_state.route = "home"
    st.rerun()
