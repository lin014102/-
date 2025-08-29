"""
main.py - LINE Todo Reminder Bot 主程式
v3.1 + Gemini AI + 信用卡帳單監控 + 自動帳單分析 完全模組化架構
"""
from flask import Flask, request, jsonify
import os
import re
import threading
import time
from datetime import timedelta

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

# 🆕 匯入信用卡帳單模組
from credit_card_manager import (
    handle_credit_card_command, is_credit_card_command, 
    is_credit_card_query, get_credit_card_summary,
    start_credit_card_monitor, get_credit_card_status
)

# 🆕 匯入 Gemini AI 模組
from gemini_analyzer import EnhancedMessageRouter

# 🆕 匯入帳單分析定時任務
from bill_scheduler import BillScheduler

# 初始化 Flask 應用
app = Flask(__name__)

# 建立模組實例
reminder_bot = ReminderBot(todo_manager)

# 🆕 使用增強版訊息路由器
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
        print("✅ 提醒機器人已啟動")
    
    def start_credit_card_monitor(self):
        """啟動信用卡帳單監控"""
        try:
            result = start_credit_card_monitor()
            self.services.append('credit_card_monitor')
            print("✅ 信用卡帳單監控已啟動")
        except Exception as e:
            print(f"⚠️ 信用卡帳單監控啟動失敗: {e}")
    
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
    <h1>LINE Todo Reminder Bot v3.1 + Gemini AI + 自動帳單分析</h1>
    <p>🇹🇼 當前台灣時間：{get_taiwan_time()}</p>
    <p>🚀 模組化架構，完全重構！</p>
    <p>💹 新增即時損益功能！</p>
    <p>🤖 整合 Gemini AI 智能對話！</p>
    <p>💳 新增信用卡帳單自動監控！</p>
    <p>📊 新增帳單自動分析與推播！</p>
    <p>📊 健康檢查：<a href="/health">/health</a></p>
    """

@app.route('/health')
def health():
    """健康檢查端點"""
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
    
    # 🆕 獲取 Gemini AI 狀態
    gemini_status = message_router.gemini_analyzer.enabled
    
    # 🆕 獲取信用卡帳單監控狀態
    try:
        credit_card_status = get_credit_card_status()
    except:
        credit_card_status = {'status': 'error', 'gmail_enabled': False, 'groq_enabled': False}
    
    # 🆕 獲取帳單分析定時任務狀態
    try:
        bill_scheduler_status = bg_services.bill_scheduler.get_status() if bg_services.bill_scheduler else {'scheduler_running': False}
    except:
        bill_scheduler_status = {'scheduler_running': False, 'error': 'not_initialized'}
    
    return jsonify({
        'status': 'healthy',
        'taiwan_time': get_taiwan_time(),
        'taiwan_time_hhmm': get_taiwan_time_hhmm(),
        'server_timezone': str(taiwan_now.tzinfo),
        'version': 'v3.1_modular_architecture_with_auto_bill_analysis',
        
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
            'credit_card_manager': {
                'status': credit_card_status.get('status', 'unknown'),
                'gmail_enabled': credit_card_status.get('gmail_enabled', False),
                'groq_enabled': credit_card_status.get('groq_enabled', False),
                'tesseract_enabled': credit_card_status.get('tesseract_enabled', False),
                'monitored_banks': credit_card_status.get('monitored_banks', []),
                'processed_bills_count': credit_card_status.get('processed_bills_count', 0),
                'last_check_time': credit_card_status.get('last_check_time'),
                'features': ['gmail_monitoring', 'auto_pdf_unlock', 'ocr_processing', 'llm_analysis']
            },
            'bill_scheduler': {
                'scheduler_running': bill_scheduler_status.get('scheduler_running', False),
                'analysis_time': bill_scheduler_status.get('analysis_time', '03:30'),
                'notification_time': bill_scheduler_status.get('notification_time', '15:15'),
                'last_analysis_date': bill_scheduler_status.get('last_analysis_date'),
                'last_notification_date': bill_scheduler_status.get('last_notification_date'),
                'notification_enabled': bill_scheduler_status.get('notification_enabled', False),
                'features': ['daily_pdf_analysis', 'google_vision_ocr', 'gemini_llm', 'line_notifications', 'google_sheets_sync']
            },
            'background_services': bg_services.services
        }
    })

@app.route('/webhook', methods=['POST'])
def webhook():
    """LINE Webhook 處理 - 統一入口"""
    try:
        data = request.get_json()
        
        for event in data.get('events', []):
            if event['type'] == 'message' and event['message']['type'] == 'text':
                reply_token = event['replyToken']
                message_text = event['message']['text']
                user_id = event['source']['userId']
                
                print(f"📨 用戶訊息: {message_text} - {get_taiwan_time()}")
                
                # 🆕 增強版訊息路由處理（包含信用卡帳單功能）
                reply_text = enhanced_message_router(message_text, user_id)
                
                # 回覆訊息
                reply_message(reply_token, reply_text)
        
        return 'OK', 200
    
    except Exception as e:
        print(f"❌ Webhook 處理錯誤: {e} - {get_taiwan_time()}")
        return 'OK', 200

def enhanced_message_router(message_text, user_id):
    """增強版訊息路由器 - 整合所有功能模組"""
    try:
        # 🆕 優先檢查信用卡帳單指令
        if is_credit_card_command(message_text) or is_credit_card_query(message_text):
            print(f"🔀 路由到信用卡帳單模組: {message_text}")
            return handle_credit_card_command(message_text)
        
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
            elif message_text.endswith('查詢'):
                account_name = message_text[:-2]
                return get_stock_summary(account_name)
        
        # 🆕 其他指令繼續使用原本的 Gemini AI 路由器
        else:
            return message_router.route_message(message_text, user_id)
    
    except Exception as e:
        print(f"❌ 訊息路由錯誤: {e}")
        return f"❌ 系統處理錯誤，請稍後再試\n🕒 {get_taiwan_time()}"

def initialize_app():
    """初始化應用程式"""
    print("🚀 LINE Todo Reminder Bot v3.1 + Gemini AI + 自動帳單分析 啟動中...")
    print(f"🇹🇼 台灣時間：{get_taiwan_time()}")
    
    # 啟動背景服務
    bg_services.start_keep_alive()
    bg_services.start_reminder_bot()
    bg_services.start_credit_card_monitor()  # 現有的信用卡帳單監控
    
    # 🆕 新增：啟動帳單分析定時任務
    try:
        bill_scheduler = BillScheduler(reminder_bot)
        bg_services.start_bill_scheduler(bill_scheduler)
    except Exception as e:
        print(f"⚠️ 帳單分析定時任務初始化失敗: {e}")
    
    print("=" * 60)
    print("📋 待辦事項管理：✅ 已載入")
    print("⏰ 提醒機器人：✅ 已啟動") 
    print("💰 股票記帳模組：✅ 已載入")
    print("💹 即時損益功能：✅ 已啟用")
    print("🤖 Gemini AI 模組：✅ 已整合")
    print("💳 信用卡帳單監控：✅ 已啟動")
    print("📊 帳單分析定時任務：✅ 已啟動")  # 🆕 新增這行
    print("🔧 模組化架構：✅ 完全重構")
    print("=" * 60)
    print("🎉 系統初始化完成！")

if __name__ == '__main__':
    # 初始化應用
    initialize_app()
    
    # 啟動 Flask 應用
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port)
