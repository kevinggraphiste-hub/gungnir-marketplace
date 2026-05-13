# voice-hume

Plugin TTS Hume Octave 2 pour Gungnir — voix expressives avec emotional
intelligence, latence ~100ms en instant_mode, 11 langues supportées.

## Endpoints

- `GET  /api/plugins/voice-hume/voices` — Liste des voix prédéfinies
- `POST /api/plugins/voice-hume/synthesize` — text → audio mp3

## Configuration

Crée un compte Hume sur https://platform.hume.ai/ et récupère ta clé API.
Puis Settings → Marketplace → voice-hume → Configurer → colle la clé dans
le champ `hume_api_key`.

## Exemple d'usage

```bash
curl -X POST 'https://gungnir.scarletwolf.cloud/api/plugins/voice-hume/synthesize' \
  -H 'Authorization: Bearer <ton-token-gungnir>' \
  -H 'Content-Type: application/json' \
  -d '{
    "text": "Bonjour, je suis Gungnir.",
    "voice_name": "ITO",
    "language": "fr",
    "instant_mode": true
  }' \
  --output test.mp3
```

Voix custom via description naturelle :

```bash
-d '{"text":"...","voice_description":"warm conversational young woman"}'
```
