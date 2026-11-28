"""Theme, shell styling and small HTML components for the BDC Transition Agent Suite (synthetic demo UI).

Three selectable themes (Quartz Light, Quartz Dark, Horizon Light) are applied through CSS variables so that every
component, including the HTML tables, follows the chosen theme. No external assets are loaded.
"""
from __future__ import annotations

import html
import json
import re

THEMES = {
    "SAP Quartz Light": {"bg": "#f5f6f7", "surface": "#ffffff", "surface2": "#f2f5f8", "ink": "#1d2d3e", "muted": "#5b738b", "line": "#d9dfe6",
                          "accent": "#0a6ed1", "on_accent": "#ffffff", "accent_soft": "#eaf3fc", "accent_line": "#b9d6f3", "ok": "#188918", "ok_soft": "#eaf6ea", "warn": "#b35c00",
                          "warn_soft": "#fff4e5", "bad": "#bb0000", "bad_soft": "#fdecec", "radius": "8px", "shadow": "0 1px 2px rgba(20,40,60,.05)", "l_source": "#2e7d32", "l_finance": "#7a5ca8", "l_bdc": "#0a6ed1", "l_dsp": "#00838f", "l_consume": "#6b7785", "l_agent": "#b8860b", "l_gov": "#c77700", "l_conn": "#bb0000", "c_fi": "#7a5ca8", "c_rec": "#2e7d32", "c_ctl": "#5b6b7b", "c_ref": "#8a95a1"},
    "SAP Quartz Dark": {"bg": "#10161c", "surface": "#1a2129", "surface2": "#222b35", "ink": "#e8edf2", "muted": "#9fb0c0", "line": "#333f4b",
                         "accent": "#5cb2ff", "on_accent": "#0b1a2a", "accent_soft": "#17304a", "accent_line": "#2f5b88", "ok": "#6fcf6f", "ok_soft": "#183321", "warn": "#f0b050",
                         "warn_soft": "#3a2c14", "bad": "#ff8080", "bad_soft": "#3b1c1c", "radius": "8px", "shadow": "none", "l_source": "#6fcf6f", "l_finance": "#b59af0", "l_bdc": "#5cb2ff", "l_dsp": "#4dd0d8", "l_consume": "#9fb0c0", "l_agent": "#e0b44c", "l_gov": "#f0a040", "l_conn": "#ff8080", "c_fi": "#b59af0", "c_rec": "#6fcf6f", "c_ctl": "#9fb0c0", "c_ref": "#7d8b99"},
    "SAP Horizon Light": {"bg": "#f5f6f7", "surface": "#ffffff", "surface2": "#eef1f4", "ink": "#1d2d3e", "muted": "#556b82", "line": "#cdd5dd",
                           "accent": "#0070f2", "on_accent": "#ffffff", "accent_soft": "#e8f1fe", "accent_line": "#aacbfa", "ok": "#256f3a", "ok_soft": "#e9f5ec", "warn": "#a65b00",
                           "warn_soft": "#fff3e0", "bad": "#aa0808", "bad_soft": "#fdeaea", "radius": "12px", "shadow": "0 0 0 1px rgba(0,0,0,.04), 0 2px 6px rgba(20,40,60,.06)", "l_source": "#2e7d32", "l_finance": "#7a5ca8", "l_bdc": "#0a6ed1", "l_dsp": "#00838f", "l_consume": "#6b7785", "l_agent": "#b8860b", "l_gov": "#c77700", "l_conn": "#bb0000", "c_fi": "#7a5ca8", "c_rec": "#2e7d32", "c_ctl": "#5b6b7b", "c_ref": "#8a95a1"},
}
DEFAULT_THEME = "SAP Quartz Light"

