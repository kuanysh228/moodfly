import numpy as np

from .atlas import load_or_calibrate
from .brain import Brain, LIFParams
from .connectome import Connectome, load
from .emotions import EmotionModel
from .plasticity import MushroomBody
from .populations import readout_groups, sensory_groups
from .speech import Speech

VARIANT = "central-v2"
PN_KC_GAIN = 3.0
SYNAPSE_SIGMA = 0.1
NEURON_SIGMA = 0.25
RATE_TAU_S = 0.2
BACKGROUND_HZ = 1.5
REWARD_HZ = 80.0
RECOGNITION_ZERO = 0.15
RECOGNITION_FULL = 0.30
RECOGNITION_AFTER_S = 0.3


class Kit:
    def __init__(self):
        full = load()
        conn = full.subset(full.label("super_class") != "optic")
        self.conn = conn
        self.params = LIFParams()
        self.sensory = sensory_groups(conn)
        self.readouts = readout_groups(conn)
        self.cell_types = conn.cell_type_counts

        w = conn.signed_synapses().astype(np.float32) * np.float32(self.params.w_syn)
        pre = np.repeat(np.arange(conn.n), np.diff(conn.indptr))
        kc = self._mask(conn.where("cell_class", ["Kenyon_Cell"]))
        pn = self._mask(conn.where("cell_class", ["ALPN"]))
        dan = self._mask(conn.where("cell_class", ["DAN"]))
        mbon = self._mask(conn.where("cell_class", ["MBON"]))
        w[pn[pre] & kc[conn.indices]] *= PN_KC_GAIN
        w[dan[pre] & (kc[conn.indices] | mbon[conn.indices])] = 0.0
        w[kc[pre] & dan[conn.indices]] = 0.0
        self.base_weights = w

        probe = Brain(conn, self.params, weights=w.copy())
        probe.run(1)
        self.atlas = load_or_calibrate(conn, probe, VARIANT)
        self.signature = self.atlas.signature
        desc = conn.where("super_class", ["descending"])
        self.groom_idx = np.union1d(self.readouts["groom"].idx, np.intersect1d(self.signature["irritation"], desc))
        self.bg_idx = conn.where("super_class", ["sensory"])
        self.pam = conn.where_prefix("cell_type", ["PAM"])
        self.ppl1 = conn.where_prefix("cell_type", ["PPL1"])
        self.rival_odor = conn.where("cell_type", ["ORN_DA1"])

    def _mask(self, idx: np.ndarray) -> np.ndarray:
        m = np.zeros(self.conn.n, bool)
        m[idx] = True
        return m

    def weights_for(self, seed: int) -> np.ndarray:
        rng = np.random.default_rng(seed)
        noise = rng.lognormal(0.0, SYNAPSE_SIGMA, len(self.base_weights)).astype(np.float32)
        gain = rng.lognormal(0.0, NEURON_SIGMA, self.conn.n).astype(np.float32)
        return self.base_weights * noise * gain[self.conn.indices]


