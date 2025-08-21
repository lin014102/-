"""
stock_manager.py - 股票記帳模組
"""
import re
import os
import json
from datetime import datetime
import pytz
import gspread
from google.oauth2.service_account import Credentials
import traceback

TAIWAN_TZ = pytz.timezone('Asia/Taipei')

class StockManager:
    def __init__(self):
        self.stock_data = {
            'accounts': {},
            'transactions': [],
            'stock_codes': {}
        }
        self.spreadsheet_url = "https://docs.google.com/spreadsheets/d/1EACr2Zu7_regqp3Po7AlNE4ZcjazKbgyvz-yYNYtcCs/edit?usp=sharing"
        self.gc = None
        self.sheet = None
        self.sheets_enabled = False
        self.last_sync_time = None
        self.init_google_sheets()
        if self.sheets_enabled:
            self.load_from_sheets_debug()
        else:
            print("股票記帳模組初始化完成（記憶體模式）")

    def init_google_sheets(self):
        try:
            creds_json = os.getenv('GOOGLE_CREDENTIALS')
            if not creds_json:
                print("未找到環境變數，使用記憶體模式")
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
            print("Google Sheets 連接成功")
            self.sheets_enabled = True
            return True
        except Exception as e:
            print(f"Google Sheets 連接失敗: {e}")
            return False

    def load_from_sheets_debug(self):
        if not self.sheets_enabled:
            return
        try:
            print("載入 Google Sheets 資料...")
            worksheets = self.sheet.worksheets()
            
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
                print(f"載入 {len(self.stock_data['accounts'])} 個帳戶")
            except Exception as e:
                print(f"載入帳戶資訊失敗: {e}")
            
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
                        stock_code_raw = row.get('股票代號')
                        if stock_code_raw is not None:
                            stock_code = str(stock_code_raw).strip()
                            if stock_code.isdigit() and len(stock_code) == 3:
                                stock_code = f"00{stock_code}"
                                print(f"修正ETF代號：{row.get('股票代號')} -> {stock_code}")
                        else:
                            stock_code = None
                        if account_name and stock_name and account_name in self.stock_data['accounts']:
                            self.stock_data['accounts'][account_name]['stocks'][stock_name] = {
                                'quantity': int(row.get('持股數量', 0)),
                                'avg_cost': float(row.get('平均成本', 0)),
                                'total_cost': int(row.get('總成本', 0)),
                                'stock_code': stock_code
                            }
                            if stock_code:
                                self.stock_data['stock_codes'][stock_name] = stock_code
                            holdings_count += 1
                    print(f"載入 {holdings_count} 筆持股記錄")
            except Exception as e:
                print(f"載入持股明細失敗: {e}")
            
        except Exception as e:
            print(f"載入資料失敗: {e}")

    def get_taiwan_time(self):
        return datetime.now(TAIWAN_TZ).strftime('%Y/%m/%d %H:%M:%S')

    def get_or_create_account(self, account_name):
        if account_name not in self.stock_data['accounts']:
            self.stock_data['accounts'][account_name] = {
                'cash': 0,
                'stocks': {},
                'created_date': self.get_taiwan_time()
            }
            return True
        return False

    def get_stock_price(self, stock_code):
        try:
            import requests
            import time
            stock_code = str(stock_code).strip()
            query_formats = self._generate_query_formats(stock_code)
            for format_name, query_code in query_formats:
                try:
                    print(f"查詢 {stock_code} 使用 {format_name}: {query_code}")
                    price = self._query_yahoo_chart(query_code)
                    if price:
                        print(f"成功取得 {stock_code} 股價: {price}")
                        return price
                    time.sleep(0.3)
                except Exception as e:
                    print(f"{format_name} 查詢失敗: {e}")
                    continue
            print(f"{stock_code} 所有格式都失敗")
            return None
        except Exception as e:
            print(f"股價查詢錯誤: {e}")
            return None

    def _generate_query_formats(self, stock_code):
        formats = []
        if len(stock_code) == 5 and stock_code.startswith('00'):
            formats.append(("ETF", f"{stock_code}.TW"))
            formats.append(("ETF備用", f"{stock_code}.TWO"))
        elif len(stock_code) == 4 and stock_code.startswith(('1', '2')):
            formats.append(("上市", f"{stock_code}.TW"))
            formats.append(("上市備用", f"{stock_code}.TWO"))
        elif len(stock_code) == 4 and stock_code.startswith(('3', '4', '5', '6', '7', '8', '9')):
            formats.append(("上櫃", f"{stock_code}.TWO"))
            formats.append(("上櫃備用", f"{stock_code}.TW"))
        else:
            formats.append(("通用1", f"{stock_code}.TW"))
            formats.append(("通用2", f"{stock_code}.TWO"))
        return formats

    def _query_yahoo_chart(self, query_code):
        try:
            import requests
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{query_code}"
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            if (data.get('chart') and data['chart'].get('result') and 
                len(data['chart']['result']) > 0 and data['chart']['result'][0].get('meta')):
                meta = data['chart']['result'][0]['meta']
                price = meta.get('regularMarketPrice')
                if price and price > 0:
                    return round(float(price), 2)
            return None
        except Exception:
            return None

    def get_realtime_pnl(self, account_name=None):
        if account_name and account_name not in self.stock_data['accounts']:
            return f"帳戶「{account_name}」不存在"
        
        accounts_to_check = {account_name: self.stock_data['accounts'][account_name]} if account_name else self.stock_data['accounts']
        result = f"即時損益：\n\n"
        total_cost = 0
        total_value = 0
        has_price_data = False
        failed_stocks = []
        
        for acc_name, account in accounts_to_check.items():
            if not account['stocks']:
                continue
            result += f"{acc_name}：\n"
            account_cost = 0
            account_value = 0
            
            for stock_name, holding in account['stocks'].items():
                cost = holding['total_cost']
                account_cost += cost
                stock_code = holding.get('stock_code') or self.stock_data['stock_codes'].get(stock_name)
                
                if stock_code:
                    print(f"查詢 {stock_name} ({stock_code}) 股價...")
                    current_price = self.get_stock_price(stock_code)
                    if current_price:
                        current_value = holding['quantity'] * current_price
                        pnl = current_value - cost
                        pnl_percent = (pnl / cost) * 100
                        account_value += current_value
                        has_price_data = True
                        pnl_text = f"+{pnl:,.0f}元 (+{pnl_percent:.1f}%)" if pnl > 0 else f"{pnl:,.0f}元 ({pnl_percent:.1f}%)" if pnl < 0 else "損益兩平"
                        result += f"   {stock_name} ({stock_code})\n"
                        result += f"      成本：{cost:,}元 ({holding['avg_cost']}元/股)\n"
                        result += f"      現值：{current_value:,}元 ({current_price}元/股)\n"
                        result += f"      {pnl_text}\n\n"
                    else:
                        failed_stocks.append(f"{stock_name} ({stock_code})")
                        result += f"   {stock_name} ({stock_code}) - 無法取得股價\n"
                        result += f"      成本：{cost:,}元\n\n"
                else:
                    result += f"   {stock_name} - 缺少股票代號\n"
                    result += f"      成本：{cost:,}元\n\n"
            
            total_cost += account_cost
            total_value += account_value
        
        if has_price_data and total_value > 0:
            total_pnl = total_value - total_cost
            total_pnl_percent = (total_pnl / total_cost) * 100
            total_pnl_text = f"+{total_pnl:,.0f}元 (+{total_pnl_percent:.1f}%)" if total_pnl > 0 else f"{total_pnl:,.0f}元 ({total_pnl_percent:.1f}%)"
            result += f"總投資成本：{total_cost:,}元\n"
            result += f"總投資現值：{total_value:,}元\n"
            result += f"總未實現損益：{total_pnl_text}\n\n"
        
        if failed_stocks:
            result += f"無法取得股價：\n"
            for stock in failed_stocks:
                result += f"   {stock}\n"
            result += f"\n可能原因：\n"
            result += f"   非交易時間\n"
            result += f"   股票暫停交易\n"
            result += f"   網路連線問題\n"
            result += f"   API 服務不可用\n\n"
        
        result += "股價來源：Yahoo Finance"
        return result

    def sync_to_sheets_safe(self):
        if not self.sheets_enabled:
            return False
        try:
            print("同步到 Google Sheets...")
            return True
        except Exception as e:
            print(f"同步失敗: {e}")
            return False

    def check_and_reload_if_needed(self):
        pass

    def parse_command(self, message_text):
        return None

    def handle_command(self, message_text):
        return "功能正在測試中"

    def get_account_summary(self, account_name):
        return "功能正在測試中"

    def get_all_accounts_summary(self):
        return "功能正在測試中"

    def get_transaction_history(self, account_name=None, limit=10):
        return "功能正在測試中"

    def get_cost_analysis(self, account_name, stock_code):
        return "功能正在測試中"

    def get_account_list(self):
        return "功能正在測試中"

    def get_help_text(self):
        return "股票記帳功能 v2.2"

