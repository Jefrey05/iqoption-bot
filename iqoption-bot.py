from iqoptionapi.stable_api import IQ_Option
import time
import pandas as pd
import ta
import requests
from datetime import datetime
import os
import threading
import logging

# Silenciar logs ruidosos de la librería
logging.getLogger('iqoptionapi').setLevel(logging.CRITICAL)

# ==============================================
# CONFIGURACIÓN (RAILWAY ENV)
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
SCAN_INTERVAL = 10

class TradingBot:
    def __init__(self):
        self.IQ = None
        self.last_signals = {}

    def connect_iqoption(self):
        """Conexión con validación forzada"""
        try:
            print(f"🔄 Conectando a IQ Option ({ACCOUNT_TYPE})...", flush=True)
            if self.IQ:
                try: self.IQ.logout()
                except: pass
            
            self.IQ = IQ_Option(EMAIL_IQ, PASSWORD_IQ)
            connected = self.IQ.connect()
            
            if connected:
                time.sleep(5)
                if self.IQ.check_connect():
                    print(f"✅ Conexión validada con éxito.", flush=True)
                    self.IQ.change_balance(ACCOUNT_TYPE)
                    return True
            
            print("❌ Error de conexión. Verificando credenciales...", flush=True)
            return False
        except Exception as e:
            print(f"❌ Error crítico: {str(e)}", flush=True)
            return False

    def get_candles_safe(self, pair):
        try:
            candles = self.IQ.get_candles(pair, TIMEFRAME, CANDLE_COUNT, time.time())
            if isinstance(candles, list) and len(candles) == CANDLE_COUNT:
                return candles
        except Exception as e:
            if "reconnect" in str(e).lower():
                return "FORCE_RECONNECT"
        return None

    def analyze_pair(self, pair):
        data = self.get_candles_safe(pair)
        if data == "FORCE_RECONNECT": return "RECONNECT"
        if not data: return None

        df = pd.DataFrame(data)
        for col in ['open', 'close', 'max', 'min']: df[col] = df[col].astype(float)
        df.rename(columns={'max': 'high', 'min': 'low'}, inplace=True)

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

        is_green = df['close'] > df['open']
        is_red = df['close'] < df['open']
        last = df.iloc[-1]

        return {
            'pair': pair, 'price': last['close'], 'rsi': last['RSI'],
            'bb_high': last['BB_high'], 'bb_low': last['BB_low'],
            'ema50': last['EMA50'], 'body': last['body'],
            'upper_wick': last['upper_wick'], 'lower_wick': last['lower_wick'],
            'avg_body': last['avg_body_10'], 
            'consecutive_green': count_consecutive(is_green),
            'consecutive_red': count_consecutive(is_red)
        }

    def send_telegram_alert(self, message):
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            payload = {'chat_id': TELEGRAM_CHAT_ID, 'text': message, 'parse_mode': 'Markdown'}
            requests.post(url, data=payload, timeout=10)
        except: pass

    def execute_trade(self, pair, action):
        try:
            print(f"🚀 Operando {action} en {pair}...", flush=True)
            self.IQ.buy(INVESTMENT, pair, action.lower(), DURATION)
        except: pass

    def check_signal(self, data):
        if not data: return None
        signal = None
        price, rsi, ema = data['price'], data['rsi'], data['ema50']
        bb_high, bb_low = data['bb_high'], data['bb_low']
        body, avg_body = data['body'], data['avg_body']

        if price > ema:
            if data['consecutive_green'] >= 4 and rsi > 70 and price >= bb_high:
                if data['upper_wick'] > (body * 0.35) and avg_body <= body <= (avg_body * 2):
                    signal = "PUT"
        elif price < ema:
            if data['consecutive_red'] >= 4 and rsi < 30 and price <= bb_low:
                if data['lower_wick'] > (body * 0.35) and avg_body <= body <= (avg_body * 2):
                    signal = "CALL"

        if not signal: return None
        signal_key = f"{data['pair']}_{signal}"
        if signal_key in self.last_signals and (time.time() - self.last_signals[signal_key]) < 600: return None
        self.last_signals[signal_key] = time.time()
        return signal

    def run(self):
        while not self.connect_iqoption():
            print("⏳ Reintentando conexión inicial en 30s...", flush=True)
            time.sleep(30)

        self.send_telegram_alert("🚀 *Bot de Trading Online en Railway*")
        
        while True:
            try:
                if not self.IQ.check_connect():
                    print("⚠️ Reconectando...", flush=True)
                    self.connect_iqoption()
                    continue

                print(f"🔎 Escaneando... ({datetime.now().strftime('%H:%M:%S')})", flush=True)
                for pair in SYMBOLS:
                    res = self.analyze_pair(pair)
                    if res == "RECONNECT":
                        self.connect_iqoption()
                        break
                    if not res: continue

                    signal = self.check_signal(res)
                    if signal:
                        self.execute_trade(pair, signal)
                        self.send_telegram_alert(f"🚨 *ALERTA:* {signal} en {pair}")
                
                time.sleep(SCAN_INTERVAL)
            except Exception as e:
                print(f"⚠️ Error: {str(e)}", flush=True)
                time.sleep(10)

if __name__ == "__main__":
    bot = TradingBot()
    bot.run()
