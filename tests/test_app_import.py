"""L'application (app.py) s'importe : aucun module de l'interface ne casse au
chargement."""

def test_import_app():
    import src.kora.app
    import src.kora.render
