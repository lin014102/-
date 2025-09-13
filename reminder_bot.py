return "❌ 設定失敗，請稍後再試"
    
    # ===== 生理期輔助功能 =====
    
    def _get_period_records_safe(self, user_id):
        """安全的獲取生理期記錄"""
        try:
            if self.use_mongodb:
                records = list(self.period_records_collection.find(
                    {'user_id': user_id}
                ).sort('start_date', -1).limit(10))
                return records
            else:
                user_records = [r for r in self._period_records if r.get('user_id') == user_id]
                return sorted(user_records, key=lambda x: x.get('start_date', ''), reverse=True)[:10]
        except Exception as e:
            print(f"❌ 查詢記錄失敗: {e}")
            return []
    
    def _calculate_simple_cycles(self, records):
        """簡化的週期計算"""
        try:
            cycles = []
            for i in range(len(records) - 1):
                try:
                    current = datetime.strptime(records[i]['start_date'], '%Y-%m-%d')
                    previous = datetime.strptime(records[i + 1]['start_date'], '%Y-%m-%d')
                    cycle_length = (current - previous).days
                    if 15 <= cycle_length <= 45:  # 合理範圍
                        cycles.append(cycle_length)
                except:
                    continue
            return cycles
        except:
            return []
    
    def _get_period_record_by_date(self, date_str, user_id):
        """根據日期獲取生理期記錄"""
        try:
            if self.use_mongodb:
                return self.period_records_collection.find_one({
                    'user_id': user_id,
                    'start_date': date_str
                })
            else:
                for record in self._period_records:
                    if record.get('user_id') == user_id and record.get('start_date') == date_str:
                        return record
                return None
        except:
            return None
    
    def _get_latest_period_record(self, user_id):
        """獲取最新的生理期記錄"""
        records = self._get_period_records_safe(user_id)
        return records[0] if records else None
    
    def _get_period_settings(self, user_id):
        """獲取生理期設定"""
        try:
            if self.use_mongodb:
                settings = self.period_settings_collection.find_one({'user_id': user_id})
                if settings:
                    return settings
            else:
                if user_id in self._period_settings:
                    return self._period_settings[user_id]
            
            return {
                'default_cycle_length': 28,
                'reminder_days_before': 5
            }
        except:
            return {
                'default_cycle_length': 28,
                'reminder_days_before': 5
            }
    
    def _update_cycle_length(self, user_id):
        """更新週期長度"""
        try:
            records = self._get_period_records_safe(user_id)
            if len(records) < 2:
                return None
            
            cycles = self._calculate_simple_cycles(records)
            if not cycles:
                return None
            
            avg_cycle = sum(cycles) // len(cycles)
            
            if records:
                last_start = datetime.strptime(records[0]['start_date'], '%Y-%m-%d')
                predicted = last_start + timedelta(days=avg_cycle)
                return {
                    'average_cycle': avg_cycle,
                    'next_prediction': predicted.strftime('%Y-%m-%d')
                }
            
            return {'average_cycle': avg_cycle}
        except:
            return None
    
    def check_period_reminders(self, user_id, taiwan_now):
        """檢查生理期提醒"""
        try:
            records = self._get_period_records_safe(user_id)
            if not records:
                return None
            
            settings = self._get_period_settings(user_id)
            cycles = self._calculate_simple_cycles(records) if len(records) >= 2 else []
            
            if not cycles:
                avg_cycle = settings.get('default_cycle_length', 28)
            else:
                avg_cycle = sum(cycles) // len(cycles)
            
            today = taiwan_now.date()
            
            last_start = datetime.strptime(records[0]['start_date'], '%Y-%m-%d').date()
            pred_date = last_start + timedelta(days=avg_cycle)
            days_diff = (pred_date - today).days
            reminder_days = settings.get('reminder_days_before', 5)
            
            if 1 <= days_diff <= reminder_days:
                return {
                    'type': 'upcoming',
                    'days': days_diff,
                    'date': pred_date.strftime('%Y-%m-%d')
                }
            elif days_diff == 0:
                return {
                    'type': 'today',
                    'date': pred_date.strftime('%Y-%m-%d')
                }
            elif days_diff < 0 and abs(days_diff) <= 7:
                return {
                    'type': 'overdue',
                    'days_overdue': abs(days_diff),
                    'predicted_date': pred_date.strftime('%Y-%m-%d')
                }
            
            return None
            
        except Exception as e:
            print(f"❌ 檢查生理期提醒失敗: {e}")
            return None
    
    def format_period_reminder(self, reminder_info):
        """格式化生理期提醒訊息"""
        if not reminder_info:
            return ""
        
        if reminder_info['type'] == 'upcoming':
            return f"💡 生理期預計 {reminder_info['days']} 天後到來 ({reminder_info['date']})，記得準備用品"
        elif reminder_info['type'] == 'today':
            return f"🩸 預計今天是生理期開始日 ({reminder_info['date']})，記得記錄並照顧自己"
        elif reminder_info['type'] == 'overdue':
            return f"🩸 生理期可能已開始 (預計 {reminder_info['predicted_date']})，記得記錄日期"
        
        return ""
    
    # ===== 核心功能 =====
    
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
    
    def set_user_id(self, user_id):
        """設定用戶ID"""
        self.user_settings['user_id'] = user_id
        self._save_user_settings()
    
    def get_time_settings(self):
        """獲取時間設定"""
        status_msg = "💾 設定已同步到雲端" if self.use_mongodb else ""
        return f"🇹🇼 台灣當前時間：{get_taiwan_time()}\n⏰ 目前提醒時間設定：\n🌅 早上：{self.user_settings['morning_time']}\n🌙 晚上：{self.user_settings['evening_time']}\n\n✅ 時區已修正為台灣時間！\n{status_msg}"
    
    def set_morning_time(self, time_str):
        self.user_settings['morning_time'] = time_str
        self._save_user_settings()
        self.last_reminders['daily_morning_date'] = None
        self.last_reminders['dated_todo_morning_date'] = None
        status_msg = "💾 已同步到雲端" if self.use_mongodb else ""
        return f"🌅 已設定早上提醒時間為：{time_str}\n🇹🇼 台灣時間\n💡 新時間將立即生效\n{status_msg}"
    
    def set_evening_time(self, time_str):
        self.user_settings['evening_time'] = time_str
        self._save_user_settings()
        self.last_reminders['daily_evening_date'] = None
        self.last_reminders['dated_todo_evening_date'] = None
        self.last_reminders['dated_todo_preview_date'] = None
        status_msg = "💾 已同步到雲端" if self.use_mongodb else ""
        return f"🌙 已設定晚上提醒時間為：{time_str}\n🇹🇼 台灣時間\n💡 新時間將立即生效\n{status_msg}"
    
    def start_reminder_thread(self):
        """啟動提醒執行緒"""
        if self.reminder_thread is None or not self.reminder_thread.is_alive():
            self.reminder_thread = threading.Thread(target=self.check_reminders, daemon=True)
            self.reminder_thread.start()
            print("✅ 增強版提醒機器人執行緒已啟動（包含智能帳單提醒和短期/時間提醒修正）")
    
    def get_reminder_counts(self):
        """獲取提醒統計"""
        short_reminders = self._get_short_reminders()
        time_reminders = self._get_time_reminders()
        
        return {
            'short_reminders': len(short_reminders),
            'time_reminders': len(time_reminders)
        }
    
    # ===== 短期和時間提醒功能 =====
    
    def _get_short_reminders(self):
        if self.use_mongodb:
            return list(self.short_reminders_collection.find({}))
        else:
            return self._short_reminders
    
    def _get_time_reminders(self):
        if self.use_mongodb:
            return list(self.time_reminders_collection.find({}))
        else:
            return self._time_reminders
    
    def _add_short_reminder(self, reminder_item):
        if self.use_mongodb:
            result = self.short_reminders_collection.insert_one(reminder_item)
            reminder_item['_id'] = result.inserted_id
        else:
            self._short_reminders.append(reminder_item)
    
    def _add_time_reminder(self, reminder_item):
        if self.use_mongodb:
            result = self.time_reminders_collection.insert_one(reminder_item)
            reminder_item['_id'] = result.inserted_id
        else:
            self._time_reminders.append(reminder_item)
    
    def _remove_short_reminder(self, reminder_id):
        if self.use_mongodb:
            self.short_reminders_collection.delete_one({"id": reminder_id})
        else:
    def _remove_short_reminder(self, reminder_id):
        if self.use_mongodb:
            self.short_reminders_collection.delete_one({"id": reminder_id})
        else:
            self._short_reminders = [r for r in self._short_reminders if r['id'] != reminder_id]
    
    def _remove_time_reminder(self, reminder_id):
        if self.use_mongodb:
            self.time_reminders_collection.delete_one({"id": reminder_id})
        else:
            self._time_reminders = [r for r in self._time_reminders if r['id'] != reminder_id]
    
    def _get_next_short_reminder_id(self):
        short_reminders = self._get_short_reminders()
        if not short_reminders:
            return 1
        return max(r['id'] for r in short_reminders) + 1
    
    def _get_next_time_reminder_id(self):
        time_reminders = self._get_time_reminders()
        if not time_reminders:
            return 1
        return max(r['id'] for r in time_reminders) + 1
    
    def parse_short_reminder(self, text):
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
        """新增短期提醒（修正版）"""
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
                'unit': parsed['unit'],
                'created_at': taiwan_now.isoformat()
            }
            self._add_short_reminder(reminder_item)
            
            status_msg = "💾 已同步到雲端" if self.use_mongodb else ""
            print(f"✅ 新增短期提醒: ID:{reminder_item['id']} - {parsed['content']} - {reminder_time.isoformat()}")
            return f"⏰ 已設定短期提醒：「{parsed['content']}」\n⏳ {parsed['original_value']}{parsed['unit']}後提醒\n📅 提醒時間：{reminder_time.strftime('%H:%M')}\n🇹🇼 台灣時間\n{status_msg}"
        else:
            return f"❌ {parsed['error']}"
    
    def add_time_reminder(self, message_text, user_id):
        """新增時間提醒（修正版）"""
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
                'reminder_time': target_time.isoformat(),
                'created_at': taiwan_now.isoformat()
            }
            self._add_time_reminder(reminder_item)
            
            date_text = '今天' if target_time.date() == taiwan_now.date() else '明天'
            status_msg = "💾 已同步到雲端" if self.use_mongodb else ""
            print(f"✅ 新增時間提醒: ID:{reminder_item['id']} - {parsed['content']} - {target_time.isoformat()}")
            return f"🕐 已設定時間提醒：「{parsed['content']}」\n⏰ {date_text} {parsed['time_string']} 提醒\n🇹🇼 台灣時間\n{status_msg}"
        else:
            return f"❌ {parsed['error']}"
    
    # ===== 查詢和刪除提醒功能 =====
    
    def get_short_reminders_list(self):
        """查詢短期提醒列表"""
        try:
            reminders = self._get_short_reminders()
            if not reminders:
                return "📝 目前沒有短期提醒"
            
            taiwan_now = get_taiwan_datetime()
            message = f"⏰ 短期提醒列表 ({len(reminders)} 項)：\n\n"
            
            for i, reminder in enumerate(reminders[:10], 1):
                try:
                    reminder_time = datetime.fromisoformat(reminder['reminder_time'].replace('Z', '+00:00'))
                    if reminder_time.tzinfo is None:
                        reminder_time = reminder_time.replace(tzinfo=TAIWAN_TZ)
                    
                    time_diff = (reminder_time - taiwan_now).total_seconds()
                    
                    if time_diff > 0:
                        if time_diff < 3600:
                            time_left = f"{int(time_diff // 60)}分鐘後"
                        elif time_diff < 86400:
                            time_left = f"{int(time_diff // 3600)}小時{int((time_diff % 3600) // 60)}分鐘後"
                        else:
                            time_left = f"{int(time_diff // 86400)}天後"
                    else:
                        time_left = "已過期"
                    
                    message += f"{i}. 🔔 {reminder['content']}\n"
                    message += f"   ⏰ {reminder_time.strftime('%m/%d %H:%M')} ({time_left})\n"
                    message += f"   🆔 ID: {reminder['id']}\n\n"
                except:
                    message += f"{i}. 🔔 {reminder['content']}\n"
                    message += f"   ⚠️ 時間解析錯誤\n"
                    message += f"   🆔 ID: {reminder['id']}\n\n"
            
            if len(reminders) > 10:
                message += f"...還有 {len(reminders) - 10} 項\n"
            
            message += "💡 使用「刪除提醒 ID」來刪除特定提醒"
            return message
            
        except Exception as e:
            print(f"❌ 查詢短期提醒失敗: {e}")
            return "❌ 查詢失敗，請稍後再試"
    
    def get_time_reminders_list(self):
        """查詢時間提醒列表"""
        try:
            reminders = self._get_time_reminders()
            if not reminders:
                return "📝 目前沒有時間提醒"
            
            taiwan_now = get_taiwan_datetime()
            message = f"🕐 時間提醒列表 ({len(reminders)} 項)：\n\n"
            
            for i, reminder in enumerate(reminders[:10], 1):
                try:
                    reminder_time = datetime.fromisoformat(reminder['reminder_time'].replace('Z', '+00:00'))
                    if reminder_time.tzinfo is None:
                        reminder_time = reminder_time.replace(tzinfo=TAIWAN_TZ)
                    
                    if reminder_time.date() == taiwan_now.date():
                        date_text = "今天"
                    elif reminder_time.date() == (taiwan_now + timedelta(days=1)).date():
                        date_text = "明天"
                    else:
                        date_text = reminder_time.strftime('%m/%d')
                    
                    message += f"{i}. 🔔 {reminder['content']}\n"
                    message += f"   ⏰ {date_text} {reminder['time_string']}\n"
                    message += f"   🆔 ID: {reminder['id']}\n\n"
                except:
                    message += f"{i}. 🔔 {reminder['content']}\n"
                    message += f"   ⚠️ 時間解析錯誤\n"
                    message += f"   🆔 ID: {reminder['id']}\n\n"
            
            if len(reminders) > 10:
                message += f"...還有 {len(reminders) - 10} 項\n"
            
            message += "💡 使用「刪除提醒 ID」來刪除特定提醒"
            return message
            
        except Exception as e:
            print(f"❌ 查詢時間提醒失敗: {e}")
            return "❌ 查詢失敗，請稍後再試"
    
    def delete_reminder(self, reminder_id):
        """刪除提醒"""
        try:
            reminder_id = int(reminder_id)
            
            # 先查找短期提醒
            short_reminders = self._get_short_reminders()
            for reminder in short_reminders:
                if reminder['id'] == reminder_id:
                    self._remove_short_reminder(reminder_id)
                    return f"✅ 已刪除短期提醒：{reminder['content']}"
            
            # 再查找時間提醒
            time_reminders = self._get_time_reminders()
            for reminder in time_reminders:
                if reminder['id'] == reminder_id:
                    self._remove_time_reminder(reminder_id)
                    return f"✅ 已刪除時間提醒：{reminder['content']}"
            
            return f"❌ 找不到 ID 為 {reminder_id} 的提醒"
            
        except ValueError:
            return "❌ 請輸入有效的提醒 ID 數字"
        except Exception as e:
            print(f"❌ 刪除提醒失敗: {e}")
            return "❌ 刪除失敗，請稍後再試"
    
    # ===== 屬性訪問器（保持相容性）=====
    
    @property 
    def short_reminders(self):
        return self._get_short_reminders()

    @property
    def time_reminders(self):
        return self._get_time_reminders()"""
reminder_bot.py - 提醒機器人模組 (完整修正版)
修正版生理期追蹤 + 下次預測查詢 + 智能帳單金額提醒整合 + 短期/時間提醒修正
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
    """提醒機器人 (MongoDB Atlas 版本) + 帳單金額整合 + 生理期追蹤 + 智能帳單提醒 + 修正短期時間提醒"""
    
    def __init__(self, todo_manager):
        """初始化提醒機器人"""
        self.todo_manager = todo_manager
        
        # 初始化 MongoDB 連接
        mongodb_uri = os.getenv('MONGODB_URI')
        if not mongodb_uri:
            print("⚠️ 警告：ReminderBot 找不到 MONGODB_URI 環境變數，使用記憶體模式")
            self._short_reminders = []
            self._time_reminders = []
            self._bill_amounts = {}
            self._period_records = []
            self._period_settings = {}
            self.use_mongodb = False
        else:
            try:
                self.client = MongoClient(mongodb_uri)
                try:
                    self.db = self.client.get_default_database()
                except:
                    self.db = self.client.reminderbot
                
                self.short_reminders_collection = self.db.short_reminders
                self.time_reminders_collection = self.db.time_reminders
                self.user_settings_collection = self.db.user_settings
                self.bill_amounts_collection = self.db.bill_amounts
                self.period_records_collection = self.db.period_records
                self.period_settings_collection = self.db.period_settings
                self.use_mongodb = True
                print("✅ ReminderBot 成功連接到 MongoDB Atlas")
            except Exception as e:
                print(f"❌ ReminderBot MongoDB 連接失敗: {e}")
                print("⚠️ ReminderBot 使用記憶體模式")
                self._short_reminders = []
                self._time_reminders = []
                self._bill_amounts = {}
                self._period_records = []
                self._period_settings = {}
                self.use_mongodb = False
        
        self.user_settings = self._load_user_settings()
        self.last_reminders = {
            'daily_morning_date': None,
            'daily_evening_date': None,
            'dated_todo_preview_date': None,
            'dated_todo_morning_date': None,
            'dated_todo_evening_date': None
        }
        self.reminder_thread = None
    
    # ===== 智能帳單提醒功能 =====
    
    def check_urgent_bill_payments(self, user_id):
        """檢查緊急的帳單繳費提醒"""
        try:
            taiwan_now = get_taiwan_datetime()
            today = taiwan_now.date()
            
            urgent_bills = []
            
            # 檢查所有銀行的帳單
            banks = ['永豐', '台新', '國泰', '星展', '匯豐', '玉山', '聯邦']
            
            for bank in banks:
                bill_info = self.get_bill_amount(bank)
                if bill_info and bill_info.get('due_date'):
                    try:
                        due_date = datetime.strptime(bill_info['due_date'], '%Y/%m/%d').date()
                        days_until_due = (due_date - today).days
                        
                        # 緊急程度分類
                        if days_until_due <= 0:
                            urgent_bills.append({
                                'bank': bank,
                                'amount': bill_info['amount'],
                                'due_date': bill_info['due_date'],
                                'days_until_due': days_until_due,
                                'urgency': 'overdue' if days_until_due < 0 else 'due_today'
                            })
                        elif days_until_due <= 3:
                            urgent_bills.append({
                                'bank': bank,
                                'amount': bill_info['amount'],
                                'due_date': bill_info['due_date'],
                                'days_until_due': days_until_due,
                                'urgency': 'urgent'
                            })
                        elif days_until_due <= 7:
                            urgent_bills.append({
                                'bank': bank,
                                'amount': bill_info['amount'],
                                'due_date': bill_info['due_date'],
                                'days_until_due': days_until_due,
                                'urgency': 'warning'
                            })
                    except ValueError:
                        continue
            
            return urgent_bills
            
        except Exception as e:
            print(f"❌ 檢查緊急帳單失敗: {e}")
            return []
    
    def format_bill_reminders(self, urgent_bills):
        """格式化帳單提醒訊息"""
        if not urgent_bills:
            return ""
        
        # 按緊急程度排序
        urgency_order = {'overdue': 0, 'due_today': 1, 'urgent': 2, 'warning': 3}
        urgent_bills.sort(key=lambda x: urgency_order.get(x['urgency'], 4))
        
        message = ""
        
        # 分類顯示
        overdue_bills = [b for b in urgent_bills if b['urgency'] == 'overdue']
        due_today_bills = [b for b in urgent_bills if b['urgency'] == 'due_today']
        urgent_bills_list = [b for b in urgent_bills if b['urgency'] == 'urgent']
        warning_bills = [b for b in urgent_bills if b['urgency'] == 'warning']
        
        if overdue_bills:
            message += "🚨 逾期未繳：\n"
            for bill in overdue_bills:
                overdue_days = abs(bill['days_until_due'])
                message += f"❗ {bill['bank']}卡費 {bill['amount']} (逾期{overdue_days}天)\n"
        
        if due_today_bills:
            if message:
                message += "\n"
            message += "⏰ 今日到期：\n"
            for bill in due_today_bills:
                message += f"🔴 {bill['bank']}卡費 {bill['amount']} (今天截止)\n"
        
        if urgent_bills_list:
            if message:
                message += "\n"
            message += "⚡ 即將到期：\n"
            for bill in urgent_bills_list:
                message += f"🟡 {bill['bank']}卡費 {bill['amount']} ({bill['days_until_due']}天後)\n"
        
        if warning_bills:
            if message:
                message += "\n"
            message += "💡 提前提醒：\n"
            for bill in warning_bills:
                message += f"🟢 {bill['bank']}卡費 {bill['amount']} ({bill['days_until_due']}天後)\n"
        
        return message
    
    # ===== 增強版日常提醒功能 =====
    
    def send_daily_reminder(self, user_id, current_time):
        """發送每日提醒（增強版 - 包含智能帳單提醒和生理期提醒）"""
        time_icon = '🌅' if current_time == self.user_settings['morning_time'] else '🌙'
        time_text = '早安' if current_time == self.user_settings['morning_time'] else '晚安'
        
        # 1. 檢查生理期提醒
        taiwan_now = get_taiwan_datetime()
        period_reminder = self.check_period_reminders(user_id, taiwan_now)
        period_message = self.format_period_reminder(period_reminder)
        
        # 2. 檢查緊急帳單提醒
        urgent_bills = self.check_urgent_bill_payments(user_id)
        bill_reminder = self.format_bill_reminders(urgent_bills)
        
        todos = self.todo_manager.todos
        
        if todos:
            pending_todos = self.todo_manager.get_pending_todos()
            completed_todos = self.todo_manager.get_completed_todos()
            
            if pending_todos:
                message = f'{time_icon} {time_text}！您有 {len(pending_todos)} 項待辦事項：\n\n'
                
                # 優先顯示緊急帳單提醒
                if bill_reminder:
                    message += f"{bill_reminder}\n"
                    message += f"{'='*20}\n\n"
                
                # 待辦事項列表（增強版顯示）
                for i, todo in enumerate(pending_todos[:5], 1):
                    date_info = f" 📅{todo.get('target_date', '')}" if todo.get('has_date') else ""
                    enhanced_content = self._enhance_todo_with_bill_amount(todo["content"])
                    message += f'{i}. ⭕ {enhanced_content}{date_info}\n'
                
                if len(pending_todos) > 5:
                    message += f'\n...還有 {len(pending_todos) - 5} 項未完成\n'
                
                # 已完成事項
                if completed_todos:
                    message += f'\n✅ 已完成 {len(completed_todos)} 項：\n'
                    for todo in completed_todos[:2]:
                        message += f'✅ {todo["content"]}\n'
                    if len(completed_todos) > 2:
                        message += f'...還有 {len(completed_todos) - 2} 項已完成\n'
                
                # 生理期提醒
                if period_message:
                    message += f'\n{period_message}\n'
                
                # 時間相關的鼓勵訊息
                if current_time == self.user_settings['morning_time']:
                    if urgent_bills:
                        message += f'\n💪 新的一天開始了！優先處理緊急帳單，然後完成其他任務！'
                    else:
                        message += f'\n💪 新的一天開始了！加油完成這些任務！'
                else:
                    if urgent_bills:
                        message += f'\n🌙 檢查一下今天的進度吧！別忘了緊急的帳單繳費！'
                    else:
                        message += f'\n🌙 檢查一下今天的進度吧！記得為明天做準備！'
                    
                message += f'\n🇹🇼 台灣時間: {get_taiwan_time_hhmm()}'
                
                send_push_message(user_id, message)
                print(f"✅ 已發送增強版每日提醒 ({len(pending_todos)} 項待辦, {len(urgent_bills)} 項緊急帳單) - 台灣時間: {get_taiwan_time()}")
                
            else:
                # 沒有待辦事項但可能有緊急帳單
                message = ""
                if current_time == self.user_settings['morning_time']:
                    message = f'{time_icon} {time_text}！🎉 太棒了！目前沒有待辦事項\n💡 可以新增今天要做的事情'
                else:
                    message = f'{time_icon} {time_text}！🎉 太棒了！今天的任務都完成了\n😴 好好休息，為明天準備新的目標！'
                
                # 即使沒有待辦事項也要檢查緊急帳單和生理期
                if bill_reminder:
                    message += f'\n\n⚠️ 重要提醒：\n{bill_reminder}'
                
                if period_message:
                    message += f'\n\n{period_message}'
                
                message += f'\n🇹🇼 台灣時間: {get_taiwan_time_hhmm()}'
                send_push_message(user_id, message)
                print(f"✅ 已發送增強版每日提醒 (無待辦事項, {len(urgent_bills)} 項緊急帳單) - 台灣時間: {get_taiwan_time()}")
                
        else:
            # 首次使用
            message = ""
            if current_time == self.user_settings['morning_time']:
                message = f'{time_icon} {time_text}！✨ 新的一天開始了！\n💡 輸入「新增 事項名稱」來建立今天的目標'
            else:
                message = f'{time_icon} {time_text}！😌 今天過得如何？\n💡 別忘了為明天規劃一些目標'
            
            # 首次使用也要檢查緊急帳單和生理期
            if bill_reminder:
                message += f'\n\n⚠️ 重要提醒：\n{bill_reminder}'
                
            if period_message:
                message += f'\n\n{period_message}'
            
            message += f'\n🇹🇼 台灣時間: {get_taiwan_time_hhmm()}'
            send_push_message(user_id, message)
            print(f"✅ 已發送增強版每日提醒 (首次使用, {len(urgent_bills)} 項緊急帳單) - 台灣時間: {get_taiwan_time()}")
    
    def _enhance_todo_with_bill_amount(self, todo_content):
        """增強待辦事項顯示（更新版 - 更智能的匹配和顯示）"""
        try:
            if '卡費' in todo_content:
                bill_info = None
                matched_bank = None
                
                # 更智能的銀行名稱匹配
                bank_patterns = {
                    '永豐': ['永豐', 'sinopac', 'SinoPac'],
                    '台新': ['台新', 'taishin', 'TAISHIN'],
                    '國泰': ['國泰', 'cathay', 'CATHAY'],
                    '星展': ['星展', 'dbs', 'DBS'],
                    '匯豐': ['匯豐', 'hsbc', 'HSBC'],
                    '玉山': ['玉山', 'esun', 'E.SUN'],
                    '聯邦': ['聯邦', 'union', 'UNION']
                }
                
                for bank_name, patterns in bank_patterns.items():
                    if any(pattern in todo_content for pattern in patterns):
                        bill_info = self.get_bill_amount(bank_name)
                        matched_bank = bank_name
                        break
                
                if bill_info and matched_bank:
                    try:
                        due_date = bill_info['due_date']
                        amount = bill_info['amount']
                        
                        # 格式化日期顯示
                        if '/' in due_date and len(due_date.split('/')) == 3:
                            year, month, day = due_date.split('/')
                            formatted_date = f"{int(month)}/{int(day)}"
                        else:
                            formatted_date = due_date
                        
                        # 計算緊急程度
                        taiwan_now = get_taiwan_datetime()
                        today = taiwan_now.date()
                        
                        try:
                            due_date_obj = datetime.strptime(due_date, '%Y/%m/%d').date()
                            days_until_due = (due_date_obj - today).days
                            
                            # 根據緊急程度添加不同的提示
                            if days_until_due < 0:
                                urgency_icon = "🚨"
                                urgency_text = f"逾期{abs(days_until_due)}天"
                            elif days_until_due == 0:
                                urgency_icon = "⏰"
                                urgency_text = "今天截止"
                            elif days_until_due <= 3:
                                urgency_icon = "⚡"
                                urgency_text = f"{days_until_due}天後"
                            elif days_until_due <= 7:
                                urgency_icon = "💡"
                                urgency_text = f"{days_until_due}天後"
                            else:
                                urgency_icon = ""
                                urgency_text = f"{days_until_due}天後"
                            
                            if urgency_icon:
                                return f"{todo_content} - {amount} {urgency_icon}({urgency_text}截止)"
                            else:
                                return f"{todo_content} - {amount}（截止：{formatted_date}）"
                                
                        except ValueError:
                            return f"{todo_content} - {amount}（截止：{formatted_date}）"
                        
                    except Exception as e:
                        return f"{todo_content} - {bill_info['amount']}"
            
            return todo_content
            
        except Exception as e:
            print(f"增強待辦事項顯示失敗: {e}")
            return todo_content
    
    # ===== 修正後的提醒檢查功能 =====
    
    def check_reminders(self):
        """主提醒檢查循環（完整修正版 - 包含所有提醒類型）"""
        while True:
            try:
                current_time = get_taiwan_time_hhmm()
                user_id = self.user_settings.get('user_id')
                taiwan_now = get_taiwan_datetime()
                today_date = taiwan_now.strftime('%Y-%m-%d')
                
                print(f"🔍 增強版提醒檢查 - 台灣時間: {get_taiwan_time()}")
                
                if user_id:
                    # === 每日定時提醒 ===
                    # 早上提醒
                    if (current_time == self.user_settings['morning_time'] and 
                        self.last_reminders['daily_morning_date'] != today_date):
                        self.send_daily_reminder(user_id, current_time)
                        self.last_reminders['daily_morning_date'] = today_date
                    
                    # 晚上提醒
                    elif (current_time == self.user_settings['evening_time'] and 
                          self.last_reminders['daily_evening_date'] != today_date):
                        self.send_daily_reminder(user_id, current_time)
                        self.last_reminders['daily_evening_date'] = today_date
                    
                    # === 短期提醒檢查 ===
                    self._check_and_send_short_reminders(user_id, taiwan_now)
                    
                    # === 時間提醒檢查 ===
                    self._check_and_send_time_reminders(user_id, taiwan_now)
                
                time.sleep(60)
            except Exception as e:
                print(f"增強版提醒檢查錯誤: {e} - 台灣時間: {get_taiwan_time()}")
                time.sleep(60)
    
    def _check_and_send_short_reminders(self, user_id, taiwan_now):
        """檢查並發送短期提醒"""
        try:
            short_reminders = self._get_short_reminders()
            print(f"🔍 檢查短期提醒，共 {len(short_reminders)} 筆記錄")
            
            for reminder in short_reminders[:]:  # 使用切片避免迭代時修改列表
                try:
                    # 解析提醒時間
                    reminder_time_str = reminder['reminder_time']
                    if reminder_time_str.endswith('Z'):
                        reminder_time_str = reminder_time_str[:-1] + '+00:00'
                    
                    reminder_time = datetime.fromisoformat(reminder_time_str)
                    
                    # 確保時間有時區資訊
                    if reminder_time.tzinfo is None:
                        reminder_time = reminder_time.replace(tzinfo=TAIWAN_TZ)
                    
                    # 檢查是否到達提醒時間（允許2分鐘誤差）
                    time_diff = (taiwan_now - reminder_time).total_seconds()
                    
                    print(f"⏱️ 短期提醒 ID:{reminder.get('id')} - 時間差: {time_diff}秒")
                    
                    if 0 <= time_diff <= 120:  # 0-2分鐘內觸發
                        # 發送提醒訊息
                        message = f"⏰ 短期提醒：{reminder['content']}\n"
                        message += f"🕒 提醒時間：{reminder_time.strftime('%H:%M')}\n"
                        message += f"🇹🇼 台灣時間：{get_taiwan_time_hhmm()}"
                        
                        send_push_message(user_id, message)
                        
                        # 移除已發送的提醒
                        self._remove_short_reminder(reminder['id'])
                        
                        print(f"✅ 已發送短期提醒: {reminder['content']} - {get_taiwan_time()}")
                    
                    # 清理過期的提醒（超過24小時）
                    elif time_diff > 86400:  # 24小時
                        self._remove_short_reminder(reminder['id'])
                        print(f"🗑️ 清理過期短期提醒: {reminder['content']}")
                        
                except Exception as e:
                    print(f"❌ 處理短期提醒失敗: {e}")
                    import traceback
                    traceback.print_exc()
                    continue
                    
        except Exception as e:
            print(f"❌ 檢查短期提醒失敗: {e}")
    
    def _check_and_send_time_reminders(self, user_id, taiwan_now):
        """檢查並發送時間提醒"""
        try:
            time_reminders = self._get_time_reminders()
            current_time_hhmm = taiwan_now.strftime('%H:%M')
            
            print(f"🔍 檢查時間提醒，共 {len(time_reminders)} 筆記錄，當前時間: {current_time_hhmm}")
            
            for reminder in time_reminders[:]:  # 使用切片避免迭代時修改列表
                try:
                    # 解析提醒時間
                    reminder_time_str = reminder['reminder_time']
                    if reminder_time_str.endswith('Z'):
                        reminder_time_str = reminder_time_str[:-1] + '+00:00'
                    
                    reminder_time = datetime.fromisoformat(reminder_time_str)
                    
                    # 確保時間有時區資訊
                    if reminder_time.tzinfo is None:
                        reminder_time = reminder_time.replace(tzinfo=TAIWAN_TZ)
                    
                    # 檢查是否到達提醒時間（精確到分鐘）
                    reminder_hhmm = reminder_time.strftime('%H:%M')
                    
                    print(f"⏱️ 時間提醒 ID:{reminder.get('id')} - 目標: {reminder_hhmm}, 當前: {current_time_hhmm}")
                    
                    if (current_time_hhmm == reminder_hhmm and 
                        taiwan_now.date() == reminder_time.date()):
                        
                        # 發送提醒訊息
                        message = f"🕐 時間提醒：{reminder['content']}\n"
                        message += f"⏰ 設定時間：{reminder['time_string']}\n"
                        message += f"🇹🇼 台灣時間：{get_taiwan_time_hhmm()}"
                        
                        send_push_message(user_id, message)
                        
                        # 移除已發送的提醒
                        self._remove_time_reminder(reminder['id'])
                        
                        print(f"✅ 已發送時間提醒: {reminder['content']} - {get_taiwan_time()}")
                    
                    # 清理過期的提醒（超過提醒時間1天）
                    elif taiwan_now > reminder_time + timedelta(days=1):
                        self._remove_time_reminder(reminder['id'])
                        print(f"🗑️ 清理過期時間提醒: {reminder['content']}")
                        
                except Exception as e:
                    print(f"❌ 處理時間提醒失敗: {e}")
                    import traceback
                    traceback.print_exc()
                    continue
                    
        except Exception as e:
            print(f"❌ 檢查時間提醒失敗: {e}")
    
    # ===== 調試功能 =====
    
    def debug_reminders(self):
        """調試提醒功能 - 檢查資料庫狀態"""
        try:
            if self.use_mongodb:
                short_count = self.short_reminders_collection.count_documents({})
                time_count = self.time_reminders_collection.count_documents({})
                print(f"📊 MongoDB 中的提醒數量 - 短期: {short_count}, 時間: {time_count}")
                
                # 顯示最新的幾筆提醒
                short_reminders = list(self.short_reminders_collection.find({}).limit(3))
                time_reminders = list(self.time_reminders_collection.find({}).limit(3))
                
                print("📋 最新短期提醒:")
                for reminder in short_reminders:
                    print(f"  ID:{reminder.get('id')} - {reminder.get('content')} - {reminder.get('reminder_time')}")
                
                print("📋 最新時間提醒:")
                for reminder in time_reminders:
                    print(f"  ID:{reminder.get('id')} - {reminder.get('content')} - {reminder.get('reminder_time')}")
            else:
                print(f"📊 記憶體中的提醒數量 - 短期: {len(self._short_reminders)}, 時間: {len(self._time_reminders)}")
                
                print("📋 短期提醒:")
                for reminder in self._short_reminders[:3]:
                    print(f"  ID:{reminder.get('id')} - {reminder.get('content')} - {reminder.get('reminder_time')}")
                
                print("📋 時間提醒:")
                for reminder in self._time_reminders[:3]:
                    print(f"  ID:{reminder.get('id')} - {reminder.get('content')} - {reminder.get('reminder_time')}")
                    
        except Exception as e:
            print(f"❌ 調試提醒功能失敗: {e}")
    
    def test_push_message(self, user_id):
        """測試推播訊息功能"""
        try:
            test_message = f"📱 測試推播訊息\n🕒 時間: {get_taiwan_time()}\n✅ 如果收到此訊息，表示推播功能正常"
            send_push_message(user_id, test_message)
            print("✅ 測試訊息已發送")
            return "✅ 測試訊息發送成功"
        except Exception as e:
            print(f"❌ 測試訊息發送失敗: {e}")
            return f"❌ 測試訊息發送失敗: {e}"
    
    # ===== 帳單金額管理功能 =====
    
    def update_bill_amount(self, bank_name, amount, due_date, statement_date=None):
        """更新銀行卡費金額"""
        try:
            normalized_bank = self._normalize_bank_name(bank_name)
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
                self.bill_amounts_collection.update_one(
                    {'bank_name': normalized_bank, 'month': month_key},
                    {'$set': bill_data},
                    upsert=True
                )
            else:
                if normalized_bank not
