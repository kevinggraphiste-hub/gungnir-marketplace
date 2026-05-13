"""
voice-hume — Hume Octave TTS (production-ready).

Endpoints sous /api/plugins/voice-hume/* :
- GET  /voices     → liste des voix prédéfinies (ITO, KORA, DACHER, etc.)
- POST /synthesize → text → audio bytes (mp3 par défaut).
                     Voix par `voice_name` (prédéfinie) OU `voice_description`
                     (langage naturel : "warm young woman, conversational").

Modèle Octave 2 (preview) : latence ~100ms, 11 langues, instant_mode disponible.

Auth : header X-Hume-Api-Key (clé du compte user via SecretsVault).
"""
from __future__ import annotations

import base64
import logging
from typing import Any

from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.db.engine import get_session
from backend.core.services.secrets_vault import SecretsVault
from backend.core.services.plugin_http_client import PluginHTTPClient

PLUGIN_ID = "voice-hume"
HUME_BASE_URL = "https://api.hume.ai"

# Voix prédéfinies Octave 2 connues (extrait de leur library publique)
# La liste évolue — l'user peut aussi passer voice_description en langage naturel.
KNOWN_VOICES = [
    {"name": "ITO", "description": "Conversational young woman", "gender": "female", "lang": "multi"},
    {"name": "KORA", "description": "Warm narrator male", "gender": "male", "lang": "multi"},
    {"name": "DACHER", "description": "Calm male narrator", "gender": "male", "lang": "multi"},
    {"name": "AURA", "description": "Bright energetic woman", "gender": "female", "lang": "multi"},
    {"name": "WHIMSY", "description": "Playful storyteller", "gender": "neutral", "lang": "multi"},
    {"name": "ECHO", "description": "Resonant deep male", "gender": "male", "lang": "multi"},
]

logger = logging.getLogger(f"gungnir.plugins.{PLUGIN_ID}")
router = APIRouter()


def _require_user_id(request: Request) -> int | None:
    return getattr(request.state, "user_id", None)


async def _resolve_api_key(user_id: int, session: AsyncSession) -> str | None:
    return await SecretsVault.get_secret(
        session,
        plugin_id=PLUGIN_ID,
        key_name="hume_api_key",
        user_id=int(user_id),
    )


@router.get("/voices")
async def list_voices(request: Request):
    """Renvoie la liste des voix prédéfinies Octave 2.

    Note : Hume permet aussi des voix custom via voice_description en langage
    naturel (ex 'warm conversational woman, late twenties'), passable au
    /synthesize. Pas besoin de clé pour cette route (liste statique).
    """
    return {"voices": KNOWN_VOICES, "count": len(KNOWN_VOICES)}


@router.post("/synthesize")
async def synthesize(
    payload: dict,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Synthétise un texte via Hume Octave 2.

    Body :
    ```json
    {
      "text": "Bonjour",
      "voice_name": "ITO",                // optionnel — voix prédéfinie
      "voice_description": "warm young woman",  // optionnel — sinon voice_name
      "speed": 1.0,                       // optionnel : 0.5 à 2.0
      "instant_mode": true,               // défaut true (latence ~100ms)
      "trailing_silence": 0.0,            // optionnel : sec de silence en fin
      "language": "fr"                    // optionnel
    }
    ```
    Renvoie audio mp3 binaire (Content-Type: audio/mpeg).

    Au moins une de voice_name ou voice_description doit être fournie.
    """
    uid = _require_user_id(request)
    if not uid:
        return JSONResponse({"error": "Authentification requise"}, status_code=401)

    api_key = await _resolve_api_key(int(uid), session)
    if not api_key:
        return JSONResponse(
            {"error": "Hume API key non configurée. Settings → Marketplace → voice-hume → Configurer."},
            status_code=400,
        )

    text = (payload.get("text") or "").strip()
    if not text:
        return JSONResponse({"error": "Champ 'text' requis"}, status_code=400)
    if len(text) > 5000:
        return JSONResponse({"error": "Texte > 5000 caractères (limite Hume Octave)"}, status_code=400)

    voice_name = payload.get("voice_name")
    voice_description = payload.get("voice_description")
    if not voice_name and not voice_description:
        return JSONResponse(
            {"error": "Au moins voice_name ou voice_description requis"},
            status_code=400,
        )

    utterance: dict[str, Any] = {"text": text}
    if voice_name:
        utterance["voice"] = {"name": voice_name}
    if voice_description:
        utterance["description"] = voice_description
    if "speed" in payload:
        utterance["speed"] = float(payload["speed"])
    if "trailing_silence" in payload:
        utterance["trailing_silence"] = float(payload["trailing_silence"])

    body: dict[str, Any] = {
        "utterances": [utterance],
        "instant_mode": bool(payload.get("instant_mode", True)),
    }
    if payload.get("language"):
        body["language"] = payload["language"]

    async with PluginHTTPClient(plugin_id=PLUGIN_ID, user_id=int(uid), session=session) as http:
        try:
            # /v0/tts (non-streaming JSON) renvoie un JSON avec `generations[*].audio` en base64
            resp = await http.post(
                f"{HUME_BASE_URL}/v0/tts",
                headers={
                    "X-Hume-Api-Key": api_key,
                    "Content-Type": "application/json",
                },
                json=body,
            )
            if resp.status_code == 401:
                return JSONResponse(
                    {"error": "Hume API key invalide. Vérifiez Settings → Marketplace → voice-hume."},
                    status_code=401,
                )
            if resp.status_code == 429:
                return JSONResponse(
                    {"error": "Hume rate limit dépassé. Réessayez dans quelques secondes."},
                    status_code=429,
                )
            if resp.status_code != 200:
                return JSONResponse(
                    {"error": f"Hume API {resp.status_code}: {resp.text[:300]}"},
                    status_code=502,
                )
            data = resp.json()
            generations = data.get("generations") or []
            if not generations:
                return JSONResponse({"error": "Hume n'a renvoyé aucune génération"}, status_code=502)
            audio_b64 = generations[0].get("audio")
            if not audio_b64:
                return JSONResponse({"error": "Hume génération sans audio"}, status_code=502)
            try:
                audio_bytes = base64.b64decode(audio_b64)
            except Exception:
                return JSONResponse({"error": "Audio b64 Hume malformé"}, status_code=502)
            return Response(content=audio_bytes, media_type="audio/mpeg")
        except Exception as e:
            logger.warning(f"Hume /v0/tts failed: {e}")
            return JSONResponse({"error": f"Hume error: {str(e)[:200]}"}, status_code=502)


@router.get("/health")
async def health():
    return {"status": "ok", "plugin": PLUGIN_ID, "version": "1.0.0"}
