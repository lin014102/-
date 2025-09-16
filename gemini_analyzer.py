"""
gemini_analyzer.py - Gemini API 訊息分析器 (增強版 - 支援對話狀態)
整合到 LINE Todo Reminder Bot v3.0
新增功能：對話狀態管理、智能確認詞處理、上下文記憶
"""
import google.generativeai as genai
import json
import os
import time
from typing import Dict, Any, Optional
from utils.time_utils import get_taiwan_time_hhmm, get_taiwan_time

class ConversationState:
    """對話狀態管理器"""
    
    def __init__(self):
        self.user_states = {}  # {user_id: {action_type, details, options, timestamp}}
        self.state_timeout = 300  # 5分鐘後自動清除狀態
    
    def set_pending_action(self, user_id: str, action_type: str, details: Dict[str, Any], options: list = None):
        """設定待確認的動作"""
        self.user_states[user_id] = {
            'action_type': action_type,
            'details': details,
            'options': options or [],
            'timestamp': time.time()
        }
        print(f"💭 設定用戶 {user_id} 的待確認動作: {action_type}")
    
    def get_pending_action(self, user_id: str) -> Optional[Dict[str, Any]]:
        """獲取待確認的動作"""
        if user_id not in self.user_states:
            return None
        
        state = self.user_states[user_id]
        # 檢查是否超時
        if time.time() - state['timestamp'] > self.state_timeout:
            self.clear_pending_action(user_id)
            return None
        
        return state
    
    def clear_pending_action(self, user_id: str):
        """清除待確認的動作"""
        if user_id in self.user_states:
            print(f"🧹 清除用戶 {user_id} 的待確認動作")
            del self.user_states[user_id]
    
    def has_pending_action(self, user_id: str) -> bool:
        """檢查是否有待確認的動作"""
        return self.get_pending_action(user_id) is not None

