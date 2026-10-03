from dataclasses import dataclass, field

import numpy as np

from .connectome import Connectome

SHIU_SUGAR = [
    720575940624963786, 720575940630233916, 720575940637568838, 720575940638202345, 720575940617000768,
    720575940630797113, 720575940632889389, 720575940621754367, 720575940621502051, 720575940640649691,
    720575940639332736, 720575940616885538, 720575940639198653, 720575940620900446, 720575940617937543,
    720575940632425919, 720575940633143833, 720575940612670570, 720575940628853239, 720575940629176663,
    720575940611875570, 720575940620589838, 720575940631147148, 720575940608305161, 720575940629388135,
    720575940630968335, 720575940606801282, 720575940617398502, 720575940616167218, 720575940620296641,
    720575940627961104,
]


@dataclass
class Group:
    key: str
    label: str
    idx: np.ndarray = field(repr=False)

    def __len__(self) -> int:
        return len(self.idx)


def _sides(c: Connectome, idx: np.ndarray) -> dict[str, np.ndarray]:
    side = c.label("side")[idx]
    return {"left": idx[side == "left"], "right": idx[side == "right"]}


def sensory_groups(c: Connectome) -> dict[str, Group]:
    sugar = np.union1d(c.where("cell_sub_class", ["sugar", "sugar/low_salt"]), c.by_root_id(SHIU_SUGAR))
    looming = np.union1d(c.where("cell_type", ["LPLC2"]), c.where("cell_type", ["LC4"]))
    loom_sides = _sides(c, looming)
    wind = np.union1d(c.where_prefix("cell_type", ["JO-C", "JO-E"]), c.where_prefix("cell_type", ["JO-F"]))
    groups = [
        Group("sugar", "Сахарные GRN (хоботок)", sugar),
        Group("bitter", "Горькие GRN", c.where("cell_sub_class", ["bitter"])),
        Group("water", "Водные GRN", c.where("cell_sub_class", ["water"])),
        Group("wind", "Джонстонов орган (антенны)", wind),
        Group("loom_left", "LPLC2/LC4 — угроза слева", loom_sides["left"]),
        Group("loom_right", "LPLC2/LC4 — угроза справа", loom_sides["right"]),
        Group("light", "Фоторецепторы R1–R8", c.where("cell_type", ["R1-6", "R7", "R8"])),
        Group("odor_good", "ORN уксуса (DM1, DM4, DP1m)", c.where("cell_type", ["ORN_DM1", "ORN_DM4", "ORN_DP1m"])),
        Group("odor_bad", "ORN геосмина/CO₂ (DA2, V)", c.where("cell_type", ["ORN_DA2", "ORN_V"])),
        Group("bristle", "Механорецепторы щетинок головы", c.where("cell_sub_class", ["head bristle", "eye bristle"])),
    ]
    return {g.key: g for g in groups}


def readout_groups(c: Connectome) -> dict[str, Group]:
    turn = _sides(c, c.where("cell_type", ["DNa01", "DNa02"]))
    groups = [
        Group("mn9", "MN9 — хоботок (питание)", c.where("cell_type", ["CB0701"])),
        Group("giant_fiber", "DNp01 — гигантское волокно", c.where("cell_type", ["DNp01"])),
        Group("escape_dn", "DNp02/04/11 — побег", c.where("cell_type", ["DNp02", "DNp04", "DNp11"])),
        Group("mdn", "MDN — задний ход", c.where("cell_type", ["MDN"])),
        Group("walk", "DNp09 — шаг вперёд", c.where("cell_type", ["DNp09"])),
        Group("turn_left", "DNa01/02 L — поворот", turn["left"]),
        Group("turn_right", "DNa01/02 R — поворот", turn["right"]),
        Group("groom", "aDN/aBN — груминг антенн", c.where("cell_type", ["DNg62", "DNge078", "SAD093"])),
        Group("pam", "PAM — дофамин «награда»", c.where_prefix("cell_type", ["PAM"])),
        Group("ppl1", "PPL1 — дофамин «наказание»", c.where_prefix("cell_type", ["PPL1"])),
        Group("octopamine", "OA — октопамин (возбуждение)", c.where_prefix("cell_type", ["OA-"])),
        Group("mbon", "MBON — выход грибовидного тела", c.where("cell_class", ["MBON"])),
    ]
    return {g.key: g for g in groups}
