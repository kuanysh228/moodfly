import math
import random
from dataclasses import dataclass, field

from .flybrain import FlyBrain, Kit
from .genome import combat
from .world import ARENA_R, ESCAPE_HZ, GROOM_HZ, Fly, _wrap

INTRO_S = 3.0
DURATION_S = 45.0
REACH_MM = 1.9
LUNGE_S = 0.18
LUNGE_SPEED = 14.0
HIT_FEEL_S = 0.4
DODGE_CD_S = 2.0
MIN_GAP_MM = 1.5


@dataclass
class Fighter:
    pet: dict
    stats: dict
    brain: FlyBrain
    fly: Fly
    cb: dict = field(init=False)
    hp: float = field(init=False)
    lunge_t: float = 0.0
    cooldown: float = 0.5
    dodge_cd: float = 0.0
    feel_hit: float = 0.0
    prev_dist: float = 12.0
    hits: int = 0
    dodges: int = 0

    def __post_init__(self):
        self.cb = combat(self.stats)
        self.hp = self.cb["hp"]


class Battle:
    def __init__(self, kit: Kit, pets: list[dict], stats: list[dict]):
        self.kit = kit
        self.t = 0.0
        self.events: list[dict] = []
        self.fx: list[dict] = []
        self.finished = False
        self.winner: int | None = None
        self.fighters = []
        for i, (pet, st) in enumerate(zip(pets, stats)):
            g = pet["genome"]
            brain = FlyBrain(kit, g["seed"], g["learning"], pet.get("memory"))
            x = -6.0 if i == 0 else 6.0
            fly = Fly(x=x, y=0.0, heading=0.0 if i == 0 else math.pi)
            self.fighters.append(Fighter(pet, st, brain, fly))
        self._log(f"Бой: {pets[0]['name']} против {pets[1]['name']}!")

    def _log(self, text: str) -> None:
        self.events.append({"t": round(self.t, 1), "text": text})

    def _fx(self, kind: str, who: int, **data) -> None:
        self.fx.append({"k": kind, "who": who, "t": round(self.t, 2)} | data)

    def _idx(self, f: Fighter) -> int:
        return 0 if f is self.fighters[0] else 1

    @property
    def phase(self) -> str:
        return "over" if self.finished else "intro" if self.t < INTRO_S else "fight"

    def _senses(self, me: Fighter, other: Fighter, dt: float) -> tuple[dict, list]:
        f, o = me.fly, other.fly
        d = max(0.3, math.hypot(o.x - f.x, o.y - f.y))
        closing = (me.prev_dist - d) / dt
        me.prev_dist = d
        drive: dict[str, float] = {}
        if o.mode != "flight":
            rel = _wrap(math.atan2(o.y - f.y, o.x - f.x) - f.heading)
            loom = 140.0 * min(1.0, (1.4 / d) ** 1.2 * (0.35 + max(0.0, closing) / 6.0))
            left = min(1.0, max(0.0, 0.5 + 0.75 * math.sin(rel)))
            drive["loom_left"] = loom * left
            drive["loom_right"] = loom * (1.0 - left)
        if me.feel_hit > 0:
            drive["bristle"] = 100.0
        extra = [(self.kit.rival_odor, 60.0 * math.exp(-d / 5.0))]
        return drive, extra

    def tick(self, dt: float = 0.02) -> None:
        if self.finished:
            return
        self.t += dt
        a, b = self.fighters
        if self.t < INTRO_S:
            for me, other in ((a, b), (b, a)):
                me.brain.tick({}, dt * 1000, [(self.kit.rival_odor, 30.0)])
            if self.t + dt >= INTRO_S:
                self._log("БОЙ!")
            return
        for me, other in ((a, b), (b, a)):
            drive, extra = self._senses(me, other, dt)
            me.brain.tick(drive, dt * 1000, extra)
        for me, other in ((a, b), (b, a)):
            self._act(me, other, dt)
        self._separate()
        self._check_end()

    def _act(self, me: Fighter, other: Fighter, dt: float) -> None:
        f, o = me.fly, other.fly
        cb, motor = me.cb, me.brain.motor
        emo = me.brain.emo_state["levels"]
        me.cooldown = max(0.0, me.cooldown - dt)
        me.dodge_cd = max(0.0, me.dodge_cd - dt)
        me.feel_hit = max(0.0, me.feel_hit - dt)
        f.mode_t += dt
        to_other = math.atan2(o.y - f.y, o.x - f.x)
        d = math.hypot(o.x - f.x, o.y - f.y)

        if f.mode == "flight":
            fl = f.flight
            fl["t"] += dt
            u = min(1.0, fl["t"] / fl["dur"])
            f.x = fl["x0"] + (fl["x1"] - fl["x0"]) * u
            f.y = fl["y0"] + (fl["y1"] - fl["y0"]) * u
            if u >= 1.0:
                f.flight, f.mode, f.mode_t = None, "attack", 0.0
                f.heading = to_other
            return

        aggression = 0.35 + 0.5 * cb["temper"] + 0.6 * emo["irritation"]
        fear = emo["fear"] * (1.6 - me.stats["courage"] / 100) + (0.25 if me.hp < 0.3 * cb["hp"] else 0.0)
        if motor["giant_fiber"] > ESCAPE_HZ and me.dodge_cd == 0:
            away = to_other + math.pi + random.uniform(-0.9, 0.9)
            dist = 3.5 + 3.0 * me.stats["agility"] / 100
            tx, ty = f.x + dist * math.cos(away), f.y + dist * math.sin(away)
            r = math.hypot(tx, ty)
            if r > ARENA_R - 1.5:
                tx, ty = tx * (ARENA_R - 1.5) / r, ty * (ARENA_R - 1.5) / r
            f.flight = {"x0": f.x, "y0": f.y, "x1": tx, "y1": ty, "t": 0.0, "dur": 0.45}
            f.mode, f.mode_t, f.speed = "flight", 0.0, 0.0
            me.dodge_cd = DODGE_CD_S
            me.lunge_t = 0.0
            me.dodges += 1
            self._fx("jump", self._idx(me), hz=round(motor["giant_fiber"]))
            self._log(f"{me.pet['name']} отпрыгнула — сработало гигантское волокно ({motor['giant_fiber']:.0f} Гц)")
            return
        if me.lunge_t > 0:
            mode = "lunge"
        elif motor["groom"] > GROOM_HZ * 1.5:
            mode = "groom"
        elif fear > aggression + 0.15:
            mode = "flee"
        else:
            mode = "attack"
        if mode != f.mode:
            if mode == "flee":
                self._fx("flee", self._idx(me))
                self._log(f"{me.pet['name']} испугалась и отступает (страх {fear:.0%})")
            elif mode == "groom":
                self._fx("groom", self._idx(me))
                self._log(f"{me.pet['name']} отвлеклась на груминг")
            f.mode, f.mode_t = mode, 0.0

        if mode == "lunge":
            me.lunge_t -= dt
            f.heading = to_other
            f.speed = LUNGE_SPEED
            if me.lunge_t <= 0:
                self._strike(me, other, d)
        elif mode == "attack":
            f.heading += 7.0 * math.sin(_wrap(to_other - f.heading)) * dt
            f.speed = cb["walk"] * (1.0 + 0.4 * aggression) if d > REACH_MM * 0.9 else 0.5
            if d < REACH_MM + 0.6 and abs(_wrap(to_other - f.heading)) < 0.5 and me.cooldown == 0:
                me.lunge_t = LUNGE_S
                f.mode = "lunge"
                self._fx("lunge", self._idx(me))
        elif mode == "flee":
            away = to_other + math.pi
            if math.hypot(f.x, f.y) > ARENA_R - 2.5:
                away = math.atan2(f.y, f.x) + math.pi / 2
            f.heading += 7.0 * math.sin(_wrap(away - f.heading)) * dt
            f.speed = cb["walk"] * 1.2
        else:
            f.speed = 0.0
            f.groom_phase += dt * 9.0

        f.x += f.speed * math.cos(f.heading) * dt
        f.y += f.speed * math.sin(f.heading) * dt
        r = math.hypot(f.x, f.y)
        if r > ARENA_R - 1.0:
            f.x, f.y = f.x * (ARENA_R - 1.0) / r, f.y * (ARENA_R - 1.0) / r
        f.gait += abs(f.speed) * dt * 3.0

    def _strike(self, me: Fighter, other: Fighter, d: float) -> None:
        me.cooldown = me.cb["lunge_cd"]
        if d > REACH_MM or other.fly.mode == "flight":
            return
        if random.random() < other.cb["dodge"]:
            other.dodges += 1
            self._fx("dodge", self._idx(other))
            self._log(f"{other.pet['name']} увернулась")
            return
        rage = me.brain.emo_state["levels"]["irritation"]
        crit = random.random() < 0.08 + 0.25 * rage
        dmg = me.cb["damage"] * (1 + 0.4 * rage) * (1.7 if crit else 1.0) * random.uniform(0.85, 1.15) * (1 - other.cb["armor"])
        other.hp = max(0.0, other.hp - dmg)
        other.feel_hit = HIT_FEEL_S
        me.hits += 1
        self._fx("hit", self._idx(me), target=self._idx(other), dmg=round(dmg), crit=crit)
        self._log(f"{me.pet['name']} бьёт {other.pet['name']}: −{dmg:.0f} HP{' — КРИТ!' if crit else ''}")

    def _separate(self) -> None:
        f, o = self.fighters[0].fly, self.fighters[1].fly
        if f.mode == "flight" or o.mode == "flight":
            return
        dx, dy = o.x - f.x, o.y - f.y
        d = math.hypot(dx, dy)
        if 0 < d < MIN_GAP_MM:
            push = (MIN_GAP_MM - d) / 2
            f.x -= dx / d * push
            f.y -= dy / d * push
            o.x += dx / d * push
            o.y += dy / d * push

    def _check_end(self) -> None:
        a, b = self.fighters
        if a.hp <= 0 or b.hp <= 0:
            self.winner = 0 if b.hp <= 0 else 1
        elif self.t >= INTRO_S + DURATION_S:
            fa, fb = a.hp / a.cb["hp"], b.hp / b.cb["hp"]
            self.winner = None if abs(fa - fb) < 0.03 else (0 if fa > fb else 1)
        else:
            return
        self.finished = True
        if self.winner is not None and self.fighters[1 - self.winner].hp <= 0:
            self._fx("ko", 1 - self.winner)
        if self.winner is None:
            self._log("Время вышло — ничья!")
        else:
            self._log(f"Победа: {self.fighters[self.winner].pet['name']}!")

    def snapshot(self) -> dict:
        flies = []
        for fi in self.fighters:
            f = fi.fly
            alt = math.sin(math.pi * min(1.0, f.flight["t"] / f.flight["dur"])) if f.flight else 0.0
            flies.append({
                "x": round(f.x, 3), "y": round(f.y, 3), "heading": round(f.heading, 3), "mode": f.mode,
                "speed": round(f.speed, 2), "proboscis": 0.0, "gait": round(f.gait, 2), "groom": round(f.groom_phase, 2),
                "alt": round(alt, 2), "hp": round(fi.hp, 1), "max_hp": round(fi.cb["hp"], 1),
                "name": fi.pet["name"], "owner": fi.pet["owner"], "hue": fi.pet["genome"]["hue"],
                "level": fi.pet["level"], "stats": fi.stats, "hits": fi.hits, "dodges": fi.dodges,
                "rage": round(fi.brain.emo_state["levels"]["irritation"], 2),
                "fear": round(fi.brain.emo_state["levels"]["fear"], 2),
                "gf": round(fi.brain.motor.get("giant_fiber", 0.0)),
            })
        return {"flies": flies, "phase": self.phase, "intro_left": round(max(0.0, INTRO_S - self.t), 2),
                "time_left": round(max(0.0, INTRO_S + DURATION_S - self.t), 1), "finished": self.finished,
                "winner": self.winner, "items": [], "threat": None, "puff": False, "touch": False, "light": False}
