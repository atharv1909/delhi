"""
QUANTIS — Live Crypto Dashboard (Fixed REST + WebSocket)
"""

import os
import json
import time
import threading
from datetime import datetime, timedelta
from collections import deque

import numpy as np
import pandas as pd
import requests
import websocket
import matplotlib.pyplot as plt
from IPython.display import display, clear_output
import warnings
warnings.filterwarnings('ignore')

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════════════════════
PRODUCT_ID = 'BTC-USD'  # Change to ETH-USD, SOL-USD, etc.

# Colors
DARK_BG = '#0d1117'; PANEL_BG = '#161b22'; GRID_CLR = '#30363d'
TXT_CLR = '#c9d1d9'; GREEN = '#3fb950'; RED = '#f85149'
BLUE = '#58a6ff'; GOLD = '#e3b341'; PURPLE = '#bc8cff'; ORANGE = '#f0883e'

# Live buffers
MAX_TICKS = 2000
price_buffer = deque(maxlen=MAX_TICKS)
time_buffer = deque(maxlen=MAX_TICKS)
bid_buffer = deque(maxlen=MAX_TICKS)
ask_buffer = deque(maxlen=MAX_TICKS)
trade_buffer = deque(maxlen=MAX_TICKS)

ws_running = False

plt.rcParams.update({
    'figure.facecolor': DARK_BG, 'axes.facecolor': PANEL_BG,
    'axes.edgecolor': GRID_CLR, 'axes.labelcolor': TXT_CLR,
    'text.color': TXT_CLR, 'xtick.color': TXT_CLR, 'ytick.color': TXT_CLR,
    'grid.color': GRID_CLR, 'grid.alpha': 0.3,
    'legend.facecolor': DARK_BG, 'legend.edgecolor': GRID_CLR,
    'legend.labelcolor': TXT_CLR,
})


# ═══════════════════════════════════════════════════════════════════════════════
# WEBSOCKET (Live ticks — this works without auth for public data)
# ═══════════════════════════════════════════════════════════════════════════════
def on_message(ws, message):
    data = json.loads(message)
    channel = data.get('channel', '')
    events = data.get('events', [])
    
    for event in events:
        if event.get('type') != 'update':
            continue
            
        if channel == 'ticker':
            for tick in event.get('tickers', []):
                if tick.get('product_id') == PRODUCT_ID:
                    price_buffer.append(float(tick.get('price', 0)))
                    bid_buffer.append(float(tick.get('bid', 0)))
                    ask_buffer.append(float(tick.get('ask', 0)))
                    time_buffer.append(datetime.utcnow())
                    
        elif channel == 'market_trades':
            for trade in event.get('trades', []):
                if trade.get('product_id') == PRODUCT_ID:
                    trade_buffer.append({
                        'price': float(trade.get('price', 0)),
                        'size': float(trade.get('size', 0)),
                        'time': datetime.utcnow(),
                        'side': trade.get('side', 'unknown')
                    })


def on_open(ws):
    print(f"✅ WebSocket connected")
    ws.send(json.dumps({
        "type": "subscribe",
        "product_ids": [PRODUCT_ID],
        "channel": "ticker"
    }))
    ws.send(json.dumps({
        "type": "subscribe",
        "product_ids": [PRODUCT_ID],
        "channel": "market_trades"
    }))
    print(f"📡 Subscribed to {PRODUCT_ID}")


def on_error(ws, error):
    print(f"❌ WebSocket Error: {error}")


def on_close(ws, *args):
    global ws_running
    ws_running = False
    print("🔌 WebSocket disconnected")


def start_ws():
    global ws_running
    ws_running = True
    ws = websocket.WebSocketApp(
        'wss://advanced-trade-ws.coinbase.com',
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close
    )
    ws.run_forever()


# ═══════════════════════════════════════════════════════════════════════════════
# REST API (Fixed — uses public endpoints that don't require auth)
# ═══════════════════════════════════════════════════════════════════════════════
def get_candles_from_coinbase():
    """
    Coinbase public API for candles.
    Uses the older /products/{id}/candles endpoint (public, no auth).
    """
    try:
        # Public endpoint (no auth needed)
        url = f'https://api.exchange.coinbase.com/products/{PRODUCT_ID}/candles'
        # granularity: 60 (1min), 300 (5min), 900 (15min), 3600 (1hr), 86400 (1day)
        params = {
            'granularity': 300,  # 5-minute candles
            'start': (datetime.utcnow() - timedelta(hours=24)).isoformat(),
            'end': datetime.utcnow().isoformat()
        }
        
        r = requests.get(url, params=params, timeout=15)
        if r.status_code != 200:
            print(f"REST Status {r.status_code}: {r.text[:200]}")
            return pd.DataFrame()
            
        data = r.json()
        if not data or not isinstance(data, list):
            return pd.DataFrame()
            
        # Coinbase returns: [time, low, high, open, close, volume]
        df = pd.DataFrame(data, columns=['time', 'low', 'high', 'open', 'close', 'volume'])
        df['time'] = pd.to_datetime(df['time'], unit='s')
        df = df.sort_values('time').set_index('time')
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = df[col].astype(float)
        return df
        
    except Exception as e:
        print(f"❌ REST Error: {e}")
        return pd.DataFrame()


