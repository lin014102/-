"""
LINE Todo Reminder Bot - 完整版本
"""
import sys
import os
from flask import Flask, request, jsonify

# 添加當前目錄到 Python 路徑
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 導入模組
try:
    from config.settings import settings
    from utils.date_utils import get_taiwan_time
    from controllers.todo_controller import todo_controller
    from controllers.message_controller import message_controller
    from services.line_service import line_service
    modules_loaded = True
except ImportError as e:
    print(f"模組導入失敗: {e}")
    modules_loaded = False

app = Flask(__name__)

@app.route('/')
def home():
    if modules_loaded:
        return f'{settings.APP_NAME} v{settings.VERSION} is running!'
    else:
        return 'LINE Bot is running!'

@app.route('/health')
def health():
    return {
        'status': 'ok',
        'time': get_taiwan_time() if modules_loaded else 'N/A',
        'modules': 'loaded' if modules_loaded else 'not loaded',
        'todos_count': len(todo_controller.todos) if modules_loaded else 0
    }

@app.route('/webhook', methods=['POST'])
def webhook():
    """LINE Webhook 處理"""
    if not modules_loaded:
        return 'Modules not loaded', 500
    
    try:
        # 獲取請求資料
        body = request.get_data(as_text=True)
        signature = request.headers.get('X-Line-Signature', '')
        
        # 驗證簽名（開發模式下會跳過）
        if not line_service.verify_signature(body, signature):
            return 'Invalid signature', 400
        
        # 解析 JSON
        data = request.get_json()
        
        # 處理訊息事件
        for event in data.get('events', []):
            if event['type'] == 'message' and event['message']['type'] == 'text':
                reply_token = event['replyToken']
                message_text = event['message']['text']
                user_id = event['source']['userId']
                
                # 處理訊息
                message_controller.handle_text_message(reply_token, message_text, user_id)
        
        return 'OK'
    
    except Exception as e:
        print(f"Webhook 處理錯誤: {e}")
        return 'Internal Server Error', 500

@app.route('/test-message')
def test_message():
    """測試訊息處理"""
    if not modules_loaded:
        return jsonify({'error': 'Modules not loaded'})
    
    # 模擬處理訊息
    result = message_controller.handle_text_message('test_token', '查詢', 'test_user')
    return jsonify({'success': result})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port)
