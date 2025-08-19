"""
LINE Todo Reminder Bot - 完整模組化版本
"""
from flask import Flask, request, jsonify
from config.settings import settings
from utils.date_utils import get_taiwan_time
from controllers.todo_controller import todo_controller

app = Flask(__name__)

@app.route('/')
def home():
    return f'{settings.APP_NAME} v{settings.VERSION} is running!'

@app.route('/health')
def health():
    return {
        'status': 'ok',
        'time': get_taiwan_time(),
        'app': settings.APP_NAME,
        'todos_count': len(todo_controller.todos)
    }

@app.route('/todos', methods=['GET'])
def get_todos():
    """獲取所有待辦事項"""
    return jsonify(todo_controller.get_all_todos())

@app.route('/todos', methods=['POST'])
def add_todo():
    """新增待辦事項"""
    data = request.get_json()
    if not data or 'content' not in data:
        return jsonify({'error': '請提供待辦事項內容'}), 400
    
    todo = todo_controller.add_todo(data['content'])
    return jsonify(todo.to_dict())

@app.route('/test')
def test():
    """測試功能"""
    todo_controller.add_todo("測試待辦事項")
    return jsonify({
        'message': '測試成功！',
        'todos': todo_controller.get_all_todos()
    })

if __name__ == '__main__':
    app.run(host=settings.HOST, port=settings.PORT)
