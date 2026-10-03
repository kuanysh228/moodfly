import queue
import time
from collections import OrderedDict

from .flybrain import FlyBrain, Kit
from .speech import normalize
from .world import World

LEARNED_NAME_AT = 0.6
LEARNED_NAME_XP = 25
SAVE_EVERY_S = 30.0
SWEET_REWARD_S = 0.3
OWNER_ONLY = {"reward", "punish", "opto", "reset", "place", "remove", "clear", "threat", "puff", "background"}


class PetRoom:
    def __init__(self, kit: Kit, pet: dict):
        self.kit = kit
        self.pet = pet
        g = pet["genome"]
        self.brain = FlyBrain(kit, g["seed"], g["learning"], pet.get("memory"))
        self.world = World()
        self.cmds: queue.Queue = queue.Queue()
        self.events: list[dict] = []
        self.t = 0.0
        self.words: OrderedDict[str, float] = OrderedDict()
        self._peak: tuple[str, float] | None = None
        self._sweet = False
        self.last_viewed = time.time()
        self.last_save = time.time()
        self.milestones: list[str] = []

    @property
    def name_key(self) -> str:
        return normalize(self.pet["name"])

    def log(self, text: str) -> None:
        self.events.append({"t": round(self.t, 1), "text": text})

    def submit(self, cmd: dict, is_owner: bool) -> None:
        if cmd.get("type") in OWNER_ONLY and not is_owner:
            return
        self.cmds.put(cmd)

    def _handle(self, cmd: dict) -> None:
        kind, w, fb = cmd.get("type"), self.world, self.brain
        if kind == "say":
            text = str(cmd.get("text", ""))[:200]
            words = fb.speech.say(text)
            if words:
                self.log(f"{cmd.get('who', '?')}: «{text}»")
        elif kind == "reward":
            fb.reward(1.0)
            self.log("Награда: дофамин PAM (1 с)")
        elif kind == "punish":
            fb.punish(1.0)
            self.log("Наказание: дофамин PPL1 (1 с)")
        elif kind == "place":
            w.place(str(cmd.get("kind")), float(cmd["x"]), float(cmd["y"]))
        elif kind == "remove":
            w.remove_near(float(cmd["x"]), float(cmd["y"]))
        elif kind == "clear":
            w.items.clear()
        elif kind == "threat":
            w.start_threat(float(cmd["x"]), float(cmd["y"]))
            self.log("Тень приближается (лупинг)")
        elif kind == "puff":
            w.puff()
            self.log("Дуновение воздуха на антенны")
        elif kind == "touch":
            w.touch()
            self.log("Касание щетинок головы")
        elif kind == "background":
            fb.background = bool(cmd.get("on"))
        elif kind == "opto":
            mode = cmd.get("mode")
            if mode == "clear":
                fb.opto.clear()
                self.log("Оптогенетика выключена")
            else:
                ct = str(cmd.get("cell_type", "")).strip()
                hz = max(0.0, min(300.0, float(cmd.get("hz", 100))))
                n = fb.set_opto(ct, mode, hz)
                if not n:
                    self.log(f"Тип клеток «{ct}» не найден")
                elif mode != "off":
                    self.log(f"{ct} ({n} нейр.) {'активирован %d Гц' % hz if mode == 'activate' else 'заглушён'}")
        elif kind == "reset":
            fb.brain.reset()
            fb.rate[:] = 0
            fb.opto.clear()
            self.world = World()
            self.log("Сброс тела и активности (память сохранена)")

    def tick(self, dt: float = 0.02) -> None:
        while not self.cmds.empty():
            self._handle(self.cmds.get_nowait())
        self.t += dt
        fb = self.brain
        fb.tick(self.world.sensory_drive(), dt * 1000)
        for text in self.world.step(dt, fb.motor, fb.emotion_input(), fb.recognition, fb.word):
            self.log(text)
        self._taste()
        self._track_words()

    def _taste(self) -> None:
        w = self.world
        sweet = w.fly.mode == "feed" and "sugar" in w.contact
        if sweet:
            self.brain.reward(SWEET_REWARD_S)
            if not self._sweet:
                self.log("Сладко: сахар включает PAM")
        self._sweet = sweet

    def _track_words(self) -> None:
        fb = self.brain
        if fb.word:
            if self._peak is None or self._peak[0] != fb.word:
                self._flush_peak()
                self._peak = (fb.word, fb.recognition)
            elif abs(fb.recognition) > abs(self._peak[1]):
                self._peak = (fb.word, fb.recognition)
        else:
            self._flush_peak()

    def _flush_peak(self) -> None:
        if not self._peak:
            return
        word, value = self._peak
        self._peak = None
        self.words[word] = round(value, 3)
        self.words.move_to_end(word)
        while len(self.words) > 10:
            self.words.popitem(last=False)
        flags = self.pet["flags"]
        if word == self.name_key and value >= LEARNED_NAME_AT and not flags.get("learned_name"):
            flags["learned_name"] = True
            self.milestones.append("learned_name")
            self.log(f"{self.pet['name']} выучила своё имя! +{LEARNED_NAME_XP} XP")

    def snapshot(self) -> dict:
        fb = self.brain
        return {
            "world": self.world.snapshot(),
            "emotions": fb.emo_state,
            "readouts": {k: round(v, 1) for k, v in fb.motor.items()},
            "opto": [{"cell_type": k, "mode": v["mode"], "hz": v["hz"], "n": int(len(v["idx"]))} for k, v in fb.opto.items()],
            "background": fb.background,
            "learning": {
                "hearing": fb.word,
                "recognition": round(fb.recognition, 3),
                "words": [{"word": w, "value": v} for w, v in reversed(self.words.items())],
                "name": self.name_key,
                "memory": round(fb.mb.strength * 100, 2),
                "reward": fb.reward_t > 0,
                "punish": fb.punish_t > 0,
            },
        }

    def memory(self) -> bytes:
        return self.brain.mb.memory()
