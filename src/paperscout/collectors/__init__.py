"""Candidate paper metadata collectors."""

from paperscout.collectors.manual import (
    ManualCandidate,
    dump_manual_candidates,
    load_manual_candidates,
)

__all__ = [
    "ManualCandidate",
    "dump_manual_candidates",
    "load_manual_candidates",
]
