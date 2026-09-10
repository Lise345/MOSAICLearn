from __future__ import annotations

import hashlib
from pathlib import Path
from html import escape
from urllib.parse import quote

import streamlit as st

from content import LEVEL_META, MODULES, ROLE_CALLOUTS
from db import (
    create_community_post,
    create_share,
    get_progress,
    get_quiz_results,
    get_share,
    list_community_posts,
    get_user,
    init_db,
    save_quiz_result,
    save_topic_progress,
    upsert_user,
)

st.set_page_config(
    page_title="MOSAIC Learn",
    page_icon="🌍",
    layout="wide",
    initial_sidebar_state="collapsed",
)
init_db()

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

/* MOSAIC interaction system: blue for actions, green for completion/success, wine for editorial accents. */
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
    background:var(--m-blue) !important;
    border-color:var(--m-blue) !important;
    color:#fff !important;
}
.stButton > button[kind="primary"]:hover,
[data-testid="stFormSubmitButton"] > button[kind="primary"]:hover {
    background:#0a3f7f !important;
    border-color:#0a3f7f !important;
}
.stButton > button[kind="secondary"],
[data-testid="stFormSubmitButton"] > button[kind="secondary"] {
    background:#fff !important;
    border-color:#bfc4c7 !important;
    color:var(--m-grey) !important;
}
.stButton > button[kind="secondary"]:hover,
[data-testid="stFormSubmitButton"] > button[kind="secondary"]:hover {
    background:var(--m-blue-10) !important;
    border-color:var(--m-blue) !important;
    color:var(--m-blue) !important;
}
.stButton > button:focus-visible,
[data-testid="stFormSubmitButton"] > button:focus-visible,
[data-testid="stLinkButton"] > a:focus-visible,
.stDownloadButton > button:focus-visible {
    outline:3px solid rgba(13,79,158,.24) !important;
    outline-offset:2px;
}
.stButton > button:disabled, [data-testid="stFormSubmitButton"] > button:disabled {
    background:#f0f0ed !important; border-color:#deded9 !important; color:#8b8b87 !important; opacity:1 !important;
}
[data-testid="stLinkButton"] > a, .stDownloadButton > button {
    background:#fff !important; border:1px solid var(--m-blue) !important; color:var(--m-blue) !important; text-decoration:none !important;
}
[data-testid="stLinkButton"] > a:hover, .stDownloadButton > button:hover {
    background:var(--m-blue-10) !important; color:var(--m-blue) !important;
}
/* Keep native Streamlit selection states in the MOSAIC palette instead of the default pink/red. */
[data-baseweb="tab"][aria-selected="true"] { color:var(--m-blue) !important; }
[data-baseweb="tab-highlight"] { background-color:var(--m-blue) !important; }
[data-testid="stSegmentedControl"] button[aria-pressed="true"] { background:var(--m-blue-10) !important; color:var(--m-blue) !important; border-color:var(--m-blue) !important; }
[data-testid="stProgress"] [role="progressbar"] > div { background-color:var(--m-blue) !important; }
[data-baseweb="tab-list"] { gap:.25rem; }
[data-baseweb="tab"] { font-family:inherit; font-weight:600; }

.m-kicker { text-transform:uppercase; letter-spacing:.11em; font-size:.72rem; color:var(--m-wine); font-weight:700; }
.m-muted { color:var(--m-muted); }
.m-small { font-size:.86rem; }

.m-brandbar { display:flex; align-items:center; justify-content:space-between; gap:1rem; border-bottom:1px solid var(--m-grey); padding:.25rem 0 .85rem; margin-bottom:1.2rem; }
.m-brandname { display:flex; align-items:center; gap:.7rem; font-weight:700; font-size:1.02rem; letter-spacing:.01em; color:var(--m-grey); }
.m-brandname span { font-weight:400; }
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
.m-track-card { border-radius:18px; padding:1.2rem; min-height:170px; border-top:5px solid var(--m-blue); margin-bottom:.7rem; }
.m-track-card.community { border-top-color:var(--m-green); } .m-track-card.learning { border-top-color:var(--m-blue); } .m-track-card.empowerment { border-top-color:var(--m-ochre); }
.m-track-icon { font-size:1.45rem; margin-bottom:.55rem; }
.m-track-card h3 { margin:.1rem 0 .38rem; font-size:1.1rem; }
.m-track-card p { color:var(--m-muted); margin:0; line-height:1.55; font-size:.9rem; }

