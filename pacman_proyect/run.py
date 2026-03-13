import pygame
from pygame.locals import *
from constant import *
from pacman import Pacman
from nodes import NodeGroup
from pallets import PelletGroup
from ghosts import Ghost

class GameController(object):
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode(SCREENSIZE, 0, 32)
        self.background = None
        self.clock = pygame.time.Clock()

def setBackground(self):
    self.background = pygame.surface.Surface(SCREENSIZE).convert()
    self.background.fill(BLACK)


def checkEvents(self):
    for event in pygame.event.get():
        if event.type == QUIT:
                exit()

class GameController(object):
if _name__ == "__main__":
    game.GameController()
    game.startGame()
    while True:
        game.update()

def update(self):
    dt = self.clock.tick(30) / 1000.0
    self.pacman.update(dt)
    self.ghost.update(dt)
    self.pallets.update(dt)
    self.checkPelletEvents()
    self.checkEvents()
    self.render()


def render(self):
    self.screen.blit(self.background, (0,0))
    self.nodes.render(self.screen)
    self.pallets.render(self.screen)
    self.pacman.render(self.screen)
    self.ghost.render(self.screen)
    pygame.display.update()


def startGame(self):
    self.nodes = NodeGroup("maze1.txt")
    self.nodes.setPortalPair((0, 17), (27, 17))
    self.pacman = Pacman(self.nodes.getPacmanNode())
    self.pallets = PelletGroup("maze1.txt")
    self.ghost = Ghost(self.nodes.getStartTempNode())

def checkPelletEvents(self):
        pellet = self.pacman.eatPellets(self.pellets.pelletList)
        if pellet:
            self.pellets.numEaten += 1
            self.pellets.pelletList.remove(pellet)