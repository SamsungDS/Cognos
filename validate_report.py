#!/usr/bin/env python3
"""validate_report.py — validate a GENERATED AMOprof HTML report.

Operates on the artefact itself, not on the raw directory: point it at any
report file and it parses what was actually rendered.  That means it works on
reports produced by a different version, on another host, or months ago — and
it validates the thing you actually ship rather than re-deriving it.

    python3 validate_report.py report.html [more.html ...]
    python3 validate_report.py results/*/amoprof_*_combined.html
    python3 validate_report.py --render <raw_dir>    # render first, then check

Check groups:

  LAYOUT     structural integrity — expected sections present, no unsubstituted
             template placeholders, no truncation, no leaked traceback
  TIER       tier claims agree with tier evidence: a tier the config declares
             must either be charted or explicitly reported as not collected
  TILES      bounded quantities within bounds, used <= capacity, no NaN/Inf,
             HBM capacity consistent with the GPU count the report states
  CHARTS     every Pearson r within [-1, 1], every scatter n >= 3, every chart
             carrying hover coordinates, no chart drawn with no data
  CROSSTAB   a quantity shown on more than one tab must agree

Exit status is non-zero if any check fails, so it can gate a release.
"""
from __future__ import annotations

import html as _html
import math
import re
import sys
from pathlib import Path


def _text(x: str) -> str:
    return " ".join(_html.unescape(re.sub(r"<[^>]+>", " ", x)).split())


def _num(s: str):
    m = re.search(r"[-+]?[\d,]*\.?\d+", s or "")
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


def _tiles(html: str) -> list[tuple[str, str, str]]:
    """(label, value, note) for every KPI tile in the document."""
    out = []
    for m in re.finditer(r'kpi-label"?[^>]*>([^<]{2,70})<', html):
        seg = html[m.start():m.start() + 1400]
        v = re.search(r"kpi-value[^>]*>(.*?)</div>", seg, re.S)
        n = re.search(r"kpi-note[^>]*>(.*?)</div>", seg, re.S)
        if v:
            out.append((_html.unescape(m.group(1)).strip(),
                        _text(v.group(1)), _text(n.group(1)) if n else ""))
    return out


def _tabs(html: str) -> dict[str, str]:
    """Split a combined report into tabs; a single-surface file is one tab."""
    marks = {}
    for name, needle in (("executive", "Executive Summary"),
                         ("interactive", "Interactive Report"),
                         ("end", "End Report")):
        i = html.find(needle)
        if i >= 0:
            marks[name] = i
    if len(marks) < 2:
        return {"report": html}
    order = sorted(marks.items(), key=lambda kv: kv[1])
    out = {}
    for k, (name, start) in enumerate(order):
        end = order[k + 1][1] if k + 1 < len(order) else len(html)
        out[name] = html[start:end]
    return out


class Result:
    def __init__(self, label: str):
        self.label, self.failures, self.warnings, self.checks = label, [], [], 0

    def check(self, ok, name, detail=""):
        self.checks += 1
        if not ok:
            self.failures.append(f"{name}" + (f" — {detail}" if detail else ""))
        return ok

    def warn(self, cond, name, detail=""):
        if cond:
            self.warnings.append(f"{name}" + (f" — {detail}" if detail else ""))


