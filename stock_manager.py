"""
stock_manager.py - 獨立股票記帳模組 + Google Sheets 整合
多帳戶股票記帳系統 v2.3 - 簡化輸入版 (支援張/零股格式)
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
            'stock_codes': {}
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
                            
                            # 同時建立股票代號對應
                            if stock_code:
                                self.stock_data['stock_codes'][stock_name] = str(stock_code)
                            
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
            self.stock_data = {'accounts': {}, 'transactions': [], 'stock_codes': {}}
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
        result += "• 新交易請使用格式：爸爸買 台積電 2330 1張 600000 0820\n"
        result += "• 零股交易：爸爸買 台積電 500 300000 0820\n"
        result += "• 股價資料來源：Yahoo Finance\n"
        result += "• 交易時間：週一至週五 09:00-13:30\n"
        result += "• 如持續無法取得股價，請檢查股票代號是否正確"
        
        return result
    
    def parse_quantity_smart(self, quantity_str):
        """智能解析數量 - 支援張/零股格式"""
        if '張' in quantity_str:
            # 張數格式：1張、2張、0.5張
            num = float(quantity_str.replace('張', ''))
            return int(num * 1000)
        else:
            # 純數字視為零股：100、500、300
            return int(quantity_str)
    
    def format_date(self, date_str):
        """格式化日期"""
        if not date_str:
            return self.get_taiwan_time().split(' ')[0]
        
        try:
            year = datetime.now().year
            month = int(date_str[:2])
            day = int(date_str[2:])
            return f"{year}/{month:02d}/{day:02d}"
        except:
            return date_str
    
    def parse_command(self, message_text):
        """解析股票相關指令 - 增強版支援張/零股格式"""
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
        
        elif match := re.match(r'(.+?)提款\s*(\d+)', message_text):
            account, amount = match.groups()
            return {'type': 'withdraw', 'account': account.strip(), 'amount': int(amount)}
        
        # 持有格式 - 支援張/零股
        elif match := re.match(r'(.+?)持有\s+(.+?)\s+(\w+)\s+(.+?)\s+(\d+)', message_text):
            account, stock_name, stock_code, quantity_str, total_cost = match.groups()
            quantity = self.parse_quantity_smart(quantity_str)
            return {'type': 'holding', 'account': account.strip(), 'stock_name': stock_name.strip(), 
                   'stock_code': stock_code.strip(), 'quantity': quantity, 'total_cost': int(total_cost)}
        
        # 完整格式（包含代號）- 優先匹配更具體的格式
        elif match := re.match(r'(.+?)(買|賣)\s+(.+?)\s+(.+?)\s+(\w+)\s+(\d+)\s+(\d{4})', message_text):
            account, action, stock_name, quantity_str, stock_code, amount, date = match.groups()
            
            # 判斷哪個是股票代號 - 股票代號通常是4位數字或包含字母
            if stock_code.isdigit() and len(stock_code) == 4:
                # stock_code 位置是股票代號
                quantity = self.parse_quantity_smart(quantity_str)
                formatted_date = self.format_date(date)
                return {'type': action, 'account': account.strip(), 'stock_name': stock_name.strip(), 
                       'stock_code': stock_code.strip(), 'quantity': quantity, 'amount': int(amount), 'date': formatted_date}
            elif quantity_str.isdigit() and len(quantity_str) == 4:
                # quantity_str 位置是股票代號，stock_code 位置是數量
                quantity = self.parse_quantity_smart(stock_code)  # 實際上是數量
                actual_stock_code = quantity_str  # 實際上是股票代號
                formatted_date = self.format_date(date)
                return {'type': action, 'account': account.strip(), 'stock_name': stock_name.strip(), 
                       'stock_code': actual_stock_code, 'quantity': quantity, 'amount': int(amount), 'date': formatted_date}
        
        # 簡化格式（不包含代號）- 支援張/零股
        elif match := re.match(r'(.+?)(買|賣)\s+(.+?)\s+(\d+)\s+(\d+)\s*(\d{4})?', message_text):
            account, action, stock_name, quantity_str, amount, date = match.groups()
            
            # 檢查是否已知股票代號
            stock_code = self.stock_data['stock_codes'].get(stock_name.strip())
            if not stock_code:
                return {'type': 'need_stock_code', 'stock_name': stock_name.strip(), 'message': message_text}
            
            quantity = self.parse_quantity_smart(quantity_str)
            formatted_date = self.format_date(date) if date else self.get_taiwan_time().split(' ')[0]
            return {'type': action, 'account': account.strip(), 'stock_name': stock_name.strip(), 
                   'stock_code': stock_code, 'quantity': quantity, 'amount': int(amount), 'date': formatted_date}
        
        elif match := re.match(r'新增帳戶\s*(.+)', message_text):
            account = match.group(1).strip()
            return {'type': 'create_account', 'account': account}
        
        return None
    
    def handle_holding(self, account_name, stock_name, stock_code, quantity, total_cost):
        """處理持有股票設定"""
        is_new = self.get_or_create_account(account_name)
        
        avg_cost = round(total_cost / quantity, 2)
        
        self.stock_data['accounts'][account_name]['stocks'][stock_name] = {
            'quantity': quantity,
            'total_cost': total_cost,
            'avg_cost': avg_cost,
            'stock_code': stock_code
        }
        
        # 更新股票代號對應
        self.stock_data['stock_codes'][stock_name] = stock_code
        
        transaction = {
            'id': len(self.stock_data['transactions']) + 1,
            'type': '持有',
            'account': account_name,
            'stock_code': stock_name,
            'quantity': quantity,
            'amount': total_cost,
            'price_per_share': avg_cost,
            'date': self.get_taiwan_time().split(' ')[0],
            'cash_after': self.stock_data['accounts'][account_name]['cash'],
            'created_at': self.get_taiwan_time()
        }
        self.stock_data['transactions'].append(transaction)
        
        # 格式化數量顯示
        if quantity >= 1000 and quantity % 1000 == 0:
            quantity_display = f"{quantity // 1000}張"
        elif quantity >= 1000:
            full_lots = quantity // 1000
            remaining = quantity % 1000
            quantity_display = f"{full_lots}張{remaining}股"
        else:
            quantity_display = f"{quantity}股"
        
        result_msg = f"📊 {account_name} 持股設定成功！\n"
        if is_new:
            result_msg += f"🆕 已建立新帳戶\n"
        result_msg += f"🏷️ {stock_name} ({stock_code})\n"
        result_msg += f"📈 持股：{quantity_display}\n"
        result_msg += f"💰 總成本：{total_cost:,}元\n"
        result_msg += f"💵 平均成本：{avg_cost}元/股"
        
        if self.sheets_enabled:
            sync_success = self.sync_to_sheets_safe()
            if sync_success:
                result_msg += "\n☁️ 已同步到 Google Sheets"
            else:
                result_msg += "\n❌ Google Sheets 同步失敗"
        else:
            result_msg += "\n💾 已儲存到記憶體"
        
        return result_msg
    
    def handle_deposit(self, account_name, amount):
        """處理入帳"""
        is_new = self.get_or_create_account(account_name)
        self.stock_data['accounts'][account_name]['cash'] += amount
        
        transaction = {
            'id': len(self.stock_data['transactions']) + 1,
            'type': '入帳',
            'account': account_name,
            'stock_code': None,
            'quantity': 0,
            'amount': amount,
            'price_per_share': 0,
            'date': self.get_taiwan_time().split(' ')[0],
            'cash_after': self.stock_data['accounts'][account_name]['cash'],
            'created_at': self.get_taiwan_time()
        }
        self.stock_data['transactions'].append(transaction)
        
        result_msg = f"💰 {account_name} 入帳成功！\n"
        if is_new:
            result_msg += f"🆕 已建立新帳戶\n"
        result_msg += f"💵 入帳金額：{amount:,}元\n"
        result_msg += f"💳 帳戶餘額：{self.stock_data['accounts'][account_name]['cash']:,}元"
        
        if self.sheets_enabled:
            sync_success = self.sync_to_sheets_safe()
            if sync_success:
                result_msg += "\n☁️ 已同步到 Google Sheets"
            else:
                result_msg += "\n❌ Google Sheets 同步失敗"
        else:
            result_msg += "\n💾 已儲存到記憶體"
        
        return result_msg
    
    def handle_withdraw(self, account_name, amount):
        """處理提款"""
        if account_name not in self.stock_data['accounts']:
            return f"❌ 帳戶「{account_name}」不存在"
        
        account = self.stock_data['accounts'][account_name]
        if account['cash'] < amount:
            return f"❌ 餘額不足！\n💳 目前餘額：{account['cash']:,}元\n💸 提款金額：{amount:,}元"
        
        account['cash'] -= amount
        
        transaction = {
            'id': len(self.stock_data['transactions']) + 1,
            'type': '提款',
            'account': account_name,
            'stock_code': None,
            'quantity': 0,
            'amount': amount,
            'price_per_share': 0,
            'date': self.get_taiwan_time().split(' ')[0],
            'cash_after': account['cash'],
            'created_at': self.get_taiwan_time()
        }
        self.stock_data['transactions'].append(transaction)
        
        result_msg = f"💸 {account_name} 提款成功！\n💵 提款金額：{amount:,}元\n💳 帳戶餘額：{account['cash']:,}元"
        
        if self.sheets_enabled:
            sync_success = self.sync_to_sheets_safe()
            if sync_success:
                result_msg += "\n☁️ 已同步到 Google Sheets"
            else:
                result_msg += "\n❌ Google Sheets 同步失敗"
        else:
            result_msg += "\n💾 已儲存到記憶體"
        
        return result_msg
    
    def handle_buy(self, account_name, stock_name, stock_code, quantity, amount, date):
        """處理買入股票"""
        if account_name not in self.stock_data['accounts']:
            return f"❌ 帳戶「{account_name}」不存在"
        
        account = self.stock_data['accounts'][account_name]
        if account['cash'] < amount:
            return f"❌ 餘額不足！\n💳 目前餘額：{account['cash']:,}元\n💰 需要金額：{amount:,}元"
        
        account['cash'] -= amount
        price_per_share = round(amount / quantity, 2)
        
        if stock_name in account['stocks']:
            existing = account['stocks'][stock_name]
            total_quantity = existing['quantity'] + quantity
            total_cost = existing['total_cost'] + amount
            avg_cost = round(total_cost / total_quantity, 2)
            
            account['stocks'][stock_name] = {
                'quantity': total_quantity,
                'total_cost': total_cost,
                'avg_cost': avg_cost,
                'stock_code': stock_code
            }
        else:
            account['stocks'][stock_name] = {
                'quantity': quantity,
                'total_cost': amount,
                'avg_cost': price_per_share,
                'stock_code': stock_code
            }
        
        # 更新股票代號對應
        self.stock_data['stock_codes'][stock_name] = stock_code
        
        transaction = {
            'id': len(self.stock_data['transactions']) + 1,
            'type': '買入',
            'account': account_name,
            'stock_code': stock_name,
            'quantity': quantity,
            'amount': amount,
            'price_per_share': price_per_share,
            'date': date,
            'cash_after': account['cash'],
            'created_at': self.get_taiwan_time()
        }
        self.stock_data['transactions'].append(transaction)
        
        # 格式化數量顯示
        if quantity >= 1000 and quantity % 1000 == 0:
            quantity_display = f"{quantity // 1000}張"
        elif quantity >= 1000:
            full_lots = quantity // 1000
            remaining = quantity % 1000
            quantity_display = f"{full_lots}張{remaining}股"
        else:
            quantity_display = f"{quantity}股"
        
        stock_info = account['stocks'][stock_name]
        
        # 總持股顯示
        total_quantity = stock_info['quantity']
        if total_quantity >= 1000 and total_quantity % 1000 == 0:
            total_display = f"{total_quantity // 1000}張"
        elif total_quantity >= 1000:
            full_lots = total_quantity // 1000
            remaining = total_quantity % 1000
            total_display = f"{full_lots}張{remaining}股"
        else:
            total_display = f"{total_quantity}股"
        
        result_msg = f"📈 {account_name} 買入成功！\n\n🏷️ {stock_name} ({stock_code})\n📊 買入：{quantity_display} @ {price_per_share}元\n💰 實付：{amount:,}元\n📅 日期：{date}\n\n📋 持股狀況：\n📊 總持股：{total_display}\n💵 平均成本：{stock_info['avg_cost']}元/股\n💳 剩餘現金：{account['cash']:,}元"
        
        if self.sheets_enabled:
            sync_success = self.sync_to_sheets_safe()
            if sync_success:
                result_msg += "\n☁️ 已同步到 Google Sheets"
            else:
                result_msg += "\n❌ Google Sheets 同步失敗"
        else:
            result_msg += "\n💾 已儲存到記憶體"
        
        return result_msg
    
    def handle_sell(self, account_name, stock_name, stock_code, quantity, amount, date):
        """處理賣出股票"""
        if account_name not in self.stock_data['accounts']:
            return f"❌ 帳戶「{account_name}」不存在"
        
        account = self.stock_data['accounts'][account_name]
        if stock_name not in account['stocks']:
            return f"❌ 沒有持有「{stock_name}」"
        
        holding = account['stocks'][stock_name]
        if holding['quantity'] < quantity:
            # 格式化持股顯示
            if holding['quantity'] >= 1000 and holding['quantity'] % 1000 == 0:
                holding_display = f"{holding['quantity'] // 1000}張"
            elif holding['quantity'] >= 1000:
                full_lots = holding['quantity'] // 1000
                remaining = holding['quantity'] % 1000
                holding_display = f"{full_lots}張{remaining}股"
            else:
                holding_display = f"{holding['quantity']}股"
            
            # 格式化欲賣出數量顯示
            if quantity >= 1000 and quantity % 1000 == 0:
                sell_display = f"{quantity // 1000}張"
            elif quantity >= 1000:
                full_lots = quantity // 1000
                remaining = quantity % 1000
                sell_display = f"{full_lots}張{remaining}股"
            else:
                sell_display = f"{quantity}股"
            
            return f"❌ 持股不足！\n📊 目前持股：{holding_display}\n📤 欲賣出：{sell_display}"
        
        price_per_share = round(amount / quantity, 2)
        sell_cost = round(holding['avg_cost'] * quantity, 2)
        profit_loss = amount - sell_cost
        
        account['cash'] += amount
        
        remaining_quantity = holding['quantity'] - quantity
        if remaining_quantity > 0:
            remaining_cost = holding['total_cost'] - sell_cost
            account['stocks'][stock_name] = {
                'quantity': remaining_quantity,
                'total_cost': remaining_cost,
                'avg_cost': holding['avg_cost'],
                'stock_code': stock_code
            }
        else:
            del account['stocks'][stock_name]
            # 如果完全賣出，從股票代號對應中移除
            if stock_name in self.stock_data['stock_codes']:
                del self.stock_data['stock_codes'][stock_name]
        
        transaction = {
            'id': len(self.stock_data['transactions']) + 1,
            'type': '賣出',
            'account': account_name,
            'stock_code': stock_name,
            'quantity': quantity,
            'amount': amount,
            'price_per_share': price_per_share,
            'date': date,
            'cash_after': account['cash'],
            'created_at': self.get_taiwan_time(),
            'profit_loss': profit_loss
        }
        self.stock_data['transactions'].append(transaction)
        
        # 格式化賣出數量顯示
        if quantity >= 1000 and quantity % 1000 == 0:
            quantity_display = f"{quantity // 1000}張"
        elif quantity >= 1000:
            full_lots = quantity // 1000
            remaining = quantity % 1000
            quantity_display = f"{full_lots}張{remaining}股"
        else:
            quantity_display = f"{quantity}股"
        
        profit_text = f"💰 獲利：+{profit_loss:,}元" if profit_loss > 0 else f"💸 虧損：{profit_loss:,}元" if profit_loss < 0 else "💫 損益兩平"
        
        result = f"📉 {account_name} 賣出成功！\n\n🏷️ {stock_name} ({stock_code})\n📊 賣出：{quantity_display} @ {price_per_share}元\n💰 實收：{amount:,}元\n📅 日期：{date}\n\n💹 本次交易：\n💵 成本：{sell_cost:,}元\n{profit_text}\n💳 現金餘額：{account['cash']:,}元"
        
        if self.sheets_enabled:
            sync_success = self.sync_to_sheets_safe()
            if sync_success:
                result += "\n☁️ 已同步到 Google Sheets"
            else:
                result += "\n❌ Google Sheets 同步失敗"
        else:
            result += "\n💾 已儲存到記憶體"
        
        if remaining_quantity > 0:
            # 格式化剩餘持股顯示
            if remaining_quantity >= 1000 and remaining_quantity % 1000 == 0:
                remaining_display = f"{remaining_quantity // 1000}張"
            elif remaining_quantity >= 1000:
                full_lots = remaining_quantity // 1000
                remaining = remaining_quantity % 1000
                remaining_display = f"{full_lots}張{remaining}股"
            else:
                remaining_display = f"{remaining_quantity}股"
            
            result += f"\n\n📋 剩餘持股：{remaining_display}"
        else:
            result += f"\n\n✅ 已全部賣出 {stock_name}"
        
        return result
    
    def create_account(self, account_name):
        """建立新帳戶"""
        is_new = self.get_or_create_account(account_name)
        if is_new:
            result_msg = f"🆕 已建立帳戶「{account_name}」\n💡 可以開始入帳和交易了！"
            
            if self.sheets_enabled:
                sync_success = self.sync_to_sheets_safe()
                if sync_success:
                    result_msg += "\n☁️ 已同步到 Google Sheets"
                else:
                    result_msg += "\n❌ Google Sheets 同步失敗"
            else:
                result_msg += "\n💾 已儲存到記憶體"
            
            return result_msg
        else:
            return f"ℹ️ 帳戶「{account_name}」已存在"
    
    def get_account_summary(self, account_name):
        """獲取帳戶摘要"""
        if account_name not in self.stock_data['accounts']:
            return f"❌ 帳戶「{account_name}」不存在"
        
        account = self.stock_data['accounts'][account_name]
        
        result = f"📊 {account_name} 帳戶摘要：\n\n💳 現金餘額：{account['cash']:,}元\n"
        
        if account['stocks']:
            result += f"\n📈 持股明細：\n"
            total_investment = 0
            for stock_name, holding in account['stocks'].items():
                stock_code = holding.get('stock_code', '')
                code_display = f" ({stock_code})" if stock_code else ""
                
                # 格式化持股數量顯示
                quantity = holding['quantity']
                if quantity >= 1000 and quantity % 1000 == 0:
                    quantity_display = f"{quantity // 1000}張"
                elif quantity >= 1000:
                    full_lots = quantity // 1000
                    remaining = quantity % 1000
                    quantity_display = f"{full_lots}張{remaining}股"
                else:
                    quantity_display = f"{quantity}股"
                
                result += f"🏷️ {stock_name}{code_display}\n"
                result += f"   📊 {quantity_display} @ {holding['avg_cost']}元\n"
                result += f"   💰 投資成本：{holding['total_cost']:,}元\n\n"
                total_investment += holding['total_cost']
            
            total_assets = account['cash'] + total_investment
            result += f"💼 總投資：{total_investment:,}元\n"
            result += f"🏦 總資產：{total_assets:,}元"
        else:
            result += "\n📝 目前無持股"
        
        return result
    
    def get_all_accounts_summary(self):
        """獲取所有帳戶總覽"""
        if not self.stock_data['accounts']:
            return "📝 目前沒有任何帳戶\n💡 輸入「爸爸入帳 100000」來建立第一個帳戶\n💡 或輸入「爸爸持有 台積電 2330 1張 600000」設定現有持股"
        
        result = "🏦 家庭投資總覽：\n\n"
        
        total_cash = 0
        total_investment = 0
        all_stocks = {}
        
        for account_name, account in self.stock_data['accounts'].items():
            result += f"👤 {account_name}：\n"
            result += f"   💳 現金 {account['cash']:,}元\n"
            
            account_investment = 0
            if account['stocks']:
                for stock_name, holding in account['stocks'].items():
                    stock_code = holding.get('stock_code', '')
                    code_display = f" ({stock_code})" if stock_code else ""
                    
                    # 格式化持股數量顯示
                    quantity = holding['quantity']
                    if quantity >= 1000 and quantity % 1000 == 0:
                        quantity_display = f"{quantity // 1000}張"
                    elif quantity >= 1000:
                        full_lots = quantity // 1000
                        remaining = quantity % 1000
                        quantity_display = f"{full_lots}張{remaining}股"
                    else:
                        quantity_display = f"{quantity}股"
                    
                    result += f"   📈 {stock_name}{code_display} {quantity_display}\n"
                    account_investment += holding['total_cost']
                    
                    if stock_name in all_stocks:
                        all_stocks[stock_name] += holding['quantity']
                    else:
                        all_stocks[stock_name] = holding['quantity']
            
            if account_investment > 0:
                result += f"   💼 投資 {account_investment:,}元\n"
            
            total_cash += account['cash']
            total_investment += account_investment
            result += "\n"
        
        result += f"💰 總現金：{total_cash:,}元\n"
        result += f"📊 總投資：{total_investment:,}元\n"
        result += f"🏦 總資產：{total_cash + total_investment:,}元"
        
        if all_stocks:
            result += f"\n\n📈 家庭總持股：\n"
            for stock_name, total_quantity in all_stocks.items():
                # 格式化總持股數量顯示
                if total_quantity >= 1000 and total_quantity % 1000 == 0:
                    total_display = f"{total_quantity // 1000}張"
                elif total_quantity >= 1000:
                    full_lots = total_quantity // 1000
                    remaining = total_quantity % 1000
                    total_display = f"{full_lots}張{remaining}股"
                else:
                    total_display = f"{total_quantity}股"
                
                result += f"🏷️ {stock_name}：{total_display}\n"
        
        if self.sheets_enabled:
            result += f"\n☁️ 資料來源：Google Sheets"
        else:
            result += f"\n💾 資料儲存：記憶體模式"
        
        return result
    
    def get_transaction_history(self, account_name=None, limit=10):
        """獲取交易記錄"""
        transactions = self.stock_data['transactions']
        
        if account_name:
            transactions = [t for t in transactions if t['account'] == account_name]
            if not transactions:
                return f"📝 {account_name} 沒有交易記錄"
            title = f"📋 {account_name} 交易記錄 (最近{limit}筆)：\n\n"
        else:
            if not transactions:
                return "📝 目前沒有任何交易記錄"
            title = f"📋 所有交易記錄 (最近{limit}筆)：\n\n"
        
        recent_transactions = sorted(transactions, key=lambda x: x['created_at'], reverse=True)[:limit]
        
        result = title
        for i, t in enumerate(recent_transactions, 1):
            result += f"{i}. {t['type']} - {t['account']}\n"
            if t['stock_code']:
                # 格式化交易數量顯示
                quantity = t['quantity']
                if quantity >= 1000 and quantity % 1000 == 0:
                    quantity_display = f"{quantity // 1000}張"
                elif quantity >= 1000:
                    full_lots = quantity // 1000
                    remaining = quantity % 1000
                    quantity_display = f"{full_lots}張{remaining}股"
                else:
                    quantity_display = f"{quantity}股"
                
                result += f"   🏷️ {t['stock_code']} {quantity_display}\n"
                if t.get('price_per_share'):
                    result += f"   💰 {t['amount']:,}元 @ {t['price_per_share']}元/股\n"
                else:
                    result += f"   💰 {t['amount']:,}元\n"
            else:
                result += f"   💰 {t['amount']:,}元\n"
            result += f"   📅 {t['date']} 💳餘額 {t['cash_after']:,}元\n\n"
        
        if self.sheets_enabled:
            result += f"☁️ 資料來源：Google Sheets"
        else:
            result += f"💾 資料來源：記憶體"
        
        return result
    
    def get_cost_analysis(self, account_name, stock_input):
        """獲取特定股票的成本分析"""
        if account_name not in self.stock_data['accounts']:
            return f"❌ 帳戶「{account_name}」不存在"
        
        account = self.stock_data['accounts'][account_name]
        
        stock_name = None
        for name in account['stocks'].keys():
            if stock_input.lower() in name.lower() or name.lower() in stock_input.lower():
                stock_name = name
                break
        
        if not stock_name:
            return f"❌ {account_name} 沒有持有「{stock_input}」相關的股票"
        
        holding = account['stocks'][stock_name]
        stock_code = holding.get('stock_code', '')
        code_display = f" ({stock_code})" if stock_code else ""
        
        # 格式化持股數量顯示
        quantity = holding['quantity']
        if quantity >= 1000 and quantity % 1000 == 0:
            quantity_display = f"{quantity // 1000}張"
        elif quantity >= 1000:
            full_lots = quantity // 1000
            remaining = quantity % 1000
            quantity_display = f"{full_lots}張{remaining}股"
        else:
            quantity_display = f"{quantity}股"
        
        related_transactions = [
            t for t in self.stock_data['transactions'] 
            if t['account'] == account_name and t.get('stock_code') == stock_name
        ]
        
        result = f"📊 {account_name} - {stock_name}{code_display} 成本分析：\n\n"
        result += f"📈 目前持股：{quantity_display}\n"
        result += f"💰 平均成本：{holding['avg_cost']}元/股\n"
        result += f"💵 總投資：{holding['total_cost']:,}元\n\n"
        result += f"📋 交易歷史：\n"
        
        for t in related_transactions:
            # 格式化交易數量顯示
            t_quantity = t['quantity']
            if t_quantity >= 1000 and t_quantity % 1000 == 0:
                t_quantity_display = f"{t_quantity // 1000}張"
            elif t_quantity >= 1000:
                full_lots = t_quantity // 1000
                remaining = t_quantity % 1000
                t_quantity_display = f"{full_lots}張{remaining}股"
            else:
                t_quantity_display = f"{t_quantity}股"
            
            if t['type'] == '買入':
                result += f"📈 {t['date']} 買入 {t_quantity_display} @ {t['price_per_share']}元\n"
            elif t['type'] == '賣出':
                profit_loss = t.get('profit_loss', 0)
                profit_text = f" (獲利+{profit_loss:,})" if profit_loss > 0 else f" (虧損{profit_loss:,})" if profit_loss < 0 else " (損益兩平)"
                result += f"📉 {t['date']} 賣出 {t_quantity_display} @ {t['price_per_share']}元{profit_text}\n"
            elif t['type'] == '持有':
                result += f"📊 {t['date']} 設定持有 {t_quantity_display} @ {t['price_per_share']}元\n"
        
        if self.sheets_enabled:
            result += f"\n☁️ 資料來源：Google Sheets"
        else:
            result += f"\n💾 資料來源：記憶體"
        
        return result
    
    def get_account_list(self):
        """獲取帳戶列表"""
        if self.stock_data['accounts']:
            account_list = list(self.stock_data['accounts'].keys())
            result = f"👥 目前帳戶列表：\n\n" + "\n".join([f"👤 {name}" for name in account_list])
            if self.sheets_enabled:
                result += f"\n\n☁️ 資料來源：Google Sheets"
            else:
                result += f"\n\n💾 資料來源：記憶體"
            return result
        else:
            return "📝 目前沒有任何帳戶"
    
    def handle_command(self, message_text):
        """處理股票指令的主要函數"""
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
                    parsed['account'], parsed['stock_name'], parsed['stock_code'],
                    parsed['quantity'], parsed['total_cost']
                )
            
            elif parsed['type'] == '買':
                return self.handle_buy(
                    parsed['account'], parsed['stock_name'], parsed['stock_code'],
                    parsed['quantity'], parsed['amount'], parsed['date']
                )
            
            elif parsed['type'] == '賣':
                return self.handle_sell(
                    parsed['account'], parsed['stock_name'], parsed['stock_code'],
                    parsed['quantity'], parsed['amount'], parsed['date']
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
            
            elif parsed['type'] == 'need_stock_code':
                return f"❌ 「{parsed['stock_name']}」尚未設定股票代號\n💡 請使用完整格式：{parsed['message']} [股票代號]\n例如：{parsed['message']} 2330"
            
        except Exception as e:
            return f"❌ 處理失敗：{str(e)}\n💡 請檢查指令格式"
        
        return "❌ 未知的指令類型"
    
    def get_help_text(self):
        """獲取幫助訊息"""
        return """💰 多帳戶股票記帳功能 v2.3 - 簡化輸入版：

