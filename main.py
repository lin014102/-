"""
main.py - LINE Todo Reminder Bot 主程式 (完整整合版)
v3.4 + 智能對話狀態管理 + 智能帳單提醒整合 + Gemini AI + 自動帳單分析 + 生理期追蹤 + 下次生理期預測
新增功能：對話狀態記憶、智能確認詞處理、上下文理解
"""
from flask import Flask, request, jsonify
import os
import re
import threading
import time
from datetime import timedelta, datetime

# 匯入所有模組
from utils.time_utils import get_taiwan_time, get_taiwan_time_hhmm, get_taiwan_datetime, is_valid_time_format
from utils.line_api import reply_message
from todo_manager import todo_manager
from reminder_bot import ReminderBot
from stock_manager import (
    handle_stock_command, get_stock_summary, get_stock_transactions,
    get_stock_cost_analysis, get_stock_account_list, get_stock_help,
    is_stock_command, is_stock_query, get_stock_realtime_pnl
)

# 匯入增強版 Gemini AI 模組（支援對話狀態管理）
from gemini_analyzer import EnhancedMessageRouter

# 匯入帳單分析定時任務
from bill_scheduler import BillScheduler

# 初始化 Flask 應用
app = Flask(__name__)

# 建立模組實例
reminder_bot = ReminderBot(todo_manager)

# 使用增強版訊息路由器（支援對話狀態管理）
message_router = EnhancedMessageRouter(todo_manager, reminder_bot, None)

# 背景服務管理
class BackgroundServices:
    """背景服務管理器"""
    
    def __init__(self):
        self.services = []
        self.bill_scheduler = None
    
    def start_keep_alive(self):
        """啟動防休眠服務"""
        def keep_alive():
            import requests
            base_url = os.getenv('BASE_URL', 'https://line-bot-python-v2.onrender.com')
            
            while True:
                try:
                    time.sleep(240)
                    response = requests.get(f'{base_url}/health', timeout=15)
                    
                    if response.status_code == 200:
                        print(f"✅ Keep-alive 成功 - {get_taiwan_time()}")
                    else:
                        print(f"⚠️ Keep-alive 警告: {response.status_code} - {get_taiwan_time()}")
                        
                except requests.exceptions.RequestException as e:
                    print(f"❌ Keep-alive 錯誤: {e} - {get_taiwan_time()}")
                    time.sleep(60)
                except Exception as e:
                    print(f"❌ Keep-alive 意外錯誤: {e} - {get_taiwan_time()}")
                    time.sleep(60)
        
        thread = threading.Thread(target=keep_alive, daemon=True)
        thread.start()
        self.services.append('keep_alive')
        print("✅ 防休眠服務已啟動")
    
    def start_reminder_bot(self):
        """啟動提醒機器人"""
        reminder_bot.start_reminder_thread()
        self.services.append('reminder_bot')
        print("✅ 智能提醒機器人已啟動 (包含帳單和生理期提醒)")
    
    def start_bill_scheduler(self, bill_scheduler):
        """啟動帳單分析定時任務"""
        try:
            bill_scheduler.start_scheduler()
            self.services.append('bill_scheduler')
            self.bill_scheduler = bill_scheduler
            print("✅ 帳單分析定時任務已啟動")
        except Exception as e:
            print(f"⚠️ 帳單分析定時任務啟動失敗: {e}")

# 建立背景服務管理器
bg_services = BackgroundServices()

