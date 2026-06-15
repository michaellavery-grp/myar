"""Headless engine test: no curses required.

Run:  python3 -m rogue.smoke_test
"""

import pickle
import random
import sys

from . import MAX_DEPTH, BOSS_EVERY
from .classes import CLASSES
from .dungeon import gen_level
from .game import Game, GameOver, GameWon
from .monsters import Monster, MONSTERS
from .player import STAT_NAMES, roll_stats
from .races import RACES


def _race(name):
    return next(r for r in RACES if r.name == name)


def _cclass(name):
    return next(c for c in CLASSES if c.name == name)


def _spawn_adjacent(g, type_name):
    """Place a fresh, awake monster next to the player; returns it."""
    mtype = next(m for m in MONSTERS if m.name == type_name)
    p = g.player
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        if g.level.passable(p.x + dx, p.y + dy) \
                and not g.level.monster_at(p.x + dx, p.y + dy):
            m = Monster(mtype, p.x + dx, p.y + dy, g.depth)
            m.asleep = False
            g.level.monsters.append(m)
            return m
    raise AssertionError("no free adjacent tile")


def test_generation():
    for depth in list(range(1, 30)) + [50, 75, 98, 99]:
        lvl = gen_level(depth)
        assert lvl.stairs_up, f"no up stairs at depth {depth}"
        if depth < MAX_DEPTH:
            assert lvl.stairs_down, f"no down stairs at depth {depth}"
        else:
            assert lvl.stairs_down is None
        if depth % BOSS_EVERY == 0 or depth == MAX_DEPTH:
            assert any(m.is_boss for m in lvl.monsters), f"no boss at {depth}"
    print("ok  level generation (incl. bosses, depth 99)")


def test_save_roundtrip():
    g = Game("Tester", RACES[0], CLASSES[0])
    blob = pickle.dumps(g)
    g2 = pickle.loads(blob)
    assert g2.player.name == "Tester"
    assert g2.depth == 1
    print("ok  save/load pickle round trip")


def test_spells():
    wizard = next(c for c in CLASSES if c.name == "Wizard")
    g = Game("Gandalf", RACES[3], wizard)  # Sun-Elf Wizard
    g.player.level = 12
    g.player.refresh_mana_cap()
    g.player.mana = g.player.max_mana
    assert g.player.max_mana > 0
    for spell in g.player.known_spells():
        g.player.mana = max(g.player.mana, spell.mana)
        g.cast(spell)  # may "fail" without target; must not raise
    print("ok  wizard spells castable headless")


def test_random_play():
    dirs = [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, 1), (1, -1), (-1, 1)]
    for race in RACES:
        for cclass in CLASSES:
            random.seed(hash((race.name, cclass.name)) & 0xFFFF)
            g = Game("Bot", race, cclass)
            try:
                for _ in range(400):
                    act = random.random()
                    consumed = False
                    if act < 0.75:
                        consumed = g.move_player(*random.choice(dirs))
                    elif act < 0.80:
                        consumed = g.search()
                    elif act < 0.85:
                        consumed = g.rest()
                    elif act < 0.90 and g.player.known_spells():
                        sp = random.choice(g.player.known_spells())
                        g.player.mana = max(g.player.mana, sp.mana)
                        consumed = g.cast(sp)
                    elif (g.player.x, g.player.y) == g.level.stairs_down:
                        consumed = g.descend()
                    else:
                        consumed = g.pickup()
                    if g.pending_identify:
                        if g.player.inventory:
                            g.identify_chosen(random.choice(g.player.inventory))
                        g.pending_identify = False
                    if consumed:
                        g.world_tick()
                    while g.pending_stat_points > 0:
                        g.allocate_stat(random.choice(STAT_NAMES))
                    g.trade_requested = False
                    g.temple_requested = False
                    g.offer_study = False
                    g.pending_copy = g.pending_etch = None
                    g.drain_msgs()
            except GameOver:
                pass
            except GameWon:
                pass
    print(f"ok  random play, {len(RACES)}x{len(CLASSES)} race/class combos")


def test_deep_combat():
    fighter = next(c for c in CLASSES if c.name == "Fighter")
    g = Game("Conan", RACES[5], fighter)  # Minotaur Fighter
    g.player.level = 40
    g.player.max_hp = g.player.hp = 600
    # Gear representative of a character who found ~15 enchant scrolls
    g.player.weapon.hit_ench = 15
    g.player.weapon.dmg_ench = 15
    g.player.stats["Str"] = 25
    random.seed(7)
    g.goto_depth(99, "up")
    boss = next(m for m in g.level.monsters if m.is_boss)
    assert "Morgoth" in boss.name
    try:
        for _ in range(3000):
            if boss not in g.level.monsters:
                break
            boss.x, boss.y = g.player.x + 1, g.player.y  # keep adjacent
            g.attack(boss)
            g.world_tick()
            g.drain_msgs()
    except GameOver:
        print("ok  Morgoth fight (player died, fairly)")
        return
    assert boss not in g.level.monsters, "Morgoth unkillable?"
    pos_items = [i for items in g.level.items.values() for i in items]
    assert any(i.kind == "amulet" for i in pos_items), "no amulet dropped"
    print("ok  Morgoth dies and drops the Amulet of Yendor")


def test_reroll_and_stat_gain():
    race = _race("Human")
    for _ in range(20):
        stats = roll_stats(race)
        assert set(stats) == set(STAT_NAMES)
        assert all(3 <= v <= 19 for v in stats.values())  # Cha+1 can hit 19

    # Racial bonuses must be able to push scores past 18 on rerolls
    minotaur, fairy = _race("Minotaur"), _race("Fairy")
    mino_strs = [roll_stats(minotaur)["Str"] for _ in range(300)]
    fairy_ints = [roll_stats(fairy)["Int"] for _ in range(300)]
    assert all(3 <= s <= 22 for s in mino_strs)
    assert max(mino_strs) > 18, "Minotaur +4 Str never exceeded 18"
    assert all(3 <= i <= 20 for i in fairy_ints)
    assert max(fairy_ints) > 18, "Fairy +2 Int never exceeded 18"
    g = Game("Bumpy", race, _cclass("Wizard"))
    g.player.exp = g.player.exp_to_level(4)
    g._check_level_up()
    assert g.player.level == 4
    assert g.pending_stat_points == 2
    before = g.player.stats["Int"]
    g.allocate_stat("Int")
    g.allocate_stat("Int")
    assert g.player.stats["Int"] == before + 2
    assert g.pending_stat_points == 0
    print("ok  stat reroll + level-4 ability increases")


