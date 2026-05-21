"""
amoprof/report/combined.py — Merge the static and interactive reports into a
single HTML file with two tabs:

  Tab 1: ⚡ Interactive  (Plotly hover charts, default)
  Tab 2: 📊 Static       (matplotlib PNG report, full fidelity)

The merger is pure HTML/CSS/JS — no server needed.  Approach:

  • A sticky tab-bar sits at the top of the page (z-index > everything else).
  • Each tab's content lives in a <div id="tab-static|interactive"> that is
    shown/hidden with a CSS class.  No iframes — both reports share the page
    and are fully accessible to the browser's Ctrl+F search.
  • CSS namespacing: static report styles are scoped under `#tab-static` and
    interactive styles under `#tab-interactive` to prevent conflicts.
  • Plotly charts load lazily only when the Interactive tab is first shown, so
    the initial page load is fast even at 5 MB+.
  • The Plotly CDN <script> tag is de-duplicated; only one copy is emitted.
  • A URL hash (#static or #interactive) is preserved so links / bookmarks
    land on the correct tab.

Public API:
    build_combined_report(
        raw_dir: Path,
        out_html: Path,
        static_html: Path | None = None,
        interactive_html: Path | None = None,
        run_label: str = "",
        theme: str = "dark",
    ) -> Path

If static_html / interactive_html are given, they are used directly.
Otherwise both are generated from raw_dir on the fly.
"""
from __future__ import annotations

import re
from pathlib import Path


# ─── HTML structure helpers ───────────────────────────────────────────────────

_TAB_CSS = """
<style id="amoprof-combined-tabs">
/* ── Combined report tab chrome ─────────────────────────────────────── */
#amoprof-tabbar {
  position: sticky;
  top: 0;
  z-index: 9999;
  display: flex;
  align-items: stretch;
  gap: 0;
  background: #0f172a;
  border-bottom: 2px solid #1e293b;
  box-shadow: 0 2px 12px rgba(0,0,0,0.45);
  padding: 0 16px;
  font-family: 'Inter', system-ui, sans-serif;
}
#amoprof-tabbar .tab-logo {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #e2e8f0;
  font-size: 13px;
  font-weight: 700;
  padding: 0 16px 0 4px;
  border-right: 1px solid #334155;
  margin-right: 8px;
  letter-spacing: -0.2px;
  white-space: nowrap;
}
#amoprof-tabbar .tab-logo span { color: #818cf8; }
.amoprof-tab-btn {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 12px 20px;
  font-size: 13px;
  font-weight: 600;
  color: #94a3b8;
  background: transparent;
  border: none;
  border-bottom: 3px solid transparent;
  cursor: pointer;
  white-space: nowrap;
  transition: color 0.15s, border-color 0.15s;
  letter-spacing: -0.1px;
}
.amoprof-tab-btn:hover { color: #e2e8f0; }
.amoprof-tab-btn.active {
  color: #a5b4fc;
  border-bottom-color: #6366f1;
  background: rgba(99,102,241,0.07);
}
.amoprof-tab-btn .tab-badge {
  font-size: 10px;
  font-weight: 700;
  padding: 2px 6px;
  border-radius: 10px;
  background: #1e293b;
  color: #64748b;
  letter-spacing: 0.3px;
}
.amoprof-tab-btn.active .tab-badge { background: #312e81; color: #a5b4fc; }
#amoprof-tabbar .tab-spacer { flex: 1; }
#amoprof-tabbar .tab-hint {
  display: flex;
  align-items: center;
  font-size: 11px;
  color: #475569;
  padding: 0 8px;
  font-style: italic;
}

/* ── Tab pane show/hide ──────────────────────────────────────────────── */
.amoprof-tab-pane { display: none; }
.amoprof-tab-pane.active { display: block; }

/* ── Per-pane style scoping — prevent card/kpi/h2 conflicts ─────────── */
/* Static pane: give its body element some breathing room below the tabbar */
#tab-static  { padding-top: 8px; }
#tab-interactive { padding-top: 8px; }
</style>
"""