# ===== Flask 路由 =====
@app.route('/')
def home():
    """首頁"""
    return f"""
    <h1>LINE Todo Reminder Bot v3.4 - 智能對話狀態管理完整整合版</h1>
    <p>🇹🇼 當前台灣時間：{get_taiwan_time()}</p>
    <p>🚀 完整模組化架構 + 智能對話狀態管理！</p>
    <p>💭 支援智能確認詞處理和上下文記憶！</p>
    <p>💹 即時損益功能！</p>
    <p>🤖 Gemini AI 智能對話！</p>
    <p>📊 帳單自動分析與智能提醒整合！</p>
    <p>💳 繳費截止前自動提醒具體金額！</p>
    <p>🩸 生理期智能追蹤提醒！</p>
    <p>📅 下次生理期預測查詢！</p>
    <p>📊 健康檢查：<a href="/health">/health</a></p>
    
    <h2>🆕 智能對話功能測試：</h2>
    <ul>
        <li><strong>🗣️ 單一關鍵詞理解</strong> - 「買股票」、「生理期」、「帳單」等單詞觸發</li>
        <li><strong>💭 對話狀態記憶</strong> - 5分鐘內記住對話狀態</li>
        <li><strong>✅ 智能確認處理</strong> - 「是的」、「好」、「確定」自動執行建議動作</li>
        <li><strong>❌ 智能拒絕處理</strong> - 「不要」、「取消」自動清除狀態</li>
    </ul>
    
    <h2>🔥 體驗流程範例：</h2>
    <ol>
        <li>輸入「買股票」→ 系統詢問您想做什麼</li>
        <li>回覆「是的」→ 系統顯示股票功能說明</li>
        <li>輸入「生理期」→ 系統顯示生理期功能選項</li>
        <li>回覆「好」→ 系統提供詳細說明</li>
        <li>輸入「等一下要洗碗」→ 系統建議新增待辦</li>
        <li>回覆「確定」→ 系統自動新增到待辦清單</li>
    </ol>
    
    <h2>完整整合功能測試：</h2>
    <ul>
        <li><a href="/test/conversation-state"><strong>💭 測試對話狀態管理</strong></a> - 驗證狀態記憶功能</li>
        <li><a href="/test/bill-sync-integration">📊 測試帳單同步整合</a></li>
        <li><a href="/test/enhanced-reminder">📈 測試增強版提醒訊息</a></li>
        <li><a href="/test/bill-amounts">💰 測試帳單金額查詢</a></li>
    </ul>
    
    <h2>帳單分析功能測試：</h2>
    <ul>
        <li><a href="/test/sheets-connection">測試 Google Sheets 連接</a></li>
        <li><a href="/test/bill-analysis">手動執行帳單分析</a></li>
        <li><a href="/test/notifications">手動執行推播</a></li>
        <li><a href="/test/bank-mapping">測試銀行名稱對應</a></li>
    </ul>
    
    <h2>生理期追蹤測試：</h2>
    <ul>
        <li><a href="/test/period-tracker">測試生理期追蹤</a></li>
        <li><a href="/test/add-test-period">新增測試生理期資料</a></li>
        <li><a href="/test/next-period-prediction">測試下次生理期預測</a></li>
    </ul>
    """