_BASE = """
:root{--bg:%(bg)s;--surface:%(surface)s;--surface2:%(surface2)s;--ink:%(ink)s;--muted:%(muted)s;--line:%(line)s;--accent:%(accent)s;--on-accent:%(on_accent)s;
--accent-soft:%(accent_soft)s;--accent-line:%(accent_line)s;--ok:%(ok)s;--ok-soft:%(ok_soft)s;--warn:%(warn)s;--warn-soft:%(warn_soft)s;
--bad:%(bad)s;--bad-soft:%(bad_soft)s;--radius:%(radius)s;--shadow:%(shadow)s;
--l-source:%(l_source)s;--l-finance:%(l_finance)s;--l-bdc:%(l_bdc)s;--l-dsp:%(l_dsp)s;--l-consume:%(l_consume)s;--l-agent:%(l_agent)s;--l-gov:%(l_gov)s;--l-conn:%(l_conn)s;
--c-fi:%(c_fi)s;--c-rec:%(c_rec)s;--c-ctl:%(c_ctl)s;--c-ref:%(c_ref)s}
.stApp{background:var(--bg)}
header[data-testid="stHeader"],[data-testid="stToolbar"],[data-testid="stDecoration"],footer,#MainMenu{display:none!important}
%(sidebar)s
:where(.stApp) :where(p,li,label,h1,h2,h3,h4,h5,h6,span,div,td,th,summary,small,caption){color:var(--ink)}
:where(.stApp) :where([data-testid="stCaptionContainer"],[data-testid="stCaptionContainer"] *){color:var(--muted)}
.stApp .block-container{max-width:none;padding:4.3rem 0 5.5rem}
.st-key-page_body{width:100%%;max-width:1500px;margin-inline:auto;padding:0 1.5rem}
h1,h2,h3,h4{letter-spacing:-.01em}
/* shell bar */
.st-key-shell{position:fixed;top:0;left:0;right:0;z-index:60;background:var(--surface);border-bottom:1px solid var(--line);padding:.5rem 1.6rem}
.st-key-shell [data-testid="stHorizontalBlock"]{align-items:center;gap:.6rem}
.st-key-shell [data-testid="stSelectbox"],.st-key-shell [data-testid="stCheckbox"]{margin:0}
.st-key-shell [data-testid="stSelectbox"]{display:flex!important;flex-direction:row!important;align-items:center;gap:.5rem}
.st-key-shell [data-testid="stSelectbox"] label p,.st-key-shell [data-testid="stCheckbox"] label p{font-size:.78rem;color:var(--muted);white-space:nowrap}
.st-key-shell [data-testid="stSelectbox"] label{min-height:0;margin:0}
.st-key-shell button[data-testid="stBaseButton-secondary"],.st-key-shell [data-testid="stPopover"] button{min-height:2.1rem;padding:.1rem .7rem}
.ag-brand{display:flex;align-items:center;gap:.7rem}
.ag-logo{position:relative;width:36px;height:36px;border-radius:9px;background:var(--accent);color:var(--on-accent)!important;font-weight:800;display:grid;place-items:center;font-size:1.05rem}
.ag-logo::after{content:"\\2713";position:absolute;right:-4px;bottom:-4px;width:15px;height:15px;border-radius:50%%;background:var(--ok);color:#fff;font-size:.62rem;display:grid;place-items:center;border:2px solid var(--surface)}
.ag-crumb{font-size:.62rem;letter-spacing:.14em;font-weight:700;color:var(--muted);text-transform:uppercase;line-height:1.1}
.ag-title{font-size:1.12rem;font-weight:700;line-height:1.25}
.ag-badge{display:inline-block;padding:.22rem .6rem;border:1px solid var(--accent-line);border-radius:6px;background:var(--accent-soft);color:var(--accent)!important;font-size:.68rem;font-weight:800;letter-spacing:.05em;white-space:nowrap}
.ag-badge.warn{background:var(--warn-soft);border-color:var(--warn);color:var(--warn)!important}
.ag-badge.ok{background:var(--ok-soft);border-color:var(--ok);color:var(--ok)!important}
/* typography */
.ag-kicker{font-size:.7rem;font-weight:800;letter-spacing:.13em;color:var(--muted);text-transform:uppercase}
.ag-h1{font-size:2.05rem;font-weight:800;letter-spacing:-.02em;margin:.2rem 0 .6rem;line-height:1.15}
.ag-lead{color:var(--muted)!important;font-size:1.02rem;line-height:1.6;max-width:640px}
.ag-note{font-size:.82rem;color:var(--muted)}
/* tabs built from radios */
[class*="st-key-tabs_"] [role="radiogroup"],.st-key-bdc_public_page [role="radiogroup"]{gap:0!important;border-bottom:1px solid var(--line);flex-wrap:wrap}
[class*="st-key-tabs_"] [data-testid="stRadioOption"],.st-key-bdc_public_page [data-testid="stRadioOption"]{padding:.65rem 1.05rem .6rem;margin:0 .1rem -1px 0;border-bottom:3px solid transparent;cursor:pointer}
[class*="st-key-tabs_"] [data-testid="stRadioOption"]>div>div:first-child,.st-key-bdc_public_page [data-testid="stRadioOption"]>div>div:first-child{display:none}
[class*="st-key-tabs_"] [data-testid="stRadioOption"] p,.st-key-bdc_public_page [data-testid="stRadioOption"] p{font-weight:600;font-size:.95rem;color:var(--muted)}
[class*="st-key-tabs_"] [data-testid="stRadioOption"][data-selected="true"],.st-key-bdc_public_page [data-testid="stRadioOption"][data-selected="true"]{border-bottom-color:var(--accent)}
[class*="st-key-tabs_"] [data-testid="stRadioOption"][data-selected="true"] p,.st-key-bdc_public_page [data-testid="stRadioOption"][data-selected="true"] p{color:var(--accent)}
/* cards, tiles, chips */
.ag-card{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);padding:.9rem 1rem;box-shadow:var(--shadow)}
.ag-card h4{margin:.15rem 0 .3rem;font-size:.98rem}.ag-card p{margin:.1rem 0;color:var(--muted);font-size:.84rem;line-height:1.45}
.ag-card.sel{border-color:var(--accent);background:var(--accent-soft)}
.ag-flow{display:grid;grid-template-columns:1fr 22px 1fr 22px 1fr 22px 1fr;gap:0;align-items:stretch;margin:.8rem 0}
.ag-flow .arrow{display:grid;place-items:center;color:var(--accent)!important;font-weight:800}
.ag-panel{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);padding:1rem 1.15rem;margin:.7rem 0;box-shadow:var(--shadow)}
.ag-panel .ag-kicker{margin-bottom:.3rem}
.ag-status{border-left:4px solid var(--ok);background:var(--ok-soft);padding:.65rem .9rem;border-radius:4px;margin:.8rem 0}
.ag-status.warn{border-left-color:var(--warn);background:var(--warn-soft)}
.ag-pill{display:inline-block;padding:.1rem .6rem;border:1px solid var(--accent-line);border-radius:99px;background:var(--accent-soft);color:var(--accent)!important;font-size:.75rem;font-weight:600}
.ag-tag{display:inline-block;margin:.2rem .3rem 0 0;padding:.05rem .5rem;border:1px solid var(--line);border-radius:99px;font-size:.7rem;color:var(--muted)!important;background:var(--surface2)}
.ag-dashed{border:1px dashed var(--accent-line);border-radius:var(--radius);padding:.8rem 1rem;background:var(--surface);margin-top:1rem}
.ag-dashed code{font-size:.8rem}
[class*="st-key-tile_"]{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);padding:.8rem .9rem .5rem;box-shadow:var(--shadow);height:100%%}
[class*="st-key-tile_"]:hover{border-color:var(--accent)}
[class*="st-key-tile_"] button p{color:var(--accent)!important}
[class*="st-key-tile_"] button{border:0!important;background:transparent!important;color:var(--accent)!important;padding:0!important;min-height:1.6rem;justify-content:flex-start;font-weight:700}
[class*="st-key-chips"] [data-testid="stColumn"]{width:auto!important;flex:0 0 auto!important;min-width:0!important}
[class*="st-key-chips"] button{border-radius:99px;border:1px solid var(--accent-line);background:var(--surface);color:var(--accent);font-size:.76rem;min-height:1.7rem;padding:.05rem .75rem}
[class*="st-key-chips"] button p{font-size:.76rem;color:var(--accent)}
[class*="st-key-chips"] [data-testid="stHorizontalBlock"]{flex-wrap:wrap!important;gap:.4rem!important}
.st-key-home_body{max-width:1060px;margin:0 auto}
/* streamlit widgets follow the theme */
.stApp [data-testid="stTextInputRootElement"],.stApp [data-testid="stSelectbox"] div:has(>input),.stApp [data-testid="stNumberInputContainer"],.stApp textarea{background:var(--surface)!important;border:1px solid var(--line)!important;border-radius:var(--radius)!important}
.stApp input,.stApp textarea{color:var(--ink)!important;-webkit-text-fill-color:var(--ink)!important;background:transparent!important}
.stApp [data-testid="stSelectbox"] svg,.stApp [data-testid="stSelectbox"] button{color:var(--muted)!important;fill:var(--muted)!important}
[role="listbox"],[data-testid="stPopoverBody"],[data-testid="stSelectboxVirtualDropdown"]{background:var(--surface)!important;color:var(--ink)!important;border:1px solid var(--line)!important;border-radius:var(--radius)}
[role="listbox"] [role="option"]{background:var(--surface)!important;color:var(--ink)!important}
[role="listbox"] [role="option"]:hover,[role="listbox"] [role="option"][data-focused="true"]{background:var(--accent-soft)!important}
[role="listbox"] *{color:var(--ink)!important}
.stApp button[data-testid="stBaseButton-primary"]{background:var(--accent);border-color:var(--accent);color:var(--on-accent);border-radius:var(--radius);font-weight:700}
.stApp button[data-testid="stBaseButton-primary"] p{color:var(--on-accent)}
.stApp button[data-testid="stBaseButton-secondary"]{background:var(--surface);border:1px solid var(--line);color:var(--ink);border-radius:var(--radius)}
[data-testid="stPopover"] button,[data-testid="stPopoverButton"]{background:var(--surface)!important;color:var(--ink)!important;border:1px solid var(--line)!important;border-radius:var(--radius)!important}
[data-testid="stPopover"] button *,[data-testid="stPopoverButton"] *{color:var(--ink)!important}
.stApp button[data-testid="stBaseButton-secondary"]:hover{border-color:var(--accent);color:var(--accent)}
[data-testid="stMetric"]{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);padding:.6rem .8rem;box-shadow:var(--shadow)}
[data-testid="stMetricValue"]{font-size:1.35rem}
[data-testid="stExpander"] details{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius)}
[data-testid="stGraphVizChart"]{background:#fff;border:1px solid var(--line);border-radius:var(--radius);padding:.5rem;overflow:auto}
[data-testid="stCode"],.stApp pre{background:var(--surface2)!important}
[data-testid="stCode"] *,.stApp pre *{color:var(--ink)!important}
.stApp code{color:var(--accent);background:var(--surface2)}
[data-testid="stAlert"]{border-radius:var(--radius)}
/* html tables */
.ag-tablewrap{overflow:auto;border:1px solid var(--line);border-radius:var(--radius);background:var(--surface);margin:.4rem 0 .9rem}
table.ag-table{border-collapse:collapse;width:100%%;font-size:.8rem}
table.ag-table th{position:sticky;top:0;background:var(--surface2);text-align:left;padding:.45rem .65rem;border-bottom:1px solid var(--line);font-size:.72rem;letter-spacing:.04em;text-transform:uppercase;color:var(--muted)!important;white-space:nowrap}
table.ag-table td{padding:.42rem .65rem;border-bottom:1px solid var(--line);vertical-align:top;line-height:1.4}
table.ag-table tr:last-child td{border-bottom:0}
table.ag-table tr:hover td{background:var(--accent-soft)}
.ag-st{display:inline-block;padding:.02rem .5rem;border-radius:99px;font-size:.72rem;font-weight:700;white-space:nowrap}
.ag-st.ok{background:var(--ok-soft);color:var(--ok)!important}.ag-st.warn{background:var(--warn-soft);color:var(--warn)!important}.ag-st.bad{background:var(--bad-soft);color:var(--bad)!important}

/* legal block */
.ag-legal{margin:2rem 0 .5rem;border-top:1px solid var(--line);padding-top:1rem;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:1.4rem;font-size:.74rem;line-height:1.55;color:var(--muted)!important}
.ag-legal b{color:var(--ink)!important;display:block;margin-bottom:.2rem;font-size:.72rem;letter-spacing:.1em;text-transform:uppercase}
.ag-legal a{color:var(--accent)!important}
@media(max-width:900px){.ag-legal{grid-template-columns:1fr}}

/* top bar: wraps instead of colliding */
.st-key-shell [data-testid="stHorizontalBlock"]{flex-wrap:wrap!important;gap:.4rem .8rem!important;align-items:center}
.st-key-shell [data-testid="stColumn"]{flex:0 0 auto!important;width:auto!important;min-width:0!important}
.st-key-shell [data-testid="stColumn"]:has(.ag-brand){flex:1 1 330px!important}
.ag-brand .ag-title,.ag-brand .ag-crumb{white-space:nowrap}
[data-testid="stMetricLabel"],[data-testid="stMetricLabel"] *{white-space:normal!important;overflow:visible!important;text-overflow:clip!important}
.st-key-ag_theme{min-width:250px}.st-key-ag_scn{min-width:350px}
.st-key-shell [data-testid="stPopover"] button,.st-key-shell button{white-space:nowrap}
.st-key-shell .ag-badge{white-space:nowrap}
.ag-badge{max-width:100%%;white-space:normal;line-height:1.35}
@media(max-width:1280px){.stApp .block-container{padding-top:7.4rem}}
/* keyboard focus */
[data-testid="stRadioOption"]:focus-within,button:focus-visible,a:focus-visible{outline:2px solid var(--accent);outline-offset:2px}

/* svg diagrams (bdcwb.diagram) */
.dg-wrap{overflow-x:auto;background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);padding:.5rem;margin:.4rem 0 .9rem}
svg.dg{display:block;height:auto;font-family:inherit}
svg.dg text{font-family:inherit}
.dg-zone{fill:var(--surface2);stroke:var(--line);stroke-width:1}
.dg-zone-t{fill:var(--muted);font-weight:700;letter-spacing:.12em;text-transform:uppercase}
.dg-box{fill:var(--surface);stroke:var(--line);stroke-width:1.2}
.dg-box.dg-dashed{stroke-dasharray:5 4}
.dg-box.dg-bad{stroke:var(--bad);fill:var(--bad-soft)}
.dg-box.dg-sel{stroke:var(--accent);fill:var(--accent-soft)}
.dg-hd{stroke:none}
.dg-t{fill:var(--ink)}
.dg-tb{fill:var(--ink);font-weight:700}
.dg-s{fill:var(--muted)}
.dg-e{stroke:var(--l-bdc);stroke-width:1.7;fill:none}
.dg-e-fi{stroke:var(--c-fi)}
.dg-e-rec{stroke:var(--c-rec)}
.dg-e-ctl{stroke:var(--c-ctl)}
.dg-e-ref{stroke:var(--c-ref)}
.dg-e-blk{stroke:var(--bad)}
.dg-e-gov{stroke:var(--l-gov)}
.dg-dash{stroke-dasharray:6 4}
.dg-ah{stroke:none}
.dg-ah.dg-e{fill:var(--l-bdc)}.dg-ah.dg-e-fi{fill:var(--c-fi)}.dg-ah.dg-e-rec{fill:var(--c-rec)}.dg-ah.dg-e-ctl{fill:var(--c-ctl)}.dg-ah.dg-e-ref{fill:var(--c-ref)}.dg-ah.dg-e-blk{fill:var(--bad)}.dg-ah.dg-e-gov{fill:var(--l-gov)}
.dg-plate{fill:var(--surface);opacity:.96}
.dg-elabel{fill:var(--muted);font-weight:600}
.dg-dot{fill:var(--l-bdc)}.dg-dot-bad{fill:var(--bad)}.dg-dot-ok{fill:var(--ok)}.dg-dot-mute{fill:var(--muted)}
.dg-chip-ok{fill:var(--ok-soft);stroke:var(--ok)}.dg-chip-warn{fill:var(--warn-soft);stroke:var(--warn)}.dg-chip-bad{fill:var(--bad-soft);stroke:var(--bad)}
.dg-chip-t-ok{fill:var(--ok);font-weight:700}.dg-chip-t-warn{fill:var(--warn);font-weight:700}.dg-chip-t-bad{fill:var(--bad);font-weight:700}
.dg-life{stroke:var(--line);stroke-width:1.2;stroke-dasharray:3 4}
/* footer */
.ag-foot{position:fixed;left:0;right:0;bottom:0;z-index:70;background:var(--surface);border-top:1px solid var(--line);padding:.35rem 1.2rem;font-size:.72rem;color:var(--muted)}
.ag-foot b{color:var(--ink)}
@media(max-width:900px){.ag-flow{grid-template-columns:1fr}.ag-flow .arrow{display:none}.ag-h1{font-size:1.6rem}}
"""
_HIDE_SIDEBAR = '[data-testid="stSidebar"],[data-testid="stSidebarCollapsedControl"],[data-testid="collapsedControl"]{display:none!important}'

