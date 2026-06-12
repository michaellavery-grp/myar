"""Dice rolling helpers."""

import random
import re

_DICE_RE = re.compile(r"^(\d+)d(\d+)([+-]\d+)?$")


def roll(spec):
    """Roll dice given a spec like '2d6' or '1d8+2'."""
    m = _DICE_RE.match(spec)
    if not m:
        raise ValueError(f"bad dice spec: {spec}")
    n, d = int(m.group(1)), int(m.group(2))
    mod = int(m.group(3) or 0)
    return sum(random.randint(1, d) for _ in range(n)) + mod


def chance(p):
    """Return True with probability p (0..1)."""
    return random.random() < p
