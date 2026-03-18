"""
conekta_handler.py
Genera referencias de pago SPEI via Conekta sandbox.
Documentación: https://developers.conekta.com/reference/orders
"""

import os
import logging
import httpx
from typing import Optional

logger = logging.getLogger(__name__)

CONEKTA_API_URL = "https://api.conekta.io"


class ConektaHandler:
    def __init__(self):
        self.api_key = os.getenv("CONEKTA_API_KEY", "")
        self.headers = {
            "Accept":        "application/vnd.conekta-v2.1.0+json",
            "Content-Type":  "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

    async def create_spei_order(self, order_info: dict,
                                 customer_info: dict) -> Optional[dict]:
        """
        Crea una orden de pago SPEI en Conekta sandbox.
        Retorna dict con clabe, monto, referencia y fecha límite.
        """
        if not self.api_key:
            logger.warning("[Conekta] API Key no configurada, usando datos simulados")
            return self._simulated_spei(order_info)

        total_centavos = int(order_info.get("total", 0) * 100)
        phone = customer_info.get("phone", "5500000000").replace("+", "").replace(" ", "")
        name  = customer_info.get("name", "Cliente Biocrowny")
        email = customer_info.get("email", f"cliente{phone[-4:]}@biocrowny.com")

        payload = {
            "currency": "MXN",
            "customer_info": {
                "name":  name,
                "email": email,
                "phone": phone[-10:],
            },
            "line_items": [
                {
                    "name":      f"Pedido Biocrowny #{order_info.get('order_name', '')}",
                    "unit_price": total_centavos,
                    "quantity":   1,
                }
            ],
            "charges": [
                {
                    "payment_method": {
                        "type":       "spei",
                        "expires_at": self._expiry_timestamp(),
                    }
                }
            ],
            "metadata": {
                "odoo_order_id":   str(order_info.get("order_id", "")),
                "odoo_order_name": order_info.get("order_name", ""),
            }
        }

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{CONEKTA_API_URL}/orders",
                    headers=self.headers,
                    json=payload,
                    timeout=10.0
                )
                if resp.status_code in (200, 201):
                    data   = resp.json()
                    charge = data["charges"]["data"][0]
                    pm     = charge["payment_method"]
                    return {
                        "clabe":       pm.get("clabe", ""),
                        "banco":       pm.get("bank", "STP"),
                        "monto":       order_info.get("total", 0),
                        "referencia":  pm.get("reference", ""),
                        "expira":      pm.get("expires_at", ""),
                        "conekta_id":  data.get("id", ""),
                    }
                else:
                    logger.error(f"[Conekta] Error {resp.status_code}: {resp.text[:200]}")
                    return self._simulated_spei(order_info)

        except Exception as e:
            logger.error(f"[Conekta] Error: {e}")
            return self._simulated_spei(order_info)

    def _simulated_spei(self, order_info: dict) -> dict:
        """
        Datos SPEI simulados para desarrollo sin API key.
        Útil para demos y pruebas escolares.
        """
        import random
        clabe = "646180157" + str(random.randint(1000000000, 9999999999))
        return {
            "clabe":      clabe,
            "banco":      "STP (Simulado)",
            "monto":      order_info.get("total", 0),
            "referencia": f"BIO{order_info.get('order_id', '0000')}",
            "expira":     "72 horas",
            "conekta_id": "simulado",
        }

    def _expiry_timestamp(self) -> int:
        """Genera timestamp de expiración: 72 horas desde ahora."""
        import time
        return int(time.time()) + (72 * 3600)

    def format_spei_message(self, spei: dict) -> str:
        """Formatea los datos SPEI para enviar por WhatsApp."""
        return (
            f"💳 *DATOS DE PAGO SPEI*\n\n"
            f"🏦 Banco: {spei['banco']}\n"
            f"📋 CLABE: `{spei['clabe']}`\n"
            f"💰 Monto: ${spei['monto']:.2f} MXN\n"
            f"🔖 Referencia: {spei['referencia']}\n"
            f"⏰ Válido por: {spei['expira']}\n\n"
            f"Una vez realizada la transferencia, "
            f"envíanos tu comprobante y procesaremos tu pedido. ✅"
        )


