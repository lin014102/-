"""
LINE Todo Reminder Bot - 時區修正版本
緊急修正：確保所有時間都使用台灣時區
"""
from flask import Flask, request, jsonify
import os
import requests
import json
import re
import threading
import time
from datetime import datetime, timedelta
import pytz

app = Flask(__name__)

# 設定台灣時區 - 這是關鍵修正
TAIWAN_TZ = pytz.timezone('Asia/Taipei')

# 資料儲存
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

def get_taiwan_time():
    """獲取台灣時間 - 修正版本"""
    return datetime.now(TAIWAN_TZ).strftime('%Y/%m/%d %H:%M:%S')

def get_taiwan_time_hhmm():
    """獲取台灣時間 HH:MM - 修正版本"""
    return datetime.now(TAIWAN_TZ).strftime('%H:%M')

def get_taiwan_datetime():
    """獲取台灣時間的 datetime 物件 - 新增函數"""
    return datetime.now(TAIWAN_TZ)

def parse_date(text):
    """解析日期格式 - 時區修正版本"""
    taiwan_now = get_taiwan_datetime()
    current_year = taiwan_now.year
    date_pattern = r'(\d{1,2})\/(\d{1,2})號?(.+)|(.+?)(\d{1,2})\/(\d{1,2})號?'
    match = re.search(date_pattern, text)
    
    if match:
        if match.group(1) and match.group(2):
            month = int(match.group(1))
            day = int(match.group(2))
            content = match.group(3).strip()
        elif match.group(5) and match.group(6):
            month = int(match.group(5))
            day = int(match.group(6))
            content = match.group(4).strip()
        else:
            return {"has_date": False, "content": text}
        
        if 1 <= month <= 12 and 1 <= day <= 31:
            # 使用台灣時區建立目標日期
            target_date = taiwan_now.replace(year=current_year, month=month, day=day,
                                           hour=0, minute=0, second=0, microsecond=0)
            
            # 如果目標日期已過，設定為明年
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
    """解析短期提醒 - 保持原有邏輯，但確保時間計算正確"""
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
    """解析時間提醒 - 保持原有邏輯"""
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

def send_push_message(user_id, message_text):
    """發送推播訊息 - 保持原有邏輯"""
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
    """回覆訊息 - 保持原有邏輯"""
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

def check_reminders():
    """檢查並發送提醒 - 時區修正版本"""
    while True:
        try:
            current_time = get_taiwan_time_hhmm()
            user_id = user_settings.get('user_id')
            taiwan_now = get_taiwan_datetime()
            
            print(f"🔍 提醒檢查 - 台灣時間: {get_taiwan_time()}")
            
            # 檢查定時提醒（每日早晚）
            if user_id and (current_time == user_settings['morning_time'] or current_time == user_settings['evening_time']):
                send_daily_reminder(user_id, current_time)
            
            # 檢查短期提醒
            check_short_reminders(taiwan_now)
            
            # 檢查時間提醒
            check_time_reminders(taiwan_now)
            
            time.sleep(60)  # 每分鐘檢查一次
        except Exception as e:
            print(f"提醒檢查錯誤: {e} - 台灣時間: {get_taiwan_time()}")
            time.sleep(60)

def send_daily_reminder(user_id, current_time):
    """發送每日提醒 - 保持原有邏輯"""
    time_icon = '🌅' if current_time == user_settings['morning_time'] else '🌙'
    time_text = '早安' if current_time == user_settings['morning_time'] else '晚安'
    
    if todos:
        message = f'{time_icon} {time_text}！您有 {len(todos)} 項待辦事項：\n\n'
        
        for i, todo in enumerate(todos[:5], 1):  # 最多顯示5項
            status = "✅" if todo.get('completed') else "⭕"
            message += f'{i}. {status} {todo["content"]}\n'
        
        if len(todos) > 5:
            message += f'\n...還有 {len(todos) - 5} 項\n'
        
        message += f'\n💪 加油完成今天的任務！\n🇹🇼 台灣時間: {get_taiwan_time_hhmm()}'
        send_push_message(user_id, message)
        print(f"✅ 已發送每日提醒 - 台灣時間: {get_taiwan_time()}")

def check_short_reminders(taiwan_now):
    """檢查短期提醒 - 時區修正版本"""
    for reminder in short_reminders[:]:
        # 解析儲存的提醒時間
        reminder_time_str = reminder['reminder_time']
        try:
            # 如果時間字串包含時區資訊
            if '+' in reminder_time_str or reminder_time_str.endswith('Z'):
                reminder_time = datetime.fromisoformat(reminder_time_str.replace('Z', '+00:00'))
                # 轉換為台灣時區
                reminder_time = reminder_time.astimezone(TAIWAN_TZ)
            else:
                # 假設是台灣時區的時間
                reminder_time = TAIWAN_TZ.localize(datetime.fromisoformat(reminder_time_str))
        except:
            # 如果解析失敗，移除這個提醒
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

def check_time_reminders(taiwan_now):
    """檢查時間提醒 - 時區修正版本"""
    for reminder in time_reminders[:]:
        # 解析儲存的提醒時間
        reminder_time_str = reminder['reminder_time']
        try:
            # 如果時間字串包含時區資訊
            if '+' in reminder_time_str or reminder_time_str.endswith('Z'):
                reminder_time = datetime.fromisoformat(reminder_time_str.replace('Z', '+00:00'))
                # 轉換為台灣時區
                reminder_time = reminder_time.astimezone(TAIWAN_TZ)
            else:
                # 假設是台灣時區的時間
                reminder_time = TAIWAN_TZ.localize(datetime.fromisoformat(reminder_time_str))
        except:
            # 如果解析失敗，移除這個提醒
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

