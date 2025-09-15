def handle_command(self, message_text):
        """處理股票指令的主要函數 - 新版"""
        parsed = self.parse_command(message_text)
        
        if not parsed:
            return "❌ 指令格式不正確\n💡 輸入「股票幫助」查看使用說明"
        
        try:
            if parsed['type'] == 'deposit':
                return self.handle_deposit(parsed['account'], parsed['amount'])
            
            elif parsed['type'] == 'withdraw':
                return self.handle_withdraw(parsed['account'], parsed['amount'])
            
            elif parsed['type'] == 'holding':
                return self.handle_holding(
                    parsed['account'], parsed['stock_input'], 
                    parsed['quantity_str'], parsed['total_cost']
                )
            
            elif parsed['type'] == 'buy':
                return self.handle_buy(
                    parsed['account'], parsed['stock_input'], parsed['quantity_str'],
                    parsed['amount'], parsed['date']
                )
            
            elif parsed['type'] == 'sell':
                return self.handle_sell(
                    parsed['account'], parsed['stock_input'], parsed['quantity_str'],
                    parsed['amount'], parsed['date']
                )
            
            elif parsed['type'] == 'create_account':
                return self.create_account(parsed['account'])
            
            elif parsed['type'] == 'set_code':
                return self.set_stock_code(parsed['stock_name'], parsed['stock_code'])
            
            elif parsed['type'] == 'price_query':
                stock_name = parsed['stock_name']
                stock_code = self.stock_data['stock_codes'].get(stock_name)
                if stock_code:
                    price = self.get_stock_price(stock_code)
                    if price:
                        return f"💹 {stock_name} ({stock_code}) 即時股價：{price}元"
                    else:
                        return f"❌ 無法取得 {stock_name} ({stock_code}) 的股價"
                else:
                    return f"❌ 請先設定 {stock_name} 的股票代號\n💡 使用：設定代號 {stock_name} XXXX"
            
            elif parsed['type'] == 'batch_code_guide':
                return """📝 批量設定股票代號說明：

請按以下格式輸入多個股票代號：
```
鴻海 2317
台積電 2330
佳世達 2352
群光 2385
台新金 2887
```

💡 使用「檢查代號」查看哪些股票還沒設定代號"""
            
            elif parsed['type'] == 'check_codes':
                return self.get_missing_stock_codes(parsed.get('account'))
            
        except Exception as e:
            return f"❌ 處理失敗：{str(e)}\n💡 請檢查指令格式"
        
        return "❌ 未知的指令類型"
    
    def get_help_text(self):
        """獲取幫助訊息 - 新版"""
        return """💰 多帳戶股票記帳功能 v2.3 - 簡化輸入版：

📋 帳戶管理：
- 爸爸入帳 50000 - 入金
- 媽媽提款 10000 - 提款  
- 新增帳戶 奶奶 - 建立帳戶

📊 持股設定（新格式 - 支援張/股單位）：
- 爸爸持有 台積電 10張 500000 - 設定現有持股（10張=10,000股）
- 媽媽持有 鴻海 500股 50000 - 零股持股
- 爸爸持有 2330 5張 300000 - 可直接用股票代號

📈 交易操作（新格式 - 簡化輸入）：
- 爸爸買 台積電 10張 500000 0820 - 買股票（包含手續費）
- 媽媽賣 鴻海 5張 250000 0821 - 賣股票（實收金額）
- 爸爸買 2330 500股 60000 0822 - 零股交易
- 媽媽賣 5483 1張 120000 0823 - 用代號交易

📊 查詢功能：
- 總覽 - 所有帳戶總覽
- 爸爸查詢 - 個人資金和持股
- 交易記錄 - 所有交易歷史
- 交易記錄 爸爸 - 個人交易記錄
- 成本查詢 爸爸 台積電 - 持股成本分析
- 帳戶列表 - 查看所有帳戶

💹 即時損益功能：
- 即時損益 - 查看所有帳戶即時損益
- 即時損益 爸爸 - 查看個人即時損益
- 股價查詢 台積電 - 查詢即時股價

📝 新版特色：
• 🆕 支援「張」和「股」單位：
  - 10張 = 10,000股（整張交易）
  - 500股 = 零股交易
  - 純數字智能判斷：≤1000視為張數，>1000視為股數

• 🆕 智能股票識別：
  - 可用股票名稱：台積電、鴻海、中美晶
  - 可用股票代號：2330、2317、5483
  - 模糊搜尋：輸入「台積」自動匹配「台積電」

• 🆕 金額保持手動輸入：
  - 包含手續費和稅的實際交易金額
  - 買入：實付金額（含手續費）
  - 賣出：實收金額（扣除手續費和稅）

• 💡 智能持股顯示：
  - 自動轉換適當單位顯示
  - 5000股 → 5張
  - 5500股 → 5張500股

☁️ v2.3 新功能：
• ✅ 大幅簡化輸入格式
• ✅ 智能單位轉換
• ✅ 股票代號自動記憶
• ✅ 模糊搜尋股票
• ✅ Google Sheets 雲端同步
• ✅ 即時股價查詢
• ✅ 未實現損益計算

💡 範例對比：
舊格式：爸爸買 中美晶 5483 1000 107653 0915
新格式：爸爸買 中美晶 1張 107653 0915
更簡化：爸爸買 5483 1張 107653 0915"""


