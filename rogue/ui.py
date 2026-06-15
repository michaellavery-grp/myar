"""Curses front end: title screens, map drawing, input, tombstone."""

import curses
import os
import pickle

from . import MAP_W, MAP_H, VERSION, SAVE_VERSION
from .dungeon import ROCK
from .game import Game, GameOver, GameWon
from .races import RACES, mods_summary
from .classes import CLASSES
from .player import STAT_NAMES, roll_stats

SAVE_PATH = os.path.expanduser("~/.myar_save.pkl")
SCORE_PATH = os.path.expanduser("~/.myar_scores")

MSG_ROW = 0
MAP_TOP = 1
STAT_ROW1 = MAP_H + 1   # 22
STAT_ROW2 = MAP_H + 2   # 23

MOVE_KEYS = {
    ord("h"): (-1, 0), ord("l"): (1, 0), ord("k"): (0, -1), ord("j"): (0, 1),
    ord("y"): (-1, -1), ord("u"): (1, -1), ord("b"): (-1, 1), ord("n"): (1, 1),
    curses.KEY_LEFT: (-1, 0), curses.KEY_RIGHT: (1, 0),
    curses.KEY_UP: (0, -1), curses.KEY_DOWN: (0, 1),
}

HELP_TEXT = """\
                       COMMANDS

  h j k l   move west / south / north / east
  y u b n   move diagonally (arrows also move)
  .         rest N turns          s   search for traps
            (asks how many; stops if a foe appears; then
             arcane casters may re-memorize spellbook spells)
  >         descend stairs       <   ascend stairs
  , or g    pick up item         i   inventory
  @         character sheet      f   fire bow (wielded)
  e         eat food             q   quaff potion
  r         read scroll          z   cast a spell
  w         wield weapon         W   wear armor
  T         take off armor       d   drop item
  c         charge (Minotaur)    C   craft (on a = table)
  t         tame a beast (needs pet food); aimed at your
            own companion, releases it into the wild
  S         save game and exit   Q   quit (no save)
  ?         this help

  Craft monster parts into gear at the = table. Trade
  with the $ trader every third level. Forest (") and
  savannah (') rooms hold wild beasts: tame one with
  pet food once you know the art — shrines (_) teach
  it early, or it comes at level 10. Your companion
  follows, fights, and takes the stairs at your heel.

  Walk into the temple (+, bold) on each level to bless,
  remove curses, restore drained levels or strength,
  fill holy water, or pray. Give a tithe to raise your
  standing: deeper devotion means kinder prayers and,
  at the highest rank, half-price rites. Ghosts and
  wraiths need an enchanted weapon or a spell to harm.

  Kill the boss every five levels. Take the Amulet of
  Yendor from Morgoth at 4950 feet, then climb back to
  the surface and ascend the stairs to win.

                 (press any key to continue)"""

TRAIT_DESC = {
    "stealth": "Stealth — monsters seldom wake at your passing",
    "slow_digestion": "Slow digestion — food lasts twice as long",
    "keen_eyes": "Keen eyes — sees farther in the dark, finds traps",
    "levitate": "Levitation — floats over floor traps",
    "poison_immune": "Poison immunity — venom and gas cannot harm you",
    "regen": "Regeneration — heals at twice the natural rate",
    "gore": "Horns — +2 melee damage",
    "magic_resist": "Magic resistance — +3 on saving throws",
    "corpse_eater": "Corpse eater — feeds on the freshly slain",
    "cantrip": "Sunfire Cantrip — innate spell (z), costs no mana",
    "perception": "Perception — may notice hidden traps nearby",
    "bowmaster": "Bowmaster — +2 to hit and +2 damage with bows",
    "charge": "Charge (c) — rush a foe in line: +2 hit, +1d8 damage",
    "labyrinth_sense": "Labyrinth sense — the exit compass on your status line",
    "diseased_bite": "Diseased bite — wounds of the living may fester and rot",
    "rage": "Rage — +2 hit / +3 damage when below 40% HP",
    "backstab2": "Backstab — double damage against unaware foes",
    "backstab3": "Backstab — TRIPLE damage against unaware foes",
    "search+": "Trained searcher — finds traps more often",
    "trap_lore": "Trap lore — senses adjacent traps automatically",
    "appraise": "Appraisal — may identify potions/scrolls on pickup",
    "dungeon_sense": "Dungeon sense — knows the layout of any room entered",
    "treasure_sense": "Treasure sense — richer gold finds",
    "ambitious": "Ambitious — ability increases every 3 levels, not 4",
    "weapon_master": "Weapon master — 20% chance to strike twice in melee",
    "beast_friend": "Beast-friend — +15% to taming attempts",
    "taming": "Beast-speech — the taming art known from level 1",
}


class Colors:
    def __init__(self):
        self.ok = False
        try:
            curses.start_color()
            curses.use_default_colors()
            for i, fg in enumerate((curses.COLOR_YELLOW, curses.COLOR_MAGENTA,
                                    curses.COLOR_CYAN, curses.COLOR_GREEN,
                                    curses.COLOR_RED, curses.COLOR_WHITE), 1):
                curses.init_pair(i, fg, -1)
            self.ok = True
        except curses.error:
            pass

    def pair(self, n, bold=False):
        a = curses.color_pair(n) if self.ok else 0
        return a | (curses.A_BOLD if bold else 0)