_OK = re.compile(r"^(COVERS_AS_IS|NO_DELTA|PASS|SYNTHETIC_PASS|OK|OFFLINE_VALIDATED|ENGINEERING_ACCEPTED_SYNTHETIC|COMPLETE|MATCH|DETECTED|True|GENERATED)$")
_WARN = re.compile(r"^(COVERS_WITH_DELTA|NOT_USED|NOT_READY|NOT CONFIGURED|CUSTOM_FIELD|CUSTOM_OBJECT|STRUCTURAL|SEMANTIC_RULE|FIELD_GAP_STANDARD|SECURITY|NO_STANDARD_PRODUCT|UNKNOWN_CATALOG|HOLD|NOT_RUN|NOT_REACHED|UNKNOWN|UNAVAILABLE|PROPOSED|READY_FOR_AUTHORIZED_EXECUTION|INSUFFICIENT_EVIDENCE|PLANNED|PENDING)$")
_BAD = re.compile(r"^(FAIL|FAILED|BLOCKED\w*|REFUSED|ERROR|MISMATCH|False)$")


def css(theme: str, show_sidebar: bool = False) -> str:
    t = THEMES.get(theme, THEMES[DEFAULT_THEME])
    return "<style>" + (_BASE % {**t, "sidebar": "" if show_sidebar else _HIDE_SIDEBAR}) + "</style>"


