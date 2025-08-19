"""
LINE Todo Reminder Bot - 模組化版本
"""
import sys
import os
from flask import Flask, request, jsonify

# 添加當前目錄到 Python 路徑
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 現在嘗試導入模組
try:
    from config.settings import settings
    from utils.date_utils import get_taiwan_time
    from controllers.todo_controller import todo_controller
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
        return 'LINE Bot is running (simplified mode)!'

@app.route('/health')
def health():
    if modules_loaded:
        return {
            'status': 'ok',
            'time': get_taiwan_time(),
            'modules': 'loaded'
        }
    else:
        return {
            'status': 'ok',
            'modules': 'not loaded'
        }

@app.route('/test')
def test():
    return jsonify({'message': 'Test successful!', 'modules_loaded': modules_loaded})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port)
