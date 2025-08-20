"""
LINE Todo Reminder Bot - v3.0 模組化版本
整合獨立的股票記帳模組
"""
from flask import Flask, request, jsonify
import os
import requests
import json
import re
import threading
import time
from datetime import datetime, timedelta

# 匯入工具模組
from utils.time_utils import get_taiwan_time, get_taiwan_time_hhmm, get_taiwan_datetime, is_valid_time_format

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

# ===== 待辦事項資料儲存 =====
todos = []
monthly_todos = []
short_reminders = []
time_reminders = []
user_settings = {
    'morning_time': '09:00',
    'evening_time': '18:00',
    'user_id': None
}

# LINE Bot 設定
CHANNEL_ACCESS_TOKEN = os.getenv('CHANNEL_ACCESS_TOKEN', '')
LINE_API_URL = 'https://api.line.me/v2/bot/message/reply'
PUSH_API_URL = 'https://api.line.me/v2/bot/message/push'

# ===== 待辦事項功能函數 =====
def parse_date(text):
    """解析日期格式"""
    taiwan_now = get_taiwan_datetime()
    current_year = taiwan_now.year
    
    patterns = [
        (r'(\d{1,2})號(.+)', 'day_only'),
        (r'(\d{1,2})\/(\d{1,2})號?(.+)', 'month_day'),
        (r'(.+?)(\d{1,2})號', 'content_day'),
        (r'(.+?)(\d{1,2})\/(\d{1,2})號?', 'content_month_day')
    ]
    
    for pattern, pattern_type in patterns:
        match = re.search(pattern, text)
        if match:
            if pattern_type == 'day_only':
                day = int(match.group(1))
                content = match.group(2).strip()
                if 1 <= day <= 31 and content:
                    month = taiwan_now.month
                    target_date = taiwan_now.replace(year=current_year, month=month, day=day,
                                                   hour=0, minute=0, second=0, microsecond=0)
                    if target_date < taiwan_now:
                        if month == 12:
                            target_date = target_date.replace(year=current_year + 1, month=1)
                        else:
                            target_date = target_date.replace(month=month + 1)
                    
                    return {
                        "has_date": True,
                        "date": target_date,
                        "content": content,
                        "date_string": f"{month}/{day}",
                        "day_only": day
                    }
                    
            elif pattern_type == 'month_day':
                month = int(match.group(1))
                day = int(match.group(2))
                content = match.group(3).strip()
                
                if 1 <= month <= 12 and 1 <= day <= 31 and content:
                    target_date = taiwan_now.replace(year=current_year, month=month, day=day,
                                                   hour=0, minute=0, second=0, microsecond=0)
                    if target_date < taiwan_now:
                        target_date = target_date.replace(year=current_year + 1)
                    
                    return {
                        "has_date": True,
                        "date": target_date,
                        "content": content,
                        "date_string": f"{month}/{day}"
                    }
                    
            elif pattern_type == 'content_day':
                content = match.group(1).strip()
                day = int(match.group(2))
                
                if 1 <= day <= 31 and content:
                    month = taiwan_now.month
                    target_date = taiwan_now.replace(year=current_year, month=month, day=day,
                                                   hour=0, minute=0, second=0, microsecond=0)
                    if target_date < taiwan_now:
                        if month == 12:
                            target_date = target_date.replace(year=current_year + 1, month=1)
                        else:
                            target_date = target_date.replace(month=month + 1)
                    
                    return {
                        "has_date": True,
                        "date": target_date,
                        "content": content,
                        "date_string": f"{month}/{day}",
                        "day_only": day
                    }
                    
            elif pattern_type == 'content_month_day':
                content = match.group(1).strip()
                month = int(match.group(2))
                day = int(match.group(3))
                
                if 1 <= month <= 12 and 1 <= day <= 31 and content:
                    target_date = taiwan_now.replace(year=current_year, month=month, day=day,
                                                   hour=0, minute=0, second=0, microsecond=0)
                    if target_date < taiwan_now:
                        target_date = target_date.replace(year=current_year + 1)
                    
                    return {
                        "has_date": True,
                        "date": target_date,
                        "content": content,
                        "date_string": f"{month}/{day}"
                    }
    
    return {"has_date": False, "content": text}

