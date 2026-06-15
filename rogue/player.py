"""The adventurer: stats, inventory, equipment, hunger, mana."""

import random
import string

from .classes import SUN_CANTRIP, DARK_CANTRIP, SCROLL_SPELL_MANA, Spell
from .items import make_weapon, make_armor, make_food, make_bag, Item, RANGED
from .rng import roll

STAT_NAMES = ["Str", "Int", "Wis", "Dex", "Con", "Cha"]
MAX_FOOD = 2000
INV_LIMIT = 23


def _roll_stat(mod):
    """3d6 best-of-two, plus the racial modifier.

    The die caps at 18 on its own; racial bonuses stack past it, so a
    Minotaur can open with Str 22 and a Fairy with Int 20.
    """
    best = max(roll("3d6"), roll("3d6"))
    return max(3, best + mod)


def stat_mod(v):
    return (v - 10) // 2


def roll_stats(race):
    """One full set of ability scores for a race (rerollable at creation)."""
    return {
        "Str": _roll_stat(race.str_mod),
        "Int": _roll_stat(race.int_mod),
        "Wis": _roll_stat(race.wis_mod),
        "Dex": _roll_stat(race.dex_mod),
        "Con": _roll_stat(race.con_mod),
        "Cha": _roll_stat(race.cha_mod),
    }


