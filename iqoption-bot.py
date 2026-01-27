"""
BOT PRINCIPAL de Trading para IQ Option
"""
from iqoptionapi.stable_api import IQ_Option
import time
import pandas as pd
import ta
import requests
from datetime import datetime
import os
import threading
import sys
import logging

# ==============================================
# CONFIGURACIÓN (VARIABLES DE ENTORNO)
# ==============================================
EMAIL_IQ = os.getenv('EMAIL_IQ')
PASSWORD_IQ = os.getenv('PASSWORD_IQ')
WHATSAPP_PHONE = os.getenv('WHATSAPP_PHONE')
WHATSAPP_API_KEY = os.getenv('WHATSAPP_API_KEY')

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

INVESTMENT = float(os.getenv('INVESTMENT', 1.0))
ACCOUNT_TYPE = os.getenv('ACCOUNT_TYPE', "PRACTICE")
DURATION = int(os.getenv('DURATION', 1))

# Pares a analizar
SYMBOLS_STR = os.getenv('SYMBOLS', '')
if SYMBOLS_STR:
    SYMBOLS = [s.strip() for s in SYMBOLS_STR.split(',')]
else:
    SYMBOLS = [
        'EURJPY-OTC', 'EURUSD-OTC', 'AUDCAD-OTC', 
        'GBPUSD-OTC', 'EURGBP-OTC', 'GBPJPY-OTC', 'USDCHF-OTC', 
        'USDHKD-OTC', 'USDINR-OTC', 'USDSGD-OTC', 'USDZAR-OTC'
    ]

TIMEFRAME = int(os.getenv('TIMEFRAME', 60))
CANDLE_COUNT = int(os.getenv('CANDLE_COUNT', 200))
SCAN_INTERVAL = int(os.getenv('SCAN_INTERVAL', 10))

