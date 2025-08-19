"""
LINE Todo Reminder Bot - 診斷版本
"""
import sys
import os
from flask import Flask, request, jsonify

# 添加當前目錄到 Python 路徑
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

app = Flask(__name__)

# 逐步測試模組載入
load_status = {}

# 測試基礎模組
try:
    from config.settings import settings
    load_status['config'] = 'success'
except ImportError as e:
    load_status['config'] = str(e)

try:
    from utils.date_utils import get_taiwan_time
    load_status['utils'] = 'success'
except ImportError as e:
    load_status['utils'] = str(e)
    # 備用方案
    from datetime import datetime
    def get_taiwan_time():
        return datetime.now().strftime('%Y/%m/%d %H:%M:%S')

try:
    from models.todo import TodoItem
    load_status['models'] = 'success'
except ImportError as e:
    load_status['models'] = str(e)

try:
    from controllers.todo_controller import todo_controller
    load_status['controllers'] = 'success'
    modules_loaded = True
except ImportError as e:
    load_status['controllers'] = str(e)
    modules_loaded = False

# 確保有基本設定
if 'config' != 'success':
    class Settings:
        APP_NAME = "LINE Todo Reminder Bot"
        VERSION = "2.0.0"
    settings = Settings()

@app.route('/')
def home():
    return f'{settings.APP_NAME} v{settings.VERSION} is running!'

@app.route('/health')
def health():
    return {
        'status': 'ok',
        'time': get_taiwan_time(),
        'modules': 'loaded' if modules_loaded else 'partially loaded',
        'load_status': load_status
    }

@app.route('/test-basic')
def test_basic():
    """測試基本功能"""
    if modules_loaded:
        # 測試新增待辦事項
        todo = todo_controller.add_todo("測試事項")
        return jsonify({
            'success': True,
            'todo': todo.to_dict(),
            'total_todos': len(todo_controller.todos)
        })
    else:
        return jsonify({'success': False, 'error': 'Modules not loaded'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port)
