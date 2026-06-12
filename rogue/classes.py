"""The nine character classes.

Class traits:
    rage            +2 to-hit / +3 damage when below 40% HP
    backstab2       double damage vs sleeping/confused monsters
    backstab3       triple damage vs sleeping/confused monsters
    stealth         monsters wake less often
    search+         better at finding traps
    trap_lore       hidden traps within reach reveal themselves
    appraise        50% chance to identify potions/scrolls on pickup
    dungeon_sense   senses the layout of any room entered, lit or not
    slow_digestion  food clock ticks at half speed
    treasure_sense  finds richer gold hoards
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Spell:
    key: str        # effect key handled in game.py
    name: str
    level: int      # character level required
    mana: int


@dataclass(frozen=True)
class CharClass:
    name: str
    desc: str
    hit_die: int
    bth: float            # base to-hit per character level
    xp_mult: float
    mana_stat: str        # "" for non-casters; "Int" or "Wis"
    mana_factor: float    # mana per (level + stat mod), 0 for non-casters
    traits: frozenset
    spells: tuple = field(default_factory=tuple)
    start_weapon: str = "mace"
    start_armor: str = "leather armor"
    start_extra: tuple = field(default_factory=tuple)  # (kind, subtype, count)


# Innate racial cantrip (Sun-Elves) — costs no mana.
SUN_CANTRIP = Spell("sun_bolt", "Sunfire Cantrip", 1, 0)

WIZARD_SPELLS = (
    Spell("magic_missile", "Magic Missile", 1, 2),
    Spell("light", "Light", 2, 2),
    Spell("blink", "Phase Door", 3, 3),
    Spell("detect_monsters", "Detect Monsters", 5, 3),
    Spell("fireball", "Fire Ball", 7, 6),
    Spell("haste", "Haste Self", 9, 8),
    Spell("teleport", "Teleport Self", 11, 8),
)

ILLUSIONIST_SPELLS = (
    Spell("confuse", "Confuse Monster", 1, 2),
    Spell("light", "Dancing Lights", 2, 2),
    Spell("blink", "Blink", 3, 3),
    Spell("invisibility", "Invisibility", 5, 6),
    Spell("phantasm", "Phantasmal Blast", 7, 5),
    Spell("mass_confuse", "Mass Confusion", 9, 8),
    Spell("teleport", "Dimension Door", 11, 8),
)

RANGER_SPELLS = (
    Spell("light", "Sunburst", 3, 2),
    Spell("detect_monsters", "Sense Beasts", 5, 3),
    Spell("cure_wounds", "Cure Wounds", 7, 4),
    Spell("haste", "Wild Speed", 9, 8),
)

DRUID_SPELLS = (
    Spell("calm_animal", "Calm Animal", 1, 2),
    Spell("light", "Sunlight", 2, 2),
    Spell("summon_pet_food", "Summon Provender", 3, 3),
    Spell("cure_wounds", "Cure Wounds", 5, 4),
    Spell("entangle", "Entangle", 7, 5),
    Spell("call_lightning", "Call Lightning", 9, 6),
    Spell("teleport", "Wind Walk", 11, 8),
)

SHAMAN_SPELLS = (
    Spell("calm_animal", "Soothe the Wild", 1, 2),
    Spell("magic_missile", "Spirit Bolt", 2, 2),
    Spell("summon_pet_food", "Spirit Feast", 3, 3),
    Spell("cure_wounds", "Mend Flesh", 5, 4),
    Spell("haste", "Ghost Dance", 7, 8),
    Spell("mass_confuse", "Dream Walk", 9, 8),
    Spell("teleport", "Spirit Journey", 11, 8),
)

CLASSES = [
    CharClass("Fighter", "A master of weapon and shield.",
              10, 1.00, 1.00, "", 0.0, frozenset({"weapon_master"}),
              start_weapon="long sword", start_armor="ring mail"),
    CharClass("Barbarian", "Rages when bloodied; d12 hit die.",
              12, 1.00, 1.05, "", 0.0, frozenset({"rage"}),
              start_weapon="battle axe", start_armor="leather armor"),
    CharClass("Ranger", "Warden of the wild; part mystic.",
              8, 0.85, 1.20, "Wis", 1.0,
              frozenset({"search+", "stealth", "beast_friend", "taming"}),
              spells=RANGER_SPELLS, start_weapon="short sword",
              start_extra=(("food", "ration", 2),
                           ("food", "pet food", 1))),
    CharClass("Thief", "Quiet feet, knife for sleeping backs.",
              6, 0.70, 1.05, "", 0.0,
              frozenset({"backstab2", "stealth", "search+"}),
              start_weapon="dagger"),
    CharClass("Assassin", "Death unseen, and thrice as sharp.",
              6, 0.75, 1.15, "", 0.0,
              frozenset({"backstab3", "stealth"}),
              start_weapon="dagger"),
    CharClass("Wizard", "Fragile flesh, terrible power.",
              4, 0.50, 1.30, "Int", 2.0, frozenset(),
              spells=WIZARD_SPELLS, start_weapon="dagger",
              start_extra=(("scroll", "magic mapping", 1),)),
    CharClass("Illusionist", "Weaves lies that kill all the same.",
              4, 0.50, 1.25, "Int", 2.0, frozenset(),
              spells=ILLUSIONIST_SPELLS, start_weapon="dagger",
              start_extra=(("potion", "healing", 1),)),
    CharClass("Explorer", "Never lost, rarely hungry.",
              8, 0.80, 1.10, "", 0.0,
              frozenset({"dungeon_sense", "slow_digestion", "search+"}),
              start_extra=(("food", "ration", 2),)),
    CharClass("Archeologist", "Reads dead tongues, robs dead kings.",
              8, 0.75, 1.10, "", 0.0,
              frozenset({"trap_lore", "appraise", "treasure_sense"}),
              start_weapon="whip",
              start_extra=(("scroll", "identify", 2),)),
    CharClass("Druid", "Speaks for beasts and green things.",
              8, 0.70, 1.25, "Wis", 2.0, frozenset({"taming"}),
              spells=DRUID_SPELLS,
              start_extra=(("food", "pet food", 2),)),
    CharClass("Shaman", "Walks with spirits; calms the wild.",
              6, 0.60, 1.20, "Wis", 2.0, frozenset({"taming"}),
              spells=SHAMAN_SPELLS, start_weapon="dagger",
              start_extra=(("food", "pet food", 2),)),
]