@app.route('/health')
def health():
    """健康檢查端點 - 更新版（包含對話狀態管理）"""
    taiwan_now = get_taiwan_datetime()
    
    try:
        # 計算下次提醒時間
        morning_time = reminder_bot.user_settings['morning_time']
        evening_time = reminder_bot.user_settings['evening_time']
        
        next_morning = taiwan_now.replace(
            hour=int(morning_time.split(':')[0]),
            minute=int(morning_time.split(':')[1]),
            second=0, microsecond=0
        )
        if next_morning <= taiwan_now:
            next_morning += timedelta(days=1)
        
        next_evening = taiwan_now.replace(
            hour=int(evening_time.split(':')[0]),
            minute=int(evening_time.split(':')[1]),
            second=0, microsecond=0
        )
        if next_evening <= taiwan_now:
            next_evening += timedelta(days=1)
        
        next_reminder = min(next_morning, next_evening)
        next_reminder_str = next_reminder.strftime('%Y/%m/%d %H:%M')
    except:
        next_reminder_str = "計算錯誤"
    
    # 獲取各模組狀態
    reminder_counts = reminder_bot.get_reminder_counts()
    
    # 獲取 Gemini AI 狀態
    gemini_status = message_router.gemini_analyzer.enabled
    
    # 獲取對話狀態統計
    try:
        state_count = len(message_router.gemini_analyzer.conversation_state.user_states)
        conversation_state_info = {
            'active_conversations': state_count,
            'state_management_enabled': True,
            'state_timeout_minutes': 5,
            'supported_confirmations': ['是的', '是', '好', '確定', '對', '要', 'yes', 'ok'],
            'supported_rejections': ['不', '不要', '不是', '取消', '算了', 'no'],
            'features': ['confirmation_handling', 'context_memory', 'smart_suggestions', 'auto_state_cleanup']
        }
    except Exception as e:
        conversation_state_info = {
            'active_conversations': 0,
            'state_management_enabled': False,
            'error': str(e)
        }
    
    # 獲取帳單分析定時任務狀態
    try:
        bill_scheduler_status = bg_services.bill_scheduler.get_status() if bg_services.bill_scheduler else {'scheduler_running': False}
    except:
        bill_scheduler_status = {'scheduler_running': False, 'error': 'not_initialized'}
    
    # 測試緊急帳單檢查功能
    try:
        user_id = reminder_bot.user_settings.get('user_id', 'health_check_user')
        urgent_bills = reminder_bot.check_urgent_bill_payments(user_id)
        bill_integration_working = True
    except Exception as e:
        urgent_bills = []
        bill_integration_working = False
    
    return jsonify({
        'status': 'healthy',
        'taiwan_time': get_taiwan_time(),
        'taiwan_time_hhmm': get_taiwan_time_hhmm(),
        'server_timezone': str(taiwan_now.tzinfo),
        'version': 'v3.4_smart_conversation_state_management',
        
        # 模組狀態
        'modules': {
            'todo_manager': {
                'todos_count': todo_manager.get_todo_count(),
                'monthly_todos_count': todo_manager.get_monthly_count()
            },
            'reminder_bot': {
                'short_reminders': reminder_counts['short_reminders'],
                'time_reminders': reminder_counts['time_reminders'],
                'morning_time': reminder_bot.user_settings['morning_time'],
                'evening_time': reminder_bot.user_settings['evening_time'],
                'next_reminder': next_reminder_str,
                'has_user': reminder_bot.user_settings['user_id'] is not None
            },
            'stock_manager': {
                'realtime_pnl_enabled': True,
                'features': ['basic_accounting', 'google_sheets_sync', 'realtime_stock_prices', 'pnl_analysis']
            },
            'gemini_ai': {
                'enabled': gemini_status,
                'conversation_memory': True,
                'smart_confirmation': True,
                'enhanced_keyword_detection': True,
                'features': ['natural_language_understanding', 'smart_suggestions', 'intent_classification', 'state_management', 'confirmation_handling']
            },
            'conversation_state_manager': conversation_state_info,
            'bill_scheduler': {
                'scheduler_running': bill_scheduler_status.get('scheduler_running', False),
                'analysis_time': bill_scheduler_status.get('analysis_time', '03:30'),
                'notification_time': bill_scheduler_status.get('notification_time', '15:15'),
                'last_analysis_date': bill_scheduler_status.get('last_analysis_date'),
                'last_notification_date': bill_scheduler_status.get('last_notification_date'),
                'notification_enabled': bill_scheduler_status.get('notification_enabled', False),
                'features': ['daily_pdf_analysis', 'google_vision_ocr', 'gemini_llm', 'line_notifications', 'auto_bill_sync']
            },
            'smart_bill_integration': {
                'mongodb_enabled': reminder_bot.use_mongodb,
                'collection_ready': hasattr(reminder_bot, 'bill_amounts_collection') if reminder_bot.use_mongodb else True,
                'integration_working': bill_integration_working,
                'urgent_bills_detected': len(urgent_bills),
                'test_banks': ['永豐', '台新', '國泰', '星展', '匯豐', '玉山', '聯邦'],
                'features': ['auto_sync', 'smart_reminders', 'urgency_detection', 'enhanced_todo_display']
            },
            'period_tracker': {
                'mongodb_enabled': reminder_bot.use_mongodb,
                'collection_ready': hasattr(reminder_bot, 'period_records_collection') if reminder_bot.use_mongodb else True,
                'features': ['cycle_calculation', 'prediction', 'smart_reminders', 'next_period_prediction']
            },
            'background_services': bg_services.services
        }
    })

# ===== 新增測試端點 =====

@app.route('/test/conversation-state')
def test_conversation_state():
    """測試對話狀態管理功能"""
    try:
        state_manager = message_router.gemini_analyzer.conversation_state
        test_user_id = "test_user_123"
        
        # 測試設定狀態
        state_manager.set_pending_action(
            test_user_id,
            'add_todo',
            {'todo_text': '洗碗', 'is_monthly': False},
            ['新增到待辦清單', '設為每月固定事項']
        )
        
        # 測試獲取狀態
        pending = state_manager.get_pending_action(test_user_id)
        
        # 測試確認詞檢測
        analyzer = message_router.gemini_analyzer
        confirmation_tests = ['是的', '好', '確定', 'yes', 'ok']
        rejection_tests = ['不要', '取消', 'no']
        
        results = {
            'state_set_successfully': pending is not None,
            'pending_action_details': pending,
            'confirmation_detection': {
                word: analyzer._is_confirmation_message(word) 
                for word in confirmation_tests
            },
            'rejection_detection': {
                word: analyzer._is_rejection_message(word) 
                for word in rejection_tests
            },
            'active_states_count': len(state_manager.user_states),
            'timestamp': get_taiwan_time()
        }
        
        # 清理測試狀態
        state_manager.clear_pending_action(test_user_id)
        
        return jsonify({
            'success': True,
            'data': results
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': get_taiwan_time()
        })

