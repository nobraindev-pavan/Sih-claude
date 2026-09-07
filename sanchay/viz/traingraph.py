"""The time-distance chart, as an SVG file.

This is the hero visual, not a map. Every controller in India reads a train
graph daily: distance up one axis, time along the other, each train a diagonal.
Draw the proposed blocks as rectangles on it and a railway judge understands
the whole contribution in three seconds with no explanation.

No plotting library. It is lines and rectangles on a scaled coordinate system,
which is about eighty lines of arithmetic and gives complete control over how
it looks on a projector.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..core.models import Plan, Scenario
from ..core.timeutil import MINUTES_PER_DAY, hhmm

CLASS_STYLE = {
    "VB": ("var(--premium)", 1.9), "RAJ": ("var(--premium)", 1.9),
    "MEX": ("var(--express)", 1.4), "PASS": ("var(--slow)", 1.1),
    "MEMU": ("var(--slow)", 1.1), "FRT": ("var(--freight)", 1.0),
}
BLOCK_FILL = {"corridor": "var(--ok)", "gap": "var(--warn)", "traffic": "var(--bad)"}


@dataclass
class Layout:
    width: int = 1080
    height: int = 520
    pad_left: int = 74
    pad_right: int = 18
    pad_top: int = 34
    pad_bottom: int = 46


def _esc(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


class TrainGraph:
    def __init__(self, sc: Scenario, route: str = "MAIN", day: int = 0,
                 layout: Layout | None = None) -> None:
        self.sc = sc
        self.route = route
        self.day = day
        self.L = layout or Layout()
        prefix = "BRCH" if route == "BRANCH" else ("DIV" if route == "DIV" else "MAIN")
        self.sections = sorted([s for s in sc.sections if s.id.startswith(prefix)],
                               key=lambda s: s.km_from)
        if not self.sections:
            raise ValueError(f"no sections on route {route}")
        self.km_lo = min(s.km_from for s in self.sections)
        self.km_hi = max(s.km_to for s in self.sections)
        self.t_lo = day * MINUTES_PER_DAY
        self.t_hi = self.t_lo + MINUTES_PER_DAY
        self._paths = [p for p in sc.paths
                       if p.section_id in {s.id for s in self.sections}
                       and p.exit_min > self.t_lo and p.enter_min < self.t_hi]
        self._train = {t.number: t for t in sc.trains}

    # -- coordinate transforms -------------------------------------------
    def x(self, minute: int) -> float:
        L = self.L
        span = self.L.width - L.pad_left - L.pad_right
        frac = (min(max(minute, self.t_lo), self.t_hi) - self.t_lo) / MINUTES_PER_DAY
        return round(L.pad_left + frac * span, 2)

    def y(self, km: float) -> float:
        L = self.L
        span = L.height - L.pad_top - L.pad_bottom
        frac = (km - self.km_lo) / max(1e-6, self.km_hi - self.km_lo)
        return round(L.pad_top + frac * span, 2)

    # -- pieces ------------------------------------------------------------
    def _grid(self) -> list[str]:
        out = [f'<rect x="{self.L.pad_left}" y="{self.L.pad_top}" '
               f'width="{self.L.width - self.L.pad_left - self.L.pad_right}" '
               f'height="{self.L.height - self.L.pad_top - self.L.pad_bottom}" '
               f'fill="var(--plot)"/>']
        stations = {}
        for s in self.sections:
            stations[s.km_from] = s.from_station
            stations[s.km_to] = s.to_station
        for km, code in sorted(stations.items()):
            yy = self.y(km)
            out.append(f'<line x1="{self.L.pad_left}" y1="{yy}" '
                       f'x2="{self.L.width - self.L.pad_right}" y2="{yy}" '
                       f'stroke="var(--rule)" stroke-width="1"/>')
            out.append(f'<text x="{self.L.pad_left - 8}" y="{yy + 3.5}" '
                       f'class="axis" text-anchor="end">{_esc(code)} '
                       f'<tspan class="dim">{km:g}</tspan></text>')
        for h in range(0, 25, 2):
            xx = self.x(self.t_lo + h * 60)
            out.append(f'<line x1="{xx}" y1="{self.L.pad_top}" x2="{xx}" '
                       f'y2="{self.L.height - self.L.pad_bottom}" stroke="var(--rule)" '
                       f'stroke-width="1" stroke-dasharray="2 4"/>')
            out.append(f'<text x="{xx}" y="{self.L.height - self.L.pad_bottom + 16}" '
                       f'class="axis" text-anchor="middle">{h:02d}</text>')
        return out

    def _corridor(self) -> list[str]:
        out = []
        for w in self.sc.corridor_windows:
            sec = next((s for s in self.sections if s.id == w.section_id), None)
            if sec is None or w.start_min >= self.t_hi or w.end_min <= self.t_lo:
                continue
            x0, x1 = self.x(w.start_min), self.x(w.end_min)
            y0, y1 = self.y(sec.km_from), self.y(sec.km_to)
            out.append(f'<rect x="{x0}" y="{min(y0, y1)}" width="{max(1, x1 - x0)}" '
                       f'height="{abs(y1 - y0)}" fill="var(--corridor)"/>')
        return out

    def _trains(self) -> list[str]:
        by_train: dict[str, list] = {}
        for p in self._paths:
            by_train.setdefault(p.train_number, []).append(p)
        out = []
        for num, segs in by_train.items():
            train = self._train[num]
            colour, width = CLASS_STYLE.get(train.train_class, ("var(--slow)", 1.0))
            secs = {s.id: s for s in self.sections}
            pts = []
            for p in sorted(segs, key=lambda p: p.enter_min):
                s = secs[p.section_id]
                a_km, b_km = (s.km_from, s.km_to) if train.direction == "DN" else (s.km_to, s.km_from)
                pts.append((self.x(p.enter_min), self.y(a_km)))
                pts.append((self.x(p.exit_min), self.y(b_km)))
            if len(pts) < 2:
                continue
            d = " ".join(f"{x},{y}" for x, y in pts)
            out.append(f'<polyline points="{d}" fill="none" stroke="{colour}" '
                       f'stroke-width="{width}" stroke-linejoin="round" opacity="0.75">'
                       f'<title>{_esc(num)} {train.train_class} {train.direction}</title>'
                       f'</polyline>')
        return out

    def _blocks(self, plan: Plan) -> list[str]:
        out = []
        secs = {s.id: s for s in self.sections}
        for b in plan.blocks:
            sec = secs.get(b.section_id)
            if sec is None or b.start_min >= self.t_hi or b.end_min <= self.t_lo:
                continue
            x0, x1 = self.x(b.start_min), self.x(b.end_min)
            y0, y1 = sorted((self.y(sec.km_from), self.y(sec.km_to)))
            fill = BLOCK_FILL.get(b.window_source, "var(--warn)")
            depts = "+".join(b.departments)
            tip = (f"{b.section_id} {hhmm(b.start_min)}-{hhmm(b.end_min)} | {depts} | "
                   f"{len(b.task_ids)} task(s) | train cost {b.train_cost:.0f}")
            out.append(f'<g><rect x="{x0}" y="{y0}" width="{max(2, x1 - x0)}" '
                       f'height="{max(6, y1 - y0)}" fill="{fill}" fill-opacity="0.88" '
                       f'stroke="var(--blockedge)" stroke-width="0.8"/>'
                       f'<title>{_esc(tip)}</title></g>')
            if x1 - x0 > 34 and y1 - y0 > 13:
                out.append(f'<text x="{(x0 + x1) / 2}" y="{(y0 + y1) / 2 + 3.5}" '
                           f'class="blk" text-anchor="middle">{_esc(depts)}</text>')
        return out

    def render(self, plan: Plan, title: str = "") -> str:
        L = self.L
        body = self._grid() + self._corridor() + self._trains() + self._blocks(plan)
        head = (f'<text x="{L.pad_left}" y="20" class="title">{_esc(title)}</text>'
                if title else "")
        return (f'<svg viewBox="0 0 {L.width} {L.height}" xmlns="http://www.w3.org/2000/svg" '
                f'font-family="ui-monospace, SFMono-Regular, Menlo, monospace">'
                f"{head}{''.join(body)}</svg>")


STYLE = """
:root{--bg:#F3F4F1;--plot:#FBFCFA;--rule:#D5DAD4;--ink:#171B1D;--dim:#6C777C;
--corridor:#DCE8F1;--premium:#1D4E77;--express:#3E7CA6;--slow:#6E8894;--freight:#98A5AA;
--ok:#2C6650;--warn:#8A6412;--bad:#A94E1E;--blockedge:#FFFFFF;--card:#FFFFFF}
@media (prefers-color-scheme:dark){:root{--bg:#12161A;--plot:#171C21;--rule:#2B343A;
--ink:#E6EAE7;--dim:#8D999E;--corridor:#1D2E3B;--premium:#7FB2DA;--express:#5E93BC;
--slow:#7E939E;--freight:#5C6A70;--ok:#63B191;--warn:#D7AC4C;--bad:#E0925C;
--blockedge:#12161A;--card:#191E22}}
body{background:var(--bg);color:var(--ink);margin:0;padding:28px;
font:14px/1.55 ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}
h1{font-size:19px;margin:0 0 4px} p.sub{color:var(--dim);margin:0 0 22px;font-size:13px}
.panel{background:var(--card);border:1px solid var(--rule);padding:14px;margin-bottom:20px}
.panel h2{font-size:13px;letter-spacing:.09em;text-transform:uppercase;color:var(--dim);
margin:0 0 10px;font-weight:600}
svg{display:block;width:100%;height:auto}
text.axis{font-size:10px;fill:var(--dim)} tspan.dim{fill:var(--dim);opacity:.65}
text.blk{font-size:9.5px;fill:#fff;font-weight:600} text.title{font-size:12px;fill:var(--ink)}
.legend{display:flex;flex-wrap:wrap;gap:16px;font-size:11.5px;color:var(--dim);margin-top:12px}
.legend i{display:inline-block;width:15px;height:8px;margin-right:6px}
table{border-collapse:collapse;width:100%;font-size:13px;margin-top:6px}
th{text-align:left;font-size:10.5px;letter-spacing:.08em;text-transform:uppercase;
color:var(--dim);padding:8px 12px;border-bottom:1px solid var(--rule)}
td{padding:8px 12px;border-bottom:1px solid var(--rule);font-variant-numeric:tabular-nums}
td:first-child{font-weight:600}
"""

LEGEND = """<div class="legend">
<span><i style="background:var(--corridor)"></i>mandated corridor window</span>
<span><i style="background:var(--ok)"></i>block in corridor window</span>
<span><i style="background:var(--warn)"></i>block in a timetable gap</span>
<span><i style="background:var(--bad)"></i>block displacing traffic</span>
<span><i style="background:var(--premium);height:2px"></i>premium</span>
<span><i style="background:var(--express);height:2px"></i>mail/express</span>
<span><i style="background:var(--freight);height:2px"></i>freight</span>
</div>"""


def render_comparison(sc: Scenario, plans: dict[str, Plan], metrics_rows: list[dict],
                      route: str = "MAIN", day: int = 1, title: str = "") -> str:
    """A standalone HTML page: one train graph per method, plus the KPI table.

    This is the artefact to put in front of a judge, and the one to screenshot
    for the deck. Open it in a browser; it needs no server and no network.
    """
    graph = TrainGraph(sc, route=route, day=day)
    panels = []
    for name, plan in plans.items():
        n_coord = sum(1 for b in plan.blocks if b.is_coordinated)
        sub = (f"{len(plan.blocks)} blocks, {n_coord} coordinated, "
               f"{len(plan.unscheduled_task_ids)} task(s) deferred")
        panels.append(f'<div class="panel"><h2>{_esc(name)} &mdash; {_esc(sub)}</h2>'
                      f'{graph.render(plan)}{LEGEND}</div>')

    cols = ["method", "n_blocks", "n_coordinated_blocks", "total_block_minutes",
            "train_cost", "completion_pct", "critical_completion_pct",
            "utilisation_pct", "objective"]
    head = "".join(f"<th>{c.replace('_', ' ')}</th>" for c in cols)
    body = "".join("<tr>" + "".join(
        f"<td>{r[c] if isinstance(r[c], str) else format(r[c], '.1f')}</td>"
        for c in cols) + "</tr>" for r in metrics_rows)

    return (f"<!doctype html><html><head><meta charset='utf-8'>"
            f"<title>{_esc(title or 'Block plan comparison')}</title>"
            f"<style>{STYLE}</style></head><body>"
            f"<h1>{_esc(title or 'Block plan comparison')}</h1>"
            f"<p class='sub'>{_esc(sc.name)} &middot; route {route} &middot; day {day} "
            f"&middot; {len(sc.tasks)} maintenance tasks &middot; "
            f"{len(sc.trains)} train paths &middot; "
            f"<strong>simulated data - not a measured railway result</strong></p>"
            f"{''.join(panels)}"
            f"<div class='panel'><h2>Metrics</h2><table><thead><tr>{head}</tr></thead>"
            f"<tbody>{body}</tbody></table></div></body></html>")
