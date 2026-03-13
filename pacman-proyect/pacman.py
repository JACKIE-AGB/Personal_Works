"""
╔══════════════════════════════════════════════════╗
║              PAC-MAN  —  pacman.py               ║
║  Requires: pip install pygame                    ║
║  Run:      python pacman.py                      ║
╚══════════════════════════════════════════════════╝

Controls:  Arrow keys  or  WASD
Ghost AI:  Edit ghost_ai.py — no changes needed here
"""

import pygame
import sys
import math
import time
from ghosts_ai import (
    GHOST_AI, compute_ghost_direction,
    DIRECTION_VECTORS, OPPOSITES, ALL_DIRS, _is_passable,
)

# ══════════════════════════════════════════════════
#  CONSTANTS
# ══════════════════════════════════════════════════
TS        = 22          # tile size in pixels
FPS       = 60
TITLE     = "PAC-MAN"

# Colours
BLACK       = (0,   0,   0)
MAZE_BLUE   = (30,  30, 220)
MAZE_BRIGHT = (60,  60, 255)
YELLOW      = (255, 224,   0)
WHITE       = (255, 255, 255)
RED         = (255,   0,   0)
DOT_COLOR   = (255, 184, 174)
PINK        = (255, 184, 255)
CYAN        = (  0, 255, 255)
ORANGE      = (255, 184,  82)
FRIGHTENED  = (  0,   0, 200)
FRIGHT_FLASH= (255, 255, 255)
EATEN_EYES  = (  0,  30, 255)

# Speeds (pixels/frame)
PACMAN_SPEED  = 1.8
GHOST_SPEED   = 1.4
FRIGHT_SPEED  = 0.9
EATEN_SPEED   = 3.0

# Mode timing (frames)  scatter/chase alternation
SCATTER_FRAMES = [7*FPS, 5*FPS, 5*FPS, 5*FPS]
CHASE_FRAMES   = [20*FPS, 20*FPS, 20*FPS, 10**9]  # last = infinite
FRIGHTENED_DUR = 8 * FPS   # reduced per level

# Tile values
WALL   = 1
DOT    = 0
EMPTY  = 2
POWER  = 3
HOUSE  = 4