class FlyBrain:
    def __init__(self, kit: Kit, seed: int, learning_gain: float = 1.0, memory: bytes | None = None):
        self.kit = kit
        self.brain = Brain(kit.conn, kit.params, seed=seed % (2**31), weights=kit.weights_for(seed))
        self.mb = MushroomBody(kit.conn, self.brain.weights, learning_gain)
        self.mb.load_memory(memory)
        self.speech = Speech(kit.conn)
        self.emotions = EmotionModel(kit.atlas)
        n = kit.conn.n
        self.rate = np.zeros(n, np.float32)
        self.frame_counts = np.zeros(n, np.uint16)
        self.opto: dict[str, dict] = {}
        self.background = True
        self.reward_t = 0.0
        self.punish_t = 0.0
        self.word: str | None = None
        self.cue_t = 0.0
        self.recognition = 0.0
        self.motor: dict[str, float] = {}
        self.emo_state = self.emotions.state()
        self.spikes_last = 0

    def reward(self, seconds: float = 1.0) -> None:
        self.reward_t = max(self.reward_t, seconds)

    def punish(self, seconds: float = 1.0) -> None:
        self.punish_t = max(self.punish_t, seconds)

    def set_opto(self, cell_type: str, mode: str, hz: float = 100.0) -> int:
        conn = self.kit.conn
        if cell_type.endswith("*") and len(cell_type) > 2:
            idx = conn.where_prefix("cell_type", [cell_type[:-1]])
        else:
            idx = conn.where("cell_type", [cell_type])
        if mode == "off" or not len(idx):
            self.opto.pop(cell_type, None)
        else:
            self.opto[cell_type] = {"mode": mode, "hz": hz, "idx": idx}
        return len(idx)

    def _apply(self, drive: dict[str, float], extra: list[tuple[np.ndarray, float]]) -> None:
        b, k = self.brain, self.kit
        b.drive_hz[:] = 0
        if self.background:
            b.drive_hz[k.bg_idx] = BACKGROUND_HZ
        for key, hz in drive.items():
            if key in k.sensory:
                idx = k.sensory[key].idx
                b.drive_hz[idx] = np.maximum(b.drive_hz[idx], hz)
        for idx, hz in extra:
            b.drive_hz[idx] = np.maximum(b.drive_hz[idx], hz)
        if self.reward_t > 0:
            b.drive_hz[k.pam] = REWARD_HZ
        if self.punish_t > 0:
            b.drive_hz[k.ppl1] = REWARD_HZ
        b.silenced[:] = 0
        for o in self.opto.values():
            if o["mode"] == "activate":
                b.drive_hz[o["idx"]] = np.maximum(b.drive_hz[o["idx"]], o["hz"])
            else:
                b.silenced[o["idx"]] = 1
                b.drive_hz[o["idx"]] = 0

    def tick(self, drive: dict[str, float], dt_ms: float = 20.0, extra=()) -> None:
        dt = dt_ms / 1000
        word, word_idx, word_t = self.speech.step(dt)
        if word != self.word:
            self.recognition = 0.0
        self.word = word
        extra = list(extra)
        if word_idx is not None:
            extra.append((word_idx, 100.0))
        self._apply(drive, extra)
        self.reward_t = max(0.0, self.reward_t - dt)
        self.punish_t = max(0.0, self.punish_t - dt)

        self.spikes_last = self.brain.run(dt_ms)
        counts = self.brain.drain()
        np.add(self.frame_counts, counts, out=self.frame_counts)
        self.rate += (counts.astype(np.float32) / dt - self.rate) * (dt / RATE_TAU_S)
        self.cue_t = 1.0 if self.word else max(0.0, self.cue_t - dt)
        self.mb.update(counts, self.rate, dt, cue=self.cue_t > 0)

        if self.word and word_t >= RECOGNITION_AFTER_S:
            value = self.mb.learned_value(self.rate)
            if value > RECOGNITION_ZERO:
                target = min(1.0, (value - RECOGNITION_ZERO) / (RECOGNITION_FULL - RECOGNITION_ZERO))
            elif value < -0.05:
                target = max(-1.0, (value + 0.05) / 0.12)
            else:
                target = 0.0
            self.recognition += (target - self.recognition) * min(1.0, dt / 0.15)

        k = self.kit
        motor = {key: float(self.rate[g.idx].mean()) if len(g) else 0.0 for key, g in k.readouts.items()}
        motor["groom"] = float(self.rate[k.groom_idx].mean())
        self.motor = motor
        self.emo_state = self.emotions.update(self.rate, dt, joy=max(0.0, self.recognition))

    def take_spikes(self) -> bytes:
        active = np.flatnonzero(self.frame_counts).astype("<u4")
        self.frame_counts[:] = 0
        return active.tobytes()

    def emotion_input(self) -> dict:
        return self.emo_state["levels"] | {"arousal": self.emo_state["arousal"]}