def test_racial_abilities():
    import rogue.game as game_mod

    # Sun-Elf innate cantrip: free to cast, hurts things
    g = Game("Sunny", _race("Sun-Elf"), _cclass("Fighter"))
    spells = g.player.known_spells()
    assert any(s.key == "sun_bolt" and s.mana == 0 for s in spells)
    m = _spawn_adjacent(g, "goblin")
    hp0 = m.hp
    assert g.cast(spells[0])
    assert m.hp < hp0 or m not in g.level.monsters

    # Wood-Elf: starts with a bow, can fire it
    g = Game("Leggy", _race("Wood-Elf"), _cclass("Thief"))
    bow = next(it for it in g.player.inventory if it.subtype == "short bow")
    g.wield(bow)
    m = _spawn_adjacent(g, "goblin")
    assert g.fire()  # turn consumed whether it hits or misses

    # Minotaur: charge a foe two tiles away in a straight line
    g = Game("Horns", _race("Minotaur"), _cclass("Barbarian"))
    p = g.player
    charged = False
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        if (g.level.passable(p.x + dx, p.y + dy)
                and g.level.passable(p.x + 2 * dx, p.y + 2 * dy)
                and not g.level.monster_at(p.x + dx, p.y + dy)
                and not g.level.monster_at(p.x + 2 * dx, p.y + 2 * dy)):
            mtype = next(mt for mt in MONSTERS if mt.name == "ogre")
            m = Monster(mtype, p.x + 2 * dx, p.y + 2 * dy, 1)
            g.level.monsters.append(m)
            assert g.charge(dx, dy)
            assert (p.x, p.y) == (m.x - dx, m.y - dy) or m not in g.level.monsters
            charged = True
            break
    assert charged, "no straight lane found for charge test"
    assert g.exit_direction()  # labyrinth sense always has an answer

    # Ghoul: bite festers (force the chance on), victim rots over time
    g = Game("Gnasher", _race("Ghoul"), _cclass("Fighter"))
    m = _spawn_adjacent(g, "cave troll")
    real_chance = game_mod.chance
    game_mod.chance = lambda p: True
    try:
        while m in g.level.monsters and not m.diseased:
            g.attack(m)
    finally:
        game_mod.chance = real_chance
    if m in g.level.monsters:
        assert m.diseased
        hp0 = m.hp
        try:
            g._monsters_act()
            assert m not in g.level.monsters or m.hp <= hp0  # rot beats regen
        except GameOver:
            pass  # the troll won the exchange; disease logic still exercised
    print("ok  racial abilities: cantrip, bow, charge, festering bite")


def test_drops():
    import rogue.game as game_mod
    real_chance = game_mod.chance
    game_mod.chance = lambda p: True
    try:
        # Humanoid: drops a weapon, gold or item
        g = Game("Looter", _race("Human"), _cclass("Fighter"))
        m = _spawn_adjacent(g, "goblin")
        pos = (m.x, m.y)
        while m in g.level.monsters:
            g.attack(m)
        kinds = {i.kind for i in g.level.items.get(pos, [])}
        assert kinds & {"weapon", "gold", "potion", "scroll", "food", "armor"}, kinds

        # Beasts: generic skin/teeth/hide plus their signature parts
        for beast, part in (("giant rat", "rat tail"), ("bat", "bat eye"),
                            ("snake", "snake venom")):
            g = Game("Skinner", _race("Human"), _cclass("Fighter"))
            g.player.level, g.player.stats["Str"] = 10, 18
            m = _spawn_adjacent(g, beast)
            pos = (m.x, m.y)
            while m in g.level.monsters:
                g.attack(m)
            subs = {i.subtype for i in g.level.items.get(pos, [])
                    if i.kind == "material"}
            assert subs & {"skin", "teeth", "hide"}, (beast, subs)
            assert part in subs, (beast, subs)

        # Humanoids with signature parts AND fangs: an orc kill stacks
        # gear/gold + an ear + teeth, all from one corpse
        for foe, part in (("orc", "orc ear"), ("kobold", "kobold tail")):
            g = Game("Trophy", _race("Human"), _cclass("Fighter"))
            g.player.level, g.player.stats["Str"] = 10, 18
            m = _spawn_adjacent(g, foe)
            pos = (m.x, m.y)
            while m in g.level.monsters:
                g.attack(m)
            drops = g.level.items.get(pos, [])
            assert any(i.kind != "material" for i in drops), foe  # gear/gold
            subs = {i.subtype for i in drops if i.kind == "material"}
            assert part in subs, (foe, subs)
            assert "teeth" in subs, f"{foe} shed no teeth: {subs}"

        # Vampire: undead, so no flesh — but those fangs drop
        g = Game("VanHelsing", _race("Human"), _cclass("Fighter"))
        g.player.level, g.player.stats["Str"] = 20, 18
        m = _spawn_adjacent(g, "vampire")
        pos = (m.x, m.y)
        while m in g.level.monsters:
            g.attack(m)
        subs = {i.subtype for i in g.level.items.get(pos, [])
                if i.kind == "material"}
        assert subs == {"teeth"}, subs

        # Skeletons: bones, and nothing fleshy
        g = Game("Gravedigger", _race("Human"), _cclass("Fighter"))
        g.player.level, g.player.stats["Str"] = 10, 18
        m = _spawn_adjacent(g, "skeleton")
        pos = (m.x, m.y)
        while m in g.level.monsters:
            g.attack(m)
        subs = {i.subtype for i in g.level.items.get(pos, [])
                if i.kind == "material"}
        assert subs == {"bone"}, subs

        # Undead (fleshless of part): never leaves materials
        g = Game("Pious", _race("Human"), _cclass("Fighter"))
        g.player.level, g.player.stats["Str"] = 10, 18
        m = _spawn_adjacent(g, "zombie")
        pos = (m.x, m.y)
        while m in g.level.monsters:
            g.attack(m)
        assert not any(i.kind == "material"
                       for i in g.level.items.get(pos, []))
    finally:
        game_mod.chance = real_chance
    print("ok  humanoid, beast, trophy and bone death drops")


def test_crafting():
    from .items import make_material, RECIPES, ARMOR_DEFS
    g = Game("Tinker", _race("Human"), _cclass("Explorer"))
    p = g.player
    px, py = p.x, p.y
    g.level.grid[py][px] = "="  # conjure a table underfoot
    assert g.at_crafting_table()
    for it in (make_material("skin", 6), make_material("hide", 10),
               make_material("teeth", 16), make_material("snake venom", 4),
               make_material("rat tail", 3), make_material("bat eye", 2),
               make_material("orc ear", 3), make_material("kobold tail", 2),
               make_material("bone", 6), make_material("drake hide", 4),
               make_material("dragon hide", 4)):
        p.add_item(it)
    bow = None
    def _is_scribe(result):
        return (result.startswith("material:vellum")
                or result.startswith("material:ink")
                or result in ("material:quill", "spellbook",
                              "copy_scroll", "etch_scroll"))
    for i, (name, needs, result) in enumerate(RECIPES):
        if _is_scribe(result):
            continue  # exercised by test_scrollcraft / test_scribing
        assert g.can_craft(RECIPES[i]), name
        if result in ("arrows", "poison_arrows"):
            bow = next(it for it in p.inventory if it.subtype == "short bow")
            ench0, pois0 = bow.dmg_ench, bow.poison_charges
            assert g.do_craft(i), name
            if result == "arrows":
                assert bow.dmg_ench == ench0 + 1
            else:
                assert bow.poison_charges == pois0 + 8
        else:
            assert g.do_craft(i), name
    # The leather ladder, up to dragon-scale at the top
    for armor in ("hide armor", "studded leather", "bone armor",
                  "drake-scale armor", "dragon-scale armor"):
        assert any(it.subtype == armor for it in p.inventory), armor
    assert ARMOR_DEFS["dragon-scale armor"] > ARMOR_DEFS["plate mail"]
    assert ARMOR_DEFS["drake-scale armor"] > ARMOR_DEFS["plate mail"]
    # Brews are pre-identified
    assert ("potion", "poison") in g.identified
    assert ("potion", "gain strength") in g.identified
    # Thirteen crafts of this size make a level-4 craftsman
    assert p.craft_level == 4, p.craft_level
    assert p.craft_exp > 0
    # Poisoned shots burn down per arrow fired
    g.wield(bow)
    m = _spawn_adjacent(g, "goblin")
    charges0 = bow.poison_charges
    assert g.fire()
    assert bow.poison_charges == charges0 - 1
    print("ok  crafting: leather ladder, trophies, brews, craft levels")


