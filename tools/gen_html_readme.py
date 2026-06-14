"""Generate readme.html — a color-coded HTML companion to README.md.

Screenshots are rendered from real generated levels using the game's own
data; bestiary and recipe tables are built from the live definitions so
they can never drift from the code.

Run from the repo root:  python3 tools/gen_html_readme.py
"""

import html
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from rogue import VERSION, MAX_DEPTH, BOSS_EVERY                  # noqa: E402
from rogue.dungeon import gen_level, ROCK                          # noqa: E402
from rogue.items import RECIPES, SYMBOLS                           # noqa: E402
from rogue.monsters import (MONSTERS, ANIMAL_TYPES, BOSS_NAMES,    # noqa: E402
                            FINAL_BOSS_NAME, SPECIAL_PARTS)

OUT = os.path.join(os.path.dirname(__file__), "..", "readme.html")

CSS = """
body { background:#15151a; color:#c8c8c8; font-family:Georgia,serif;
       max-width:900px; margin:2em auto; padding:0 1em; line-height:1.5; }
h1,h2,h3 { color:#e8d9a0; font-variant:small-caps; }
h1 { border-bottom:2px solid #5a4d2b; }
h2 { border-bottom:1px solid #3a3422; margin-top:2em; }
a { color:#7fb4d9; }
code, kbd { background:#22222a; color:#e0e0e0; padding:1px 5px;
            border-radius:3px; font-family:Menlo,monospace; }
pre.screen { background:#0a0a0e; border:1px solid #333; border-radius:6px;
             padding:14px; font:13px/1.15 Menlo,Monaco,monospace;
             overflow-x:auto; color:#9a9a9a; }
table { border-collapse:collapse; margin:1em 0; width:100%; }
th { background:#22222a; color:#e8d9a0; text-align:left; }
th,td { border:1px solid #333; padding:4px 10px; }
tr:nth-child(even) { background:#1a1a20; }
.letter { font-family:Menlo,monospace; font-weight:bold; text-align:center; }
.hostile { color:#e8e8e8; font-weight:bold; }
.wary    { color:#d9c34c; }
.friendly{ color:#5fd75f; }
.pet     { color:#6aff6a; font-weight:bold; }
.boss    { color:#ff5c5c; font-weight:bold; }
.gold    { color:#ffd700; font-weight:bold; }
.potion  { color:#d678d6; }
.scroll  { color:#6fd7d7; }
.food    { color:#5fd75f; }
.itm     { color:#e8e8e8; }
.forest  { color:#3fae3f; }
.savanna { color:#c8a93c; }
.door    { color:#d9c34c; }
.stairs  { color:#ffffff; font-weight:bold; }
.tbl     { color:#6fd7d7; font-weight:bold; }
.shrine  { color:#ffffff; font-weight:bold; }
.trader  { color:#ffd700; font-weight:bold; }
.player  { color:#ffffff; font-weight:bold; }
.wall    { color:#7a7a7a; }
.dim     { color:#555; }
.legend span { margin-right:1.4em; }
footer { margin-top:3em; color:#666; font-size:0.9em;
         border-top:1px solid #333; padding-top:1em; }
"""

TERRAIN_CLASS = {
    '"': "forest", "'": "savanna", "+": "door", ">": "stairs", "<": "stairs",
    "=": "tbl", "_": "shrine", "-": "wall", "|": "wall", ".": "dim",
    "#": "dim", "^": "boss",
}

ITEM_CLASS = {
    "gold": "gold", "amulet": "gold", "potion": "potion", "scroll": "scroll",
    "food": "food", "material": "food",
}


def span(cls, text):
    return f'<span class="{cls}">{html.escape(text)}</span>'


def monster_class(m):
    if m.tamed:
        return "pet"
    if m.attitude == "friendly":
        return "friendly"
    if m.attitude == "wary":
        return "wary"
    if m.is_boss:
        return "boss"
    return "hostile"


