"""Rogue-style dungeon levels: a 3x3 grid of rooms joined by corridors."""

import random
from dataclasses import dataclass

from . import MAP_W, MAP_H, MAX_DEPTH, BOSS_EVERY
from .rng import chance
from .items import rand_item, make_gold, make_food
from .monsters import (Monster, choose_type, make_boss, make_animal,
                       make_same_animal)

GRID = 3
CELL_W = MAP_W // GRID       # 26
CELL_H = MAP_H // GRID       # 7

ROCK, FLOOR, WALL_H, WALL_V = " ", ".", "-", "|"
DOOR, PASSAGE, STAIRS_DOWN, STAIRS_UP = "+", "#", ">", "<"
CRAFT_TABLE = "="
FOREST, SAVANNAH = '"', "'"   # biome room floors: grass and dry scrub
SHRINE = "_"                  # a shrine of the wild teaches taming
PASSABLE = {FLOOR, PASSAGE, DOOR, STAIRS_DOWN, STAIRS_UP, CRAFT_TABLE,
            FOREST, SAVANNAH, SHRINE}
BIOME_FLOORS = {"forest": FOREST, "savannah": SAVANNAH}

TRADER_EVERY = 3  # a trader sets up shop on every third level
# The healing temple is an overlay fixture (like the trader), not a floor
# tile — you bump into it to pray. Drawn as a bold cross.
TEMPLE_GLYPH = "+"

TRAP_KINDS = ["dart", "gas", "teleport", "trapdoor"]


@dataclass
class Room:
    x: int
    y: int
    w: int
    h: int
    lit: bool = True
    gone: bool = False
    biome: str = ""   # "", "forest" or "savannah"

    def contains(self, x, y):
        return self.x <= x < self.x + self.w and self.y <= y < self.y + self.h

    def floor_tiles(self):
        for fy in range(self.y + 1, self.y + self.h - 1):
            for fx in range(self.x + 1, self.x + self.w - 1):
                yield fx, fy

    def all_tiles(self):
        for ty in range(self.y, self.y + self.h):
            for tx in range(self.x, self.x + self.w):
                yield tx, ty


@dataclass
class Trap:
    kind: str
    hidden: bool = True


class Level:
    def __init__(self, depth):
        self.depth = depth
        self.grid = [[ROCK] * MAP_W for _ in range(MAP_H)]
        self.rooms = []
        self.items = {}        # (x, y) -> [Item, ...]
        self.monsters = []
        self.traps = {}        # (x, y) -> Trap
        self.stairs_up = None
        self.stairs_down = None
        self.explored = set()
        self.visible = set()
        self.seen_items = set()
        self.boss_spawned = False
        self.crafting_table = None
        self.trader_pos = None
        self.trader_stock = []
        self.temple_pos = None

    def tile(self, x, y):
        if 0 <= x < MAP_W and 0 <= y < MAP_H:
            return self.grid[y][x]
        return ROCK

    def passable(self, x, y):
        return self.tile(x, y) in PASSABLE

    def monster_at(self, x, y):
        for m in self.monsters:
            if m.x == x and m.y == y:
                return m
        return None

    def room_at(self, x, y):
        for r in self.rooms:
            if not r.gone and r.contains(x, y):
                return r
        return None

    def random_floor(self, avoid=None, min_dist=0):
        spots = []
        for r in self.rooms:
            if r.gone:
                continue
            spots.extend(r.floor_tiles())
        random.shuffle(spots)
        for x, y in spots:
            if self.monster_at(x, y):
                continue
            if avoid and max(abs(x - avoid[0]), abs(y - avoid[1])) < min_dist:
                continue
            return x, y
        return spots[0] if spots else (self.stairs_up or self.stairs_down)


def _union(parent, a, b):
    ra, rb = _find(parent, a), _find(parent, b)
    if ra == rb:
        return False
    parent[ra] = rb
    return True


