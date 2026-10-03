import time

import numpy as np
import pandas as pd

from .connectome import CATEGORICAL
from .paths import BRAIN_NPZ, RAW


def _codes(series: pd.Series) -> tuple[np.ndarray, np.ndarray]:
    cat = series.astype("category")
    return cat.cat.codes.to_numpy(np.int32), np.asarray(cat.cat.categories, dtype=str)


def main() -> None:
    t0 = time.time()
    comp = pd.read_csv(RAW / "Completeness_783.csv", index_col=0)
    root_ids = comp.index.to_numpy(np.int64)
    n = len(root_ids)
    print(f"neurons: {n}")

    con = pd.read_parquet(
        RAW / "Connectivity_783.parquet",
        columns=["Presynaptic_Index", "Postsynaptic_Index", "Excitatory x Connectivity"],
    )
    pre = con["Presynaptic_Index"].to_numpy(np.int64)
    post = con["Postsynaptic_Index"].to_numpy(np.int32)
    w = con["Excitatory x Connectivity"].to_numpy(np.int16)
    del con
    order = np.argsort(pre, kind="stable")
    pre, post, w = pre[order], post[order], w[order]
    indptr = np.zeros(n + 1, dtype=np.int64)
    np.cumsum(np.bincount(pre, minlength=n), out=indptr[1:])
    print(f"connections: {len(post)}")

    ann = pd.read_csv(RAW / "neuron_annotations.tsv", sep="\t", low_memory=False)
    ann = ann.drop_duplicates("root_id").set_index("root_id").reindex(root_ids)
    print(f"annotated: {ann['super_class'].notna().sum()} / {n}")

    pos = ann[["pos_x", "pos_y", "pos_z"]].to_numpy(np.float64) * np.array([4, 4, 40]) / 1000
    centre = np.nanmedian(pos, axis=0)
    pos = np.nan_to_num(pos - centre, nan=0.0).astype(np.float32)

    arrays = {
        "root_ids": root_ids,
        "indptr": indptr,
        "indices": post,
        "syn": w,
        "pos": pos,
    }
    for col in CATEGORICAL:
        codes, names = _codes(ann[col])
        arrays[f"{col}_codes"] = codes
        arrays[f"{col}_names"] = names

    BRAIN_NPZ.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(BRAIN_NPZ, **arrays)
    print(f"wrote {BRAIN_NPZ} ({BRAIN_NPZ.stat().st_size / 1e6:.0f} MB) in {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
