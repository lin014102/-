"""
reminder_bot.py - 提醒機器人模組 (完整整合版 + 修復短期提醒 + 修復每月提醒)
修正版生理期追蹤 + 下次預測查詢 + 智能帳單金額提醒整合 + 完整短期提醒功能 + 完整每月提醒功能
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
    """提醒機器人 (MongoDB Atlas 版本) + 帳單金額整合 + 生理期追蹤 + 智能帳單提醒 + 完整短期提醒功能 + 每月提醒功能"""
    
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
        
        # 修正：加入每月提醒的追蹤變數
        self.last_reminders = {
            'daily_morning_date': None,
            'daily_evening_date': None,
            'morning_todo_preview_date': None,    # 新增：早上預告明天
            'dated_todo_preview_date': None,      # 前一天晚上預告
            'dated_todo_morning_date': None,      # 當天早上提醒
            'dated_todo_evening_date': None       # 當天晚上提醒
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

    # ===== 每月提醒功能 =====
    
    def send_dated_todo_preview(self, user_id, taiwan_now):
        """發送有日期的待辦事項預告（前一天晚上）"""
        try:
            tomorrow = taiwan_now + timedelta(days=1)
            tomorrow_day = tomorrow.day
            
            # 獲取明天的每月事項
            monthly_items = self.todo_manager.get_monthly_items_for_day(tomorrow_day)
            
            # 獲取明天的有日期待辦事項
            tomorrow_str = tomorrow.strftime('%Y/%m/%d')
            dated_todos = self.todo_manager.get_pending_todos_by_date(tomorrow_str)
            
            if monthly_items or dated_todos:
                message = f"📅 明天 ({tomorrow.strftime('%m/%d')}) 的重要提醒：\n\n"
                
                # 檢查緊急帳單
                urgent_bills = self.check_urgent_bill_payments(user_id)
                bill_reminder = self.format_bill_reminders(urgent_bills)
                
                if bill_reminder:
                    message += f"{bill_reminder}\n"
                    message += f"{'='*20}\n\n"
                
                # 每月固定事項
                if monthly_items:
                    message += "🔄 每月固定事項：\n"
                    for i, item in enumerate(monthly_items, 1):
                        enhanced_content = self._enhance_todo_with_bill_amount(item["content"])
                        message += f"{i}. 📌 {enhanced_content}\n"
                    message += "\n"
                
                # 有日期的待辦事項
                if dated_todos:
                    message += "📋 指定日期待辦：\n"
                    for i, todo in enumerate(dated_todos, len(monthly_items) + 1):
                        enhanced_content = self._enhance_todo_with_bill_amount(todo["content"])
                        message += f"{i}. 📅 {enhanced_content}\n"
                    message += "\n"
                
                message += f"💡 記得提前準備！\n"
                message += f"🇹🇼 台灣時間: {get_taiwan_time_hhmm()}"
                
                send_push_message(user_id, message)
                print(f"✅ 已發送明天待辦事項預告 (每月:{len(monthly_items)}, 指定:{len(dated_todos)}) - 台灣時間: {get_taiwan_time()}")
                
        except Exception as e:
            print(f"❌ 發送待辦事項預告失敗: {e}")

    def send_dated_todo_reminder(self, user_id, taiwan_now, time_period):
        """發送有日期的待辦事項提醒（當天）"""
        try:
            current_day = taiwan_now.day
            today_str = taiwan_now.strftime('%Y/%m/%d')
            
            # 1. 將每月事項自動加入今日待辦清單
            added_monthly_items = self.todo_manager.add_monthly_todo_to_daily(taiwan_now)
            
            # 2. 獲取今天的所有待辦事項（包含新加入的每月事項）
            today_todos = self.todo_manager.get_today_pending_todos(taiwan_now)
            
            # 3. 獲取今天的每月事項（用於顯示）
            monthly_items = self.todo_manager.get_monthly_items_for_day(current_day)
            
            if today_todos or monthly_items:
                time_icon = '🌅' if time_period == 'morning' else '🌙'
                time_text = '早安' if time_period == 'morning' else '晚安'
                
                message = f"{time_icon} {time_text}！今天有重要事項需要處理：\n\n"
                
                # 檢查緊急帳單
                urgent_bills = self.check_urgent_bill_payments(user_id)
                bill_reminder = self.format_bill_reminders(urgent_bills)
                
                if bill_reminder:
                    message += f"{bill_reminder}\n"
                    message += f"{'='*20}\n\n"
                
                # 如果有新加入的每月事項
                if added_monthly_items:
                    message += "🔄 已自動加入今日待辦：\n"
                    for i, item in enumerate(added_monthly_items, 1):
                        enhanced_content = self._enhance_todo_with_bill_amount(item)
                        message += f"{i}. 📌 {enhanced_content}\n"
                    message += "\n"
                
                # 所有今日待辦事項
                if today_todos:
                    message += f"📋 今日待辦事項 ({len(today_todos)} 項)：\n"
                    for i, todo in enumerate(today_todos[:10], 1):  # 最多顯示10項
                        enhanced_content = self._enhance_todo_with_bill_amount(todo["content"])
                        message += f"{i}. ⭕ {enhanced_content}\n"
                    
                    if len(today_todos) > 10:
                        message += f"...還有 {len(today_todos) - 10} 項\n"
                    message += "\n"
                
                # 生理期提醒
                period_reminder = self.check_period_reminders(user_id, taiwan_now)
                period_message = self.format_period_reminder(period_reminder)
                if period_message:
                    message += f"{period_message}\n\n"
                
                # 鼓勵訊息
                if time_period == 'morning':
                    message += f"💪 新的一天開始了！優先處理重要事項！"
                else:
                    message += f"🌙 檢查一下今天的進度，為明天做準備！"
                
                message += f"\n🇹🇼 台灣時間: {get_taiwan_time_hhmm()}"
                
                send_push_message(user_id, message)
                print(f"✅ 已發送當日待辦事項提醒 ({time_period}, {len(today_todos)} 項) - 台灣時間: {get_taiwan_time()}")
                
        except Exception as e:
            print(f"❌ 發送當日待辦事項提醒失敗: {e}")

    # ===== 修復版短期提醒功能 =====
    
    def send_short_reminder(self, user_id, reminder):
        """發送短期提醒"""
        try:
            message = f"⏰ 短期提醒時間到！\n\n"
            message += f"📝 提醒內容：{reminder['content']}\n"
            message += f"🕒 設定時間：{reminder['original_value']}{reminder['unit']}前\n"
            message += f"🇹🇼 當前台灣時間：{get_taiwan_time_hhmm()}"
            
            send_push_message(user_id, message)
            print(f"✅ 已發送短期提醒：{reminder['content']} - 台灣時間: {get_taiwan_time()}")
            
        except Exception as e:
            print(f"❌ 發送短期提醒失敗: {e}")
    
    def send_time_reminder(self, user_id, reminder):
        """發送時間提醒"""
        try:
            message = f"🕐 定時提醒時間到！\n\n"
            message += f"📝 提醒內容：{reminder['content']}\n"
            message += f"⏰ 設定時間：{reminder['time_string']}\n"
            message += f"🇹🇼 當前台灣時間：{get_taiwan_time_hhmm()}"
            
            send_push_message(user_id, message)
            print(f"✅ 已發送定時提醒：{reminder['content']} ({reminder['time_string']}) - 台灣時間: {get_taiwan_time()}")
            
        except Exception as e:
            print(f"❌ 發送定時提醒失敗: {e}")
    
    def check_and_send_short_reminders(self):
        """檢查並發送短期提醒"""
        try:
            taiwan_now = get_taiwan_datetime()
            short_reminders = self._get_short_reminders()
            
            reminders_to_remove = []
            
            for reminder in short_reminders:
                reminder_time = datetime.fromisoformat(reminder['reminder_time'])
                
                # 檢查是否到時間（允許1分鐘的誤差）
                time_diff = (taiwan_now - reminder_time).total_seconds()
                
                if 0 <= time_diff <= 60:  # 在提醒時間後的1分鐘內
                    self.send_short_reminder(reminder['user_id'], reminder)
                    reminders_to_remove.append(reminder['id'])
                elif time_diff > 60:  # 超過1分鐘，視為過期
                    print(f"⚠️ 短期提醒過期：{reminder['content']} (過期 {int(time_diff/60)} 分鐘)")
                    reminders_to_remove.append(reminder['id'])
            
            # 移除已發送或過期的提醒
            for reminder_id in reminders_to_remove:
                self._remove_short_reminder(reminder_id)
                
        except Exception as e:
            print(f"❌ 檢查短期提醒失敗: {e}")
    
    def check_and_send_time_reminders(self):
        """檢查並發送時間提醒"""
        try:
            taiwan_now = get_taiwan_datetime()
            time_reminders = self._get_time_reminders()
            
            reminders_to_remove = []
            
            for reminder in time_reminders:
                reminder_time = datetime.fromisoformat(reminder['reminder_time'])
                
                # 檢查是否到時間（允許1分鐘的誤差）
                time_diff = (taiwan_now - reminder_time).total_seconds()
                
                if 0 <= time_diff <= 60:  # 在提醒時間後的1分鐘內
                    self.send_time_reminder(reminder['user_id'], reminder)
                    reminders_to_remove.append(reminder['id'])
                elif time_diff > 60:  # 超過1分鐘，視為過期
                    print(f"⚠️ 時間提醒過期：{reminder['content']} ({reminder['time_string']}) (過期 {int(time_diff/60)} 分鐘)")
                    reminders_to_remove.append(reminder['id'])
            
            # 移除已發送或過期的提醒
            for reminder_id in reminders_to_remove:
                self._remove_time_reminder(reminder_id)
                
        except Exception as e:
            print(f"❌ 檢查時間提醒失敗: {e}")
    
    # ===== 修復版提醒檢查核心邏輯 =====
    
    def check_reminders(self):
        """主提醒檢查循環（修復版 - 包含短期提醒、時間提醒、每日提醒、每月提醒、帳單和生理期提醒）"""
        while True:
            try:
                current_time = get_taiwan_time_hhmm()
                user_id = self.user_settings.get('user_id')
                taiwan_now = get_taiwan_datetime()
                today_date = taiwan_now.strftime('%Y-%m-%d')
                
                print(f"🔍 完整提醒檢查 - 台灣時間: {get_taiwan_time()}")
                
                # 1. 檢查短期提醒
                self.check_and_send_short_reminders()
                
                # 2. 檢查時間提醒
                self.check_and_send_time_reminders()
                
                # 3. 檢查每日提醒
                if user_id:
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
                    
                    # 4. 檢查每月提醒 - 前一天晚上預告
                    if (current_time == self.user_settings['evening_time'] and 
                        self.last_reminders.get('dated_todo_preview_date') != today_date):
                        self.send_dated_todo_preview(user_id, taiwan_now)
                        self.last_reminders['dated_todo_preview_date'] = today_date
                    # 4.5 檢查每月提醒 - 早上也預告明天（新增）
                    if (current_time == self.user_settings['morning_time'] and 
                       self.last_reminders.get('morning_todo_preview_date') != today_date):
                       self.send_dated_todo_preview(user_id, taiwan_now)
                       self.last_reminders['morning_todo_preview_date'] = today_date        
                    
                    # 5. 檢查每月提醒 - 當天早上提醒
                    if (current_time == self.user_settings['morning_time'] and 
                        self.last_reminders.get('dated_todo_morning_date') != today_date):
                        self.send_dated_todo_reminder(user_id, taiwan_now, 'morning')
                        self.last_reminders['dated_todo_morning_date'] = today_date
                    
                    # 6. 檢查每月提醒 - 當天晚上提醒
                    elif (current_time == self.user_settings['evening_time'] and 
                          self.last_reminders.get('dated_todo_evening_date') != today_date):
                        self.send_dated_todo_reminder(user_id, taiwan_now, 'evening')
                        self.last_reminders['dated_todo_evening_date'] = today_date
                
                time.sleep(60)  # 每分鐘檢查一次
            except Exception as e:
                print(f"❌ 完整提醒檢查錯誤: {e} - 台灣時間: {get_taiwan_time()}")
                time.sleep(60)
    
    def start_reminder_thread(self):
        """啟動提醒執行緒"""
        if self.reminder_thread is None or not self.reminder_thread.is_alive():
            self.reminder_thread = threading.Thread(target=self.check_reminders, daemon=True)
            self.reminder_thread.start()
            print("✅ 完整提醒機器人執行緒已啟動（包含短期提醒、時間提醒、智能帳單提醒、生理期提醒和每月提醒）")
    
    def get_reminder_counts(self):
        """獲取提醒統計"""
        short_reminders = self._get_short_reminders()
        time_reminders = self._get_time_reminders()
        
        return {
            'short_reminders': len(short_reminders),
            'time_reminders': len(time_reminders)
        }
    
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
        """獲取生理期狀態和預測"""
        try:
            records = self._get_period_records_safe(user_id)
            
            if not records:
                return "📊 生理期追蹤狀態\n\n❌ 尚未有任何記錄\n💡 請使用「記錄生理期 YYYY/MM/DD」開始追蹤"
            
            latest_record = records[0]
            
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
            
            if len(records) >= 2:
                try:
                    cycles = self._calculate_simple_cycles(records)
                    if cycles:
                        avg_cycle = sum(cycles) // len(cycles)
                        message += f"📊 平均週期：約 {avg_cycle} 天\n"
                        
                        last_start = datetime.strptime(latest_record['start_date'], '%Y-%m-%d')
                        predicted = last_start + timedelta(days=avg_cycle)
                        message += f"📅 下次預測：約 {predicted.strftime('%Y-%m-%d')}\n"
                except Exception as e:
                    message += "📊 週期計算中...\n"
            
            message += "\n💡 指令：\n"
            message += "• 記錄生理期 YYYY/MM/DD\n"
            message += "• 生理期結束 YYYY/MM/DD\n"
            message += "• 下次生理期\n"
            message += "• 生理期設定"
            
            return message
            
        except Exception as e:
            return "❌ 獲取狀態失敗，請稍後再試"
    
    def get_next_period_prediction(self, user_id):
        """獲取下次生理期預測日期"""
        try:
            records = self._get_period_records_safe(user_id)
            
            if not records:
                return "📅 下次生理期預測\n\n❌ 尚未有任何記錄\n💡 請先使用「記錄生理期 YYYY/MM/DD」建立歷史資料，才能進行預測"
            
            if len(records) < 2:
                latest_record = records[0]
                last_start = datetime.strptime(latest_record['start_date'], '%Y-%m-%d')
                
                settings = self._get_period_settings(user_id)
                default_cycle = settings.get('default_cycle_length', 28)
                
                predicted_date = last_start + timedelta(days=default_cycle)
                today = datetime.now().date()
                days_until = (predicted_date.date() - today).days
                
                message = "📅 下次生理期預測\n\n"
                message += f"⚠️ 記錄不足，使用預設週期 {default_cycle} 天\n"
                message += f"📅 預測日期：{predicted_date.strftime('%Y-%m-%d')}\n"
                
                if days_until > 0:
                    message += f"⏳ 距離：{days_until} 天後\n"
                elif days_until == 0:
                    message += f"📍 就是今天！\n"
                else:
                    message += f"⚠️ 可能已過期 {abs(days_until)} 天\n"
                
                message += f"\n💡 記錄數：{len(records)} 筆\n"
                message += "💡 至少需要 2 筆記錄才能計算準確週期"
                
                return message
            
            cycles = self._calculate_simple_cycles(records)
            
            if not cycles:
                return "📅 下次生理期預測\n\n⚠️ 週期資料異常，無法計算\n💡 請檢查記錄的日期是否正確"
            
            avg_cycle = sum(cycles) // len(cycles)
            min_cycle = min(cycles)
            max_cycle = max(cycles)
            
            latest_record = records[0]
            last_start = datetime.strptime(latest_record['start_date'], '%Y-%m-%d')
            
            predicted_date = last_start + timedelta(days=avg_cycle)
            earliest_date = last_start + timedelta(days=min_cycle)
            latest_date = last_start + timedelta(days=max_cycle)
            
            today = datetime.now().date()
            days_until_predicted = (predicted_date.date() - today).days
            days_until_earliest = (earliest_date.date() - today).days
            days_until_latest = (latest_date.date() - today).days
            
            message = "📅 下次生理期預測\n\n"
            message += f"🎯 最可能日期：{predicted_date.strftime('%Y-%m-%d')}\n"
            
            if days_until_predicted > 0:
                message += f"⏳ 距離：{days_until_predicted} 天後\n"
            elif days_until_predicted == 0:
                message += f"📍 就是今天！\n"
            else:
                message += f"⚠️ 可能已過期 {abs(days_until_predicted)} 天\n"
            
            message += f"\n📊 可能範圍：\n"
            message += f"🟢 最早：{earliest_date.strftime('%Y-%m-%d')} ({days_until_earliest}天{"後" if days_until_earliest >= 0 else "前"})\n"
            message += f"🔴 最晚：{latest_date.strftime('%Y-%m-%d')} ({days_until_latest}天{"後" if days_until_latest >= 0 else "前"})\n"
            
            message += f"\n📈 週期分析：\n"
            message += f"📊 平均週期：{avg_cycle} 天\n"
            message += f"📏 週期範圍：{min_cycle} - {max_cycle} 天\n"
            message += f"📋 分析基礎：{len(cycles)} 個週期\n"
            
            if days_until_earliest <= 7:
                message += f"\n💡 貼心提醒：\n"
                if days_until_earliest <= 3:
                    message += f"🎒 建議準備生理用品！\n"
                elif days_until_earliest <= 7:
                    message += f"📝 可以開始準備相關用品\n"
            
            message += f"\n📍 基於最近記錄：{latest_record['start_date']}\n"
            status_msg = "💾 已同步到雲端" if self.use_mongodb else ""
            message += f"{status_msg}"
            
            return message
            
        except Exception as e:
            return "❌ 預測失敗，請稍後再試"
    
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
            return "❌ 設定失敗，請稍後再試"
    
    # ===== 輔助功能 =====
    
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
                    if 15 <= cycle_length <= 45:
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
    
    # ===== 原有核心功能 =====
    
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
    
    def get_all_reminders(self, user_id):
        """獲取所有提醒列表"""
        try:
            taiwan_now = get_taiwan_datetime()
            
            short_reminders = self._get_short_reminders()
            user_short_reminders = [r for r in short_reminders if r.get('user_id') == user_id]
            
            time_reminders = self._get_time_reminders()
            user_time_reminders = [r for r in time_reminders if r.get('user_id') == user_id]
            
            message = "📋 提醒清單\n\n"
            
            if user_short_reminders:
                message += "⏰ 短期提醒：\n"
                for reminder in user_short_reminders:
                    try:
                        reminder_time = datetime.fromisoformat(reminder['reminder_time'])
                        time_diff = (reminder_time - taiwan_now).total_seconds()
                        
                        if time_diff > 0:
                            if time_diff < 3600:
                                remaining = f"{int(time_diff/60)}分鐘後"
                            elif time_diff < 86400:
                                hours = int(time_diff/3600)
                                minutes = int((time_diff % 3600)/60)
                                remaining = f"{hours}小時{minutes}分鐘後"
                            else:
                                days = int(time_diff/86400)
                                hours = int((time_diff % 86400)/3600)
                                remaining = f"{days}天{hours}小時後"
                            
                            message += f"• {reminder['content']} ({remaining})\n"
                        else:
                            message += f"• {reminder['content']} (待發送)\n"
                    except:
                        message += f"• {reminder['content']} (時間解析錯誤)\n"
                message += "\n"
            
            if user_time_reminders:
                message += "🕐 定時提醒：\n"
                for reminder in user_time_reminders:
                    try:
                        reminder_time = datetime.fromisoformat(reminder['reminder_time'])
                        
                        if reminder_time.date() == taiwan_now.date():
                            date_text = "今天"
                        elif reminder_time.date() == (taiwan_now + timedelta(days=1)).date():
                            date_text = "明天"
                        else:
                            date_text = reminder_time.strftime('%m/%d')
                        
                        message += f"• {reminder['content']} ({date_text} {reminder['time_string']})\n"
                    except:
                        message += f"• {reminder['content']} ({reminder.get('time_string', '時間錯誤')})\n"
                message += "\n"
            
            if not user_short_reminders and not user_time_reminders:
                message += "📝 目前沒有任何提醒\n\n"
                message += "💡 設定提醒方式：\n"
                message += "• 短期：「5分鐘後倒垃圾」\n"
                message += "• 定時：「14:00倒垃圾」\n"
            else:
                total_count = len(user_short_reminders) + len(user_time_reminders)
                message += f"📊 總計 {total_count} 個提醒"
            
            message += f"\n🕒 查詢時間：{get_taiwan_time_hhmm()}"
            return message
            
        except Exception as e:
            print(f"❌ 獲取提醒列表失敗: {e}")
            return f"❌ 獲取提醒列表失敗，請稍後再試\n🕒 {get_taiwan_time()}"
    
    # ===== 屬性訪問器 =====
    
    @property 
    def short_reminders(self):
        return self._get_short_reminders()

    @property
    def time_reminders(self):
        return self._get_time_reminders()