def parse_short_reminder(text):
    """解析短期提醒"""
    patterns = [
        (r'(\d+)分鐘後(.+)', '分鐘', 1),
        (r'(\d+)小時後(.+)', '小時', 60),
        (r'(\d+)秒後(.+)', '秒', 1/60)
    ]
    
    for pattern, unit, multiplier in patterns:
        match = re.search(pattern, text)
        if match:
            value = int(match.group(1))
            content = match.group(2).strip()
            
            if not content:
                return {"is_valid": False, "error": "請輸入提醒內容"}
            
            minutes = value * multiplier
            
            if unit == '分鐘' and not (1 <= value <= 1440):
                return {"is_valid": False, "error": "分鐘數請設定在 1-1440 之間"}
            elif unit == '小時' and not (1 <= value <= 24):
                return {"is_valid": False, "error": "小時數請設定在 1-24 之間"}
            elif unit == '秒' and not (10 <= value <= 3600):
                return {"is_valid": False, "error": "秒數請設定在 10-3600 之間"}
            
            return {
                "is_valid": True,
                "minutes": minutes,
                "original_value": value,
                "unit": unit,
                "content": content
            }
    
    return {"is_valid": False, "error": "格式不正確，請使用：數字+時間單位+後+內容\n例如：5分鐘後倒垃圾"}

def parse_time_reminder(text):
    """解析時間提醒"""
    time_pattern = r'(\d{1,2}):(\d{2})(.+)'
    match = re.search(time_pattern, text)
    
    if match:
        hours = int(match.group(1))
        minutes = int(match.group(2))
        content = match.group(3).strip()
        
        if not content:
            return {"is_valid": False, "error": "請輸入提醒內容"}
        
        if not (0 <= hours <= 23):
            return {"is_valid": False, "error": "小時請設定在 0-23 之間"}
        
        if not (0 <= minutes <= 59):
            return {"is_valid": False, "error": "分鐘請設定在 0-59 之間"}
        
        return {
            "is_valid": True,
            "hours": hours,
            "minutes": minutes,
            "time_string": f"{hours:02d}:{minutes:02d}",
            "content": content
        }
    
    return {"is_valid": False, "error": "格式不正確，請使用：HH:MM+內容\n例如：12:00倒垃圾"}

# ===== LINE API 函數 =====
def send_push_message(user_id, message_text):
    """發送推播訊息"""
    if not CHANNEL_ACCESS_TOKEN or not user_id:
        print(f"模擬推播給 {user_id}: {message_text} (台灣時間: {get_taiwan_time()})")
        return False
    
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {CHANNEL_ACCESS_TOKEN}'
    }
    
    data = {
        'to': user_id,
        'messages': [{
            'type': 'text',
            'text': message_text
        }]
    }
    
    try:
        response = requests.post(PUSH_API_URL, headers=headers, data=json.dumps(data))
        print(f"推播發送 - 狀態碼: {response.status_code} - 台灣時間: {get_taiwan_time()}")
        return response.status_code == 200
    except Exception as e:
        print(f"推播失敗: {e} - 台灣時間: {get_taiwan_time()}")
        return False

def reply_message(reply_token, message_text):
    """回覆訊息"""
    if not CHANNEL_ACCESS_TOKEN:
        print(f"模擬回覆: {message_text} (台灣時間: {get_taiwan_time()})")
        return False
    
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {CHANNEL_ACCESS_TOKEN}'
    }
    
    data = {
        'replyToken': reply_token,
        'messages': [{
            'type': 'text',
            'text': message_text
        }]
    }
    
    try:
        response = requests.post(LINE_API_URL, headers=headers, data=json.dumps(data))
        return response.status_code == 200
    except Exception as e:
        print(f"回覆失敗: {e} - 台灣時間: {get_taiwan_time()}")
        return False

