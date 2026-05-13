"""
voice-speechmatics — Speechmatics STT batch (production-ready).

Endpoints sous /api/plugins/voice-speechmatics/* :
- POST /transcribe       → multipart audio + lang/operating_point
                           → {job_id, status: "submitted"}
- GET  /transcript/{id}  → poll le job, renvoie {status, transcript?}
- GET  /transcribe-sync  → wrapper sync : transcribe + poll jusqu'à done
                           → {transcript: "..."}

Batch API : POST /v2/jobs/ (multipart data_file + config JSON)
Auth : Authorization: Bearer <api_key>
Realtime WebSocket : wss://eu2.rt.speechmatics.com/v2 (non implémenté
en V1 — pour streaming live, intégration séparée à faire)

Pricing : ~$0.6/h (Standard) à $1.8/h (Enhanced).
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, Request, Depends, UploadFile, File, Form
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.db.engine import get_session
from backend.core.services.secrets_vault import SecretsVault
from backend.core.services.plugin_http_client import PluginHTTPClient

PLUGIN_ID = "voice-speechmatics"
SM_BASE_URL = "https://asr.api.speechmatics.com/v2"

logger = logging.getLogger(f"gungnir.plugins.{PLUGIN_ID}")
router = APIRouter()


def _require_user_id(request: Request) -> int | None:
    return getattr(request.state, "user_id", None)


async def _resolve_api_key(user_id: int, session: AsyncSession) -> str | None:
    return await SecretsVault.get_secret(
        session,
        plugin_id=PLUGIN_ID,
        key_name="speechmatics_api_key",
        user_id=int(user_id),
    )


def _build_config(language: str, operating_point: str) -> str:
    """Construit le JSON config Speechmatics pour la transcription batch."""
    return json.dumps({
        "type": "transcription",
        "transcription_config": {
            "language": language,
            "operating_point": operating_point,  # "standard" ou "enhanced"
            "diarization": "speaker",
        },
    })


@router.post("/transcribe")
async def transcribe(
    request: Request,
    file: UploadFile = File(...),
    language: str = Form("fr"),
    operating_point: str = Form("enhanced"),
    session: AsyncSession = Depends(get_session),
):
    """Soumet un job de transcription batch. Async — utilisez /transcript/{id}
    pour récupérer le résultat, ou /transcribe-sync pour attendre.

    Multipart : `file` (audio), `language` (défaut fr), `operating_point`
    (standard|enhanced, défaut enhanced).
    """
    uid = _require_user_id(request)
    if not uid:
        return JSONResponse({"error": "Authentification requise"}, status_code=401)

    api_key = await _resolve_api_key(int(uid), session)
    if not api_key:
        return JSONResponse(
            {"error": "Speechmatics API key non configurée. Settings → Marketplace → voice-speechmatics."},
            status_code=400,
        )

    audio_bytes = await file.read()
    if not audio_bytes:
        return JSONResponse({"error": "Fichier audio vide"}, status_code=400)

    if operating_point not in ("standard", "enhanced"):
        return JSONResponse({"error": "operating_point doit être 'standard' ou 'enhanced'"}, status_code=400)

    config_json = _build_config(language, operating_point)

    async with PluginHTTPClient(plugin_id=PLUGIN_ID, user_id=int(uid), session=session) as http:
        try:
            files = {
                "data_file": (file.filename or "audio.wav", audio_bytes, file.content_type or "audio/wav"),
                "config": (None, config_json, "application/json"),
            }
            resp = await http.post(
                f"{SM_BASE_URL}/jobs/",
                headers={"Authorization": f"Bearer {api_key}"},
                files=files,
            )
            if resp.status_code == 401:
                return JSONResponse({"error": "Speechmatics API key invalide"}, status_code=401)
            if resp.status_code != 201:
                return JSONResponse(
                    {"error": f"Speechmatics {resp.status_code}: {resp.text[:300]}"},
                    status_code=502,
                )
            job = resp.json()
            return {"job_id": job.get("id"), "status": "submitted"}
        except Exception as e:
            logger.warning(f"Speechmatics POST /jobs failed: {e}")
            return JSONResponse({"error": f"Speechmatics error: {str(e)[:200]}"}, status_code=502)


@router.get("/transcript/{job_id}")
async def get_transcript(
    job_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Renvoie le statut + transcript final d'un job de transcription.

    Statuts possibles : `running` (encore en cours), `done`, `rejected` (échec).
    Quand `done`, le champ `transcript` contient le texte final.
    """
    uid = _require_user_id(request)
    if not uid:
        return JSONResponse({"error": "Authentification requise"}, status_code=401)

    api_key = await _resolve_api_key(int(uid), session)
    if not api_key:
        return JSONResponse({"error": "Speechmatics API key non configurée"}, status_code=400)

    async with PluginHTTPClient(plugin_id=PLUGIN_ID, user_id=int(uid), session=session) as http:
        try:
            # Status du job
            status_resp = await http.get(
                f"{SM_BASE_URL}/jobs/{job_id}",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            if status_resp.status_code == 404:
                return JSONResponse({"error": f"Job {job_id} introuvable"}, status_code=404)
            if status_resp.status_code != 200:
                return JSONResponse(
                    {"error": f"Speechmatics status {status_resp.status_code}"},
                    status_code=502,
                )
            job = status_resp.json().get("job") or status_resp.json()
            status = job.get("status", "unknown")

            if status != "done":
                return {"job_id": job_id, "status": status}

            # Si done, récupère le transcript txt
            tr_resp = await http.get(
                f"{SM_BASE_URL}/jobs/{job_id}/transcript?format=txt",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            if tr_resp.status_code != 200:
                return JSONResponse(
                    {"error": f"Speechmatics transcript {tr_resp.status_code}"},
                    status_code=502,
                )
            return {"job_id": job_id, "status": "done", "transcript": tr_resp.text}
        except Exception as e:
            logger.warning(f"Speechmatics GET /jobs/{job_id} failed: {e}")
            return JSONResponse({"error": f"Speechmatics error: {str(e)[:200]}"}, status_code=502)


@router.post("/transcribe-sync")
async def transcribe_sync(
    request: Request,
    file: UploadFile = File(...),
    language: str = Form("fr"),
    operating_point: str = Form("enhanced"),
    poll_timeout_s: int = Form(180),
    session: AsyncSession = Depends(get_session),
):
    """Wrapper sync : soumet le job + poll jusqu'à done (ou timeout).

    Pratique pour usage simple — pour les longs audios (> 10 min) préférer
    le mode async transcribe + transcript/{id} pour ne pas bloquer la
    requête HTTP.
    """
    submit_resp = await transcribe(
        request=request, file=file, language=language,
        operating_point=operating_point, session=session,
    )
    if isinstance(submit_resp, JSONResponse):
        return submit_resp
    job_id = submit_resp.get("job_id")
    if not job_id:
        return JSONResponse({"error": "Pas de job_id renvoyé"}, status_code=502)

    # Poll
    elapsed = 0
    while elapsed < poll_timeout_s:
        await asyncio.sleep(3)
        elapsed += 3
        result = await get_transcript(job_id=job_id, request=request, session=session)
        if isinstance(result, JSONResponse):
            return result
        if result.get("status") == "done":
            return result
        if result.get("status") == "rejected":
            return JSONResponse({"error": "Speechmatics job rejected", "job_id": job_id}, status_code=502)

    return JSONResponse(
        {"error": f"Timeout polling après {poll_timeout_s}s. Récupérez via /transcript/{job_id} plus tard."},
        status_code=504,
    )


@router.get("/health")
async def health():
    return {"status": "ok", "plugin": PLUGIN_ID, "version": "1.0.0"}