📋 帳戶管理：
- 爸爸入帳 50000 - 入金
- 媽媽提款 10000 - 提款  
- 新增帳戶 奶奶 - 建立帳戶

📊 持股設定（新格式 - 支援張/零股）：
- 爸爸持有 台積電 2330 1張 600000 - 設定現有持股（整張）
- 媽媽持有 鴻海 2317 500 52500 - 設定現有持股（零股）

📈 交易操作（新格式 - 支援張/零股）：
🔸 整張交易：
- 爸爸買 台積電 2330 1張 600000 0820 - 買1張台積電
- 媽媽賣 鴻海 2317 2張 210000 0821 - 賣2張鴻海

🔸 零股交易：
- 爸爸買 台積電 2330 500 300000 0820 - 買500股零股
- 媽媽賣 鴻海 100 10500 0821 - 賣100股零股

🔸 簡化格式（已設定代號後）：
- 爸爸買 台積電 1張 600000 0820
- 媽媽賣 鴻海 500 52500 0821

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

📝 新格式說明：
• 🆕 數量輸入方式：
  - 整張：1張、2張、0.5張（自動轉換為股數）
  - 零股：直接輸入數字 100、500、300（視為股數）
• 🆕 第一次交易需包含股票代號，之後可省略
• 日期：0820 = 8月20日，1225 = 12月25日
• 股票代號：台股請使用4位數代號（如：2330）