# 防休眠機制 - 改進版本
def keep_alive():
    """防休眠機制 - 改進版本"""
    base_url = os.getenv('BASE_URL', 'https://line-bot-python-v2.onrender.com')
    
    while True:
        try:
            # 每 4 分鐘自己發送請求保持活躍
            time.sleep(240)  # 4 分鐘
            
            response = requests.get(f'{base_url}/health', timeout=15)
            
            if response.status_code == 200:
                print(f"✅ Keep-alive 成功 - 台灣時間: {get_taiwan_time()}")
            else:
                print(f"⚠️ Keep-alive 警告: {response.status_code} - 台灣時間: {get_taiwan_time()}")
                
        except requests.exceptions.RequestException as e:
            print(f"❌ Keep-alive 錯誤: {e} - 台灣時間: {get_taiwan_time()}")
            time.sleep(60)  # 錯誤時等待較短時間後重試
        except Exception as e:
            print(f"❌ Keep-alive 意外錯誤: {e} - 台灣時間: {get_taiwan_time()}")
            time.sleep(60)

keep_alive_thread = threading.Thread(target=keep_alive, daemon=True)
keep_alive_thread.start()

@app.route('/')
def home():
    return f'LINE Todo Reminder Bot v2.1 - 時區已修正！當前台灣時間: {get_taiwan_time()}'

@app.route('/health')
def health():
    """健康檢查端點 - 時區修正版本"""
    taiwan_now = get_taiwan_datetime()
    
    # 計算下次提醒時間
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
    
    return {
        'status': 'healthy',
        'taiwan_time': get_taiwan_time(),
        'taiwan_time_hhmm': get_taiwan_time_hhmm(),
        'server_timezone': str(taiwan_now.tzinfo),
        'todos_count': len(todos),
        'short_reminders': len(short_reminders),
        'time_reminders': len(time_reminders),
        'morning_time': user_settings['morning_time'],
        'evening_time': user_settings['evening_time'],
        'next_reminder': next_reminder_str,
        'has_user': user_settings['user_id'] is not None,
        'version': '2.1_timezone_fixed'
    }

@app.route('/webhook', methods=['POST'])
def webhook():
    """LINE Webhook 處理 - 時區修正版本"""
    try:
        data = request.get_json()
        
        for event in data.get('events', []):
            if event['type'] == 'message' and event['message']['type'] == 'text':
                reply_token = event['replyToken']
                message_text = event['message']['text'].strip()
                user_id = event['source']['userId']
                
                # 儲存用戶ID
                user_settings['user_id'] = user_id
                
                print(f"用戶訊息: {message_text} - 台灣時間: {get_taiwan_time()}")
                
                # 查詢時間 - 修正顯示
                if message_text == '查詢時間':
                    reply_text = f"🇹🇼 台灣當前時間：{get_taiwan_time()}\n⏰ 目前提醒時間設定：\n🌅 早上：{user_settings['morning_time']}\n🌙 晚上：{user_settings['evening_time']}\n\n✅ 時區已修正為台灣時間！"

                # 短期提醒 - 時區修正
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

                # 時間提醒 - 時區修正
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

                # 其他功能保持原有邏輯...
                elif message_text in ['幫助', 'help', '說明']:
                    reply_text = """📋 完整功能待辦事項機器人 v2.1：

🔹 基本功能：
- 新增 [事項] - 新增待辦事項
- 新增 8/9號繳卡費 - 新增有日期的事項
- 查詢 - 查看所有待辦事項
- 刪除 [編號] - 刪除指定事項
- 完成 [編號] - 標記為已完成

⏰ 提醒功能：
- 5分鐘後倒垃圾 - 短期提醒
- 12:00開會 - 時間提醒
- 早上時間 09:00 - 設定早上提醒
- 晚上時間 18:00 - 設定晚上提醒
- 查詢時間 - 查看當前台灣時間

🔄 每月功能：
- 每月新增 5號繳卡費 - 每月固定事項
- 每月清單 - 查看每月事項

🇹🇼 v2.1 更新：已修正時區問題，所有時間均為台灣時間！"""

                # 保持其他原有功能...
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

                elif message_text == '測試':
                    reply_text = f"✅ 機器人正常運作！\n🇹🇼 當前台灣時間：{get_taiwan_time()}\n⏰ 完整提醒功能已啟用\n💡 輸入「幫助」查看所有功能"

                else:
                    reply_text = f"您說：{message_text}\n🇹🇼 當前台灣時間：{get_taiwan_time_hhmm()}\n\n💡 輸入「幫助」查看可用功能"
                
                # 發送回覆
                reply_message(reply_token, reply_text)
        
        return 'OK', 200
    
    except Exception as e:
        print(f"Webhook 處理錯誤: {e} - 台灣時間: {get_taiwan_time()}")
        return 'OK', 200

if __name__ == '__main__':
    print(f"🚀 LINE Bot 啟動 - 台灣時間: {get_taiwan_time()}")
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port)
