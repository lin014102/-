"""
reminder_bot.py - 提醒機器人模組
從 app.py 拆分出來
"""
import re
import threading
import time
from datetime import datetime, timedelta
from utils.time_utils import get_taiwan_time, get_taiwan_time_hhmm, get_taiwan_datetime, TAIWAN_TZ
from utils.line_api import send_push_message

class ReminderBot:
    """提醒機器人"""
    
    def __init__(self, todo_manager):
        """初始化提醒機器人"""
        self.todo_manager = todo_manager
        self.short_reminders = []
        self.time_reminders = []
        self.user_settings = {
            'morning_time': '09:00',
            'evening_time': '18:00',
            'user_id': None
        }
        # 新增：防重複提醒的日期追蹤
        self.last_reminders = {
            'daily_morning_date': None,
            'daily_evening_date': None,
            'dated_todo_preview_date': None,
            'dated_todo_morning_date': None,
            'dated_todo_evening_date': None
        }
        self.reminder_thread = None
    
    def parse_short_reminder(self, text):
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
    
    def parse_time_reminder(self, text):
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
    
    def add_short_reminder(self, message_text, user_id):
        """新增短期提醒"""
        parsed = self.parse_short_reminder(message_text)
        if parsed['is_valid']:
            taiwan_now = get_taiwan_datetime()
            reminder_time = taiwan_now + timedelta(minutes=parsed['minutes'])
            reminder_item = {
                'id': len(self.short_reminders) + 1,
                'user_id': user_id,
                'content': parsed['content'],
                'reminder_time': reminder_time.isoformat(),
                'original_value': parsed['original_value'],
                'unit': parsed['unit']
            }
            self.short_reminders.append(reminder_item)
            
            return f"⏰ 已設定短期提醒：「{parsed['content']}」\n⏳ {parsed['original_value']}{parsed['unit']}後提醒\n📅 提醒時間：{reminder_time.strftime('%H:%M')}\n🇹🇼 台灣時間"
        else:
            return f"❌ {parsed['error']}"
    
    def add_time_reminder(self, message_text, user_id):
        """新增時間提醒"""
        parsed = self.parse_time_reminder(message_text)
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
                'id': len(self.time_reminders) + 1,
                'user_id': user_id,
                'content': parsed['content'],
                'time_string': parsed['time_string'],
                'reminder_time': target_time.isoformat()
            }
            self.time_reminders.append(reminder_item)
            
            date_text = '今天' if target_time.date() == taiwan_now.date() else '明天'
            return f"🕐 已設定時間提醒：「{parsed['content']}」\n⏰ {date_text} {parsed['time_string']} 提醒\n🇹🇼 台灣時間"
        else:
            return f"❌ {parsed['error']}"
    
    def set_morning_time(self, time_str):
        """設定早上提醒時間"""
        self.user_settings['morning_time'] = time_str
        # 重置防重複標記，允許新時間立即提醒
        self.last_reminders['daily_morning_date'] = None
        self.last_reminders['dated_todo_morning_date'] = None
        return f"🌅 已設定早上提醒時間為：{time_str}\n🇹🇼 台灣時間\n💡 新時間將立即生效"
    
    def set_evening_time(self, time_str):
        """設定晚上提醒時間"""
        self.user_settings['evening_time'] = time_str
        # 重置防重複標記，允許新時間立即提醒
        self.last_reminders['daily_evening_date'] = None
        self.last_reminders['dated_todo_evening_date'] = None
        self.last_reminders['dated_todo_preview_date'] = None
        return f"🌙 已設定晚上提醒時間為：{time_str}\n🇹🇼 台灣時間\n💡 新時間將立即生效"
    
    def set_user_id(self, user_id):
        """設定用戶ID"""
        self.user_settings['user_id'] = user_id
    
    def get_time_settings(self):
        """獲取時間設定"""
        return f"🇹🇼 台灣當前時間：{get_taiwan_time()}\n⏰ 目前提醒時間設定：\n🌅 早上：{self.user_settings['morning_time']}\n🌙 晚上：{self.user_settings['evening_time']}\n\n✅ 時區已修正為台灣時間！"
    
    def check_reminders(self):
        """檢查並發送提醒 - 主要循環"""
        while True:
            try:
                current_time = get_taiwan_time_hhmm()
                user_id = self.user_settings.get('user_id')
                taiwan_now = get_taiwan_datetime()
                today_date = taiwan_now.strftime('%Y-%m-%d')
                
                print(f"🔍 提醒檢查 - 台灣時間: {get_taiwan_time()}")
                
                # 檢查每日提醒（加入防重複機制）
                if user_id:
                    if (current_time == self.user_settings['morning_time'] and 
                        self.last_reminders['daily_morning_date'] != today_date):
                        self.send_daily_reminder(user_id, current_time)
                        self.last_reminders['daily_morning_date'] = today_date
                    
                    elif (current_time == self.user_settings['evening_time'] and 
                          self.last_reminders['daily_evening_date'] != today_date):
                        self.send_daily_reminder(user_id, current_time)
                        self.last_reminders['daily_evening_date'] = today_date
                
                # 檢查每月預告（防重複）
                if (user_id and current_time == self.user_settings['evening_time'] and 
                    self.last_reminders['daily_evening_date'] == today_date):  # 確保晚上提醒已發送
                    self.check_monthly_preview(taiwan_now, user_id)
                
                # 檢查每月提醒
                if current_time == "09:00":
                    self.check_monthly_reminders(taiwan_now, user_id)
                
                # 新增：檢查有日期待辦事項的預告（前一天晚上）
                if (user_id and current_time == self.user_settings['evening_time'] and 
                    self.last_reminders['dated_todo_preview_date'] != today_date):
                    self.check_dated_todo_preview(taiwan_now, user_id)
                    self.last_reminders['dated_todo_preview_date'] = today_date
                
                # 新增：檢查有日期待辦事項的當天提醒
                if user_id:
                    if (current_time == self.user_settings['morning_time'] and 
                        self.last_reminders['dated_todo_morning_date'] != today_date):
                        self.check_dated_todo_reminders(taiwan_now, user_id, 'morning')
                        self.last_reminders['dated_todo_morning_date'] = today_date
                    
                    elif (current_time == self.user_settings['evening_time'] and 
                          self.last_reminders['dated_todo_evening_date'] != today_date):
                        self.check_dated_todo_reminders(taiwan_now, user_id, 'evening')
                        self.last_reminders['dated_todo_evening_date'] = today_date
                
                # 檢查短期和時間提醒
                self.check_short_reminders(taiwan_now)
                self.check_time_reminders(taiwan_now)
                
                time.sleep(60)
            except Exception as e:
                print(f"提醒檢查錯誤: {e} - 台灣時間: {get_taiwan_time()}")
                time.sleep(60)
    
    def send_daily_reminder(self, user_id, current_time):
        """發送每日提醒"""
        time_icon = '🌅' if current_time == self.user_settings['morning_time'] else '🌙'
        time_text = '早安' if current_time == self.user_settings['morning_time'] else '晚安'
        
        todos = self.todo_manager.todos
        if todos:
            pending_todos = self.todo_manager.get_pending_todos()
            completed_todos = self.todo_manager.get_completed_todos()
            
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
                
                if current_time == self.user_settings['morning_time']:
                    message += f'\n💪 新的一天開始了！加油完成這些任務！'
                else:
                    message += f'\n🌙 檢查一下今天的進度吧！記得為明天做準備！'
                    
                message += f'\n🇹🇼 台灣時間: {get_taiwan_time_hhmm()}'
                
                send_push_message(user_id, message)
                print(f"✅ 已發送每日提醒 ({len(pending_todos)} 項待辦) - 台灣時間: {get_taiwan_time()}")
            else:
                if current_time == self.user_settings['morning_time']:
                    message = f'{time_icon} {time_text}！🎉 太棒了！目前沒有待辦事項\n💡 可以新增今天要做的事情'
                else:
                    message = f'{time_icon} {time_text}！🎉 太棒了！今天的任務都完成了\n😴 好好休息，為明天準備新的目標！'
                
                message += f'\n🇹🇼 台灣時間: {get_taiwan_time_hhmm()}'
                send_push_message(user_id, message)
                print(f"✅ 已發送每日提醒 (無待辦事項) - 台灣時間: {get_taiwan_time()}")
        else:
            if current_time == self.user_settings['morning_time']:
                message = f'{time_icon} {time_text}！✨ 新的一天開始了！\n💡 輸入「新增 事項名稱」來建立今天的目標'
            else:
                message = f'{time_icon} {time_text}！😌 今天過得如何？\n💡 別忘了為明天規劃一些目標'
            
            message += f'\n🇹🇼 台灣時間: {get_taiwan_time_hhmm()}'
            send_push_message(user_id, message)
            print(f"✅ 已發送每日提醒 (首次使用) - 台灣時間: {get_taiwan_time()}")
    
    def check_monthly_preview(self, taiwan_now, user_id):
        """檢查明天的每月提醒"""
        if not self.todo_manager.monthly_todos or not user_id:
            return
        
        tomorrow = taiwan_now + timedelta(days=1)
        tomorrow_day = tomorrow.day
        
        monthly_items_tomorrow = self.todo_manager.get_monthly_items_for_day(tomorrow_day)
        
        if monthly_items_tomorrow:
            message = f"📅 每月提醒預告！\n\n明天 ({tomorrow.strftime('%m/%d')}) 有 {len(monthly_items_tomorrow)} 項每月固定事項：\n\n"
            
            for i, item in enumerate(monthly_items_tomorrow, 1):
                message += f"{i}. 🔄 {item['content']}\n"
            
            message += f"\n💡 明天早上會自動加入待辦清單並提醒您\n🇹🇼 台灣時間: {get_taiwan_time_hhmm()}"
            
            send_push_message(user_id, message)
            print(f"✅ 已發送每月預告提醒，明天有 {len(monthly_items_tomorrow)} 項事項 - 台灣時間: {get_taiwan_time()}")
    
    def check_monthly_reminders(self, taiwan_now, user_id):
        """檢查每月提醒"""
        if not self.todo_manager.monthly_todos or not user_id:
            return
        
        added_items = self.todo_manager.add_monthly_todo_to_daily(taiwan_now)
        
        if added_items:
            message = f"🔄 每月提醒！今天 ({taiwan_now.strftime('%m/%d')}) 的固定事項：\n\n"
            for i, content in enumerate(added_items, 1):
                message += f"{i}. 📅 {content}\n"
            
            message += f"\n✅ 已自動加入今日待辦清單"
            message += f"\n💡 昨天已經預告過，現在正式提醒！"
            message += f"\n🇹🇼 台灣時間: {get_taiwan_time_hhmm()}"
            
            send_push_message(user_id, message)
            print(f"✅ 已發送每月正式提醒，加入 {len(added_items)} 項事項 - 台灣時間: {get_taiwan_time()}")
    
    def check_dated_todo_preview(self, taiwan_now, user_id):
        """新增：檢查明天有日期的待辦事項預告"""
        if not user_id:
            return
        
        tomorrow = taiwan_now + timedelta(days=1)
        tomorrow_str = tomorrow.strftime('%Y/%m/%d')
        
        # 獲取明天的有日期待辦事項（未完成的）
        tomorrow_todos = []
        for todo in self.todo_manager.get_pending_todos():
            if todo.get('has_date') and todo.get('target_date') == tomorrow_str:
                tomorrow_todos.append(todo)
        
        if tomorrow_todos:
            message = f"📅 明日待辦提醒！\n\n明天 ({tomorrow.strftime('%m/%d')}) 有 {len(tomorrow_todos)} 項待辦事項：\n\n"
            
            for i, todo in enumerate(tomorrow_todos, 1):
                message += f"{i}. 📋 {todo['content']}\n"
            
            message += f"\n💡 明天早上和晚上會持續提醒，直到完成或刪除\n🇹🇼 台灣時間: {get_taiwan_time_hhmm()}"
            
            send_push_message(user_id, message)
            print(f"✅ 已發送明日待辦預告，明天有 {len(tomorrow_todos)} 項有日期事項 - 台灣時間: {get_taiwan_time()}")
    
    def check_dated_todo_reminders(self, taiwan_now, user_id, time_type):
        """新增：檢查有日期待辦事項的當天提醒"""
        if not user_id:
            return
        
        today_str = taiwan_now.strftime('%Y/%m/%d')
        time_icon = '🌅' if time_type == 'morning' else '🌙'
        time_text = '早上' if time_type == 'morning' else '晚上'
        
        # 獲取今天的有日期待辦事項（未完成的）
        today_todos = []
        for todo in self.todo_manager.get_pending_todos():
            if todo.get('has_date') and todo.get('target_date') == today_str:
                today_todos.append(todo)
        
        if today_todos:
            message = f"{time_icon} {time_text}特別提醒！\n\n今天 ({taiwan_now.strftime('%m/%d')}) 有 {len(today_todos)} 項重要事項：\n\n"
            
            for i, todo in enumerate(today_todos, 1):
                message += f"{i}. 🎯 {todo['content']}\n"
            
            if time_type == 'morning':
                message += f"\n💪 今天要完成這些重要任務！"
            else:
                message += f"\n🌙 檢查一下今天的重要事項完成了嗎？"
            
            message += f"\n💡 完成後請標記完成或刪除，以停止提醒"
            message += f"\n🇹🇼 台灣時間: {get_taiwan_time_hhmm()}"
            
            send_push_message(user_id, message)
            print(f"✅ 已發送今日有日期待辦提醒 ({time_text}，{len(today_todos)} 項) - 台灣時間: {get_taiwan_time()}")
    
    def check_short_reminders(self, taiwan_now):
        """檢查短期提醒"""
        for reminder in self.short_reminders[:]:
            reminder_time_str = reminder['reminder_time']
            try:
                if '+' in reminder_time_str or reminder_time_str.endswith('Z'):
                    reminder_time = datetime.fromisoformat(reminder_time_str.replace('Z', '+00:00'))
                    reminder_time = reminder_time.astimezone(TAIWAN_TZ)
                else:
                    reminder_time = TAIWAN_TZ.localize(datetime.fromisoformat(reminder_time_str))
            except:
                print(f"⚠️ 無法解析提醒時間: {reminder_time_str}")
                self.short_reminders.remove(reminder)
                continue
            
            if reminder_time <= taiwan_now:
                user_id = reminder.get('user_id') or self.user_settings.get('user_id')
                if user_id:
                    message = f"⏰ 短期提醒時間到！\n\n📋 {reminder['content']}\n🎯 該去執行了！\n🇹🇼 台灣時間: {get_taiwan_time_hhmm()}"
                    send_push_message(user_id, message)
                    print(f"✅ 已發送短期提醒: {reminder['content']} - 台灣時間: {get_taiwan_time()}")
                self.short_reminders.remove(reminder)
    
    def check_time_reminders(self, taiwan_now):
        """檢查時間提醒"""
        for reminder in self.time_reminders[:]:
            reminder_time_str = reminder['reminder_time']
            try:
                if '+' in reminder_time_str or reminder_time_str.endswith('Z'):
                    reminder_time = datetime.fromisoformat(reminder_time_str.replace('Z', '+00:00'))
                    reminder_time = reminder_time.astimezone(TAIWAN_TZ)
                else:
                    reminder_time = TAIWAN_TZ.localize(datetime.fromisoformat(reminder_time_str))
            except:
                print(f"⚠️ 無法解析提醒時間: {reminder_time_str}")
                self.time_reminders.remove(reminder)
                continue
                
            if reminder_time <= taiwan_now:
                user_id = reminder.get('user_id') or self.user_settings.get('user_id')
                if user_id:
                    message = f"🕐 時間提醒！\n\n📋 {reminder['content']}\n⏰ {reminder['time_string']}\n🎯 該去執行了！\n🇹🇼 台灣時間: {get_taiwan_time_hhmm()}"
                    send_push_message(user_id, message)
                    print(f"✅ 已發送時間提醒: {reminder['content']} - 台灣時間: {get_taiwan_time()}")
                self.time_reminders.remove(reminder)
    
    def start_reminder_thread(self):
        """啟動提醒執行緒"""
        if self.reminder_thread is None or not self.reminder_thread.is_alive():
            self.reminder_thread = threading.Thread(target=self.check_reminders, daemon=True)
            self.reminder_thread.start()
            print("✅ 提醒機器人執行緒已啟動")
    
    def get_reminder_counts(self):
        """獲取提醒數量"""
        return {
            'short_reminders': len(self.short_reminders),
            'time_reminders': len(self.time_reminders)
        }