def esc(v) -> str:
    # '$' would otherwise start markdown math; whitespace (incl. newlines) is collapsed so uploaded text can never end an HTML block and inject markdown
    return html.escape(" ".join(str(v).split()), quote=True).replace("$", "&#36;")


def _cell(v) -> str:
    if isinstance(v, (dict, list, tuple)):
        v = json.dumps(v, default=str)
    s = str(v)
    cls = "ok" if _OK.match(s) else "warn" if _WARN.match(s) else "bad" if _BAD.match(s) else ""
    return f'<span class="ag-st {cls}">{esc(s)}</span>' if cls else esc(s)


MAX_ROWS = 400  # keep the browser light: a table shows at most this many rows and says so


def html_table(rows: list[dict], max_height: int = 420) -> str:
    if not rows:
        return '<div class="ag-note">No rows.</div>'
    total = len(rows)
    rows = rows[:MAX_ROWS]
    cols: list[str] = []
    for r in rows:
        for k in r:
            if k not in cols:
                cols.append(k)
    head = "".join(f"<th>{esc(c)}</th>" for c in cols)
    body = "".join("<tr>" + "".join(f"<td>{_cell(r.get(c, ''))}</td>" for c in cols) + "</tr>" for r in rows)
    more = f'<div class="ag-note">Showing {MAX_ROWS} of {total} rows.</div>' if total > MAX_ROWS else ""
    return f'<div class="ag-tablewrap" style="max-height:{max_height}px"><table class="ag-table"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>{more}'


