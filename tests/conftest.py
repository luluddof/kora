import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Les tests du multijoueur n'ecoutent que sur la machine (pas de fenetre du
# pare-feu Windows) : net.BIND.
os.environ.setdefault("KORA_BIND", "127.0.0.1")