def _addstr(scr, y, x, text, attr=0):
    try:
        scr.addnstr(y, x, text, max(0, 80 - x), attr)
    except curses.error:
        pass


def item_attr(colors, item):
    if item.kind in ("gold", "amulet"):
        return colors.pair(1, bold=True)
    if item.kind == "potion":
        return colors.pair(2)
    if item.kind == "scroll":
        return colors.pair(3)
    if item.kind == "food":
        return colors.pair(4)
    return colors.pair(6)


def draw(scr, game, colors):
    scr.erase()
    lvl, p = game.level, game.player
    for y in range(MAP_H):
        for x in range(MAP_W):
            pos = (x, y)
            visible = pos in lvl.visible
            explored = pos in lvl.explored
            if not visible and not explored:
                continue
            ch, attr = lvl.grid[y][x], 0
            if ch == ROCK:
                continue
            if ch in "><":
                attr = colors.pair(6, bold=True)
            elif ch == "=":
                attr = colors.pair(3, bold=True)
            elif ch == '"':
                attr = colors.pair(4)        # forest grass
            elif ch == "'":
                attr = colors.pair(1)        # savannah scrub
            elif ch == "_":
                attr = colors.pair(6, bold=True)  # shrine of the wild
            trap = lvl.traps.get(pos)
            if trap and not trap.hidden:
                ch, attr = "^", colors.pair(5)
            if (visible or pos in lvl.seen_items) and pos in lvl.items:
                it = lvl.items[pos][-1]
                ch, attr = it.symbol, item_attr(colors, it)
            _addstr(scr, y + MAP_TOP, x, ch, attr)
    if lvl.trader_pos and (lvl.trader_pos in lvl.visible
                           or lvl.trader_pos in lvl.explored):
        _addstr(scr, lvl.trader_pos[1] + MAP_TOP, lvl.trader_pos[0], "$",
                colors.pair(1, bold=True))
    if lvl.temple_pos and (lvl.temple_pos in lvl.visible
                           or lvl.temple_pos in lvl.explored):
        _addstr(scr, lvl.temple_pos[1] + MAP_TOP, lvl.temple_pos[0], "+",
                colors.pair(3, bold=True))  # a bold cross: the temple
    for m in lvl.monsters:
        if game.monster_visible(m):
            if m.tamed:
                attr = colors.pair(4, bold=True)       # your companion
            elif m.attitude == "friendly":
                attr = colors.pair(4)
            elif m.attitude == "wary":
                attr = colors.pair(1)
            elif m.is_boss:
                attr = colors.pair(5, bold=True)
            else:
                attr = colors.pair(6, bold=True)
            _addstr(scr, m.y + MAP_TOP, m.x, m.type.ch, attr)
    _addstr(scr, p.y + MAP_TOP, p.x, "@", colors.pair(6, bold=True))

    s1 = (f"{p.name} the {p.race.name} {p.cclass.name}"
          f"    Lv:{p.level}  Exp:{p.exp}  Au:{p.gold}"
          f"  Dpth:{game.depth * 50}ft"
          + (f"  Exit:{game.exit_direction()}"
             if "labyrinth_sense" in p.race.traits else "")
          + ("  [AMULET]" if p.has_amulet else ""))
    mana = f"  Mn:{p.mana}/{p.max_mana}" if p.max_mana else ""
    hp_str = f"HP:{p.hp}/{p.max_hp}"
    if p.temp_hp > 0:
        hp_str += f"(+{p.temp_hp})"
    status = []
    if p.blessed > 0:
        status.append("Blessed")
    if p.confused > 0:
        status.append("Confused")
    status_str = ("  " + " ".join(status)) if status else ""
    s2 = (f"{hp_str}{mana}  AC:{p.ac}"
          f"  St:{p.stats['Str']} In:{p.stats['Int']} Wi:{p.stats['Wis']}"
          f" Dx:{p.stats['Dex']} Co:{p.stats['Con']} Ch:{p.stats['Cha']}"
          f"  {p.hunger_state()}{status_str}")
    _addstr(scr, STAT_ROW1, 0, s1, colors.pair(6))
    _addstr(scr, STAT_ROW2, 0, s2, colors.pair(6))


def show_messages(scr, game, colors):
    msgs = game.drain_msgs()
    if not msgs:
        _addstr(scr, MSG_ROW, 0, "")
        return
    # Word-wrap the whole queue: a single long message (a companion's
    # farewell, a tame success) must split into --More-- pages too,
    # not silently truncate at the screen edge.
    chunks = _wrap_text(" ".join(msgs), 70)
    for i, chunk in enumerate(chunks):
        scr.move(MSG_ROW, 0)
        scr.clrtoeol()
        more = "--More--" if i < len(chunks) - 1 else ""
        _addstr(scr, MSG_ROW, 0, f"{chunk} {more}", colors.pair(6, bold=True))
        scr.refresh()
        if more:
            while scr.getch() not in (ord(" "), ord("\n"), 27):
                pass


