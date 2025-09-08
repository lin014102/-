"""
main.py - LINE Todo Reminder Bot 主程式
v3.1 + Gemini AI + 自動帳單分析 完全模組化架構 + 帳單金額整合
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

# 🆕 暫時註解信用卡帳單模組 - 檔案已刪除
# from credit_card_manager import (
#     handle_credit_card_command, is_credit_card_command, 
#     is_credit_card_query, get_credit_card_summary,
#     start_credit_card_monitor, get_credit_card_status
# )

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
        """暫時停用信用卡帳單監控 - 模組已移除"""
        try:
            # result = start_credit_card_monitor()
            # self.services.append('credit_card_monitor')
            print("⚠️ 信用卡帳單監控已暫時停用 (模組不存在)")
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
    <p>📊 新增帳單自動分析與推播！</p>
    <p>💳 新增帳單金額智能提醒整合！</p>
    <p>📊 健康檢查：<a href="/health">/health</a></p>
    <h2>測試端點：</h2>
    <ul>
        <li><a href="/test/sheets-connection">測試 Google Sheets 連接</a></li>
        <li><a href="/test/bill-analysis">手動執行帳單分析</a></li>
        <li><a href="/test/notifications">手動執行推播</a></li>
        <li><a href="/test/bill-amounts">測試帳單金額查詢</a></li>
        <li><a href="/test/add-test-bill">新增測試帳單資料</a></li>
        <li><a href="/test/enhanced-reminder">測試增強版提醒</a></li>
        <li><a href="/test/bank-mapping">測試銀行名稱對應</a></li>
    </ul>
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
    
    # 🆕 信用卡帳單監控狀態 - 提供預設值
    credit_card_status = {
        'status': 'disabled', 
        'gmail_enabled': False, 
        'groq_enabled': False,
        'tesseract_enabled': False,
        'monitored_banks': [],
        'processed_bills_count': 0,
        'last_check_time': None,
        'note': '模組已暫時移除'
    }
    
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
        'version': 'v3.1_modular_architecture_with_bill_amount_integration',
        
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
            'credit_card_manager': credit_card_status,
            'bill_scheduler': {
                'scheduler_running': bill_scheduler_status.get('scheduler_running', False),
                'analysis_time': bill_scheduler_status.get('analysis_time', '03:30'),
                'notification_time': bill_scheduler_status.get('notification_time', '15:15'),
                'last_analysis_date': bill_scheduler_status.get('last_analysis_date'),
                'last_notification_date': bill_scheduler_status.get('last_notification_date'),
                'notification_enabled': bill_scheduler_status.get('notification_enabled', False),
                'features': ['daily_pdf_analysis', 'google_vision_ocr', 'gemini_llm', 'line_notifications', 'google_sheets_sync']
            },
            'bill_amount_integration': {
                'mongodb_enabled': reminder_bot.use_mongodb,
                'collection_ready': hasattr(reminder_bot, 'bill_amounts_collection') if reminder_bot.use_mongodb else True,
                'test_banks': ['永豐', '台新', '國泰', '星展', '匯豐', '玉山', '聯邦'],
                'features': ['bank_name_normalization', 'amount_storage', 'enhanced_reminders']
            },
            'background_services': bg_services.services
        }
    })

# ===== 原有測試端點 =====
@app.route('/test/bill-analysis')
def test_bill_analysis():
    """手動測試帳單分析功能"""
    try:
        if not bg_services.bill_scheduler:
            return jsonify({
                'success': False,
                'error': '帳單分析器未初始化'
            })
        
        # 手動觸發分析任務
        bg_services.bill_scheduler._run_daily_analysis()
        
        return jsonify({
            'success': True,
            'message': '手動分析任務已執行',
            'timestamp': get_taiwan_time()
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': get_taiwan_time()
        })

@app.route('/test/notifications')
def test_notifications():
    """手動測試推播功能"""
    try:
        if not bg_services.bill_scheduler:
            return jsonify({
                'success': False,
                'error': '帳單分析器未初始化'
            })
        
        # 手動觸發推播任務
        bg_services.bill_scheduler._run_daily_notifications()
        
        return jsonify({
            'success': True,
            'message': '手動推播任務已執行',
            'timestamp': get_taiwan_time()
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': get_taiwan_time()
        })

@app.route('/test/sheets-connection')
def test_sheets_connection():
    """測試 Google Sheets 連接"""
    try:
        if not bg_services.bill_scheduler:
            return jsonify({
                'success': False,
                'error': '帳單分析器未初始化'
            })
        
        sheets_handler = bg_services.bill_scheduler.sheets_handler
        
        # 測試讀取待處理檔案
        pending_files = sheets_handler.get_pending_files()
        failed_files = sheets_handler.get_failed_files()
        notification_files = sheets_handler.get_notification_pending_files()
        
        return jsonify({
            'success': True,
            'data': {
                'pending_files_count': len(pending_files),
                'failed_files_count': len(failed_files),
                'notification_pending_count': len(notification_files),
                'pending_files': pending_files[:3] if pending_files else [],  # 顯示前3筆
                'failed_files': failed_files[:3] if failed_files else [],
                'notification_files': notification_files[:3] if notification_files else []
            },
            'timestamp': get_taiwan_time()
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': get_taiwan_time()
        })

@app.route('/test/analyze-single/<file_id>')
def test_analyze_single(file_id):
    """測試分析單一檔案"""
    try:
        if not bg_services.bill_scheduler:
            return jsonify({
                'success': False,
                'error': '帳單分析器未初始化'
            })
        
        sheets_handler = bg_services.bill_scheduler.sheets_handler
        drive_handler = bg_services.bill_scheduler.drive_handler
        bill_analyzer = bg_services.bill_scheduler.bill_analyzer
        
        # 從 sheets 中找到對應的檔案資訊
        pending_files = sheets_handler.get_pending_files()
        target_file = None
        
        for file_info in pending_files:
            if file_info['file_id'] == file_id:
                target_file = file_info
                break
        
        if not target_file:
            return jsonify({
                'success': False,
                'error': f'找不到檔案 ID: {file_id}',
                'available_files': [f['file_id'] for f in pending_files[:5]]
            })
        
        # 下載檔案
        file_content = drive_handler.download_file(target_file['file_id'], target_file['filename'])
        
        if not file_content:
            return jsonify({
                'success': False,
                'error': '檔案下載失敗'
            })
        
        # 取得銀行設定
        bank_config = sheets_handler.get_bank_config_by_filename(target_file['filename'])
        
        if not bank_config:
            return jsonify({
                'success': False,
                'error': '找不到銀行設定'
            })
        
        # 執行分析
        analysis_result = bill_analyzer.analyze_pdf(
            file_content, 
            bank_config, 
            target_file['filename']
        )
        
        return jsonify({
            'success': True,
            'file_info': target_file,
            'bank_config': bank_config,
            'analysis_result': analysis_result,
            'timestamp': get_taiwan_time()
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': get_taiwan_time()
        })

@app.route('/test/vision-api')
def test_vision_api():
    """測試 Vision API 連接"""
    try:
        if not bg_services.bill_scheduler:
            return jsonify({'success': False, 'error': '帳單分析器未初始化'})
        
        # 檢查環境變數設定
        vision_api_key = os.getenv('GOOGLE_CLOUD_VISION_API_KEY')
        return jsonify({
            'success': True,
            'api_key_configured': vision_api_key is not None,
            'api_key_prefix': vision_api_key[:10] if vision_api_key else None,
            'timestamp': get_taiwan_time()
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ===== 新增：帳單金額整合測試端點 =====

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

@app.route('/test/add-test-bill')
def test_add_bill():
    """手動新增測試帳單金額"""
    try:
        # 新增一筆測試資料
        success = reminder_bot.update_bill_amount(
            bank_name="永豐銀行",
            amount="NT$15,234",
            due_date="2025/01/24",
            statement_date="2025/01/01"
        )
        
        if success:
            return jsonify({
                'success': True,
                'message': '測試帳單金額新增成功',
                'test_data': {
                    'bank': '永豐銀行',
                    'amount': 'NT$15,234',
                    'due_date': '2025/01/24'
                },
                'timestamp': get_taiwan_time()
            })
        else:
            return jsonify({
                'success': False,
                'error': '新增失敗',
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
        # 測試不同的待辦事項內容
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

@app.route('/test/bank-mapping')
def test_bank_mapping():
    """測試銀行名稱標準化"""
    try:
        test_banks = [
            "永豐銀行",
            "SinoPac", 
            "台新銀行",
            "TAISHIN",
            "星展銀行",
            "DBS Bank",
            "國泰世華",
            "CATHAY",
            "未知銀行"
        ]
        
        results = {}
        for bank in test_banks:
            normalized = reminder_bot._normalize_bank_name(bank)
            results[bank] = normalized
        
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
    """LINE Webhook 處理 - 統一入口"""
    try:
        data = request.get_json()
        
        for event in data.get('events', []):
            if event['type'] == 'message' and event['message']['type'] == 'text':
                reply_token = event['replyToken']
                message_text = event['message']['text']
                user_id = event['source']['userId']
                
                print(f"📨 用戶訊息: {message_text} - {get_taiwan_time()}")
                
                # 🆕 增強版訊息路由處理（信用卡功能暫時停用）
                reply_text = enhanced_message_router(message_text, user_id)
                
                # 回覆訊息
                reply_message(reply_token, reply_text)
        
        return 'OK', 200
    
    except Exception as e:
        print(f"❌ Webhook 處理錯誤: {e} - {get_taiwan_time()}")
        return 'OK', 200

def enhanced_message_router(message_text, user_id):
    """增強版訊息路由器 - 整合所有功能模組（信用卡功能暫時停用）"""
    try:
        # 🆕 信用卡帳單指令暫時停用
        # if is_credit_card_command(message_text) or is_credit_card_query(message_text):
        #     print(f"🔀 路由到信用卡帳單模組: {message_text}")
        #     return handle_credit_card_command(message_text)
        
        # 檢查股票相關指令
        if is_stock_command(message_text):
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
    print("🚀 LINE Todo Reminder Bot v3.1 + Gemini AI + 自動帳單分析 + 帳單金額整合 啟動中...")
    print(f"🇹🇼 台灣時間：{get_taiwan_time()}")
    
    # 啟動背景服務
    bg_services.start_keep_alive()
    bg_services.start_reminder_bot()
    bg_services.start_credit_card_monitor()  # 會顯示停用訊息
    
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
    print("💳 信用卡帳單監控：⚠️ 暫時停用")
    print("📊 帳單分析定時任務：✅ 已啟動")
    print("💰 帳單金額智能提醒：✅ 已整合")
    print("🔧 模組化架構：✅ 完全重構")
    print("=" * 60)
    print("🎉 系統初始化完成！")

if __name__ == '__main__':
    # 初始化應用
    initialize_app()
    
    # 啟動 Flask 應用
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port)
