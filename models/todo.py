"""
待辦事項資料模型
"""

class TodoItem:
    """待辦事項模型"""
    
    def __init__(self, id, content, created_at, completed=False, 
                 has_date=False, target_date=None, date_string=None):
        self.id = id
        self.content = content
        self.created_at = created_at
        self.completed = completed
        self.has_date = has_date
        self.target_date = target_date
        self.date_string = date_string
    
    def to_dict(self):
        """轉換為字典"""
        return {
            'id': self.id,
            'content': self.content,
            'created_at': self.created_at,
            'completed': self.completed,
            'has_date': self.has_date,
            'target_date': self.target_date,
            'date_string': self.date_string
        }
