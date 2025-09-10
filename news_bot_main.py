# news_bot_main.py - 支援設定指令
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
    <h1>財經新聞推播機器人</h1>
    <p>🇹🇼 當前台灣時間：{get_taiwan_time()}</p>
    <p>📰 專門推播鉅亨網即時新聞</p>
    <p>📊 健康檢查：<a href="/health">/health</a></p>
    <h2>基本指令：</h2>
    <ul>
        <li>開始新聞推播</li>
        <li>停止新聞推播</li>
        <li>新聞狀態</li>
        <li>測試新聞</li>
        <li>新聞設定</li>
    </ul>
    <h2>設定指令：</h2>
    <ul>
        <li>設定間隔 [分鐘]</li>
        <li>設定時間 [開始時] [開始分] [結束時] [結束分]</li>
        <li>設定關鍵字 [關鍵字1,關鍵字2]</li>
        <li>清空關鍵字</li>
        <li>切換週末</li>
    </ul>
    """

@app.route('/health')
def health():
    return jsonify({
        'status': 'healthy',
        'taiwan_time': get_taiwan_time(),
        'version': 'news_bot_v2.0_optimized',
        'services': bg_services.services,
        'news_monitoring': {
            'is_running': news_bot.is_running,
            'user_id': news_bot.user_id,
            'last_news_id': news_bot.last_news_id,
            'check_interval_minutes': news_bot.check_interval // 60,
            'keywords_filter': news_bot.keywords_filter,
            'push_time_range': f"{news_bot.start_time.strftime('%H:%M')}-{news_bot.end_time.strftime('%H:%M')}",
            'weekend_enabled': news_bot.weekend_enabled
        }
    })

def handle_news_command(message_text, user_id):
    """處理新聞相關指令（包含設定指令）"""
    try:
        # 基本控制指令
        if message_text in ['開始新聞推播', '開始推播', '啟動新聞']:
            return news_bot.start_news_monitoring(user_id)
        
        elif message_text in ['停止新聞推播', '停止推播', '關閉新聞']:
            return news_bot.stop_news_monitoring()
        
        elif message_text in ['新聞狀態', '狀態查詢', '監控狀態']:
            return news_bot.get_news_status()
        
        elif message_text in ['測試新聞', '新聞測試']:
            # 手動抓取一則最新新聞
            news_list = news_bot.fetch_cnyes_news()
            if news_list:
                latest_news = news_list[0]
                formatted_message = news_bot.format_news_message(latest_news)
                return f"📰 測試新聞推播\n\n{formatted_message}"
            else:
                return "❌ 無法抓取新聞進行測試"
        
        # 設定指令
        elif message_text.startswith('設定間隔'):
            # 格式: 設定間隔 10
            match = re.search(r'設定間隔\s+(\d+)', message_text)
            if match:
                minutes = int(match.group(1))
                return news_bot.set_check_interval(minutes)
            else:
                return "❌ 格式錯誤\n💡 正確格式：設定間隔 [分鐘]\n例如：設定間隔 10"
        
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
        
        elif message_text.startswith('設定關鍵字'):
            # 格式: 設定關鍵字 台積電,聯發科,鴻海
            keywords_part = message_text.replace('設定關鍵字', '').strip()
            if keywords_part:
                return news_bot.set_keywords_filter(keywords_part)
            else:
                return "❌ 請指定關鍵字\n💡 正確格式：設定關鍵字 [關鍵字1,關鍵字2]\n例如：設定關鍵字 台積電,聯發科,鴻海"
        
        elif message_text in ['清空關鍵字', '移除關鍵字', '刪除關鍵字']:
            return news_bot.set_keywords_filter([])
        
        elif message_text in ['切換週末', '週末設定', '週末推播']:
            return news_bot.toggle_weekend()
        
        elif message_text in ['新聞設定', '設定說明', '設定幫助']:
            return news_bot.get_settings_help()
        
        elif message_text in ['新聞幫助', '指令說明', '說明']:
            return """📰 新聞機器人指令說明

