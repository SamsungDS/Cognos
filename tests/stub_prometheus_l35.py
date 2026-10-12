"""Stub Prometheus mimicking Mandar's L3.5 topology.

  msl-ssg-cx03.msl.lab:9101   amoprof service  -> amoprof_* only, NO node_disk_*
  msl-ssg-cx03.msl.lab:9100   node_exporter    -> node_disk_* for two names:
        nvme2n1     field 11 = 0      (namespace head)
        nvme2c2n1   field 11 = live   (controller path)
"""
import json, re, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

HOST = "msl-ssg-cx03.msl.lab"
AMO, NODE = f"{HOST}:9101", f"{HOST}:9100"

# metric -> list of (labels, value_fn)
SERIES = []
for dev, f11, f9 in (("nvme2n1", 0.0, 7.0), ("nvme2c2n1", 3.4, 7.0)):
    SERIES.append(("node_disk_io_time_weighted_seconds_total",
                   {"instance": NODE, "job": "node", "device": dev}, f11))
    SERIES.append(("node_disk_io_now",
                   {"instance": NODE, "job": "node", "device": dev}, f9))
    SERIES.append(("node_disk_read_bytes_total",
                   {"instance": NODE, "job": "node", "device": dev}, 1.2e9))
# an idle sibling device that would dilute an unscoped avg()
for dev in ("sda", "dm-0", "nvme0n1"):
    SERIES.append(("node_disk_io_time_weighted_seconds_total",
                   {"instance": NODE, "job": "node", "device": dev}, 0.0))
    SERIES.append(("node_disk_io_now",
                   {"instance": NODE, "job": "node", "device": dev}, 0.0))
# The device the operator is actually looking at in Grafana, under a name
# from a different namespace than the one they passed on the command line.
SERIES.append(("node_disk_io_time_weighted_seconds_total",
               {"instance": NODE, "job": "node", "device": "nvme6c6n1"}, 11.2))
SERIES.append(("node_disk_io_now",
               {"instance": NODE, "job": "node", "device": "nvme6c6n1"}, 64.0))
# the amoprof service: present, but publishes no node_disk_*
SERIES.append(("amoprof_iostat_read_bw_mb_mean",
               {"instance": AMO, "job": "amoprof"}, 410.0))
SERIES.append(("amoprof_nvme_driver_nvme_inflight_mean",
               {"instance": AMO, "job": "amoprof"}, 0.0))

# Prometheus validates a quoted label value as a STRING LITERAL before the
# regex engine sees it, with Go's escape rules -- in which `\.` is not an
# escape. Rejecting it here is what makes this stub able to catch the bug
# that shipped in v1.59.0:
#
#   400 bad_data: parse error: unknown escape sequence U+002E '.'
#
# Without this check the stub accepted a query a real Prometheus refuses.
_VALID_ESCAPES = set('abfnrtv\\\'"0123456789xuU')


def promql_string_error(expr):
    """The error a real Prometheus returns for a bad escape, or None."""
    i, n, in_str, quote = 0, len(expr), False, ""
    while i < n:
        c = expr[i]
        if not in_str:
            if c in "\"'":
                in_str, quote = True, c
            i += 1
            continue
        if c == quote:
            in_str = False
            i += 1
            continue
        if c == "\\":
            nxt = expr[i + 1] if i + 1 < n else ""
            if nxt not in _VALID_ESCAPES:
                return (f"invalid parameter \"query\": 1:{i + 1}: parse error: "
                        f"unknown escape sequence U+{ord(nxt):04X} {nxt!r}")
            i += 2
            continue
        i += 1
    return None


_SEL = re.compile(r"^(\w+)\{([^}]*)\}|^(\w+)")


def _parse_sel(body):
    out = {}
    for part in re.findall(r'(\w+)\s*(=~|=)\s*"([^"]*)"', body or ""):
        out[part[0]] = (part[1], part[2])
    return out


def _match(labels, sel):
    for k, (op, v) in sel.items():
        got = labels.get(k, "")
        if op == "=":
            if got != v:
                return False
        else:
            if not re.fullmatch(v, got):
                return False
    return True


def evaluate(expr, start, end, step):
    """Enough PromQL for the expressions under test."""
    m = re.search(r"([a-zA-Z_][a-zA-Z0-9_]*)\{([^}]*)\}", expr)
    if m:
        metric, body = m.group(1), m.group(2)
    else:
        m2 = re.search(r"\b(node_[a-z_]+|amoprof_[a-z0-9_]+)\b", expr)
        if not m2:
            return []
        metric, body = m2.group(1), ""
    sel = _parse_sel(body)
    hits = [(lb, v) for (nm, lb, v) in SERIES if nm == metric and _match(lb, sel)]
    if not hits:
        return []
    agg_all = expr.strip().startswith("avg(")
    ts = [start + i * step for i in range(int((end - start) // step) + 1)]
    if agg_all:
        mean = sum(v for _lb, v in hits) / len(hits)
        return [{"metric": {}, "values": [[t, f"{mean:.6f}"] for t in ts]}]
    return [{"metric": lb, "values": [[t, f"{v:.6f}"] for t in ts]}
            for lb, v in hits]


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path.endswith("/label/__name__/values"):
            payload = {"status": "success",
                       "data": sorted({nm for nm, _l, _v in SERIES})}
        elif u.path.endswith("/query_range"):
            expr = q.get("query", [""])[0]
            _err = promql_string_error(expr)
            if _err:
                b = json.dumps({"status": "error", "errorType": "bad_data",
                                "error": _err}).encode()
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)
                return
            start = float(q.get("start", ["0"])[0])
            end = float(q.get("end", ["600"])[0])
            step = float(q.get("step", ["60"])[0])
            payload = {"status": "success",
                       "data": {"resultType": "matrix",
                                "result": evaluate(expr, start, end, step)}}
        elif u.path.endswith("/series"):
            payload = {"status": "success",
                       "data": [dict(l, __name__=nm) for nm, l, _v in SERIES]}
        elif u.path.endswith("/targets"):
            payload = {"status": "success", "data": {"activeTargets": [
                {"labels": {"job": "node", "instance": NODE}, "health": "up"},
                {"labels": {"job": "amoprof", "instance": AMO}, "health": "up"},
            ]}}
        else:
            payload = {"status": "success", "data": []}
        b = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)


def serve():
    s = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return s, f"http://127.0.0.1:{s.server_port}"
