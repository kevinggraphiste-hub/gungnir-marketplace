"""
voice-cartesia — Cartesia TTS via API officielle (production-ready).

Endpoints exposés sous /api/plugins/voice-cartesia/* :
- GET  /voices     → liste des voix Cartesia disponibles
- GET  /models     → liste des modèles (sonic-2, sonic-2-2025-03-07, etc.)
- POST /synthesize → text → audio bytes (mp3 par défaut, wav/pcm/opus possibles)

Le plugin utilise SecretsVault pour la clé API (per-user) et PluginHTTPClient
pour les appels (filtrage egress + audit trail Gungnir).

Usage exemple côté frontend :
    const resp = await apiFetch('/api/plugins/voice-cartesia/synthesize', {
        method: 'POST',
        body: JSON.stringify({text: 'Bonjour', voice: '<voice_id>'}),
    })
    const audioBlob = await resp.blob()
    new Audio(URL.createObjectURL(audioBlob)).play()
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.db.engine import get_session
from backend.core.services.secrets_vault import SecretsVault
from backend.core.services.plugin_http_client import PluginHTTPClient

PLUGIN_ID = "voice-cartesia"
CARTESIA_BASE_URL = "https://api.cartesia.ai"
CARTESIA_VERSION_HEADER = "2024-11-13"
DEFAULT_MODEL = "sonic-2"
DEFAULT_OUTPUT_FORMAT = {"container": "mp3", "encoding": "mp3", "sample_rate": 44100}

logger = logging.getLogger(f"gungnir.plugins.{PLUGIN_ID}")
router = APIRouter()


async def _resolve_api_key(user_id: int, session: AsyncSession) -> str | None:
    return await SecretsVault.get_secret(
        session,
        plugin_id=PLUGIN_ID,
        key_name="cartesia_api_key",
        user_id=int(user_id),
    )


def _require_user_id(request: Request) -> int | None:
    return getattr(request.state, "user_id", None)


@router.get("/voices")
async def list_voices(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Liste les voix Cartesia disponibles pour le compte de l'user."""
    uid = _require_user_id(request)
    if not uid:
        return JSONResponse({"error": "Authentification requise"}, status_code=401)
    api_key = await _resolve_api_key(int(uid), session)
    if not api_key:
        return JSONResponse(
            {"error": "Cartesia API key non configurée. Settings → Marketplace → voice-cartesia → Configurer."},
            status_code=400,
        )
    async with PluginHTTPClient(plugin_id=PLUGIN_ID, user_id=int(uid), session=session) as http:
        try:
            resp = await http.get(
                f"{CARTESIA_BASE_URL}/voices/",
                headers={
                    "X-API-Key": api_key,
                    "Cartesia-Version": CARTESIA_VERSION_HEADER,
                },
            )
            if resp.status_code != 200:
                return JSONResponse(
                    {"error": f"Cartesia API {resp.status_code}: {resp.text[:200]}"},
                    status_code=502,
                )
            voices = resp.json()
            # Normalise pour l'UI Gungnir (id, name, language, gender)
            normalized = []
            for v in voices if isinstance(voices, list) else []:
                normalized.append({
                    "id": v.get("id"),
                    "name": v.get("name"),
                    "language": v.get("language"),
                    "description": v.get("description"),
                    "is_owner": v.get("is_owner", False),
                })
            return {"voices": normalized, "count": len(normalized)}
        except Exception as e:
            logger.warning(f"Cartesia /voices failed: {e}")
            return JSONResponse({"error": f"Cartesia /voices error: {str(e)[:200]}"}, status_code=502)


@router.get("/models")
async def list_models():
    """Liste statique des modèles TTS Cartesia recommandés.

    Pas d'endpoint Cartesia public pour ça à ce jour — on hardcode les
    modèles recommandés par leur doc 2024-2026. À mettre à jour si nouveau
    modèle sort.
    """
    return {
        "models": [
            {"id": "sonic-2", "name": "Sonic 2 (latest, top quality, ~75ms latency)", "default": True},
            {"id": "sonic-english", "name": "Sonic English"},
            {"id": "sonic-multilingual", "name": "Sonic Multilingual"},
            {"id": "sonic-turbo", "name": "Sonic Turbo (latency-optimized)"},
        ]
    }