def render_level(lvl, player_pos=None):
    """Render a Level to colored HTML, everything revealed."""
    cells = {}
    for y, row in enumerate(lvl.grid):
        for x, ch in enumerate(row):
            if ch == ROCK:
                continue
            cells[(x, y)] = (ch, TERRAIN_CLASS.get(ch, "dim"))
    for pos, trap in lvl.traps.items():
        if not trap.hidden:
            cells[pos] = ("^", "boss")
    for pos, items in lvl.items.items():
        it = items[-1]
        cells[pos] = (it.symbol, ITEM_CLASS.get(it.kind, "itm"))
    if lvl.trader_pos:
        cells[lvl.trader_pos] = ("$", "trader")
    if lvl.temple_pos:
        cells[lvl.temple_pos] = ("+", "tbl")  # bold cross
    for m in lvl.monsters:
        cells[(m.x, m.y)] = (m.type.ch, monster_class(m))
    if player_pos:
        cells[player_pos] = ("@", "player")
    lines = []
    height = len(lvl.grid)
    width = len(lvl.grid[0])
    for y in range(height):
        out = []
        for x in range(width):
            if (x, y) in cells:
                ch, cls = cells[(x, y)]
                out.append(span(cls, ch))
            else:
                out.append(" ")
        lines.append("".join(out).rstrip())
    return "<pre class=\"screen\">" + "\n".join(lines) + "</pre>"


def find_showcase_level():
    """A depth-3 level with both biomes, animals and the trader."""
    for seed in range(500):
        random.seed(seed)
        lvl = gen_level(3)
        biomes = {r.biome for r in lvl.rooms if r.biome}
        animals = [m for m in lvl.monsters if "tameable" in m.type.flags]
        if {"forest", "savannah"} <= biomes and len(animals) >= 2 \
                and lvl.trader_pos:
            return lvl
    random.seed(1)
    return gen_level(3)


def find_boss_level():
    random.seed(11)
    return gen_level(50)  # the Balrog of Moria


def bestiary_animals():
    rows = []
    for biome, types in ANIMAL_TYPES.items():
        for t in types:
            cls = ("friendly" if t.diet in ("omnivore", "herbivore")
                   else "wary")
            attitude = "friendly" if cls == "friendly" else "wary"
            rows.append(
                f"<tr><td class='letter'>{span(cls, t.ch)}</td>"
                f"<td>{t.name}</td><td>{biome}</td><td>{t.genus}</td>"
                f"<td>{t.diet}</td><td class='{cls}'>{attitude}</td></tr>")
    return ("<table><tr><th>Letter</th><th>Animal</th><th>Biome</th>"
            "<th>Genus</th><th>Diet</th><th>Spawns as</th></tr>"
            + "".join(rows) + "</table>")


def bestiary_monsters():
    notes = {
        "erratic": "erratic flight", "poison": "poison",
        "regen": "regenerates", "undead": "undead", "pack": "packs",
        "gold": "carries gold", "humanoid": "humanoid",
        "mindless": "mindless", "fangs": "sheds teeth",
        "incorporeal": "incorporeal (mundane blows half-miss)",
        "needs_magic": "needs magic/enchanted weapon to harm",
        "drain_level": "drains a level", "spineless": "spineless",
        "acid": "corrodes armor", "spores": "confusing spores",
        "slow": "slow", "ferocious": "ferocious",
    }
    rows = []
    for t in MONSTERS:
        tags = [notes[f] for f in
                ("humanoid", "undead", "incorporeal", "needs_magic",
                 "drain_level", "spineless", "acid", "spores", "ferocious",
                 "mindless", "poison", "regen", "erratic", "pack", "slow",
                 "gold", "fangs") if f in t.flags]
        part = SPECIAL_PARTS.get(t.name)
        if part:
            tags.append(f"drops {part[0]}s")
        rows.append(
            f"<tr><td class='letter'>{span('hostile', t.ch)}</td>"
            f"<td>{t.name}</td><td>{t.min_depth}&ndash;{t.max_depth}</td>"
            f"<td>{', '.join(tags) or '&mdash;'}</td></tr>")
    return ("<table><tr><th>Letter</th><th>Monster</th><th>Depths</th>"
            "<th>Notes</th></tr>" + "".join(rows) + "</table>")


def bestiary_bosses():
    rows = []
    for i, (name, ch) in enumerate(BOSS_NAMES):
        depth = (i + 1) * BOSS_EVERY
        rows.append(
            f"<tr><td>{depth}</td><td class='boss'>{html.escape(name)}</td>"
            f"<td class='letter'>{span('boss', ch)}</td></tr>")
    rows.append(
        f"<tr><td><b>{MAX_DEPTH}</b></td>"
        f"<td class='boss'><b>{html.escape(FINAL_BOSS_NAME)}</b></td>"
        f"<td class='letter'>{span('boss', 'M')}</td></tr>")
    return ("<table><tr><th>Depth</th><th>Boss</th><th>Letter</th></tr>"
            + "".join(rows) + "</table>")


