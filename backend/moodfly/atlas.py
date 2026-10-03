import hashlib
import json
import time
from dataclasses import asdict, dataclass

import numpy as np

from .brain import Brain
from .connectome import Connectome
from .paths import DATA
from .populations import sensory_groups

ATLAS_VERSION = 2


@dataclass(frozen=True)
class EmotionDef:
    key: str
    label: str
    color: str
    valence: float
    triggers: tuple


EMOTIONS = (
    EmotionDef("appetite", "Аппетит", "#3fae5a", +1.0, ((("sugar", 100),), (("water", 100),))),
    EmotionDef("disgust", "Отвращение", "#9085e9", -1.0, ((("bitter", 100),), (("odor_bad", 80),))),
    EmotionDef("fear", "Страх", "#e5484d", -1.0, ((("loom_left", 100), ("loom_right", 100)),)),
    EmotionDef("irritation", "Раздражение", "#c98500", -0.4, ((("wind", 100),), (("bristle", 80),))),
    EmotionDef("interest", "Интерес", "#3987e5", +0.5, ((("odor_good", 80),),)),
)

CALIBRATION_MS = 1000.0
MIN_RATE_HZ = 5.0
SPECIFICITY = 3.0


@dataclass
class Atlas:
    parts: dict[str, list[tuple[np.ndarray, np.ndarray]]]

    @property
    def signature(self) -> dict[str, np.ndarray]:
        return {k: np.unique(np.concatenate([idx for idx, _ in v])) for k, v in self.parts.items()}


def _cache_key(brain: Brain, variant: str) -> str:
    blob = json.dumps(
        {"v": ATLAS_VERSION, "params": asdict(brain.p), "emotions": [asdict(e) for e in EMOTIONS], "n": brain.conn.n, "variant": variant},
        sort_keys=True,
    )
    return hashlib.sha1(blob.encode()).hexdigest()[:12]


def _calibrate(conn: Connectome, brain: Brain) -> Atlas:
    groups = sensory_groups(conn)
    excluded = np.zeros(conn.n, bool)
    excluded[conn.where("super_class", ["sensory", "sensory_ascending"])] = True
    for g in groups.values():
        excluded[g.idx] = True

    responses: dict[str, list[np.ndarray]] = {}
    for emo in EMOTIONS:
        responses[emo.key] = []
        for trigger in emo.triggers:
            brain.reset()
            brain.drive_hz[:] = 0
            for group, hz in trigger:
                brain.drive_hz[groups[group].idx] = hz
            brain.drain()
            brain.run(CALIBRATION_MS)
            responses[emo.key].append(brain.drain() / (CALIBRATION_MS / 1000))
    brain.reset()
    brain.drive_hz[:] = 0

    best = {k: np.max(v, axis=0) for k, v in responses.items()}
    parts = {}
    for key, rates in responses.items():
        others = np.max([r for k, r in best.items() if k != key], axis=0)
        parts[key] = []
        for rate in rates:
            ok = (rate > MIN_RATE_HZ) & (rate > SPECIFICITY * others + 2.0) & ~excluded
            parts[key].append((np.flatnonzero(ok), rate[ok].astype(np.float32)))
    return Atlas(parts)


def load_or_calibrate(conn: Connectome, brain: Brain, variant: str = "") -> Atlas:
    path = DATA / f"atlas_{_cache_key(brain, variant)}.npz"
    if path.exists():
        z = np.load(path)
        return Atlas({e.key: [(z[f"{e.key}_{i}_idx"], z[f"{e.key}_{i}_ref"]) for i in range(len(e.triggers))] for e in EMOTIONS})
    t0 = time.time()
    print("Calibrating emotion atlas (one-time)...")
    atlas = _calibrate(conn, brain)
    arrays = {}
    for e in EMOTIONS:
        for i, (idx, ref) in enumerate(atlas.parts[e.key]):
            arrays[f"{e.key}_{i}_idx"] = idx
            arrays[f"{e.key}_{i}_ref"] = ref
        sizes = " + ".join(str(len(idx)) for idx, _ in atlas.parts[e.key])
        print(f"  {e.label:12s} {sizes} signature neurons")
    np.savez(path, **arrays)
    print(f"  done in {time.time() - t0:.0f} s -> {path.name}")
    return atlas
