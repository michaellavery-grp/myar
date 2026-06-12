"""Monsters of the deep, plus the bosses that hold court every five levels.

Flags:
    erratic   moves randomly half the time
    poison    melee may sap strength
    regen     regains 1 HP per turn
    undead    a ghoul gains no meal from these
    mindless  immune to phantasms and illusions
    pack      spawns with friends
    gold      carries a hoard
    boss      a guardian of the stairs
    humanoid  may drop a weapon, gold or gear when slain
              (beasts and the like instead may drop skin, teeth or hide)
    fangs     sharp teeth — an independent chance to drop monster teeth,
              stacking with every other drop
"""

import random
from dataclasses import dataclass, field

from .rng import roll


@dataclass(frozen=True)
class MonsterType:
    name: str
    ch: str
    level: int
    hp: str
    ac: int
    dmg: str
    xp: int
    min_depth: int
    max_depth: int
    flags: frozenset = field(default_factory=frozenset)
    genus: str = ""   # canine, feline, cervine, boar, ... (tameable beasts)
    diet: str = ""    # carnivore, omnivore, herbivore


def _f(*flags):
    return frozenset(flags)


MONSTERS = [
    MonsterType("giant rat", "r", 1, "1d6", 11, "1d3", 2, 1, 6, _f("fangs")),
    MonsterType("bat", "b", 1, "1d8", 13, "1d2", 3, 1, 8,
                _f("erratic", "fangs")),
    MonsterType("kobold", "k", 1, "1d8", 12, "1d4", 4, 1, 7,
                _f("humanoid", "fangs")),
    MonsterType("jackal", "j", 1, "1d4", 12, "1d2", 2, 1, 6,
                _f("pack", "fangs")),
    MonsterType("snake", "s", 2, "2d6", 13, "1d3", 9, 2, 11,
                _f("poison", "fangs")),
    MonsterType("goblin", "g", 2, "2d8", 13, "1d6", 12, 2, 12,
                _f("humanoid", "fangs")),
    MonsterType("orc", "o", 3, "3d8", 14, "1d8", 20, 3, 16,
                _f("gold", "humanoid", "fangs")),
    MonsterType("zombie", "z", 3, "3d8", 11, "1d8", 17, 4, 16,
                _f("undead", "mindless")),
    MonsterType("skeleton", "S", 2, "2d8", 12, "1d6", 14, 2, 20,
                _f("undead", "mindless")),
    MonsterType("hobgoblin", "H", 4, "4d8", 14, "2d4", 30, 5, 18,
                _f("humanoid", "fangs")),
    MonsterType("giant centipede", "c", 4, "3d6", 15, "1d3", 25, 5, 18,
                _f("poison")),
    MonsterType("wight", "W", 5, "5d8", 15, "1d8", 45, 7, 22, _f("undead")),
    MonsterType("ogre", "O", 6, "6d8", 14, "2d6", 70, 8, 26,
                _f("gold", "humanoid", "fangs")),
    MonsterType("cave troll", "T", 7, "7d8", 15, "2d8", 110, 10, 34,
                _f("regen", "humanoid", "fangs")),
    MonsterType("wraith", "w", 8, "8d8", 16, "1d10", 150, 12, 40, _f("undead")),
    MonsterType("vampire", "V", 9, "9d8", 17, "2d8", 220, 14, 48,
                _f("undead", "regen", "fangs")),
    MonsterType("stone giant", "P", 10, "10d8", 16, "3d6", 280, 15, 55,
                _f("gold", "humanoid")),
    MonsterType("lich", "L", 11, "10d8", 18, "2d10", 380, 22, 70,
                _f("undead")),
    MonsterType("fire drake", "d", 11, "10d10", 18, "3d8", 420, 25, 75,
                _f("fangs")),
    MonsterType("balrog", "B", 13, "13d8", 18, "3d8", 600, 30, 85, _f()),
    MonsterType("greater demon", "&", 14, "14d8", 19, "3d10", 750, 40, 99,
                _f("fangs")),
    MonsterType("ancient dragon", "D", 15, "14d10", 19, "4d8", 900, 50, 99,
                _f("gold", "fangs")),
    MonsterType("titan", "P", 16, "16d10", 20, "4d10", 1200, 60, 99,
                _f("gold", "humanoid")),
]

# One boss per five levels of depth; index = depth // 5 - 1. Final boss at 99.
BOSS_NAMES = [
    ("Grip, the Warg Chieftain", "j"),
    ("Boldor, King of the Yeeks", "k"),
    ("Grishnakh, the Hill Orc", "o"),
    ("The Barrow-Wight King", "W"),
    ("Gorbag of Minas Morgul", "o"),
    ("Bert the Stone Troll", "T"),
    ("Ulfang the Black", "H"),
    ("The Ogre Tyrant", "O"),
    ("Shelob's Last Daughter", "c"),
    ("The Balrog of Moria", "B"),
    ("Khamul, the Easterling", "w"),
    ("Itangast the Fire Drake", "d"),
    ("The Witch-King's Herald", "w"),
    ("Vlad, Sire of the Night", "V"),
    ("The Stone Titan", "P"),
    ("Maeglor the Lich-Lord", "L"),
    ("Glaurung, Father of Dragons", "D"),
    ("Gothmog, High Captain of Balrogs", "B"),
    ("Ancalagon the Black", "D"),
]

FINAL_BOSS_NAME = "Morgoth, Lord of Darkness"

