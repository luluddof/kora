import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Les tests du multijoueur n'ecoutent que sur la machine (pas de fenetre du
# pare-feu Windows) : net.BIND.
os.environ.setdefault("KORA_BIND", "127.0.0.1")
# La musique de guerre (music.py) ne sort jamais des haut-parleurs pendant
# les tests.
os.environ["SDL_AUDIODRIVER"] = "dummy"


import pytest


@pytest.fixture(autouse=True)
def _fresh_theme():
    """Les polices et surfaces de la charte ne survivent pas a un pygame.quit
    (certains tests en font) : chaque test repart de zero."""
    from src.kora import theme

    theme.reset()
    yield


@pytest.fixture(autouse=True)
def _whole_tree():
    """L'arbre complet au depart de chaque test (une partie dessinee cache
    les savoirs que son sort a ecartes : layout.set_tree_hidden)."""
    from src.kora import layout

    layout.set_tree_hidden(frozenset())
    yield
