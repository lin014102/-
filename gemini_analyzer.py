"""
gemini_analyzer.py - Gemini API 訊息分析器
整合到 LINE Todo Reminder Bot v3.0
"""
import google.generativeai as genai
import json
import os
from typing import Dict, Any, Optional
from utils.time_utils import get_taiwan_time_hhmm, get_taiwan_time

class GeminiAnalyzer:
    """Gemini API 訊息分析器"""
    
    def __init__(self):
        # 設定 Gemini API
        api_key = os.getenv('GEMINI_API_KEY')
        if api_key:
            try:
                genai.configure(api_key=api_key)
                self.model = genai.GenerativeModel('gemini-pro')
                self.enabled = True
                print("✅ Gemini API 已啟用")
            except Exception as e:
                self.enabled = False
                print(f"❌ Gemini API 初始化失敗: {e}")
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
                # 清理回應文字，移除可能的 markdown 格式
                response_text = response.text.strip()
                if response_text.startswith('```json'):
                    response_text = response_text[7:]
                if response_text.endswith('```'):
                    response_text = response_text[:-3]
                
                result = json.loads(response_text)
                print(f"🤖 Gemini 分析結果: {result.get('intent')} - {result.get('confidence')}")
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

這是一個 LINE 機器人，支援以下功能：

1. 待辦事項 (todo)：
   - 新增待辦：「新增 買菜」
   - 查詢清單：「查詢」、「清單」  
   - 刪除事項：「刪除 1」
   - 完成事項：「完成 1」
   - 每月待辦：「每月新增 5號繳卡費」

2. 提醒功能 (reminder)：
   - 短期提醒：「30分鐘後開會」、「2小時後倒垃圾」
   - 時間提醒：「19:00吃晚餐」
   - 設定提醒時間：「早上時間 09:00」、「晚上時間 18:00」

3. 股票記帳 (stock)：
   - 股票交易：「爸爸買 2330 100 50000 0820」
   - 入金：「爸爸入帳 50000」
   - 查詢總覽：「總覽」
   - 即時損益：「即時損益」
   - 股價查詢：「股價查詢 台積電」、「估價查詢 台積電」
   - 設定代號：「設定代號 台積電 2330」

4. 系統功能 (system)：
   - 幫助：「幫助」、「help」、「說明」
   - 測試：「測試」

請回傳 JSON 格式：
{{
    "intent": "todo|reminder|stock|system|chat",
    "action": "具體動作描述",
    "confidence": 0.0-1.0,
    "parameters": {{
        "extracted_info": "從訊息中提取的關鍵資訊"
    }},
    "suggested_command": "如果訊息不夠明確，建議的完整指令"
}}

範例：
- "幫我記住明天開會" → {{"intent": "reminder", "action": "add_reminder", "confidence": 0.8, "parameters": {{"extracted_info": "明天開會"}}, "suggested_command": "明天的具體時間提醒功能開發中，目前支援：19:00開會"}}
- "我想買台積電" → {{"intent": "stock", "action": "stock_interest", "confidence": 0.7, "parameters": {{"extracted_info": "買台積電"}}, "suggested_command": "爸爸買 2330 100 50000 0820"}}
- "幫我記住買菜" → {{"intent": "todo", "action": "add_todo", "confidence": 0.9, "parameters": {{"extracted_info": "買菜"}}, "suggested_command": "新增 買菜"}}

