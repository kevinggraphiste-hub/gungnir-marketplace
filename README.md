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

| Plugin | Type | Provider | Souverain |
|---|---|---|---|
| `voice-cartesia` | TTS streaming basse latence | Cartesia (US) | ❌ |
| `voice-hume` | TTS expressif émotion | Hume EVI (US) | ❌ |
| `voice-voxa` | TTS FR premium | Voxa (FR) | ✅ |
| `voice-acapela` | TTS FR/BE multilingue | Acapela (BE) | ✅ |
| `voice-speechmatics` | STT pro multilingue | Speechmatics (UK) | ✅ |

Tous les plugins seeds sont **stubs minimaux** — ils déclarent leurs
permissions et exposent un endpoint test, mais l'intégration complète
avec les APIs respectives reste à compléter par leur auteur respectif
ou par ScarletWolf après partenariat.
