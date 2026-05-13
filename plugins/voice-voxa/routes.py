"""Stub plugin — voir voice-cartesia/routes.py pour le pattern complet."""
from fastapi import APIRouter
router = APIRouter()

@router.get("/health")
async def health():
    return {"status": "stub", "message": "Plugin seed, implémentation à venir."}
