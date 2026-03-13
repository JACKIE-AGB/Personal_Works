"allow change the ai later"

from collections import deque
import math
import random

ROWS = 29
COLS = 28

# ─────────────────────────────────────────────────────────
#  Individual ghost personalities
# ─────────────────────────────────────────────────────────

class BlinkyAI:
    """Red — direct chaser.  Target = Pac-Man's exact tile."""
    COLOR = (255, 0, 0)
    NAME  = "blinky"

    def get_target(self, ghost, pacman, all_ghosts, maze):
        return (pacman.tx, pacman.ty)


class PinkyAI:
    """Pink — ambusher.  Target = 4 tiles ahead of Pac-Man."""
    COLOR = (255, 184, 255)
    NAME  = "pinky"

    OFFSETS = {
        "up":    (0, -4),
        "down":  (0,  4),
        "left":  (-4, 0),
        "right": (4,  0),
    }

    def get_target(self, ghost, pacman, all_ghosts, maze):
        dx, dy = self.OFFSETS.get(pacman.direction, (0, 0))
        return (pacman.tx + dx, pacman.ty + dy)


class InkyAI:
    """Cyan — flanker.  Uses Blinky's position to compute target."""
    COLOR = (0, 255, 255)
    NAME  = "inky"

    OFFSETS = {
        "up":    (0, -2),
        "down":  (0,  2),
        "left":  (-2, 0),
        "right": (2,  0),
    }

    def get_target(self, ghost, pacman, all_ghosts, maze):
        dx, dy = self.OFFSETS.get(pacman.direction, (0, 0))
        pivot_x = pacman.tx + dx
        pivot_y = pacman.ty + dy

        blinky = next((g for g in all_ghosts if g.name == "blinky"), None)
        bx = blinky.tx if blinky else pacman.tx
        by = blinky.ty if blinky else pacman.ty

        return (
            pivot_x + (pivot_x - bx),
            pivot_y + (pivot_y - by),
        )


class ClydeAI:
    """Orange — shy ghost.  Chases when far (>8 tiles), scatters when close."""
    COLOR = (255, 184, 82)
    NAME  = "clyde"

    def get_target(self, ghost, pacman, all_ghosts, maze):
        dist = math.hypot(ghost.tx - pacman.tx, ghost.ty - pacman.ty)
        if dist > 8:
            return (pacman.tx, pacman.ty)
        return (1, ROWS - 2)   # scatter to bottom-left corner


# Registry — maps ghost name → AI instance
GHOST_AI = {
    "blinky": BlinkyAI(),
    "pinky":  PinkyAI(),
    "inky":   InkyAI(),
    "clyde":  ClydeAI(),
}

# Scatter corner per ghost (used in scatter mode)
SCATTER_CORNERS = {
    "blinky": (COLS - 2, 1),
    "pinky":  (1,        1),
    "inky":   (COLS - 2, ROWS - 2),
    "clyde":  (1,        ROWS - 2),
}

# ─────────────────────────────────────────────────────────
#  Movement engine  (BFS — swap for A* or random here)
# ─────────────────────────────────────────────────────────

DIRECTION_VECTORS = {
    "up":    (0, -1),
    "down":  (0,  1),
    "left":  (-1, 0),
    "right": (1,  0),
}

OPPOSITES = {
    "up": "down", "down": "up",
    "left": "right", "right": "left",
}

ALL_DIRS = ["up", "down", "left", "right"]


def _is_passable(tx, ty, maze):
    """True if the tile can be entered by a ghost."""
    if tx < 0 or ty < 0 or ty >= len(maze) or tx >= len(maze[0]):
        return False
    return maze[ty][tx] != 1


def _bfs(start_x, start_y, target_x, target_y, current_dir, maze):
    """
    BFS from (start_x, start_y) toward (target_x, target_y).
    Returns the first direction to take, or current_dir on failure.

    Replace this function body with A* / random walk / etc. to change
    the pathfinding without touching ghost personalities.
    """
    queue   = deque()
    visited = set()
    visited.add((start_x, start_y))

    for d in ALL_DIRS:
        if d == OPPOSITES.get(current_dir):
            continue                          # no reversing
        dx, dy = DIRECTION_VECTORS[d]
        nx, ny = start_x + dx, start_y + dy
        if _is_passable(nx, ny, maze) and (nx, ny) not in visited:
            visited.add((nx, ny))
            queue.append((nx, ny, d))

    while queue:
        cx, cy, first_dir = queue.popleft()
        if cx == target_x and cy == target_y:
            return first_dir
        for d in ALL_DIRS:
            dx, dy = DIRECTION_VECTORS[d]
            nx, ny = cx + dx, cy + dy
            if _is_passable(nx, ny, maze) and (nx, ny) not in visited:
                visited.add((nx, ny))
                queue.append((nx, ny, first_dir))

    # Fallback: any passable direction
    for d in ALL_DIRS:
        dx, dy = DIRECTION_VECTORS[d]
        nx, ny = start_x + dx, start_y + dy
        if _is_passable(nx, ny, maze):
            return d

    return current_dir


def compute_ghost_direction(ghost, pacman, all_ghosts, maze):
    """
    Main function called by the game each tick per ghost.
    Returns a direction string: "up" | "down" | "left" | "right"

    ghost.mode can be: "scatter" | "chase" | "frightened" | "eaten"
    """

    # ── Frightened: random valid direction
    if ghost.mode == "frightened":
        opp = OPPOSITES.get(ghost.direction)
        valid = []
        for d in ALL_DIRS:
            if d == opp:
                continue
            dx, dy = DIRECTION_VECTORS[d]
            if _is_passable(ghost.tx + dx, ghost.ty + dy, maze):
                valid.append(d)
        return random.choice(valid) if valid else ghost.direction

    # ── Eaten: return to ghost house
    if ghost.mode == "eaten":
        hx, hy = ghost.home_tile
        return _bfs(ghost.tx, ghost.ty, hx, hy, ghost.direction, maze)

    # ── Scatter: go to fixed corner
    if ghost.mode == "scatter":
        tx, ty = SCATTER_CORNERS.get(ghost.name, (ghost.tx, ghost.ty))
        return _bfs(ghost.tx, ghost.ty, tx, ty, ghost.direction, maze)

    # ── Chase: use personality AI
    ai = GHOST_AI.get(ghost.name)
    if ai:
        tx, ty = ai.get_target(ghost, pacman, all_ghosts, maze)
    else:
        tx, ty = pacman.tx, pacman.ty

    return _bfs(ghost.tx, ghost.ty, tx, ty, ghost.direction, maze)