請只回傳 JSON，不要其他文字。
"""
    
    def _fallback_analysis(self, message_text: str) -> Dict[str, Any]:
        """降級分析（關鍵字匹配）"""
        message_lower = message_text.lower().strip()
        
        # 股票相關
        if any(keyword in message_text for keyword in ['買', '賣', '股票', '股價', '損益', '入帳', '總覽', '台積電', '鴻海']):
            return {
                "intent": "stock",
                "action": "stock_command",
                "confidence": 0.8,
                "parameters": {"extracted_info": message_text},
                "suggested_command": None
            }
        
        # 提醒相關
        elif any(keyword in message_text for keyword in ['提醒', '分鐘後', '小時後', '時間', '記得']):
            return {
                "intent": "reminder", 
                "action": "add_reminder",
                "confidence": 0.8,
                "parameters": {"extracted_info": message_text},
                "suggested_command": None
            }
        
        # 待辦事項
        elif any(keyword in message_text for keyword in ['新增', '刪除', '完成', '清單', '查詢', '待辦', '要做']):
            return {
                "intent": "todo",
                "action": "todo_management", 
                "confidence": 0.8,
                "parameters": {"extracted_info": message_text},
                "suggested_command": None
            }
        
        # 系統功能
        elif message_text in ['幫助', 'help', '說明', '測試']:
            return {
                "intent": "system",
                "action": "help_or_status",
                "confidence": 1.0,
                "parameters": {"extracted_info": message_text},
                "suggested_command": None
            }
        
        # 預設為聊天
        else:
            return {
                "intent": "chat",
                "action": "general_chat",
                "confidence": 0.3,
                "parameters": {"extracted_info": message_text},
                "suggested_command": self._suggest_command(message_text)
            }
    
    def _suggest_command(self, message_text: str) -> Optional[str]:
        """為不明確的訊息建議指令"""
        message_lower = message_text.lower()
        
        if any(word in message_lower for word in ['提醒', '記得', '別忘了']):
            return "💡 提醒功能範例：\n• 30分鐘後開會\n• 19:00吃晚餐\n• 早上時間 09:00"
        
        elif any(word in message_lower for word in ['股票', '買', '賣', '投資', '台積電']):
            return "💡 股票功能範例：\n• 爸爸買 2330 100 50000 0820\n• 總覽\n• 即時損益\n• 股價查詢 台積電"
        
        elif any(word in message_lower for word in ['待辦', '事情', '要做', '任務']):
            return "💡 待辦功能範例：\n• 新增 買菜\n• 查詢\n• 完成 1"
        
        return None


class EnhancedMessageRouter:
    """增強版訊息路由器 - 整合 Gemini AI"""
    
    def __init__(self, todo_mgr, reminder_bot, stock_mgr):
        self.todo_manager = todo_mgr
        self.reminder_bot = reminder_bot
        self.gemini_analyzer = GeminiAnalyzer()
        
        # 導入原有的路由邏輯需要的模組
        from stock_manager import (
            handle_stock_command, get_stock_summary, get_stock_transactions,
            get_stock_cost_analysis, get_stock_account_list, get_stock_help,
            is_stock_command, is_stock_query, get_stock_realtime_pnl
        )
        from utils.time_utils import is_valid_time_format
        import re
        
        # 保存引用以便使用
        self.handle_stock_command = handle_stock_command
        self.get_stock_summary = get_stock_summary
        self.get_stock_transactions = get_stock_transactions
        self.get_stock_cost_analysis = get_stock_cost_analysis
        self.get_stock_account_list = get_stock_account_list
        self.get_stock_help = get_stock_help
        self.is_stock_command = is_stock_command
        self.is_stock_query = is_stock_query
        self.get_stock_realtime_pnl = get_stock_realtime_pnl
        self.is_valid_time_format = is_valid_time_format
        self.re = re
    
    def route_message(self, message_text, user_id):
        """智能路由訊息"""
        message_text = message_text.strip()
        
        # 設定用戶ID
        self.reminder_bot.set_user_id(user_id)
        
        # 🚀 使用 Gemini 分析訊息
        analysis = self.gemini_analyzer.analyze_message(message_text)
        
        # 先檢查是否為精確匹配的指令（高優先級）
        if self._is_exact_command(message_text):
            return self._handle_original_logic(message_text, user_id)
        
        # 如果置信度高，使用 AI 建議的處理方式
        if analysis.get('confidence', 0) >= 0.7:
            ai_response = self._handle_ai_analyzed_message(analysis, message_text, user_id)
            if ai_response:
                return ai_response
        
        # 否則使用原有的精確匹配邏輯
        return self._handle_original_logic(message_text, user_id)
    
    def _is_exact_command(self, message_text):
        """檢查是否為精確的現有指令"""
        exact_commands = [
            '總覽', '交易記錄', '帳戶列表', '股票幫助', '查詢時間', 
            '查詢', '清單', '每月清單', '幫助', 'help', '說明', '測試',
            '即時股價查詢', '即時損益'
        ]
        
        if message_text in exact_commands:
            return True
            
        # 檢查特定格式的指令
        patterns = [
            r'^新增 .+',
            r'^刪除 \d+',  
            r'^完成 \d+',
            r'^每月新增 .+',
            r'^每月刪除 \d+',
            r'^早上時間 \d{1,2}:\d{2}',
            r'^晚上時間 \d{1,2}:\d{2}',
            r'^\d{1,2}:\d{2}.+',
            r'.+(分鐘後|小時後|秒後)',
            r'^.+查詢$',
            r'^股價查詢 .+',
            r'^估價查詢 .+',
            r'^設定代號 .+',
            r'^成本查詢 .+ .+',
            r'^交易記錄 .+',
            r'^即時損益 .+'
        ]
        
        for pattern in patterns:
            if self.re.match(pattern, message_text):
                return True
                
        return self.is_stock_command(message_text)
    
    def _handle_ai_analyzed_message(self, analysis, message_text, user_id):
        """處理 AI 分析後的訊息"""
        intent = analysis.get('intent')
        action = analysis.get('action')
        params = analysis.get('parameters', {})
        suggested_command = analysis.get('suggested_command')
        extracted_info = params.get('extracted_info', '')
        
        # 根據意圖提供智能建議
        if intent == 'stock':
            if '買' in message_text or '購買' in message_text:
                return f"💰 您想要買股票嗎？\n\n請使用完整格式：\n📝 帳戶名 買 股票代號 張數 金額 日期\n💡 例如：爸爸 買 2330 100 50000 0820\n\n❓ 需要查詢股價嗎？\n🔍 輸入「股價查詢 台積電」\n\n📚 輸入「股票幫助」查看完整說明"
            
            elif any(word in message_text for word in ['股價', '多少錢', '價格']):
                stock_name = self._extract_stock_name(message_text)
                if stock_name:
                    return f"💹 您想查詢 {stock_name} 的股價嗎？\n\n請使用：\n🔍 股價查詢 {stock_name}\n📊 估價查詢 {stock_name}\n\n💡 記得先設定代號：\n⚙️ 設定代號 {stock_name} [股票代號]"
                else:
                    return "💹 股價查詢功能：\n\n使用方式：\n• 股價查詢 台積電\n• 估價查詢 鴻海\n• 股價 中華電\n\n💡 記得先用「設定代號 股票名稱 代號」設定股票代號"
        
        elif intent == 'reminder':
            if '明天' in message_text:
                task = self._extract_task_from_reminder(message_text)
                return f"⏰ 明天的提醒功能開發中！\n\n您想提醒：{task}\n\n🔧 目前支援：\n• 30分鐘後{task}\n• 19:00{task}（當日時間提醒）\n• 新增 明天{task}（加入待辦清單）"
            
            elif any(word in message_text for word in ['記得', '別忘了', '提醒我']):
                task = self._extract_task_from_reminder(message_text)
                return f"📝 您想設定提醒：{task}\n\n請選擇方式：\n⏰ 30分鐘後{task}\n🕐 19:00{task}\n📋 新增 {task}（加入待辦清單）"
        
        elif intent == 'todo':
            if any(word in message_text for word in ['要做', '記住', '別忘了']):
                task = self._extract_todo_content(message_text)
                if task:
                    return f"📝 您想新增待辦事項嗎？\n\n建議內容：{task}\n\n✅ 請回覆「新增 {task}」確認新增\n📅 或回覆「每月新增 {task}」設為每月固定事項"
        
        elif intent == 'chat':
            # 一般對話 - 提供友善回應和建議
            response = f"😊 您說：{message_text}\n🇹🇼 當前時間：{get_taiwan_time_hhmm()}"
            
            if suggested_command:
                response += f"\n\n{suggested_command}"
            else:
                response += "\n\n💡 輸入「幫助」查看所有功能\n💰 輸入「股票幫助」查看股票功能"
            
            return response
        
        return None  # 如果沒有特殊處理，返回 None 讓原邏輯處理
    
    def _extract_stock_name(self, message_text):
        """從訊息中提取股票名稱"""
        common_stocks = ['台積電', '鴻海', '聯發科', '中華電', '台塑', '中鋼', '第一金']
        for stock in common_stocks:
            if stock in message_text:
                return stock
        return None
    
    def _extract_task_from_reminder(self, message_text):
        """從提醒訊息中提取任務"""
        for prefix in ['記得', '別忘了', '提醒我', '提醒']:
            if prefix in message_text:
                parts = message_text.split(prefix, 1)
                if len(parts) > 1:
                    task = parts[1].strip()
                    return self._clean_task_text(task)
        return "指定任務"
    
    def _extract_todo_content(self, message_text):
        """從自然語言中提取待辦內容"""
        for prefix in ['要做', '要', '需要', '記得', '別忘了', '記住']:
            if prefix in message_text:
                parts = message_text.split(prefix, 1)
                if len(parts) > 1:
                    content = parts[1].strip()
                    return self._clean_task_text(content)
        return None
    
    def _clean_task_text(self, text):
        """清理任務文字"""
        # 清理常見的結尾詞
        for suffix in ['啊', '哦', '喔', '！', '。', '的事', '這件事']:
            text = text.rstrip(suffix)
        return text.strip()
    
    def _handle_original_logic(self, message_text, user_id):
        """原有的精確匹配邏輯"""
        # 這裡包含你原本 MessageRouter 的所有邏輯
        
        # === 股票功能路由 ===
        if self.is_stock_command(message_text):
            return self.handle_stock_command(message_text)
        
        elif message_text == '總覽':
            return self.get_stock_summary()
        
        elif message_text.endswith('查詢') and message_text != '查詢':
            account_name = message_text[:-2].strip()
            if account_name in ['股票', '帳戶']:
                return self.get_stock_summary()
            else:
                return self.get_stock_summary(account_name)
        
        elif message_text == '即時股價查詢':
            return "💹 即時股價查詢說明：\n\n使用方式：\n• 股價查詢 台積電\n• 估價查詢 鴻海\n• 股價 中華電\n\n💡 記得先用「設定代號 股票名稱 代號」設定股票代號"

        elif message_text.startswith('估價查詢 '):
            stock_name = message_text.replace('估價查詢 ', '').strip()
            return self.handle_stock_command(f"股價查詢 {stock_name}")

        elif message_text.startswith('即時損益 '):
            account_name = message_text.replace('即時損益 ', '').strip()
            return self.get_stock_realtime_pnl(account_name)

        elif message_text == '即時損益':
            return self.get_stock_realtime_pnl()
        
        elif message_text.startswith('檢查代號'):
            return self.handle_stock_command(message_text)
        
        elif message_text.startswith('設定代號 '):
            return self.handle_stock_command(message_text)
        
        elif message_text.startswith('股價查詢 ') or message_text.startswith('股價 '):
            return self.handle_stock_command(message_text)
        
        elif message_text == '交易記錄':
            return self.get_stock_transactions()
        
        elif message_text.startswith('交易記錄 '):
            account_name = message_text[5:].strip()
            return self.get_stock_transactions(account_name)
        
        elif message_text.startswith('成本查詢 ') and ' ' in message_text[5:]:
            parts = message_text[5:].strip().split(' ', 1)
            if len(parts) == 2:
                account_name, stock_code = parts
                return self.get_stock_cost_analysis(account_name, stock_code)
            else:
                return "❌ 格式不正確\n💡 例如：成本查詢 爸爸 2330"
        
        elif message_text == '帳戶列表':
            return self.get_stock_account_list()
        
        elif message_text == '股票幫助':
            return self.get_stock_help()
        
        # === 提醒功能路由 ===
        elif message_text == '查詢時間':
            return self.reminder_bot.get_time_settings()
        
        elif message_text.startswith('早上時間 '):
            time_str = message_text[5:].strip()
            if self.is_valid_time_format(time_str):
                return self.reminder_bot.set_morning_time(time_str)
            else:
                return "❌ 時間格式不正確，請使用 HH:MM 格式，例如：08:30"
        
        elif message_text.startswith('晚上時間 '):
            time_str = message_text[5:].strip()
            if self.is_valid_time_format(time_str):
                return self.reminder_bot.set_evening_time(time_str)
            else:
                return "❌ 時間格式不正確，請使用 HH:MM 格式，例如：19:00"
        
        elif any(keyword in message_text for keyword in ['分鐘後', '小時後', '秒後']):
            return self.reminder_bot.add_short_reminder(message_text, user_id)
        
        elif self.re.match(r'^\d{1,2}:\d{2}.+', message_text):
            return self.reminder_bot.add_time_reminder(message_text, user_id)
        
        # === 待辦事項功能路由 ===
        elif message_text.startswith('新增 '):
            todo_text = message_text[3:].strip()
            return self.todo_manager.add_todo(todo_text)
        
        elif message_text in ['查詢', '清單']:
            return self.todo_manager.get_todo_list()
        
        elif message_text.startswith('刪除 '):
            index_str = message_text[3:]
            return self.todo_manager.delete_todo(index_str)
        
        elif message_text.startswith('完成 '):
            index_str = message_text[3:]
            return self.todo_manager.complete_todo(index_str)
        
        elif message_text.startswith('每月新增 '):
            todo_text = message_text[5:].strip()
            return self.todo_manager.add_monthly_todo(todo_text)
        
        elif message_text == '每月清單':
            return self.todo_manager.get_monthly_list()
            
        elif message_text.startswith('每月刪除 '):
            index_str = message_text[5:].strip()
            return self.todo_manager.delete_monthly_todo(index_str)
        
        # === 系統功能 ===
        elif message_text in ['幫助', 'help', '說明']:
            return self.get_help_message()
        
        elif message_text == '測試':
            return self.get_system_status()
        
        else:
            return self.get_default_response(message_text)
    
    def get_help_message(self):
        """獲取幫助訊息"""
        return """📋 LINE Todo Bot v3.0 + AI 完整功能：

