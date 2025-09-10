# news_bot_main.py
from flask import Flask, request, jsonify
import os
import threading
import time
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
    <h2>支援指令：</h2>
    <ul>
        <li>開始新聞推播</li>
        <li>停止新聞推播</li>
        <li>新聞狀態</li>
        <li>測試新聞</li>
    </ul>
    """

@app.route('/health')
def health():
    return jsonify({
        'status': 'healthy',
        'taiwan_time': get_taiwan_time(),
        'version': 'news_bot_v1.0',
        'services': bg_services.services,
        'news_monitoring': {
            'is_running': news_bot.is_running,
            'user_id': news_bot.user_id,
            'last_news_id': news_bot.last_news_id
        }
    })

def handle_news_command(message_text, user_id):
    """處理新聞相關指令"""
    try:
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
        
        elif message_text in ['新聞幫助', '指令說明', '說明']:
            return """📰 新聞機器人指令說明

🔔 推播控制：
• 開始新聞推播 - 啟動自動新聞監控
• 停止新聞推播 - 停止自動新聞監控

📊 狀態查詢：
• 新聞狀態 - 查看監控狀態
• 測試新聞 - 手動抓取最新新聞

ℹ️ 其他：
• 新聞幫助 - 顯示此說明

📰 新聞來源：鉅亨網
⏰ 檢查頻率：每5分鐘
🕐 當前時間：""" + get_taiwan_time()
        
        else:
            return f"""歡迎使用財經新聞機器人！

📰 可用指令：
• 開始新聞推播
• 停止新聞推播  
• 新聞狀態
• 測試新聞
• 新聞幫助

🕐 當前時間：{get_taiwan_time()}

💡 輸入「新聞幫助」查看詳細說明"""
    
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

def initialize_app():
    print("🚀 財經新聞推播機器人啟動中...")
    print(f"🇹🇼 台灣時間：{get_taiwan_time()}")
    
    bg_services.start_keep_alive()
    
    print("=" * 40)
    print("📰 新聞推播機器人：✅ 已啟動")
    print("🔄 支援指令：開始新聞推播、停止新聞推播、新聞狀態")
    print("📊 測試端點：/test/fetch-news、/test/format-news")
    print("=" * 40)
    print("🎉 系統初始化完成！")

if __name__ == '__main__':
    initialize_app()
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port)