def select_item(scr, game, colors, kinds, verb):
    p = game.player
    items = [it for it in p.inventory if not kinds or it.kind in kinds]
    if not items:
        game.msg(f"You have nothing to {verb}.")
        return None
    h = len(items) + 2
    _overlay_box(scr, h, f" {verb.capitalize()} what? (ESC to cancel) ")
    for i, it in enumerate(items):
        tag = ""
        if it is p.weapon:
            tag = " (weapon in hand)"
        elif it is p.armor:
            tag = " (being worn)"
        _addstr(scr, 2 + i, 4, f"{it.letter}) {game.item_name(it)}{tag}")
    scr.refresh()
    while True:
        c = scr.getch()
        if c == 27:
            return None
        it = p.get_by_letter(chr(c)) if 0 < c < 256 else None
        if it and it in items:
            return it


def select_spell(scr, game, colors):
    p = game.player
    spells = p.known_spells()
    if not spells:
        game.msg("You know no spells.")
        return None
    _overlay_box(scr, len(spells) + 2, " Cast which spell? (ESC to cancel) ")
    for i, s in enumerate(spells):
        _addstr(scr, 2 + i, 4,
                f"{chr(ord('a') + i)}) {s.name}  [{s.mana} mana]")
    scr.refresh()
    while True:
        c = scr.getch()
        if c == 27:
            return None
        idx = c - ord("a")
        if 0 <= idx < len(spells):
            return spells[idx]


def _overlay_box(scr, height, title):
    for y in range(1, height + 2):
        _addstr(scr, y, 2, " " * 60)
    _addstr(scr, 1, 3, title, curses.A_REVERSE)


def show_inventory(scr, game, colors):
    p = game.player
    if not p.inventory:
        game.msg("Your pack is empty.")
        return
    _overlay_box(scr, len(p.inventory) + 2, " Inventory ")
    for i, it in enumerate(p.inventory):
        tag = ""
        if it is p.weapon:
            tag = " (weapon in hand)"
        elif it is p.armor:
            tag = " (being worn)"
        _addstr(scr, 2 + i, 4, f"{it.letter}) {game.item_name(it)}{tag}")
    _addstr(scr, len(p.inventory) + 2, 4, "(press any key)")
    scr.refresh()
    scr.getch()


def show_character_sheet(scr, game, colors):
    p = game.player
    scr.erase()
    _addstr(scr, 1, 4, f"{p.name} the {p.race.name} {p.cclass.name}",
            curses.A_BOLD)
    nxt = p.exp_to_level(p.level + 1)
    drained = (f" (drained from {p.max_level_reached})"
               if p.level < p.max_level_reached else "")
    _addstr(scr, 3, 4, f"Level {p.level}{drained}   Exp {p.exp}/{nxt}   "
            f"Gold {p.gold}   Depth {game.depth * 50}ft   "
            f"Craftsman Lv {p.craft_level}")
    mana = f"   Mana {p.mana}/{p.max_mana}" if p.max_mana else ""
    temp = f" (+{p.temp_hp} temp)" if p.temp_hp else ""
    _addstr(scr, 4, 4, f"HP {p.hp}/{p.max_hp}{temp}{mana}   AC {p.ac}"
            f"   Hunger: {p.hunger_state() or 'well fed'}")
    ranks = ["stranger", "supplicant", "faithful", "patron"]
    bits = [f"Tithe: {p.tithe_total} Au (rank {p.tithe_level()}, "
            f"{ranks[p.tithe_level()]})"]
    if p.blessed:
        bits.append(f"Blessed {p.blessed}")
    if p.confused:
        bits.append(f"Confused {p.confused}")
    _addstr(scr, 6, 4, "   ".join(bits))
    _addstr(scr, 5, 4, "   ".join(f"{s}:{p.stats[s]}" for s in STAT_NAMES))
    wield = game.item_name(p.weapon) if p.weapon else "nothing"
    worn = game.item_name(p.armor) if p.armor else "nothing"
    _addstr(scr, 7, 4, f"Wielding: {wield}")
    _addstr(scr, 8, 4, f"Wearing:  {worn}"
            + ("   [Amulet of Yendor]" if p.has_amulet else ""))
    row = 10
    pet = game.pet
    if pet is not None:
        here = pet in game.level.monsters
        _addstr(scr, 9, 4,
                f"Companion: a {pet.name} ({pet.type.genus}), "
                f"HP {pet.hp}/{pet.max_hp}"
                + ("" if here else " — waiting on another level"))
        row = 11
    _addstr(scr, row, 4, "Abilities:", curses.A_UNDERLINE)
    row += 1
    if p.race.infravision:
        _addstr(scr, row, 6, f"Infravision — senses warm bodies "
                f"{p.race.infravision} tiles off in the dark")
        row += 1
    traits = sorted(p.race.traits | p.cclass.traits)
    for t in traits:
        if row > 21:
            break
        _addstr(scr, row, 6, TRAIT_DESC.get(t, t))
        row += 1
    if not traits and not p.race.infravision:
        _addstr(scr, row, 6, "none — just grit and steel")
        row += 1
    spells = p.known_spells()
    if spells and row <= 20:
        row += 1
        _addstr(scr, row, 4, "Spells (cast with z):", curses.A_UNDERLINE)
        row += 1
        for s in spells:
            if row > 22:
                break
            cost = "no mana" if s.mana == 0 else f"{s.mana} mana"
            _addstr(scr, row, 6, f"{s.name}  [{cost}]")
            row += 1
    _addstr(scr, 23, 4, "(press any key)")
    scr.refresh()
    scr.getch()