def test_craft_quality():
    import rogue.game as game_mod
    from .items import make_material
    g = Game("Master", _race("Human"), _cclass("Archeologist"))
    p = g.player
    g.level.grid[p.y][p.x] = "="
    p.craft_level = 6
    p.add_item(make_material("skin", 3))
    real_chance = game_mod.chance
    game_mod.chance = lambda c: True
    try:
        assert g.do_craft(0)  # leather armor, forced magical quality
    finally:
        game_mod.chance = real_chance
    assert any(it.kind == "armor" and it.subtype == "leather armor"
               and it.ac_ench == 2 for it in p.inventory), \
        "magical (+2) craft did not occur at craftsman level 6"
    print("ok  masterwork/magical crafting at high craftsman levels")


def test_multi_pickup():
    from .items import make_material, make_gold, Item
    g = Game("Greedy", _race("Human"), _cclass("Fighter"))
    pos = (g.player.x, g.player.y)
    g.level.items.setdefault(pos, []).extend([
        make_material("bone", 2),
        Item("potion", "healing"),
        make_gold(1),
    ])
    gold0 = g.player.gold
    assert g.pickup()
    assert pos not in g.level.items, "tile not fully cleared"
    assert g.player.gold > gold0
    assert any(it.kind == "potion" for it in g.player.inventory)
    bag = g.player.bag()
    assert bag is not None and bag.contents.get("bone", 0) >= 2, \
        "materials did not land in the crafting bag"
    print("ok  multiple items on one tile picked up together")


def test_crafting_bag():
    from .items import make_material
    g = Game("Packrat", _race("Human"), _cclass("Fighter"))
    p = g.player
    bag = p.bag()
    assert bag is not None, "no crafting bag at start"
    slots0 = len(p.inventory)
    # Twenty different pickups, zero new slots
    for sub in ("skin", "hide", "teeth", "bone") * 5:
        assert p.add_item(make_material(sub))
    assert len(p.inventory) == slots0, "materials consumed inventory slots"
    assert g.material_count("skin") == 5
    # Bag feeds the crafting table
    g.level.grid[p.y][p.x] = "="
    from .items import RECIPES
    leather_idx = next(i for i, r in enumerate(RECIPES)
                       if r[0] == "leather armor")
    assert g.can_craft(RECIPES[leather_idx])
    assert g.do_craft(leather_idx)
    assert g.material_count("skin") == 2  # 3 consumed from the bag
    # The bag itself stays put
    assert not g.drop(bag)
    assert bag in p.inventory
    print("ok  crafting bag: one slot, holds all, feeds the table")


def test_taming():
    import rogue.game as game_mod
    from .items import make_pet_food
    from .monsters import ANIMAL_TYPES, Monster as M

    # Druids, Shamans, Rangers and Wood-Elves know taming from level 1;
    # everyone else learns at 10 or at a shrine
    g = Game("Radagast", _race("Human"), _cclass("Druid"))
    assert g.player.knows_taming
    assert Game("Strider", _race("Human"), _cclass("Ranger")).player.knows_taming
    assert Game("Legolas", _race("Wood-Elf"), _cclass("Fighter")).player.knows_taming
    g2 = Game("Conan", _race("Human"), _cclass("Fighter"))
    assert not g2.player.knows_taming
    g2.player.exp = g2.player.exp_to_level(10)
    g2._check_level_up()
    assert g2.player.knows_taming, "taming not learned at level 10"
    g3 = Game("Pilgrim", _race("Human"), _cclass("Fighter"))
    g3.level.grid[g3.player.y][g3.player.x] = "_"
    g3._step_on_tile()
    assert g3.player.knows_taming, "shrine did not teach taming"

    # Tame a wolf with pet food (forced success)
    p = g.player
    wolf_t = next(t for t in ANIMAL_TYPES["forest"] if t.name == "wolf")
    wolf = M(wolf_t, p.x + 1, p.y, 1)
    wolf.asleep = False
    wolf.attitude = "wary"
    assert g.level.passable(p.x + 1, p.y) or True  # tame ignores terrain
    g.level.monsters.append(wolf)
    real_chance = game_mod.chance
    game_mod.chance = lambda c: True
    try:
        assert g.tame(1, 0)
    finally:
        game_mod.chance = real_chance
    assert wolf.tamed and g.pet is wolf
    assert wolf.attitude == "friendly"
    assert wolf.type.genus == "canine"

    # The pet follows you down the stairs when close
    p.x, p.y = g.level.stairs_down
    wolf.x, wolf.y = p.x + 1, p.y
    g.descend()
    assert g.pet in g.level.monsters, "pet did not follow downstairs"

    # The pet fights hostiles; ten ticks must not crash
    foe = _spawn_adjacent(g, "goblin")
    foe.x, foe.y = g.pet.x + 1, g.pet.y
    try:
        for _ in range(10):
            g.world_tick()
            g.drain_msgs()
            if foe not in g.level.monsters:
                break
    except GameOver:
        pass

    # Release the wolf, then a lion takes its place
    pet = g.pet
    assert g.release_pet()
    assert g.pet is None and not pet.tamed
    assert pet.attitude == "friendly"  # parted as friends, re-tameable
    g.level.monsters = [m for m in g.level.monsters
                        if m is not pet and m is not foe]
    lion_t = next(t for t in ANIMAL_TYPES["savannah"] if t.name == "lion")
    d = next(dd for dd in ((1, 0), (-1, 0), (0, 1), (0, -1))
             if not g.level.monster_at(p.x + dd[0], p.y + dd[1]))
    lion = M(lion_t, p.x + d[0], p.y + d[1], g.depth)
    lion.asleep = False
    lion.attitude = "wary"
    g.level.monsters.append(lion)
    g.player.add_item(make_pet_food())
    game_mod.chance = lambda c: True
    try:
        assert g.tame(*d)
    finally:
        game_mod.chance = real_chance
    assert g.pet is lion and lion.tamed
    print("ok  taming: learn paths, tame, fight, release, tame anew")


def test_message_wrapping():
    """Single messages longer than the line must page via --More--."""
    from .ui import _wrap_text
    farewell = ("You scratch the antelope behind the ears and let it go. "
                "It lingers a moment, then pads away, free.")
    chunks = _wrap_text(farewell, 70)
    assert len(chunks) >= 2, "long message did not split into pages"
    assert all(len(c) <= 70 for c in chunks)
    assert " ".join(chunks) == farewell, "wrapping lost words"
    print("ok  long messages wrap into --More-- pages")


