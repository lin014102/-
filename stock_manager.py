def get_realtime_pnl(self, account_name=None):
        """獲取即時損益"""
        if account_name and account_name not in self.stock_data['accounts']:
            return f"❌ 帳戶「{account_name}」不存在"
        
        accounts_to_check = {account_name: self.stock_data['accounts'][account_name]} if account_name else self.stock_data['accounts']
        
        result = f"💹 {'即時損益' if not account_name else f'{account_name} 即時損益'}：\n\n"
        
        total_cost = 0
        total_value = 0
        has_price_data = False
        
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
                        result += f"   📈 {stock_name} ({stock_code}) - ⚠️ 無法取得股價\n"
                        result += f"      💰 成本：{cost:,}元\n\n"
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
        
        result += "💡 提示：\n"
        result += "• 新交易請使用格式：爸爸買 台積電 2330 100 50000 0820\n"
        result += "• 股價資料來源：Yahoo Finance\n"
        result += "• 股價可能有15分鐘延遲"
        
        return result"""
stock_manager.py - 獨立股票記帳模組 + Google Sheets 整合
多帳戶股票記帳系統 v2.1 - 即時損益版 - 完整修復版
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
            creds_json = os.getenv('GOOGLE_CREDENTIALS')
            
            if not creds_json:
                print("⚠️ 未找到 GOOGLE_CREDENTIALS 環境變數，使用記憶體模式")
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
            except Exception as e:
                print(f"❌ 同步持股明細失敗: {e}")
            
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
        """查詢股票即時價格"""
        try:
            import requests
            import json
            
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{stock_code}.TW"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            data = response.json()
            
            if data['chart']['result'] and data['chart']['result'][0]['meta']:
                price = data['chart']['result'][0]['meta']['regularMarketPrice']
                return round(price, 2)
            else:
                return None
                
        except Exception as e:
            print(f"⚠️ 股價查詢失敗: {e}")
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
            for stock_name in account['stocks'].keys():
                if stock_name not in self.stock_data['stock_codes']:
                    missing_stocks.add(stock_name)
        
        if missing_stocks:
            result = "⚠️ 以下股票尚未設定代號：\n\n"
            for stock in sorted(missing_stocks):
                result += f"📈 {stock}\n"
            result += "\n💡 使用方式：\n"
            result += "• 設定代號 股票名稱 代號\n"
            result += "• 或使用「批量設定代號」功能"
            return result
        else:
            return "✅ 所有持股都已設定股票代號"
    
    def get_realtime_pnl(self, account_name=None):
        """獲取即時損益"""
        if account_name and account_name not in self.stock_data['accounts']:
            return f"❌ 帳戶「{account_name}」不存在"
        
        accounts_to_check = {account_name: self.stock_data['accounts'][account_name]} if account_name else self.stock_data['accounts']
        
        result = f"💹 {'即時損益' if not account_name else f'{account_name} 即時損益'}：\n\n"
        
        total_cost = 0
        total_value = 0
        has_price_data = False
        
        for acc_name, account in accounts_to_check.items():
            if not account['stocks']:
                continue
                
            result += f"👤 {acc_name}：\n"
            account_cost = 0
            account_value = 0
            
            for stock_name, holding in account['stocks'].items():
                cost = holding['total_cost']
                account_cost += cost
                
                stock_code = self.stock_data['stock_codes'].get(stock_name)
                if stock_code:
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
                        result += f"   📈 {stock_name} ({stock_code}) - ⚠️ 無法取得股價\n"
                        result += f"      💰 成本：{cost:,}元\n\n"
                else:
                    result += f"   📈 {stock_name} - ⚠️ 請先設定股票代號\n"
                    result += f"      💰 成本：{cost:,}元\n"
                    result += f"      💡 使用：設定代號 {stock_name} XXXX\n\n"
            
            total_cost += account_cost
            total_value += account_value
        
        if has_price_data and total_value > 0:
            total_pnl = total_value - total_cost
            total_pnl_percent = (total_pnl / total_cost) * 100
            total_pnl_text = f"🟢 +{total_pnl:,.0f}元 (+{total_pnl_percent:.1f}%)" if total_pnl > 0 else f"🔴 {total_pnl:,.0f}元 ({total_pnl_percent:.1f}%)"
            
            result += f"📊 總投資成本：{total_cost:,}元\n"
            result += f"💎 總投資現值：{total_value:,}元\n"
            result += f"💹 總未實現損益：{total_pnl_text}\n\n"
        
        result += "💡 提示：\n"
        result += "• 使用「設定代號 股票名稱 代號」來設定股票代號\n"
        result += "• 股價資料來源：Yahoo Finance\n"
        result += "• 股價可能有15分鐘延遲"
        
        return result
    
    def parse_command(self, message_text):
        """解析股票相關指令"""
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
        
        elif match := re.match(r'(.+?)持有\s+(.+?)\s+(\w+)\s+(\d+)\s+(\d+)', message_text):
            account, stock_name, stock_code, quantity, total_cost = match.groups()
            return {'type': 'holding', 'account': account.strip(), 'stock_name': stock_name.strip(), 
                   'stock_code': stock_code.strip(), 'quantity': int(quantity), 'total_cost': int(total_cost)}
        
        elif match := re.match(r'(.+?)買\s+(.+?)\s+(\w+)\s+(\d+)\s+(\d+)\s+(\d{4})
        
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
        
        if self.sheets_enabled:
            self.sync_to_sheets_safe()
        
        result_msg = f"📊 {account_name} 持股設定成功！\n"
        if is_new:
            result_msg += f"🆕 已建立新帳戶\n"
        result_msg += f"🏷️ {stock_name} ({stock_code})\n"
        result_msg += f"📈 持股：{quantity}股\n"
        result_msg += f"💰 總成本：{total_cost:,}元\n"
        result_msg += f"💵 平均成本：{avg_cost}元/股"
        
        if self.sheets_enabled:
            result_msg += f"\n☁️ 已同步到 Google Sheets"
        else:
            result_msg += f"\n💾 已儲存到記憶體"
        
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
        
        if self.sheets_enabled:
            self.sync_to_sheets_safe()
        
        result_msg = f"💰 {account_name} 入帳成功！\n"
        if is_new:
            result_msg += f"🆕 已建立新帳戶\n"
        result_msg += f"💵 入帳金額：{amount:,}元\n"
        result_msg += f"💳 帳戶餘額：{self.stock_data['accounts'][account_name]['cash']:,}元"
        
        if self.sheets_enabled:
            result_msg += f"\n☁️ 已同步到 Google Sheets"
        else:
            result_msg += f"\n💾 已儲存到記憶體"
        
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
        
        if self.sheets_enabled:
            self.sync_to_sheets_safe()
        
        result_msg = f"💸 {account_name} 提款成功！\n💵 提款金額：{amount:,}元\n💳 帳戶餘額：{account['cash']:,}元"
        
        if self.sheets_enabled:
            result_msg += f"\n☁️ 已同步到 Google Sheets"
        else:
            result_msg += f"\n💾 已儲存到記憶體"
        
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
        
        if self.sheets_enabled:
            self.sync_to_sheets_safe()
        
        stock_info = account['stocks'][stock_name]
        result_msg = f"📈 {account_name} 買入成功！\n\n🏷️ {stock_name} ({stock_code})\n📊 買入：{quantity}股 @ {price_per_share}元\n💰 實付：{amount:,}元\n📅 日期：{date}\n\n📋 持股狀況：\n📊 總持股：{stock_info['quantity']}股\n💵 平均成本：{stock_info['avg_cost']}元/股\n💳 剩餘現金：{account['cash']:,}元"
        
        if self.sheets_enabled:
            result_msg += f"\n☁️ 已同步到 Google Sheets"
        else:
            result_msg += f"\n💾 已儲存到記憶體"
        
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
            return f"❌ 持股不足！\n📊 目前持股：{holding['quantity']}股\n📤 欲賣出：{quantity}股"
        
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
        
        if self.sheets_enabled:
            self.sync_to_sheets_safe()
        
        profit_text = f"💰 獲利：+{profit_loss:,}元" if profit_loss > 0 else f"💸 虧損：{profit_loss:,}元" if profit_loss < 0 else "💫 損益兩平"
        
        result = f"📉 {account_name} 賣出成功！\n\n🏷️ {stock_name} ({stock_code})\n📊 賣出：{quantity}股 @ {price_per_share}元\n💰 實收：{amount:,}元\n📅 日期：{date}\n\n💹 本次交易：\n💵 成本：{sell_cost:,}元\n{profit_text}\n💳 現金餘額：{account['cash']:,}元"
        
        if self.sheets_enabled:
            result += f"\n☁️ 已同步到 Google Sheets"
        else:
            result += f"\n💾 已儲存到記憶體"
        
        if remaining_quantity > 0:
            result += f"\n\n📋 剩餘持股：{remaining_quantity}股"
        else:
            result += f"\n\n✅ 已全部賣出 {stock_name}"
        
        return result
    
    def create_account(self, account_name):
        """建立新帳戶"""
        is_new = self.get_or_create_account(account_name)
        if is_new:
            result_msg = f"🆕 已建立帳戶「{account_name}」\n💡 可以開始入帳和交易了！"
            if self.sheets_enabled:
                result_msg += f"\n☁️ 已同步到 Google Sheets"
            else:
                result_msg += f"\n💾 已儲存到記憶體"
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
                result += f"🏷️ {stock_name}\n"
                result += f"   📊 {holding['quantity']}股 @ {holding['avg_cost']}元\n"
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
            return "📝 目前沒有任何帳戶\n💡 輸入「爸爸入帳 100000」來建立第一個帳戶\n💡 或輸入「爸爸持有 台積電 100 50000」設定現有持股"
        
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
                    result += f"   📈 {stock_name} {holding['quantity']}股\n"
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
                result += f"🏷️ {stock_name}：{total_quantity}股\n"
        
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
                result += f"   🏷️ {t['stock_code']} {t['quantity']}股\n"
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
        
        related_transactions = [
            t for t in self.stock_data['transactions'] 
            if t['account'] == account_name and t.get('stock_code') == stock_name
        ]
        
        result = f"📊 {account_name} - {stock_name} 成本分析：\n\n"
        result += f"📈 目前持股：{holding['quantity']}股\n"
        result += f"💰 平均成本：{holding['avg_cost']}元/股\n"
        result += f"💵 總投資：{holding['total_cost']:,}元\n\n"
        result += f"📋 交易歷史：\n"
        
        for t in related_transactions:
            if t['type'] == '買入':
                result += f"📈 {t['date']} 買入 {t['quantity']}股 @ {t['price_per_share']}元\n"
            elif t['type'] == '賣出':
                profit_loss = t.get('profit_loss', 0)
                profit_text = f" (獲利+{profit_loss:,})" if profit_loss > 0 else f" (虧損{profit_loss:,})" if profit_loss < 0 else " (損益兩平)"
                result += f"📉 {t['date']} 賣出 {t['quantity']}股 @ {t['price_per_share']}元{profit_text}\n"
            elif t['type'] == '持有':
                result += f"📊 {t['date']} 設定持有 {t['quantity']}股 @ {t['price_per_share']}元\n"
        
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
            
            elif parsed['type'] == 'buy':
                return self.handle_buy(
                    parsed['account'], parsed['stock_name'], parsed['stock_code'],
                    parsed['quantity'], parsed['amount'], parsed['date']
                )
            
            elif parsed['type'] == 'sell':
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
            
        except Exception as e:
            return f"❌ 處理失敗：{str(e)}\n💡 請檢查指令格式"
        
        return "❌ 未知的指令類型"
    
    def get_help_text(self):
        """獲取幫助訊息"""
        return """💰 多帳戶股票記帳功能 v2.2 - 代號整合版：