def allocate_stats_overlay(scr, game, colors):
    p = game.player
    _overlay_box(scr, 8, f" Raise which ability?  "
                 f"({game.pending_stat_points} point"
                 f"{'s' if game.pending_stat_points > 1 else ''} left) ")
    for i, s in enumerate(STAT_NAMES):
        _addstr(scr, 2 + i, 4, f"{chr(ord('a') + i)}) {s}  {p.stats[s]}")
    scr.refresh()
    while True:
        c = scr.getch()
        idx = c - ord("a")
        if 0 <= idx < len(STAT_NAMES):
            game.allocate_stat(STAT_NAMES[idx])
            return


def roll_stats_screen(scr, race, cclass):
    while True:
        stats = roll_stats(race)
        scr.erase()
        _addstr(scr, 1, 6, "M.Y.A.R. — Mike's Yet Another Rogue", curses.A_BOLD)
        _addstr(scr, 3, 4, f"Your {race.name} {cclass.name} rolls the bones "
                "of fate:", curses.A_UNDERLINE)
        row = 5
        for s in STAT_NAMES:
            _addstr(scr, row, 8, f"{s}: {stats[s]:>2}")
            row += 1
        hp = race.hit_die + cclass.hit_die // 2 + max(0, (stats["Con"] - 10) // 2)
        _addstr(scr, row + 1, 8, f"Starting HP: {hp}")
        _addstr(scr, row + 3, 4, "(a)ccept these scores, or (r)oll again?")
        scr.refresh()
        while True:
            c = scr.getch()
            if c in (ord("a"), ord("\n"), ord(" ")):
                return stats
            if c == ord("r"):
                break


def craft_screen(scr, game, colors):
    from .items import RECIPES, MATERIALS
    if not game.at_crafting_table():
        game.msg("There is no crafting table here. Look for a '=' sign.")
        return False
    def label(key):
        if key.startswith("any:"):
            return "mixed scraps"
        if ":" in key:
            kind, sub = key.split(":", 1)
            return f"{sub} potion" if kind == "potion" else sub
        return key

    name_w = max(len(name) for name, _, _ in RECIPES) + 2
    while True:
        scr.erase()
        p = game.player
        _addstr(scr, 1, 4, "CRAFTING TABLE", curses.A_BOLD)
        nxt = p.craft_exp_to(p.craft_level + 1)
        _addstr(scr, 2, 4, f"Craftsman level {p.craft_level}   "
                f"({p.craft_exp}/{nxt} craft xp)")
        owned = [f"{m}:{game.material_count(m)}" for m in MATERIALS
                 if game.material_count(m) > 0]
        mat_lines, cur = [], ""
        for entry in owned:
            if cur and len(cur) + 2 + len(entry) > 62:
                mat_lines.append(cur)
                cur = entry
            else:
                cur = f"{cur}  {entry}".strip()
        mat_lines.append(cur or "none")
        _addstr(scr, 3, 4, f"Materials — {mat_lines[0]}")
        for k, extra in enumerate(mat_lines[1:]):
            _addstr(scr, 4 + k, 16, extra)
        top = 4 + len(mat_lines)
        makeable = [(i, RECIPES[i]) for i in game.craftable_now()]
        if not makeable:
            _addstr(scr, top, 4, "You lack the materials to make anything "
                    "here. Go hunting.", curses.A_DIM)
        for j, (i, (name, needs, _)) in enumerate(makeable):
            cost = ", ".join(f"{n} {label(s)}" for s, n in needs.items())
            _addstr(scr, top + j, 4,
                    f"{chr(ord('a') + j)}) {name:<{name_w}} [{cost}]",
                    curses.A_BOLD)
        _addstr(scr, top + max(1, len(makeable)) + 1, 4,
                "Craft which? (ESC to step away)")
        scr.refresh()
        c = scr.getch()
        if c == 27:
            return False
        j = c - ord("a")
        if 0 <= j < len(makeable):
            crafted = game.do_craft(makeable[j][0])
            if game.pending_copy is not None or game.pending_etch is not None:
                verb = "copy" if game.pending_copy is not None else "etch"
                it = select_item(scr, game, colors, ("scroll",), verb)
                if game.pending_copy is not None:
                    return game.copy_scroll(it)
                return game.etch_scroll(it)
            return crafted


