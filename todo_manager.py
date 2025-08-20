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
                        
                elif pattern_type == 'content_month_day':
                    content = match.group(1).strip()
                    month = int(match.group(2))
                    day = int(match.group(3))
                    
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
        
        return {"has_date": False, "content": text}
    
    def add_todo(self, todo_text):
        """新增待辦事項"""
        if not todo_text:
            return "❌ 請輸入要新增的事項內容"
        
        parsed = self.parse_date(todo_text)
        todo_item = {
            'id': len(self.todos) + 1,
            'content': parsed['content'],
            'created_at': get_taiwan_time(),
            'completed': False,
            'has_date': parsed.get('has_date', False),
            'target_date': parsed.get('date').strftime('%Y/%m/%d') if parsed.get('date') else None,
            'date_string': parsed.get('date_string')
        }
        self.todos.append(todo_item)
        
        if parsed.get('has_date'):
            return f"✅ 已新增待辦事項：「{parsed['content']}」\n📅 目標日期：{parsed['date'].strftime('%Y/%m/%d')}\n📋 目前共有 {len(self.todos)} 項\n🇹🇼 台灣時間建立"
        else:
            return f"✅ 已新增待辦事項：「{parsed['content']}」\n📋 目前共有 {len(self.todos)} 項\n🇹🇼 台灣時間建立"
    
    def get_todo_list(self):
        """查詢待辦事項清單"""
        if self.todos:
            reply_text = f"📋 待辦事項清單 ({len(self.todos)} 項)：\n\n"
            for i, todo in enumerate(self.todos, 1):
                status = "✅" if todo.get('completed') else "⭕"
                date_info = f" 📅{todo.get('target_date', '')}" if todo.get('has_date') else ""
                reply_text += f"{i}. {status} {todo['content']}{date_info}\n"
            reply_text += "\n💡 輸入「幫助」查看更多功能"
            return reply_text
        else:
            return "📝 目前沒有待辦事項"
    
    def delete_todo(self, index_str):
        """刪除待辦事項"""
        try:
            index = int(index_str.strip()) - 1
            if 0 <= index < len(self.todos):
                deleted_todo = self.todos.pop(index)
                return f"🗑️ 已刪除：「{deleted_todo['content']}」"
            else:
                return "❌ 編號不正確"
        except:
            return "❌ 請輸入正確編號"
    
    def complete_todo(self, index_str):
        """完成待辦事項"""
        try:
            index = int(index_str.strip()) - 1
            if 0 <= index < len(self.todos):
                self.todos[index]['completed'] = True
                return f"🎉 已完成：「{self.todos[index]['content']}」"
            else:
                return "❌ 編號不正確"
        except:
            return "❌ 請輸入正確編號"
    
    def add_monthly_todo(self, todo_text):
        """新增每月固定事項"""
        if not todo_text:
            return "❌ 請輸入要新增的每月事項內容\n💡 例如：每月新增 24號繳水電卡費"
        
        parsed = self.parse_date(todo_text)
        
        if parsed.get('has_date'):
            if parsed.get('day_only'):
                day = parsed['day_only']
                date_display = f"{day}號"
            elif parsed.get('date_string'):
                try:
                    day = int(parsed['date_string'].split('/')[1])
                    date_display = f"{day}號"
                except:
                    day = 1
                    date_display = "1號"
            else:
                day = 1
                date_display = "1號"
        else:
            day = 1
            date_display = "1號"
        
        monthly_item = {
            'id': len(self.monthly_todos) + 1,
            'content': parsed['content'],
            'created_at': get_taiwan_time(),
            'has_date': parsed.get('has_date', False),
            'date_string': parsed.get('date_string'),
            'day': day,
            'date_display': date_display
        }
        self.monthly_todos.append(monthly_item)
        
        return f"🔄 已新增每月事項：「{parsed['content']}」\n📅 每月 {date_display} 提醒\n📋 目前共有 {len(self.monthly_todos)} 項每月事項\n💡 會在前一天預告 + 當天提醒"
    
    def get_monthly_list(self):
        """查詢每月固定事項清單"""
        if self.monthly_todos:
            # 確保每個項目都有 date_display
            for item in self.monthly_todos:
                if not item.get('date_display'):
                    if item.get('has_date') and item.get('date_string'):
                        try:
                            day = int(item['date_string'].split('/')[1])
                            item['date_display'] = f"{day}號"
                        except:
                            item['date_display'] = f"{item.get('day', 1)}號"
                    else:
                        item['date_display'] = f"{item.get('day', 1)}號"
            
            reply_text = f"🔄 每月固定事項清單 ({len(self.monthly_todos)} 項)：\n\n"
            for i, item in enumerate(self.monthly_todos, 1):
                date_display = item.get('date_display', f"{item.get('day', 1)}號")
                reply_text += f"{i}. 📅 每月 {date_display} - {item['content']}\n"
            reply_text += f"\n💡 這些事項會在前一天晚上預告，當天早上自動加入待辦清單"
            return reply_text
        else:
            return "📝 目前沒有每月固定事項\n💡 輸入「每月新增 5號繳卡費」來新增"
    
    def add_monthly_todo_to_daily(self, taiwan_now):
        """將每月事項加入當日待辦清單"""
        if not self.monthly_todos:
            return []
        
        current_day = taiwan_now.day
        added_items = []
        
        monthly_items_today = []
        for item in self.monthly_todos:
            target_day = item.get('day', 1)
            if target_day == current_day:
                monthly_items_today.append(item)
        
        if monthly_items_today:
            for item in monthly_items_today:
                # 檢查是否已經存在
                already_exists = any(
                    todo['content'] == item['content'] and 
                    todo.get('created_at', '').startswith(taiwan_now.strftime('%Y/%m/%d'))
                    for todo in self.todos
                )
                
                if not already_exists:
                    todo_item = {
                        'id': len(self.todos) + 1,
                        'content': item['content'],
                        'created_at': get_taiwan_time(),
                        'completed': False,
                        'has_date': True,
                        'target_date': taiwan_now.strftime('%Y/%m/%d'),
                        'date_string': f"{taiwan_now.month}/{taiwan_now.day}",
                        'from_monthly': True
                    }
                    self.todos.append(todo_item)
                    added_items.append(item['content'])
        
        return added_items
    
    def get_monthly_items_for_day(self, day):
        """獲取指定日期的每月事項"""
        monthly_items = []
        for item in self.monthly_todos:
            target_day = item.get('day', 1)
            if target_day == day:
                monthly_items.append(item)
        return monthly_items
    
    def get_todo_count(self):
        """獲取待辦事項數量"""
        return len(self.todos)
    
    def get_monthly_count(self):
        """獲取每月事項數量"""
        return len(self.monthly_todos)
    
    def get_pending_todos(self):
        """獲取未完成的待辦事項"""
        return [todo for todo in self.todos if not todo.get('completed', False)]
    
    def get_completed_todos(self):
        """獲取已完成的待辦事項"""
        return [todo for todo in self.todos if todo.get('completed', False)]


# 建立全域實例，供其他模組使用
todo_manager = TodoManager()
