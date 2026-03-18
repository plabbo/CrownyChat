"""
meta_sender.py
Envía mensajes de WhatsApp via Meta Cloud API.
"""

import os
import httpx
import logging

logger = logging.getLogger(__name__)

META_API_URL = "https://graph.facebook.com/v19.0"
PHONE_NUMBER_ID = os.getenv("META_PHONE_NUMBER_ID")
META_ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN")


async def send_whatsapp_message(to: str, text: str):
    """Envía un mensaje de texto via Meta WhatsApp Cloud API."""
    url = f"{META_API_URL}/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {META_ACCESS_TOKEN}",
        "Content-Type":  "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to":   to,
        "type": "text",
        "text": {"body": text},
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, headers=headers, json=payload)
        if resp.status_code != 200:
            logger.error(f"[Meta] Error enviando mensaje: {resp.text}")
        else:
            logger.info(f"[Meta] Mensaje enviado a {to}")
