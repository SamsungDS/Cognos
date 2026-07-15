"""
amoprof/report/layered.py — section-per-layer HTML renderer.

Consumes the `{layer_name → LayerAnalysis}` mapping produced by
`amoprof.layers.run_layered_analyze()` and emits a standalone HTML
report with one `<section>` per layer, a sticky top nav, and each
layer's charts embedded inline.

Chart payload contract (mirrors LayerAnalysis.charts[i]):
  kind="b64"  → base64 PNG,   embedded as <img src="data:image/png;base64,…">
  kind="html" → HTML fragment, embedded verbatim (e.g. plotly div)

Stage 4 is additive: this renderer runs when the caller passes
--layered-report to `amoprof analyze`. The existing static/interactive/
combined reports continue to work through their old code paths — this
module never imports the 20k-line report/amoprof.py chart functions
directly; it just consumes the LayerAnalysis objects.
"""

from __future__ import annotations

import html
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

log = logging.getLogger("amoprof.report.layered")


# ── Palette (mirrors report/amoprof.py so themes stay consistent) ──────────
_BG      = "#f8fafc"
_BG2     = "#ffffff"
_BG3     = "#f1f5f9"
_BORDER  = "#cbd5e1"
_TEXT    = "#0f172a"
_MUTED   = "#475569"
_ACCENT  = "#4f46e5"


def _css() -> str:
    return f"""
<style>
  html,body {{ margin:0; padding:0; background:{_BG}; color:{_TEXT};
              font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif; }}
  header.amoprof-header {{ position:sticky; top:0; z-index:20;
              background:{_BG2}; border-bottom:1px solid {_BORDER};
              padding:12px 24px; box-shadow:0 1px 3px rgba(15,23,42,0.06); }}
  header.amoprof-header h1 {{ margin:0 0 6px; font-size:18px; font-weight:600; color:{_TEXT}; }}
  header.amoprof-header .meta {{ font-size:12px; color:{_MUTED}; }}
  nav.amoprof-nav {{ display:flex; gap:8px; flex-wrap:wrap; margin-top:10px; }}
  nav.amoprof-nav a {{ font-size:12px; text-decoration:none; padding:4px 10px;
              border:1px solid {_BORDER}; border-radius:999px; color:{_MUTED};
              background:{_BG3}; }}
  nav.amoprof-nav a:hover {{ background:{_ACCENT}; color:#ffffff; border-color:{_ACCENT}; }}
  main.amoprof-main {{ max-width:1240px; margin:0 auto; padding:24px; }}
  section.amoprof-layer {{ margin:0 0 32px; }}
  section.amoprof-layer h2 {{ font-size:15px; font-weight:600; color:{_TEXT};
              margin:24px 0 8px; padding:4px 0 6px; border-bottom:2px solid {_ACCENT};
              display:inline-block; padding-right:12px; }}
  .amoprof-count {{ display:inline-block; font-size:11px; color:{_MUTED};
              margin-left:8px; padding:2px 8px; background:{_BG3};
              border:1px solid {_BORDER}; border-radius:999px; }}
  .amoprof-empty {{ font-size:12px; color:{_MUTED}; padding:12px 16px;
              background:{_BG2}; border:1px dashed {_BORDER}; border-radius:8px; }}
  .amoprof-chart-grid {{ display:grid; gap:16px;
              grid-template-columns:repeat(auto-fit, minmax(560px, 1fr)); }}
  .amoprof-chart {{ background:{_BG2}; border:1px solid {_BORDER};
              border-radius:10px; padding:12px; }}
  .amoprof-chart-title {{ font-size:12px; color:{_MUTED}; margin:0 0 8px;
              text-transform:uppercase; letter-spacing:0.03em; }}
  .amoprof-chart img {{ width:100%; height:auto; display:block; }}
  .amoprof-warn {{ font-size:12px; color:#b91c1c; background:#fef2f2;
              border:1px solid #fca5a5; border-radius:8px; padding:8px 12px;
              margin:8px 0; }}
  footer.amoprof-footer {{ font-size:11px; color:{_MUTED}; padding:16px 24px;
              border-top:1px solid {_BORDER}; text-align:center; }}
</style>"""


