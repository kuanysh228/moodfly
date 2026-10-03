import json
import random
from dataclasses import asdict, dataclass

import numpy as np

from .flybrain import VARIANT, FlyBrain, Kit
from .paths import DATA

TRAINABLE = ("strength", "speed", "agility", "durability")
POINT_VALUE = 3
STAT_LABELS = {
    "strength": "Сила", "speed": "Скорость", "agility": "Ловкость", "durability": "Прочность",
    "courage": "Смелость", "temper": "Вспыльчивость", "learning": "Обучаемость",
}


@dataclass
class Genome:
    seed: int
    size: float
    legs: float
    wings: float
    cuticle: float
    learning: float
    hue: int

    @classmethod
    def random(cls, seed: int | None = None) -> "Genome":
        seed = seed if seed is not None else random.getrandbits(48)
        r = random.Random(seed)
        g = lambda lo, hi: round(r.uniform(lo, hi), 3)
        return cls(seed, g(0.85, 1.15), g(0.8, 1.2), g(0.8, 1.2), g(0.8, 1.2), g(0.7, 1.3), r.randrange(360))

    def to_dict(self) -> dict:
        return asdict(self)


LOOM_HZ, BRISTLE_HZ, SUGAR_HZ = 40, 25, 30
MEASURES = ("escape_latency_ms", "giant_fiber_hz", "fear", "irritation", "groom_hz", "mn9_hz", "appetite")
REFERENCE_FLIES = 12


def checkup(kit: Kit, genome: Genome) -> dict:
    fb = FlyBrain(kit, genome.seed)
    fb.background = False
    b = fb.brain
    gf = kit.readouts["giant_fiber"].idx
    for key in ("loom_left", "loom_right"):
        b.drive_hz[kit.sensory[key].idx] = LOOM_HZ
    latency = 300
    for ms in range(1, 301):
        b.run(1)
        if b.counts[gf].any():
            latency = ms
            break
    out = {"escape_latency_ms": latency}

    def trial(drive: dict, ticks: int) -> FlyBrain:
        f = FlyBrain(kit, genome.seed)
        f.background = False
        for _ in range(ticks):
            f.tick(drive)
        return f

    f = trial({"loom_left": LOOM_HZ, "loom_right": LOOM_HZ}, 15)
    out["giant_fiber_hz"] = round(f.motor["giant_fiber"], 1)
    out["fear"] = round(f.emotions.raw["fear"], 4)
    f = trial({"bristle": BRISTLE_HZ}, 25)
    out["irritation"] = round(f.emotions.raw["irritation"], 4)
    out["groom_hz"] = round(f.motor["groom"], 1)
    f = trial({"sugar": SUGAR_HZ}, 25)
    out["mn9_hz"] = round(f.motor["mn9"], 1)
    out["appetite"] = round(f.emotions.raw["appetite"], 4)
    return out


def reference(kit: Kit) -> dict[str, tuple[float, float]]:
    path = DATA / f"reference_{VARIANT}.json"
    if path.exists():
        return {k: tuple(v) for k, v in json.loads(path.read_text()).items()}
    print(f"Measuring {REFERENCE_FLIES} reference flies for stat scaling (one-time)...")
    rows = [checkup(kit, Genome.random(10_000 + i)) for i in range(REFERENCE_FLIES)]
    ref = {k: (float(np.mean([r[k] for r in rows])), float(np.std([r[k] for r in rows]) or 1.0)) for k in MEASURES}
    path.write_text(json.dumps(ref))
    return ref


def _clip(x: float) -> int:
    return int(round(min(100.0, max(1.0, x))))


def base_stats(genome: Genome, check: dict, ref: dict) -> dict[str, int]:
    z = {k: float(np.clip((check[k] - ref[k][0]) / ref[k][1], -2.5, 2.5)) for k in MEASURES}
    return {
        "strength": _clip(50 + 150 * (genome.size - 1)),
        "speed": _clip(50 + 125 * (genome.legs - 1)),
        "agility": _clip(50 + 10 * z["giant_fiber_hz"] - 6 * z["escape_latency_ms"] + 60 * (genome.wings - 1)),
        "durability": _clip(50 + 90 * (genome.cuticle - 1) + 60 * (genome.size - 1)),
        "courage": _clip(50 - 18 * z["fear"]),
        "temper": _clip(50 + 18 * z["irritation"]),
        "learning": _clip(50 + 120 * (genome.learning - 1)),
    }


def stats(genome: Genome, check: dict, ref: dict, points: dict[str, int]) -> dict[str, int]:
    s = base_stats(genome, check, ref)
    for k in TRAINABLE:
        s[k] = _clip(s[k] + POINT_VALUE * points.get(k, 0))
    return s


def xp_to_next(level: int) -> int:
    return 40 * level


def combat(s: dict[str, int]) -> dict[str, float]:
    return {
        "hp": 60 + 0.8 * s["durability"],
        "walk": 3.5 + 0.06 * s["speed"],
        "damage": 4 + 0.12 * s["strength"],
        "armor": s["durability"] / 400,
        "dodge": s["agility"] / 400,
        "lunge_cd": 1.5 - 0.007 * s["agility"],
        "temper": s["temper"] / 100,
    }


def describe(check: dict, ref: dict) -> list[str]:
    def vs(key: str, higher: str, lower: str) -> str:
        z = (check[key] - ref[key][0]) / ref[key][1]
        return higher if z > 0.5 else lower if z < -0.5 else "как у средней мухи"

    return [
        f"Гигантское волокно: первый спайк через {check['escape_latency_ms']} мс после тени, {check['giant_fiber_hz']} Гц — {vs('giant_fiber_hz', 'резвее средней мухи', 'медленнее средней мухи')}",
        f"Страх от тени: {round(check['fear'] * 100)}% — {vs('fear', 'пугливее других', 'смелее других')}",
        f"Раздражение от касания: {round(check['irritation'] * 100)}%, груминг {check['groom_hz']} Гц — {vs('irritation', 'вспыльчивее других', 'спокойнее других')}",
        f"Сахар: MN9 {check['mn9_hz']} Гц — {vs('mn9_hz', 'сладкоежка', 'равнодушна к сладкому')}",
    ]