stock_manager = StockManager()

def handle_stock_command(message_text):
    return stock_manager.handle_command(message_text)

def get_stock_summary(account_name=None):
    stock_manager.check_and_reload_if_needed()
    if account_name:
        return stock_manager.get_account_summary(account_name)
    else:
        return stock_manager.get_all_accounts_summary()

def get_stock_transactions(account_name=None, limit=10):
    stock_manager.check_and_reload_if_needed()
    return stock_manager.get_transaction_history(account_name, limit)

def get_stock_cost_analysis(account_name, stock_code):
    stock_manager.check_and_reload_if_needed()
    return stock_manager.get_cost_analysis(account_name, stock_code)

def get_stock_account_list():
    stock_manager.check_and_reload_if_needed()
    return stock_manager.get_account_list()

def get_stock_realtime_pnl(account_name=None):
    return stock_manager.get_realtime_pnl(account_name)

def get_stock_help():
    return stock_manager.get_help_text()

def is_stock_command(message_text):
    stock_keywords = ['買入', '賣出', '入帳', '提款', '新增帳戶', '持有', '設定代號']
    return any(keyword in message_text for keyword in stock_keywords) or re.match(r'.+?(買|賣|持有)\s+', message_text) is not None

def is_stock_query(message_text):
    query_patterns = ['總覽', '帳戶列表', '股票幫助', '交易記錄', '成本查詢', '即時損益', '股價查詢', '股價', '檢查代號', '批量設定代號', '估價查詢', '即時股價查詢']
    return any(pattern in message_text for pattern in query_patterns) or message_text.endswith('查詢') or message_text.startswith('即時損益') or message_text.startswith('估價查詢')
