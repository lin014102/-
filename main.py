"""
main.py - LINE Todo Reminder Bot 主程式
v3.0 完全模組化架構
"""
from flask import Flask, request, jsonify
import os
import re
import threading
import time
from datetime import timedelta

# 匯入所有模組
from utils.time_utils import get_taiwan_time, get_taiwan_time_hhmm, get_taiwan_datetime, is_valid_time_format
from utils.line_api import reply_message
from todo_manager import todo_manager
from reminder_bot import ReminderBot
from stock_manager import (
    handle_stock_command, get_stock_summary, get_stock_transactions,
    get_stock_cost_analysis, get_stock_account_list, get_stock_help,
    is_stock_command, is_stock_query
)

# 初始化 Flask 應用
app = Flask(__name__)

# 建立模組實例
reminder_bot = ReminderBot(todo_manager)

class MessageRouter:
    """訊息路由器 - 分發訊息到對應模組"""
    
    def __init__(self, todo_mgr, reminder_bot, stock_mgr):
        self.todo_manager = todo_mgr
        self.reminder_bot = reminder_bot
        # stock_manager 是靜態函數，不需要實例
    
    def route_message(self, message_text, user_id):
        """路由訊息到對應的處理模組"""
        message_text = message_text.strip()
        
        # 設定用戶ID
        self.reminder_bot.set_user_id(user_id)
        
        # === 股票功能路由 ===
        if is_stock_command(message_text):
            return handle_stock_command(message_text)
        
        elif message_text == '總覽':
            return get_stock_summary()
        
        elif message_text.endswith('查詢') and message_text != '查詢':
            account_name = message_text[:-2].strip()
            if account_name in ['股票', '帳戶']:
                return get_stock_summary()
            else:
                return get_stock_summary(account_name)
        
        elif message_text == '交易記錄':
            return get_stock_transactions()
        
        elif message_text.startswith('交易記錄 '):
            account_name = message_text[5:].strip()
            return get_stock_transactions(account_name)
        
        elif message_text.startswith('成本查詢 ') and ' ' in message_text[5:]:
            parts = message_text[5:].strip().split(' ', 1)
            if len(parts) == 2:
                account_name, stock_code = parts
                return get_stock_cost_analysis(account_name, stock_code)
            else:
                return "❌ 格式不正確\n💡 例如：成本查詢 爸爸 2330"
        
        elif message_text == '帳戶列表':
            return get_stock_account_list()
        
        elif message_text == '股票幫助':
            return get_stock_help()
        
        # === 提醒功能路由 ===
        elif message_text == '查詢時間':
            return self.reminder_bot.get_time_settings()
        
        elif message_text.startswith('早上時間 '):
            time_str = message_text[5:].strip()
            if is_valid_time_format(time_str):
                return self.reminder_bot.set_morning_time(time_str)
            else:
                return "❌ 時間格式不正確，請使用 HH:MM 格式，例如：08:30"
        
        elif message_text.startswith('晚上時間 '):
            time_str = message_text[5:].strip()
            if is_valid_time_format(time_str):
                return self.reminder_bot.set_evening_time(time_str)
            else:
                return "❌ 時間格式不正確，請使用 HH:MM 格式，例如：19:00"
        
        elif any(keyword in message_text for keyword in ['分鐘後', '小時後', '秒後']):
            return self.reminder_bot.add_short_reminder(message_text, user_id)
        
        elif re.match(r'^\d{1,2}:\d{2}.+', message_text):
            return self.reminder_bot.add_time_reminder(message_text, user_id)
        
        # === 待辦事項功能路由 ===
        elif message_text.startswith('新增 '):
            todo_text = message_text[3:].strip()
            return self.todo_manager.add_todo(todo_text)
        
        elif message_text in ['查詢', '清單']:
            return self.todo_manager.get_todo_list()
        
        elif message_text.startswith('刪除 '):
            index_str = message_text[3:]
            return self.todo_manager.delete_todo(index_str)
        
        elif message_text.startswith('完成 '):
            index_str = message_text[3:]
            return self.todo_manager.complete_todo(index_str)
        
        elif message_text.startswith('每月新增 '):
            todo_text = message_text[5:].strip()
            return self.todo_manager.add_monthly_todo(todo_text)
        
        elif message_text == '每月清單':
            return self.todo_manager.get_monthly_list()
        
        # === 系統功能 ===
        elif message_text in ['幫助', 'help', '說明']:
            return self.get_help_message()
        
        elif message_text == '測試':
            return self.get_system_status()
        
        else:
            return self.get_default_response(message_text)
    
    def get_help_message(self):
        """獲取幫助訊息"""
        return """📋 LINE Todo Bot v3.0 完整功能：

🔹 待辦事項：
- 新增 [事項] - 新增待辦事項
- 查詢 - 查看待辦清單
- 刪除 [編號] - 刪除事項
- 完成 [編號] - 標記完成

⏰ 提醒功能：
- 5分鐘後倒垃圾 - 短期提醒
- 12:00開會 - 時間提醒
- 早上時間 09:00 - 設定早上提醒
- 晚上時間 18:00 - 設定晚上提醒

🔄 每月功能：
- 每月新增 5號繳卡費 - 每月固定事項
- 每月清單 - 查看每月事項

💰 股票記帳：
- 爸爸入帳 50000 - 入金
- 爸爸買 2330 100 50000 0820 - 買股票（簡化版）
- 總覽 - 查看所有帳戶
- 股票幫助 - 股票功能詳細說明

🚀 v3.0 新功能：完全模組化架構，易於擴充！"""
    
    def get_system_status(self):
        """獲取系統狀態"""
        return f"""✅ 系統狀態檢查
🇹🇼 當前台灣時間：{get_taiwan_time()}

📊 模組狀態：
⏰ 提醒機器人：✅ 運行中
📋 待辦事項管理：✅ 已載入
💰 股票記帳模組：✅ 已載入

🔧 架構：完全模組化
🚀 版本：v3.0

💡 輸入「幫助」查看功能列表"""
    
    def get_default_response(self, message_text):
        """預設回應"""
        return f"""您說：{message_text}
🇹🇼 當前台灣時間：{get_taiwan_time_hhmm()}

💡 輸入「幫助」查看待辦功能
💰 輸入「股票幫助」查看股票功能"""

