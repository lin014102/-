"""
stock_analyzer.py - 股票技術分析模組
專注於技術分析、支撐壓力計算、買賣建議
完全獨立於記帳系統
"""
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import pytz

TAIWAN_TZ = pytz.timezone('Asia/Taipei')

class StockAnalyzer:
    """股票技術分析器"""
    
    def __init__(self):
        """初始化分析器"""
        self.cache = {}  # 簡單的快取機制
        self.cache_timeout = 300  # 5分鐘快取
    
    def get_stock_data(self, stock_code, period='3mo'):
        """取得股票歷史資料"""
        try:
            # 格式化台股代號
            if not stock_code.endswith('.TW') and not stock_code.endswith('.TWO'):
                formatted_code = f"{stock_code}.TW"
            else:
                formatted_code = stock_code
            
            # 檢查快取
            cache_key = f"{formatted_code}_{period}"
            if cache_key in self.cache:
                cached_time, cached_data = self.cache[cache_key]
                if (datetime.now() - cached_time).seconds < self.cache_timeout:
                    return cached_data
            
            # 下載資料
            stock = yf.Ticker(formatted_code)
            df = stock.history(period=period)
            
            if df.empty:
                return None
            
            # 儲存快取
            self.cache[cache_key] = (datetime.now(), df)
            return df
            
        except Exception as e:
            print(f"取得股票資料失敗: {e}")
            return None
    
    def calculate_support_resistance(self, df, window=20):
        """計算支撐壓力位"""
        if df is None or df.empty:
            return None
        
        supports = []
        resistances = []
        
        # 1. 前波高低點法
        for i in range(window, len(df) - window):
            # 找低點（支撐）
            if df['Low'].iloc[i] == df['Low'].iloc[i-window:i+window].min():
                supports.append(df['Low'].iloc[i])
            
            # 找高點（壓力）
            if df['High'].iloc[i] == df['High'].iloc[i-window:i+window].max():
                resistances.append(df['High'].iloc[i])
        
        # 2. 均線支撐壓力
        ma5 = df['Close'].rolling(window=5).mean().iloc[-1]
        ma10 = df['Close'].rolling(window=10).mean().iloc[-1]
        ma20 = df['Close'].rolling(window=20).mean().iloc[-1]
        ma60 = df['Close'].rolling(window=60).mean().iloc[-1]
        
        current_price = df['Close'].iloc[-1]
        
        # 判斷均線是支撐還是壓力
        mas = [ma5, ma10, ma20, ma60]
        for ma in mas:
            if pd.notna(ma):
                if ma < current_price:
                    supports.append(ma)
                else:
                    resistances.append(ma)
        
        # 3. 成交量密集區
        volume_price = df.groupby(pd.cut(df['Close'], bins=30))['Volume'].sum()
        top_volume_prices = volume_price.nlargest(3)
        
        for interval in top_volume_prices.index:
            mid_price = (interval.left + interval.right) / 2
            if mid_price < current_price:
                supports.append(mid_price)
            else:
                resistances.append(mid_price)
        
        # 整理並去重
        supports = sorted(list(set([round(s, 2) for s in supports if pd.notna(s)])), reverse=True)
        resistances = sorted(list(set([round(r, 2) for r in resistances if pd.notna(r)])))
        
        return {
            'supports': supports[:5],  # 取前5個最近的支撐
            'resistances': resistances[:5],  # 取前5個最近的壓力
            'ma5': round(ma5, 2) if pd.notna(ma5) else None,
            'ma10': round(ma10, 2) if pd.notna(ma10) else None,
            'ma20': round(ma20, 2) if pd.notna(ma20) else None,
            'ma60': round(ma60, 2) if pd.notna(ma60) else None
        }
    
    def calculate_indicators(self, df):
        """計算技術指標"""
        if df is None or df.empty:
            return None
        
        indicators = {}
        
        # RSI
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        indicators['rsi'] = round(rsi.iloc[-1], 2) if pd.notna(rsi.iloc[-1]) else None
        
        # KD
        low_14 = df['Low'].rolling(window=14).min()
        high_14 = df['High'].rolling(window=14).max()
        rsv = (df['Close'] - low_14) / (high_14 - low_14) * 100
        k = rsv.ewm(com=2).mean()
        d = k.ewm(com=2).mean()
        indicators['k'] = round(k.iloc[-1], 2) if pd.notna(k.iloc[-1]) else None
        indicators['d'] = round(d.iloc[-1], 2) if pd.notna(d.iloc[-1]) else None
        
        # MACD
        ema12 = df['Close'].ewm(span=12).mean()
        ema26 = df['Close'].ewm(span=26).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9).mean()
        indicators['macd'] = round(macd.iloc[-1], 2) if pd.notna(macd.iloc[-1]) else None
        indicators['macd_signal'] = round(signal.iloc[-1], 2) if pd.notna(signal.iloc[-1]) else None
        
        return indicators
    
    def analyze_buy_signals(self, df, support_resistance, indicators):
        """分析買入訊號"""
        if df is None or not support_resistance or not indicators:
            return []
        
        signals = []
        current_price = df['Close'].iloc[-1]
        
        # 1. 支撐位附近
        supports = support_resistance['supports']
        for support in supports:
            diff_percent = ((current_price - support) / support) * 100
            if -2 <= diff_percent <= 0:  # 在支撐位±2%內
                signals.append({
                    'type': 'support',
                    'price': support,
                    'strength': 3,
                    'reason': f'接近支撐位 {support}元'
                })
        
        # 2. 超賣訊號
        if indicators.get('rsi') and indicators['rsi'] < 30:
            signals.append({
                'type': 'oversold_rsi',
                'strength': 2,
                'reason': f'RSI超賣 ({indicators["rsi"]})'
            })
        
        if indicators.get('k') and indicators['k'] < 20:
            signals.append({
                'type': 'oversold_kd',
                'strength': 2,
                'reason': f'KD超賣 (K={indicators["k"]})'
            })
        
        # 3. 均線支撐
        mas = {
            'MA5': support_resistance.get('ma5'),
            'MA10': support_resistance.get('ma10'),
            'MA20': support_resistance.get('ma20'),
            'MA60': support_resistance.get('ma60')
        }
        
        for ma_name, ma_value in mas.items():
            if ma_value and ma_value < current_price:
                diff_percent = ((current_price - ma_value) / ma_value) * 100
                if diff_percent <= 2:
                    signals.append({
                        'type': 'ma_support',
                        'price': ma_value,
                        'strength': 2,
                        'reason': f'接近{ma_name}支撐 ({ma_value}元)'
                    })
        
        # 4. 下影線判斷
        last_candle = df.iloc[-1]
        body = abs(last_candle['Close'] - last_candle['Open'])
        lower_shadow = min(last_candle['Open'], last_candle['Close']) - last_candle['Low']
        
        if lower_shadow > body * 2:
            signals.append({
                'type': 'hammer',
                'strength': 2,
                'reason': '出現長下影線（買盤支撐）'
            })
        
        return signals
    
    def analyze_sell_signals(self, df, support_resistance, indicators):
        """分析賣出訊號"""
        if df is None or not support_resistance or not indicators:
            return []
        
        signals = []
        current_price = df['Close'].iloc[-1]
        
        # 1. 壓力位附近
        resistances = support_resistance['resistances']
        for resistance in resistances:
            diff_percent = ((resistance - current_price) / current_price) * 100
            if 0 <= diff_percent <= 2:
                signals.append({
                    'type': 'resistance',
                    'price': resistance,
                    'strength': 3,
                    'reason': f'接近壓力位 {resistance}元'
                })
        
        # 2. 超買訊號
        if indicators.get('rsi') and indicators['rsi'] > 70:
            signals.append({
                'type': 'overbought_rsi',
                'strength': 2,
                'reason': f'RSI超買 ({indicators["rsi"]})'
            })
        
        if indicators.get('k') and indicators['k'] > 80:
            signals.append({
                'type': 'overbought_kd',
                'strength': 2,
                'reason': f'KD超買 (K={indicators["k"]})'
            })
        
        # 3. 均線壓力
        mas = {
            'MA5': support_resistance.get('ma5'),
            'MA10': support_resistance.get('ma10'),
            'MA20': support_resistance.get('ma20'),
            'MA60': support_resistance.get('ma60')
        }
        
        for ma_name, ma_value in mas.items():
            if ma_value and ma_value > current_price:
                diff_percent = ((ma_value - current_price) / current_price) * 100
                if diff_percent <= 2:
                    signals.append({
                        'type': 'ma_resistance',
                        'price': ma_value,
                        'strength': 2,
                        'reason': f'接近{ma_name}壓力 ({ma_value}元)'
                    })
        
        # 4. 上影線判斷
        last_candle = df.iloc[-1]
        body = abs(last_candle['Close'] - last_candle['Open'])
        upper_shadow = last_candle['High'] - max(last_candle['Open'], last_candle['Close'])
        
        if upper_shadow > body * 2:
            signals.append({
                'type': 'shooting_star',
                'strength': 2,
                'reason': '出現長上影線（賣壓出現）'
            })
        
        # 5. KD高檔死叉
        if indicators.get('k') and indicators.get('d'):
            if indicators['k'] < indicators['d'] and indicators['k'] > 80:
                signals.append({
                    'type': 'kd_death_cross',
                    'strength': 3,
                    'reason': f'KD高檔死叉 (K={indicators["k"]}, D={indicators["d"]})'
                })
        
        return signals
    
    def generate_suggestions(self, buy_signals, sell_signals, support_resistance, current_price):
        """生成買賣建議"""
        suggestions = {
            'buy_points': [],
            'sell_points': [],
            'stop_loss': None,
            'action': 'hold'
        }
        
        # 計算買賣訊號強度
        buy_strength = sum([s['strength'] for s in buy_signals])
        sell_strength = sum([s['strength'] for s in sell_signals])
        
        # 買點建議
        if buy_signals:
            # 找最強的支撐位
            support_signals = [s for s in buy_signals if s['type'] in ['support', 'ma_support']]
            if support_signals:
                primary_support = min([s['price'] for s in support_signals if 'price' in s])
                suggestions['buy_points'].append({
                    'price': round(primary_support, 2),
                    'priority': 'high',
                    'reasons': [s['reason'] for s in buy_signals[:3]]
                })
        
        # 賣點建議
        if sell_signals:
            # 找最近的壓力位
            resistance_signals = [s for s in sell_signals if s['type'] in ['resistance', 'ma_resistance']]
            if resistance_signals:
                primary_resistance = min([s['price'] for s in resistance_signals if 'price' in s])
                suggestions['sell_points'].append({
                    'price': round(primary_resistance, 2),
                    'priority': 'high',
                    'reasons': [s['reason'] for s in sell_signals[:3]]
                })
        
        # 停損建議
        if support_resistance['supports']:
            nearest_support = max([s for s in support_resistance['supports'] if s < current_price], default=None)
            if nearest_support:
                stop_loss = round(nearest_support * 0.97, 2)  # 支撐下方3%
                suggestions['stop_loss'] = stop_loss
        
        # 操作建議
        if buy_strength >= 5 and buy_strength > sell_strength:
            suggestions['action'] = 'buy'
        elif sell_strength >= 5 and sell_strength > buy_strength:
            suggestions['action'] = 'sell'
        elif buy_strength >= 3 and sell_strength < 3:
            suggestions['action'] = 'consider_buy'
        elif sell_strength >= 3 and buy_strength < 3:
            suggestions['action'] = 'consider_sell'
        
        return suggestions
    
    def analyze(self, stock_code, stock_name=None):
        """完整技術分析"""
        # 取得資料
        df = self.get_stock_data(stock_code)
        if df is None or df.empty:
            return f"無法取得 {stock_code} 的股票資料"
        
        current_price = df['Close'].iloc[-1]
        
        # 計算支撐壓力
        sr = self.calculate_support_resistance(df)
        if not sr:
            return f"無法計算 {stock_code} 的支撐壓力位"
        
        # 計算指標
        indicators = self.calculate_indicators(df)
        
        # 分析訊號
        buy_signals = self.analyze_buy_signals(df, sr, indicators)
        sell_signals = self.analyze_sell_signals(df, sr, indicators)
        
        # 生成建議
        suggestions = self.generate_suggestions(buy_signals, sell_signals, sr, current_price)
        
        # 格式化輸出 - 白話版
        display_name = stock_name if stock_name else stock_code
        result = f"📊 {display_name} ({stock_code}) 技術分析\n\n"
        result += f"💹 目前價格：{current_price:.2f}元\n\n"
        
        # 支撐位 - 白話版
        result += "🟢 支撐位（可能跌不下去的價位）\n"
        if sr['supports']:
            labels = ["👈 優先買點", "備用買點", "最後防線"]
            for i, support in enumerate(sr['supports'][:3], 1):
                diff = ((current_price - support) / support) * 100
                strength = "⭐⭐⭐" if i == 1 else "⭐⭐" if i == 2 else "⭐"
                label = labels[i-1] if i <= len(labels) else ""
                result += f"{strength} {support:.0f}元 ({diff:.1f}%) {label}\n"
        else:
            result += "暫無明確支撐位\n"
        
        # 壓力位 - 白話版
        result += "\n🔴 壓力位（可能漲不上去的價位）\n"
        if sr['resistances']:
            for i, resistance in enumerate(sr['resistances'][:3], 1):
                diff = ((resistance - current_price) / current_price) * 100
                strength = "⭐⭐⭐" if i == 1 else "⭐⭐" if i == 2 else "⭐"
                label = "👈 建議先賣" if i == 1 else ""
                result += f"{strength} {resistance:.0f}元 (+{diff:.1f}%) {label}\n"
        else:
            result += "暫無明確壓力位\n"
        
        # 技術狀態 - 白話版
        result += f"\n📈 技術狀態\n"
        
        # 判斷趨勢
        if indicators.get('rsi') and indicators.get('k'):
            rsi = indicators['rsi']
            k = indicators['k']
            
            if rsi > 70 or k > 80:
                result += "- 最近漲很快，有點過熱\n"
                if rsi > 75 and k > 85:
                    result += "- 短期買盤強，但小心回檔"
                else:
                    result += "- 建議觀望，等回檔再進場"
            elif rsi < 30 or k < 20:
                result += "- 跌很深了，可能快止跌\n"
                result += "- 可以開始注意買點"
            else:
                result += "- 目前處於正常範圍\n"
                result += "- 可以耐心等待機會"
            
            result += f" (RSI {rsi:.1f} / KD {k:.1f}"
            if rsi > 70 or k > 80:
                result += " 偏高)\n"
            elif rsi < 30 or k < 20:
                result += " 偏低)\n"
            else:
                result += " 正常)\n"
        
        # RSI/KD 說明
        result += "\n💬 RSI、KD 是什麼？\n"
        result += "看股票「漲太快或跌太快」的指標\n"
        result += "> 70-80 = 漲太快，要小心\n"
        result += "< 20-30 = 跌太深，可能反彈\n"
        
        # 操作建議 - 白話版
        result += f"\n💡 操作建議\n"
        action_text = {
            'buy': '🟢 建議買進\n逢低可以分批進場',
            'sell': '🔴 建議賣出\n有賺先獲利，等回檔再買',
            'consider_buy': '🟡 可考慮買進\n等跌到支撐再買',
            'consider_sell': '🟡 可考慮賣出\n漲到壓力可先賣一些',
            'hold': '⚪ 建議觀望\n等更明確的訊號'
        }
        result += f"{action_text.get(suggestions['action'], '⚪ 建議觀望')}\n"
        
        # 停損
        if suggestions['stop_loss']:
            result += f"\n🛑 停損：{suggestions['stop_loss']:.0f}元\n"
        
        result += f"\n⏰ {datetime.now(TAIWAN_TZ).strftime('%Y/%m/%d %H:%M')}"
        result += "\n⚠️ 僅供參考，非投資建議"
        
        return result
    
    def quick_analysis(self, stock_code, stock_name=None):
        """快速分析（簡化版）"""
        df = self.get_stock_data(stock_code, period='1mo')
        if df is None or df.empty:
            return None
        
        current_price = df['Close'].iloc[-1]
        sr = self.calculate_support_resistance(df, window=10)
        
        if not sr:
            return None
        
        nearest_support = max([s for s in sr['supports'] if s < current_price], default=None)
        nearest_resistance = min([r for r in sr['resistances'] if r > current_price], default=None)
        
        return {
            'current_price': round(current_price, 2),
            'support': round(nearest_support, 2) if nearest_support else None,
            'resistance': round(nearest_resistance, 2) if nearest_resistance else None
        }


# 建立全域實例
stock_analyzer = StockAnalyzer()

# 對外接口
def analyze_stock(stock_code, stock_name=None):
    """分析股票 - 對外接口"""
    return stock_analyzer.analyze(stock_code, stock_name)

def quick_analyze_stock(stock_code, stock_name=None):
    """快速分析 - 對外接口"""
    return stock_analyzer.quick_analysis(stock_code, stock_name)
