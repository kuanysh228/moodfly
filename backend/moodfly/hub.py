import struct
import threading
import time
from collections import deque

import numpy as np

from .battle import Battle
from .db import DB
from .emotions import emotion_meta
from .flybrain import Kit
from .genome import STAT_LABELS, TRAINABLE, Genome, checkup, combat, describe, reference, stats, xp_to_next
from .room import LEARNED_NAME_XP, SAVE_EVERY_S, PetRoom
from .world import ARENA_R, FLY_LEN

TICK_S = 0.02
FRAME_S = 1 / 25
ROOM_IDLE_S = 20.0
BATTLE_LINGER_S = 15.0
XP_WIN, XP_LOSS, XP_DRAW = 30, 12, 18
POINTS_PER_LEVEL = 2
MAX_LIVE_BATTLES = 2


class Session:
    def __init__(self, key: str, obj):
        self.key = key
        self.obj = obj
        self.kind = "battle" if isinstance(obj, Battle) else "pet"
        self.viewers = 0
        self.frame: dict | None = None
        self.bins: list[bytes] = []
        self.frame_id = 0
        self.sps = deque(maxlen=50)
        self.ended_at: float | None = None

    def brains(self):
        if self.kind == "pet":
            return [self.obj.brain]
        return [f.brain for f in self.obj.fighters]