# 建立全域實例
stock_manager = StockManager()


# 對外接口函數，供 main.py 使用
def handle_stock_command(message_text):
    """處理股票指令 - 對外接口"""
    return stock_manager.handle_command(message_text)


def get_stock_summary(account_name=None):
    """獲取股票摘要 - 對外接口"""
    stock_manager.check_and_reload_if_needed()
    
    if account_name:
        return stock_manager.get_account_summary(account_name)
    else:
        return stock_manager.get_all_accounts_summary()


def get_stock_transactions(account_name=None, limit=10):
    """獲取交易記錄 - 對外接口"""
    stock_manager.check_and_reload_if_needed()
    
    return stock_manager.get_transaction_history(account_name, limit)


def get_stock_cost_analysis(account_name, stock_code):
    """獲取成本分析 - 對外接口"""
    stock_manager.check_and_reload_if_needed()
    
    return stock_manager.get_cost_analysis(account_name, stock_code)


def get_stock_account_list():
    """獲取帳戶列表 - 對外接口"""
    stock_manager.check_and_reload_if_needed()
    
    return stock_manager.get_account_list()


def get_stock_realtime_pnl(account_name=None):
    """獲取即時損益 - 對外接口"""
    return stock_manager.get_realtime_pnl(account_name)


def get_stock_help():
    """獲取股票幫助 - 對外接口"""
    return stock_manager.get_help_text()


def is_stock_command(message_text):
    """判斷是否為股票指令 - 對外接口"""
    stock_keywords = ['買入', '賣出', '入帳', '提款', '新增帳戶', '持有', '設定代號']
    return any(keyword in message_text for keyword in stock_keywords) or \
           re.match(r'.+?(買|賣|持有)\s+', message_text) is not None


def is_stock_query(message_text):
    """判斷是否為股票查詢指令 - 對外接口 (修正版)"""
    # 明確的股票查詢關鍵字
    stock_specific_patterns = [
        '總覽', '帳戶列表', '股票幫助', '交易記錄', '成本查詢',
        '即時損益', '股價查詢', '股價', '檢查代號', '批量設定代號',
        '估價查詢', '即時股價查詢'
    ]
    
    # 檢查是否包含明確的股票相關關鍵字
    if any(pattern in message_text for pattern in stock_specific_patterns):
        return True
    
    # 檢查是否以「即時損益」或「即時股價查詢」開頭
    if message_text.startswith('即時損益') or message_text.startswith('估價查詢'):
        return True
    
    # 檢查是否為明確的帳戶名稱查詢格式（避免誤判單純的「查詢」）
    if message_text.endswith('查詢') and len(message_text) > 2:
        account_part = message_text[:-2].strip()
        
        # 排除一些明顯不是帳戶名稱的查詢
        non_account_queries = [
            '待辦', '任務', 'todo', '提醒', '清單', 
            '生理期', '帳單', '卡費', '股票', '股價',
            '成本', '損益', '代號', '交易'
        ]
        
        # 如果查詢內容包含非帳戶相關關鍵字，不視為股票查詢
        if any(keyword in account_part for keyword in non_account_queries):
            return False
            
        # 如果是純粹的「查詢」，不視為股票查詢
        if account_part == '':
            return False
            
        # 檢查是否可能是帳戶名稱（通常是中文姓名或簡短稱呼）
        if len(account_part) <= 4 and account_part.replace(' ', ''):
            return True
    
    return False


