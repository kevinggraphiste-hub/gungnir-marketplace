# voice-speechmatics

Plugin STT Speechmatics pour Gungnir — top qualité multilingue (35+ langues),
batch ou realtime, souverain UK/EU.

## Endpoints

- `POST /api/plugins/voice-speechmatics/transcribe` — soumet un job batch (async)
- `GET  /api/plugins/voice-speechmatics/transcript/{job_id}` — récupère le statut + transcript
- `POST /api/plugins/voice-speechmatics/transcribe-sync` — wrapper sync (soumet + poll)

## Configuration

1. Créer un compte sur https://portal.speechmatics.com/
2. Plan trial : ~500 minutes/mois gratuites
3. Settings → API Keys → Create API Key (Bearer token long)
4. Dans Gungnir : Settings → Marketplace → voice-speechmatics → Configurer
5. Coller la clé dans le champ `speechmatics_api_key`

## Exemple usage (sync — audio court < 10 min)

```bash
curl -X POST 'https://gungnir.scarletwolf.cloud/api/plugins/voice-speechmatics/transcribe-sync' \
  -H 'Authorization: Bearer <ton-token-gungnir>' \
  -F 'file=@audio.wav' \
  -F 'language=fr' \
  -F 'operating_point=enhanced'
```

Réponse :

```json
{"job_id":"abc123","status":"done","transcript":"Bonjour, ceci est un test."}
```

## Exemple usage (async — audio long)

```bash
# 1. Soumettre
curl -X POST '.../transcribe' -F 'file=@long.wav' -F 'language=fr'
# → {"job_id":"abc123","status":"submitted"}

# 2. Poller plus tard (toutes les 30s)
curl '.../transcript/abc123'
# → {"job_id":"abc123","status":"running"}
# ... attendre ...
# → {"job_id":"abc123","status":"done","transcript":"..."}
```

## Limites V1

- **Batch uniquement** — pas de WebSocket realtime (à venir si demande).
- Diarization activée par défaut (identification des locuteurs).
- `operating_point` : `enhanced` (défaut, top qualité) ou `standard` (moins cher, qualité correcte).
