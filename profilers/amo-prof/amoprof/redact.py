"""Keep credentials and internal endpoints out of run directories and reports.

SGLang's server_info carries the server's launch arguments, including
--admin-api-key, and the report rendered them verbatim in the launch command
and the server_info table -- five times per report -- next to the internal
Prometheus address.  Secrets are redacted where they enter (the server_info
fetch and the setup details copy), and every written report is scrubbed of
any secret value or Prometheus URL its run directory still holds, so a run
recorded before this change is covered too.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

REDACTED = "[redacted]"
PROM_REDACTED = "[Prometheus URL redacted]"

# Names whose value is a credential -- admin_api_key, --hf-token, HF_TOKEN --
# matched on whole name segments, so --max-total-tokens, tokenizer_path and
# MAX_TOKENS are left alone.
_SECRET_SEGMENTS = {"token", "secret", "password", "passwd", "credential",
                    "credentials", "apikey"}


def _is_secret_name(name: Any) -> bool:
    segs = [s for s in re.split(r"[^a-z0-9]+", str(name).lower()) if s]
    return (any(s in _SECRET_SEGMENTS for s in segs)
            or any(a == "api" and b == "key" for a, b in zip(segs, segs[1:]))
            or any(a == "auth" and b == "key" for a, b in zip(segs, segs[1:])))


# --admin-api-key VALUE / --hf-token=VALUE on a command line.  The value
# stops at markup (< > &), so a key at the end of a table cell does not take
# the closing tags with it when a whole report page is scrubbed.
_FLAG_ANY_RE = re.compile(r"(--[A-Za-z0-9][A-Za-z0-9-]*)(\s+|=)"
                          r"(\"[^\"<>]*\"|'[^'<>]*'|[^\s\"'<>&-][^\s\"'<>&]*)")
# HF_TOKEN=VALUE in an environment prefix.
_ENV_ANY_RE = re.compile(r"\b([A-Z][A-Z0-9_]*)=([^\s\"'<>&]+)")
# Self-identifying token formats, caught wherever they appear.
_TOKEN_RE = re.compile(r"(?<![\w-])(?:sk-[A-Za-z0-9_-]{8,}|hf_[A-Za-z0-9]{20,}"
                       r"|gh[pousr]_[A-Za-z0-9]{20,}|glpat-[A-Za-z0-9_-]{16,})")
# Keys naming the Prometheus endpoint in summaries and setup details.
_PROM_KEYS = ("prometheus_source", "prometheus_url", "Prometheus URL",
              "prometheus_base_url", "prom_url")


def _is_secret_key(key: Any) -> bool:
    return _is_secret_name(key)


def _flag_secrets(s: str):
    for m in _FLAG_ANY_RE.finditer(s):
        if _is_secret_name(m.group(1)):
            yield m
    for m in _ENV_ANY_RE.finditer(s):
        if _is_secret_name(m.group(1)):
            yield m


def _secret_value(v: Any) -> bool:
    return isinstance(v, str) and v.strip() not in ("", "None", "null")


def secrets_in(obj: Any) -> set:
    """Every credential value found in a JSON-like object or string."""
    found: set = set()

    def walk(o, key=None):
        if isinstance(o, dict):
            for k, v in o.items():
                walk(v, k)
        elif isinstance(o, (list, tuple)):
            for v in o:
                walk(v, key)
        elif isinstance(o, str):
            if key is not None and _is_secret_key(key) and _secret_value(o):
                found.add(o.strip())
            for m in _flag_secrets(o):
                found.add(m.group(m.lastindex).strip("\"'"))
            found.update(_TOKEN_RE.findall(o))

    walk(obj)
    # Too short to replace without hitting ordinary text.
    return {s for s in found if len(s) >= 6 and s != REDACTED}


def redact_text(s: str) -> str:
    s = _FLAG_ANY_RE.sub(lambda m: (f"{m.group(1)}{m.group(2)}{REDACTED}"
                                    if _is_secret_name(m.group(1)) else m.group(0)), s)
    s = _ENV_ANY_RE.sub(lambda m: (f"{m.group(1)}={REDACTED}"
                                   if _is_secret_name(m.group(1)) else m.group(0)), s)
    return _TOKEN_RE.sub(REDACTED, s)


def redact_obj(obj: Any) -> Any:
    """A copy with credential values replaced; structure and other values kept."""
    if isinstance(obj, dict):
        return {k: (REDACTED if _is_secret_key(k) and _secret_value(v) else redact_obj(v))
                for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact_obj(v) for v in obj]
    if isinstance(obj, str):
        return redact_text(obj)
    return obj


def _read_json(p: Path) -> Any:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def scrub_terms(raw_dir: "Path | str | None") -> dict:
    """{literal: replacement} for every secret and Prometheus URL in raw_dir."""
    terms: dict = {}
    if not raw_dir:
        return terms
    rd = Path(raw_dir)
    docs = [_read_json(rd / f) for f in ("setup_details.json", "server_info.json",
                                         "sglang_summary.json")]
    for d in docs:
        for s in secrets_in(d):
            terms[s] = REDACTED
        if isinstance(d, dict):
            for k in _PROM_KEYS:
                v = str(d.get(k) or "").strip().rstrip("/")
                if re.match(r"https?://", v):
                    terms[v] = PROM_REDACTED
    return terms


def scrub_html(html: str, raw_dir: "Path | str | None" = None,
               extra: "dict | None" = None) -> str:
    """Remove every known secret / Prometheus URL, then any secret-shaped text."""
    terms = dict(scrub_terms(raw_dir))
    terms.update(extra or {})
    # Longest first, so a URL is replaced whole before any part of it.
    for lit in sorted(terms, key=len, reverse=True):
        html = html.replace(lit, terms[lit])
    return redact_text(html)


def scrub_file(path: "Path | str", raw_dir: "Path | str | None" = None) -> None:
    p = Path(path)
    try:
        txt = p.read_text(encoding="utf-8")
    except Exception:
        return
    new = scrub_html(txt, raw_dir)
    if new != txt:
        p.write_text(new, encoding="utf-8")
