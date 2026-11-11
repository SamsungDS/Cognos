"""Stub Prometheus with three hosts publishing the same exporters.

  host-dgx1   sglang :30000, node_exporter :9100, amoprof service :9101
  host-dgx3   node_exporter :9100, amoprof service :9101   (another GPU node)
  host-cx03   node_exporter :9100, amoprof service :9101   (the memory node)

Only dgx1 serves SGLang.  Every host's amoprof service publishes the same
gauge names with different values, and every node_exporter publishes
node_disk_* for its own devices -- the shape in which an unpinned fetch
averaged three machines, or took whichever host's sample came first.

Counters are linear in time (value = base + slope * t), so a rate is the
slope; gauges are constant.
"""
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

DGX1, DGX3, CX03 = "host-dgx1.example.com", "host-dgx3.example.com", "host-cx03.example.com"
MIB = 1048576.0

# (metric, labels, base, slope) -- slope 0 for gauges
SERIES = [("sglang:num_running_reqs",
           {"instance": f"{DGX1}:30000", "job": "sglang"}, 5.0, 0.0)]
for host, iops, bw in ((DGX1, 1000.0, 300.0), (DGX3, 5000.0, 50.0), (CX03, 24000.0, 900.0)):
    amo = {"instance": f"{host}:9101", "job": "amoprof"}
    SERIES += [("amoprof_nvme_driver_nvme_rd_iops_sysfs", amo, iops, 0.0),
               ("amoprof_nvme_driver_nvme_wr_iops_sysfs", amo, iops / 2, 0.0),
               ("amoprof_nvme_driver_nvme_rd_bw_mbs_sysfs", amo, bw, 0.0),
               ("amoprof_nvme_driver_nvme_wr_bw_mbs_sysfs", amo, bw / 2, 0.0)]
# node_disk_*: dgx1's HiCache device nvme6n1 is the busy one; its OS disk
# nvme0n1 has a far larger lifetime byte count but is nearly idle in the
# window, so "highest cumulative value" picked the wrong device for bytes.
for host, dev, ops_s, bytes_s, bytes_base in (
        (DGX1, "nvme6n1", 1000.0, 300 * MIB, 1e12),
        (DGX1, "nvme0n1", 2.0, 1 * MIB, 9e15),
        (DGX3, "nvme1n1", 5000.0, 50 * MIB, 5e12),
        (CX03, "nvme2n1", 24000.0, 900 * MIB, 7e12)):
    nd = {"instance": f"{host}:9100", "job": "node", "device": dev}
    SERIES += [("node_disk_reads_completed_total", nd, 1e6, ops_s),
               ("node_disk_writes_completed_total", nd, 1e6, ops_s / 2),
               ("node_disk_read_bytes_total", nd, bytes_base, bytes_s),
               ("node_disk_written_bytes_total", nd, bytes_base, bytes_s / 2)]


def _parse_sel(body):
    return {k: (op, v) for k, op, v in
            re.findall(r'(\w+)\s*(=~|!=|=)\s*"([^"]*)"', body or "")}


def _match(name, labels, sel):
    for k, (op, v) in sel.items():
        got = name if k == "__name__" else labels.get(k, "")
        if op == "=" and got != v:
            return False
        if op == "!=" and got == v:
            return False
        if op == "=~" and not re.fullmatch(v, got):
            return False
    return True


def _select(expr):
    """Series matched by the first selector in `expr`."""
    m = re.search(r'([a-zA-Z_:][a-zA-Z0-9_:]*)?\{([^}]*)\}', expr)
    if m:
        name, sel = m.group(1), _parse_sel(m.group(2))
        if name:
            sel["__name__"] = ("=", name)
    else:
        m2 = re.search(r'\b((?:node|amoprof|sglang)[a-zA-Z0-9_:]*)\b', expr)
        if not m2:
            return []
        sel = {"__name__": ("=", m2.group(1))}
    return [(nm, lb, b, s) for nm, lb, b, s in SERIES if _match(nm, lb, sel)]


def evaluate(expr, start, end, step):
    hits = _select(expr)
    if not hits:
        return []
    is_rate = bool(re.search(r"\b(rate|irate|increase)\(", expr))
    ts = [start + i * step for i in range(int((end - start) // step) + 1)]

    def val(b, s, t):
        return s if is_rate else b + s * (t - start)

    if expr.strip().startswith(("avg(", "sum(", "max(")):
        agg = expr.strip()[:3]
        out = []
        for t in ts:
            vs = [val(b, s, t) for _n, _l, b, s in hits]
            out.append([t, f"{(sum(vs) / len(vs) if agg == 'avg' else sum(vs) if agg == 'sum' else max(vs)):.6f}"])
        return [{"metric": {}, "values": out}]
    return [{"metric": dict(lb, __name__=nm),
             "values": [[t, f"{val(b, s, t):.6f}"] for t in ts]}
            for nm, lb, b, s in hits]


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, payload, code=200):
        b = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path.endswith("/label/__name__/values"):
            return self._send({"status": "success",
                               "data": sorted({nm for nm, *_ in SERIES})})
        if u.path.endswith("/query_range"):
            return self._send({"status": "success", "data": {
                "resultType": "matrix",
                "result": evaluate(q.get("query", [""])[0],
                                   float(q.get("start", ["0"])[0]),
                                   float(q.get("end", ["600"])[0]),
                                   float(q.get("step", ["60"])[0]))}})
        if u.path.endswith("/series"):
            out = []
            for m in q.get("match[]", []):
                out += [dict(lb, __name__=nm) for nm, lb, _b, _s in _select(m)]
            return self._send({"status": "success", "data": out})
        if u.path.endswith("/targets"):
            tg = sorted({(lb["job"], lb["instance"]) for _n, lb, _b, _s in SERIES})
            return self._send({"status": "success", "data": {"activeTargets": [
                {"labels": {"job": j, "instance": i}, "health": "up"} for j, i in tg]}})
        return self._send({"status": "success", "data": []})


def serve():
    s = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return s, f"http://127.0.0.1:{s.server_port}"