# 建立訊息路由器實例
message_router = MessageRouter(todo_manager, reminder_bot, None)

# 背景服務管理
class BackgroundServices:
    """背景服務管理器"""
    
    def __init__(self):
        self.services = []
    
    def start_keep_alive(self):
        """啟動防休眠服務"""
        def keep_alive():
            import requests
            base_url = os.getenv('BASE_URL', 'https://line-bot-python-v2.onrender.com')
            
            while True:
                try:
                    time.sleep(240)
                    response = requests.get(f'{base_url}/health', timeout=15)
                    
                    if response.status_code == 200:
                        print(f"✅ Keep-alive 成功 - {get_taiwan_time()}")
                    else:
                        print(f"⚠️ Keep-alive 警告: {response.status_code} - {get_taiwan_time()}")
                        
                except requests.exceptions.RequestException as e:
                    print(f"❌ Keep-alive 錯誤: {e} - {get_taiwan_time()}")
                    time.sleep(60)
                except Exception as e:
                    print(f"❌ Keep-alive 意外錯誤: {e} - {get_taiwan_time()}")
                    time.sleep(60)
        
        thread = threading.Thread(target=keep_alive, daemon=True)
        thread.start()
        self.services.append('keep_alive')
        print("✅ 防休眠服務已啟動")
    
    def start_reminder_bot(self):
        """啟動提醒機器人"""
        reminder_bot.start_reminder_thread()
        self.services.append('reminder_bot')
        print("✅ 提醒機器人已啟動")

# 建立背景服務管理器
bg_services = BackgroundServices()