def _find(parent, a):
    while parent[a] != a:
        parent[a] = parent[parent[a]]
        a = parent[a]
    return a


def gen_level(depth):
    for _ in range(80):
        lvl = _try_gen(depth)
        if lvl is not None:
            return lvl
    raise RuntimeError("dungeon generation failed")


def _try_gen(depth):
    lvl = Level(depth)
    grid = lvl.grid
    rooms = {}

    gone_cells = set()
    for cell in random.sample(range(9), random.randint(0, 2)):
        gone_cells.add((cell % GRID, cell // GRID))

    for gy in range(GRID):
        for gx in range(GRID):
            cx, cy = gx * CELL_W, gy * CELL_H
            if (gx, gy) in gone_cells:
                jx, jy = cx + CELL_W // 2, cy + CELL_H // 2
                grid[jy][jx] = PASSAGE
                rooms[(gx, gy)] = Room(jx, jy, 1, 1, gone=True)
                continue
            w = random.randint(5, CELL_W - 2)
            h = random.randint(4, CELL_H - 1)
            x = cx + random.randint(0, CELL_W - 1 - w)
            y = cy + random.randint(0, CELL_H - 1 - h)
            lit = random.random() > min(0.04 * depth, 0.65)
            r = random.random()
            biome = "forest" if r < 0.12 else (
                "savannah" if r < 0.20 else "")
            room = Room(x, y, w, h, lit=lit, biome=biome)
            floor_ch = BIOME_FLOORS.get(biome, FLOOR)
            rooms[(gx, gy)] = room
            for ty in range(y, y + h):
                for tx in range(x, x + w):
                    if ty in (y, y + h - 1):
                        grid[ty][tx] = WALL_H
                    elif tx in (x, x + w - 1):
                        grid[ty][tx] = WALL_V
                    else:
                        grid[ty][tx] = floor_ch
    lvl.rooms = list(rooms.values())

    edges = []
    for gy in range(GRID):
        for gx in range(GRID):
            if gx + 1 < GRID:
                edges.append(((gx, gy), (gx + 1, gy), "h"))
            if gy + 1 < GRID:
                edges.append(((gx, gy), (gx, gy + 1), "v"))
    random.shuffle(edges)
    parent = {(gx, gy): (gx, gy) for gy in range(GRID) for gx in range(GRID)}
    chosen = []
    for a, b, d in edges:
        if _union(parent, a, b):
            chosen.append((a, b, d))
    for a, b, d in edges:
        if (a, b, d) not in chosen and chance(0.3):
            chosen.append((a, b, d))

    for a, b, d in chosen:
        _connect(grid, rooms[a], rooms[b], d)

    real_rooms = [r for r in lvl.rooms if not r.gone]
    up_room = random.choice(real_rooms)
    ux, uy = random.choice(list(up_room.floor_tiles()))
    grid[uy][ux] = STAIRS_UP
    lvl.stairs_up = (ux, uy)

    if depth < MAX_DEPTH:
        down_room = random.choice(real_rooms)
        dx, dy = random.choice(list(down_room.floor_tiles()))
        if (dx, dy) == (ux, uy):
            return None
        grid[dy][dx] = STAIRS_DOWN
        lvl.stairs_down = (dx, dy)

    if not _connected(lvl):
        return None

    _populate(lvl)
    return lvl


def _exit_point(room, side):
    """Door tile and corridor start just outside it. side: E/W/N/S."""
    if room.gone:
        return (room.x, room.y), (room.x, room.y)
    if side == "E":
        d = (room.x + room.w - 1, random.randint(room.y + 1, room.y + room.h - 2))
        return d, (d[0] + 1, d[1])
    if side == "W":
        d = (room.x, random.randint(room.y + 1, room.y + room.h - 2))
        return d, (d[0] - 1, d[1])
    if side == "S":
        d = (random.randint(room.x + 1, room.x + room.w - 2), room.y + room.h - 1)
        return d, (d[0], d[1] + 1)
    d = (random.randint(room.x + 1, room.x + room.w - 2), room.y)
    return d, (d[0], d[1] - 1)


def _dig(grid, x, y):
    if grid[y][x] == ROCK:
        grid[y][x] = PASSAGE


def _connect(grid, ra, rb, direction):
    if direction == "h":
        door_a, start = _exit_point(ra, "E")
        door_b, end = _exit_point(rb, "W")
        if not ra.gone:
            grid[door_a[1]][door_a[0]] = DOOR
        if not rb.gone:
            grid[door_b[1]][door_b[0]] = DOOR
        midx = random.randint(start[0], end[0])
        for x in range(start[0], midx + 1):
            _dig(grid, x, start[1])
        lo, hi = sorted((start[1], end[1]))
        for y in range(lo, hi + 1):
            _dig(grid, midx, y)
        for x in range(midx, end[0] + 1):
            _dig(grid, x, end[1])
    else:
        door_a, start = _exit_point(ra, "S")
        door_b, end = _exit_point(rb, "N")
        if not ra.gone:
            grid[door_a[1]][door_a[0]] = DOOR
        if not rb.gone:
            grid[door_b[1]][door_b[0]] = DOOR
        midy = random.randint(start[1], end[1])
        for y in range(start[1], midy + 1):
            _dig(grid, start[0], y)
        lo, hi = sorted((start[0], end[0]))
        for x in range(lo, hi + 1):
            _dig(grid, x, midy)
        for y in range(midy, end[1] + 1):
            _dig(grid, end[0], y)


def _connected(lvl):
    start = lvl.stairs_up
    seen = {start}
    stack = [start]
    while stack:
        x, y = stack.pop()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if (nx, ny) not in seen and lvl.passable(nx, ny):
                seen.add((nx, ny))
                stack.append((nx, ny))
    if lvl.stairs_down and lvl.stairs_down not in seen:
        return False
    for r in lvl.rooms:
        if r.gone:
            continue
        if not any(t in seen for t in r.floor_tiles()):
            return False
    return True


def _populate(lvl):
    depth = lvl.depth
    # Monsters
    count = random.randint(3, 5) + depth // 6
    for _ in range(count):
        spot = lvl.random_floor(avoid=lvl.stairs_up, min_dist=6)
        if not spot:
            continue
        mtype = choose_type(depth)
        lvl.monsters.append(Monster(mtype, spot[0], spot[1], depth))
        if "pack" in mtype.flags:
            for _ in range(random.randint(1, 3)):
                ps = lvl.random_floor(avoid=lvl.stairs_up, min_dist=6)
                if ps:
                    lvl.monsters.append(Monster(mtype, ps[0], ps[1], depth))

    # Boss guarding the way down (and at 99, the Amulet)
    if depth % BOSS_EVERY == 0 or depth == MAX_DEPTH:
        if lvl.stairs_down:
            anchor = lvl.stairs_down
            spot = _near(lvl, anchor) or lvl.random_floor()
        else:
            # Final level: Morgoth holds court far from the entrance.
            spot = lvl.random_floor(avoid=lvl.stairs_up, min_dist=12)
        if spot:
            lvl.monsters.append(Monster(make_boss(depth), spot[0], spot[1], depth))
            lvl.boss_spawned = True

    # Items and gold
    for _ in range(random.randint(2, 4)):
        spot = lvl.random_floor()
        if spot:
            lvl.items.setdefault(spot, []).append(rand_item(depth))
    for _ in range(random.randint(1, 3)):
        spot = lvl.random_floor()
        if spot:
            lvl.items.setdefault(spot, []).append(make_gold(depth))

    # Traps
    for _ in range(random.randint(0, 1 + depth // 8)):
        spot = lvl.random_floor(avoid=lvl.stairs_up, min_dist=3)
        if spot and spot not in lvl.traps and spot != lvl.stairs_down:
            kinds = TRAP_KINDS if depth < MAX_DEPTH else TRAP_KINDS[:3]
            lvl.traps[spot] = Trap(random.choice(kinds))

    # Wild animals roam the biome rooms, peaceable until provoked.
    # Birds of a feather flock together — fowl arrive 2-4 at a time.
    for room in lvl.rooms:
        if room.gone or not room.biome:
            continue
        for _ in range(random.randint(1, 2)):
            spots = [t for t in room.floor_tiles()
                     if not lvl.monster_at(*t)]
            if not spots:
                break
            m = make_animal(room.biome, depth)
            m.x, m.y = random.choice(spots)
            lvl.monsters.append(m)
            if m.type.genus == "fowl":
                for _ in range(random.randint(1, 3)):  # the rest of the flock
                    flock_spots = [t for t in room.floor_tiles()
                                   if not lvl.monster_at(*t)]
                    if not flock_spots:
                        break
                    bird = make_same_animal(m.type, depth)
                    bird.x, bird.y = random.choice(flock_spots)
                    lvl.monsters.append(bird)

    # A crafting table somewhere on every level
    spot = lvl.random_floor(avoid=lvl.stairs_up, min_dist=2)
    if spot and spot not in lvl.traps and spot not in (lvl.stairs_down,
                                                       lvl.stairs_up):
        lvl.grid[spot[1]][spot[0]] = CRAFT_TABLE
        lvl.crafting_table = spot

    # Sometimes, a mossy shrine of the wild (teaches the taming art)
    shrine_pos = None
    if chance(0.25):
        spot = lvl.random_floor(avoid=lvl.stairs_up, min_dist=2)
        if spot and lvl.tile(*spot) in (FLOOR, FOREST, SAVANNAH) \
                and spot not in lvl.traps:
            lvl.grid[spot[1]][spot[0]] = SHRINE
            shrine_pos = spot

    # A healing temple on every level — set up next to the shrine when
    # there is one, so the holy ground is shared.
    _place_temple(lvl, shrine_pos)

    # A trader every third level — a fixture, not a monster; can't be fought
    if depth % TRADER_EVERY == 0:
        spot = lvl.random_floor(avoid=lvl.stairs_up, min_dist=4)
        if (spot and spot not in lvl.traps and not lvl.monster_at(*spot)
                and lvl.tile(*spot) in (FLOOR, FOREST, SAVANNAH)):
            lvl.trader_pos = spot
            lvl.trader_stock = [rand_item(depth)
                                for _ in range(random.randint(4, 6))]
            lvl.trader_stock.append(make_food())
            from .items import make_pet_food
            lvl.trader_stock.append(make_pet_food())


def _near(lvl, pos):
    if not pos:
        return None
    for dx, dy in ((0, 1), (1, 0), (0, -1), (-1, 0), (1, 1), (-1, -1),
                   (1, -1), (-1, 1)):
        nx, ny = pos[0] + dx, pos[1] + dy
        if (lvl.tile(nx, ny) in (FLOOR, FOREST, SAVANNAH)
                and not lvl.monster_at(nx, ny)):
            return nx, ny
    return None


def _temple_ok(lvl, pos):
    if pos is None:
        return False
    if lvl.tile(*pos) not in (FLOOR, FOREST, SAVANNAH):
        return False
    return (pos not in lvl.traps and pos != lvl.trader_pos
            and pos not in (lvl.stairs_up, lvl.stairs_down)
            and not lvl.monster_at(*pos))


def _place_temple(lvl, shrine_pos):
    """Site the temple beside the shrine if possible, else anywhere open."""
    if shrine_pos is not None:
        spot = _near(lvl, shrine_pos)
        if _temple_ok(lvl, spot):
            lvl.temple_pos = spot
            return
    for _ in range(40):
        spot = lvl.random_floor(avoid=lvl.stairs_up, min_dist=3)
        if _temple_ok(lvl, spot):
            lvl.temple_pos = spot
            return