📋 帳戶管理：
- 爸爸入帳 50000 - 入金
- 媽媽提款 10000 - 提款  
- 新增帳戶 奶奶 - 建立帳戶

📊 持股設定（新格式 - 包含股票代號）：
- 爸爸持有 台積電 2330 200 120000 - 設定現有持股
- 媽媽持有 鴻海 2317 100 50000 - 包含股票代號

📈 交易操作（新格式 - 包含股票代號）：
- 爸爸買 台積電 2330 100 50000 0820 - 買股票
- 媽媽賣 鴻海 2317 50 25000 0821 - 賣股票

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
• 🆕 交易時必須包含股票代號：
  - 持有：爸爸持有 股票名稱 代號 數量 總成本
  - 買入：爸爸買 股票名稱 代號 數量 金額 日期
  - 賣出：爸爸賣 股票名稱 代號 數量 金額 日期
• 日期：0820 = 8月20日，1225 = 12月25日
• 股票代號：台股請使用4位數代號（如：2330）

☁️ v2.2 新功能：
• 🆕 股票代號自動儲存在 Google Sheets
• 🆕 即時損益無需額外設定代號
• 🆕 重新部署後代號不會丟失
• ✅ Google Sheets 雲端同步
• ✅ 支援自訂股票名稱
• ✅ 資料永久保存
• ✅ 即時股價查詢
• ✅ 未實現損益計算"""


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
    """判斷是否為股票查詢指令 - 對外接口"""
    query_patterns = [
        '總覽', '帳戶列表', '股票幫助', '交易記錄', '成本查詢',
        '即時損益', '股價查詢', '股價', '檢查代號', '批量設定代號',
        '估價查詢', '即時股價查詢'
    ]
    
    return any(pattern in message_text for pattern in query_patterns) or \
           message_text.endswith('查詢') or \
           message_text.startswith('即時損益') or \
           message_text.startswith('估價查詢')


if __name__ == "__main__":
    sm = StockManager()
    print("=== 測試持有（新格式）===")
    print(sm.handle_command("爸爸持有 台積電 2330 200 120000"))
    print()
    print("=== 測試入帳 ===")
    print(sm.handle_command("爸爸入帳 100000"))
    print()
    print("=== 測試買入（新格式）===")
    print(sm.handle_command("爸爸買 台積電 2330 100 50000 0820"))
    print()
    print("=== 測試查詢 ===")
    print(sm.get_account_summary("爸爸"))
    print()
    print("=== 測試總覽 ===")
    print(sm.get_all_accounts_summary())
    print()
    print("=== 測試即時損益 ===")
    print(sm.get_realtime_pnl()), message_text):
            account, stock_name, stock_code, quantity, amount, date = match.groups()
            try:
                year = datetime.now().year
                month = int(date[:2])
                day = int(date[2:])
                formatted_date = f"{year}/{month:02d}/{day:02d}"
            except:
                return None
            return {'type': 'buy', 'account': account.strip(), 'stock_name': stock_name.strip(), 
                   'stock_code': stock_code.strip(), 'quantity': int(quantity), 'amount': int(amount), 'date': formatted_date}
        
        elif match := re.match(r'(.+?)賣\s+(.+?)\s+(\w+)\s+(\d+)\s+(\d+)\s+(\d{4})
        
        elif match := re.match(r'新增帳戶\s*(.+)', message_text):
            account = match.group(1).strip()
            return {'type': 'create_account', 'account': account}
        
        return None
    
    def handle_holding(self, account_name, stock_name, quantity, total_cost):
        """處理持有股票設定"""
        is_new = self.get_or_create_account(account_name)
        
        avg_cost = round(total_cost / quantity, 2)
        
        self.stock_data['accounts'][account_name]['stocks'][stock_name] = {
            'quantity': quantity,
            'total_cost': total_cost,
            'avg_cost': avg_cost
        }
        
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
        
        if self.sheets_enabled:
            self.sync_to_sheets_safe()
        
        result_msg = f"📊 {account_name} 持股設定成功！\n"
        if is_new:
            result_msg += f"🆕 已建立新帳戶\n"
        result_msg += f"🏷️ {stock_name}\n"
        result_msg += f"📈 持股：{quantity}股\n"
        result_msg += f"💰 總成本：{total_cost:,}元\n"
        result_msg += f"💵 平均成本：{avg_cost}元/股"
        
        if self.sheets_enabled:
            result_msg += f"\n☁️ 已同步到 Google Sheets"
        else:
            result_msg += f"\n💾 已儲存到記憶體"
        
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
        
        if self.sheets_enabled:
            self.sync_to_sheets_safe()
        
        result_msg = f"💰 {account_name} 入帳成功！\n"
        if is_new:
            result_msg += f"🆕 已建立新帳戶\n"
        result_msg += f"💵 入帳金額：{amount:,}元\n"
        result_msg += f"💳 帳戶餘額：{self.stock_data['accounts'][account_name]['cash']:,}元"
        
        if self.sheets_enabled:
            result_msg += f"\n☁️ 已同步到 Google Sheets"
        else:
            result_msg += f"\n💾 已儲存到記憶體"
        
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
        
        if self.sheets_enabled:
            self.sync_to_sheets_safe()
        
        result_msg = f"💸 {account_name} 提款成功！\n💵 提款金額：{amount:,}元\n💳 帳戶餘額：{account['cash']:,}元"
        
        if self.sheets_enabled:
            result_msg += f"\n☁️ 已同步到 Google Sheets"
        else:
            result_msg += f"\n💾 已儲存到記憶體"
        
        return result_msg
    
    def handle_buy(self, account_name, stock_name, quantity, amount, date):
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
                'avg_cost': avg_cost
            }
        else:
            account['stocks'][stock_name] = {
                'quantity': quantity,
                'total_cost': amount,
                'avg_cost': price_per_share
            }
        
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
        
        if self.sheets_enabled:
            self.sync_to_sheets_safe()
        
        stock_info = account['stocks'][stock_name]
        result_msg = f"📈 {account_name} 買入成功！\n\n🏷️ {stock_name}\n📊 買入：{quantity}股 @ {price_per_share}元\n💰 實付：{amount:,}元\n📅 日期：{date}\n\n📋 持股狀況：\n📊 總持股：{stock_info['quantity']}股\n💵 平均成本：{stock_info['avg_cost']}元/股\n💳 剩餘現金：{account['cash']:,}元"
        
        if self.sheets_enabled:
            result_msg += f"\n☁️ 已同步到 Google Sheets"
        else:
            result_msg += f"\n💾 已儲存到記憶體"
        
        return result_msg
    
    def handle_sell(self, account_name, stock_name, quantity, amount, date):
        """處理賣出股票"""
        if account_name not in self.stock_data['accounts']:
            return f"❌ 帳戶「{account_name}」不存在"
        
        account = self.stock_data['accounts'][account_name]
        if stock_name not in account['stocks']:
            return f"❌ 沒有持有「{stock_name}」"
        
        holding = account['stocks'][stock_name]
        if holding['quantity'] < quantity:
            return f"❌ 持股不足！\n📊 目前持股：{holding['quantity']}股\n📤 欲賣出：{quantity}股"
        
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
                'avg_cost': holding['avg_cost']
            }
        else:
            del account['stocks'][stock_name]
        
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
        
        if self.sheets_enabled:
            self.sync_to_sheets_safe()
        
        profit_text = f"💰 獲利：+{profit_loss:,}元" if profit_loss > 0 else f"💸 虧損：{profit_loss:,}元" if profit_loss < 0 else "💫 損益兩平"
        
        result = f"📉 {account_name} 賣出成功！\n\n🏷️ {stock_name}\n📊 賣出：{quantity}股 @ {price_per_share}元\n💰 實收：{amount:,}元\n📅 日期：{date}\n\n💹 本次交易：\n💵 成本：{sell_cost:,}元\n{profit_text}\n💳 現金餘額：{account['cash']:,}元"
        
        if self.sheets_enabled:
            result += f"\n☁️ 已同步到 Google Sheets"
        else:
            result += f"\n💾 已儲存到記憶體"
        
        if remaining_quantity > 0:
            result += f"\n\n📋 剩餘持股：{remaining_quantity}股"
        else:
            result += f"\n\n✅ 已全部賣出 {stock_name}"
        
        return result
    
    def create_account(self, account_name):
        """建立新帳戶"""
        is_new = self.get_or_create_account(account_name)
        if is_new:
            result_msg = f"🆕 已建立帳戶「{account_name}」\n💡 可以開始入帳和交易了！"
            if self.sheets_enabled:
                result_msg += f"\n☁️ 已同步到 Google Sheets"
            else:
                result_msg += f"\n💾 已儲存到記憶體"
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
                result += f"🏷️ {stock_name}\n"
                result += f"   📊 {holding['quantity']}股 @ {holding['avg_cost']}元\n"
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
            return "📝 目前沒有任何帳戶\n💡 輸入「爸爸入帳 100000」來建立第一個帳戶\n💡 或輸入「爸爸持有 台積電 100 50000」設定現有持股"
        
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
                    result += f"   📈 {stock_name} {holding['quantity']}股\n"
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
                result += f"🏷️ {stock_name}：{total_quantity}股\n"
        
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
                result += f"   🏷️ {t['stock_code']} {t['quantity']}股\n"
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
        
        related_transactions = [
            t for t in self.stock_data['transactions'] 
            if t['account'] == account_name and t.get('stock_code') == stock_name
        ]
        
        result = f"📊 {account_name} - {stock_name} 成本分析：\n\n"
        result += f"📈 目前持股：{holding['quantity']}股\n"
        result += f"💰 平均成本：{holding['avg_cost']}元/股\n"
        result += f"💵 總投資：{holding['total_cost']:,}元\n\n"
        result += f"📋 交易歷史：\n"
        
        for t in related_transactions:
            if t['type'] == '買入':
                result += f"📈 {t['date']} 買入 {t['quantity']}股 @ {t['price_per_share']}元\n"
            elif t['type'] == '賣出':
                profit_loss = t.get('profit_loss', 0)
                profit_text = f" (獲利+{profit_loss:,})" if profit_loss > 0 else f" (虧損{profit_loss:,})" if profit_loss < 0 else " (損益兩平)"
                result += f"📉 {t['date']} 賣出 {t['quantity']}股 @ {t['price_per_share']}元{profit_text}\n"
            elif t['type'] == '持有':
                result += f"📊 {t['date']} 設定持有 {t['quantity']}股 @ {t['price_per_share']}元\n"
        
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
                    parsed['account'], parsed['stock_name'], 
                    parsed['quantity'], parsed['total_cost']
                )
            
            elif parsed['type'] == 'buy':
                return self.handle_buy(
                    parsed['account'], parsed['stock_name'], 
                    parsed['quantity'], parsed['amount'], parsed['date']
                )
            
            elif parsed['type'] == 'sell':
                return self.handle_sell(
                    parsed['account'], parsed['stock_name'], 
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
            
        except Exception as e:
            return f"❌ 處理失敗：{str(e)}\n💡 請檢查指令格式"
        
        return "❌ 未知的指令類型"
    
    def get_help_text(self):
        """獲取幫助訊息"""
        return """💰 多帳戶股票記帳功能 v2.1 - 即時損益版：

