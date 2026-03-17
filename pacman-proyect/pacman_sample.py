import pygame
import sys
import math
from ghostIA_sample import GhostAI

# ==============================================================================
# CONFIGURACIÓN Y CONSTANTES VISUALES (Adaptadas del segundo código)
# ==============================================================================
TILE_SIZE = 30
FPS = 10           # Velocidad del juego (cuántos movimientos por segundo)
HUD_H = 50         # Altura del HUD inferior en píxeles
LIVES_START = 3    # Vidas iniciales

# Colores (Copiados para mayor fidelidad visual)
BLACK       = (0, 0, 0)
MAZE_BLUE   = (25, 25, 166)
MAZE_BRIGHT = (50, 50, 255)
YELLOW      = (255, 255, 0)
WHITE       = (255, 255, 255)
DOT_COLOR   = (255, 184, 174)
RED         = (255, 0, 0)     # Blinky
PINK        = (255, 184, 255) # Pinky
CYAN        = (0, 255, 255)   # Inky
ORANGE      = (255, 184, 82)  # Clyde

# Mapa básico (1 = Pared, 0 = Punto, P = Pacman inicial, G = Fantasma inicial)
LEVEL = [
    "1111111111111111111",
    "1000000001000000001",
    "1011011101011101101",
    "1000000000000000001",
    "1011010111110101101",
    "1000010001000100001",
    "1111011101011101111",
    "000101000GGGG101000",  # 4 fantasmas: Blinky(R), Pinky(P), Inky(C), Clyde(O)
    "1111010111110101111",
    "100000000P000000001",
    "1011011101011101101",
    "1001000000000001001",
    "1101010111110101011",
    "1000010001000100001",
    "1011111101011111101",
    "1000000000000000001",
    "1111111111111111111"
]

