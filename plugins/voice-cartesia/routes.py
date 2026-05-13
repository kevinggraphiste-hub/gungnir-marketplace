"""
voice-cartesia — stub plugin pour Cartesia TTS streaming.

Endpoint : POST /api/plugins/voice-cartesia/synthesize
{text, voice?} → audio bytes (mp3 par défaut).

Implémentation complète à compléter avec le SDK Cartesia officiel.
Pour l'instant : skeleton qui consomme SecretsVault + PluginHTTPClient
correctement (sécurité V4).
"""
from __future__ import annotations

from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.db.engine import get_session
from backend.core.services.secrets_vault import SecretsVault
from backend.core.services.plugin_http_client import PluginHTTPClient

PLUGIN_ID = "voice-cartesia"
router = APIRouter()


@router.post("/synthesize")
async def synthesize(
    payload: dict,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        return JSONResponse({"error": "Authentification requise"}, status_code=401)

    api_key = await SecretsVault.get_secret(
        session, plugin_id=PLUGIN_ID,
        key_name="cartesia_api_key", user_id=int(user_id),
    )
    if not api_key:
        return JSONResponse(
            {"error": "Cartesia API key non configurée. Settings → Marketplace → voice-cartesia"},
            status_code=400,
        )

    text = (payload.get("text") or "").strip()
    voice = payload.get("voice") or "default"
    if not text:
        return JSONResponse({"error": "Champ 'text' requis"}, status_code=400)

    async with PluginHTTPClient(
        plugin_id=PLUGIN_ID, user_id=int(user_id), session=session,
    ) as http:
        try:
            resp = await http.post(
                "https://api.cartesia.ai/tts/bytes",
                headers={
                    "X-API-Key": api_key,
                    "Content-Type": "application/json",
                    "Cartesia-Version": "2024-06-30",
                },
                json={
                    "model_id": "sonic-2",
                    "transcript": text,
                    "voice": {"mode": "id", "id": voice},
                    "output_format": {"container": "mp3", "encoding": "mp3", "sample_rate": 44100},
                },
            )
            resp.raise_for_status()
            return Response(content=resp.content, media_type="audio/mpeg")
        except Exception as e:
            return JSONResponse({"error": f"Cartesia API failed: {str(e)[:200]}"}, status_code=502)
