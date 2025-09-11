# news_bot_main.py - 改進版本支援多則新聞推播
from flask import Flask, request, jsonify
import os
import threading
import time
import re
from datetime import timedelta
from utils.time_utils import get_taiwan_time, get_taiwan_time_hhmm, get_taiwan_datetime
from utils.line_api import reply_message
from news_bot import NewsBot

app = Flask(__name__)

# 建立新聞Bot實例
news_bot = NewsBot()

# 背景服務管理
class BackgroundServices:
    def __init__(self):
        self.services = []
    
    def start_keep_alive(self):
        def keep_alive():
            import requests
            base_url = os.getenv('NEWS_BOT_BASE_URL', 'https://financial-news-bot.onrender.com')
            
            while True:
                try:
                    time.sleep(240)
                    response = requests.get(f'{base_url}/health', timeout=15)
                    
                    if response.status_code == 200:
                        print(f"✅ Keep-alive 成功 - {get_taiwan_time()}")
                    else:
                        print(f"⚠️ Keep-alive 警告: {response.status_code} - {get_taiwan_time()}")
                        
                except Exception as e:
                    print(f"❌ Keep-alive 錯誤: {e} - {get_taiwan_time()}")
                    time.sleep(60)
        
        thread = threading.Thread(target=keep_alive, daemon=True)
        thread.start()
        self.services.append('keep_alive')
        print("✅ 防休眠服務已啟動")

bg_services = BackgroundServices()

@app.route('/')
def home():
    return f"""
    <h1>財經新聞推播機器人 v2.1 (改進版)</h1>
    <p>🇹🇼 當前台灣時間：{get_taiwan_time()}</p>
    <p>📰 專門推播鉅亨網即時新聞</p>
    <p>📊 健康檢查：<a href="/health">/health</a></p>
    
    <h2>🆕 新功能：</h2>
    <ul>
        <li>✅ 支援多則新聞推播 - 不再漏掉任何新聞</li>
        <li>✅ 完整新聞連結 - 可直接點擊閱讀全文</li>
        <li>✅ 推播數量控制 - 避免洗版</li>
    </ul>
    
    <h2>新聞分類：</h2>
    <ul>
        <li>台股模式 - 專注台股新聞</li>
        <li>美股模式 - 專注美股新聞</li>
        <li>綜合模式 - 全部財經新聞</li>
    </ul>
    
    <h2>基本指令：</h2>
    <ul>
        <li>開始新聞推播</li>
        <li>停止新聞推播</li>
        <li>新聞狀態</li>
        <li>測試新聞</li>
        <li>設定推播數量 [數量] - 設定單次最大推播則數</li>
    </ul>
    """

@app.route('/health')
def health():
    return jsonify({
        'status': 'healthy',
        'taiwan_time': get_taiwan_time(),
        'version': 'news_bot_v2.1_improved_multi_news',
        'services': bg_services.services,
        'news_monitoring': {
            'is_running': news_bot.is_running,
            'user_id': news_bot.user_id,
            'last_check_time': news_bot.last_check_time.isoformat() if news_bot.last_check_time else None,
            'check_interval_minutes': news_bot.check_interval // 60,
            'news_category': news_bot.news_category,
            'push_time_range': f"{news_bot.start_time.strftime('%H:%M')}-{news_bot.end_time.strftime('%H:%M')}",
            'weekend_enabled': news_bot.weekend_enabled,
            'max_news_per_check': news_bot.max_news_per_check,
            'news_interval_seconds': news_bot.news_interval
        }
    })