def recipes_table():
    def label(key):
        if key.startswith("any:"):
            opts = key[4:].split("|")
            return "any of: " + ", ".join(opts)
        if ":" in key:
            kind, sub = key.split(":", 1)
            return f"{sub} ({kind})"
        return key

    rows = []
    for name, needs, _ in RECIPES:
        cost = "; ".join(f"{n} &times; {html.escape(label(k))}"
                         for k, n in needs.items())
        rows.append(f"<tr><td>{html.escape(name)}</td><td>{cost}</td></tr>")
    return ("<table><tr><th>Item</th><th>Ingredients</th></tr>"
            + "".join(rows) + "</table>")


def legend():
    pairs = [
        ("hostile", "hostile monster"), ("wary", "wary beast"),
        ("friendly", "friendly beast"), ("pet", "your companion"),
        ("boss", "boss / trap"), ("trader", "$ trader"),
        ("forest", '" forest'), ("savanna", "' savannah"),
        ("tbl", "= crafting table"), ("shrine", "_ shrine"),
        ("gold", "* gold"), ("potion", "! potion"),
        ("scroll", "? scroll"), ("food", "% food / ~ material"),
    ]
    return ("<p class='legend'>"
            + "".join(span(c, "■") + f" {html.escape(t)} " for c, t in pairs)
            + "</p>")


def main():
    showcase = find_showcase_level()
    boss_lvl = find_boss_level()
    animals = sorted({m.name for m in showcase.monsters
                      if "tameable" in m.type.flags})
    boss = next(m for m in boss_lvl.monsters if m.is_boss)

    body = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>M.Y.A.R. — Mike's Yet Another Rogue</title>
<style>{CSS}</style></head><body>

<h1>M.Y.A.R. &mdash; Mike's Yet Another Rogue</h1>
<p><i>v{VERSION} &mdash; a classic terminal roguelike in the manner of
Rogue (1980) and The Mines of Moria. Pure Python, pure curses, zero
dependencies. See <a href="README.md">README.md</a> for the full
manual; this page is the color-rendered tour.</i></p>

<h2>The Quest</h2>
<p>The <b>Amulet of Yendor</b> lies 4,950 feet down on level
<b>{MAX_DEPTH}</b>, held by <b>{html.escape(FINAL_BOSS_NAME)}</b>.
A named boss guards every fifth level. Kill Morgoth, take the Amulet,
climb home. Death is permanent.</p>

<h2>Screenshot &mdash; the wild dungeon</h2>
<p>Depth 150ft: a <span class="forest">forest room</span> and a
<span class="savanna">savannah room</span> with wild beasts
({html.escape(", ".join(animals))}), a
<span class="trader">trader ($)</span>, a
<span class="tbl">crafting table (=)</span> and the way
<span class="stairs">down (&gt;)</span>.</p>
{render_level(showcase, player_pos=showcase.stairs_up)}
{legend()}

<h2>Screenshot &mdash; a boss level</h2>
<p>Depth 2,500ft: <span class="boss">{html.escape(boss.name)}
({boss.type.ch})</span> holds the stairs.</p>
{render_level(boss_lvl, player_pos=boss_lvl.stairs_up)}

<h2>Bestiary</h2>
<p>Colors as rendered in the terminal: white hostile, yellow wary,
green friendly, bright green your companion, red boss.</p>
<h3>Wild Animals (tameable)</h3>
{bestiary_animals()}
<h3>Monsters</h3>
{bestiary_monsters()}
<h3>Bosses &mdash; every {BOSS_EVERY}th level</h3>
{bestiary_bosses()}

<h2>Crafting Recipes</h2>
<p>Found at the <span class="tbl">= table</span> on every level; the
in-game menu shows only what your materials allow. From craftsman
level 3 results may be <b>masterwork (+1)</b>; from level 5,
<b>magical (+2)</b>.</p>
{recipes_table()}

<footer>Generated by <code>tools/gen_html_readme.py</code> from the
game's own data &mdash; regenerate after balance changes.
Release early, release often.</footer>
</body></html>
"""
    with open(OUT, "w") as f:
        f.write(body)
    print(f"wrote {os.path.normpath(OUT)} "
          f"({os.path.getsize(OUT)} bytes)")


if __name__ == "__main__":
    main()
