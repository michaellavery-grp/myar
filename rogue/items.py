"""Items: potions, scrolls, weapons, armor, food, gold and the Amulet."""

import random
from dataclasses import dataclass, field

from .rng import roll, chance

SYMBOLS = {
    "potion": "!", "scroll": "?", "weapon": ")", "armor": "]",
    "food": "%", "gold": "*", "amulet": ",", "material": "~", "bag": "&",
}

# Crafting ingredients harvested from slain monsters.
MATERIALS = ("skin", "teeth", "hide", "bat eye", "snake venom", "rat tail",
             "orc ear", "kobold tail", "bone", "drake hide", "dragon hide")

# Any two of these small parts make a portion of pet food — pets aren't picky.
PET_SCRAPS = ("bat eye", "rat tail", "bone", "orc ear", "kobold tail")

# Ingredient keys are material subtypes, "<kind>:<subtype>" to consume a
# carried item (e.g. "potion:poison", "armor:leather armor"), or
# "any:a|b|c" to accept a mix drawn from several materials.
# What a crafting table ('=') can make: (name, {ingredient: count}, result-key)
RECIPES = [
    ("leather armor", {"skin": 3}, "armor:leather armor"),
    ("hide armor", {"hide": 3}, "armor:hide armor"),
    ("studded leather", {"armor:leather armor": 1, "teeth": 4},
     "armor:studded leather"),
    ("bone armor", {"bone": 6, "hide": 2}, "armor:bone armor"),
    ("drake-scale armor", {"drake hide": 4}, "armor:drake-scale armor"),
    ("dragon-scale armor", {"dragon hide": 4}, "armor:dragon-scale armor"),
    ("short bow", {"hide": 1, "teeth": 2}, "weapon:short bow"),
    ("long bow", {"hide": 2, "teeth": 3}, "weapon:long bow"),
    ("fine arrows (+1 bow dmg)", {"teeth": 3, "skin": 1}, "arrows"),
    ("vial of poison", {"snake venom": 2, "rat tail": 1}, "potion:poison"),
    ("poison arrows (8 shots)",
     {"potion:poison": 1, "teeth": 2, "bat eye": 1}, "poison_arrows"),
    ("savage brew (strength)", {"orc ear": 3, "snake venom": 1},
     "potion:gain strength"),
    ("kobold-tail soup", {"kobold tail": 2, "rat tail": 1}, "food:ration"),
    ("pet food (any 2 small parts)",
     {"any:" + "|".join(PET_SCRAPS): 2}, "food:pet food"),
]

WEAPON_DEFS = {
    "whip": "1d3",
    "dagger": "1d4",
    "short bow": "1d6",
    "short sword": "1d6",
    "mace": "2d4",
    "long bow": "1d8",
    "long sword": "3d4",
    "battle axe": "1d8",
    "two-handed sword": "4d4",
}

# Bows fire with 'f'; swung in melee they're just an awkward club.
RANGED = {"short bow", "long bow"}

ARMOR_DEFS = {
    "leather armor": 2,
    "hide armor": 3,
    "ring mail": 3,
    "studded leather": 4,
    "scale mail": 4,
    "bone armor": 5,
    "chain mail": 5,
    "splint mail": 6,
    "plate mail": 7,
    "drake-scale armor": 8,
    "dragon-scale armor": 9,
}

# Armors found as dungeon loot; the scale/bone tiers are craft-only.
LOOT_ARMORS = ["leather armor", "hide armor", "ring mail", "scale mail",
               "chain mail", "splint mail", "plate mail"]

POTION_SUBTYPES = [
    "healing", "extra healing", "gain strength", "poison",
    "haste self", "restore strength",
]
POTION_WEIGHTS = [30, 12, 12, 12, 10, 10]

SCROLL_SUBTYPES = [
    "magic mapping", "teleportation", "enchant weapon",
    "enchant armor", "identify", "light",
]
SCROLL_WEIGHTS = [12, 12, 12, 12, 22, 12]

POTION_COLORS = [
    "ruby", "azure", "murky", "smoky", "emerald", "amber",
    "violet", "inky", "milky", "golden", "crimson", "viscous",
]