class GeminiAnalyzer:
    """Gemini API 訊息分析器（增強版）"""
    
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
        
        # 新增對話狀態管理
        self.conversation_state = ConversationState()
    
    def analyze_message(self, message_text: str, user_id: str = None) -> Dict[str, Any]:
        """分析用戶訊息，返回意圖和參數（支援對話狀態）"""
        
        # 🔥 優先檢查是否為確認類訊息
        if user_id and self._is_confirmation_message(message_text):
            pending = self.conversation_state.get_pending_action(user_id)
            if pending:
                print(f"✅ 檢測到確認訊息，處理待確認動作: {pending['action_type']}")
                return self._handle_confirmation_response(message_text, pending, user_id)
        
        # 🔥 檢查是否為拒絕類訊息
        if user_id and self._is_rejection_message(message_text):
            if self.conversation_state.has_pending_action(user_id):
                self.conversation_state.clear_pending_action(user_id)
                return {
                    "intent": "system",
                    "action": "cancel_action",
                    "confidence": 1.0,
                    "parameters": {"message": "好的，已取消操作"},
                    "suggested_command": None
                }
        
        if not self.enabled:
            print("📝 Gemini 未啟用，使用降級分析")
            return self._fallback_analysis(message_text, user_id)
        
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
                print(f"🤖 Gemini 分析: 訊息='{message_text}' → 意圖={result.get('intent')} 置信度={result.get('confidence')}")
                return result
            except json.JSONDecodeError as e:
                # 如果 JSON 解析失敗，降級到關鍵字匹配
                print(f"⚠️ Gemini JSON 解析失敗: {e}")
                print(f"📄 原始回應: {response.text[:200]}")
                return self._fallback_analysis(message_text, user_id)
                
        except Exception as e:
            print(f"❌ Gemini API 錯誤: {e}")
            return self._fallback_analysis(message_text, user_id)
    
    def _is_confirmation_message(self, message_text: str) -> bool:
        """檢查是否為確認類訊息"""
        confirmation_words = [
            '是的', '是', '好', '確定', '對', '要', 'yes', 'ok', 'y',
            '沒錯', '正確', '可以', '同意', '執行', '開始', '繼續'
        ]
        message_lower = message_text.lower().strip()
        return message_lower in confirmation_words or any(word in message_lower for word in confirmation_words)
    
    def _is_rejection_message(self, message_text: str) -> bool:
        """檢查是否為拒絕類訊息"""
        rejection_words = [
            '不', '不要', '不是', '取消', '算了', 'no', 'n',
            '不用', '不對', '錯了', '停止', '結束'
        ]
        message_lower = message_text.lower().strip()
        return message_lower in rejection_words or any(word in message_lower for word in rejection_words)
    
    def _handle_confirmation_response(self, message_text: str, pending_action: Dict[str, Any], user_id: str) -> Dict[str, Any]:
        """處理確認回應"""
        action_type = pending_action['action_type']
        details = pending_action['details']
        
        # 清除待確認狀態
        self.conversation_state.clear_pending_action(user_id)
        
        # 根據動作類型返回執行指令
        if action_type == 'add_todo':
            return {
                "intent": "todo",
                "action": "execute_add_todo",
                "confidence": 1.0,
                "parameters": {
                    "todo_text": details['todo_text'],
                    "is_monthly": details.get('is_monthly', False)
                },
                "suggested_command": f"新增 {details['todo_text']}"
            }
        
        elif action_type == 'add_reminder':
            return {
                "intent": "reminder",
                "action": "execute_add_reminder", 
                "confidence": 1.0,
                "parameters": {
                    "reminder_text": details['reminder_text'],
                    "reminder_type": details.get('reminder_type', 'time')
                },
                "suggested_command": details['reminder_text']
            }
        
        elif action_type == 'stock_purchase':
            return {
                "intent": "stock",
                "action": "show_stock_purchase_help",
                "confidence": 1.0,
                "parameters": {"show_help": True},
                "suggested_command": None
            }
        
        elif action_type == 'period_record':
            return {
                "intent": "period",
                "action": "show_period_help",
                "confidence": 1.0,
                "parameters": {"show_help": True},
                "suggested_command": None
            }
        
        elif action_type == 'bill_query':
            return {
                "intent": "bill",
                "action": "show_bill_query",
                "confidence": 1.0,
                "parameters": {"show_overview": True},
                "suggested_command": "帳單查詢"
            }
        
        else:
            # 預設處理
            return {
                "intent": "system",
                "action": "confirmation_received",
                "confidence": 1.0,
                "parameters": {"message": "好的，我來為您處理"},
                "suggested_command": None
            }
    
    def _create_analysis_prompt(self, message_text: str) -> str:
        """建立分析提示詞（增強版）"""
        return f"""
請分析以下用戶訊息，並回傳 JSON 格式的結果。

用戶訊息："{message_text}"

這是一個 LINE 機器人，支援以下功能：

1. 待辦事項 (todo)：
   - 新增待辦：「新增 買菜」
   - 查詢清單：「查詢」、「清單」  
   - 自然語言待辦：「等一下要洗碗」、「記得買菜」、「8/28要開會」

2. 提醒功能 (reminder)：
   - 短期提醒：「30分鐘後開會」、「2小時後倒垃圾」
   - 時間提醒：「19:00吃晚餐」
   - 日期提醒：「明天提醒開會」、「記得明天放假」

3. 股票記帳 (stock)：
   - 股票交易：「爸爸買 2330 100 50000 0820」
   - 股票查詢：「我想買台積電」、「台積電多少錢」
   - 關鍵詞：「買股票」、「股票」、「股價」

4. 生理期追蹤 (period)：
   - 關鍵詞：「生理期」、「月經」、「經期」、「週期」
   - 記錄：「記錄生理期」、「生理期開始」
   - 查詢：「生理期查詢」、「下次生理期」

5. 帳單查詢 (bill)：
   - 關鍵詞：「帳單」、「卡費」、「繳費」
   - 查詢：「帳單查詢」、「緊急帳單」

6. 系統功能 (system)：幫助、測試等

🔥 重要分析規則：
- 單一關鍵詞也要識別：「買股票」→ stock, 「生理期」→ period, 「帳單」→ bill
- 如果包含「等一下」「要」「記得」「別忘了」→ 很可能是待辦事項
- 如果包含「明天」「後天」「下週」→ 很可能是提醒功能
- 如果包含日期格式「8/28」「12/25」→ 很可能是提醒功能
- 提高單一關鍵詞的置信度，不要因為訊息簡短就降低置信度

請回傳 JSON 格式：
{{
    "intent": "todo|reminder|stock|period|bill|system|chat",
    "action": "具體動作描述",
    "confidence": 0.0-1.0,
    "parameters": {{
        "extracted_info": "從訊息中提取的關鍵資訊"
    }},
    "suggested_command": "如果訊息不夠明確，建議的完整指令"
}}

範例分析：
- "買股票" → {{"intent": "stock", "confidence": 0.9, "action": "stock_purchase_intent"}}
- "生理期" → {{"intent": "period", "confidence": 0.9, "action": "period_query_intent"}}  
- "帳單" → {{"intent": "bill", "confidence": 0.9, "action": "bill_query_intent"}}
- "等一下要洗碗" → {{"intent": "todo", "confidence": 0.85, "suggested_command": "新增 洗碗"}}

請只回傳純 JSON，不要包含任何其他文字或 markdown 格式。
"""
    
    def _fallback_analysis(self, message_text: str, user_id: str = None) -> Dict[str, Any]:
        """降級分析（關鍵字匹配）- 增強版"""
        message_lower = message_text.lower().strip()
        print(f"🔍 降級分析: {message_text}")
        
        # 🔥 單一關鍵詞檢測 - 提高置信度
        
        # 股票相關 - 擴大關鍵詞範圍
        if any(keyword in message_text for keyword in ['買股票', '股票', '股價', '買賣', '投資', '台積電', '鴻海']):
            print("💰 匹配到股票關鍵字")
            return {
                "intent": "stock",
                "action": "stock_purchase_intent",
                "confidence": 0.9,  # 提高置信度
                "parameters": {"extracted_info": message_text},
                "suggested_command": None
            }
        
        # 生理期相關 - 新增檢測
        elif any(keyword in message_text for keyword in ['生理期', '月經', '經期', '週期', 'MC']):
            print("🩸 匹配到生理期關鍵字")
            return {
                "intent": "period",
                "action": "period_query_intent",
                "confidence": 0.9,  # 提高置信度
                "parameters": {"extracted_info": message_text},
                "suggested_command": None
            }
        
        # 帳單相關 - 新增檢測
        elif any(keyword in message_text for keyword in ['帳單', '卡費', '繳費', '信用卡', '銀行']):
            print("💳 匹配到帳單關鍵字")
            return {
                "intent": "bill",
                "action": "bill_query_intent",
                "confidence": 0.9,  # 提高置信度
                "parameters": {"extracted_info": message_text},
                "suggested_command": None
            }
        
        # 待辦事項相關 - 優先檢查
        elif any(keyword in message_text for keyword in ['等一下要', '等等要', '記得', '別忘了', '要做', '待辦']):
            print("📝 匹配到待辦關鍵字")
            return {
                "intent": "todo",
                "action": "add_todo_suggestion",
                "confidence": 0.8,
                "parameters": {"extracted_info": message_text},
                "suggested_command": None
            }
        
        # 日期提醒相關
        elif any(keyword in message_text for keyword in ['明天', '後天', '下週']) or '/' in message_text:
            print("📅 匹配到日期關鍵字")
            return {
                "intent": "reminder",
                "action": "date_reminder",
                "confidence": 0.8,
                "parameters": {"extracted_info": message_text},
                "suggested_command": None
            }
        
        # 提醒相關
        elif any(keyword in message_text for keyword in ['提醒', '分鐘後', '小時後', '時間']):
            print("⏰ 匹配到提醒關鍵字")
            return {
                "intent": "reminder", 
                "action": "add_reminder",
                "confidence": 0.8,
                "parameters": {"extracted_info": message_text},
                "suggested_command": None
            }
        
        # 待辦事項 - 更廣泛的匹配
        elif any(keyword in message_text for keyword in ['新增', '刪除', '完成', '清單', '查詢']):
            print("📋 匹配到管理關鍵字")
            return {
                "intent": "todo",
                "action": "todo_management", 
                "confidence": 0.8,
                "parameters": {"extracted_info": message_text},
                "suggested_command": None
            }
        
        # 系統功能
        elif message_text in ['幫助', 'help', '說明', '測試']:
            print("🔧 匹配到系統關鍵字")
            return {
                "intent": "system",
                "action": "help_or_status",
                "confidence": 1.0,
                "parameters": {"extracted_info": message_text},
                "suggested_command": None
            }
        
        # 預設為聊天 - 但提高機會被 AI 處理
        else:
            print("💬 預設為聊天")
            return {
                "intent": "chat",
                "action": "general_chat",
                "confidence": 0.6,  # 提高置信度讓更多訊息被處理
                "parameters": {"extracted_info": message_text},
                "suggested_command": self._suggest_command(message_text)
            }
    
    def _suggest_command(self, message_text: str) -> Optional[str]:
        """為不明確的訊息建議指令"""
        message_lower = message_text.lower()
        
        if any(word in message_lower for word in ['要', '等一下', '等等']):
            return "💡 看起來是待辦事項？\n• 新增 [您的事項]\n• 或直接說完整的事情"
        
        elif any(word in message_lower for word in ['提醒', '記得', '別忘了']):
            return "💡 提醒功能範例：\n• 30分鐘後開會\n• 19:00吃晚餐\n• 早上時間 09:00"
        
        elif any(word in message_lower for word in ['股票', '買', '賣', '投資', '台積電']):
            return "💡 股票功能範例：\n• 爸爸買 2330 100 50000 0820\n• 總覽\n• 即時損益\n• 股價查詢 台積電"
        
        return None


