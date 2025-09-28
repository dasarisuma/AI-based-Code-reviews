"""Central severity utilities shared by CLI, agents, and workflows."""
from __future__ import annotations
from typing import Iterable

SEVERITY_ORDER = ["critical", "error", "high", "warning", "medium", "low", "info"]

# Weight: lower is more severe
_SEVERITY_WEIGHTS = {s: i for i, s in enumerate(SEVERITY_ORDER)}

BLOCK_DEFAULT = {"critical", "error"}


def weight(severity: str) -> int:
    return _SEVERITY_WEIGHTS.get(severity.lower(), 999)


def most_severe(severities: Iterable[str]) -> str:
    try:
        return min((s.lower() for s in severities), key=weight)
    except ValueError:
        return "info"


def status_from_comments(severities: Iterable[str]) -> str:
    sev_list = [s.lower() for s in severities]
    if any(s in ("critical", "error") for s in sev_list):
        return "Reject"
    if any(s in ("high", "warning") for s in sev_list) or sev_list.count("medium") > 2:
        return "Needs Changes"
    return "Approve"
