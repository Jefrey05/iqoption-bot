from iqoptionapi.stable_api import IQ_Option
import time
import pandas as pd
import ta
import requests
from datetime import datetime
import os
import threading

# ==============================================
# CONFIGURACIÓN (EDITA ESTO)
# ==============================================
EMAIL_IQ = "jefrey4643@gmail.com"       # Tu email en IQ Option
PASSWORD_IQ = "elcotizado05"            # Tu contraseña en IQ Option
WHATSAPP_PHONE = "18293154991"          # Tu número con código de país (ej: +51...)
WHATSAPP_API_KEY = "7312545"            # Tu API Key de CallMeBot

# Configuración de Telegram
TELEGRAM_TOKEN = "8331514893:AAFspPw5NHQ8A-3L9x8n5eYJkVPDbiX1UpA"    # Token de tu bot de Telegram
TELEGRAM_CHAT_ID = "1040018534"         # Tu Chat ID de Telegram

# Configuración de Trading
INVESTMENT = 1.0          # Cantidad a invertir por operación
ACCOUNT_TYPE = "PRACTICE" # "PRACTICE" o "REAL"
DURATION = 1              # Duración en minutos (1 para M1)

# Pares a analizar


SYMBOLS = [
    'EURJPY-OTC', 'EURUSD-OTC', 'AUDCAD-OTC', 
    'GBPUSD-OTC', 'EURGBP-OTC', 'GBPJPY-OTC', 'USDCHF-OTC', 


    
]

TIMEFRAME = 60  # Velas de 1 minuto
CANDLE_COUNT = 200
SCAN_INTERVAL = 60

