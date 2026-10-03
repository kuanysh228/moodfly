import numpy as np

from .atlas import EMOTIONS, Atlas

TAU_RISE_S = 0.4
TAU_DECAY_S = 3.0
GAIN = 1.5
CALM_THRESHOLD = 0.15

JOY = {"key": "joy", "label": "Радость узнавания", "color": "#d55181", "valence": 1.0}


def emotion_meta(atlas: Atlas) -> list[dict]:
    sig = atlas.signature
    meta = [{"key": e.key, "label": e.label, "color": e.color, "neurons": int(len(sig[e.key]))} for e in EMOTIONS]
    return meta + [{k: JOY[k] for k in ("key", "label", "color")} | {"neurons": 0}]


class EmotionModel:
    def __init__(self, atlas: Atlas):
        self.atlas = atlas
        self.level = {e.key: 0.0 for e in EMOTIONS} | {"joy": 0.0}
        self.raw = dict(self.level)

    def scores(self, rate_hz: np.ndarray) -> dict[str, float]:
        out = {}
        for e in EMOTIONS:
            score = max(
                (float(np.mean(np.minimum(rate_hz[idx] / ref, 2.0))) for idx, ref in self.atlas.parts[e.key] if len(idx)),
                default=0.0,
            )
            out[e.key] = 1.0 - float(np.exp(-GAIN * score))
        return out

    def update(self, rate_hz: np.ndarray, dt: float, joy: float = 0.0) -> dict:
        targets = self.scores(rate_hz) | {"joy": float(np.clip(joy, 0, 1))}
        for key, target in targets.items():
            self.raw[key] = target
            tau = TAU_RISE_S if target > self.level[key] else TAU_DECAY_S
            self.level[key] += (target - self.level[key]) * min(1.0, dt / tau)
        return self.state()

    def state(self) -> dict:
        lv = self.level
        valence = float(np.clip(sum(e.valence * lv[e.key] for e in EMOTIONS) + JOY["valence"] * lv["joy"], -1, 1))
        arousal = float(np.clip(max(lv.values()) * 0.85 + 0.15 * float(np.mean(list(lv.values()))), 0, 1))
        calm = float(np.clip(1.0 - arousal * 1.4, 0, 1))
        top = max(lv, key=lv.get)
        dominant = top if lv[top] >= CALM_THRESHOLD else "calm"
        return {
            "levels": {k: round(float(v), 3) for k, v in lv.items()} | {"calm": round(calm, 3)},
            "valence": round(valence, 3),
            "arousal": round(arousal, 3),
            "dominant": dominant,
        }
