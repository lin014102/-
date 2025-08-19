"""
LINE Todo Reminder Bot - 簡化版本
"""
from flask import Flask, request, jsonify
import os
from datetime import datetime

app = Flask(__name__)

# 簡單的設定
APP_NAME = "LINE Todo Reminder Bot"
VERSION = "2.0.0"
PORT = int(os.getenv('PORT', 8000))

# 簡單的記憶體儲存
todos = []

def get_taiwan_time():
    """獲取台灣時間字串"""
    return datetime.now().strftime('%Y/%m/%d %H:%M:%S')

@app.route('/')
def home():
    return f'{APP_NAME} v{VERSION} is running!'

@app.route('/health')
def health():
    return {
        'status': 'ok',
        'time': get_taiwan_time(),
        'app': APP_NAME
    }

@app.route('/test-todo', methods=['POST'])
def test_todo():
    """測試新增待辦事項"""
    todo = {
        'id': len(todos) + 1,
        'content': "測試事項",
        'created_at': get_taiwan_time()
    }
    todos.append(todo)
    return jsonify(todo)

@app.route('/todos')
def get_todos():
    """查看所有待辦事項"""
    return jsonify(todos)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORT)