.m-module-card { border-radius:20px; overflow:hidden; min-height:298px; margin-bottom:.7rem; }
.m-module-art { height:88px; position:relative; overflow:hidden; background:#f6f6f3; }
.m-module-art:before, .m-module-art:after { content:""; position:absolute; border-radius:15px; transform:rotate(-8deg); }
.m-module-art:before { width:42%; height:120%; right:11%; top:-30%; }
.m-module-art:after { width:31%; height:80%; right:-4%; bottom:-20%; }
.m-module-art.learning { border-top:7px solid var(--m-blue); } .m-module-art.learning:before{background:var(--m-cyan)} .m-module-art.learning:after{background:var(--m-blue)}
.m-module-art.community { border-top:7px solid var(--m-green); } .m-module-art.community:before{background:var(--m-green)} .m-module-art.community:after{background:var(--m-lime)}
.m-module-art.empowerment { border-top:7px solid var(--m-ochre); } .m-module-art.empowerment:before{background:var(--m-ochre)} .m-module-art.empowerment:after{background:var(--m-wine)}
.m-module-body { padding:1.05rem 1.1rem 1rem; }
.m-module-body h3 { margin:.45rem 0; font-size:1.2rem; line-height:1.23; }
.m-module-body p { color:var(--m-muted); font-size:.88rem; line-height:1.55; min-height:68px; }
.m-module-meta { display:flex; gap:.45rem; flex-wrap:wrap; margin-top:.65rem; color:var(--m-muted); font-size:.78rem; }
.m-status { display:inline-block; font-size:.7rem; padding:.22rem .55rem; border-radius:999px; font-weight:700; }
.m-status.available { background:var(--m-green-10); color:var(--m-green); } .m-status.soon { background:#efefec; color:#73736f; }

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

.m-phase-header { display:flex; gap:1rem; align-items:flex-start; margin:1.9rem 0 .65rem; }
.m-phase-number { font-size:.72rem; font-weight:700; color:var(--m-wine); letter-spacing:.1em; padding-top:.25rem; }
.m-phase-header h3 { margin:0; font-size:1.25rem; }
.m-phase-header p { margin:.2rem 0 0; color:var(--m-muted); font-size:.88rem; }
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
.m-reading-intro { width:100%; max-width:1360px; margin:1.7rem auto .9rem; }
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
.m-theory-progress { display:flex; gap:.42rem; width:min(380px,58%); margin:0 auto .95rem; }
.m-theory-dot { height:6px; flex:1; border-radius:999px; background:#e5e5e0; }
.m-theory-dot.active { background:var(--m-blue); }

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
.m-driver-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:.8rem; margin:1.5rem auto; }

/* Keyed layout zones prevent Streamlit controls from visually sticking to adjacent cards. */
.st-key-theory_navigation { max-width:1360px; margin:1.15rem auto 1.9rem; }
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
.m-share-card { max-width:760px; border:1px solid var(--m-line); border-radius:18px; padding:1.25rem; background:var(--m-soft); }
.m-community-hero { border:1px solid var(--m-line); border-radius:22px; padding:clamp(1.4rem,4vw,2.6rem); background:linear-gradient(120deg,var(--m-green-10),#fff 60%,var(--m-lime-10)); margin-bottom:1.15rem; border-top:7px solid var(--m-green); } .m-community-hero h1{margin:.35rem 0 .55rem;font-size:clamp(2rem,4vw,3rem);letter-spacing:-.03em}.m-community-hero p{max-width:760px;color:#50504d;line-height:1.65}.m-post{border:1px solid var(--m-line);border-radius:15px;padding:.95rem 1rem;background:white;margin:.65rem 0}.m-post-meta{color:var(--m-muted);font-size:.76rem;margin-bottom:.42rem}.m-post p{margin:0;white-space:pre-wrap;line-height:1.6}

@media (max-width: 820px) {
    .block-container{padding-left:1.25rem;padding-right:1.25rem}
    .m-hero{grid-template-columns:1fr}.m-hero-art{min-height:220px}.m-convince-hero{grid-template-columns:1fr}.m-convince-art{min-height:150px}
    .m-building-grid,.m-evidence-grid{grid-template-columns:repeat(2,minmax(0,1fr));}.m-brandtag{display:none}
    .m-theory-card{min-height:290px}.m-theory-inner{max-width:none}
}
@media (max-width: 620px) {
    .block-container{padding-top:4.75rem;padding-left:1rem;padding-right:1rem}
    .m-building-grid,.m-evidence-grid,.m-resource-grid,.m-driver-grid{grid-template-columns:1fr}
    .m-lesson-row{grid-template-columns:38px minmax(0,1fr)}.m-lesson-time{grid-column:2}
    .m-theory-card{min-height:0;padding:1.5rem 1.25rem;border-radius:19px}.m-theory-progress{width:78%;margin-bottom:.75rem}
    .st-key-theory_navigation [data-testid="stButton"] button{min-width:0;width:100%;font-size:.86rem}
    .m-mini-mark{width:30px;height:30px}.m-brandbar{margin-bottom:.8rem}
}
</style>
""",
    unsafe_allow_html=True,
)


APP_DIR = Path(__file__).resolve().parent
ASSETS_DIR = APP_DIR / "assets"
APPROVED_LOGO = ASSETS_DIR / "mosaic-logo.png"


def brand_mark_html() -> str:
    return "<span class='m-mini-mark' aria-hidden='true'>" + "".join("<i></i>" for _ in range(9)) + "</span>"


def render_brandbar():
    st.markdown(
        f"<div class='m-brandbar'><div class='m-brandname'>{brand_mark_html()}<strong>MOSAIC</strong> <span>Learn</span></div><div class='m-brandtag'>Developing innovative and effective policies for sustainable land use</div></div>",
        unsafe_allow_html=True,
    )


def learning_topics(module):
    """Topics that count toward course progress. Convince is a resource hub."""
    return [topic for topic in module.get("topics", []) if topic.get("level") != "Convince"]


def _secret(name: str, default=""):
    try:
        return st.secrets.get(name, default)
    except Exception:
        return default


def auth_is_configured() -> bool:
    try:
        return "auth" in st.secrets
    except Exception:
        return False


def navigate(route: str, module_id: str | None = None, topic_id: str | None = None):
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
    st.rerun()


def get_current_user():
    """Use Streamlit OIDC when configured; otherwise show an explicit demo login."""
    if auth_is_configured():
        if not st.user.is_logged_in:
            st.markdown(
                """
                <div class="m-module-hero learning">
                    <div class="m-kicker">MOSAIC Learn</div>
                    <h1>Learn from Europe's land-use experiments</h1>
                    <p>Sign in to see your modules, save progress, and share results.</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button("Sign in", type="primary"):
                st.login()
            st.stop()

        email = getattr(st.user, "email", "") or getattr(st.user, "sub", "learner")
        name = getattr(st.user, "name", "") or str(email).split("@")[0]
        user_id = hashlib.sha256(str(email).encode("utf-8")).hexdigest()[:24]
        return {"user_id": user_id, "email": str(email), "name": str(name), "demo": False}

    st.session_state.setdefault("demo_user", None)
    if not st.session_state.demo_user:
        st.markdown(
            """
            <div class="m-module-hero learning">
                <div class="m-kicker">MOSAIC Learn · prototype</div>
                <h1>Try the learning experience</h1>
                <p>This draft uses a demo account locally. Configure OIDC later for real sign-in.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        with st.form("demo_login", border=True):
            name = st.text_input("Name", value="Alex Learner")
            email = st.text_input("Email", value="alex@example.org")
            role = st.selectbox("I mainly work in", list(ROLE_CALLOUTS))
            submitted = st.form_submit_button("Enter MOSAIC Learn", type="primary")
        if submitted:
            if "@" not in email:
                st.error("Enter a plausible email address for the demo.")
                st.stop()
            user_id = hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()[:24]
            st.session_state.demo_user = {
                "user_id": user_id,
                "email": email.strip().lower(),
                "name": name.strip() or "Learner",
                "role": role,
                "demo": True,
            }
            upsert_user(user_id, email, name, role)
            st.rerun()
        st.stop()

    return st.session_state.demo_user


def module_completion(user_id: str, module_id: str):
    module = MODULES[module_id]
    topics = learning_topics(module)
    if not topics:
        return 0.0, 0, 0
    progress = get_progress(user_id, module_id)
    completed = sum(1 for topic in topics if progress.get(topic["id"], {}).get("completed"))
    return completed / len(topics), completed, len(topics)


def first_incomplete_topic(user_id: str, module_id: str) -> str | None:
    module = MODULES[module_id]
    topics = learning_topics(module)
    progress = get_progress(user_id, module_id)
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


def module_card_html(module_id: str, user_id: str) -> str:
    module = MODULES[module_id]
    ratio, done, total = module_completion(user_id, module_id)
    track_class = module["track"].lower()
    status_class = "available" if module["status"] == "Available" else "soon"
    status_text = module["status"]
    progress = progress_bar_html(ratio) if total else ""
    topic_meta = f"{done}/{total} learning steps" if total else "Module structure coming soon"
    return f"""
    <div class="m-module-card">
        <div class="m-module-art {track_class}"></div>
        <div class="m-module-body">
            <span class="m-status {status_class}">{escape(status_text)}</span>
            <div class="m-kicker" style="margin-top:.65rem">{escape(module['track'])}</div>
            <h3>{escape(module['short_title'])}</h3>
            <p>{escape(module['description'])}</p>
            {progress}
            <div class="m-module-meta"><span>{escape(topic_meta)}</span><span>•</span><span>{module['estimated_minutes']} min</span></div>
        </div>
    </div>
    """


def render_sidebar(user):
    route = st.session_state.get("route", "home")
    with st.sidebar:
        if APPROVED_LOGO.exists():
            st.image(str(APPROVED_LOGO), width=178)
            st.caption("Learn")
        else:
            st.markdown(f"<div class='m-sidebar-wordmark'>{brand_mark_html()}<strong>MOSAIC</strong> <span>Learn</span></div>", unsafe_allow_html=True)
            st.caption("Add assets/mosaic-logo.png to use the approved MOSAIC logo.")
        st.caption(f"{user['name']} · {user.get('email', '')}")
        st.markdown("---")

        items = [
            ("home", "⌂  Home"),
            ("learning", "◔  My learning"),
            ("catalogue", "▦  Modules"),
            ("community", "✣  Community"),
            ("results", "↗  Results"),
            ("profile", "○  Profile"),
        ]
        for key, label in items:
            button_type = "primary" if route == key else "secondary"
            if st.button(label, key=f"nav-{key}", use_container_width=True, type=button_type):
                navigate(key)

        if route in {"module", "topic", "convince"}:
            st.markdown("---")
            module_id = st.session_state.get("module_id", "drivers")
            module = MODULES.get(module_id, MODULES["drivers"])
            st.caption("OPEN MODULE")
            st.markdown(f"**{module['short_title']}**")
            ratio, done, total = module_completion(user["user_id"], module_id)
            st.progress(ratio, text=f"{done}/{total} learning steps")
            if st.button("Module overview", use_container_width=True):
                navigate("module", module_id)
            if module.get("convince"):
                if st.button("Convince: evidence & resources", key=f"side-convince-{module_id}", use_container_width=True, type="primary" if route == "convince" else "secondary"):
                    navigate("convince", module_id)

            if route == "topic":
                topic_id = st.session_state.get("topic_id")
                progress = get_progress(user["user_id"], module_id)
                for idx, topic in enumerate(learning_topics(module), start=1):
                    marker = "✓" if progress.get(topic["id"], {}).get("completed") else str(idx)
                    prefix = "→" if topic["id"] == topic_id else marker
                    if st.button(f"{prefix}  {topic['title']}", key=f"side-topic-{topic['id']}", use_container_width=True):
                        navigate("topic", module_id, topic["id"])


def page_home(user):
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
        ("Community", "◫", "Share experiences, questions and reflections with other MOSAIC learners.", "community", None),
        ("Learning", "◎", "Understand the deeper drivers behind current land-use decisions.", "module", "drivers"),
        ("Empowerment", "↝", "Explore future pathways and return with sharper options for action.", "module", "future-pathways"),
    ]
    for col, (title, icon, text, target_type, target_id) in zip(cols, tracks):
        with col:
            st.markdown(f"<div class='m-track-card {title.lower()}'><div class='m-track-icon'>{icon}</div><div class='m-kicker'>{title}</div><h3>{title}</h3><p>{text}</p></div>", unsafe_allow_html=True)
            if target_type == "community":
                if st.button("Open community →", key="home-track-community", use_container_width=True):
                    navigate("community")
            else:
                module = MODULES[target_id]
                if module["status"] == "Available":
                    if st.button(f"Explore {title.lower()} →", key=f"home-track-{target_id}", use_container_width=True):
                        navigate("module", target_id)
                else:
                    st.button("Coming soon", key=f"home-track-{target_id}", disabled=True, use_container_width=True)

    st.markdown("<div class='m-section-title'><h2>Continue learning</h2><p>Pick up the learning journey that is most useful right now.</p></div>", unsafe_allow_html=True)
    available = [(mid, m) for mid, m in MODULES.items() if m["status"] == "Available"]
    cols = st.columns(min(2, len(available)))
    for col, (module_id, module) in zip(cols, available):
        with col:
            ratio, done, total = module_completion(user["user_id"], module_id)
            st.markdown(module_card_html(module_id, user["user_id"]), unsafe_allow_html=True)
            topic_id = first_incomplete_topic(user["user_id"], module_id)
            label = "Continue →" if done else "Start module →"
            if topic_id and st.button(label, key=f"home-continue-{module_id}", type="primary", use_container_width=True):
                navigate("topic", module_id, topic_id)


def page_catalogue(user):
    st.markdown("<div class='m-kicker'>Catalogue</div>", unsafe_allow_html=True)
    st.title("MOSAIC Learn modules")
    st.caption("Follow the learning loop or open a module on its own when you need a specific method or explanation.")

    cols = st.columns(3)
    for idx, (module_id, module) in enumerate(MODULES.items()):
        with cols[idx % 3]:
            st.markdown(module_card_html(module_id, user["user_id"]), unsafe_allow_html=True)
            if module["status"] == "Available":
                if st.button("Open module →", key=f"open-{module_id}", type="primary", use_container_width=True):
                    navigate("module", module_id)
            else:
                st.button("Coming soon", key=f"soon-{module_id}", disabled=True, use_container_width=True)


def page_learning(user):
    st.markdown("<div class='m-kicker'>Your dashboard</div>", unsafe_allow_html=True)
    st.title("My learning")
    st.caption("Your active modules, progress and next lesson in one place.")

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
    progress = get_progress(user["user_id"], module_id)

    for level in ["Understand", "Apply"]:
        phase_topics = [t for t in learning_topics(module) if t["level"] == level]
        if not phase_topics:
            continue
        meta = LEVEL_META[level]
        st.markdown(
            f"""
            <div class="m-phase-header">
                <div class="m-phase-number">{meta['number']}</div>
                <div><h3>{meta['verb']}</h3><p>{meta['tagline']}</p></div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        for topic in phase_topics:
            saved = progress.get(topic["id"], {})
            done = bool(saved.get("completed"))
            state_class = "done" if done else ""
            marker = "✓" if done else meta["icon"]
            st.markdown(
                f"""
                <div class="m-lesson-row">
                    <div class="m-lesson-state {state_class}">{marker}</div>
                    <div><h4>{escape(topic['title'])}</h4><p>{escape(topic['summary'])}</p></div>
                    <div class="m-lesson-time">{topic['minutes']} min</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button("Review step" if done else "Start step", key=f"module-topic-{topic['id']}", use_container_width=True):
                navigate("topic", module_id, topic["id"])


def render_module_modes(user, module_id: str):
    module = MODULES[module_id]
    topics = learning_topics(module)
    understand = [t for t in topics if t.get("level") == "Understand"]
    apply_steps = [t for t in topics if t.get("level") == "Apply"]
    cols = st.columns(3)
    cards = [
        ("understand", "01", "Understand", "Read the concepts in short, easy-to-scan steps and check your understanding.", f"{len(understand)} learning step{'s' if len(understand) != 1 else ''}"),
        ("apply", "02", "Apply", "Move from concepts to methods, decisions and reflections in your own context.", f"{len(apply_steps)} practical step{'s' if len(apply_steps) != 1 else ''}"),
        ("convince", "03", "Convince", "Browse examples, arguments, policy briefs and evidence you can reuse with other people.", "Resource hub · not graded"),
    ]
    for col, (cls, num, title, text, note) in zip(cols, cards):
        with col:
            st.markdown(f"<div class='m-mode-card {cls}'><div class='m-mode-num'>{num}</div><h3>{title}</h3><p>{text}</p><span class='m-mode-note'>{note}</span></div>", unsafe_allow_html=True)
            if cls == "convince":
                if st.button("Open evidence & resources →", key=f"mode-convince-{module_id}", use_container_width=True, type="primary"):
                    navigate("convince", module_id)
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

    stored = get_user(user["user_id"]) or user
    role_name = stored.get("role") or "Research"
    if role_name in ROLE_CALLOUTS:
        st.markdown(f"<div class='m-role-callout'><strong>For your role</strong><br>{escape(ROLE_CALLOUTS[role_name])}</div>", unsafe_allow_html=True)

    render_building_blocks(module)
    render_module_routes(user, module_id)

    st.markdown("<div class='m-section-title'><h2>Understand & apply</h2><p>This is the tracked learning path. Theory is broken into short cards; practical steps add tools, examples, self-checks and reflections.</p></div>", unsafe_allow_html=True)
    render_module_path(user, module_id)

    if module.get("convince"):
        st.markdown("<div class='m-section-title'><h2>Need to bring someone else with you?</h2><p>Open Convince when you need examples, audience-specific arguments or shareable evidence rather than another lesson.</p></div>", unsafe_allow_html=True)
        if st.button("Open Convince: evidence & resources →", key=f"module-convince-bottom-{module_id}", type="primary"):
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
    st.markdown("<div class='m-reading-intro'><h3>The driver system</h3></div>", unsafe_allow_html=True)
    st.markdown(
        f"<div class='m-driver-grid'>{cards}</div><p class='m-muted m-small'>The point is not to choose one box. Ask how these forces interact in place and for a specific actor.</p>",
        unsafe_allow_html=True,
    )


def render_theory_story(module_id: str, topic):
    cards = topic.get("theory_cards") or []
    if not cards:
        st.markdown(f"<div class='m-reading'>{escape(topic.get('body', ''))}</div>", unsafe_allow_html=True)
        return

    state_key = f"theory-step-{module_id}-{topic['id']}"
    st.session_state.setdefault(state_key, 1)
    step = int(st.session_state[state_key])
    step = max(1, min(len(cards), step))
    st.session_state[state_key] = step

    st.markdown(
        "<div class='m-reading-intro'><h3>Read the theory one idea at a time</h3>"
        "<p>Move with the arrows. Each screen keeps one idea in focus, while the text itself stays at a comfortable reading width.</p></div>",
        unsafe_allow_html=True,
    )

    item = cards[step - 1]
    bullets = ""
    if item.get("bullets"):
        bullets = "<ul>" + "".join(f"<li>{escape(b)}</li>" for b in item["bullets"]) + "</ul>"
    dots = "".join(
        f"<span class='m-theory-dot {'active' if idx == step else ''}'></span>" for idx in range(1, len(cards) + 1)
    )

    # Keep this HTML on one logical line. Indented closing tags can be parsed as
    # Markdown code blocks by some Streamlit/Markdown combinations.
    card_html = (
        "<div class='m-theory-wrap'>"
        f"<div class='m-theory-progress' aria-label='Theory progress: step {step} of {len(cards)}'>{dots}</div>"
        "<div class='m-theory-card'><div class='m-theory-inner'>"
        f"<div class='m-theory-label'>{escape(item.get('label', 'Core idea'))} · {step}/{len(cards)}</div>"
        f"<h3>{escape(item['title'])}</h3>"
        f"<p>{escape(item['text'])}</p>"
        f"{bullets}"
        "</div></div></div>"
    )
    st.markdown(card_html, unsafe_allow_html=True)

    def _set_story_step(target: int):
        st.session_state[state_key] = max(1, min(len(cards), target))

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
                disabled=step >= len(cards),
                on_click=_set_story_step,
                args=(step + 1,),
            )


def render_learning_extras(topic):
    if topic.get("practice_note"):
        st.markdown(
            f"<div class='m-practice-note'><div class='label'>From MOSAIC practice</div><p>{escape(topic['practice_note'])}</p></div>",
            unsafe_allow_html=True,
        )
    tool = topic.get("tool")
    if tool:
        st.markdown(
            f"<div class='m-tool-card'><div class='label'>Try the method</div><h4>{escape(tool['name'])}</h4><p>{escape(tool['description'])}</p></div>",
            unsafe_allow_html=True,
        )
    questions = topic.get("self_check") or []
    if questions:
        with st.expander("3-minute self-check"):
            st.caption("Use these as reflection prompts. You do not need to save answers here unless you want to use the reflection box below.")
            for idx, question in enumerate(questions, start=1):
                st.checkbox(question, key=f"selfcheck-{topic['id']}-{idx}")


def render_quiz(user, module_id: str, topic):
    quiz = topic.get("quiz")
    if not quiz:
        return

    st.markdown("### Quick check")
    previous = get_quiz_results(user["user_id"], module_id).get(topic["id"])
    prior_index = int(previous["selected_index"]) if previous else None
    choice = st.radio(
        quiz["question"],
        quiz["options"],
        index=prior_index,
        key=f"quiz-{module_id}-{topic['id']}",
    )
    if st.button("Check answer", key=f"check-{module_id}-{topic['id']}"):
        selected = quiz["options"].index(choice)
        correct = selected == quiz["answer"]
        save_quiz_result(user["user_id"], module_id, topic["id"], selected, correct)
        if correct:
            st.success("Correct. " + quiz["explanation"])
        else:
            st.error("Not quite. " + quiz["explanation"])

    previous = get_quiz_results(user["user_id"], module_id).get(topic["id"])
    if previous:
        if previous["is_correct"]:
            st.caption("✓ Knowledge check completed correctly")
        else:
            st.caption("Try the knowledge check again when you're ready.")


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
    saved = get_progress(user["user_id"], module_id).get(topic["id"], {})
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

    render_theory_story(module_id, topic)

    if topic["id"] == "drivers-as-system":
        render_driver_visual(module)

    st.markdown(
        f"<div class='m-takeaway'><strong>Key idea</strong><br>{escape(topic['takeaway'])}</div>",
        unsafe_allow_html=True,
    )

    render_learning_extras(topic)
    render_quiz(user, module_id, topic)

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

    with st.container(key="reflection_actions"):
        action1, action2 = st.columns([1, 1], gap="medium")
        with action1:
            if st.button("Save reflection", key=f"save-{module_id}-{topic['id']}", use_container_width=True):
                save_topic_progress(
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
                    save_topic_progress(
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
                    save_topic_progress(user["user_id"], module_id, topic["id"], completed=False)
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
    if module_id not in MODULES or not MODULES[module_id].get("convince"):
        navigate("module", module_id if module_id in MODULES else "drivers")
        return
    module = MODULES[module_id]
    hub = module["convince"]

    if st.button("← Module overview"):
        navigate("module", module_id)

    st.markdown(
        f"""
        <div class='m-convince-hero'>
            <div class='m-convince-copy'>
                <div class='m-kicker'>03 · Convince · {escape(module['short_title'])}</div>
                <h1>{escape(hub['title'])}</h1>
                <p>{escape(hub['intro'])}</p>
            </div>
            <div class='m-convince-art' aria-hidden='true'></div>
        </div>
        <div class='m-hub-note'><strong>This is not another lesson.</strong> Convince is a reusable evidence and communications space. Browse it when you need to explain the approach, prepare a meeting, build a brief or show what MOSAIC learned in practice. It does not affect course completion.</div>
        """,
        unsafe_allow_html=True,
    )

    why_tab, examples_tab, audience_tab, resources_tab = st.tabs(["Why it matters", "MOSAIC examples", "Arguments by audience", "Resources"])

    with why_tab:
        st.markdown("### A case you can make quickly")
        cards = "".join(
            f"<div class='m-evidence-card {escape(item.get('accent','blue'))}'><h3>{escape(item['title'])}</h3><p>{escape(item['text'])}</p></div>"
            for item in hub.get("why", [])
        )
        st.markdown(f"<div class='m-evidence-grid'>{cards}</div>", unsafe_allow_html=True)
        if hub.get("pitch"):
            st.markdown(f"<div class='m-pitch'><div class='label'>30-second starting point</div><p>{escape(hub['pitch'])}</p></div>", unsafe_allow_html=True)
            st.caption("Use this as a starting point and adapt it to your audience and context.")

    with examples_tab:
        st.markdown("### What this looked like in MOSAIC")
        st.caption("Short practice examples are easier to reuse in meetings, briefs and presentations than a long theory recap.")
        for item in hub.get("examples", []):
            st.markdown(
                f"<div class='m-example-card'><div class='m-example-place'>{escape(item['place'])}</div><h3>{escape(item['title'])}</h3><p>{escape(item['text'])}</p><div class='m-example-lesson'>What this helps you say · {escape(item['lesson'])}</div></div>",
                unsafe_allow_html=True,
            )

    with audience_tab:
        audiences = list(hub.get("audiences", {}))
        if audiences:
            choice = st.segmented_control("Who are you trying to convince?", audiences, default=audiences[0], key=f"convince-audience-{module_id}")
            item = hub["audiences"][choice]
            tags = "".join(f"<span>{escape(x)}</span>" for x in item.get("use", []))
            st.markdown(f"<div class='m-audience-card'><div class='m-kicker'>{escape(choice)}</div><h3>{escape(item['headline'])}</h3><p>{escape(item['text'])}</p><div class='m-audience-tags'>{tags}</div></div>", unsafe_allow_html=True)
            st.markdown("#### Build your own version")
            st.text_area("Your message or talking points", key=f"convince-notes-{module_id}-{choice}", placeholder="Adapt the case to the person, organisation or decision in front of you...", height=140)

    with resources_tab:
        st.markdown("### Policy briefs, decks and evidence")
        st.caption("The draft shows where these assets belong. Connect the approved MOSAIC files when you have the final public URLs or local assets.")
        resources = hub.get("resources", [])
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


def page_results(user):
    st.markdown("<div class='m-kicker'>Progress</div>", unsafe_allow_html=True)
    st.title("Results & sharing")
    available_ids = [mid for mid, m in MODULES.items() if m["status"] == "Available"]
    module_id = st.selectbox(
        "Module",
        available_ids,
        format_func=lambda mid: MODULES[mid]["short_title"],
        key="results-module-select",
    )
    module = MODULES[module_id]
    ratio, done, total = module_completion(user["user_id"], module_id)
    progress = get_progress(user["user_id"], module_id)
    quizzes = get_quiz_results(user["user_id"], module_id)

    quiz_count = sum(1 for t in learning_topics(module) if t.get("quiz"))
    quiz_correct = sum(1 for q in quizzes.values() if q["is_correct"])

    a, b, c = st.columns(3)
    with a:
        st.markdown(f"<div class='m-stat'><div class='value'>{round(ratio * 100)}%</div><div class='label'>Module progress</div></div>", unsafe_allow_html=True)
    with b:
        st.markdown(f"<div class='m-stat'><div class='value'>{done}/{total}</div><div class='label'>Learning steps completed</div></div>", unsafe_allow_html=True)
    with c:
        quiz_text = f"{quiz_correct}/{quiz_count}" if quiz_count else "—"
        st.markdown(f"<div class='m-stat'><div class='value'>{quiz_text}</div><div class='label'>Knowledge checks correct</div></div>", unsafe_allow_html=True)

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
            <p class="m-muted m-small">Knowledge checks: {quiz_correct}/{quiz_count if quiz_count else '—'}. Private reflections are not included.</p>
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
    st.markdown(
        """
        <div class='m-community-hero'>
            <div class='m-kicker'>Community · the MOSAIC mycelium</div>
            <h1>Turn individual learning into shared knowledge</h1>
            <p>Share a short experience, question or reflection from a learning module, and browse what other learners are noticing in their own land-use contexts.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    browse_tab, share_tab = st.tabs(["Browse reflections", "Create a post"])
    with browse_tab:
        posts = list_community_posts(40)
        if not posts:
            st.info("No reflections have been shared yet. Be the first to add one.")
        for post in posts:
            module = MODULES.get(post.get("module_id"))
            module_label = module["short_title"] if module else "General reflection"
            topic = topic_by_id(post.get("module_id"), post.get("topic_id")) if post.get("module_id") in MODULES and post.get("topic_id") else None
            context = module_label + (f" · {topic['title']}" if topic else "")
            date_text = str(post.get("created_at", ""))[:10]
            st.markdown(
                f"<div class='m-post'><div class='m-post-meta'><strong>{escape(post['author_name'])}</strong> · {escape(context)} · {escape(date_text)}</div><p>{escape(post['post_text'])}</p></div>",
                unsafe_allow_html=True,
            )

    with share_tab:
        available_ids = [mid for mid, m in MODULES.items() if m["status"] == "Available"]
        default_id = st.session_state.get("community_module") if st.session_state.get("community_module") in available_ids else available_ids[0]
        default_index = available_ids.index(default_id)

        module_id = st.selectbox(
            "Related module",
            available_ids,
            index=default_index,
            format_func=lambda mid: MODULES[mid]["short_title"],
            key="community-post-module",
        )
        topic_options = [None] + [t["id"] for t in learning_topics(MODULES[module_id])]
        topic_id = st.selectbox(
            "Related lesson (optional)",
            topic_options,
            format_func=lambda tid: "Whole module / general" if tid is None else topic_by_id(module_id, tid)["title"],
            key="community-post-topic",
        )
        with st.form("community-post-form", border=True):
            text = st.text_area(
                "What would you like to share?",
                placeholder="A result you tried, something that surprised you, a question for others, or a short field reflection...",
                height=150,
                max_chars=1200,
            )
            st.caption("Visible to other learners in the MOSAIC community.")
            submitted = st.form_submit_button("Publish", type="primary")
        if submitted:
            cleaned = text.strip()
            if not cleaned:
                st.error("Write something before publishing.")
            else:
                create_community_post(user["user_id"], user["name"], cleaned, module_id, topic_id)
                st.success("Published to the MOSAIC learning community.")
                st.session_state.pop("community_module", None)


def page_profile(user):
    stored = get_user(user["user_id"]) or user
    st.markdown("<div class='m-kicker'>Account</div>", unsafe_allow_html=True)
    st.title("Profile")
    st.write(f"Signed in as **{stored.get('name', user['name'])}**")
    role = st.selectbox(
        "I mainly work in",
        list(ROLE_CALLOUTS),
        index=list(ROLE_CALLOUTS).index(stored.get("role")) if stored.get("role") in ROLE_CALLOUTS else 0,
    )
    if st.button("Save profile", type="primary"):
        upsert_user(user["user_id"], user["email"], user["name"], role)
        if user.get("demo"):
            st.session_state.demo_user["role"] = role
        st.success("Profile updated")

    st.markdown("<div class='m-section-title'><h2>My reflection notebook</h2><p>Everything you save while learning is gathered here, across all modules.</p></div>", unsafe_allow_html=True)
    reflections = []
    for module_id, module in MODULES.items():
        if module.get("status") != "Available":
            continue
        module_progress = get_progress(user["user_id"], module_id)
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

    st.divider()
    if user.get("demo"):
        st.caption("Demo mode: this is not secure authentication.")
        if st.button("Leave demo account"):
            st.session_state.demo_user = None
            st.session_state.route = "home"
            st.rerun()
    else:
        if st.button("Sign out"):
            st.logout()


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
    c.metric("Knowledge checks", f"{s['knowledge_checks_correct']}/{s['knowledge_checks_total']}")
    st.caption("Private reflections and notes are not included in this shared view.")


# Public result links bypass account login.
share_token = st.query_params.get("share")
if share_token:
    render_brandbar()
    page_public_result(str(share_token))
    st.stop()

user = get_current_user()
if not get_user(user["user_id"]):
    upsert_user(user["user_id"], user["email"], user["name"], user.get("role", "Research"))

# Route state is intentionally independent from the sidebar. This fixes the
# previous "open module -> home -> open module" rerun loop.
st.session_state.setdefault("route", "home")
st.session_state.setdefault("module_id", "drivers")
# Remove obsolete router state from v1 if the app hot-reloads in an existing session.
st.session_state.pop("goto", None)
st.session_state.pop("selected_module", None)
st.session_state.pop("selected_topic", None)

render_sidebar(user)
render_brandbar()

route = st.session_state.route
if route == "home":
    page_home(user)
elif route == "learning":
    page_learning(user)
elif route == "catalogue":
    page_catalogue(user)
elif route == "community":
    page_community(user)
elif route == "module":
    page_module(user)
elif route == "topic":
    page_topic(user)
elif route == "convince":
    page_convince(user)
elif route == "results":
    page_results(user)
elif route == "profile":
    page_profile(user)
else:
    st.session_state.route = "home"
    st.rerun()