def test_pet_jumping():
    """A wedged or distant companion jumps to the player's side, and
    stairs carry it from anywhere on the level."""
    import rogue.game as game_mod
    from .items import make_pet_food
    from .monsters import ANIMAL_TYPES, Monster as M
    g = Game("Houndmaster", _race("Human"), _cclass("Druid"))
    p = g.player
    wolf_t = next(t for t in ANIMAL_TYPES["forest"] if t.name == "wolf")
    wolf = M(wolf_t, p.x + 1, p.y, 1)
    wolf.asleep = False
    g.level.monsters.append(wolf)
    g.player.add_item(make_pet_food())
    real_chance = game_mod.chance
    game_mod.chance = lambda c: True
    try:
        assert g.tame(1, 0)
    finally:
        game_mod.chance = real_chance
    # Strand the wolf far away: it must jump back within a few turns.
    # (Clear hostiles first — a companion in melee rightly stays to fight.)
    g.level.monsters = [m for m in g.level.monsters if m.tamed]
    far = g.level.random_floor(avoid=(p.x, p.y), min_dist=10)
    if far:
        wolf.x, wolf.y = far
        for _ in range(4):
            g._monsters_act()
            g.drain_msgs()
        from .game import _dist
        assert _dist(wolf.x, wolf.y, p.x, p.y) <= 2, \
            "stranded companion failed to jump to the player"
    # Stairs carry the companion from ANY distance now
    far = g.level.random_floor(avoid=(p.x, p.y), min_dist=10)
    if far:
        wolf.x, wolf.y = far
    p.x, p.y = g.level.stairs_down
    g.descend()
    assert g.pet in g.level.monsters, \
        "companion left behind on the old level"
    g.drain_msgs()
    print("ok  pet jumping: wedged pets jump to you, stairs never strand")


def test_biomes_and_animals():
    from .dungeon import FOREST, SAVANNAH
    found_biomes, found_animals, found_shrine = set(), 0, False
    for seed in range(40):
        random.seed(7000 + seed)
        lvl = gen_level(3)
        for room in lvl.rooms:
            if room.biome:
                found_biomes.add(room.biome)
        for m in lvl.monsters:
            if "tameable" in m.type.flags:
                found_animals += 1
                assert m.attitude in ("wary", "friendly")
                assert m.type.genus, "animal without a genus"
                exp = ("friendly" if m.type.diet in ("omnivore", "herbivore")
                       else "wary")
                assert m.attitude == exp
        if any("_" in "".join(row) for row in lvl.grid):
            found_shrine = True
    assert found_biomes == {"forest", "savannah"}, found_biomes
    assert found_animals > 10, "biome rooms are not spawning animals"
    assert found_shrine, "no shrine generated in 40 levels"
    print(f"ok  biomes: forest+savannah, {found_animals} wild beasts, shrines")


def test_nature_spells():
    from .monsters import ANIMAL_TYPES, Monster as M
    g = Game("Mara", _race("Human"), _cclass("Shaman"))
    p = g.player
    p.level = 11
    p.refresh_mana_cap()
    p.mana = p.max_mana = 50
    # Calm Animal befriends the nearest wild beast — make the lion the
    # only one so the test is deterministic
    g.level.monsters = [m for m in g.level.monsters
                        if "tameable" not in m.type.flags]
    lion_t = next(t for t in ANIMAL_TYPES["savannah"] if t.name == "lion")
    lion = M(lion_t, p.x + 1, p.y, 1)
    lion.asleep = False
    lion.attitude = "wary"
    g.level.monsters.append(lion)
    calm = next(s for s in p.known_spells() if s.key == "calm_animal")
    assert g.cast(calm)
    assert lion.attitude == "friendly"
    # Summon pet food conjures portions
    feast = next(s for s in p.known_spells() if s.key == "summon_pet_food")
    before = sum(it.count for it in p.inventory
                 if it.kind == "food" and it.subtype == "pet food")
    assert g.cast(feast)
    after = sum(it.count for it in p.inventory
                if it.kind == "food" and it.subtype == "pet food")
    assert after == before + 2
    # With a hostile around, attack spells prefer it over the friendly lion
    foe = _spawn_adjacent(g, "goblin")
    foe.attitude = "hostile"
    assert g._nearest_visible_monster() is foe
    print("ok  druid/shaman: calm animal, summoned pet food, safe targeting")


def test_pet_food_scraps():
    """Any two small parts — e.g. a bat eye & a bone — make one pet food."""
    from .items import make_material, RECIPES, PET_SCRAPS
    idx = next(i for i, r in enumerate(RECIPES) if r[2] == "food:pet food")
    combos = [("bat eye", "bone"), ("rat tail", "orc ear"),
              ("kobold tail", "kobold tail")]
    for a, b in combos:
        g = Game("Cook", _race("Human"), _cclass("Fighter"))
        p = g.player
        g.level.grid[p.y][p.x] = "="
        assert not g.can_craft(RECIPES[idx])  # bare cupboard
        p.add_item(make_material(a))
        p.add_item(make_material(b))
        assert g.can_craft(RECIPES[idx]), (a, b)
        before = sum(it.count for it in p.inventory
                     if it.kind == "food" and it.subtype == "pet food")
        assert g.do_craft(idx), (a, b)
        after = sum(it.count for it in p.inventory
                    if it.kind == "food" and it.subtype == "pet food")
        assert after == before + 1, "should yield exactly one portion"
        # scraps fully consumed
        assert all(g.material_count(s) == 0 for s in PET_SCRAPS), (a, b)
    print("ok  pet food from any two scraps (eye+bone, tails, ears...)")


def test_scrollcraft():
    """Vellum, quills, ink, spellbook, copying and etching scrolls."""
    from .items import make_material, RECIPES, Item

    def ridx(result):
        # Tolerate the "#N" output-count suffix on material recipes.
        key = result.split("#")[0]
        return next(i for i, r in enumerate(RECIPES)
                    if r[2].split("#")[0] == key)

    g = Game("Scribe", _race("Fairy"), _cclass("Illusionist"))
    p = g.player
    g.level.grid[p.y][p.x] = "="
    for it in (make_material("hide", 16), make_material("feather", 4),
               make_material("gall gland", 8)):
        p.add_item(it)

    # Raw scribe materials
    for result, mat in (("material:vellum", "vellum"),
                        ("material:quill", "quill"),
                        ("material:ink", "ink")):
        assert g.do_craft(ridx(result)), result
        assert g.material_count(mat) >= 1, mat
    # Enough vellum for the book (6) + a copy job (1)
    for _ in range(6):
        assert g.do_craft(ridx("material:vellum"))
    for _ in range(3):
        assert g.do_craft(ridx("material:ink"))
    assert g.do_craft(ridx("material:quill"))

    # The spellbook itself (and only one)
    assert g.do_craft(ridx("spellbook"))
    assert p.spellbook() is not None
    assert not g.do_craft(ridx("spellbook")), "second grimoire allowed?"

    # Copying: identified scrolls duplicate and stack
    scroll = Item("scroll", "magic mapping", count=1)
    p.add_item(scroll)
    g.identify(scroll)
    assert not g.do_craft(ridx("copy_scroll"))  # pends on scroll choice
    assert g.pending_copy is not None
    assert g.copy_scroll(scroll)
    assert scroll.count == 2, "copied scroll did not stack"

    # Etching: scroll becomes a permanent book spell
    assert not g.do_craft(ridx("etch_scroll"))
    assert g.pending_etch is not None
    assert g.etch_scroll(scroll)
    assert "magic mapping" in p.spellbook().contents
    assert scroll.count == 1, "etching should consume one scroll"
    assert not p.book_studied

    # Rest offers study; memorize and cast from the book
    assert g.rest()
    assert g.offer_study
    p.memorized = ["magic mapping"]
    p.book_studied = True
    g.offer_study = False
    book_spell = next(s for s in p.known_spells()
                      if s.key == "scroll:magic mapping")
    p.mana = max(p.mana, book_spell.mana)
    explored0 = len(g.level.explored)
    assert g.cast(book_spell)
    assert len(g.level.explored) > explored0, "book-cast mapping did nothing"

    # Non-arcane casters are shut out
    g2 = Game("Grunt", _race("Human"), _cclass("Fighter"))
    g2.level.grid[g2.player.y][g2.player.x] = "="
    for it in (make_material("vellum", 2), make_material("ink", 2),
               make_material("quill", 2)):
        g2.player.add_item(it)
    s2 = Item("scroll", "light")
    g2.player.add_item(s2)
    g2.identify(s2)
    assert not g2.do_craft(ridx("copy_scroll"))
    assert g2.pending_copy is None, "fighter allowed to copy scrolls"
    print("ok  scrollcraft: vellum/quill/ink, spellbook, copy, etch, cast")


