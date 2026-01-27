from iqoptionapi.stable_api import IQ_Option
import time
import pandas as pd
import ta
import requests
from datetime import datetime
import os
import threading

# ==============================================
# CONFIGURACIÓN (RECOGE VALORES DE RAILWAY)
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
        self.connected = False
        self.last_signals = {}

    def connect_iqoption(self):
        try:
            self.IQ = IQ_Option(EMAIL_IQ, PASSWORD_IQ)
            self.connected = self.IQ.connect()
            if self.connected and self.IQ.check_connect():
                print(f"✅ Conexión exitosa a IQ Option ({ACCOUNT_TYPE})")
                self.IQ.change_balance(ACCOUNT_TYPE)
                return True
            return False
        except Exception as e:
            print(f"❌ Error al conectar: {str(e)}")
            return False

    def get_candles(self, pair):
        try:
            candles = self.IQ.get_candles(pair, TIMEFRAME, CANDLE_COUNT, time.time())
            return candles if candles and len(candles) == CANDLE_COUNT else None
        except: return None

    def analyze_pair(self, pair):
        candles = self.get_candles(pair)
        if not candles: return None
        df = pd.DataFrame(candles)
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
        consecutive_green = count_consecutive(is_green)
        consecutive_red = count_consecutive(is_red)
        last = df.iloc[-1]

        return {
            'pair': pair, 'price': last['close'], 'rsi': last['RSI'],
            'bb_high': last['BB_high'], 'bb_low': last['BB_low'],
            'ema50': last['EMA50'], 'body': last['body'],
            'upper_wick': last['upper_wick'], 'lower_wick': last['lower_wick'],
            'avg_body': last['avg_body_10'], 
            'consecutive_green': consecutive_green, 'consecutive_red': consecutive_red
        }

    def send_telegram_alert(self, message):
        try:
            msg_telegram = message.replace("%0A", "\n")
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            payload = {'chat_id': TELEGRAM_CHAT_ID, 'text': msg_telegram, 'parse_mode': 'Markdown'}
            requests.post(url, data=payload)
        except: pass

    def send_whatsapp_alert(self, message):
        try:
            url = f"https://api.callmebot.com/whatsapp.php?phone={WHATSAPP_PHONE}&apikey={WHATSAPP_API_KEY}&text={message}"
            requests.get(url)
        except: pass

    def execute_trade(self, pair, action):
        print(f"🚀 Intentando operacion {action} en {pair}...")
        balance_before = self.IQ.get_balance()
        check, id = self.IQ.buy(INVESTMENT, pair, action.lower(), DURATION)
        if check and id: return {"type": "BINARY", "id": id, "balance_before": balance_before}
        check, id = self.IQ.buy_digital_spot(pair, INVESTMENT, action.lower(), DURATION)
        if check: return {"type": "DIGITAL", "id": id, "balance_before": balance_before}
        return None

    def check_trade_result_safe(self, trade_info, pair, action):
        time.sleep((DURATION * 60) + 30)
        final_balance = self.IQ.get_balance()
        profit = final_balance - trade_info['balance_before']
        result_text = "💰 WIN" if profit > 0 else "📉 LOSS" if profit < 0 else "🤝 EMPATE"
        msg = (f"🏁 *RESULTADO DE OPERACIÓN* 🏁\n\n*Par:* {pair}\n*Dirección:* {action.upper()}\n*Resultado:* {result_text}\n*Profit:* ${profit:.2f}")
        self.send_telegram_alert(msg)

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
        if not self.connect_iqoption(): return
        print("\n🔎 Iniciando escaneo automático...")
        self.send_telegram_alert("🚀 *Bot de Trading Iniciado*")
        
        while True:
            try:
                if not self.IQ.check_connect():
                    print("⚠️ Conexión perdida. Intentando reconectar...")
                    if not self.connect_iqoption():
                        time.sleep(10)
                        continue

                print(f"🔎 Escaneando {len(SYMBOLS)} pares... ({datetime.now().strftime('%H:%M:%S')})")
                for pair in SYMBOLS:
                    try:
                        analysis = self.analyze_pair(pair)
                        if not analysis: continue
                        signal = self.check_signal(analysis)
                        if signal:
                            trade_info = self.execute_trade(pair, signal)
                            if trade_info:
                                msg = (f"🚨 *OPERACIÓN ABIERTA* 🚨\n\n*Par:* {pair}\n*Dirección:* {signal.upper()}")
                                self.send_telegram_alert(msg)
                                threading.Thread(target=self.check_trade_result_safe, args=(trade_info, pair, signal), daemon=True).start()
                    except: continue
                time.sleep(SCAN_INTERVAL)
            except Exception as e:
                print(f"Error general: {str(e)}")
                time.sleep(5)

if __name__ == "__main__":
    bot = TradingBot()
    bot.run()
