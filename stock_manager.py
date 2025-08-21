"""
stock_manager.py - 獨立股票記帳模組 + Google Sheets 整合
多帳戶股票記帳系統 v2.2 - 代號整合版
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
        
        return result_msg
    
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
        
        result_msg = f"📊 {account_name} 持股設定成功！\n"
        if is_new:
            result_msg += f"🆕 已建立新帳戶\n"
        result_msg += f"🏷️ {stock_name} ({stock_code})\n"
        result_msg += f"📈 持股：{quantity}股\n"
        result_msg += f"💰 總成本：{total_cost:,}元\n"
        result_msg += f"💵 平均成本：{avg_cost}元/股"
        
        return result_msg
    
    def get_all_accounts_summary(self):
        """獲取所有帳戶總覽"""
        if not self.stock_data['accounts']:
            return "📝 目前沒有任何帳戶\n💡 輸入「爸爸入帳 100000」來建立第一個帳戶\n💡 或輸入「爸爸持有 台積電 2330 100 50000」設定現有持股"
        
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
                    result += f"   📈 {stock_name}{code_display} {holding['quantity']}股\n"
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
        
        return result
    
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
                result += f"🏷️ {stock_name}{code_display}\n"
                result += f"   📊 {holding['quantity']}股 @ {holding['avg_cost']}元\n"
                result += f"   💰 投資成本：{holding['total_cost']:,}元\n\n"
                total_investment += holding['total_cost']
            
            total_assets = account['cash'] + total_investment
            result += f"💼 總投資：{total_investment:,}元\n"
            result += f"🏦 總資產：{total_assets:,}元"
        else:
            result += "\n📝 目前無持股"
        
        return result
    
    def parse_command(self, message_text):
        """解析股票相關指令"""
        message_text = message_text.strip()
        
        if match := re.match(r'(.+?)入帳\s*(\d+)', message_text):
            account, amount = match.groups()
            return {'type': 'deposit', 'account': account.strip(), 'amount': int(amount)}
        
        elif match := re.match(r'(.+?)持有\s+(.+?)\s+(\w+)\s+(\d+)\s+(\d+)', message_text):
            account, stock_name, stock_code, quantity, total_cost = match.groups()
            return {
                'type': 'holding', 
                'account': account.strip(), 
                'stock_name': stock_name.strip(), 
                'stock_code': str(stock_code).strip(), 
                'quantity': int(quantity), 
                'total_cost': int(total_cost)
            }
        
        return None
    
    def handle_command(self, message_text):
        """處理股票指令的主要函數"""
        parsed = self.parse_command(message_text)
        
        if not parsed:
            return "❌ 指令格式不正確\n💡 輸入「股票幫助」查看使用說明"
        
        try:
            if parsed['type'] == 'deposit':
                return self.handle_deposit(parsed['account'], parsed['amount'])
            
            elif parsed['type'] == 'holding':
                return self.handle_holding(
                    parsed['account'], parsed['stock_name'], parsed['stock_code'],
                    parsed['quantity'], parsed['total_cost']
                )
            
        except Exception as e:
            return f"❌ 處理失敗：{str(e)}\n💡 請檢查指令格式"
        
        return "❌ 未知的指令類型"
    
    def get_help_text(self):
        """獲取幫助訊息"""
        return """💰 多帳戶股票記帳功能 v2.2：

📋 帳戶管理：
- 爸爸入帳 50000 - 入金

📊 持股設定：
- 爸爸持有 台積電 2330 200 120000 - 設定現有持股

📊 查詢功能：
- 總覽 - 所有帳戶總覽
- 爸爸查詢 - 個人資金和持股"""


# 建立全域實例
stock_manager = StockManager()


# 對外接口函數，供 main.py 使用
def handle_stock_command(message_text):
    """處理股票指令 - 對外接口"""
    return stock_manager.handle_command(message_text)


def get_stock_summary(account_name=None):
    """獲取股票摘要 - 對外接口"""
    if account_name:
        return stock_manager.get_account_summary(account_name)
    else:
        return stock_manager.get_all_accounts_summary()


def get_stock_help():
    """獲取股票幫助 - 對外接口"""
    return stock_manager.get_help_text()


def is_stock_command(message_text):
    """判斷是否為股票指令 - 對外接口"""
    stock_keywords = ['入帳', '持有']
    return any(keyword in message_text for keyword in stock_keywords)


def is_stock_query(message_text):
    """判斷是否為股票查詢指令 - 對外接口"""
    query_patterns = ['總覽', '股票幫助']
    return any(pattern in message_text for pattern in query_patterns) or message_text.endswith('查詢')


if __name__ == "__main__":
    sm = StockManager()
    print("=== 測試持有 ===")
    print(sm.handle_command("爸爸持有 台積電 2330 200 120000"))
    print()
    print("=== 測試入帳 ===")
    print(sm.handle_command("爸爸入帳 100000"))
    print()
    print("=== 測試總覽 ===")
    print(sm.get_all_accounts_summary())
