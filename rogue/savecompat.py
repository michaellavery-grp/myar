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
from .dungeon import FLOOR, BIOME_FLOORS
from .items import make_bag
from .monsters import MONSTERS, make_animal
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

        _ensure(game, "pending_stat_points", 0)
        _ensure(game, "trade_requested", False)
        _ensure(game, "pet", None)

        for lvl in game.levels.values():
            _ensure(lvl, "crafting_table", None)
            _ensure(lvl, "trader_pos", None)
            _ensure(lvl, "trader_stock", [])
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

        game.save_version = SAVE_VERSION
        game.msg(f"(Your save was carried forward from version {old} "
                 f"to {SAVE_VERSION}.)")
        return game
    except Exception:
        return None