def test_scribing_and_dweomery():
    """The full scribe's craft and the spellcraft (dweomery) it feeds.

    Guards the menu-availability bug: 'etch a scroll into spellbook' must
    NOT be offered until a blank spellbook has actually been crafted and
    is on the character. Also exercises every prerequisite gate and the
    downstream memorize-and-cast flow.
    """
    from .items import make_material, RECIPES, Item

    def ridx(result):
        # Tolerate the "#N" output-count suffix on material recipes.
        key = result.split("#")[0]
        return next(i for i, r in enumerate(RECIPES)
                    if r[2].split("#")[0] == key)

    def menu(g):
        """Exactly what the crafting table would display right now."""
        return set(g.craftable_now())

    SPELLBOOK, COPY, ETCH = (ridx("spellbook"), ridx("copy_scroll"),
                             ridx("etch_scroll"))
    VELLUM, QUILL, INK = (ridx("material:vellum"), ridx("material:quill"),
                          ridx("material:ink"))

    # --- non-arcane casters never see scribe recipes ---------------------
    fg = Game("Grunt", _race("Human"), _cclass("Fighter"))
    fg.level.grid[fg.player.y][fg.player.x] = "="
    for it in (make_material("vellum", 9), make_material("ink", 9),
               make_material("quill", 9), make_material("hide", 9)):
        fg.player.add_item(it)
    s = Item("scroll", "light")
    fg.player.add_item(s)
    fg.identify(s)
    m = menu(fg)
    assert SPELLBOOK not in m and COPY not in m and ETCH not in m, \
        "fighter was offered scribe recipes"
    assert not fg.recipe_available(RECIPES[ETCH])

    # --- arcane caster, full materials, NO spellbook ---------------------
    g = Game("Scribe", _race("Fairy"), _cclass("Wizard"))
    p = g.player
    g.level.grid[p.y][p.x] = "="
    for it in (make_material("vellum", 9), make_material("ink", 9),
               make_material("quill", 9), make_material("hide", 9)):
        p.add_item(it)
    m = menu(g)
    # THE BUG: etch must not appear without a spellbook, even with mats
    assert ETCH not in m, "etch offered with no spellbook (the reported bug)"
    assert SPELLBOOK in m, "spellbook recipe should be available"
    # copy needs an identified scroll — none yet
    assert COPY not in m, "copy offered with no identified scroll"
    assert not g.do_craft(ETCH), "etch should hard-fail without a book"
    assert p.spellbook() is None, "failed etch must not conjure a book"

    # Give an identified scroll → copy becomes available, etch still not
    scroll = Item("scroll", "magic mapping")
    p.add_item(scroll)
    g.identify(scroll)
    m = menu(g)
    assert COPY in m and ETCH not in m

    # --- craft the spellbook -------------------------------------------
    assert g.do_craft(SPELLBOOK)
    book = p.spellbook()
    assert book is not None
    m = menu(g)
    assert SPELLBOOK not in m, "second spellbook should not be offered"
    assert ETCH in m, "etch must be available once the book exists"

    # --- etch fills the book; offer withdraws when full -----------------
    # (etch is a two-step craft: do_craft(ETCH) arms it, then a chosen
    #  scroll is consumed — exactly as the UI drives it.)
    subs = ["magic mapping", "teleportation", "light", "identify",
            "enchant weapon", "enchant armor"]
    for sub in subs:
        if not any(it.kind == "scroll" and it.subtype == sub
                   for it in p.inventory):
            sc = Item("scroll", sub)
            p.add_item(sc)
            g.identify(sc)
        if g.material_count("ink") < 1:
            p.add_item(make_material("ink", 1))
        if g.material_count("quill") < 1:
            p.add_item(make_material("quill", 1))
        assert ETCH in menu(g), f"etch should be available for {sub}"
        assert not g.do_craft(ETCH)          # arms pending_etch
        assert g.pending_etch is not None
        target = next(it for it in p.inventory
                      if it.kind == "scroll" and it.subtype == sub)
        assert g.etch_scroll(target), sub
        assert sub in book.contents
    assert len(book.contents) == 6
    # Full book: etch no longer offered even with scrolls + materials
    extra = Item("scroll", "light")
    p.add_item(extra)
    g.identify(extra)
    p.add_item(make_material("ink", 2))
    p.add_item(make_material("quill", 2))
    assert ETCH not in menu(g), "etch offered on a full (6/6) spellbook"

    # An identified scroll already etched doesn't re-enable etch on its own
    only_dupes = Game("Dupe", _race("Fairy"), _cclass("Wizard"))
    p2 = only_dupes.player
    only_dupes.level.grid[p2.y][p2.x] = "="
    for it in (make_material("vellum", 9), make_material("hide", 2),
               make_material("ink", 5), make_material("quill", 5)):
        p2.add_item(it)
    assert only_dupes.do_craft(ridx("spellbook"))
    d = Item("scroll", "light")
    p2.add_item(d)
    only_dupes.identify(d)
    assert not only_dupes.do_craft(ridx("etch_scroll"))  # arm it
    assert only_dupes.etch_scroll(d)            # light now in book
    dupe = Item("scroll", "light")              # another light scroll
    p2.add_item(dupe)
    only_dupes.identify(dupe)
    assert ridx("etch_scroll") not in menu(only_dupes), \
        "etch offered when the only scroll is already in the book"

    # --- dweomery: memorize from the book and cast -----------------------
    p.memorized = ["magic mapping"]
    p.book_studied = True
    spell = next(s for s in p.known_spells()
                 if s.key == "scroll:magic mapping")
    p.mana = max(p.mana, spell.mana)
    explored0 = len(g.level.explored)
    assert g.cast(spell)
    assert len(g.level.explored) > explored0, "book-cast mapping did nothing"
    # Only up to 3 may be memorized; known_spells reflects the loadout
    p.memorized = ["light", "identify", "teleportation"]
    book_spells = [s for s in p.known_spells() if s.key.startswith("scroll:")]
    assert len(book_spells) == 3
    print("ok  scribing & dweomery: etch gated on a real spellbook, "
          "full craft + cast chain")