☁️ v2.3 新功能：
• 🆕 支援張/零股簡化輸入格式
• 🆕 智能數量識別（張 vs 零股）
• 🆕 更友善的持股數量顯示
• 🆕 股票代號記憶功能
• ✅ Google Sheets 雲端同步
• ✅ 支援自訂股票名稱
• ✅ 資料永久保存
• ✅ 即時股價查詢
• ✅ 未實現損益計算

💡 使用範例：
• 首次：爸爸買 台積電 2330 1張 600000 0820
• 後續：爸爸買 台積電 500 300000 0821
• 後續：爸爸賣 台積電 1張 650000 0825"""


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
    print("=== 測試持有（新格式）===")
    print(sm.handle_command("爸爸持有 台積電 2330 1張 600000"))
    print()
    print("=== 測試零股持有 ===")
    print(sm.handle_command("媽媽持有 鴻海 2317 500 52500"))
    print()
    print("=== 測試入帳 ===")
    print(sm.handle_command("爸爸入帳 100000"))
    print()
    print("=== 測試買入（新格式）===")
    print(sm.handle_command("爸爸買 台積電 2330 1張 600000 0820"))
    print()
    print("=== 測試零股買入 ===")
    print(sm.handle_command("媽媽買 鴻海 2317 300 31500 0821"))
    print()
    print("=== 測試簡化格式買入 ===")
    print(sm.handle_command("爸爸買 台積電 500 300000 0822"))
    print()
    print("=== 測試查詢 ===")
    print(sm.get_account_summary("爸爸"))
    print()
    print("=== 測試總覽 ===")
    print(sm.get_all_accounts_summary())
    print()
    print("=== 測試即時損益 ===")
    print(sm.get_realtime_pnl())
