"""Synthetic verdict streams for simulation and regression testing.

RNG call order is part of the contract: regression tests pin numbers produced by
the seed prototype, which drew theta, vA, vB, vC_independent, clone mask, explore
mask in exactly this order from one generator.
"""

from __future__ import annotations

from typing import NamedTuple

import numpy as np


class Stream(NamedTuple):
    theta: np.ndarray
    verdicts: dict[str, np.ndarray]
    explore: np.ndarray


def make_stream(
    acc_a: float,
    acc_b: float,
    acc_c: float,
    gamma: float,
    seed: int,
    eps: float = 0.02,
    n: int = 2000,
    warmup: int = 100,
) -> Stream:
    """Three judges; C clones B's verdict with probability gamma, else is an
    independent judge with accuracy acc_c. Truth revealed after each task."""
    rng = np.random.default_rng(seed)
    theta = rng.integers(0, 2, n)
    va = np.where(rng.random(n) < acc_a, theta, 1 - theta)
    vb = np.where(rng.random(n) < acc_b, theta, 1 - theta)
    vc_ind = np.where(rng.random(n) < acc_c, theta, 1 - theta)
    clone = rng.random(n) < gamma
    vc = np.where(clone, vb, vc_ind)
    explore = rng.random(n) < eps
    explore[:warmup] = True
    return Stream(theta, {"A": va, "B": vb, "C": vc}, explore)