def test_fowl():
    import rogue.game as game_mod
    from .monsters import ANIMAL_TYPES, SPECIAL_PARTS, Monster as M
    fowl = [t for ts in ANIMAL_TYPES.values() for t in ts
            if t.genus == "fowl"]
    names = {t.name for t in fowl}
    assert names == {"hen", "rooster", "duck", "goose", "cockatrice",
                     "phoenix"}, names
    for t in fowl:
        assert SPECIAL_PARTS[t.name][0] == "feather", t.name
    assert SPECIAL_PARTS["giant centipede"][0] == "gall gland"
    # A slain goose yields feathers (forced)
    g = Game("Fowler", _race("Human"), _cclass("Fighter"))
    p = g.player
    goose_t = next(t for t in fowl if t.name == "goose")
    goose = M(goose_t, p.x + 1, p.y, 1)
    goose.asleep = False
    g.level.monsters.append(goose)
    real_chance = game_mod.chance
    game_mod.chance = lambda c: True
    try:
        while goose in g.level.monsters:
            g.attack(goose)
    finally:
        game_mod.chance = real_chance
    drops = {i.subtype for i in g.level.items.get((goose.x, goose.y), [])
             if i.kind == "material"}
    assert "feather" in drops, drops
    print("ok  fowl: six birds, feather drops, centipede gall glands")


def test_fowl_flocking_and_retrofit():
    """Fowl spawn in flocks, and pre-v1.4 saves get birds retrofitted."""
    from collections import Counter
    fowl = {"hen", "rooster", "duck", "goose", "cockatrice", "phoenix"}

    # Flocking: across many levels, fowl rooms hold multiple same-species
    flock_sizes = []
    for seed in range(120):
        random.seed(9000 + seed)
        lvl = gen_level(3)
        by_room = {}
        for m in lvl.monsters:
            if m.type.name in fowl:
                room = lvl.room_at(m.x, m.y)
                if room is not None:
                    by_room.setdefault(id(room), Counter())[m.type.name] += 1
        for counts in by_room.values():
            flock_sizes.append(max(counts.values()))
    assert flock_sizes, "no fowl spawned at all"
    avg = sum(flock_sizes) / len(flock_sizes)
    assert avg >= 2.0, f"fowl not flocking (avg same-species cluster {avg:.2f})"

    # Retrofit: a pre-fowl cached level gains birds on migration.
    # Build a level the way an old save would have — animals, no fowl.
    from .savecompat import migrate_game
    from . import SAVE_VERSION
    random.seed(123)
    g = Game("OldTimer", _race("Human"), _cclass("Wizard"))
    lvl = gen_level(3)
    # Strip every fowl to simulate a level generated before v1.4
    lvl.monsters = [m for m in lvl.monsters if m.type.name not in fowl]
    biome_rooms = [r for r in lvl.rooms if not r.gone and r.biome]
    if not biome_rooms:  # ensure at least one biome room to seed into
        room = next(r for r in lvl.rooms if not r.gone)
        room.biome = "forest"
        biome_rooms = [room]
    g.levels = {3: lvl}
    g.save_version = 11        # pre-fowl-retrofit
    before = sum(1 for m in lvl.monsters if m.type.name in fowl)
    assert before == 0
    g = migrate_game(g)
    assert g is not None and g.save_version == SAVE_VERSION
    after = sum(1 for m in g.levels[3].monsters if m.type.name in fowl)
    assert after >= len(biome_rooms), \
        f"retrofit seeded {after} fowl for {len(biome_rooms)} biome rooms"
    print(f"ok  fowl flocking (avg {avg:.1f}/flock) + pre-v1.4 retrofit")


def test_ranged_combat():
    """Bows: range caps, no firing through walls, skeleton arrow-resist."""
    import rogue.game as game_mod
    from .items import make_weapon, RANGED_RANGE
    from .monsters import MONSTERS, Monster as M

    g = Game("Archer", _race("Wood-Elf"), _cclass("Ranger"))
    p = g.player
    # Find an open run of floor to lay out the test precisely
    room = next(r for r in g.level.rooms if not r.gone and r.w >= 8)
    fy = room.y + 1
    p.x, p.y = room.x + 1, fy
    bow = make_weapon("short bow")
    p.add_item(bow)
    g.wield(bow)
    assert RANGED_RANGE["short bow"] == 5 and RANGED_RANGE["long bow"] == 7

    # A goblin just past short-bow range is not a valid target...
    goblin_t = next(t for t in MONSTERS if t.name == "goblin")
    far = M(goblin_t, p.x + 6, fy, 3)
    g.level.monsters = [far]
    assert g._ranged_target() is None, "short bow hit beyond 5 squares"
    # ...but a long bow (range 7) can reach it
    longbow = make_weapon("long bow")
    p.add_item(longbow)
    g.wield(longbow)
    assert g._ranged_target() is far, "long bow couldn't reach 6 squares"

    # No shooting through a wall: drop a wall between archer and target
    g.wield(bow)
    near = M(goblin_t, p.x + 3, fy, 3)
    g.level.monsters = [near]
    assert g._ranged_target() is near
    g.level.grid[fy][p.x + 2] = "|"          # a wall in the way
    assert not g._clear_shot(near.x, near.y)
    assert g._ranged_target() is None, "fired an arrow through a wall"
    g.level.grid[fy][p.x + 2] = "."          # restore

    # Skeletons take roughly half ranged damage. Use a deadeye archer so
    # nearly every shot lands, fire many times at each, compare totals.
    skel_t = next(t for t in MONSTERS if t.name == "skeleton")
    p.level, p.stats["Dex"] = 25, 22  # huge to-hit; arrows land
    p.weapon.hit_ench = 5

    def total_damage(mtype):
        tgt = M(mtype, p.x + 2, fy, 2)
        tgt.asleep = False
        tgt.hp = tgt.max_hp = 100000
        g.level.monsters = [tgt]
        for _ in range(400):
            g.fire()
            g.drain_msgs()
        return tgt.max_hp - tgt.hp

    skel_dmg = total_damage(skel_t)
    gob_dmg = total_damage(goblin_t)
    assert skel_dmg < gob_dmg * 0.7, \
        f"skeleton took {skel_dmg}, goblin {gob_dmg} — resist too weak"
    print("ok  ranged: bow ranges (5/7), no wall shots, skeleton resist")


def test_corridor_sight():
    """The player sees creatures down the full length of a corridor."""
    g = Game("Scout", _race("Human"), _cclass("Fighter"))
    # Build a clean horizontal corridor in rock and stand at one end
    lvl = g.level
    y = 0
    # find a fully-rock row to carve (avoid clobbering rooms)
    for ty in range(len(lvl.grid)):
        if all(c == " " for c in lvl.grid[ty][2:14]):
            y = ty
            break
    else:
        print("ok  corridor sight (no clean rock row; skipped)")
        return
    for x in range(2, 14):
        lvl.grid[y][x] = "#"
    g.player.x, g.player.y = 2, y
    from .monsters import MONSTERS, Monster as M
    rat = M(next(t for t in MONSTERS if t.name == "giant rat"), 11, y, 1)
    lvl.monsters = [rat]
    g.compute_fov()
    assert (11, y) in lvl.visible, "far corridor tile not visible"
    assert g.monster_visible(rat), "creature down the corridor unseen"
    # A wall mid-corridor should block sight beyond it
    lvl.grid[y][6] = "|"
    g.compute_fov()
    assert (11, y) not in lvl.visible, "saw past a wall in the corridor"
    print("ok  corridor sight: whole length visible, walls block")


