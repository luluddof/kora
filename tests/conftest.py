import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Les tests du multijoueur n'ecoutent que sur la machine (pas de fenetre du
# pare-feu Windows) : net.BIND.
os.environ.setdefault("KORA_BIND", "127.0.0.1")


import pytest


@pytest.fixture(autouse=True)
def _fresh_theme():
    """Les polices et surfaces de la charte ne survivent pas a un pygame.quit
    (certains tests en font) : chaque test repart de zero."""
    from src.kora import theme

    theme.reset()
    yield