def handle_news_command(message_text, user_id):
    """處理新聞相關指令（包含改進功能）"""
    try:
        # 基本控制指令
        if message_text in ['開始新聞推播', '開始推播', '啟動新聞']:
            return news_bot.start_news_monitoring(user_id)
        
        elif message_text in ['停止新聞推播', '停止推播', '關閉新聞']:
            return news_bot.stop_news_monitoring()
        
        elif message_text in ['新聞狀態', '狀態查詢', '監控狀態']:
            return news_bot.get_news_status()
        
        elif message_text in ['測試新聞', '新聞測試']:
            # 手動抓取最新新聞進行測試
            news_list = news_bot.fetch_cnyes_news()
            if news_list:
                latest_news = news_list[0]
                formatted_message = news_bot.format_news_message(latest_news)
                return f"📰 測試新聞推播\n\n{formatted_message}"
            else:
                return "❌ 無法抓取新聞進行測試"
        
        elif message_text in ['測試多則', '測試多則新聞']:
            # 測試多則新聞推播
            news_list = news_bot.fetch_cnyes_news()
            if news_list and len(news_list) >= 2:
                test_news = news_list[:2]  # 取前兩則進行測試
                success_count = news_bot.send_multiple_news_notifications(test_news)
                return f"📰 多則新聞測試完成\n✅ 成功推播 {success_count}/{len(test_news)} 則新聞"
            else:
                return "❌ 無法抓取足夠新聞進行多則測試"
        
        # 新聞分類切換指令
        elif message_text in ['台股模式', '台股新聞', '切換台股']:
            result = news_bot.set_news_category('tw_stock')
            return f"✅ {result}\n📈 現在將推播台股相關新聞"
        
        elif message_text in ['美股模式', '美股新聞', '切換美股']:
            result = news_bot.set_news_category('us_stock')
            return f"✅ {result}\n🇺🇸 現在將推播美股相關新聞"
        
        elif message_text in ['綜合模式', '綜合新聞', '全部新聞']:
            result = news_bot.set_news_category('headline')
            return f"✅ {result}\n📰 現在將推播綜合財經新聞"
        
        elif message_text in ['外匯模式', '外匯新聞']:
            result = news_bot.set_news_category('forex')
            return f"✅ {result}\n💱 現在將推播外匯相關新聞"
        
        elif message_text in ['期貨模式', '期貨新聞']:
            result = news_bot.set_news_category('futures')
            return f"✅ {result}\n📊 現在將推播期貨相關新聞"
        
        elif message_text in ['新聞分類', '分類說明', '分類幫助']:
            return news_bot.get_category_help()
        
        # 設定指令
        elif message_text.startswith('設定間隔'):
            # 格式: 設定間隔 10
            match = re.search(r'設定間隔\s+(\d+)', message_text)
            if match:
                minutes = int(match.group(1))
                return news_bot.set_check_interval(minutes)
            else:
                return "❌ 格式錯誤\n💡 正確格式：設定間隔 [分鐘]\n例如：設定間隔 10"
        
        elif message_text.startswith('設定推播數量'):
            # 格式: 設定推播數量 3
            match = re.search(r'設定推播數量\s+(\d+)', message_text)
            if match:
                max_count = int(match.group(1))
                return news_bot.set_max_news_per_check(max_count)
            else:
                return "❌ 格式錯誤\n💡 正確格式：設定推播數量 [數量]\n例如：設定推播數量 3"
        
        elif message_text.startswith('設定時間'):
            # 格式: 設定時間 9 0 21 0
            match = re.search(r'設定時間\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)', message_text)
            if match:
                start_hour = int(match.group(1))
                start_minute = int(match.group(2))
                end_hour = int(match.group(3))
                end_minute = int(match.group(4))
                
                # 驗證時間格式
                if not (0 <= start_hour <= 23 and 0 <= start_minute <= 59 and 
                        0 <= end_hour <= 23 and 0 <= end_minute <= 59):
                    return "❌ 時間格式錯誤，請確認時間範圍正確"
                
                return news_bot.set_time_range(start_hour, start_minute, end_hour, end_minute)
            else:
                return "❌ 格式錯誤\n💡 正確格式：設定時間 [開始時] [開始分] [結束時] [結束分]\n例如：設定時間 9 0 21 0"
        
        elif message_text in ['切換週末', '週末設定', '週末推播']:
            return news_bot.toggle_weekend()
        
        elif message_text in ['新聞設定', '設定說明', '設定幫助']:
            return """⚙️ 新聞機器人設定說明 (改進版)

📰 新聞分類：
• 台股模式 - 專注台股新聞
• 美股模式 - 專注美股新聞  
• 綜合模式 - 全部財經新聞
• 外匯模式 - 外匯相關新聞
• 期貨模式 - 期貨相關新聞

⏰ 時間設定：
• 設定間隔 [分鐘] - 調整檢查頻率(1-60分鐘)
• 設定時間 [開始時] [開始分] [結束時] [結束分] - 推播時間範圍
• 切換週末 - 開啟/關閉週末推播

📊 推播控制 (新功能)：
• 設定推播數量 [數量] - 單次最大推播則數(1-10則)
• 系統會自動間隔2秒推播多則新聞，避免洗版

🔗 完整連結 (新功能)：
• 每則新聞都包含完整閱讀連結
• 可直接點擊查看鉅亨網原文

💡 推薦設定：
台股模式 + 設定時間 9 0 13 30 + 設定推播數量 3
美股模式 + 設定時間 21 30 4 0 + 設定推播數量 5"""
        
        elif message_text in ['新聞幫助', '指令說明', '說明']:
            return """📰 新聞機器人指令說明 (v2.1改進版)

🔔 基本控制：
• 開始新聞推播 - 啟動自動新聞監控
• 停止新聞推播 - 停止自動新聞監控
• 新聞狀態 - 查看監控狀態和設定
• 測試新聞 - 手動抓取最新新聞
• 測試多則 - 測試多則新聞推播功能

📈 新聞分類：
• 台股模式 - 專注台股新聞
• 美股模式 - 專注美股新聞
• 綜合模式 - 全部財經新聞

⚙️ 時間設定：
• 設定間隔 [分鐘] - 調整檢查頻率
• 設定時間 [開始時] [開始分] [結束時] [結束分] - 推播時間
• 切換週末 - 週末推播開關

📊 推播控制 (🆕新功能)：
• 設定推播數量 [數量] - 控制單次最大推播則數

ℹ️ 說明文檔：
• 新聞設定 - 詳細設定說明
• 新聞分類 - 分類功能說明

🆕 改進功能：
✅ 多則新聞推播 - 5分鐘內所有新聞都不會漏掉
✅ 完整新聞連結 - 每則新聞都有閱讀全文連結
✅ 推播數量控制 - 避免一次推播太多新聞
✅ 智能時間間隔 - 多則新聞間隔推播避免洗版

💡 建議使用：
1. 選擇 台股模式 或 美股模式
2. 設定推播數量 3 (推薦)
3. 開始新聞推播

📰 新聞來源：鉅亨網
🕐 當前時間：""" + get_taiwan_time()
        
        else:
            return f"""歡迎使用財經新聞機器人！(v2.1改進版)

🆕 新功能亮點：
✅ 多則新聞推播 - 再也不會漏掉任何新聞
✅ 完整新聞連結 - 直接點擊閱讀全文
✅ 推播數量控制 - 避免訊息洗版

📰 快速開始：
• 台股模式 - 專注台股投資新聞
• 美股模式 - 專注美股投資新聞
• 設定推播數量 3 - 控制推播則數
• 開始新聞推播 - 立即啟動監控

📊 功能特色：
✅ 智能分類 - 台股/美股專區
✅ 時間控制 - 設定推播時間範圍
✅ 週末開關 - 控制週末是否推播
✅ 頻率調整 - 自訂檢查間隔
✅ 多則推播 - 不漏掉任何新新聞
✅ 完整連結 - 直接閱讀原文

🕐 當前時間：{get_taiwan_time()}

💡 輸入「新聞幫助」查看完整指令"""
    
    except Exception as e:
        print(f"❌ 處理新聞指令失敗: {e}")
        return f"❌ 指令處理失敗，請稍後再試\n🕐 {get_taiwan_time()}"

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.get_json()
        
        for event in data.get('events', []):
            if event['type'] == 'message' and event['message']['type'] == 'text':
                reply_token = event['replyToken']
                message_text = event['message']['text']
                user_id = event['source']['userId']
                
                print(f"📨 新聞Bot收到訊息: {message_text} - {get_taiwan_time()}")
                
                # 處理新聞指令
                reply_text = handle_news_command(message_text, user_id)
                reply_message(reply_token, reply_text, bot_type='news')
        
        return 'OK', 200
    
    except Exception as e:
        print(f"❌ Webhook 處理錯誤: {e} - {get_taiwan_time()}")
        return 'OK', 200

