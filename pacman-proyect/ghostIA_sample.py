import random

class GhostAI:
    def __init__(self, ai_type="random"):
        """
        Tipos de IA disponibles inicialmente:
        - "random": Movimiento completamente al azar.
        - "chase": Sigue a Pac-Man basándose en la distancia más corta (Manhattan).
        - En el futuro puedes agregar "ml_model" para cargar tu red neuronal.
        """
        self.ai_type = ai_type
        # Aquí podrías cargar tu modelo entrenado en el futuro
        # self.model = tf.keras.models.load_model('mi_modelo_fantasma.h5')

    def get_valid_moves(self, ghost_pos, grid):
        """Devuelve una lista de movimientos válidos (no paredes) para el fantasma."""
        x, y = ghost_pos
        moves = []
        # Arriba, Abajo, Izquierda, Derecha
        directions = [(0, -1), (0, 1), (-1, 0), (1, 0)] 
        
        for dx, dy in directions:
            nx, ny = x + dx, y + dy
            # Verifica si la próxima celda está dentro del mapa y no es pared ('1')
            if 0 <= ny < len(grid) and 0 <= nx < len(grid[0]) and grid[ny][nx] != '1':
                moves.append((dx, dy))
        return moves

    def decide_move(self, ghost_pos, pacman_pos, grid):
        """
        Esta es la función principal que el juego llamará en cada turno.
        Recibe el estado actual (posiciones y mapa) y devuelve una acción (dx, dy).
        """
        valid_moves = self.get_valid_moves(ghost_pos, grid)
        
        if not valid_moves:
            return (0, 0) # Si se queda atascado (no debería pasar)

        if self.ai_type == "random":
            return random.choice(valid_moves)
            
        elif self.ai_type == "chase":
            # Lógica básica: Elegir el movimiento que minimice la distancia a Pac-Man
            best_move = valid_moves[0]
            min_dist = float('inf')
            
            for dx, dy in valid_moves:
                nx, ny = ghost_pos[0] + dx, ghost_pos[1] + dy
                # Distancia Manhattan
                dist = abs(nx - pacman_pos[0]) + abs(ny - pacman_pos[1]) 
                if dist < min_dist:
                    min_dist = dist
                    best_move = (dx, dy)
            return best_move
            
        # --- AQUÍ CONECTARÁS TUS MODELOS ENTRENADOS ---
        # elif self.ai_type == "ml_model":
        #     state = self.build_state_vector(ghost_pos, pacman_pos, grid)
        #     action = self.model.predict(state)
        #     return self.decode_action(action)
        
        return random.choice(valid_moves)