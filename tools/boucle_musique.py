"""Faire d'un morceau une BOUCLE sans couture (la musique de guerre).

    python tools/boucle_musique.py source.wav data/music/casus_bellis.ogg

Le jeu fait lui-meme le fondu d'entree (et de sortie) : la boucle prend le
coeur du morceau, apres sa montee et avant son extinction.
  1. Le debut A : la ou la montee est finie (le volume atteint son plein).
  2. La fin B : dans les dernieres secondes avant l'extinction, la ou les
     XFADE secondes qui suivent B ressemblent le plus aux XFADE secondes
     qui suivent A (le meme accord, le meme temps du rythme) : on compare
     les spectres (bandes d'energie), puis on cale la phase a l'echantillon
     pres (correlation de la forme d'onde).
  3. La boucle = le morceau de A a B ; ses XFADE premieres secondes sont un
     fondu enchaine (a puissance egale) entre la suite de B et le debut A :
     la fin de la boucle s'enchaine sur la suite naturelle de B, qui se
     fond dans le debut. On n'entend pas le raccord.
Ecrit un OGG Vorbis (soundfile) et dit ce qu'il a choisi, et la mesure du
raccord (le saut d'echantillon, la difference de spectre au raccord, comparee
a celle d'une couture ordinaire du morceau).
"""

from __future__ import annotations

import sys

import numpy as np
import soundfile as sf

XFADE = 2.0
HOP = 512
BANDS = 48
# On cherche A dans les premieres secondes apres la montee, B dans les
# dernieres SEARCH secondes avant l'extinction.
SEARCH = 25.0
FULL_DB = -6.0


def _rms_db(mono: np.ndarray, rate: int, step: float = 0.1) -> np.ndarray:
    n = int(rate * step)
    frames = len(mono) // n
    rms = np.sqrt(np.mean(mono[: frames * n].reshape(frames, n) ** 2, axis=1))
    return 20 * np.log10(np.maximum(rms, 1e-7) / max(rms.max(), 1e-7))


def _bands(mono: np.ndarray) -> np.ndarray:
    """Spectre par trame (HOP), regroupe en BANDS bandes logarithmiques, en log."""
    win = np.hanning(HOP * 4)
    frames = (len(mono) - len(win)) // HOP
    idx = np.arange(len(win))[None, :] + HOP * np.arange(frames)[:, None]
    spec = np.abs(np.fft.rfft(mono[idx] * win, axis=1))
    edges = np.unique(np.geomspace(2, spec.shape[1] - 1, BANDS + 1).astype(int))
    out = np.stack([spec[:, a:b].mean(axis=1) for a, b in zip(edges[:-1], edges[1:])], axis=1)
    return np.log1p(out * 50)


def build(src: str, dst: str) -> dict:
    data, rate = sf.read(src, dtype="float32", always_2d=True)
    mono = data.mean(axis=1)
    db = _rms_db(mono, rate)
    loud = np.where(db >= FULL_DB)[0]
    a_min = loud[0] * 0.1 + 0.5
    end_full = loud[-1] * 0.1 - 0.5
    L = int(XFADE * rate)
    feat = _bands(mono)
    w = int(XFADE * rate / HOP)
    fa0 = int(a_min * rate / HOP)
    a_frames = range(fa0, fa0 + int(4.0 * rate / HOP))
    b_hi = int((end_full - XFADE) * rate / HOP)
    b_lo = int((end_full - SEARCH) * rate / HOP)

    def window(f):
        v = feat[f : f + w].ravel()
        v = v - v.mean()
        return v / (np.linalg.norm(v) + 1e-9)

    best = (-2.0, 0, 0)
    bwins = {fb: window(fb) for fb in range(b_lo, b_hi)}
    for fa in a_frames:
        va = window(fa)
        for fb, vb in bwins.items():
            s = float(va @ vb)
            if s > best[0]:
                best = (s, fa, fb)
    score, fa, fb = best
    A, B = fa * HOP, fb * HOP
    # La phase a l'echantillon pres : on deplace B de +/- 15 ms.
    span = int(0.015 * rate)
    ref = mono[A : A + int(0.05 * rate)]
    shifts = range(-span, span + 1)
    corr = [float(np.dot(ref, mono[B + d : B + d + len(ref)])) for d in shifts]
    B += list(shifts)[int(np.argmax(corr))]
    loop = data[A:B].copy()
    t = np.linspace(0.0, np.pi / 2, L, dtype=np.float32)[:, None]
    loop[:L] = data[A : A + L] * np.sin(t) + data[B : B + L] * np.cos(t)
    # La mesure du raccord : le saut d'echantillon a la couture (fin -> debut),
    # compare aux sauts ordinaires d'un echantillon au suivant.
    seam = float(np.abs(loop[0] - loop[-1]).max())
    ordinary = float(np.percentile(np.abs(np.diff(data[A:B], axis=0)).max(axis=1), 99))
    # Par blocs : libsndfile plante en ecrivant un long OGG d'un seul coup.
    with sf.SoundFile(dst, "w", rate, loop.shape[1], format="OGG", subtype="VORBIS") as out:
        for i in range(0, len(loop), 1 << 15):
            out.write(loop[i : i + (1 << 15)])
    return {
        "debut": A / rate, "fin": B / rate, "duree": (B - A) / rate, "ressemblance": score,
        "saut_raccord": seam, "saut_ordinaire_99": ordinary,
    }


if __name__ == "__main__":
    out = build(sys.argv[1], sys.argv[2])
    for k, v in out.items():
        print(f"{k} : {v:.4f}")
