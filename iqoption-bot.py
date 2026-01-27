from iqoptionapi.stable_api import IQ_Option
import time
import pandas as pd
import ta
import requests
from datetime import datetime
import os
import threading
import logging
import sys

# ==============================================
# LIMPIEZA TOTAL DE LOGS (Elimina el ruido rojo)
# ==============================================
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)
logging.basicConfig(level=logging.CRITICAL)
logging.getLogger('iqoptionapi').setLevel(logging.CRITICAL)

# ==============================================
# CONFIGURACIÓN
# ==============================================
EMAIL_IQ = os.getenv("EMAIL_IQ")
PASSWORD_IQ = os.getenv("PASSWORD_IQ")
WHATSAPP_PHONE = os.getenv("WHATSAPP_PHONE")
WHATSAPP_API_KEY = os.getenv("WHATSAPP_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
INVESTMENT = float(os.getenv("INVESTMENT", "1.0"))
ACCOUNT_TYPE = os.getenv("ACCOUNT_TYPE", "PRACTICE")
DURATION = int(os.getenv("DURATION", "1"))

SYMBOLS = [
    'EURJPY-OTC', 'EURUSD-OTC', 'AUDCAD-OTC', 
    'GBPUSD-OTC', 'EURGBP-OTC', 'GBPJPY-OTC', 'USDCHF-OTC', 
    'USDHKD-OTC', 'USDINR-OTC', 'USDSGD-OTC', 'USDZAR-OTC',
]

TIMEFRAME = 60
CANDLE_COUNT = 200
SCAN_INTERVAL = 60

def log_print(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

class TradingBot:
    def __init__(self):
        self.IQ = None
        self.last_signals = {}
        self.error_count = 0

    def connect_iqoption(self):
        """Conexión limpia"""
        try:
            log_print(f"🔄 Intentando conexión ({ACCOUNT_TYPE})...")
            self.IQ = IQ_Option(EMAIL_IQ, PASSWORD_IQ)
            connected = self.IQ.connect()
            
            if connected and self.IQ.check_connect():
                log_print(f"✅ CONECTADO.")
                self.IQ.change_balance(ACCOUNT_TYPE)
                self.error_count = 0
                return True
            
            return False
        except:
            return False

    def get_candles(self, pair):
        try:
            # Petición directa a la API
            candles = self.IQ.get_candles(pair, TIMEFRAME, CANDLE_COUNT, time.time())
            if isinstance(candles, list) and len(candles) == CANDLE_COUNT:
                self.error_count = 0
                return candles
        except:
            pass
        
        self.error_count += 1
        return None

    def analyze_and_trade(self, pair):
        candles = self.get_candles(pair)
        if not candles: return

        df = pd.DataFrame(candles)
        for col in ['open', 'close', 'max', 'min']: df[col] = df[col].astype(float)
        df.rename(columns={'max': 'high', 'min': 'low'}, inplace=True)

        # Indicadores básicos
        df['RSI'] = ta.momentum.RSIIndicator(df['close'], window=14).rsi()
        bb = ta.volatility.BollingerBands(df['close'], window=14, window_dev=2)
        df['BB_high'] = bb.bollinger_hband()
        df['BB_low'] = bb.bollinger_lband()
        df['EMA50'] = ta.trend.EMAIndicator(df['close'], window=50).ema_indicator()
        df['body'] = abs(df['close'] - df['open'])
        df['upper_wick'] = df['high'] - df[['open', 'close']].max(axis=1)
        df['lower_wick'] = df[['open', 'close']].min(axis=1) - df['low']
        df['avg_body_10'] = df['body'].rolling(window=10).mean()

        def count_consecutive(series):
            count = 0
            for val in reversed(series.values):
                if val: count += 1
                else: break
            return count

        last = df.iloc[-1]
        signal = None

        if last['close'] > last['EMA50']:
            if count_consecutive(df['close'] > df['open']) >= 4 and last['RSI'] > 70 and last['close'] >= last['BB_high']:
                if last['upper_wick'] > (last['body'] * 0.35):
                    signal = "PUT"
        elif last['close'] < last['EMA50']:
            if count_consecutive(df['close'] < df['open']) >= 4 and last['RSI'] < 30 and last['close'] <= last['BB_low']:
                if last['lower_wick'] > (last['body'] * 0.35):
                    signal = "CALL"

        if signal:
            signal_key = f"{pair}_{signal}"
            if signal_key not in self.last_signals or (time.time() - self.last_signals[signal_key]) > 600:
                self.last_signals[signal_key] = time.time()
                log_print(f"� SEÑAL {signal} en {pair}. Operando...")
                self.IQ.buy(INVESTMENT, pair, signal.lower(), DURATION)
                self.send_telegram(f"🚨 *ALERTA:* {signal} en {pair}\nInversión: ${INVESTMENT}")

    def send_telegram(self, msg):
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            requests.post(url, data={'chat_id': TELEGRAM_CHAT_ID, 'text': msg, 'parse_mode': 'Markdown'}, timeout=5)
        except: pass

    def run(self):
        if not self.connect_iqoption():
            log_print("❌ Error de inicio. Railway reiniciará en 30s...")
            time.sleep(30)
            sys.exit(1)

        self.send_telegram("🚀 *Bot de Trading Iniciado en Railway*")
        
        while True:
            try:
                if not self.IQ.check_connect():
                    log_print("⚠️ Conexión perdida. Reiniciando proceso...")
                    sys.exit(1)

                if self.error_count > 5:
                    log_print("⚠️ Demasiados errores de datos. Reiniciando proceso...")
                    sys.exit(1)

                log_print(f"🔎 Escaneando {len(SYMBOLS)} pares...")
                for pair in SYMBOLS:
                    self.analyze_and_trade(pair)
                
                time.sleep(SCAN_INTERVAL)
            except Exception as e:
                log_print(f"💥 Error inesperado: {str(e)}")
                sys.exit(1)

if __name__ == "__main__":
    bot = TradingBot()
    bot.run()