class EnhancedMessageRouter:
    """增強版訊息路由器 - 整合對話狀態管理"""
    
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
        """智能路由訊息（增強版 - 支援對話狀態）"""
        message_text = message_text.strip()
        
        # 設定用戶ID
        self.reminder_bot.set_user_id(user_id)
        
        print(f"🎯 路由分析開始: '{message_text}'")
        
        # 🚀 使用 Gemini 分析訊息（傳入 user_id 支援對話狀態）
        analysis = self.gemini_analyzer.analyze_message(message_text, user_id)
        
        # 先檢查是否為精確匹配的指令（高優先級）
        if self._is_exact_command(message_text):
            print("✅ 精確指令匹配，使用原邏輯")
            return self._handle_original_logic(message_text, user_id)
        
        # 🔥 降低置信度閾值，讓更多訊息被 AI 處理
        confidence_threshold = 0.4  # 從 0.5 降到 0.4
        
        if analysis.get('confidence', 0) >= confidence_threshold:
            print(f"🤖 使用 AI 處理 (置信度: {analysis.get('confidence')})")
            ai_response = self._handle_ai_analyzed_message(analysis, message_text, user_id)
            if ai_response:
                return ai_response
        
        # 否則使用原有的精確匹配邏輯
        print("📋 使用原邏輯處理")
        return self._handle_original_logic(message_text, user_id)
    
    def _handle_ai_analyzed_message(self, analysis, message_text, user_id):
        """處理 AI 分析後的訊息（增強版 - 支援對話狀態）"""
        intent = analysis.get('intent')
        action = analysis.get('action')
        params = analysis.get('parameters', {})
        suggested_command = analysis.get('suggested_command')
        extracted_info = params.get('extracted_info', '')
        
        print(f"🧠 AI 處理: intent={intent}, action={action}")
        
        # 🔥 處理執行動作（確認後的動作）
        if action == 'execute_add_todo':
            todo_text = params.get('todo_text')
            is_monthly = params.get('is_monthly', False)
            
            if is_monthly:
                return self.todo_manager.add_monthly_todo(todo_text)
            else:
                return self.todo_manager.add_todo(todo_text)
        
        elif action == 'execute_add_reminder':
            reminder_text = params.get('reminder_text')
            return self.reminder_bot.add_time_reminder(reminder_text, user_id)
        
        elif action == 'show_stock_purchase_help':
            return f"💰 股票交易說明：\n\n📝 基本格式：\n帳戶名 買 股票代號 張數 金額 日期\n💡 例如：爸爸 買 2330 100 50000 0820\n\n🔍 其他功能：\n• 總覽 - 查看所有帳戶\n• 股價查詢 台積電\n• 即時損益\n\n📚 輸入「股票幫助」查看完整說明"
        
        elif action == 'show_period_help':
            return f"🩸 生理期追蹤功能：\n\n📝 記錄功能：\n• 記錄生理期 YYYY/MM/DD\n• 生理期結束 YYYY/MM/DD\n\n🔍 查詢功能：\n• 生理期查詢 - 查看狀態\n• 下次生理期 - 預測下次時間\n\n⚙️ 設定功能：\n• 生理期設定 28天 提前5天"
        
        elif action == 'show_bill_query':
            # 直接執行帳單查詢
            from main import handle_bill_query_command
            return handle_bill_query_command("帳單查詢", user_id)
        
        elif action == 'cancel_action':
            return params.get('message', '好的，已取消操作')
        
        elif action == 'confirmation_received':
            return params.get('message', '好的，我來為您處理')
        
        # 🔥 根據意圖提供智能建議並設定待確認狀態
        elif intent == 'stock' and action == 'stock_purchase_intent':
            # 設定待確認狀態
            self.gemini_analyzer.conversation_state.set_pending_action(
                user_id, 
                'stock_purchase',
                {'intent': 'stock_help'},
                ['查看股票功能說明', '查詢股價', '查看帳戶總覽']
            )
            
            return f"💰 您想要使用股票功能嗎？\n\n可以做什麼：\n📊 查看帳戶總覽\n💹 查詢股價\n📈 記錄股票交易\n📋 查看即時損益\n\n📝 回覆「是的」查看詳細說明\n🔍 或直接輸入「總覽」查看帳戶"
        
        elif intent == 'period' and action == 'period_query_intent':
            # 設定待確認狀態
            self.gemini_analyzer.conversation_state.set_pending_action(
                user_id,
                'period_record', 
                {'intent': 'period_help'},
                ['查看生理期功能說明', '記錄生理期', '查詢狀態']
            )
            
            return f"🩸 您想要使用生理期追蹤功能嗎？\n\n可以做什麼：\n📝 記錄生理期開始/結束\n🔍 查詢週期狀態\n📅 預測下次生理期\n⚙️ 設定提醒偏好\n\n📝 回覆「是的」查看詳細說明\n📊 或直接輸入「生理期查詢」查看狀態"
        
        elif intent == 'bill' and action == 'bill_query_intent':
            # 設定待確認狀態  
            self.gemini_analyzer.conversation_state.set_pending_action(
                user_id,
                'bill_query',
                {'intent': 'bill_overview'},
                ['查看帳單總覽', '查看緊急帳單', '查看特定銀行']
            )
            
            return f"💳 您想要查詢帳單嗎？\n\n可以查詢：\n📊 所有銀行帳單總覽\n🚨 緊急/即將到期帳單\n🏦 特定銀行帳單狀態\n\n📝 回覆「是的」查看帳單總覽\n🔍 或直接輸入「帳單查詢」"
        
        elif intent == 'reminder':
            if '明天' in message_text:
                task = self._extract_task_from_reminder(message_text)
                # 設定待確認狀態
                self.gemini_analyzer.conversation_state.set_pending_action(
                    user_id,
                    'add_reminder',
                    {'reminder_text': f"明天{task}", 'reminder_type': 'todo'},
                    ['加入待辦清單', '設定時間提醒']
                )
                
                return f"⏰ 您想提醒明天的事情：{task}\n\n建議方式：\n📋 加入待辦清單\n⏰ 設定時間提醒（如：明天09:00{task}）\n\n📝 回覆「是的」加入待辦清單"
            
            elif '/' in message_text:  # 日期格式
                # 設定待確認狀態
                self.gemini_analyzer.conversation_state.set_pending_action(
                    user_id,
                    'add_reminder', 
                    {'reminder_text': message_text, 'reminder_type': 'todo'},
                    ['加入待辦清單', '設定時間提醒']
                )
                
                return f"📅 您想設定日期提醒：{message_text}\n\n建議方式：\n📋 加入待辦清單\n⏰ 設定當日時間提醒\n\n📝 回覆「是的」加入待辦清單"
            
            elif any(word in message_text for word in ['記得', '別忘了', '提醒我']):
                task = self._extract_task_from_reminder(message_text)
                # 設定待確認狀態
                self.gemini_analyzer.conversation_state.set_pending_action(
                    user_id,
                    'add_reminder',
                    {'reminder_text': task, 'reminder_type': 'time'},
                    ['設定時間提醒', '加入待辦清單']
                )
                
                return f"📝 您想設定提醒：{task}\n\n建議方式：\n⏰ 30分鐘後{task}\n🕐 19:00{task}\n📋 新增到待辦清單\n\n📝 回覆「是的」設定時間提醒"
        
        elif intent == 'todo':
            if action == 'add_todo_suggestion':
                task = self._extract_todo_content(message_text)
                if task:
                    # 設定待確認狀態
                    self.gemini_analyzer.conversation_state.set_pending_action(
                        user_id,
                        'add_todo',
                        {'todo_text': task, 'is_monthly': False},
                        ['新增到待辦清單', '設為每月固定事項']
                    )
                    
                    return f"📝 您想新增待辦事項：{task}\n\n📝 回覆「是的」確認新增\n📅 或回覆「每月」設為每月固定事項"
                else:
                    return f"📝 這似乎是待辦事項！\n\n您說：{message_text}\n\n✅ 要新增到待辦清單嗎？\n回覆「是的」即可新增"
        
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
        # 更智能的提取
        if '等一下要' in message_text:
            return message_text.replace('等一下要', '').strip()
        elif '等等要' in message_text:
            return message_text.replace('等等要', '').strip()
        elif '要' in message_text and '/' in message_text:
            return message_text  # 保持日期格式
        
        for prefix in ['要做', '要', '需要', '記得', '別忘了', '記住']:
            if prefix in message_text:
                parts = message_text.split(prefix, 1)
                if len(parts) > 1:
                    content = parts[1].strip()
                    return self._clean_task_text(content)
        return message_text  # 如果沒找到特殊前綴，返回整句
    
    def _clean_task_text(self, text):
        """清理任務文字"""
        # 清理常見的結尾詞
        for suffix in ['啊', '哦', '喔', '！', '。', '的事', '這件事']:
            text = text.rstrip(suffix)
        return text.strip()
    
    def _is_exact_command(self, message_text):
        """檢查是否為精確的現有指令（放寬限制）"""
        exact_commands = [
            '總覽', '交易記錄', '帳戶列表', '股票幫助', '查詢時間', 
            '清單', '每月清單', '幫助', 'help', '說明', '測試',
            '即時股價查詢', '即時損益'
        ]
        
        # 移除 '查詢' 讓它能被 AI 處理
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
            r'^股價查詢 .+',
            r'^估價查詢 .+',
            r'^設定代號 .+',
            r'^成本查詢 .+ .+',
            r'^交易記錄 .+',
            r'^即時損益 .+',
            r'^記錄生理期 .+',
            r'^生理期結束 .+',
            r'^帳單查詢,
            r'^緊急帳單
        ]
        
        for pattern in patterns:
            if self.re.match(pattern, message_text):
                return True
                
        return self.is_stock_command(message_text)
    
    def _handle_original_logic(self, message_text, user_id):
        """原有的精確匹配邏輯（完整版）"""
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

