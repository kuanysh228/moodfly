import math
import random
from dataclasses import asdict, dataclass, field

ARENA_R = 12.0
FLY_LEN = 2.6
WALK_SPEED = 5.0

DROP_KINDS = {"sugar": 120.0, "bitter": 120.0, "water": 100.0}
ODOR_KINDS = {"odor_good": 90.0, "odor_bad": 90.0}
ODOR_SIGMA = 4.0

THREAT_S = 1.0
PUFF_S = 0.8
TOUCH_S = 0.6

OWNER = (0.0, -ARENA_R + 0.4)
COME_RECOGNITION = 0.45
FLEE_RECOGNITION = -0.35

FEED_HZ = 18.0
ESCAPE_HZ = 40.0
GROOM_HZ = 4.0
BACKUP_HZ = 8.0


def _wrap(a: float) -> float:
    return (a + math.pi) % (2 * math.pi) - math.pi


@dataclass
class Item:
    id: int
    kind: str
    x: float
    y: float
    amount: float = 1.0

    @property
    def r(self) -> float:
        return 0.6 + 1.2 * self.amount if self.kind in DROP_KINDS else 0.8


@dataclass
class Fly:
    x: float = 0.0
    y: float = 0.0
    heading: float = math.pi / 2
    speed: float = 0.0
    omega: float = 0.0
    mode: str = "walk"
    mode_t: float = 0.0
    proboscis: float = 0.0
    gait: float = 0.0
    groom_phase: float = 0.0
    flight: dict | None = None
    cooldown: float = 0.0

    @property
    def head(self) -> tuple[float, float]:
        d = FLY_LEN * 0.45
        return self.x + d * math.cos(self.heading), self.y + d * math.sin(self.heading)