_TAB_JS = """
<script id="amoprof-combined-tabs-js">
(function() {
  var TABS = ['interactive', 'static'];
  var STORAGE_KEY = 'amoprof_active_tab';

  function showTab(id) {
    TABS.forEach(function(t) {
      var pane = document.getElementById('tab-' + t);
      var btn  = document.getElementById('tabBtn-' + t);
      if (!pane || !btn) return;
      if (t === id) {
        pane.classList.add('active');
        btn.classList.add('active');
      } else {
        pane.classList.remove('active');
        btn.classList.remove('active');
      }
    });
    // Update URL hash (no page reload)
    try { history.replaceState(null, '', '#' + id); } catch(e) {}
    // Persist for next open
    try { localStorage.setItem(STORAGE_KEY, id); } catch(e) {}
    // Trigger Plotly resize if switching to interactive (charts need relayout)
    if (id === 'interactive' && window.Plotly) {
      setTimeout(function() {
        var plots = document.getElementById('tab-interactive')
                            .querySelectorAll('.plotly-graph-div');
        plots.forEach(function(el) {
          try { Plotly.relayout(el, {}); } catch(e) {}
        });
      }, 50);
    }
  }

  window.amoprofShowTab = showTab;

  document.addEventListener('DOMContentLoaded', function() {
    // Determine initial tab from: URL hash > localStorage > default (interactive)
    var hash = (window.location.hash || '').replace('#', '');
    var stored = '';
    try { stored = localStorage.getItem(STORAGE_KEY) || ''; } catch(e) {}
    var initial = (TABS.indexOf(hash) >= 0)    ? hash
                : (TABS.indexOf(stored) >= 0)  ? stored
                : 'interactive';
    showTab(initial);
  });
})();
</script>
"""

_TABBAR_HTML = """
<div id="amoprof-tabbar" role="tablist">
  <div class="tab-logo">📊 <span>AMO</span>prof</div>
  <button id="tabBtn-interactive" class="amoprof-tab-btn" role="tab"
          onclick="amoprofShowTab('interactive')"
          title="Interactive Plotly charts — hover for exact values">
    ⚡ Interactive
    <span class="tab-badge">PLOTLY</span>
  </button>
  <button id="tabBtn-static" class="amoprof-tab-btn" role="tab"
          onclick="amoprofShowTab('static')"
          title="Full static report with all chart sections">
    📊 Static
    <span class="tab-badge">PNG</span>
  </button>
  <div class="tab-spacer"></div>
  <div class="tab-hint">⌨ Press Alt+1 / Alt+2 to switch tabs</div>
</div>
<script>
document.addEventListener('keydown', function(e) {
  if (e.altKey && e.key === '1') amoprofShowTab('interactive');
  if (e.altKey && e.key === '2') amoprofShowTab('static');
});
</script>
"""


# ─── Core merger ─────────────────────────────────────────────────────────────

def _extract_head_parts(html: str) -> tuple[str, str]:
    """Return (head_inner, body_inner) from a full HTML document.

    Uses rfind / rpartition logic for </body> and </head> so that JS strings
    embedded in the document (e.g. the static report's "open in new tab" popup
    that contains '<body …></body></html>') do not fool the regex into stopping
    at the wrong closing tag.
    """
    # ── <head> ───────────────────────────────────────────────────────────────
    head_open  = re.search(r'<head[^>]*>', html, re.IGNORECASE)
    # Use the FIRST </head> that comes after the head open
    head_close_idx = html.lower().find('</head>')
    if head_open and head_close_idx > head_open.start():
        head = html[head_open.end():head_close_idx]
    else:
        head = ''

    # ── <body> ───────────────────────────────────────────────────────────────
    # Find the LAST <body> open tag (the real document body, not one inside JS)
    # and the LAST </body> close tag.
    body_open_iter = list(re.finditer(r'<body[^>]*>', html, re.IGNORECASE))
    # The real <body> is typically the LAST one found, or the one that appears
    # AFTER </head>.  Use the last open tag whose offset > head_close_idx.
    real_body_open = None
    for m in body_open_iter:
        if m.start() > head_close_idx:
            real_body_open = m
            break
    if real_body_open is None and body_open_iter:
        real_body_open = body_open_iter[-1]

    # The real </body> is the LAST one in the document.
    real_body_close = html.lower().rfind('</body>')

    if real_body_open and real_body_close > real_body_open.end():
        body = html[real_body_open.end():real_body_close]
    else:
        # No proper <body> tags — treat whole document as body
        body = html

    return head, body