def _render_chart(chart: dict[str, Any]) -> str:
    name = chart.get("name", "chart")
    kind = chart.get("kind", "b64")
    payload = chart.get("payload", "")
    title = html.escape(name.replace("_", " ").title())
    if not payload:
        return ""
    if kind == "b64":
        body = f'<img alt="{title}" src="data:image/png;base64,{payload}">'
    elif kind == "html":
        # Trust the payload (produced by our own chart_* fns).
        body = payload
    else:
        body = f'<div class="amoprof-warn">unknown chart kind: {html.escape(kind)}</div>'
    return (f'<div class="amoprof-chart">'
            f'<p class="amoprof-chart-title">{title}</p>{body}</div>')


def _render_section(analysis: Any) -> str:
    title = html.escape(getattr(analysis, "title", analysis.name))
    slug  = html.escape(analysis.name)
    charts = list(getattr(analysis, "charts", []) or [])
    warnings = list(getattr(analysis, "warnings", []) or [])

    parts = [f'<section class="amoprof-layer" id="section-{slug}">']
    parts.append(f'<h2>{title}<span class="amoprof-count">{len(charts)} chart'
                 f'{"s" if len(charts) != 1 else ""}</span></h2>')
    for w in warnings:
        parts.append(f'<div class="amoprof-warn">{html.escape(str(w))}</div>')
    if charts:
        parts.append('<div class="amoprof-chart-grid">')
        for c in charts:
            snippet = _render_chart(c)
            if snippet:
                parts.append(snippet)
        parts.append('</div>')
    else:
        parts.append('<div class="amoprof-empty">No charts produced for this '
                     'layer — likely no data was captured for the underlying '
                     'collectors.</div>')
    parts.append('</section>')
    return "\n".join(parts)


def build_layered_report(raw_dir: str | Path,
                         out_html: str | Path,
                         run_label: str = "",
                         theme: str = "light") -> Path:
    """Render `{layer → LayerAnalysis}` into a single HTML file.

    Returns the path written. Raises no exceptions on empty results —
    an empty run just produces a report where every section says
    "no charts produced for this layer".
    """
    from ..layers import run_layered_analyze  # local import: avoid cycles

    raw_dir = Path(raw_dir)
    out_html = Path(out_html)

    results = run_layered_analyze(raw_dir)

    nav_links = [f'<a href="#section-{html.escape(a.name)}">'
                 f'{html.escape(getattr(a, "title", a.name))}</a>'
                 for a in results.values()]
    sections = [_render_section(a) for a in results.values()]

    total_charts = sum(len(getattr(a, "charts", []) or []) for a in results.values())
    generated_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    label = html.escape(run_label or raw_dir.parent.name or raw_dir.name)

    doc = f"""<!doctype html>
<html><head><meta charset="utf-8">
<title>AMOprof layered report — {label}</title>
{_css()}
</head><body>
<header class="amoprof-header">
  <h1>AMOprof — layered analysis</h1>
  <div class="meta">Run: {label} · Generated: {generated_at} · {total_charts} chart{'s' if total_charts != 1 else ''} across {len(results)} layer{'s' if len(results) != 1 else ''}</div>
  <nav class="amoprof-nav">{''.join(nav_links)}</nav>
</header>
<main class="amoprof-main">
{chr(10).join(sections)}
</main>
<footer class="amoprof-footer">
  AMOprof layered report · one section per AI-stack layer · theme={html.escape(theme)}
</footer>
</body></html>"""

    out_html.parent.mkdir(parents=True, exist_ok=True)
    out_html.write_text(doc, encoding="utf-8")
    log.info("Wrote layered report: %s (%d charts, %d layers)",
             out_html, total_charts, len(results))
    return out_html


__all__ = ["build_layered_report"]