# ===== 提醒系統函數 =====
def check_reminders():
    """檢查並發送提醒"""
    from utils.time_utils import TAIWAN_TZ  # 在這裡匯入時區
    
    while True:
        try:
            current_time = get_taiwan_time_hhmm()
            user_id = user_settings.get('user_id')
            taiwan_now = get_taiwan_datetime()
            
            print(f"🔍 提醒檢查 - 台灣時間: {get_taiwan_time()}")
            
            if user_id and (current_time == user_settings['morning_time'] or current_time == user_settings['evening_time']):
                send_daily_reminder(user_id, current_time)
            
            if current_time == user_settings['evening_time']:
                check_monthly_preview(taiwan_now, user_id)
            
            if current_time == "09:00":
                check_monthly_reminders(taiwan_now, user_id)
            
            check_short_reminders(taiwan_now, TAIWAN_TZ)
            check_time_reminders(taiwan_now, TAIWAN_TZ)
            
            time.sleep(60)
        except Exception as e:
            print(f"提醒檢查錯誤: {e} - 台灣時間: {get_taiwan_time()}")
            time.sleep(60)

def send_daily_reminder(user_id, current_time):
    """發送每日提醒"""
    time_icon = '🌅' if current_time == user_settings['morning_time'] else '🌙'
    time_text = '早安' if current_time == user_settings['morning_time'] else '晚安'
    
    if todos:
        pending_todos = [todo for todo in todos if not todo.get('completed', False)]
        completed_todos = [todo for todo in todos if todo.get('completed', False)]
        
        if pending_todos:
            message = f'{time_icon} {time_text}！您有 {len(pending_todos)} 項待辦事項：\n\n'
            
            for i, todo in enumerate(pending_todos[:5], 1):
                date_info = f" 📅{todo.get('target_date', '')}" if todo.get('has_date') else ""
                message += f'{i}. ⭕ {todo["content"]}{date_info}\n'
            
            if len(pending_todos) > 5:
                message += f'\n...還有 {len(pending_todos) - 5} 項未完成\n'
            
            if completed_todos:
                message += f'\n✅ 已完成 {len(completed_todos)} 項：\n'
                for todo in completed_todos[:2]:
                    message += f'✅ {todo["content"]}\n'
                if len(completed_todos) > 2:
                    message += f'...還有 {len(completed_todos) - 2} 項已完成\n'
            
            if current_time == user_settings['morning_time']:
                message += f'\n💪 新的一天開始了！加油完成這些任務！'
            else:
                message += f'\n🌙 檢查一下今天的進度吧！記得為明天做準備！'
                
            message += f'\n🇹🇼 台灣時間: {get_taiwan_time_hhmm()}'
            
            send_push_message(user_id, message)
            print(f"✅ 已發送每日提醒 ({len(pending_todos)} 項待辦) - 台灣時間: {get_taiwan_time()}")
        else:
            if current_time == user_settings['morning_time']:
                message = f'{time_icon} {time_text}！🎉 太棒了！目前沒有待辦事項\n💡 可以新增今天要做的事情'
            else:
                message = f'{time_icon} {time_text}！🎉 太棒了！今天的任務都完成了\n😴 好好休息，為明天準備新的目標！'
            
            message += f'\n🇹🇼 台灣時間: {get_taiwan_time_hhmm()}'
            send_push_message(user_id, message)
            print(f"✅ 已發送每日提醒 (無待辦事項) - 台灣時間: {get_taiwan_time()}")
    else:
        if current_time == user_settings['morning_time']:
            message = f'{time_icon} {time_text}！✨ 新的一天開始了！\n💡 輸入「新增 事項名稱」來建立今天的目標'
        else:
            message = f'{time_icon} {time_text}！😌 今天過得如何？\n💡 別忘了為明天規劃一些目標'
        
        message += f'\n🇹🇼 台灣時間: {get_taiwan_time_hhmm()}'
        send_push_message(user_id, message)
        print(f"✅ 已發送每日提醒 (首次使用) - 台灣時間: {get_taiwan_time()}")

