"""Canonical solver for degenerate constraint systems (reference build)."""
import numpy as np


def solve(A, b):
    A = np.asarray(A, float)
    b = np.asarray(b, float)
    return np.linalg.pinv(A) @ b
