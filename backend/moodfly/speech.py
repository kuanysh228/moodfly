import hashlib
import re
from collections import deque
from dataclasses import dataclass

import numpy as np

from .connectome import Connectome

MIN_GLOMERULI, MAX_GLOMERULI = 3, 8
WORD_HZ = 100.0
WORD_S = 0.8
GAP_S = 0.4
MAX_WORDS = 6
RESERVED = {"ORN_DM1", "ORN_DM4", "ORN_DP1m", "ORN_DA2", "ORN_V", "ORN_DA1"}


def normalize(word: str) -> str:
    return re.sub(r"[^\w-]", "", word.lower().replace("ё", "е"))


def words_of(text: str) -> list[str]:
    return [w for w in (normalize(t) for t in text.split()) if w][:MAX_WORDS]


@dataclass
class Heard:
    word: str
    t_left: float
    gap: bool = False


class Speech:
    def __init__(self, conn: Connectome):
        self.conn = conn
        types = conn.label("cell_type")[conn.where("cell_class", ["olfactory"])]
        names, counts = np.unique(types, return_counts=True)
        self.pool = [n for n, c in zip(names, counts) if n.startswith("ORN_") and c >= 15 and n not in RESERVED]
        self.queue: deque[Heard] = deque()
        self.current: Heard | None = None
        self._cache: dict[str, np.ndarray] = {}

    def _slot(self, token: str) -> str:
        return self.pool[int.from_bytes(hashlib.sha256(token.encode()).digest()[:8], "little") % len(self.pool)]

    def glomeruli(self, word: str) -> list[str]:
        w = f"^{normalize(word)}$"
        out: list[str] = []
        for i in range(len(w) - 1):
            g = self._slot(w[i : i + 2])
            if g not in out:
                out.append(g)
        salt = 0
        while len(out) < MIN_GLOMERULI:
            g = self._slot(f"{w}#{salt}")
            salt += 1
            if g not in out:
                out.append(g)
        return out[:MAX_GLOMERULI]

    def neurons(self, word: str) -> np.ndarray:
        if word not in self._cache:
            self._cache[word] = self.conn.where("cell_type", self.glomeruli(word))
        return self._cache[word]

    def say(self, text: str) -> list[str]:
        words = words_of(text)
        for w in words:
            self.queue.append(Heard(w, WORD_S))
            self.queue.append(Heard(w, GAP_S, gap=True))
        return words

    def step(self, dt: float) -> tuple[str | None, np.ndarray | None, float]:
        if self.current is None or self.current.t_left <= 0:
            self.current = self.queue.popleft() if self.queue else None
        if self.current is None:
            return None, None, 0.0
        self.current.t_left -= dt
        if self.current.gap:
            return None, None, 0.0
        return self.current.word, self.neurons(self.current.word), WORD_S - self.current.t_left
