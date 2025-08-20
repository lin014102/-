"""
LINE Todo Reminder Bot - v3.0 模組化版本
整合獨立的股票記帳模組
"""
from flask import Flask, request, jsonify
import os
import re
import threading
import time
from datetime import timedelta

# 匯入工具模組
from utils.time_utils import get_taiwan_time, get_taiwan_time_hhmm, get_taiwan_datetime, is_valid_time_format
from utils.line_api import send_push_message, reply_message

# 匯入待辦事項模組
from todo_manager import todo_manager

# 匯入提醒機器人模組
from reminder_bot import ReminderBot

# 匯入股票模組
from stock_manager import (
    handle_stock_command,
    get_stock_summary,
    get_stock_transactions,
    get_stock_cost_analysis,
    get_stock_account_list,
    get_stock_help,
    is_stock_command,
    is_stock_query
)

app = Flask(__name__)

# 建立提醒機器人實例
reminder_bot = ReminderBot(todo_manager)

# 防休眠機制
def keep_alive():
    """防休眠機制"""
    import requests
    base_url = os.getenv('BASE_URL', 'https://line-bot-python-v2.onrender.com')
    
    while True:
        try:
            time.sleep(240)
            response = requests.get(f'{base_url}/health', timeout=15)
            
            if response.status_code == 200:
                print(f"✅ Keep-alive 成功 - 台灣時間: {get_taiwan_time()}")
            else:
                print(f"⚠️ Keep-alive 警告: {response.status_code} - 台灣時間: {get_taiwan_time()}")
                
        except requests.exceptions.RequestException as e:
            print(f"❌ Keep-alive 錯誤: {e} - 台灣時間: {get_taiwan_time()}")
            time.sleep(60)
        except Exception as e:
            print(f"❌ Keep-alive 意外錯誤: {e} - 台灣時間: {get_taiwan_time()}")
            time.sleep(60)

keep_alive_thread = threading.Thread(target=keep_alive, daemon=True)
keep_alive_thread.start()

# 啟動提醒機器人
reminder_bot.start_reminder_thread()

# ===== Flask 路由 =====
@app.route('/')
def home():
    return f'LINE Todo Reminder Bot v3.0 - 模組化設計！當前台灣時間: {get_taiwan_time()}'

@app.route('/health')
def health():
    """健康檢查端點"""
    taiwan_now = get_taiwan_datetime()
    
    try:
        next_morning = taiwan_now.replace(
            hour=int(reminder_bot.user_settings['morning_time'].split(':')[0]),
            minute=int(reminder_bot.user_settings['morning_time'].split(':')[1]),
            second=0, microsecond=0
        )
        if next_morning <= taiwan_now:
            next_morning += timedelta(days=1)
        
        next_evening = taiwan_now.replace(
            hour=int(reminder_bot.user_settings['evening_time'].split(':')[0]),
            minute=int(reminder_bot.user_settings['evening_time'].split(':')[1]),
            second=0, microsecond=0
        )
        if next_evening <= taiwan_now:
            next_evening += timedelta(days=1)
        
        next_reminder = min(next_morning, next_evening)
        next_reminder_str = next_reminder.strftime('%Y/%m/%d %H:%M')
    except:
        next_reminder_str = "計算錯誤"
    
    reminder_counts = reminder_bot.get_reminder_counts()
    
    return jsonify({
        'status': 'healthy',
        'taiwan_time': get_taiwan_time(),
        'taiwan_time_hhmm': get_taiwan_time_hhmm(),
        'server_timezone': str(taiwan_now.tzinfo),
        'todos_count': todo_manager.get_todo_count(),
        'monthly_todos_count': todo_manager.get_monthly_count(),
        'short_reminders': reminder_counts['short_reminders'],
        'time_reminders': reminder_counts['time_reminders'],
        'morning_time': reminder_bot.user_settings['morning_time'],
        'evening_time': reminder_bot.user_settings['evening_time'],
        'next_reminder': next_reminder_str,
        'has_user': reminder_bot.user_settings['user_id'] is not None,
        'version': '3.0_modular_design'
    })

