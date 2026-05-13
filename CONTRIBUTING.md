# Contribuer à gungnir-marketplace

Ce repo héberge le catalog public des plugins et workflows installables
depuis la marketplace Gungnir.

## Comment publier un plugin/workflow

### Workflows (recommandé)

1. Créez le workflow dans Forge (https://gungnir.scarletwolf.cloud/plugins/forge)
2. Cliquez sur **Publier Marketplace** dans la barre d'outils
3. Confirmez — Forge crée automatiquement une PR sur ce repo, signée avec votre clé Ed25519
4. La CI [auto-review.yml](.github/workflows/auto-review.yml) valide la PR :
   - Signature Ed25519 vs `manifest.author_pubkey`
   - YAML parseable
   - Cohérence : tous les `tool:` du YAML sont dans `manifest.workflow.tools_required`
   - Cohérence : tous les domaines réseau statiques sont dans `manifest.permissions.network_egress`
   - Scan patterns suspects (eval, exec, shell, subprocess) — bloquant pour les workflows
5. Si tout passe : auto-merge en squash. Sinon : commentaire détaillé sur la PR.

### Plugins code (advanced)

Pour les plugins type `voice`, `productivity`, etc. (avec `routes.py`) :

1. Forkez ce repo
2. Créez `plugins/{plugin-id}/` avec `manifest.json`, `routes.py`, `signature.bin`, `README.md`, `icon.png` (optionnel)
3. Signez avec votre clé Ed25519 (la pubkey doit être dans `manifest.author_pubkey`)
4. Mettez à jour `catalog.json` (incrémenter `version`, ajouter votre entrée dans `plugins[]`)
5. Ouvrez une PR — la CI fait la revue automatique
6. Pour les patterns shell/eval/exec dans `routes.py` : warning non-bloquant (revue humaine recommandée)

## Identification & révocation

Chaque plugin/workflow est signé avec la clé Ed25519 du contributeur.
La `author_pubkey` dans le manifest permet de vérifier la signature et
d'identifier l'auteur. En cas de plugin malveillant, la pubkey est
révoquée et tous les plugins signés par cette clé sont automatiquement
désinstallés des Gungnir des users (mécanisme de revocation list à venir).

## Plugins officiels ScarletWolf

Les plugins signés avec la clé `scarletwolf` (hardcodée dans Gungnir comme
trusted) obtiennent un badge "✓ Officiel" dans l'UI marketplace. Les plugins
community avec une `author_pubkey` user obtiennent un badge "✓ Communauté
(@username)".

## Format manifest

Voir l'exemple complet pour un workflow dans le repo Gungnir : `MARKETPLACE.md`.

Champs minimaux pour la CI :

```json
{
  "name": "workflow-mon-truc-u42",
  "display_name": "Mon truc",
  "version": "1.0.0",
  "author": "user:42",
  "author_pubkey": "<pubkey_ed25519_hex_64_chars>",
  "description": "...",
  "type": "workflow",
  "workflow": {
    "entry": "workflow.yaml",
    "tools_required": ["web_fetch", "llm_call"]
  },
  "permissions": {
    "network_egress": ["*.example.com"]
  }
}
```