📋 帳戶管理：
- 爸爸入帳 50000 - 入金
- 媽媽提款 10000 - 提款  
- 新增帳戶 奶奶 - 建立帳戶

📊 持股設定：
- 爸爸持有 台積電 200 120000 - 設定現有持股
- 媽媽持有 我的好股票 100 50000 - 支援自訂名稱

📈 交易操作（支援自訂股票名稱）：
- 爸爸買 台積電 100 50000 0820 - 買股票
- 媽媽賣 我的好股票 50 25000 0821 - 賣股票

📊 查詢功能：
- 總覽 - 所有帳戶總覽
- 爸爸查詢 - 個人資金和持股
- 交易記錄 - 所有交易歷史
- 交易記錄 爸爸 - 個人交易記錄
- 成本查詢 爸爸 台積電 - 持股成本分析
- 帳戶列表 - 查看所有帳戶

💹 新功能 - 即時損益：
- 設定代號 台積電 2330 - 設定股票代號
- 股價查詢 台積電 - 查詢即時股價
- 即時損益 - 查看所有帳戶即時損益
- 即時損益 爸爸 - 查看個人即時損益

📝 格式說明：
• 支援任意股票名稱：台積電、鴻海、我的好股票 等
• 日期：0820 = 8月20日，1225 = 12月25日
• 股票代號：台股請使用4位數代號（如：2330）