🔹 待辦事項：
- 新增 [事項] - 新增待辦事項
- 查詢 - 查看待辦清單
- 刪除 [編號] - 刪除事項
- 完成 [編號] - 標記完成

⏰ 提醒功能：
- 5分鐘後倒垃圾 - 短期提醒
- 12:00開會 - 時間提醒
- 早上時間 09:00 - 設定早上提醒
- 晚上時間 18:00 - 設定晚上提醒

🔄 每月功能：
- 每月新增 5號繳卡費 - 每月固定事項
- 每月清單 - 查看每月事項
- 每月刪除 [編號] - 刪除每月事項

💰 股票記帳：
- 爸爸入帳 50000 - 入金
- 爸爸買 2330 100 50000 0820 - 買股票
- 總覽 - 查看所有帳戶
- 即時損益 - 查看即時損益
- 估價查詢 台積電 - 查詢股價
- 設定代號 台積電 2330 - 設定股票代號
- 股票幫助 - 股票功能詳細說明

🤖 AI 智能功能：
- 自然語言理解，例如：
- 「我想買台積電」
- 「記得明天開會」
- 「幫我記住買菜」

🚀 v3.0 + AI：模組化架構 + 智能對話！"""
    
    def get_system_status(self):
        """獲取系統狀態"""
        ai_status = "✅ 已啟用" if self.gemini_analyzer.enabled else "❌ 未啟用"
        return f"""✅ 系統狀態檢查
🇹🇼 當前台灣時間：{get_taiwan_time()}

📊 模組狀態：
⏰ 提醒機器人：✅ 運行中
📋 待辦事項管理：✅ 已載入
💰 股票記帳模組：✅ 已載入
💹 即時損益功能：✅ 已啟用
🤖 Gemini AI：{ai_status}

🔧 架構：完全模組化 + AI
🚀 版本：v3.0 + Gemini

💡 輸入「幫助」查看功能列表"""
    
    def get_default_response(self, message_text):
        """預設回應（增強版）"""
        basic_response = f"""😊 您說：{message_text}
🇹🇼 當前台灣時間：{get_taiwan_time_hhmm()}

💡 輸入「幫助」查看待辦功能
💰 輸入「股票幫助」查看股票功能
💹 輸入「即時損益」查看股票損益

🤖 提示：您可以用自然語言跟我對話！
例如：「我想買台積電」、「記得明天開會」"""
        
        return basic_response