def trade_screen(scr, game, colors):
    p = game.player
    mode = "buy"
    note = '"Welcome, friend! Cold steel and warm bread, fair prices."'
    while True:
        scr.erase()
        _addstr(scr, 1, 4, f"THE TRADER'S WAGON — {game.depth * 50} feet down",
                curses.A_BOLD)
        _addstr(scr, 2, 4, f"Your gold: {p.gold}    "
                "(TAB switches buy/sell, ESC leaves)")
        if mode == "buy":
            stock = game.level.trader_stock
            _addstr(scr, 4, 4, "For sale:", curses.A_UNDERLINE)
            if not stock:
                _addstr(scr, 5, 6, "The wagon is bare — you bought the lot.")
            for i, it in enumerate(stock):
                _addstr(scr, 5 + i, 4,
                        f"{chr(ord('a') + i)}) {game.item_name(it):<44}"
                        f"{game.buy_price(it):>6} Au")
        else:
            sellables = [it for it in p.inventory if game.sellable(it)]
            _addstr(scr, 4, 4, "The trader appraises your goods:",
                    curses.A_UNDERLINE)
            if not sellables:
                _addstr(scr, 5, 6, "Nothing in your pack interests them.")
            for i, it in enumerate(sellables):
                _addstr(scr, 5 + i, 4,
                        f"{it.letter}) {game.item_name(it):<44}"
                        f"{game.sell_price(it):>6} Au")
        _addstr(scr, 20, 4, note[:74], curses.A_DIM)
        scr.refresh()
        c = scr.getch()
        if c == 27:
            game.drain_msgs()
            return
        if c == 9:  # TAB
            mode = "sell" if mode == "buy" else "buy"
            continue
        if mode == "buy":
            idx = c - ord("a")
            if 0 <= idx < len(game.level.trader_stock):
                game.buy(idx)
        else:
            it = p.get_by_letter(chr(c)) if 0 < c < 256 else None
            if it and game.sellable(it):
                game.sell(it)
        msgs = game.drain_msgs()
        if msgs:
            note = " ".join(msgs)


def temple_screen(scr, game, colors):
    p = game.player
    note = '"Welcome, weary one. The gods watch the deep places too."'
    ranks = ["a stranger", "a supplicant", "a faithful giver", "a patron"]
    while True:
        scr.erase()
        _addstr(scr, 1, 4, f"THE HEALING TEMPLE — {game.depth * 50} feet down",
                curses.A_BOLD)
        tl = p.tithe_level()
        _addstr(scr, 2, 4, f"Gold: {p.gold}    Tithe given: {p.tithe_total} "
                f"(rank {tl} — {ranks[tl]})")
        # Afflictions the temple can mend — surfaced up front.
        ail = []
        if p.level < p.max_level_reached:
            ail.append(f"level drained to {p.level}/{p.max_level_reached}")
        if p.stats["Str"] < p.max_str:
            ail.append(f"Str sapped to {p.stats['Str']}/{p.max_str}")
        if any((it.hit_ench < 0 or it.dmg_ench < 0 or it.ac_ench < 0)
               for it in (p.weapon, p.armor) if it is not None):
            ail.append("cursed gear")
        _addstr(scr, 3, 4, ("Afflictions: " + "; ".join(ail)) if ail
                else "Afflictions: none — you are hale.",
                curses.A_BOLD if ail else curses.A_DIM)
        half = (" — HALF PRICE" if tl >= len(p.TITHE_TIERS) - 1 else "")
        prayed = game.temple_already_prayed()
        rows = [
            ("b", f"Bless ({game.temple_price('bless')} Au){half}"),
            ("r", f"Remove curse ({game.temple_price('remove curse')} Au){half}"),
            ("l", f"Restore level ({game.temple_price('restore level')} Au)"
                  + (f" — drained to {p.level}/{p.max_level_reached}"
                     if p.level < p.max_level_reached else "")),
            ("s", f"Restore strength "
                  f"({game.temple_price('restore strength')} Au)"),
            ("h", f"Fill holy water ({game.temple_price('holy water')} Au)"),
            ("p", "Pray (already answered here)" if prayed
                  else "Pray (free — once per temple; the gods answer as "
                       "they will)"),
            ("g", "Give tithe (offer gold; raises your standing)"),
        ]
        for i, (k, label) in enumerate(rows):
            _addstr(scr, 4 + i, 4, f"{k}) {label}")
        _addstr(scr, 4 + len(rows) + 1, 4, "(ESC to leave the temple)")
        _addstr(scr, 20, 4, note[:74], curses.A_DIM)
        scr.refresh()
        c = scr.getch()
        if c == 27:
            game.drain_msgs()
            return
        ch = chr(c) if 0 < c < 256 else ""
        if ch == "b":
            game.temple_bless()
        elif ch == "r":
            game.temple_remove_curse()
        elif ch == "l":
            game.temple_restore_level()
        elif ch == "s":
            game.temple_restore_strength()
        elif ch == "h":
            game.temple_fill_holy_water()
        elif ch == "p":
            game.temple_pray()
            _drain_temple_stat_points(scr, game, colors)
        elif ch == "g":
            amt = _prompt_amount(scr, "How much gold to tithe? ")
            if amt:
                game.temple_give_tithe(amt)
        msgs = game.drain_msgs()
        if msgs:
            note = " ".join(msgs)


