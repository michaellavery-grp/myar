"""Save-game migration: upgrade old saves in place instead of wiping them.

Pickled objects from older versions are missing attributes added since,
and carry stale copies of race/class/monster definitions. This module
patches everything up to the current SAVE_VERSION so a long-running
character survives updates.

When adding a feature that changes saved structures: bump SAVE_VERSION
in __init__.py AND add the matching defaults below.
"""

import random

from . import SAVE_VERSION
from .classes import CLASSES
from .dungeon import FLOOR, BIOME_FLOORS, _place_temple
from .items import make_bag
from .monsters import MONSTERS, ANIMAL_TYPES, make_animal, make_same_animal
from .races import RACES


def _ensure(obj, attr, value):
    if not hasattr(obj, attr):
        setattr(obj, attr, value)


def _ensure_frozen(obj, attr, value):
    """Like _ensure, for frozen dataclasses (MonsterType)."""
    if not hasattr(obj, attr):
        object.__setattr__(obj, attr, value)


def _patch_item(it):
    _ensure(it, "poison_charges", 0)
    _ensure(it, "contents", {})


def _patch_monster(m):
    _ensure(m, "diseased", False)
    _ensure(m, "attitude", "hostile")
    _ensure(m, "tamed", False)
    _ensure(m, "rooted", 0)
    _ensure(m, "blinded", 0)
    _ensure(m, "stuck", 0)
    _ensure(m, "max_hp", getattr(m, "hp", 1))
    # Relink the type to the current definition when possible so new
    # fields (genus, diet) and rebalanced flags come along.
    current = next((t for t in MONSTERS if t.name == m.type.name), None)
    if current is not None:
        m.type = current
    else:  # bosses and animals are built dynamically — patch in place
        _ensure_frozen(m.type, "genus", "")
        _ensure_frozen(m.type, "diet", "")


def _wild_regrowth(lvl):
    """Old levels predate the wild — let one room grow over."""
    rooms = [r for r in lvl.rooms if not r.gone and not r.biome]
    if not rooms or random.random() > 0.5:
        return
    room = random.choice(rooms)
    room.biome = random.choice(["forest", "savannah"])
    ch = BIOME_FLOORS[room.biome]
    for x, y in room.floor_tiles():
        if lvl.grid[y][x] == FLOOR:
            lvl.grid[y][x] = ch
    for _ in range(random.randint(1, 2)):
        spots = [t for t in room.floor_tiles() if not lvl.monster_at(*t)]
        if not spots:
            break
        a = make_animal(room.biome, lvl.depth)
        a.x, a.y = random.choice(spots)
        lvl.monsters.append(a)


_FOWL = {t.name for ts in ANIMAL_TYPES.values() for t in ts
         if t.genus == "fowl"}


def _make_fowl(biome, depth):
    """Spawn a fowl specifically (for retrofitting pre-v1.4 saves)."""
    fowl_types = [t for t in ANIMAL_TYPES[biome] if t.genus == "fowl"]
    for _ in range(12):
        a = make_animal(biome, depth)
        if a.type.name in _FOWL:
            return a
    # Fallback: build directly from the first fowl type
    from .monsters import Monster
    t = fowl_types[0]
    a = Monster(t, 0, 0, depth)
    a.asleep = False
    a.attitude = ("friendly" if t.diet in ("omnivore", "herbivore")
                  else "wary")
    return a


def _seed_fowl(lvl):
    """Pre-v1.4 levels were generated without fowl. Let some birds in:
    every biome room with no fowl gets one, so existing saves can find
    the scribe's feathers without descending to fresh levels."""
    biome_rooms = [r for r in lvl.rooms if not r.gone and r.biome]
    for room in biome_rooms:
        has_fowl = any(m.type.name in _FOWL and room.contains(m.x, m.y)
                       for m in lvl.monsters)
        if has_fowl:
            continue
        spots = [t for t in room.floor_tiles() if not lvl.monster_at(*t)]
        if spots:
            a = _make_fowl(room.biome, lvl.depth)
            a.x, a.y = random.choice(spots)
            lvl.monsters.append(a)
            # Birds of a feather — settle a small flock of the same kind
            for _ in range(random.randint(1, 2)):
                free = [t for t in room.floor_tiles()
                        if not lvl.monster_at(*t)]
                if not free:
                    break
                bird = make_same_animal(a.type, lvl.depth)
                bird.x, bird.y = random.choice(free)
                lvl.monsters.append(bird)


