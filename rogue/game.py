"""Game state and turn logic: combat, magic, hunger, traps, the lot."""

import random

from . import MAX_DEPTH, BOSS_EVERY, AMULET_DEPTH, SAVE_VERSION
from .dungeon import (gen_level, FLOOR, DOOR, PASSAGE, STAIRS_DOWN, STAIRS_UP,
                      ROCK, CRAFT_TABLE, SHRINE)
from .items import (POTION_SUBTYPES, SCROLL_SUBTYPES, POTION_COLORS,
                    random_scroll_title, make_amulet, make_gold,
                    make_material, make_weapon, make_armor, rand_item,
                    item_value, MATERIALS, RECIPES, WEAPON_DEFS, RANGED,
                    make_holy_water)
from .items import Item
from .monsters import (Monster, choose_type, SPECIAL_PARTS, make_animal,
                       make_same_animal)
from .player import Player, MAX_FOOD
from .rng import roll, chance


class GameOver(Exception):
    def __init__(self, cause):
        super().__init__(cause)
        self.cause = cause


class GameWon(Exception):
    pass


def _dist(ax, ay, bx, by):
    return max(abs(ax - bx), abs(ay - by))


class Game:
    def __init__(self, name, race, cclass, stats=None):
        self.save_version = SAVE_VERSION
        self.player = Player(name, race, cclass, stats)
        self.levels = {}
        self.depth = 1
        self.max_depth_reached = 1
        self.turn = 0
        self.msgs = []
        self.haste_parity = False
        self.detect_turns = 0
        self.pending_identify = False
        self.pending_stat_points = 0
        self.trade_requested = False
        self.temple_requested = False
        self.pet = None
        self.offer_study = False
        self.pending_copy = None   # materials owed once a scroll is chosen
        self.pending_etch = None
        self._init_identification()
        self.level = self._get_level(1)
        self.player.x, self.player.y = self.level.stairs_up
        self.compute_fov()
        self.msg(f"Hail, {name} the {race.name} {cclass.name}! "
                 f"The Amulet of Yendor lies {AMULET_DEPTH * 50} feet below.")

    # -- identification ----------------------------------------------------

    def _init_identification(self):
        colors = POTION_COLORS[:]
        random.shuffle(colors)
        self.appearance = {}
        for i, sub in enumerate(POTION_SUBTYPES):
            self.appearance[("potion", sub)] = colors[i]
        for sub in SCROLL_SUBTYPES:
            self.appearance[("scroll", sub)] = random_scroll_title()
        self.identified = set()

    def identify(self, item):
        self.identified.add((item.kind, item.subtype))

    def is_identified(self, item):
        if item.kind == "potion" and item.subtype == "holy water":
            return True  # sacred water is never a mystery
        return (item.kind not in ("potion", "scroll")
                or (item.kind, item.subtype) in self.identified)

    def item_name(self, item, capital=False):
        n = item.count
        if item.kind == "potion":
            if self.is_identified(item):
                base = f"potion{'s' if n > 1 else ''} of {item.subtype}"
            else:
                col = self.appearance[("potion", item.subtype)]
                base = f"{col} potion{'s' if n > 1 else ''}"
            name = f"{n} {base}" if n > 1 else f"a {base}"
        elif item.kind == "scroll":
            if self.is_identified(item):
                base = f"scroll{'s' if n > 1 else ''} of {item.subtype}"
            else:
                title = self.appearance[("scroll", item.subtype)]
                base = f"scroll{'s' if n > 1 else ''} titled '{title}'"
            name = f"{n} {base}" if n > 1 else f"a {base}"
        elif item.kind == "weapon":
            name = f"a {item.hit_ench:+d},{item.dmg_ench:+d} {item.subtype}"
            if item.poison_charges > 0:
                name += f" (poisoned x{item.poison_charges})"
        elif item.kind == "armor":
            name = f"{item.ac_ench:+d} {item.subtype} [{item.ac + item.ac_ench}]"
        elif item.kind == "food":
            if item.subtype == "pet food":
                name = (f"{n} portions of pet food" if n > 1
                        else "a portion of pet food")
            else:
                name = (f"{n} rations of food" if n > 1
                        else "a ration of food")
        elif item.kind == "material":
            words = {"skin": ("an untanned skin", "untanned skins"),
                     "teeth": ("a monster tooth", "monster teeth"),
                     "hide": ("a thick hide", "thick hides"),
                     "bat eye": ("a bat eye", "bat eyes"),
                     "snake venom": ("a gland of snake venom",
                                     "glands of snake venom"),
                     "rat tail": ("a rat tail", "rat tails"),
                     "orc ear": ("an orc ear", "orc ears"),
                     "kobold tail": ("a kobold tail", "kobold tails"),
                     "bone": ("a bleached bone", "bleached bones"),
                     "drake hide": ("a drake hide", "drake hides"),
                     "dragon hide": ("a dragon hide", "dragon hides"),
                     "feather": ("a feather", "feathers"),
                     "gall gland": ("a gall gland", "gall glands"),
                     "vellum": ("a sheet of vellum", "sheets of vellum"),
                     "quill": ("a quill", "quills"),
                     "ink": ("a vial of ink", "vials of ink")}
            one, many = words[item.subtype]
            name = one if n == 1 else f"{n} {many}"
        elif item.kind == "gold":
            name = f"{item.count} pieces of gold"
        elif item.kind == "bag":
            total = sum(item.contents.values())
            name = (f"a crafting bag ({total} material"
                    f"{'s' if total != 1 else ''})" if total
                    else "a crafting bag (empty)")
        elif item.kind == "spellbook":
            name = f"a spellbook ({len(item.contents)}/6 spells etched)"
        elif item.kind == "amulet":
            name = "the Amulet of Yendor"
        else:
            name = item.subtype
        if capital:
            name = name[0].upper() + name[1:]
        return name

    # -- messages ----------------------------------------------------------

    def msg(self, text):
        self.msgs.append(text)

    def drain_msgs(self):
        out, self.msgs = self.msgs, []
        return out

    # -- levels and stairs ---------------------------------------------------

    def _get_level(self, depth):
        if depth not in self.levels:
            self.levels[depth] = gen_level(depth)
        return self.levels[depth]

    def goto_depth(self, depth, arrive):
        # A companion always finds the stairs — it follows from anywhere
        # on the level, no matter how far it lagged behind.
        traveling_pet = None
        if (self.pet is not None
                and getattr(self, "level", None) is not None
                and self.pet in self.level.monsters):
            self.level.monsters.remove(self.pet)
            traveling_pet = self.pet
        depth = max(1, min(MAX_DEPTH, depth))
        self.depth = depth
        self.max_depth_reached = max(self.max_depth_reached, depth)
        self.level = self._get_level(depth)
        if arrive == "up" and self.level.stairs_up:
            self.player.x, self.player.y = self.level.stairs_up
        elif arrive == "down" and self.level.stairs_down:
            self.player.x, self.player.y = self.level.stairs_down
        else:
            spot = self.level.random_floor()
            self.player.x, self.player.y = spot
        m = self.level.monster_at(self.player.x, self.player.y)
        if m:
            self._displace(m)
        if traveling_pet:
            spot = self._spot_near_player()
            if spot:
                traveling_pet.x, traveling_pet.y = spot
                self.level.monsters.append(traveling_pet)
                self.msg(f"Your {traveling_pet.name} pads after you.")
            else:
                self.level.monsters.append(traveling_pet)
        self.compute_fov()

    def _spot_near_player(self):
        p = self.player
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                nx, ny = p.x + dx, p.y + dy
                if ((dx, dy) != (0, 0) and self.level.passable(nx, ny)
                        and not self.level.monster_at(nx, ny)
                        and not self._is_fixture(nx, ny)):
                    return nx, ny
        return self.level.random_floor(avoid=(p.x, p.y), min_dist=2)

    def _is_fixture(self, x, y):
        """A tile occupied by an un-walkable fixture (trader or temple)."""
        return (x, y) in (self.level.trader_pos, self.level.temple_pos)

    def _displace(self, m):
        """Shove a monster off the player's tile (never delete it)."""
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                nx, ny = m.x + dx, m.y + dy
                if ((nx, ny) != (self.player.x, self.player.y)
                        and self.level.passable(nx, ny)
                        and not self.level.monster_at(nx, ny)):
                    m.x, m.y = nx, ny
                    return
        spot = self.level.random_floor(avoid=(self.player.x, self.player.y),
                                       min_dist=2)
        if spot:
            m.x, m.y = spot

    def descend(self):
        p = self.player
        if (p.x, p.y) != self.level.stairs_down:
            self.msg("There are no stairs down here.")
            return False
        self.goto_depth(self.depth + 1, "up")
        self.msg(f"You descend to {self.depth * 50} feet.")
        return True

    def ascend(self):
        p = self.player
        if (p.x, p.y) != self.level.stairs_up:
            self.msg("There are no stairs up here.")
            return False
        if self.depth == 1:
            if p.has_amulet:
                raise GameWon()
            self.msg("A mysterious force stops you. The Amulet is not yours yet.")
            return False
        self.goto_depth(self.depth - 1, "down")
        self.msg(f"You climb back up to {self.depth * 50} feet.")
        return True

    # -- field of view -------------------------------------------------------

    def compute_fov(self):
        lvl, p = self.level, self.player
        vis = set()
        room = lvl.room_at(p.x, p.y)
        if room:
            if room.lit:
                vis.update(room.all_tiles())
            if "dungeon_sense" in p.cclass.traits:
                lvl.explored.update(room.all_tiles())
        radius = 2 if "keen_eyes" in p.race.traits else 1
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                vis.add((p.x + dx, p.y + dy))
        # See down the full length of corridors (and a peek into the room
        # at the far end), so creatures ahead are never a blind surprise.
        start_room = room
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1),
                       (1, 1), (-1, -1), (1, -1), (-1, 1)):
            cx, cy = p.x, p.y
            for _ in range(14):
                cx += dx
                cy += dy
                if not lvl.passable(cx, cy):
                    break
                vis.add((cx, cy))
                r = lvl.room_at(cx, cy)
                if r is not None and r is not start_room:
                    break  # reveal the far doorway, then stop at the room
        lvl.visible = vis
        lvl.explored |= vis
        for pos in list(lvl.items):
            if pos in vis:
                lvl.seen_items.add(pos)
        if "trap_lore" in p.cclass.traits:
            for pos, trap in lvl.traps.items():
                if trap.hidden and _dist(p.x, p.y, *pos) <= 1:
                    trap.hidden = False
                    self.msg("You note a suspicious flagstone. (trap)")
        elif "perception" in p.race.traits:
            for pos, trap in lvl.traps.items():
                if (trap.hidden and _dist(p.x, p.y, *pos) <= 1
                        and chance(0.25)):
                    trap.hidden = False
                    self.msg("Your sharp eyes catch a hidden trap!")

    def monster_visible(self, m):
        if (m.x, m.y) in self.level.visible:
            return True
        if self.detect_turns > 0:
            return True
        infra = self.player.race.infravision
        return infra and _dist(self.player.x, self.player.y, m.x, m.y) <= infra

    # -- player actions (return True if a turn was consumed) ----------------

    def move_player(self, dx, dy):
        p = self.player
        if p.confused > 0:
            # Staggering — the chosen direction goes awry
            p.confused -= 1
            dx, dy = random.choice([(a, b) for a in (-1, 0, 1)
                                    for b in (-1, 0, 1) if (a, b) != (0, 0)])
        nx, ny = p.x + dx, p.y + dy
        if (nx, ny) == self.level.trader_pos:
            self.trade_requested = True
            return False
        if (nx, ny) == self.level.temple_pos:
            self.temple_requested = True
            return False
        mon = self.level.monster_at(nx, ny)
        if mon:
            if mon.tamed:
                mon.x, mon.y = p.x, p.y  # swap places with your companion
                p.x, p.y = nx, ny
                self._step_on_tile()
                return True
            self.attack(mon)
            return True
        if not self.level.passable(nx, ny):
            return False
        p.x, p.y = nx, ny
        self._step_on_tile()
        return True

    def _step_on_tile(self):
        p, lvl = self.player, self.level
        pos = (p.x, p.y)
        items = lvl.items.get(pos)
        if items:
            self.pickup()
        trap = lvl.traps.get(pos)
        if trap:
            self._spring_trap(trap, pos)
        if lvl.tile(p.x, p.y) == STAIRS_DOWN:
            self.msg("There is a staircase leading down here.")
        elif lvl.tile(p.x, p.y) == STAIRS_UP:
            self.msg("There is a staircase leading up here.")
        elif lvl.tile(p.x, p.y) == SHRINE:
            if not p.knows_taming:
                p.knows_taming = True
                self.msg("You kneel at a mossy shrine of the wild. The "
                         "speech of beasts fills your mind! (t to tame)")
            else:
                self.msg("A quiet shrine of the wild. The beasts already "
                         "know you.")

    def pickup(self):
        """Pick up everything underfoot (until the pack fills)."""
        p, lvl = self.player, self.level
        pos = (p.x, p.y)
        items = lvl.items.get(pos)
        if not items:
            self.msg("There is nothing here to pick up.")
            return False
        picked_any = False
        while items:
            item = items[-1]
            if item.kind == "gold":
                bonus = 1.3 if "treasure_sense" in p.cclass.traits else 1.0
                amount = int(item.count * bonus)
                p.gold += amount
                items.pop()
                self.msg(f"You find {amount} pieces of gold.")
            elif item.kind == "amulet":
                items.pop()
                p.has_amulet = True
                self.msg("You snatch up the Amulet of Yendor! "
                         "Now flee to the surface!")
            else:
                if (item.kind in ("potion", "scroll")
                        and not self.is_identified(item)):
                    if "appraise" in p.cclass.traits and chance(0.5):
                        self.identify(item)
                        self.msg("Your scholarly eye knows this one.")
                    elif (p.can_scribe() and item.kind == "scroll"
                          and chance(min(0.9, 0.60 + 0.06 * p.mod("Int")))):
                        self.identify(item)
                        self.msg("You recognize the incantation on the "
                                 "scroll at a glance.")
                if not p.add_item(item):
                    self.msg("Your pack is full.")
                    break
                items.pop()
                if item.kind == "material":
                    self.msg(f"You tuck {self.item_name(item)} into your "
                             "crafting bag.")
                else:
                    self.msg(f"You now have {self.item_name(item)} "
                             f"({item.letter}).")
            picked_any = True
        if not items:
            del lvl.items[pos]
            lvl.seen_items.discard(pos)
        return picked_any

    def drop(self, item):
        p, lvl = self.player, self.level
        if item.kind == "bag":
            self.msg("Best keep your crafting bag — a crafter never parts "
                     "with their tools.")
            return False
        if item is p.weapon:
            p.weapon = None
        if item is p.armor:
            p.armor = None
        p.inventory.remove(item)
        item.letter = ""
        lvl.items.setdefault((p.x, p.y), []).append(item)
        lvl.seen_items.add((p.x, p.y))
        self.msg(f"You drop {self.item_name(item)}.")
        return True

    def eat(self, item):
        p = self.player
        p.remove_one(item)
        if item.subtype == "pet food":
            p.food = min(MAX_FOOD, p.food + 250)
            self.msg("Sawdust and old liver. Strictly for the dog, next time.")
        else:
            p.food = min(MAX_FOOD, p.food + 900 + random.randint(0, 400))
            self.msg(random.choice(["My, that was a yummy meal.",
                                    "Tastes like dust and history.",
                                    "That hit the spot."]))
        return True

    def quaff(self, item):
        p = self.player
        sub = item.subtype
        p.remove_one(item)
        first_time = not self.is_identified(item)
        self.identify(item)
        if sub == "holy water":
            p.hp = min(p.max_hp, p.hp + roll("2d8") + 8)
            p.confused = 0
            p.blessed += 25
            for it in (p.weapon, p.armor):
                if it is not None:
                    it.hit_ench = max(0, it.hit_ench)
                    it.dmg_ench = max(0, it.dmg_ench)
                    it.ac_ench = max(0, it.ac_ench)
            self.msg("The holy water blazes cool and clean — wounds close, "
                     "curses lift, and a blessing settles upon you.")
            return True
        if sub == "healing":
            p.hp = min(p.max_hp, p.hp + roll("1d8") + 8)
            self.msg("You begin to feel better.")
        elif sub == "extra healing":
            p.hp = min(p.max_hp + 1, p.hp + roll("2d8") + 16)
            p.max_hp = max(p.max_hp, p.hp)
            self.msg("You begin to feel much better.")
        elif sub == "gain strength":
            p.stats["Str"] = min(25, p.stats["Str"] + 1)
            p.max_str = max(p.max_str, p.stats["Str"])
            self.msg("You feel stronger. What bulging muscles!")
        elif sub == "poison":
            if "poison_immune" in p.race.traits:
                self.msg("The poison slides off your dead veins harmlessly.")
            else:
                loss = roll("1d3")
                if "magic_resist" in p.race.traits:
                    loss = max(1, loss // 2)
                p.stats["Str"] = max(3, p.stats["Str"] - loss)
                self.msg("You feel very sick. The potion was poison!")
        elif sub == "haste self":
            p.haste += 12 + roll("1d8")
            self.msg("You feel yourself moving much faster.")
        elif sub == "restore strength":
            p.stats["Str"] = p.max_str
            self.msg("Your strength returns; you feel warm all over.")
        if first_time:
            self.msg(f"(That was a potion of {sub}.)")
        return True

    def read(self, item):
        if item.kind == "spellbook":
            if not self.player.is_arcane():
                self.msg("The glyphs swim before your untrained eyes.")
                return False
            self.player.book_studied = False
            self.msg("You leaf through your spellbook. "
                     "Rest (.) to commit spells to memory.")
            return False
        p = self.player
        sub = item.subtype
        p.remove_one(item)
        self.identify(item)
        self._scroll_effect(sub)
        return True

    def _scroll_effect(self, sub):
        """The effect of a scroll — read once, or cast from a spellbook."""
        p, lvl = self.player, self.level
        if sub == "magic mapping":
            for y in range(len(lvl.grid)):
                for x in range(len(lvl.grid[0])):
                    if lvl.grid[y][x] != ROCK:
                        lvl.explored.add((x, y))
            self.msg("A map of the level unfolds in your mind!")
        elif sub == "teleportation":
            self._teleport()
        elif sub == "enchant weapon":
            if p.weapon:
                p.weapon.hit_ench += 1
                p.weapon.dmg_ench += 1
                self.msg(f"Your {p.weapon.subtype} glows blue for a moment.")
            else:
                self.msg("Your hands tingle.")
        elif sub == "enchant armor":
            if p.armor:
                p.armor.ac_ench += 1
                self.msg(f"Your {p.armor.subtype} glows silver for a moment.")
            else:
                self.msg("Your skin itches.")
        elif sub == "identify":
            self.pending_identify = True
            self.msg("Choose an item to identify!")
        elif sub == "light":
            self._light_room()
        return True

    def identify_chosen(self, item):
        self.identify(item)
        self.pending_identify = False
        self.msg(f"That is {self.item_name(item)}.")

    def wield(self, item):
        p = self.player
        if item.kind != "weapon":
            self.msg("You can't wield that.")
            return False
        p.weapon = item
        self.msg(f"You are now wielding {self.item_name(item)}.")
        return True

    def wear(self, item):
        p = self.player
        if item.kind != "armor":
            self.msg("You can't wear that.")
            return False
        p.armor = item
        self.msg(f"You are now wearing {self.item_name(item)}.")
        return True

    def take_off(self):
        p = self.player
        if not p.armor:
            self.msg("You aren't wearing any armor.")
            return False
        self.msg(f"You take off {self.item_name(p.armor)}.")
        p.armor = None
        return True

    def search(self):
        p, lvl = self.player, self.level
        base = 1 / 3
        if "search+" in p.cclass.traits or "keen_eyes" in p.race.traits:
            base = 1 / 2
        found = False
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                pos = (p.x + dx, p.y + dy)
                trap = lvl.traps.get(pos)
                if trap and trap.hidden and chance(base):
                    trap.hidden = False
                    found = True
                    self.msg(f"You found a {trap.kind} trap!")
        if not found:
            self.msg("You search the area.")
        return True

    def rest(self):
        # Resting is also when a caster re-prepares their mind, so any
        # rest (not just after etching a new spell) offers the study menu.
        p = self.player
        book = p.spellbook()
        if p.is_arcane() and book is not None and book.contents:
            self.offer_study = True
        return True

    def hostile_in_sight(self):
        """True if a hostile monster is currently visible — used to
        interrupt a multi-turn rest."""
        return any(m.attitude == "hostile" and not m.tamed
                   and self.monster_visible(m)
                   for m in self.level.monsters)

    def _clear_shot(self, tx, ty):
        """True if no wall blocks the line from the player to (tx, ty)."""
        x0, y0 = self.player.x, self.player.y
        dx, dy = abs(tx - x0), abs(ty - y0)
        sx = 1 if tx > x0 else -1
        sy = 1 if ty > y0 else -1
        err = dx - dy
        x, y = x0, y0
        while (x, y) != (tx, ty):
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x += sx
            if e2 < dx:
                err += dx
                y += sy
            if (x, y) == (tx, ty):
                break
            if not self.level.passable(x, y):
                return False  # an arrow cannot fly through stone
        return True

    def _ranged_target(self):
        """Nearest shootable monster: within bow range and with a clear,
        unobstructed line — no firing through walls."""
        from .items import RANGED_RANGE
        p = self.player
        rng = RANGED_RANGE.get(p.weapon.subtype, 5)
        cands = [m for m in self.level.monsters
                 if not m.tamed
                 and _dist(p.x, p.y, m.x, m.y) <= rng
                 and self._clear_shot(m.x, m.y)]
        if not cands:
            return None
        hostile = [m for m in cands if m.attitude == "hostile"]
        pool = hostile or cands
        return min(pool, key=lambda m: _dist(p.x, p.y, m.x, m.y))

    def fire(self):
        """Loose an arrow at the nearest monster in range and line of sight."""
        p = self.player
        if not p.has_ranged():
            self.msg("You have no ranged weapon in hand.")
            return False
        m = self._ranged_target()
        if not m:
            self.msg("There is no clear shot in range.")
            return False
        m.asleep = False
        bow = p.weapon
        magical = bow.hit_ench > 0 or bow.dmg_ench > 0
        if "needs_magic" in m.type.flags and not magical:
            self.msg(f"Your arrow passes through the {m.name} without "
                     "effect — it needs enchanted shafts or magic.")
            return True
        if ("incorporeal" in m.type.flags and not magical and chance(0.5)):
            self.msg(f"Your arrow sails through the {m.name}.")
            return True
        attack_roll = random.randint(1, 20) + p.ranged_to_hit()
        if attack_roll < m.type.ac:
            self.msg(f"Your arrow whistles past the {m.name}.")
            if bow.poison_charges > 0:
                bow.poison_charges -= 1  # the venom is spent either way
            return True
        dmg = p.ranged_damage()
        if "arrow_resist" in m.type.flags:
            dmg = max(1, dmg // 2)  # arrows rattle harmlessly through bone
            self.msg(f"Your arrow clatters through the {m.name}'s frame.")
        else:
            self.msg(f"Your arrow strikes the {m.name}!")
        self._hurt_monster(m, dmg)
        if bow.poison_charges > 0:
            bow.poison_charges -= 1
            if m in self.level.monsters:
                if "undead" in m.type.flags:
                    self.msg(f"The venom means nothing to the {m.name}.")
                else:
                    self.msg("The poison burns in the wound!")
                    self._hurt_monster(m, roll("1d6"))
        return True

    def charge(self, dx, dy):
        """Minotaur: rush in a straight line and gore the first foe met."""
        p = self.player
        if "charge" not in p.race.traits:
            self.msg("You lack the bulk for a proper charge.")
            return False
        x, y, steps, target = p.x, p.y, 0, None
        for _ in range(5):
            x += dx
            y += dy
            if self._is_fixture(x, y):
                break  # no trampling the trader or temple
            target = self.level.monster_at(x, y)
            if target:
                break
            if not self.level.passable(x, y):
                break
            steps += 1
        if not target:
            self.msg("There is nothing there to charge.")
            return False
        if steps == 0:
            self.attack(target)  # too close for a run-up
            return True
        p.x, p.y = x - dx, y - dy
        self.msg(f"You lower your horns and charge the {target.name}!")
        self.attack(target, charging=True)
        self._step_on_tile()
        return True

    # -- taming ----------------------------------------------------------

    def _tame_chance(self, m):
        p = self.player
        c = 0.25 + 0.05 * p.mod("Cha") - 0.03 * m.level
        if "taming" in p.cclass.traits:
            c += 0.25
        if "beast_friend" in p.cclass.traits:
            c += 0.15
        if "beast_friend" in p.race.traits:
            c += 0.15
        c += {"friendly": 0.20, "wary": 0.0, "hostile": -0.20}[m.attitude]
        return max(0.05, min(0.95, c))

    def tame(self, dx, dy):
        p = self.player
        if not p.knows_taming:
            self.msg("You don't know the way of beasts. "
                     "(Find a shrine, or learn it at level 10.)")
            return False
        m = self.level.monster_at(p.x + dx, p.y + dy)
        if not m or "tameable" not in m.type.flags:
            self.msg("There is no wild beast there to tame.")
            return False
        if m.tamed:
            self.msg(f"The {m.name} is already yours, heart and hide.")
            return False
        if self.pet is not None:
            self.msg("You can only handle one companion at a time. "
                     f"(Press t toward your {self.pet.name} to release it.)")
            return False
        food = next((it for it in p.inventory
                     if it.kind == "food" and it.subtype == "pet food"), None)
        if food is None:
            self.msg("You need pet food to win a wild heart.")
            return False
        p.remove_one(food)
        m.asleep = False
        if chance(self._tame_chance(m)):
            m.tamed = True
            m.attitude = "friendly"
            self.pet = m
            self.msg(f"The {m.name} takes the food from your hand... and "
                     f"stays! You have tamed the {m.genus_name()}!")
            p.exp += m.xp // 2
            self._check_level_up()
        else:
            self.msg(f"The {m.name} snatches the food and shies away.")
        return True

    def release_pet(self):
        """Set your companion free. It leaves as a friend, not a stranger."""
        pet = self.pet
        if pet is None:
            return False
        pet.tamed = False
        pet.attitude = "friendly"
        self.pet = None
        self.msg(f"You scratch the {pet.name} behind the ears and let it "
                 "go. It lingers a moment, then pads away, free.")
        return True

    def exit_direction(self):
        """Labyrinth sense: compass direction of the way onward."""
        target = self.level.stairs_down or self.level.stairs_up
        if not target:
            return "?"
        p = self.player
        dx, dy = target[0] - p.x, target[1] - p.y
        s = ("N" if dy < 0 else "S" if dy > 0 else "")
        s += ("W" if dx < 0 else "E" if dx > 0 else "")
        return s or "here"

    # -- crafting ------------------------------------------------------------

    def at_crafting_table(self):
        return self.level.tile(self.player.x, self.player.y) == CRAFT_TABLE

    @staticmethod
    def _ingredient_kind(key):
        """Keys are material subtypes, or '<kind>:<subtype>' carried items."""
        if ":" in key:
            kind, sub = key.split(":", 1)
            return kind, sub
        return "material", key

    def material_count(self, key):
        if key.startswith("any:"):
            return sum(self.material_count(opt)
                       for opt in key[4:].split("|"))
        kind, sub = self._ingredient_kind(key)
        total = sum(it.count for it in self.player.inventory
                    if it.kind == kind and it.subtype == sub)
        if kind == "material":
            bag = self.player.bag()
            if bag is not None:
                total += bag.contents.get(sub, 0)
        return total

    def can_craft(self, recipe):
        _, needs, _ = recipe
        return all(self.material_count(k) >= n for k, n in needs.items())

    def _identified_scrolls(self):
        return [it for it in self.player.inventory
                if it.kind == "scroll" and self.is_identified(it)]

    def recipe_available(self, recipe):
        """Prerequisites beyond raw materials — what the craft menu should
        actually offer. Materials are checked separately by can_craft.

        Scribe recipes are arcane-only and have object prerequisites: you
        cannot etch without a spellbook, cannot bind a second spellbook,
        and cannot copy/etch without an identified scroll to work from.
        """
        _, _, result = recipe
        p = self.player
        if result in ("copy_scroll", "etch_scroll", "spellbook"):
            if not p.can_scribe():
                return False
        if result == "spellbook":
            return p.spellbook() is None           # one grimoire only
        if result == "copy_scroll":
            return bool(self._identified_scrolls())
        if result == "etch_scroll":
            book = p.spellbook()
            if book is None or len(book.contents) >= 6:
                return False
            # need an identified scroll not already etched into the book
            return any(it.subtype not in book.contents
                       for it in self._identified_scrolls())
        return True

    def craftable_now(self):
        """The recipe indices the table should currently display."""
        return [i for i, r in enumerate(RECIPES)
                if self.can_craft(r) and self.recipe_available(r)]

    def _consume_materials(self, needs):
        p = self.player
        for key, n in needs.items():
            if key.startswith("any:"):
                remaining = n
                for opt in key[4:].split("|"):
                    take = min(remaining, self.material_count(opt))
                    if take:
                        self._consume_materials({opt: take})
                        remaining -= take
                    if remaining == 0:
                        break
                continue
            kind, sub = self._ingredient_kind(key)
            remaining = n
            if kind == "material":
                bag = p.bag()
                if bag is not None and remaining > 0:
                    have = bag.contents.get(sub, 0)
                    take = min(remaining, have)
                    if take:
                        remaining -= take
                        if have - take > 0:
                            bag.contents[sub] = have - take
                        else:
                            bag.contents.pop(sub, None)
                if remaining == 0:
                    continue
            matches = [it for it in p.inventory
                       if it.kind == kind and it.subtype == sub]
            # Spend loose copies before anything currently equipped
            matches.sort(key=lambda it: it is p.weapon or it is p.armor)
            for it in matches:
                take = min(remaining, it.count)
                it.count -= take
                remaining -= take
                if it.count <= 0:
                    if it is p.weapon:
                        p.weapon = None
                    if it is p.armor:
                        p.armor = None
                        self.msg("You cut apart the armor you were wearing.")
                    p.inventory.remove(it)
                if remaining == 0:
                    break

    def _gain_craft_exp(self, needs):
        p = self.player
        p.craft_exp += 15 + 10 * sum(needs.values())
        while p.craft_exp >= p.craft_exp_to(p.craft_level + 1):
            p.craft_level += 1
            self.msg(f"Your hands grow surer — craftsman level "
                     f"{p.craft_level}!")
            if p.craft_level == 3:
                self.msg("Masterwork pieces are now within your skill.")
            elif p.craft_level == 5:
                self.msg("You sense how to work magic into your craft.")

    def do_craft(self, idx):
        """Craft RECIPES[idx]; returns True if a turn was spent."""
        name, needs, result = RECIPES[idx]
        if not self.at_crafting_table():
            self.msg("You need to stand at a crafting table (=).")
            return False
        if not self.can_craft(RECIPES[idx]):
            self.msg("You lack the materials for that.")
            return False
        if result in ("copy_scroll", "etch_scroll"):
            p = self.player
            if not p.can_scribe():
                self.msg("Only arcane casters and Sun-Elves work "
                         "scroll-craft.")
                return False
            if result == "etch_scroll":
                book = p.spellbook()
                if book is None:
                    self.msg("You need a spellbook to etch into.")
                    return False
                if len(book.contents) >= 6:
                    self.msg("Your spellbook is full — six spells, no more.")
                    return False
            if not any(it.kind == "scroll" and self.is_identified(it)
                       for it in p.inventory):
                self.msg("You carry no identified scrolls to work from.")
                return False
            # Materials are spent when the scroll is chosen (UI follows up)
            if result == "copy_scroll":
                self.pending_copy = dict(needs)
            else:
                self.pending_etch = dict(needs)
            return False
        if result in ("arrows", "poison_arrows"):
            bow = None
            if self.player.weapon and self.player.weapon.subtype in RANGED:
                bow = self.player.weapon
            else:
                bow = next((it for it in self.player.inventory
                            if it.kind == "weapon" and it.subtype in RANGED),
                           None)
            if bow is None:
                self.msg("Arrows need a bow to feed; you carry none.")
                return False
            self._consume_materials(needs)
            if result == "arrows":
                bow.dmg_ench += 1
                self.msg(f"You fletch keen arrows for your {bow.subtype} "
                         f"(now {bow.hit_ench:+d},{bow.dmg_ench:+d}).")
            else:
                bow.poison_charges += 8
                self.msg(f"You coat your arrows in venom — your {bow.subtype} "
                         f"holds {bow.poison_charges} poisoned shots.")
            self._gain_craft_exp(needs)
            return True
        if result == "spellbook":
            if self.player.spellbook() is not None:
                self.msg("One grimoire is enough for any pair of hands.")
                return False
            item = Item("spellbook", "spellbook")
            if not self.player.add_item(item):
                self.msg("Your pack is too full to hold the finished work.")
                return False
            self._consume_materials(needs)
            self.msg("You bind hide and vellum into a blank spellbook!")
            self._gain_craft_exp(needs)
            return True
        kind, _, subtype = result.partition(":")
        # A "#N" suffix on the subtype means the craft yields N units.
        out_count = 1
        if "#" in subtype:
            subtype, _, n = subtype.partition("#")
            out_count = int(n)
        if kind == "potion":
            item = Item("potion", subtype)
            self.identify(item)  # you brewed it; no mystery what it is
        elif kind == "food":
            item = Item("food", subtype)
        elif kind == "material":
            item = make_material(subtype, count=out_count)
        elif kind == "armor":
            item = make_armor(subtype)
        else:
            item = make_weapon(subtype)
        p = self.player
        tag = ""
        if kind in ("armor", "weapon"):
            bonus = 0
            if p.craft_level >= 5 and chance(0.10 + 0.05 * (p.craft_level - 5)):
                bonus, tag = 2, " It thrums with woven magic!"
            elif p.craft_level >= 3 and chance(0.20 + 0.05 * (p.craft_level - 3)):
                bonus, tag = 1, " A masterwork!"
            if kind == "armor":
                item.ac_ench += bonus
            else:
                item.hit_ench += bonus
                item.dmg_ench += bonus
        if not p.add_item(item):
            self.msg("Your pack is too full to hold the finished work.")
            return False
        self._consume_materials(needs)
        self.msg(f"You work at the table... and finish "
                 f"{self.item_name(item)}!{tag}")
        self._gain_craft_exp(needs)
        return True

    def copy_scroll(self, item):
        """Finish a copy-scroll craft once the source scroll is chosen."""
        needs, self.pending_copy = self.pending_copy, None
        if needs is None:
            return False
        if item is None or item.kind != "scroll":
            self.msg("You set the quill down, nothing copied.")
            return False
        if not self.is_identified(item):
            self.msg("You can't copy glyphs you don't yet understand.")
            return False
        self._consume_materials(needs)
        self.player.add_item(Item("scroll", item.subtype))
        self.msg(f"You painstakingly copy {self.item_name(item)}. "
                 "The new scroll joins the old.")
        self._gain_craft_exp(needs)
        return True

    def etch_scroll(self, item):
        """Finish an etch craft: the scroll becomes a permanent book spell."""
        needs, self.pending_etch = self.pending_etch, None
        if needs is None:
            return False
        p = self.player
        book = p.spellbook()
        if item is None or item.kind != "scroll" or book is None:
            self.msg("You set the burin down, nothing etched.")
            return False
        if not self.is_identified(item):
            self.msg("You can't etch glyphs you don't yet understand.")
            return False
        if item.subtype in book.contents:
            self.msg(f"The spell of {item.subtype} is already in your book.")
            return False
        if len(book.contents) >= 6:
            self.msg("Your spellbook is full — six spells, no more.")
            return False
        self._consume_materials(needs)
        p.remove_one(item)
        book.contents[item.subtype] = 1
        p.book_studied = False
        self.msg(f"You etch the spell of {item.subtype} into your "
                 f"spellbook ({len(book.contents)}/6). "
                 "Rest (.) to commit spells to memory.")
        self._gain_craft_exp(needs)
        return True

    # -- trading -------------------------------------------------------------

    def buy_price(self, item):
        cha = self.player.mod("Cha")
        return max(1, int(item_value(item) * (1.1 - 0.03 * cha)))

    def sell_price(self, item):
        cha = self.player.mod("Cha")
        return max(0, int(item_value(item) * 0.5 * (1 + 0.03 * cha)))

    def sellable(self, item):
        return (item is not self.player.weapon and item is not self.player.armor
                and item.kind != "amulet" and item_value(item) > 0)

    def buy(self, idx):
        p = self.player
        stock = self.level.trader_stock
        if not (0 <= idx < len(stock)):
            return
        item = stock[idx]
        price = self.buy_price(item)
        if p.gold < price:
            self.msg('"Come back when your purse is heavier," sniffs the trader.')
            return
        if not p.add_item(item):
            self.msg("Your pack is full.")
            return
        p.gold -= price
        stock.pop(idx)
        self.msg(f"You buy {self.item_name(item)} for {price} gold.")

    def sell(self, item):
        p = self.player
        if not self.sellable(item):
            self.msg('"I don\'t deal in such things," says the trader.')
            return
        price = self.sell_price(item)
        p.remove_one(item)
        p.gold += price
        self.msg(f"The trader pays you {price} gold.")

    # -- the healing temple --------------------------------------------------

    TEMPLE_BASE_PRICES = {
        "bless": 100, "remove curse": 150, "restore level": 300,
        "restore strength": 120, "holy water": 200,
    }
    # At the highest tithe tier, these four services are half price.
    TEMPLE_HALF_AT_MAX = {"bless", "remove curse", "restore level",
                          "restore strength"}

    def temple_price(self, service):
        base = self.TEMPLE_BASE_PRICES.get(service, 0)
        if (self.player.tithe_level() >= len(self.player.TITHE_TIERS) - 1
                and service in self.TEMPLE_HALF_AT_MAX):
            base //= 2
        return base

    def temple_bless(self):
        p = self.player
        price = self.temple_price("bless")
        if p.gold < price:
            self.msg("The acolyte shakes his head; you cannot pay the offering.")
            return
        p.gold -= price
        p.blessed += 30 + 20 * p.tithe_level()  # tithe deepens the favor
        self.msg("A serene light settles over you. You feel blessed "
                 f"(+1 to-hit, +1 AC) for {p.blessed} turns.")

    def temple_remove_curse(self):
        p = self.player
        price = self.temple_price("remove curse")
        if p.gold < price:
            self.msg("You cannot pay for the rite of cleansing.")
            return
        cursed = [it for it in (p.weapon, p.armor) if it is not None and
                  (it.hit_ench < 0 or it.dmg_ench < 0 or it.ac_ench < 0)]
        if not cursed:
            self.msg("The priest senses no curse upon you. Your gold stays.")
            return
        p.gold -= price
        for it in cursed:
            it.hit_ench = max(0, it.hit_ench)
            it.dmg_ench = max(0, it.dmg_ench)
            it.ac_ench = max(0, it.ac_ench)
        self.msg("Black vapors hiss away — the curse is lifted.")

    def temple_restore_level(self):
        p = self.player
        price = self.temple_price("restore level")
        if p.level >= p.max_level_reached:
            self.msg("Your spirit is whole; there is nothing to restore.")
            return
        if p.gold < price:
            self.msg("You cannot pay for the rite of restoration.")
            return
        p.gold -= price
        while p.level < p.max_level_reached:
            p.level += 1
            p.max_hp += max(1, p.cclass.hit_die // 2 + max(0, p.mod("Con")))
        p.exp = max(p.exp, p.exp_to_level(p.level))
        p.refresh_mana_cap()
        self.msg(f"Life floods back into you — restored to level {p.level}!")

    def temple_restore_strength(self):
        p = self.player
        price = self.temple_price("restore strength")
        if p.stats["Str"] >= p.max_str:
            self.msg("Your strength is already at its peak.")
            return
        if p.gold < price:
            self.msg("You cannot pay for the rite.")
            return
        p.gold -= price
        p.stats["Str"] = p.max_str
        self.msg("Vigor returns to your limbs; your strength is restored.")

    def temple_fill_holy_water(self):
        p = self.player
        price = self.temple_price("holy water")
        if p.gold < price:
            self.msg("The font is not free, pilgrim.")
            return
        if not p.add_item(make_holy_water()):
            self.msg("You have nothing to hold the holy water.")
            return
        p.gold -= price
        self.msg("You fill a vial at the sacred font. (a potion of holy water)")

    def temple_give_tithe(self, amount):
        p = self.player
        amount = min(amount, p.gold)
        if amount <= 0:
            self.msg("You have no gold to give.")
            return
        before = p.tithe_level()
        p.gold -= amount
        p.tithe_total += amount
        self.msg(f"You lay {amount} gold upon the altar.")
        if p.tithe_level() > before:
            self.msg(f"The gods take note — you are now a tithe-patron of "
                     f"rank {p.tithe_level()}. Blessings and prayers will "
                     "favor you more.")

    def temple_already_prayed(self):
        return self.level.temple_prayed

    def temple_pray(self):
        """A gamble: the higher your tithe, the kinder the answer.
        Each temple grants a single prayer — no grinding the altar."""
        p = self.player
        if self.level.temple_prayed:
            self.msg("You have already prayed at this altar. The gods "
                     "expect you to walk on.")
            return
        self.level.temple_prayed = True
        tl = p.tithe_level()
        roll_d = random.random() + 0.08 * tl  # devotion tips the scales
        if roll_d < 0.20:
            self.msg("The silence is absolute. Your prayer goes unanswered.")
            return
        if roll_d < 0.40:
            heal = roll("2d8") + p.level
            p.hp = min(p.max_hp, p.hp + heal)
            p.confused = 0
            self.msg("A gentle warmth mends your wounds and clears your head.")
            return
        if roll_d < 0.62:
            p.temp_hp = max(p.temp_hp, 5 + 2 * p.level + 3 * tl)
            self.msg(f"A shield of faith surrounds you — {p.temp_hp} "
                     "temporary hit points.")
            return
        if roll_d < 0.82:
            gain = 5 + p.level
            p.max_hp += gain
            p.hp += gain
            self.msg(f"You feel hardier — your maximum hit points rise by "
                     f"{gain}!")
            return
        if roll_d < 0.96:
            self.pending_stat_points += 1
            self.msg("The gods grant you a measure of their strength! "
                     "(an ability point to spend)")
            return
        # The rarest grace
        p.blessed += 60
        gain = 8 + p.level
        p.max_hp += gain
        p.hp += gain
        self.pending_stat_points += 1
        self.msg("A pillar of radiance engulfs you — you are profoundly "
                 "favored! (HP, an ability point, and a long blessing)")

    # -- magic ---------------------------------------------------------------

    def cast(self, spell):
        p = self.player
        if p.mana < spell.mana:
            self.msg("You haven't the strength of mind for that spell.")
            return False
        if spell.key.startswith("scroll:"):
            ok = self._scroll_effect(spell.key[7:])
        else:
            ok = getattr(self, "_sp_" + spell.key)()
        if ok:
            p.mana -= spell.mana
        return ok

    def _nearest_visible_monster(self):
        """Nearest target: hostiles first; never your own companion."""
        cands = [m for m in self.level.monsters
                 if not m.tamed and self.monster_visible(m)]
        if not cands:
            return None
        hostile = [m for m in cands if m.attitude == "hostile"]
        pool = hostile or cands
        p = self.player
        return min(pool, key=lambda m: _dist(p.x, p.y, m.x, m.y))

    def _sp_magic_missile(self):
        m = self._nearest_visible_monster()
        if not m:
            self.msg("There is nothing to aim at.")
            return False
        dmg = roll("2d6") + self.player.level // 2
        self.msg(f"A bolt of force strikes the {m.name}!")
        self._hurt_monster(m, dmg)
        return True

    def _sp_fireball(self):
        target = self._nearest_visible_monster()
        if not target:
            self.msg("There is nothing to aim at.")
            return False
        self.msg("A ball of fire blossoms!")
        tx, ty = target.x, target.y
        for m in list(self.level.monsters):
            if m.tamed:
                continue  # you'd never forgive yourself
            if _dist(tx, ty, m.x, m.y) <= 2:
                self._hurt_monster(m, roll("4d6"))
        return True

    def _sp_phantasm(self):
        m = self._nearest_visible_monster()
        if not m:
            self.msg("There is no mind to assault.")
            return False
        if "mindless" in m.type.flags:
            self.msg(f"The {m.name} has no mind to deceive.")
            return True
        dmg = roll("3d6") + self.player.level // 2
        self.msg(f"Horrors beyond reason assail the {m.name}!")
        self._hurt_monster(m, dmg)
        return True

    def _sp_confuse(self):
        m = self._nearest_visible_monster()
        if not m:
            self.msg("There is nothing to bewilder.")
            return False
        self._confuse_monster(m)
        return True

    def _sp_mass_confuse(self):
        any_hit = False
        for m in list(self.level.monsters):
            if self.monster_visible(m):
                self._confuse_monster(m)
                any_hit = True
        if not any_hit:
            self.msg("The phantasm dances for no one.")
            return False
        return True

    def _confuse_monster(self, m):
        if "mindless" in m.type.flags:
            self.msg(f"The {m.name} is unmoved.")
            return
        m.confused = 10 + roll("1d10")
        m.asleep = False
        self.msg(f"The {m.name} staggers, eyes spinning.")

    def _sp_light(self):
        self._light_room()
        return True

    def _sp_blink(self):
        p, lvl = self.player, self.level
        spots = [(x, y) for x in range(max(0, p.x - 6), p.x + 7)
                 for y in range(max(0, p.y - 6), p.y + 7)
                 if lvl.passable(x, y) and not lvl.monster_at(x, y)]
        if spots:
            p.x, p.y = random.choice(spots)
        self.msg("The world blinks.")
        self.compute_fov()
        self._step_on_tile()
        return True

    def _sp_teleport(self):
        self._teleport()
        return True

    def _sp_detect_monsters(self):
        self.detect_turns = 6
        self.msg("You sense the presence of monsters.")
        return True

    def _sp_cure_wounds(self):
        p = self.player
        p.hp = min(p.max_hp, p.hp + roll("1d8") + p.level // 2)
        self.msg("Warmth knits your wounds.")
        return True

    def _sp_haste(self):
        self.player.haste += 15
        self.msg("The world slows around you.")
        return True

    def _sp_sun_bolt(self):
        m = self._nearest_visible_monster()
        if not m:
            self.msg("There is nothing to aim at.")
            return False
        dmg = roll("1d3") + self.player.level // 4
        self.msg(f"A lance of sunlight sears the {m.name}!")
        self._hurt_monster(m, dmg)
        return True

    def _sp_gloom(self):
        """Dark-Elf innate: engulf the nearest foe in blinding gloom for
        six turns. It cannot see out; you see in and strike freely."""
        m = self._nearest_visible_monster()
        if not m:
            self.msg("There is no foe to engulf.")
            return False
        if "mindless" in m.type.flags and "undead" in m.type.flags:
            # eyeless skeletons/zombies aren't fooled by mere darkness
            self.msg(f"The gloom gathers, but the {m.name} has no eyes "
                     "to blind.")
            return True
        m.blinded = 6
        m.asleep = False
        self.msg(f"Darkness boils up and swallows the {m.name} — it gropes "
                 "blindly while you see clear within.")
        return True

    def _sp_calm_animal(self):
        p = self.player
        beasts = [m for m in self.level.monsters
                  if "tameable" in m.type.flags and not m.tamed
                  and self.monster_visible(m)]
        if not beasts:
            self.msg("There are no wild beasts in sight.")
            return False
        m = min(beasts, key=lambda b: _dist(p.x, p.y, b.x, b.y))
        m.attitude = "friendly"
        m.asleep = False
        m.confused = 0
        self.msg(f"The {m.name} settles, ears soft. It watches you kindly.")
        return True

    def _sp_summon_pet_food(self):
        if not self.player.add_item(Item("food", "pet food", count=2)):
            self.msg("Your pack is too full for conjured provender.")
            return False
        self.msg("Savory provender materializes in your pack.")
        return True

    def _sp_entangle(self):
        m = self._nearest_visible_monster()
        if not m:
            self.msg("There is nothing to bind.")
            return False
        m.rooted = 5 + roll("1d5")
        m.asleep = False
        self.msg(f"Vines erupt from the stone and bind the {m.name}!")
        return True

    def _sp_call_lightning(self):
        m = self._nearest_visible_monster()
        if not m:
            self.msg("The thunder finds no mark.")
            return False
        dmg = roll("3d8") + self.player.level // 2
        self.msg(f"Lightning cracks down upon the {m.name}!")
        self._hurt_monster(m, dmg)
        return True

    def _sp_invisibility(self):
        self.player.invis += 20 + roll("1d10")
        self.msg("Your outline fades from sight.")
        return True

    def _teleport(self):
        p = self.player
        spot = self.level.random_floor()
        if spot:
            p.x, p.y = spot
        self.msg("You are suddenly somewhere else.")
        self.compute_fov()
        self._step_on_tile()

    def _light_room(self):
        room = self.level.room_at(self.player.x, self.player.y)
        if room:
            room.lit = True
            self.msg("The room floods with light.")
            self.compute_fov()
        else:
            self.msg("The light gutters out in the cramped passage.")

    # -- combat ----------------------------------------------------------------

    def attack(self, mon, charging=False):
        p = self.player
        magical = p.weapon_is_magical()
        # Wraiths and the like shrug off mundane steel entirely.
        if "needs_magic" in mon.type.flags and not magical:
            self.msg(f"Your weapon passes through the {mon.name} "
                     "without effect — only enchanted arms or magic can "
                     "harm it!")
            mon.asleep = False
            return
        # A ghost is half-real; mundane blows often pass clean through.
        if ("incorporeal" in mon.type.flags and not magical
                and chance(0.5)):
            self.msg(f"Your blow passes harmlessly through the {mon.name}.")
            mon.asleep = False
            return
        was_oblivious = mon.asleep or mon.confused > 0
        mon.asleep = False
        attack_roll = random.randint(1, 20) + p.to_hit_bonus()
        if charging:
            attack_roll += 2
        if attack_roll < mon.type.ac:
            self.msg(f"You miss the {mon.name}.")
            return
        dmg = p.damage_roll()
        if charging:
            dmg += roll("1d8")
        if was_oblivious:
            if "backstab3" in p.cclass.traits:
                dmg *= 3
                self.msg(f"You drive your blade deep into the {mon.name}'s back!")
            elif "backstab2" in p.cclass.traits:
                dmg *= 2
                self.msg(f"You stab the {mon.name} from behind!")
        if p.rage_active() and not p.raging:
            p.raging = True
            self.msg("You fly into a berserk rage!")
        self._hurt_monster(mon, dmg, hit_msg=True)
        if ("weapon_master" in p.cclass.traits
                and mon in self.level.monsters and chance(0.2)):
            second = random.randint(1, 20) + p.to_hit_bonus()
            if second >= mon.type.ac:
                self.msg("You strike again in a flash of steel!")
                self._hurt_monster(mon, p.damage_roll())
        if (mon.hp > 0 and "diseased_bite" in p.race.traits
                and not mon.diseased
                and "undead" not in mon.type.flags
                and "mindless" not in mon.type.flags
                and chance(0.25)):
            mon.diseased = True
            self.msg(f"Your filthy bite festers in the {mon.name}'s wound!")

    def _hurt_monster(self, mon, dmg, hit_msg=False):
        mon.hp -= dmg
        if mon.hp > 0:
            if hit_msg:
                self.msg(f"You hit the {mon.name}.")
            mon.asleep = False
            if not mon.tamed and mon.attitude != "hostile":
                mon.attitude = "hostile"
                self.msg(f"The {mon.name} turns on you, wild-eyed!")
            return
        self.level.monsters.remove(mon)
        self.msg(f"You have slain the {mon.name}!"
                 if mon.is_boss else f"You have defeated the {mon.name}.")
        self._reward_kill(mon)

    def _reward_kill(self, mon):
        p = self.player
        p.exp += mon.xp
        self._check_level_up()
        if ("corpse_eater" in p.race.traits
                and "undead" not in mon.type.flags
                and _dist(p.x, p.y, mon.x, mon.y) <= 1):
            p.food = min(MAX_FOOD, p.food + 100 + mon.level * 20)
            self.msg("You feed greedily upon the corpse.")
        pos = (mon.x, mon.y)
        if "gold" in mon.type.flags and chance(0.7):
            self.level.items.setdefault(pos, []).append(
                make_gold(self.depth, rich=mon.is_boss))
        if mon.is_boss:
            if self.depth >= AMULET_DEPTH:
                self.level.items.setdefault(pos, []).append(make_amulet())
                self.msg("Something glitters amid the ruin of the fallen lord...")
            self.level.items.setdefault(pos, []).append(rand_item(self.depth))
        else:
            flags = mon.type.flags
            if "humanoid" in flags and chance(0.4):
                r = random.random()
                if r < 0.4:
                    drop = make_weapon(random.choice(list(WEAPON_DEFS)))
                elif r < 0.8:
                    drop = make_gold(self.depth)
                else:
                    drop = rand_item(self.depth)
                self.level.items.setdefault(pos, []).append(drop)
                self.msg(f"The {mon.name} drops something.")
            if ("humanoid" not in flags and "undead" not in flags
                    and chance(0.45)):
                drop = make_material(random.choice(("skin", "teeth", "hide")))
                self.level.items.setdefault(pos, []).append(drop)
                self.msg(f"You harvest {self.item_name(drop)} "
                         "from the carcass.")
            special = SPECIAL_PARTS.get(mon.type.name)
            if special and chance(special[1]):
                drop = make_material(special[0])
                self.level.items.setdefault(pos, []).append(drop)
                self.msg(f"You cut {self.item_name(drop)} from the "
                         f"{mon.name}.")
            # Fangs shed teeth — independent of (stacking with) all other
            # drops: an orc can yield gold, gear, an ear AND teeth.
            if "fangs" in flags and chance(0.3):
                drop = make_material("teeth")
                self.level.items.setdefault(pos, []).append(drop)
                self.msg(f"You pry sharp teeth from the {mon.name}'s jaw.")
        if pos in self.level.items and pos in self.level.visible:
            self.level.seen_items.add(pos)

    def _check_level_up(self):
        p = self.player
        while p.exp >= p.exp_to_level(p.level + 1):
            p.level += 1
            p.max_level_reached = max(p.max_level_reached, p.level)
            gain = random.randint(1, p.cclass.hit_die) + max(0, p.mod("Con"))
            gain = max(1, gain)
            p.max_hp += gain
            p.hp += gain
            old_spells = {s.key for s in p.cclass.spells if s.level <= p.level - 1}
            p.refresh_mana_cap()
            p.mana = p.max_mana
            self.msg(f"Welcome to level {p.level}!")
            for s in p.known_spells():
                if s.key not in old_spells and s.level == p.level:
                    self.msg(f"You have learned the spell of {s.name}!")
            every = 3 if "ambitious" in p.race.traits else 4
            if p.level % every == 0:
                self.pending_stat_points += 2
                self.msg("You feel your potential expand! "
                         "You may raise your abilities.")
            if p.level >= 10 and not p.knows_taming:
                p.knows_taming = True
                self.msg("Long roads teach quiet lessons — you have "
                         "learned the art of taming! (t)")

    def allocate_stat(self, name):
        p = self.player
        if self.pending_stat_points <= 0:
            return
        p.stats[name] = min(25, p.stats[name] + 1)
        if name == "Str":
            p.max_str = max(p.max_str, p.stats["Str"])
        p.refresh_mana_cap()
        self.pending_stat_points -= 1
        self.msg(f"You feel your {name} increase ({p.stats[name]}).")

    def _damage_player(self, dmg):
        """Apply damage, spending transient (prayer) hit points first."""
        p = self.player
        if p.temp_hp > 0:
            absorbed = min(p.temp_hp, dmg)
            p.temp_hp -= absorbed
            dmg -= absorbed
        p.hp -= dmg

    def monster_attack(self, mon):
        p = self.player
        flags = mon.type.flags
        attack_roll = random.randint(1, 20) + mon.level
        if attack_roll < p.ac:
            self.msg(f"The {mon.name} misses you.")
            return
        dmg = max(1, roll(mon.type.dmg))
        if "ferocious" in flags:
            dmg += roll("1d6")
        self._damage_player(dmg)
        self.msg(f"The {mon.name} hits you.")
        if "poison" in flags and "poison_immune" not in p.race.traits:
            save = random.randint(1, 20) + p.mod("Con")
            if "magic_resist" in p.race.traits:
                save += 3
            if save < 12:
                p.stats["Str"] = max(3, p.stats["Str"] - 1)
                self.msg("You feel a sting... and weaker.")
        if "acid" in flags and p.armor is not None and p.hp > 0:
            save = random.randint(1, 20) + p.mod("Dex")
            if "levitate" in p.race.traits or save >= 14:
                pass  # nimble enough to keep the acid off your gear
            else:
                p.armor.ac_ench -= 1
                self.msg(f"The {mon.name}'s touch corrodes your "
                         f"{p.armor.subtype}!")
        if ("spores" in flags and p.hp > 0
                and "magic_resist" not in p.race.traits):
            save = random.randint(1, 20) + p.mod("Con")
            if save < 13:
                p.confused += roll("1d6") + 3
                self.msg("Choking spores burst around you — the world reels!")
        if "drain_level" in flags and p.hp > 0:
            self._drain_level(mon)
        if p.hp <= 0:
            raise GameOver(f"killed by {self._kill_name(mon)}")

    def _drain_level(self, mon):
        """A spectre's chill steals a hard-won level (restore at a temple)."""
        p = self.player
        if "magic_resist" in p.race.traits and chance(0.5):
            self.msg("The draining chill washes over you, but your blood "
                     "holds its warmth.")
            return
        if p.level <= 1:
            p.exp = 0
            self.msg(f"The {mon.name} drains at your very essence!")
            return
        p.level -= 1
        loss = max(1, p.cclass.hit_die // 2 + max(0, p.mod("Con")))
        p.max_hp = max(1, p.max_hp - loss)
        p.hp = min(p.hp, p.max_hp)
        p.exp = p.exp_to_level(p.level)
        p.refresh_mana_cap()
        self.msg(f"The {mon.name}'s touch drains your life — "
                 f"you sink to level {p.level}! (restore it at a temple)")

    def _kill_name(self, mon):
        return mon.name if mon.is_boss else f"a {mon.name}"

    # -- traps -------------------------------------------------------------

    def _spring_trap(self, trap, pos):
        p = self.player
        if "levitate" in p.race.traits:
            if trap.hidden:
                trap.hidden = False
                self.msg(f"You flutter over a {trap.kind} trap.")
            return
        trap.hidden = False
        if trap.kind == "dart":
            save = random.randint(1, 20) + p.mod("Dex")
            if save >= 13:
                self.msg("A dart whizzes past your ear!")
            else:
                p.hp -= roll("1d6")
                self.msg("A small dart buries itself in your shoulder!")
                if p.hp <= 0:
                    raise GameOver("killed by a poisoned dart")
        elif trap.kind == "gas":
            save = random.randint(1, 20) + p.mod("Con")
            if "magic_resist" in p.race.traits:
                save += 3
            if "poison_immune" in p.race.traits or save >= 13:
                self.msg("A strange vapor curls around you, then fades.")
            else:
                p.stats["Str"] = max(3, p.stats["Str"] - 1)
                self.msg("A green gas envelops you. You feel weaker!")
        elif trap.kind == "teleport":
            self.msg("You step on a rune and the world lurches!")
            self._teleport()
        elif trap.kind == "trapdoor":
            self.msg("The floor gives way! You plummet into darkness!")
            p.hp -= roll("1d6")
            if p.hp <= 0:
                raise GameOver("died in a fall through a trapdoor")
            self.goto_depth(self.depth + 1, "random")

    # -- world tick ----------------------------------------------------------

    def world_tick(self):
        """Advance the world one step after a player action."""
        self.turn += 1
        p = self.player

        self._tick_hunger()

        skip_monsters = False
        if p.haste > 0:
            p.haste -= 1
            self.haste_parity = not self.haste_parity
            skip_monsters = self.haste_parity
        if p.invis > 0:
            p.invis -= 1
        if p.blessed > 0:
            p.blessed -= 1
            if p.blessed == 0:
                self.msg("The warmth of the blessing fades.")
        if p.temp_hp > 0 and self.turn % 8 == 0:
            p.temp_hp -= 1  # transient vigor bleeds away slowly
        if self.detect_turns > 0:
            self.detect_turns -= 1

        if not skip_monsters:
            self._monsters_act()
            self._random_encounter()

        self._regenerate()
        if not p.rage_active():
            p.raging = False
        self.compute_fov()

    def _tick_hunger(self):
        p = self.player
        slow = ("slow_digestion" in p.race.traits
                or "slow_digestion" in p.cclass.traits)
        if slow and self.turn % 2 == 0:
            return
        before = p.hunger_state()
        p.food -= 1
        after = p.hunger_state()
        if after != before and after:
            self.msg({"Hungry": "You are starting to feel hungry.",
                      "Weak": "You are weak from hunger!",
                      "Fainting": "You are fainting from lack of food!"}[after])
        if p.food <= -100:
            raise GameOver("starved to death")

    def _regenerate(self):
        p = self.player
        interval = max(3, 20 - p.level - p.mod("Con") * 2)
        if "regen" in p.race.traits:
            interval = max(2, interval // 2)
        if self.turn % interval == 0 and p.hp < p.max_hp:
            p.hp += 1
        if p.max_mana and self.turn % 6 == 0 and p.mana < p.max_mana:
            p.mana += 1

    def _random_encounter(self):
        if not chance(1 / 60):
            return
        # In wild rooms, the wild wanders in
        biome_rooms = [r for r in self.level.rooms
                       if not r.gone and r.biome]
        if biome_rooms and chance(0.3):
            room = random.choice(biome_rooms)
            spots = [t for t in room.floor_tiles()
                     if not self.level.monster_at(*t)
                     and t != (self.player.x, self.player.y)]
            if spots:
                m = make_animal(room.biome, self.depth)
                m.x, m.y = random.choice(spots)
                self.level.monsters.append(m)
                if m.type.genus == "fowl":  # a flock wanders in together
                    for _ in range(random.randint(1, 3)):
                        free = [t for t in room.floor_tiles()
                                if not self.level.monster_at(*t)
                                and t != (self.player.x, self.player.y)]
                        if not free:
                            break
                        bird = make_same_animal(m.type, self.depth)
                        bird.x, bird.y = random.choice(free)
                        self.level.monsters.append(bird)
                return
        spot = self.level.random_floor(avoid=(self.player.x, self.player.y),
                                       min_dist=10)
        if spot:
            m = Monster(choose_type(self.depth), spot[0], spot[1], self.depth)
            m.asleep = False
            self.level.monsters.append(m)

    def _monsters_act(self):
        p = self.player
        for m in list(self.level.monsters):
            if m not in self.level.monsters:
                continue
            if m.diseased:
                m.hp -= 1
                if m.hp <= 0:
                    self.level.monsters.remove(m)
                    if self.monster_visible(m):
                        self.msg(f"The {m.name} rots away before your eyes!")
                    self._reward_kill(m)
                    continue
            elif "regen" in m.type.flags and m.hp < m.max_hp:
                m.hp += 1
            if m.tamed:
                self._pet_act(m)
                continue
            # Sluggish things (cubes, fungi) act only every other turn
            if "slow" in m.type.flags and self.turn % 2 == 0:
                continue
            if m.asleep:
                self._maybe_wake(m)
                continue
            if m.blinded > 0:
                # Swallowed in gloom: gropes at random, can't find or
                # strike the player (who sees and attacks freely).
                m.blinded -= 1
                self._stumble(m)
                continue
            if m.confused > 0:
                m.confused -= 1
                self._move_random(m)
                continue
            if m.rooted > 0:
                m.rooted -= 1
                if (m.attitude == "hostile"
                        and _dist(m.x, m.y, p.x, p.y) <= 1):
                    self.monster_attack(m)
                continue
            if m.attitude != "hostile":
                if chance(0.4):
                    self._move_random(m)
                continue
            d = _dist(m.x, m.y, p.x, p.y)
            if d <= 1:
                self.monster_attack(m)
                continue
            pet = self.pet
            if (pet is not None and pet in self.level.monsters
                    and _dist(m.x, m.y, pet.x, pet.y) <= 1 and chance(0.4)):
                self._attack_pet(m, pet)
                continue
            chasing = True
            if p.invis > 0 and chance(0.7):
                chasing = False
            if "erratic" in m.type.flags and chance(0.5):
                chasing = False
            if chasing:
                self._move_toward(m, p.x, p.y)
            else:
                self._move_random(m)

    def _pet_act(self, pet):
        p = self.player
        target = next((m for m in self.level.monsters
                       if not m.tamed and m.attitude == "hostile"
                       and not m.asleep
                       and _dist(pet.x, pet.y, m.x, m.y) <= 1), None)
        if target:
            pet.stuck = 0
            attack_roll = random.randint(1, 20) + pet.level + 2
            if attack_roll >= target.type.ac:
                dmg = max(1, roll(pet.type.dmg) + pet.level // 3)
                target.hp -= dmg
                if target.hp <= 0:
                    self.level.monsters.remove(target)
                    if self.monster_visible(pet) or self.monster_visible(target):
                        self.msg(f"Your {pet.name} savages the "
                                 f"{target.name}!")
                    self._reward_kill(target)
                elif self.monster_visible(pet):
                    self.msg(f"Your {pet.name} bites the {target.name}.")
            return
        d = _dist(pet.x, pet.y, p.x, p.y)
        if d > 2:
            self._move_toward(pet, p.x, p.y)
            if _dist(pet.x, pet.y, p.x, p.y) >= d:
                pet.stuck += 1  # wedged on a corner, doorway or crowd
            else:
                pet.stuck = 0
            # Jumping: a companion that loses you jumps to your side.
            if d > 7 or pet.stuck >= 3:
                self._pet_jump(pet)
        else:
            pet.stuck = 0
            if chance(0.5):
                self._move_random(pet)

    def _pet_jump(self, pet):
        """Companions never truly lose you — they jump to your side."""
        spot = self._spot_near_player()
        if not spot:
            return
        pet.x, pet.y = spot
        pet.stuck = 0
        self.msg(f"Your {pet.name} jumps out of the gloom to your side.")

    def _attack_pet(self, m, pet):
        attack_roll = random.randint(1, 20) + m.level
        if attack_roll < pet.type.ac:
            if self.monster_visible(pet):
                self.msg(f"The {m.name} snaps at your {pet.name} and misses.")
            return
        pet.hp -= max(1, roll(m.type.dmg))
        if pet.hp <= 0:
            self.level.monsters.remove(pet)
            self.pet = None
            self.msg(f"Your {pet.name} is slain by the {m.name}! "
                     "You will remember it.")
        elif self.monster_visible(pet):
            self.msg(f"The {m.name} wounds your {pet.name}.")

    def _maybe_wake(self, m):
        p = self.player
        d = _dist(m.x, m.y, p.x, p.y)
        same_room = (self.level.room_at(m.x, m.y) is not None
                     and self.level.room_at(m.x, m.y)
                     is self.level.room_at(p.x, p.y))
        if d > 7 and not same_room:
            return
        base = 0.4 if (same_room or d <= 3) else 0.15
        if ("stealth" in p.race.traits or "stealth" in p.cclass.traits):
            base /= 2
        base *= max(0.5, 1 - max(0, p.mod("Cha")) * 0.05)
        if chance(base):
            m.asleep = False

    def _try_move(self, m, nx, ny):
        if not self.level.passable(nx, ny):
            return False
        if self._is_fixture(nx, ny):
            return False
        if self.level.monster_at(nx, ny):
            return False
        if (nx, ny) == (self.player.x, self.player.y):
            return False
        m.x, m.y = nx, ny
        return True

    def _move_toward(self, m, tx, ty):
        dx = (tx > m.x) - (tx < m.x)
        dy = (ty > m.y) - (ty < m.y)
        options = [(dx, dy), (dx, 0), (0, dy)]
        random.shuffle(options[1:])
        for ox, oy in options:
            if (ox, oy) != (0, 0) and self._try_move(m, m.x + ox, m.y + oy):
                return
        self._move_random(m)

    def _move_random(self, m):
        dirs = [(dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                if (dx, dy) != (0, 0)]
        random.shuffle(dirs)
        for dx, dy in dirs:
            if (m.x + dx, m.y + dy) == (self.player.x, self.player.y):
                if (m.confused == 0 and not m.tamed
                        and m.attitude == "hostile"):
                    self.monster_attack(m)
                    return
                continue
            if self._try_move(m, m.x + dx, m.y + dy):
                return

    def _stumble(self, m):
        """Move at random, never striking the player (blinded monsters)."""
        dirs = [(dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                if (dx, dy) != (0, 0)]
        random.shuffle(dirs)
        for dx, dy in dirs:
            if self._try_move(m, m.x + dx, m.y + dy):  # never the player tile
                return

    # -- scoring ---------------------------------------------------------------

    def score(self, won=False):
        p = self.player
        s = p.gold + 100 * self.max_depth_reached + 200 * p.level
        if won:
            s += 5000
        return s
