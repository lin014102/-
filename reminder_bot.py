"""
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
    
    # ===== 🆕 智能帳單提醒功能 =====
    
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
        
        # 2. 🆕 檢查緊急帳單提醒
        urgent_bills = self.check_urgent_bill_payments(user_id)
        bill_reminder = self.format_bill_reminders(urgent_bills)
        
        todos = self.todo_manager.todos
        
        if todos:
            pending_todos = self.todo_manager.get_pending_todos()
            completed_todos = self.todo_manager.get_completed_todos()
            
            if pending_todos:
                message = f'{time_icon} {time_text}！您有 {len(pending_todos)} 項待辦事項：\n\n'
                
                # 🆕 優先顯示緊急帳單提醒
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
                
                # 🆕 即使沒有待辦事項也要檢查緊急帳單和生理期
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
    
    # ===== 🔧 修正後的提醒檢查功能 =====
    
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
                    
                    # === 🆕 短期提醒檢查 ===
                    self._check_and_send_short_reminders(user_id, taiwan_now)
                    
                    # === 🆕 時間提醒檢查 ===
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
    
    # ===== 🔧 調試功能 =====
    
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
    
    # ===== 帳單金額管理功能（保留原有功能）=====
    
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
