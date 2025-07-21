import ccxt
import pandas as pd
import numpy as np
import time
import requests
from datetime import datetime
import matplotlib.pyplot as plt
from threading import Thread, Lock

# --- SETTINGS ---
FEE = 0.015                     # Shakepay's ~1.5% spread
SHORT_WINDOW = 7               # EMA/SMA short window
LONG_WINDOW = 30                 # EMA/SMA long window
USE_EMA = True                  # Use EMA (True) or SMA (False)
CHECK_INTERVAL = 60           # Check every 1 hour (in seconds)
TELEGRAM_BOT_TOKEN = "7326321585:AAGhFHTqnK-r4ce0NBHceBJLC649KV21qG8"  # Optional
TELEGRAM_CHAT_ID = "1255286244"               # Optional

# --- GLOBALS (Thread-Safe) ---
plot_data = {
    'timestamps': [],
    'ratio': [],
    'short_ma': [],
    'long_ma': [],
    'signal': [],
    'profit_btc': []  # Projected profit in BTC terms   
}
plot_lock = Lock()  # Prevent race conditions

# --- INITIALIZE EXCHANGE (Binance) ---
exchange = ccxt.binance()

# --- FETCH LATEST BTC/ETH RATIO ---
def get_live_ratio():
    btc_price = exchange.fetch_ticker('BTC/USDT')['last']
    eth_price = exchange.fetch_ticker('ETH/USDT')['last']
    return btc_price / eth_price

# --- MOVING AVERAGE CALCULATION ---
def calculate_ma(ratio_data, short_window=SHORT_WINDOW, long_window=LONG_WINDOW, use_ema=USE_EMA):
    df = pd.DataFrame(ratio_data, columns=['ratio'])
    if use_ema:
        df['short_ma'] = df['ratio'].ewm(span=short_window, adjust=False).mean()
        df['long_ma'] = df['ratio'].ewm(span=long_window, adjust=False).mean()
    else:
        df['short_ma'] = df['ratio'].rolling(window=short_window).mean()
        df['long_ma'] = df['ratio'].rolling(window=long_window).mean()
    df['signal'] = np.where(df['short_ma'] > df['long_ma'], 1, -1)
    return df

# --- TELEGRAM ALERTS (Optional) ---
def send_telegram_alert(message):
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        params = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
        requests.post(url, params=params).json()

