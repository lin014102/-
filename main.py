"""
todo_manager.py - 待辦事項管理模組 (MongoDB Atlas 版本)
從 app.py 拆分出來
"""
import re
import os
from datetime import datetime
from pymongo import MongoClient
from utils.time_utils import get_taiwan_time, get_taiwan_datetime

class TodoManager:
    """待辦事項管理器 (MongoDB Atlas 版本)"""
    
    def __init__(self):
        """初始化 MongoDB 連接"""
        # 從環境變數取得 MongoDB URI
        mongodb_uri = os.getenv('MONGODB_URI')
        if not mongodb_uri:
            print("⚠️ 警告：找不到 MONGODB_URI 環境變數，使用記憶體模式")
            self._todos = []
            self._monthly_todos = []
            self.use_mongodb = False
            return
        
        try:
            # 連接到 MongoDB Atlas
            self.client = MongoClient(mongodb_uri)
            
            # 指定資料庫名稱 (如果 URI 中沒有預設資料庫)
            try:
                self.db = self.client.get_default_database()
            except:
                # 如果沒有預設資料庫，使用 'reminderbot' 作為資料庫名稱
                self.db = self.client.reminderbot
            
            self.todos_collection = self.db.todos
            self.monthly_collection = self.db.monthly_todos
            self.use_mongodb = True
            print("✅ 成功連接到 MongoDB Atlas")
            
            # 測試連接
            self.client.admin.command('ping')
            print("✅ MongoDB 連接測試成功")
            
        except Exception as e:
            print(f"❌ MongoDB 連接失敗: {e}")
            print("⚠️ 使用記憶體模式")
            self._todos = []
            self._monthly_todos = []
            self.use_mongodb = False
    
    def _get_todos(self):
        """獲取所有待辦事項"""
        if self.use_mongodb:
            return list(self.todos_collection.find({}))
        else:
            return self._todos
    
    def _get_monthly_todos(self):
        """獲取所有每月事項"""
        if self.use_mongodb:
            return list(self.monthly_collection.find({}))
        else:
            return self._monthly_todos
    
    def _add_todo(self, todo_item):
        """新增待辦事項到資料庫"""
        if self.use_mongodb:
            result = self.todos_collection.insert_one(todo_item)
            todo_item['_id'] = result.inserted_id
            return todo_item
        else:
            self._todos.append(todo_item)
            return todo_item
    
    def _add_monthly_todo(self, monthly_item):
        """新增每月事項到資料庫"""
        if self.use_mongodb:
            result = self.monthly_collection.insert_one(monthly_item)
            monthly_item['_id'] = result.inserted_id
            return monthly_item
        else:
            self._monthly_todos.append(monthly_item)
            return monthly_item
    
    def _update_todo(self, todo_id, update_data):
        """更新待辦事項"""
        if self.use_mongodb:
            self.todos_collection.update_one(
                {'id': todo_id}, 
                {'$set': update_data}
            )
        else:
            for todo in self._todos:
                if todo['id'] == todo_id:
                    todo.update(update_data)
                    break
    
    def _delete_todo(self, todo_id):
        """刪除待辦事項"""
        if self.use_mongodb:
            self.todos_collection.delete_one({'id': todo_id})
        else:
            self._todos = [todo for todo in self._todos if todo['id'] != todo_id]
    
    def _get_next_todo_id(self):
        """獲取下一個待辦事項 ID"""
        todos = self._get_todos()
        if not todos:
            return 1
        return max(todo['id'] for todo in todos) + 1
    
    def _get_next_monthly_id(self):
        """獲取下一個每月事項 ID"""
        monthly_todos = self._get_monthly_todos()
        if not monthly_todos:
            return 1
        return max(item['id'] for item in monthly_todos) + 1
    
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
            'id': self._get_next_todo_id(),
            'content': parsed['content'],
            'created_at': get_taiwan_time(),
            'completed': False,
            'has_date': parsed.get('has_date', False),
            'target_date': parsed.get('date').strftime('%Y/%m/%d') if parsed.get('date') else None,
            'date_string': parsed.get('date_string')
        }
        
        self._add_todo(todo_item)
        todos_count = len(self._get_todos())
        
        if parsed.get('has_date'):
            return f"✅ 已新增待辦事項：「{parsed['content']}」\n📅 目標日期：{parsed['date'].strftime('%Y/%m/%d')}\n📋 目前共有 {todos_count} 項\n🇹🇼 台灣時間建立\n💾 已同步到雲端"
        else:
            return f"✅ 已新增待辦事項：「{parsed['content']}」\n📋 目前共有 {todos_count} 項\n🇹🇼 台灣時間建立\n💾 已同步到雲端"
    
    def get_todo_list(self):
        """查詢待辦事項清單"""
        todos = self._get_todos()
        if todos:
            reply_text = f"📋 待辦事項清單 ({len(todos)} 項)：\n\n"
            for i, todo in enumerate(todos, 1):
                status = "✅" if todo.get('completed') else "⭕"
                date_info = f" 📅{todo.get('target_date', '')}" if todo.get('has_date') else ""
                reply_text += f"{i}. {status} {todo['content']}{date_info}\n"
            reply_text += "\n💡 輸入「幫助」查看更多功能"
            if self.use_mongodb:
                reply_text += "\n💾 資料已同步到雲端"
            return reply_text
        else:
            return "📝 目前沒有待辦事項"
    
    def delete_todo(self, index_str):
        """刪除待辦事項"""
        try:
            todos = self._get_todos()
            index = int(index_str.strip()) - 1
            if 0 <= index < len(todos):
                deleted_todo = todos[index]
                self._delete_todo(deleted_todo['id'])
                return f"🗑️ 已刪除：「{deleted_todo['content']}」\n💾 已同步到雲端"
            else:
                return "❌ 編號不正確"
        except:
            return "❌ 請輸入正確編號"
    
    def complete_todo(self, index_str):
        """完成待辦事項"""
        try:
            todos = self._get_todos()
            index = int(index_str.strip()) - 1
            if 0 <= index < len(todos):
                todo = todos[index]
                self._update_todo(todo['id'], {'completed': True})
                return f"🎉 已完成：「{todo['content']}」\n💾 已同步到雲端"
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
            'id': self._get_next_monthly_id(),
            'content': parsed['content'],
            'created_at': get_taiwan_time(),
            'has_date': parsed.get('has_date', False),
            'date_string': parsed.get('date_string'),
            'day': day,
            'date_display': date_display
        }
        
        self._add_monthly_todo(monthly_item)
        monthly_count = len(self._get_monthly_todos())
        
        return f"🔄 已新增每月事項：「{parsed['content']}」\n📅 每月 {date_display} 提醒\n📋 目前共有 {monthly_count} 項每月事項\n💡 會在前一天預告 + 當天提醒\n💾 已同步到雲端"
    
    def delete_monthly_todo(self, index_str):
        """刪除每月固定事項"""
        try:
            monthly_todos = self._get_monthly_todos()
            index = int(index_str.strip()) - 1
            if 0 <= index < len(monthly_todos):
                deleted_item = monthly_todos[index]
                
                # 從資料庫刪除
                if self.use_mongodb:
                    self.monthly_collection.delete_one({'id': deleted_item['id']})
                else:
                    self._monthly_todos = [item for item in self._monthly_todos if item['id'] != deleted_item['id']]
                
                date_display = deleted_item.get('date_display', f"{deleted_item.get('day', 1)}號")
                status_msg = "💾 已同步到雲端" if self.use_mongodb else ""
                return f"🗑️ 已刪除每月事項：「{deleted_item['content']}」\n📅 原本每月 {date_display} 提醒\n{status_msg}"
            else:
                return "❌ 編號不正確"
        except:
            return "❌ 請輸入正確編號"

    def get_monthly_list(self):
        """查詢每月固定事項清單"""
        monthly_todos = self._get_monthly_todos()
        if monthly_todos:
            # 確保每個項目都有 date_display
            for item in monthly_todos:
                if not item.get('date_display'):
                    if item.get('has_date') and item.get('date_string'):
                        try:
                            day = int(item['date_string'].split('/')[1])
                            item['date_display'] = f"{day}號"
                        except:
                            item['date_display'] = f"{item.get('day', 1)}號"
                    else:
                        item['date_display'] = f"{item.get('day', 1)}號"
            
            reply_text = f"🔄 每月固定事項清單 ({len(monthly_todos)} 項)：\n\n"
            for i, item in enumerate(monthly_todos, 1):
                date_display = item.get('date_display', f"{item.get('day', 1)}號")
                reply_text += f"{i}. 📅 每月 {date_display} - {item['content']}\n"
            reply_text += f"\n💡 這些事項會在前一天晚上預告，當天早上自動加入待辦清單"
            if self.use_mongodb:
                reply_text += "\n💾 資料已同步到雲端"
            return reply_text
        else:
            return "📝 目前沒有每月固定事項\n💡 輸入「每月新增 5號繳卡費」來新增"
    
    def add_monthly_todo_to_daily(self, taiwan_now):
        """將每月事項加入當日待辦清單"""
        monthly_todos = self._get_monthly_todos()
        if not monthly_todos:
            return []
        
        current_day = taiwan_now.day
        added_items = []
        
        monthly_items_today = []
        for item in monthly_todos:
            target_day = item.get('day', 1)
            if target_day == current_day:
                monthly_items_today.append(item)
        
        if monthly_items_today:
            todos = self._get_todos()
            for item in monthly_items_today:
                # 檢查是否已經存在
                already_exists = any(
                    todo['content'] == item['content'] and 
                    todo.get('created_at', '').startswith(taiwan_now.strftime('%Y/%m/%d'))
                    for todo in todos
                )
                
                if not already_exists:
                    todo_item = {
                        'id': self._get_next_todo_id(),
                        'content': item['content'],
                        'created_at': get_taiwan_time(),
                        'completed': False,
                        'has_date': True,
                        'target_date': taiwan_now.strftime('%Y/%m/%d'),
                        'date_string': f"{taiwan_now.month}/{taiwan_now.day}",
                        'from_monthly': True
                    }
                    self._add_todo(todo_item)
                    added_items.append(item['content'])
        
        return added_items
    
    def get_monthly_items_for_day(self, day):
        """獲取指定日期的每月事項"""
        monthly_todos = self._get_monthly_todos()
        monthly_items = []
        for item in monthly_todos:
            target_day = item.get('day', 1)
            if target_day == day:
                monthly_items.append(item)
        return monthly_items
    
    # 新增：用於支援有日期待辦事項提醒的方法
    def get_todos_by_date(self, target_date_str):
        """根據日期獲取待辦事項"""
        todos = self._get_todos()
        todos_for_date = []
        for todo in todos:
            if todo.get('has_date') and todo.get('target_date') == target_date_str:
                todos_for_date.append(todo)
        return todos_for_date
    
    def get_pending_todos_by_date(self, target_date_str):
        """根據日期獲取未完成的待辦事項"""
        todos = self._get_todos()
        pending_todos = []
        for todo in todos:
            if (todo.get('has_date') and 
                todo.get('target_date') == target_date_str and 
                not todo.get('completed', False)):
                pending_todos.append(todo)
        return pending_todos
    
    def get_today_pending_todos(self, taiwan_now):
        """獲取今天未完成的有日期待辦事項"""
        today_str = taiwan_now.strftime('%Y/%m/%d')
        return self.get_pending_todos_by_date(today_str)
    
    def get_tomorrow_pending_todos(self, taiwan_now):
        """獲取明天未完成的有日期待辦事項"""
        from datetime import timedelta
        tomorrow = taiwan_now + timedelta(days=1)
        tomorrow_str = tomorrow.strftime('%Y/%m/%d')
        return self.get_pending_todos_by_date(tomorrow_str)
    
    def get_todo_count(self):
        """獲取待辦事項數量"""
        return len(self._get_todos())
    
    def get_monthly_count(self):
        """獲取每月事項數量"""
        return len(self._get_monthly_todos())
    
    def get_pending_todos(self):
        """獲取未完成的待辦事項"""
        todos = self._get_todos()
        return [todo for todo in todos if not todo.get('completed', False)]
    
    def get_completed_todos(self):
        """獲取已完成的待辦事項"""
        todos = self._get_todos()
        return [todo for todo in todos if todo.get('completed', False)]

    @property
    def todos(self):
        """為了向後相容性，提供 todos 屬性"""
        return self._get_todos()

    @property
    def monthly_todos(self):
        """為了向後相容性，提供 monthly_todos 屬性"""
        return self._get_monthly_todos()


# 建立全域實例，供其他模組使用
todo_manager = TodoManager()