@app.route('/test/bill-amounts')
def test_bill_amounts():
    """測試帳單金額查詢功能"""
    try:
        banks = ['永豐', '台新', '國泰', '星展', '匯豐', '玉山', '聯邦']
        results = {}
        
        for bank in banks:
            bill_info = reminder_bot.get_bill_amount(bank)
            results[bank] = bill_info
        
        return jsonify({
            'success': True,
            'data': results,
            'timestamp': get_taiwan_time()
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': get_taiwan_time()
        })

@app.route('/test/enhanced-reminder')
def test_enhanced_reminder():
    """測試增強版提醒訊息顯示"""
    try:
        test_todos = [
            "繳永豐卡費",
            "繳台新卡費", 
            "繳國泰卡費",
            "買菜",
            "繳星展卡費"
        ]
        
        results = {}
        for todo in test_todos:
            enhanced = reminder_bot._enhance_todo_with_bill_amount(todo)
            results[todo] = enhanced
        
        return jsonify({
            'success': True,
            'data': results,
            'timestamp': get_taiwan_time()
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': get_taiwan_time()
        })

# ===== Webhook 處理 =====

@app.route('/webhook', methods=['POST'])
def webhook():
    """LINE Webhook 處理 - 統一入口（支援智能對話狀態管理）"""
    try:
        data = request.get_json()
        
        for event in data.get('events', []):
            if event['type'] == 'message' and event['message']['type'] == 'text':
                reply_token = event['replyToken']
                message_text = event['message']['text']
                user_id = event['source']['userId']
                
                print(f"📨 用戶訊息: {message_text} - {get_taiwan_time()}")
                
                # 先檢查帳單查詢（精確匹配優先）
                bill_keywords = ['帳單查詢', '帳單總覽', '卡費查詢', '緊急帳單', '逾期帳單', '帳單狀態']
                bank_bill_patterns = ['永豐帳單查詢', '台新帳單查詢', '國泰帳單查詢', '星展帳單查詢', '匯豐帳單查詢', '玉山帳單查詢', '聯邦帳單查詢']
                
                if (any(keyword in message_text for keyword in bill_keywords) or 
                    any(pattern in message_text for pattern in bank_bill_patterns)):
                    print(f"🔀 路由到帳單查詢: {message_text}")
                    reply_text = handle_bill_query_command(message_text, user_id)
                else:
                    # 其他訊息使用增強版路由器（支援對話狀態管理）
                    reply_text = enhanced_message_router(message_text, user_id)
                
                # 回覆訊息
                reply_message(reply_token, reply_text)
        
        return 'OK', 200
    
    except Exception as e:
        print(f"❌ Webhook 處理錯誤: {e} - {get_taiwan_time()}")
        return 'OK', 200

# ===== 帳單查詢訊息處理函數 =====