def validate_html(html: str, label: str) -> Result:
    r = Result(label)
    unesc = _html.unescape(html)
    # A combined report embeds each tab in an iframe `srcdoc`, where the inner
    # markup survives with its quotes escaped.  Unescaping once gives the real
    # tab markup, so tile/chart checks see the same content a browser renders.
    if "srcdoc=" in html and html.count("kpi-label") < 4:
        html = unesc

    # ---- LAYOUT ------------------------------------------------------------
    r.check(len(html) > 50_000, "LAYOUT document is non-trivial", f"{len(html)} bytes")
    r.check(html.rstrip().endswith(("</html>", "</body>", "</div>", "</script>", ">")),
            "LAYOUT document is not truncated", repr(html.rstrip()[-40:]))
    # `metric{label}` in documentation text is PromQL, not an unsubstituted
    # placeholder, so require the brace to be preceded by whitespace or a tag.
    stray = {m.group(1) for m in
             re.finditer(r"(?:^|[\s>])\{(_?[a-z][a-z0-9_]{3,40})\}", html, re.M)
             if not m.group(1).startswith(("font", "margin", "grid", "flex",
                                           "text", "border"))}
    r.check(not stray, "LAYOUT no unsubstituted template placeholders",
            ", ".join(sorted(stray)[:5]))
    r.check("Correlation charts unavailable" not in html,
            "LAYOUT bottleneck section rendered without an internal error",
            _text(html[html.find("Correlation charts unavailable"):][:130])
            if "Correlation charts unavailable" in html else "")
    r.check("Bottleneck Analysis" in html, "LAYOUT Bottleneck Analysis section present")
    r.check("Traceback (most recent call last)" not in html,
            "LAYOUT no Python traceback leaked into the report")

    tiles = _tiles(html)
    r.check(len(tiles) >= 4, "LAYOUT summary tiles rendered", f"{len(tiles)} tiles")

    # ---- TIER --------------------------------------------------------------
    section = html.split("Bottleneck Analysis", 1)[-1]
    axes = {t: section.count(f"{t} &#183;") + section.count(f"{t} \u00b7")
            for t in ("L1", "L2", "L3", "L3.5", "NET")}
    axes["L3"] = max(0, axes["L3"] - axes["L3.5"])   # "L3.5" contains "L3"

    claims_l2 = bool(re.search(r"HiCache[^<]{0,40}(enabled|\d)", unesc, re.I))
    claims_l3 = bool(re.search(r"L3 (storage|Device|Mount)|hicache_storage_backend",
                               unesc, re.I))
    says_uncollected = bool(re.search(
        r"not collected in this run|no L2 charts|no L3 charts|NO TELEMETRY|"
        r"has no timeseries", unesc, re.I))

    r.check(axes["L1"] > 0, "TIER L1 (GPU/HBM) is charted", "no L1 axis references")
    if claims_l2:
        r.check(axes["L2"] > 0 or says_uncollected,
                "TIER L2 declared in config is charted or explicitly reported absent",
                f"{axes['L2']} L2 axis refs, no 'not collected' statement")
    if claims_l3:
        r.check(axes["L3"] > 0 or axes["L3.5"] > 0 or says_uncollected,
                "TIER L3 declared in config is charted or explicitly reported absent",
                f"{axes['L3']} L3 axis refs, no 'not collected' statement")
    r.warn(axes["L2"] == 0 and axes["L3"] == 0 and axes["L3.5"] == 0,
           "TIER only L1 charted — no memory or storage tier data in this run")

    # ---- TILES -------------------------------------------------------------
    for lab, val, _note in tiles:
        low = lab.lower()
        r.check("nan" not in val.lower() and "inf" not in val.lower().split(),
                f"TILES '{lab}' has no NaN/Inf", val[:30])
        n = _num(val)
        if n is None:
            continue
        if "%" in val or any(k in low for k in ("util", "hit", "fill")):
            r.check(-0.01 <= n <= 100.01, f"TILES '{lab}' is a valid percentage", f"{n}")
        if any(k in low for k in ("used", "bw", "throughput", "power", "tokens",
                                  "capacity", "latency", "ttft", "tpot", "count")):
            r.check(n >= 0, f"TILES '{lab}' is non-negative", f"{n}")
        if re.search(r"\br\s*/\s*w\b|read\s*/\s*write|\bin\s*/\s*out\b", lab, re.I):
            continue          # two independent quantities, not used/capacity
        m = re.match(r"\s*([\d.,]+)\s*(?:GB|MB|TB|%)?\s*/\s*([\d.,]+)", val)
        if m:
            a, b = float(m.group(1).replace(",", "")), float(m.group(2).replace(",", ""))
            if b > 0:
                r.check(a <= b * 1.02, f"TILES '{lab}' used <= capacity", f"{a} / {b}")

    # The GPU util headline is the overall mean its formula describes, not the
    # busy-only mean: that one read 99.4% for GPUs idle 80% of the window.
    for lab, val, note in tiles:
        if lab.strip().lower() != "gpu util":
            continue
        shown = _num(val)
        m_ov = re.search(r"overall\s+([\d.]+)\s*%", note)
        if shown is not None and m_ov:
            r.check(abs(shown - float(m_ov.group(1))) < 0.15,
                    "TILES 'GPU util' headline is the overall mean",
                    f"headline {shown} vs overall {m_ov.group(1)} in its note")

    # Compare the HBM tile's own capacity against the per-GPU capacity and GPU
    # count stated in that same tile's note — matching "N GB/GPU" anywhere in
    # the document picks up per-GPU *usage* figures from unrelated charts.
    _hbm = next(((v, n) for l, v, n in tiles if "hbm used" in l.lower()), None)
    if _hbm:
        _val, _note = _hbm
        m3 = re.search(r"/\s*([\d.,]+)", _val)
        m4 = re.search(r"([\d.]+)\s*GB\s*(?:/|per )GPU", _note)
        mg = re.search(r"(\d+)\s*GPU\(s\)", _note)
        if m3 and m4 and mg:
            shown = float(m3.group(1).replace(",", ""))
            per, cnt = float(m4.group(1)), float(mg.group(1))
            r.check(abs(shown - per * cnt) / max(shown, 1) < 0.05,
                    "TILES HBM capacity = per-GPU x GPU count stated in the tile",
                    f"shown={shown:.0f} GB, {per:.0f} x {cnt:g} = {per*cnt:.0f} GB")

    kv = re.search(r"KV = ([\d.]+) KB/token \(([^)]*)\)", unesc)
    if kv:
        kb, src = float(kv.group(1)), kv.group(2)
        r.check(1.0 <= kb <= 4096.0, "TILES KV bytes/token is plausible", f"{kb} KB")
        r.warn("ESTIMATE" in src or "UNRESOLVED" in src,
               "TILES KV bytes/token is estimated, not from model config", src[:50])

    # ---- CHARTS ------------------------------------------------------------
    rs = [float(x) for x in re.findall(r"Pearson r = ([+-][\d.]+)", html)]
    bad = [x for x in rs if math.isnan(x) or not (-1.0001 <= x <= 1.0001)]
    r.check(not bad, "CHARTS all Pearson r within [-1, 1]", f"{len(bad)} out of range")
    r.check(bool(rs), "CHARTS correlations were computed", f"{len(rs)} coefficients")

    ns = [int(x) for x in re.findall(r"n=(\d+) time-aligned", html)]
    if ns:
        r.check(min(ns) >= 3, "CHARTS every scatter has n >= 3", f"min n={min(ns)}")
        r.warn(min(ns) < 30, "CHARTS some scatters use very few samples",
               f"min n={min(ns)}")

    panels = re.findall(r'<div class="corr-chart[^"]*"[^>]*>(<svg.*?</svg>)', html, re.S)
    if panels:
        miss = sum(1 for p in panels if "<title>" not in p)
        r.check(miss == 0, "CHARTS every chart has hover coordinates",
                f"{miss}/{len(panels)} without")
        empty = sum(1 for p in panels
                    if p.count("<circle") + p.count("<rect") <= 2 and "<polyline" not in p)
        r.check(empty == 0, "CHARTS no chart drawn with no data",
                f"{empty}/{len(panels)} empty")

    # Per-request distribution charts: the completion-based ones count the
    # same requests, so their n must match; TTFT counts first tokens and may
    # differ by requests in flight at the window edges, which must be said.
    _ns = {}
    for m_t in re.finditer(r'font-weight="800">([^<]{3,60}?) — p50 / p90 / p99</text>', unesc):
        m_n = re.search(r"n=([\d,]+) ([a-z][^<]{2,60})</text>", unesc[m_t.end():m_t.end() + 8000])
        if m_n:
            _ns[m_t.group(1).strip()] = (int(m_n.group(1).replace(",", "")), m_n.group(2))
    _done = {k: v for k, v in _ns.items()
             if k in ("E2E request latency", "Input tokens / request", "Output tokens / request")}
    if len(_done) >= 2:
        r.check(len({n for n, _ in _done.values()}) == 1,
                "CHARTS completion-based request charts report the same n",
                ", ".join(f"{k} n={n}" for k, (n, _) in _done.items()))
    if "TTFT" in _ns and _done:
        n_ttft, n_done = _ns["TTFT"][0], next(iter(_done.values()))[0]
        r.check(n_ttft == n_done or "Why the n counts differ" in unesc,
                "CHARTS TTFT vs completed-request n difference is explained",
                f"TTFT n={n_ttft} vs completed n={n_done}, no explanation")
        r.check(all(lbl != "observations" for _, lbl in _ns.values()),
                "CHARTS distribution n says what it counts",
                ", ".join(f"{k}: {lbl}" for k, (_, lbl) in _ns.items() if lbl == "observations"))

    # HBM composition is a partition of the device: its bands must add up to
    # the capacity in the chart header.  KV in use was once counted twice,
    # giving 214.1 GB (119%) on a 179 GB card.
    i = unesc.find("HBM composition per GPU")
    if i >= 0:
        seg = _text(unesc[i:unesc.find("</svg>", i)])
        cap = re.search(r"used of ([\d.,]+) GB", seg)
        bands = [float(g.replace(",", ""))
                 for g in re.findall(r"— ([\d.,]+) GB \(\d+%\)", seg)]
        if cap and bands:
            dev = float(cap.group(1).replace(",", ""))
            # Bands are printed to 0.1 GB, so allow rounding per band.
            r.check(abs(sum(bands) - dev) <= max(0.06 * len(bands), dev * 0.01),
                    "CHARTS HBM composition bands sum to device capacity",
                    f"{' + '.join(f'{b:g}' for b in bands)} = {sum(bands):.1f} GB vs {dev:g} GB")

    # ---- CROSSTAB ----------------------------------------------------------
    tabs = _tabs(html)
    # Latency prints one way, like the KPI tiles (6730 ms): no thousands
    # separator, no scientific notation.  The Executive tab once showed one
    # TTFT p50 as 6,730 / 6,730.22 / 6,730.2 / 7.4e+03 beside tiles reading 6730.
    if "executive" in tabs:
        ex = _html.unescape(_html.unescape(tabs["executive"]))
        odd = sorted({m.group(0) for m in re.finditer(
            r"\b\d{1,3}(?:,\d{3})+(?:\.\d+)? ?ms\b|\b\d\.\d+e[+-]\d+ ?ms\b", ex)})
        r.check(not odd, "CROSSTAB Executive latencies use the tile format (no comma)",
                f"{len(odd)} e.g. {', '.join(odd[:3])}")
    if len(tabs) > 1:
        per_tab = {k: {l: v for l, v, _ in _tiles(t)} for k, t in tabs.items()}
        names = [n for n in ("executive", "interactive") if n in per_tab]
        if len(names) == 2:
            a_, b_ = per_tab[names[0]], per_tab[names[1]]
            for lab in sorted(set(a_) & set(b_)):
                x, y = _num(a_[lab]), _num(b_[lab])
                if x is None or y is None or max(abs(x), abs(y)) == 0:
                    continue
                r.check(abs(x - y) / max(abs(x), abs(y)) < 0.02,
                        f"CROSSTAB '{lab}' agrees across tabs",
                        f"{names[0]}={x} {names[1]}={y}")
    return r


def main(argv: list[str]) -> int:
    args = argv[1:]
    targets: list[tuple[str, str]] = []

    if args and args[0] == "--render":
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from amoprof.report import combined as C
        for a in args[1:]:
            targets.append((f"{Path(a).name} (rendered)",
                            C.build_executive_summary_html(Path(a))))
    else:
        for a in args:
            p = Path(a)
            if not p.exists():
                print(f"{a}: NOT FOUND")
                return 2
            targets.append((p.name, p.read_text(encoding="utf-8", errors="replace")))

    if not targets:
        print(__doc__)
        return 2

    total = 0
    for name, html in targets:
        res = validate_html(html, name)
        status = "PASS" if not res.failures else f"FAIL ({len(res.failures)})"
        print(f"\n{'=' * 74}\n{res.label}\n  {res.checks} checks — {status}")
        for f in res.failures:
            print(f"  FAIL  {f}")
        for w in res.warnings:
            print(f"  warn  {w}")
        total += len(res.failures)

    print(f"\n{'=' * 74}")
    print("TOTAL: all checks passed" if not total else f"TOTAL: {total} failure(s)")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
