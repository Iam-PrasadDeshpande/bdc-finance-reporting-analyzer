"""Architecture diagrams built on bdcwb.diagram: landscape across systems, agent-suite architecture, data-flow pipeline, deployment options,
orchestration sequence, and a layered graph for dependencies and concepts. All derived from the scenario run or from the project's own model;
all synthetic; nothing here is a tenant-verified fact.

Landscape layout rules (so nothing overlaps): agent suite on top, read-only adapters below it, then one zone per layer with system boxes,
numbered zone-to-zone flow arrows (listed in a flow key), skipping flows in a corridor under the zones, and the reconciliation overlay at the bottom.
"""
from __future__ import annotations

from collections import OrderedDict

from .diagram import Svg, esc, fit, tw, wrap

W = 1440
PAD = 24
LANES = [("source", "Source systems"), ("finance", "Finance consolidation"), ("bdc", "SAP Business Data Cloud"), ("dsp", "Datasphere"), ("consume", "Consumption")]
BAD = {"NOT REACHED", "UNAVAILABLE", "NOT RUN", "NOT AUTHORIZED"}
SHORT_ROW = [("Released CDS interface views", "CDS interface views"), ("Advanced DataStore objects", "ADSO"), ("Customer-managed product packages", "Customer-managed"), ("(optional)", "(opt.)"),
             ("FI replication from source systems", "FI replication"), ("Reference reporting output", "Reference output")]
FLOW_NAME = {"data products / extraction": "extraction", "analytic model consumption": "consumption", "history (reference only)": "reference (BW)", "mapped FI": "mapped FI",
             "ODP": "ODP", "acquisition": "acquisition", "optional": "optional"}
CIRC = "123456789"


def _short_row(name: str) -> str:
    for a, b in SHORT_ROW:
        name = name.replace(a, b)
    return name


def _group(comps: list[dict], lane: str) -> "OrderedDict[str, list[dict]]":
    g: "OrderedDict[str, list[dict]]" = OrderedDict()
    for c in comps:
        if c["layer"] == lane:
            g.setdefault(c["system"], []).append(c)
    return g


def _chip(svg: Svg, x, y, text, kind="ok", size=10.5, anchor="start") -> float:
    w = tw(text, size, True) + 14
    x0 = x if anchor == "start" else x - w / 2
    svg.add(f'<rect class="dg-chip-{kind}" x="{x0:.1f}" y="{y - 11:.1f}" width="{w:.1f}" height="17" rx="8.5"/>')
    svg.add(f'<text class="dg-chip-t-{kind}" x="{x0 + w / 2:.1f}" y="{y + 1.5:.1f}" text-anchor="middle" font-size="{size}">{esc(text)}</text>')
    return w