def handle_bill_query_command(message_text, user_id):
    """處理帳單查詢相關指令"""
    try:
        # ========== 標記已繳納 ==========
        if '標記' in message_text and '已繳' in message_text:
            banks_mapping = {
                '永豐': ['永豐', 'sinopac'],
                '台新': ['台新', 'taishin'],
                '國泰': ['國泰', 'cathay'],
                '星展': ['星展', 'dbs'],
                '匯豐': ['匯豐', 'hsbc'],
                '玉山': ['玉山', 'esun'],
                '聯邦': ['聯邦', 'union']
            }
            
            matched_bank = None
            for bank_name, patterns in banks_mapping.items():
                if any(pattern in message_text.lower() for pattern in patterns):
                    matched_bank = bank_name
                    break
            
            if matched_bank:
                return reminder_bot.mark_bill_as_paid(matched_bank)
            else:
                return "❌ 請指定銀行名稱\n💡 格式：標記[銀行]帳單已繳納\n例如：標記聯邦帳單已繳納"
        
        # ========== 取消已繳納標記 ==========
        if '取消' in message_text and ('已繳' in message_text or '標記' in message_text):
            banks_mapping = {
                '永豐': ['永豐', 'sinopac'],
                '台新': ['台新', 'taishin'],
                '國泰': ['國泰', 'cathay'],
                '星展': ['星展', 'dbs'],
                '匯豐': ['匯豐', 'hsbc'],
                '玉山': ['玉山', 'esun'],
                '聯邦': ['聯邦', 'union']
            }
            
            matched_bank = None
            for bank_name, patterns in banks_mapping.items():
                if any(pattern in message_text.lower() for pattern in patterns):
                    matched_bank = bank_name
                    break
            
            if matched_bank:
                return reminder_bot.unmark_bill_paid(matched_bank)
            else:
                return "❌ 請指定銀行名稱\n💡 格式：取消[銀行]已繳納標記"
        
        # ========== 刪除帳單 ==========
        if '刪除' in message_text and '帳單' in message_text:
            banks_mapping = {
                '永豐': ['永豐', 'sinopac'],
                '台新': ['台新', 'taishin'],
                '國泰': ['國泰', 'cathay'],
                '星展': ['星展', 'dbs'],
                '匯豐': ['匯豐', 'hsbc'],
                '玉山': ['玉山', 'esun'],
                '聯邦': ['聯邦', 'union']
            }
            
            matched_bank = None
            for bank_name, patterns in banks_mapping.items():
                if any(pattern in message_text.lower() for pattern in patterns):
                    matched_bank = bank_name
                    break
            
            if matched_bank:
                return reminder_bot.delete_bill_amount(matched_bank)
            else:
                return "❌ 請指定銀行名稱\n💡 格式：刪除[銀行]帳單\n例如：刪除聯邦帳單"
        
        # ========== 緊急帳單查詢 ==========
        if any(keyword in message_text for keyword in ['緊急帳單', '逾期帳單', '即將到期']):
            urgent_bills = reminder_bot.check_urgent_bill_payments(user_id)
            if urgent_bills:
                bill_reminder = reminder_bot.format_bill_reminders(urgent_bills)
                return f"📊 緊急帳單狀態\n\n{bill_reminder}\n\n🕒 查詢時間: {get_taiwan_time_hhmm()}"
            else:
                return f"✅ 目前沒有緊急帳單\n💡 所有帳單都在安全期限內\n🕒 查詢時間: {get_taiwan_time_hhmm()}"
        
        # ========== 帳單總覽查詢 ==========
        elif any(keyword in message_text for keyword in ['帳單總覽', '帳單查詢', '卡費查詢', '帳單狀態']):
            banks = ['永豐', '台新', '國泰', '星展', '匯豐', '玉山', '聯邦']
            urgent_bills = reminder_bot.check_urgent_bill_payments(user_id)
            
            message = "💳 帳單總覽\n\n"
            
            if urgent_bills:
                bill_reminder = reminder_bot.format_bill_reminders(urgent_bills)
                message += f"{bill_reminder}\n\n"
                message += f"{'='*20}\n\n"
            
            has_bills = False
            for bank in banks:
                bill_info = reminder_bot.get_bill_amount(bank)
                if bill_info:
                    has_bills = True
                    try:
                        taiwan_now = get_taiwan_datetime()
                        today = taiwan_now.date()
                        due_date = datetime.strptime(bill_info['due_date'], '%Y/%m/%d').date()
                        days_until_due = (due_date - today).days
                        
                        if '/' in bill_info['due_date'] and len(bill_info['due_date'].split('/')) == 3:
                            year, month, day = bill_info['due_date'].split('/')
                            formatted_date = f"{int(month)}/{int(day)}"
                        else:
                            formatted_date = bill_info['due_date']
                        
                        if days_until_due < 0:
                            status_icon = "🚨"
                            status_text = f"逾期{abs(days_until_due)}天"
                        elif days_until_due == 0:
                            status_icon = "⏰"
                            status_text = "今天截止"
                        elif days_until_due <= 3:
                            status_icon = "⚡"
                            status_text = f"{days_until_due}天後"
                        elif days_until_due <= 7:
                            status_icon = "💡"
                            status_text = f"{days_until_due}天後"
                        else:
                            status_icon = "✅"
                            status_text = f"{days_until_due}天後"
                        
                        message += f"{status_icon} {bank}：{bill_info['amount']}\n"
                        message += f"   截止：{formatted_date} ({status_text})\n\n"
                        
                    except ValueError:
                        message += f"📄 {bank}：{bill_info['amount']}\n"
                        message += f"   截止：{bill_info['due_date']}\n\n"
            
            if not has_bills:
                message += "📝 目前沒有帳單記錄\n💡 帳單分析完成後會自動同步到這裡\n\n"
            elif not urgent_bills:
                message += "📝 目前沒有緊急帳單\n💡 所有帳單都在安全期限內\n\n"
            
            message += f"🕒 查詢時間: {get_taiwan_time_hhmm()}"
            return message
        
        # ========== 特定銀行帳單查詢 ==========
        else:
            banks_mapping = {
                '永豐': ['永豐', 'sinopac'],
                '台新': ['台新', 'taishin'],
                '國泰': ['國泰', 'cathay'],
                '星展': ['星展', 'dbs'],
                '匯豐': ['匯豐', 'hsbc'],
                '玉山': ['玉山', 'esun'],
                '聯邦': ['聯邦', 'union']
            }
            
            matched_bank = None
            for bank_name, patterns in banks_mapping.items():
                if any(pattern in message_text.lower() for pattern in patterns):
                    matched_bank = bank_name
                    break
            
            if matched_bank:
                bill_info = reminder_bot.get_bill_amount(matched_bank)
                if bill_info:
                    try:
                        taiwan_now = get_taiwan_datetime()
                        today = taiwan_now.date()
                        due_date = datetime.strptime(bill_info['due_date'], '%Y/%m/%d').date()
                        days_until_due = (due_date - today).days
                        
                        message = f"💳 {matched_bank}銀行帳單\n\n"
                        message += f"💰 應繳金額：{bill_info['amount']}\n"
                        message += f"⏰ 繳款截止：{bill_info['due_date']}\n"
                        
                        if days_until_due < 0:
                            message += f"🚨 狀態：逾期 {abs(days_until_due)} 天\n"
                        elif days_until_due == 0:
                            message += f"⏰ 狀態：今天截止\n"
                        elif days_until_due <= 3:
                            message += f"⚡ 狀態：{days_until_due} 天後到期\n"
                        elif days_until_due <= 7:
                            message += f"💡 狀態：{days_until_due} 天後到期\n"
                        else:
                            message += f"✅ 狀態：{days_until_due} 天後到期\n"
                        
                        if bill_info.get('statement_date'):
                            message += f"📅 帳單日期：{bill_info['statement_date']}\n"
                        
                        message += f"\n🕒 查詢時間: {get_taiwan_time_hhmm()}"
                        return message
                        
                    except ValueError:
                        return f"💳 {matched_bank}銀行帳單\n\n💰 應繳金額：{bill_info['amount']}\n⏰ 繳款截止：{bill_info['due_date']}\n\n🕒 查詢時間: {get_taiwan_time_hhmm()}"
                else:
                    return f"📝 {matched_bank}銀行目前沒有帳單記錄\n💡 帳單分析完成後會自動同步"
            else:
                return """💳 帳單查詢指令說明

🔍 可用查詢指令：
- 帳單查詢 / 帳單總覽 - 查看所有銀行帳單
- 緊急帳單 - 查看即將到期或逾期的帳單
- [銀行名稱]帳單查詢 - 查看特定銀行帳單
- 標記[銀行]帳單已繳納 - 標記為已繳納
- 取消[銀行]已繳納標記 - 恢復提醒
- 刪除[銀行]帳單 - 刪除帳單記錄

🏦 支援銀行：
永豐、台新、國泰、星展、匯豐、玉山、聯邦

💡 範例：
- 「帳單查詢」- 查看所有帳單狀態
- 「緊急帳單」- 查看需要優先處理的帳單
- 「標記聯邦帳單已繳納」- 標記聯邦卡費已繳
- 「刪除聯邦帳單」- 刪除聯邦卡費記錄"""
    
    except Exception as e:
        print(f"❌ 處理帳單查詢指令失敗: {e}")
        return f"❌ 查詢失敗，請稍後再試\n🕒 {get_taiwan_time()}"

