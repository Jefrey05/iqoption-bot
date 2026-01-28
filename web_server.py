"""
Servidor web mejorado para nube
"""
from flask import Flask, jsonify
import os
import time
import logging

app = Flask(__name__)
start_time = time.time()

@app.route('/')
def home():
    return jsonify({
        "status": "online",
        "service": "IQ Option Cloud Bot",
        "uptime": int(time.time() - start_time),
        "timestamp": time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime()),
        "environment": "cloud" if os.environ.get('RAILWAY_ENVIRONMENT') else "local"
    })

@app.route('/ping')
def ping():
    return jsonify({"status": "pong", "timestamp": time.time()})

@app.route('/debug')
def debug():
    """Endpoint de debug para ver variables"""
    debug_info = {
        "cloud": os.environ.get('RAILWAY_ENVIRONMENT') is not None,
        "port": os.environ.get('PORT'),
        "email_set": bool(os.environ.get('EMAIL_IQ')),
        "telegram_set": bool(os.environ.get('TELEGRAM_TOKEN')),
        "variables": {k: "***" if "PASS" in k or "KEY" in k else "Set" 
                     for k in os.environ if 'IQ' in k or 'TELEGRAM' in k or 'WHATSAPP' in k}
    }
    return jsonify(debug_info)

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    logger.info(f"🌐 Servidor web cloud en puerto {port}")
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
