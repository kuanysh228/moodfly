import re
from dataclasses import dataclass
from functools import cached_property

import numpy as np

from .paths import BRAIN_NPZ

CATEGORICAL = ["super_class", "cell_class", "cell_sub_class", "cell_type", "side", "top_nt", "known_nt"]

NT_SIGN = {
    "acetylcholine": 1, "histamine": 1, "dopamine": 1, "serotonin": 1, "octopamine": 1, "tyramine": 1,
    "gaba": -1, "glutamate": -1,
}


def _parse_known_nt(text: str) -> int:
    for token in re.split(r"[;,]", text):
        token = token.strip()
        if token in NT_SIGN:
            return NT_SIGN[token]
    return 0


@dataclass
class Connectome:
    root_ids: np.ndarray
    indptr: np.ndarray
    indices: np.ndarray
    syn: np.ndarray
    pos: np.ndarray
    codes: dict[str, np.ndarray]
    names: dict[str, np.ndarray]

    @property
    def n(self) -> int:
        return len(self.root_ids)

    def label(self, col: str) -> np.ndarray:
        names = np.append(self.names[col], "")
        return names[self.codes[col]]

    def where(self, col: str, values) -> np.ndarray:
        wanted = np.flatnonzero(np.isin(self.names[col], list(values)))
        return np.flatnonzero(np.isin(self.codes[col], wanted))

    def where_prefix(self, col: str, prefixes) -> np.ndarray:
        wanted = [i for i, s in enumerate(self.names[col]) if s.startswith(tuple(prefixes))]
        return np.flatnonzero(np.isin(self.codes[col], wanted))

    def by_root_id(self, ids) -> np.ndarray:
        idx = np.searchsorted(self.root_ids, ids)
        idx = np.clip(idx, 0, self.n - 1)
        return idx[self.root_ids[idx] == np.asarray(ids)]

    def signed_synapses(self, policy: str = "annotated") -> np.ndarray:
        if policy == "shiu":
            return self.syn
        sign = np.zeros(self.n, np.int8)
        sign[np.repeat(np.arange(self.n), np.diff(self.indptr))] = np.sign(self.syn)
        top = np.array([NT_SIGN.get(s, 0) for s in self.names["top_nt"]] + [0], np.int8)[self.codes["top_nt"]]
        known = np.array([_parse_known_nt(s) for s in self.names["known_nt"]] + [0], np.int8)[self.codes["known_nt"]]
        sign = np.where(top != 0, top, sign)
        sign = np.where(known != 0, known, sign)
        sign[self.where("cell_class", ["ALLN"])] = -1
        pre_sign = np.repeat(sign, np.diff(self.indptr))
        return (np.abs(self.syn) * pre_sign).astype(np.int16)

    def subset(self, keep: np.ndarray) -> "Connectome":
        new_idx = np.full(self.n, -1, np.int64)
        new_idx[keep] = np.arange(int(keep.sum()))
        pre = np.repeat(np.arange(self.n), np.diff(self.indptr))
        edge = keep[pre] & keep[self.indices]
        pre_new = new_idx[pre[edge]]
        indptr = np.zeros(int(keep.sum()) + 1, np.int64)
        np.cumsum(np.bincount(pre_new, minlength=len(indptr) - 1), out=indptr[1:])
        return Connectome(
            root_ids=self.root_ids[keep],
            indptr=indptr,
            indices=new_idx[self.indices[edge]].astype(np.int32),
            syn=self.syn[edge],
            pos=self.pos[keep],
            codes={c: v[keep] for c, v in self.codes.items()},
            names=self.names,
        )

    @cached_property
    def cell_type_counts(self) -> list[tuple[str, int]]:
        counts = np.bincount(self.codes["cell_type"][self.codes["cell_type"] >= 0], minlength=len(self.names["cell_type"]))
        return sorted(((str(t), int(c)) for t, c in zip(self.names["cell_type"], counts) if c), key=lambda x: x[0])


def load(path=BRAIN_NPZ) -> Connectome:
    if not path.exists():
        raise SystemExit(
            f"{path} not found. Run `python scripts/fetch_data.py` then `uv run moodfly-build` first."
        )
    z = np.load(path)
    if np.any(np.diff(z["root_ids"]) <= 0):
        raise ValueError("root_ids must be sorted (Completeness_783.csv order)")
    return Connectome(
        root_ids=z["root_ids"],
        indptr=z["indptr"],
        indices=z["indices"],
        syn=z["syn"],
        pos=z["pos"],
        codes={c: z[f"{c}_codes"] for c in CATEGORICAL},
        names={c: z[f"{c}_names"] for c in CATEGORICAL},
    )