class Hub:
    def __init__(self):
        t0 = time.time()
        self.kit = Kit()
        self.ref = reference(self.kit)
        self.db = DB()
        self.sessions: dict[str, Session] = {}
        self.clients: set = set()
        self.lock = threading.RLock()
        self.speed = 1.0
        self._running = False
        self._battle_seq = 0
        print(f"Hub ready in {time.time() - t0:.1f} s: {self.kit.conn.n} neurons per pet brain")

    def hello(self) -> dict:
        k = self.kit
        return {
            "type": "hello",
            "n": k.conn.n,
            "arena_r": ARENA_R,
            "fly_len": FLY_LEN,
            "emotions": emotion_meta(k.atlas),
            "readouts": [{"key": g.key, "label": g.label, "n": len(g)} for g in k.readouts.values()],
            "sensory": [{"key": g.key, "label": g.label, "n": len(g)} for g in k.sensory.values()],
            "super_classes": [str(s) for s in k.conn.names["super_class"]],
            "cell_types": k.cell_types,
            "stat_labels": STAT_LABELS,
            "trainable": list(TRAINABLE),
        }

    def brain_binary(self) -> bytes:
        conn = self.kit.conn
        sc = conn.codes["super_class"].astype(np.int16)
        sc[sc < 0] = 255
        emo = np.zeros(conn.n, np.uint8)
        for i, e in enumerate(emotion_meta(self.kit.atlas), start=1):
            if e["key"] in self.kit.signature:
                emo[self.kit.signature[e["key"]]] = i
        return struct.pack("<4I", conn.n, 0, 0, 0) + conn.pos.astype("<f4").tobytes() + sc.astype(np.uint8).tobytes() + emo.tobytes()

    def broadcast(self, msg: dict) -> None:
        for c in list(self.clients):
            c.push(msg)

    def notify_user(self, user_id: int, msg: dict) -> None:
        for c in list(self.clients):
            if c.user and c.user["id"] == user_id:
                c.push(msg)

    def broadcast_lists(self) -> None:
        self.broadcast({"type": "pets", "pets": self.pets_public()})
        self.broadcast({"type": "battles", "battles": self.battles_public()})

    def pet_stats(self, pet: dict) -> dict:
        return stats(Genome(**pet["genome"]), pet["checkup"], self.ref, pet["points"])

    def pet_public(self, pet: dict) -> dict:
        st = self.pet_stats(pet)
        live = self.sessions.get(f"pet:{pet['id']}")
        return {
            "id": pet["id"], "name": pet["name"], "owner": pet["owner"], "owner_id": pet["owner_id"],
            "level": pet["level"], "xp": pet["xp"], "xp_next": xp_to_next(pet["level"]), "unspent": pet["unspent"],
            "wins": pet["wins"], "losses": pet["losses"], "draws": pet["draws"],
            "stats": st, "combat": {k: round(v, 2) for k, v in combat(st).items()},
            "hue": pet["genome"]["hue"], "checkup": describe(pet["checkup"], self.ref),
            "points": pet["points"], "seed": pet["genome"]["seed"],
            "genes": {k: pet["genome"][k] for k in ("size", "legs", "wings", "cuticle", "learning")},
            "learned_name": bool(pet["flags"].get("learned_name")),
            "online": live is not None, "in_battle": self._in_battle(pet["id"]),
        }

    def pets_public(self) -> list[dict]:
        return [self.pet_public(p) for p in self.db.pets()]

    def _in_battle(self, pet_id: int) -> bool:
        return any(s.kind == "battle" and s.ended_at is None and pet_id in (f.pet["id"] for f in s.obj.fighters)
                   for s in self.sessions.values())

    def create_pet(self, user: dict, name: str) -> dict:
        genome = Genome.random()
        check = checkup(self.kit, genome)
        pet = self.db.create_pet(user["id"], name, genome.to_dict(), check)
        self.broadcast_lists()
        return pet

    def allocate(self, user: dict, stat: str) -> dict | None:
        pet = self.db.pet_of(user["id"])
        if not pet or stat not in TRAINABLE or pet["unspent"] <= 0:
            return pet
        pet["points"][stat] = pet["points"].get(stat, 0) + 1
        self.db.update_pet(pet["id"], points=pet["points"], unspent=pet["unspent"] - 1)
        return self.db.pet(pet["id"])

    def grant_xp(self, pet_id: int, amount: int) -> list[str]:
        pet = self.db.pet(pet_id)
        xp, level, unspent, notes = pet["xp"] + amount, pet["level"], pet["unspent"], []
        while xp >= xp_to_next(level):
            xp -= xp_to_next(level)
            level += 1
            unspent += POINTS_PER_LEVEL
            notes.append(f"{pet['name']} достигла уровня {level}! +{POINTS_PER_LEVEL} очка характеристик")
        self.db.update_pet(pet_id, xp=xp, level=level, unspent=unspent)
        return notes

    def watch(self, key: str | None, user: dict | None) -> Session | None:
        if not key:
            return None
        with self.lock:
            s = self.sessions.get(key)
            if s is None and key.startswith("pet:"):
                pet = self.db.pet(int(key.split(":")[1]))
                if not pet:
                    return None
                s = Session(key, PetRoom(self.kit, pet))
                self.sessions[key] = s
                self.broadcast({"type": "pets", "pets": self.pets_public()})
            if s:
                s.viewers += 1
            return s

    def unwatch(self, s: Session | None) -> None:
        if s:
            with self.lock:
                s.viewers = max(0, s.viewers - 1)
                if s.kind == "pet":
                    s.obj.last_viewed = time.time()

    def challenge(self, user: dict, target_id: int) -> tuple[str | None, str]:
        mine = self.db.pet_of(user["id"])
        target = self.db.pet(target_id)
        if not mine or not target:
            return None, "Питомец не найден"
        if mine["id"] == target["id"]:
            return None, "Нельзя драться с самой собой"
        with self.lock:
            if self._in_battle(mine["id"]) or self._in_battle(target["id"]):
                return None, "Кто-то из бойцов уже на арене"
            live = sum(1 for s in self.sessions.values() if s.kind == "battle" and s.ended_at is None)
            if live >= MAX_LIVE_BATTLES:
                return None, "Арена занята, попробуйте через минуту"
            for p in (mine, target):
                room = self.sessions.get(f"pet:{p['id']}")
                if room:
                    p["memory"] = room.obj.memory()
            battle = Battle(self.kit, [mine, target], [self.pet_stats(mine), self.pet_stats(target)])
            self._battle_seq += 1
            key = f"battle:{self._battle_seq}"
            self.sessions[key] = Session(key, battle)
        self.broadcast({"type": "notice", "text": f"{mine['name']} ({mine['owner']}) вызвала на бой {target['name']} ({target['owner']})!", "battle": key})
        self.broadcast_lists()
        return key, ""

    def battles_public(self) -> list[dict]:
        out = []
        for s in self.sessions.values():
            if s.kind == "battle":
                b = s.obj
                out.append({"key": s.key, "names": [f.pet["name"] for f in b.fighters], "owners": [f.pet["owner"] for f in b.fighters],
                            "finished": b.finished})
        return out

    def _finish_battle(self, s: Session) -> None:
        b = s.obj
        s.ended_at = time.time()
        ids = [f.pet["id"] for f in b.fighters]
        names = [f.pet["name"] for f in b.fighters]
        notes = []
        for i, pid in enumerate(ids):
            pet = self.db.pet(pid)
            if b.winner is None:
                self.db.update_pet(pid, draws=pet["draws"] + 1)
                notes += self.grant_xp(pid, XP_DRAW)
            elif b.winner == i:
                self.db.update_pet(pid, wins=pet["wins"] + 1)
                notes += self.grant_xp(pid, XP_WIN)
            else:
                self.db.update_pet(pid, losses=pet["losses"] + 1)
                notes += self.grant_xp(pid, XP_LOSS)
        winner_id = ids[b.winner] if b.winner is not None else None
        self.db.save_battle(ids[0], ids[1], winner_id, {"names": names, "hp": [round(f.hp) for f in b.fighters], "t": round(b.t, 1)})
        result = "ничья" if b.winner is None else f"победила {names[b.winner]}"
        self.broadcast({"type": "notice", "text": f"{names[0]} vs {names[1]}: {result}"})
        for n in notes:
            self.broadcast({"type": "notice", "text": n})
        self.broadcast_lists()

    def _milestones(self, room: PetRoom) -> None:
        while room.milestones:
            m = room.milestones.pop()
            if m == "learned_name":
                self.db.update_pet(room.pet["id"], flags=room.pet["flags"])
                notes = self.grant_xp(room.pet["id"], LEARNED_NAME_XP)
                for n in notes:
                    self.notify_user(room.pet["owner_id"], {"type": "notice", "text": n})
                self.broadcast({"type": "pets", "pets": self.pets_public()})

    def _publish(self, s: Session) -> None:
        brains = s.brains()
        bins = [struct.pack("<I", i) + b.take_spikes() for i, b in enumerate(brains)]
        if s.kind == "pet":
            room = s.obj
            body = room.snapshot()
            events, room.events = room.events, []
            t = room.t
        else:
            b = s.obj
            body = b.snapshot()
            body["fighters"] = [{"emotions": f.brain.emo_state, "readouts": {k: round(v, 1) for k, v in f.brain.motor.items()}} for f in b.fighters]
            body["fx"], b.fx = b.fx, []
            events, b.events = b.events, []
            t = b.t
        sps = sum(s.sps) / (len(s.sps) * TICK_S) if s.sps else 0
        s.frame = {"type": "frame", "channel": s.key, "kind": s.kind, "t": round(t, 2), "speed": round(self.speed, 2),
                   "spikes_per_s": int(sps), "active": int(sum(len(x) // 4 - 1 for x in bins)), "events": events} | body
        s.bins = bins
        s.frame_id += 1

    def run_forever(self) -> None:
        self._running = True
        next_t = time.perf_counter()
        last_pub = 0.0
        sim_acc = wall_acc = 0.0
        while self._running:
            t0 = time.perf_counter()
            with self.lock:
                live = list(self.sessions.values())
            for s in live:
                if s.ended_at is not None:
                    continue
                s.obj.tick(TICK_S)
                s.sps.append(sum(b.spikes_last for b in s.brains()))
                if s.kind == "pet":
                    self._milestones(s.obj)
                elif s.obj.finished:
                    self._publish(s)
                    self._finish_battle(s)
            if live:
                sim_acc += TICK_S
                wall_acc += time.perf_counter() - t0
                if sim_acc >= 1.0:
                    self.speed = sim_acc / max(wall_acc, 1e-6)
                    sim_acc = wall_acc = 0.0
            now = time.perf_counter()
            if now - last_pub >= FRAME_S:
                for s in live:
                    if s.ended_at is None:
                        self._publish(s)
                last_pub = now
                self._housekeeping()
            next_t += TICK_S
            delay = next_t - time.perf_counter()
            if delay > 0:
                time.sleep(delay)
            elif delay < -0.25:
                next_t = time.perf_counter()

    def _housekeeping(self) -> None:
        now = time.time()
        changed = False
        with self.lock:
            for key, s in list(self.sessions.items()):
                if s.kind == "pet":
                    room = s.obj
                    idle = s.viewers == 0 and now - room.last_viewed > ROOM_IDLE_S
                    if idle or now - room.last_save > SAVE_EVERY_S:
                        self.db.update_pet(room.pet["id"], memory=room.memory())
                        room.last_save = now
                    if idle:
                        del self.sessions[key]
                        changed = True
                elif s.ended_at is not None and now - s.ended_at > BATTLE_LINGER_S:
                    del self.sessions[key]
                    changed = True
        if changed:
            self.broadcast_lists()

    def save_all(self) -> None:
        with self.lock:
            for s in self.sessions.values():
                if s.kind == "pet":
                    self.db.update_pet(s.obj.pet["id"], memory=s.obj.memory())

    def stop(self) -> None:
        self._running = False
        self.save_all()
