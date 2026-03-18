"""
check_connections.py
====================
Corre este script ANTES de main.py para verificar que todo está conectado.
Uso: python check_connections.py
"""

import os
import sys
from dotenv import load_dotenv

load_dotenv()

VERDE  = "\033[92m✅"
ROJO   = "\033[91m❌"
RESET  = "\033[0m"
WARN   = "\033[93m⚠️"

def ok(msg):  print(f"{VERDE} {msg}{RESET}")
def err(msg): print(f"{ROJO} {msg}{RESET}")
def warn(msg): print(f"{WARN} {msg}{RESET}")

print("\n══════════════════════════════════════")
print("   DIAGNÓSTICO DEL BOT WhatsApp-Odoo  ")
print("══════════════════════════════════════\n")

errores = 0

# ── 1. Variables de entorno ───────────────────────────────────────────────
print("── 1. Variables de entorno ─────────────")
required_vars = {
    "GEMINI_API_KEY":    "Google Gemini",
    "ODOO_URL":          "Odoo URL",
    "ODOO_DB":           "Odoo Base de Datos",
    "ODOO_USER":         "Odoo Usuario",
    "ODOO_PASSWORD":     "Odoo Contraseña",
}
for var, label in required_vars.items():
    val = os.getenv(var, "")
    if val and not val.startswith("PEGA_") and not val.startswith("tu_"):
        ok(f"{label}: configurado")
    else:
        err(f"{label} ({var}): FALTA o tiene valor de ejemplo")
        errores += 1

# WhatsApp — al menos uno debe estar configurado
meta_ok   = bool(os.getenv("META_ACCESS_TOKEN") and not os.getenv("META_ACCESS_TOKEN","").startswith("EAAx"))
twilio_ok = bool(os.getenv("TWILIO_ACCOUNT_SID"))
if meta_ok:
    ok("WhatsApp: Meta Cloud API configurada")
elif twilio_ok:
    ok("WhatsApp: Twilio configurado")
else:
    warn("WhatsApp: ni Meta ni Twilio configurados (necesario para recibir mensajes)")

print()

# ── 2. Dependencias Python ───────────────────────────────────────────────
print("── 2. Dependencias Python ──────────────")
packages = ["fastapi", "uvicorn", "google.generativeai", "httpx", "dotenv", "multipart"]
for pkg in packages:
    try:
        __import__(pkg.replace("-", "_"))
        ok(f"{pkg}")
    except ImportError:
        err(f"{pkg} — ejecuta: pip install -r requirements.txt")
        errores += 1
print()

# ── 3. Conexión con Odoo ─────────────────────────────────────────────────
print("── 3. Conexión con Odoo ────────────────")
odoo_url = os.getenv("ODOO_URL", "")
odoo_db  = os.getenv("ODOO_DB", "")
odoo_user = os.getenv("ODOO_USER", "")
odoo_pass = os.getenv("ODOO_PASSWORD", "")

if not all([odoo_url, odoo_db, odoo_user, odoo_pass]):
    warn("Saltando prueba de Odoo — credenciales incompletas en .env")
else:
    try:
        import xmlrpc.client
        common = xmlrpc.client.ServerProxy(f"{odoo_url}/xmlrpc/2/common")
        version = common.version()
        ok(f"Odoo alcanzable: versión {version.get('server_version', '?')}")

        uid = common.authenticate(odoo_db, odoo_user, odoo_pass, {})
        if uid:
            ok(f"Autenticación exitosa: UID={uid}")

            # Probar lectura de productos
            models = xmlrpc.client.ServerProxy(f"{odoo_url}/xmlrpc/2/object")
            products = models.execute_kw(
                odoo_db, uid, odoo_pass,
                "product.template", "search_read",
                [[("sale_ok", "=", True), ("active", "=", True)]],
                {"fields": ["name", "list_price"], "limit": 3}
            )
            ok(f"Lectura de productos: {len(products)} encontrados en catálogo")
            for p in products:
                print(f"   → {p['name']} — ${p['list_price']:.2f}")
        else:
            err("Autenticación fallida — verifica ODOO_USER y ODOO_PASSWORD")
            errores += 1

    except ConnectionRefusedError:
        err(f"No se puede conectar a {odoo_url} — verifica ODOO_URL")
        errores += 1
    except Exception as e:
        err(f"Error Odoo: {e}")
        errores += 1
print()

# ── 4. Conexión con Gemini ───────────────────────────────────────────────
print("── 4. Conexión con Gemini ──────────────")
gemini_key = os.getenv("GEMINI_API_KEY", "")
if not gemini_key or gemini_key.startswith("AIzaSy_PEGA"):
    warn("Saltando prueba de Gemini — GEMINI_API_KEY no configurada")
else:
    try:
        import google.generativeai as genai
        genai.configure(api_key=gemini_key)
        model = genai.GenerativeModel("gemini-2.5-flash")
        response = model.generate_content('Responde solo "ok"')
        ok(f"Gemini responde: '{response.text.strip()[:20]}'")
    except Exception as e:
        err(f"Error Gemini: {e}")
        errores += 1
print()

# ── Resumen ───────────────────────────────────────────────────────────────
print("══════════════════════════════════════")
if errores == 0:
    print(f"{VERDE} Todo listo. Corre: python main.py{RESET}")
else:
    print(f"{ROJO} {errores} error(s) encontrado(s). Revisa tu .env{RESET}")
    print(f"\n{'VERDE'} Siguiente paso: abre .env y completa las credenciales que faltan.")
print("══════════════════════════════════════\n")