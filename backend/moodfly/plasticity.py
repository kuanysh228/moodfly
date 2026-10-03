import numpy as np

from .connectome import Connectome

TAU_ELIG_S = 2.0
TAU_BASELINE_S = 60.0
ELIG_THRESHOLD = 8.0
KC_RATE_THRESHOLD = 10.0
ETA = 3e-4
KAPPA = 0.002
DAN_GATE_HZ = 40.0
RATIO_MIN = 0.05
TAU_FORGET_S = 3600.0


class MushroomBody:
    def __init__(self, conn: Connectome, weights: np.ndarray, eta_gain: float = 1.0):
        self.weights = weights
        self.eta = ETA * eta_gain
        kc = conn.where("cell_class", ["Kenyon_Cell"])
        mbon = conn.where("cell_class", ["MBON"])
        dan = conn.where("cell_class", ["DAN"])
        self.kc, self.mbon, self.dan = kc, mbon, dan
        pre = np.repeat(np.arange(conn.n), np.diff(conn.indptr))

        def local(idx):
            m = np.full(conn.n, -1, np.int64)
            m[idx] = np.arange(len(idx))
            return m

        kc_l, mbon_l, dan_l = local(kc), local(mbon), local(dan)
        self.edges = np.flatnonzero((kc_l[pre] >= 0) & (mbon_l[conn.indices] >= 0))
        self.kc_of = kc_l[pre[self.edges]]
        self.mbon_of = mbon_l[conn.indices[self.edges]]
        self.w0 = weights[self.edges].copy()
        self.ratio = np.ones(len(self.edges), np.float32)

        dm = np.flatnonzero((dan_l[pre] >= 0) & (mbon_l[conn.indices] >= 0))
        a = np.zeros((len(mbon), len(dan)), np.float32)
        np.add.at(a, (mbon_l[conn.indices[dm]], dan_l[pre[dm]]), np.abs(conn.syn[dm]).astype(np.float32))
        self.dan_to_mbon = a / np.maximum(a.sum(axis=1, keepdims=True), 1.0)
        is_ppl1 = np.char.startswith(conn.label("cell_type")[dan].astype(str), "PPL1")
        ppl1_share = self.dan_to_mbon[:, is_ppl1].sum(axis=1)
        nt = conn.label("top_nt")[mbon]
        self.valence = np.where(nt == "glutamate", -1.0, np.where((nt == "acetylcholine") & (ppl1_share > 0.5), 1.0, 0.0)).astype(np.float32)
        self.elig = np.zeros(len(kc), np.float32)
        self.baseline = np.zeros(len(kc), np.float32)
        self.age = 0.0

    def update(self, counts: np.ndarray, rate_hz: np.ndarray, dt: float, cue: bool = False) -> None:
        self.age += dt
        kc_counts = counts[self.kc]
        if not cue:
            self.baseline += (kc_counts / dt - self.baseline) * np.float32(dt / min(TAU_BASELINE_S, 2.0 + self.age))
        self.elig *= np.float32(np.exp(-dt / TAU_ELIG_S))
        self.elig += kc_counts
        drive = self.dan_to_mbon @ rate_hz[self.dan]
        e = np.maximum(self.elig - self.baseline * TAU_ELIG_S - ELIG_THRESHOLD, 0.0)
        if e.max() > 0:
            ek, d = e[self.kc_of], drive[self.mbon_of]
            taught = d > DAN_GATE_HZ
            if taught.any():
                self.ratio[taught] *= np.exp(-self.eta * ek[taught] * d[taught] * dt).astype(np.float32)
            if cue:
                rest = ~taught
                self.ratio[rest] += (1.0 - self.ratio[rest]) * np.minimum(1.0, KAPPA * ek[rest] * dt).astype(np.float32)
        self.ratio += (1.0 - self.ratio) * np.float32(dt / TAU_FORGET_S)
        np.maximum(self.ratio, RATIO_MIN, out=self.ratio)
        self.weights[self.edges] = self.w0 * self.ratio

    def learned_value(self, rate_hz: np.ndarray) -> float:
        r = np.maximum(rate_hz[self.kc] - self.baseline - KC_RATE_THRESHOLD, 0.0)
        if r.sum() < 50:
            return 0.0
        drive = r[self.kc_of] * self.w0
        change = np.bincount(self.mbon_of, weights=drive * (self.ratio - 1.0), minlength=len(self.mbon))
        total = np.bincount(self.mbon_of, weights=drive, minlength=len(self.mbon))
        return float((self.valence * change).sum() / max(1e-6, (np.abs(self.valence) * total).sum()))

    def memory(self) -> bytes:
        return self.ratio.astype(np.float16).tobytes()

    def load_memory(self, blob: bytes | None) -> None:
        if blob:
            ratio = np.frombuffer(blob, np.float16).astype(np.float32)
            if len(ratio) == len(self.ratio):
                self.ratio[:] = ratio
                self.weights[self.edges] = self.w0 * self.ratio

    @property
    def strength(self) -> float:
        return float(1.0 - self.ratio.mean())
