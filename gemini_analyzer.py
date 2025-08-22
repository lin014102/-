# ===== 新增檔案：gemini_analyzer.py =====
import google.generativeai as genai
import json
import os
from typing import Dict, Any, Optional

class GeminiAnalyzer:
    """Gemini API 訊息分析器"""
    
    def __init__(self):
        # 設定 Gemini API
        api_key = os.getenv('GEMINI_API_KEY')
        if api_key:
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel('gemini-pro')
            self.enabled = True
        else:
            self.enabled = False
            print("⚠️ GEMINI_API_KEY 未設定，將使用傳統關鍵字匹配")
    
    def analyze_message(self, message_text: str) -> Dict[str, Any]:
        """分析用戶訊息，返回意圖和參數"""
        if not self.enabled:
            return self._fallback_analysis(message_text)
        
        try:
            prompt = self._create_analysis_prompt(message_text)
            response = self.model.generate_content(prompt)
            
            # 嘗試解析 JSON 回應
            try:
                result = json.loads(response.text)
                return result
            except json.JSONDecodeError:
                # 如果 JSON 解析失敗，降級到關鍵字匹配
                print(f"⚠️ Gemini 回應解析失敗，降級處理: {response.text[:100]}")
                return self._fallback_analysis(message_text)
                
        except Exception as e:
            print(f"❌ Gemini API 錯誤: {e}")
            return self._fallback_analysis(message_text)
    
    def _create_analysis_prompt(self, message_text: str) -> str:
        """建立分析提示詞"""
        return f"""
請分析以下用戶訊息，並回傳 JSON 格式的結果。

用戶訊息："{message_text}"

功能分類：
1. 待辦事項 (todo)：新增、查詢、刪除、完成待辦事項
2. 提醒功能 (reminder)：設定時間提醒、短期提醒
3. 股票記帳 (stock)：股票買賣、查詢、記帳功能
4. 系統功能 (system)：幫助、測試、查看狀態
5. 聊天對話 (chat)：一般對話或不明確的訊息

請回傳 JSON 格式：
{{
    "intent": "todo|reminder|stock|system|chat",
    "action": "具體動作",
    "confidence": 0.0-1.0,
    "parameters": {{
        "key": "value"
    }},
    "suggested_command": "建議的精確指令（如果需要）"
}}

範例：
- "幫我明天提醒開會" → {{"intent": "reminder", "action": "add_time_reminder", "parameters": {{"time": "明天", "task": "開會"}}}}
- "我想買台積電" → {{"intent": "stock", "action": "stock_transaction", "parameters": {{"action": "buy", "stock": "台積電"}}}}
- "查看我的代辦" → {{"intent": "todo", "action": "list_todos"}}
"""
    
    def _fallback_analysis(self, message_text: str) -> Dict[str, Any]:
        """降級分析（關鍵字匹配）"""
        message_lower = message_text.lower().strip()
        
        # 股票相關
        if any(keyword in message_text for keyword in ['買', '賣', '股票', '股價', '損益', '入帳', '總覽']):
            return {
                "intent": "stock",
                "action": "stock_command",
                "confidence": 0.8,
                "parameters": {"original_text": message_text},
                "suggested_command": None
            }
        
        # 提醒相關
        elif any(keyword in message_text for keyword in ['提醒', '分鐘後', '小時後', '時間']):
            return {
                "intent": "reminder",
                "action": "add_reminder",
                "confidence": 0.8,
                "parameters": {"original_text": message_text},
                "suggested_command": None
            }
        
        # 待辦事項
        elif any(keyword in message_text for keyword in ['新增', '刪除', '完成', '清單', '查詢']):
            return {
                "intent": "todo",
                "action": "todo_management",
                "confidence": 0.8,
                "parameters": {"original_text": message_text},
                "suggested_command": None
            }
        
        # 系統功能
        elif message_text in ['幫助', 'help', '說明', '測試']:
            return {
                "intent": "system",
                "action": "help_or_status",
                "confidence": 1.0,
                "parameters": {"original_text": message_text},
                "suggested_command": None
            }
        
        # 預設為聊天
        else:
            return {
                "intent": "chat",
                "action": "general_chat",
                "confidence": 0.3,
                "parameters": {"original_text": message_text},
                "suggested_command": self._suggest_command(message_text)
            }
    
    def _suggest_command(self, message_text: str) -> Optional[str]:
        """為不明確的訊息建議指令"""
        message_lower = message_text.lower()
        
        if '提醒' in message_lower or '記得' in message_lower:
            return "💡 提醒功能範例：\n• 30分鐘後開會\n• 19:00吃晚餐\n• 早上時間 09:00"
        
        elif '股票' in message_lower or '買' in message_lower or '投資' in message_lower:
            return "💡 股票功能範例：\n• 爸爸買 2330 100 50000 0820\n• 總覽\n• 即時損益"
        
        elif '待辦' in message_lower or '事情' in message_lower:
            return "💡 待辦功能範例：\n• 新增 買菜\n• 查詢\n• 完成 1"
        
        return None