_SYLLABLES = ["zel", "gor", "nym", "ash", "ka", "drel", "ix", "mor", "thu",
              "vae", "qua", "lor", "ne", "pha", "rog", "ulm", "yth", "bar"]


def random_scroll_title():
    n = random.randint(2, 4)
    return " ".join(
        "".join(random.choice(_SYLLABLES)
                for _ in range(random.randint(1, 2))).upper()
        for _ in range(n))


@dataclass
class Item:
    kind: str
    subtype: str
    dmg: str = ""
    ac: int = 0
    hit_ench: int = 0
    dmg_ench: int = 0
    ac_ench: int = 0
    count: int = 1
    letter: str = ""
    poison_charges: int = 0  # envenomed shots remaining (bows)
    contents: dict = field(default_factory=dict)  # crafting bag innards

    @property
    def symbol(self):
        return SYMBOLS[self.kind]

    def stacks_with(self, other):
        if self.kind != other.kind or self.subtype != other.subtype:
            return False
        return self.kind in ("potion", "scroll", "food", "material")


def make_weapon(subtype, hit_ench=0, dmg_ench=0):
    return Item("weapon", subtype, dmg=WEAPON_DEFS[subtype],
                hit_ench=hit_ench, dmg_ench=dmg_ench)


def make_armor(subtype, ac_ench=0):
    return Item("armor", subtype, ac=ARMOR_DEFS[subtype], ac_ench=ac_ench)


def make_food(count=1):
    return Item("food", "ration", count=count)


def make_material(subtype, count=1):
    return Item("material", subtype, count=count)


def make_bag():
    return Item("bag", "crafting bag")


def make_pet_food(count=1):
    return Item("food", "pet food", count=count)


def _avg_dmg(spec):
    n, _, rest = spec.partition("d")
    d = int(rest.split("+")[0].split("-")[0])
    return int(n) * (d + 1) / 2


def item_value(item):
    """Base gold value of one unit, for trading."""
    if item.kind == "potion":
        return 60
    if item.kind == "scroll":
        return 90
    if item.kind == "food":
        return 30
    if item.kind == "material":
        return {"snake venom": 30, "bat eye": 20, "rat tail": 10,
                "orc ear": 12, "kobold tail": 10, "bone": 10,
                "drake hide": 60, "dragon hide": 120}.get(item.subtype, 15)
    if item.kind == "weapon":
        ench = item.hit_ench + item.dmg_ench
        return max(5, int(30 + _avg_dmg(item.dmg) * 15 + ench * 60))
    if item.kind == "armor":
        return max(5, item.ac * 35 + item.ac_ench * 60)
    return 0  # the Amulet is not for sale


def make_amulet():
    return Item("amulet", "amulet")


def make_gold(depth, rich=False):
    value = roll("2d8") * (depth + 2)
    if rich:
        value = int(value * 1.3)
    return Item("gold", "gold", count=max(2, value))


def rand_item(depth):
    """Random non-gold item appropriate-ish for the depth."""
    r = random.random()
    if r < 0.30:
        sub = random.choices(POTION_SUBTYPES, POTION_WEIGHTS)[0]
        return Item("potion", sub)
    if r < 0.60:
        sub = random.choices(SCROLL_SUBTYPES, SCROLL_WEIGHTS)[0]
        return Item("scroll", sub)
    if r < 0.76:
        return make_food()
    if r < 0.88:
        names = list(WEAPON_DEFS)
        # deeper levels skew toward the back of the list
        idx = min(len(names) - 1,
                  int(random.random() * (2 + depth / 12)) + random.randint(0, 2))
        ench = (1 if chance(0.25) else 0) + (1 if depth > 25 and chance(0.3) else 0)
        cursed = -1 if chance(0.08) else 0
        return make_weapon(names[idx], hit_ench=ench + cursed, dmg_ench=ench)
    names = LOOT_ARMORS
    idx = min(len(names) - 1,
              int(random.random() * (1 + depth / 14)) + random.randint(0, 2))
    ench = (1 if chance(0.25) else 0) + (1 if depth > 25 and chance(0.3) else 0)
    cursed = -1 if chance(0.08) else 0
    return make_armor(names[idx], ac_ench=ench + cursed)
