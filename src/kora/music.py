"""LA MUSIQUE : la musique de guerre (Casus bellis).

Elle ne joue QUE quand le joueur est en guerre : une guerre declaree qui
l'implique (diplo.wars_of), ou une bataille ou se battent ses gens. Elle
part du DEBUT du morceau (sa propre montee) quand la guerre commence et
s'eteint en douceur (FADE_OUT) quand elle finit ; ensuite elle boucle sur
le coeur du morceau, sans couture (data/music/casus_bellis.ogg :
tools/boucle_musique.py y a mis un fondu enchaine et les etiquettes
LOOPSTART / LOOPLENGTH, que SDL_mixer suit a l'echantillon pres ; jouee
en flux par pygame.mixer.music).
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
# Le morceau a sa propre montee : un fondu d'entree tres court (pas de clic).
FADE_IN = 0.5
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
        self.loaded = False
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
            if not self.loaded:
                pygame.mixer.music.load(str(data_dir() / "music" / WAR_TRACK))
                self.loaded = True
        except (pygame.error, OSError, FileNotFoundError):
            self.broken = True
            return False
        return True

    def heard_volume(self) -> float:
        """Le volume que joue le melangeur (0 quand rien ne joue)."""
        if not self.playing or not pygame.mixer.get_init():
            return 0.0
        return pygame.mixer.music.get_volume()

    def set_volume(self, volume: float, on: bool | None = None) -> None:
        self.volume = max(0.0, min(1.0, volume))
        if on is not None:
            self.on = on
        if self.playing:
            pygame.mixer.music.set_volume(self.volume if self.on else 0.0)

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
                # Depuis le debut du morceau (meme si un fondu de sortie
                # finissait encore) ; la boucle suit les etiquettes du fichier.
                try:
                    pygame.mixer.music.set_volume(self.volume)
                    pygame.mixer.music.play(loops=-1, fade_ms=int(FADE_IN * 1000))
                except pygame.error:
                    self.broken = True
                    return
                self.playing = True
            elif self.playing:
                pygame.mixer.music.set_volume(self.volume)
            return
        if self.playing:
            self.calm += dt
            if self.calm >= HOLD or not self.on or self.volume <= 0:
                self.stop()

    def prefs(self) -> dict:
        return {"music_volume": round(self.volume, 2), "music_on": self.on}

    def stop(self, fade: float = FADE_OUT) -> None:
        """S'eteint en douceur (fadeout ne bloque pas le jeu)."""
        if self.playing and pygame.mixer.get_init():
            pygame.mixer.music.fadeout(int(fade * 1000))
        self.playing = False