@app.route('/test/fetch-news')
def test_fetch_news():
    """測試新聞抓取功能"""
    try:
        news_list = news_bot.fetch_cnyes_news()
        
        if news_list:
            return jsonify({
                'success': True,
                'news_count': len(news_list),
                'current_category': news_bot.news_category,
                'latest_news': {
                    'title': news_list[0].get('title', ''),
                    'newsId': news_list[0].get('newsId', ''),
                    'publishAt': news_list[0].get('publishAt', ''),
                    'news_url': f"https://news.cnyes.com/news/id/{news_list[0].get('newsId', '')}"
                } if news_list else None,
                'timestamp': get_taiwan_time()
            })
        else:
            return jsonify({
                'success': False,
                'error': '無法抓取新聞',
                'current_category': news_bot.news_category,
                'timestamp': get_taiwan_time()
            })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': get_taiwan_time()
        })

@app.route('/test/format-news')
def test_format_news():
    """測試新聞格式化功能"""
    try:
        news_list = news_bot.fetch_cnyes_news()
        
        if news_list:
            latest_news = news_list[0]
            formatted_message = news_bot.format_news_message(latest_news)
            
            return jsonify({
                'success': True,
                'current_category': news_bot.news_category,
                'raw_news': latest_news,
                'formatted_message': formatted_message,
                'news_url': f"https://news.cnyes.com/news/id/{latest_news.get('newsId', '')}",
                'timestamp': get_taiwan_time()
            })
        else:
            return jsonify({
                'success': False,
                'error': '無法抓取新聞進行格式化測試',
                'current_category': news_bot.news_category,
                'timestamp': get_taiwan_time()
            })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': get_taiwan_time()
        })