def check_monthly_preview(taiwan_now, user_id):
    """檢查明天的每月提醒"""
    if not monthly_todos or not user_id:
        return
    
    tomorrow = taiwan_now + timedelta(days=1)
    tomorrow_day = tomorrow.day
    
    monthly_items_tomorrow = []
    for item in monthly_todos:
        target_day = item.get('day', 1)
        if target_day == tomorrow_day:
            monthly_items_tomorrow.append(item)
    
    if monthly_items_tomorrow:
        message = f"📅 每月提醒預告！\n\n明天 ({tomorrow.strftime('%m/%d')}) 有 {len(monthly_items_tomorrow)} 項每月固定事項：\n\n"
        
        for i, item in enumerate(monthly_items_tomorrow, 1):
            message += f"{i}. 🔄 {item['content']}\n"
        
        message += f"\n💡 明天早上會自動加入待辦清單並提醒您\n🇹🇼 台灣時間: {get_taiwan_time_hhmm()}"
        
        send_push_message(user_id, message)
        print(f"✅ 已發送每月預告提醒，明天有 {len(monthly_items_tomorrow)} 項事項 - 台灣時間: {get_taiwan_time()}")

def check_monthly_reminders(taiwan_now, user_id):
    """檢查每月提醒"""
    if not monthly_todos or not user_id:
        return
    
    current_day = taiwan_now.day
    
    monthly_items_today = []
    for item in monthly_todos:
        target_day = item.get('day', 1)
        if target_day == current_day:
            monthly_items_today.append(item)
    
    if monthly_items_today:
        added_items = []
        for item in monthly_items_today:
            already_exists = any(
                todo['content'] == item['content'] and 
                todo.get('created_at', '').startswith(taiwan_now.strftime('%Y/%m/%d'))
                for todo in todos
            )
            
            if not already_exists:
                todo_item = {
                    'id': len(todos) + 1,
                    'content': item['content'],
                    'created_at': get_taiwan_time(),
                    'completed': False,
                    'has_date': True,
                    'target_date': taiwan_now.strftime('%Y/%m/%d'),
                    'date_string': f"{taiwan_now.month}/{taiwan_now.day}",
                    'from_monthly': True
                }
                todos.append(todo_item)
                added_items.append(item['content'])
        
        if added_items:
            message = f"🔄 每月提醒！今天 ({taiwan_now.strftime('%m/%d')}) 的固定事項：\n\n"
            for i, content in enumerate(added_items, 1):
                message += f"{i}. 📅 {content}\n"
            
            message += f"\n✅ 已自動加入今日待辦清單"
            message += f"\n💡 昨天已經預告過，現在正式提醒！"
            message += f"\n🇹🇼 台灣時間: {get_taiwan_time_hhmm()}"
            
            send_push_message(user_id, message)
            print(f"✅ 已發送每月正式提醒，加入 {len(added_items)} 項事項 - 台灣時間: {get_taiwan_time()}")

def check_short_reminders(taiwan_now, TAIWAN_TZ):
    """檢查短期提醒"""
    for reminder in short_reminders[:]:
        reminder_time_str = reminder['reminder_time']
        try:
            if '+' in reminder_time_str or reminder_time_str.endswith('Z'):
                reminder_time = datetime.fromisoformat(reminder_time_str.replace('Z', '+00:00'))
                reminder_time = reminder_time.astimezone(TAIWAN_TZ)
            else:
                reminder_time = TAIWAN_TZ.localize(datetime.fromisoformat(reminder_time_str))
        except:
            print(f"⚠️ 無法解析提醒時間: {reminder_time_str}")
            short_reminders.remove(reminder)
            continue
        
        if reminder_time <= taiwan_now:
            user_id = reminder.get('user_id') or user_settings.get('user_id')
            if user_id:
                message = f"⏰ 短期提醒時間到！\n\n📋 {reminder['content']}\n🎯 該去執行了！\n🇹🇼 台灣時間: {get_taiwan_time_hhmm()}"
                send_push_message(user_id, message)
                print(f"✅ 已發送短期提醒: {reminder['content']} - 台灣時間: {get_taiwan_time()}")
            short_reminders.remove(reminder)