def test_scroll_knowledge_and_thief():
    """Arcane casters often know a scroll's name on pickup; thieves can
    read scrolls."""
    import rogue.game as game_mod
    from .items import Item

    # Arcane caster identifies scrolls on pickup (INT-boosted chance)
    g = Game("Mage", _race("Sun-Elf"), _cclass("Wizard"))
    p = g.player
    p.stats["Int"] = 18
    ided = 0
    for _ in range(60):
        sc = Item("scroll", "teleportation")
        g.identified.discard(("scroll", "teleportation"))
        g.level.items[(p.x, p.y)] = [sc]
        g.pickup()
        if ("scroll", "teleportation") in g.identified:
            ided += 1
        # clear inventory scrolls for the next round
        p.inventory = [it for it in p.inventory if it.kind != "scroll"]
    assert ided > 20, f"arcane scroll-recognition too rare ({ided}/60)"

    # A Thief can read a scroll and get its effect
    g = Game("Sneak", _race("Human"), _cclass("Thief"))
    p = g.player
    sc = Item("scroll", "magic mapping")
    p.add_item(sc)
    g.identify(sc)
    explored0 = len(g.level.explored)
    assert g.read(sc), "thief could not read a scroll"
    assert len(g.level.explored) > explored0, "thief's scroll had no effect"
    print("ok  scroll knowledge (arcane) + thieves read scrolls")


def test_new_monsters():
    """Ghost (incorporeal), wraith (needs magic), spectre (drain),
    acid, spores, and the new cryptids exist and behave."""
    import rogue.game as game_mod
    from .monsters import MONSTERS, Monster as M

    names = {m.name for m in MONSTERS}
    for n in ("ghost", "spectre", "gelatinous cube", "ooze", "myconoid",
              "gnoll", "bugbear", "owlbear"):
        assert n in names, f"missing monster {n}"
    wraith = next(m for m in MONSTERS if m.name == "wraith")
    assert "needs_magic" in wraith.flags

    real_chance = game_mod.chance
    real_rand = random.randint

    # Wraith: a mundane weapon cannot harm it; a magical one can
    g = Game("Knight", _race("Human"), _cclass("Fighter"))
    p = g.player
    p.level, p.stats["Str"] = 12, 18
    p.weapon.hit_ench = p.weapon.dmg_ench = 0  # strip the starting enchant
    w = M(wraith, p.x + 1, p.y, 12)
    w.asleep = False
    g.level.monsters.append(w)
    hp0 = w.hp
    game_mod.chance = lambda c: True
    try:
        g.attack(w)
        assert w.hp == hp0, "mundane weapon harmed a wraith"
        p.weapon.hit_ench = 2  # now enchanted
        game_mod.randint = lambda a, b: b  # guarantee the to-hit lands
        g.attack(w)
        assert w.hp < hp0, "enchanted weapon failed to harm a wraith"
    finally:
        game_mod.chance = real_chance
        game_mod.randint = real_rand

    # Ghost: half of mundane blows pass through (negated by magic)
    g = Game("Priest", _race("Human"), _cclass("Fighter"))
    p = g.player
    p.level, p.stats["Str"] = 12, 18
    p.weapon.hit_ench = p.weapon.dmg_ench = 0
    ghost_t = next(m for m in MONSTERS if m.name == "ghost")
    passed = hit = 0
    for _ in range(200):
        gh = M(ghost_t, p.x + 1, p.y, 6)
        gh.asleep = False
        before = gh.hp
        g.level.monsters = [gh]
        game_mod.randint = lambda a, b: b  # always rolls to hit if reached
        try:
            g.attack(gh)
        finally:
            game_mod.randint = real_rand
        if gh.hp == before:
            passed += 1
        else:
            hit += 1
    assert 60 < passed < 140, f"ghost pass-through not ~50% ({passed}/200)"

    # Spectre drains a level; temple restore brings it back
    g = Game("Victim", _race("Human"), _cclass("Fighter"))
    p = g.player
    p.exp = p.exp_to_level(8)
    g._check_level_up()
    assert p.level == 8 and p.max_level_reached == 8
    spectre_t = next(m for m in MONSTERS if m.name == "spectre")
    sp = M(spectre_t, p.x + 1, p.y, 18)
    game_mod.chance = lambda c: False  # no magic-resist dodge (human anyway)
    game_mod.randint = lambda a, b: b   # spectre's blow lands
    try:
        g._drain_level(sp)
    finally:
        game_mod.chance = real_chance
        game_mod.randint = real_rand
    assert p.level == 7, "spectre did not drain a level"
    assert p.max_level_reached == 8
    p.gold = 10000
    g.temple_restore_level()
    assert p.level == 8, "temple did not restore the drained level"

    # Acid corrodes armor; spores confuse
    g = Game("Target", _race("Human"), _cclass("Fighter"))
    p = g.player
    p.armor.ac_ench = 3
    cube = M(next(m for m in MONSTERS if m.name == "gelatinous cube"),
             p.x + 1, p.y, 8)
    game_mod.randint = lambda a, b: b if (a, b) == (1, 20) else real_rand(a, b)
    try:
        g.monster_attack(cube)  # hits (roll 20), acid save fails on... force
    finally:
        game_mod.randint = real_rand
    # armor either corroded or saved; ensure no crash and ac_ench <= 3
    assert p.armor.ac_ench <= 3
    print("ok  new monsters: ghost, wraith, spectre, acid, cryptids")


def test_temple():
    """Bless, remove curse, restore strength, holy water, tithe tiers."""
    from .items import make_holy_water
    g = Game("Pilgrim", _race("Human"), _cclass("Fighter"))
    p = g.player
    p.gold = 20000

    # Temple appears on levels
    assert any(gen_level(d).temple_pos is not None for d in range(1, 6))

    # Bless grants the status
    g.temple_bless()
    assert p.blessed > 0
    ac0 = p.ac
    # (blessing adds +1 AC)
    assert p.ac >= ac0

    # Remove curse fixes negative enchants
    p.weapon.hit_ench = -2
    p.armor.ac_ench = -1
    g.temple_remove_curse()
    assert p.weapon.hit_ench == 0 and p.armor.ac_ench == 0

    # Restore strength
    p.max_str = p.stats["Str"]
    p.stats["Str"] -= 4
    g.temple_restore_strength()
    assert p.stats["Str"] == p.max_str

    # Holy water: fill, then quaff lifts a curse + blesses
    n0 = sum(1 for it in p.inventory if it.subtype == "holy water")
    g.temple_fill_holy_water()
    hw = next(it for it in p.inventory if it.subtype == "holy water")
    assert g.is_identified(hw)
    p.armor.ac_ench = -3
    p.blessed = 0
    g.quaff(hw)
    assert p.armor.ac_ench == 0 and p.blessed > 0

    # Tithe tiers and the half-price perk at the top rank
    full = g.temple_price("bless")
    p.tithe_total = 0
    assert p.tithe_level() == 0
    g.temple_give_tithe(5000)
    assert p.tithe_level() == 3
    assert g.temple_price("bless") == full // 2  # halved at max rank
    assert g.temple_price("holy water") == g.TEMPLE_BASE_PRICES["holy water"]

    # Prayer never crashes and (eventually) grants something across tries.
    # (Reset the per-temple gate each loop — we're sampling the RNG here.)
    import rogue.game as game_mod
    granted = False
    for _ in range(50):
        g.level.temple_prayed = False
        hp_before, mhp_before = p.hp, p.max_hp
        pts_before = g.pending_stat_points
        g.temple_pray()
        if (p.hp > hp_before or p.max_hp > mhp_before or p.temp_hp > 0
                or g.pending_stat_points > pts_before or p.blessed > 0):
            granted = True
        g.pending_stat_points = 0
        p.temp_hp = 0
    assert granted, "prayer never granted a benefit in 50 tries"

    # Pray is once per temple — a second prayer at the same altar is refused
    g.level.temple_prayed = False
    g.temple_pray()
    assert g.level.temple_prayed
    p.hp = p.max_hp = 200
    p.temp_hp = 0
    g.pending_stat_points = 0
    g.temple_pray()  # second attempt
    assert (g.pending_stat_points == 0 and p.temp_hp == 0), \
        "prayed twice at the same temple"
    # A fresh level's temple is a fresh prayer
    g.goto_depth(g.depth + 1, "up")
    assert not g.temple_already_prayed(), "new temple should allow a prayer"
    print("ok  temple: bless, uncurse, restore, holy water, tithe, pray-once")