# ══════════════════════════════════════════════════
#  MAZE  (29 rows × 28 cols)
# ══════════════════════════════════════════════════
MAZE_TEMPLATE = [
    [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],
    [1,0,0,0,0,0,0,0,0,0,0,0,0,1,1,0,0,0,0,0,0,0,0,0,0,0,0,1],
    [1,0,1,1,1,1,0,1,1,1,1,1,0,1,1,0,1,1,1,1,1,0,1,1,1,1,0,1],
    [1,3,1,1,1,1,0,1,1,1,1,1,0,1,1,0,1,1,1,1,1,0,1,1,1,1,3,1],
    [1,0,1,1,1,1,0,1,1,1,1,1,0,1,1,0,1,1,1,1,1,0,1,1,1,1,0,1],
    [1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1],
    [1,0,1,1,1,1,0,1,1,0,1,1,1,1,1,1,1,1,0,1,1,0,1,1,1,1,0,1],
    [1,0,1,1,1,1,0,1,1,0,1,1,1,1,1,1,1,1,0,1,1,0,1,1,1,1,0,1],
    [1,0,0,0,0,0,0,1,1,0,0,0,0,1,1,0,0,0,0,1,1,0,0,0,0,0,0,1],
    [1,1,1,1,1,1,0,1,1,1,1,1,2,1,1,2,1,1,1,1,1,0,1,1,1,1,1,1],
    [1,1,1,1,1,1,0,1,1,2,2,2,2,2,2,2,2,2,2,1,1,0,1,1,1,1,1,1],
    [1,1,1,1,1,1,0,1,1,2,1,1,1,4,4,1,1,1,2,1,1,0,1,1,1,1,1,1],
    [1,1,1,1,1,1,0,1,1,2,1,4,4,4,4,4,4,1,2,1,1,0,1,1,1,1,1,1],
    [2,2,2,2,2,2,0,2,2,2,1,4,4,4,4,4,4,1,2,2,2,0,2,2,2,2,2,2],
    [1,1,1,1,1,1,0,1,1,2,1,4,4,4,4,4,4,1,2,1,1,0,1,1,1,1,1,1],
    [1,1,1,1,1,1,0,1,1,2,1,1,1,1,1,1,1,1,2,1,1,0,1,1,1,1,1,1],
    [1,1,1,1,1,1,0,1,1,2,2,2,2,2,2,2,2,2,2,1,1,0,1,1,1,1,1,1],
    [1,1,1,1,1,1,0,1,1,2,1,1,1,1,1,1,1,1,2,1,1,0,1,1,1,1,1,1],
    [1,0,0,0,0,0,0,0,0,0,0,0,0,1,1,0,0,0,0,0,0,0,0,0,0,0,0,1],
    [1,0,1,1,1,1,0,1,1,1,1,1,0,1,1,0,1,1,1,1,1,0,1,1,1,1,0,1],
    [1,0,1,1,1,1,0,1,1,1,1,1,0,1,1,0,1,1,1,1,1,0,1,1,1,1,0,1],
    [1,3,0,0,1,1,0,0,0,0,0,0,0,2,2,0,0,0,0,0,0,0,1,1,0,0,3,1],
    [1,1,1,0,1,1,0,1,1,0,1,1,1,1,1,1,1,1,0,1,1,0,1,1,0,1,1,1],
    [1,1,1,0,1,1,0,1,1,0,1,1,1,1,1,1,1,1,0,1,1,0,1,1,0,1,1,1],
    [1,0,0,0,0,0,0,1,1,0,0,0,0,1,1,0,0,0,0,1,1,0,0,0,0,0,0,1],
    [1,0,1,1,1,1,1,1,1,1,1,1,0,1,1,0,1,1,1,1,1,1,1,1,1,1,0,1],
    [1,0,1,1,1,1,1,1,1,1,1,1,0,1,1,0,1,1,1,1,1,1,1,1,1,1,0,1],
    [1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1],
    [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],
]

ROWS = len(MAZE_TEMPLATE)
COLS = len(MAZE_TEMPLATE[0])
W    = COLS * TS
H    = ROWS * TS + 60   # extra space for HUD

# ══════════════════════════════════════════════════
#  HELPER: tile ↔ pixel
# ══════════════════════════════════════════════════
def tile_center(t):
    return t * TS + TS // 2