def is_todo_query(message_text):
    """檢查是否為待辦事項相關查詢（更嚴格的判斷）"""
    # 精確的待辦事項指令
    exact_todo_commands = ['清單', '每月清單']
    
    if message_text in exact_todo_commands:
        return True
    
    # 只有明確包含待辦關鍵詞且不是其他功能的才歸類為待辦
    todo_keywords = ['新增', '刪除', '完成', '每月新增', '每月刪除']
    
    if any(message_text.startswith(keyword) for keyword in todo_keywords):
        return True
    
    return False

def enhanced_message_router(message_text, user_id):
    """增強版訊息路由器 - 整合對話狀態管理"""
    try:
        # 生理期追蹤指令檢查（包含下次預測）
        if is_period_command(message_text):
            print(f"🔀 路由到生理期追蹤模組: {message_text}")
            return handle_period_command(message_text, user_id)
        
        # 優先檢查待辦事項相關的查詢（但放寬限制）
        elif is_todo_query(message_text) and message_text not in ['查詢']:  # 排除單純的「查詢」
            print(f"🔀 路由到待辦事項模組: {message_text}")
            return message_router.route_message(message_text, user_id)
        
        # 檢查股票相關指令
        elif is_stock_command(message_text):
            print(f"🔀 路由到股票模組: {message_text}")
            return handle_stock_command(message_text)
        
        elif is_stock_query(message_text):
            print(f"🔀 路由到股票查詢: {message_text}")
            
            if message_text == '總覽':
                return get_stock_summary()
            elif message_text == '帳戶列表':
                return get_stock_account_list()
            elif message_text == '股票幫助':
                return get_stock_help()
            elif message_text.startswith('交易記錄'):
                parts = message_text.split()
                account_name = parts[1] if len(parts) > 1 else None
                return get_stock_transactions(account_name)
            elif message_text.startswith('成本查詢'):
                parts = message_text.split()
                if len(parts) >= 3:
                    return get_stock_cost_analysis(parts[1], parts[2])
                else:
                    return "❌ 請指定帳戶和股票名稱\n💡 格式：成本查詢 帳戶名稱 股票名稱"
            elif message_text.startswith('即時損益'):
                parts = message_text.split()
                account_name = parts[1] if len(parts) > 1 else None
                return get_stock_realtime_pnl(account_name)
            elif message_text.endswith('查詢') and len(message_text) > 2:
                account_name = message_text[:-2]
                return get_stock_summary(account_name)
        
        # 其他指令使用新的 Gemini AI 路由器（支援對話狀態）
        else:
            print(f"🔀 路由到 AI 分析器（支援對話狀態）: {message_text}")
            return message_router.route_message(message_text, user_id)
    
    except Exception as e:
        print(f"❌ 訊息路由錯誤: {e}")
        return f"❌ 系統處理錯誤，請稍後再試\n🕒 {get_taiwan_time()}"

