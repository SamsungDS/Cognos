"""Credentials and the Prometheus address never reach a report or run dir.

A report showed the SGLang launch command with --admin-api-key in full, five
times, plus the internal Prometheus URL.
"""
import json
import pathlib
import sys

from amoprof import cli
from amoprof.redact import REDACTED, PROM_REDACTED, redact_obj, redact_text, scrub_html

KEY = "sk-sg-lc-bg-bs-api-key"
LAUNCH = (f"python3 -m sglang.launch_server --model-path google/gemma-4-31b-it "
          f"--admin-api-key {KEY} --max-total-tokens 196153 --tokenizer-path tok "
          f"--hf-token=hf_secretvalue --enable-hierarchical-cache")
PROM = "http://105.128.44.21:9090"


def test_launch_command_secrets_are_redacted_and_nothing_else():
    out = redact_text(LAUNCH)
    assert KEY not in out and "hf_secretvalue" not in out
    assert f"--admin-api-key {REDACTED}" in out and f"--hf-token={REDACTED}" in out
    # Look-alike names are configuration, not credentials.
    assert "--max-total-tokens 196153" in out and "--tokenizer-path tok" in out
    assert redact_text("HF_TOKEN=abcdef123 MAX_TOKENS=5 run") == f"HF_TOKEN={REDACTED} MAX_TOKENS=5 run"


def test_server_info_dict_keeps_its_shape():
    si = {"admin_api_key": KEY, "api_key": None, "tokenizer_path": "google/x",
          "max_total_num_tokens": 196153, "nested": {"hf_token": "abcdef1234"}}
    assert redact_obj(si) == {"admin_api_key": REDACTED, "api_key": None,
                              "tokenizer_path": "google/x", "max_total_num_tokens": 196153,
                              "nested": {"hf_token": REDACTED}}


def test_scrubbing_a_page_keeps_its_markup():
    html = f"<td>--admin-api-key mysecret</td><td class=\"x\">ok</td>"
    assert scrub_html(html) == f"<td>--admin-api-key {REDACTED}</td><td class=\"x\">ok</td>"


def _raw_with_secrets(base):
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    from test_l35_report_consistency import _mk
    raw = _mk(base)
    sd = json.loads((raw / "setup_details.json").read_text())
    sd.update({"SGLang launch command": LAUNCH,
               "SGLang server_info raw": {"admin_api_key": KEY, "api_key": None},
               "Prometheus URL": PROM})
    (raw / "setup_details.json").write_text(json.dumps(sd))
    (raw / "sglang_summary.json").write_text(json.dumps({"prometheus_source": PROM}))
    return raw


def test_raw_secrets_are_scrubbed_in_every_escape_form(tmp_path):
    raw = _raw_with_secrets(tmp_path / "r")
    page = (f"<pre>{LAUNCH}</pre><td>{{'admin_api_key': '{KEY}'}}</td>"
            f"<iframe srcdoc=\"&lt;td&gt;&amp;#x27;{KEY}&amp;#x27;&lt;/td&gt;\"></iframe>"
            f"<b>Source</b>: {PROM}/")
    out = scrub_html(page, raw)
    assert KEY not in out and "105.128.44.21" not in out
    assert out.count(REDACTED) >= 3 and PROM_REDACTED in out


def test_interactive_report_has_no_secret(tmp_path):
    from amoprof.report.interactive import build_report
    raw = _raw_with_secrets(tmp_path / "r")
    out = build_report(raw, tmp_path / "report.html", run_label="t")
    html = pathlib.Path(out).read_text(encoding="utf-8")
    assert KEY not in html and "hf_secretvalue" not in html and "105.128.44.21" not in html


def test_setup_details_copy_is_redacted_on_disk(tmp_path):
    src = tmp_path / "setup.json"
    src.write_text(json.dumps({"SGLang launch command": LAUNCH,
                               "SGLang server_info raw": {"admin_api_key": KEY}}))
    raw = tmp_path / "raw"
    raw.mkdir()

    class A:
        setup_details = str(src)
        setup_details_override = False
        benchmark = ""
    cli._copy_setup_details(A, raw)
    text = (raw / "setup_details.json").read_text()
    assert KEY not in text and "hf_secretvalue" not in text
    assert "--max-total-tokens 196153" in text


def test_enhanced_end_report_has_no_prometheus_address(tmp_path):
    # The enhancer rewrites the static End Report and adds a setup panel with
    # a "Prometheus URL" row after the report builder has run.
    from amoprof.report.enhancer import enhance_report
    raw = _raw_with_secrets(tmp_path / "r")
    page = tmp_path / "end.html"
    page.write_text(f"<html><head></head><body><td>Prometheus URL</td><td>{PROM}</td>"
                    f"<pre>{LAUNCH}</pre></body></html>", encoding="utf-8")
    enhance_report(page, raw_dir=raw, theme="dark")
    html = page.read_text(encoding="utf-8")
    assert "105.128.44.21" not in html and KEY not in html
