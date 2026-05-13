# Gungnir Marketplace — Seeds

Ce dossier contient le squelette du futur repo `gungnir-marketplace` à
créer publiquement par ScarletWolf. Il sert à amorcer la marketplace avec
5 plugins voice exemples + le catalog.json initial.

## Initialiser le repo gungnir-marketplace

```bash
# 1. Créer le repo public sur GitHub : kevinggraphiste-hub/gungnir-marketplace
# 2. Cloner localement et copier le contenu de ce dossier :

git clone https://github.com/kevinggraphiste-hub/gungnir-marketplace.git
cd gungnir-marketplace
cp -r ../Gungnir/deploy/marketplace-seeds/* .

# 3. Pour chaque plugin, créer le tarball :
for plugin in plugins/*/; do
  name=$(basename "$plugin")
  version=$(jq -r .version "$plugin/manifest.json")
  tar -czf "$plugin/$name-$version.tar.gz" -C "$plugin" \
    --exclude="*.tar.gz" .
done

# 4. Pousser
git add -A
git commit -m "init: marketplace seeds (5 voice plugins)"
git push -u origin main
```

Une fois en place, l'URL `https://raw.githubusercontent.com/kevinggraphiste-hub/gungnir-marketplace/main/catalog.json`
sera consommée par le backend Gungnir (cf `marketplace.DEFAULT_CATALOG_URL`).

## Structure attendue

```
gungnir-marketplace/
├── catalog.json                    # listing public consommé par Gungnir
├── plugins/
│   ├── voice-cartesia/
│   │   ├── manifest.json
│   │   ├── routes.py
│   │   ├── icon.png
│   │   └── voice-cartesia-1.0.0.tar.gz
│   ├── voice-hume/
│   │   └── ...
│   └── ...
└── README.md (cf MARKETPLACE.md du repo Gungnir pour la doc dev)
```

## Plugins seeds inclus

| Plugin | Type | Provider | Statut |
|---|---|---|---|
| `voice-cartesia` | TTS streaming basse latence | Cartesia (US) | ✅ Production-ready |

**RÈGLE STRICTE** : tout plugin publié sur la marketplace **DOIT** être
pleinement fonctionnel et testable par un utilisateur final. Pas de
stubs, pas de placeholders, pas de "à compléter".

Les plugins en cours de développement (Hume, Voxa, Acapela, Speechmatics)
sont temporairement retirés du catalog publié — ils reviendront quand
leur intégration aura été complétée et testée bout-en-bout.