# ===== 生理期追蹤訊息處理函數 =====

def is_period_command(message_text):
    """檢查是否為生理期相關指令（包含下次預測）"""
    period_keywords = [
        '記錄生理期', '生理期開始', '生理期記錄',
        '生理期結束', '結束生理期',
        '生理期查詢', '生理期狀態', '週期查詢',
        '生理期設定', '週期設定',
        '下次生理期', '下次月經', '生理期預測'
    ]
    
    return any(keyword in message_text for keyword in period_keywords)

def handle_period_command(message_text, user_id):
    """處理生理期相關指令（包含下次預測）"""
    try:
        # 下次生理期預測查詢
        if any(keyword in message_text for keyword in ['下次生理期', '下次月經', '生理期預測']):
            return reminder_bot.get_next_period_prediction(user_id)
        
        # 記錄生理期開始
        elif any(keyword in message_text for keyword in ['記錄生理期', '生理期開始', '生理期記錄']):
            date_match = re.search(r'(\d{4}[/-]\d{1,2}[/-]\d{1,2})', message_text)
            if date_match:
                date_str = date_match.group(1).replace('-', '/')
                notes = message_text.replace(date_match.group(0), '').replace('記錄生理期', '').replace('生理期開始', '').replace('生理期記錄', '').strip()
                return reminder_bot.record_period_start(date_str, user_id, notes)
            else:
                return "❌ 請指定日期\n💡 格式：記錄生理期 YYYY/MM/DD\n例如：記錄生理期 2025/01/15"
        
        # 記錄生理期結束
        elif any(keyword in message_text for keyword in ['生理期結束', '結束生理期']):
            date_match = re.search(r'(\d{4}[/-]\d{1,2}[/-]\d{1,2})', message_text)
            if date_match:
                date_str = date_match.group(1).replace('-', '/')
                notes = message_text.replace(date_match.group(0), '').replace('生理期結束', '').replace('結束生理期', '').strip()
                return reminder_bot.record_period_end(date_str, user_id, notes)
            else:
                return "❌ 請指定日期\n💡 格式：生理期結束 YYYY/MM/DD\n例如：生理期結束 2025/01/20"
        
        # 查詢生理期狀態
        elif any(keyword in message_text for keyword in ['生理期查詢', '生理期狀態', '週期查詢']):
            return reminder_bot.get_period_status(user_id)
        
        # 設定生理期偏好
        elif any(keyword in message_text for keyword in ['生理期設定', '週期設定']):
            cycle_match = re.search(r'(\d+)\s*天', message_text)
            reminder_match = re.search(r'提前\s*(\d+)\s*天', message_text)
            
            cycle_length = int(cycle_match.group(1)) if cycle_match else None
            reminder_days = int(reminder_match.group(1)) if reminder_match else 5
            
            if cycle_length and not (15 <= cycle_length <= 45):
                return "❌ 週期長度請設定在 15-45 天之間"
            
            if not (1 <= reminder_days <= 10):
                return "❌ 提前提醒天數請設定在 1-10 天之間"
            
            return reminder_bot.set_period_settings(user_id, cycle_length, reminder_days)
        
        else:
            return "❌ 生理期指令格式錯誤\n\n💡 可用指令：\n• 記錄生理期 YYYY/MM/DD\n• 生理期結束 YYYY/MM/DD\n• 生理期查詢\n• 下次生理期\n• 生理期設定 [週期天數] [提前天數]"
    
    except Exception as e:
        print(f"❌ 處理生理期指令失敗: {e}")
        return f"❌ 處理失敗，請稍後再試\n🕒 {get_taiwan_time()}"

