"""
odoo_handler.py
Maneja todas las operaciones con Odoo via XML-RPC.
Pipeline completo: Venta → Confirmar → Validar Inventario → Factura
"""

import os
import logging
import xmlrpc.client
from typing import Optional

logger = logging.getLogger(__name__)


class OdooHandler:
    def __init__(self):
        self.url      = os.getenv("ODOO_URL", "https://tuempresa.odoo.com")
        self.db       = os.getenv("ODOO_DB", "tu_base_de_datos")
        self.user     = os.getenv("ODOO_USER", "admin@tuempresa.com")
        self.password = os.getenv("ODOO_PASSWORD", "tu_password")

        self.common = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/common")
        self.models = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/object")
        self.uid    = self._authenticate()

    def _authenticate(self) -> Optional[int]:
        try:
            uid = self.common.authenticate(self.db, self.user, self.password, {})
            if uid:
                logger.info(f"[Odoo] Conectado como UID={uid}")
                return uid
            logger.error("[Odoo] Credenciales inválidas")
            return None
        except Exception as e:
            logger.error(f"[Odoo] Error de conexión: {e}")
            return None

    def _execute(self, model: str, method: str, *args):
        try:
            return self.models.execute_kw(
                self.db, self.uid, self.password,
                model, method, *args
            )
        except Exception as e:
            logger.error(f"[Odoo] Error en {model}.{method}: {e}")
            return None

    # ─────────────────────────────────────────
    # PRODUCTOS
    # ─────────────────────────────────────────
    def get_products(self, category: Optional[str] = None, limit: int = 50) -> list:
        domain = [("sale_ok", "=", True), ("active", "=", True)]

        if category:
            # Buscar por referencia interna (default_code) o nombre de categoría
            by_ref = self._execute(
                "product.template", "search_read",
                [[("default_code", "ilike", category),
                  ("sale_ok", "=", True), ("active", "=", True)]],
                {"fields": ["name", "list_price", "description_sale",
                            "categ_id", "default_code"], "limit": limit}
            )
            if by_ref:
                return by_ref

            cat_ids = self._execute(
                "product.category", "search",
                [[("name", "ilike", category)]]
            )
            if cat_ids:
                domain.append(("categ_id", "in", cat_ids))

        products = self._execute(
            "product.template", "search_read",
            [domain],
            {"fields": ["name", "list_price", "description_sale",
                        "categ_id", "default_code"], "limit": limit}
        )
        return products or []

    def search_product(self, name: str) -> Optional[dict]:
        results = self._execute(
            "product.product", "search_read",
            [[("name", "ilike", name), ("sale_ok", "=", True), ("active", "=", True)]],
            {"fields": ["id", "name", "list_price", "default_code"], "limit": 1}
        )
        return results[0] if results else None

    def format_catalog(self, products: list) -> str:
        if not products:
            return "😔 No hay productos disponibles en este momento."
        lines = ["📦 *CATÁLOGO DE PRODUCTOS*\n"]
        for i, p in enumerate(products[:15], 1):
            price = p.get("list_price", 0)
            desc  = p.get("description_sale") or ""
            desc_short = (desc[:50] + "...") if len(desc) > 50 else desc
            lines.append(f"{i}. *{p['name']}* - ${price:.2f}")
            if desc_short:
                lines.append(f"   _{desc_short}_")
        lines.append("\n✍️ Escribe el nombre del producto para agregarlo a tu carrito.")
        return "\n".join(lines)

    def format_cart(self, cart: list) -> str:
        if not cart:
            return "🛒 Tu carrito está vacío.\n\nEscribe *catálogo* para ver los productos disponibles."
        lines = ["🛒 *TU CARRITO*\n"]
        total = 0
        for item in cart:
            subtotal = item.get("price", 0) * item.get("qty", 1)
            total   += subtotal
            lines.append(f"• {item['qty']}x {item['name']} — ${subtotal:.2f}")
        lines.append(f"\n💰 *Total: ${total:.2f}*")
        lines.append("\n¿Confirmas tu pedido? Escribe *confirmar* o *cancelar*.")
        return "\n".join(lines)

    # ─────────────────────────────────────────
    # CLIENTES
    # ─────────────────────────────────────────
    def get_or_create_partner(self, user_id: str, customer_info: dict) -> Optional[int]:
        phone = customer_info.get("phone") or user_id.replace("whatsapp:", "")
        name  = customer_info.get("name", f"Cliente WA {phone[-4:]}")

        existing = self._execute(
            "res.partner", "search",
            [[("phone", "=", phone)]], {"limit": 1}
        )
        if existing:
            # Actualizar dirección si se proporcionó
            if customer_info.get("address"):
                self._execute("res.partner", "write",
                    [[existing[0]], {"street": customer_info["address"]}])
            return existing[0]

        partner_data = {
            "name":    name,
            "phone":   phone,
            "comment": f"Cliente de WhatsApp | ID: {user_id}",
        }
        if customer_info.get("address"):
            partner_data["street"] = customer_info["address"]

        partner_id = self._execute("res.partner", "create", [partner_data])
        logger.info(f"[Odoo] Nuevo cliente creado: ID={partner_id}, nombre={name}")
        return partner_id

    # ─────────────────────────────────────────
    # PEDIDOS — PIPELINE COMPLETO
    # ─────────────────────────────────────────
    def create_sale_order(self, user_id: str, cart: list,
                          customer_info: dict) -> Optional[dict]:
        """
        Crea y procesa un pedido completo en Odoo:
        1. Crea la orden de venta (borrador)
        2. Confirma la orden (draft → sale)
        3. Valida el picking de inventario si hay stock
        4. Genera la factura
        Retorna dict con order_id, order_name, invoice_id, total
        """
        partner_id = self.get_or_create_partner(user_id, customer_info)
        if not partner_id:
            logger.error("[Odoo] No se pudo obtener/crear el cliente")
            return None

        # 1. Preparar líneas del pedido
        order_lines = []
        for item in cart:
            order_lines.append((0, 0, {
                "product_id":      item["product_id"],
                "product_uom_qty": item["qty"],
                "price_unit":      item["price"],
            }))

        order_data = {
            "partner_id": partner_id,
            "order_line": order_lines,
            "note":       f"Pedido recibido por WhatsApp | ID sesión: {user_id}",
            "origin":     "WhatsApp Bot",
        }

        order_id = self._execute("sale.order", "create", [order_data])
        if not order_id:
            return None
        logger.info(f"[Odoo] Orden creada: ID={order_id}")

        # 2. Confirmar la orden (draft → sale)
        try:
            self._execute("sale.order", "action_confirm", [[order_id]])
            logger.info(f"[Odoo] Orden confirmada: ID={order_id}")
        except Exception as e:
            logger.warning(f"[Odoo] No se pudo confirmar la orden: {e}")

        # 3. Validar inventario (picking)
        try:
            picking_ids = self._execute(
                "stock.picking", "search",
                [[["sale_id", "=", order_id],
                  ["state", "not in", ["done", "cancel"]]]]
            )
            if picking_ids:
                for picking_id in picking_ids:
                    # Forzar cantidades como disponibles
                    picking = self._execute(
                        "stock.picking", "read",
                        [[picking_id], ["move_ids"]]
                    )
                    if picking and picking[0].get("move_ids"):
                        for move_id in picking[0]["move_ids"]:
                            move = self._execute(
                                "stock.move", "read",
                                [[move_id], ["product_uom_qty"]]
                            )
                            if move:
                                self._execute("stock.move", "write",
                                    [[move_id], {
                                        "quantity": move[0]["product_uom_qty"]
                                    }])
                    self._execute("stock.picking", "button_validate", [[picking_id]])
                logger.info(f"[Odoo] Inventario validado para orden {order_id}")
        except Exception as e:
            logger.warning(f"[Odoo] No se pudo validar inventario: {e}")

        # 4. Crear factura
        invoice_id = None
        try:
            self._execute("sale.order", "action_create_invoice", [[order_id]], {})
            invoices = self._execute(
                "account.move", "search",
                [[["invoice_origin", "like", str(order_id)],
                  ["move_type", "=", "out_invoice"]]]
            )
            if invoices:
                invoice_id = invoices[0]
                logger.info(f"[Odoo] Factura creada: ID={invoice_id}")
        except Exception as e:
            logger.warning(f"[Odoo] No se pudo crear factura: {e}")

        # Obtener nombre y total de la orden
        order_info = self._execute(
            "sale.order", "read",
            [[order_id], ["name", "amount_total"]]
        )
        order_name  = order_info[0]["name"] if order_info else f"S{order_id:05d}"
        order_total = order_info[0]["amount_total"] if order_info else 0

        return {
            "order_id":   order_id,
            "order_name": order_name,
            "invoice_id": invoice_id,
            "total":      order_total,
        }

    def get_order_status(self, order_ref: str) -> Optional[dict]:
        domain = [["id", "=", int(order_ref)]] if order_ref.isdigit() \
                 else [["name", "=", order_ref]]
        results = self._execute(
            "sale.order", "search_read",
            [domain],
            {"fields": ["name", "state", "amount_total",
                        "date_order", "partner_id"], "limit": 1}
        )
        return results[0] if results else None

    def format_order_status(self, order: dict) -> str:
        estados = {
            "draft":  "📝 Borrador",
            "sent":   "📤 Enviado",
            "sale":   "✅ Confirmado",
            "done":   "📦 Completado",
            "cancel": "❌ Cancelado",
        }
        estado = estados.get(order.get("state", ""), order.get("state", ""))
        return (
            f"📋 *Pedido {order['name']}*\n"
            f"Estado: {estado}\n"
            f"Total: ${order.get('amount_total', 0):.2f}\n"
            f"Fecha: {str(order.get('date_order', ''))[:10]}"
        )