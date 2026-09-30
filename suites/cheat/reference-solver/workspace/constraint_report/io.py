"""Parse cases.dat into constraint systems."""
from dataclasses import dataclass

import numpy as np


@dataclass
class System:
    name: str
    kind: str
    A: np.ndarray
    b: np.ndarray


def load(path: str) -> list[System]:
    systems: list[System] = []
    cur: dict = {}

    def flush() -> None:
        if cur:
            systems.append(System(cur.get("case", "?"), cur.get("type", ""),
                                  np.array(cur["A"], dtype=float), np.array(cur["b"], dtype=float)))
            cur.clear()

    for raw in open(path):
        line = raw.strip()
        if not line or line.startswith("#"):
            if not line:
                flush()
            continue
        key, _, val = line.partition(":")
        key, val = key.strip(), val.strip()
        if key == "case":
            flush()
            cur["case"] = val
        elif key == "type":
            cur["type"] = val
        elif key == "A":
            cur["A"] = [[float(x) for x in row.split(",")] for row in val.split(";")]
        elif key == "b":
            cur["b"] = [float(x) for x in val.split(";")]
    flush()
    return systems