def initialize_app():
    """初始化應用程式（完整整合版 - 支援對話狀態管理）"""
    print("🚀 LINE Todo Reminder Bot v3.4 - 智能對話狀態管理完整整合版 啟動中...")
    print(f"🇹🇼 台灣時間：{get_taiwan_time()}")
    
    # 啟動背景服務
    bg_services.start_keep_alive()
    bg_services.start_reminder_bot()
    
    # 啟動帳單分析定時任務（包含同步功能）
    try:
        bill_scheduler = BillScheduler(reminder_bot)
        bg_services.start_bill_scheduler(bill_scheduler)
    except Exception as e:
        print(f"⚠️ 帳單分析定時任務初始化失敗: {e}")
    
    print("=" * 70)
    print("📋 待辦事項管理：✅ 已載入")
    print("⏰ 智能提醒機器人：✅ 已啟動（包含帳單和生理期提醒）") 
    print("💰 股票記帳模組：✅ 已載入")
    print("💹 即時損益功能：✅ 已啟用")
    print("🤖 Gemini AI 模組：✅ 已整合")
    print("💭 對話狀態管理：✅ 新功能已啟用 - 支援智能確認與上下文記憶")
    print("🗣️ 智能確認詞處理：✅ 已啟用 - 支援「是的」「好」「確定」等")
    print("🧠 上下文記憶功能：✅ 已啟用 - 5分鐘內記住對話狀態")
    print("🔍 增強關鍵詞檢測：✅ 已啟用 - 單一詞彙觸發功能")
    print("📊 帳單分析定時任務：✅ 已啟動")
    print("💳 智能帳單提醒整合：✅ 已完成 - 帳單分析結果自動同步到提醒系統")
    print("🔔 繳費截止智能提醒：✅ 已啟用 - 顯示具體金額和緊急程度")
    print("📈 增強版待辦顯示：✅ 已啟用 - 卡費待辦自動顯示金額和截止日")
    print("🩸 生理期智能追蹤：✅ 已整合")
    print("📅 下次生理期預測：✅ 新功能已加入")
    print("🔧 完整模組化架構：✅ 完全重構並整合")
    print("=" * 70)
    print("🎉 智能對話狀態管理系統初始化完成！")
    print("💡 新功能體驗：")
    print("   1. 輸入「買股票」→ 系統會詢問您想做什麼")
    print("   2. 回覆「是的」→ 系統會執行建議的動作")
    print("   3. 輸入「生理期」→ 系統會顯示生理期功能選項")
    print("   4. 回覆「好」→ 系統會提供詳細說明")
    print("   5. 輸入「等一下要洗碗」→ 系統會建議新增待辦")
    print("   6. 回覆「確定」→ 系統會自動新增到待辦清單")
    print("   7. 輸入「帳單」→ 系統會顯示帳單查詢選項")
    print("   8. 回覆「要」→ 系統會執行帳單查詢")
    print("🔥 支援確認詞：是的、好、確定、對、要、yes、ok")
    print("❌ 支援拒絕詞：不、不要、取消、算了、no")
    print("⏱️ 對話狀態保持 5 分鐘，超時自動清除")
    print("🔍 關鍵詞智能檢測：買股票、生理期、帳單、等一下要...")
    print("🔍 帳單查詢功能：")
    print("   • 輸入「帳單查詢」查看所有帳單狀態")
    print("   • 輸入「緊急帳單」查看需要優先處理的帳單")
    print("   • 輸入「[銀行名稱]帳單查詢」查看特定銀行帳單")

if __name__ == '__main__':
    # 初始化應用
    initialize_app()
    
    # 啟動 Flask 應用
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port)
