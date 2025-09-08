"""
reminder_bot.py - 提醒機器人模組 (修正版生理期追蹤)
修正 get_period_status 函數的錯誤處理
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
    """提醒機器人 (MongoDB Atlas 版本) + 帳單金額整合 + 生理期追蹤"""
    
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
    
    # ===== 生理期追蹤功能 =====
    
    def record_period_start(self, start_date, user_id, notes=""):
        """記錄生理期開始"""
        try:
            if isinstance(start_date, str):
                if '/' in start_date:
                    start_datetime = datetime.strptime(start_date, '%Y/%m/%d')
                else:
                    start_datetime = datetime.strptime(start_date, '%Y-%m-%d')
            else:
                start_datetime = start_date
            
            start_date_str = start_datetime.strftime('%Y-%m-%d')
            
            existing_record = self._get_period_record_by_date(start_date_str, user_id)
            if existing_record:
                return f"❌ {start_date_str} 已有生理期記錄"
            
            record = {
                'user_id': user_id,
                'start_date': start_date_str,
                'end_date': None,
                'notes': notes,
                'created_at': datetime.now().isoformat()
            }
            
            if self.use_mongodb:
                self.period_records_collection.insert_one(record)
            else:
                self._period_records.append(record)
            
            cycle_info = self._update_cycle_length(user_id)
            
            status_msg = "💾 已同步到雲端" if self.use_mongodb else ""
            message = f"✅ 生理期記錄成功：{start_date_str}\n"
            if cycle_info and cycle_info.get('average_cycle'):
                message += f"📊 當前平均週期：{cycle_info['average_cycle']} 天\n"
                if cycle_info.get('next_prediction'):
                    message += f"📅 下次預測：{cycle_info['next_prediction']}\n"
            message += f"{status_msg}"
            
            print(f"✅ 生理期記錄成功: {start_date_str}")
            return message
            
        except ValueError:
            return "❌ 日期格式錯誤，請使用 YYYY/MM/DD 或 YYYY-MM-DD 格式"
        except Exception as e:
            print(f"❌ 記錄生理期失敗: {e}")
            return "❌ 記錄失敗，請稍後再試"
    
    def record_period_end(self, end_date, user_id, notes=""):
        """記錄生理期結束"""
        try:
            if isinstance(end_date, str):
                if '/' in end_date:
                    end_datetime = datetime.strptime(end_date, '%Y/%m/%d')
                else:
                    end_datetime = datetime.strptime(end_date, '%Y-%m-%d')
            else:
                end_datetime = end_date
            
            end_date_str = end_datetime.strftime('%Y-%m-%d')
            
            recent_record = self._get_latest_period_record(user_id)
            if not recent_record:
                return "❌ 找不到未結束的生理期記錄"
            
            if recent_record.get('end_date'):
                return "❌ 最近的生理期記錄已經結束"
            
            if self.use_mongodb:
                self.period_records_collection.update_one(
                    {'_id': recent_record['_id']},
                    {'$set': {'end_date': end_date_str, 'end_notes': notes}}
                )
            else:
                for record in self._period_records:
                    if record == recent_record:
                        record['end_date'] = end_date_str
                        record['end_notes'] = notes
                        break
            
            start_date = recent_record['start_date']
            duration = (end_datetime - datetime.strptime(start_date, '%Y-%m-%d')).days + 1
            
            status_msg = "💾 已同步到雲端" if self.use_mongodb else ""
            message = f"✅ 生理期結束記錄成功：{end_date_str}\n"
            message += f"📊 本次持續：{duration} 天\n"
            message += f"📅 期間：{start_date} 至 {end_date_str}\n"
            message += f"{status_msg}"
            
            print(f"✅ 生理期結束記錄成功: {end_date_str}")
            return message
            
        except ValueError:
            return "❌ 日期格式錯誤，請使用 YYYY/MM/DD 或 YYYY-MM-DD 格式"
        except Exception as e:
            print(f"❌ 記錄生理期結束失敗: {e}")
            return "❌ 記錄失敗，請稍後再試"
    
    def get_period_status(self, user_id):
        """獲取生理期狀態和預測 - 修正版"""
        try:
            print(f"🔍 開始獲取生理期狀態，用戶ID: {user_id}")
            
            # 簡化查詢，避免複雜操作
            records = self._get_period_records_safe(user_id)
            print(f"📊 找到 {len(records)} 筆記錄")
            
            if not records:
                return "📊 生理期追蹤狀態\n\n❌ 尚未有任何記錄\n💡 請使用「記錄生理期 YYYY/MM/DD」開始追蹤"
            
            # 最近記錄
            latest_record = records[0]
            print(f"📅 最新記錄：{latest_record}")
            
            message = "📊 生理期追蹤狀態\n\n"
            message += f"📅 最近記錄：{latest_record['start_date']}"
            
            if latest_record.get('end_date'):
                try:
                    start = datetime.strptime(latest_record['start_date'], '%Y-%m-%d')
                    end = datetime.strptime(latest_record['end_date'], '%Y-%m-%d')
                    duration = (end - start).days + 1
                    message += f" - {latest_record['end_date']} ({duration}天)\n"
                except:
                    message += f" - {latest_record['end_date']}\n"
            else:
                message += " (進行中)\n"
            
            message += f"📋 總記錄數：{len(records)} 次\n"
            
            # 簡化的週期計算
            if len(records) >= 2:
                try:
                    cycles = self._calculate_simple_cycles(records)
                    if cycles:
                        avg_cycle = sum(cycles) // len(cycles)
                        message += f"📊 平均週期：約 {avg_cycle} 天\n"
                        
                        # 簡單預測
                        last_start = datetime.strptime(latest_record['start_date'], '%Y-%m-%d')
                        predicted = last_start + timedelta(days=avg_cycle)
                        message += f"📅 下次預測：約 {predicted.strftime('%Y-%m-%d')}\n"
                except Exception as e:
                    print(f"⚠️ 週期計算失敗: {e}")
                    message += "📊 週期計算中...\n"
            
            message += "\n💡 指令：\n"
            message += "• 記錄生理期 YYYY/MM/DD\n"
            message += "• 生理期結束 YYYY/MM/DD\n"
            message += "• 生理期設定"
            
            print("✅ 狀態獲取成功")
            return message
            
        except Exception as e:
            print(f"❌ 獲取生理期狀態失敗: {e}")
            import traceback
            traceback.print_exc()
            return "❌ 獲取狀態失敗，請稍後再試"
    
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
    
    def set_period_settings(self, user_id, cycle_length=None, reminder_days=5):
        """設定生理期追蹤偏好"""
        try:
            settings = {
                'user_id': user_id,
                'default_cycle_length': cycle_length or 28,
                'reminder_days_before': reminder_days,
                'updated_at': datetime.now().isoformat()
            }
            
            if self.use_mongodb:
                self.period_settings_collection.update_one(
                    {'user_id': user_id},
                    {'$set': settings},
                    upsert=True
                )
            else:
                self._period_settings[user_id] = settings
            
            status_msg = "💾 已同步到雲端" if self.use_mongodb else ""
            message = f"✅ 生理期設定更新成功\n"
            message += f"📊 預設週期：{settings['default_cycle_length']} 天\n"
            message += f"⏰ 提前提醒：{settings['reminder_days_before']} 天\n"
            message += f"{status_msg}"
            
            return message
            
        except Exception as e:
            print(f"❌ 設定生理期偏好失敗: {e}")
            return "❌ 設定失敗，請稍後再試"
    
    def _get_period_records(self, user_id, limit=10):
        """獲取生理期記錄"""
        return self._get_period_records_safe(user_id)
    
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
            
            # 簡單預測
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
        """檢查生理期提醒 - 簡化版"""
        try:
            records = self._get_period_records_safe(user_id)
            if not records:
                return None
            
            settings = self._get_period_settings(user_id)
            cycles = self._calculate_simple_cycles(records) if len(records) >= 2 else []
            
            if not cycles:
                return None
            
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
                if normalized_bank not in self._bill_amounts:
                    self._bill_amounts[normalized_bank] = {}
                self._bill_amounts[normalized_bank][month_key] = bill_data
            
            print(f"✅ 更新 {normalized_bank} {month_key} 卡費: {amount}")
            return True
            
        except Exception as e:
            print(f"❌ 更新卡費金額失敗: {e}")
            return False
    
    def _normalize_bank_name(self, bank_name):
        """銀行名稱標準化"""
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
        
        return bank_name
    
    def get_bill_amount(self, bank_name, target_month=None):
        """取得指定銀行的最新卡費金額"""
        try:
            normalized_bank = self._normalize_bank_name(bank_name)
            
            if self.use_mongodb:
                query = {'bank_name': normalized_bank}
                if target_month:
                    query['month'] = target_month
                
                result = self.bill_amounts_collection.find(query).sort('updated_at', -1).limit(1)
                
                for bill_data in result:
                    return {
                        'amount': bill_data['amount'],
                        'due_date': bill_data['due_date'],
                        'statement_date': bill_data.get('statement_date'),
                        'month': bill_data['month']
                    }
            else:
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
        """增強待辦事項顯示"""
        try:
            if '卡費' in todo_content:
                bill_info = None
                
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
    
    # ===== 原有功能保持不變 =====
    
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
    
    def send_daily_reminder(self, user_id, current_time):
        """發送每日提醒（包含生理期提醒）"""
        time_icon = '🌅' if current_time == self.user_settings['morning_time'] else '🌙'
        time_text = '早安' if current_time == self.user_settings['morning_time'] else '晚安'
        
        # 檢查生理期提醒
        taiwan_now = get_taiwan_datetime()
        period_reminder = self.check_period_reminders(user_id, taiwan_now)
        period_message = self.format_period_reminder(period_reminder)
        
        todos = self.todo_manager.todos
        if todos:
            pending_todos = self.todo_manager.get_pending_todos()
            completed_todos = self.todo_manager.get_completed_todos()
            
            if pending_todos:
                message = f'{time_icon} {time_text}！您有 {len(pending_todos)} 項待辦事項：\n\n'
                
                for i, todo in enumerate(pending_todos[:5], 1):
                    date_info = f" 📅{todo.get('target_date', '')}" if todo.get('has_date') else ""
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
                
                # 添加生理期提醒
                if period_message:
                    message += f'\n{period_message}\n'
                
                if current_time == self.user_settings['morning_time']:
                    message += f'\n💪 新的一天開始了！加油完成這些任務！'
                else:
                    message += f'\n🌙 檢查一下今天的進度吧！記得為明天做準備！'
                    
                message += f'\n🇹🇼 台灣時間: {get_taiwan_time_hhmm()}'
                
                send_push_message(user_id, message)
                print(f"✅ 已發送每日提醒 ({len(pending_todos)} 項待辦) - 台灣時間: {get_taiwan_time()}")
            else:
                message = ""
                if current_time == self.user_settings['morning_time']:
                    message = f'{time_icon} {time_text}！🎉 太棒了！目前沒有待辦事項\n💡 可以新增今天要做的事情'
                else:
                    message = f'{time_icon} {time_text}！🎉 太棒了！今天的任務都完成了\n😴 好好休息，為明天準備新的目標！'
                
                # 即使沒有待辦事項也要檢查生理期提醒
                if period_message:
                    message += f'\n\n{period_message}'
                
                message += f'\n🇹🇼 台灣時間: {get_taiwan_time_hhmm()}'
                send_push_message(user_id, message)
                print(f"✅ 已發送每日提醒 (無待辦事項) - 台灣時間: {get_taiwan_time()}")
        else:
            message = ""
            if current_time == self.user_settings['morning_time']:
                message = f'{time_icon} {time_text}！✨ 新的一天開始了！\n💡 輸入「新增 事項名稱」來建立今天的目標'
            else:
                message = f'{time_icon} {time_text}！😌 今天過得如何？\n💡 別忘了為明天規劃一些目標'
            
            # 首次使用也要檢查生理期提醒
            if period_message:
                message += f'\n\n{period_message}'
            
            message += f'\n🇹🇼 台灣時間: {get_taiwan_time_hhmm()}'
            send_push_message(user_id, message)
            print(f"✅ 已發送每日提醒 (首次使用) - 台灣時間: {get_taiwan_time()}")
    
    # ===== 其他原有功能的簡化實作 =====
    
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
    
    def check_reminders(self):
        while True:
            try:
                current_time = get_taiwan_time_hhmm()
                user_id = self.user_settings.get('user_id')
                taiwan_now = get_taiwan_datetime()
                today_date = taiwan_now.strftime('%Y-%m-%d')
                
                print(f"🔍 提醒檢查 - 台灣時間: {get_taiwan_time()}")
                
                if user_id:
                    if (current_time == self.user_settings['morning_time'] and 
                        self.last_reminders['daily_morning_date'] != today_date):
                        self.send_daily_reminder(user_id, current_time)
                        self.last_reminders['daily_morning_date'] = today_date
                    
                    elif (current_time == self.user_settings['evening_time'] and 
                          self.last_reminders['daily_evening_date'] != today_date):
                        self.send_daily_reminder(user_id, current_time)
                        self.last_reminders['daily_evening_date'] = today_date
                
                time.sleep(60)
            except Exception as e:
                print(f"提醒檢查錯誤: {e} - 台灣時間: {get_taiwan_time()}")
                time.sleep(60)
    
    def start_reminder_thread(self):
        if self.reminder_thread is None or not self.reminder_thread.is_alive():
            self.reminder_thread = threading.Thread(target=self.check_reminders, daemon=True)
            self.reminder_thread.start()
            print("✅ 提醒機器人執行緒已啟動")
    
    def get_reminder_counts(self):
        return {
            'short_reminders': len(self._get_short_reminders()),
            'time_reminders': len(self._get_time_reminders())
        }

    @property 
    def short_reminders(self):
        return self._get_short_reminders()

    @property
    def time_reminders(self):
        return self._get_time_reminders()
