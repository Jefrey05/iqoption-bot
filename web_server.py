"""
Servidor web simple para mantener activa la aplicación en Railway.
"""
from flask import Flask, jsonify
import os
import time
import logging
from datetime import datetime

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Estado del servidor
server_start_time = time.time()

@app.route('/')
def home():
    """Página principal"""
    return jsonify({
        "service": "IQ Option Trading Bot - Web Server",
        "status": "online",
        "timestamp": datetime.now().isoformat(),
        "uptime_seconds": int(time.time() - server_start_time),
        "endpoints": ["/ping", "/health", "/"]
    })

@app.route('/ping')
def ping():
    """Endpoint para keep-alive"""
    logger.info(f"📡 Ping recibido: {datetime.now().isoformat()}")
    return jsonify({
        "status": "pong",
        "timestamp": datetime.now().isoformat()
    })

@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat()
    })

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    logger.info(f"🚀 Servidor web iniciado en puerto {port}")
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)