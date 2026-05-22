"""
amoprof/report/combined.py — Merge the static and interactive reports into a
single HTML file with two tabs using <iframe srcdoc> for complete isolation.

  Tab 1: ⚡ Interactive  (Plotly hover charts, default)
  Tab 2: 📊 Static       (full amoprof matplotlib PNG report)

Why <iframe srcdoc>?
  • Each report has its own CSS that conflicts with the other (both define
    `.card`, `h2`, `body`, `.kpi-grid`, etc.). CSS scoping via selector
    prefixing is fragile and breaks the reports' own internal styling.
  • An <iframe srcdoc> provides complete DOM, CSS, and JS isolation by
    design — each report runs in its own browsing context exactly as if
    it were opened in its own tab.
  • The parent page only needs the tab-bar chrome; no CSS surgery needed.

Behaviour:
  • Tab bar is sticky at the top (z-index 9999).
  • Interactive tab is shown by default.
  • Alt+1 / Alt+2 keyboard shortcuts.
  • Last-used tab remembered in localStorage.
  • URL hash (#interactive or #static) updated on switch.
  • Each iframe is 100 % of the viewport height (minus tab bar) and
    scrolls independently.
  • The static iframe is loaded lazily (src set when first activated)
    so the page opens fast even though the static HTML is ~5 MB.

Public API:
    build_combined_report(
        raw_dir: Path,
        out_html: Path,
        static_html_path: Path | None = None,
        interactive_html_path: Path | None = None,
        run_label: str = "",
        theme: str = "dark",
    ) -> Path
"""
from __future__ import annotations

import html as _html
import re
from pathlib import Path


# ─── Tab-bar chrome (in the outer wrapper page only) ─────────────────────────

_OUTER_CSS = """
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  html, body {
    height: 100%;
    background: #0f172a;
    font-family: 'Inter', system-ui, sans-serif;
  }
  /* ── Tab bar ─────────────────────────────────────────────────────── */
  #amoprof-tabbar {
    position: fixed;
    top: 0; left: 0; right: 0;
    z-index: 9999;
    height: 46px;
    display: flex;
    align-items: stretch;
    background: #0f172a;
    border-bottom: 2px solid #1e293b;
    box-shadow: 0 2px 12px rgba(0,0,0,0.5);
    padding: 0 12px;
  }
  .tab-logo {
    display: flex; align-items: center; gap: 7px;
    color: #e2e8f0; font-size: 13px; font-weight: 700;
    padding: 0 14px 0 2px;
    border-right: 1px solid #334155;
    margin-right: 6px;
    letter-spacing: -0.2px;
    white-space: nowrap;
  }
  .tab-logo span { color: #818cf8; }
  .tab-btn {
    display: flex; align-items: center; gap: 6px;
    padding: 0 18px;
    font-size: 13px; font-weight: 600;
    color: #94a3b8;
    background: transparent;
    border: none;
    border-bottom: 3px solid transparent;
    cursor: pointer;
    white-space: nowrap;
    transition: color 0.15s, border-color 0.15s, background 0.15s;
    letter-spacing: -0.1px;
    height: 100%;
  }
  .tab-btn:hover { color: #e2e8f0; background: rgba(255,255,255,0.04); }
  .tab-btn.active {
    color: #a5b4fc;
    border-bottom-color: #6366f1;
    background: rgba(99,102,241,0.08);
  }
  .tab-badge {
    font-size: 9.5px; font-weight: 700;
    padding: 2px 5px; border-radius: 8px;
    background: #1e293b; color: #64748b;
    letter-spacing: 0.4px;
  }
  .tab-btn.active .tab-badge { background: #312e81; color: #a5b4fc; }
  .tab-spacer { flex: 1; }
  .tab-hint {
    display: flex; align-items: center;
    font-size: 10.5px; color: #475569;
    padding: 0 8px; font-style: italic;
  }
  /* ── Iframe panels ───────────────────────────────────────────────── */
  .tab-frame {
    position: fixed;
    top: 46px; left: 0; right: 0; bottom: 0;
    border: none;
    width: 100%;
    height: calc(100vh - 46px);
    background: #fff;
    display: none;
  }
  .tab-frame.active { display: block; }
</style>
"""

_OUTER_JS = """
<script>
(function() {
  var TABS = ['interactive', 'static'];
  var KEY  = 'amoprof_active_tab';
  var _staticLoaded = false;

  function showTab(id) {
    TABS.forEach(function(t) {
      var frame = document.getElementById('frame-' + t);
      var btn   = document.getElementById('btn-'   + t);
      if (!frame || !btn) return;
      if (t === id) {
        frame.classList.add('active');
        btn.classList.add('active');
        // Lazy-load the static iframe the first time it's shown
        if (t === 'static' && !_staticLoaded) {
          var src = frame.getAttribute('data-srcdoc');
          if (src) {
            frame.srcdoc = src;
            frame.removeAttribute('data-srcdoc');
          }
          _staticLoaded = true;
        }
      } else {
        frame.classList.remove('active');
        btn.classList.remove('active');
      }
    });
    try { history.replaceState(null, '', '#' + id); } catch(e) {}
    try { localStorage.setItem(KEY, id); } catch(e) {}
  }

  window.amoprofShowTab = showTab;

  document.addEventListener('DOMContentLoaded', function() {
    var hash   = (window.location.hash || '').replace('#', '');
    var stored = '';
    try { stored = localStorage.getItem(KEY) || ''; } catch(e) {}
    var initial = TABS.indexOf(hash)   >= 0 ? hash
                : TABS.indexOf(stored) >= 0 ? stored
                : 'interactive';
    showTab(initial);
  });

  document.addEventListener('keydown', function(e) {
    if (!e.altKey) return;
    if (e.key === '1') { amoprofShowTab('interactive'); e.preventDefault(); }
    if (e.key === '2') { amoprofShowTab('static');      e.preventDefault(); }
  });
})();
</script>
"""