☁️ v2.1 功能：
• Google Sheets 雲端同步
• 支援自訂股票名稱  
• 初始持股設定
• 資料永久保存
• 🆕 即時股價查詢
• 🆕 未實現損益計算
• 🆕 投資績效分析"""


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
    """判斷是否為股票查詢指令 - 對外接口"""
    query_patterns = [
        '總覽', '帳戶列表', '股票幫助', '交易記錄', '成本查詢',
        '即時損益', '股價查詢', '股價', '檢查代號', '批量設定代號',
        '估價查詢', '即時股價查詢'
    ]
    
    return any(pattern in message_text for pattern in query_patterns) or \
           message_text.endswith('查詢') or \
           message_text.startswith('即時損益') or \
           message_text.startswith('估價查詢')


if __name__ == "__main__":
    sm = StockManager()
    print("=== 測試持有 ===")
    print(sm.handle_command("爸爸持有 台積電 200 120000"))
    print()
    print("=== 測試入帳 ===")
    print(sm.handle_command("爸爸入帳 100000"))
    print()
    print("=== 測試買入 ===")
    print(sm.handle_command("爸爸買 台積電 100 50000 0820"))
    print()
    print("=== 測試查詢 ===")
    print(sm.get_account_summary("爸爸"))
    print()
    print("=== 測試總覽 ===")
    print(sm.get_all_accounts_summary()), message_text):
            account, stock_name, stock_code, quantity, amount, date = match.groups()
            try:
                year = datetime.now().year
                month = int(date[:2])
                day = int(date[2:])
                formatted_date = f"{year}/{month:02d}/{day:02d}"
            except:
                return None
            return {'type': 'sell', 'account': account.strip(), 'stock_name': stock_name.strip(), 
                   'stock_code': stock_code.strip(), 'quantity': int(quantity), 'amount': int(amount), 'date': formatted_date}
        
        elif match := re.match(r'新增帳戶\s*(.+)', message_text):
            account = match.group(1).strip()
            return {'type': 'create_account', 'account': account}
        
        return None
    
    def handle_holding(self, account_name, stock_name, quantity, total_cost):
        """處理持有股票設定"""
        is_new = self.get_or_create_account(account_name)
        
        avg_cost = round(total_cost / quantity, 2)
        
        self.stock_data['accounts'][account_name]['stocks'][stock_name] = {
            'quantity': quantity,
            'total_cost': total_cost,
            'avg_cost': avg_cost
        }
        
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
        
        if self.sheets_enabled:
            self.sync_to_sheets_safe()
        
        result_msg = f"📊 {account_name} 持股設定成功！\n"
        if is_new:
            result_msg += f"🆕 已建立新帳戶\n"
        result_msg += f"🏷️ {stock_name}\n"
        result_msg += f"📈 持股：{quantity}股\n"
        result_msg += f"💰 總成本：{total_cost:,}元\n"
        result_msg += f"💵 平均成本：{avg_cost}元/股"
        
        if self.sheets_enabled:
            result_msg += f"\n☁️ 已同步到 Google Sheets"
        else:
            result_msg += f"\n💾 已儲存到記憶體"
        
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
        
        if self.sheets_enabled:
            self.sync_to_sheets_safe()
        
        result_msg = f"💰 {account_name} 入帳成功！\n"
        if is_new:
            result_msg += f"🆕 已建立新帳戶\n"
        result_msg += f"💵 入帳金額：{amount:,}元\n"
        result_msg += f"💳 帳戶餘額：{self.stock_data['accounts'][account_name]['cash']:,}元"
        
        if self.sheets_enabled:
            result_msg += f"\n☁️ 已同步到 Google Sheets"
        else:
            result_msg += f"\n💾 已儲存到記憶體"
        
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
        
        if self.sheets_enabled:
            self.sync_to_sheets_safe()
        
        result_msg = f"💸 {account_name} 提款成功！\n💵 提款金額：{amount:,}元\n💳 帳戶餘額：{account['cash']:,}元"
        
        if self.sheets_enabled:
            result_msg += f"\n☁️ 已同步到 Google Sheets"
        else:
            result_msg += f"\n💾 已儲存到記憶體"
        
        return result_msg
    
    def handle_buy(self, account_name, stock_name, quantity, amount, date):
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
                'avg_cost': avg_cost
            }
        else:
            account['stocks'][stock_name] = {
                'quantity': quantity,
                'total_cost': amount,
                'avg_cost': price_per_share
            }
        
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
        
        if self.sheets_enabled:
            self.sync_to_sheets_safe()
        
        stock_info = account['stocks'][stock_name]
        result_msg = f"📈 {account_name} 買入成功！\n\n🏷️ {stock_name}\n📊 買入：{quantity}股 @ {price_per_share}元\n💰 實付：{amount:,}元\n📅 日期：{date}\n\n📋 持股狀況：\n📊 總持股：{stock_info['quantity']}股\n💵 平均成本：{stock_info['avg_cost']}元/股\n💳 剩餘現金：{account['cash']:,}元"
        
        if self.sheets_enabled:
            result_msg += f"\n☁️ 已同步到 Google Sheets"
        else:
            result_msg += f"\n💾 已儲存到記憶體"
        
        return result_msg
    
    def handle_sell(self, account_name, stock_name, quantity, amount, date):
        """處理賣出股票"""
        if account_name not in self.stock_data['accounts']:
            return f"❌ 帳戶「{account_name}」不存在"
        
        account = self.stock_data['accounts'][account_name]
        if stock_name not in account['stocks']:
            return f"❌ 沒有持有「{stock_name}」"
        
        holding = account['stocks'][stock_name]
        if holding['quantity'] < quantity:
            return f"❌ 持股不足！\n📊 目前持股：{holding['quantity']}股\n📤 欲賣出：{quantity}股"
        
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
                'avg_cost': holding['avg_cost']
            }
        else:
            del account['stocks'][stock_name]
        
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
        
        if self.sheets_enabled:
            self.sync_to_sheets_safe()
        
        profit_text = f"💰 獲利：+{profit_loss:,}元" if profit_loss > 0 else f"💸 虧損：{profit_loss:,}元" if profit_loss < 0 else "💫 損益兩平"
        
        result = f"📉 {account_name} 賣出成功！\n\n🏷️ {stock_name}\n📊 賣出：{quantity}股 @ {price_per_share}元\n💰 實收：{amount:,}元\n📅 日期：{date}\n\n💹 本次交易：\n💵 成本：{sell_cost:,}元\n{profit_text}\n💳 現金餘額：{account['cash']:,}元"
        
        if self.sheets_enabled:
            result += f"\n☁️ 已同步到 Google Sheets"
        else:
            result += f"\n💾 已儲存到記憶體"
        
        if remaining_quantity > 0:
            result += f"\n\n📋 剩餘持股：{remaining_quantity}股"
        else:
            result += f"\n\n✅ 已全部賣出 {stock_name}"
        
        return result
    
    def create_account(self, account_name):
        """建立新帳戶"""
        is_new = self.get_or_create_account(account_name)
        if is_new:
            result_msg = f"🆕 已建立帳戶「{account_name}」\n💡 可以開始入帳和交易了！"
            if self.sheets_enabled:
                result_msg += f"\n☁️ 已同步到 Google Sheets"
            else:
                result_msg += f"\n💾 已儲存到記憶體"
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
                result += f"🏷️ {stock_name}\n"
                result += f"   📊 {holding['quantity']}股 @ {holding['avg_cost']}元\n"
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
            return "📝 目前沒有任何帳戶\n💡 輸入「爸爸入帳 100000」來建立第一個帳戶\n💡 或輸入「爸爸持有 台積電 100 50000」設定現有持股"
        
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
                    result += f"   📈 {stock_name} {holding['quantity']}股\n"
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
                result += f"🏷️ {stock_name}：{total_quantity}股\n"
        
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
                result += f"   🏷️ {t['stock_code']} {t['quantity']}股\n"
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
        
        related_transactions = [
            t for t in self.stock_data['transactions'] 
            if t['account'] == account_name and t.get('stock_code') == stock_name
        ]
        
        result = f"📊 {account_name} - {stock_name} 成本分析：\n\n"
        result += f"📈 目前持股：{holding['quantity']}股\n"
        result += f"💰 平均成本：{holding['avg_cost']}元/股\n"
        result += f"💵 總投資：{holding['total_cost']:,}元\n\n"
        result += f"📋 交易歷史：\n"
        
        for t in related_transactions:
            if t['type'] == '買入':
                result += f"📈 {t['date']} 買入 {t['quantity']}股 @ {t['price_per_share']}元\n"
            elif t['type'] == '賣出':
                profit_loss = t.get('profit_loss', 0)
                profit_text = f" (獲利+{profit_loss:,})" if profit_loss > 0 else f" (虧損{profit_loss:,})" if profit_loss < 0 else " (損益兩平)"
                result += f"📉 {t['date']} 賣出 {t['quantity']}股 @ {t['price_per_share']}元{profit_text}\n"
            elif t['type'] == '持有':
                result += f"📊 {t['date']} 設定持有 {t['quantity']}股 @ {t['price_per_share']}元\n"
        
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
                    parsed['account'], parsed['stock_name'], 
                    parsed['quantity'], parsed['total_cost']
                )
            
            elif parsed['type'] == 'buy':
                return self.handle_buy(
                    parsed['account'], parsed['stock_name'], 
                    parsed['quantity'], parsed['amount'], parsed['date']
                )
            
            elif parsed['type'] == 'sell':
                return self.handle_sell(
                    parsed['account'], parsed['stock_name'], 
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
            
        except Exception as e:
            return f"❌ 處理失敗：{str(e)}\n💡 請檢查指令格式"
        
        return "❌ 未知的指令類型"
    
    def get_help_text(self):
        """獲取幫助訊息"""
        return """💰 多帳戶股票記帳功能 v2.1 - 即時損益版：

