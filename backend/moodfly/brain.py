from dataclasses import dataclass

import numba as nb
import numpy as np

from .connectome import Connectome


@dataclass(frozen=True)
class LIFParams:
    dt_ms: float = 1.0
    v0: float = -52.0
    v_reset: float = -52.0
    v_th: float = -45.0
    tau_m: float = 20.0
    tau_syn: float = 5.0
    t_ref: float = 2.2
    t_delay: float = 1.8
    w_syn: float = 0.275
    poisson_scale: float = 250.0
    adapt_mv: float = 0.2
    tau_adapt_ms: float = 1000.0


@nb.njit(cache=True, fastmath=True, nogil=True)
def _seed(seed):
    np.random.seed(seed)


N_CHUNKS = 16


@nb.njit(cache=True, fastmath=True, nogil=True, parallel=True)
def _run(
    n_steps, t0, v, g, a, ref, buf, indptr, indices, weights, p_drive, silenced, counts,
    a_vv, a_vg, a_gg, a_aa, v0, v_reset, v_th, d_adapt, kick, ref_steps, delay,
):
    n = v.shape[0]
    ring = buf.shape[0]
    chunk = (n + N_CHUNKS - 1) // N_CHUNKS
    spiked = np.empty(n, np.int32)
    n_spiked = np.zeros(N_CHUNKS, np.int64)
    total = 0
    for s in range(n_steps):
        t = t0 + s
        row = buf[t % ring]
        for c in nb.prange(N_CHUNKS):
            lo = c * chunk
            hi = min(lo + chunk, n)
            ns = 0
            for i in range(lo, hi):
                gi = g[i] + row[i]
                row[i] = 0.0
                a[i] *= a_aa
                if ref[i] > 0:
                    ref[i] -= 1
                    g[i] = gi
                    continue
                vi = v0 + (v[i] - v0) * a_vv + gi * a_vg
                gi *= a_gg
                p = p_drive[i]
                if p > 0.0 and np.random.random() < p:
                    vi += kick
                if silenced[i] != 0:
                    vi = v0
                elif vi > v_th + a[i]:
                    vi = v_reset
                    gi = 0.0
                    if p > 0.0:
                        ref[i] = 0
                    else:
                        ref[i] = ref_steps
                        a[i] += d_adapt
                    spiked[lo + ns] = i
                    ns += 1
                    if counts[i] < 65535:
                        counts[i] += 1
                v[i] = vi
                g[i] = gi
            n_spiked[c] = ns
        out = buf[(t + delay) % ring]
        for c in range(N_CHUNKS):
            lo = c * chunk
            for k in range(n_spiked[c]):
                j = spiked[lo + k]
                for e in range(indptr[j], indptr[j + 1]):
                    out[indices[e]] += weights[e]
            total += n_spiked[c]
    return total


class Brain:
    def __init__(
        self, conn: Connectome, params: LIFParams = LIFParams(), seed: int = 0,
        sign_policy: str = "annotated", weights: np.ndarray | None = None,
    ):
        self.conn = conn
        self.p = params
        n = conn.n
        dt = params.dt_ms
        self.delay = max(1, round(params.t_delay / dt))
        self.ref_steps = max(1, round(params.t_ref / dt))
        self.a_vv = float(np.exp(-dt / params.tau_m))
        self.a_gg = float(np.exp(-dt / params.tau_syn))
        self.a_vg = float(
            params.tau_syn / (params.tau_syn - params.tau_m) * (np.exp(-dt / params.tau_syn) - np.exp(-dt / params.tau_m))
        )
        self.a_aa = float(np.exp(-dt / params.tau_adapt_ms))
        if weights is None:
            weights = conn.signed_synapses(sign_policy).astype(np.float32) * np.float32(params.w_syn)
        self.weights = weights
        self.v = np.full(n, params.v0, np.float32)
        self.g = np.zeros(n, np.float32)
        self.a = np.zeros(n, np.float32)
        self.ref = np.zeros(n, np.int16)
        self.buf = np.zeros((self.delay + 1, n), np.float32)
        self.drive_hz = np.zeros(n, np.float32)
        self.silenced = np.zeros(n, np.uint8)
        self.counts = np.zeros(n, np.uint16)
        self.step_idx = 0
        _seed(seed)

    @property
    def t_ms(self) -> float:
        return self.step_idx * self.p.dt_ms

    def run(self, ms: float) -> int:
        n_steps = max(1, round(ms / self.p.dt_ms))
        p_drive = self.drive_hz * np.float32(self.p.dt_ms / 1000.0)
        total = _run(
            n_steps, self.step_idx, self.v, self.g, self.a, self.ref, self.buf,
            self.conn.indptr, self.conn.indices, self.weights, p_drive, self.silenced, self.counts,
            self.a_vv, self.a_vg, self.a_gg, self.a_aa, self.p.v0, self.p.v_reset, self.p.v_th,
            self.p.adapt_mv, self.p.w_syn * self.p.poisson_scale, self.ref_steps, self.delay,
        )
        self.step_idx += n_steps
        return int(total)

    def drain(self) -> np.ndarray:
        out = self.counts.copy()
        self.counts[:] = 0
        return out

    def reset(self) -> None:
        self.v[:] = self.p.v0
        self.g[:] = 0
        self.a[:] = 0
        self.ref[:] = 0
        self.buf[:] = 0
        self.counts[:] = 0
