"""
todo_manager.py - 待辦事項管理模組
從 app.py 拆分出來
"""
import re
from datetime import datetime
from utils.time_utils import get_taiwan_time, get_taiwan_datetime

class TodoManager:
    """待辦事項管理器"""
    
    def __init__(self):
        """初始化待辦事項資料"""
        self.todos = []
        self.monthly_todos = []
    
    def parse_date(self, text):
        """解析日期格式"""
        taiwan_now = get_taiwan_datetime()
        current_year = taiwan_now.year
        
        patterns = [
            (r'(\d{1,2})號(.+)', 'day_only'),
            (r'(\d{1,2})\/(\d{1,2})號?(.+)', 'month_day'),
            (r'(.+?)(\d{1,2})號', 'content_day'),
            (r'(.+?)(\d{1,2})\/(\d{1,2})號?', 'content_month_day')
        ]
        
        for pattern, pattern_type in patterns:
            match = re.search(pattern, text)
            if match:
                if pattern_type == 'day_only':
                    day = int(match.group(1))
                    content = match.group(2).strip()
                    if 1 <= day <= 31 and content:
                        month = taiwan_now.month
                        target_date = taiwan_now.replace(year=current_year, month=month, day=day,
                                                       hour=0, minute=0, second=0, microsecond=0)
                        if target_date < taiwan_now:
                            if month == 12:
                                target_date = target_date.replace(year=current_year + 1, month=1)
                            else:
                                target_date = target_date.replace(month=month + 1)
                        
                        return {
                            "has_date": True,
                            "date": target_date,
                            "content": content,
                            "date_string": f"{month}/{day}",
                            "day_only": day
                        }
                        
                elif pattern_type == 'month_day':
                    month = int(match.group(1))
                    day = int(match.group(2))
                    content = match.group(3).strip()
                    
                    if 1 <= month <= 12 and 1 <= day <= 31 and content:
                        target_date = taiwan_now.replace(year=current_year, month=month, day=day,
                                                       hour=0, minute=0, second=0, microsecond=0)
                        if target_date < taiwan_now:
                            target_date = target_date.replace(year=current_year + 1)
                        
                        return {
                            "has_date": True,
                            "date": target_date,
                            "content": content,
                            "date_string": f"{month}/{day}"
                        }
                        
                elif pattern_type == 'content_day':
                    content = match.group(1).strip()
                    day = int(match.group(2))
                    
                    if 1 <= day <= 31 and content:
                        month = taiwan_now.month
                        target_date = taiwan_now.replace(year=current_year, month=month, day=day,
                                                       hour=0, minute=0, second=0, microsecond=0)
                        if target