🔔 基本控制：
• 開始新聞推播 - 啟動自動新聞監控
• 停止新聞推播 - 停止自動新聞監控
• 新聞狀態 - 查看監控狀態和設定
• 測試新聞 - 手動抓取最新新聞

⚙️ 進階設定：
• 設定間隔 [分鐘] - 調整檢查頻率(1-60分鐘)
• 設定時間 [開始時] [開始分] [結束時] [結束分] - 設定推播時間範圍
• 設定關鍵字 [關鍵字1,關鍵字2] - 只推播包含特定關鍵字的新聞
• 清空關鍵字 - 移除關鍵字過濾
• 切換週末 - 開啟/關閉週末推播

ℹ️ 說明文檔：
• 新聞設定 - 詳細設定說明
• 新聞幫助 - 顯示此說明

📰 新聞來源：鉅亨網
🕐 當前時間：""" + get_taiwan_time()
        
        else:
            return f"""歡迎使用財經新聞機器人！

📰 快速開始：
• 開始新聞推播 - 立即啟動監控
• 新聞狀態 - 查看當前設定
• 測試新聞 - 測試功能
• 新聞幫助 - 完整指令說明

⚙️ 智能功能：
✅ 關鍵字過濾 - 只推播感興趣的新聞
✅ 時間控制 - 設定推播時間範圍
✅ 週末開關 - 控制週末是否推播
✅ 頻率調整 - 自訂檢查間隔

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
                'latest_news': {
                    'title': news_list[0].get('title', ''),
                    'newsId': news_list[0].get('newsId', ''),
                    'publishAt': news_list[0].get('publishAt', '')
                } if news_list else None,
                'timestamp': get_taiwan_time()
            })
        else:
            return jsonify({
                'success': False,
                'error': '無法抓取新聞',
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
                'raw_news': latest_news,
                'formatted_message': formatted_message,
                'timestamp': get_taiwan_time()
            })
        else:
            return jsonify({
                'success': False,
                'error': '無法抓取新聞進行格式化測試',
                'timestamp': get_taiwan_time()
            })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': get_taiwan_time()
        })

@app.route('/test/check-filters')
def test_check_filters():
    """測試過濾條件"""
    try:
        # 檢查時間過濾
        time_ok, time_msg = news_bot.is_in_push_time()
        
        # 測試新聞關鍵字過濾
        news_list = news_bot.fetch_cnyes_news()
        keyword_results = []
        
        if news_list:
            for news in news_list[:3]:  # 測試前3則新聞
                keyword_ok, keyword_msg = news_bot.matches_keywords(news)
                keyword_results.append({
                    'title': news.get('title', ''),
                    'matches': keyword_ok,
                    'message': keyword_msg
                })
        
        return jsonify({
            'success': True,
            'time_filter': {
                'passes': time_ok,
                'message': time_msg
            },
            'keyword_filter': {
                'current_keywords': news_bot.keywords_filter,
                'test_results': keyword_results
            },
            'settings': {
                'check_interval_minutes': news_bot.check_interval // 60,
                'push_time_range': f"{news_bot.start_time.strftime('%H:%M')}-{news_bot.end_time.strftime('%H:%M')}",
                'weekend_enabled': news_bot.weekend_enabled
            },
            'timestamp': get_taiwan_time()
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': get_taiwan_time()
        })

def initialize_app():
    print("🚀 財經新聞推播機器人 v2.0 啟動中...")
    print(f"🇹🇼 台灣時間：{get_taiwan_time()}")
    
    bg_services.start_keep_alive()
    
    print("=" * 50)
    print("📰 新聞推播機器人：✅ 已啟動")
    print("🔄 基本功能：開始推播、停止推播、狀態查詢、測試新聞")
    print("⚙️ 進階設定：間隔調整、時間控制、關鍵字過濾、週末開關")
    print("📊 測試端點：/test/fetch-news、/test/format-news、/test/check-filters")
    print("=" * 50)
    print("🎉 系統初始化完成！")

if __name__ == '__main__':
    initialize_app()
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port)
