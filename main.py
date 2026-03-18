"""
main.py — WhatsApp → Gemini → Odoo Order Bot
Pipeline completo: Venta → Inventario → Factura → SPEI
"""

import os
import logging
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse
from dotenv import load_dotenv
import uvicorn

load_dotenv()

from gemini_handler import GeminiHandler
from odoo_handler import OdooHandler
from session_manager import SessionManager
from conekta_handler import ConektaHandler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="WhatsApp-Gemini-Odoo Bot")

gemini   = GeminiHandler()
odoo     = OdooHandler()
sessions = SessionManager()
conekta  = ConektaHandler()


# ──────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────
def truncate_for_whatsapp(text: str, limit: int = 1500) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n\n_(Escribe 'más' para continuar)_"

def escape_xml(text: str) -> str:
    return (text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;"))


# ──────────────────────────────────────────────────────
# STARTUP
# ──────────────────────────────────────────────────────
@app.on_event("startup")
async def startup_event():
    products = odoo.get_products()
    gemini.set_catalog(products)
    logger.info(f"[Startup] Catálogo cargado: {len(products)} productos disponibles para Gemini")


@app.post("/admin/reload-catalog")
async def reload_catalog():
    products = odoo.get_products()
    gemini.set_catalog(products)
    return {"status": "ok", "productos": len(products)}


# ──────────────────────────────────────────────────────
# WEBHOOK CONEKTA — recibe notificación de pago recibido
# ──────────────────────────────────────────────────────
@app.post("/webhook/conekta")
async def conekta_webhook(request: Request):
    """
    Conekta llama este endpoint cuando un pago SPEI es recibido.
    Actualiza el estado del pedido en Odoo y notifica al cliente.
    """
    try:
        data       = await request.json()
        event_type = data.get("type", "")

        if event_type == "order.paid":
            order_data  = data["data"]["object"]
            odoo_order  = order_data.get("metadata", {}).get("odoo_order_name", "")
            conekta_id  = order_data.get("id", "")
            logger.info(f"[Conekta] Pago recibido para orden Odoo: {odoo_order}")
            # Aquí podrías confirmar la factura en Odoo o enviar WhatsApp al cliente
            # Por ahora solo logueamos — suficiente para demo escolar

    except Exception as e:
        logger.error(f"[Conekta webhook] Error: {e}")

    return {"status": "ok"}


# ──────────────────────────────────────────────────────
# WEBHOOK TWILIO
# ──────────────────────────────────────────────────────
@app.post("/webhook/twilio")
async def twilio_webhook(request: Request):
    form        = await request.form()
    from_number = form.get("From", "")
    body        = form.get("Body", "").strip()

    if not from_number or not body:
        return PlainTextResponse("", status_code=200)

    logger.info(f"[Twilio] De: {from_number} | Msg: {body}")
    reply = await process_message(from_number, body)
    reply = truncate_for_whatsapp(reply)
    reply = escape_xml(reply)

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Message><Body>{reply}</Body></Message>
</Response>"""
    return PlainTextResponse(twiml, media_type="application/xml")


# ──────────────────────────────────────────────────────
# WEBHOOK META
# ──────────────────────────────────────────────────────
VERIFY_TOKEN = os.getenv("META_VERIFY_TOKEN", "mi_token_secreto")

@app.get("/webhook/meta")
async def meta_verify(request: Request):
    params = request.query_params
    if params.get("hub.verify_token") == VERIFY_TOKEN:
        return PlainTextResponse(params.get("hub.challenge", ""))
    raise HTTPException(status_code=403, detail="Token inválido")


@app.post("/webhook/meta")
async def meta_webhook(request: Request):
    data = await request.json()
    try:
        entry       = data["entry"][0]["changes"][0]["value"]
        message     = entry["messages"][0]
        from_number = message["from"]
        body        = message["text"]["body"].strip()
        logger.info(f"[Meta] De: {from_number} | Msg: {body}")
        reply = await process_message(from_number, body)
        from meta_sender import send_whatsapp_message
        await send_whatsapp_message(from_number, reply)
    except (KeyError, IndexError):
        pass
    return {"status": "ok"}


# ──────────────────────────────────────────────────────
# LÓGICA CENTRAL
# ──────────────────────────────────────────────────────
async def process_message(user_id: str, message: str) -> str:
    session = sessions.get_or_create(user_id)

    response = await gemini.process(session, message, phone=user_id)

    action = response.get("action")
    reply  = response.get("reply", "¿En qué te puedo ayudar?")

    if action == "show_catalog":
        products     = odoo.get_products(response.get("category"))
        catalog_text = odoo.format_catalog(products)
        reply        = reply + "\n\n" + catalog_text

    elif action == "add_to_cart":
        for item in response.get("items", []):
            product = odoo.search_product(item["name"])
            if product:
                sessions.add_to_cart(user_id, product, item.get("qty", 1))
            else:
                reply = f"❌ No encontré '{item['name']}'. Escribe *catálogo* para ver las opciones disponibles."

    elif action == "show_cart":
        cart  = sessions.get_cart(user_id)
        reply = odoo.format_cart(cart)

    elif action == "request_address":
        # Gemini ya redactó el mensaje pidiendo la dirección
        pass

    elif action == "out_of_scope":
        # Gemini ya redactó la respuesta redirigiendo al cliente
        pass

    elif action == "save_customer":
        customer_info = response.get("customer_info", {})
        sessions.update_customer_info(user_id, customer_info)

        cart            = sessions.get_cart(user_id)
        updated_session = sessions.get_or_create(user_id)
        has_address     = updated_session.get("customer_info", {}).get("address")

        if has_address and cart:
            order_result = odoo.create_sale_order(
                user_id, cart, updated_session.get("customer_info", {})
            )
            if order_result:
                sessions.clear_cart(user_id)
                spei = await conekta.create_spei_order(
                    order_result, updated_session.get("customer_info", {})
                )
                spei_msg = conekta.format_spei_message(spei)
                reply = (
                    f"🎉 ¡Pedido *{order_result['order_name']}* creado y registrado en Odoo!\n\n"
                    f"{spei_msg}"
                )
            else:
                reply = reply + "\n\n❌ Hubo un problema al crear el pedido. Escribe *confirmar* para intentar de nuevo."

    elif action == "confirm_order":
        cart = sessions.get_cart(user_id)
        if not cart:
            reply = "🛒 Tu carrito está vacío. Escribe *catálogo* para ver productos."
        else:
            customer_info = session.get("customer_info", {})
            order_result  = odoo.create_sale_order(user_id, cart, customer_info)
            if order_result:
                sessions.clear_cart(user_id)
                spei    = await conekta.create_spei_order(order_result, customer_info)
                spei_msg = conekta.format_spei_message(spei)
                reply = (
                    f"🎉 ¡Pedido *{order_result['order_name']}* creado exitosamente!\n\n"
                    f"{spei_msg}"
                )
            else:
                reply = "❌ Error al crear el pedido. Intenta de nuevo o contacta a soporte."

    elif action == "cancel_order":
        sessions.clear_cart(user_id)

    elif action == "check_order":
        order_ref = response.get("order_ref")
        if order_ref:
            order = odoo.get_order_status(order_ref)
            reply = odoo.format_order_status(order) if order else f"No encontré el pedido #{order_ref}."

    sessions.add_message(user_id, "user", message)
    sessions.add_message(user_id, "assistant", reply)

    return reply


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)