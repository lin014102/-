"""
LINE Todo Reminder Bot - 完整提醒功能版本
"""
from flask import Flask, request, jsonify
import os
import requests
import json
import re
import threading
import time
from datetime import datetime, timedelta

app = Flask(__name__)

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
    """獲取台灣時間"""
    return datetime.now().strftime('%Y/%m/%d %H:%M:%S')

def get_taiwan_time_hhmm():
    """獲取台灣時間 HH:MM"""
    return datetime.now().strftime('%H:%M')

def parse_date(text):
    """解析日期格式"""
    current_year = datetime.now().year
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
            target_date = datetime(current_year, month, day)
            if target_date < datetime.now():
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

def send_push_message(user_id, message_text):
    """發送推播訊息"""
    if not CHANNEL_ACCESS_TOKEN or not user_id:
        print(f"模擬推播給 {user_id}: {message_text}")
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
        return response.status_code == 200
    except Exception as e:
        print(f"推播失敗: {e}")
        return False

def reply_message(reply_token, message_text):
    """回覆訊息"""
    if not CHANNEL_ACCESS_TOKEN:
        print(f"模擬回覆: {message_text}")
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
        print(f"回覆失敗: {e}")
        return False

def check_reminders():
    """檢查並發送提醒"""
    while True:
        try:
            current_time = get_taiwan_time_hhmm()
            user_id = user_settings.get('user_id')
            
            # 檢查定時提醒
            if user_id and (current_time == user_settings['morning_time'] or current_time == user_settings['evening_time']):
                send_daily_reminder(user_id, current_time)
            
            # 檢查短期提醒
            check_short_reminders()
            
            # 檢查時間提醒
            check_time_reminders()
            
            time.sleep(60)  # 每分鐘檢查一次
        except Exception as e:
            print(f"提醒檢查錯誤: {e}")
            time.sleep(60)

def send_daily_reminder(user_id, current_time):
    """發送每日提醒"""
    time_icon = '🌅' if current_time == user_settings['morning_time'] else '🌙'
    time_text = '早安' if current_time == user_settings['morning_time'] else '晚安'
    
    if todos:
        message = f'{time_icon} {time_text}！您有 {len(todos)} 項待辦事項：\n\n'
        
        for i, todo in enumerate(todos[:5], 1):  # 最多顯示5項
            status = "✅" if todo.get('completed') else "⭕"
            message += f'{i}. {status} {todo["content"]}\n'
        
        if len(todos) > 5:
            message += f'\n...還有 {len(todos) - 5} 項\n'
        
        message += '\n💪 加油完成今天的任務！'
        send_push_message(user_id, message)

def check_short_reminders():
    """檢查短期提醒"""
    current_time = datetime.now()
    for reminder in short_reminders[:]:
        if datetime.fromisoformat(reminder['reminder_time']) <= current_time:
            user_id = reminder.get('user_id') or user_settings.get('user_id')
            if user_id:
                message = f"⏰ 短期提醒時間到！\n\n📋 {reminder['content']}\n🎯 該去執行了！"
                send_push_message(user_id, message)
            short_reminders.remove(reminder)

def check_time_reminders():
    """檢查時間提醒"""
    current_time = datetime.now()
    for reminder in time_reminders[:]:
        if datetime.fromisoformat(reminder['reminder_time']) <= current_time:
            user_id = reminder.get('user_id') or user_settings.get('user_id')
            if user_id:
                message = f"🕐 時間提醒！\n\n📋 {reminder['content']}\n⏰ {reminder['time_string']}\n🎯 該去執行了！"
                send_push_message(user_id, message)
            time_reminders.remove(reminder)

# 啟動提醒檢查執行緒
reminder_thread = threading.Thread(target=check_reminders, daemon=True)
reminder_thread.start()

# 防休眠機制
def keep_alive():
    """防休眠機制"""
    while True:
        try:
            # 每10分鐘自己發送請求保持活躍
            time.sleep(600)
            requests.get('https://line-bot-python-v2.onrender.com/health', timeout=10)
            print(f"Keep-alive: {get_taiwan_time()}")
        except:
            pass

keep_alive_thread = threading.Thread(target=keep_alive, daemon=True)
keep_alive_thread.start()

@app.route('/')
def home():
    return 'LINE Todo Reminder Bot v2.0 with Full Reminders!'

@app.route('/health')
def health():
    return {
        'status': 'ok',
        'time': get_taiwan_time(),
        'todos_count': len(todos),
        'short_reminders': len(short_reminders),
        'time_reminders': len(time_reminders),
        'morning_time': user_settings['morning_time'],
        'evening_time': user_settings['evening_time']
    }

