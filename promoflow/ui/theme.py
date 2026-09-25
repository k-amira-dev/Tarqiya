"""PromoFlow look & feel: University of Sharjah palette (sustainability green, black navigation, light greys).

Streamlit only lets us restyle its widgets through CSS, so this module injects one stylesheet and offers small
helpers for HTML fragments. Widgets that need a specific style get a `key`, which Streamlit exposes as the
CSS class `st-key-<key>` (e.g. `card_identity` → `.st-key-card_identity`).
"""
import html as _html

import streamlit as st

# Eight-point star (two overlapping squares): a nod to the geometric motifs on the UoS website.
LOGO_SVG = (
    '<svg viewBox="0 0 40 40" width="{s}" height="{s}" aria-hidden="true">'
    '<rect x="8" y="8" width="24" height="24" rx="3" fill="#00B386"/>'
    '<rect x="8" y="8" width="24" height="24" rx="3" fill="#00B386" transform="rotate(45 20 20)"/>'
    '<circle cx="20" cy="20" r="6.5" fill="{hole}"/></svg>'
)

CSS = r"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');
:root{
  --g-500:#00B386; --g-600:#009B72; --g-700:#007F5E; --g-50:#E8F7F1; --g-100:#CDEFE2;
  --ink:#0F1411; --ink-2:#3A433E; --muted:#6B756F; --line:#E4E8E5; --bg:#F4F5F2; --white:#FFFFFF;
  --black:#0B0D0C; --amber:#B7791F; --amber-50:#FFF7E6; --red:#C0362C; --red-50:#FDECEA;
  --radius:14px; --shadow:0 1px 2px rgba(15,20,17,.04),0 8px 24px rgba(15,20,17,.06);
}
html,body,.stApp,.stApp p,.stApp label,.stApp input,.stApp textarea,.stApp button,.stApp select,
.stApp li,.stApp [data-testid="stMarkdownContainer"]{font-family:'Plus Jakarta Sans',system-ui,sans-serif}
.stApp{background:var(--bg);color:var(--ink)}
#MainMenu,footer,[data-testid="stToolbarActions"],.stDeployButton,[data-testid="stDecoration"]{display:none!important}
header[data-testid="stHeader"]{background:transparent;height:2.5rem}
/* containers that only hold a <style> block or the 1px cookie iframe take no space */
[data-testid="stElementContainer"]:has(style),[data-testid="stElementContainer"]:has(iframe[height="1"]){display:none}
.block-container{padding:2rem 2.6rem 3rem!important;max-width:1280px!important}
::-webkit-scrollbar{width:8px;height:8px}::-webkit-scrollbar-thumb{background:#CFD6D2;border-radius:8px}

/* ---------- buttons ---------- */
.stButton button,.stFormSubmitButton button,[data-testid="stPageLink-NavLink"]{border-radius:10px!important;transition:all .15s ease}
button[kind="primary"],button[data-testid^="stBaseButton-primary"]{
  background:var(--g-600)!important;border:1px solid var(--g-600)!important;color:#fff!important;font-weight:700!important;
  box-shadow:0 6px 16px rgba(0,155,114,.22)}
button[kind="primary"]:hover,button[data-testid^="stBaseButton-primary"]:hover{background:var(--g-700)!important;border-color:var(--g-700)!important;transform:translateY(-1px)}
button[kind="primary"] p,button[data-testid^="stBaseButton-primary"] p{color:#fff!important;font-weight:700}
button[data-testid^="stBaseButton-secondary"]{background:#fff;border:1px solid var(--line);color:var(--ink);font-weight:600}
button[data-testid^="stBaseButton-secondary"]:hover{border-color:var(--g-500);color:var(--g-700)}

/* ---------- inputs ---------- */
.stApp label p{font-size:13px!important;font-weight:600!important;color:var(--ink-2)!important}
div[data-baseweb="input"],div[data-baseweb="textarea"],div[data-baseweb="select"]>div,
div[data-baseweb="base-input"]{border-radius:10px!important;background:#fff!important}
div[data-baseweb="input"],div[data-baseweb="textarea"],div[data-baseweb="select"]>div{border:1px solid var(--line)!important}
div[data-baseweb="input"]:focus-within,div[data-baseweb="textarea"]:focus-within,
div[data-baseweb="select"]>div:focus-within{border-color:var(--g-500)!important;box-shadow:0 0 0 3px rgba(0,179,134,.15)}
input:disabled,textarea:disabled{-webkit-text-fill-color:var(--ink-2)!important}
[data-baseweb="tag"]{background:var(--g-50)!important;border-radius:8px!important}
[data-baseweb="tag"] span{color:var(--g-700)!important;font-weight:600}
[data-testid="stRadio"] [role="radiogroup"]{gap:.4rem 1.2rem}
[data-testid="stCaptionContainer"]{color:var(--muted)}

/* ---------- sidebar (black, like the UoS navigation bar) ---------- */
section[data-testid="stSidebar"]{background:var(--black);border-right:none}
section[data-testid="stSidebar"] *{color:#E9EEEB}
section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"]{padding:1.2rem 1rem 1.5rem}
[data-testid="stSidebarNav"]{display:none}
section[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"]{padding:.55rem .75rem;margin:1px 0;border:1px solid transparent}
section[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"] p{font-size:13.5px;font-weight:500;color:#C9D1CC}
section[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"]:hover{background:rgba(255,255,255,.06)}
section[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"][aria-current="page"],
section[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"].active{background:rgba(0,179,134,.16);border-color:rgba(0,179,134,.35)}
section[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"][aria-current="page"] p{color:#fff;font-weight:700}
section[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"][disabled],
section[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"][aria-disabled="true"]{opacity:.38}
section[data-testid="stSidebar"] button[data-testid^="stBaseButton-secondary"]{background:transparent;border:1px solid rgba(255,255,255,.18)}
section[data-testid="stSidebar"] button[data-testid^="stBaseButton-secondary"]:hover{border-color:var(--g-500);background:rgba(0,179,134,.1)}
section[data-testid="stSidebar"] hr{border-color:rgba(255,255,255,.1)}
.pf-soon{display:flex;justify-content:space-between;align-items:center;padding:.42rem .75rem;font-size:13px;color:#7E8983!important}
.pf-soon span{color:#7E8983!important}
.pf-soon em{font-style:normal;font-size:10px;font-weight:700;letter-spacing:.5px;text-transform:uppercase;color:#5F6A64!important;
  border:1px solid rgba(255,255,255,.12);border-radius:6px;padding:1px 6px}
.pf-brand{display:flex;align-items:center;gap:10px;padding:2px 4px 18px}
.pf-brand b{font-size:18px;letter-spacing:-.3px;color:#fff}
.pf-brand small{display:block;font-size:10.5px;color:#8F9B94!important;letter-spacing:.4px;margin-top:1px}
.pf-navlabel{font-size:10.5px;font-weight:700;letter-spacing:1.1px;color:#77827C!important;margin:16px 6px 6px;text-transform:uppercase}
.pf-user{display:flex;align-items:center;gap:10px;padding:12px 6px 12px}
.pf-av{width:36px;height:36px;border-radius:50%;background:var(--g-600);display:flex;align-items:center;justify-content:center;font-weight:700;font-size:13px;color:#fff!important;flex-shrink:0}
.pf-user b{font-size:13px;color:#fff;display:block;line-height:1.3}
.pf-user span{font-size:11.5px;color:#8F9B94!important}

/* ---------- cards & page furniture ---------- */
[class*="st-key-card_"]{background:var(--white);border:1px solid var(--line);border-radius:var(--radius);
  padding:22px 24px 24px!important;box-shadow:var(--shadow)}
.pf-card-h{display:flex;align-items:center;gap:12px;margin:0 0 4px}
.pf-card-h .num{width:30px;height:30px;border-radius:9px;background:var(--g-50);color:var(--g-700);font-weight:800;font-size:13px;
  display:flex;align-items:center;justify-content:center;flex-shrink:0}
.pf-card-h h3{font-size:16.5px!important;font-weight:700!important;margin:0!important;padding:0!important;color:var(--ink)}
.pf-card-sub{font-size:12.8px;color:var(--muted);margin:2px 0 14px 42px;line-height:1.5}
.pf-hero{background:linear-gradient(120deg,#0B0D0C 0%,#0F2A21 55%,#00785A 100%);border-radius:18px;padding:26px 30px;color:#fff;
  position:relative;overflow:hidden;margin-bottom:22px}
.pf-hero::after{content:"";position:absolute;right:-60px;top:-60px;width:260px;height:260px;opacity:.18;
  background:repeating-conic-gradient(from 22.5deg,#00B386 0 22.5deg,transparent 22.5deg 45deg);border-radius:50%}
.pf-hero .crumb{font-size:12px;color:#9FE5CD;font-weight:600;letter-spacing:.3px}
.pf-hero h1{font-size:28px!important;font-weight:800!important;margin:6px 0 6px!important;padding:0!important;color:#fff!important;letter-spacing:-.5px}
.pf-hero p{color:#CFE0D8;font-size:14px;margin:0;max-width:720px;line-height:1.55}
.pf-chip{display:inline-flex;align-items:center;gap:6px;border-radius:999px;padding:4px 11px;font-size:11.5px;font-weight:700;letter-spacing:.2px}
.pf-chip.draft{background:rgba(255,255,255,.12);color:#fff;border:1px solid rgba(255,255,255,.25)}
.pf-chip.green{background:var(--g-50);color:var(--g-700)}
.pf-chip.amber{background:var(--amber-50);color:var(--amber)}
.pf-chip.red{background:var(--red-50);color:var(--red)}
.pf-chip.grey{background:#EEF1EF;color:var(--muted)}
.pf-kv{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin:4px 0 10px}
.pf-kv div{background:#F8FAF8;border:1px solid var(--line);border-radius:11px;padding:10px 13px}
.pf-kv span{display:block;font-size:11px;color:var(--muted);font-weight:600;text-transform:uppercase;letter-spacing:.5px}
.pf-kv b{display:block;font-size:14px;color:var(--ink);font-weight:600;margin-top:3px;overflow-wrap:anywhere;line-height:1.35}
.pf-note{font-size:12.5px;color:var(--muted);background:#F8FAF8;border:1px dashed #D5DDD8;border-radius:10px;padding:9px 12px;margin-top:6px}
.pf-stat{background:#F8FAF8;border:1px solid var(--line);border-radius:12px;padding:10px 12px}
.pf-stat b{display:block;font-size:26px;font-weight:800;letter-spacing:-.5px;color:var(--ink);line-height:1.1}
.pf-stat span{font-size:11.5px;color:var(--muted);font-weight:600}
.pf-check{display:flex;gap:10px;align-items:flex-start;padding:10px 0;border-top:1px solid var(--line)}
.pf-check:first-of-type{border-top:none}
.pf-check .ic{width:22px;height:22px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:800;flex-shrink:0;margin-top:1px}
.pf-check .ic.ok{background:var(--g-50);color:var(--g-700)}
.pf-check .ic.warn{background:var(--amber-50);color:var(--amber)}
.pf-check .ic.fail{background:var(--red-50);color:var(--red)}
.pf-check .ic.info{background:#EEF1EF;color:var(--muted)}
.pf-check b{font-size:13px;color:var(--ink);display:block}
.pf-check small{font-size:12px;color:var(--muted);line-height:1.45;display:block;margin-top:1px}
.pf-err{background:var(--red-50);color:var(--red);border-radius:10px;padding:10px 14px;font-size:13px;margin:8px 0}
.pf-err li{margin:2px 0}

/* ---------- dashboard tiles ---------- */
.pf-tiles{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}
.pf-tile{background:#fff;border:1px solid var(--line);border-radius:16px;padding:20px 22px;box-shadow:var(--shadow);min-height:132px}
.pf-tile.hi{background:var(--g-600);border-color:var(--g-600)}
.pf-tile.hi *{color:#fff!important}
.pf-tile h4{font-size:16px!important;font-weight:700!important;margin:0 0 6px!important;padding:0!important}
.pf-tile p{font-size:13px;color:var(--muted);margin:0;line-height:1.5}
</style>
"""

LOGIN_CSS = r"""
<style>
section[data-testid="stSidebar"],[data-testid="stSidebarCollapsedControl"],[data-testid="stExpandSidebarButton"]{display:none!important}
header[data-testid="stHeader"]{display:none}
.stApp{background:
  radial-gradient(900px 480px at 110% -10%,rgba(0,179,134,.20),transparent 60%),
  radial-gradient(700px 420px at -10% 110%,rgba(0,179,134,.16),transparent 60%),
  var(--bg)}
.block-container{max-width:1100px!important;padding-top:0!important}
.pf-topbar{display:flex;align-items:center;justify-content:space-between;background:var(--black);color:#fff;
  margin:0 -100vw 0;padding:14px 100vw;}
.pf-topbar .l{display:flex;align-items:center;gap:10px;font-weight:700;font-size:15px}
.pf-topbar .r{font-size:12.5px;color:#AEB9B3}
[class*="st-key-auth_card"]{background:#fff;border:1px solid var(--line);border-radius:22px;padding:34px 36px 26px!important;
  box-shadow:0 30px 60px -20px rgba(15,20,17,.18),0 2px 6px rgba(15,20,17,.04);margin-top:9vh}
.pf-auth-mark{display:flex;justify-content:center;margin-bottom:10px}
.pf-auth-h{text-align:center;font-size:25px;font-weight:800;letter-spacing:-.5px;margin:0}
.pf-auth-s{text-align:center;font-size:13.5px;color:var(--muted);margin:6px 0 22px}
[class*="st-key-auth_card"] [data-testid="stForm"]{border:none;padding:0}
.pf-auth-foot{text-align:center;font-size:12px;color:var(--muted);margin-top:16px;line-height:1.55}
.pf-legal{text-align:center;font-size:11.5px;color:#8B948F;margin-top:18px}
</style>
"""


def inject() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def inject_auth() -> None:
    st.markdown(LOGIN_CSS, unsafe_allow_html=True)


def html(fragment: str, target=None) -> None:
    """Render an HTML fragment. Lines are joined because blank lines break Streamlit's HTML blocks."""
    (target or st).markdown(" ".join(line.strip() for line in fragment.splitlines() if line.strip()),
                            unsafe_allow_html=True)


def esc(text) -> str:
    return _html.escape("" if text is None else str(text))


def logo(size: int = 30, hole: str = "#0B0D0C") -> str:
    return LOGO_SVG.format(s=size, hole=hole)


def card_header(number: str, title: str, subtitle: str = "", target=None) -> None:
    sub = f'<div class="pf-card-sub">{esc(subtitle)}</div>' if subtitle else ""
    html(f'<div class="pf-card-h"><div class="num">{esc(number)}</div><h3>{esc(title)}</h3></div>{sub}', target)


def initials(name: str | None) -> str:
    parts = [p for p in (name or "").replace(".", " ").split() if p.lower() not in {"dr", "prof"}]
    return ("".join(p[0] for p in parts[:2]) or "?").upper()
