import re
from pathlib import Path


def _code_lines(path):
    """(line number, text) for every line that is not a comment."""
    for i, line in enumerate(path.read_text().splitlines(), 1):
        if not line.lstrip().startswith("#"):
            yield i, line


def test_ssd_bw_pct_initializer_before_first_use():
    # The Executive findings read these before the evidence block that once
    # defined them, which raised a NameError.  Each must be assigned before
    # any code reads it.
    p = Path(__file__).resolve().parents[1] / "amoprof" / "report" / "combined.py"
    lines = list(_code_lines(p))
    for name, init in (("_ssd_bw_target_mbs", "_ssd_bw_target_mbs = 7000.0"),
                       ("_ssd_bw_pct", "_ssd_bw_pct = (")):
        uses = [i for i, l in lines if re.search(rf"\b{name}\b", l)]
        assigned = [i for i, l in lines if l.strip().startswith(init)]
        assert assigned, f"{name} is never initialised"
        assert uses and uses[0] == assigned[0], (
            f"{name} first appears on line {uses[0]} before its assignment on line {assigned[0]}")
