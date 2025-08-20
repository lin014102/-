"""
stock_manager.py - 獨立股票記帳模組
多帳戶股票記帳系統
"""
import re
from datetime import datetime
import pytz

# 設定台灣時區
TAIWAN_TZ = pytz.timezone('Asia/Taipei')

class StockManager:
    """股票記帳管理器"""
    
    def __init__(self):
        """初始化股票資料"""
        self.stock_data = {
            'accounts': {
                # '爸爸': {
                #     'cash': 100000,
                #     'stocks': {
                #         '2330 台積電': {
                #             'quantity': 100,
                #             'total_cost': 50000,
                #             'avg_cost': 500.0
                #         }
                #     },
                #     'created_date': '2024/08/20'
                # }
            },
            'transactions': [
                # {
                #     'id': 1,
                #     'type': '買入',  # 買入/賣出/入帳/提款
                #     'account': '爸爸',
                #     'stock_code': '2330 台積電',
                #     'quantity': 100,
                #     'amount': 50000,
                #     'price_per_share': 500.0,
                #     'date': '2024/08/20',
                #     'cash_after': 50000,
                #     'created_at': '2024/08/20 15:30:00'
                # }
            ]
        }
        
        # 常見股票代碼對照表
        self.stock_names = {
            '2330': '台積電', '2317': '鴻海', '2454': '聯發科', '2308': '台達電',
            '2382': '廣達', '3711': '日月光', '2303': '聯電', '2881': '富邦金',
            '2412': '中華電', '1303': '南亞', '1301': '台塑', '2886': '兆豐金',
            '2357': '華碩', '2327': '國巨', '6505': '台塑化', '1216': '統一',
            '2891': '中信金', '2002': '中鋼', '3008': '大立光', '2395': '研華'
        }
    
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
        
        # 買入（簡化版）：爸爸買 2330 100 50000 0820
        elif match := re.match(r'(.+?)買\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d{4})$', message_text):
            account, code, quantity, amount, date = match.groups()
            # 轉換日期格式 0820 -> 2024/08/20
            try:
                year = datetime.now().year
                month = int(date[:2])
                day = int(date[2:])
                formatted_date = f"{year}/{month:02d}/{day:02d}"
            except:
                return None
            
            stock_name = self.stock_names.get(code, '未知股票')
            
            return {
                'type': 'buy',
                'account': account.strip(),
                'stock_code': f"{code} {stock_name}",
                'quantity': int(quantity),
                'amount': int(amount),
                'date': formatted_date
            }
        
        # 賣出（簡化版）：媽媽賣 2317 50 5000 0821
        elif match := re.match(r'(.+?)賣\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d{4})$', message_text):
            account, code, quantity, amount, date = match.groups()
            try:
                year = datetime.now().year
                month = int(date[:2])
                day = int(date[2:])
                formatted_date = f"{year}/{month:02d}/{day:02d}"
            except:
                return None
            
            stock_name = self.stock_names.get(code, '未知股票')
            
            return {
                'type': 'sell',
                'account': account.strip(),
                'stock_code': f"{code} {stock_name}",
                'quantity': int(quantity),
                'amount': int(amount),
                'date': formatted_date
            }
        
        # 買入（完整版）：爸爸買入 2330 台積電 100股 實付50000元 2024/08/20
        elif match := re.match(r'(.+?)買入\s*(\d+)\s*(.+?)\s*(\d+)股\s*實付(\d+)元\s*(\d{4}/\d{1,2}/\d{1,2})', message_text):
            account, code, name, quantity, amount, date = match.groups()
            return {
                'type': 'buy',
                'account': account.strip(),
                'stock_code': f"{code} {name.strip()}",
                'quantity': int(quantity),
                'amount': int(amount),
                'date': date.strip()
            }
        
        # 賣出（完整版）：媽媽賣出 2317 鴻海 50股 實收5000元 2024/08/21
        elif match := re.match(r'(.+?)賣出\s*(\d+)\s*(.+?)\s*(\d+)股\s*實收(\d+)元\s*(\d{4}/\d{1,2}/\d{1,2})', message_text):
            account, code, name, quantity, amount, date = match.groups()
            return {
                'type': 'sell',
                'account': account.strip(),
                'stock_code': f"{code} {name.strip()}",
                'quantity': int(quantity),
                'amount': int(amount),
                'date': date.strip()
            }
        
        # 新增帳戶：新增帳戶 奶奶
        elif match := re.match(r'新增帳戶\s*(.+)', message_text):
            account = match.group(1).strip()
            return {
                'type': 'create_account',
                'account': account
            }
        
        return None
    
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
        
        result_msg = f"💰 {account_name} 入帳成功！\n"
        if is_new:
            result_msg += f"🆕 已建立新帳戶\n"
        result_msg += f"💵 入帳金額：{amount:,}元\n"
        result_msg += f"💳 帳戶餘額：{self.stock_data['accounts'][account_name]['cash']:,}元"
        
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
        
        return f"💸 {account_name} 提款成功！\n💵 提款金額：{amount:,}元\n💳 帳戶餘額：{account['cash']:,}元"
    
    def handle_buy(self, account_name, stock_code, quantity, amount, date):
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
        if stock_code in account['stocks']:
            # 已有持股，計算新的平均成本
            existing = account['stocks'][stock_code]
            total_quantity = existing['quantity'] + quantity
            total_cost = existing['total_cost'] + amount
            avg_cost = round(total_cost / total_quantity, 2)
            
            account['stocks'][stock_code] = {
                'quantity': total_quantity,
                'total_cost': total_cost,
                'avg_cost': avg_cost
            }
        else:
            # 新股票
            account['stocks'][stock_code] = {
                'quantity': quantity,
                'total_cost': amount,
                'avg_cost': price_per_share
            }
        
        # 記錄交易
        transaction = {
            'id': len(self.stock_data['transactions']) + 1,
            'type': '買入',
            'account': account_name,
            'stock_code': stock_code,
            'quantity': quantity,
            'amount': amount,
            'price_per_share': price_per_share,
            'date': date,
            'cash_after': account['cash'],
            'created_at': self.get_taiwan_time()
        }
        self.stock_data['transactions'].append(transaction)
        
        stock_info = account['stocks'][stock_code]
        return f"📈 {account_name} 買入成功！\n\n🏷️ {stock_code}\n📊 買入：{quantity}股 @ {price_per_share}元\n💰 實付：{amount:,}元\n📅 日期：{date}\n\n📋 持股狀況：\n📊 總持股：{stock_info['quantity']}股\n💵 平均成本：{stock_info['avg_cost']}元/股\n💳 剩餘現金：{account['cash']:,}元"
    
    def handle_sell(self, account_name, stock_code, quantity, amount, date):
        """處理賣出股票"""
        if account_name not in self.stock_data['accounts']:
            return f"❌ 帳戶「{account_name}」不存在"
        
        account = self.stock_data['accounts'][account_name]
        if stock_code not in account['stocks']:
            return f"❌ 沒有持有「{stock_code}」"
        
        holding = account['stocks'][stock_code]
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
            account['stocks'][stock_code] = {
                'quantity': remaining_quantity,
                'total_cost': remaining_cost,
                'avg_cost': holding['avg_cost']  # 平均成本不變
            }
        else:
            # 全部賣完
            del account['stocks'][stock_code]
        
        # 記錄交易
        transaction = {
            'id': len(self.stock_data['transactions']) + 1,
            'type': '賣出',
            'account': account_name,
            'stock_code': stock_code,
            'quantity': quantity,
            'amount': amount,
            'price_per_share': price_per_share,
            'date': date,
            'cash_after': account['cash'],
            'created_at': self.get_taiwan_time(),
            'profit_loss': profit_loss
        }
        self.stock_data['transactions'].append(transaction)
        
        profit_text = f"💰 獲利：+{profit_loss:,}元" if profit_loss > 0 else f"💸 虧損：{profit_loss:,}元" if profit_loss < 0 else "💫 損益兩平"
        
        result = f"📉 {account_name} 賣出成功！\n\n🏷️ {stock_code}\n📊 賣出：{quantity}股 @ {price_per_share}元\n💰 實收：{amount:,}元\n📅 日期：{date}\n\n💹 本次交易：\n💵 成本：{sell_cost:,}元\n{profit_text}\n💳 現金餘額：{account['cash']:,}元"
        
        if remaining_quantity > 0:
            result += f"\n\n📋 剩餘持股：{remaining_quantity}股"
        else:
            result += f"\n\n✅ 已全部賣出 {stock_code}"
        
        return result
    
    def create_account(self, account_name):
        """建立新帳戶"""
        is_new = self.get_or_create_account(account_name)
        if is_new:
            return f"🆕 已建立帳戶「{account_name}」\n💡 可以開始入帳和交易了！"
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
            for stock_code, holding in account['stocks'].items():
                result += f"🏷️ {stock_code}\n"
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
            return "📝 目前沒有任何帳戶\n💡 輸入「爸爸入帳 100000」來建立第一個帳戶"
        
        result = "🏦 家庭投資總覽：\n\n"
        
        total_cash = 0
        total_investment = 0
        all_stocks = {}
        
        for account_name, account in self.stock_data['accounts'].items():
            result += f"👤 {account_name}：\n"
            result += f"   💳 現金 {account['cash']:,}元\n"
            
            account_investment = 0
            if account['stocks']:
                for stock_code, holding in account['stocks'].items():
                    result += f"   📈 {stock_code} {holding['quantity']}股\n"
                    account_investment += holding['total_cost']
                    
                    # 統計總持股
                    if stock_code in all_stocks:
                        all_stocks[stock_code] += holding['quantity']
                    else:
                        all_stocks[stock_code] = holding['quantity']
            
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
            for stock_code, total_quantity in all_stocks.items():
                result += f"🏷️ {stock_code}：{total_quantity}股\n"
        
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
                result += f"   💰 {t['amount']:,}元 @ {t['price_per_share']}元/股\n"
            else:
                result += f"   💰 {t['amount']:,}元\n"
            result += f"   📅 {t['date']} 💳餘額 {t['cash_after']:,}元\n\n"
        
        return result
    
    def get_cost_analysis(self, account_name, stock_code_input):
        """獲取特定股票的成本分析"""
        if account_name not in self.stock_data['accounts']:
            return f"❌ 帳戶「{account_name}」不存在"
        
        account = self.stock_data['accounts'][account_name]
        
        # 如果只輸入股票代碼，尋找完整的股票代碼+名稱
        stock_code = None
        if stock_code_input.isdigit():
            # 只輸入代碼，找到完整名稱
            for code in account['stocks'].keys():
                if code.startswith(stock_code_input + ' '):
                    stock_code = code
                    break
            if not stock_code:
                return f"❌ {account_name} 沒有持有代碼「{stock_code_input}」的股票"
        else:
            # 輸入完整名稱
            stock_code = stock_code_input
            if stock_code not in account['stocks']:
                return f"❌ {account_name} 沒有持有「{stock_code}」"
        
        holding = account['stocks'][stock_code]
        
        # 查找相關交易記錄
        related_transactions = [
            t for t in self.stock_data['transactions'] 
            if t['account'] == account_name and t['stock_code'] == stock_code
        ]
        
        result = f"📊 {account_name} - {stock_code} 成本分析：\n\n"
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
        
        return result
    
    def get_account_list(self):
        """獲取帳戶列表"""
        if self.stock_data['accounts']:
            account_list = list(self.stock_data['accounts'].keys())
            return f"👥 目前帳戶列表：\n\n" + "\n".join([f"👤 {name}" for name in account_list])
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
            
            elif parsed['type'] == 'buy':
                return self.handle_buy(
                    parsed['account'], parsed['stock_code'], 
                    parsed['quantity'], parsed['amount'], parsed['date']
                )
            
            elif parsed['type'] == 'sell':
                return self.handle_sell(
                    parsed['account'], parsed['stock_code'], 
                    parsed['quantity'], parsed['amount'], parsed['date']
                )
            
            elif parsed['type'] == 'create_account':
                return self.create_account(parsed['account'])
            
        except Exception as e:
            return f"❌ 處理失敗：{str(e)}\n💡 請檢查指令格式"
        
        return "❌ 未知的指令類型"
    
    def get_help_text(self):
        """獲取幫助訊息"""
        return """💰 多帳戶股票記帳功能：

📋 帳戶管理：
- 爸爸入帳 50000 - 入金
- 媽媽提款 10000 - 提款  
- 新增帳戶 奶奶 - 建立帳戶

📈 交易操作：
🔸 簡化版（推薦）：
- 爸爸買 2330 100 50000 0820 - 買股票
- 媽媽賣 2317 50 5000 0821 - 賣股票

🔸 完整版（向下相容）：
- 爸爸買入 2330 台積電 100股 實付50000元 2024/08/20
- 媽媽賣出 2317 鴻海 50股 實收5000元 2024/08/21

📊 查詢功能：
- 總覽 - 所有帳戶總覽
- 爸爸查詢 - 個人資金和持股
- 交易記錄 - 所有交易歷史
- 交易記錄 爸爸 - 個人交易記錄
- 成本查詢 爸爸 2330 - 持股成本分析
- 帳戶列表 - 查看所有帳戶

📝 格式說明：
• 簡化版：帳戶 買/賣 股票代碼 股數 金額 日期(MMDD)
• 日期：0820 = 8月20日，1225 = 12月25日
• 自動識別股票：2330=台積電、2317=鴻海等

💡 v3.0：交易指令更簡潔，獨立模組設計！"""


# 建立全域實例
stock_manager = StockManager()


# 對外接口函數，供 app.py 使用
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
    stock_keywords = ['買入', '賣出', '入帳', '提款', '新增帳戶']
    return any(keyword in message_text for keyword in stock_keywords) or \
           re.match(r'.+?(買|賣)\s+\d+', message_text) is not None


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
    
    # 測試入帳
    print("=== 測試入帳 ===")
    print(sm.handle_command("爸爸入帳 100000"))
    print()
    
    # 測試買入
    print("=== 測試買入 ===")
    print(sm.handle_command("爸爸買 2330 100 50000 0820"))
    print()
    
    # 測試查詢
    print("=== 測試查詢 ===")
    print(sm.get_account_summary("爸爸"))
    print()
    
    # 測試總覽
    print("=== 測試總覽 ===")
    print(sm.get_all_accounts_summary())
