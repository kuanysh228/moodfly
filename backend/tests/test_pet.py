import numpy as np

from moodfly.connectome import CATEGORICAL, Connectome
from moodfly.genome import Genome, base_stats, combat, stats
from moodfly.speech import Speech, words_of


def orn_connectome(n_types: int = 40, per_type: int = 20) -> Connectome:
    n = n_types * per_type
    names = {c: np.array(["x"]) for c in CATEGORICAL}
    names["cell_class"] = np.array(["olfactory"])
    names["cell_type"] = np.array([f"ORN_G{i:02d}" for i in range(n_types)])
    codes = {c: np.full(n, -1, np.int32) for c in CATEGORICAL}
    codes["cell_class"][:] = 0
    codes["cell_type"] = np.repeat(np.arange(n_types, dtype=np.int32), per_type)
    return Connectome(
        root_ids=np.arange(n, dtype=np.int64), indptr=np.zeros(n + 1, np.int64), indices=np.zeros(0, np.int32),
        syn=np.zeros(0, np.int16), pos=np.zeros((n, 3), np.float32), codes=codes, names=names,
    )


def test_word_codes_are_stable_and_similar_words_overlap():
    sp = Speech(orn_connectome())
    assert sp.glomeruli("Муся") == sp.glomeruli("муся!")
    musya, musik, window = set(sp.glomeruli("муся")), set(sp.glomeruli("мусик")), set(sp.glomeruli("окно"))
    assert len(musya & musik) >= 3
    assert len(musya & musik) > len(musya & window)
    assert 3 <= len(sp.glomeruli("я")) <= 8


def test_speech_queue_presents_words_in_order():
    sp = Speech(orn_connectome())
    assert words_of("Муся, иди сюда!") == ["муся", "иди", "сюда"]
    sp.say("Муся иди")
    heard = []
    for _ in range(200):
        w, idx, _t = sp.step(0.02)
        if w and (not heard or heard[-1] != w):
            heard.append(w)
            assert len(idx) > 0
    assert heard == ["муся", "иди"]


def test_mutations_raise_body_stats_only():
    g = Genome.random(123)
    check = {"escape_latency_ms": 9, "giant_fiber_hz": 80.0, "fear": 0.38, "irritation": 0.30, "groom_hz": 14.0, "mn9_hz": 10.0, "appetite": 0.28}
    ref = {k: (v, 1.0) for k, v in check.items()}
    base = base_stats(g, check, ref)
    up = stats(g, check, ref, {"strength": 2, "speed": 1})
    assert up["strength"] == min(100, base["strength"] + 6)
    assert up["speed"] == min(100, base["speed"] + 3)
    assert up["courage"] == base["courage"]
    assert combat(up)["damage"] > combat(base)["damage"]
