"""Shared production policy constants and upload policy gate enforcement."""

from __future__ import annotations

from typing import TYPE_CHECKING

WORD_BANDS = {"short": (105, 155), "long": (1100, 1500)}

if TYPE_CHECKING:
    from tools.policy_gate import PolicyGateReport


def evaluate_policy_gate(project_data: dict, **kwargs) -> PolicyGateReport:
    """Evaluates project data against the mandatory upload policy gate."""
    from tools.policy_gate import evaluate_policy_gate as _eval_gate
    return _eval_gate(project_data, **kwargs)