@app.route('/test/multi-news')
def test_multi_news():
    """測試多則新聞功能"""
    try:
        # 模擬檢查新新聞
        new_news_list = news_bot.check_new_news()
        
        return jsonify({
            'success': True,
            'current_category': news_bot.news_category,
            'new_news_count': len(new_news_list),
            'max_news_per_check': news_bot.max_news_per_check,
            'news_interval_seconds': news_bot.news_interval,
            'last_check_time': news_bot.last_check_time.isoformat() if news_bot.last_check_time else None,
            'sample_news': [
                {
                    'title': news.get('title', '')[:50] + '...' if len(news.get('title', '')) > 50 else news.get('title', ''),
                    'newsId': news.get('newsId', ''),
                    'publishAt': news.get('publishAt', ''),
                    'news_url': f"https://news.cnyes.com/news/id/{news.get('newsId', '')}"
                } for news in new_news_list[:3]
            ] if new_news_list else [],
            'timestamp': get_taiwan_time()
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': get_taiwan_time()
        })

@app.route('/test/category/<category>')
def test_category(category):
    """測試不同分類的新聞"""
    try:
        old_category = news_bot.news_category
        news_bot.news_category = category
        
        news_list = news_bot.fetch_cnyes_news()
        
        # 恢復原分類
        news_bot.news_category = old_category
        
        return jsonify({
            'success': True,
            'test_category': category,
            'news_count': len(news_list) if news_list else 0,
            'sample_titles': [news.get('title', '') for news in news_list[:3]] if news_list else [],
            'sample_urls': [f"https://news.cnyes.com/news/id/{news.get('newsId', '')}" for news in news_list[:3]] if news_list else [],
            'timestamp': get_taiwan_time()
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': get_taiwan_time()
        })

def initialize_app():
    print("🚀 財經新聞推播機器人 v2.1 (改進版) 啟動中...")
    print(f"🇹🇼 台灣時間：{get_taiwan_time()}")
    
    bg_services.start_keep_alive()
    
    print("=" * 60)
    print("📰 新聞推播機器人：✅ 已啟動")
    print("🔄 基本功能：開始推播、停止推播、狀態查詢、測試新聞")
    print("📈 分類模式：台股模式、美股模式、綜合模式")
    print("🆕 改進功能：")
    print("   ✅ 多則新聞推播 - 5分鐘內所有新聞都不漏掉")
    print("   ✅ 完整新聞連結 - 每則新聞都有閱讀全文連結")
    print("   ✅ 推播數量控制 - 可設定單次最大推播則數")
    print("   ✅ 智能推播間隔 - 多則新聞間自動間隔避免洗版")
    print("📊 測試端點：/test/fetch-news、/test/format-news、/test/multi-news")
    print("=" * 60)
    print("🎉 系統初始化完成！")

if __name__ == '__main__':
    initialize_app()
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port)
