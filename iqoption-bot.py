"""
BOT PARA NUBE (Railway) - VERSIÓN CORREGIDA
"""
from iqoptionapi.stable_api import IQ_Option
import time
import pandas as pd
import ta
import requests
from datetime import datetime, timedelta
import os
import threading
import sys
import logging
import pytz
import json

# ==============================================
# CONFIGURACIÓN ESPECÍFICA PARA NUBE
# ==============================================
TIMEZONE = pytz.timezone('America/Santo_Domingo')

def get_local_time():
    """Obtener hora RD sincronizada"""
    utc_now = datetime.utcnow().replace(tzinfo=pytz.utc)
    return utc_now.astimezone(TIMEZONE)

def format_local_time():
    return get_local_time().strftime('%Y-%m-%d %H:%M:%S')

# Configurar logging para nube
class CloudFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        local_time = get_local_time()
        return local_time.strftime('%Y-%m-%d %H:%M:%S')

# ==============================================
# CONFIGURACIÓN
# ==============================================
# EN NUBE: Usar siempre variables de entorno
EMAIL_IQ = os.environ.get('EMAIL_IQ', '')
PASSWORD_IQ = os.environ.get('PASSWORD_IQ', '')
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', '')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')
WHATSAPP_PHONE = os.environ.get('WHATSAPP_PHONE', '')
WHATSAPP_API_KEY = os.environ.get('WHATSAPP_API_KEY', '')

INVESTMENT = float(os.environ.get('INVESTMENT', 1.0))
ACCOUNT_TYPE = os.environ.get('ACCOUNT_TYPE', 'PRACTICE')
DURATION = int(os.environ.get('DURATION', 1))

# Pares optimizados para nube (menos es mejor)
SYMBOLS = [
    'EURJPY-OTC', 'EURUSD-OTC', 'AUDCAD-OTC', 
    'GBPUSD-OTC', 'EURGBP-OTC', 'GBPJPY-OTC', 'USDCHF-OTC', 
]

TIMEFRAME = 60
CANDLE_COUNT = 200  # REDUCIDO para nube
SCAN_INTERVAL = 10  # AUMENTADO para nube

# Configuración especial para nube
CLOUD_MODE = os.environ.get('RAILWAY_ENVIRONMENT') is not None
REQUEST_TIMEOUT = 30 if CLOUD_MODE else 10
MAX_RETRIES = 3 if CLOUD_MODE else 2

# ==============================================
# LOGGING
# ==============================================
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

handler = logging.StreamHandler(sys.stdout)
formatter = CloudFormatter('%(asctime)s - [CLOUD] - %(levelname)s - %(message)s')
handler.setFormatter(formatter)

if not logger.handlers:
    logger.addHandler(handler)

