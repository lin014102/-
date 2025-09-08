"""
reminder_bot.py - 提醒機器人模組 (MongoDB Atlas 版本) + 帳單金額整合
從 app.py 拆分出來，新增帳單金額顯示功能
"""
import re
import os
import threading
import time
from datetime import datetime, timedelta
from pymongo import MongoClient
from utils.time_utils import get_taiwan_time, get_taiwan_time_hhmm, get_taiwan_datetime, TAIWAN_TZ
from utils.line_api import send_push_message

class ReminderBot:
    """提醒機器人 (MongoDB Atlas 版本) + 帳單金額整合"""
    
    def __init__(self, todo_manager):
        """初始化提醒機器人"""
        self.todo_manager = todo_manager
        
        # 初始化 MongoDB 連接（與 todo_manager 共用相同邏輯）
        mongodb_uri = os.getenv('MONGODB_URI')
        if not mongodb_uri:
            print("⚠️ 警告：ReminderBot 找不到 MONGODB_URI 環境變數，使用記憶體模式")
            self._short_reminders = []
            self._time_reminders = []
            self._bill_amounts = {}  # 新增：帳單金額記憶體儲存
            self.use_mongodb = False
        else:
            try:
                # 連接到 MongoDB Atlas
                self.client = MongoClient(mongodb_uri)
                
                # 指定資料庫名稱 (如果 URI 中沒有預設資料庫)
                try:
                    self.db = self.client.get_default_database()
                except:
                    # 如果沒有預設資料庫，使用 'reminderbot' 作為資料庫名稱
                    self.db = self.client.reminderbot
                
                self.short_reminders_collection = self.db.short_reminders
                self.time_reminders_collection = self.db.time_reminders
                self.user_settings_collection = self.db.user_settings
                self.bill_amounts_collection = self.db.bill_amounts  # 新增：帳單金額集合
                self.use_mongodb = True
                print("✅ ReminderBot 成功連接到 MongoDB Atlas")
            except Exception as e:
                print(f"❌ ReminderBot MongoDB 連接失敗: {e}")
                print("⚠️ ReminderBot 使用記憶體模式")
                self._short_reminders = []
                self._time_reminders = []
                self._bill_amounts = {}  # 新增：帳單金額記憶體儲存
                self.use_mongodb = False
        
        # 載入或初始化用戶設定
        self.user_settings = self._load_user_settings()
        
        # 新增：防重複提醒的日期追蹤
        self.last_reminders = {
            'daily_morning_date': None,
            'daily_evening_date': None,
            'dated_todo_preview_date': None,
            'dated_todo_morning_date': None,
            'dated_todo_evening_date': None
        }
        self.reminder_thread = None
    
    # ===== 新增：帳單金額管理功能 =====
    
    def update_bill_amount(self, bank_name, amount, due_date, statement_date=None):
        """
        更新銀行卡費金額 (由帳單分析模組呼叫)
        
        Args:
            bank_name: 銀行名稱 (如 "永豐銀行")
            amount: 應繳金額 (如 "NT$15,000")
            due_date: 繳款截止日 (如 "2025/01/24")
            statement_date: 帳單日期 (可選)
        """
        try:
            # 標準化銀行名稱
            normalized_bank = self._normalize_bank_name(bank_name)
            
            # 取得月份 (用繳款截止日)
            due_datetime = datetime.strptime(due_date, '%Y/%m/%d')
            month_key = due_datetime.strftime('%Y-%m')
            
            bill_data = {
                'bank_name': normalized_bank,
                'original_bank_name': bank_name,
                'amount': amount,
                'due_date': due_date,
                'statement_date': statement_date,
                'month': month_key,
                'updated_at': datetime.now().isoformat()
            }
            
            if self.use_mongodb:
                # 更新或新增到 MongoDB
                self.bill_amounts_collection.update_one(
                    {
                        'bank_name': normalized_bank,
                        'month': month_key
                    },
                    {'$set': bill_data},
                    upsert=True
                )
            else:
                # 記憶體模式
                if normalized_bank not in self._bill_amounts:
                    self._bill_amounts[normalized_bank] = {}
                self._bill_amounts[normalized_bank][month_key] = bill_data
            
            print(f"✅ 更新 {normalized_bank} {month_key} 卡費: {amount}")
            return True
            
        except Exception as e:
            print(f"❌ 更新卡費金額失敗: {e}")
            return False
    
    def _normalize_bank_name(self, bank_name):
        """簡化版銀行名稱標準化 - 使用關鍵字模糊匹配"""
        name = bank_name.upper()
        
        if '永豐' in name or 'SINOPAC' in name:
            return '永豐'
        if '台新' in name or 'TAISHIN' in name:
            return '台新'
        if '國泰' in name or 'CATHAY' in name:
            return '國泰'
        if '星展' in name or 'DBS' in name:
            return '星展'
        if '匯豐' in name or 'HSBC' in name:
            return '匯豐'
        if '玉山' in name or 'ESUN' in name or 'E.SUN' in name:
            return '玉山'
        if '聯邦' in name or 'UNION' in name:
            return '聯邦'
        
        return bank_name  # 找不到就回傳原名
    
    def get_bill_amount(self, bank_name, target_month=None):
        """
        取得指定銀行的最新卡費金額
        
        Args:
            bank_name: 銀行名稱 (如 "永豐")
            target_month: 目標月份 (可選，格式：2025-01)
            
        Returns:
            dict: {amount: str, due_date: str} 或 None
        """
        try:
            normalized_bank = self._normalize_bank_name(bank_name)
            
            if self.use_mongodb:
                query = {'bank_name': normalized_bank}
                if target_month:
                    query['month'] = target_month
                
                # 查詢最新資料
                result = self.bill_amounts_collection.find(query).sort('updated_at', -1).limit(1)
                
                for bill_data in result:
                    return {
                        'amount': bill_data['amount'],
                        'due_date': bill_data['due_date'],
                        'statement_date': bill_data.get('statement_date'),
                        'month': bill_data['month']
                    }
            else:
                # 記憶體模式
                if normalized_bank in self._bill_amounts:
                    months = sorted(self._bill_amounts[normalized_bank].keys(), reverse=True)
                    if months:
                        latest_data = self._bill_amounts[normalized_bank][months[0]]
                        return {
                            'amount': latest_data['amount'],
                            'due_date': latest_data['due_date'],
                            'statement_date': latest_data.get('statement_date'),
                            'month': latest_data['month']
                        }
            
            return None
            
        except Exception as e:
            print(f"❌ 取得卡費金額失敗: {e}")
            return None
    
    def _enhance_todo_with_bill_amount(self, todo_content):
        """簡化版待辦事項增強 - 使用關鍵字匹配"""
        try:
            # 檢查是否為卡費相關事項
            if '卡費' in todo_content:
                bill_info = None
                
                # 用簡單的關鍵字檢查
                if '永豐' in todo_content:
                    bill_info = self.get_bill_amount('永豐')
                elif '台新' in todo_content:
                    bill_info = self.get_bill_amount('台新')
                elif '國泰' in todo_content:
                    bill_info = self.get_bill_amount('國泰')
                elif '星展' in todo_content:
                    bill_info = self.get_bill_amount('星展')
                elif '匯豐' in todo_content:
                    bill_info = self.get_bill_amount('匯豐')
                elif '玉山' in todo_content:
                    bill_info = self.get_bill_amount('玉山')
                elif '聯邦' in todo_content:
                    bill_info = self.get_bill_amount('聯邦')
                
                if bill_info:
                    # 簡化日期格式 (從 2025/01/24 轉為 1/24)
                    try:
                        due_date = bill_info['due_date']
                        if '/' in due_date and len(due_date.split('/')) == 3:
                            _, month, day = due_date.split('/')
                            formatted_date = f"{int(month)}/{int(day)}"
                        else:
                            formatted_date = due_date
                        
                        return f"{todo_content} - {bill_info['amount']}（截止：{formatted_date}）"
                    except:
                        return f"{todo_content} - {bill_info['amount']}"
            
            return todo_content
            
        except Exception as e:
            print(f"增強待辦事項顯示失敗: {e}")
            return todo_content
    
    # ===== 以下為原有功能，略作修改 =====
    
    def _load_user_settings(self):
        """載入用戶設定"""
        if self.use_mongodb:
            settings = self.user_settings_collection.find_one({"type": "main_settings"})
            if settings:
                return {
                    'morning_time': settings.get('morning_time', '09:00'),
                    'evening_time': settings.get('evening_time', '18:00'),
                    'user_id': settings.get('user_id', None)
                }
        
        # 預設設定
        return {
            'morning_time': '09:00',
            'evening_time': '18:00',
            'user_id': None
        }
    
    def _save_user_settings(self):
        """儲存用戶設定"""
        if self.use_mongodb:
            self.user_settings_collection.update_one(
                {"type": "main_settings"},
                {"$set": {
                    "type": "main_settings",
                    "morning_time": self.user_settings['morning_time'],
                    "evening_time": self.user_settings['evening_time'],
                    "user_id": self.user_settings['user_id']
                }},
                upsert=True
            )
    
    def _get_short_reminders(self):
        """獲取短期提醒列表"""
        if self.use_mongodb:
            return list(self.short_reminders_collection.find({}))
        else:
            return self._short_reminders
    
    def _get_time_reminders(self):
        """獲取時間提醒列表"""
        if self.use_mongodb:
            return list(self.time_reminders_collection.find({}))
        else:
            return self._time_reminders
    
    def _add_short_reminder(self, reminder_item):
        """新增短期提醒"""
        if self.use_mongodb:
            result = self.short_reminders_collection.insert_one(reminder_item)
            reminder_item['_id'] = result.inserted_id
        else:
            self._short_reminders.append(reminder_item)
    
    def _add_time_reminder(self, reminder_item):
        """新增時間提醒"""
        if self.use_mongodb:
            result = self.time_reminders_collection.insert_one(reminder_item)
            reminder_item['_id'] = result.inserted_id
        else:
            self._time_reminders.append(reminder_item)
    
    def _remove_short_reminder(self, reminder_id):
        """移除短期提醒"""
        if self.use_mongodb:
            self.short_reminders_collection.delete_one({"id": reminder_id})
        else:
            self._short_reminders = [r for r in self._short_reminders if r['id'] != reminder_id]
    
    def _remove_time_reminder(self, reminder_id):
        """移除時間提醒"""
        if self.use_mongodb:
            self.time_reminders_collection.delete_one({"id": reminder_id})
        else:
            self._time_reminders = [r for r in self._time_reminders if r['id'] != reminder_id]
    
    def _get_next_short_reminder_id(self):
        """獲取下一個短期提醒 ID"""
        short_reminders = self._get_short_reminders()
        if not short_reminders:
            return 1
        return max(r['id'] for r in short_reminders) + 1
    
    def _get_next_time_reminder_id(self):
        """獲取下一個時間提醒 ID"""
        time_reminders = self._get_time_reminders()
        if not time_reminders:
            return 1
        return max(r['id'] for r in time_reminders) + 1
    
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
                'id': self._get_next_short_reminder_id(),
                'user_id': user_id,
                'content': parsed['content'],
                'reminder_time': reminder_time.isoformat(),
                'original_value': parsed['original_value'],
                'unit': parsed['unit']
            }
            self._add_short_reminder(reminder_item)
            
            status_msg = "💾 已同步到雲端" if self.use_mongodb else ""
            return f"⏰ 已設定短期提醒：「{parsed['content']}」\n⏳ {parsed['original_value']}{parsed['unit']}後提醒\n📅 提醒時間：{reminder_time.strftime('%H:%M')}\n🇹🇼 台灣時間\n{status_msg}"
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
                'id': self._get_next_time_reminder_id(),
                'user_id': user_id,
                'content': parsed['content'],
                'time_string': parsed['time_string'],
                'reminder_time': target_time.isoformat()
            }
            self._add_time_reminder(reminder_item)
            
            date_text = '今天' if target_time.date() == taiwan_now.date() else '明天'
            status_msg = "💾 已同步到雲端" if self.use_mongodb else ""
            return f"🕐 已設定時間提醒：「{parsed['content']}」\n⏰ {date_text} {parsed['time_string']} 提醒\n🇹🇼 台灣時間\n{status_msg}"
        else:
            return f"❌ {parsed['error']}"
    
    def set_morning_time(self, time_str):
        """設定早上提醒時間"""
        self.user_settings['morning_time'] = time_str
        self._save_user_settings()
        # 重置防重複標記，允許新時間立即提醒
        self.last_reminders['daily_morning_date'] = None
        self.last_reminders['dated_todo_morning_date'] = None
        status_msg = "💾 已同步到雲端" if self.use_mongodb else ""
        return f"🌅 已設定早上提醒時間為：{time_str}\n🇹🇼 台灣時間\n💡 新時間將立即生效\n{status_msg}"
    
    def set_evening_time(self, time_str):
        """設定晚上提醒時間"""
        self.user_settings['evening_time'] = time_str
        self._save_user_settings()
        # 重置防重複標記，允許新時間立即提醒
        self.last_reminders['daily_evening_date'] = None
        self.last_reminders['dated_todo_evening_date'] = None
        self.last_reminders['dated_todo_preview_date'] = None
        status_msg = "💾 已同步到雲端" if self.use_mongodb else ""
        return f"🌙 已設定晚上提醒時間為：{time_str}\n🇹🇼 台灣時間\n💡 新時間將立即生效\n{status_msg}"
    
    def set_user_id(self, user_id):
        """設定用戶ID"""
        self.user_settings['user_id'] = user_id
        self._save_user_settings()
    
    def get_time_settings(self):
        """獲取時間設定"""
        status_msg = "💾 設定已同步到雲端" if self.use_mongodb else ""
        return f"🇹🇼 台灣當前時間：{get_taiwan_time()}\n⏰ 目前提醒時間設定：\n🌅 早上：{self.user_settings['morning_time']}\n🌙 晚上：{self.user_settings['evening_time']}\n\n✅ 時區已修正為台灣時間！\n{status_msg}"
    
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
        """發送每日提醒（修改版，包含帳單金額）"""
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
                    
                    # 🆕 增強顯示：加入帳單金額
                    enhanced_content = self._enhance_todo_with_bill_amount(todo["content"])
                    
                    message += f'{i}. ⭕ {enhanced_content}{date_info}\n'
                
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
        """檢查明天有日期的待辦事項預告"""
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
        """檢查有日期待辦事項的當天提醒"""
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
        short_reminders = self._get_short_reminders()
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
                self._remove_short_reminder(reminder['id'])
                continue
            
            if reminder_time <= taiwan_now:
                user_id = reminder.get('user_id') or self.user_settings.get('user_id')
                if user_id:
                    message = f"⏰ 短期提醒時間到！\n\n📋 {reminder['content']}\n🎯 該去執行了！\n🇹🇼 台灣時間: {get_taiwan_time_hhmm()}"
                    send_push_message(user_id, message)
                    print(f"✅ 已發送短期提醒: {reminder['content']} - 台灣時間: {get_taiwan_time()}")
                self._remove_short_reminder(reminder['id'])
    
    def check_time_reminders(self, taiwan_now):
        """檢查時間提醒"""
        time_reminders = self._get_time_reminders()
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
                self._remove_time_reminder(reminder['id'])
                continue
                
            if reminder_time <= taiwan_now:
                user_id = reminder.get('user_id') or self.user_settings.get('user_id')
                if user_id:
                    message = f"🕐 時間提醒！\n\n📋 {reminder['content']}\n⏰ {reminder['time_string']}\n🎯 該去執行了！\n🇹🇼 台灣時間: {get_taiwan_time_hhmm()}"
                    send_push_message(user_id, message)
                    print(f"✅ 已發送時間提醒: {reminder['content']} - 台灣時間: {get_taiwan_time()}")
                self._remove_time_reminder(reminder['id'])
    
    def start_reminder_thread(self):
        """啟動提醒執行緒"""
        if self.reminder_thread is None or not self.reminder_thread.is_alive():
            self.reminder_thread = threading.Thread(target=self.check_reminders, daemon=True)
            self.reminder_thread.start()
            print("✅ 提醒機器人執行緒已啟動")
    
    def get_reminder_counts(self):
        """獲取提醒數量"""
        return {
            'short_reminders': len(self._get_short_reminders()),
            'time_reminders': len(self._get_time_reminders())
        }

    @property 
    def short_reminders(self):
        """為了向後相容性，提供 short_reminders 屬性"""
        return self._get_short_reminders()

    @property
    def time_reminders(self):
        """為了向後相容性，提供 time_reminders 屬性"""
        return self._get_time_reminders()