def migrate_game(game):
    """Upgrade a loaded Game to the current save version.

    Returns the migrated game, or None if it cannot be salvaged.
    """
    try:
        old = getattr(game, "save_version", 0)
        if old == SAVE_VERSION:
            return game
        p = game.player

        # Stale pickled copies of race/class lose newly added traits and
        # spells — relink to the live definitions by name.
        p.race = next((r for r in RACES if r.name == p.race.name), p.race)
        p.cclass = next((c for c in CLASSES if c.name == p.cclass.name),
                        p.cclass)

        _ensure(p, "craft_level", 1)
        _ensure(p, "craft_exp", 0)
        _ensure(p, "knows_taming", False)
        # Retro-grant skills the (relinked) race/class now bestow
        if ("taming" in p.race.traits or "taming" in p.cclass.traits
                or p.level >= 10):
            p.knows_taming = True
        for it in p.inventory:
            _patch_item(it)
        if p.bag() is None:
            bag = make_bag()
            # sweep any loose materials into it
            for it in list(p.inventory):
                if it.kind == "material":
                    bag.contents[it.subtype] = (
                        bag.contents.get(it.subtype, 0) + it.count)
                    p.inventory.remove(it)
            if not p.add_item(bag):
                bag.letter = "z"
                p.inventory.append(bag)

        _ensure(p, "memorized", [])
        _ensure(p, "book_studied", True)
        _ensure(p, "max_level_reached", p.level)
        _ensure(p, "blessed", 0)
        _ensure(p, "confused", 0)
        _ensure(p, "temp_hp", 0)
        _ensure(p, "tithe_total", 0)

        # v17: Sun-Elves gained an innate mana pool. Recompute the cap for
        # everyone (harmless) and top up any newly-granted mana.
        if old < 17:
            before = getattr(p, "max_mana", 0)
            p.refresh_mana_cap()
            if p.max_mana > before:
                p.mana = p.max_mana
                if "arcane" in p.race.traits and not p.cclass.mana_stat:
                    game.msg("(Innate arcane power wells up in you — you "
                             "can now cast cantrips and grimoire spells.)")
        _ensure(game, "pending_stat_points", 0)
        _ensure(game, "trade_requested", False)
        _ensure(game, "temple_requested", False)
        _ensure(game, "pet", None)
        _ensure(game, "offer_study", False)
        _ensure(game, "pending_copy", None)
        _ensure(game, "pending_etch", None)

        # v9: fanged monsters now shed teeth. Back-pay for every fang the
        # old algorithm swallowed: six monster teeth, on the house.
        if old < 9:
            bag = p.bag()
            if bag is not None:
                bag.contents["teeth"] = bag.contents.get("teeth", 0) + 6
                game.msg("(Six monster teeth settle into your crafting "
                         "bag — fanged foes now shed them.)")

        # v14: hides and skins now make vellum more generously. Retcon a
        # stack of parchment for the hides you already spent.
        if old < 14:
            bag = p.bag()
            if bag is not None:
                bag.contents["vellum"] = bag.contents.get("vellum", 0) + 6
                game.msg("(Six sheets of vellum are pressed into your bag — "
                         "your old hides and skins should have made more.)")

        # v15: the study menu used to require an easily-missed toggle, so
        # some casters etched spells but ended up with an empty memory.
        # If a studied spellbook has spells but nothing is memorized,
        # commit up to three of them now.
        if old < 15 and p.is_arcane():
            book = p.spellbook()
            if book is not None and book.contents and not p.memorized:
                p.memorized = sorted(book.contents)[:3]
                game.msg("(Your etched spells settle into memory: "
                         + ", ".join(p.memorized) + ". Cast them with z.)")

        for lvl in game.levels.values():
            _ensure(lvl, "crafting_table", None)
            _ensure(lvl, "trader_pos", None)
            _ensure(lvl, "trader_stock", [])
            _ensure(lvl, "temple_pos", None)
            _ensure(lvl, "temple_prayed", False)
            _ensure(lvl, "seen_items", set())
            for room in lvl.rooms:
                _ensure(room, "biome", "")
            for m in lvl.monsters:
                _patch_monster(m)
            for items in lvl.items.values():
                for it in items:
                    _patch_item(it)
            for it in lvl.trader_stock:
                _patch_item(it)
            if old < 7:
                _wild_regrowth(lvl)
            if old < 12:
                _seed_fowl(lvl)  # birds came in v1.4; retrofit old levels
            if old < 13 and lvl.temple_pos is None:
                # Temples came in v1.5 — raise one on each cached level.
                shrine = next(((x, y) for y, row in enumerate(lvl.grid)
                               for x, ch in enumerate(row) if ch == "_"), None)
                _place_temple(lvl, shrine)

        if old < 12 and any(
                any(m.type.name in _FOWL for m in lvl.monsters)
                for lvl in game.levels.values()):
            game.msg("(Fowl have come to roost in your wild rooms — look "
                     "for the birds, scribe.)")

        game.save_version = SAVE_VERSION
        game.msg(f"(Your save was carried forward from version {old} "
                 f"to {SAVE_VERSION}.)")
        return game
    except Exception:
        return None
