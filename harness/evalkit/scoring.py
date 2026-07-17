"""Execution-based scoring: mechanical first, judge never required for E0.

- scalar: relative tolerance (absolute near zero).
- table: order-normalized row comparison, numeric cells with tolerance.
- facts: every expected fact must appear in the answer — string facts by
  case-insensitive containment (structured or text answers), numeric facts by
  any number in the answer matching within tolerance.

A question scores 1.0 or 0.0. Partial credit hides failures; the design wants
failures loud, typed, and turned into limitation events.
"""

from __future__ import annotations

import re

SCALAR_REL_TOL = 1e-6
FACT_REL_TOL = 0.02
_NUM = re.compile(r"-?\d[\d,]*\.?\d*")


def _close(a: float, b: float, rel: float) -> bool:
    if a == b:
        return True
    scale = max(abs(a), abs(b))
    if scale < 1e-9:
        return True
    return abs(a - b) / scale <= rel


def _numbers_in(text: str) -> list[float]:
    out = []
    for tok in _NUM.findall(text):
        try:
            out.append(float(tok.replace(",", "")))
        except ValueError:
            pass
    return out


def score_scalar(expected: float, got, rel: float = SCALAR_REL_TOL) -> bool:
    if got is None:
        return False
    try:
        return _close(float(expected), float(got), rel)
    except (TypeError, ValueError):
        return False


def score_table(expected: list, got, rel: float = SCALAR_REL_TOL) -> bool:
    if not isinstance(got, list) or len(got) != len(expected):
        return False

    def norm(rows):
        normed = []
        for row in rows:
            cells = []
            for c in row:
                if isinstance(c, (int, float)) and not isinstance(c, bool):
                    cells.append(("n", float(c)))
                else:
                    cells.append(("s", str(c).strip().lower()))
            normed.append(tuple(cells))
        return sorted(normed)

    for erow, grow in zip(norm(expected), norm(got)):
        if len(erow) != len(grow):
            return False
        for (ek, ev), (gk, gv) in zip(erow, grow):
            if ek != gk:
                return False
            if ek == "n" and not _close(ev, gv, rel):
                return False
            if ek == "s" and ev != gv:
                return False
    return True


def score_facts(expected: dict, got, rel: float = FACT_REL_TOL) -> bool:
    """`got` may be a dict of facts or free text containing them."""
    if got is None:
        return False
    if isinstance(got, dict):
        for k, v in expected.items():
            if k not in got:
                return False
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                if not score_scalar(v, got[k], rel):
                    return False
            elif str(got[k]).strip().lower() != str(v).strip().lower():
                return False
        return True
    text = str(got)
    nums = _numbers_in(text)
    low = text.lower()
    for v in expected.values():
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            if not any(_close(float(v), n, rel) for n in nums):
                return False
        elif str(v).strip().lower() not in low:
            return False
    return True


def score(question, answer) -> bool:
    """Score an AgentAnswer (or raw value) against a Question."""
    got = getattr(answer, "value", answer)
    if getattr(answer, "answer_type", None) == "no_answer":
        return False
    if question.answer_type == "scalar":
        return score_scalar(question.expected, got)
    if question.answer_type == "table":
        return score_table(question.expected, got)
    if question.answer_type == "facts":
        return score_facts(question.expected, got)
    raise ValueError(f"unknown answer_type {question.answer_type!r}")