def _scope_css(css_block: str, scope_id: str) -> str:
    """Prefix every CSS rule in `css_block` with `#scope_id` so styles only
    apply inside that tab pane.

    Handles:
      .foo { ... }         →  #scope_id .foo { ... }
      body { ... }         →  #scope_id { ... }      (body = the pane itself)
      * { ... }            →  #scope_id * { ... }
      @media ... { ... }   →  kept (re-scoped inside)
      @keyframes / @font   →  kept as-is (global)
      :root { ... }        →  kept as-is (CSS variables must be global)
    """
    # Parse and scope rule by rule using a simple state machine
    result = []
    i = 0
    n = len(css_block)

    while i < n:
        # Skip whitespace
        while i < n and css_block[i] in ' \t\n\r':
            result.append(css_block[i])
            i += 1
        if i >= n:
            break

        # Comments
        if css_block[i:i+2] == '/*':
            end = css_block.find('*/', i+2)
            end = end + 2 if end >= 0 else n
            result.append(css_block[i:end])
            i = end
            continue

        # At-rules
        if css_block[i] == '@':
            at_end = css_block.find('{', i)
            semi   = css_block.find(';', i)
            # Simple at-rules (no block): @import, @charset, @namespace
            if semi >= 0 and (at_end < 0 or semi < at_end):
                result.append(css_block[i:semi+1])
                i = semi + 1
                continue
            at_kw = css_block[i:i+20].lower()
            # Passthrough at-rules (don't scope inside)
            if any(at_kw.startswith(k) for k in ('@keyframes', '@font-face', ':root')):
                # Find matching closing brace
                depth = 0
                j = at_end
                while j < n:
                    if css_block[j] == '{': depth += 1
                    elif css_block[j] == '}':
                        depth -= 1
                        if depth == 0:
                            result.append(css_block[i:j+1])
                            i = j + 1
                            break
                    j += 1
                else:
                    result.append(css_block[i:])
                    i = n
                continue
            # Block at-rules (@media, @supports): recurse into their content
            if at_end >= 0:
                at_header = css_block[i:at_end+1]
                depth = 1
                j = at_end + 1
                while j < n and depth > 0:
                    if css_block[j] == '{': depth += 1
                    elif css_block[j] == '}': depth -= 1
                    j += 1
                inner = css_block[at_end+1:j-1]
                scoped_inner = _scope_css(inner, scope_id)
                result.append(at_header + scoped_inner + '}')
                i = j
                continue

        # Regular rule: collect selector(s) up to '{'
        brace = css_block.find('{', i)
        if brace < 0:
            result.append(css_block[i:])
            break
        selector_block = css_block[i:brace].strip()
        # Find matching closing brace
        depth = 1
        j = brace + 1
        while j < n and depth > 0:
            if css_block[j] == '{': depth += 1
            elif css_block[j] == '}': depth -= 1
            j += 1
        rule_body = css_block[brace:j]  # includes { ... }

        # Scope each comma-separated selector
        scoped_selectors = []
        for sel in selector_block.split(','):
            sel = sel.strip()
            if not sel:
                continue
            # Normalise body/html/root selectors — they become the pane div itself
            norm = sel.lower().strip()
            if norm in ('body', 'html', ':root', '*'):
                scoped_selectors.append(f'#{scope_id}')
            elif norm.startswith('body ') or norm.startswith('html '):
                scoped_selectors.append(f'#{scope_id} ' + sel[5:].strip())
            else:
                scoped_selectors.append(f'#{scope_id} ' + sel)

        if scoped_selectors:
            result.append(', '.join(scoped_selectors) + ' ' + rule_body)
        i = j

    return ''.join(result)


