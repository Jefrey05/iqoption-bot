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
from flask import Flask

# ================== FLASK PARA RAILWAY ==================
app = Flask(__name__)

@app.route("/")
def health():
    return "BOT IQ OPTION ACTIVO", 200

# ================== CONFIG ==================
logging.getLogger('iqoptionapi').setLevel(logging.CRITICAL)

EMAIL_IQ = os.getenv("EMAIL_IQ")
PASSWORD_IQ = os.getenv("PASSWORD_IQ")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
INVESTMENT = float(os.getenv("INVESTMENT", "1"))
ACCOUNT_TYPE = os.getenv("ACCOUNT_TYPE", "PRACTICE")
DURATION = int(os.getenv("DURATION", "1"))

SYMBOLS = [
    'EURUSD-OTC','GBPUSD-OTC','USDJPY-OTC','EURJPY-OTC'
]

TIMEFRAME = 60
CANDLE_COUNT = 200
SCAN_INTERVAL = 15

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

# ================== BOT ==================
class TradingBot:
    def __init__(self):
        self.IQ = None
        self.last_signals = {}

    def connect(self):
        while True:
            try:
                log("🔄 Conectando a IQ Option...")
                self.IQ = IQ_Option(EMAIL_IQ, PASSWORD_IQ)
                self.IQ.connect()
                time.sleep(3)

                if self.IQ.check_connect():
                    self.IQ.change_balance(ACCOUNT_TYPE)
                    log("✅ Conectado correctamente")
                    return
            except Exception as e:
                log(f"❌ Error conexión: {e}")
            time.sleep(20)

    def get_data(self, pair):
        try:
            candles = self.IQ.get_candles(pair, TIMEFRAME, CANDLE_COUNT, time.time())
            if not candles:
                return None

            df = pd.DataFrame(candles)
            df[['open','close','max','min']] = df[['open','close','max','min']].astype(float)
            df.rename(columns={'max':'high','min':'low'}, inplace=True)

            df['RSI'] = ta.momentum.RSIIndicator(df['close'], 14).rsi()
            df['EMA50'] = ta.trend.EMAIndicator(df['close'], 50).ema_indicator()
            bb = ta.volatility.BollingerBands(df['close'])
            df['BBH'] = bb.bollinger_hband()
            df['BBL'] = bb.bollinger_lband()

            return df.iloc[-1]
        except:
            return None

    def send_telegram(self, msg):
        if not TELEGRAM_TOKEN: return
        try:
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                data={"chat_id": TELEGRAM_CHAT_ID, "text": msg},
                timeout=5
            )
        except:
            pass

    def run(self):
        self.connect()
        self.send_telegram("🚀 Bot IQ Option activo en Railway")

        while True:
            try:
                if not self.IQ.check_connect():
                    log("⚠️ Reconectando...")
                    self.connect()

                for pair in SYMBOLS:
                    data = self.get_data(pair)
                    if data is None: continue

                    if data['RSI'] > 70 and data['close'] >= data['BBH']:
                        log(f"📉 PUT {pair}")
                        self.IQ.buy(INVESTMENT, pair, "put", DURATION)

                    if data['RSI'] < 30 and data['close'] <= data['BBL']:
                        log(f"📈 CALL {pair}")
                        self.IQ.buy(INVESTMENT, pair, "call", DURATION)

                time.sleep(SCAN_INTERVAL)
            except Exception as e:
                log(f"⚠️ Error loop: {e}")
                time.sleep(10)

# ================== START ==================
if __name__ == "__main__":
    bot = TradingBot()
    threading.Thread(target=bot.run, daemon=True).start()

    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
