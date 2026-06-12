"""The eight playable races, Moria-style: stat mods, hit dice, XP factors, traits.

Traits:
    stealth         monsters wake less often
    slow_digestion  food clock ticks at half speed
    keen_eyes       larger sight radius in the dark, better searching
    levitate        floats over floor traps
    poison_immune   immune to poison (snakes, gas, potions)
    regen           regenerates hit points faster
    gore            +2 melee damage (horns)
    magic_resist    +3 on saving throws, half damage from poison potions
    corpse_eater    feeds on the slain (gains food on killing living monsters)
    cantrip         innate Sunfire Cantrip, castable at no mana cost
    perception      may passively notice hidden traps nearby
    bowmaster       +2 to hit and +2 damage with bows
    charge          the 'c' command: rush a foe in a straight line
    labyrinth_sense always knows the compass direction of the exit
    diseased_bite   melee wounds may fester, rotting living foes
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Race:
    name: str
    desc: str
    str_mod: int
    int_mod: int
    wis_mod: int
    dex_mod: int
    con_mod: int
    cha_mod: int
    hit_die: int
    xp_mult: float
    traits: frozenset
    infravision: int = 0  # radius in tiles at which warm bodies glow in the dark


RACES = [
    Race("Human", "Adaptable and ambitious; the measure of all things.",
         0, 0, 0, 0, 0, 1, 8, 1.00, frozenset({"ambitious"})),
    Race("Hobbit", "Small, nimble and quiet, with sharp eyes and a full pantry.",
         -2, 1, 1, 3, 1, 1, 6, 1.10,
         frozenset({"stealth", "slow_digestion", "keen_eyes"})),
    Race("Wood-Elf", "Children of the forest; swift, wise and keen of sight.",
         -1, 1, 1, 2, -1, 1, 7, 1.20,
         frozenset({"keen_eyes", "stealth", "perception", "bowmaster",
                    "beast_friend", "taming"})),
    Race("Sun-Elf", "High elves of the light, steeped in lore and grace.",
         -1, 2, 2, 1, -1, 2, 6, 1.30,
         frozenset({"magic_resist", "keen_eyes", "cantrip"})),
    Race("Dark-Elf", "Dwellers in the deep places, seeing where others are blind.",
         0, 1, 0, 2, -1, -1, 6, 1.25, frozenset({"stealth"}), infravision=6),
    Race("Minotaur", "A horned mountain of muscle bred for the labyrinth.",
         4, -2, -1, -1, 2, -2, 12, 1.30,
         frozenset({"gore", "charge", "labyrinth_sense"}), infravision=2),
    Race("Fairy", "A flickering mote of wing and mischief, hard to hit, easy to break.",
         -4, 2, 1, 4, -2, 2, 4, 1.40,
         frozenset({"levitate", "stealth"})),
    Race("Ghoul", "A grave-cold thing that hungers; the dead do not poison the dead.",
         1, -2, -1, -1, 3, -4, 9, 1.35,
         frozenset({"poison_immune", "regen", "corpse_eater", "slow_digestion",
                    "diseased_bite"}),
         infravision=3),
]


def mods_summary(r):
    parts = []
    for label, v in (("St", r.str_mod), ("In", r.int_mod), ("Wi", r.wis_mod),
                     ("Dx", r.dex_mod), ("Co", r.con_mod), ("Ch", r.cha_mod)):
        parts.append(f"{label}{v:+d}")
    return " ".join(parts)