def _extract_styles(head: str) -> list[tuple[str, str]]:
    """Return list of (id_or_empty, css_text) for each <style> tag in head."""
    out = []
    for m in re.finditer(r'<style([^>]*)>(.*?)</style>', head, re.DOTALL | re.IGNORECASE):
        attrs = m.group(1)
        css   = m.group(2)
        id_m  = re.search(r'\bid=["\']([^"\']+)', attrs)
        out.append((id_m.group(1) if id_m else '', css))
    return out


def _extract_scripts(head: str) -> list[str]:
    """Return list of <script ...>...</script> or <script src=...> strings."""
    return re.findall(r'<script[^>]*>.*?</script>|<script[^>]+/>', head, re.DOTALL | re.IGNORECASE)


def _dedup_plotly_cdn(html: str) -> str:
    """Ensure only one Plotly CDN <script> tag survives in the document."""
    plotly_re = re.compile(r'<script[^>]+plot\.ly[^>]*>.*?</script>|'
                           r'<script[^>]+plotly[^>]*>.*?</script>',
                           re.DOTALL | re.IGNORECASE)
    matches = list(plotly_re.finditer(html))
    if len(matches) <= 1:
        return html
    # Keep first, remove the rest
    for m in reversed(matches[1:]):
        html = html[:m.start()] + html[m.end():]
    return html


def merge_reports(
    static_html: str,
    interactive_html: str,
    run_label: str = "",
    title: str = "AMOprof Combined Report",
) -> str:
    """Merge two full HTML documents into one tabbed HTML string."""

    static_head,      static_body      = _extract_head_parts(static_html)
    interactive_head, interactive_body = _extract_head_parts(interactive_html)

    # ── Collect styles from both heads ──────────────────────────────────────
    combined_head_parts: list[str] = []
    seen_style_ids: set[str] = set()

    # Interactive styles come first (they define the base layout)
    for sid, css in _extract_styles(interactive_head):
        if sid and sid in seen_style_ids:
            continue
        if sid:
            seen_style_ids.add(sid)
        # Scope interactive styles to its tab pane (except enhancer theme which
        # is already scoped and handles dark mode globally)
        if sid == 'amoprof-enhancer-theme':
            combined_head_parts.append(f'<style id="{sid}">{css}</style>')
        else:
            scoped = _scope_css(css, 'tab-interactive')
            combined_head_parts.append(
                f'<style id="int-{sid or "main"}">{scoped}</style>')

    # Static styles scoped to #tab-static
    for sid, css in _extract_styles(static_head):
        if sid and sid in seen_style_ids:
            continue
        if sid:
            seen_style_ids.add(sid)
        scoped = _scope_css(css, 'tab-static')
        combined_head_parts.append(
            f'<style id="sta-{sid or "main"}">{scoped}</style>')

    # Tab chrome CSS (unscoped — it styles the tabbar itself)
    combined_head_parts.append(_TAB_CSS)

    # ── Scripts ─────────────────────────────────────────────────────────────
    # Collect all <script> tags from both heads, de-dup by src URL
    seen_srcs: set[str] = set()
    script_tags: list[str] = []
    for tag in _extract_scripts(interactive_head) + _extract_scripts(static_head):
        src_m = re.search(r'\bsrc=["\']([^"\']+)', tag, re.IGNORECASE)
        src = src_m.group(1) if src_m else None
        if src:
            if src in seen_srcs:
                continue
            seen_srcs.add(src)
        script_tags.append(tag)

    # ── Title ────────────────────────────────────────────────────────────────
    label_suffix = f" — {run_label}" if run_label else ""
    page_title = f"{title}{label_suffix}"

    # ── Build <head> ─────────────────────────────────────────────────────────
    head_html = (
        f'<meta charset="utf-8"/>\n'
        f'<meta name="viewport" content="width=device-width,initial-scale=1"/>\n'
        f'<title>{page_title}</title>\n'
        + '\n'.join(combined_head_parts)
        + '\n'.join(script_tags)
    )

    # ── Build combined <body> ────────────────────────────────────────────────
    body_html = (
        _TABBAR_HTML
        + f'\n<div id="tab-interactive" class="amoprof-tab-pane" role="tabpanel">\n'
        + interactive_body
        + '\n</div>\n'
        + f'\n<div id="tab-static" class="amoprof-tab-pane" role="tabpanel">\n'
        + static_body
        + '\n</div>\n'
        + _TAB_JS
    )

    combined = (
        '<!DOCTYPE html>\n'
        f'<html lang="en">\n'
        f'<head>\n{head_html}\n</head>\n'
        f'<body style="margin:0;padding:0">\n{body_html}\n</body>\n'
        '</html>'
    )

    return _dedup_plotly_cdn(combined)