def _prompt_amount(scr, prompt):
    _addstr(scr, 22, 4, prompt + " " * 20)
    curses.echo()
    curses.curs_set(1)
    try:
        raw = scr.getstr(22, 4 + len(prompt), 8)
    finally:
        curses.noecho()
        curses.curs_set(0)
    try:
        return max(0, int(raw.decode("utf-8", "replace").strip() or "0"))
    except ValueError:
        return 0


def _drain_temple_stat_points(scr, game, colors):
    """Prayer can grant ability points — spend them right here."""
    while game.pending_stat_points > 0:
        allocate_stats_overlay(scr, game, colors)


def _resolve_identify(scr, game, colors):
    if not game.pending_identify:
        return
    draw(scr, game, colors)
    show_messages(scr, game, colors)
    target = select_item(scr, game, colors, (), "identify")
    if target:
        game.identify_chosen(target)
    else:
        game.pending_identify = False


def study_menu(scr, game, colors):
    """Choose up to 3 spells from the etched spellbook to hold in mind."""
    from .classes import SCROLL_SPELL_MANA
    p = game.player
    game.offer_study = False
    p.book_studied = True
    book = p.spellbook()
    if book is None or not book.contents:
        return
    etched = sorted(book.contents)
    selected = [s for s in p.memorized if s in etched]
    # Sensible default: if nothing is currently in memory, pre-select the
    # etched spells (up to 3) so a plain ENTER memorizes what you wrote.
    if not selected:
        selected = etched[:3]
    enter_keys = (10, 13, curses.KEY_ENTER)
    while True:
        _overlay_box(scr, len(etched) + 4,
                     " Study spellbook (up to 3 in memory) ")
        for i, sub in enumerate(etched):
            mark = "x" if sub in selected else " "
            _addstr(scr, 2 + i, 4,
                    f"{chr(ord('a') + i)}) [{mark}] {sub}"
                    f"  [{SCROLL_SPELL_MANA.get(sub, 8)} mana]")
        _addstr(scr, 2 + len(etched), 4,
                f"In memory: {len(selected)}/3   "
                "(letter = toggle, ENTER = memorize, ESC = keep current)")
        scr.refresh()
        c = scr.getch()
        if c == 27:  # keep previous memorization
            return
        if c in enter_keys:
            p.memorized = list(selected)
            game.msg("The spells settle into your mind: "
                     + ", ".join(selected) + "." if selected
                     else "You close the book, mind calm and empty.")
            return
        i = c - ord("a")
        if 0 <= i < len(etched):
            sub = etched[i]
            if sub in selected:
                selected.remove(sub)
            elif len(selected) < 3:
                selected.append(sub)


def show_help(scr):
    lines = HELP_TEXT.splitlines()
    per_page = 21
    pages = [lines[i:i + per_page] for i in range(0, len(lines), per_page)]
    for pno, page in enumerate(pages):
        scr.erase()
        for i, line in enumerate(page):
            _addstr(scr, i + 1, 4, line)
        more = ("(press any key for more)" if pno < len(pages) - 1
                else "(press any key to return)")
        _addstr(scr, per_page + 2, 4, more)
        scr.refresh()
        scr.getch()


def confirm(scr, colors, question):
    _addstr(scr, MSG_ROW, 0, question + " " * 20, colors.pair(6, bold=True))
    scr.refresh()
    return scr.getch() in (ord("y"), ord("Y"))


def pick_from_menu(scr, title, entries):
    """entries: list of (name, info, desc). Returns chosen index.

    Up to 8 entries get the roomy two-line layout; larger lists (the
    class menu) go one line per entry so everything fits in 24 rows.
    """
    one_line = len(entries) > 8
    scr.erase()
    _addstr(scr, 1, 6, "M.Y.A.R. — Mike's Yet Another Rogue", curses.A_BOLD)
    _addstr(scr, 2, 6, f"v{VERSION} — in the manner of Rogue and Moria")
    _addstr(scr, 4, 4, title, curses.A_UNDERLINE)
    row = 6 if not one_line else 5
    for i, (name, info, desc) in enumerate(entries):
        if one_line:
            _addstr(scr, row, 4,
                    f"{chr(ord('a') + i)}) {name:<13} {info:<17} {desc}")
            row += 1
        else:
            _addstr(scr, row, 4, f"{chr(ord('a') + i)}) {name:<14} {info}")
            _addstr(scr, row + 1, 8, desc, curses.A_DIM)
            row += 2
    scr.refresh()
    while True:
        c = scr.getch()
        idx = c - ord("a")
        if 0 <= idx < len(entries):
            return idx