def _num(svg: Svg, x, y, n: int, cls="dg-e") -> None:
    """Numbered marker on a flow arrow; the flow key explains it."""
    svg.add(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="9.5" class="dg-plate"/><circle cx="{x:.1f}" cy="{y:.1f}" r="9" class="{cls}" style="fill:var(--surface);stroke-width:1.5"/>')
    svg.add(f'<text x="{x:.1f}" y="{y + 3.7:.1f}" text-anchor="middle" font-size="10.5" font-weight="700" class="dg-tb">{n}</text>')


def landscape_svg(L: dict, agents_view: list[dict], tools_n: int) -> tuple[str, Svg]:
    comps, flows = L["components"], L["flows"]
    lanes = [(k, t) for k, t in LANES if any(c["layer"] == k for c in comps)]
    n = len(lanes)
    gap = 58
    colw = (W - 2 * PAD - (n - 1) * gap) / n
    lane_x = {k: PAD + i * (colw + gap) for i, (k, _) in enumerate(lanes)}
    lane_i = {k: i for i, (k, _) in enumerate(lanes)}
    inner = colw - 24

    # ---------------------------------------------------------------- agent suite band (top)
    agent_boxes = ([("Cockpit UI", "Home, journey, ontology, agents"), ("Orchestrator", "planner and validator; refuses writes")] +
                   [(a["name"], f"stages {', '.join(str(s) for s in a['stages'])} - {a['tool_count']} tools") for a in agents_view] +
                   [("Typed tool layer", f"{tools_n} MCP-style tools"), ("Domain engines", "12 deterministic engines"), ("Evidence store", "persisted results")])
    gov_boxes = [("Business rule book", "AI proposes, human approves"), ("Approval queue", "draft-only proposals"), ("Execution planner", "3 modes, writes blocked"),
                 ("Acceptance gates", "G01-G15"), ("Audit log", "redacted, idempotent")]
    ag_top = 10
    ag_row_y = ag_top + 44
    gov_y = ag_row_y + 56 + 34
    ag_bottom = gov_y + 46 + 14
    bus_y = ag_bottom + 20
    ad_y = bus_y + 26
    ad_h = 46
    zone_y = ad_y + ad_h + 36
    y0 = zone_y + 48

    # ---------------------------------------------------------------- system boxes
    layout, boxes = [], {}
    col_bottom = {}
    for k, title in lanes:
        y = y0
        for sysid, items in _group(comps, k).items():
            head = next((c for c in items if c["kind"] == "System"), None)
            rows = [c for c in items if c is not head]
            name = head["name"] if head else "Analytic models and consumers"
            sub = head["detail"] if head else "Datasphere analytic models and optional downstream consumers"
            name_lines = wrap(name, inner, 14, 2, True)
            sub_lines = wrap(sub, inner, 10.5, 3)
            h = 18 + len(name_lines) * 17 + len(sub_lines) * 13 + 12 + len(rows) * 21 + 10
            b = {"lane": k, "sys": sysid, "name": name_lines, "sub": sub_lines, "rows": rows, "x": lane_x[k], "y": y, "w": colw, "h": h, "opt": bool(head and head["status"] == "OPTIONAL")}
            layout.append(b)
            boxes["CON" if (k == "consume" and sysid == "-") else sysid] = b
            y += h + 14
        col_bottom[k] = y - 14
    zone_bottom = max(col_bottom.values()) + 16

    # ---------------------------------------------------------------- group flows into numbered zone-level arrows
    groups: "OrderedDict[tuple, dict]" = OrderedDict()
    for f in flows:
        if f["plane"] not in ("data", "fi", "ref"):
            continue
        a, c = ("CON" if f["from"] == "CON.AM" else f["from"]), ("CON" if f["to"] == "CON.AM" else f["to"])
        if a not in boxes or c not in boxes:
            continue
        la, lc = boxes[a]["lane"], boxes[c]["lane"]
        if la == lc:
            continue
        name = "FI replication" if f["label"].startswith("FI replication") else FLOW_NAME.get(f["label"], f["label"])
        key = (la, lc, f["plane"], name)
        g = groups.setdefault(key, {"pairs": [], "name": name, "plane": f["plane"], "la": la, "lc": lc})
        pair = f"{a} to {'analytic models' if c == 'CON' else c}" + (f" ({f['label'].split('cc')[-1].strip()})" if f["label"].startswith("FI replication") else "")
        if pair not in g["pairs"]:
            g["pairs"].append(pair)
    order = sorted(groups.values(), key=lambda g: (lane_i[g["la"]], lane_i[g["lc"]], g["plane"]))
    for i, g in enumerate(order, 1):
        g["no"] = i
    # recon
    rec = [f for f in flows if f["plane"] == "recon"]
    n_corr = sum(1 for g in order if lane_i[g["lc"]] - lane_i[g["la"]] > 1)
    corr_y0 = zone_bottom + 22
    rec_y0 = corr_y0 + n_corr * 20 + 34
    rec_h = 14 + len(rec) * 28
    key_y = rec_y0 + rec_h + 14
    key_rows = max(1, (len(order) + 1) // 2)
    legend_y = key_y + 22 + key_rows * 18 + 22
    H = legend_y + 26

    svg = Svg(W, H, "Landscape architecture across systems", 1100)

    # ---------------------------------------------------------------- agent suite zone
    zx, zw = PAD - 8, W - 2 * PAD + 16
    svg.rect(zx, ag_top, zw, ag_bottom - ag_top, "dg-zone", 10)
    svg.add(f'<rect x="{zx:.1f}" y="{ag_top}" width="{zw:.1f}" height="4" rx="2" style="fill:var(--l-agent)"/>')
    svg.text(zx + 14, ag_top + 28, "AGENT SUITE (THIS WORKBENCH)", "dg-zone-t", size=11)
    needs = [max(tw(t, 12, True), max(tw(s_, 10) for s_ in [s]) * 0.62) + 26 for t, s in agent_boxes]
    avail = zw - 28 - (len(agent_boxes) - 1) * 14
    scale = avail / sum(needs)
    widths = [w * scale for w in needs]
    x = zx + 14
    tool_x = None
    for i, ((t, s), bw) in enumerate(zip(agent_boxes, widths)):
        svg.rect(x, ag_row_y, bw, 56, "dg-box", 8)
        svg.box(f"agent:{t}", x, ag_row_y, bw, 56, "node", t)
        svg.text(x + 10, ag_row_y + 22, t, "dg-tb", size=12, bold=True, max_w=bw - 20)
        for j, ln in enumerate(wrap(s, bw - 20, 10, 2)):
            svg.text(x + 10, ag_row_y + 38 + j * 12, ln, "dg-s", size=10, max_w=bw - 20)
        if i:
            svg.add(f'<path class="dg-e dg-e-ctl" d="M{x - 14:.1f},{ag_row_y + 28:.1f} H{x:.1f}" fill="none" marker-end="url(#{svg.marker("dg-e-ctl")})"/>')
        if t == "Typed tool layer":
            tool_x = x + bw / 2
        x += bw + 14
    svg.text(zx + 14, gov_y - 8, "GOVERNANCE", "dg-zone-t", size=10.5)
    gw = (zw - 28 - (len(gov_boxes) - 1) * 14) / len(gov_boxes)
    for i, (t, s) in enumerate(gov_boxes):
        gx = zx + 14 + i * (gw + 14)
        svg.rect(gx, gov_y, gw, 46, "dg-box", 8)
        svg.add(f'<rect x="{gx:.1f}" y="{gov_y}" width="4" height="46" rx="2" style="fill:var(--l-gov)"/>')
        svg.box(f"gov:{t}", gx, gov_y, gw, 46, "node", t)
        svg.text(gx + 12, gov_y + 20, t, "dg-tb", size=12, bold=True, max_w=gw - 20)
        svg.text(gx + 12, gov_y + 35, s, "dg-s", size=10, max_w=gw - 20)

    # ---------------------------------------------------------------- adapters (read only, not configured) and their connectors
    adapter_label = {"source": "Backend metadata adapter", "finance": "CFIN / BW adapter", "bdc": "BDC catalog adapter", "dsp": "Datasphere adapter", "consume": "Consumer adapter"}
    svg.text(PAD, bus_y - 4, "", "dg-s", size=1)
    centers = []
    for k, _ in lanes:
        ax, aw = lane_x[k] + 8, colw - 16
        svg.rect(ax, ad_y, aw, ad_h, "dg-box dg-bad dg-dashed", 8)
        svg.box(f"adapter:{k}", ax, ad_y, aw, ad_h, "node", adapter_label[k])
        svg.text(ax + 12, ad_y + 20, adapter_label[k], "dg-tb", size=11.5, bold=True, max_w=aw - 24)
        svg.text(ax + 12, ad_y + 36, "read only - NOT CONFIGURED", "dg-s", size=10, max_w=aw - 24)
        cx = ax + aw / 2
        centers.append(cx)
        svg.add(f'<path class="dg-e dg-e-blk dg-dash" d="M{cx:.1f},{ad_y:.1f} V{bus_y:.1f}" fill="none"/>')
        svg.add(f'<path class="dg-e dg-e-blk dg-dash" d="M{cx:.1f},{ad_y + ad_h:.1f} V{zone_y - 1:.1f}" fill="none" marker-end="url(#{svg.marker("dg-e-blk")})"/>')
    if tool_x is not None:
        svg.add(f'<path class="dg-e dg-e-blk dg-dash" d="M{tool_x:.1f},{ag_bottom:.1f} V{bus_y:.1f}" fill="none"/>')
    xs = centers + [tool_x if tool_x is not None else centers[0]]
    svg.add(f'<path class="dg-e dg-e-blk dg-dash" d="M{min(xs):.1f},{bus_y:.1f} H{max(xs):.1f}" fill="none"/>')

    if tool_x is not None:
        cw = tw("NOT REACHED (DEMO)", 10, True) + 14
        svg.add(f'<rect class="dg-plate" x="{tool_x + 6:.1f}" y="{bus_y - 12:.1f}" width="{cw + 4:.1f}" height="22" rx="8"/>')
        _chip(svg, tool_x + 8, bus_y + 1, "NOT REACHED (DEMO)", "bad", 10)
    # ---------------------------------------------------------------- zones and system boxes
    for k, title in lanes:
        zx_ = lane_x[k] - 8
        svg.rect(zx_, zone_y, colw + 16, zone_bottom - zone_y, "dg-zone", 10)
        svg.add(f'<rect x="{zx_:.1f}" y="{zone_y}" width="{colw + 16:.1f}" height="4" rx="2" style="fill:var(--l-{k})"/>')
        svg.text(zx_ + 12, zone_y + 28, title, "dg-zone-t", size=11, max_w=colw - 8)
    for b in layout:
        x, y, w, h = b["x"], b["y"], b["w"], b["h"]
        svg.rect(x, y, w, h, "dg-box" + (" dg-dashed" if b["opt"] else ""), 8)
        svg.add(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="5" rx="2" style="fill:var(--l-{b["lane"]})"/>')
        svg.box(f"sys:{b['sys']}", x, y, w, h, "node", " ".join(b["name"]))
        yy = y + 14
        for ln in b["name"]:
            yy += 17
            svg.text(x + 12, yy, ln, "dg-tb", size=14, bold=True, max_w=inner)
        for ln in b["sub"]:
            yy += 13
            svg.text(x + 12, yy, ln, "dg-s", size=10.5, max_w=inner)
        yy += 12
        svg.add(f'<line x1="{x + 12:.1f}" y1="{yy - 6:.1f}" x2="{x + w - 12:.1f}" y2="{yy - 6:.1f}" class="dg-life"/>')
        for c in b["rows"]:
            yy += 21
            bad = c["status"] in BAD
            dot = "dg-dot-bad" if bad else "dg-dot-mute" if c["status"] in ("OPTIONAL", "REFERENCE") else "dg-dot-ok" if c["status"] == "OFFLINE_VALIDATED" else "dg-dot"
            tip = esc(c["detail"] + ((" | " + c["interface"]) if c["interface"] not in ("-", "") else ""))
            svg.add(f'<g><title>{tip}</title><circle class="{dot}" cx="{x + 16:.1f}" cy="{yy - 4:.1f}" r="3.6"/>')
            svg.text(x + 26, yy, _short_row(c["name"]), "dg-t", size=11.5, max_w=w - 38)
            svg.add("</g>")

    # ---------------------------------------------------------------- zone-level flow arrows
    slot: dict[tuple[int, int], int] = {}
    corr = 0
    for g in order:
        ia, ic = lane_i[g["la"]], lane_i[g["lc"]]
        cls = {"fi": "dg-e dg-e-fi", "ref": "dg-e dg-e-ref", "data": "dg-e"}[g["plane"]]
        dash = g["plane"] == "ref"
        tip = esc(g["name"] + ": " + "; ".join(g["pairs"]))
        if ic - ia == 1 or ia - ic == 1:
            k = slot.get((ia, ic), 0)
            slot[(ia, ic)] = k + 1
            y = y0 + 22 + k * 30
            xa = lane_x[g["la"]] + colw + 8
            xb = lane_x[g["lc"]] - 8
            if ia > ic:
                xa, xb = lane_x[g["la"]] - 8, lane_x[g["lc"]] + colw + 8
            svg.add(f"<g><title>{tip}</title>")
            svg.path([(xa, y), (xb, y)], cls, dash=dash, r=0)
            _num(svg, (xa + xb) / 2, y, g["no"], cls.split()[-1])
            svg.add("</g>")
        else:
            xa = lane_x[g["la"]] + colw / 2 + corr * 10
            xb = lane_x[g["lc"]] + colw / 2 - corr * 10
            yc = zone_bottom + 12 + corr * 20 + 8
            corr += 1
            svg.add(f"<g><title>{tip}</title>")
            svg.path([(xa, zone_bottom), (xa, yc), (xb, yc), (xb, zone_bottom + 1)], cls, dash=dash)
            _num(svg, (xa + xb) / 2, yc, g["no"], cls.split()[-1])
            svg.add("</g>")

    # ---------------------------------------------------------------- reconciliation overlay (below the zones, nothing crosses it)
    svg.text(PAD, rec_y0 - 6, "RECONCILIATION (SYNTHETIC VERDICTS, NOT LIVE VALIDATION)", "dg-zone-t", size=11)
    endpoints = {"L1": ("source", "bdc"), "L2": ("bdc", "dsp"), "L3": ("source", "dsp"), "B1": ("source", "finance"), "B4": ("finance", "bdc")}
    for i, f in enumerate(rec):
        key = f["label"].split()[0]
        a, c = endpoints.get(key, ("source", "bdc"))
        if a not in lane_x or c not in lane_x:
            continue
        y = rec_y0 + 14 + i * 28
        x1, x2 = lane_x[a] + colw / 2 - 20, lane_x[c] + colw / 2 + 20
        svg.add(f'<path class="dg-e dg-e-rec" d="M{x1:.1f},{y - 7:.1f} V{y:.1f} H{x2:.1f} V{y - 7:.1f}" fill="none"/>')
        txt = f["label"].split(":")[0]
        verdict = f["status"]
        chip_w = tw(verdict, 10.5, True) + 14
        w = tw(txt, 11, True) + 12 + chip_w + 18
        mid = (x1 + x2) / 2
        svg.add(f'<rect class="dg-plate" x="{mid - w / 2:.1f}" y="{y - 13:.1f}" width="{w:.1f}" height="26" rx="6"/>')
        svg.text(mid - w / 2 + 9, y + 4, txt, "dg-tb", size=11, bold=True)
        _chip(svg, mid - w / 2 + 9 + tw(txt, 11, True) + 10, y + 1, verdict, "ok" if "PASS" in verdict else "warn")

    # ---------------------------------------------------------------- flow key
    svg.text(PAD, key_y + 4, "FLOW KEY", "dg-zone-t", size=11)
    half = (W - 2 * PAD) / 2
    for i, g in enumerate(order):
        col, row = i % 2, i // 2
        x, y = PAD + col * half, key_y + 24 + row * 18
        _num(svg, x + 9, y - 4, g["no"], {"fi": "dg-e-fi", "ref": "dg-e-ref", "data": "dg-e"}[g["plane"]])
        pairs = "; ".join(g["pairs"])
        svg.text(x + 24, y, f"{g['name']}: {pairs}", "dg-t", size=11, max_w=half - 40)

    # ---------------------------------------------------------------- legend
    ly = legend_y
    x = PAD
    for cls, lab, dash in (("dg-e", "data flow", False), ("dg-e dg-e-fi", "Finance (FI) flow", False), ("dg-e dg-e-ref", "reference / optional", True),
                           ("dg-e dg-e-rec", "reconciliation level", False), ("dg-e dg-e-ctl", "control", False), ("dg-e dg-e-blk", "interface not reached", True)):
        svg.add(f'<path class="{cls}{" dg-dash" if dash else ""}" d="M{x:.1f},{ly:.1f} H{x + 28:.1f}" fill="none"/>')
        svg.text(x + 34, ly + 4, lab, "dg-s", size=11)
        x += 34 + tw(lab, 11) + 26
    return svg.render(), svg


# ====================================================================================================================== shared card helper
def _card(svg: Svg, bid: str, x, y, w, h, title: str, lines: list[str] | None = None, accent: str | None = None, cls: str = "dg-box", size: float = 12,
          sub_size: float = 10.5, kind: str = "node", wrap_lines: int = 3) -> None:
    svg.rect(x, y, w, h, cls, 8)
    svg.box(bid, x, y, w, h, kind, title)
    if accent:
        svg.add(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="4" rx="2" style="fill:var(--{accent})"/>')
    ty = y + 24
    for t in wrap(title, w - 20, size, 2, True):
        svg.text(x + 10, ty, t, "dg-tb", size=size, bold=True, max_w=w - 20)
        ty += size + 4
    for ln in (lines or []):
        for t in wrap(ln, w - 20, sub_size, wrap_lines):
            svg.text(x + 10, ty, t, "dg-s", size=sub_size, max_w=w - 20)
            ty += sub_size + 3.5


def _auto_h(title: str, lines: list[str] | None, w: float, size: float = 12, sub_size: float = 10.5, wrap_lines: int = 3) -> float:
    h = 24 + len(wrap(title, w - 20, size, 2, True)) * (size + 4)
    for ln in (lines or []):
        h += len(wrap(ln, w - 20, sub_size, wrap_lines)) * (sub_size + 3.5)
    return h + 12


def _zone(svg: Svg, x, y, w, h, title: str, accent: str) -> None:
    svg.rect(x, y, w, h, "dg-zone", 10)
    svg.add(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="4" rx="2" style="fill:var(--{accent})"/>')
    svg.text(x + 14, y + 26, title, "dg-zone-t", size=11, max_w=w - 28)


def _arrow(svg: Svg, pts, cls="dg-e dg-e-ctl", dash=False, label=None, r=6) -> None:
    svg.path(pts, cls, dash=dash, label=label, r=r)


# ====================================================================================================================== agent-suite architecture
def agent_arch_svg(res: dict, scn: str) -> tuple[str, Svg]:
    from . import agents, landscape
    cv = agents.catalog_view()
    tools = agents.tool_catalog()
    by_agent: dict[str, list[dict]] = {}
    for t in tools:
        by_agent.setdefault(t["agent"], []).append(t)
    main_w = W - 2 * PAD - 340
    gx = PAD + main_w + 44          # governance column (a 44px gutter carries the connectors)
    gw = W - PAD - gx
    svg = Svg(W, 10, "Agent suite architecture", 1100)
    zones: dict[str, tuple[float, float]] = {}
    y = 10

    # ---- experience
    zones["exp"] = (y, 112)
    _zone(svg, PAD, y, main_w, 112, "EXPERIENCE", "l-source")
    bw = (main_w - 28 - 2 * 36) / 3
    bx = PAD + 14
    for i, (t, s) in enumerate((("Users", "Architect, SAP team, Finance owner"), ("Cockpit UI", "Home, Delta journey, Ontology, Agents, Architecture & operations"), ("Old demo", "v0.12 reporting analyzer on one page"))):
        _card(svg, f"exp:{t}", bx + i * (bw + 36), y + 38, bw, 64, t, [s], size=12, sub_size=10, wrap_lines=2)
    _arrow(svg, [(bx + bw, y + 70), (bx + bw + 36, y + 70)])
    y += 112 + 26

    # ---- orchestration
    zones["orch"] = (y, 132)
    _zone(svg, PAD, y, main_w, 132, "ORCHESTRATION (PLANNER AND VALIDATOR)", "l-agent")
    ow = (main_w - 28 - 3 * 36) / 4
    ox = [PAD + 14 + i * (ow + 36) for i in range(4)]
    _card(svg, "orch:request", ox[0], y + 38, ow, 84, "Request", ["Plain-language request and the selected scenario"])
    _card(svg, "orch:planner", ox[1], y + 38, ow, 84, "Planner: deterministic (demo, active)", ["Reproducible and testable; routes to the lead agent"], accent="ok", wrap_lines=3)
    _card(svg, "orch:llm", ox[2], y + 38, ow, 84, "LLM planner (not configured)", ["Would plug in here behind the same contract"], cls="dg-box dg-dashed dg-bad")
    _card(svg, "orch:validator", ox[3], y + 38, ow, 84, "Plan validator", ["Known tools and allowed authority only; write requests refused; unrecognised plans execute nothing"], accent="l-gov", wrap_lines=4)
    for i in range(3):
        _arrow(svg, [(ox[i] + ow, y + 80), (ox[i + 1], y + 80)], dash=(i == 1))
    _arrow(svg, [(PAD + main_w / 2, y - 26), (PAD + main_w / 2, y)])
    y += 132 + 26

    # ---- agents
    aw = (main_w - 28 - 2 * 24) / 3
    heads = []
    for a in cv:
        tl = wrap(f"{a['name']} - stages {', '.join(str(s) for s in a['stages'])}", aw - 20, 12, 2, True)
        bl = wrap(a["blurb"], aw - 20, 10, 4)
        heads.append((tl, bl))
    start_off = max(24 + len(tl) * 16 + len(bl) * 13.5 + 10 for tl, bl in heads)
    rows_max = max(len(v) for v in by_agent.values())
    card_h = start_off + rows_max * 14 + 12
    zh = 38 + card_h + 14
    zones["agents"] = (y, zh)
    _zone(svg, PAD, y, main_w, zh, "THREE AGENTS (TYPED TOOLS, FIXED AUTHORITY)", "l-agent")
    for i, a in enumerate(cv):
        ax = PAD + 14 + i * (aw + 24)
        svg.rect(ax, y + 38, aw, card_h, "dg-box", 8)
        svg.box(f"agent:{a['id']}", ax, y + 38, aw, card_h, "node", a["name"])
        svg.add(f'<rect x="{ax:.1f}" y="{y + 38:.1f}" width="{aw:.1f}" height="4" rx="2" style="fill:var(--l-agent)"/>')
        ty = y + 38 + 24
        tl, bl = heads[i]
        for t in tl:
            svg.text(ax + 10, ty, t, "dg-tb", size=12, bold=True, max_w=aw - 20)
            ty += 16
        for t in bl:
            svg.text(ax + 10, ty, t, "dg-s", size=10, max_w=aw - 20)
            ty += 13.5
        ty = y + 38 + start_off + 4
        for t in by_agent.get(a["name"], []):
            dot = "dg-dot-ok" if t["authority"] == "read" else "dg-dot" if t["authority"] == "read (simulated)" else "dg-dot-mute"
            svg.add(f'<circle class="{dot}" cx="{ax + 14:.1f}" cy="{ty - 3.5:.1f}" r="3.2"/>')
            svg.text(ax + 24, ty, t["tool"], "dg-t", size=10.5, max_w=aw - 34)
            ty += 14
    _arrow(svg, [(PAD + main_w / 2, y - 26), (PAD + main_w / 2, y)])
    y += zh + 26

    # ---- typed tool layer
    zones["tools"] = (y, 96)
    _zone(svg, PAD, y, main_w, 96, f"TYPED TOOL LAYER ({len(tools)} MCP-STYLE TOOLS)", "l-dsp")
    svg.text(PAD + 14, y + 50, "Every tool declares: name, owning agent, authority class, input schema, layer reached. Output is data, never instructions.", "dg-s", size=11, max_w=main_w - 28)
    cx = PAD + 14
    for lab, kind in (("read", "ok"), ("read (simulated)", "ok"), ("read + local draft", "warn"), ("draft only", "warn"), ("no write authority exists", "bad")):
        cx += _chip(svg, cx, y + 76, lab, kind, 10.5) + 10
    _arrow(svg, [(PAD + main_w / 2, y - 26), (PAD + main_w / 2, y)])
    y += 96 + 26

    # ---- engines
    engines = landscape.ENGINES
    per_row = 6
    eh = 38 + 2 * 66 + 8
    zones["engines"] = (y, eh)
    _zone(svg, PAD, y, main_w, eh, f"DOMAIN ENGINES ({len(engines)}, DETERMINISTIC)", "l-bdc")
    ew = (main_w - 28 - (per_row - 1) * 12) / per_row
    for i, (n_, mod) in enumerate(engines):
        r, c = divmod(i, per_row)
        _card(svg, f"eng:{n_}", PAD + 14 + c * (ew + 12), y + 38 + r * 66, ew, 58, n_, [mod], size=11, sub_size=10, wrap_lines=1)
    _arrow(svg, [(PAD + main_w / 2, y - 26), (PAD + main_w / 2, y)])
    y += eh + 26

    # ---- evidence
    ev = [("Persisted run", "results.json: both scenarios"), ("Release evidence", "tests and audit, timestamped"), ("Golden expectations", "hand-authored, independent"),
          ("Catalog fixture", "SIM_ products, evidence classes"), ("Synthetic generator", "seeded, reproducible")]
    zones["evidence"] = (y, 112)
    _zone(svg, PAD, y, main_w, 112, "EVIDENCE AND STATE (ALL SYNTHETIC)", "l-gov")
    vw = (main_w - 28 - 4 * 12) / 5
    for i, (t, s) in enumerate(ev):
        _card(svg, f"ev:{t}", PAD + 14 + i * (vw + 12), y + 38, vw, 62, t, [s], size=11, sub_size=10, wrap_lines=2)
    _arrow(svg, [(PAD + main_w / 2, y - 26), (PAD + main_w / 2, y)])
    y += 112 + 26

    # ---- adapters and systems (not connected)
    zones["adapters"] = (y, 100)
    _zone(svg, PAD, y, main_w, 100, "READ-ONLY ADAPTERS AND SAP LANDSCAPE (NOT CONNECTED)", "l-conn")
    half = (main_w - 28 - 60) / 2
    _card(svg, "ad:all", PAD + 14, y + 38, half, 54, "Read-only adapters (proposed)", ["One per system; NOT CONFIGURED in this build"], cls="dg-box dg-bad dg-dashed", size=11, sub_size=10, wrap_lines=2)
    _card(svg, "ad:sys", PAD + 14 + half + 60, y + 38, half, 54, "ECC, S/4HANA, Central Finance, BW, BDC, Datasphere", ["No connection exists"], cls="dg-box dg-dashed", size=11, sub_size=10, wrap_lines=2)
    _arrow(svg, [(PAD + 14 + half, y + 65), (PAD + 14 + half + 60, y + 65)], "dg-e dg-e-blk", dash=True)
    # the path from the tool layer runs in the gutter on the right, never through other boxes
    ty0, th0 = zones["tools"]
    gut = PAD + main_w + 18
    svg.add(f'<path class="dg-e dg-e-blk dg-dash" d="M{PAD + main_w:.1f},{ty0 + 30:.1f} H{gut:.1f} V{y + 65:.1f} H{PAD + main_w - 1:.1f}" fill="none" marker-end="url(#{svg.marker("dg-e-blk")})"/>')
    _chip(svg, PAD + main_w - 14 - (tw("NOT REACHED (DEMO)", 10, True) + 14), y + 22, "NOT REACHED (DEMO)", "bad", 10)
    y += 100 + 10

    # ---- governance column: each control sits at the layer it governs
    gov = {"orch": ("Approval queue", "Write-like requests become draft-only proposals; a named human approves outside the suite"),
           "agents": ("Business rule book", "AI proposes, never approves; approvals here are synthetic-scope fixtures"),
           "tools": ("Execution planner", "DEMO, CONNECTED_READ_ONLY, CONTROLLED_EXECUTION; DEPLOYED and RUNTIME_VERIFIED unreachable"),
           "engines": ("Audit log", "Redacted; idempotency keys; bounded retries"),
           "evidence": ("Acceptance gates and status", "G01-G15 on synthetic evidence; LIVE_SAP, LIVE_BDC and FINANCE stay HOLD")}
    gtop = zones["orch"][0] - 10
    _zone(svg, gx - 8, gtop, gw + 8, y - gtop - 10, "GOVERNANCE AND CONTROLS", "l-gov")
    for key, (t, s) in gov.items():
        zy, zh_ = zones[key]
        gh_ = min(zh_ - 16, max(86, _auto_h(t, [s], gw - 8, 12, 10, 4)))
        _card(svg, f"gov:{t}", gx + 4, zy + (zh_ - gh_) / 2, gw - 8, gh_, t, [s], size=12, sub_size=10, wrap_lines=4)
        _arrow(svg, [(PAD + main_w, zy + zh_ / 2), (gx + 4, zy + zh_ / 2)], "dg-e dg-e-gov", dash=True)
    svg.h = y + 10
    return svg.render(), svg


# ====================================================================================================================== data-flow pipeline (ontology wiring)
def dataflow_svg(res: dict, scn: str) -> tuple[str, Svg]:
    from collections import Counter
    from . import ontology
    o = ontology.build(res, scn)
    lin = o["lineage"]
    c = o["counts"]
    s = res["scenarios"][scn]
    sysn = Counter(x["system"] for x in lin)
    dtypes = Counter(x["delta_type"] for x in lin)
    acq = Counter(x["acq_type"] for x in lin if x["acq_type"] != "-")
    key_of = lambda d: ("reuse" if d == "REUSE_STANDARD" else "extend" if d in ("KEY_USER_EXTENSION", "DEVELOPER_EXTENSION", "DATA_PRODUCT_EXTENSION")
                        else "new" if d == "CREATE_CUSTOMER_MANAGED_PRODUCT" else "dsp" if d == "DATASPHERE_ENRICHMENT" else "unres")
    pair = Counter((key_of(x["decision"]), x["acq_type"]) for x in lin if x["acq_type"] != "-")
    lay = s["model"]["layers"]
    sem = lay["4_semantic"]
    n_cols = 6
    colw = 188
    gap = (W - 2 * PAD - n_cols * colw) / (n_cols - 1)
    xs = [PAD + i * (colw + gap) for i in range(n_cols)]
    top = 60
    svg = Svg(W, 10, "End-to-end data flow and wiring", 1100)
    heads = ["SAP objects and delta", "Solution", "Acquisition", "Harmonize and transform", "Semantic model", "Analytic models and proof"]
    accents = ["l-source", "l-agent", "l-bdc", "l-dsp", "l-dsp", "l-consume"]
    for i, h in enumerate(heads):
        svg.text(xs[i], 28, f"{i + 1}  {h}".upper(), "dg-zone-t", size=10.5, max_w=colw + gap - 8)
        svg.add(f'<rect x="{xs[i]:.1f}" y="36" width="{colw}" height="3" rx="1.5" style="fill:var(--{accents[i]})"/>')

    def listcard(i, bid, title, rows, y, accent=None, cls="dg-box"):
        h = 30 + len(rows) * 16 + 10
        svg.rect(xs[i], y, colw, h, cls, 8)
        svg.box(bid, xs[i], y, colw, h, "node", title)
        if accent:
            svg.add(f'<rect x="{xs[i]:.1f}" y="{y:.1f}" width="{colw}" height="4" rx="2" style="fill:var(--{accent})"/>')
        svg.text(xs[i] + 10, y + 22, title, "dg-tb", size=12, bold=True, max_w=colw - 20)
        for j, r in enumerate(rows):
            svg.text(xs[i] + 10, y + 42 + j * 16, r, "dg-t", size=10.5, max_w=colw - 20)
        return y + h

    # 1 objects and delta
    y = listcard(0, "df:objects", f"{c['objects']} SAP objects", [f"{k}: {v}" for k, v in sorted(sysn.items())], top, "l-source")
    delta_top = y + 16
    y = listcard(0, "df:delta", "Delta found", [f"{k.replace('_', ' ').lower()}: {v}" for k, v in sorted(dtypes.items(), key=lambda kv: -kv[1])], delta_top, "l-gov")
    end0 = y
    delta_mid = delta_top + 15
    # 2 solution
    sol = [("reuse", "Reuse the standard product", c["reused"]), ("extend", "Extend the SAP product", c["extended"]),
           ("new", "New backend CDS view + customer-managed model", c["created"]), ("dsp", "Solve in Datasphere", c["datasphere"]), ("unres", "Verify the catalog or blocked", c["unresolved"])]
    sol_y = {}
    y = top
    for key, t, n_ in sol:
        h = _auto_h(t, [f"{n_} object(s)"], colw, 11, 10, 1) + 6
        _card(svg, f"df:sol:{key}", xs[1], y, colw, h, t, [f"{n_} object(s)"], size=11, sub_size=10, wrap_lines=1, cls="dg-box" + (" dg-bad" if key == "unres" else ""))
        sol_y[key] = y + h / 2
        y += h + 12
    end1 = y
    # 3 acquisition
    ac = [("INSTALLED_PRODUCT", "Installed SAP product, consumed as is"), ("REPLICATION_FLOW", "Replication flow for a customer-managed product"), ("ENRICHMENT_SOURCE", "Enrichment source combined in Datasphere")]
    ac_y = {}
    y = top + 14
    for typ, t in ac:
        _card(svg, f"df:acq:{typ}", xs[2], y, colw, 66, t, [f"{acq.get(typ, 0)} acquisition(s)"], size=11, sub_size=10, wrap_lines=1)
        ac_y[typ] = y + 33
        y += 66 + 28
    end2 = y
    # 4 views
    harm = [v["view"] for v in lay["2_harmonization"]]
    trans = [v["view"] for v in lay["3_transformation"]]
    yh = top
    y = listcard(3, "df:harm", "Harmonization views", harm, yh, "l-dsp")
    yt = y + 14
    y = listcard(3, "df:trans", "Transformation views", trans, yt, "l-dsp")
    end3 = y
    # 5 semantic
    facts = [f["name"] for f in sem["facts"]]
    dims = [d if isinstance(d, str) else d.get("name", "") for d in sem["dimensions"]] + [b["name"] for b in sem["bridges"]]
    yf = top
    y = listcard(4, "df:facts", "Facts", facts, yf, "l-dsp")
    yd = y + 14
    y = listcard(4, "df:dims", "Dimensions and bridges", dims, yd, "l-dsp")
    end4 = y
    # 6 models and proof
    y = top
    model_y = []
    for m in sem["analytic_models"]:
        _card(svg, f"df:am:{m['name']}", xs[5], y, colw, 74, m["name"], [", ".join(f.replace("FACT_", "").lower() for f in m["facts"])], size=12, sub_size=10, wrap_lines=3, accent="l-consume")
        model_y.append(y + 37)
        y += 74 + 12
    rec = {k: (v or {}).get("status", "-") for k, v in s["recon"]["levels"].items() if (v or {}).get("status", "-") != "-"}
    svg.text(xs[5], y + 12, "RECONCILIATION (SYNTHETIC)", "dg-zone-t", size=10)
    y += 26
    for k, v in rec.items():
        svg.text(xs[5], y + 3, k, "dg-tb", size=11, bold=True)
        _chip(svg, xs[5] + 32, y, v, "ok" if "PASS" in v else "warn", 10)
        y += 24
    end5 = y

    # ---- connectors
    right = lambda i: xs[i] + colw
    xm1 = right(0) + gap / 2
    for key, ty in sol_y.items():                       # delta -> each route (bus)
        _arrow(svg, [(right(0), delta_mid), (xm1, delta_mid), (xm1, ty), (xs[1], ty)], "dg-e dg-e-ctl", r=5)
    offs = {"reuse": -17, "extend": -6, "new": 6, "dsp": 17, "unres": 0}
    for (route, typ), n_ in pair.items():                # route -> acquisition type, numbered with the object count
        if typ in ac_y and route in sol_y:
            x1, y1, x2, y2 = right(1), sol_y[route], xs[2], ac_y[typ]
            xm = x1 + gap / 2 + offs[route]
            _arrow(svg, [(x1, y1), (xm, y1), (xm, y2), (x2, y2)], "dg-e" + (" dg-e-fi" if typ == "REPLICATION_FLOW" else ""), r=5)
            _num(svg, xm, (y1 + y2) / 2 if y1 != y2 else y1, n_, "dg-e" + (" dg-e-fi" if typ == "REPLICATION_FLOW" else ""))
    xm2 = right(2) + gap / 2
    for typ, ay in ac_y.items():                         # acquisition -> harmonization
        _arrow(svg, [(right(2), ay), (xm2, ay), (xm2, yh + 22), (xs[3], yh + 22)], "dg-e", r=5)
    _arrow(svg, [(right(3), yh + 22), (right(3) + gap / 2, yh + 22), (right(3) + gap / 2, yf + 22), (xs[4], yf + 22)], "dg-e", r=5)
    _arrow(svg, [(right(3), yt + 22), (right(3) + gap / 2, yt + 22), (right(3) + gap / 2, yf + 22 + 6), (xs[4], yf + 22 + 6)], "dg-e", r=5)
    for my in model_y:
        _arrow(svg, [(right(4), yf + 22), (right(4) + gap / 2, yf + 22), (right(4) + gap / 2, my), (xs[5], my)], "dg-e", r=5)
    H = max(end0, end1, end2, end3, end4, end5) + 56
    svg.text(PAD, H - 26, "Numbers on the connectors are SAP objects following that route. Reconciliation verdicts are scenario-level and synthetic, not a per-object proof.", "dg-s", size=11)
    svg.h = H
    return svg.render(), svg


# ====================================================================================================================== deployment options
def deployment_svg(opt: str, res: dict | None = None) -> tuple[str, Svg]:
    h = 372
    svg = Svg(W, h, f"Deployment option {opt}", 1100)
    chain = [("Cockpit UI", "Streamlit app"), ("Orchestrator", "planner + validator"), ("Agents", "3 agents"), ("Typed tool layer", "27 tools"), ("Domain engines", "12 engines"), ("Evidence store", "synthetic")]

    def row(x, y, w, items, pre="o"):
        bw = (w - (len(items) - 1) * 14) / len(items)
        for i, (t, s) in enumerate(items):
            _card(svg, f"{pre}:{t}", x + i * (bw + 14), y, bw, 54, t, [s], size=11, sub_size=10, wrap_lines=1)
            if i:
                _arrow(svg, [(x + i * (bw + 14) - 14, y + 27), (x + i * (bw + 14), y + 27)])

    _zone(svg, PAD, 10, 190, h - 30, "USER", "l-source")
    _card(svg, "d:browser", PAD + 14, 80, 162, 70, "Browser", ["Architect, SAP team"], size=12)
    if opt == "P1":
        _zone(svg, PAD + 240, 10, 760, h - 30, "APP HOST (STREAMLIT COMMUNITY CLOUD OR LOCAL) - ONE PYTHON PROCESS", "l-agent")
        row(PAD + 254, 78, 732, chain[:3])
        row(PAD + 254, 168, 732, chain[3:])
        _arrow(svg, [(PAD + 190 + 14, 115), (PAD + 240, 115)], label="HTTPS")
        _zone(svg, PAD + 1050, 10, W - 2 * PAD - 1050, h - 30, "SAP LANDSCAPE", "l-conn")
        _card(svg, "d:sap", PAD + 1064, 80, W - 2 * PAD - 1078, 90, "No connection", ["by design: no credentials, no network path, nothing to leak"], cls="dg-box dg-dashed dg-bad", size=12, sub_size=10, wrap_lines=3)
        _arrow(svg, [(PAD + 1000, 115), (PAD + 1050, 115)], "dg-e dg-e-blk", dash=True, label="none")
        svg.text(PAD + 254, h - 40, "Choice for demonstrations and offline use. Synthetic data only.", "dg-s", size=11.5)
    elif opt == "P2":
        _zone(svg, PAD + 240, 10, 520, h - 30, "CUSTOMER-CONTROLLED ZONE (NON-PRODUCTION NETWORK)", "l-agent")
        row(PAD + 254, 70, 492, chain[:3])
        row(PAD + 254, 150, 492, chain[3:])
        _card(svg, "d:secret", PAD + 254, 224, 240, 54, "Secret store", ["customer-owned; never in code or logs"], size=11, sub_size=10, wrap_lines=1, accent="l-gov")
        _card(svg, "d:adapters", PAD + 510, 224, 236, 54, "Read-only adapters", ["metadata, catalog, aggregates"], size=11, sub_size=10, wrap_lines=1, cls="dg-box dg-dashed dg-bad")
        _arrow(svg, [(PAD + 190 + 14, 115), (PAD + 240, 115)], label="SSO")
        _zone(svg, PAD + 810, 10, W - 2 * PAD - 810, h - 30, "SAP LANDSCAPE (READ ONLY)", "l-source")
        sy = 60
        for i, t in enumerate(("S/4HANA and ECC", "Central Finance and BW", "SAP Business Data Cloud", "Datasphere")):
            _card(svg, f"d:sys{i}", PAD + 824, sy + i * 56, W - 2 * PAD - 838, 46, t, None, size=11)
        _arrow(svg, [(PAD + 746, 251), (PAD + 790, 251), (PAD + 790, 150), (PAD + 824, 150)], "dg-e dg-e-blk", dash=True, label="read only")
        svg.text(PAD + 254, h - 40, "Design intent, not built. The next step if read-only access is authorized.", "dg-s", size=11.5)
    else:
        _zone(svg, PAD + 240, 10, 500, h - 30, "ENTERPRISE PLATFORM", "l-agent")
        row(PAD + 254, 70, 472, [("Cockpit UI", "app"), ("Orchestrator", "planner"), ("Agent runtime", "agents + tools")])
        row(PAD + 254, 150, 472, [("Tool gateway", "policy, quota, audit"), ("Approval service", "named humans"), ("Registry", "control plane only")])
        _arrow(svg, [(PAD + 190 + 14, 115), (PAD + 240, 115)], label="SSO")
        _zone(svg, PAD + 790, 10, 300, h - 30, "CONTROLLED EXECUTORS", "l-gov")
        _card(svg, "d:exec", PAD + 804, 70, 272, 80, "ADT and Datasphere executors", ["only verified interfaces, per-action approval, idempotent and resumable (design intent)"], size=11, sub_size=10, wrap_lines=3)
        _zone(svg, PAD + 1130, 10, W - 2 * PAD - 1130, h - 30, "SAP NON-PRODUCTION", "l-source")
        _card(svg, "d:np", PAD + 1144, 70, W - 2 * PAD - 1158, 80, "Non-production systems", ["production is never targeted"], size=11, sub_size=10, wrap_lines=2)
        _arrow(svg, [(PAD + 740, 197), (PAD + 790, 197), (PAD + 790, 110), (PAD + 804, 110)], "dg-e dg-e-gov", dash=True, label="approved")
        _arrow(svg, [(PAD + 1076, 110), (PAD + 1130, 110), (PAD + 1144, 110)], "dg-e dg-e-blk", dash=True)
        svg.text(PAD + 254, h - 40, "Conditional, not approved and not built. Needs a gateway, a registry and an approval service.", "dg-s", size=11.5)
    return svg.render(), svg


# ====================================================================================================================== orchestration sequence
def sequence_svg(events: list[dict], upto: int) -> tuple[str, Svg]:
    order = ["UI", "Orchestrator"]
    for e in events:
        for k in (e["from"], e["to"]):
            if k not in order and k not in ("Typed tool layer", "SAP connectors", "Approval queue"):
                order.append(k)
    agents_ = [k for k in order[2:] if k.endswith("agent")]
    layers = [k for k in order[2:] if not k.endswith("agent")]
    parts = ["UI", "Orchestrator"] + agents_ + ["Typed tool layer"] + layers + [k for k in ("Approval queue", "SAP connectors") if any(k in (e["from"], e["to"]) for e in events)]
    n = len(parts)
    colw = (W - 2 * PAD) / n
    cx = {p: PAD + colw * (i + 0.5) for i, p in enumerate(parts)}
    step = 30
    top = 80
    H = top + len(events) * step + 40
    svg = Svg(W, H, "Orchestration sequence", 1100)
    for p in parts:
        bad = p == "SAP connectors"
        bw = min(colw - 14, 176)
        svg.rect(cx[p] - bw / 2, 10, bw, 46, "dg-box" + (" dg-bad dg-dashed" if bad else ""), 8)
        svg.box(f"seq:{p}", cx[p] - bw / 2, 10, bw, 46, "node", p)
        lines = wrap(p, bw - 14, 11.5, 2, True)
        for j, ln in enumerate(lines):
            svg.text(cx[p], 30 + j * 14 - (7 if len(lines) == 2 else 0) + 2, ln, "dg-tb", anchor="middle", size=11.5, bold=True, max_w=bw - 12)
        svg.add(f'<line class="dg-life" x1="{cx[p]:.1f}" y1="56" x2="{cx[p]:.1f}" y2="{H - 20:.1f}"/>')
    for i, e in enumerate(events):
        y = top + i * step
        live = i < upto
        a, b = cx.get(e["from"]), cx.get(e["to"])
        if a is None or b is None:
            continue
        cls = "dg-e dg-e-blk" if e["state"] in ("REFUSED", "NOT_REACHED") else "dg-e" if e["state"] in ("REQUEST", "PLAN") else "dg-e dg-e-ctl"
        dash = e["state"] in ("RESULT", "NOT_REACHED", "REFUSED")
        op = "" if live else ' style="opacity:.28"'
        svg.add(f"<g{op}>")
        if a == b:
            svg.path([(a, y - 8), (a + 26, y - 8), (a + 26, y + 6), (a, y + 6)], cls, r=4)
        else:
            svg.path([(a, y), (b, y)], cls, dash=dash, r=0)
        lab = f"{i + 1}. {e['label']}"
        lx = min(a, b) + 8
        room = abs(b - a) - 16 if a != b else colw - 40
        svg.text(lx if a != b else a + 32, y - 6 if a != b else y, lab, "dg-s", size=10.5, max_w=max(60, room))
        svg.add("</g>")
    return svg.render(), svg


# ====================================================================================================================== layered graph (dependencies, concepts)
def layered_svg(nodes: list[dict], edges: list[tuple[str, str]], title: str = "Graph", kind_class: dict | None = None, max_label: int = 150) -> tuple[str, Svg]:
    """nodes: {"id","label","kind","sub"}; edges: (from, to). Longest-path layering, dummy nodes for long edges, barycentre ordering, rounded S-curves."""
    ids = [n["id"] for n in nodes]
    idx = {i: k for k, i in enumerate(ids)}
    out: dict[str, list[str]] = {i: [] for i in ids}
    inc: dict[str, list[str]] = {i: [] for i in ids}
    clean = []
    for a, b in edges:
        if a in idx and b in idx and a != b and b not in out[a]:
            out[a].append(b)
            inc[b].append(a)
            clean.append((a, b))
    # break cycles (DFS back edges)
    state: dict[str, int] = {}
    back = set()

    def dfs(u):
        state[u] = 1
        for v in out[u]:
            if state.get(v) == 1:
                back.add((u, v))
            elif state.get(v) is None:
                dfs(v)
        state[u] = 2
    for i in ids:
        if state.get(i) is None:
            dfs(i)
    dag = [(a, b) for a, b in clean if (a, b) not in back]
    layer = {i: 0 for i in ids}
    for _ in range(len(ids)):
        ch = False
        for a, b in dag:
            if layer[b] < layer[a] + 1:
                layer[b] = layer[a] + 1
                ch = True
        if not ch:
            break
    # dummies for long edges
    chains = []
    cols: dict[int, list[str]] = {}
    for i in ids:
        cols.setdefault(layer[i], []).append(i)
    for a, b in dag:
        span = layer[b] - layer[a]
        chain = [a]
        for k in range(1, span):
            d = f"~{a}>{b}:{k}"
            layer[d] = layer[a] + k
            cols.setdefault(layer[d], []).append(d)
            chain.append(d)
        chain.append(b)
        chains.append(chain)
    pos = {}
    for L_, lst in cols.items():
        for r, v in enumerate(lst):
            pos[v] = r
    nbr = {}
    for ch in chains:
        for u, v in zip(ch, ch[1:]):
            nbr.setdefault(v, []).append(u)
            nbr.setdefault(u, []).append(v)
    for _ in range(6):
        for L_ in sorted(cols):
            lst = cols[L_]
            bary = {v: (sum(pos[u] for u in nbr.get(v, []) if layer[u] != L_) / max(1, len([u for u in nbr.get(v, []) if layer[u] != L_]))) if nbr.get(v) else pos[v] for v in lst}
            lst.sort(key=lambda v: (bary[v], pos[v]))
            for r, v in enumerate(lst):
                pos[v] = r
    by = {n["id"]: n for n in nodes}
    nh, rowh = 42, 62
    colw_ = max_label + 70
    nlayers = max(cols) + 1 if cols else 1
    maxrows = max(len(v) for v in cols.values()) if cols else 1
    width = PAD * 2 + nlayers * colw_
    height = 30 + maxrows * rowh + 30
    svg = Svg(max(width, 900), height, title, 900)
    xy = {}
    for L_, lst in cols.items():
        off = (maxrows - len(lst)) * rowh / 2
        for v in lst:
            xy[v] = (PAD + L_ * colw_, 20 + off + pos[v] * rowh)
    kc = kind_class or {}
    for ch in chains:
        pts = []
        for u, v in zip(ch, ch[1:]):
            x1, y1 = xy[u][0] + (max_label if not u.startswith("~") else 0), xy[u][1] + nh / 2
            x2, y2 = xy[v][0], xy[v][1] + nh / 2
            if not pts:
                pts.append((x1, y1))
            xm = (x1 + x2) / 2
            pts += [(xm, y1), (xm, y2), (x2, y2)]
        svg.path(pts, "dg-e dg-e-ref", arrow=True, r=6)
    for b_, a_ in [(b, a) for a, b in back]:
        pass
    for i, n in enumerate(nodes):
        x, y = xy[n["id"]]
        k = kc.get(n.get("kind", ""), "dg-box")
        svg.rect(x, y, max_label, nh, k, 7)
        svg.box(f"g:{n['id']}", x, y, max_label, nh, "node", n["label"])
        svg.text(x + 8, y + 17, n["label"], "dg-tb", size=11, bold=True, max_w=max_label - 16)
        if n.get("sub"):
            svg.text(x + 8, y + 31, n["sub"], "dg-s", size=9.5, max_w=max_label - 16)
    return svg.render(), svg
