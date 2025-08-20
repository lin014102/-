"""
stock_manager.py - 獨立股票記帳模組 + Google Sheets 整合
多帳戶股票記帳系統 v2.0
"""
import re
import os
import json
from datetime import datetime
import pytz
import gspread
from google.oauth2.service_account import Credentials

# 設定台灣時區
TAIWAN_TZ = pytz.timezone('Asia/Taipei')

class StockManager:
    """股票記帳管理器 - 整合 Google Sheets"""
    
    def __init__(self):
        """初始化股票資料和 Google Sheets 連接"""
        self.stock_data = {
            'accounts': {},
            'transactions': []
        }
        
        # Google Sheets 設定
        self.spreadsheet_url = "https://docs.google.com/spreadsheets/d/1EACr2Zu7_regqp3Po7AlNE4ZcjazKbgyvz-yYNYtcCs/edit?usp=sharing"
        self.gc = None
        self.sheet = None
        
        # 初始化 Google Sheets 連接
        self.init_google_sheets()
        
        # 從 Google Sheets 載入資料
        self.load_from_sheets()
    
    def init_google_sheets(self):
        """初始化 Google Sheets 連接"""
        try:
            # 從環境變數獲取憑證
            creds_json = os.getenv('GOOGLE_CREDENTIALS')
            
            if creds_json:
                # 使用環境變數中的憑證
                creds_dict = json.loads(creds_json)
                credentials = Credentials.from_service_account_info(
                    creds_dict,
                    scopes=['https://spreadsheets.google.com/feeds',
                           'https://www.googleapis.com/auth/drive']
                )
            else:
                # 如果沒有環境變數，使用預設憑證（開發時使用）
                credentials = Credentials.from_service_account_info(
                    {
                        "type": "service_account",
                        "project_id": "stock-manager-bot",
                        "private_key_id": "fe4f9f04bc9566c58c08b2430fcbd68b2bf5cf92",
                        "private_key": "-----BEGIN PRIVATE KEY-----\nMIIEvAIBADANBgkqhkiG9w0BAQEFAASCBKYwggSiAgEAAoIBAQDcT1s1djGAbCVu\nB9kCo4Y2r2ouTGZlDpwsK4+hqj6z8BbQXOEvoqVvqR6Y6DSgZ8n2DBNZ0WN6Flev\ne9c+HcgPOZdsD3Iy0FRPZlbcFLwvpsnJFLoJPph5NtUHFscvI/Z8FF8Tp4w5lYw+\nJBqHiKmzBooGRhLY+TJSveeN8idoshdhKatZI+7z+zBqv7d6cZ6JiUN5Dn6kx/sh\nBLqVzEjGcWMiSeC0Cr8gsvFQJQZP3+wByRbGDV2s4eOu7ncrU4HMXC17YOEC3hX/\nISX93aZfIw3NvsEWUKBz8AlINTU/GXODq1YPEoA9wX4C2xUUMHtz1RGb6S/+xh5l\nIGGHp4SVAgMBAAECggEAHGaxOsUlQImwkZdlZy0EN7c0GF/fsMDKFU+lppEMoE8f\n7HXszyKdR+B6LKV9aKhjUDA3q76N9RvoQJvVyxDfzPFUZKk2bvfjG+afj/kEVvLz\nfyldik+Ngc2LIkInehudbQWF9EIHQRfXCokbpRlTIdyCnVMZ9EAROBAknRdN8/W0\nO5AFyL7Q56/yY81oBx4z5Kb4VkKtEbLDadj6kfilt3ErFBGayjnzWQhg5/Bwjpgh\nANrJlwZWtdO1l3ejkjKMMGBPDPKnKD/9kL5qE3qnr8dWQ4W9lzzQl+k5mCBNVokZ\nKOrAu87l+ft000GUO4WGn3BxZkOw/6pR9VeXvC26iQKBgQD3oHPauQt/+0alDnEW\nbqLI06bq5sEv41aUoq5evYTueTYiQ5/wZoP9zpLJC+HeQ2P6K+FBW+UKXVMw7eOh\n4kUBlRD0OhWQxGlqZcK8+HRgqkmLFSB6/uPM3ddlbxaVOiUFYMo4qVdeLTUO0heJ\nDqh6QBJUuF8hjcQb/nPMHDxxUwKBgQDjwnCRRhWYh1rkfhF3o7p2W9hL7dwqSFOH\n2JnldjWLoN/zr9a3mvj7NKQrPya4Kuz1QpHtj1QWa/JN0TnZNY9EUF4g4B5x84m5\niQwmQw+bkLhw9Yrog4Fa8pRNRMAp9n+PTgzhKbTbdSnz92w8azUT27w/kGwAFAaW\nCThrNSftdwKBgCL7DaK2RUOdEYu7kIoksuY/z/KbCmtjaBWzLYLArwipItaQSwXA\n1aCDEAVKomuthXAPxtBe1Ooz6M6erGtv9WOV1UFK+0TqGiInoezkBDyrkZwOLfpy\nC2gjZowztzL5dcVeuPJsKaVqKXaggyafZXlvl6dULEwnJK73sRACZR91AoGAcoZB\nCCuPjGTzZVWm/tvLVNyWBIgUXwaDShm2ONWZ0x4Pvn86npREgjxUGJLmq1CaWjEh\nI60ggS3CZzK/veLaqWUoD6viYzYsmKi6/TpXTMgWlmZBdO07TDoSLFBXuEIEnlCG\n1WmdUYS2lcBiIndd9yBUpjm+tMNdFHCKeA4Ah70CgYAH6P6h1M4rMy8GUAUeomxQ\nVJ5NHGpt3Nalo6eHWW7RZpCXIiAXKXiEwKf/8QLU3VxArew+niu9lzn9e2K75P0E\npFECoYxgKn+MAPGYSKjNVFg6hwdnYYWnCnd6NAkGoqlo/QkJ1XjE+RHEQfvxZ/zg\nYP95hz4Uq0XDn2/lOPJdbw==\n-----END PRIVATE KEY-----\n",
                        "client_email": "stock-manager-bot-628@stock-manager-bot.iam.gserviceaccount.com",
                        "client_id": "102511237567756729838",
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.googleapis.com/token",
                        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                        "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/stock-manager-bot-628%40stock-manager-bot.iam.gserviceaccount.com",
                        "universe_domain": "googleapis.com"
                    },
                    scopes=['https://spreadsheets.google.com/feeds',
                           'https://www.googleapis.com/auth/drive']
                )
            
            self.gc = gspread.authorize(credentials)
            self.sheet = self.gc.open_by_url(self.spreadsheet_url)
            
            print("✅ Google Sheets 連接成功")
            
        except Exception as e:
            print(f"❌ Google Sheets 連接失敗: {e}")
            print("📝 將使用記憶體模式運行")
    
    def load_from_sheets(self):
        """從 Google Sheets 載入資料"""
        if not self.sheet:
            return
        
        try:
            # 載入帳戶資訊
            accounts_sheet = self.sheet.worksheet("帳戶資訊")
            accounts_data = accounts_sheet.get_all_records()
            
            for row in accounts_data:
                if row.get('帳戶名稱'):
                    self.stock_data['accounts'][row['帳戶名稱']] = {
                        'cash': int(row.get('現金餘額', 0)),
                        'stocks': {},
                        'created_date': row.get('建立日期', self.get_taiwan_time())
                    }
            
            # 載入持股明細
            holdings_sheet = self.sheet.worksheet("持股明細")
            holdings_data = holdings_sheet.get_all_records()
            
            for row in holdings_data:
                account_name = row.get('帳戶名稱')
                stock_name = row.get('股票名稱')
                
                if account_name and stock_name and account_name in self.stock_data['accounts']:
                    self.stock_data['accounts'][account_name]['stocks'][stock_name] = {
                        'quantity': int(row.get('持股數量', 0)),
                        'avg_cost': float(row.get('平均成本', 0)),
                        'total_cost': int(row.get('總成本', 0))
                    }
            
            # 載入交易記錄
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
            
            print(f"✅ 從 Google Sheets 載入資料成功")
            print(f"📊 帳戶數量: {len(self.stock_data['accounts'])}")
            print(f"📈 交易記錄: {len(self.stock_data['transactions'])} 筆")
            
        except Exception as e:
            print(f"❌ 載入 Google Sheets 資料失敗: {e}")
    
    def sync_to_sheets(self):
        """同步資料到 Google Sheets"""
        if not self.sheet:
            return False
        
        try:
            # 同步帳戶資訊
            accounts_sheet = self.sheet.worksheet("帳戶資訊")
            accounts_sheet.clear()
            
            # 設定標題
            accounts_sheet.append_row(['帳戶名稱', '現金餘額', '建立日期'])
            
            # 寫入帳戶資料
            for account_name, account_data in self.stock_data['accounts'].items():
                accounts_sheet.append_row([
                    account_name,
                    account_data['cash'],
                    account_data['created_date']
                ])
            
            # 同步持股明細
            holdings_sheet = self.sheet.worksheet("持股明細")
            holdings_sheet.clear()
            holdings_sheet.append_row(['帳戶名稱', '股票名稱', '持股數量', '平均成本', '總成本'])
            
            for account_name, account_data in self.stock_data['accounts'].items():
                for stock_name, stock_data in account_data['stocks'].items():
                    holdings_sheet.append_row([
                        account_name,
                        stock_name,
                        stock_data['quantity'],
                        stock_data['avg_cost'],
                        stock_data['total_cost']
                    ])
            
            # 同步交易記錄
            transactions_sheet = self.sheet.worksheet("交易記錄")
            transactions_sheet.clear()
            transactions_sheet.append_row([
                '交易ID', '類型', '帳戶', '股票名稱', '數量', '金額', 
                '單價', '日期', '現金餘額', '建立時間', '損益'
            ])
            
            for transaction in self.stock_data['transactions']:
                transactions_sheet.append_row([
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
            
            print("✅ 資料已同步到 Google Sheets")
            return True
            
        except Exception as e:
            print(f"❌ 同步到 Google Sheets 失敗: {e}")
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
            self.sync_to_sheets()  # 立即同步
            return True  # 新建立
        return False     # 已存在
    
    def parse_command(self, message_text):
        """解析股票相關指令"""
        message_text = message_text.strip()
        
        # 入帳：爸爸入帳 50000
        if match := re.match(r'(.+?)入帳\s*(\d+)', message_text):
            account, amount = match.groups()
            return {
                'type': 'deposit',
                'account': account.strip(),
                'amount': int(amount)
            }
        
        # 提款：媽媽提款 10000
        elif match := re.match(r'(.+?)提款\s*(\d+)', message_text):
            account, amount = match.groups()
            return {
                'type': 'withdraw',
                'account': account.strip(),
                'amount': int(amount)
            }
        
        # 持有（新功能）：爸爸持有 台積電 200 120000
        elif match := re.match(r'(.+?)持有\s+(.+?)\s+(\d+)\s+(\d+)', message_text):
            account, stock_name, quantity, total_cost = match.groups()
            return {
                'type': 'holding',
                'account': account.strip(),
                'stock_name': stock_name.strip(),
                'quantity': int(quantity),
                'total_cost': int(total_cost)
            }
        
        # 買入（支援自訂名稱）：爸爸買 台積電 100 50000 0820
        elif match := re.match(r'(.+?)買\s+(.+?)\s+(\d+)\s+(\d+)\s+(\d{4})$', message_text):
            account, stock_name, quantity, amount, date = match.groups()
            # 轉換日期格式 0820 -> 2024/08/20
            try:
                year = datetime.now().year
                month = int(date[:2])
                day = int(date[2:])
                formatted_date = f"{year}/{month:02d}/{day:02d}"
            except:
                return None
            
            return {
                'type': 'buy',
                'account': account.strip(),
                'stock_name': stock_name.strip(),
                'quantity': int(quantity),
                'amount': int(amount),
                'date': formatted_date
            }
        
        # 賣出（支援自訂名稱）：媽媽賣 台積電 50 5000 0821
        elif match := re.match(r'(.+?)賣\s+(.+?)\s+(\d+)\s+(\d+)\s+(\d{4})$', message_text):
            account, stock_name, quantity, amount, date = match.groups()
            try:
                year = datetime.now().year
                month = int(date[:2])
                day = int(date[2:])
                formatted_date = f"{year}/{month:02d}/{day:02d}"
            except:
                return None
            
            return {
                'type': 'sell',
                'account': account.strip(),
                'stock_name': stock_name.strip(),
                'quantity': int(quantity),
                'amount': int(amount),
                'date': formatted_date
            }
        
        # 新增帳戶：新增帳戶 奶奶
        elif match := re.match(r'新增帳戶\s*(.+)', message_text):
            account = match.group(1).strip()
            return {
                'type': 'create_account',
                'account': account
            }
        
        return None
    
    def handle_holding(self, account_name, stock_name, quantity, total_cost):
        """處理持有股票設定"""
        is_new = self.get_or_create_account(account_name)
        
        # 計算平均成本
        avg_cost = round(total_cost / quantity, 2)
        
        # 設定持股
        self.stock_data['accounts'][account_name]['stocks'][stock_name] = {
            'quantity': quantity,
            'total_cost': total_cost,
            'avg_cost': avg_cost
        }
        
        # 記錄交易（設定初始持股）
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
        
        # 同步到 Google Sheets
        self.sync_to_sheets()
        
        result_msg = f"📊 {account_name} 持股設定成功！\n"
        if is_new:
            result_msg += f"🆕 已建立新帳戶\n"
        result_msg += f"🏷️ {stock_name}\n"
        result_msg += f"📈 持股：{quantity}股\n"
        result_msg += f"💰 總成本：{total_cost:,}元\n"
        result_msg += f"💵 平均成本：{avg_cost}元/股\n"
        result_msg += f"☁️ 已同步到 Google Sheets"
        
        return result_msg
    
    def handle_deposit(self, account_name, amount):
        """處理入帳"""
        is_new = self.get_or_create_account(account_name)
        self.stock_data['accounts'][account_name]['cash'] += amount
        
        # 記錄交易
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
        
        # 同步到 Google Sheets
        self.sync_to_sheets()
        
        result_msg = f"💰 {account_name} 入帳成功！\n"
        if is_new:
            result_msg += f"🆕 已建立新帳戶\n"
        result_msg += f"💵 入帳金額：{amount:,}元\n"
        result_msg += f"💳 帳戶餘額：{self.stock_data['accounts'][account_name]['cash']:,}元\n"
        result_msg += f"☁️ 已同步到 Google Sheets"
        
        return result_msg
    
    def handle_withdraw(self, account_name, amount):
        """處理提款"""
        if account_name not in self.stock_data['accounts']:
            return f"❌ 帳戶「{account_name}」不存在"
        
        account = self.stock_data['accounts'][account_name]
        if account['cash'] < amount:
            return f"❌ 餘額不足！\n💳 目前餘額：{account['cash']:,}元\n💸 提款金額：{amount:,}元"
        
        account['cash'] -= amount
        
        # 記錄交易
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
        
        # 同步到 Google Sheets
        self.sync_to_sheets()
        
        return f"💸 {account_name} 提款成功！\n💵 提款金額：{amount:,}元\n💳 帳戶餘額：{account['cash']:,}元\n☁️ 已同步到 Google Sheets"
    
    def handle_buy(self, account_name, stock_name, quantity, amount, date):
        """處理買入股票"""
        if account_name not in self.stock_data['accounts']:
            return f"❌ 帳戶「{account_name}」不存在"
        
        account = self.stock_data['accounts'][account_name]
        if account['cash'] < amount:
            return f"❌ 餘額不足！\n💳 目前餘額：{account['cash']:,}元\n💰 需要金額：{amount:,}元"
        
        # 扣除現金
        account['cash'] -= amount
        
        # 計算每股價格
        price_per_share = round(amount / quantity, 2)
        
        # 更新持股
        if stock_name in account['stocks']:
            # 已有持股，計算新的平均成本
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
            # 新股票
            account['stocks'][stock_name] = {
                'quantity': quantity,
                'total_cost': amount,
                'avg_cost': price_per_share
            }
        
        # 記錄交易
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
        
        # 同步到 Google Sheets
        self.sync_to_sheets()
        
        stock_info = account['stocks'][stock_name]
        return f"📈 {account_name} 買入成功！\n\n🏷️ {stock_name}\n📊 買入：{quantity}股 @ {price_per_share}元\n💰 實付：{amount:,}元\n📅 日期：{date}\n\n📋 持股狀況：\n📊 總持股：{stock_info['quantity']}股\n💵 平均成本：{stock_info['avg_cost']}元/股\n💳 剩餘現金：{account['cash']:,}元\n☁️ 已同步到 Google Sheets"
    
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
        
        # 計算每股價格
        price_per_share = round(amount / quantity, 2)
        
        # 計算損益
        sell_cost = round(holding['avg_cost'] * quantity, 2)
        profit_loss = amount - sell_cost
        
        # 增加現金
        account['cash'] += amount
        
        # 更新持股
        remaining_quantity = holding['quantity'] - quantity
        if remaining_quantity > 0:
            # 還有剩餘持股
            remaining_cost = holding['total_cost'] - sell_cost
            account['stocks'][stock_name] = {
                'quantity': remaining_quantity,
                'total_cost': remaining_cost,
                'avg_cost': holding['avg_cost']  # 平均成本不變
            }
        else:
            # 全部賣完
            del account['stocks'][stock_name]
        
        # 記錄交易
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
        
        # 同步到 Google Sheets
        self.sync_to_sheets()
        
        profit_text = f"💰 獲利：+{profit_loss:,}元" if profit_loss > 0 else f"💸 虧損：{profit_loss:,}元" if profit_loss < 0 else "💫 損益兩平"
        
        result = f"📉 {account_name} 賣出成功！\n\n🏷️ {stock_name}\n📊 賣出：{quantity}股 @ {price_per_share}元\n💰 實收：{amount:,}元\n📅 日期：{date}\n\n💹 本次交易：\n💵 成本：{sell_cost:,}元\n{profit_text}\n💳 現金餘額：{account['cash']:,}元\n☁️ 已同步到 Google Sheets"
        
        if remaining_quantity > 0:
            result += f"\n\n📋 剩餘持股：{remaining_quantity}股"
        else:
            result += f"\n\n✅ 已全部賣出 {stock_name}"
        
        return result
    
    def create_account(self, account_name):
        """建立新帳戶"""
        is_new = self.get_or_create_account(account_name)
        if is_new:
            return f"🆕 已建立帳戶「{account_name}」\n💡 可以開始入帳和交易了！\n☁️ 已同步到 Google Sheets"
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
                    
                    # 統計總持股
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
        
        result += f"\n☁️ 資料來源：Google Sheets"
        
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
        
        # 按時間倒序
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
        
        result += f"☁️ 資料來源：Google Sheets"
        
        return result
    
    def get_cost_analysis(self, account_name, stock_input):
        """獲取特定股票的成本分析"""
        if account_name not in self.stock_data['accounts']:
            return f"❌ 帳戶「{account_name}」不存在"
        
        account = self.stock_data['accounts'][account_name]
        
        # 尋找匹配的股票名稱
        stock_name = None
        for name in account['stocks'].keys():
            if stock_input.lower() in name.lower() or name.lower() in stock_input.lower():
                stock_name = name
                break
        
        if not stock_name:
            return f"❌ {account_name} 沒有持有「{stock_input}」相關的股票"
        
        holding = account['stocks'][stock_name]
        
        # 查找相關交易記錄
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
        
        result += f"\n☁️ 資料來源：Google Sheets"
        
        return result
    
    def get_account_list(self):
        """獲取帳戶列表"""
        if self.stock_data['accounts']:
            account_list = list(self.stock_data['accounts'].keys())
            result = f"👥 目前帳戶列表：\n\n" + "\n".join([f"👤 {name}" for name in account_list])
            result += f"\n\n☁️ 資料來源：Google Sheets"
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
            
        except Exception as e:
            return f"❌ 處理失敗：{str(e)}\n💡 請檢查指令格式"
        
        return "❌ 未知的指令類型"
    
    def get_help_text(self):
        """獲取幫助訊息"""
        return """💰 多帳戶股票記帳功能 v2.0 + Google Sheets：

📋 帳戶管理：
- 爸爸入帳 50000 - 入金
- 媽媽提款 10000 - 提款  
- 新增帳戶 奶奶 - 建立帳戶

📊 持股設定（新功能）：
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

📝 格式說明：
• 支援任意股票名稱：台積電、鴻海、我的好股票 等
• 日期：0820 = 8月20日，1225 = 12月25日
• 持有指令：帳戶 持有 股票名稱 股數 總成本

☁️ v2.0 新功能：
• Google Sheets 雲端同步
• 支援自訂股票名稱  
• 初始持股設定
• 資料永久保存"""


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


def get_stock_transactions(account_name=None, limit=10):
    """獲取交易記錄 - 對外接口"""
    return stock_manager.get_transaction_history(account_name, limit)


def get_stock_cost_analysis(account_name, stock_code):
    """獲取成本分析 - 對外接口"""
    return stock_manager.get_cost_analysis(account_name, stock_code)


def get_stock_account_list():
    """獲取帳戶列表 - 對外接口"""
    return stock_manager.get_account_list()


def get_stock_help():
    """獲取股票幫助 - 對外接口"""
    return stock_manager.get_help_text()


def is_stock_command(message_text):
    """判斷是否為股票指令 - 對外接口"""
    stock_keywords = ['買入', '賣出', '入帳', '提款', '新增帳戶', '持有']
    return any(keyword in message_text for keyword in stock_keywords) or \
           re.match(r'.+?(買|賣|持有)\s+', message_text) is not None


def is_stock_query(message_text):
    """判斷是否為股票查詢指令 - 對外接口"""
    query_patterns = [
        '總覽',
        '帳戶列表',
        '股票幫助',
        '交易記錄',
        '成本查詢'
    ]
    
    return any(pattern in message_text for pattern in query_patterns) or \
           message_text.endswith('查詢')


# 使用範例
if __name__ == "__main__":
    # 測試股票管理器
    sm = StockManager()
    
    # 測試持有
    print("=== 測試持有 ===")
    print(sm.handle_command("爸爸持有 台積電 200 120000"))
    print()
    
    # 測試入帳
    print("=== 測試入帳 ===")
    print(sm.handle_command("爸爸入帳 100000"))
    print()
    
    # 測試買入
    print("=== 測試買入 ===")
    print(sm.handle_command("爸爸買 台積電 100 50000 0820"))
    print()
    
    # 測試查詢
    print("=== 測試查詢 ===")
    print(sm.get_account_summary("爸爸"))
    print()
    
    # 測試總覽
    print("=== 測試總覽 ===")
    print(sm.get_all_accounts_summary())