# --- LIVE TRADING LOGIC ---
class LiveArbitrageBot:
    def __init__(self):
        self.historical_ratio = pd.DataFrame(columns=['timestamp', 'ratio'])
        self.current_btc = 0.00000609   # Your current BTC balance
        self.current_eth = 0.002591871230724891  # Your current ETH balance
        self.current_profit = 0.0
    
    def update_historical_data(self):
        ratio = get_live_ratio()
        new_row = pd.DataFrame({'timestamp': [datetime.now()], 'ratio': [ratio]})
        
        # Fix for FutureWarning: ensure consistent columns
        if self.historical_ratio.empty:
            self.historical_ratio = new_row
        else:
            self.historical_ratio = pd.concat(
                [self.historical_ratio, new_row],
                ignore_index=True,
                axis=0,
                join='inner'  # Only keep common columns
            )
        
        with plot_lock:
            plot_data['timestamps'].append(datetime.now())
            plot_data['ratio'].append(ratio)
            
            if len(plot_data['ratio']) >= LONG_WINDOW:
                ma_data = calculate_ma(plot_data['ratio'][-LONG_WINDOW:])
                
                # Ensure we don't append NaN if MA calculation fails
                short_ma = ma_data['short_ma'].iloc[-1] if not ma_data.empty else np.nan
                long_ma = ma_data['long_ma'].iloc[-1] if not ma_data.empty else np.nan
                signal = ma_data['signal'].iloc[-1] if not ma_data.empty else np.nan
                
                plot_data['short_ma'].append(short_ma)
                plot_data['long_ma'].append(long_ma)
                plot_data['signal'].append(signal)
                
                # Safe profit calculation
                if 'profit_btc' not in plot_data:
                    plot_data['profit_btc'] = []
                    
                if signal == 1 and not np.isnan(signal):  # Hold BTC
                    eth_held = self.current_eth
                    self.current_profit = (eth_held * ratio) * (1 - FEE) - self.current_btc
                elif signal == -1 and not np.isnan(signal):  # Hold ETH
                    btc_held = self.current_btc
                    self.current_profit = (btc_held / ratio) * (1 - FEE) * ratio - self.current_btc
                    
                plot_data['profit_btc'].append(self.current_profit)
                
            else:
                plot_data['short_ma'].append(np.nan)
                plot_data['long_ma'].append(np.nan)
                plot_data['signal'].append(np.nan)
                plot_data['profit_btc'].append(np.nan)
                    
    def generate_signal(self):
        if len(self.historical_ratio) >= LONG_WINDOW:
            df = calculate_ma(self.historical_ratio.copy())
            latest_signal = df['signal'].iloc[-1]
            latest_ratio = df['ratio'].iloc[-1]
            
            if latest_signal == 1:  # Favor BTC
                if self.current_eth > 0:
                    btc_gain = (self.current_eth * latest_ratio) * (1 - FEE)
                    alert_msg = f"🚀 [SWAP] ETH → BTC | Gain: {btc_gain:.6f} BTC | Ratio: {latest_ratio:.4f} | Potential Profit: {self.current_profit:.2f}"
                    print(alert_msg)
                    if self.current_profit > 0.01:
                        send_telegram_alert(alert_msg)
            else:  # Favor ETH
                if self.current_btc > 0:
                    eth_gain = (self.current_btc / latest_ratio) * (1 - FEE)
                    alert_msg = f"💎 [SWAP] BTC → ETH | Gain: {eth_gain:.6f} ETH | Ratio: {latest_ratio:.4f} | Potential Profit: {self.current_profit:.2f}"
                    print(alert_msg)
                    if self.current_profit > 0.01:
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

# --- LIVE DASHBOARD (Main Thread) ---
def live_dashboard():
    plt.ion()
    fig, ax = plt.subplots(figsize=(12, 6))
    
    while True:
        with plot_lock:
            if len(plot_data['timestamps']) > 1:
                ax.clear()
                
                # Plot Ratio and MAs
                ax.plot(plot_data['timestamps'], plot_data['ratio'], label='BTC/ETH Ratio', color='blue', linewidth=2)
                ax.plot(plot_data['timestamps'], plot_data['short_ma'], label=f'Short MA ({SHORT_WINDOW})', color='orange', linestyle='--')
                ax.plot(plot_data['timestamps'], plot_data['long_ma'], label=f'Long MA ({LONG_WINDOW})', color='green', linestyle='--')
                
                # Highlight signals
                ax.fill_between(
                    plot_data['timestamps'],
                    min(plot_data['ratio']),
                    max(plot_data['ratio']),
                    where=(np.array(plot_data['signal']) == 1),
                    color='green', alpha=0.2, label='Hold BTC'
                )
                ax.fill_between(
                    plot_data['timestamps'],
                    min(plot_data['ratio']),
                    max(plot_data['ratio']),
                    where=(np.array(plot_data['signal']) == -1),
                    color='red', alpha=0.2, label='Hold ETH'
                )
                
                # Add profit annotations (if available)
                if 'profit_btc' in plot_data:
                    last_profit = plot_data['profit_btc'][-1]
                    ax.annotate(
                        f"Projected Profit: {last_profit:.4f} BTC",
                        xy=(plot_data['timestamps'][-1], plot_data['ratio'][-1]),
                        xytext=(10, 10), textcoords='offset points',
                        bbox=dict(boxstyle='round,pad=0.5', fc='yellow', alpha=0.5)
                    )
                
                ax.set_title('BTC/ETH Arbitrage Dashboard (Live)')
                ax.legend(loc='upper left')
                ax.grid(True)
                plt.pause(1)

# --- START THE BOT ---
if __name__ == "__main__":
    bot = LiveArbitrageBot()
    
    # Start live trading thread
    trading_thread = Thread(target=bot.run_live)
    trading_thread.daemon = True
    trading_thread.start()
    
    # Start live dashboard in main thread
    live_dashboard()