💳 帳單查詢：
- 帳單查詢 - 查看所有帳單
- 緊急帳單 - 查看即將到期帳單
- [銀行名稱]帳單查詢 - 查看特定銀行

🩸 生理期追蹤：
- 記錄生理期 YYYY/MM/DD - 記錄開始
- 生理期結束 YYYY/MM/DD - 記錄結束
- 生理期查詢 - 查看狀態
- 下次生理期 - 預測下次時間

🤖 AI 智能功能：
- 自然語言理解，例如：
- 「買股票」→ 顯示股票功能
- 「生理期」→ 顯示生理期功能
- 「帳單」→ 顯示帳單查詢
- 「記得明天開會」→ 智能提醒建議
- 「等一下要洗碗」→ 待辦事項建議
- 確認詞：「是的」「好」「確定」

🚀 v3.0 + AI：模組化架構 + 智能對話 + 狀態記憶！"""
    
    def get_system_status(self):
        """獲取系統狀態"""
        ai_status = "✅ 已啟用" if self.gemini_analyzer.enabled else "❌ 未啟用"
        state_count = len(self.gemini_analyzer.conversation_state.user_states)
        
        return f"""✅ 系統狀態檢查
🇹🇼 當前台灣時間：{get_taiwan_time()}

📊 模組狀態：
⏰ 提醒機器人：✅ 運行中
📋 待辦事項管理：✅ 已載入
💰 股票記帳模組：✅ 已載入
💹 即時損益功能：✅ 已啟用
🤖 Gemini AI：{ai_status}
💭 對話狀態管理：✅ 已啟用 (活躍用戶: {state_count})

🔧 架構：完全模組化 + AI + 智能對話
🚀 版本：v3.0 + Gemini + State Management

💡 輸入「幫助」查看功能列表"""
    
    def get_default_response(self, message_text):
        """預設回應（增強版）"""
        basic_response = f"""😊 您說：{message_text}
🇹🇼 當前台灣時間：{get_taiwan_time_hhmm()}

💡 輸入「幫助」查看待辦功能
💰 輸入「股票幫助」查看股票功能
💹 輸入「即時損益」查看股票損益

🤖 提示：您可以用自然語言跟我對話！
例如：「買股票」、「生理期」、「帳單」、「記得明天開會」、「等一下要洗碗」
確認時回覆：「是的」「好」「確定」"""
        
        return basic_response
