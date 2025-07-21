import ccxt
import pandas as pd
import numpy as np
import time
import requests
from datetime import datetime
import matplotlib.pyplot as plt
from threading import Thread

# --- SETTINGS ---
FEE = 0.015                     # Shakepay's ~1.5% spread
SHORT_WINDOW = 10               # EMA/SMA short window
LONG_WINDOW = 50                # EMA/SMA long window
USE_EMA = True                  # Use EMA (True) or SMA (False)
CHECK_INTERVAL = 3600           # Check every 1 hour (in seconds)
TELEGRAM_BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"  # Optional
TELEGRAM_CHAT_ID = "YOUR_CHAT_ID"               # Optional

# --- INITIALIZE EXCHANGE (Binance) ---
exchange = ccxt.binance()

# --- FETCH LATEST BTC/ETH RATIO ---
def get_live_ratio():
    btc_price = exchange.fetch_ticker('BTC/USDT')['last']
    eth_price = exchange.fetch_ticker('ETH/USDT')['last']
    return btc_price / eth_price

# --- MOVING AVERAGE CALCULATION ---
def calculate_ma(df, column='ratio', short_window=SHORT_WINDOW, long_window=LONG_WINDOW, use_ema=USE_EMA):
    if use_ema:
        df['short_ma'] = df[column].ewm(span=short_window, adjust=False).mean()
        df['long_ma'] = df[column].ewm(span=long_window, adjust=False).mean()
    else:
        df['short_ma'] = df[column].rolling(window=short_window).mean()
        df['long_ma'] = df[column].rolling(window=long_window).mean()
    df['signal'] = np.where(df['short_ma'] > df['long_ma'], 1, -1)  # 1 = BTC, -1 = ETH
    return df

# --- TELEGRAM ALERTS (Optional) ---
def send_telegram_alert(message):
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        params = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message
        }
        requests.post(url, params=params).json()

# --- LIVE TRADING LOGIC ---
class LiveArbitrageBot:
    def __init__(self):
        self.historical_ratio = pd.DataFrame(columns=['timestamp', 'ratio'])
        self.current_btc = 1.0   # Your current BTC balance (edit this)
        self.current_eth = 10.0  # Your current ETH balance (edit this)
    
    def update_historical_data(self):
        ratio = get_live_ratio()
        new_row = pd.DataFrame({
            'timestamp': [datetime.now()],
            'ratio': [ratio]
        })
        self.historical_ratio = pd.concat([self.historical_ratio, new_row], ignore_index=True)
        return ratio
    
    def generate_signal(self):
        if len(self.historical_ratio) >= LONG_WINDOW:
            df = calculate_ma(self.historical_ratio.copy())
            latest_signal = df['signal'].iloc[-1]
            latest_ratio = df['ratio'].iloc[-1]
            
            if latest_signal == 1:  # Favor BTC
                if self.current_eth > 0:
                    btc_gain = (self.current_eth * latest_ratio) * (1 - FEE)
                    alert_msg = f"🚀 [SWAP] ETH → BTC | Gain: {btc_gain:.6f} BTC | Ratio: {latest_ratio:.4f}"
                    print(alert_msg)
                    send_telegram_alert(alert_msg)
            else:  # Favor ETH
                if self.current_btc > 0:
                    eth_gain = (self.current_btc / latest_ratio) * (1 - FEE)
                    alert_msg = f"💎 [SWAP] BTC → ETH | Gain: {eth_gain:.6f} ETH | Ratio: {latest_ratio:.4f}"
                    print(alert_msg)
                    send_telegram_alert(alert_msg)
    
    def run_live(self):
        print("🚀 Starting Live BTC/ETH Arbitrage Bot...")
        while True:
            try:
                self.update_historical_data()
                self.generate_signal()
                time.sleep(CHECK_INTERVAL)
            except Exception as e:
                print(f"⚠️ Error: {e}")
                time.sleep(60)

# --- LIVE DASHBOARD (Matplotlib) ---
def live_dashboard(bot):
    plt.ion()  # Interactive mode
    fig, ax = plt.subplots(figsize=(10, 5))
    
    while True:
        if len(bot.historical_ratio) > LONG_WINDOW:
            df = calculate_ma(bot.historical_ratio.copy())
            ax.clear()
            ax.plot(df['timestamp'], df['ratio'], label='BTC/ETH Ratio', color='blue')
            ax.plot(df['timestamp'], df['short_ma'], label=f'Short MA ({SHORT_WINDOW})', color='orange')
            ax.plot(df['timestamp'], df['long_ma'], label=f'Long MA ({LONG_WINDOW})', color='green')
            
            # Highlight buy/sell signals
            ax.fill_between(df['timestamp'], df['ratio'], where=(df['signal'] == 1), color='green', alpha=0.3)
            ax.fill_between(df['timestamp'], df['ratio'], where=(df['signal'] == -1), color='red', alpha=0.3)
            
            ax.set_title('Live BTC/ETH Arbitrage Dashboard')
            ax.legend()
            plt.pause(60)  # Update every 60 seconds

# --- START THE BOT ---
if __name__ == "__main__":
    bot = LiveArbitrageBot()
    
    # Start live trading thread
    trading_thread = Thread(target=bot.run_live)
    trading_thread.daemon = True
    trading_thread.start()
    
    # Start live dashboard (optional)
    dashboard_thread = Thread(target=live_dashboard, args=(bot,))
    dashboard_thread.daemon = True
    dashboard_thread.start()
    
    # Keep main thread alive
    while True:
        time.sleep(1)