if __name__ == "__main__":
    sm = StockManager()
    print("=== 測試新格式持有 ===")
    print(sm.handle_command("爸爸持有 台積電 10張 500000"))
    print()
    print("=== 測試新格式買入 ===")
    print(sm.handle_command("爸爸買 2330 5張 300000 0820"))
    print()
    print("=== 測試零股交易 ===")
    print(sm.handle_command("媽媽買 中美晶 500股 60000 0821"))
    print()
    print("=== 測試查詢 ===")
    print(sm.get_account_summary("爸爸"))
    print()
    print("=== 測試總覽 ===")
    print(sm.get_all_accounts_summary()) """
stock_manager.py - 改進版股票記帳模組 + Google Sheets 整合
多帳戶股票記帳系統 v2.3 - 簡化輸入版
"""
import re
import os
import json
from datetime import datetime
import pytz
import gspread
from google.oauth2.service_account import Credentials
import traceback

# 設定台灣時區
TAIWAN_TZ = pytz.timezone('Asia/Taipei')

class StockManager:
    """股票記帳管理器 - 整合 Google Sheets"""
    
    def __init__(self):
        """初始化股票資料和 Google Sheets 連接"""
        # 初始化資料結構
        self.stock_data = {
            'accounts': {},
            'transactions': [],
            'stock_codes': {},
            'stock_names': {}  # 新增：代號到名稱的對應
        }
        
        # Google Sheets 設定
        self.spreadsheet_url = "https://docs.google.com/spreadsheets/d/1EACr2Zu7_regqp3Po7AlNE4ZcjazKbgyvz-yYNYtcCs/edit?usp=sharing"
        self.gc = None
        self.sheet = None
        self.sheets_enabled = False
        self.last_sync_time = None
        
        # 初始化 Google Sheets 連接
        self.init_google_sheets()
        
        # 從 Google Sheets 載入資料
        if self.sheets_enabled:
            self.load_from_sheets_debug()
        else:
            print("📊 股票記帳模組初始化完成（記憶體模式）")
    
    def init_google_sheets(self):
        """初始化 Google Sheets 連接"""
        try:
            creds_json = os.getenv('GOOGLE_SERVICE_ACCOUNT_JSON')
            
            if not creds_json:
                print("⚠️ 未找到 GOOGLE_SERVICE_ACCOUNT_JSON 環境變數，使用記憶體模式")
                return False
            
            creds_dict = json.loads(creds_json)
            credentials = Credentials.from_service_account_info(
                creds_dict,
                scopes=[
                    'https://spreadsheets.google.com/feeds',
                    'https://www.googleapis.com/auth/drive'
                ]
            )
            
            self.gc = gspread.authorize(credentials)
            self.sheet = self.gc.open_by_url(self.spreadsheet_url)
            
            print("✅ Google Sheets 連接成功")
            self.sheets_enabled = True
            return True
            
        except json.JSONDecodeError as e:
            print(f"❌ JSON 格式錯誤: {e}")
            print("📝 將使用記憶體模式運行")
            return False
        except Exception as e:
            print(f"❌ Google Sheets 連接失敗: {e}")
            print("📝 將使用記憶體模式運行")
            return False
    
    def load_from_sheets_debug(self):
        """從 Google Sheets 載入資料"""
        if not self.sheets_enabled:
            return
        
        try:
            print("🔄 載入 Google Sheets 資料...")
            
            worksheets = self.sheet.worksheets()
            print(f"📋 找到 {len(worksheets)} 個工作表")
            
            # 載入帳戶資訊
            try:
                accounts_sheet = self.sheet.worksheet("帳戶資訊")
                accounts_data = accounts_sheet.get_all_records()
                
                for row in accounts_data:
                    if row.get('帳戶名稱'):
                        self.stock_data['accounts'][row['帳戶名稱']] = {
                            'cash': int(row.get('現金餘額', 0)),
                            'stocks': {},
                            'created_date': row.get('建立日期', self.get_taiwan_time())
                        }
                print(f"✅ 載入 {len(self.stock_data['accounts'])} 個帳戶")
                
            except Exception as e:
                print(f"❌ 載入帳戶資訊失敗: {e}")
            
            # 載入持股明細
            try:
                holdings_sheet = None
                for ws in worksheets:
                    if '持股明細' in ws.title.strip():
                        holdings_sheet = ws
                        break
                
                if holdings_sheet:
                    holdings_data = holdings_sheet.get_all_records()
                    holdings_count = 0
                    
                    for row in holdings_data:
                        account_name = row.get('帳戶名稱')
                        stock_name = row.get('股票名稱')
                        stock_code = row.get('股票代號')
                        
                        if account_name and stock_name and account_name in self.stock_data['accounts']:
                            self.stock_data['accounts'][account_name]['stocks'][stock_name] = {
                                'quantity': int(row.get('持股數量', 0)),
                                'avg_cost': float(row.get('平均成本', 0)),
                                'total_cost': int(row.get('總成本', 0)),
                                'stock_code': str(stock_code) if stock_code else None
                            }
                            
                            # 建立雙向對應
                            if stock_code:
                                self.stock_data['stock_codes'][stock_name] = str(stock_code)
                                self.stock_data['stock_names'][str(stock_code)] = stock_name
                            
                            holdings_count += 1
                    
                    print(f"✅ 載入 {holdings_count} 筆持股記錄")
                    print(f"✅ 載入 {len(self.stock_data['stock_codes'])} 個股票代號")
                else:
                    print("⚠️ 找不到持股明細工作表")
                
            except Exception as e:
                print(f"❌ 載入持股明細失敗: {e}")
                
            # 載入交易記錄
            try:
                transactions_sheet = self.sheet.worksheet("交易記錄")
                transactions_data = transactions_sheet.get_all_records()
                
                for row in transactions_data:
                    if row.get('交易ID'):
                        transaction = {
                            'id': int(row['交易ID']),
                            'type': row.get('類型', ''),
                            'account': row.get('帳戶', ''),
                            'stock_code': row.get('股票名稱') if row.get('股票名稱') else None,
                            'quantity': int(row.get('數量', 0)),
                            'amount': int(row.get('金額', 0)),
                            'price_per_share': float(row.get('單價', 0)) if row.get('單價') else 0,
                            'date': row.get('日期', ''),
                            'cash_after': int(row.get('現金餘額', 0)),
                            'created_at': row.get('建立時間', ''),
                            'profit_loss': float(row.get('損益', 0)) if row.get('損益') else None
                        }
                        self.stock_data['transactions'].append(transaction)
                
                print(f"✅ 載入 {len(self.stock_data['transactions'])} 筆交易記錄")
                
            except Exception as e:
                print(f"❌ 載入交易記錄失敗: {e}")
            
            print(f"✅ 資料載入完成")
            
        except Exception as e:
            print(f"❌ 載入 Google Sheets 資料失敗: {e}")
            traceback.print_exc()
    
    def check_and_reload_if_needed(self):
        """檢查是否需要重新載入資料"""
        if not self.sheets_enabled:
            return
        
        import time
        current_time = time.time()
        
        if (self.last_sync_time is None or 
            current_time - self.last_sync_time > 30):
            print("🔄 檢測到可能的外部修改，重新載入資料...")
            self.reload_data_from_sheets()

    def reload_data_from_sheets(self):
        """重新從 Google Sheets 載入最新資料"""
        if self.sheets_enabled:
            print("🔄 重新載入 Google Sheets 最新資料...")
            self.stock_data = {'accounts': {}, 'transactions': [], 'stock_codes': {}, 'stock_names': {}}
            self.load_from_sheets_debug()

    def sync_to_sheets_safe(self):
        """安全同步資料到 Google Sheets"""
        if not self.sheets_enabled:
            return False
        
        try:
            import time
            self.last_sync_time = time.time()
            
            print("🔄 安全同步資料到 Google Sheets...")
            
            # 同步帳戶資訊
            print("📊 同步帳戶資訊...")
            try:
                accounts_sheet = self.sheet.worksheet("帳戶資訊")
                
                try:
                    current_header = accounts_sheet.row_values(1)
                    expected_header = ['帳戶名稱', '現金餘額', '建立日期']
                    if current_header != expected_header:
                        accounts_sheet.update('A1:C1', [expected_header])
                except:
                    accounts_sheet.update('A1:C1', [['帳戶名稱', '現金餘額', '建立日期']])
                
                data_rows = []
                for account_name, account_data in self.stock_data['accounts'].items():
                    data_rows.append([
                        account_name,
                        account_data['cash'],
                        account_data['created_date']
                    ])
                
                if data_rows:
                    range_name = f"A2:C{len(data_rows) + 1}"
                    accounts_sheet.update(range_name, data_rows)
                    
                    current_rows = len(accounts_sheet.get_all_values())
                    if current_rows > len(data_rows) + 1:
                        clear_range = f"A{len(data_rows) + 2}:C{current_rows}"
                        accounts_sheet.batch_clear([clear_range])
                
                print("✅ 帳戶資訊同步成功")
            except Exception as e:
                print(f"❌ 同步帳戶資訊失敗: {e}")
                return False
            
            # 同步持股明細
            print("📈 同步持股明細...")
            try:
                holdings_sheet = None
                worksheets = self.sheet.worksheets()
                for ws in worksheets:
                    if '持股明細' in ws.title.strip():
                        holdings_sheet = ws
                        break
                
                if holdings_sheet:
                    try:
                        expected_header = ['帳戶名稱', '股票名稱', '股票代號', '持股數量', '平均成本', '總成本']
                        holdings_sheet.update('A1:F1', [expected_header])
                    except:
                        pass
                    
                    data_rows = []
                    for account_name, account_data in self.stock_data['accounts'].items():
                        for stock_name, stock_data in account_data['stocks'].items():
                            stock_code = stock_data.get('stock_code', '')
                            data_rows.append([
                                account_name,
                                stock_name,
                                stock_code,
                                stock_data['quantity'],
                                stock_data['avg_cost'],
                                stock_data['total_cost']
                            ])
                    
                    if data_rows:
                        range_name = f"A2:F{len(data_rows) + 1}"
                        holdings_sheet.update(range_name, data_rows)
                        
                        current_rows = len(holdings_sheet.get_all_values())
                        if current_rows > len(data_rows) + 1:
                            clear_range = f"A{len(data_rows) + 2}:F{current_rows}"
                            holdings_sheet.batch_clear([clear_range])
                    else:
                        current_rows = len(holdings_sheet.get_all_values())
                        if current_rows > 1:
                            clear_range = f"A2:F{current_rows}"
                            holdings_sheet.batch_clear([clear_range])
                    
                    print("✅ 持股明細同步成功")
                else:
                    print("❌ 找不到持股明細工作表")
                    return False
            except Exception as e:
                print(f"❌ 同步持股明細失敗: {e}")
                return False
            
            # 同步交易記錄
            print("📋 同步交易記錄...")
            try:
                transactions_sheet = self.sheet.worksheet("交易記錄")
                
                try:
                    expected_header = ['交易ID', '類型', '帳戶', '股票名稱', '數量', '金額', '單價', '日期', '現金餘額', '建立時間', '損益']
                    transactions_sheet.update('A1:K1', [expected_header])
                except:
                    pass
                
                data_rows = []
                for transaction in self.stock_data['transactions']:
                    data_rows.append([
                        transaction['id'],
                        transaction['type'],
                        transaction['account'],
                        transaction.get('stock_code', ''),
                        transaction['quantity'],
                        transaction['amount'],
                        transaction.get('price_per_share', 0),
                        transaction['date'],
                        transaction['cash_after'],
                        transaction['created_at'],
                        transaction.get('profit_loss', '')
                    ])
                
                if data_rows:
                    range_name = f"A2:K{len(data_rows) + 1}"
                    transactions_sheet.update(range_name, data_rows)
                    
                    current_rows = len(transactions_sheet.get_all_values())
                    if current_rows > len(data_rows) + 1:
                        clear_range = f"A{len(data_rows) + 2}:K{current_rows}"
                        transactions_sheet.batch_clear([clear_range])
                else:
                    current_rows = len(transactions_sheet.get_all_values())
                    if current_rows > 1:
                        clear_range = f"A2:K{current_rows}"
                        transactions_sheet.batch_clear([clear_range])
                
                print("✅ 交易記錄同步成功")
            except Exception as e:
                print(f"❌ 同步交易記錄失敗: {e}")
                return False
            
            print("✅ 安全同步完成")
            return True
            
        except Exception as e:
            print(f"❌ 安全同步失敗: {e}")
            traceback.print_exc()
            return False
    
    def get_taiwan_time(self):
        """獲取台灣時間"""
        return datetime.now(TAIWAN_TZ).strftime('%Y/%m/%d %H:%M:%S')
    
    def get_or_create_account(self, account_name):
        """獲取或建立帳戶"""
        if account_name not in self.stock_data['accounts']:
            self.stock_data['accounts'][account_name] = {
                'cash': 0,
                'stocks': {},
                'created_date': self.get_taiwan_time()
            }
            return True
        return False
    
    def resolve_stock_info(self, stock_input):
        """解析股票資訊 - 支援股票名稱和代號"""
        stock_input = stock_input.strip()
        
        # 檢查是否為純數字（股票代號）
        if stock_input.isdigit():
            stock_code = stock_input
            # 從已知的代號對應中找股票名稱
            stock_name = self.stock_data['stock_names'].get(stock_code)
            if not stock_name:
                # 如果沒有對應，使用代號作為名稱
                stock_name = f"股票{stock_code}"
            return stock_name, stock_code
        
        # 檢查是否為已知的股票名稱
        elif stock_input in self.stock_data['stock_codes']:
            stock_name = stock_input
            stock_code = self.stock_data['stock_codes'][stock_input]
            return stock_name, stock_code
        
        # 模糊搜尋現有股票名稱
        else:
            for existing_name in self.stock_data['stock_codes'].keys():
                if stock_input in existing_name or existing_name in stock_input:
                    stock_name = existing_name
                    stock_code = self.stock_data['stock_codes'][existing_name]
                    return stock_name, stock_code
            
            # 如果都找不到，返回輸入的名稱和空代號
            return stock_input, None
    
    def parse_quantity_unit(self, quantity_str):
        """解析數量和單位 - 支援張和股"""
        quantity_str = quantity_str.strip()
        
        # 檢查是否包含"張"
        if '張' in quantity_str:
            quantity = int(quantity_str.replace('張', ''))
            actual_quantity = quantity * 1000  # 1張 = 1000股
            unit = '張'
            return actual_quantity, quantity, unit
        
        # 檢查是否包含"股"
        elif '股' in quantity_str:
            quantity = int(quantity_str.replace('股', ''))
            actual_quantity = quantity
            unit = '股'
            return actual_quantity, quantity, unit
        
        # 純數字時的智能判斷
        else:
            quantity = int(quantity_str)
            # 小於等於1000時假設為張數，大於1000時假設為股數
            if quantity <= 1000:
                actual_quantity = quantity * 1000
                unit = '張'
                display_quantity = quantity
            else:
                actual_quantity = quantity
                unit = '股'
                display_quantity = quantity
            
            return actual_quantity, display_quantity, unit
    
    def get_stock_price(self, stock_code):
        """查詢股票即時價格 - 改進版"""
        
        # 修正問題股票代號
        if stock_code == '915':
            stock_code = '00915.TW'
        elif stock_code == '929':
            stock_code = '00929.TW'
        elif stock_code == '3078':
            stock_code = '3078.TWO'
        elif stock_code == '3374':
            stock_code = '3374.TWO'
        elif stock_code == '5483':
            stock_code = '5483.TWO'
        elif stock_code == '4541':
            stock_code = '4541.TWO'
        
        try:
            import requests
            import json
            import time
            
            # 確保股票代號格式正確
            if not stock_code.endswith('.TW') and not stock_code.endswith('.TWO'):
                formatted_code = f"{stock_code}.TW"
            else:
                formatted_code = stock_code
            
            # 方法1: Yahoo Finance API
            try:
                url = f"https://query1.finance.yahoo.com/v8/finance/chart/{formatted_code}"
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                }
                
                response = requests.get(url, headers=headers, timeout=10)
                response.raise_for_status()
                data = response.json()
                
                if (data.get('chart') and 
                    data['chart'].get('result') and 
                    len(data['chart']['result']) > 0 and
                    data['chart']['result'][0].get('meta')):
                    
                    meta = data['chart']['result'][0]['meta']
                    price = meta.get('regularMarketPrice')
                    
                    if price and price > 0:
                        print(f"✅ 取得 {stock_code} 股價: {price}")
                        return round(float(price), 2)
                
            except requests.exceptions.RequestException as e:
                print(f"⚠️ Yahoo Finance API 請求失敗: {e}")
            except (KeyError, TypeError, ValueError) as e:
                print(f"⚠️ Yahoo Finance 資料解析失敗: {e}")
            
            print(f"⚠️ {stock_code} 股價查詢失敗")
            return None
                
        except Exception as e:
            print(f"⚠️ 股價查詢發生未預期錯誤: {e}")
            return None
    
    def set_stock_code(self, stock_name, stock_code):
        """設定股票代號對應"""
        self.stock_data['stock_codes'][stock_name] = stock_code
        self.stock_data['stock_names'][stock_code] = stock_name
        return f"✅ 已設定 {stock_name} 代號為 {stock_code}"
    
    def get_missing_stock_codes(self, account_name=None):
        """檢查缺少代號的股票"""
        accounts_to_check = {account_name: self.stock_data['accounts'][account_name]} if account_name else self.stock_data['accounts']
        
        missing_stocks = set()
        
        for acc_name, account in accounts_to_check.items():
            for stock_name, stock_data in account['stocks'].items():
                if not stock_data.get('stock_code') and stock_name not in self.stock_data['stock_codes']:
                    missing_stocks.add(stock_name)
        
        if missing_stocks:
            result = "⚠️ 以下股票尚未設定代號：\n\n"
            for stock in sorted(missing_stocks):
                result += f"📈 {stock}\n"
            result += "\n💡 請使用新格式重新交易來設定代號"
            return result
        else:
            return "✅ 所有持股都已設定股票代號"
    
    def get_realtime_pnl(self, account_name=None):
        """獲取即時損益 - 改進版"""
        if account_name and account_name not in self.stock_data['accounts']:
            return f"❌ 帳戶「{account_name}」不存在"
        
        accounts_to_check = {account_name: self.stock_data['accounts'][account_name]} if account_name else self.stock_data['accounts']
        
        result = f"💹 {'即時損益' if not account_name else f'{account_name} 即時損益'}：\n\n"
        
        total_cost = 0
        total_value = 0
        has_price_data = False
        failed_stocks = []
        
        for acc_name, account in accounts_to_check.items():
            if not account['stocks']:
                continue
                
            result += f"👤 {acc_name}：\n"
            account_cost = 0
            account_value = 0
            
            for stock_name, holding in account['stocks'].items():
                cost = holding['total_cost']
                account_cost += cost
                
                # 優先從持股記錄取得股票代號
                stock_code = holding.get('stock_code') or self.stock_data['stock_codes'].get(stock_name)
                
                if stock_code:
                    print(f"🔍 正在查詢 {stock_name} ({stock_code}) 的股價...")
                    current_price = self.get_stock_price(stock_code)
                    
                    if current_price:
                        current_value = holding['quantity'] * current_price
                        pnl = current_value - cost
                        pnl_percent = (pnl / cost) * 100
                        
                        account_value += current_value
                        has_price_data = True
                        
                        pnl_text = f"🟢 +{pnl:,.0f}元 (+{pnl_percent:.1f}%)" if pnl > 0 else f"🔴 {pnl:,.0f}元 ({pnl_percent:.1f}%)" if pnl < 0 else "💫 損益兩平"
                        
                        result += f"   📈 {stock_name} ({stock_code})\n"
                        result += f"      💰 成本：{cost:,}元 ({holding['avg_cost']}元/股)\n"
                        result += f"      💎 現值：{current_value:,}元 ({current_price}元/股)\n"
                        result += f"      {pnl_text}\n\n"
                    else:
                        failed_stocks.append(f"{stock_name} ({stock_code})")
                        result += f"   📈 {stock_name} ({stock_code}) - ❌ 無法取得股價\n"
                        result += f"      💰 成本：{cost:,}元 ({holding['avg_cost']}元/股)\n"
                        result += f"      ⚠️ 請檢查股票代號或稍後再試\n\n"
                else:
                    result += f"   📈 {stock_name} - ⚠️ 缺少股票代號\n"
                    result += f"      💰 成本：{cost:,}元\n"
                    result += f"      💡 請更新交易時包含股票代號\n\n"
            
            total_cost += account_cost
            total_value += account_value
        
        if has_price_data and total_value > 0:
            total_pnl = total_value - total_cost
            total_pnl_percent = (total_pnl / total_cost) * 100
            total_pnl_text = f"🟢 +{total_pnl:,.0f}元 (+{total_pnl_percent:.1f}%)" if total_pnl > 0 else f"🔴 {total_pnl:,.0f}元 ({total_pnl_percent:.1f}%)"
            
            result += f"📊 總投資成本：{total_cost:,}元\n"
            result += f"💎 總投資現值：{total_value:,}元\n"
            result += f"💹 總未實現損益：{total_pnl_text}\n\n"
        
        # 顯示失敗的股票查詢
        if failed_stocks:
            result += f"⚠️ 以下股票無法取得即時股價：\n"
            for stock in failed_stocks:
                result += f"   • {stock}\n"
            result += f"\n💡 可能原因：\n"
            result += f"   • 非交易時間（平日 09:00-13:30）\n"
            result += f"   • 股票暫停交易或已下市\n"
            result += f"   • 網路連線問題\n"
            result += f"   • API 服務暫時不可用\n\n"
        
        result += "💡 提示：\n"
        result += "• 新交易請使用格式：爸爸買 台積電 10張 500000 0820\n"
        result += "• 支援單位：張（1張=1000股）、股（零股）\n"
        result += "• 可用股票代號：爸爸買 2330 5張 600000 0820\n"
        result += "• 股價資料來源：Yahoo Finance\n"
        result += "• 交易時間：週一至週五 09:00-13:30"
        
        return result
    
    def parse_command(self, message_text):
        """解析股票相關指令 - 新版支援張/股單位"""
        message_text = message_text.strip()
        
        if message_text == '批量設定代號':
            return {'type': 'batch_code_guide'}
        
        elif match := re.match(r'檢查代號(?:\s+(.+))?', message_text):
            account_name = match.group(1).strip() if match.group(1) else None
            return {'type': 'check_codes', 'account': account_name}
        
        elif match := re.match(r'設定代號\s+(.+?)\s+(\w+)', message_text):
            stock_name, stock_code = match.groups()
            return {'type': 'set_code', 'stock_name': stock_name.strip(), 'stock_code': stock_code.strip()}
        
        elif match := re.match(r'(?:股價查詢|股價|估價查詢)\s+(.+)', message_text):
            stock_name = match.group(1).strip()
            return {'type': 'price_query', 'stock_name': stock_name}
        
        elif match := re.match(r'(.+?)入帳\s*(\d+)', message_text):
            account, amount = match.groups()
            return {'type': 'deposit', 'account': account.strip(), 'amount': int(amount)}
