import traceback

from src.kora.app import run

if __name__ == "__main__":
    try:
        run()
    except Exception:
        # L'exe n'a pas de console : l'erreur est ecrite a cote des sauvegardes
        # (%APPDATA%\Kora\kora_erreur.txt), pour qu'on sache pourquoi il s'est ferme.
        from src.kora import __version__
        from src.kora.persist import default_save_path

        path = default_save_path().parent.parent / "kora_erreur.txt"
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"Kora {__version__}\n\n" + traceback.format_exc(), encoding="utf-8")
        except OSError:
            pass
        raise