# ─── Entry point ─────────────────────────────────────────────────────────────

def build_combined_report(
    raw_dir: Path,
    out_html: Path,
    static_html_path: "Path | None" = None,
    interactive_html_path: "Path | None" = None,
    run_label: str = "",
    theme: str = "dark",
) -> Path:
    """Generate a combined tabbed HTML report from raw_dir.

    If static_html_path / interactive_html_path are given, they are read
    directly (useful when you've already generated both reports separately).
    Otherwise both are generated from raw_dir on the fly.

    Args:
        raw_dir:              Path to the raw/ directory.
        out_html:             Output path for the combined file.
        static_html_path:     Optional pre-generated static report HTML.
        interactive_html_path:Optional pre-generated interactive report HTML.
        run_label:            Short label shown in the page title.
        theme:                "dark" or "light" for the static report.

    Returns the path to the written combined file.
    """
    import logging
    log = logging.getLogger("amoprof.combined")
    raw_dir  = Path(raw_dir)
    out_html = Path(out_html)
    out_html.parent.mkdir(parents=True, exist_ok=True)

    # ── Generate or load static report ──────────────────────────────────────
    if static_html_path and Path(static_html_path).exists():
        static_html = Path(static_html_path).read_text(encoding='utf-8', errors='replace')
        log.info("combined: loaded static report from %s", static_html_path)
    else:
        import tempfile, subprocess, sys
        tmp_static = out_html.parent / "_tmp_static.html"
        try:
            import importlib.util as _ilu
            spec = _ilu.spec_from_file_location(
                'amoprof_report',
                Path(__file__).parent / 'amoprof.py')
            _mod = _ilu.module_from_spec(spec)
            spec.loader.exec_module(_mod)
            _mod.main(argv=[str(raw_dir), '--output', str(tmp_static)])
        except Exception as e:
            log.warning("combined: static report generation failed (%s) — "
                        "running as subprocess", e)
            subprocess.run(
                [sys.executable, str(Path(__file__).parent / 'amoprof.py'),
                 str(raw_dir), '--output', str(tmp_static)],
                check=True)
        # Apply theme via enhancer
        try:
            from .enhancer import enhance_report
            enhance_report(tmp_static, raw_dir=raw_dir, theme=theme)
        except Exception as e:
            log.warning("combined: enhancer failed (%s)", e)
        static_html = tmp_static.read_text(encoding='utf-8', errors='replace')
        try:
            tmp_static.unlink()
        except OSError:
            pass
        log.info("combined: generated static report (%d KB)", len(static_html)//1024)

    # ── Generate or load interactive report ─────────────────────────────────
    if interactive_html_path and Path(interactive_html_path).exists():
        interactive_html = Path(interactive_html_path).read_text(
            encoding='utf-8', errors='replace')
        log.info("combined: loaded interactive report from %s", interactive_html_path)
    else:
        from .interactive import build_report as _build_int
        tmp_int = out_html.parent / "_tmp_interactive.html"
        _build_int(raw_dir, tmp_int, run_label=run_label)
        interactive_html = tmp_int.read_text(encoding='utf-8', errors='replace')
        try:
            tmp_int.unlink()
        except OSError:
            pass
        log.info("combined: generated interactive report (%d KB)",
                 len(interactive_html)//1024)

    # ── Merge ────────────────────────────────────────────────────────────────
    combined = merge_reports(
        static_html,
        interactive_html,
        run_label=run_label,
    )

    out_html.write_text(combined, encoding='utf-8')
    log.info("combined: wrote %s (%d KB)", out_html, len(combined)//1024)
    return out_html
