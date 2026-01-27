"""
BOT PRINCIPAL de Trading para IQ Option - CON RECONEXIÓN MEJORADA
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
# CONFIGURACIÓN
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

# Pares a analizar - REDUCIDOS para pruebas
SYMBOLS = [
 'EURJPY-OTC', 'EURUSD-OTC', 'AUDCAD-OTC', 
    'GBPUSD-OTC', 'EURGBP-OTC', 'GBPJPY-OTC', 'USDCHF-OTC'
]

TIMEFRAME = int(os.getenv('TIMEFRAME', 60))
CANDLE_COUNT = int(os.getenv('CANDLE_COUNT', 100))  # REDUCIDO
SCAN_INTERVAL = int(os.getenv('SCAN_INTERVAL', 30))  # AUMENTADO a 30s

# Configuración de reconexión MEJORADA
MAX_RECONNECTION_ATTEMPTS = int(os.getenv('MAX_RECONNECTION_ATTEMPTS', 5))
RECONNECTION_DELAY = int(os.getenv('RECONNECTION_DELAY', 10))
HEARTBEAT_INTERVAL = int(os.getenv('HEARTBEAT_INTERVAL', 300))  # 5 minutos

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# ==============================================
# CLASE PRINCIPAL DEL BOT - MEJORADA
# ==============================================
class TradingBot:
    def __init__(self):
        self.IQ = None
        self.connected = False
        self.running = False
        self.last_signals = {}
        self.reconnection_attempts = 0
        self.last_heartbeat = time.time()
        self.connection_errors = 0
        self.max_connection_errors = 10

    def validate_config(self):
        """Validar configuración"""
        required_vars = ['EMAIL_IQ', 'PASSWORD_IQ', 'TELEGRAM_TOKEN', 'TELEGRAM_CHAT_ID']
        missing = []
        
        for var in required_vars:
            if not os.getenv(var):
                missing.append(var)
        
        if missing:
            logger.error(f"❌ Variables faltantes: {', '.join(missing)}")
            return False
        
        logger.info("✅ Configuración validada")
        return True

    def check_connection_health(self):
        """Verificar salud de la conexión"""
        try:
            if not self.IQ or not hasattr(self.IQ, 'check_connect'):
                return False
            
            # Método 1: Verificar conexión directa
            if hasattr(self.IQ, 'check_connect'):
                status = self.IQ.check_connect()
                if not status:
                    logger.warning("⚠️ check_connect() retornó False")
                    return False
            
            # Método 2: Intentar obtener algo simple
            current_time = self.IQ.get_server_timestamp()
            if current_time:
                self.connection_errors = 0
                return True
            else:
                self.connection_errors += 1
                return False
                
        except Exception as e:
            self.connection_errors += 1
            logger.error(f"❌ Error en check_connection_health: {str(e)}")
            return False

    def connect_iqoption(self, force_reconnect=False):
        """Conectar/reconectar a IQ Option con manejo mejorado"""
        try:
            if self.IQ and not force_reconnect:
                # Cerrar conexión anterior si existe
                try:
                    self.IQ.close()
                except:
                    pass
            
            logger.info("🔄 Creando nueva conexión IQ Option...")
            self.IQ = IQ_Option(EMAIL_IQ, PASSWORD_IQ)
            
            # Configurar timeout más largo para la nube
            logger.info("⏳ Conectando (esto puede tomar 10-20 segundos)...")
            
            # Intentar conexión con timeout
            start_time = time.time()
            self.connected = False
            
            # Primer intento
            self.connected = self.IQ.connect()
            
            if not self.connected:
                # Segundo intento después de 5 segundos
                time.sleep(5)
                logger.info("🔄 Segundo intento de conexión...")
                self.connected = self.IQ.connect()
            
            if self.connected:
                # Verificar conexión
                time.sleep(2)  # Esperar que se estabilice
                
                if self.IQ.check_connect():
                    self.IQ.change_balance(ACCOUNT_TYPE)
                    balance = self.IQ.get_balance()
                    
                    logger.info(f"✅ Conexión establecida ({ACCOUNT_TYPE})")
                    logger.info(f"💰 Balance: ${balance:.2f}")
                    logger.info(f"⏱️ Tiempo conexión: {time.time() - start_time:.1f}s")
                    
                    self.reconnection_attempts = 0
                    self.connection_errors = 0
                    self.last_heartbeat = time.time()
                    return True
                else:
                    logger.error("❌ Conexión establecida pero check_connect() falla")
                    return False
            else:
                logger.error("❌ No se pudo establecer conexión")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error crítico en connect_iqoption: {str(e)}")
            return False

    def heartbeat(self):
        """Heartbeat periódico para mantener conexión activa"""
        current_time = time.time()
        if current_time - self.last_heartbeat > HEARTBEAT_INTERVAL:
            logger.info("❤️ Enviando heartbeat...")
            try:
                # Actividad simple para mantener conexión
                if self.IQ:
                    # 1. Verificar hora del servidor
                    server_time = self.IQ.get_server_timestamp()
                    if server_time:
                        logger.info(f"🕒 Hora servidor: {server_time}")
                    
                    # 2. Verificar balance
                    balance = self.IQ.get_balance()
                    logger.info(f"💰 Balance actual: ${balance:.2f}")
                    
                    self.last_heartbeat = current_time
                    self.connection_errors = 0
                    return True
                else:
                    logger.warning("⚠️ No hay conexión para heartbeat")
                    return False
            except Exception as e:
                logger.error(f"❌ Error en heartbeat: {str(e)}")
                self.connection_errors += 1
                return False
        return True

    def safe_get_candles(self, pair, retries=2):
        """Obtener velas con reintentos"""
        for attempt in range(retries):
            try:
                # Primero verificar conexión
                if not self.check_connection_health():
                    logger.warning(f"⚠️ {pair}: Conexión no saludable, reintentando...")
                    if not self.reconnect_iqoption():
                        return None
                
                candles = self.IQ.get_candles(pair, TIMEFRAME, CANDLE_COUNT, time.time())
                
                if candles and len(candles) >= CANDLE_COUNT // 2:  # Aceptar al menos la mitad
                    logger.debug(f"✅ {pair}: {len(candles)} velas obtenidas")
                    return candles
                else:
                    logger.warning(f"⚠️ {pair}: Datos insuficientes (intento {attempt+1}/{retries})")
                    
            except Exception as e:
                logger.error(f"❌ {pair}: Error en get_candles: {str(e)}")
            
            # Esperar antes de reintentar
            if attempt < retries - 1:
                time.sleep(2)
        
        # Si llegamos aquí, todos los intentos fallaron
        logger.error(f"❌ {pair}: Fallaron todos los intentos de get_candles")
        self.connection_errors += 1
        return None

    def reconnect_iqoption(self):
        """Reconexión mejorada"""
        if self.connection_errors >= self.max_connection_errors:
            logger.error("🚨 Demasiados errores de conexión. Reiniciando...")
            self.send_telegram_alert("🚨 *DEMASIADOS ERRORES* - Reiniciando bot...")
            # Aquí podrías reiniciar el proceso, pero por ahora solo reconectamos
            self.connection_errors = 0
        
        self.reconnection_attempts += 1
        logger.warning(f"🔄 Reconexión {self.reconnection_attempts}/{MAX_RECONNECTION_ATTEMPTS}")
        
        self.send_telegram_alert(f"⚠️ *RECONEXIÓN* Intento {self.reconnection_attempts}")
        
        # Cerrar conexión anterior
        try:
            if self.IQ:
                self.IQ.close()
        except:
            pass
        
        # Intentar reconectar
        if self.connect_iqoption(force_reconnect=True):
            logger.info("✅ Reconexión exitosa")
            self.send_telegram_alert("✅ *CONEXIÓN RESTABLECIDA*")
            return True
        
        # Esperar con backoff exponencial
        wait_time = RECONNECTION_DELAY * (2 ** (self.reconnection_attempts - 1))
        wait_time = min(wait_time, 300)  # Máximo 5 minutos
        
        logger.info(f"⏳ Esperando {wait_time}s...")
        time.sleep(wait_time)
        
        if self.reconnection_attempts >= MAX_RECONNECTION_ATTEMPTS:
            logger.error(f"❌ Máximos intentos de reconexión")
            self.send_telegram_alert("🔴 *BOT DETENIDO* - Máximos intentos de reconexión")
            return False
        
        return False

    def analyze_pair(self, pair):
        """Analizar un par"""
        candles = self.safe_get_candles(pair)
        if not candles:
            return None

        try:
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
                return True
            else:
                logger.error(f"❌ Telegram error: {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"❌ Error Telegram: {str(e)}")
            return False

    def scan_markets_safe(self):
        """Escaneo seguro con manejo de errores"""
        if not self.check_connection_health():
            logger.warning("⚠️ Conexión no saludable antes de escanear")
            if not self.reconnect_iqoption():
                return 0
        
        # Heartbeat periódico
        self.heartbeat()
        
        logger.info(f"🔎 Escaneando {len(SYMBOLS)} pares...")
        signals_found = 0
        
        for pair in SYMBOLS:
            try:
                if not self.running:
                    break
                
                # Verificar conexión antes de cada par
                if self.connection_errors > 3:
                    logger.warning("⚠️ Demasiados errores, verificando conexión...")
                    if not self.check_connection_health():
                        self.reconnect_iqoption()
                
                analysis = self.analyze_pair(pair)
                if not analysis:
                    continue

                # (Aquí iría tu lógica de señales, manteniendo la que ya tienes)
                # signal = self.check_signal(analysis)
                # ...
                
                # Para pruebas, solo loguear
                logger.info(f"📊 {pair}: ${analysis['price']:.5f} RSI:{analysis['rsi']:.1f}")

            except Exception as e:
                logger.error(f"❌ Error en {pair}: {str(e)}")
                self.connection_errors += 1
                continue
        
        logger.info(f"✅ Escaneo completado. Errores: {self.connection_errors}")
        return signals_found

    def run(self):
        """Ejecutar bot principal"""
        logger.info("🚀 Iniciando Bot de Trading Mejorado...")
        
        if not self.validate_config():
            logger.error("❌ Configuración inválida")
            return
        
        self.running = True
        
        # Conexión inicial
        if not self.connect_iqoption():
            logger.error("❌ Conexión inicial fallida")
            if not self.reconnect_iqoption():
                return
        
        self.send_telegram_alert(
            f"🚀 *Bot Mejorado Iniciado*\n"
            f"*Hora:* {datetime.now().strftime('%H:%M:%S')}\n"
            f"*Pares:* {len(SYMBOLS)}\n"
            f"*Intervalo:* {SCAN_INTERVAL}s"
        )
        
        logger.info("🔎 Iniciando escaneo...")
        
        consecutive_errors = 0
        max_consecutive_errors = 3
        
        try:
            while self.running:
                try:
                    # Escanear
                    signals = self.scan_markets_safe()
                    
                    if signals > 0:
                        logger.info(f"📈 Señales encontradas: {signals}")
                    
                    # Reiniciar contador de errores si el escaneo fue exitoso
                    consecutive_errors = 0
                    
                    # Esperar para siguiente escaneo
                    logger.info(f"⏳ Esperando {SCAN_INTERVAL} segundos...")
                    for i in range(SCAN_INTERVAL):
                        if not self.running:
                            break
                        
                        # Verificar conexión durante la espera
                        if i % 10 == 0:  # Cada 10 segundos
                            if not self.check_connection_health():
                                logger.warning("⚠️ Conexión débil durante espera")
                        
                        time.sleep(1)
                        
                except Exception as e:
                    consecutive_errors += 1
                    logger.error(f"❌ Error en ciclo: {str(e)}")
                    
                    if consecutive_errors >= max_consecutive_errors:
                        logger.error("🚨 Demasiados errores consecutivos")
                        self.send_telegram_alert("🚨 *ERRORES CONSECUTIVOS* - Reiniciando...")
                        
                        # Intentar reconexión completa
                        if not self.reconnect_iqoption():
                            break
                        
                        consecutive_errors = 0
                    
                    time.sleep(30)  # Esperar 30s antes de reintentar
        
        except KeyboardInterrupt:
            logger.info("\n🛑 Detenido manualmente")
        except Exception as e:
            logger.error(f"❌ Error fatal: {str(e)}")
        finally:
            self.running = False
            self.send_telegram_alert("🛑 *Bot Detenido*")
            logger.info("🛑 Bot detenido")

if __name__ == "__main__":
    # Modo Railway: ejecutar directamente
    # Modo local: también ejecutar directamente
    bot = TradingBot()
    bot.run()

