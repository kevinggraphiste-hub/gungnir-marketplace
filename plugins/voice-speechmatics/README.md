# voice-speechmatics

Stub seed du plugin **voice-speechmatics** pour la Gungnir Marketplace.

Ce dossier contient le squelette minimal pour publier le plugin sur le repo
`gungnir-marketplace`. L'intégration complète avec l'API du provider reste
à compléter par l'auteur du plugin.

## Structure

- `manifest.json` — métadonnées + permissions (cf MARKETPLACE.md)
- `routes.py` — endpoints FastAPI (stub)
- `README.md` — ce fichier

Pour générer le tarball publié :

```bash
tar -czf voice-speechmatics-1.0.0.tar.gz manifest.json routes.py README.md
```
