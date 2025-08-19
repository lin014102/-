"""
LINE Todo Reminder Bot - 修正版本
"""
import sys
import os
from flask import Flask, request, jsonify

# 添加當前目錄到 Python 路徑
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

app = Flask(__name__)

# 嘗試載入模組並提供詳細錯誤信息
modules_loaded = False
error_message = ""

try:
    from config.settings import settings
    print("✅ config.settings 載入成功")
except ImportError as e:
    print(f"❌ config.settings 載入失敗: {e}")
    error_message += f"config.settings: {e}; "

try:
    from utils.date_utils import get_taiwan_time
    print("✅ utils.date_utils 載入成功")
except ImportError as e:
    print(f"❌ utils.date_utils 載入失敗: {e}")
    error_message += f"utils.date_utils: {e}; "

# 如果基本模組載入失敗，使用備用方案
if error_message:
    print(f"使用備用方案，錯誤: {error_message}")
    class Settings:
        APP_NAME = "LINE Todo Reminder Bot"
        VERSION = "2.0.0"
    settings = Settings()
    
    from datetime import datetime
    def get_taiwan_time():
        return datetime.now().strftime('%Y/%m/%d %H:%M:%S')

# 嘗試載入其他模組
try:
    from controllers.todo_controller import todo_controller
    from controllers.message_controller import message_controller
    from services.line_service import line_service
    modules_loaded = True
    print("✅ 所有模組載入成功")
except ImportError as e:
    print(f"❌ 控制器模組載入失敗: {e}")
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
        'error': error_message if error_message else None,
        'todos_count': len(todo_controller.todos) if modules_loaded else 0
    }

@app.route('/debug')
def debug():
    """除錯信息"""
    return {
        'modules_loaded': modules_loaded,
        'error_message': error_message,
        'python_path': sys.path[:3],
        'current_dir': current_dir,
        'files_in_dir': os.listdir(current_dir)
    }

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port)