def merge_reports(
    static_html: str,
    interactive_html: str,
    run_label: str = "",
    title: str = "AMOprof Combined Report",
) -> str:
    """Return a combined HTML string with two iframe-isolated tabs.

    Each report is embedded via <iframe srcdoc="..."> so their CSS and JS
    are completely isolated — no selector scoping or de-duplication needed.
    The static iframe is lazy-loaded (deferred until the tab is first clicked)
    so the initial page open is fast.
    """
    label_suffix = f" — {run_label}" if run_label else ""
    page_title   = f"{title}{label_suffix}"

    # Escape the HTML for srcdoc attribute values.
    # srcdoc content must have & → &amp;  and " → &quot; (the attr uses double-quotes).
    def _srcdoc(html_str: str) -> str:
        return html_str.replace('&', '&amp;').replace('"', '&quot;')

    int_srcdoc = _srcdoc(interactive_html)
    sta_srcdoc = _srcdoc(static_html)

    # The interactive iframe loads immediately (it's small ~300 KB).
    # The static iframe uses data-srcdoc and is only moved to srcdoc when the
    # tab is first activated (lazy load), saving ~5 MB on initial parse.

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>{_html.escape(page_title)}</title>
  {_OUTER_CSS}
</head>
<body>

<div id="amoprof-tabbar" role="tablist">
  <div class="tab-logo">📊 <span>AMO</span>prof</div>
  <button id="btn-interactive" class="tab-btn" role="tab"
          onclick="amoprofShowTab('interactive')"
          title="Interactive Plotly charts — hover for exact values">
    ⚡ Interactive
    <span class="tab-badge">PLOTLY</span>
  </button>
  <button id="btn-static" class="tab-btn" role="tab"
          onclick="amoprofShowTab('static')"
          title="Full static report — matplotlib PNGs, bottleneck table, formulas">
    📊 Static
    <span class="tab-badge">PNG</span>
  </button>
  <div class="tab-spacer"></div>
  <div class="tab-hint">⌨ Alt+1 / Alt+2</div>
</div>

<iframe id="frame-interactive"
        class="tab-frame"
        srcdoc="{int_srcdoc}"
        title="Interactive Report">
</iframe>

<iframe id="frame-static"
        class="tab-frame"
        data-srcdoc="{sta_srcdoc}"
        title="Static Report">
</iframe>

{_OUTER_JS}
</body>
</html>"""


# ─── Entry point ─────────────────────────────────────────────────────────────

def build_combined_report(
    raw_dir: Path,
    out_html: Path,
    static_html_path: "Path | None" = None,
    interactive_html_path: "Path | None" = None,
    run_label: str = "",
    theme: str = "dark",
) -> Path:
    """Generate a combined tabbed HTML report.

    If static_html_path / interactive_html_path are given they are read
    directly; otherwise both are generated from raw_dir on the fly.
    Returns the path to the written combined file.
    """
    import logging
    log = logging.getLogger("amoprof.combined")
    raw_dir  = Path(raw_dir)
    out_html = Path(out_html)
    out_html.parent.mkdir(parents=True, exist_ok=True)

    # ── Load or generate static report ──────────────────────────────────────
    if static_html_path and Path(static_html_path).exists():
        static_html = Path(static_html_path).read_text(encoding='utf-8', errors='replace')
        log.info("combined: loaded static report from %s (%d KB)",
                 static_html_path, len(static_html) // 1024)
    else:
        import sys, subprocess
        tmp = out_html.parent / "_tmp_static.html"
        try:
            import importlib.util as _ilu
            spec = _ilu.spec_from_file_location(
                'amoprof_report', Path(__file__).parent / 'amoprof.py')
            _mod = _ilu.module_from_spec(spec)
            spec.loader.exec_module(_mod)
            _mod.main(argv=[str(raw_dir), '--output', str(tmp)])
        except Exception as e:
            log.warning("combined: static report inline gen failed (%s) — subprocess", e)
            subprocess.run([sys.executable,
                            str(Path(__file__).parent / 'amoprof.py'),
                            str(raw_dir), '--output', str(tmp)], check=True)
        try:
            from .enhancer import enhance_report
            enhance_report(tmp, raw_dir=raw_dir, theme=theme)
        except Exception as e:
            log.warning("combined: enhancer failed (%s)", e)
        static_html = tmp.read_text(encoding='utf-8', errors='replace')
        try: tmp.unlink()
        except OSError: pass
        log.info("combined: generated static report (%d KB)", len(static_html) // 1024)

    # ── Load or generate interactive report ─────────────────────────────────
    if interactive_html_path and Path(interactive_html_path).exists():
        interactive_html = Path(interactive_html_path).read_text(
            encoding='utf-8', errors='replace')
        log.info("combined: loaded interactive report from %s (%d KB)",
                 interactive_html_path, len(interactive_html) // 1024)
    else:
        from .interactive import build_report as _build_int
        tmp = out_html.parent / "_tmp_interactive.html"
        _build_int(raw_dir, tmp, run_label=run_label)
        interactive_html = tmp.read_text(encoding='utf-8', errors='replace')
        try: tmp.unlink()
        except OSError: pass
        log.info("combined: generated interactive report (%d KB)",
                 len(interactive_html) // 1024)

    # ── Merge ────────────────────────────────────────────────────────────────
    combined = merge_reports(static_html, interactive_html, run_label=run_label)
    out_html.write_text(combined, encoding='utf-8')
    log.info("combined: wrote %s (%d KB)", out_html, len(combined) // 1024)
    return out_html
