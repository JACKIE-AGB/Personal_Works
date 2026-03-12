import pygame
from pygame.locals import *
from constant import *
from pacman import Pacman
from nodes import NodeGroup
from pallets import PelletGroup

class GameController(object):
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode(SCREENSIZE, 0, 32)
        self.background = None

def setBackground(self):
    self.background = pygame.surface.Surface(SCREENSIZE).convert()
    self.background.fill(BLACK)

def startGame(self):
    self.setBackground()

def update(self):
    self.checkEvents()
    self.render()

def checkEvents(self):
    for event in pygame.event.get():
        if event.type == QUIT:
                exit()

def render(self):
    pygame.display.update()

class GameController(object):
    ...

if _name__ == "__main__":
    game.GameController()
    game.startGame()
    while True:
        game.update()

def __init__(self):
    ...
    self.clock = pygame.time.Clock()

def update(self);
    dt = self.clock.tick(30) / 1000.0
    self.checkEvents()
    self.render()

...
from pacman import Pacman

def startGame(self):
    ...
    self.pacman = Pacman

def update(self):
    dt = self.clock.tick(30) / 1000.0
    self.pacman.update(dt)
    self.pallets.update(dt)
    self.checkPelletEvents()
    self.checkEvents()
    self.render()

def render(self):
    self.screen.blit(self.background, (0, 0))
    self.pacman.render(self.screen)
    pygame.display.update()

from nodes import NodeGroup

def startgame(self):
    self.setBackGround()
    self.nodes.setupTestNodes()
    self.pacman = Pacman()

def render(self):
    self.screen.blit(self.background, (0,0))
    self.nodes.render(self.screen)
    self.pallets.render(self.screen)
    self.pacman.render(self.screen)
    pygame.display.update()

def startGame(self):
    self.setBackGround()
    self.nodes = NodeGroup("mazetest.txt")
    self.pacman = Pacman(self.nodes.getStartTempNode())

def startGame(self):
    self.nodes = NodeGroup("maze1.txt")
    self.nodes.setPortalPair((0, 17), (27, 17))
    self.pacman = Pacman(self.nodes.getPacmanNode())
    self.pallets = PelletGroup("maze1.txt")

def checkPelletEvents(self):
        pellet = self.pacman.eatPellets(self.pellets.pelletList)
        if pellet:
            self.pellets.numEaten += 1
            self.pellets.pelletList.remove(pellet)