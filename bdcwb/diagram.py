"""SVG diagram engine for the architecture views. Pure Python, no dependencies, deterministic output.

Why not Graphviz in the browser: it froze the page on larger graphs and gives no control over layout, alignment or typography. These diagrams are laid out
here with explicit coordinates, so nothing overlaps, every label is measured to fit its box, and the output is one inline SVG that follows the app theme
(colours come from CSS variables through the dg-* classes defined in suite_theme.css).

Every diagram records its boxes (Svg.boxes) so tests can assert there are no overlapping boxes and that no label is wider than its box.
"""
from __future__ import annotations

import html
import itertools

CHAR_W = 0.57          # average glyph width as a fraction of the font size (conservative for the UI font)
_ids = itertools.count(1)


def esc(x) -> str:
    return html.escape(str(x), quote=True).replace("$", "&#36;")


def tw(text: str, size: float = 12, bold: bool = False) -> float:
    return len(text) * size * CHAR_W * (1.07 if bold else 1.0)


def wrap(text: str, width: float, size: float = 12, max_lines: int = 3, bold: bool = False) -> list[str]:
    words, lines, cur = str(text).split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if tw(t, size, bold) <= width or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        while last and tw(last + "...", size, bold) > width:
            last = last[:-1]
        lines[-1] = last.rstrip() + "..."
    return lines or [""]


def fit(text: str, width: float, size: float = 12, bold: bool = False) -> str:
    """One line that fits the width (ellipsised)."""
    text = str(text)
    if tw(text, size, bold) <= width:
        return text
    while text and tw(text + "...", size, bold) > width:
        text = text[:-1]
    return text.rstrip() + "..."


class Svg:
    def __init__(self, width: float, height: float, title: str = "", min_width: float | None = None):
        self.w, self.h, self.title = width, height, title
        self.min_width = min_width or width
        self.parts: list[str] = []
        self.boxes: list[dict] = []     # {"id","x","y","w","h","kind","label","pad"}: used by tests
        self.labels: list[dict] = []    # {"text","size","bold","max"}: text and the width it must fit
        self.uid = next(_ids)
        self._markers: set[str] = set()

    # ------------------------------------------------------------------ primitives
    def add(self, s: str) -> None:
        self.parts.append(s)

    def rect(self, x, y, w, h, cls="dg-box", rx=8, extra="") -> None:
        self.add(f'<rect class="{cls}" x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{rx}" {extra}/>')

    def text(self, x, y, txt, cls="dg-t", anchor="start", size=12, bold=False, max_w: float | None = None) -> None:
        if max_w is not None:
            txt = fit(txt, max_w, size, bold)
            self.labels.append({"text": txt, "size": size, "bold": bold, "max": max_w})
        self.add(f'<text class="{cls}" x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" font-size="{size}"' + (' font-weight="700"' if bold else "") + f'>{esc(txt)}</text>')

    def marker(self, cls: str) -> str:
        mid = f"dg{self.uid}-{cls}"
        if cls not in self._markers:
            self._markers.add(cls)
            self.add(f'<defs><marker id="{mid}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" class="dg-ah {cls}"/></marker></defs>')
        return mid

    def box(self, bid, x, y, w, h, kind="box", label="") -> None:
        self.boxes.append({"id": bid, "x": x, "y": y, "w": w, "h": h, "kind": kind, "label": label})

    def path(self, pts: list[tuple[float, float]], cls="dg-e", arrow=True, r=7, dash=False, label: str | None = None, label_at: float = 0.5, lbl_cls="dg-elabel") -> None:
        """Rounded orthogonal polyline with an arrowhead and an optional label plate."""
        d = _rounded(pts, r)
        mid = self.marker(cls.split()[-1]) if arrow else None
        self.add(f'<path class="{cls}{" dg-dash" if dash else ""}" d="{d}" fill="none"' + (f' marker-end="url(#{mid})"' if mid else "") + "/>")
        if label:
            x, y = _point_at(pts, label_at)
            w = tw(label, 10.5) + 12
            self.add(f'<rect class="dg-plate" x="{x - w / 2:.1f}" y="{y - 9:.1f}" width="{w:.1f}" height="18" rx="4"/>')
            self.add(f'<text class="{lbl_cls}" x="{x:.1f}" y="{y + 3.6:.1f}" text-anchor="middle" font-size="10.5">{esc(label)}</text>')
            self.labels.append({"text": label, "size": 10.5, "bold": False, "max": w - 10})

    def render(self) -> str:
        head = (f'<div class="dg-wrap"><svg class="dg" role="img" aria-label="{esc(self.title)}" viewBox="0 0 {self.w:.0f} {self.h:.0f}" width="100%" '
                f'style="min-width:{self.min_width:.0f}px" xmlns="http://www.w3.org/2000/svg">')
        return head + "".join(self.parts) + "</svg></div>"


def _rounded(pts, r) -> str:
    if len(pts) < 3:
        return "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    d = f"M{pts[0][0]:.1f},{pts[0][1]:.1f}"
    for i in range(1, len(pts) - 1):
        (x0, y0), (x1, y1), (x2, y2) = pts[i - 1], pts[i], pts[i + 1]
        l1 = max(abs(x1 - x0) + abs(y1 - y0), 1e-6)
        l2 = max(abs(x2 - x1) + abs(y2 - y1), 1e-6)
        rr = min(r, l1 / 2, l2 / 2)
        ax, ay = x1 - (x1 - x0) / l1 * rr, y1 - (y1 - y0) / l1 * rr
        bx, by = x1 + (x2 - x1) / l2 * rr, y1 + (y2 - y1) / l2 * rr
        d += f" L{ax:.1f},{ay:.1f} Q{x1:.1f},{y1:.1f} {bx:.1f},{by:.1f}"
    d += f" L{pts[-1][0]:.1f},{pts[-1][1]:.1f}"
    return d


def _point_at(pts, frac):
    segs = [(abs(b[0] - a[0]) + abs(b[1] - a[1]), a, b) for a, b in zip(pts, pts[1:])]
    total = sum(s[0] for s in segs) or 1
    want, acc = total * frac, 0.0
    for ln, a, b in segs:
        if acc + ln >= want:
            t = (want - acc) / (ln or 1)
            return a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
        acc += ln
    return pts[-1]


def overlapping_boxes(boxes: list[dict], kinds: tuple[str, ...] = ("node",)) -> list[tuple[str, str]]:
    """Pairs of boxes of the given kinds that overlap (touching edges are fine)."""
    bad = []
    bs = [b for b in boxes if b["kind"] in kinds]
    for i, a in enumerate(bs):
        for c in bs[i + 1:]:
            if a["x"] < c["x"] + c["w"] - 0.5 and c["x"] < a["x"] + a["w"] - 0.5 and a["y"] < c["y"] + c["h"] - 0.5 and c["y"] < a["y"] + a["h"] - 0.5:
                bad.append((a["id"], c["id"]))
    return bad


def too_wide_labels(labels: list[dict]) -> list[str]:
    return [l["text"] for l in labels if tw(l["text"], l["size"], l["bold"]) > l["max"] + 1]
