"""
main.py - LINE Todo Reminder Bot 主程式 (完整整合版)
v3.3 + 智能帳單提醒整合 + Gemini AI + 自動帳單分析 + 生理期追蹤 + 下次生理期預測
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

# 匯入 Gemini AI 模組
from gemini_analyzer import EnhancedMessageRouter

# 匯入帳單分析定時任務
from bill_scheduler import BillScheduler

# 初始化 Flask 應用
app = Flask(__name__)

# 建立模組實例
reminder_bot = ReminderBot(todo_manager)

# 使用增強版訊息路由器
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
    <h1>LINE Todo Reminder Bot v3.3 - 智能帳單提醒完整整合版</h1>
    <p>🇹🇼 當前台灣時間：{get_taiwan_time()}</p>
    <p>🚀 完整模組化架構 + 智能帳單提醒整合！</p>
    <p>💹 即時損益功能！</p>
    <p>🤖 Gemini AI 智能對話！</p>
    <p>📊 帳單自動分析與智能提醒整合！</p>
    <p>💳 繳費截止前自動提醒具體金額！</p>
    <p>🩸 生理期智能追蹤提醒！</p>
    <p>📅 下次生理期預測查詢！</p>
    <p>📊 健康檢查：<a href="/health">/health</a></p>
    
    <h2>🆕 完整整合功能測試：</h2>
    <ul>
        <li><a href="/test/bill-sync-integration"><strong>📊 測試帳單同步整合</strong></a> - 驗證帳單分析結果自動同步到提醒系統</li>
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
    """健康檢查端點 - 更新版"""
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
        'version': 'v3.3_smart_bill_reminder_integration',
        
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
                'features': ['natural_language_understanding', 'smart_suggestions', 'intent_classification']
            },
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

# ===== 測試端點 =====

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
    """LINE Webhook 處理 - 統一入口（包含智能帳單提醒整合）"""
    try:
        data = request.get_json()
        
        for event in data.get('events', []):
            if event['type'] == 'message' and event['message']['type'] == 'text':
                reply_token = event['replyToken']
                message_text = event['message']['text']
                user_id = event['source']['userId']
                
                print(f"📨 用戶訊息: {message_text} - {get_taiwan_time()}")
                
                # 🔥 在這裡直接攔截帳單查詢，不經過路由器
                bill_keywords = ['帳單查詢', '帳單總覽', '卡費查詢', '緊急帳單', '逾期帳單', '帳單狀態']
                bank_bill_patterns = ['永豐帳單查詢', '台新帳單查詢', '國泰帳單查詢', '星展帳單查詢', '匯豐帳單查詢', '玉山帳單查詢', '聯邦帳單查詢']
                
                if (any(keyword in message_text for keyword in bill_keywords) or 
                    any(pattern in message_text for pattern in bank_bill_patterns)):
                    print(f"🔀 路由到帳單查詢: {message_text}")
                    reply_text = handle_bill_query_command(message_text, user_id)
                else:
                    # 其他訊息才使用路由器
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
        # 緊急帳單查詢
        if any(keyword in message_text for keyword in ['緊急帳單', '逾期帳單', '即將到期']):
            urgent_bills = reminder_bot.check_urgent_bill_payments(user_id)
            if urgent_bills:
                bill_reminder = reminder_bot.format_bill_reminders(urgent_bills)
                return f"📊 緊急帳單狀態\n\n{bill_reminder}\n\n🕒 查詢時間: {get_taiwan_time_hhmm()}"
            else:
                return f"✅ 目前沒有緊急帳單\n💡 所有帳單都在安全期限內\n🕒 查詢時間: {get_taiwan_time_hhmm()}"
        
        # 帳單總覽查詢
        elif any(keyword in message_text for keyword in ['帳單總覽', '帳單查詢', '卡費查詢', '帳單狀態']):
            banks = ['永豐', '台新', '國泰', '星展', '匯豐', '玉山', '聯邦']
            urgent_bills = reminder_bot.check_urgent_bill_payments(user_id)
            
            message = "💳 帳單總覽\n\n"
            
            # 顯示緊急帳單提醒
            if urgent_bills:
                bill_reminder = reminder_bot.format_bill_reminders(urgent_bills)
                message += f"{bill_reminder}\n\n"
                message += f"{'='*20}\n\n"
            
            # 顯示所有銀行帳單狀態
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
                        
                        # 格式化日期顯示
                        if '/' in bill_info['due_date'] and len(bill_info['due_date'].split('/')) == 3:
                            year, month, day = bill_info['due_date'].split('/')
                            formatted_date = f"{int(month)}/{int(day)}"
                        else:
                            formatted_date = bill_info['due_date']
                        
                        # 狀態顯示
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
        
        # 特定銀行帳單查詢
        else:
            # 檢查是否指定特定銀行
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
                # 通用帳單查詢幫助
                return """💳 帳單查詢指令說明