@dataclass
class World:
    fly: Fly = field(default_factory=Fly)
    items: list[Item] = field(default_factory=list)
    threat: dict | None = None
    puff_t: float = 0.0
    touch_t: float = 0.0
    light: bool = False
    contact: dict = field(default_factory=dict)
    _next_id: int = 1

    def place(self, kind: str, x: float, y: float) -> None:
        if kind not in DROP_KINDS and kind not in ODOR_KINDS:
            return
        if math.hypot(x, y) > ARENA_R:
            return
        self.items.append(Item(self._next_id, kind, x, y))
        self._next_id += 1

    def remove_near(self, x: float, y: float) -> None:
        if self.items:
            nearest = min(self.items, key=lambda it: math.hypot(it.x - x, it.y - y))
            if math.hypot(nearest.x - x, nearest.y - y) < nearest.r + 1.5:
                self.items.remove(nearest)

    def start_threat(self, x: float, y: float) -> None:
        f = self.fly
        self.threat = {"x": x, "y": y, "t": 0.0, "bearing": math.atan2(y - f.y, x - f.x)}

    def puff(self) -> None:
        self.puff_t = PUFF_S

    def touch(self) -> None:
        self.touch_t = TOUCH_S

    def odor_at(self, kind: str, x: float, y: float) -> float:
        return sum(
            it.amount * math.exp(-((it.x - x) ** 2 + (it.y - y) ** 2) / (2 * ODOR_SIGMA**2))
            for it in self.items
            if it.kind == kind
        )

    def sensory_drive(self) -> dict[str, float]:
        f = self.fly
        drive: dict[str, float] = {}
        hx, hy = f.head
        self.contact = {}
        if f.mode != "flight":
            for it in self.items:
                if it.kind in DROP_KINDS and math.hypot(it.x - hx, it.y - hy) < it.r + 0.3:
                    self.contact[it.kind] = it
                    drive[it.kind] = DROP_KINDS[it.kind] * min(1.0, 0.4 + it.amount)
        for kind, hz in ODOR_KINDS.items():
            c = min(1.0, self.odor_at(kind, hx, hy))
            if c > 0.02:
                drive[kind] = hz * c
        if self.threat:
            progress = min(1.0, self.threat["t"] / THREAT_S)
            rel = _wrap(self.threat["bearing"] - f.heading)
            left = min(1.0, max(0.0, 0.5 + 0.75 * math.sin(rel)))
            loom = 140.0 * progress**2
            drive["loom_left"] = loom * left
            drive["loom_right"] = loom * (1.0 - left)
        if self.puff_t > 0:
            drive["wind"] = 120.0
        if self.touch_t > 0:
            drive["bristle"] = 100.0
        if self.light:
            drive["light"] = 6.0
        return drive

    def step(self, dt: float, motor: dict[str, float], emo: dict[str, float], recognition: float = 0.0, word: str | None = None) -> list[str]:
        f = self.fly
        events: list[str] = []
        self.puff_t = max(0.0, self.puff_t - dt)
        self.touch_t = max(0.0, self.touch_t - dt)
        f.cooldown = max(0.0, f.cooldown - dt)
        f.mode_t += dt
        if self.threat:
            self.threat["t"] += dt
            if self.threat["t"] > THREAT_S + 0.4:
                self.threat = None

        def set_mode(m: str, why: str | None = None) -> None:
            if f.mode != m:
                f.mode, f.mode_t = m, 0.0
                if why:
                    events.append(why)

        if f.mode == "flight":
            self._fly_step(dt)
        elif motor["giant_fiber"] > ESCAPE_HZ and f.cooldown == 0:
            self._take_off()
            set_mode("flight", f"Взлёт! Гигантское волокно DNp01 {motor['giant_fiber']:.0f} Гц")
        elif motor["groom"] > GROOM_HZ:
            set_mode("groom", f"Чистит голову и антенны (grooming DN {motor['groom']:.0f} Гц)")
        elif motor["mn9"] > FEED_HZ:
            set_mode("feed", f"Вытягивает хоботок (MN9 {motor['mn9']:.0f} Гц)")
        elif motor["mdn"] > BACKUP_HZ:
            set_mode("backup", f"Пятится назад (MDN {motor['mdn']:.0f} Гц)")
        elif recognition > COME_RECOGNITION and f.mode != "come" and math.hypot(f.x - OWNER[0], f.y - OWNER[1]) > 2.5:
            set_mode("come", f"Узнала «{word}» и бежит к хозяину! (память грибовидного тела)")
        elif recognition < FLEE_RECOGNITION and f.mode != "flee":
            set_mode("flee", f"«{word}» — плохое слово, убегает (память грибовидного тела)")
        elif f.mode == "come" and (f.mode_t > 4.0 or math.hypot(f.x - OWNER[0], f.y - OWNER[1]) < 2.2):
            set_mode("pause")
        elif f.mode == "flee" and f.mode_t > 2.0:
            set_mode("walk")
        elif f.mode in ("feed", "groom", "backup") and f.mode_t > 0.3:
            set_mode("walk")
        elif f.mode == "walk" and random.random() < 0.12 * dt:
            set_mode("pause")
        elif f.mode == "pause" and random.random() < (0.6 + 2 * emo.get("arousal", 0)) * dt:
            set_mode("walk")

        target_p = min(1.0, motor["mn9"] / 40.0) if f.mode == "feed" else 0.0
        f.proboscis += (target_p - f.proboscis) * min(1.0, dt / 0.08)

        if f.mode == "flight":
            return events
        if f.mode == "walk":
            target_speed = WALK_SPEED * (1.0 + motor["walk"] / 10.0 + 0.8 * emo.get("arousal", 0))
        elif f.mode in ("come", "flee"):
            target_speed = WALK_SPEED * 1.8
        elif f.mode == "backup":
            target_speed = -3.0
        else:
            target_speed = 0.0
        f.speed += (target_speed - f.speed) * min(1.0, dt / 0.15)

        omega = -0.08 * (motor["turn_right"] - motor["turn_left"])
        f.omega += (random.gauss(0, 6.0) - f.omega) * min(1.0, dt / 0.3)
        omega += f.omega * (1.0 if f.mode == "walk" else 0.2)
        for kind, weight in (("odor_good", emo.get("interest", 0)), ("odor_bad", -emo.get("disgust", 0))):
            gx, gy = self._odor_gradient(kind)
            if gx or gy:
                omega += 4.0 * weight * math.sin(_wrap(math.atan2(gy, gx) - f.heading))
        if f.mode in ("come", "flee"):
            to_owner = math.atan2(OWNER[1] - f.y, OWNER[0] - f.x)
            goal = to_owner if f.mode == "come" else to_owner + math.pi
            omega = 6.0 * math.sin(_wrap(goal - f.heading))
        r = math.hypot(f.x, f.y)
        if r > ARENA_R - 1.5 and f.speed > 0 and f.mode != "come":
            omega += 3.0 * math.sin(_wrap(math.atan2(-f.y, -f.x) - f.heading))

        if f.mode in ("walk", "backup", "come", "flee"):
            f.heading = _wrap(f.heading + omega * dt)
        f.x += f.speed * math.cos(f.heading) * dt
        f.y += f.speed * math.sin(f.heading) * dt
        r = math.hypot(f.x, f.y)
        if r > ARENA_R - 1.0:
            f.x, f.y = f.x * (ARENA_R - 1.0) / r, f.y * (ARENA_R - 1.0) / r
        f.gait += abs(f.speed) * dt * 3.0
        f.groom_phase += dt * 9.0 if f.mode == "groom" else 0.0

        if f.mode == "feed":
            for kind in ("sugar", "water"):
                it = self.contact.get(kind)
                if it:
                    it.amount -= 0.12 * dt
                    if it.amount <= 0:
                        self.items.remove(it)
                        events.append("Капля съедена")
        return events

    def _odor_gradient(self, kind: str) -> tuple[float, float]:
        hx, hy = self.fly.head
        e = 0.5
        gx = self.odor_at(kind, hx + e, hy) - self.odor_at(kind, hx - e, hy)
        gy = self.odor_at(kind, hx, hy + e) - self.odor_at(kind, hx, hy - e)
        return (gx, gy) if math.hypot(gx, gy) > 1e-4 else (0.0, 0.0)

    def _take_off(self) -> None:
        f = self.fly
        away = f.heading + math.pi
        if self.threat:
            away = self.threat["bearing"] + math.pi
        away += random.uniform(-0.6, 0.6)
        dist = random.uniform(5.0, 9.0)
        tx, ty = f.x + dist * math.cos(away), f.y + dist * math.sin(away)
        r = math.hypot(tx, ty)
        if r > ARENA_R - 2.0:
            tx, ty = tx * (ARENA_R - 2.0) / r, ty * (ARENA_R - 2.0) / r
        f.flight = {"x0": f.x, "y0": f.y, "x1": tx, "y1": ty, "t": 0.0, "dur": 0.7}
        f.speed = 0.0

    def _fly_step(self, dt: float) -> None:
        f = self.fly
        fl = f.flight
        fl["t"] += dt
        u = min(1.0, fl["t"] / fl["dur"])
        f.x = fl["x0"] + (fl["x1"] - fl["x0"]) * u
        f.y = fl["y0"] + (fl["y1"] - fl["y0"]) * u
        f.heading = _wrap(math.atan2(fl["y1"] - fl["y0"], fl["x1"] - fl["x0"]))
        if u >= 1.0:
            f.flight = None
            f.mode, f.mode_t = "walk", 0.0
            f.cooldown = 1.5

    def snapshot(self) -> dict:
        f = self.fly
        alt = 0.0
        if f.flight:
            u = min(1.0, f.flight["t"] / f.flight["dur"])
            alt = math.sin(math.pi * u)
        return {
            "fly": {
                "x": round(f.x, 3), "y": round(f.y, 3), "heading": round(f.heading, 3),
                "speed": round(f.speed, 2), "mode": f.mode, "proboscis": round(f.proboscis, 2),
                "gait": round(f.gait, 2), "groom": round(f.groom_phase, 2), "alt": round(alt, 2),
            },
            "items": [asdict(it) | {"r": round(it.r, 2)} for it in self.items],
            "threat": None if not self.threat else {
                "x": self.threat["x"], "y": self.threat["y"],
                "progress": round(min(1.0, self.threat["t"] / THREAT_S), 2),
            },
            "puff": self.puff_t > 0,
            "touch": self.touch_t > 0,
            "light": self.light,
            "contact": sorted(self.contact),
            "owner": {"x": OWNER[0], "y": OWNER[1]},
        }