📋 帳戶管理：
- 爸爸入帳 50000 - 入金
- 媽媽提款 10000 - 提款  
- 新增帳戶 奶奶 - 建立帳戶

📊 持股設定：
- 爸爸持有 台積電 200 120000 - 設定現有持股
- 媽媽持有 我的好股票 100 50000 - 支援自訂名稱

📈 交易操作（支援自訂股票名稱）：
- 爸爸買 台積電 100 50000 0820 - 買股票
- 媽媽賣 我的好股票 50 25000 0821 - 賣股票

📊 查詢功能：
- 總覽 - 所有帳戶總覽
- 爸爸查詢 - 個人資金和持股
- 交易記錄 - 所有交易歷史
- 交易記錄 爸爸 - 個人交易記錄
- 成本查詢 爸爸 台積電 - 持股成本分析
- 帳戶列表 - 查看所有帳戶

💹 新功能 - 即時損益：
- 設定代號 台積電 2330 - 設定股票代號
- 股價查詢 台積電 - 查詢即時股價
- 即時損益 - 查看所有帳戶即時損益
- 即時損益 爸爸 - 查看個人即時損益

📝 格式說明：
• 支援任意股票名稱：台積電、鴻海、我的好股票 等
• 日期：0820 = 8月20日，1225 = 12月25日
• 股票代號：台股請使用4位數代號（如：2330）