def prompt_name(scr):
    scr.erase()
    _addstr(scr, 4, 4, "What is your name, adventurer? ")
    curses.echo()
    curses.curs_set(1)
    try:
        raw = scr.getstr(4, 36, 18)
    finally:
        curses.noecho()
        curses.curs_set(0)
    name = raw.decode("utf-8", "replace").strip()
    return name or os.environ.get("USER", "Rodney").capitalize()


def _wrap_text(text, width):
    words = text.split()
    lines, cur = [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return lines or [""]


def tombstone(scr, game, cause, colors):
    p = game.player
    scr.erase()
    W = 26  # interior width of the stone; all text is centered inside it
    rows = [
        " " * 11 + "_" * (W - 8),
        " " * 10 + "/" + " " * (W - 8) + "\\",
        " " * 9 + "/" + "REST".center(W - 6) + "\\",
        " " * 8 + "/" + "IN".center(W - 4) + "\\",
        " " * 7 + "/" + "PEACE".center(W - 2) + "\\",
        " " * 6 + "/" + " " * W + "\\",
    ]

    def body(text=""):
        rows.append(" " * 6 + "|" + text[:W].center(W) + "|")

    body(p.name[:W])
    body(f"{p.race.name} {p.cclass.name}")
    body(f"{p.gold} Au")
    for line in _wrap_text(cause, W - 2)[:3]:
        body(line)
    body(f"at {game.depth * 50} feet")
    rows.append(" " * 5 + "*|" + "*    *    *".center(W) + "| *")
    rows.append("_" * 5 + r")/\\_//(\/(/\)/\//\/\/(/\)|_)" + "_" * 7)

    for i, line in enumerate(rows):
        _addstr(scr, i + 1, 8, line)
    base = len(rows) + 2
    _addstr(scr, base, 12,
            f"Score: {game.score()}   (deepest: {game.max_depth_reached * 50}ft, "
            f"level {p.level})")
    _addstr(scr, base + 2, 12, "press any key...")
    scr.refresh()
    scr.getch()


def victory(scr, game, colors):
    p = game.player
    scr.erase()
    lines = [
        "You emerge blinking into the sunlight,",
        "the Amulet of Yendor warm against your chest.",
        "",
        f"{p.name} the {p.race.name} {p.cclass.name} has conquered",
        "the Dungeons of Doom and the Lord of Darkness himself.",
        "",
        f"Gold: {p.gold}    Level: {p.level}    Score: {game.score(won=True)}",
        "",
        "Your name is whispered in songs forever after.",
        "",
        "press any key...",
    ]
    for i, line in enumerate(lines):
        _addstr(scr, 5 + i, 10, line, curses.A_BOLD if i < 2 else 0)
    scr.refresh()
    scr.getch()


def record_score(game, result):
    p = game.player
    won = result == "escaped with the Amulet"
    try:
        with open(SCORE_PATH, "a") as f:
            f.write(f"{game.score(won=won):>8}  {p.name} the {p.race.name} "
                    f"{p.cclass.name}, {result} at {game.depth * 50}ft\n")
    except OSError:
        pass


def load_save():
    if not os.path.exists(SAVE_PATH):
        return None
    try:
        with open(SAVE_PATH, "rb") as f:
            game = pickle.load(f)
        os.remove(SAVE_PATH)  # no save scumming
    except Exception:
        try:
            os.remove(SAVE_PATH)
        except OSError:
            pass
        return None
    if getattr(game, "save_version", -1) != SAVE_VERSION:
        from .savecompat import migrate_game
        game = migrate_game(game)  # carries old characters forward
    return game


def save_game(game):
    with open(SAVE_PATH, "wb") as f:
        pickle.dump(game, f)


def handle_key(scr, game, colors, c):
    """Dispatch one key. Returns True if a turn was consumed."""
    if c in MOVE_KEYS:
        dx, dy = MOVE_KEYS[c]
        return game.move_player(dx, dy)
    ch = chr(c) if 0 < c < 256 else ""
    if ch == ".":
        return game.rest()
    if ch == "s":
        return game.search()
    if ch == ">":
        return game.descend()
    if ch == "<":
        return game.ascend()
    if ch in (",", "g"):
        return game.pickup()
    if ch == "i":
        show_inventory(scr, game, colors)
        return False
    if ch == "@":
        show_character_sheet(scr, game, colors)
        return False
    if ch == "f":
        return game.fire()
    if ch == "c":
        _addstr(scr, MSG_ROW, 0, "Charge in which direction?" + " " * 40,
                colors.pair(6, bold=True))
        scr.refresh()
        c2 = scr.getch()
        if c2 in MOVE_KEYS:
            return game.charge(*MOVE_KEYS[c2])
        return False
    if ch == "C":
        return craft_screen(scr, game, colors)
    if ch == "t":
        _addstr(scr, MSG_ROW, 0, "Tame in which direction?" + " " * 40,
                colors.pair(6, bold=True))
        scr.refresh()
        c2 = scr.getch()
        if c2 not in MOVE_KEYS:
            return False
        dx, dy = MOVE_KEYS[c2]
        m = game.level.monster_at(game.player.x + dx, game.player.y + dy)
        if m is not None and m is game.pet:
            if confirm(scr, colors,
                       f"Release your {m.name} back into the wild? (y/n)"):
                return game.release_pet()
            return False
        return game.tame(dx, dy)
    if ch == "e":
        it = select_item(scr, game, colors, ("food",), "eat")
        return game.eat(it) if it else False
    if ch == "q":
        it = select_item(scr, game, colors, ("potion",), "quaff")
        return game.quaff(it) if it else False
    if ch == "r":
        it = select_item(scr, game, colors, ("scroll", "spellbook"), "read")
        if not it:
            return False
        consumed = game.read(it)
        _resolve_identify(scr, game, colors)
        return consumed
    if ch == "z":
        sp = select_spell(scr, game, colors)
        if not sp:
            return False
        consumed = game.cast(sp)
        _resolve_identify(scr, game, colors)  # Identify cast from the book
        return consumed
    if ch == "w":
        it = select_item(scr, game, colors, ("weapon",), "wield")
        return game.wield(it) if it else False
    if ch == "W":
        it = select_item(scr, game, colors, ("armor",), "wear")
        return game.wear(it) if it else False
    if ch == "T":
        return game.take_off()
    if ch == "d":
        it = select_item(scr, game, colors, (), "drop")
        return game.drop(it) if it else False
    if ch == "?":
        show_help(scr)
        return False
    return False


def main(stdscr):
    curses.curs_set(0)
    if curses.LINES < 24 or curses.COLS < 80:
        raise SystemExit("This game needs a terminal of at least 80x24.")
    colors = Colors()
    stdscr.keypad(True)

    game = load_save()
    if game is not None:
        game.msg("Your saved game crackles back to life. (save file consumed)")
    else:
        ridx = pick_from_menu(
            stdscr, "Choose your race:",
            [(r.name, f"{mods_summary(r)}   HD{r.hit_die}", r.desc)
             for r in RACES])
        cidx = pick_from_menu(
            stdscr, "Choose your class:",
            [(c.name, f"HD{c.hit_die}"
              + (f"  caster({c.mana_stat})" if c.mana_stat else ""),
              c.desc)
             for c in CLASSES])
        name = prompt_name(stdscr)
        stats = roll_stats_screen(stdscr, RACES[ridx], CLASSES[cidx])
        game = Game(name, RACES[ridx], CLASSES[cidx], stats)

    try:
        while True:
            draw(stdscr, game, colors)
            show_messages(stdscr, game, colors)
            try:
                c = stdscr.getch()
            except KeyboardInterrupt:
                c = ord("Q")
            if c == ord("Q"):
                if confirm(stdscr, colors, "Really quit without saving? (y/n)"):
                    record_score(game, "quit the dungeon")
                    return
                continue
            if c == ord("S"):
                if confirm(stdscr, colors, "Save and exit? (y/n)"):
                    save_game(game)
                    return
                continue
            try:
                # Resting asks how long, then rests that many turns
                # (interrupted if a hostile comes into view), and re-opens
                # spell memorization afterward for arcane casters.
                extra_rest = 0
                if c == ord("."):
                    n = _prompt_amount(stdscr,
                                       "Rest how many turns? (ENTER = 1) ")
                    extra_rest = max(0, (n or 1) - 1)
                consumed = handle_key(stdscr, game, colors, c)
                if game.trade_requested:
                    game.trade_requested = False
                    trade_screen(stdscr, game, colors)
                if game.temple_requested:
                    game.temple_requested = False
                    temple_screen(stdscr, game, colors)
                if consumed:
                    game.world_tick()
                    p = game.player
                    for _ in range(extra_rest):
                        if game.hostile_in_sight():
                            game.msg("A monster appears — you stop resting.")
                            break
                        if (p.hp >= p.max_hp
                                and p.mana >= p.max_mana):
                            game.msg("You are fully rested.")
                            break
                        game.rest()
                        game.world_tick()
                        draw(stdscr, game, colors)
                        stdscr.refresh()
                    while game.pending_stat_points > 0:
                        draw(stdscr, game, colors)
                        show_messages(stdscr, game, colors)
                        allocate_stats_overlay(stdscr, game, colors)
                    if game.offer_study:
                        draw(stdscr, game, colors)
                        show_messages(stdscr, game, colors)
                        study_menu(stdscr, game, colors)
                    while game.player.food <= 0 and game.player.food > -100:
                        # fainting: may lose turns
                        from .rng import chance as _ch
                        if not _ch(0.2):
                            break
                        game.msg("You faint from lack of food!")
                        draw(stdscr, game, colors)
                        show_messages(stdscr, game, colors)
                        game.world_tick()
            except GameOver as e:
                game.msgs.append("You die...")
                draw(stdscr, game, colors)
                show_messages(stdscr, game, colors)
                record_score(game, e.cause)
                tombstone(stdscr, game, e.cause, colors)
                return
            except GameWon:
                record_score(game, "escaped with the Amulet")
                victory(stdscr, game, colors)
                return
    finally:
        pass