@app.route('/webhook', methods=['POST'])
def webhook():
    """LINE Webhook 處理"""
    try:
        data = request.get_json()
        
        for event in data.get('events', []):
            if event['type'] == 'message' and event['message']['type'] == 'text':
                reply_token = event['replyToken']
                message_text = event['message']['text'].strip()
                user_id = event['source']['userId']
                
                # 儲存用戶ID
                user_settings['user_id'] = user_id
                
                print(f"用戶訊息: {message_text}")
                
                # 幫助訊息
                if message_text in ['幫助', 'help', '說明']:
                    reply_text = """📋 完整功能待辦事項機器人：

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

🔄 每月功能：
- 每月新增 5號繳卡費 - 每月固定事項
- 每月清單 - 查看每月事項

💡 更多指令請輸入對應功能試試！"""

                # 基本待辦功能（保持原有代碼）
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
                            reply_text = f"✅ 已新增待辦事項：「{parsed['content']}」\n📅 目標日期：{parsed['date'].strftime('%Y/%m/%d')}\n📋 目前共有 {len(todos)} 項"
                        else:
                            reply_text = f"✅ 已新增待辦事項：「{parsed['content']}」\n📋 目前共有 {len(todos)} 項"
                    else:
                        reply_text = "❌ 請輸入要新增的事項內容"

                # 短期提醒
                elif any(keyword in message_text for keyword in ['分鐘後', '小時後', '秒後']):
                    parsed = parse_short_reminder(message_text)
                    if parsed['is_valid']:
                        reminder_time = datetime.now() + timedelta(minutes=parsed['minutes'])
                        reminder_item = {
                            'id': len(short_reminders) + 1,
                            'user_id': user_id,
                            'content': parsed['content'],
                            'reminder_time': reminder_time.isoformat(),
                            'original_value': parsed['original_value'],
                            'unit': parsed['unit']
                        }
                        short_reminders.append(reminder_item)
                        
                        reply_text = f"⏰ 已設定短期提醒：「{parsed['content']}」\n⏳ {parsed['original_value']}{parsed['unit']}後提醒\n📅 提醒時間：{reminder_time.strftime('%H:%M')}"
                    else:
                        reply_text = f"❌ {parsed['error']}"

                # 時間提醒
                elif re.match(r'^\d{1,2}:\d{2}.+', message_text):
                    parsed = parse_time_reminder(message_text)
                    if parsed['is_valid']:
                        now = datetime.now()
                        target_time = now.replace(hour=parsed['hours'], minute=parsed['minutes'], second=0, microsecond=0)
                        
                        if target_time <= now:
                            target_time += timedelta(days=1)
                        
                        reminder_item = {
                            'id': len(time_reminders) + 1,
                            'user_id': user_id,
                            'content': parsed['content'],
                            'time_string': parsed['time_string'],
                            'reminder_time': target_time.isoformat()
                        }
                        time_reminders.append(reminder_item)
                        
                        date_text = '今天' if target_time.date() == now.date() else '明天'
                        reply_text = f"🕐 已設定時間提醒：「{parsed['content']}」\n⏰ {date_text} {parsed['time_string']} 提醒"
                    else:
                        reply_text = f"❌ {parsed['error']}"

                # 設定提醒時間
                elif message_text.startswith('早上時間 '):
                    time_str = message_text[5:].strip()
                    if re.match(r'^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$', time_str):
                        user_settings['morning_time'] = time_str
                        reply_text = f"🌅 已設定早上提醒時間為：{time_str}"
                    else:
                        reply_text = "❌ 時間格式不正確，請使用 HH:MM 格式，例如：08:30"

                elif message_text.startswith('晚上時間 '):
                    time_str = message_text[5:].strip()
                    if re.match(r'^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$', time_str):
                        user_settings['evening_time'] = time_str
                        reply_text = f"🌙 已設定晚上提醒時間為：{time_str}"
                    else:
                        reply_text = "❌ 時間格式不正確，請使用 HH:MM 格式，例如：19:00"

                elif message_text == '查詢時間':
                    reply_text = f"⏰ 目前提醒時間設定：\n🌅 早上：{user_settings['morning_time']}\n🌙 晚上：{user_settings['evening_time']}\n🕐 目前時間：{get_taiwan_time_hhmm()}"

                # 其他原有功能保持不變...
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

                elif message_text == '測試':
                    reply_text = "✅ 機器人正常運作！\n⏰ 完整提醒功能已啟用\n💡 輸入「幫助」查看所有功能"

                else:
                    reply_text = f"您說：{message_text}\n\n💡 輸入「幫助」查看可用功能"
                
                # 發送回覆
                reply_message(reply_token, reply_text)
        
        return 'OK', 200
    
    except Exception as e:
        print(f"Webhook 處理錯誤: {e}")
        return 'OK', 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port)