def get_candles_from_alternative():
    """
    Fallback: Use yfinance as emergency backup (15-min delayed but works)
    """
    try:
        import yfinance as yf
        ticker = yf.Ticker(f"{PRODUCT_ID.split('-')[0]}-USD")
        df = ticker.history(period="1d", interval="5m")
        if df.empty:
            return pd.DataFrame()
        df = df.rename(columns={
            'Open': 'open', 'High': 'high', 'Low': 'low', 
            'Close': 'close', 'Volume': 'volume'
        })
        return df
    except:
        return pd.DataFrame()


def get_candles():
    """Try Coinbase public API first, fallback to alternatives"""
    df = get_candles_from_coinbase()
    if not df.empty:
        print(f"✅ Loaded {len(df)} candles from Coinbase public API")
        return df
    
    print("⚠️  Coinbase public API failed, trying fallback...")
    df = get_candles_from_alternative()
    if not df.empty:
        print(f"✅ Loaded {len(df)} candles from fallback")
        return df
    
    print("❌ All data sources failed")
    return pd.DataFrame()


# ═══════════════════════════════════════════════════════════════════════════════
# INDICATORS
# ═══════════════════════════════════════════════════════════════════════════════
def add_indicators(df):
    df = df.copy()
    df['ema_9'] = df['close'].ewm(span=9, adjust=False).mean()
    df['ema_21'] = df['close'].ewm(span=21, adjust=False).mean()
    df['sma_20'] = df['close'].rolling(20).mean()
    df['bb_std'] = df['close'].rolling(20).std()
    df['bb_upper'] = df['sma_20'] + 2 * df['bb_std']
    df['bb_lower'] = df['sma_20'] - 2 * df['bb_std']
    
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / (loss + 1e-8)
    df['rsi'] = 100 - (100 / (1 + rs))
    
    ema_12 = df['close'].ewm(span=12, adjust=False).mean()
    ema_26 = df['close'].ewm(span=26, adjust=False).mean()
    df['macd'] = ema_12 - ema_26
    df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    df['macd_hist'] = df['macd'] - df['macd_signal']
    df['returns'] = df['close'].pct_change()
    
    return df