# ==============================================
# CLASE PRINCIPAL DEL BOT
# ==============================================
class TradingBot:
    def __init__(self):
        self.IQ = None
        self.connected = False
        self.last_signals = {}

    def connect_iqoption(self):
        """Conectar a IQ Option"""
        try:
            self.IQ = IQ_Option(EMAIL_IQ, PASSWORD_IQ)
            self.connected = self.IQ.connect()
            
            if self.connected and self.IQ.check_connect():
                print(f"✅ Conexión exitosa a IQ Option ({ACCOUNT_TYPE})")
                self.IQ.change_balance(ACCOUNT_TYPE)
                return True
            else:
                print("❌ Error de conexión")
                return False
        except Exception as e:
            print(f"❌ Error al conectar: {str(e)}")
            return False

    def get_candles(self, pair):
        """Obtener velas históricas"""
        try:
            candles = self.IQ.get_candles(pair, TIMEFRAME, CANDLE_COUNT, time.time())
            return candles if candles and len(candles) == CANDLE_COUNT else None
        except:
            return None

    def analyze_pair(self, pair):
        """Analizar un par con RSI, Bollinger Bands, EMA 50 y Price Action"""
        candles = self.get_candles(pair)
        if not candles:
            return None

        df = pd.DataFrame(candles)
        for col in ['open', 'close', 'max', 'min']:
            df[col] = df[col].astype(float)
        
        df.rename(columns={'max': 'high', 'min': 'low'}, inplace=True)

        # Indicadores
        df['RSI'] = ta.momentum.RSIIndicator(df['close'], window=14).rsi()
        bb = ta.volatility.BollingerBands(df['close'], window=14, window_dev=2)
        df['BB_high'] = bb.bollinger_hband()
        df['BB_low'] = bb.bollinger_lband()
        df['EMA50'] = ta.trend.EMAIndicator(df['close'], window=50).ema_indicator()

        # Análisis de velas
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
            'consecutive_green': consecutive_green,
            'consecutive_red': consecutive_red
        }

    def send_telegram_alert(self, message):
        """Enviar mensaje a Telegram"""
        try:
            msg_telegram = message.replace("%0A", "\n")
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            payload = {'chat_id': TELEGRAM_CHAT_ID, 'text': msg_telegram, 'parse_mode': 'Markdown'}
            requests.post(url, data=payload)
            print("📤 Alerta enviada a Telegram")
        except Exception as e:
            print(f"❌ Error Telegram: {str(e)}")

    def send_whatsapp_alert(self, message):
        """Enviar mensaje a WhatsApp"""
        try:
            url = f"https://api.callmebot.com/whatsapp.php?phone={WHATSAPP_PHONE}&apikey={WHATSAPP_API_KEY}&text={message}"
            requests.get(url)
            print("📤 Alerta enviada a WhatsApp")
        except: pass

    def execute_trade(self, pair, action):
        """Ejecutar operación priorizando Binaria sobre Digital"""
        print(f"🚀 Intentando operacion {action} en {pair}...")
        
        # Balance ANTES de operar
        balance_before = self.IQ.get_balance()

        # 1. Intentar en Binaria primero
        check, id = self.IQ.buy(INVESTMENT, pair, action.lower(), DURATION)
        if check and id:
            print(f"✅ Operación BINARIA abierta ID: {id}")
            return {"type": "BINARY", "id": id, "balance_before": balance_before}
        
        # 2. Si falla Binaria, intentar en Digital
        print(f"   ⚠️ Binaria no disponible, intentando Digital...")
        check, id = self.IQ.buy_digital_spot(pair, INVESTMENT, action.lower(), DURATION)
        if check:
            print(f"✅ Operación DIGITAL abierta ID: {id}")
            return {"type": "DIGITAL", "id": id, "balance_before": balance_before}
            
        print(f"❌ Error: Activo {pair} no disponible en este momento.")
        return None

    def check_trade_result_safe(self, trade_info, pair, action):
        """Vigila el resultado mediante balance y reporta detalles completos"""
        print(f"⏳ Vigilando {pair} ({trade_info['type']}) en segundo plano...")
        
        balance_before = trade_info['balance_before']
        
        # Esperar duración + buffer (Aumentado a 30s)
        time.sleep((DURATION * 60) + 30)
        
        final_balance = self.IQ.get_balance()
        profit = final_balance - balance_before
        
        if final_balance > balance_before:
            result_text = "💰 WIN"
        elif final_balance < balance_before:
            result_text = "📉 LOSS"
        else:
            result_text = "🤝 EMPATE"

        msg = (
            f"🏁 *RESULTADO DE OPERACIÓN* 🏁\n\n"
            f"*Par:* {pair}\n"
            f"*Dirección:* {action.upper()}\n"
            f"*Tipo:* {trade_info['type']}\n"
            f"*Resultado:* {result_text}\n"
            f"*Profit:* ${profit:.2f}\n"
            f"*Balance actual:* ${final_balance:.2f}"
        )
        self.send_telegram_alert(msg)
        print(f"🏁 {result_text} en {pair} (${profit:.2f}) | Balance: ${final_balance:.2f}")

    def check_signal(self, data):
        """Lógica de Estrategia Agotamiento"""
        if not data: return None
        
        signal = None
        price, rsi, ema = data['price'], data['rsi'], data['ema50']
        bb_high, bb_low = data['bb_high'], data['bb_low']
        body, avg_body = data['body'], data['avg_body']

        # Tendencia ALCISTA -> Buscar PUT
        if price > ema:
            if data['consecutive_green'] >= 4 and rsi > 70 and price >= bb_high:
                if data['upper_wick'] > (body * 0.35) and avg_body <= body <= (avg_body * 2):
                    signal = "PUT"

        # Tendencia BAJISTA -> Buscar CALL
        elif price < ema:
            if data['consecutive_red'] >= 4 and rsi < 30 and price <= bb_low:
                if data['lower_wick'] > (body * 0.35) and avg_body <= body <= (avg_body * 2):
                    signal = "CALL"

        if not signal: return None

        signal_key = f"{data['pair']}_{signal}"
        if signal_key in self.last_signals and (time.time() - self.last_signals[signal_key]) < 600:
            return None
        
        self.last_signals[signal_key] = time.time()
        return signal

    def run(self):
        if not self.connect_iqoption(): return

        print("\n🔎 Iniciando escaneo automático...")
        self.send_telegram_alert("🚀 *Bot de Trading Iniciado*\n\nEscaneando mercados...")
        
        try:
            while True:
                print(f"🔎 Escaneando {len(SYMBOLS)} pares... ({datetime.now().strftime('%H:%M:%S')})")
                for pair in SYMBOLS:
                    try:
                        analysis = self.analyze_pair(pair)
                        if not analysis:
                            print(f"   ⚠️ {pair}: Sin datos")
                            continue

                        signal = self.check_signal(analysis)
                        if signal:
                            # 1. Alerta inicial inmediata con DIRECCIÓN
                            trade_info = self.execute_trade(pair, signal)
                            
                            if trade_info:
                                msg_opened = (
                                    f"🚨 *NUEVA OPERACIÓN ABIERTA* 🚨\n\n"
                                    f"*Par:* {pair}\n"
                                    f"*Dirección:* {signal.upper()}\n"
                                    f"*Precio:* {analysis['price']:.5f}"
                                )
                                self.send_telegram_alert(msg_opened)
                                self.send_whatsapp_alert(msg_opened.replace("\n", "%0A"))

                                # 2. Monitoreo en segundo plano
                                threading.Thread(target=self.check_trade_result_safe, args=(trade_info, pair, signal), daemon=True).start()
                                print(f"   🔔 SEÑAL {signal} DETECTADA en {pair} - Operando...")
                            else:
                                msg_closed = f"⚠️ *SEÑAL NO OPERADA*\n*Par:* {pair}\n*Motivo:* Mercado cerrado."
                                self.send_telegram_alert(msg_closed)
                                print(f"   ❌ Operación cancelada en {pair} (Mercado cerrado)")
                        else:
                            # Opcional: ver progreso por par
                            # print(f"   ✅ {pair}: Analizado (sin señal)")
                            pass

                    except Exception as e:
                        print(f"Error en {pair}: {str(e)}")
                
                print(f"⏳ Esperando {SCAN_INTERVAL} segundos para el siguiente escaneo...")
                time.sleep(SCAN_INTERVAL)
        except KeyboardInterrupt:
            print("\n🛑 Detenido")

if __name__ == "__main__":
    bot = TradingBot()
    bot.run()