def px_to_tile(px):
    return int((px + TS // 2) // TS)

# ══════════════════════════════════════════════════
#  PACMAN
# ══════════════════════════════════════════════════
class Pacman:
    START_TX, START_TY = 14, 23

    def __init__(self):
        self.reset()

    def reset(self):
        self.tx        = self.START_TX
        self.ty        = self.START_TY
        self.px        = float(tile_center(self.tx))
        self.py        = float(tile_center(self.ty))
        self.direction = "left"
        self.next_dir  = "left"
        self.alive     = True
        self.mouth     = 0.0      # radians
        self.mouth_inc = 0.15

    def set_next_dir(self, d):
        self.next_dir = d

    def update(self, maze):
        if not self.alive:
            return

        # Try queued direction
        dx, dy = DIRECTION_VECTORS[self.next_dir]
        ntx = self.tx + dx
        nty = self.ty + dy
        cx  = tile_center(self.tx)
        cy  = tile_center(self.ty)
        near_center = abs(self.px - cx) < PACMAN_SPEED + 1 and abs(self.py - cy) < PACMAN_SPEED + 1

        if near_center and _is_passable(ntx, nty, maze):
            self.direction = self.next_dir
            self.px = float(cx)
            self.py = float(cy)

        # Move in current direction
        dx, dy = DIRECTION_VECTORS[self.direction]
        npx = self.px + dx * PACMAN_SPEED
        npy = self.py + dy * PACMAN_SPEED
        check_tx = round(npx / TS)
        check_ty = round(npy / TS)

        if _is_passable(check_tx, check_ty, maze):
            self.px = npx
            self.py = npy
        else:
            self.px = float(tile_center(self.tx))
            self.py = float(tile_center(self.ty))

        # Tunnel wrap
        if self.px < -TS // 2:
            self.px = COLS * TS + TS // 2
        elif self.px > COLS * TS + TS // 2:
            self.px = float(-TS // 2)

        # Update tile
        self.tx = int(((self.px + TS // 2) // TS) % COLS)
        self.ty = max(0, min(ROWS - 1, int((self.py + TS // 2) // TS)))

        # Mouth animation
        self.mouth += self.mouth_inc
        if self.mouth >= 0.4 or self.mouth <= 0.0:
            self.mouth_inc = -self.mouth_inc

    def draw(self, surf, anim_frame, dying_pct=None):
        cx = int(self.px)
        cy = int(self.py)
        r  = int(TS * 0.45)

        if dying_pct is not None:
            # Death animation: mouth opens fully then disappears
            angle = dying_pct * math.pi
            if dying_pct >= 1.0:
                return
            start_a = math.radians(angle * 180 / math.pi)
            end_a   = math.radians(360) - start_a
            rect = pygame.Rect(cx - r, cy - r, r * 2, r * 2)
            pygame.draw.arc(surf, YELLOW, rect, end_a, start_a + math.pi * 2, r)
            pygame.draw.polygon(surf, YELLOW, [
                (cx, cy),
                (cx + int(r * math.cos(start_a)), cy - int(r * math.sin(start_a))),
                (cx + int(r * math.cos(end_a)),   cy - int(r * math.sin(end_a))),
            ])
            return

        DIR_ANGLES = {"right": 0, "down": 90, "left": 180, "up": 270}
        base = math.radians(DIR_ANGLES.get(self.direction, 0))
        mouth_rad = self.mouth

        # Body
        points = [(cx, cy)]
        steps  = 30
        a_start = base + mouth_rad
        a_end   = base + 2 * math.pi - mouth_rad
        for i in range(steps + 1):
            a = a_start + (a_end - a_start) * i / steps
            points.append((cx + int(r * math.cos(a)), cy - int(r * math.sin(a))))
        if len(points) >= 3:
            pygame.draw.polygon(surf, YELLOW, points)

        # Eye
        eye_offsets = {
            "right": (3, -6), "left": (-3, -6),
            "up":    (-6, -3), "down": (6, 3),
        }
        ex, ey = eye_offsets.get(self.direction, (3, -6))
        pygame.draw.circle(surf, BLACK, (cx + ex, cy + ey), 2)

# ══════════════════════════════════════════════════
#  GHOST
# ══════════════════════════════════════════════════
GHOST_DEFS = [
    {"name": "blinky", "start_tx": 13, "start_ty": 11, "home": (13, 11), "release_delay": 0  },
    {"name": "pinky",  "start_tx": 14, "start_ty": 13, "home": (14, 13), "release_delay": 60 },
    {"name": "inky",   "start_tx": 13, "start_ty": 13, "home": (13, 13), "release_delay": 120},
    {"name": "clyde",  "start_tx": 15, "start_ty": 13, "home": (15, 13), "release_delay": 180},
]

class Ghost:
    def __init__(self, defn):
        self.name          = defn["name"]
        self.start_tx      = defn["start_tx"]
        self.start_ty      = defn["start_ty"]
        self.home_tile     = defn["home"]
        self.base_delay    = defn["release_delay"]
        self.color         = GHOST_AI[self.name].COLOR if self.name in GHOST_AI else WHITE
        self.reset()

    def reset(self):
        self.tx            = self.start_tx
        self.ty            = self.start_ty
        self.px            = float(tile_center(self.tx))
        self.py            = float(tile_center(self.ty))
        self.direction     = "left"
        self.mode          = "scatter"
        self.release_delay = self.base_delay

    def _speed(self):
        if self.mode == "frightened": return FRIGHT_SPEED
        if self.mode == "eaten":      return EATEN_SPEED
        return GHOST_SPEED

    def update(self, pacman, all_ghosts, maze):
        if self.release_delay > 0:
            self.release_delay -= 1
            return

        speed = self._speed()
        cx = tile_center(self.tx)
        cy = tile_center(self.ty)
        near_center = abs(self.px - cx) < speed + 1 and abs(self.py - cy) < speed + 1

        if near_center:
            self.px = float(cx)
            self.py = float(cy)

            # Check if eaten ghost reached home
            if self.mode == "eaten":
                if self.tx == self.home_tile[0] and self.ty == self.home_tile[1]:
                    self.mode = "scatter"

            pac_proxy = pacman   # has .tx .ty .direction
            self.direction = compute_ghost_direction(self, pac_proxy, all_ghosts, maze)

        dv = DIRECTION_VECTORS[self.direction]
        npx = self.px + dv[0] * speed
        npy = self.py + dv[1] * speed
        ntx = round(npx / TS)
        nty = round(npy / TS)

        if _is_passable(ntx, nty, maze):
            self.px = npx
            self.py = npy

        # Tunnel
        if self.px < -TS // 2:
            self.px = COLS * TS + TS // 2
        elif self.px > COLS * TS + TS // 2:
            self.px = float(-TS // 2)

        self.tx = int(((self.px + TS // 2) // TS) % COLS)
        self.ty = max(0, min(ROWS - 1, int((self.py + TS // 2) // TS)))

    def draw(self, surf, anim_frame, frightened_timer):
        cx = int(self.px)
        cy = int(self.py)
        r  = int(TS * 0.46)

        if self.mode == "eaten":
            _draw_ghost_eyes(surf, cx, cy, self.direction, EATEN_EYES)
            return

        # Color
        if self.mode == "frightened":
            flash = frightened_timer < 2 * FPS and (anim_frame // 10) % 2 == 0
            color = FRIGHT_FLASH if flash else FRIGHTENED
        else:
            color = self.color

        # Head (semicircle)
        pygame.draw.circle(surf, color, (cx, cy - 2), r)

        # Body rectangle
        pygame.draw.rect(surf, color, pygame.Rect(cx - r, cy - 2, r * 2, r + 4))

        # Wavy bottom
        segs   = 4
        seg_w  = (r * 2) // segs
        base_y = cy + r + 2
        wave   = []
        wave.append((cx - r, base_y))
        for i in range(segs):
            bx  = cx - r + seg_w * i
            tip = base_y - 4 if i % 2 == 0 else base_y + 4
            wave.append((bx + seg_w // 2, tip))
            wave.append((bx + seg_w, base_y))
        wave.append((cx + r, cy + 2))
        wave.append((cx - r, cy + 2))
        if len(wave) >= 3:
            pygame.draw.polygon(surf, color, wave)

        if self.mode == "frightened":
            # Simple frightened face
            pygame.draw.rect(surf, WHITE, pygame.Rect(cx - 6, cy - 5, 4, 4))
            pygame.draw.rect(surf, WHITE, pygame.Rect(cx + 2, cy - 5, 4, 4))
            # Wavy mouth
            for i in range(5):
                mx = cx - 5 + i * 2
                my = cy + 2 + (1 if i % 2 == 0 else -1)
                pygame.draw.circle(surf, WHITE, (mx, my), 1)
        else:
            _draw_ghost_eyes(surf, cx, cy, self.direction, WHITE)


def _draw_ghost_eyes(surf, cx, cy, direction, sclera):
    offsets = {
        "right": (2, 0), "left": (-2, 0),
        "up":    (0, -2), "down": (0, 2),
    }
    ox, oy = offsets.get(direction, (1, 0))
    for ex in (-3, 3):
        pygame.draw.circle(surf, sclera,  (cx + ex,          cy - 3),          3)
        pygame.draw.circle(surf, (0, 0, 200), (cx + ex + ox, cy - 3 + oy),     1)


# ══════════════════════════════════════════════════
#  GAME
# ══════════════════════════════════════════════════
class Game:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption(TITLE)
        self.screen = pygame.display.set_mode((W, H))
        self.clock  = pygame.time.Clock()
        self.font_big   = pygame.font.SysFont("couriernew", 20, bold=True)
        self.font_small = pygame.font.SysFont("couriernew", 13, bold=True)
        self.font_huge  = pygame.font.SysFont("couriernew", 32, bold=True)

        self.hi_score   = 0
        self.state      = "title"    # title | ready | playing | dying | winning | gameover
        self._new_game()

    # ── setup ─────────────────────────────────────
    def _new_game(self):
        self.score   = 0
        self.lives   = 3
        self.level   = 1
        self._reset_maze()
        self._reset_entities()
        self.anim_frame      = 0
        self.ready_timer     = 0
        self.dead_timer      = 0
        self.win_timer       = 0
        self.ghost_eat_score = 200

    def _reset_maze(self):
        self.maze = [row[:] for row in MAZE_TEMPLATE]
        self.total_dots = sum(
            1 for row in self.maze for t in row if t in (DOT, POWER)
        )
        self.dots_left = self.total_dots

    def _reset_entities(self):
        self.pacman = Pacman()
        self.ghosts = [Ghost(d) for d in GHOST_DEFS]
        self.frightened_timer = 0
        self.mode_phase       = 0
        self.scatter_timer    = SCATTER_FRAMES[0]
        self.chase_timer      = 0
        self.ghost_eat_score  = 200

    # ── mode cycling ──────────────────────────────
    def _update_ghost_modes(self):
        if self.frightened_timer > 0:
            self.frightened_timer -= 1
            if self.frightened_timer == 0:
                target = "scatter" if self.mode_phase % 2 == 0 else "chase"
                for g in self.ghosts:
                    if g.mode == "frightened":
                        g.mode = target
            return

        if self.mode_phase % 2 == 0:   # scatter phase
            self.scatter_timer -= 1
            if self.scatter_timer <= 0:
                self.mode_phase += 1
                ci = min(self.mode_phase // 2, len(CHASE_FRAMES) - 1)
                self.chase_timer = CHASE_FRAMES[ci]
                for g in self.ghosts:
                    if g.mode not in ("eaten",):
                        g.mode = "chase"
        else:                           # chase phase
            self.chase_timer -= 1
            if self.chase_timer <= 0:
                self.mode_phase += 1
                si = min(self.mode_phase // 2, len(SCATTER_FRAMES) - 1)
                self.scatter_timer = SCATTER_FRAMES[si]
                for g in self.ghosts:
                    if g.mode not in ("eaten",):
                        g.mode = "scatter"

    # ── dot eating ────────────────────────────────
    def _check_dots(self):
        tx, ty = self.pacman.tx, self.pacman.ty
        tile   = self.maze[ty][tx]
        if tile == DOT:
            self.maze[ty][tx] = EMPTY
            self.score     += 10
            self.dots_left -= 1
        elif tile == POWER:
            self.maze[ty][tx] = EMPTY
            self.score     += 50
            self.dots_left -= 1
            dur = max(3, FRIGHTENED_DUR - (self.level - 1) * FPS)
            self.frightened_timer = dur
            self.ghost_eat_score  = 200
            for g in self.ghosts:
                if g.mode != "eaten":
                    g.mode = "frightened"
        if self.score > self.hi_score:
            self.hi_score = self.score

    # ── ghost collision ───────────────────────────
    def _check_collisions(self):
        for g in self.ghosts:
            dx = abs(self.pacman.px - g.px)
            dy = abs(self.pacman.py - g.py)
            if dx < TS * 0.7 and dy < TS * 0.7:
                if g.mode == "frightened":
                    g.mode = "eaten"
                    self.score += self.ghost_eat_score
                    self.ghost_eat_score = min(self.ghost_eat_score * 2, 1600)
                elif g.mode != "eaten":
                    self.pacman.alive = False
                    self.state = "dying"
                    self.dead_timer = FPS + 30   # ~1.5 s

    # ── update ────────────────────────────────────
    def update(self):
        self.anim_frame += 1

        if self.state == "title" or self.state == "gameover":
            return

        if self.state == "ready":
            self.ready_timer -= 1
            if self.ready_timer <= 0:
                self.state = "playing"
            return

        if self.state == "playing":
            self._update_ghost_modes()
            self.pacman.update(self.maze)
            for g in self.ghosts:
                g.update(self.pacman, self.ghosts, self.maze)
            self._check_dots()
            self._check_collisions()
            if self.dots_left <= 0:
                self.state    = "winning"
                self.win_timer = FPS * 2

        elif self.state == "dying":
            self.dead_timer -= 1
            if self.dead_timer <= 0:
                self.lives -= 1
                if self.lives <= 0:
                    self.state = "gameover"
                else:
                    self._reset_entities()
                    self.state       = "ready"
                    self.ready_timer = FPS + 30

        elif self.state == "winning":
            self.win_timer -= 1
            if self.win_timer <= 0:
                self.level    += 1
                self._reset_maze()
                self._reset_entities()
                self.state       = "ready"
                self.ready_timer = FPS + 30

    # ── draw ──────────────────────────────────────
    def draw(self):
        self.screen.fill(BLACK)
        self._draw_maze()

        # Ghosts (not during death spin)
        if self.state != "dying":
            for g in self.ghosts:
                g.draw(self.screen, self.anim_frame, self.frightened_timer)

        # Pac-Man
        if self.state == "dying":
            pct = 1.0 - self.dead_timer / (FPS + 30)
            self.pacman.draw(self.screen, self.anim_frame, dying_pct=pct)
        else:
            self.pacman.draw(self.screen, self.anim_frame)

        self._draw_hud()

        if self.state == "ready":
            self._draw_centered("READY!", YELLOW, W // 2, 23 * TS + TS // 2, self.font_big)

        if self.state == "title":
            self._draw_overlay()

        if self.state == "gameover":
            self._draw_gameover()

        if self.state == "winning":
            # Flash maze
            if (self.anim_frame // 10) % 2 == 0:
                flash_surf = pygame.Surface((W, ROWS * TS), pygame.SRCALPHA)
                flash_surf.fill((255, 255, 255, 40))
                self.screen.blit(flash_surf, (0, 0))

        pygame.display.flip()

    def _draw_maze(self):
        for y, row in enumerate(self.maze):
            for x, tile in enumerate(row):
                rx, ry = x * TS, y * TS
                if tile == WALL:
                    pygame.draw.rect(self.screen, MAZE_BLUE,   (rx, ry, TS, TS))
                    pygame.draw.rect(self.screen, MAZE_BRIGHT, (rx+1, ry+1, TS-2, TS-2))
                    pygame.draw.rect(self.screen, MAZE_BLUE,   (rx+2, ry+2, TS-4, TS-4))
                elif tile == DOT:
                    cx, cy = rx + TS // 2, ry + TS // 2
                    pygame.draw.circle(self.screen, DOT_COLOR, (cx, cy), 2)
                elif tile == POWER:
                    cx, cy = rx + TS // 2, ry + TS // 2
                    pulse  = int(4 + 2 * math.sin(self.anim_frame * 0.1))
                    alpha  = 128 + int(127 * math.sin(self.anim_frame * 0.1))
                    col    = (255, 184, 174)
                    pygame.draw.circle(self.screen, col, (cx, cy), pulse)

    def _draw_hud(self):
        hud_y = ROWS * TS + 8
        labels = [
            (f"SCORE  {self.score:>6}",   W // 4),
            (f"HIGH   {self.hi_score:>6}", W // 2),
            (f"LIVES  {self.lives}",       3 * W // 4 - 20),
            (f"LEVEL  {self.level}",       3 * W // 4 + 50),
        ]
        for text, xpos in labels:
            surf = self.font_small.render(text, True, WHITE)
            self.screen.blit(surf, (xpos - surf.get_width() // 2, hud_y))

        # Life icons
        for i in range(self.lives):
            lx = 10 + i * 18
            ly = hud_y + 20
            points = [(lx, ly)]
            for step in range(21):
                a = math.radians(30 + step * (300 / 20))
                points.append((lx + int(8 * math.cos(a)), ly - int(8 * math.sin(a))))
            if len(points) >= 3:
                pygame.draw.polygon(self.screen, YELLOW, points)

    def _draw_centered(self, text, color, x, y, font):
        surf = font.render(text, True, color)
        self.screen.blit(surf, (x - surf.get_width() // 2, y - surf.get_height() // 2))

    def _draw_overlay(self):
        overlay = pygame.Surface((W, ROWS * TS), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        self.screen.blit(overlay, (0, 0))

        self._draw_centered("PAC-MAN", YELLOW, W // 2, ROWS * TS // 2 - 60, self.font_huge)
        self._draw_centered("ARROW KEYS or WASD", WHITE,  W // 2, ROWS * TS // 2,      self.font_small)
        if (self.anim_frame // 30) % 2 == 0:
            self._draw_centered("PRESS ENTER TO START", YELLOW, W // 2, ROWS * TS // 2 + 30, self.font_small)

    def _draw_gameover(self):
        overlay = pygame.Surface((W, ROWS * TS), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        self.screen.blit(overlay, (0, 0))
        self._draw_centered("GAME OVER", RED,    W // 2, ROWS * TS // 2 - 40, self.font_huge)
        self._draw_centered(f"SCORE: {self.score}", WHITE, W // 2, ROWS * TS // 2 + 10, self.font_big)
        if (self.anim_frame // 30) % 2 == 0:
            self._draw_centered("PRESS ENTER TO RETRY", YELLOW, W // 2, ROWS * TS // 2 + 50, self.font_small)

    # ── input ─────────────────────────────────────
    def handle_input(self):
        KEY_DIR = {
            pygame.K_UP:    "up",    pygame.K_w: "up",
            pygame.K_DOWN:  "down",  pygame.K_s: "down",
            pygame.K_LEFT:  "left",  pygame.K_a: "left",
            pygame.K_RIGHT: "right", pygame.K_d: "right",
        }
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    if self.state == "title":
                        self._new_game()
                        self.state       = "ready"
                        self.ready_timer = FPS + 30
                    elif self.state == "gameover":
                        self._new_game()
                        self.state       = "ready"
                        self.ready_timer = FPS + 30
                if event.key in KEY_DIR and self.state == "playing":
                    self.pacman.set_next_dir(KEY_DIR[event.key])

        # Held keys for smooth turning
        pressed = pygame.key.get_pressed()
        if self.state == "playing":
            for k, d in KEY_DIR.items():
                if pressed[k]:
                    self.pacman.set_next_dir(d)

    # ── main loop ─────────────────────────────────
    def run(self):
        while True:
            self.handle_input()
            self.update()
            self.draw()
            self.clock.tick(FPS)


# ══════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════
if __name__ == "__main__":
    Game().run()