# ===== 修改 main.py 中的 MessageRouter =====
class EnhancedMessageRouter:
    """增強版訊息路由器 - 整合 Gemini AI"""
    
    def __init__(self, todo_mgr, reminder_bot, stock_mgr):
        self.todo_manager = todo_mgr
        self.reminder_bot = reminder_bot
        self.gemini_analyzer = GeminiAnalyzer()  # 🆕 新增
        
        # 原有的路由器邏輯保持不變
        self.original_router = MessageRouter(todo_mgr, reminder_bot, stock_mgr)
    
    def route_message(self, message_text, user_id):
        """智能路由訊息"""
        message_text = message_text.strip()
        
        # 設定用戶ID
        self.reminder_bot.set_user_id(user_id)
        
        # 🚀 使用 Gemini 分析訊息
        analysis = self.gemini_analyzer.analyze_message(message_text)
        
        # 如果置信度高，使用 AI 建議的處理方式
        if analysis.get('confidence', 0) >= 0.7:
            return self._handle_ai_analyzed_message(analysis, message_text, user_id)
        
        # 否則使用原有的精確匹配邏輯
        return self.original_router.route_message(message_text, user_id)
    
    def _handle_ai_analyzed_message(self, analysis, message_text, user_id):
        """處理 AI 分析後的訊息"""
        intent = analysis.get('intent')
        action = analysis.get('action')
        params = analysis.get('parameters', {})
        suggested_command = analysis.get('suggested_command')
        
        # 根據意圖路由到對應模組
        if intent == 'stock':
            # 如果是模糊的股票意圖，提供建議
            if action == 'stock_transaction' and 'stock' in params:
                stock_name = params['stock']
                return f"💰 您想要操作 {stock_name} 嗎？\n\n請使用完整格式：\n• 帳戶名 買 股票代號 張數 金額 日期\n• 例如：爸爸 買 2330 100 50000 0820\n\n💡 或輸入「股票幫助」查看完整說明"
            
            # 否則使用原有邏輯處理
            return self.original_router.route_message(message_text, user_id)
        
        elif intent == 'reminder':
            # 提醒功能的智能處理
            if '明天' in message_text:
                return "⏰ 明天的提醒功能開發中！\n\n目前支援：\n• 30分鐘後提醒\n• 19:00開會（當日時間提醒）"
            
            return self.original_router.route_message(message_text, user_id)
        
        elif intent == 'todo':
            # 待辦事項的智能處理
            if action == 'todo_management':
                # 嘗試智能解析新增動作
                if any(word in message_text for word in ['要', '需要', '記得', '別忘了']):
                    # 提取可能的待辦內容
                    todo_content = self._extract_todo_content(message_text)
                    if todo_content:
                        return f"📝 您想新增待辦事項嗎？\n\n建議內容：{todo_content}\n\n請回覆「新增 {todo_content}」確認新增"
            
            return self.original_router.route_message(message_text, user_id)
        
        elif intent == 'system':
            return self.original_router.route_message(message_text, user_id)
        
        elif intent == 'chat':
            # 一般對話 - 提供友善回應和建議
            response = f"😊 您說：{message_text}\n🇹🇼 當前時間：{get_taiwan_time_hhmm()}"
            
            if suggested_command:
                response += f"\n\n{suggested_command}"
            else:
                response += "\n\n💡 輸入「幫助」查看所有功能"
            
            return response
        
        # 預設情況
        return self.original_router.route_message(message_text, user_id)
    
    def _extract_todo_content(self, message_text):
        """從自然語言中提取待辦內容"""
        # 簡單的關鍵字提取邏輯
        for prefix in ['要', '需要', '記得', '別忘了']:
            if prefix in message_text:
                parts = message_text.split(prefix, 1)
                if len(parts) > 1:
                    content = parts[1].strip()
                    # 清理常見的結尾詞
                    for suffix in ['啊', '哦', '喔', '！', '。']:
                        content = content.rstrip(suffix)
                    return content
        return None


# ===== 在 main.py 中替換路由器 =====
# 將這行：
# message_router = MessageRouter(todo_manager, reminder_bot, None)

# 改為：
# message_router = EnhancedMessageRouter(todo_manager, reminder_bot, None)
