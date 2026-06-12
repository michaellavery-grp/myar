# M.Y.A.R. — Mike's Yet Another Rogue

A classic terminal roguelike in the tradition of the original **Rogue**
(1980) and **The Mines of Moria** — pure Python, pure curses, zero
dependencies.

```
 ---------                                -----------------
 |.......|                                |....C..........|
 |...@...+########                        +"""""""""""""".|
 |.......|       ##########################+..............|
 ---------                                |............>..|
                                          -----------------
```

---

## Table of Contents

- [Game Info](#game-info)
- [Controls](#controls)
- [Character Creation](#character-creation)
- [Races](#races)
- [Classes](#classes)
- [Leveling](#leveling)
- [Crafting & Craftsman Levels](#crafting--craftsman-levels)
- [Areas of the Dungeon](#areas-of-the-dungeon)
- [Bestiary](#bestiary)
- [Taming & Companions](#taming--companions)
- [Items & Identification](#items--identification)
- [Saving](#saving)
- [Development & Testing](#development--testing)

---

## Game Info

**The Quest:** the **Amulet of Yendor** lies 4,950 feet down, on dungeon
level **99**, in the claws of **Morgoth, Lord of Darkness**. A named boss
guards the stairs on **every fifth level**. Slay Morgoth, seize the
Amulet, and climb all the way back to the surface to win. Death is
permanent.

**Running it:**

```sh
cd ~/rogue
python3 -m rogue
```

Requires Python 3.9+ and a terminal of at least **80×24**.

**Reading the map:**

| Symbol | Meaning | Symbol | Meaning |
|:------:|---------|:------:|---------|
| `@` | you | `letters` | monsters (color = attitude) |
| `.` | floor | `#` | corridor |
| `-` `\|` | walls | `+` | door |
| `>` `<` | stairs down / up | `^` | revealed trap |
| `"` | forest grass | `'` | savannah scrub |
| `=` | crafting table | `_` | shrine of the wild |
| `$` | trader | `*` | gold |
| `!` | potion | `?` | scroll |
| `)` | weapon | `]` | armor |
| `%` | food | `~` | crafting material |
| `,` | the Amulet of Yendor | | |

Monster colors: **white** hostile, **yellow** wary, **green** friendly,
**bright green** your companion, **red** boss.

---

## Controls

```
h j k l     move west / south / north / east
y u b n     move diagonally           (arrow keys also move)
.           rest one turn             s   search for traps
> / <       descend / ascend stairs   , g pick up
i           inventory                 d   drop item
@           character sheet           ?   help
e           eat                       q   quaff potion
r           read scroll               z   cast a spell
w           wield weapon              W   wear armor
T           take off armor            f   fire bow
c           charge (Minotaur)         t   tame a beast
C           craft (on a = table)
S           save game and exit        Q   quit (no save)
```

---

## Character Creation

1. **Pick a race** (8) and **a class** (11).
2. **Roll your stats** — the classic six: **Str, Int, Wis, Dex, Con,
   Cha**, each rolled 3d6 best-of-two plus your racial modifier. Racial
   bonuses stack past 18: a Minotaur can open with **Str 22**, a Fairy
   with **Int 20**.
3. **Reroll freely** until you like the hand fate dealt, then accept.

Stat effects: **Str** melee to-hit and damage · **Dex** AC and accuracy ·
**Con** HP and regeneration · **Int/Wis** caster mana · **Cha** monster
wariness, starting gold, trader prices, and taming success.

---

## Races

| Race | Mods | HD | Abilities |
|------|------|:--:|-----------|
| **Human** | Ch+1 | 8 | Ambitious — stat gains every 3 levels; cheapest XP curve |
| **Hobbit** | St−2 In+1 Wi+1 Dx+3 Co+1 Ch+1 | 6 | Stealth, keen eyes, slow digestion |
| **Wood-Elf** | St−1 In+1 Wi+1 Dx+2 Co−1 Ch+1 | 7 | Keen eyes, stealth, perception (spots traps), bowmaster (+2/+2 with bows, starts with one), beast-friend (+15% taming), **innate taming from level 1** |
| **Sun-Elf** | St−1 In+2 Wi+2 Dx+1 Co−1 Ch+2 | 6 | Magic resistance, keen eyes, innate **Sunfire Cantrip** (free to cast) |
| **Dark-Elf** | In+1 Dx+2 Co−1 Ch−1 | 6 | Stealth, infravision 6 (sees warm bodies in the dark) |
| **Minotaur** | St+4 In−2 Wi−1 Dx−1 Co+2 Ch−2 | 12 | Gore (+2 melee), **charge** (`c`), labyrinth sense (exit compass), infravision 2 |
| **Fairy** | St−4 In+2 Wi+1 Dx+4 Co−2 Ch+2 | 4 | Levitates over traps, +3 AC, stealth — and very fragile |
| **Ghoul** | St+1 In−2 Wi−1 Dx−1 Co+3 Ch−4 | 9 | Poison immune, regenerates, feeds on the slain, **diseased bite** (wounds fester), infravision 3 |

---

## Classes

| Class | HD | Caster | Abilities |
|-------|:--:|:------:|-----------|
| **Fighter** | 10 | — | Best to-hit; weapon master (20% double strike) |
| **Barbarian** | 12 | — | Rage below 40% HP (+2 hit / +3 damage) |
| **Ranger** | 8 | Wis | Nature spells, stealth, searching, beast-friend, **innate taming from level 1** (+40% total); starts with pet food |
| **Thief** | 6 | — | Backstab ×2 vs unaware foes, stealth, searching |
| **Assassin** | 6 | — | Backstab **×3**, stealth |
| **Wizard** | 4 | Int | Magic Missile, Fire Ball, Haste, Teleport… |
| **Illusionist** | 4 | Int | Confusion, Blink, Invisibility, Phantasmal Blast… |
| **Explorer** | 8 | — | Dungeon sense (maps rooms), slow digestion, searching |
| **Archeologist** | 8 | — | Trap lore (auto-detect), appraisal (auto-identify), treasure sense, whip |
| **Druid** | 8 | Wis | Calm Animal, Summon Provender, Entangle, Call Lightning, Wind Walk; **tames from level 1** (+25%) |
| **Shaman** | 6 | Wis | Soothe the Wild, Spirit Bolt, Spirit Feast, Ghost Dance, Dream Walk; **tames from level 1** (+25%) |

Casters regain mana over time; mana grows with level and Int (arcane) or
Wis (nature/spirit). New spells announce themselves as you level.

---

## Leveling

- **Experience** comes from kills (and half-XP from successful tamings).
  Each race and class has an XP multiplier — Humans level cheapest,
  Wizards and Fairies pay a premium for their gifts.
- **Hit points** rise each level by your class hit die plus Con bonus.
- **Ability increases:** every **4th level** (every **3rd** for Humans)
  you receive **2 ability points** — put both in one stat (+2) or split
  them across two (+1/+1). Stats cap at 25.
- **Taming** is learned automatically at **level 10** (see
  [Taming](#taming--companions) for earlier paths).

---

## Crafting & Craftsman Levels

Every level of the dungeon has a **crafting table** (`=`). Stand on it
and press `C` — the menu shows **only what you can make right now**.

- **Materials** come from kills, and all of them live in your **crafting
  bag**: one inventory slot, bottomless, undroppable.
  - **Beasts** (not humanoid, not undead) drop skins, teeth and hides.
  - **Signature parts:** rat tails, bat eyes, snake venom, orc ears,
    kobold tails, **bones** from skeletons, **drake and dragon hides**.
  - **Humanoids** may drop a weapon, gold or gear instead.
- **The leather ladder:** leather [2] → hide [3] → **studded leather**
  [4] (a leather armor + 4 teeth) → **bone armor** [5] → … →
  **drake-scale [8]** → **dragon-scale [9]**, the finest armor in the
  game. Scale and bone tiers are **craft-only** — never loot.
- **Bows & arrows:** short and long bows; **fine arrows** (+1 bow damage,
  permanent); **poison arrows** (brew a vial of poison from snake venom,
  then envenom a bow for 8 shots, +1d6 each — the undead don't care).
- **Provisions:** savage brew (a strength potion), kobold-tail soup
  (a full ration), and **pet food** — **any two small parts** (bat eye,
  rat tail, bone, orc ear, kobold tail, in any combination) make one
  portion. A bat eye and a bone? Dinner.
- **Craftsman levels:** every craft earns craft-XP (shown on the table
  screen and your `@` sheet). From **craftsman level 3** your work can
  come out **masterwork** (+1); from **level 5**, **magical** (+2) — the
  odds improve with every level beyond.

---

## Areas of the Dungeon

- **99 levels**, each a classic 3×3 lattice of rooms and corridors. Deep
  rooms are more often dark. Depth is measured in feet (50 per level).
- **Forest rooms** (`"`) and **savannah rooms** (`'`) are wild biomes
  where tameable animals live and wander in over time.
- **Shrines of the wild** (`_`) appear on roughly a quarter of levels —
  step on one to learn taming early.
- **Crafting tables** (`=`) — one per level, always.
- **Traders** (`$`) — every **3rd level**. Walk into them to buy and
  sell (TAB switches modes). They cannot be attacked, monsters leave
  them be, and **Charisma sways their prices** both ways.
- **Bosses** — every **5th level**, a named guardian holds the stairs
  down: Grip the Warg Chieftain, Bert the Stone Troll, the Balrog of
  Moria at 2,500 feet… and **Morgoth at 99** with the Amulet.
- **Monsters scale** with depth, wander in as random encounters, and
  range from rats and jackals to liches, balrogs, ancient dragons and
  titans. Traps hide underfoot: darts, gas, teleports and trapdoors.

---

## Bestiary

On-screen colors: **white** = hostile, **yellow** = wary (won't attack
unless provoked), **green** = friendly, **bright green** = your
companion, **red** = boss. See [readme.html](readme.html) for the
color-rendered version.

### Wild Animals (tameable)

| Letter | Animal | Biome | Genus | Diet | Spawns as |
|:------:|--------|-------|-------|------|-----------|
| `C` | wolf | forest | canine | carnivore | wary |
| `f` | panther | forest | feline | carnivore | wary |
| `q` | wild boar | forest | boar | omnivore | friendly |
| `q` | stag | forest | cervine | herbivore | friendly |
| `f` | lion | savannah | feline | carnivore | wary |
| `C` | hyena | savannah | canine | carnivore | wary |
| `q` | antelope | savannah | cervine | herbivore | friendly |

### Monsters (hostile)

| Letter | Monster | Depths | Notes |
|:------:|---------|:------:|-------|
| `r` | giant rat | 1–6 | drops rat tails |
| `b` | bat | 1–8 | erratic flight; drops bat eyes |
| `k` | kobold | 1–7 | humanoid; drops kobold tails |
| `j` | jackal | 1–6 | hunts in packs |
| `s` | snake | 2–11 | poison; drops venom glands |
| `g` | goblin | 2–12 | humanoid |
| `S` | skeleton | 2–20 | undead; drops bones |
| `o` | orc | 3–16 | humanoid, carries gold; drops orc ears |
| `z` | zombie | 4–16 | undead, mindless |
| `H` | hobgoblin | 5–18 | humanoid |
| `c` | giant centipede | 5–18 | poison |
| `W` | wight | 7–22 | undead |
| `O` | ogre | 8–26 | humanoid, carries gold |
| `T` | cave troll | 10–34 | humanoid, regenerates |
| `w` | wraith | 12–40 | undead |
| `V` | vampire | 14–48 | undead, regenerates |
| `P` | stone giant | 15–55 | humanoid, carries gold |
| `L` | lich | 22–70 | undead |
| `d` | fire drake | 25–75 | drops drake hides |
| `B` | balrog | 30–85 | of Morgoth's brood |
| `&` | greater demon | 40–99 | |
| `D` | ancient dragon | 50–99 | carries gold; drops dragon hides |
| `P` | titan | 60–99 | humanoid, carries gold |

### Bosses (every 5th level — red on screen)

| Depth | Boss | Letter |
|:-----:|------|:------:|
| 5 | Grip, the Warg Chieftain | `j` |
| 10 | Boldor, King of the Yeeks | `k` |
| 15 | Grishnakh, the Hill Orc | `o` |
| 20 | The Barrow-Wight King | `W` |
| 25 | Gorbag of Minas Morgul | `o` |
| 30 | Bert the Stone Troll | `T` |
| 35 | Ulfang the Black | `H` |
| 40 | The Ogre Tyrant | `O` |
| 45 | Shelob's Last Daughter | `c` |
| 50 | The Balrog of Moria | `B` |
| 55 | Khamul, the Easterling | `w` |
| 60 | Itangast the Fire Drake | `d` |
| 65 | The Witch-King's Herald | `w` |
| 70 | Vlad, Sire of the Night | `V` |
| 75 | The Stone Titan | `P` |
| 80 | Maeglor the Lich-Lord | `L` |
| 85 | Glaurung, Father of Dragons | `D` |
| 90 | Gothmog, High Captain of Balrogs | `B` |
| 95 | Ancalagon the Black | `D` |
| **99** | **Morgoth, Lord of Darkness** | `M` |

All bosses guard the down staircase, carry rich hoards, and regenerate.
Morgoth holds the Amulet of Yendor.

## Taming & Companions

- **Learn the art:** Druids, Shamans, **Rangers and Wood-Elves** know it
  from level 1. Everyone else learns at **level 10**, or early at a
  **shrine of the wild**.
- **Wild beasts** live in biome rooms, tracked by **genus** — canine
  (wolf, hyena), feline (panther, lion), cervine (stag, antelope), boar —
  and **diet**: grazers spawn *friendly* (green), hunters *wary*
  (yellow). None attack unless provoked; provoke one and it turns.
- **To tame:** stand next to a beast, press `t` and a direction. Each
  attempt feeds it one portion of **pet food** (craft, buy, or conjure
  it). Success rises with **Cha**, the beast's mood, and your gifts:
  **+25%** for Druids, Shamans and Rangers (class gift), **+15%** more
  for beast-friends (Rangers and Wood-Elves, stacking — a Wood-Elf
  Ranger tames at +55%). Calm Animal makes any beast friendly first —
  the easiest mark.
- **Your companion** (one at a time) follows at heel, savages hostile
  monsters (kills credit you), swaps places when you bump into it, rides
  trapdoors and staircases with you when within 2 tiles — or waits
  faithfully on the old level. It appears on your `@` sheet with its HP.
- Animals **scale with depth** — a wolf tamed at 3,000 feet is a dire
  companion. Pets can die; monsters will snap back at them. Your spells
  and arrows will never target your own companion.

---

## Items & Identification

- **Potions and scrolls are unidentified** each game ("a murky potion",
  "a scroll titled 'ZELGOR NYM ASH'") until drunk, read, identified by
  scroll, or appraised (Archeologist). Brews you craft yourself are
  always identified.
- Weapons carry to-hit/damage enchantments (`a +1,+2 long sword`),
  armor an AC bonus; both can be raised by enchant scrolls, masterwork
  or magical crafting.
- **Hunger** is the clock: eat rations before you weaken. Hobbits,
  Ghouls and Explorers digest slowly; Ghouls also feed on the slain.
- Multiple items pile on one tile, and walking over a pile picks up
  **everything**.

---

## Saving

- `S` saves to `~/.myar_save.pkl` and exits. The save loads
  automatically on next launch and is **consumed on load** — no
  save-scumming. Permadeath is honored: dying ends the character.
- **Saves survive updates.** When the save format changes, your game is
  **migrated in place** — new traits, the crafting bag, biome regrowth
  and so on are patched into your existing character instead of wiping
  it. Old levels even sprout the occasional wild room ("wild regrowth")
  so new features reach saves that predate them.
- High scores append to `~/.myar_scores`.

---

## Development & Testing

```sh
python3 -m rogue.smoke_test    # headless engine tests (no terminal needed)
python3 pty_test.py            # drives the real curses UI through a pty
```

The smoke test covers level generation at all depths, bosses, combat,
spells, crafting, taming, biomes, traders, drop balance and the Morgoth
fight.

**Save fixture:** a copy of a real save lives at `testdata/user_save.pkl`.
Every test run loads it, migrates it to the current save version, and
plays 80 turns — so format changes can't silently break a long-running
character. Refresh it any time with:

```sh
cp ~/.myar_save.pkl testdata/user_save.pkl
```
