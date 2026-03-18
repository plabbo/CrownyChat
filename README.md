

https://github.com/user-attachments/assets/416c659f-b341-46f7-9bf8-ed6b3c13bb95

# 🤖 WhatsApp + Gemini AI + Odoo — Bot de Pedidos

Recibe pedidos por WhatsApp, Gemini los entiende y los registra automáticamente en Odoo.

---

## ⚡ Inicio rápido (3 pasos)

### 1. Instalar dependencias
```bash
pip install -r requirements.txt
```

### 2. Configurar APIs
```bash
# Renombra el archivo de ejemplo
cp .env.example .env

# Abre .env y pega tus credenciales:
#   → GEMINI_API_KEY   (console.cloud.google.com/apis → Gemini API)
#   → ODOO_URL / ODOO_DB / ODOO_USER / ODOO_PASSWORD
#   → META o TWILIO según cuál uses para WhatsApp
```

### 3. Correr el servidor
```bash
python main.py
# ✅ Servidor corriendo en http://localhost:8000
```

---

## 📲 Conectar WhatsApp

### Opción A — Twilio (para pruebas, más fácil)
1. Crea cuenta en [twilio.com](https://twilio.com)
2. Descarga [ngrok](https://ngrok.com) y corre: `ngrok http 8000`
3. En Twilio → WhatsApp Sandbox → Webhook URL: `https://XXXX.ngrok.io/webhook/twilio`

### Opción B — Meta Cloud API (para producción)
1. Ve a [developers.facebook.com](https://developers.facebook.com) → Crear App → WhatsApp
2. En Webhooks pon: `https://tudominio.com/webhook/meta`
3. Token de verificación: el valor de `META_VERIFY_TOKEN` en tu `.env`

---

## 🗂️ Archivos del proyecto

```
📁 bot/
├── main.py            ← Servidor principal (punto de entrada)
├── gemini_handler.py  ← Lógica de IA con Google Gemini
├── odoo_handler.py    ← Conexión con Odoo (XML-RPC)
├── session_manager.py ← Carritos y sesiones por usuario
├── meta_sender.py     ← Envío de mensajes via Meta API
├── .env.example       ← Plantilla de configuración  ← EMPIEZA AQUÍ
└── requirements.txt   ← Dependencias Python
```

---

## 💬 Ejemplo de conversación

```
Usuario  →  Hola
Bot      →  ¡Hola! Soy el asistente de pedidos 🛍️ ¿Cuál es tu nombre?

Usuario  →  Soy Carlos
Bot      →  ¡Hola Carlos! ¿Qué deseas hacer?

Usuario  →  Quiero ver el catálogo
Bot      →  📦 CATÁLOGO DE PRODUCTOS
             1. Laptop Dell - $15,000.00
             2. Mouse Inalámbrico - $350.00
             ...

Usuario  →  Quiero 1 Mouse Inalámbrico
Bot      →  ✅ Agregado: 1x Mouse Inalámbrico

Usuario  →  Confirmar pedido
Bot      →  🎉 ¡Pedido #1042 creado en Odoo!
             Te contactaremos para la entrega.
```

---

## 🔑 ¿Dónde obtengo las APIs?

| API | URL |
|-----|-----|
| Gemini API Key | https://aistudio.google.com/app/apikey |
| Odoo (nube) | Ajustes → Técnico → API Keys |
| Meta WhatsApp | https://developers.facebook.com |
| Twilio | https://console.twilio.com |