# ===== Flask 路由 =====
@app.route('/')
def home():
    """首頁"""
    return f"""
    <h1>LINE Todo Reminder Bot v3.0</h1>
    <p>🇹🇼 當前台灣時間：{get_taiwan_time()}</p>
    <p>🚀 模組化架構，完全重構！</p>
    <p>📊 健康檢查：<a href="/health">/health</a></p>
    """

@app.route('/health')
def health():
    """健康檢查端點"""
    taiwan_now = get_taiwan_datetime()
    
    try:
        # 計算下次提醒時間
        morning_time = reminder_bot.user_settings['morning_time']
        evening_time = reminder_bot.user_settings['evening_time']
        
        next_morning = taiwan_now.replace(
            hour=int(morning_time.split(':')[0]),
            minute=int(morning_time.split(':')[1]),
            second=0, microsecond=0
        )
        if next_morning <= taiwan_now:
            next_morning += timedelta(days=1)
        
        next_evening = taiwan_now.replace(
            hour=int(evening_time.split(':')[0]),
            minute=int(evening_time.split(':')[1]),
            second=0, microsecond=0
        )
        if next_evening <= taiwan_now:
            next_evening += timedelta(days=1)
        
        next_reminder = min(next_morning, next_evening)
        next_reminder_str = next_reminder.strftime('%Y/%m/%d %H:%M')
    except:
        next_reminder_str = "計算錯誤"
    
    # 獲取各模組狀態
    reminder_counts = reminder_bot.get_reminder_counts()
    
    return jsonify({
        'status': 'healthy',
        'taiwan_time': get_taiwan_time(),
        'taiwan_time_hhmm': get_taiwan_time_hhmm(),
        'server_timezone': str(taiwan_now.tzinfo),
        'version': 'v3.0_modular_architecture',
        
        # 模組狀態
        'modules': {
            'todo_manager': {
                'todos_count': todo_manager.get_todo_count(),
                'monthly_todos_count': todo_manager.get_monthly_count()
            },
            'reminder_bot': {
                'short_reminders': reminder_counts['short_reminders'],
                'time_reminders': reminder_counts['time_reminders'],
                'morning_time': reminder_bot.user_settings['morning_time'],
                'evening_time': reminder_bot.user_settings['evening_time'],
                'next_reminder': next_reminder_str,
                'has_user': reminder_bot.user_settings['user_id'] is not None
            },
            'background_services': bg_services.services
        }
    })

@app.route('/webhook', methods=['POST'])
def webhook():
    """LINE Webhook 處理 - 統一入口"""
    try:
        data = request.get_json()
        
        for event in data.get('events', []):
            if event['type'] == 'message' and event['message']['type'] == 'text':
                reply_token = event['replyToken']
                message_text = event['message']['text']
                user_id = event['source']['userId']
                
                print(f"📨 用戶訊息: {message_text} - {get_taiwan_time()}")
                
                # 使用訊息路由器處理
                reply_text = message_router.route_message(message_text, user_id)
                
                # 回覆訊息
                reply_message(reply_token, reply_text)
        
        return 'OK', 200
    
    except Exception as e:
        print(f"❌ Webhook 處理錯誤: {e} - {get_taiwan_time()}")
        return 'OK', 200

def initialize_app():
    """初始化應用程式"""
    print("🚀 LINE Todo Reminder Bot v3.0 啟動中...")
    print(f"🇹🇼 台灣時間：{get_taiwan_time()}")
    
    # 啟動背景服務
    bg_services.start_keep_alive()
    bg_services.start_reminder_bot()
    
    print("=" * 50)
    print("📋 待辦事項管理：✅ 已載入")
    print("⏰ 提醒機器人：✅ 已啟動") 
    print("💰 股票記帳模組：✅ 已載入")
    print("🔧 模組化架構：✅ 完全重構")
    print("=" * 50)
    print("🎉 系統初始化完成！")

if __name__ == '__main__':
    # 初始化應用
    initialize_app()
    
    # 啟動 Flask 應用
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port)