class Player:
    def __init__(self, name, race, cclass, stats=None):
        self.name = name
        self.race = race
        self.cclass = cclass
        self.stats = dict(stats) if stats else roll_stats(race)
        self.max_str = self.stats["Str"]
        self.level = 1
        self.max_level_reached = 1
        self.exp = 0
        self.gold = 20 + roll("2d20") + self.stats["Cha"]
        self.max_hp = race.hit_die + cclass.hit_die // 2 + max(0, self.mod("Con"))
        self.hp = self.max_hp
        self.food = 1300
        self.x = self.y = 0
        self.inventory = []
        self.weapon = None
        self.armor = None
        self.haste = 0
        self.invis = 0
        self.blessed = 0      # turns of divine favor (+to-hit, +AC)
        self.confused = 0     # turns of staggering (spores, gas)
        self.temp_hp = 0      # transient hit points from prayer
        self.tithe_total = 0  # lifetime gold given to the temples
        self.has_amulet = False
        self.raging = False
        self.craft_level = 1
        self.craft_exp = 0
        self.knows_taming = ("taming" in cclass.traits
                             or "taming" in race.traits)
        self.memorized = []       # scroll-spells held in mind (max 3)
        self.book_studied = True  # False = the book has unstudied changes

        self.max_mana = self._mana_max()
        self.mana = self.max_mana

        w = make_weapon(cclass.start_weapon, hit_ench=1, dmg_ench=1)
        a = make_armor(cclass.start_armor, ac_ench=1)
        self.add_item(w)
        self.add_item(a)
        self.weapon, self.armor = w, a
        self.add_item(make_food(2))
        self.add_item(make_bag())
        for kind, subtype, count in cclass.start_extra:
            for _ in range(count):
                self.add_item(Item(kind, subtype))
        if "bowmaster" in race.traits:
            self.add_item(make_weapon("short bow"))

    # -- derived numbers ---------------------------------------------------

    def mod(self, stat):
        return stat_mod(self.stats[stat])

    def _mana_max(self):
        c = self.cclass
        if not c.mana_stat:
            return 0
        return max(0, int((self.level + self.mod(c.mana_stat)) * c.mana_factor))

    def refresh_mana_cap(self):
        self.max_mana = self._mana_max()
        self.mana = min(self.mana, self.max_mana)

    @property
    def ac(self):
        base = 10 + self.mod("Dex")
        if self.armor:
            base += self.armor.ac + self.armor.ac_ench
        if self.race.name == "Fairy":
            base += 3
        if self.blessed > 0:
            base += 1
        return base

    TITHE_TIERS = (0, 250, 1000, 5000)  # gold thresholds for levels 0-3

    def tithe_level(self):
        lvl = 0
        for i, threshold in enumerate(self.TITHE_TIERS):
            if self.tithe_total >= threshold:
                lvl = i
        return lvl

    def hunger_state(self):
        if self.food <= 0:
            return "Fainting"
        if self.food < 150:
            return "Weak"
        if self.food < 300:
            return "Hungry"
        return ""

    def hunger_penalty(self):
        return {"": 0, "Hungry": 0, "Weak": -1, "Fainting": -2}[self.hunger_state()]

    def rage_active(self):
        return ("rage" in self.cclass.traits
                and self.hp <= max(1, int(self.max_hp * 0.4)))

    def to_hit_bonus(self):
        b = int(self.level * self.cclass.bth) + self.mod("Str") + self.mod("Dex") // 2
        b += self.hunger_penalty()
        if self.weapon:
            b += self.weapon.hit_ench
        if self.rage_active():
            b += 2
        if self.blessed > 0:
            b += 1
        return b

    def weapon_is_magical(self):
        w = self.weapon
        return w is not None and (w.hit_ench > 0 or w.dmg_ench > 0)

    def damage_roll(self):
        if self.weapon and self.weapon.subtype not in RANGED:
            dmg = roll(self.weapon.dmg) + self.weapon.dmg_ench
        else:
            dmg = random.randint(1, 2)  # fists, or clubbing with a bow
        dmg += self.mod("Str")
        if "gore" in self.race.traits:
            dmg += 2
        if self.rage_active():
            dmg += 3
        return max(1, dmg)

    def has_ranged(self):
        return self.weapon is not None and self.weapon.subtype in RANGED

    def ranged_to_hit(self):
        b = int(self.level * self.cclass.bth) + self.mod("Dex")
        b += self.hunger_penalty() + self.weapon.hit_ench
        if "bowmaster" in self.race.traits:
            b += 2
        return b

    def ranged_damage(self):
        dmg = roll(self.weapon.dmg) + self.weapon.dmg_ench + self.mod("Dex") // 2
        if "bowmaster" in self.race.traits:
            dmg += 2
        return max(1, dmg)

    def exp_to_level(self, lvl):
        """Total experience needed to attain character level lvl."""
        if lvl <= 1:
            return 0
        mult = self.race.xp_mult * self.cclass.xp_mult
        base = 10 * (2 ** (lvl - 2))
        if lvl > 12:
            base = 10 * (2 ** 10) + (lvl - 12) * 5000
        return int(base * mult)

    def craft_exp_to(self, lvl):
        """Total craft experience needed to attain craftsman level lvl."""
        return 50 * lvl * (lvl - 1)

    def is_arcane(self):
        """Arcane (Int-based) casters who can cast memorized book spells."""
        return self.cclass.mana_stat == "Int"

    def can_scribe(self):
        """Who may identify scrolls on sight and work the scribe's craft
        (vellum/quill/ink, copy, spellbook, etch): arcane casters and the
        lore-steeped Sun-Elves of any class."""
        return self.is_arcane() or "arcane" in self.race.traits

    def spellbook(self):
        return next((it for it in self.inventory
                     if it.kind == "spellbook"), None)

    def known_spells(self):
        spells = [s for s in self.cclass.spells if s.level <= self.level]
        if "cantrip" in self.race.traits:
            spells.insert(0, SUN_CANTRIP)
        if "gloom" in self.race.traits:
            spells.insert(0, DARK_CANTRIP)
        if self.is_arcane():
            for sub in self.memorized:
                spells.append(Spell("scroll:" + sub,
                                    f"{sub.title()} (book)", 1,
                                    SCROLL_SPELL_MANA.get(sub, 8)))
        return spells

    # -- inventory ---------------------------------------------------------

    def free_letter(self):
        used = {it.letter for it in self.inventory}
        for ch in string.ascii_lowercase:
            if ch not in used:
                return ch
        return None

    def bag(self):
        return next((it for it in self.inventory if it.kind == "bag"), None)

    def add_item(self, item):
        """Add to inventory, stacking when possible. Returns False if full.

        Crafting materials disappear into the crafting bag — one slot,
        bottomless, all ingredients inside.
        """
        if item.kind == "material":
            bag = self.bag()
            if bag is not None:
                bag.contents[item.subtype] = (
                    bag.contents.get(item.subtype, 0) + item.count)
                return True
        for it in self.inventory:
            if it.stacks_with(item):
                it.count += item.count
                return True
        letter = self.free_letter()
        if letter is None or len(self.inventory) >= INV_LIMIT:
            return False
        item.letter = letter
        self.inventory.append(item)
        return True

    def remove_one(self, item):
        item.count -= 1
        if item.count <= 0 and item in self.inventory:
            self.inventory.remove(item)

    def get_by_letter(self, letter):
        for it in self.inventory:
            if it.letter == letter:
                return it
        return None
