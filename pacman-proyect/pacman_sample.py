import pygame
import sys
import math
from ghostIA_sample import GhostAI

# ==============================================================================
# CONFIGURACIÓN Y CONSTANTES VISUALES (Adaptadas del segundo código)
# ==============================================================================
TILE_SIZE = 30
FPS = 10  # Velocidad del juego (cuántos movimientos por segundo)

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
    "000101000G000101000",
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
    
    # Configurar ventana
    width = len(LEVEL[0]) * TILE_SIZE
    height = len(LEVEL) * TILE_SIZE
    screen = pygame.display.set_mode((width, height))
    pygame.display.set_caption("Pac-Man Prototipo: Gráficos Intuitivos")
    clock = pygame.time.Clock()

    # Convertir el mapa de strings a una lista de listas modificable
    grid = [list(row) for row in LEVEL]
    
    pacman = None
    ghosts = []
    
    # Inicializar IA de los fantasmas (usando el archivo separado)
    ai_random = GhostAI(ai_type="random")
    ai_chaser = GhostAI(ai_type="chase")

    # Encontrar posiciones iniciales y asignar colores fieles
    ghost_colors = [RED, PINK, CYAN, ORANGE] # Colores originales de los fantasmas
    g_count = 0
    
    for y, row in enumerate(grid):
        for x, col in enumerate(row):
            if col == 'P':
                pacman = Entity(x, y, YELLOW)
                grid[y][x] = ' ' # Limpiar casilla
            elif col == 'G':
                # Asignar una IA y color diferente a cada fantasma 'G' encontrado
                ia = ai_chaser if g_count % 2 == 0 else ai_random
                color = ghost_colors[g_count % len(ghost_colors)]
                ghosts.append({'entity': Entity(x, y, color), 'ia': ia})
                grid[y][x] = ' '
                g_count += 1

    # Variables de control
    pacman_dx, pacman_dy = 0, 0
    score = 0
    anim_frame = 0 # Contador para animaciones
    running = True

    while running:
        anim_frame += 1 # Incrementar frame de animación

        # 1. Manejo de eventos (Teclado)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_UP:
                    pacman_dx, pacman_dy = 0, -1
                elif event.key == pygame.K_DOWN:
                    pacman_dx, pacman_dy = 0, 1
                elif event.key == pygame.K_LEFT:
                    pacman_dx, pacman_dy = -1, 0
                elif event.key == pygame.K_RIGHT:
                    pacman_dx, pacman_dy = 1, 0

        # 2. Lógica de Pac-Man (Movimiento por cuadrícula)
        next_px, next_py = pacman.x + pacman_dx, pacman.y + pacman_dy
        # Validar si Pac-Man choca con pared
        if 0 <= next_py < len(grid) and 0 <= next_px < len(grid[0]) and grid[next_py][next_px] != '1':
            pacman.x, pacman.y = next_px, next_py
            pacman.direction = (pacman_dx, pacman_dy) # Actualizar dirección para dibujo
            
            # Comer punto
            if grid[pacman.y][pacman.x] == '0':
                grid[pacman.y][pacman.x] = ' '
                score += 10

        # 3. Lógica de Fantasmas (Consultando ghosts_ia.py)
        for g in ghosts:
            ghost_obj = g['entity']
            ia_module = g['ia']
            
            # Le pasamos el estado actual al cerebro del fantasma
            move_dx, move_dy = ia_module.decide_move(
                (ghost_obj.x, ghost_obj.y), 
                (pacman.x, pacman.y), 
                grid
            )
            
            ghost_obj.x += move_dx
            ghost_obj.y += move_dy
            if move_dx != 0 or move_dy != 0:
                ghost_obj.direction = (move_dx, move_dy) # Actualizar dirección para ojos

            # Comprobar colisión (GameOver)
            if ghost_obj.x == pacman.x and ghost_obj.y == pacman.y:
                print(f"¡Fin del juego! Puntuación final: {score}")
                running = False

        # 4. DIBUJAR EN PANTALLA
        screen.fill(BLACK)
        
        # Dibujar mapa (Con gráficos mejorados)
        for y, row in enumerate(grid):
            for x, col in enumerate(row):
                rx, ry = x * TILE_SIZE, y * TILE_SIZE
                if col == '1': # Pared (estilo neón azul)
                    # Dibujar líneas de borde para que parezca más el clásico
                    pygame.draw.rect(screen, MAZE_BLUE, (rx, ry, TILE_SIZE, TILE_SIZE), 2)
                    pygame.draw.rect(screen, MAZE_BRIGHT, (rx+2, ry+2, TILE_SIZE-4, TILE_SIZE-4), 1)

                elif col == '0': # Punto a comer (usando DOT_COLOR)
                    cx, cy = rx + TILE_SIZE // 2, ry + TILE_SIZE // 2
                    pygame.draw.circle(screen, DOT_COLOR, (cx, cy), 3)

        # Dibujar entidades USANDO LOS NUEVOS MÉTODOS AVANZADOS
        pacman.draw_pacman(screen, anim_frame)
        for g in ghosts:
            g['entity'].draw_ghost(screen, anim_frame)

        # (Opcional) Dibujar puntuación
        # font = pygame.font.SysFont(None, 24)
        # score_text = font.render(f'Score: {score}', True, WHITE)
        # screen.blit(score_text, (10, 10))

        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    main()