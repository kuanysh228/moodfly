import pytest

from moodfly.paths import BRAIN_NPZ

pytestmark = pytest.mark.skipif(not BRAIN_NPZ.exists(), reason="run scripts/fetch_data.py and moodfly-build first")

SEED = 12345


@pytest.fixture(scope="module")
def kit():
    from moodfly.flybrain import Kit

    return Kit()


def run(fb, seconds, drive=None, reward_at=None) -> float:
    peak = 0.0
    for i in range(int(seconds / 0.02)):
        if reward_at is not None and i == int(reward_at / 0.02):
            fb.reward(1.0)
        fb.tick(drive or {})
        if abs(fb.recognition) > abs(peak):
            peak = fb.recognition
    return peak


def say(fb, word, reward_at=None) -> float:
    fb.speech.say(word)
    peak = run(fb, 2.5, reward_at=reward_at)
    run(fb, 1.0)
    return peak


def test_odour_alone_does_not_teach(kit):
    from moodfly.flybrain import FlyBrain

    fb = FlyBrain(kit, SEED)
    run(fb, 3.0)
    run(fb, 10.0, {"odor_good": 90})
    assert fb.mb.strength < 0.005
    assert abs(fb.mb.learned_value(fb.rate)) < 0.05


def test_reward_teaches_the_name_and_extinction_undoes_it(kit):
    from moodfly.flybrain import FlyBrain

    fb = FlyBrain(kit, SEED)
    run(fb, 3.0)
    trained = [say(fb, "кузя", reward_at=0.3) for _ in range(4)]
    assert trained[-1] > 0.6
    assert abs(say(fb, "окно")) < 0.15

    ext = [say(fb, "кузя") for _ in range(10)]
    assert ext[0] > 0.5
    assert ext[-1] < 0.3


def test_drinking_sugar_rewards_the_word_just_heard(kit):
    from moodfly.room import PetRoom

    room = PetRoom(kit, {"id": 0, "name": "Кузя", "owner_id": 0, "flags": {}, "genome": {"seed": SEED, "learning": 1.0}})
    for _ in range(100):
        room.tick()
    w, fb = room.world, room.brain
    rewarded, peaks = 0, []
    for _ in range(5):
        w.items.clear()
        w.place("sugar", *w.fly.head)
        fb.speech.say("кузя")
        for _ in range(100):
            room.tick()
            rewarded += fb.reward_t > 0
        w.items.clear()
        for _ in range(100):
            room.tick()
        peaks.append(say(fb, "кузя"))
    assert rewarded > 100
    assert any("Сладко" in e["text"] for e in room.events)
    assert peaks[-1] > 0.3
