import numpy as np

from moodfly.brain import Brain, LIFParams
from moodfly.connectome import Connectome

NAMES = {c: np.array(["x"]) for c in ["super_class", "cell_class", "cell_sub_class", "cell_type", "side", "top_nt", "known_nt"]}


def chain(n: int, syn: int) -> Connectome:
    pre = np.arange(n - 1)
    indptr = np.zeros(n + 1, np.int64)
    indptr[1:n] = np.cumsum(np.bincount(pre, minlength=n - 1))
    indptr[n] = indptr[n - 1]
    return Connectome(
        root_ids=np.arange(n, dtype=np.int64),
        indptr=indptr,
        indices=np.arange(1, n, dtype=np.int32),
        syn=np.full(n - 1, syn, np.int16),
        pos=np.zeros((n, 3), np.float32),
        codes={c: np.full(n, -1, np.int32) for c in NAMES},
        names=NAMES,
    )


def brain(conn, **kw) -> Brain:
    return Brain(conn, LIFParams(**kw), sign_policy="shiu")


def test_poisson_drive_sets_rate():
    b = brain(chain(2, 0))
    b.drive_hz[0] = 100
    b.run(5000)
    rate = b.drain()[0] / 5
    assert 85 < rate < 115


def test_strong_excitation_propagates_and_silence_blocks():
    b = brain(chain(3, 200))
    b.drive_hz[0] = 100
    b.run(1000)
    counts = b.drain()
    assert counts[1] > 20 and counts[2] > 20

    b.reset()
    b.silenced[1] = 1
    b.run(1000)
    counts = b.drain()
    assert counts[0] > 50 and counts[1] == 0 and counts[2] == 0


def test_inhibition_and_no_spontaneous_activity():
    b = brain(chain(2, -200))
    b.drive_hz[0] = 100
    b.run(1000)
    assert b.drain()[1] == 0

    quiet = brain(chain(5, 50))
    quiet.run(1000)
    assert quiet.drain().sum() == 0


def test_adaptation_lowers_sustained_rate():
    rates = []
    for adapt in (0.0, 1.0):
        b = brain(chain(2, 100), adapt_mv=adapt)
        b.drive_hz[0] = 150
        b.run(3000)
        b.drain()
        b.run(1000)
        rates.append(b.drain()[1])
    assert rates[1] < rates[0]