🔍 可用查詢指令：
• 帳單查詢 / 帳單總覽 - 查看所有銀行帳單
• 緊急帳單 - 查看即將到期或逾期的帳單
• [銀行名稱]帳單查詢 - 查看特定銀行帳單

🏦 支援銀行：
永豐、台新、國泰、星展、匯豐、玉山、聯邦

💡 範例：
• 「帳單查詢」- 查看所有帳單狀態
• 「緊急帳單」- 查看需要優先處理的帳單
• 「永豐帳單查詢」- 查看永豐銀行帳單"""
    
    except Exception as e:
        print(f"❌ 處理帳單查詢指令失敗: {e}")
        return f"❌ 查詢失敗，請稍後再試\n🕒 {get_taiwan_time()}"

def is_todo_query(message_text):
    """檢查是否為待辦事項相關查詢"""
    todo_keywords = [
        '查詢', '清單', '列表', '待辦', '任務', 'todo', 
        '提醒', '事項', '計畫', '安排'
    ]
    
    if message_text.strip() == '查詢':
        return True
    
    if any(keyword in message_text for keyword in todo_keywords):
        # 排除股票相關查詢
        stock_exclusions = [
            '股票', '股價', '損益', '帳戶', '交易', '成本',
            '總覽', '即時', '代號'
        ]
        
        # 排除帳單相關查詢
        bill_exclusions = [
            '帳單', '卡費', '繳費', '永豐', '台新', '國泰', 
            '星展', '匯豐', '玉山', '聯邦', '緊急帳單', '逾期帳單'
        ]
        
        if not any(stock_word in message_text for stock_word in stock_exclusions) and \
           not any(bill_word in message_text for bill_word in bill_exclusions):
            return True
    
    return False

def enhanced_message_router(message_text, user_id):
    """增強版訊息路由器 - 整合所有功能模組（包含智能帳單提醒）"""
    try:
        # 生理期追蹤指令檢查（包含下次預測）
        if is_period_command(message_text):
            print(f"🔀 路由到生理期追蹤模組: {message_text}")
            return handle_period_command(message_text, user_id)
        
        # 優先檢查待辦事項相關的查詢
        elif is_todo_query(message_text):
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
        
        # 其他指令使用原本的 Gemini AI 路由器
        else:
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
    """初始化應用程式（完整整合版）"""
    print("🚀 LINE Todo Reminder Bot v3.3 - 智能帳單提醒完整整合版 啟動中...")
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
    print("📊 帳單分析定時任務：✅ 已啟動")
    print("💳 智能帳單提醒整合：✅ 已完成 - 帳單分析結果自動同步到提醒系統")
    print("🔔 繳費截止智能提醒：✅ 已啟用 - 顯示具體金額和緊急程度")
    print("📈 增強版待辦顯示：✅ 已啟用 - 卡費待辦自動顯示金額和截止日")
    print("🩸 生理期智能追蹤：✅ 已整合")
    print("📅 下次生理期預測：✅ 新功能已加入")
    print("🔧 完整模組化架構：✅ 完全重構並整合")
    print("=" * 70)
    print("🎉 智能帳單提醒系統初始化完成！")
    print("💡 特色功能：")
    print("   • 帳單分析完成後自動同步金額到提醒系統")
    print("   • 每日提醒自動檢查緊急帳單並優先顯示")
    print("   • 卡費相關待辦事項自動顯示具體金額和截止日期")
    print("   • 根據緊急程度智能標記（逾期/今日截止/即將到期）")
    print("   • 整合生理期追蹤，提供全方位健康提醒")
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