def check_time_reminders(taiwan_now, TAIWAN_TZ):
    """檢查時間提醒"""
    for reminder in time_reminders[:]:
        reminder_time_str = reminder['reminder_time']
        try:
            if '+' in reminder_time_str or reminder_time_str.endswith('Z'):
                reminder_time = datetime.fromisoformat(reminder_time_str.replace('Z', '+00:00'))
                reminder_time = reminder_time.astimezone(TAIWAN_TZ)
            else:
                reminder_time = TAIWAN_TZ.localize(datetime.fromisoformat(reminder_time_str))
        except:
            print(f"⚠️ 無法解析提醒時間: {reminder_time_str}")
            time_reminders.remove(reminder)
            continue
            
        if reminder_time <= taiwan_now:
            user_id = reminder.get('user_id') or user_settings.get('user_id')
            if user_id:
                message = f"🕐 時間提醒！\n\n📋 {reminder['content']}\n⏰ {reminder['time_string']}\n🎯 該去執行了！\n🇹🇼 台灣時間: {get_taiwan_time_hhmm()}"
                send_push_message(user_id, message)
                print(f"✅ 已發送時間提醒: {reminder['content']} - 台灣時間: {get_taiwan_time()}")
            time_reminders.remove(reminder)

# 啟動提醒檢查執行緒
reminder_thread = threading.Thread(target=check_reminders, daemon=True)
reminder_thread.start()