# ==============================================================================
# CLASE DE ENTIDAD ACTUALIZADA CON GRÁFICOS AVANZADOS
# ==============================================================================
class Entity:
    def __init__(self, x, y, color):
        self.x = x
        self.y = y
        self.color = color
        self.direction = (1, 0) # Dirección inicial (derecha)
        self.mouth_open = True # Para animación de Pacman

    def draw_pacman(self, screen, anim_frame):
        # Coordenadas del centro en píxeles
        cx = self.x * TILE_SIZE + TILE_SIZE // 2
        cy = self.y * TILE_SIZE + TILE_SIZE // 2
        r = TILE_SIZE // 2 - 2

        # Animación de boca (parpadeo cada pocos frames)
        if (anim_frame // 3) % 2 == 0:
            # Boca cerrada: Círculo completo
            pygame.draw.circle(screen, YELLOW, (cx, cy), r)
        else:
            # Boca abierta: Usamos un arco
            # Definimos el ángulo de la boca basándonos en la dirección
            angle_map = {
                (1, 0): 0,    # Derecha
                (-1, 0): 180, # Izquierda
                (0, -1): 90,  # Arriba
                (0, 1): 270   # Abajo
            }
            base_angle = angle_map.get(self.direction, 0)
            
            # Ángulos para el arco (en radianes)
            mouth_width = 50 # Ancho de la boca en grados
            start_angle = math.radians(base_angle + mouth_width)
            end_angle = math.radians(base_angle + 360 - mouth_width)

            # Dibujar el cuerpo de Pacman (un arco amarillo grueso)
            rect = pygame.Rect(cx - r, cy - r, r * 2, r * 2)
            pygame.draw.arc(screen, YELLOW, rect, start_angle, end_angle, r)
            # Rellenar el centro (dibujar polígono para que no sea solo un borde)
            points = [(cx, cy)]
            for angle in range(base_angle + mouth_width, base_angle + 360 - mouth_width + 1, 10):
                rad = math.radians(angle)
                points.append((cx + int(r * math.cos(rad)), cy - int(r * math.sin(rad))))
            if len(points) > 2:
                pygame.draw.polygon(screen, YELLOW, points)

        # Ojo de Pacman
        eye_r = 2
        # Posición relativa del ojo
        eye_offsets = {
            (1, 0): (3, -6),   # Derecha
            (-1, 0): (-3, -6), # Izquierda
            (0, -1): (-6, -3), # Arriba
            (0, 1): (6, 3)     # Abajo
        }
        ex, ey = eye_offsets.get(self.direction, (3, -6))
        pygame.draw.circle(screen, BLACK, (cx + ex, cy + ey), eye_r)

    def draw_ghost(self, screen, anim_frame):
        cx = self.x * TILE_SIZE + TILE_SIZE // 2
        cy = self.y * TILE_SIZE + TILE_SIZE // 2
        r = TILE_SIZE // 2 - 2
        
        color = self.color

        # 1. Cabeza (semicírculo superior)
        pygame.draw.circle(screen, color, (cx, cy - 2), r)

        # 2. Cuerpo (rectángulo inferior)
        rect = pygame.Rect(cx - r, cy - 2, r * 2, r // 2 + 5)
        pygame.draw.rect(screen, color, rect)

        # 3. Base ondulada (animada)
        num_waves = 3
        wave_width = (r * 2) // num_waves
        base_y = cy + r - 2
        
        # Animación de la onda cambiando qué "pico" está arriba
        wave_offset = (anim_frame // 5) % 2
        
        for i in range(num_waves):
            wave_cx = cx - r + i * wave_width + wave_width // 2
            # Alternar la altura para simular movimiento
            if (i + wave_offset) % 2 == 0:
                # Dibuja un pequeño círculo hacia abajo
                pygame.draw.circle(screen, color, (wave_cx, base_y), wave_width // 2 + 1)
            else:
                # Dibuja un pequeño círculo ligeramente más arriba
                pygame.draw.circle(screen, color, (wave_cx, base_y - 3), wave_width // 2 + 1)

        # 4. Ojos (Sclera blanca y pupila azul)
        self._draw_ghost_eyes(screen, cx, cy)

    def _draw_ghost_eyes(self, screen, cx, cy):
        eye_sclera_r = 4
        eye_pupil_r = 2
        
        # Desplazamiento de la pupila según la dirección
        pupil_offsets = {
            (1, 0): (2, 0),   # Derecha
            (-1, 0): (-2, 0), # Izquierda
            (0, -1): (0, -2), # Arriba
            (0, 1): (0, 2)    # Abajo
        }
        px, py = pupil_offsets.get(self.direction, (2, 0))

        # Ojo izquierdo
        # Sclera
        pygame.draw.circle(screen, WHITE, (cx - 5, cy - 3), eye_sclera_r)
        # Pupila
        pygame.draw.circle(screen, (0, 0, 200), (cx - 5 + px, cy - 3 + py), eye_pupil_r)

        # Ojo derecho
        # Sclera
        pygame.draw.circle(screen, WHITE, (cx + 5, cy - 3), eye_sclera_r)
        # Pupila
        pygame.draw.circle(screen, (0, 0, 200), (cx + 5 + px, cy - 3 + py), eye_pupil_r)


# ==============================================================================
# BUCLE PRINCIPAL DEL JUEGO
# ==============================================================================
def main():
    pygame.init()
    
    # Configurar ventana (con espacio para HUD)
    map_width  = len(LEVEL[0]) * TILE_SIZE
    map_height = len(LEVEL)    * TILE_SIZE
    screen = pygame.display.set_mode((map_width, map_height + HUD_H))
    pygame.display.set_caption("Pac-Man Prototipo: Gráficos Intuitivos")
    clock = pygame.time.Clock()

    # Fuentes para HUD y pantallas
    font_hud    = pygame.font.SysFont("couriernew", 15, bold=True)
    font_big    = pygame.font.SysFont("couriernew", 30, bold=True)
    font_medium = pygame.font.SysFont("couriernew", 17, bold=True)

    # ── IA disponibles ────────────────────────────────────────────────────────
    ai_chaser = GhostAI(ai_type="chase")
    ai_random = GhostAI(ai_type="random")

    # Tabla de IAs y nombres por fantasma (orden de aparición en el mapa)
    GHOST_DEFS = [
        {"color": RED,    "name": "Blinky", "ia": ai_chaser},  # 0 - perseguidor
        {"color": PINK,   "name": "Pinky",  "ia": ai_random},  # 1 - aleatorio
        {"color": CYAN,   "name": "Inky",   "ia": ai_chaser},  # 2 - perseguidor
        {"color": ORANGE, "name": "Clyde",  "ia": ai_random},  # 3 - aleatorio
    ]

    # ── Función de reset de posiciones (sin borrar puntos ya comidos) ─────────
    def reset_positions():
        """Regresa a Pac-Man y los fantasmas a su posición inicial."""
        pacman.x, pacman.y = pacman_start
        pacman.direction   = (1, 0)
        for i, g in enumerate(ghosts):
            g['entity'].x, g['entity'].y = ghost_starts[i]
            g['entity'].direction        = (1, 0)

    # ── Función de reset completo (nueva partida) ─────────────────────────────
    def full_reset():
        nonlocal score, lives, game_state, grid
        score      = 0
        lives      = LIVES_START
        game_state = "playing"
        grid[:]    = [list(row) for row in LEVEL]
        # Limpiar marcadores de G/P del grid
        for y, row in enumerate(grid):
            for x, col in enumerate(row):
                if col in ('P', 'G'):
                    grid[y][x] = '0'
        reset_positions()

    # ── Parsear mapa inicial ──────────────────────────────────────────────────
    grid    = [list(row) for row in LEVEL]
    pacman  = None
    ghosts  = []
    g_count = 0

    for y, row in enumerate(grid):
        for x, col in enumerate(row):
            if col == 'P':
                pacman      = Entity(x, y, YELLOW)
                grid[y][x]  = '0'    # Deja un punto en el inicio
            elif col == 'G':
                defn = GHOST_DEFS[g_count % len(GHOST_DEFS)]
                ghosts.append({
                    'entity': Entity(x, y, defn["color"]),
                    'ia':     defn["ia"],
                    'name':   defn["name"],
                })
                grid[y][x] = '0'     # Celda libre bajo el fantasma
                g_count    += 1

    # Guardar posiciones de inicio para respawn
    pacman_start = (pacman.x, pacman.y)
    ghost_starts = [(g['entity'].x, g['entity'].y) for g in ghosts]

    # ── Variables de control ──────────────────────────────────────────────────
    pacman_dx  = 0
    pacman_dy  = 0
    score      = 0
    lives      = LIVES_START
    anim_frame = 0
    game_state = "playing"   # "playing" | "gameover"

    # ── Bucle principal ───────────────────────────────────────────────────────
    while True:
        anim_frame += 1

        # ── 1. Eventos ────────────────────────────────────────────────────────
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()

            elif event.type == pygame.KEYDOWN:
                if game_state == "playing":
                    if event.key == pygame.K_UP:
                        pacman_dx, pacman_dy = 0, -1
                    elif event.key == pygame.K_DOWN:
                        pacman_dx, pacman_dy = 0,  1
                    elif event.key == pygame.K_LEFT:
                        pacman_dx, pacman_dy = -1, 0
                    elif event.key == pygame.K_RIGHT:
                        pacman_dx, pacman_dy =  1, 0

                elif game_state == "gameover":
                    if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        full_reset()           # Jugar de nuevo
                    elif event.key == pygame.K_ESCAPE:
                        pygame.quit()
                        sys.exit()

        # ── 2. Lógica (solo si se está jugando) ───────────────────────────────
        if game_state == "playing":

            # Movimiento de Pac-Man
            next_px = pacman.x + pacman_dx
            next_py = pacman.y + pacman_dy
            if (0 <= next_py < len(grid) and
                    0 <= next_px < len(grid[0]) and
                    grid[next_py][next_px] != '1'):
                pacman.x, pacman.y = next_px, next_py
                pacman.direction   = (pacman_dx, pacman_dy)
                if grid[pacman.y][pacman.x] == '0':
                    grid[pacman.y][pacman.x] = ' '
                    score += 10

            # Movimiento de Fantasmas
            for g in ghosts:
                ghost_obj  = g['entity']
                ia_module  = g['ia']
                move_dx, move_dy = ia_module.decide_move(
                    (ghost_obj.x, ghost_obj.y),
                    (pacman.x,    pacman.y),
                    grid
                )
                ghost_obj.x += move_dx
                ghost_obj.y += move_dy
                if move_dx != 0 or move_dy != 0:
                    ghost_obj.direction = (move_dx, move_dy)

            # Colisión Pac-Man ↔ Fantasma
            for g in ghosts:
                if g['entity'].x == pacman.x and g['entity'].y == pacman.y:
                    lives -= 1
                    if lives <= 0:
                        lives      = 0
                        game_state = "gameover"
                    else:
                        reset_positions()   # Respawn: vuelven al inicio
                    break                   # Solo procesar una colisión por frame

        # ── 3. Dibujar ────────────────────────────────────────────────────────
        screen.fill(BLACK)

        # Mapa
        for y, row in enumerate(grid):
            for x, col in enumerate(row):
                rx, ry = x * TILE_SIZE, y * TILE_SIZE
                if col == '1':
                    pygame.draw.rect(screen, MAZE_BLUE,   (rx, ry, TILE_SIZE, TILE_SIZE), 2)
                    pygame.draw.rect(screen, MAZE_BRIGHT, (rx+2, ry+2, TILE_SIZE-4, TILE_SIZE-4), 1)
                elif col == '0':
                    cx_dot = rx + TILE_SIZE // 2
                    cy_dot = ry + TILE_SIZE // 2
                    pygame.draw.circle(screen, DOT_COLOR, (cx_dot, cy_dot), 3)

        # Entidades
        pacman.draw_pacman(screen, anim_frame)
        for g in ghosts:
            g['entity'].draw_ghost(screen, anim_frame)

        # HUD inferior
        hud_y = map_height + 8
        # Puntuación
        score_surf = font_hud.render(f"SCORE  {score:>6}", True, WHITE)
        screen.blit(score_surf, (map_width // 4 - score_surf.get_width() // 2, hud_y))
        # Vidas (texto)
        lives_label = font_hud.render("VIDAS", True, WHITE)
        screen.blit(lives_label, (map_width * 3 // 4 - 30, hud_y))
        # Íconos de vidas (mini Pac-Man)
        icon_y = hud_y + 20
        for i in range(lives):
            lx = map_width * 3 // 4 + 10 + i * 20
            r  = 7
            points = [(lx, icon_y)]
            for step in range(21):
                a = math.radians(35 + step * (290 / 20))
                points.append((lx + int(r * math.cos(a)), icon_y - int(r * math.sin(a))))
            if len(points) >= 3:
                pygame.draw.polygon(screen, YELLOW, points)
        if lives == 0:
            empty = font_hud.render("---", True, RED)
            screen.blit(empty, (map_width * 3 // 4 + 10, icon_y - 6))

        # Pantalla de Game Over
        if game_state == "gameover":
            overlay = pygame.Surface((map_width, map_height), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 200))
            screen.blit(overlay, (0, 0))

            def draw_centered(text, color, y, font):
                surf = font.render(text, True, color)
                screen.blit(surf, (map_width // 2 - surf.get_width() // 2, y))

            cx_mid = map_height // 2
            draw_centered("GAME OVER",           RED,    cx_mid - 60, font_big)
            draw_centered(f"PUNTUACIÓN: {score}", WHITE,  cx_mid - 10, font_medium)
            pygame.draw.line(screen, (80, 80, 80),
                             (map_width // 4, cx_mid + 20),
                             (3 * map_width // 4, cx_mid + 20), 1)

            blink = (anim_frame // 20) % 2 == 0
            enter_col = YELLOW if blink else (160, 120, 0)
            esc_col   = (200, 70, 70) if not blink else (130, 40, 40)
            draw_centered("[ENTER]  JUGAR DE NUEVO", enter_col, cx_mid + 32, font_medium)
            draw_centered("[ESC]    SALIR",           esc_col,   cx_mid + 58, font_medium)

        pygame.display.flip()
        clock.tick(FPS)

if __name__ == "__main__":
    main()