def badge(text: str, kind: str = "") -> str:
    return f'<span class="ag-badge {kind}">{esc(text)}</span>'


def card(title: str, body: str, selected: bool = False, kicker: str = "") -> str:
    k = f'<div class="ag-kicker">{esc(kicker)}</div>' if kicker else ""
    return f'<div class="ag-card{" sel" if selected else ""}">{k}<h4>{esc(title)}</h4><p>{esc(body)}</p></div>'


def flow(items: list[tuple[str, str, str]], selected: int = 1) -> str:
    n = len(items)
    parts = []
    for i, (t, sub, d) in enumerate(items):
        if i:
            parts.append('<div class="arrow">&rarr;</div>')
        parts.append(f'<div class="ag-card{" sel" if i == selected else ""}"><h4>{esc(t)}</h4><p><b>{esc(sub)}</b></p><p>{esc(d)}</p></div>')
    cols = " ".join(["minmax(0,1fr)"] * n).replace(" minmax", " 22px minmax")
    return f'<div class="ag-flow" style="grid-template-columns:{cols}">' + "".join(parts) + "</div>"


def footer(extra: str = "") -> str:
    return ('<div class="ag-foot"><b>Demo and learning purposes only.</b> Synthetic finance data; no live SAP, BDC or Datasphere system is connected. '
            'SYNTHETIC_PASS is not a live Finance validation. Independent prototype, not affiliated with SAP. &copy; 2026 Prasad Deshpande &middot; Independent work &middot; '
            '<a href="https://www.prasaddeshpande.com" target="_blank" rel="noopener noreferrer">www.prasaddeshpande.com</a>' + extra + "</div>")


