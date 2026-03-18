"""
session_manager.py
Gestiona las sesiones de los usuarios (carrito, historial, datos del cliente).
En producción reemplazar con Redis o base de datos.
"""

import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)

SESSION_TTL = 3600 * 4  # 4 horas de inactividad


class SessionManager:
    def __init__(self):
        self._sessions: dict = {}

    def get_or_create(self, user_id: str) -> dict:
        """Obtiene o crea una sesión para el usuario."""
        now = time.time()
        session = self._sessions.get(user_id)

        # Crear nueva sesión o resetear si expiró
        if not session or (now - session.get("last_active", 0)) > SESSION_TTL:
            self._sessions[user_id] = {
                "user_id":       user_id,
                "cart":          [],
                "customer_info": {},
                "history":       [],
                "created_at":    now,
                "last_active":   now,
            }
            logger.info(f"[Session] Nueva sesión para {user_id}")

        self._sessions[user_id]["last_active"] = now
        return self._sessions[user_id]

    def add_to_cart(self, user_id: str, product: dict, qty: int = 1):
        """Agrega o actualiza un producto en el carrito."""
        session = self.get_or_create(user_id)
        cart = session["cart"]

        # Verificar si ya está en el carrito
        for item in cart:
            if item["product_id"] == product["id"]:
                item["qty"] += qty
                logger.info(f"[Session] Carrito actualizado: {product['name']} x{item['qty']}")
                return

        # Agregar nuevo ítem
        cart.append({
            "product_id": product["id"],
            "name":       product["name"],
            "price":      product.get("list_price", 0),
            "qty":        qty,
        })
        logger.info(f"[Session] Agregado al carrito: {product['name']} x{qty}")

    def get_cart(self, user_id: str) -> list:
        """Retorna el carrito del usuario."""
        return self._sessions.get(user_id, {}).get("cart", [])

    def clear_cart(self, user_id: str):
        """Vacía el carrito."""
        if user_id in self._sessions:
            self._sessions[user_id]["cart"] = []

    def update_customer_info(self, user_id: str, info: dict):
        """Actualiza los datos del cliente."""
        session = self.get_or_create(user_id)
        session["customer_info"].update({k: v for k, v in info.items() if v})
        logger.info(f"[Session] Datos cliente actualizados para {user_id}: {list(info.keys())}")

    def add_message(self, user_id: str, role: str, content: str):
        """Agrega un mensaje al historial de conversación."""
        session = self.get_or_create(user_id)
        session["history"].append({"role": role, "content": content})
        # Mantener solo los últimos 20 mensajes
        session["history"] = session["history"][-20:]

    def clear_session(self, user_id: str):
        """Elimina la sesión completa del usuario."""
        self._sessions.pop(user_id, None)
