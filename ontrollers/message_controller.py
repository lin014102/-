"""
訊息處理控制器
"""
from services.line_service import line_service
from controllers.todo_controller import todo_controller

class MessageController:
    """訊息處理控制器"""
    
    def __init__(self):
        pass
    
    def handle_text_message(self, reply_token, message_text, user_id):
        """處理文字訊息"""
        message = message_text.strip()
        
        # 幫助訊息
        if message in ['幫助', 'help', '說明']:
            reply = self.get_help_message()
        
        # 查詢待辦事項
        elif message in ['查詢', '清單', '列表']:
            todos = todo_controller.get_all_todos()
            if todos:
                reply = "📋 您的待辦事項：\n\n"
                for i, todo in enumerate(todos, 1):
                    reply += f"{i}. {todo['content']}\n"
            else:
                reply = "📝 目前沒有待辦事項\n輸入「新增 [事項]」來新增"
        
        # 新增待辦事項
        elif message.startswith('新增 '):
            content = message[3:].strip()
            if content:
                todo = todo_controller.add_todo(content)
                reply = f"✅ 已新增待辦事項：「{content}」\n目前共有 {len(todo_controller.todos)} 項"
            else:
                reply = "❌ 請輸入要新增的事項內容"
        
        # 預設回覆
        else:
            reply = f"您說：{message}\n\n輸入「幫助」查看可用指令"
        
        # 發送回覆
        return line_service.reply_message(reply_token, reply)
    
    def get_help_message(self):
        """獲取幫助訊息"""
        return """📋 LINE 待辦事項機器人

🔹 基本指令：
- 新增 [事項] - 新增待辦事項
- 查詢 - 查看所有待辦事項
- 幫助 - 顯示此說明

💡 範例：
新增 買牛奶
新增 8點開會
查詢

更多功能開發中... 🚀"""

# 創建全域實例
message_controller = MessageController()