# Configuración de reconexión
MAX_RECONNECTION_ATTEMPTS = int(os.getenv('MAX_RECONNECTION_ATTEMPTS', 10))
RECONNECTION_DELAY = int(os.getenv('RECONNECTION_DELAY', 30))

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# ==============================================
# CLASE PRINCIPAL DEL BOT
# ==============================================
class TradingBot:
    def __init__(self):
        self.IQ = None
        self.connected = False
        self.running = False
        self.last_signals = {}
        self.reconnection_attempts = 0

    def validate_config(self):
        """Validar que todas las variables necesarias estén configuradas"""
        required_vars = ['EMAIL_IQ', 'PASSWORD_IQ', 'TELEGRAM_TOKEN', 'TELEGRAM_CHAT_ID']
        missing = []
        
        for var in required_vars:
            if not os.getenv(var):
                missing.append(var)
        
        if missing:
            logger.error(f"❌ Variables faltantes: {', '.join(missing)}")
            logger.error("Por favor, configura estas variables en Railway")
            return False
        
        logger.info("✅ Configuración validada correctamente")
        return True

    def connect_iqoption(self):
        """Conectar a IQ Option"""
        try:
            if not EMAIL_IQ or not PASSWORD_IQ:
                logger.error("❌ Credenciales de IQ Option no configuradas")
                return False
            
            logger.info("🔗 Conectando a IQ Option...")
            self.IQ = IQ_Option(EMAIL_IQ, PASSWORD_IQ)
            self.connected = self.IQ.connect()
            
            if self.connected and self.IQ.check_connect():
                logger.info(f"✅ Conexión exitosa ({ACCOUNT_TYPE})")
                self.IQ.change_balance(ACCOUNT_TYPE)
                balance = self.IQ.get_balance()
                logger.info(f"💰 Balance: ${balance:.2f}")
                self.reconnection_attempts = 0
                return True
            else:
                logger.error("❌ Error de conexión a IQ Option")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error al conectar: {str(e)}")
            return False

    def reconnect_iqoption(self):
        """Reconectar automáticamente"""
        while self.running and self.reconnection_attempts < MAX_RECONNECTION_ATTEMPTS:
            self.reconnection_attempts += 1
            logger.warning(f"🔄 Intento de reconexión {self.reconnection_attempts}/{MAX_RECONNECTION_ATTEMPTS}")
            
            self.send_telegram_alert(f"⚠️ *RECONEXIÓN INTENTO {self.reconnection_attempts}*")
            
            if self.connect_iqoption():
                logger.info("✅ Reconexión exitosa")
                self.send_telegram_alert("✅ *CONEXIÓN RESTABLECIDA*")
                return True
            
            wait_time = RECONNECTION_DELAY * self.reconnection_attempts
            logger.info(f"⏳ Esperando {wait_time} segundos...")
            time.sleep(wait_time)
        
        logger.error(f"❌ Máximos intentos de reconexión alcanzados")
        self.send_telegram_alert("🔴 *BOT DETENIDO* - Máximos intentos de reconexión")
        return False

    def get_candles(self, pair):
        """Obtener velas históricas"""
        try:
            candles = self.IQ.get_candles(pair, TIMEFRAME, CANDLE_COUNT, time.time())
            if candles and len(candles) == CANDLE_COUNT:
                return candles
            else:
                logger.warning(f"⚠️ {pair}: Datos incompletos")
                return None
        except:
            return None

    def analyze_pair(self, pair):
        """Analizar un par"""
        try:
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
            
        except Exception as e:
            logger.error(f"❌ Error analizando {pair}: {str(e)}")
            return None

    def send_telegram_alert(self, message):
        """Enviar mensaje a Telegram"""
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            payload = {
                'chat_id': TELEGRAM_CHAT_ID, 
                'text': message, 
                'parse_mode': 'Markdown'
            }
            response = requests.post(url, data=payload, timeout=10)
            if response.status_code == 200:
                logger.info("📤 Alerta enviada a Telegram")
            else:
                logger.error(f"❌ Error Telegram: {response.status_code}")
        except Exception as e:
            logger.error(f"❌ Error enviando Telegram: {str(e)}")

    def send_whatsapp_alert(self, message):
        """Enviar mensaje a WhatsApp"""
        try:
            if not WHATSAPP_PHONE or not WHATSAPP_API_KEY:
                return
                
            import urllib.parse
            encoded_msg = urllib.parse.quote(message)
            url = f"https://api.callmebot.com/whatsapp.php?phone={WHATSAPP_PHONE}&apikey={WHATSAPP_API_KEY}&text={encoded_msg}"
            requests.get(url, timeout=10)
            logger.info("📤 Alerta enviada a WhatsApp")
        except Exception as e:
            logger.error(f"❌ Error enviando WhatsApp: {str(e)}")

    def execute_trade(self, pair, action):
        """Ejecutar operación"""
        logger.info(f"🚀 Intentando {action} en {pair}")
        
        try:
            balance_before = self.IQ.get_balance()

            # 1. Intentar Binaria
            check, id = self.IQ.buy(INVESTMENT, pair, action.lower(), DURATION)
            if check and id:
                logger.info(f"✅ Binaria ID: {id}")
                return {"type": "BINARY", "id": id, "balance_before": balance_before}
            
            # 2. Intentar Digital
            logger.info(f"⚠️ Probando Digital...")
            check, id = self.IQ.buy_digital_spot(pair, INVESTMENT, action.lower(), DURATION)
            if check:
                logger.info(f"✅ Digital ID: {id}")
                return {"type": "DIGITAL", "id": id, "balance_before": balance_before}
                
            logger.warning(f"❌ {pair} no disponible")
            return None
            
        except Exception as e:
            logger.error(f"❌ Error en trade: {str(e)}")
            return None

    def check_trade_result_safe(self, trade_info, pair, action):
        """Vigilar resultado"""
        logger.info(f"⏳ Vigilando {pair}...")
        
        try:
            balance_before = trade_info['balance_before']
            wait_time = (DURATION * 60) + 30
            time.sleep(wait_time)
            
            final_balance = self.IQ.get_balance()
            profit = final_balance - balance_before
            
            if final_balance > balance_before:
                result_text = "💰 WIN"
            elif final_balance < balance_before:
                result_text = "📉 LOSS"
            else:
                result_text = "🤝 EMPATE"

            msg = (
                f"🏁 *RESULTADO*\n\n"
                f"*Par:* {pair}\n"
                f"*Dirección:* {action.upper()}\n"
                f"*Tipo:* {trade_info['type']}\n"
                f"*Resultado:* {result_text}\n"
                f"*Profit:* ${profit:.2f}\n"
                f"*Balance:* ${final_balance:.2f}"
            )
            self.send_telegram_alert(msg)
            logger.info(f"🏁 {result_text} en {pair}")
            
        except Exception as e:
            logger.error(f"❌ Error en resultado: {str(e)}")

    def check_signal(self, data):
        """Lógica de estrategia"""
        if not data: return None
        
        signal = None
        price, rsi, ema = data['price'], data['rsi'], data['ema50']
        bb_high, bb_low = data['bb_high'], data['bb_low']
        body, avg_body = data['body'], data['avg_body']

        # Tendencia ALCISTA -> PUT
        if price > ema:
            if data['consecutive_green'] >= 4 and rsi > 70 and price >= bb_high:
                if data['upper_wick'] > (body * 0.35) and avg_body <= body <= (avg_body * 2):
                    signal = "PUT"

        # Tendencia BAJISTA -> CALL
        elif price < ema:
            if data['consecutive_red'] >= 4 and rsi < 30 and price <= bb_low:
                if data['lower_wick'] > (body * 0.35) and avg_body <= body <= (avg_body * 2):
                    signal = "CALL"

        if not signal: return None

        # Prevenir señales duplicadas
        signal_key = f"{data['pair']}_{signal}"
        current_time = time.time()
        if signal_key in self.last_signals:
            if (current_time - self.last_signals[signal_key]) < 600:
                logger.info(f"⏳ Señal ignorada (repetida)")
                return None
        
        self.last_signals[signal_key] = current_time
        return signal

    def scan_markets(self):
        """Escaneo principal"""
        logger.info(f"🔎 Escaneando {len(SYMBOLS)} pares...")
        signals_found = 0
        
        for pair in SYMBOLS:
            try:
                if not self.running:
                    break
                    
                analysis = self.analyze_pair(pair)
                if not analysis:
                    continue

                signal = self.check_signal(analysis)
                if signal:
                    signals_found += 1
                    trade_info = self.execute_trade(pair, signal)
                    
                    if trade_info:
                        msg_opened = (
                            f"🚨 *OPERACIÓN ABIERTA*\n\n"
                            f"*Par:* {pair}\n"
                            f"*Dirección:* {signal.upper()}\n"
                            f"*Precio:* {analysis['price']:.5f}"
                        )
                        self.send_telegram_alert(msg_opened)
                        self.send_whatsapp_alert(msg_opened.replace("\n", "%0A"))

                        threading.Thread(
                            target=self.check_trade_result_safe, 
                            args=(trade_info, pair, signal), 
                            daemon=True
                        ).start()
                        logger.info(f"🔔 {signal} en {pair}")
                    else:
                        msg_closed = f"⚠️ *SEÑAL NO OPERADA*\n*Par:* {pair}"
                        self.send_telegram_alert(msg_closed)

            except Exception as e:
                logger.error(f"❌ Error en {pair}: {str(e)}")
                continue
        
        logger.info(f"✅ Escaneo completado. Señales: {signals_found}")
        return signals_found

    def run(self):
        """Ejecutar bot principal"""
        logger.info("🚀 Iniciando Bot de Trading...")
        
        # Validar configuración
        if not self.validate_config():
            logger.error("❌ Configuración inválida. Saliendo...")
            return
        
        self.running = True
        
        # Conexión inicial
        if not self.connect_iqoption():
            logger.error("❌ Conexión fallida. Iniciando reconexión...")
            if not self.reconnect_iqoption():
                return
        
        # Mensaje de inicio
        self.send_telegram_alert(
            f"🚀 *Bot Iniciado*\n\n"
            f"*Hora:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"*Cuenta:* {ACCOUNT_TYPE}\n"
            f"*Pares:* {len(SYMBOLS)}"
        )
        
        logger.info("🔎 Iniciando escaneo automático...")
        
        try:
            while self.running:
                try:
                    # Verificar conexión
                    if not self.IQ.check_connect():
                        logger.warning("⚠️ Conexión perdida")
                        if not self.reconnect_iqoption():
                            break
                    
                    # Escanear
                    self.scan_markets()
                    
                    # Esperar para siguiente escaneo
                    logger.info(f"⏳ Esperando {SCAN_INTERVAL}s...")
                    for i in range(SCAN_INTERVAL):
                        if not self.running:
                            break
                        time.sleep(1)
                        
                except KeyboardInterrupt:
                    logger.info("\n🛑 Detenido por usuario")
                    break
                except Exception as e:
                    logger.error(f"❌ Error: {str(e)}")
                    time.sleep(30)
        
        finally:
            self.running = False
            self.send_telegram_alert("🛑 *Bot Detenido*")
            logger.info("🛑 Bot detenido")

if __name__ == "__main__":
    bot = TradingBot()
    bot.run()