def legal_html() -> str:
    """Disclaimer, trademarks and credits, credited to the owner (wording follows www.prasaddeshpande.com)."""
    return ('<div class="ag-legal">'
            '<div><b>Disclaimer</b>Independent assessment prototype by Prasad Deshpande, for demonstration and learning. It is not affiliated with, sponsored or endorsed by SAP SE. '
            'All data is synthetic and no SAP, BDC or Datasphere system is connected. SYNTHETIC_PASS is not a customer Finance validation and nothing here is a recommendation for a customer system. '
            'Provided as is, without warranty.</div>'
            '<div><b>Trademarks</b>SAP, SAP S/4HANA, SAP Business Data Cloud, SAP Datasphere and other SAP products and services mentioned are trademarks or registered trademarks of SAP SE '
            '(or an SAP affiliate company) in Germany and other countries. Streamlit, Databricks and other product names are trademarks of their respective owners. The SAP-style themes are inspired by public SAP design and use no SAP assets. Architected by Prasad&trade; is a mark of Prasad Deshpande.</div>'
            '<div><b>Credits</b>&copy; 2026 Prasad Deshpande. All rights reserved. Architected, designed and developed by Prasad Deshpande. Independent work. '
            'Reference: <a href="https://www.prasaddeshpande.com" target="_blank" rel="noopener noreferrer">www.prasaddeshpande.com</a></div></div>')


