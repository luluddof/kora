"""LA MUSIQUE : la musique de guerre (Casus bellis).

Elle ne joue QUE quand le joueur est en guerre : une guerre declaree qui
l'implique (diplo.wars_of), ou une bataille ou se battent ses gens. Elle
monte en douceur (FADE_IN) quand la guerre commence et s'eteint en douceur
(FADE_OUT) quand elle finit ; elle tourne en boucle sans couture
(data/music/casus_bellis.ogg : tools/boucle_musique.py en a fait une
boucle, le raccord ne s'entend pas) - jouee comme un son entier (pas en
flux), le melangeur la reprend a l'echantillon pres.
Le volume (0 a 100 %) et la musique coupee sont des reglages du joueur
(reglages.json : "music_volume", "music_on" ; l'ecran des Reglages).
Interface seulement : la partie ne change pas (le multijoueur non plus).
Sans carte son, rien ne se passe (et rien ne plante).
"""

from __future__ import annotations

import pygame

from src.kora import battle, diplo
from src.kora.theme import data_dir

WAR_TRACK = "casus_bellis.ogg"
FADE_IN = 4.0
FADE_OUT = 6.0
DEFAULT_VOLUME = 0.6
# La musique ne repart pas tout de suite apres une treve : HOLD secondes.
HOLD = 3.0
CHECK = 0.5


def wants_war_music(state) -> bool:
    """Le joueur (state.viewer) est-il en guerre ?"""
    me = state.viewer
    if diplo.wars_of(state, me):
        return True
    for bt in battle.battles(state):
        if bt.outcome:
            continue
        for bid in bt.attackers + bt.defenders:
            band = state.bands.get(bid)
            if band is not None and band.tribe_id == me:
                return True
    return False


class Director:
    """Le chef d'orchestre d'une partie : update(state, dt) a chaque image."""

    def __init__(self, prefs: dict | None = None) -> None:
        prefs = prefs or {}
        self.volume = float(prefs.get("music_volume", DEFAULT_VOLUME))
        self.on = bool(prefs.get("music_on", True))
        self.sound = None
        self.channel = None
        self.broken = False
        self.playing = False
        self.calm = 0.0
        # "Ecouter" (les reglages) : la musique joue, guerre ou pas.
        self.listening = False
        # La guerre n'est regardee que toutes les CHECK secondes.
        self.war = False
        self.since_check = CHECK

    def _ready(self) -> bool:
        if self.broken:
            return False
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=48000, size=-16, channels=2)
            if self.sound is None:
                self.sound = pygame.mixer.Sound(str(data_dir() / "music" / WAR_TRACK))
        except (pygame.error, OSError, FileNotFoundError):
            self.broken = True
            return False
        return True

    def set_volume(self, volume: float, on: bool | None = None) -> None:
        self.volume = max(0.0, min(1.0, volume))
        if on is not None:
            self.on = on
        if self.channel is not None:
            self.channel.set_volume(self.volume if self.on else 0.0)

    def update(self, state, dt: float) -> None:
        """state : la partie (None au menu de demarrage)."""
        self.since_check += dt
        if self.since_check >= CHECK:
            self.since_check = 0.0
            self.war = state is not None and wants_war_music(state)
        if state is None:
            self.war = False
        want = self.on and self.volume > 0 and (self.listening or self.war)
        if want:
            self.calm = 0.0
            if not self.playing and self._ready():
                self.channel = self.sound.play(loops=-1, fade_ms=int(FADE_IN * 1000))
                if self.channel is not None:
                    self.channel.set_volume(self.volume)
                    self.playing = True
            elif self.channel is not None:
                self.channel.set_volume(self.volume)
            return
        if self.playing:
            self.calm += dt
            if self.calm >= HOLD or not self.on or self.volume <= 0:
                self.stop()

    def prefs(self) -> dict:
        return {"music_volume": round(self.volume, 2), "music_on": self.on}

    def stop(self, fade: float = FADE_OUT) -> None:
        if self.channel is not None:
            self.channel.fadeout(int(fade * 1000))
        self.playing = False
        self.channel = None