# ═══════════════════════════════════════════════════════════════════════════════
# DASHBOARD
# ═══════════════════════════════════════════════════════════════════════════════
def render_dashboard(hist_df):
    df = add_indicators(hist_df)
    
    live_price = price_buffer[-1] if price_buffer else df['close'].iloc[-1]
    live_bid = bid_buffer[-1] if bid_buffer else live_price
    live_ask = ask_buffer[-1] if ask_buffer else live_price
    spread = live_ask - live_bid
    
    if len(price_buffer) > 10:
        recent = list(price_buffer)[-100:]
        live_high, live_low = max(recent), min(recent)
    else:
        live_high = live_low = live_price
    
    recent_trades = [t for t in trade_buffer if (datetime.utcnow() - t['time']).seconds < 60]
    buy_p = sum(t['size'] for t in recent_trades if t['side'] == 'BUY')
    sell_p = sum(t['size'] for t in recent_trades if t['side'] == 'SELL')
    ratio = buy_p / (sell_p + 1e-8)
    
    fig = plt.figure(figsize=(16, 18), facecolor=DARK_BG)
    fig.suptitle(f'{PRODUCT_ID} LIVE | ${live_price:,.2f} | Spread ${spread:.2f} | '
                 f'{"BULLISH" if ratio > 1.5 else "BEARISH" if ratio < 0.67 else "NEUTRAL"}',
                 color='#f0f6fc', fontsize=16, fontweight='bold', y=0.98)
    
    gs = fig.add_gridspec(4, 2, hspace=0.15, wspace=0.1,
                          left=0.06, right=0.94, top=0.95, bottom=0.03)
    
    # Main chart
    ax1 = fig.add_subplot(gs[0, :])
    ax1.fill_between(df.index, df['bb_upper'], df['bb_lower'], alpha=0.08, color=BLUE)
    ax1.plot(df.index, df['close'], color=TXT_CLR, linewidth=1.2, label='Close', zorder=3)
    ax1.plot(df.index, df['ema_9'], color=GOLD, linewidth=1, label='EMA 9', zorder=2)
    ax1.plot(df.index, df['ema_21'], color=PURPLE, linewidth=1, label='EMA 21', zorder=2)
    
    if time_buffer and price_buffer:
        lt, lp = list(time_buffer)[-50:], list(price_buffer)[-50:]
        ax1.plot(lt, lp, color=GREEN, linewidth=2, alpha=0.8, label='Live', zorder=4)
        ax1.scatter([lt[-1]], [lp[-1]], color=GREEN, s=120, zorder=5, edgecolors='white')
    
    ax1.set_title('Price + Live Feed', fontsize=11, loc='left')
    ax1.legend(fontsize=8, loc='upper left')
    ax1.set_ylabel('Price (USD)')
    
    # Volume
    ax2 = fig.add_subplot(gs[1, :])
    colors = [GREEN if c >= o else RED for c, o in zip(df['close'], df['open'])]
    ax2.bar(df.index, df['volume'], color=colors, alpha=0.5, width=0.003)
    ax2.set_title('Volume', fontsize=11, loc='left')
    
    # RSI + MACD
    ax3 = fig.add_subplot(gs[2, 0])
    ax3.plot(df.index, df['rsi'], color=BLUE, linewidth=1.2)
    ax3.axhline(70, color=RED, linestyle='--', alpha=0.5)
    ax3.axhline(30, color=GREEN, linestyle='--', alpha=0.5)
    ax3.set_title('RSI (14)', fontsize=10, loc='left')
    ax3.set_ylim(0, 100)
    
    ax4 = fig.add_subplot(gs[2, 1])
    ax4.plot(df.index, df['macd'], color=BLUE, linewidth=1, label='MACD')
    ax4.plot(df.index, df['macd_signal'], color=RED, linewidth=1, label='Signal')
    colors_macd = [GREEN if h >= 0 else RED for h in df['macd_hist'].fillna(0)]
    ax4.bar(df.index, df['macd_hist'], color=colors_macd, alpha=0.5, width=0.003)
    ax4.axhline(0, color=GRID_CLR, linewidth=0.5)
    ax4.set_title('MACD', fontsize=10, loc='left')
    ax4.legend(fontsize=7)
    
    # Live tick chart + stats
    ax5 = fig.add_subplot(gs[3, :])
    ax5.set_facecolor(DARK_BG)
    ax5.axis('off')
    
    if len(price_buffer) > 10:
        times = list(time_buffer)[-200:]
        prices = list(price_buffer)[-200:]
        # Mini chart inside stats panel
        left, bottom, width, height = 0.06, 0.08, 0.6, 0.12
        ax_mini = fig.add_axes([left, bottom, width, height])
        ax_mini.set_facecolor(PANEL_BG)
        ax_mini.plot(times, prices, color=GREEN, linewidth=1.5)
        ax_mini.fill_between(times, prices, alpha=0.1, color=GREEN)
        ax_mini.set_title('Last 200 Ticks', fontsize=10, color=TXT_CLR, loc='left')
        ax_mini.tick_params(colors=TXT_CLR, labelsize=7)
        for spine in ax_mini.spines.values():
            spine.set_color(GRID_CLR)
    
    # Stats text
    stats = [
        f"Price: ${live_price:,.2f} | Bid: ${live_bid:,.2f} | Ask: ${live_ask:,.2f} | Spread: ${spread:.2f}",
        f"24h Range: ${live_low:,.2f} - ${live_high:,.2f} | Buffer: {len(price_buffer)} ticks",
        f"Buy: {buy_p:.2f} | Sell: {sell_p:.2f} | Ratio: {ratio:.2f} | Trades/min: {len(recent_trades)}",
        f"Last Update: {datetime.utcnow().strftime('%H:%M:%S')} UTC | WebSocket: {'ON' if ws_running else 'OFF'}"
    ]
    
    for i, s in enumerate(stats):
        color = GREEN if 'BULLISH' in s or 'ON' in s else RED if 'BEARISH' in s or 'OFF' in s else GOLD
        fig.text(0.68, 0.18 - i*0.04, s, fontsize=10, color=color, family='monospace')
    
    return fig


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════
def run_live(duration_seconds=300, refresh=5):
    print('🚀 QUANTIS Live Crypto Dashboard')
    print(f'📊 {PRODUCT_ID}')
    print('─' * 50)
    
    # Start WebSocket
    print('⏳ Starting WebSocket...')
    ws_thread = threading.Thread(target=start_ws, daemon=True)
    ws_thread.start()
    time.sleep(3)
    
    if not ws_running:
        print("❌ WebSocket failed")
        return
    
    # Get historical data
    print('⏳ Fetching historical data...')
    hist_df = get_candles()
    if hist_df.empty:
        print("❌ No historical data available")
        return
    
    # Live loop
    print(f'⏳ Running for {duration_seconds}s, refresh every {refresh}s...')
    print('Press Ctrl+C to stop\n')
    
    start = time.time()
    try:
        while time.time() - start < duration_seconds:
            clear_output(wait=True)
            
            # Refresh historical data every 2 minutes
            if int(time.time() - start) % 120 == 0:
                new_df = get_candles()
                if not new_df.empty:
                    hist_df = new_df
            
            fig = render_dashboard(hist_df)
            display(fig)
            plt.close(fig)
            
            remaining = int(duration_seconds - (time.time() - start))
            print(f"⏱️  Refresh in {refresh}s... ({remaining}s remaining)")
            time.sleep(refresh)
            
    except KeyboardInterrupt:
        print('\n🛑 Stopped')
    finally:
        print(f'\n🏁 Total ticks: {len(price_buffer)}')


if __name__ == '__main__':
    run_live(duration_seconds=300, refresh=5)