# 防休眠機制
def keep_alive():
    """防休眠機制"""
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
            hour=int(user_settings['morning_time'].split(':')[0]),
            minute=int(user_settings['morning_time'].split(':')[1]),
            second=0, microsecond=0
        )
        if next_morning <= taiwan_now:
            next_morning += timedelta(days=1)
        
        next_evening = taiwan_now.replace(
            hour=int(user_settings['evening_time'].split(':')[0]),
            minute=int(user_settings['evening_time'].split(':')[1]),
            second=0, microsecond=0
        )
        if next_evening <= taiwan_now:
            next_evening += timedelta(days=1)
        
        next_reminder = min(next_morning, next_evening)
        next_reminder_str = next_reminder.strftime('%Y/%m/%d %H:%M')
    except:
        next_reminder_str = "計算錯誤"
    
    return jsonify({
        'status': 'healthy',
        'taiwan_time': get_taiwan_time(),
        'taiwan_time_hhmm': get_taiwan_time_hhmm(),
        'server_timezone': str(taiwan_now.tzinfo),
        'todos_count': len(todos),
        'monthly_todos_count': len(monthly_todos),
        'short_reminders': len(short_reminders),
        'time_reminders': len(time_reminders),
        'morning_time': user_settings['morning_time'],
        'evening_time': user_settings['evening_time'],
        'next_reminder': next_reminder_str,
        'has_user': user_settings['user_id'] is not None,
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
                
                user_settings['user_id'] = user_id
                
                print(f"用戶訊息: {message_text} - 台灣時間: {get_taiwan_time()}")
                
                # === 股票功能路由 ===
                if is_stock_command(message_text):
                    reply_text = handle_stock_command(message_text)
                
                elif message_text == '總覽':
                    reply_text = get_stock_summary()
                
                elif message_text.endswith('查詢'):
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

                # === 待辦事項功能路由 ===
                elif message_text == '查詢時間':
                    reply_text = f"🇹🇼 台灣當前時間：{get_taiwan_time()}\n⏰ 目前提醒時間設定：\n🌅 早上：{user_settings['morning_time']}\n🌙 晚上：{user_settings['evening_time']}\n\n✅ 時區已修正為台灣時間！"

                elif message_text.startswith('早上時間 '):
                    time_str = message_text[5:].strip()
                    if is_valid_time_format(time_str):
                        user_settings['morning_time'] = time_str
                        reply_text = f"🌅 已設定早上提醒時間為：{time_str}\n🇹🇼 台灣時間"
                    else:
                        reply_text = "❌ 時間格式不正確，請使用 HH:MM 格式，例如：08:30"

                elif message_text.startswith('晚上時間 '):
                    time_str = message_text[5:].strip()
                    if is_valid_time_format(time_str):
                        user_settings['evening_time'] = time_str
                        reply_text = f"🌙 已設定晚上提醒時間為：{time_str}\n🇹🇼 台灣時間"
                    else:
                        reply_text = "❌ 時間格式不正確，請使用 HH:MM 格式，例如：19:00"

                elif any(keyword in message_text for keyword in ['分鐘後', '小時後', '秒後']):
                    parsed = parse_short_reminder(message_text)
                    if parsed['is_valid']:
                        taiwan_now = get_taiwan_datetime()
                        reminder_time = taiwan_now + timedelta(minutes=parsed['minutes'])
                        reminder_item = {
                            'id': len(short_reminders) + 1,
                            'user_id': user_id,
                            'content': parsed['content'],
                            'reminder_time': reminder_time.isoformat(),
                            'original_value': parsed['original_value'],
                            'unit': parsed['unit']
                        }
                        short_reminders.append(reminder_item)
                        
                        reply_text = f"⏰ 已設定短期提醒：「{parsed['content']}」\n⏳ {parsed['original_value']}{parsed['unit']}後提醒\n📅 提醒時間：{reminder_time.strftime('%H:%M')}\n🇹🇼 台灣時間"
                    else:
                        reply_text = f"❌ {parsed['error']}"

                elif re.match(r'^\d{1,2}:\d{2}.+', message_text):
                    parsed = parse_time_reminder(message_text)
                    if parsed['is_valid']:
                        taiwan_now = get_taiwan_datetime()
                        target_time = taiwan_now.replace(
                            hour=parsed['hours'], 
                            minute=parsed['minutes'], 
                            second=0, 
                            microsecond=0
                        )
                        
                        if target_time <= taiwan_now:
                            target_time += timedelta(days=1)
                        
                        reminder_item = {
                            'id': len(time_reminders) + 1,
                            'user_id': user_id,
                            'content': parsed['content'],
                            'time_string': parsed['time_string'],
                            'reminder_time': target_time.isoformat()
                        }
                        time_reminders.append(reminder_item)
                        
                        date_text = '今天' if target_time.date() == taiwan_now.date() else '明天'
                        reply_text = f"🕐 已設定時間提醒：「{parsed['content']}」\n⏰ {date_text} {parsed['time_string']} 提醒\n🇹🇼 台灣時間"
                    else:
                        reply_text = f"❌ {parsed['error']}"

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

🆕 v3.0 新功能：模組化設計，股票功能獨立！"""

                elif message_text.startswith('新增 '):
                    todo_text = message_text[3:].strip()
                    if todo_text:
                        parsed = parse_date(todo_text)
                        todo_item = {
                            'id': len(todos) + 1,
                            'content': parsed['content'],
                            'created_at': get_taiwan_time(),
                            'completed': False,
                            'has_date': parsed.get('has_date', False),
                            'target_date': parsed.get('date').strftime('%Y/%m/%d') if parsed.get('date') else None,
                            'date_string': parsed.get('date_string')
                        }
                        todos.append(todo_item)
                        
                        if parsed.get('has_date'):
                            reply_text = f"✅ 已新增待辦事項：「{parsed['content']}」\n📅 目標日期：{parsed['date'].strftime('%Y/%m/%d')}\n📋 目前共有 {len(todos)} 項\n🇹🇼 台灣時間建立"
                        else:
                            reply_text = f"✅ 已新增待辦事項：「{parsed['content']}」\n📋 目前共有 {len(todos)} 項\n🇹🇼 台灣時間建立"
                    else:
                        reply_text = "❌ 請輸入要新增的事項內容"

                elif message_text in ['查詢', '清單']:
                    if todos:
                        reply_text = f"📋 待辦事項清單 ({len(todos)} 項)：\n\n"
                        for i, todo in enumerate(todos, 1):
                            status = "✅" if todo.get('completed') else "⭕"
                            date_info = f" 📅{todo.get('target_date', '')}" if todo.get('has_date') else ""
                            reply_text += f"{i}. {status} {todo['content']}{date_info}\n"
                        reply_text += "\n💡 輸入「幫助」查看更多功能"
                    else:
                        reply_text = "📝 目前沒有待辦事項"

                elif message_text.startswith('刪除 '):
                    try:
                        index = int(message_text[3:].strip()) - 1
                        if 0 <= index < len(todos):
                            deleted_todo = todos.pop(index)
                            reply_text = f"🗑️ 已刪除：「{deleted_todo['content']}」"
                        else:
                            reply_text = f"❌ 編號不正確"
                    except:
                        reply_text = "❌ 請輸入正確編號"

                elif message_text.startswith('完成 '):
                    try:
                        index = int(message_text[3:].strip()) - 1
                        if 0 <= index < len(todos):
                            todos[index]['completed'] = True
                            reply_text = f"🎉 已完成：「{todos[index]['content']}」"
                        else:
                            reply_text = f"❌ 編號不正確"
                    except:
                        reply_text = "❌ 請輸入正確編號"

                elif message_text.startswith('每月新增 '):
                    todo_text = message_text[5:].strip()
                    if todo_text:
                        parsed = parse_date(todo_text)
                        
                        if parsed.get('has_date'):
                            if parsed.get('day_only'):
                                day = parsed['day_only']
                                date_display = f"{day}號"
                            elif parsed.get('date_string'):
                                try:
                                    day = int(parsed['date_string'].split('/')[1])
                                    date_display = f"{day}號"
                                except:
                                    day = 1
                                    date_display = "1號"
                            else:
                                day = 1
                                date_display = "1號"
                        else:
                            day = 1
                            date_display = "1號"
                        
                        monthly_item = {
                            'id': len(monthly_todos) + 1,
                            'content': parsed['content'],
                            'created_at': get_taiwan_time(),
                            'has_date': parsed.get('has_date', False),
                            'date_string': parsed.get('date_string'),
                            'day': day,
                            'date_display': date_display
                        }
                        monthly_todos.append(monthly_item)
                        
                        reply_text = f"🔄 已新增每月事項：「{parsed['content']}」\n📅 每月 {date_display} 提醒\n📋 目前共有 {len(monthly_todos)} 項每月事項\n💡 會在前一天預告 + 當天提醒"
                    else:
                        reply_text = "❌ 請輸入要新增的每月事項內容\n💡 例如：每月新增 24號繳水電卡費"

                elif message_text == '每月清單':
                    if monthly_todos:
                        for item in monthly_todos:
                            if not item.get('date_display'):
                                if item.get('has_date') and item.get('date_string'):
                                    try:
                                        day = int(item['date_string'].split('/')[1])
                                        item['date_display'] = f"{day}號"
                                    except:
                                        item['date_display'] = f"{item.get('day', 1)}號"
                                else:
                                    item['date_display'] = f"{item.get('day', 1)}號"
                        
                        reply_text = f"🔄 每月固定事項清單 ({len(monthly_todos)} 項)：\n\n"
                        for i, item in enumerate(monthly_todos, 1):
                            date_display = item.get('date_display', f"{item.get('day', 1)}號")
                            reply_text += f"{i}. 📅 每月 {date_display} - {item['content']}\n"
                        reply_text += f"\n💡 這些事項會在前一天晚上預告，當天早上自動加入待辦清單"
                    else:
                        reply_text = "📝 目前沒有每月固定事項\n💡 輸入「每月新增 5號繳卡費」來新增"

                elif message_text == '測試':
                    reply_text = f"✅ 機器人正常運作！\n🇹🇼 當前台灣時間：{get_taiwan_time()}\n⏰ 待辦提醒功能已啟用\n💰 股票記帳模組已載入\n🔧 模組化設計運作中\n💡 輸入「幫助」或「股票幫助」查看功能"

                else:
                    reply_text = f"您說：{message_text}\n🇹🇼 當前台灣時間：{get_taiwan_time_hhmm()}\n\n💡 輸入「幫助」查看待辦功能\n💰 輸入「股票幫助」查看股票功能"
                
                reply_message(reply_token, reply_text)
        
        return 'OK', 200
    
    except Exception as e:
        print(f"Webhook 處理錯誤: {e} - 台灣時間: {get_taiwan_time()}")
        return 'OK', 200

if __name__ == '__main__':
    print(f"🚀 LINE Bot v3.0 模組化版本啟動 - 台灣時間: {get_taiwan_time()}")
    print(f"📋 待辦事項功能：已啟用")
    print(f"💰 股票記帳模組：已載入")
    print(f"🔧 模組化設計：運作中")
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port)