☁️ v2.1 功能：
• Google Sheets 雲端同步
• 支援自訂股票名稱  
• 初始持股設定
• 資料永久保存
• 🆕 即時股價查詢
• 🆕 未實現損益計算
• 🆕 投資績效分析"""


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
    """判斷是否為股票查詢指令 - 對外接口"""
    query_patterns = [
        '總覽', '帳戶列表', '股票幫助', '交易記錄', '成本查詢',
        '即時損益', '股價查詢', '股價', '檢查代號', '批量設定代號',
        '估價查詢', '即時股價查詢'
    ]
    
    return any(pattern in message_text for pattern in query_patterns) or \
           message_text.endswith('查詢') or \
           message_text.startswith('即時損益') or \
           message_text.startswith('估價查詢')


if __name__ == "__main__":
    sm = StockManager()
    print("=== 測試持有 ===")
    print(sm.handle_command("爸爸持有 台積電 200 120000"))
    print()
    print("=== 測試入帳 ===")
    print(sm.handle_command("爸爸入帳 100000"))
    print()
    print("=== 測試買入 ===")
    print(sm.handle_command("爸爸買 台積電 100 50000 0820"))
    print()
    print("=== 測試查詢 ===")
    print(sm.get_account_summary("爸爸"))
    print()
    print("=== 測試總覽 ===")
    print(sm.get_all_accounts_summary())
