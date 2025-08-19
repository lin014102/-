"""
LINE Todo Reminder Bot - 模組化版本
"""
from flask import Flask, request, jsonify
import os

# 導入我們建立的模組
from config.settings import settings
from utils.date_utils import get_taiwan_time, get_taiwan_time_hhmm
from models.todo import TodoItem

app = Flask(__name__)

# 簡單的記憶體儲存（之後會改用資料庫）
todos = []

@app.route('/')
def home():
    return f'{settings.APP_NAME} v{settings.VERSION} is running!'

@app.route('/health')
def health():
    return {
        'status': 'ok',
        'time': get_taiwan_time(),
        'app': settings.APP_NAME
    }

@app.route('/test-todo', methods=['POST'])
def test_todo():
    """測試新增待辦事項"""
    todo = TodoItem(
        id=len(todos) + 1,
        content="測試事項",
        created_at=get_taiwan_time()
    )
    todos.append(todo)
    return jsonify(todo.to_dict())

@app.route('/todos')
def get_todos():
    """查看所有待辦事項"""
    return jsonify([todo.to_dict() for todo in todos])

if __name__ == '__main__':
    app.run(host=settings.HOST, port=settings.PORT, debug=settings.DEBUG)
