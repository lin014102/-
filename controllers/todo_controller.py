"""
待辦事項控制器
"""
from utils.date_utils import get_taiwan_time
from models.todo import TodoItem

class TodoController:
    """待辦事項控制器"""
    
    def __init__(self):
        self.todos = []  # 簡單的記憶體儲存
    
    def add_todo(self, content):
        """新增待辦事項"""
        todo = TodoItem(
            id=len(self.todos) + 1,
            content=content,
            created_at=get_taiwan_time()
        )
        self.todos.append(todo)
        return todo
    
    def get_all_todos(self):
        """獲取所有待辦事項"""
        return [todo.to_dict() for todo in self.todos]
    
    def delete_todo(self, todo_id):
        """刪除待辦事項"""
        self.todos = [todo for todo in self.todos if todo.id != todo_id]
        return True

# 創建全域實例
todo_controller = TodoController()