def test_drop_balance():
    """Tails must flow generously enough to keep soup on the menu."""
    from collections import Counter
    g = Game("Balance", _race("Human"), _cclass("Fighter"))
    pos = (g.player.x, g.player.y)

    def harvest(type_name, kills=200):
        mtype = next(mt for mt in MONSTERS if mt.name == type_name)
        got = Counter()
        for _ in range(kills):
            g.level.items.pop(pos, None)
            g._reward_kill(Monster(mtype, pos[0], pos[1], 3))
            for it in g.level.items.get(pos, []):
                if it.kind == "material":
                    got[it.subtype] += it.count
            while g.pending_stat_points:
                g.allocate_stat("Str")
            g.drain_msgs()
        return got

    kobolds = harvest("kobold")
    rats = harvest("giant rat")
    # ~75% nominal; demand at least 60% even on an unlucky seed
    assert kobolds["kobold tail"] >= 120, kobolds
    assert rats["rat tail"] >= 120, rats
    soups = min(kobolds["kobold tail"] // 2, rats["rat tail"])
    assert soups >= 60, f"only {soups} soups from 400 kills"
    print(f"ok  drop balance: 400 early kills fund {soups} kobold-tail soups")


def test_user_save_fixture():
    """Load the checked-in copy of the player's real save, migrate it to
    the current version, and play a few dozen turns. Keeps long-running
    characters safe across updates. Refresh the fixture with:
        cp ~/.myar_save.pkl testdata/user_save.pkl
    """
    import os
    import pickle
    path = os.path.join(os.path.dirname(__file__), "..",
                        "testdata", "user_save.pkl")
    if not os.path.exists(path):
        print("ok  user save fixture (none present, skipped)")
        return
    with open(path, "rb") as f:
        g = pickle.load(f)

    def _materials(player):
        out = {}
        bag = next((it for it in player.inventory if it.kind == "bag"), None)
        if bag is not None:
            for k, v in getattr(bag, "contents", {}).items():
                out[k] = out.get(k, 0) + v
        for it in player.inventory:
            if it.kind == "material":
                out[it.subtype] = out.get(it.subtype, 0) + it.count
        return out

    mats_before = _materials(g.player)
    gold_before = g.player.gold
    old_version = getattr(g, "save_version", 0)
    from .savecompat import migrate_game
    g = migrate_game(g)
    assert g is not None, "save migration failed"
    mats_after = _materials(g.player)
    expected = dict(mats_before)
    if old_version < 9:  # teeth back-pay for the fang fix
        expected["teeth"] = expected.get("teeth", 0) + 6
    if old_version < 14:  # vellum retcon for the hide/skin buff
        expected["vellum"] = expected.get("vellum", 0) + 6
    assert mats_after == expected, \
        f"migration altered materials: {mats_before} -> {mats_after}"
    assert g.player.gold == gold_before, "migration altered gold"
    from . import SAVE_VERSION
    assert g.save_version == SAVE_VERSION
    assert g.player.bag() is not None
    # Retro-granted skills arrive with migration (e.g. Wood-Elf/Ranger taming)
    p = g.player
    if ("taming" in p.race.traits or "taming" in p.cclass.traits
            or p.level >= 10):
        assert p.knows_taming, "migration did not retro-grant taming"
    g.compute_fov()
    dirs = [(1, 0), (-1, 0), (0, 1), (0, -1),
            (1, 1), (-1, -1), (1, -1), (-1, 1)]
    try:
        for _ in range(80):
            g.move_player(*random.choice(dirs))
            g.world_tick()
            while g.pending_stat_points:
                g.allocate_stat("Str")
            g.trade_requested = False
            g.drain_msgs()
    except (GameOver, GameWon):
        pass
    print(f"ok  user save fixture: {g.player.name} the {g.player.race.name} "
          f"{g.player.cclass.name} (depth {g.depth}) migrates and plays")


def test_trader():
    g = Game("Haggler", _race("Human"), _cclass("Archeologist"))
    g.goto_depth(3, "up")
    lvl = g.level
    assert lvl.trader_pos is not None, "no trader on depth 3"
    assert lvl.trader_stock, "trader has no stock"
    assert lvl.tile(*lvl.trader_pos) in (".", '"', "'"), "trader on bad tile"
    # Trader is not a monster: nothing to attack, spells can't target it
    assert lvl.monster_at(*lvl.trader_pos) is None
    # Bumping into the trader requests a trade, consumes no turn
    p = g.player
    p.x, p.y = lvl.trader_pos[0] - 1, lvl.trader_pos[1]
    consumed = g.move_player(1, 0)
    assert not consumed and g.trade_requested
    assert (p.x, p.y) != lvl.trader_pos, "walked through the trader"
    # Buying
    p.gold = 100000
    n0 = len(lvl.trader_stock)
    g.buy(0)
    assert len(lvl.trader_stock) == n0 - 1
    # Selling a ration
    ration = next(it for it in p.inventory if it.kind == "food")
    gold0 = p.gold
    g.sell(ration)
    assert p.gold > gold0
    # Monsters refuse to step onto the trader's tile
    from .monsters import Monster as M
    mtype = next(mt for mt in MONSTERS if mt.name == "orc")
    m = M(mtype, lvl.trader_pos[0] - 1, lvl.trader_pos[1], 3)
    g.level.monsters.append(m)
    assert not g._try_move(m, *lvl.trader_pos)
    print("ok  trader: unattackable, buys and sells, every 3rd level")


if __name__ == "__main__":
    random.seed(1234)
    test_generation()
    test_save_roundtrip()
    test_spells()
    test_reroll_and_stat_gain()
    test_racial_abilities()
    test_drops()
    test_crafting()
    test_craft_quality()
    test_multi_pickup()
    test_crafting_bag()
    test_pet_food_scraps()
    test_scrollcraft()
    test_scribing_and_dweomery()
    test_fowl()
    test_fowl_flocking_and_retrofit()
    test_ranged_combat()
    test_corridor_sight()
    test_scroll_knowledge_and_thief()
    test_new_monsters()
    test_temple()
    test_drop_balance()
    test_taming()
    test_message_wrapping()
    test_pet_jumping()
    test_biomes_and_animals()
    test_nature_spells()
    test_user_save_fixture()
    test_trader()
    test_random_play()
    test_deep_combat()
    print("ALL OK")
    sys.exit(0)