_LANE_COLORS = {"source": "#2e7d32", "finance": "#7a5ca8", "bdc": "#0a6ed1", "dsp": "#00838f", "consume": "#888888", "agent": "#b8860b", "gov": "#c77700", "conn": "#bb0000"}
_DOT_BAD = {"NOT REACHED", "UNAVAILABLE", "NOT RUN", "NOT AUTHORIZED"}
_DOT_OK = {"OFFLINE_VALIDATED", "PASS", "SYNTHETIC_PASS"}
_DOT_MUTE = {"OPTIONAL", "REFERENCE"}


def _short(x: str, n: int = 100) -> str:
    return x if len(x) <= n else x[: n - 1] + "\u2026"


def _row(c: dict) -> str:
    st_ = c["status"]
    kind = "bad" if st_ in _DOT_BAD else "ok" if st_ in _DOT_OK else "mute" if st_ in _DOT_MUTE else ""
    iface = f' &middot; {esc(_short(c["interface"], 48))}' if c["interface"] not in ("-", "") else ""
    return (f'<div class="ag-cmp" title="{esc(c["detail"])}"><span class="ag-dot {kind}"></span><span><b>{esc(c["name"])}</b>'
            f'<span class="d">{esc(_short(c["detail"]))}{iface}</span></span></div>')


def _card(title: str, sub: str, rows: str, layer: str, extra: str = "") -> str:
    return (f'<div class="ag-sys {extra}" style="--lc:{_LANE_COLORS[layer]}"><div class="nm">{esc(title)}</div>'
            f'<div class="rl">{esc(_short(sub, 120))}</div>{rows}</div>')