# Monsters that yield a signature part when slain: name -> (part, chance).
# Skeletons are the one undead exception — bones are the point. Tails drop
# generously so kobold-tail soup stays on the menu.
SPECIAL_PARTS = {
    "giant rat": ("rat tail", 0.75),
    "bat": ("bat eye", 0.60),
    "snake": ("snake venom", 0.60),
    "orc": ("orc ear", 0.60),
    "kobold": ("kobold tail", 0.75),
    "skeleton": ("bone", 0.75),
    "fire drake": ("drake hide", 0.65),
    "ancient dragon": ("dragon hide", 0.65),
    "giant centipede": ("gall gland", 0.60),  # the inkmaker's friend
    # All fowl shed feathers generously — the scribe's first harvest
    "hen": ("feather", 0.75),
    "rooster": ("feather", 0.75),
    "duck": ("feather", 0.75),
    "goose": ("feather", 0.75),
    "cockatrice": ("feather", 0.70),
    "phoenix": ("feather", 0.70),
}


def make_boss(depth):
    """Build the guardian for a boss depth (multiples of 5, plus 99)."""
    if depth >= 99:
        name, ch = FINAL_BOSS_NAME, "M"
    else:
        name, ch = BOSS_NAMES[min(depth // 5 - 1, len(BOSS_NAMES) - 1)]
    level = 2 + depth // 3
    hp = 20 + depth * 4
    ac = min(22, 12 + depth // 7)
    d_n = 2 + depth // 33
    d_s = 4 + depth // 14
    xp = 60 + depth * 45
    return MonsterType(name, ch, level, f"{hp}d1", ac, f"{d_n}d{d_s}", xp,
                       depth, depth, _f("boss", "gold", "regen"))


class Monster:
    def __init__(self, mtype, x, y, depth=None):
        self.type = mtype
        self.x = x
        self.y = y
        depth = depth if depth is not None else mtype.min_depth
        # Out-of-depth scaling keeps old monsters dangerous in the deeps.
        bonus = max(0, depth - mtype.min_depth)
        self.max_hp = roll(mtype.hp) + bonus
        self.hp = self.max_hp
        self.level = mtype.level + bonus // 10
        self.xp = mtype.xp + bonus * 3
        self.asleep = ("boss" not in mtype.flags) and random.random() < 0.5
        self.confused = 0
        self.diseased = False
        self.attitude = "hostile"   # hostile | wary | friendly
        self.tamed = False
        self.rooted = 0
        self.stuck = 0   # turns a companion has failed to close distance

    @property
    def name(self):
        return self.type.name

    def genus_name(self):
        return self.type.genus or self.type.name

    @property
    def is_boss(self):
        return "boss" in self.type.flags


# Wild, tameable beasts that live in biome rooms (forest / savannah).
# They spawn at any depth and scale with it — a deep wolf is a dire wolf.
ANIMAL_TYPES = {
    "forest": [
        MonsterType("duck", "a", 1, "1d4", 12, "1d2", 2, 1, 99,
                    _f("tameable", "beast"), genus="fowl", diet="omnivore"),
        MonsterType("goose", "a", 1, "1d6", 12, "1d3", 3, 1, 99,
                    _f("tameable", "beast"), genus="fowl", diet="omnivore"),
        MonsterType("phoenix", "a", 8, "6d8", 16, "2d6", 90, 1, 99,
                    _f("tameable", "beast", "regen"),
                    genus="fowl", diet="carnivore"),
        MonsterType("wolf", "C", 2, "2d6", 13, "1d6", 10, 1, 99,
                    _f("tameable", "beast", "pack", "fangs"),
                    genus="canine", diet="carnivore"),
        MonsterType("panther", "f", 3, "3d6", 14, "1d8", 18, 1, 99,
                    _f("tameable", "beast", "fangs"),
                    genus="feline", diet="carnivore"),
        MonsterType("wild boar", "q", 2, "2d8", 12, "1d6", 12, 1, 99,
                    _f("tameable", "beast", "fangs"),  # tusks count
                    genus="boar", diet="omnivore"),
        MonsterType("stag", "q", 2, "2d6", 13, "1d4", 8, 1, 99,
                    _f("tameable", "beast"), genus="cervine", diet="herbivore"),
    ],
    "savannah": [
        MonsterType("hen", "a", 1, "1d4", 12, "1d2", 2, 1, 99,
                    _f("tameable", "beast"), genus="fowl", diet="herbivore"),
        MonsterType("rooster", "a", 1, "1d6", 12, "1d3", 3, 1, 99,
                    _f("tameable", "beast"), genus="fowl", diet="omnivore"),
        MonsterType("cockatrice", "a", 4, "3d8", 14, "1d6", 35, 1, 99,
                    _f("tameable", "beast", "poison"),
                    genus="fowl", diet="carnivore"),
        MonsterType("lion", "f", 5, "4d8", 14, "2d6", 40, 1, 99,
                    _f("tameable", "beast", "fangs"),
                    genus="feline", diet="carnivore"),
        MonsterType("hyena", "C", 3, "3d6", 13, "1d6", 16, 1, 99,
                    _f("tameable", "beast", "pack", "fangs"),
                    genus="canine", diet="carnivore"),
        MonsterType("antelope", "q", 2, "2d6", 14, "1d4", 8, 1, 99,
                    _f("tameable", "beast"), genus="cervine", diet="herbivore"),
    ],
}


def make_animal(biome, depth):
    """A wild animal for a biome room; peaceful unless it eats meat."""
    mtype = random.choice(ANIMAL_TYPES[biome])
    m = Monster(mtype, 0, 0, depth)
    m.asleep = False
    m.attitude = ("friendly" if mtype.diet in ("omnivore", "herbivore")
                  else "wary")
    return m


def choose_type(depth):
    pool = [m for m in MONSTERS if m.min_depth <= depth <= m.max_depth]
    if not pool:
        pool = sorted(MONSTERS, key=lambda m: abs(m.min_depth - depth))[:4]
    return random.choice(pool)
