"""
server.py — produzione-ready
Usa: gunicorn -w 4 -b 0.0.0.0:5000 server:app
"""
import os, logging
from flask import Flask, request, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_talisman import Talisman
import resend
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# ─── CORS ────────────────────────────────────────────────────────────────────
ALLOWED_ORIGIN = os.getenv("ALLOWED_ORIGIN", "https://portfolio-vert-mu-fbqkanoz77.vercel.app")

@app.after_request
def add_cors_headers(response):
    origin = request.headers.get("Origin", "")
    if origin == ALLOWED_ORIGIN:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response

# ─── Rate limiting ────────────────────────────────────────────────────────────
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
)

# ─── Security headers ─────────────────────────────────────────────────────────
csp = {
    "default-src": ["'self'"],
    "script-src":  ["'self'", "cdnjs.cloudflare.com", "cdn.jsdelivr.net"],
    "style-src":   ["'self'", "'unsafe-inline'", "fonts.googleapis.com"],
    "font-src":    ["'self'", "fonts.gstatic.com", "api.fontshare.com"],
    "img-src":     ["'self'", "data:"],
    "connect-src": ["'self'"],
    "frame-ancestors": ["'none'"],
}
Talisman(
    app,
    content_security_policy=csp,
    force_https=False,
    strict_transport_security=False,
    referrer_policy="strict-origin-when-cross-origin",
    frame_options="DENY",
)

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

# ─── Helpers ──────────────────────────────────────────────────────────────────
def send_email(name: str, email: str, phone: str, message: str) -> None:
    resend.api_key = os.getenv("RESEND_API_KEY")
    to_email = os.getenv("TO_EMAIL")

    params: resend.Emails.SendParams = {
        "from": "Portfolio Contact <onboarding@resend.dev>",
        "to": [to_email],
        "subject": f"Nuovo contatto da {name}",
        "text": f"Nome:     {name}\nEmail:    {email}\nTelefono: {phone or 'non fornito'}\n\nMessaggio:\n{message}",
    }
    resend.Emails.send(params)

# ─── Routes ───────────────────────────────────────────────────────────────────
@app.route("/contact", methods=["POST", "OPTIONS"])
@limiter.limit("5 per minute; 200 per day")
def contact():
    if request.method == "OPTIONS":
        return jsonify({}), 200

    data    = request.get_json(silent=True) or {}
    name    = str(data.get("name",    "")).strip()[:120]
    email   = str(data.get("email",   "")).strip()[:254]
    phone   = str(data.get("phone",   "")).strip()[:30]
    message = str(data.get("message", "")).strip()[:2000]
    privacy = data.get("privacy_accepted", False)

    if not all([name, email, message]):
        return jsonify({"ok": False, "error": "Campi obbligatori mancanti"}), 400
    if not privacy:
        return jsonify({"ok": False, "error": "Consenso privacy obbligatorio"}), 400
    if "@" not in email or "." not in email.split("@")[-1]:
        return jsonify({"ok": False, "error": "Email non valida"}), 400

    try:
        send_email(name, email, phone, message)
        logger.info("Contatto ricevuto da %s <%s>", name, email)
        return jsonify({"ok": True, "message": "Messaggio inviato con successo"})
    except Exception as exc:
        logger.exception("Errore invio email: %s", exc)
        return jsonify({"ok": False, "error": "Errore interno, riprova più tardi"}), 500

@app.route("/health")
def health():
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    app.run(debug=False, host="127.0.0.1", port=5000)
