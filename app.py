"""
LINE Todo Reminder Bot - 完整版本
"""
import sys
import os
from flask import Flask, request, jsonify

# 添加當前目錄到 Python 路徑
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

app = Flask(__name__)

# 載入模組
try:
    from config.settings import settings
    from utils.date_utils import get_taiwan_time
    from controllers.todo_controller import todo_controller
    from controllers.message_controller import message_controller
    from services.line_service import line_service
    
    # 更新 LINE 服務的 token
    line_service.channel_access_token = settings.CHANNEL_ACCESS_TOKEN
    line_service.channel_secret = settings.CHANNEL_SECRET
    
    modules_loaded = True
except ImportError as e:
    print(f"模組載入失敗: {e}")
    modules_loaded = False

@app.route('/')
def home():
    return f'{settings.APP_NAME} v{settings.VERSION} is running!'

@app.route('/health')
def health():
    return {
        'status': 'ok',
        'time': get_taiwan_time(),
        'modules': 'loaded' if modules_loaded else 'not loaded',
        'webhook_ready': modules_loaded
    }

@app.route('/webhook', methods=['POST'])
def webhook():
    """LINE Webhook 處理"""
    if not modules_loaded:
        print("模組未載入")
        return 'Internal Server Error', 500
    
    try:
        # 獲取請求資料
        body = request.get_data(as_text=True)
        signature = request.headers.get('X-Line-Signature', '')
        
        print(f"收到 Webhook 請求")
        
        # 驗證簽名
        if not line_service.verify_signature(body, signature):
            print("簽名驗證失敗")
            return 'Bad Request', 400
        
        # 解析 JSON
        data = request.get_json()
        print(f"解析資料: {data}")
        
        # 處理事件
        for event in data.get('events', []):
            print(f"處理事件: {event}")
            
            if event['type'] == 'message' and event['message']['type'] == 'text':
                reply_token = event['replyToken']
                message_text = event['message']['text']
                user_id = event['source']['userId']
                
                print(f"收到訊息: {message_text} from {user_id}")
                
                # 處理訊息
                success = message_controller.handle_text_message(reply_token, message_text, user_id)
                print(f"訊息處理結果: {success}")
        
        return 'OK', 200
    
    except Exception as e:
        print(f"Webhook 處理錯誤: {e}")
        return 'OK', 200  # 即使有錯誤也回傳 200

@app.route('/test-webhook')
def test_webhook():
    """測試 Webhook 功能"""
    if not modules_loaded:
        return jsonify({'error': 'Modules not loaded'})
    
    return jsonify({
        'webhook_ready': True,
        'line_token_configured': bool(settings.CHANNEL_ACCESS_TOKEN),
        'line_secret_configured': bool(settings.CHANNEL_SECRET)
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port)