# ==============================================
# BOT OPTIMIZADO PARA NUBE
# ==============================================
class CloudTradingBot:
    def __init__(self):
        self.IQ = None
        self.connected = False
        self.running = False
        self.last_signals = {}
        self.retry_count = 0
        self.cloud_mode = CLOUD_MODE
        
        logger.info(f"🌐 {'MODO NUBE' if self.cloud_mode else 'MODO LOCAL'}")
        logger.info(f"🕒 Hora servidor: {format_local_time()}")
        
    def debug_env_vars(self):
        """Debug: Verificar variables de entorno"""
        env_vars = ['EMAIL_IQ', 'PASSWORD_IQ', 'TELEGRAM_TOKEN', 'TELEGRAM_CHAT_ID']
        for var in env_vars:
            value = os.environ.get(var)
            if value:
                logger.debug(f"✅ {var}: Configurada")
            else:
                logger.error(f"❌ {var}: NO configurada")
    
    def connect_iqoption_cloud(self):
        """Conexión optimizada para nube"""
        try:
            logger.info("☁️ Conectando desde nube...")
            
            # Para nube, aumentar timeouts
            self.IQ = IQ_Option(EMAIL_IQ, PASSWORD_IQ)
            
            # Configurar para cloud
            if self.cloud_mode:
                # Intentar conectar con más paciencia
                for attempt in range(3):
                    logger.info(f"   Intento {attempt+1}/3...")
                    self.connected = self.IQ.connect()
                    
                    if self.connected:
                        break
                    time.sleep(5)
            else:
                self.connected = self.IQ.connect()
            
            if self.connected and self.IQ.check_connect():
                # Verificar hora del servidor IQ Option
                server_time = self.get_server_timestamp()
                if server_time:
                    local_time = get_local_time()
                    time_diff = abs((server_time - local_time).total_seconds())
                    
                    if time_diff > 30:
                        logger.warning(f"⚠️ Diferencia horaria: {time_diff:.0f}s")
                        logger.warning("   Esto puede causar errores en cloud")
                
                self.IQ.change_balance(ACCOUNT_TYPE)
                balance = self.IQ.get_balance()
                
                logger.info(f"✅ Conexión cloud exitosa")
                logger.info(f"💰 Balance: ${balance:.2f}")
                logger.info(f"📡 IP: {self.get_public_ip()}")
                
                return True
            else:
                logger.error("❌ Falló conexión cloud")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error conexión cloud: {str(e)}")
            return False
    
    def get_server_timestamp(self):
        """Obtener timestamp del servidor IQ Option"""
        try:
            return self.IQ.get_server_timestamp()
        except:
            return None
    
    def get_public_ip(self):
        """Obtener IP pública (útil para debug)"""
        try:
            response = requests.get('https://api.ipify.org?format=json', timeout=5)
            return response.json().get('ip', 'Desconocida')
        except:
            return "No detectada"
    
    def get_candles_cloud(self, pair, max_retries=MAX_RETRIES):
        """Obtener velas optimizado para cloud"""
        for attempt in range(max_retries):
            try:
                if not self.IQ or not self.IQ.check_connect():
                    logger.warning(f"⚠️ {pair}: Reconectando...")
                    if not self.connect_iqoption_cloud():
                        return None
                
                # Añadir delay entre requests en cloud
                if self.cloud_mode and attempt > 0:
                    time.sleep(1)
                
                candles = self.IQ.get_candles(pair, TIMEFRAME, CANDLE_COUNT, time.time())
                
                if candles and len(candles) >= CANDLE_COUNT:
                    logger.debug(f"✅ {pair}: {len(candles)} velas (intento {attempt+1})")
                    return candles
                elif candles:
                    logger.warning(f"⚠️ {pair}: Solo {len(candles)}/{CANDLE_COUNT} velas")
                    # Aceptar si tenemos al menos 50%
                    if len(candles) >= CANDLE_COUNT // 2:
                        return candles
                
            except Exception as e:
                logger.error(f"❌ {pair}: Error intento {attempt+1}: {str(e)}")
                if attempt < max_retries - 1:
                    time.sleep(2)
        
        logger.error(f"❌ {pair}: Falló después de {max_retries} intentos")
        self.retry_count += 1
        return None
    
    def analyze_pair_cloud(self, pair):
        """Análisis optimizado para cloud"""
        candles = self.get_candles_cloud(pair)
        if not candles:
            return None
        
        try:
            df = pd.DataFrame(candles)
            
            # Verificar datos mínimos
            if len(df) < 20:
                logger.warning(f"⚠️ {pair}: Datos insuficientes para análisis")
                return None
            
            for col in ['open', 'close', 'max', 'min']:
                df[col] = df[col].astype(float)
            
            df.rename(columns={'max': 'high', 'min': 'low'}, inplace=True)
            
            # Indicadores (mantener pero con validación)
            try:
                df['RSI'] = ta.momentum.RSIIndicator(df['close'], window=14).rsi()
                bb = ta.volatility.BollingerBands(df['close'], window=14, window_dev=2)
                df['BB_high'] = bb.bollinger_hband()
                df['BB_low'] = bb.bollinger_lband()
                df['EMA50'] = ta.trend.EMAIndicator(df['close'], window=50).ema_indicator()
            except Exception as e:
                logger.error(f"❌ {pair}: Error calculando indicadores: {str(e)}")
                return None
            
            # Análisis de velas
            df['body'] = abs(df['close'] - df['open'])
            df['upper_wick'] = df['high'] - df[['open', 'close']].max(axis=1)
            df['lower_wick'] = df[['open', 'close']].min(axis=1) - df['low']
            df['avg_body_10'] = df['body'].rolling(window=10).mean()
            
            # Conteo velas consecutivas
            def count_consecutive(series):
                count = 0
                for val in reversed(series.values):
                    if val: 
                        count += 1
                    else: 
                        break
                return count
            
            is_green = df['close'] > df['open']
            is_red = df['close'] < df['open']
            
            consecutive_green = count_consecutive(is_green)
            consecutive_red = count_consecutive(is_red)
            
            last = df.iloc[-1]
            
            # Validar que RSI no sea NaN
            if pd.isna(last['RSI']) or pd.isna(last['EMA50']):
                logger.warning(f"⚠️ {pair}: Indicadores con NaN")
                return None
            
            analysis = {
                'pair': pair, 
                'price': last['close'], 
                'rsi': float(last['RSI']),
                'bb_high': float(last['BB_high']), 
                'bb_low': float(last['BB_low']),
                'ema50': float(last['EMA50']), 
                'body': float(last['body']),
                'upper_wick': float(last['upper_wick']), 
                'lower_wick': float(last['lower_wick']),
                'avg_body': float(last['avg_body_10']), 
                'consecutive_green': consecutive_green,
                'consecutive_red': consecutive_red,
                'timestamp': time.time()
            }
            
            logger.debug(f"📊 {pair}: ${analysis['price']:.5f} RSI:{analysis['rsi']:.1f}")
            return analysis
            
        except Exception as e:
            logger.error(f"❌ {pair}: Error análisis: {str(e)}")
            return None
    
    def check_signal_cloud(self, data):
        """Estrategia con validación extra para cloud"""
        if not data:
            return None
        
        # Verificar que los datos sean válidos
        required_keys = ['rsi', 'ema50', 'price', 'bb_high', 'bb_low', 'body', 'avg_body']
        for key in required_keys:
            if key not in data or data[key] is None:
                logger.warning(f"⚠️ {data.get('pair', 'Unknown')}: Falta {key}")
                return None
        
        signal = None
        price = data['price']
        rsi = data['rsi']
        ema = data['ema50']
        bb_high = data['bb_high']
        bb_low = data['bb_low']
        body = data['body']
        avg_body = data['avg_body']
        upper_wick = data['upper_wick']
        lower_wick = data['lower_wick']
        consecutive_green = data['consecutive_green']
        consecutive_red = data['consecutive_red']
        
        # Validar rangos
        if rsi < 0 or rsi > 100 or price <= 0 or body < 0:
            logger.warning(f"⚠️ {data['pair']}: Datos fuera de rango")
            return None
        
        # SEÑAL PUT
        if price > ema and ema > 0:  # Añadir validación ema > 0
            if (consecutive_green >= 4 and rsi > 70 and 
                price >= bb_high and bb_high > 0):
                if body > 0 and upper_wick > (body * 0.35) and avg_body > 0:
                    if avg_body <= body <= (avg_body * 2):
                        signal = "PUT"
                        logger.info(f"📉 CLOUD: Señal PUT en {data['pair']}")
        
        # SEÑAL CALL
        elif price < ema and ema > 0:
            if (consecutive_red >= 4 and rsi < 30 and 
                price <= bb_low and bb_low > 0):
                if body > 0 and lower_wick > (body * 0.35) and avg_body > 0:
                    if avg_body <= body <= (avg_body * 2):
                        signal = "CALL"
                        logger.info(f"📈 CLOUD: Señal CALL en {data['pair']}")
        
        # Prevenir señales duplicadas
        if signal:
            signal_key = f"{data['pair']}_{signal}_{int(time.time() / 300)}"  # Cambia cada 5 min
            if signal_key in self.last_signals:
                logger.debug(f"⏳ {data['pair']}: Señal reciente ignorada")
                return None
            
            self.last_signals[signal_key] = time.time()
            
            # Log detallado para debug
            logger.info(f"🎯 SEÑAL CONFIRMADA: {signal} en {data['pair']}")
            logger.info(f"   📍 Precio: {price:.5f}, EMA: {ema:.5f}")
            logger.info(f"   📊 RSI: {rsi:.1f}, Cuerpo: {body:.5f}")
            logger.info(f"   🔄 Consecutivas: {'Verde' if signal=='PUT' else 'Roja'} {consecutive_green if signal=='PUT' else consecutive_red}")
        
        return signal
    
    def send_cloud_alert(self, message):
        """Enviar alerta optimizada para cloud"""
        try:
            # Telegram
            if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
                url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
                payload = {
                    'chat_id': TELEGRAM_CHAT_ID,
                    'text': f"☁️ {message}",
                    'parse_mode': 'Markdown'
                }
                response = requests.post(url, json=payload, timeout=10)
                logger.info(f"📤 Telegram: {'✅' if response.status_code == 200 else '❌'}")
            
            # WhatsApp
            if WHATSAPP_PHONE and WHATSAPP_API_KEY:
                import urllib.parse
                encoded_msg = urllib.parse.quote(f"☁️ {message}")
                url = f"https://api.callmebot.com/whatsapp.php?phone={WHATSAPP_PHONE}&apikey={WHATSAPP_API_KEY}&text={encoded_msg}"
                requests.get(url, timeout=10)
                
        except Exception as e:
            logger.error(f"❌ Error enviando alerta cloud: {str(e)}")
    
    def execute_trade_cloud(self, pair, action):
        """Ejecutar trade en cloud con validación extra"""
        logger.info(f"☁️ Intentando {action} en {pair}...")
        
        try:
            # Verificar conexión
            if not self.IQ or not self.IQ.check_connect():
                logger.warning("⚠️ Reconectando antes de trade...")
                if not self.connect_iqoption_cloud():
                    return None
            
            balance_before = self.IQ.get_balance()
            
            # 1. Intentar Binaria
            check, id = self.IQ.buy(INVESTMENT, pair, action.lower(), DURATION)
            if check and id:
                logger.info(f"✅ CLOUD: Binaria ID {id}")
                return {
                    "type": "BINARY",
                    "id": id,
                    "balance_before": balance_before,
                    "pair": pair,
                    "action": action
                }
            
            # 2. Intentar Digital
            logger.info("   ⚠️ Probando Digital...")
            check, id = self.IQ.buy_digital_spot(pair, INVESTMENT, action.lower(), DURATION)
            if check:
                logger.info(f"✅ CLOUD: Digital ID {id}")
                return {
                    "type": "DIGITAL",
                    "id": id,
                    "balance_before": balance_before,
                    "pair": pair,
                    "action": action
                }
            
            logger.warning(f"❌ {pair}: No disponible en cloud")
            return None
            
        except Exception as e:
            logger.error(f"❌ Error trade cloud: {str(e)}")
            return None
    
    def run_cloud_scan(self):
        """Escaneo optimizado para cloud"""
        logger.info(f"🔍 CLOUD: Escaneando {len(SYMBOLS)} pares...")
        
        signals_found = 0
        
        for pair in SYMBOLS:
            try:
                if not self.running:
                    break
                
                # Analizar
                analysis = self.analyze_pair_cloud(pair)
                if not analysis:
                    continue
                
                # Verificar señal
                signal = self.check_signal_cloud(analysis)
                
                if signal:
                    signals_found += 1
                    
                    # Alertar
                    alert_msg = (
                        f"🚨 *SEÑAL EN NUBE*\n\n"
                        f"*Par:* {pair}\n"
                        f"*Señal:* {signal}\n"
                        f"*Precio:* {analysis['price']:.5f}\n"
                        f"*RSI:* {analysis['rsi']:.1f}\n"
                        f"*Hora RD:* {format_local_time()}"
                    )
                    
                    self.send_cloud_alert(alert_msg)
                    
                    # Ejecutar trade
                    trade_info = self.execute_trade_cloud(pair, signal)
                    
                    if trade_info:
                        # Monitorear en segundo plano
                        threading.Thread(
                            target=self.monitor_trade,
                            args=(trade_info,),
                            daemon=True
                        ).start()
                        
                        logger.info(f"✅ CLOUD: Trade ejecutado en {pair}")
                    else:
                        logger.warning(f"⚠️ CLOUD: No se pudo ejecutar en {pair}")
                
                else:
                    # Solo debug detallado
                    logger.debug(f"   {pair}: Sin señal")
            
            except Exception as e:
                logger.error(f"❌ Error en {pair}: {str(e)}")
                continue
        
        if signals_found > 0:
            logger.info(f"📊 CLOUD: {signals_found} señales encontradas")
        else:
            logger.info("✅ CLOUD: Escaneo completado (0 señales)")
        
        return signals_found
    
    def monitor_trade(self, trade_info):
        """Monitorear resultado"""
        try:
            logger.info(f"⏳ CLOUD: Monitoreando {trade_info['id']}...")
            time.sleep((DURATION * 60) + 20)
            
            balance_after = self.IQ.get_balance()
            profit = balance_after - trade_info['balance_before']
            
            result = "💰 WIN" if profit > 0 else "📉 LOSS" if profit < 0 else "🤝 EMPATE"
            
            result_msg = (
                f"🏁 *RESULTADO NUBE*\n\n"
                f"*Par:* {trade_info['pair']}\n"
                f"*Resultado:* {result}\n"
                f"*Profit:* ${profit:.2f}\n"
                f"*Balance:* ${balance_after:.2f}"
            )
            
            self.send_cloud_alert(result_msg)
            
        except Exception as e:
            logger.error(f"❌ Error monitoreo: {str(e)}")
    
    def run(self):
        """Ejecutar bot en cloud"""
        logger.info("=" * 50)
        logger.info("🚀 INICIANDO BOT EN NUBE")
        logger.info("=" * 50)
        
        # Debug variables
        self.debug_env_vars()
        
        self.running = True
        
        # Conexión inicial
        if not self.connect_iqoption_cloud():
            logger.error("❌ No se pudo conectar desde nube")
            return
        
        # Mensaje inicial
        self.send_cloud_alert(f"🤖 *Bot iniciado en nube*\nHora RD: {format_local_time()}")
        
        logger.info("✅ Bot cloud iniciado")
        
        try:
            while self.running:
                try:
                    # Escanear
                    self.run_cloud_scan()
                    
                    # Esperar
                    logger.info(f"⏳ CLOUD: Esperando {SCAN_INTERVAL}s...")
                    for i in range(SCAN_INTERVAL):
                        if not self.running:
                            break
                        time.sleep(1)
                    
                except KeyboardInterrupt:
                    break
                except Exception as e:
                    logger.error(f"❌ Error ciclo: {str(e)}")
                    time.sleep(30)
        
        finally:
            self.running = False
            self.send_cloud_alert("🛑 *Bot en nube detenido*")
            logger.info("🛑 Bot cloud detenido")

# ==============================================
# EJECUCIÓN
# ==============================================
if __name__ == "__main__":
    # Determinar automáticamente si estamos en cloud
    is_cloud = os.environ.get('RAILWAY_ENVIRONMENT') is not None or os.environ.get('PORT') is not None
    
    if is_cloud:
        logger.info("🌐 DETECTADO: Entorno de nube")
        bot = CloudTradingBot()
        bot.run()
    else:
        logger.info("💻 DETECTADO: Entorno local")
        # Aquí podrías importar tu bot local
        bot = CloudTradingBot()
        bot.cloud_mode = False
        bot.run()