@app.route('/webhook', methods=['POST'])
def webhook():
    """LINE Webhook 處理 - 模組化版本"""
    try:
        data = request.get_json()
        
        for event in data.get('events', []):
            if event['type'] == 'message' and event['message']['type'] == 'text':
                reply_token = event['replyToken']
                message_text = event['message']['text'].strip()
                user_id = event['source']['userId']
                
                # 設定用戶ID到提醒機器人
                reminder_bot.set_user_id(user_id)
                
                print(f"用戶訊息: {message_text} - 台灣時間: {get_taiwan_time()}")
                
                # === 股票功能路由 ===
                if is_stock_command(message_text):
                    reply_text = handle_stock_command(message_text)
                
                elif message_text == '總覽':
                    reply_text = get_stock_summary()
                
                elif message_text.endswith('查詢') and message_text != '查詢':
                    account_name = message_text[:-2].strip()
                    if account_name in ['股票', '帳戶']:
                        reply_text = get_stock_summary()
                    else:
                        reply_text = get_stock_summary(account_name)
                
                elif message_text == '交易記錄':
                    reply_text = get_stock_transactions()
                
                elif message_text.startswith('交易記錄 '):
                    account_name = message_text[5:].strip()
                    reply_text = get_stock_transactions(account_name)
                
                elif message_text.startswith('成本查詢 ') and ' ' in message_text[5:]:
                    parts = message_text[5:].strip().split(' ', 1)
                    if len(parts) == 2:
                        account_name, stock_code = parts
                        reply_text = get_stock_cost_analysis(account_name, stock_code)
                    else:
                        reply_text = "❌ 格式不正確\n💡 例如：成本查詢 爸爸 2330"
                
                elif message_text == '帳戶列表':
                    reply_text = get_stock_account_list()
                
                elif message_text == '股票幫助':
                    reply_text = get_stock_help()

                # === 提醒功能路由 - 使用 ReminderBot ===
                elif message_text == '查詢時間':
                    reply_text = reminder_bot.get_time_settings()

                elif message_text.startswith('早上時間 '):
                    time_str = message_text[5:].strip()
                    if is_valid_time_format(time_str):
                        reply_text = reminder_bot.set_morning_time(time_str)
                    else:
                        reply_text = "❌ 時間格式不正確，請使用 HH:MM 格式，例如：08:30"

                elif message_text.startswith('晚上時間 '):
                    time_str = message_text[5:].strip()
                    if is_valid_time_format(time_str):
                        reply_text = reminder_bot.set_evening_time(time_str)
                    else:
                        reply_text = "❌ 時間格式不正確，請使用 HH:MM 格式，例如：19:00"

                elif any(keyword in message_text for keyword in ['分鐘後', '小時後', '秒後']):
                    reply_text = reminder_bot.add_short_reminder(message_text, user_id)

                elif re.match(r'^\d{1,2}:\d{2}.+', message_text):
                    reply_text = reminder_bot.add_time_reminder(message_text, user_id)

                elif message_text in ['幫助', 'help', '說明']:
                    reply_text = """📋 LINE Todo Bot v3.0 完整功能：

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

🆕 v3.0 新功能：模組化設計，完全重構！"""

                # === 待辦事項功能 - 使用 TodoManager ===
                elif message_text.startswith('新增 '):
                    todo_text = message_text[3:].strip()
                    reply_text = todo_manager.add_todo(todo_text)

                elif message_text in ['查詢', '清單']:
                    reply_text = todo_manager.get_todo_list()

                elif message_text.startswith('刪除 '):
                    index_str = message_text[3:]
                    reply_text = todo_manager.delete_todo(index_str)

                elif message_text.startswith('完成 '):
                    index_str = message_text[3:]
                    reply_text = todo_manager.complete_todo(index_str)

                elif message_text.startswith('每月新增 '):
                    todo_text = message_text[5:].strip()
                    reply_text = todo_manager.add_monthly_todo(todo_text)

                elif message_text == '每月清單':
                    reply_text = todo_manager.get_monthly_list()

                elif message_text == '測試':
                    reply_text = f"✅ 機器人正常運作！\n🇹🇼 當前台灣時間：{get_taiwan_time()}\n⏰ 提醒機器人：已啟動\n📋 待辦事項管理：已載入\n💰 股票記帳模組：已載入\n🔧 模組化設計：完全重構\n💡 輸入「幫助」或「股票幫助」查看功能"

                else:
                    reply_text = f"您說：{message_text}\n🇹🇼 當前台灣時間：{get_taiwan_time_hhmm()}\n\n💡 輸入「幫助」查看待辦功能\n💰 輸入「股票幫助」查看股票功能"
                
                reply_message(reply_token, reply_text)
        
        return 'OK', 200
    
    except Exception as e:
        print(f"Webhook 處理錯誤: {e} - 台灣時間: {get_taiwan_time()}")
        return 'OK', 200

if __name__ == '__main__':
    print(f"🚀 LINE Bot v3.0 模組化版本啟動 - 台灣時間: {get_taiwan_time()}")
    print(f"📋 待辦事項管理：已載入")
    print(f"⏰ 提醒機器人：已啟動")
    print(f"💰 股票記帳模組：已載入")
    print(f"🔧 模組化設計：完全重構")
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port)
