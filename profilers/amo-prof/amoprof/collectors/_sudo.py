"""Shared sudo wrappers used by privileged collectors.

Some collectors need root for nvme-cli SMART, bpftrace, perf, IPMI, AMDuProf
MSR reads, etc.  These wrappers use non-interactive sudo (`-n`) so AMOprof
never hangs waiting for a password prompt. When running as root, sudo is a
no-op.
"""
from __future__ import annotations

import os
import subprocess


def _sudo_cmd(cmd, use_sudo: bool = True, preserve_env: bool = False):
    if use_sudo and os.geteuid() != 0:
        return ["sudo", "-n"] + (["-E"] if preserve_env else []) + list(cmd)
    return list(cmd)


def _sudo_check_output(cmd, use_sudo: bool = True, preserve_env: bool = False, **kwargs):
    return subprocess.check_output(_sudo_cmd(cmd, use_sudo, preserve_env), **kwargs)


def _sudo_run(cmd, use_sudo: bool = True, preserve_env: bool = False, **kwargs):
    return subprocess.run(_sudo_cmd(cmd, use_sudo, preserve_env), **kwargs)


def _sudo_popen(cmd, use_sudo: bool = True, preserve_env: bool = False, **kwargs):
    return subprocess.Popen(_sudo_cmd(cmd, use_sudo, preserve_env), **kwargs)