@router.post("/synthesize")
async def synthesize(
    payload: dict,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Synthétise un texte en audio via Cartesia Sonic-2.

    Body :
    ```json
    {
      "text": "Bonjour",
      "voice": "<voice_id>",        // requis, format Cartesia
      "model": "sonic-2",           // optionnel, défaut sonic-2
      "language": "fr",             // optionnel
      "speed": "normal",            // optionnel : slow|normal|fast OU float -1..1
      "container": "mp3"            // optionnel : mp3|wav|raw
    }
    ```
    Renvoie le binaire audio (Content-Type: audio/mpeg ou audio/wav selon container).
    """
    uid = _require_user_id(request)
    if not uid:
        return JSONResponse({"error": "Authentification requise"}, status_code=401)

    api_key = await _resolve_api_key(int(uid), session)
    if not api_key:
        return JSONResponse(
            {"error": "Cartesia API key non configurée. Settings → Marketplace → voice-cartesia → Configurer."},
            status_code=400,
        )

    text = (payload.get("text") or "").strip()
    voice = payload.get("voice")
    if not text:
        return JSONResponse({"error": "Champ 'text' requis"}, status_code=400)
    if not voice:
        return JSONResponse(
            {"error": "Champ 'voice' (voice_id Cartesia) requis. Récupérez-en un via GET /voices."},
            status_code=400,
        )

    model = payload.get("model") or DEFAULT_MODEL
    language = payload.get("language") or "fr"
    speed = payload.get("speed") or "normal"
    container = payload.get("container") or "mp3"

    output_format: dict[str, Any] = {"container": container}
    if container == "mp3":
        output_format.update({"sample_rate": 44100, "bit_rate": 128000})
    elif container == "wav":
        output_format.update({"encoding": "pcm_f32le", "sample_rate": 44100})
    elif container == "raw":
        output_format.update({"encoding": "pcm_s16le", "sample_rate": 44100})

    body: dict[str, Any] = {
        "model_id": model,
        "transcript": text,
        "voice": {"mode": "id", "id": voice},
        "language": language,
        "output_format": output_format,
    }
    if speed != "normal":
        body["voice"]["__experimental_controls"] = {"speed": speed}

    async with PluginHTTPClient(plugin_id=PLUGIN_ID, user_id=int(uid), session=session) as http:
        try:
            resp = await http.post(
                f"{CARTESIA_BASE_URL}/tts/bytes",
                headers={
                    "X-API-Key": api_key,
                    "Content-Type": "application/json",
                    "Cartesia-Version": CARTESIA_VERSION_HEADER,
                },
                json=body,
            )
            if resp.status_code == 401:
                return JSONResponse(
                    {"error": "Cartesia API key invalide. Vérifiez Settings → Marketplace → voice-cartesia."},
                    status_code=401,
                )
            if resp.status_code == 402:
                return JSONResponse(
                    {"error": "Crédit Cartesia épuisé. https://play.cartesia.ai/billing"},
                    status_code=402,
                )
            if resp.status_code == 429:
                return JSONResponse(
                    {"error": "Cartesia rate limit dépassé. Réessayez dans quelques secondes."},
                    status_code=429,
                )
            if resp.status_code != 200:
                return JSONResponse(
                    {"error": f"Cartesia API {resp.status_code}: {resp.text[:300]}"},
                    status_code=502,
                )
            media_type = "audio/mpeg" if container == "mp3" else f"audio/{container}"
            return Response(content=resp.content, media_type=media_type)
        except Exception as e:
            logger.warning(f"Cartesia /tts/bytes failed: {e}")
            return JSONResponse({"error": f"Cartesia error: {str(e)[:200]}"}, status_code=502)


@router.get("/health")
async def health():
    """Vérifie que l'API Cartesia répond avec la clé configurée."""
    return {"status": "ok", "plugin": PLUGIN_ID, "version": "1.0.0"}
