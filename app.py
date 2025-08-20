"""
LINE Todo Reminder Bot - 加入股票記帳功能
v3.0 - 多帳戶股票記帳版本
"""
from flask import Flask, request, jsonify
import os
import requests
import json
import re
import threading
import time
from datetime import datetime, timedelta
import pytz

app = Flask(__name__)

# 設定台灣時區
TAIWAN_TZ = pytz.timezone('Asia/Taipei')

# ===== 待辦事項資料儲存 =====
todos = []
monthly_todos = []
short_reminders = []
time_reminders = []
user_settings = {
    'morning_time': '09:00',
    'evening_time': '18:00',
    'user_id': None
}

# ===== 股票記帳資料儲存 =====
stock_data = {
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

# LINE Bot 設定
CHANNEL_ACCESS_TOKEN = os.getenv('CHANNEL_ACCESS_TOKEN', '')
LINE_API_URL = 'https://api.line.me/v2/bot/message/reply'
PUSH_API_URL = 'https://api.line.me/v2/bot/message/push'

# ===== 時間相關函數 =====
def get_taiwan_time():
    """獲取台灣時間"""
    return datetime.now(TAIWAN_TZ).strftime('%Y/%m/%d %H:%M:%S')

def get_taiwan_time_hhmm():
    """獲取台灣時間 HH:MM"""
    return datetime.now(TAIWAN_TZ).strftime('%H:%M')

def get_taiwan_datetime():
    """獲取台灣時間的 datetime 物件"""
    return datetime.now(TAIWAN_TZ)

def is_valid_time_format(time_str):
    """驗證時間格式是否正確"""
    if ':' not in time_str or len(time_str) > 5:
        return False
    
    try:
        parts = time_str.split(':')
        if len(parts) != 2:
            return False
        
        hours = int(parts[0])
        minutes = int(parts[1])
        
        return 0 <= hours <= 23 and 0 <= minutes <= 59
    except:
        return False

# ===== 股票功能函數 =====
def get_or_create_account(account_name):
    """獲取或建立帳戶"""
    if account_name not in stock_data['accounts']:
        stock_data['accounts'][account_name] = {
            'cash': 0,
            'stocks': {},
            'created_date': get_taiwan_time()
        }
        return True  # 新建立
    return False     # 已存在

def parse_stock_command(message_text):
    """解析股票相關指令 - 簡化版本"""
    message_text = message_text.strip()
    
    # 入帳：入 爸爸 50000
    if match := re.match(r'^入\s+(.+?)\s+(\d+)

def handle_stock_deposit(account_name, amount):
    """處理入帳"""
    is_new = get_or_create_account(account_name)
    stock_data['accounts'][account_name]['cash'] += amount
    
    # 記錄交易
    transaction = {
        'id': len(stock_data['transactions']) + 1,
        'type': '入帳',
        'account': account_name,
        'stock_code': None,
        'quantity': 0,
        'amount': amount,
        'price_per_share': 0,
        'date': get_taiwan_time().split(' ')[0],
        'cash_after': stock_data['accounts'][account_name]['cash'],
        'created_at': get_taiwan_time()
    }
    stock_data['transactions'].append(transaction)
    
    result_msg = f"💰 {account_name} 入帳成功！\n"
    if is_new:
        result_msg += f"🆕 已建立新帳戶\n"
    result_msg += f"💵 入帳金額：{amount:,}元\n"
    result_msg += f"💳 帳戶餘額：{stock_data['accounts'][account_name]['cash']:,}元"
    
    return result_msg

def handle_stock_withdraw(account_name, amount):
    """處理提款"""
    if account_name not in stock_data['accounts']:
        return f"❌ 帳戶「{account_name}」不存在"
    
    account = stock_data['accounts'][account_name]
    if account['cash'] < amount:
        return f"❌ 餘額不足！\n💳 目前餘額：{account['cash']:,}元\n💸 提款金額：{amount:,}元"
    
    account['cash'] -= amount
    
    # 記錄交易
    transaction = {
        'id': len(stock_data['transactions']) + 1,
        'type': '提款',
        'account': account_name,
        'stock_code': None,
        'quantity': 0,
        'amount': amount,
        'price_per_share': 0,
        'date': get_taiwan_time().split(' ')[0],
        'cash_after': account['cash'],
        'created_at': get_taiwan_time()
    }
    stock_data['transactions'].append(transaction)
    
    return f"💸 {account_name} 提款成功！\n💵 提款金額：{amount:,}元\n💳 帳戶餘額：{account['cash']:,}元"

def handle_stock_buy(account_name, stock_code, quantity, amount, date):
    """處理買入股票"""
    if account_name not in stock_data['accounts']:
        return f"❌ 帳戶「{account_name}」不存在"
    
    account = stock_data['accounts'][account_name]
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
        'id': len(stock_data['transactions']) + 1,
        'type': '買入',
        'account': account_name,
        'stock_code': stock_code,
        'quantity': quantity,
        'amount': amount,
        'price_per_share': price_per_share,
        'date': date,
        'cash_after': account['cash'],
        'created_at': get_taiwan_time()
    }
    stock_data['transactions'].append(transaction)
    
    stock_info = account['stocks'][stock_code]
    return f"📈 {account_name} 買入成功！\n\n🏷️ {stock_code}\n📊 買入：{quantity}股 @ {price_per_share}元\n💰 實付：{amount:,}元\n📅 日期：{date}\n\n📋 持股狀況：\n📊 總持股：{stock_info['quantity']}股\n💵 平均成本：{stock_info['avg_cost']}元/股\n💳 剩餘現金：{account['cash']:,}元"

def handle_stock_sell(account_name, stock_code, quantity, amount, date):
    """處理賣出股票"""
    if account_name not in stock_data['accounts']:
        return f"❌ 帳戶「{account_name}」不存在"
    
    account = stock_data['accounts'][account_name]
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
        'id': len(stock_data['transactions']) + 1,
        'type': '賣出',
        'account': account_name,
        'stock_code': stock_code,
        'quantity': quantity,
        'amount': amount,
        'price_per_share': price_per_share,
        'date': date,
        'cash_after': account['cash'],
        'created_at': get_taiwan_time(),
        'profit_loss': profit_loss
    }
    stock_data['transactions'].append(transaction)
    
    profit_text = f"💰 獲利：+{profit_loss:,}元" if profit_loss > 0 else f"💸 虧損：{profit_loss:,}元" if profit_loss < 0 else "💫 損益兩平"
    
    result = f"📉 {account_name} 賣出成功！\n\n🏷️ {stock_code}\n📊 賣出：{quantity}股 @ {price_per_share}元\n💰 實收：{amount:,}元\n📅 日期：{date}\n\n💹 本次交易：\n💵 成本：{sell_cost:,}元\n{profit_text}\n💳 現金餘額：{account['cash']:,}元"
    
    if remaining_quantity > 0:
        result += f"\n\n📋 剩餘持股：{remaining_quantity}股"
    else:
        result += f"\n\n✅ 已全部賣出 {stock_code}"
    
    return result

def get_account_summary(account_name):
    """獲取帳戶摘要"""
    if account_name not in stock_data['accounts']:
        return f"❌ 帳戶「{account_name}」不存在"
    
    account = stock_data['accounts'][account_name]
    
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

def get_all_accounts_summary():
    """獲取所有帳戶總覽"""
    if not stock_data['accounts']:
        return "📝 目前沒有任何帳戶\n💡 輸入「爸爸入帳 100000」來建立第一個帳戶"
    
    result = "🏦 家庭投資總覽：\n\n"
    
    total_cash = 0
    total_investment = 0
    all_stocks = {}
    
    for account_name, account in stock_data['accounts'].items():
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

def get_transaction_history(account_name=None, limit=10):
    """獲取交易記錄"""
    transactions = stock_data['transactions']
    
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

def get_stock_cost_analysis(account_name, stock_code_input):
    """獲取特定股票的成本分析 - 支援簡化輸入"""
    if account_name not in stock_data['accounts']:
        return f"❌ 帳戶「{account_name}」不存在"
    
    account = stock_data['accounts'][account_name]
    
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
        t for t in stock_data['transactions'] 
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

def handle_stock_command(message_text, user_id):
    """處理股票相關指令"""
    parsed = parse_stock_command(message_text)
    
    if not parsed:
        return "❌ 指令格式不正確\n💡 輸入「股票幫助」查看使用說明"
    
    try:
        if parsed['type'] == 'deposit':
            return handle_stock_deposit(parsed['account'], parsed['amount'])
        
        elif parsed['type'] == 'withdraw':
            return handle_stock_withdraw(parsed['account'], parsed['amount'])
        
        elif parsed['type'] == 'buy':
            return handle_stock_buy(
                parsed['account'], parsed['stock_code'], 
                parsed['quantity'], parsed['amount'], parsed['date']
            )
        
        elif parsed['type'] == 'sell':
            return handle_stock_sell(
                parsed['account'], parsed['stock_code'], 
                parsed['quantity'], parsed['amount'], parsed['date']
            )
        
        elif parsed['type'] == 'create_account':
            is_new = get_or_create_account(parsed['account'])
            if is_new:
                return f"🆕 已建立帳戶「{parsed['account']}」\n💡 可以開始入帳和交易了！"
            else:
                return f"ℹ️ 帳戶「{parsed['account']}」已存在"
        
    except Exception as e:
        return f"❌ 處理失敗：{str(e)}\n💡 請檢查指令格式"
    
    return "❌ 未知的指令類型"

# ===== 待辦事項功能函數 (保持原有) =====
def parse_date(text):
    """解析日期格式 - 改進版本，更好地處理每月事項"""
    taiwan_now = get_taiwan_datetime()
    current_year = taiwan_now.year
    
    # 改進的日期模式，更靈活地匹配
    patterns = [
        # 格式：24號繳水電卡費
        (r'(\d{1,2})號(.+)', 'day_only'),
        # 格式：8/24繳水電卡費 或 8/24號繳水電卡費
        (r'(\d{1,2})\/(\d{1,2})號?(.+)', 'month_day'),
        # 格式：繳水電卡費24號
        (r'(.+?)(\d{1,2})號', 'content_day'),
        # 格式：繳水電卡費8/24
        (r'(.+?)(\d{1,2})\/(\d{1,2})號?', 'content_month_day')
    ]
    
    for pattern, pattern_type in patterns:
        match = re.search(pattern, text)
        if match:
            print(f"DEBUG: 匹配到模式 {pattern_type}: {match.groups()}")
            
            if pattern_type == 'day_only':
                # 24號繳水電卡費
                day = int(match.group(1))
                content = match.group(2).strip()
                if 1 <= day <= 31 and content:
                    # 使用當前月份
                    month = taiwan_now.month
                    target_date = taiwan_now.replace(year=current_year, month=month, day=day,
                                                   hour=0, minute=0, second=0, microsecond=0)
                    if target_date < taiwan_now:
                        if month == 12:
                            target_date = target_date.replace(year=current_year + 1, month=1)
                        else:
                            target_date = target_date.replace(month=month + 1)
                    
                    return {
                        "has_date": True,
                        "date": target_date,
                        "content": content,
                        "date_string": f"{month}/{day}",
                        "day_only": day  # 新增：只有日期的情況
                    }
                    
            elif pattern_type == 'month_day':
                # 8/24繳水電卡費
                month = int(match.group(1))
                day = int(match.group(2))
                content = match.group(3).strip()
                
                if 1 <= month <= 12 and 1 <= day <= 31 and content:
                    target_date = taiwan_now.replace(year=current_year, month=month, day=day,
                                                   hour=0, minute=0, second=0, microsecond=0)
                    if target_date < taiwan_now:
                        target_date = target_date.replace(year=current_year + 1)
                    
                    return {
                        "has_date": True,
                        "date": target_date,
                        "content": content,
                        "date_string": f"{month}/{day}"
                    }
                    
            elif pattern_type == 'content_day':
                # 繳水電卡費24號
                content = match.group(1).strip()
                day = int(match.group(2))
                
                if 1 <= day <= 31 and content:
                    month = taiwan_now.month
                    target_date = taiwan_now.replace(year=current_year, month=month, day=day,
                                                   hour=0, minute=0, second=0, microsecond=0)
                    if target_date < taiwan_now:
                        if month == 12:
                            target_date = target_date.replace(year=current_year + 1, month=1)
                        else:
                            target_date = target_date.replace(month=month + 1)
                    
                    return {
                        "has_date": True,
                        "date": target_date,
                        "content": content,
                        "date_string": f"{month}/{day}",
                        "day_only": day
                    }
                    
            elif pattern_type == 'content_month_day':
                # 繳水電卡費8/24
                content = match.group(1).strip()
                month = int(match.group(2))
                day = int(match.group(3))
                
                if 1 <= month <= 12 and 1 <= day <= 31 and content:
                    target_date = taiwan_now.replace(year=current_year, month=month, day=day,
                                                   hour=0, minute=0, second=0, microsecond=0)
                    if target_date < taiwan_now:
                        target_date = target_date.replace(year=current_year + 1)
                    
                    return {
                        "has_date": True,
                        "date": target_date,
                        "content": content,
                        "date_string": f"{month}/{day}"
                    }
    
    print(f"DEBUG: 沒有匹配到任何日期模式，原文: {text}")
    return {"has_date": False, "content": text}

def parse_short_reminder(text):
    """解析短期提醒"""
    patterns = [
        (r'(\d+)分鐘後(.+)', '分鐘', 1),
        (r'(\d+)小時後(.+)', '小時', 60),
        (r'(\d+)秒後(.+)', '秒', 1/60)
    ]
    
    for pattern, unit, multiplier in patterns:
        match = re.search(pattern, text)
        if match:
            value = int(match.group(1))
            content = match.group(2).strip()
            
            if not content:
                return {"is_valid": False, "error": "請輸入提醒內容"}
            
            minutes = value * multiplier
            
            if unit == '分鐘' and not (1 <= value <= 1440):
                return {"is_valid": False, "error": "分鐘數請設定在 1-1440 之間"}
            elif unit == '小時' and not (1 <= value <= 24):
                return {"is_valid": False, "error": "小時數請設定在 1-24 之間"}
            elif unit == '秒' and not (10 <= value <= 3600):
                return {"is_valid": False, "error": "秒數請設定在 10-3600 之間"}
            
            return {
                "is_valid": True,
                "minutes": minutes,
                "original_value": value,
                "unit": unit,
                "content": content
            }
    
    return {"is_valid": False, "error": "格式不正確，請使用：數字+時間單位+後+內容\n例如：5分鐘後倒垃圾"}

def parse_time_reminder(text):
    """解析時間提醒"""
    time_pattern = r'(\d{1,2}):(\d{2})(.+)'
    match = re.search(time_pattern, text)
    
    if match:
        hours = int(match.group(1))
        minutes = int(match.group(2))
        content = match.group(3).strip()
        
        if not content:
            return {"is_valid": False, "error": "請輸入提醒內容"}
        
        if not (0 <= hours <= 23):
            return {"is_valid": False, "error": "小時請設定在 0-23 之間"}
        
        if not (0 <= minutes <= 59):
            return {"is_valid": False, "error": "分鐘請設定在 0-59 之間"}
        
        return {
            "is_valid": True,
            "hours": hours,
            "minutes": minutes,
            "time_string": f"{hours:02d}:{minutes:02d}",
            "content": content
        }
    
    return {"is_valid": False, "error": "格式不正確，請使用：HH:MM+內容\n例如：12:00倒垃圾"}

# ===== LINE API 函數 =====
def send_push_message(user_id, message_text):
    """發送推播訊息"""
    if not CHANNEL_ACCESS_TOKEN or not user_id:
        print(f"模擬推播給 {user_id}: {message_text} (台灣時間: {get_taiwan_time()})")
        return False
    
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {CHANNEL_ACCESS_TOKEN}'
    }
    
    data = {
        'to': user_id,
        'messages': [{
            'type': 'text',
            'text': message_text
        }]
    }
    
    try:
        response = requests.post(PUSH_API_URL, headers=headers, data=json.dumps(data))
        print(f"推播發送 - 狀態碼: {response.status_code} - 台灣時間: {get_taiwan_time()}")
        return response.status_code == 200
    except Exception as e:
        print(f"推播失敗: {e} - 台灣時間: {get_taiwan_time()}")
        return False

def reply_message(reply_token, message_text):
    """回覆訊息"""
    if not CHANNEL_ACCESS_TOKEN:
        print(f"模擬回覆: {message_text} (台灣時間: {get_taiwan_time()})")
        return False
    
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {CHANNEL_ACCESS_TOKEN}'
    }
    
    data = {
        'replyToken': reply_token,
        'messages': [{
            'type': 'text',
            'text': message_text
        }]
    }
    
    try:
        response = requests.post(LINE_API_URL, headers=headers, data=json.dumps(data))
        return response.status_code == 200
    except Exception as e:
        print(f"回覆失敗: {e} - 台灣時間: {get_taiwan_time()}")
        return False

# ===== 提醒系統函數 =====
def check_reminders():
    """檢查並發送提醒 - 改進版本"""
    while True:
        try:
            current_time = get_taiwan_time_hhmm()
            user_id = user_settings.get('user_id')
            taiwan_now = get_taiwan_datetime()
            
            print(f"🔍 提醒檢查 - 台灣時間: {get_taiwan_time()}")
            
            # 檢查定時提醒（每日早晚） - 改進：每次都提醒所有待辦事項
            if user_id and (current_time == user_settings['morning_time'] or current_time == user_settings['evening_time']):
                send_daily_reminder(user_id, current_time)
            
            # 檢查每月提醒 - 改進：前一天預告 + 當天提醒
            if current_time == user_settings['evening_time']:  # 晚上檢查明天的每月事項
                check_monthly_preview(taiwan_now, user_id)
            
            if current_time == "09:00":  # 早上檢查今天的每月事項
                check_monthly_reminders(taiwan_now, user_id)
            
            # 檢查短期提醒
            check_short_reminders(taiwan_now)
            
            # 檢查時間提醒
            check_time_reminders(taiwan_now)
            
            time.sleep(60)  # 每分鐘檢查一次
        except Exception as e:
            print(f"提醒檢查錯誤: {e} - 台灣時間: {get_taiwan_time()}")
            time.sleep(60)

def send_daily_reminder(user_id, current_time):
    """發送每日提醒 - 改進版本：每次都提醒所有待辦事項"""
    time_icon = '🌅' if current_time == user_settings['morning_time'] else '🌙'
    time_text = '早安' if current_time == user_settings['morning_time'] else '晚安'
    
    if todos:
        # 分類待辦事項
        pending_todos = [todo for todo in todos if not todo.get('completed', False)]
        completed_todos = [todo for todo in todos if todo.get('completed', False)]
        
        if pending_todos:
            message = f'{time_icon} {time_text}！您有 {len(pending_todos)} 項待辦事項：\n\n'
            
            # 顯示未完成的事項（最多5項）
            for i, todo in enumerate(pending_todos[:5], 1):
                date_info = f" 📅{todo.get('target_date', '')}" if todo.get('has_date') else ""
                message += f'{i}. ⭕ {todo["content"]}{date_info}\n'
            
            if len(pending_todos) > 5:
                message += f'\n...還有 {len(pending_todos) - 5} 項未完成\n'
            
            # 如果有已完成的事項，也顯示（最多2項）
            if completed_todos:
                message += f'\n✅ 已完成 {len(completed_todos)} 項：\n'
                for todo in completed_todos[:2]:
                    message += f'✅ {todo["content"]}\n'
                if len(completed_todos) > 2:
                    message += f'...還有 {len(completed_todos) - 2} 項已完成\n'
            
            if current_time == user_settings['morning_time']:
                message += f'\n💪 新的一天開始了！加油完成這些任務！'
            else:
                message += f'\n🌙 檢查一下今天的進度吧！記得為明天做準備！'
                
            message += f'\n🇹🇼 台灣時間: {get_taiwan_time_hhmm()}'
            
            send_push_message(user_id, message)
            print(f"✅ 已發送每日提醒 ({len(pending_todos)} 項待辦) - 台灣時間: {get_taiwan_time()}")
        else:
            # 所有事項都已完成
            if current_time == user_settings['morning_time']:
                message = f'{time_icon} {time_text}！🎉 太棒了！目前沒有待辦事項\n💡 可以新增今天要做的事情'
            else:
                message = f'{time_icon} {time_text}！🎉 太棒了！今天的任務都完成了\n😴 好好休息，為明天準備新的目標！'
            
            message += f'\n🇹🇼 台灣時間: {get_taiwan_time_hhmm()}'
            send_push_message(user_id, message)
            print(f"✅ 已發送每日提醒 (無待辦事項) - 台灣時間: {get_taiwan_time()}")
    else:
        # 完全沒有任何事項
        if current_time == user_settings['morning_time']:
            message = f'{time_icon} {time_text}！✨ 新的一天開始了！\n💡 輸入「新增 事項名稱」來建立今天的目標'
        else:
            message = f'{time_icon} {time_text}！😌 今天過得如何？\n💡 別忘了為明天規劃一些目標'
        
        message += f'\n🇹🇼 台灣時間: {get_taiwan_time_hhmm()}'
        send_push_message(user_id, message)
        print(f"✅ 已發送每日提醒 (首次使用) - 台灣時間: {get_taiwan_time()}")

def check_monthly_preview(taiwan_now, user_id):
    """檢查明天的每月提醒 - 新增功能：前一天預告"""
    if not monthly_todos or not user_id:
        return
    
    tomorrow = taiwan_now + timedelta(days=1)
    tomorrow_day = tomorrow.day
    
    # 檢查明天是否有每月事項
    monthly_items_tomorrow = []
    for item in monthly_todos:
        target_day = item.get('day', 1)
        if target_day == tomorrow_day:
            monthly_items_tomorrow.append(item)
    
    if monthly_items_tomorrow:
        message = f"📅 每月提醒預告！\n\n明天 ({tomorrow.strftime('%m/%d')}) 有 {len(monthly_items_tomorrow)} 項每月固定事項：\n\n"
        
        for i, item in enumerate(monthly_items_tomorrow, 1):
            message += f"{i}. 🔄 {item['content']}\n"
        
        message += f"\n💡 明天早上會自動加入待辦清單並提醒您\n🇹🇼 台灣時間: {get_taiwan_time_hhmm()}"
        
        send_push_message(user_id, message)
        print(f"✅ 已發送每月預告提醒，明天有 {len(monthly_items_tomorrow)} 項事項 - 台灣時間: {get_taiwan_time()}")

def check_monthly_reminders(taiwan_now, user_id):
    """檢查每月提醒 - 改進版本：當天正式提醒"""
    if not monthly_todos or not user_id:
        return
    
    current_day = taiwan_now.day
    
    # 檢查是否有符合今天日期的每月事項
    monthly_items_today = []
    for item in monthly_todos:
        target_day = item.get('day', 1)
        if target_day == current_day:
            monthly_items_today.append(item)
    
    if monthly_items_today:
        # 自動將每月事項加入今日待辦
        added_items = []
        for item in monthly_items_today:
            # 檢查是否已經加入過（避免重複）
            already_exists = any(
                todo['content'] == item['content'] and 
                todo.get('created_at', '').startswith(taiwan_now.strftime('%Y/%m/%d'))
                for todo in todos
            )
            
            if not already_exists:
                todo_item = {
                    'id': len(todos) + 1,
                    'content': item['content'],
                    'created_at': get_taiwan_time(),
                    'completed': False,
                    'has_date': True,
                    'target_date': taiwan_now.strftime('%Y/%m/%d'),
                    'date_string': f"{taiwan_now.month}/{taiwan_now.day}",
                    'from_monthly': True
                }
                todos.append(todo_item)
                added_items.append(item['content'])
        
        if added_items:
            # 發送每月提醒
            message = f"🔄 每月提醒！今天 ({taiwan_now.strftime('%m/%d')}) 的固定事項：\n\n"
            for i, content in enumerate(added_items, 1):
                message += f"{i}. 📅 {content}\n"
            
            message += f"\n✅ 已自動加入今日待辦清單"
            message += f"\n💡 昨天已經預告過，現在正式提醒！"
            message += f"\n🇹🇼 台灣時間: {get_taiwan_time_hhmm()}"
            
            send_push_message(user_id, message)
            print(f"✅ 已發送每月正式提醒，加入 {len(added_items)} 項事項 - 台灣時間: {get_taiwan_time()}")

def check_short_reminders(taiwan_now):
    """檢查短期提醒"""
    for reminder in short_reminders[:]:
        reminder_time_str = reminder['reminder_time']
        try:
            if '+' in reminder_time_str or reminder_time_str.endswith('Z'):
                reminder_time = datetime.fromisoformat(reminder_time_str.replace('Z', '+00:00'))
                reminder_time = reminder_time.astimezone(TAIWAN_TZ)
            else:
                reminder_time = TAIWAN_TZ.localize(datetime.fromisoformat(reminder_time_str))
        except:
            print(f"⚠️ 無法解析提醒時間: {reminder_time_str}")
            short_reminders.remove(reminder)
            continue
        
        if reminder_time <= taiwan_now:
            user_id = reminder.get('user_id') or user_settings.get('user_id')
            if user_id:
                message = f"⏰ 短期提醒時間到！\n\n📋 {reminder['content']}\n🎯 該去執行了！\n🇹🇼 台灣時間: {get_taiwan_time_hhmm()}"
                send_push_message(user_id, message)
                print(f"✅ 已發送短期提醒: {reminder['content']} - 台灣時間: {get_taiwan_time()}")
            short_reminders.remove(reminder)

def check_time_reminders(taiwan_now):
    """檢查時間提醒"""
    for reminder in time_reminders[:]:
        reminder_time_str = reminder['reminder_time']
        try:
            if '+' in reminder_time_str or reminder_time_str.endswith('Z'):
                reminder_time = datetime.fromisoformat(reminder_time_str.replace('Z', '+00:00'))
                reminder_time = reminder_time.astimezone(TAIWAN_TZ)
            else:
                reminder_time = TAIWAN_TZ.localize(datetime.fromisoformat(reminder_time_str))
        except:
            print(f"⚠️ 無法解析提醒時間: {reminder_time_str}")
            time_reminders.remove(reminder)
            continue
            
        if reminder_time <= taiwan_now:
            user_id = reminder.get('user_id') or user_settings.get('user_id')
            if user_id:
                message = f"🕐 時間提醒！\n\n📋 {reminder['content']}\n⏰ {reminder['time_string']}\n🎯 該去執行了！\n🇹🇼 台灣時間: {get_taiwan_time_hhmm()}"
                send_push_message(user_id, message)
                print(f"✅ 已發送時間提醒: {reminder['content']} - 台灣時間: {get_taiwan_time()}")
            time_reminders.remove(reminder)

# 啟動提醒檢查執行緒
reminder_thread = threading.Thread(target=check_reminders, daemon=True)
reminder_thread.start()

# 防休眠機制
def keep_alive():
    """防休眠機制"""
    base_url = os.getenv('BASE_URL', 'https://line-bot-python-v2.onrender.com')
    
    while True:
        try:
            time.sleep(240)  # 4 分鐘
            response = requests.get(f'{base_url}/health', timeout=15)
            
            if response.status_code == 200:
                print(f"✅ Keep-alive 成功 - 台灣時間: {get_taiwan_time()}")
            else:
                print(f"⚠️ Keep-alive 警告: {response.status_code} - 台灣時間: {get_taiwan_time()}")
                
        except requests.exceptions.RequestException as e:
            print(f"❌ Keep-alive 錯誤: {e} - 台灣時間: {get_taiwan_time()}")
            time.sleep(60)
        except Exception as e:
            print(f"❌ Keep-alive 意外錯誤: {e} - 台灣時間: {get_taiwan_time()}")
            time.sleep(60)

keep_alive_thread = threading.Thread(target=keep_alive, daemon=True)
keep_alive_thread.start()

# ===== Flask 路由 =====
@app.route('/')
def home():
    return f'LINE Todo Reminder Bot v3.0 - 股票記帳功能已加入！當前台灣時間: {get_taiwan_time()}'

@app.route('/health')
def health():
    """健康檢查端點"""
    taiwan_now = get_taiwan_datetime()
    
    try:
        next_morning = taiwan_now.replace(
            hour=int(user_settings['morning_time'].split(':')[0]),
            minute=int(user_settings['morning_time'].split(':')[1]),
            second=0, microsecond=0
        )
        if next_morning <= taiwan_now:
            next_morning += timedelta(days=1)
        
        next_evening = taiwan_now.replace(
            hour=int(user_settings['evening_time'].split(':')[0]),
            minute=int(user_settings['evening_time'].split(':')[1]),
            second=0, microsecond=0
        )
        if next_evening <= taiwan_now:
            next_evening += timedelta(days=1)
        
        next_reminder = min(next_morning, next_evening)
        next_reminder_str = next_reminder.strftime('%Y/%m/%d %H:%M')
    except:
        next_reminder_str = "計算錯誤"
    
    return {
        'status': 'healthy',
        'taiwan_time': get_taiwan_time(),
        'taiwan_time_hhmm': get_taiwan_time_hhmm(),
        'server_timezone': str(taiwan_now.tzinfo),
        'todos_count': len(todos),
        'monthly_todos_count': len(monthly_todos),
        'short_reminders': len(short_reminders),
        'time_reminders': len(time_reminders),
        'stock_accounts_count': len(stock_data['accounts']),
        'stock_transactions_count': len(stock_data['transactions']),
        'morning_time': user_settings['morning_time'],
        'evening_time': user_settings['evening_time'],
        'next_reminder': next_reminder_str,
        'has_user': user_settings['user_id'] is not None,
        'version': '3.0_stock_trading'
    }

@app.route('/webhook', methods=['POST'])
def webhook():
    """LINE Webhook 處理"""
    try:
        data = request.get_json()
        
        for event in data.get('events', []):
            if event['type'] == 'message' and event['message']['type'] == 'text':
                reply_token = event['replyToken']
                message_text = event['message']['text'].strip()
                user_id = event['source']['userId']
                
                # 儲存用戶ID
                user_settings['user_id'] = user_id
                
                print(f"用戶訊息: {message_text} - 台灣時間: {get_taiwan_time()}")
                
                # === 股票功能路由 ===
                if any(keyword in message_text for keyword in ['買入', '賣出', '入帳', '提款', '新增帳戶']) or \
                   re.match(r'.+?(買|賣)\s+\d+', message_text):
                    reply_text = handle_stock_command(message_text, user_id)
                
                # 股票查詢功能（簡化版本）
                elif message_text == '總覽':
                    reply_text = get_all_accounts_summary()
                
                elif message_text.endswith('查詢'):
                    account_name = message_text[:-2].strip()  # 去掉「查詢」
                    if account_name in ['股票', '帳戶']:
                        reply_text = get_all_accounts_summary()
                    else:
                        reply_text = get_account_summary(account_name)
                
                elif message_text == '交易記錄':
                    reply_text = get_transaction_history()
                
                elif message_text.startswith('交易記錄 '):
                    account_name = message_text[5:].strip()
                    reply_text = get_transaction_history(account_name)
                
                elif message_text.startswith('成本查詢 ') and ' ' in message_text[5:]:
                    parts = message_text[5:].strip().split(' ', 1)
                    if len(parts) == 2:
                        account_name, stock_code = parts
                        reply_text = get_stock_cost_analysis(account_name, stock_code)
                    else:
                        reply_text = "❌ 格式不正確\n💡 例如：成本查詢 爸爸 2330"
                
                elif message_text == '帳戶列表':
                    if stock_data['accounts']:
                        account_list = list(stock_data['accounts'].keys())
                        reply_text = f"👥 目前帳戶列表：\n\n" + "\n".join([f"👤 {name}" for name in account_list])
                    else:
                        reply_text = "📝 目前沒有任何帳戶"
                
                elif message_text == '股票幫助':
                    reply_text = """💰 多帳戶股票記帳功能：

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

💡 v3.0：交易指令更簡潔，其他功能保持原樣！"""

                # === 待辦事項功能路由 (保持原有邏輯) ===
                # 查詢時間
                elif message_text == '查詢時間':
                    reply_text = f"🇹🇼 台灣當前時間：{get_taiwan_time()}\n⏰ 目前提醒時間設定：\n🌅 早上：{user_settings['morning_time']}\n🌙 晚上：{user_settings['evening_time']}\n\n✅ 時區已修正為台灣時間！"

                # 設定提醒時間
                elif message_text.startswith('早上時間 '):
                    time_str = message_text[5:].strip()
                    if is_valid_time_format(time_str):
                        user_settings['morning_time'] = time_str
                        reply_text = f"🌅 已設定早上提醒時間為：{time_str}\n🇹🇼 台灣時間"
                    else:
                        reply_text = "❌ 時間格式不正確，請使用 HH:MM 格式，例如：08:30"

                elif message_text.startswith('晚上時間 '):
                    time_str = message_text[5:].strip()
                    if is_valid_time_format(time_str):
                        user_settings['evening_time'] = time_str
                        reply_text = f"🌙 已設定晚上提醒時間為：{time_str}\n🇹🇼 台灣時間"
                    else:
                        reply_text = "❌ 時間格式不正確，請使用 HH:MM 格式，例如：19:00"

                # 短期提醒
                elif any(keyword in message_text for keyword in ['分鐘後', '小時後', '秒後']):
                    parsed = parse_short_reminder(message_text)
                    if parsed['is_valid']:
                        taiwan_now = get_taiwan_datetime()
                        reminder_time = taiwan_now + timedelta(minutes=parsed['minutes'])
                        reminder_item = {
                            'id': len(short_reminders) + 1,
                            'user_id': user_id,
                            'content': parsed['content'],
                            'reminder_time': reminder_time.isoformat(),
                            'original_value': parsed['original_value'],
                            'unit': parsed['unit']
                        }
                        short_reminders.append(reminder_item)
                        
                        reply_text = f"⏰ 已設定短期提醒：「{parsed['content']}」\n⏳ {parsed['original_value']}{parsed['unit']}後提醒\n📅 提醒時間：{reminder_time.strftime('%H:%M')}\n🇹🇼 台灣時間"
                    else:
                        reply_text = f"❌ {parsed['error']}"

                # 時間提醒
                elif re.match(r'^\d{1,2}:\d{2}.+', message_text):
                    parsed = parse_time_reminder(message_text)
                    if parsed['is_valid']:
                        taiwan_now = get_taiwan_datetime()
                        target_time = taiwan_now.replace(
                            hour=parsed['hours'], 
                            minute=parsed['minutes'], 
                            second=0, 
                            microsecond=0
                        )
                        
                        if target_time <= taiwan_now:
                            target_time += timedelta(days=1)
                        
                        reminder_item = {
                            'id': len(time_reminders) + 1,
                            'user_id': user_id,
                            'content': parsed['content'],
                            'time_string': parsed['time_string'],
                            'reminder_time': target_time.isoformat()
                        }
                        time_reminders.append(reminder_item)
                        
                        date_text = '今天' if target_time.date() == taiwan_now.date() else '明天'
                        reply_text = f"🕐 已設定時間提醒：「{parsed['content']}」\n⏰ {date_text} {parsed['time_string']} 提醒\n🇹🇼 台灣時間"
                    else:
                        reply_text = f"❌ {parsed['error']}"

                # 幫助訊息
                elif message_text in ['幫助', 'help', '說明']:
                    reply_text = """📋 LINE Todo Bot v3.0 完整功能：

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

💰 股票記帳：
- 爸爸入帳 50000 - 入金
- 爸爸買入 2330 台積電 100股 實付50000元 2024/08/20
- 總覽 - 查看所有帳戶
- 股票幫助 - 股票功能詳細說明

🆕 v3.0 新功能：完整的多帳戶股票記帳系統！"""

                # 待辦事項功能
                elif message_text.startswith('新增 '):
                    todo_text = message_text[3:].strip()
                    if todo_text:
                        parsed = parse_date(todo_text)
                        todo_item = {
                            'id': len(todos) + 1,
                            'content': parsed['content'],
                            'created_at': get_taiwan_time(),
                            'completed': False,
                            'has_date': parsed.get('has_date', False),
                            'target_date': parsed.get('date').strftime('%Y/%m/%d') if parsed.get('date') else None,
                            'date_string': parsed.get('date_string')
                        }
                        todos.append(todo_item)
                        
                        if parsed.get('has_date'):
                            reply_text = f"✅ 已新增待辦事項：「{parsed['content']}」\n📅 目標日期：{parsed['date'].strftime('%Y/%m/%d')}\n📋 目前共有 {len(todos)} 項\n🇹🇼 台灣時間建立"
                        else:
                            reply_text = f"✅ 已新增待辦事項：「{parsed['content']}」\n📋 目前共有 {len(todos)} 項\n🇹🇼 台灣時間建立"
                    else:
                        reply_text = "❌ 請輸入要新增的事項內容"

                elif message_text in ['查詢', '清單']:
                    if todos:
                        reply_text = f"📋 待辦事項清單 ({len(todos)} 項)：\n\n"
                        for i, todo in enumerate(todos, 1):
                            status = "✅" if todo.get('completed') else "⭕"
                            date_info = f" 📅{todo.get('target_date', '')}" if todo.get('has_date') else ""
                            reply_text += f"{i}. {status} {todo['content']}{date_info}\n"
                        reply_text += "\n💡 輸入「幫助」查看更多功能"
                    else:
                        reply_text = "📝 目前沒有待辦事項"

                elif message_text.startswith('刪除 '):
                    try:
                        index = int(message_text[3:].strip()) - 1
                        if 0 <= index < len(todos):
                            deleted_todo = todos.pop(index)
                            reply_text = f"🗑️ 已刪除：「{deleted_todo['content']}」"
                        else:
                            reply_text = f"❌ 編號不正確"
                    except:
                        reply_text = "❌ 請輸入正確編號"

                elif message_text.startswith('完成 '):
                    try:
                        index = int(message_text[3:].strip()) - 1
                        if 0 <= index < len(todos):
                            todos[index]['completed'] = True
                            reply_text = f"🎉 已完成：「{todos[index]['content']}」"
                        else:
                            reply_text = f"❌ 編號不正確"
                    except:
                        reply_text = "❌ 請輸入正確編號"

                # 每月功能
                elif message_text.startswith('每月新增 '):
                    todo_text = message_text[5:].strip()
                    if todo_text:
                        parsed = parse_date(todo_text)
                        print(f"DEBUG: 解析結果: {parsed}")
                        
                        # 完全修正：更智能的日期處理
                        if parsed.get('has_date'):
                            if parsed.get('day_only'):
                                # 只有日期的情況，例如：24號繳水電卡費
                                day = parsed['day_only']
                                date_display = f"{day}號"
                            elif parsed.get('date_string'):
                                # 有月/日的情況，例如：8/24繳水電卡費
                                try:
                                    day = int(parsed['date_string'].split('/')[1])
                                    date_display = f"{day}號"
                                except:
                                    day = 1
                                    date_display = "1號"
                            else:
                                day = 1
                                date_display = "1號"
                        else:
                            # 沒有指定日期，例如：每月新增 買菜
                            day = 1
                            date_display = "1號"
                        
                        monthly_item = {
                            'id': len(monthly_todos) + 1,
                            'content': parsed['content'],
                            'created_at': get_taiwan_time(),
                            'has_date': parsed.get('has_date', False),
                            'date_string': parsed.get('date_string'),
                            'day': day,
                            'date_display': date_display
                        }
                        monthly_todos.append(monthly_item)
                        print(f"DEBUG: 新增的每月事項: {monthly_item}")
                        
                        reply_text = f"🔄 已新增每月事項：「{parsed['content']}」\n📅 每月 {date_display} 提醒\n📋 目前共有 {len(monthly_todos)} 項每月事項\n💡 會在前一天預告 + 當天提醒"
                    else:
                        reply_text = "❌ 請輸入要新增的每月事項內容\n💡 例如：每月新增 24號繳水電卡費"

                elif message_text == '每月清單':
                    if monthly_todos:
                        # 清理舊資料：為沒有 date_display 的項目補充
                        for item in monthly_todos:
                            if not item.get('date_display'):
                                if item.get('has_date') and item.get('date_string'):
                                    try:
                                        day = int(item['date_string'].split('/')[1])
                                        item['date_display'] = f"{day}號"
                                    except:
                                        item['date_display'] = f"{item.get('day', 1)}號"
                                else:
                                    item['date_display'] = f"{item.get('day', 1)}號"
                        
                        reply_text = f"🔄 每月固定事項清單 ({len(monthly_todos)} 項)：\n\n"
                        for i, item in enumerate(monthly_todos, 1):
                            date_display = item.get('date_display', f"{item.get('day', 1)}號")
                            reply_text += f"{i}. 📅 每月 {date_display} - {item['content']}\n"
                        reply_text += f"\n💡 這些事項會在前一天晚上預告，當天早上自動加入待辦清單"
                    else:
                        reply_text = "📝 目前沒有每月固定事項\n💡 輸入「每月新增 5號繳卡費」來新增"

                # 新增：清理每月資料的指令
                elif message_text == '清理每月':
                    if monthly_todos:
                        # 修正所有每月事項的顯示格式
                        fixed_count = 0
                        for item in monthly_todos:
                            if not item.get('date_display') or 'every month' in str(item.get('date_display', '')):
                                if item.get('has_date') and item.get('date_string'):
                                    try:
                                        day = int(item['date_string'].split('/')[1])
                                        item['date_display'] = f"{day}號"
                                        fixed_count += 1
                                    except:
                                        item['date_display'] = f"{item.get('day', 1)}號"
                                        fixed_count += 1
                                else:
                                    item['date_display'] = f"{item.get('day', 1)}號"
                                    fixed_count += 1
                        
                        reply_text = f"🔧 已修正 {fixed_count} 項每月事項的顯示格式\n💡 現在輸入「每月清單」查看修正結果"
                    else:
                        reply_text = "📝 目前沒有每月固定事項需要清理"

                # 測試功能
                elif message_text == '測試':
                    reply_text = f"✅ 機器人正常運作！\n🇹🇼 當前台灣時間：{get_taiwan_time()}\n⏰ 待辦提醒功能已啟用\n💰 股票記帳功能已啟用\n💡 輸入「幫助」或「股票幫助」查看功能"

                # 預設回應
                else:
                    reply_text = f"您說：{message_text}\n🇹🇼 當前台灣時間：{get_taiwan_time_hhmm()}\n\n💡 輸入「幫助」查看待辦功能\n💰 輸入「股票幫助」查看股票功能"
                
                # 發送回覆
                reply_message(reply_token, reply_text)
        
        return 'OK', 200
    
    except Exception as e:
        print(f"Webhook 處理錯誤: {e} - 台灣時間: {get_taiwan_time()}")
        return 'OK', 200

if __name__ == '__main__':
    print(f"🚀 LINE Bot v3.0 啟動 - 台灣時間: {get_taiwan_time()}")
    print(f"📋 待辦事項功能：已啟用")
    print(f"💰 股票記帳功能：已啟用")
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port), message_text):
        account, amount = match.groups()
        return {
            'type': 'deposit',
            'account': account.strip(),
            'amount': int(amount)
        }
    
    # 提款：出 媽媽 10000  
    elif match := re.match(r'^出\s+(.+?)\s+(\d+)

def handle_stock_deposit(account_name, amount):
    """處理入帳"""
    is_new = get_or_create_account(account_name)
    stock_data['accounts'][account_name]['cash'] += amount
    
    # 記錄交易
    transaction = {
        'id': len(stock_data['transactions']) + 1,
        'type': '入帳',
        'account': account_name,
        'stock_code': None,
        'quantity': 0,
        'amount': amount,
        'price_per_share': 0,
        'date': get_taiwan_time().split(' ')[0],
        'cash_after': stock_data['accounts'][account_name]['cash'],
        'created_at': get_taiwan_time()
    }
    stock_data['transactions'].append(transaction)
    
    result_msg = f"💰 {account_name} 入帳成功！\n"
    if is_new:
        result_msg += f"🆕 已建立新帳戶\n"
    result_msg += f"💵 入帳金額：{amount:,}元\n"
    result_msg += f"💳 帳戶餘額：{stock_data['accounts'][account_name]['cash']:,}元"
    
    return result_msg

def handle_stock_withdraw(account_name, amount):
    """處理提款"""
    if account_name not in stock_data['accounts']:
        return f"❌ 帳戶「{account_name}」不存在"
    
    account = stock_data['accounts'][account_name]
    if account['cash'] < amount:
        return f"❌ 餘額不足！\n💳 目前餘額：{account['cash']:,}元\n💸 提款金額：{amount:,}元"
    
    account['cash'] -= amount
    
    # 記錄交易
    transaction = {
        'id': len(stock_data['transactions']) + 1,
        'type': '提款',
        'account': account_name,
        'stock_code': None,
        'quantity': 0,
        'amount': amount,
        'price_per_share': 0,
        'date': get_taiwan_time().split(' ')[0],
        'cash_after': account['cash'],
        'created_at': get_taiwan_time()
    }
    stock_data['transactions'].append(transaction)
    
    return f"💸 {account_name} 提款成功！\n💵 提款金額：{amount:,}元\n💳 帳戶餘額：{account['cash']:,}元"

def handle_stock_buy(account_name, stock_code, quantity, amount, date):
    """處理買入股票"""
    if account_name not in stock_data['accounts']:
        return f"❌ 帳戶「{account_name}」不存在"
    
    account = stock_data['accounts'][account_name]
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
        'id': len(stock_data['transactions']) + 1,
        'type': '買入',
        'account': account_name,
        'stock_code': stock_code,
        'quantity': quantity,
        'amount': amount,
        'price_per_share': price_per_share,
        'date': date,
        'cash_after': account['cash'],
        'created_at': get_taiwan_time()
    }
    stock_data['transactions'].append(transaction)
    
    stock_info = account['stocks'][stock_code]
    return f"📈 {account_name} 買入成功！\n\n🏷️ {stock_code}\n📊 買入：{quantity}股 @ {price_per_share}元\n💰 實付：{amount:,}元\n📅 日期：{date}\n\n📋 持股狀況：\n📊 總持股：{stock_info['quantity']}股\n💵 平均成本：{stock_info['avg_cost']}元/股\n💳 剩餘現金：{account['cash']:,}元"

def handle_stock_sell(account_name, stock_code, quantity, amount, date):
    """處理賣出股票"""
    if account_name not in stock_data['accounts']:
        return f"❌ 帳戶「{account_name}」不存在"
    
    account = stock_data['accounts'][account_name]
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
        'id': len(stock_data['transactions']) + 1,
        'type': '賣出',
        'account': account_name,
        'stock_code': stock_code,
        'quantity': quantity,
        'amount': amount,
        'price_per_share': price_per_share,
        'date': date,
        'cash_after': account['cash'],
        'created_at': get_taiwan_time(),
        'profit_loss': profit_loss
    }
    stock_data['transactions'].append(transaction)
    
    profit_text = f"💰 獲利：+{profit_loss:,}元" if profit_loss > 0 else f"💸 虧損：{profit_loss:,}元" if profit_loss < 0 else "💫 損益兩平"
    
    result = f"📉 {account_name} 賣出成功！\n\n🏷️ {stock_code}\n📊 賣出：{quantity}股 @ {price_per_share}元\n💰 實收：{amount:,}元\n📅 日期：{date}\n\n💹 本次交易：\n💵 成本：{sell_cost:,}元\n{profit_text}\n💳 現金餘額：{account['cash']:,}元"
    
    if remaining_quantity > 0:
        result += f"\n\n📋 剩餘持股：{remaining_quantity}股"
    else:
        result += f"\n\n✅ 已全部賣出 {stock_code}"
    
    return result

def get_account_summary(account_name):
    """獲取帳戶摘要"""
    if account_name not in stock_data['accounts']:
        return f"❌ 帳戶「{account_name}」不存在"
    
    account = stock_data['accounts'][account_name]
    
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

def get_all_accounts_summary():
    """獲取所有帳戶總覽"""
    if not stock_data['accounts']:
        return "📝 目前沒有任何帳戶\n💡 輸入「爸爸入帳 100000」來建立第一個帳戶"
    
    result = "🏦 家庭投資總覽：\n\n"
    
    total_cash = 0
    total_investment = 0
    all_stocks = {}
    
    for account_name, account in stock_data['accounts'].items():
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

def get_transaction_history(account_name=None, limit=10):
    """獲取交易記錄"""
    transactions = stock_data['transactions']
    
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

def get_stock_cost_analysis(account_name, stock_code):
    """獲取特定股票的成本分析"""
    if account_name not in stock_data['accounts']:
        return f"❌ 帳戶「{account_name}」不存在"
    
    account = stock_data['accounts'][account_name]
    if stock_code not in account['stocks']:
        return f"❌ {account_name} 沒有持有「{stock_code}」"
    
    holding = account['stocks'][stock_code]
    
    # 查找相關交易記錄
    related_transactions = [
        t for t in stock_data['transactions'] 
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

def handle_stock_command(message_text, user_id):
    """處理股票相關指令"""
    parsed = parse_stock_command(message_text)
    
    if not parsed:
        return "❌ 指令格式不正確\n💡 輸入「股票幫助」查看使用說明"
    
    try:
        if parsed['type'] == 'deposit':
            return handle_stock_deposit(parsed['account'], parsed['amount'])
        
        elif parsed['type'] == 'withdraw':
            return handle_stock_withdraw(parsed['account'], parsed['amount'])
        
        elif parsed['type'] == 'buy':
            return handle_stock_buy(
                parsed['account'], parsed['stock_code'], 
                parsed['quantity'], parsed['amount'], parsed['date']
            )
        
        elif parsed['type'] == 'sell':
            return handle_stock_sell(
                parsed['account'], parsed['stock_code'], 
                parsed['quantity'], parsed['amount'], parsed['date']
            )
        
        elif parsed['type'] == 'create_account':
            is_new = get_or_create_account(parsed['account'])
            if is_new:
                return f"🆕 已建立帳戶「{parsed['account']}」\n💡 可以開始入帳和交易了！"
            else:
                return f"ℹ️ 帳戶「{parsed['account']}」已存在"
        
    except Exception as e:
        return f"❌ 處理失敗：{str(e)}\n💡 請檢查指令格式"
    
    return "❌ 未知的指令類型"

# ===== 待辦事項功能函數 (保持原有) =====
def parse_date(text):
    """解析日期格式 - 改進版本，更好地處理每月事項"""
    taiwan_now = get_taiwan_datetime()
    current_year = taiwan_now.year
    
    # 改進的日期模式，更靈活地匹配
    patterns = [
        # 格式：24號繳水電卡費
        (r'(\d{1,2})號(.+)', 'day_only'),
        # 格式：8/24繳水電卡費 或 8/24號繳水電卡費
        (r'(\d{1,2})\/(\d{1,2})號?(.+)', 'month_day'),
        # 格式：繳水電卡費24號
        (r'(.+?)(\d{1,2})號', 'content_day'),
        # 格式：繳水電卡費8/24
        (r'(.+?)(\d{1,2})\/(\d{1,2})號?', 'content_month_day')
    ]
    
    for pattern, pattern_type in patterns:
        match = re.search(pattern, text)
        if match:
            print(f"DEBUG: 匹配到模式 {pattern_type}: {match.groups()}")
            
            if pattern_type == 'day_only':
                # 24號繳水電卡費
                day = int(match.group(1))
                content = match.group(2).strip()
                if 1 <= day <= 31 and content:
                    # 使用當前月份
                    month = taiwan_now.month
                    target_date = taiwan_now.replace(year=current_year, month=month, day=day,
                                                   hour=0, minute=0, second=0, microsecond=0)
                    if target_date < taiwan_now:
                        if month == 12:
                            target_date = target_date.replace(year=current_year + 1, month=1)
                        else:
                            target_date = target_date.replace(month=month + 1)
                    
                    return {
                        "has_date": True,
                        "date": target_date,
                        "content": content,
                        "date_string": f"{month}/{day}",
                        "day_only": day  # 新增：只有日期的情況
                    }
                    
            elif pattern_type == 'month_day':
                # 8/24繳水電卡費
                month = int(match.group(1))
                day = int(match.group(2))
                content = match.group(3).strip()
                
                if 1 <= month <= 12 and 1 <= day <= 31 and content:
                    target_date = taiwan_now.replace(year=current_year, month=month, day=day,
                                                   hour=0, minute=0, second=0, microsecond=0)
                    if target_date < taiwan_now:
                        target_date = target_date.replace(year=current_year + 1)
                    
                    return {
                        "has_date": True,
                        "date": target_date,
                        "content": content,
                        "date_string": f"{month}/{day}"
                    }
                    
            elif pattern_type == 'content_day':
                # 繳水電卡費24號
                content = match.group(1).strip()
                day = int(match.group(2))
                
                if 1 <= day <= 31 and content:
                    month = taiwan_now.month
                    target_date = taiwan_now.replace(year=current_year, month=month, day=day,
                                                   hour=0, minute=0, second=0, microsecond=0)
                    if target_date < taiwan_now:
                        if month == 12:
                            target_date = target_date.replace(year=current_year + 1, month=1)
                        else:
                            target_date = target_date.replace(month=month + 1)
                    
                    return {
                        "has_date": True,
                        "date": target_date,
                        "content": content,
                        "date_string": f"{month}/{day}",
                        "day_only": day
                    }
                    
            elif pattern_type == 'content_month_day':
                # 繳水電卡費8/24
                content = match.group(1).strip()
                month = int(match.group(2))
                day = int(match.group(3))
                
                if 1 <= month <= 12 and 1 <= day <= 31 and content:
                    target_date = taiwan_now.replace(year=current_year, month=month, day=day,
                                                   hour=0, minute=0, second=0, microsecond=0)
                    if target_date < taiwan_now:
                        target_date = target_date.replace(year=current_year + 1)
                    
                    return {
                        "has_date": True,
                        "date": target_date,
                        "content": content,
                        "date_string": f"{month}/{day}"
                    }
    
    print(f"DEBUG: 沒有匹配到任何日期模式，原文: {text}")
    return {"has_date": False, "content": text}

def parse_short_reminder(text):
    """解析短期提醒"""
    patterns = [
        (r'(\d+)分鐘後(.+)', '分鐘', 1),
        (r'(\d+)小時後(.+)', '小時', 60),
        (r'(\d+)秒後(.+)', '秒', 1/60)
    ]
    
    for pattern, unit, multiplier in patterns:
        match = re.search(pattern, text)
        if match:
            value = int(match.group(1))
            content = match.group(2).strip()
            
            if not content:
                return {"is_valid": False, "error": "請輸入提醒內容"}
            
            minutes = value * multiplier
            
            if unit == '分鐘' and not (1 <= value <= 1440):
                return {"is_valid": False, "error": "分鐘數請設定在 1-1440 之間"}
            elif unit == '小時' and not (1 <= value <= 24):
                return {"is_valid": False, "error": "小時數請設定在 1-24 之間"}
            elif unit == '秒' and not (10 <= value <= 3600):
                return {"is_valid": False, "error": "秒數請設定在 10-3600 之間"}
            
            return {
                "is_valid": True,
                "minutes": minutes,
                "original_value": value,
                "unit": unit,
                "content": content
            }
    
    return {"is_valid": False, "error": "格式不正確，請使用：數字+時間單位+後+內容\n例如：5分鐘後倒垃圾"}

def parse_time_reminder(text):
    """解析時間提醒"""
    time_pattern = r'(\d{1,2}):(\d{2})(.+)'
    match = re.search(time_pattern, text)
    
    if match:
        hours = int(match.group(1))
        minutes = int(match.group(2))
        content = match.group(3).strip()
        
        if not content:
            return {"is_valid": False, "error": "請輸入提醒內容"}
        
        if not (0 <= hours <= 23):
            return {"is_valid": False, "error": "小時請設定在 0-23 之間"}
        
        if not (0 <= minutes <= 59):
            return {"is_valid": False, "error": "分鐘請設定在 0-59 之間"}
        
        return {
            "is_valid": True,
            "hours": hours,
            "minutes": minutes,
            "time_string": f"{hours:02d}:{minutes:02d}",
            "content": content
        }
    
    return {"is_valid": False, "error": "格式不正確，請使用：HH:MM+內容\n例如：12:00倒垃圾"}

# ===== LINE API 函數 =====
def send_push_message(user_id, message_text):
    """發送推播訊息"""
    if not CHANNEL_ACCESS_TOKEN or not user_id:
        print(f"模擬推播給 {user_id}: {message_text} (台灣時間: {get_taiwan_time()})")
        return False
    
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {CHANNEL_ACCESS_TOKEN}'
    }
    
    data = {
        'to': user_id,
        'messages': [{
            'type': 'text',
            'text': message_text
        }]
    }
    
    try:
        response = requests.post(PUSH_API_URL, headers=headers, data=json.dumps(data))
        print(f"推播發送 - 狀態碼: {response.status_code} - 台灣時間: {get_taiwan_time()}")
        return response.status_code == 200
    except Exception as e:
        print(f"推播失敗: {e} - 台灣時間: {get_taiwan_time()}")
        return False

def reply_message(reply_token, message_text):
    """回覆訊息"""
    if not CHANNEL_ACCESS_TOKEN:
        print(f"模擬回覆: {message_text} (台灣時間: {get_taiwan_time()})")
        return False
    
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {CHANNEL_ACCESS_TOKEN}'
    }
    
    data = {
        'replyToken': reply_token,
        'messages': [{
            'type': 'text',
            'text': message_text
        }]
    }
    
    try:
        response = requests.post(LINE_API_URL, headers=headers, data=json.dumps(data))
        return response.status_code == 200
    except Exception as e:
        print(f"回覆失敗: {e} - 台灣時間: {get_taiwan_time()}")
        return False

# ===== 提醒系統函數 =====
def check_reminders():
    """檢查並發送提醒 - 改進版本"""
    while True:
        try:
            current_time = get_taiwan_time_hhmm()
            user_id = user_settings.get('user_id')
            taiwan_now = get_taiwan_datetime()
            
            print(f"🔍 提醒檢查 - 台灣時間: {get_taiwan_time()}")
            
            # 檢查定時提醒（每日早晚） - 改進：每次都提醒所有待辦事項
            if user_id and (current_time == user_settings['morning_time'] or current_time == user_settings['evening_time']):
                send_daily_reminder(user_id, current_time)
            
            # 檢查每月提醒 - 改進：前一天預告 + 當天提醒
            if current_time == user_settings['evening_time']:  # 晚上檢查明天的每月事項
                check_monthly_preview(taiwan_now, user_id)
            
            if current_time == "09:00":  # 早上檢查今天的每月事項
                check_monthly_reminders(taiwan_now, user_id)
            
            # 檢查短期提醒
            check_short_reminders(taiwan_now)
            
            # 檢查時間提醒
            check_time_reminders(taiwan_now)
            
            time.sleep(60)  # 每分鐘檢查一次
        except Exception as e:
            print(f"提醒檢查錯誤: {e} - 台灣時間: {get_taiwan_time()}")
            time.sleep(60)

def send_daily_reminder(user_id, current_time):
    """發送每日提醒 - 改進版本：每次都提醒所有待辦事項"""
    time_icon = '🌅' if current_time == user_settings['morning_time'] else '🌙'
    time_text = '早安' if current_time == user_settings['morning_time'] else '晚安'
    
    if todos:
        # 分類待辦事項
        pending_todos = [todo for todo in todos if not todo.get('completed', False)]
        completed_todos = [todo for todo in todos if todo.get('completed', False)]
        
        if pending_todos:
            message = f'{time_icon} {time_text}！您有 {len(pending_todos)} 項待辦事項：\n\n'
            
            # 顯示未完成的事項（最多5項）
            for i, todo in enumerate(pending_todos[:5], 1):
                date_info = f" 📅{todo.get('target_date', '')}" if todo.get('has_date') else ""
                message += f'{i}. ⭕ {todo["content"]}{date_info}\n'
            
            if len(pending_todos) > 5:
                message += f'\n...還有 {len(pending_todos) - 5} 項未完成\n'
            
            # 如果有已完成的事項，也顯示（最多2項）
            if completed_todos:
                message += f'\n✅ 已完成 {len(completed_todos)} 項：\n'
                for todo in completed_todos[:2]:
                    message += f'✅ {todo["content"]}\n'
                if len(completed_todos) > 2:
                    message += f'...還有 {len(completed_todos) - 2} 項已完成\n'
            
            if current_time == user_settings['morning_time']:
                message += f'\n💪 新的一天開始了！加油完成這些任務！'
            else:
                message += f'\n🌙 檢查一下今天的進度吧！記得為明天做準備！'
                
            message += f'\n🇹🇼 台灣時間: {get_taiwan_time_hhmm()}'
            
            send_push_message(user_id, message)
            print(f"✅ 已發送每日提醒 ({len(pending_todos)} 項待辦) - 台灣時間: {get_taiwan_time()}")
        else:
            # 所有事項都已完成
            if current_time == user_settings['morning_time']:
                message = f'{time_icon} {time_text}！🎉 太棒了！目前沒有待辦事項\n💡 可以新增今天要做的事情'
            else:
                message = f'{time_icon} {time_text}！🎉 太棒了！今天的任務都完成了\n😴 好好休息，為明天準備新的目標！'
            
            message += f'\n🇹🇼 台灣時間: {get_taiwan_time_hhmm()}'
            send_push_message(user_id, message)
            print(f"✅ 已發送每日提醒 (無待辦事項) - 台灣時間: {get_taiwan_time()}")
    else:
        # 完全沒有任何事項
        if current_time == user_settings['morning_time']:
            message = f'{time_icon} {time_text}！✨ 新的一天開始了！\n💡 輸入「新增 事項名稱」來建立今天的目標'
        else:
            message = f'{time_icon} {time_text}！😌 今天過得如何？\n💡 別忘了為明天規劃一些目標'
        
        message += f'\n🇹🇼 台灣時間: {get_taiwan_time_hhmm()}'
        send_push_message(user_id, message)
        print(f"✅ 已發送每日提醒 (首次使用) - 台灣時間: {get_taiwan_time()}")

def check_monthly_preview(taiwan_now, user_id):
    """檢查明天的每月提醒 - 新增功能：前一天預告"""
    if not monthly_todos or not user_id:
        return
    
    tomorrow = taiwan_now + timedelta(days=1)
    tomorrow_day = tomorrow.day
    
    # 檢查明天是否有每月事項
    monthly_items_tomorrow = []
    for item in monthly_todos:
        target_day = item.get('day', 1)
        if target_day == tomorrow_day:
            monthly_items_tomorrow.append(item)
    
    if monthly_items_tomorrow:
        message = f"📅 每月提醒預告！\n\n明天 ({tomorrow.strftime('%m/%d')}) 有 {len(monthly_items_tomorrow)} 項每月固定事項：\n\n"
        
        for i, item in enumerate(monthly_items_tomorrow, 1):
            message += f"{i}. 🔄 {item['content']}\n"
        
        message += f"\n💡 明天早上會自動加入待辦清單並提醒您\n🇹🇼 台灣時間: {get_taiwan_time_hhmm()}"
        
        send_push_message(user_id, message)
        print(f"✅ 已發送每月預告提醒，明天有 {len(monthly_items_tomorrow)} 項事項 - 台灣時間: {get_taiwan_time()}")

def check_monthly_reminders(taiwan_now, user_id):
    """檢查每月提醒 - 改進版本：當天正式提醒"""
    if not monthly_todos or not user_id:
        return
    
    current_day = taiwan_now.day
    
    # 檢查是否有符合今天日期的每月事項
    monthly_items_today = []
    for item in monthly_todos:
        target_day = item.get('day', 1)
        if target_day == current_day:
            monthly_items_today.append(item)
    
    if monthly_items_today:
        # 自動將每月事項加入今日待辦
        added_items = []
        for item in monthly_items_today:
            # 檢查是否已經加入過（避免重複）
            already_exists = any(
                todo['content'] == item['content'] and 
                todo.get('created_at', '').startswith(taiwan_now.strftime('%Y/%m/%d'))
                for todo in todos
            )
            
            if not already_exists:
                todo_item = {
                    'id': len(todos) + 1,
                    'content': item['content'],
                    'created_at': get_taiwan_time(),
                    'completed': False,
                    'has_date': True,
                    'target_date': taiwan_now.strftime('%Y/%m/%d'),
                    'date_string': f"{taiwan_now.month}/{taiwan_now.day}",
                    'from_monthly': True
                }
                todos.append(todo_item)
                added_items.append(item['content'])
        
        if added_items:
            # 發送每月提醒
            message = f"🔄 每月提醒！今天 ({taiwan_now.strftime('%m/%d')}) 的固定事項：\n\n"
            for i, content in enumerate(added_items, 1):
                message += f"{i}. 📅 {content}\n"
            
            message += f"\n✅ 已自動加入今日待辦清單"
            message += f"\n💡 昨天已經預告過，現在正式提醒！"
            message += f"\n🇹🇼 台灣時間: {get_taiwan_time_hhmm()}"
            
            send_push_message(user_id, message)
            print(f"✅ 已發送每月正式提醒，加入 {len(added_items)} 項事項 - 台灣時間: {get_taiwan_time()}")

def check_short_reminders(taiwan_now):
    """檢查短期提醒"""
    for reminder in short_reminders[:]:
        reminder_time_str = reminder['reminder_time']
        try:
            if '+' in reminder_time_str or reminder_time_str.endswith('Z'):
                reminder_time = datetime.fromisoformat(reminder_time_str.replace('Z', '+00:00'))
                reminder_time = reminder_time.astimezone(TAIWAN_TZ)
            else:
                reminder_time = TAIWAN_TZ.localize(datetime.fromisoformat(reminder_time_str))
        except:
            print(f"⚠️ 無法解析提醒時間: {reminder_time_str}")
            short_reminders.remove(reminder)
            continue
        
        if reminder_time <= taiwan_now:
            user_id = reminder.get('user_id') or user_settings.get('user_id')
            if user_id:
                message = f"⏰ 短期提醒時間到！\n\n📋 {reminder['content']}\n🎯 該去執行了！\n🇹🇼 台灣時間: {get_taiwan_time_hhmm()}"
                send_push_message(user_id, message)
                print(f"✅ 已發送短期提醒: {reminder['content']} - 台灣時間: {get_taiwan_time()}")
            short_reminders.remove(reminder)

def check_time_reminders(taiwan_now):
    """檢查時間提醒"""
    for reminder in time_reminders[:]:
        reminder_time_str = reminder['reminder_time']
        try:
            if '+' in reminder_time_str or reminder_time_str.endswith('Z'):
                reminder_time = datetime.fromisoformat(reminder_time_str.replace('Z', '+00:00'))
                reminder_time = reminder_time.astimezone(TAIWAN_TZ)
            else:
                reminder_time = TAIWAN_TZ.localize(datetime.fromisoformat(reminder_time_str))
        except:
            print(f"⚠️ 無法解析提醒時間: {reminder_time_str}")
            time_reminders.remove(reminder)
            continue
            
        if reminder_time <= taiwan_now:
            user_id = reminder.get('user_id') or user_settings.get('user_id')
            if user_id:
                message = f"🕐 時間提醒！\n\n📋 {reminder['content']}\n⏰ {reminder['time_string']}\n🎯 該去執行了！\n🇹🇼 台灣時間: {get_taiwan_time_hhmm()}"
                send_push_message(user_id, message)
                print(f"✅ 已發送時間提醒: {reminder['content']} - 台灣時間: {get_taiwan_time()}")
            time_reminders.remove(reminder)

# 啟動提醒檢查執行緒
reminder_thread = threading.Thread(target=check_reminders, daemon=True)
reminder_thread.start()

# 防休眠機制
def keep_alive():
    """防休眠機制"""
    base_url = os.getenv('BASE_URL', 'https://line-bot-python-v2.onrender.com')
    
    while True:
        try:
            time.sleep(240)  # 4 分鐘
            response = requests.get(f'{base_url}/health', timeout=15)
            
            if response.status_code == 200:
                print(f"✅ Keep-alive 成功 - 台灣時間: {get_taiwan_time()}")
            else:
                print(f"⚠️ Keep-alive 警告: {response.status_code} - 台灣時間: {get_taiwan_time()}")
                
        except requests.exceptions.RequestException as e:
            print(f"❌ Keep-alive 錯誤: {e} - 台灣時間: {get_taiwan_time()}")
            time.sleep(60)
        except Exception as e:
            print(f"❌ Keep-alive 意外錯誤: {e} - 台灣時間: {get_taiwan_time()}")
            time.sleep(60)

keep_alive_thread = threading.Thread(target=keep_alive, daemon=True)
keep_alive_thread.start()

# ===== Flask 路由 =====
@app.route('/')
def home():
    return f'LINE Todo Reminder Bot v3.0 - 股票記帳功能已加入！當前台灣時間: {get_taiwan_time()}'

@app.route('/health')
def health():
    """健康檢查端點"""
    taiwan_now = get_taiwan_datetime()
    
    try:
        next_morning = taiwan_now.replace(
            hour=int(user_settings['morning_time'].split(':')[0]),
            minute=int(user_settings['morning_time'].split(':')[1]),
            second=0, microsecond=0
        )
        if next_morning <= taiwan_now:
            next_morning += timedelta(days=1)
        
        next_evening = taiwan_now.replace(
            hour=int(user_settings['evening_time'].split(':')[0]),
            minute=int(user_settings['evening_time'].split(':')[1]),
            second=0, microsecond=0
        )
        if next_evening <= taiwan_now:
            next_evening += timedelta(days=1)
        
        next_reminder = min(next_morning, next_evening)
        next_reminder_str = next_reminder.strftime('%Y/%m/%d %H:%M')
    except:
        next_reminder_str = "計算錯誤"
    
    return {
        'status': 'healthy',
        'taiwan_time': get_taiwan_time(),
        'taiwan_time_hhmm': get_taiwan_time_hhmm(),
        'server_timezone': str(taiwan_now.tzinfo),
        'todos_count': len(todos),
        'monthly_todos_count': len(monthly_todos),
        'short_reminders': len(short_reminders),
        'time_reminders': len(time_reminders),
        'stock_accounts_count': len(stock_data['accounts']),
        'stock_transactions_count': len(stock_data['transactions']),
        'morning_time': user_settings['morning_time'],
        'evening_time': user_settings['evening_time'],
        'next_reminder': next_reminder_str,
        'has_user': user_settings['user_id'] is not None,
        'version': '3.0_stock_trading'
    }

@app.route('/webhook', methods=['POST'])
def webhook():
    """LINE Webhook 處理"""
    try:
        data = request.get_json()
        
        for event in data.get('events', []):
            if event['type'] == 'message' and event['message']['type'] == 'text':
                reply_token = event['replyToken']
                message_text = event['message']['text'].strip()
                user_id = event['source']['userId']
                
                # 儲存用戶ID
                user_settings['user_id'] = user_id
                
                print(f"用戶訊息: {message_text} - 台灣時間: {get_taiwan_time()}")
                
                # === 股票功能路由 ===
                if any(keyword in message_text for keyword in ['買入', '賣出', '入帳', '提款', '新增帳戶']):
                    reply_text = handle_stock_command(message_text, user_id)
                
                # 股票查詢功能
                elif message_text == '總覽':
                    reply_text = get_all_accounts_summary()
                
                elif message_text.endswith('查詢'):
                    account_name = message_text[:-2].strip()  # 去掉「查詢」
                    if account_name in ['股票', '帳戶']:
                        reply_text = get_all_accounts_summary()
                    else:
                        reply_text = get_account_summary(account_name)
                
                elif message_text == '交易記錄':
                    reply_text = get_transaction_history()
                
                elif message_text.startswith('交易記錄 '):
                    account_name = message_text[5:].strip()
                    reply_text = get_transaction_history(account_name)
                
                elif message_text.startswith('成本查詢 ') and ' ' in message_text[5:]:
                    parts = message_text[5:].strip().split(' ', 1)
                    if len(parts) == 2:
                        account_name, stock_code = parts
                        reply_text = get_stock_cost_analysis(account_name, stock_code)
                    else:
                        reply_text = "❌ 格式不正確\n💡 例如：成本查詢 爸爸 2330 台積電"
                
                elif message_text == '帳戶列表':
                    if stock_data['accounts']:
                        account_list = list(stock_data['accounts'].keys())
                        reply_text = f"👥 目前帳戶列表：\n\n" + "\n".join([f"👤 {name}" for name in account_list])
                    else:
                        reply_text = "📝 目前沒有任何帳戶"
                
                elif message_text == '股票幫助':
                    reply_text = """💰 多帳戶股票記帳功能：

📋 帳戶管理：
- 爸爸入帳 50000 - 入金
- 媽媽提款 10000 - 提款  
- 新增帳戶 奶奶 - 建立帳戶

📈 交易操作：
- 爸爸買入 2330 台積電 100股 實付50000元 2024/08/20
- 媽媽賣出 2317 鴻海 50股 實收5000元 2024/08/21

📊 查詢功能：
- 總覽 - 所有帳戶總覽
- 爸爸查詢 - 個人資金和持股
- 交易記錄 - 所有交易歷史
- 交易記錄 爸爸 - 個人交易記錄
- 成本查詢 爸爸 2330 台積電 - 持股成本分析
- 帳戶列表 - 查看所有帳戶

💡 v3.0 新功能：完整的多帳戶股票記帳！"""

                # === 待辦事項功能路由 (保持原有邏輯) ===
                # 查詢時間
                elif message_text == '查詢時間':
                    reply_text = f"🇹🇼 台灣當前時間：{get_taiwan_time()}\n⏰ 目前提醒時間設定：\n🌅 早上：{user_settings['morning_time']}\n🌙 晚上：{user_settings['evening_time']}\n\n✅ 時區已修正為台灣時間！"

                # 設定提醒時間
                elif message_text.startswith('早上時間 '):
                    time_str = message_text[5:].strip()
                    if is_valid_time_format(time_str):
                        user_settings['morning_time'] = time_str
                        reply_text = f"🌅 已設定早上提醒時間為：{time_str}\n🇹🇼 台灣時間"
                    else:
                        reply_text = "❌ 時間格式不正確，請使用 HH:MM 格式，例如：08:30"

                elif message_text.startswith('晚上時間 '):
                    time_str = message_text[5:].strip()
                    if is_valid_time_format(time_str):
                        user_settings['evening_time'] = time_str
                        reply_text = f"🌙 已設定晚上提醒時間為：{time_str}\n🇹🇼 台灣時間"
                    else:
                        reply_text = "❌ 時間格式不正確，請使用 HH:MM 格式，例如：19:00"

                # 短期提醒
                elif any(keyword in message_text for keyword in ['分鐘後', '小時後', '秒後']):
                    parsed = parse_short_reminder(message_text)
                    if parsed['is_valid']:
                        taiwan_now = get_taiwan_datetime()
                        reminder_time = taiwan_now + timedelta(minutes=parsed['minutes'])
                        reminder_item = {
                            'id': len(short_reminders) + 1,
                            'user_id': user_id,
                            'content': parsed['content'],
                            'reminder_time': reminder_time.isoformat(),
                            'original_value': parsed['original_value'],
                            'unit': parsed['unit']
                        }
                        short_reminders.append(reminder_item)
                        
                        reply_text = f"⏰ 已設定短期提醒：「{parsed['content']}」\n⏳ {parsed['original_value']}{parsed['unit']}後提醒\n📅 提醒時間：{reminder_time.strftime('%H:%M')}\n🇹🇼 台灣時間"
                    else:
                        reply_text = f"❌ {parsed['error']}"

                # 時間提醒
                elif re.match(r'^\d{1,2}:\d{2}.+', message_text):
                    parsed = parse_time_reminder(message_text)
                    if parsed['is_valid']:
                        taiwan_now = get_taiwan_datetime()
                        target_time = taiwan_now.replace(
                            hour=parsed['hours'], 
                            minute=parsed['minutes'], 
                            second=0, 
                            microsecond=0
                        )
                        
                        if target_time <= taiwan_now:
                            target_time += timedelta(days=1)
                        
                        reminder_item = {
                            'id': len(time_reminders) + 1,
                            'user_id': user_id,
                            'content': parsed['content'],
                            'time_string': parsed['time_string'],
                            'reminder_time': target_time.isoformat()
                        }
                        time_reminders.append(reminder_item)
                        
                        date_text = '今天' if target_time.date() == taiwan_now.date() else '明天'
                        reply_text = f"🕐 已設定時間提醒：「{parsed['content']}」\n⏰ {date_text} {parsed['time_string']} 提醒\n🇹🇼 台灣時間"
                    else:
                        reply_text = f"❌ {parsed['error']}"

                # 幫助訊息
                elif message_text in ['幫助', 'help', '說明']:
                    reply_text = """📋 LINE Todo Bot v3.0 完整功能：

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

💰 股票記帳：
- 爸爸入帳 50000 - 入金
- 爸爸買入 2330 台積電 100股 實付50000元 2024/08/20
- 總覽 - 查看所有帳戶
- 股票幫助 - 股票功能詳細說明

🆕 v3.0 新功能：完整的多帳戶股票記帳系統！"""

                # 待辦事項功能
                elif message_text.startswith('新增 '):
                    todo_text = message_text[3:].strip()
                    if todo_text:
                        parsed = parse_date(todo_text)
                        todo_item = {
                            'id': len(todos) + 1,
                            'content': parsed['content'],
                            'created_at': get_taiwan_time(),
                            'completed': False,
                            'has_date': parsed.get('has_date', False),
                            'target_date': parsed.get('date').strftime('%Y/%m/%d') if parsed.get('date') else None,
                            'date_string': parsed.get('date_string')
                        }
                        todos.append(todo_item)
                        
                        if parsed.get('has_date'):
                            reply_text = f"✅ 已新增待辦事項：「{parsed['content']}」\n📅 目標日期：{parsed['date'].strftime('%Y/%m/%d')}\n📋 目前共有 {len(todos)} 項\n🇹🇼 台灣時間建立"
                        else:
                            reply_text = f"✅ 已新增待辦事項：「{parsed['content']}」\n📋 目前共有 {len(todos)} 項\n🇹🇼 台灣時間建立"
                    else:
                        reply_text = "❌ 請輸入要新增的事項內容"

                elif message_text in ['查詢', '清單']:
                    if todos:
                        reply_text = f"📋 待辦事項清單 ({len(todos)} 項)：\n\n"
                        for i, todo in enumerate(todos, 1):
                            status = "✅" if todo.get('completed') else "⭕"
                            date_info = f" 📅{todo.get('target_date', '')}" if todo.get('has_date') else ""
                            reply_text += f"{i}. {status} {todo['content']}{date_info}\n"
                        reply_text += "\n💡 輸入「幫助」查看更多功能"
                    else:
                        reply_text = "📝 目前沒有待辦事項"

                elif message_text.startswith('刪除 '):
                    try:
                        index = int(message_text[3:].strip()) - 1
                        if 0 <= index < len(todos):
                            deleted_todo = todos.pop(index)
                            reply_text = f"🗑️ 已刪除：「{deleted_todo['content']}」"
                        else:
                            reply_text = f"❌ 編號不正確"
                    except:
                        reply_text = "❌ 請輸入正確編號"

                elif message_text.startswith('完成 '):
                    try:
                        index = int(message_text[3:].strip()) - 1
                        if 0 <= index < len(todos):
                            todos[index]['completed'] = True
                            reply_text = f"🎉 已完成：「{todos[index]['content']}」"
                        else:
                            reply_text = f"❌ 編號不正確"
                    except:
                        reply_text = "❌ 請輸入正確編號"

                # 每月功能
                elif message_text.startswith('每月新增 '):
                    todo_text = message_text[5:].strip()
                    if todo_text:
                        parsed = parse_date(todo_text)
                        print(f"DEBUG: 解析結果: {parsed}")
                        
                        # 完全修正：更智能的日期處理
                        if parsed.get('has_date'):
                            if parsed.get('day_only'):
                                # 只有日期的情況，例如：24號繳水電卡費
                                day = parsed['day_only']
                                date_display = f"{day}號"
                            elif parsed.get('date_string'):
                                # 有月/日的情況，例如：8/24繳水電卡費
                                try:
                                    day = int(parsed['date_string'].split('/')[1])
                                    date_display = f"{day}號"
                                except:
                                    day = 1
                                    date_display = "1號"
                            else:
                                day = 1
                                date_display = "1號"
                        else:
                            # 沒有指定日期，例如：每月新增 買菜
                            day = 1
                            date_display = "1號"
                        
                        monthly_item = {
                            'id': len(monthly_todos) + 1,
                            'content': parsed['content'],
                            'created_at': get_taiwan_time(),
                            'has_date': parsed.get('has_date', False),
                            'date_string': parsed.get('date_string'),
                            'day': day,
                            'date_display': date_display
                        }
                        monthly_todos.append(monthly_item)
                        print(f"DEBUG: 新增的每月事項: {monthly_item}")
                        
                        reply_text = f"🔄 已新增每月事項：「{parsed['content']}」\n📅 每月 {date_display} 提醒\n📋 目前共有 {len(monthly_todos)} 項每月事項\n💡 會在前一天預告 + 當天提醒"
                    else:
                        reply_text = "❌ 請輸入要新增的每月事項內容\n💡 例如：每月新增 24號繳水電卡費"

                elif message_text == '每月清單':
                    if monthly_todos:
                        # 清理舊資料：為沒有 date_display 的項目補充
                        for item in monthly_todos:
                            if not item.get('date_display'):
                                if item.get('has_date') and item.get('date_string'):
                                    try:
                                        day = int(item['date_string'].split('/')[1])
                                        item['date_display'] = f"{day}號"
                                    except:
                                        item['date_display'] = f"{item.get('day', 1)}號"
                                else:
                                    item['date_display'] = f"{item.get('day', 1)}號"
                        
                        reply_text = f"🔄 每月固定事項清單 ({len(monthly_todos)} 項)：\n\n"
                        for i, item in enumerate(monthly_todos, 1):
                            date_display = item.get('date_display', f"{item.get('day', 1)}號")
                            reply_text += f"{i}. 📅 每月 {date_display} - {item['content']}\n"
                        reply_text += f"\n💡 這些事項會在前一天晚上預告，當天早上自動加入待辦清單"
                    else:
                        reply_text = "📝 目前沒有每月固定事項\n💡 輸入「每月新增 5號繳卡費」來新增"

                # 新增：清理每月資料的指令
                elif message_text == '清理每月':
                    if monthly_todos:
                        # 修正所有每月事項的顯示格式
                        fixed_count = 0
                        for item in monthly_todos:
                            if not item.get('date_display') or 'every month' in str(item.get('date_display', '')):
                                if item.get('has_date') and item.get('date_string'):
                                    try:
                                        day = int(item['date_string'].split('/')[1])
                                        item['date_display'] = f"{day}號"
                                        fixed_count += 1
                                    except:
                                        item['date_display'] = f"{item.get('day', 1)}號"
                                        fixed_count += 1
                                else:
                                    item['date_display'] = f"{item.get('day', 1)}號"
                                    fixed_count += 1
                        
                        reply_text = f"🔧 已修正 {fixed_count} 項每月事項的顯示格式\n💡 現在輸入「每月清單」查看修正結果"
                    else:
                        reply_text = "📝 目前沒有每月固定事項需要清理"

                # 測試功能
                elif message_text == '測試':
                    reply_text = f"✅ 機器人正常運作！\n🇹🇼 當前台灣時間：{get_taiwan_time()}\n⏰ 待辦提醒功能已啟用\n💰 股票記帳功能已啟用\n💡 輸入「幫助」或「股票幫助」查看功能"

                # 預設回應
                else:
                    reply_text = f"您說：{message_text}\n🇹🇼 當前台灣時間：{get_taiwan_time_hhmm()}\n\n💡 輸入「幫助」查看待辦功能\n💰 輸入「股票幫助」查看股票功能"
                
                # 發送回覆
                reply_message(reply_token, reply_text)
        
        return 'OK', 200
    
    except Exception as e:
        print(f"Webhook 處理錯誤: {e} - 台灣時間: {get_taiwan_time()}")
        return 'OK', 200

if __name__ == '__main__':
    print(f"🚀 LINE Bot v3.0 啟動 - 台灣時間: {get_taiwan_time()}")
    print(f"📋 待辦事項功能：已啟用")
    print(f"💰 股票記帳功能：已啟用")
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port), message_text):
        account, amount = match.groups()
        return {
            'type': 'withdraw',
            'account': account.strip(),
            'amount': int(amount)
        }
    
    # 買入（簡化版）：買 爸爸 2330 100 50000 0820
    elif match := re.match(r'^買\s+(.+?)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d{4})

def handle_stock_deposit(account_name, amount):
    """處理入帳"""
    is_new = get_or_create_account(account_name)
    stock_data['accounts'][account_name]['cash'] += amount
    
    # 記錄交易
    transaction = {
        'id': len(stock_data['transactions']) + 1,
        'type': '入帳',
        'account': account_name,
        'stock_code': None,
        'quantity': 0,
        'amount': amount,
        'price_per_share': 0,
        'date': get_taiwan_time().split(' ')[0],
        'cash_after': stock_data['accounts'][account_name]['cash'],
        'created_at': get_taiwan_time()
    }
    stock_data['transactions'].append(transaction)
    
    result_msg = f"💰 {account_name} 入帳成功！\n"
    if is_new:
        result_msg += f"🆕 已建立新帳戶\n"
    result_msg += f"💵 入帳金額：{amount:,}元\n"
    result_msg += f"💳 帳戶餘額：{stock_data['accounts'][account_name]['cash']:,}元"
    
    return result_msg

def handle_stock_withdraw(account_name, amount):
    """處理提款"""
    if account_name not in stock_data['accounts']:
        return f"❌ 帳戶「{account_name}」不存在"
    
    account = stock_data['accounts'][account_name]
    if account['cash'] < amount:
        return f"❌ 餘額不足！\n💳 目前餘額：{account['cash']:,}元\n💸 提款金額：{amount:,}元"
    
    account['cash'] -= amount
    
    # 記錄交易
    transaction = {
        'id': len(stock_data['transactions']) + 1,
        'type': '提款',
        'account': account_name,
        'stock_code': None,
        'quantity': 0,
        'amount': amount,
        'price_per_share': 0,
        'date': get_taiwan_time().split(' ')[0],
        'cash_after': account['cash'],
        'created_at': get_taiwan_time()
    }
    stock_data['transactions'].append(transaction)
    
    return f"💸 {account_name} 提款成功！\n💵 提款金額：{amount:,}元\n💳 帳戶餘額：{account['cash']:,}元"

def handle_stock_buy(account_name, stock_code, quantity, amount, date):
    """處理買入股票"""
    if account_name not in stock_data['accounts']:
        return f"❌ 帳戶「{account_name}」不存在"
    
    account = stock_data['accounts'][account_name]
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
        'id': len(stock_data['transactions']) + 1,
        'type': '買入',
        'account': account_name,
        'stock_code': stock_code,
        'quantity': quantity,
        'amount': amount,
        'price_per_share': price_per_share,
        'date': date,
        'cash_after': account['cash'],
        'created_at': get_taiwan_time()
    }
    stock_data['transactions'].append(transaction)
    
    stock_info = account['stocks'][stock_code]
    return f"📈 {account_name} 買入成功！\n\n🏷️ {stock_code}\n📊 買入：{quantity}股 @ {price_per_share}元\n💰 實付：{amount:,}元\n📅 日期：{date}\n\n📋 持股狀況：\n📊 總持股：{stock_info['quantity']}股\n💵 平均成本：{stock_info['avg_cost']}元/股\n💳 剩餘現金：{account['cash']:,}元"

def handle_stock_sell(account_name, stock_code, quantity, amount, date):
    """處理賣出股票"""
    if account_name not in stock_data['accounts']:
        return f"❌ 帳戶「{account_name}」不存在"
    
    account = stock_data['accounts'][account_name]
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
        'id': len(stock_data['transactions']) + 1,
        'type': '賣出',
        'account': account_name,
        'stock_code': stock_code,
        'quantity': quantity,
        'amount': amount,
        'price_per_share': price_per_share,
        'date': date,
        'cash_after': account['cash'],
        'created_at': get_taiwan_time(),
        'profit_loss': profit_loss
    }
    stock_data['transactions'].append(transaction)
    
    profit_text = f"💰 獲利：+{profit_loss:,}元" if profit_loss > 0 else f"💸 虧損：{profit_loss:,}元" if profit_loss < 0 else "💫 損益兩平"
    
    result = f"📉 {account_name} 賣出成功！\n\n🏷️ {stock_code}\n📊 賣出：{quantity}股 @ {price_per_share}元\n💰 實收：{amount:,}元\n📅 日期：{date}\n\n💹 本次交易：\n💵 成本：{sell_cost:,}元\n{profit_text}\n💳 現金餘額：{account['cash']:,}元"
    
    if remaining_quantity > 0:
        result += f"\n\n📋 剩餘持股：{remaining_quantity}股"
    else:
        result += f"\n\n✅ 已全部賣出 {stock_code}"
    
    return result

def get_account_summary(account_name):
    """獲取帳戶摘要"""
    if account_name not in stock_data['accounts']:
        return f"❌ 帳戶「{account_name}」不存在"
    
    account = stock_data['accounts'][account_name]
    
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

def get_all_accounts_summary():
    """獲取所有帳戶總覽"""
    if not stock_data['accounts']:
        return "📝 目前沒有任何帳戶\n💡 輸入「爸爸入帳 100000」來建立第一個帳戶"
    
    result = "🏦 家庭投資總覽：\n\n"
    
    total_cash = 0
    total_investment = 0
    all_stocks = {}
    
    for account_name, account in stock_data['accounts'].items():
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

def get_transaction_history(account_name=None, limit=10):
    """獲取交易記錄"""
    transactions = stock_data['transactions']
    
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

def get_stock_cost_analysis(account_name, stock_code):
    """獲取特定股票的成本分析"""
    if account_name not in stock_data['accounts']:
        return f"❌ 帳戶「{account_name}」不存在"
    
    account = stock_data['accounts'][account_name]
    if stock_code not in account['stocks']:
        return f"❌ {account_name} 沒有持有「{stock_code}」"
    
    holding = account['stocks'][stock_code]
    
    # 查找相關交易記錄
    related_transactions = [
        t for t in stock_data['transactions'] 
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

def handle_stock_command(message_text, user_id):
    """處理股票相關指令"""
    parsed = parse_stock_command(message_text)
    
    if not parsed:
        return "❌ 指令格式不正確\n💡 輸入「股票幫助」查看使用說明"
    
    try:
        if parsed['type'] == 'deposit':
            return handle_stock_deposit(parsed['account'], parsed['amount'])
        
        elif parsed['type'] == 'withdraw':
            return handle_stock_withdraw(parsed['account'], parsed['amount'])
        
        elif parsed['type'] == 'buy':
            return handle_stock_buy(
                parsed['account'], parsed['stock_code'], 
                parsed['quantity'], parsed['amount'], parsed['date']
            )
        
        elif parsed['type'] == 'sell':
            return handle_stock_sell(
                parsed['account'], parsed['stock_code'], 
                parsed['quantity'], parsed['amount'], parsed['date']
            )
        
        elif parsed['type'] == 'create_account':
            is_new = get_or_create_account(parsed['account'])
            if is_new:
                return f"🆕 已建立帳戶「{parsed['account']}」\n💡 可以開始入帳和交易了！"
            else:
                return f"ℹ️ 帳戶「{parsed['account']}」已存在"
        
    except Exception as e:
        return f"❌ 處理失敗：{str(e)}\n💡 請檢查指令格式"
    
    return "❌ 未知的指令類型"

# ===== 待辦事項功能函數 (保持原有) =====
def parse_date(text):
    """解析日期格式 - 改進版本，更好地處理每月事項"""
    taiwan_now = get_taiwan_datetime()
    current_year = taiwan_now.year
    
    # 改進的日期模式，更靈活地匹配
    patterns = [
        # 格式：24號繳水電卡費
        (r'(\d{1,2})號(.+)', 'day_only'),
        # 格式：8/24繳水電卡費 或 8/24號繳水電卡費
        (r'(\d{1,2})\/(\d{1,2})號?(.+)', 'month_day'),
        # 格式：繳水電卡費24號
        (r'(.+?)(\d{1,2})號', 'content_day'),
        # 格式：繳水電卡費8/24
        (r'(.+?)(\d{1,2})\/(\d{1,2})號?', 'content_month_day')
    ]
    
    for pattern, pattern_type in patterns:
        match = re.search(pattern, text)
        if match:
            print(f"DEBUG: 匹配到模式 {pattern_type}: {match.groups()}")
            
            if pattern_type == 'day_only':
                # 24號繳水電卡費
                day = int(match.group(1))
                content = match.group(2).strip()
                if 1 <= day <= 31 and content:
                    # 使用當前月份
                    month = taiwan_now.month
                    target_date = taiwan_now.replace(year=current_year, month=month, day=day,
                                                   hour=0, minute=0, second=0, microsecond=0)
                    if target_date < taiwan_now:
                        if month == 12:
                            target_date = target_date.replace(year=current_year + 1, month=1)
                        else:
                            target_date = target_date.replace(month=month + 1)
                    
                    return {
                        "has_date": True,
                        "date": target_date,
                        "content": content,
                        "date_string": f"{month}/{day}",
                        "day_only": day  # 新增：只有日期的情況
                    }
                    
            elif pattern_type == 'month_day':
                # 8/24繳水電卡費
                month = int(match.group(1))
                day = int(match.group(2))
                content = match.group(3).strip()
                
                if 1 <= month <= 12 and 1 <= day <= 31 and content:
                    target_date = taiwan_now.replace(year=current_year, month=month, day=day,
                                                   hour=0, minute=0, second=0, microsecond=0)
                    if target_date < taiwan_now:
                        target_date = target_date.replace(year=current_year + 1)
                    
                    return {
                        "has_date": True,
                        "date": target_date,
                        "content": content,
                        "date_string": f"{month}/{day}"
                    }
                    
            elif pattern_type == 'content_day':
                # 繳水電卡費24號
                content = match.group(1).strip()
                day = int(match.group(2))
                
                if 1 <= day <= 31 and content:
                    month = taiwan_now.month
                    target_date = taiwan_now.replace(year=current_year, month=month, day=day,
                                                   hour=0, minute=0, second=0, microsecond=0)
                    if target_date < taiwan_now:
                        if month == 12:
                            target_date = target_date.replace(year=current_year + 1, month=1)
                        else:
                            target_date = target_date.replace(month=month + 1)
                    
                    return {
                        "has_date": True,
                        "date": target_date,
                        "content": content,
                        "date_string": f"{month}/{day}",
                        "day_only": day
                    }
                    
            elif pattern_type == 'content_month_day':
                # 繳水電卡費8/24
                content = match.group(1).strip()
                month = int(match.group(2))
                day = int(match.group(3))
                
                if 1 <= month <= 12 and 1 <= day <= 31 and content:
                    target_date = taiwan_now.replace(year=current_year, month=month, day=day,
                                                   hour=0, minute=0, second=0, microsecond=0)
                    if target_date < taiwan_now:
                        target_date = target_date.replace(year=current_year + 1)
                    
                    return {
                        "has_date": True,
                        "date": target_date,
                        "content": content,
                        "date_string": f"{month}/{day}"
                    }
    
    print(f"DEBUG: 沒有匹配到任何日期模式，原文: {text}")
    return {"has_date": False, "content": text}

def parse_short_reminder(text):
    """解析短期提醒"""
    patterns = [
        (r'(\d+)分鐘後(.+)', '分鐘', 1),
        (r'(\d+)小時後(.+)', '小時', 60),
        (r'(\d+)秒後(.+)', '秒', 1/60)
    ]
    
    for pattern, unit, multiplier in patterns:
        match = re.search(pattern, text)
        if match:
            value = int(match.group(1))
            content = match.group(2).strip()
            
            if not content:
                return {"is_valid": False, "error": "請輸入提醒內容"}
            
            minutes = value * multiplier
            
            if unit == '分鐘' and not (1 <= value <= 1440):
                return {"is_valid": False, "error": "分鐘數請設定在 1-1440 之間"}
            elif unit == '小時' and not (1 <= value <= 24):
                return {"is_valid": False, "error": "小時數請設定在 1-24 之間"}
            elif unit == '秒' and not (10 <= value <= 3600):
                return {"is_valid": False, "error": "秒數請設定在 10-3600 之間"}
            
            return {
                "is_valid": True,
                "minutes": minutes,
                "original_value": value,
                "unit": unit,
                "content": content
            }
    
    return {"is_valid": False, "error": "格式不正確，請使用：數字+時間單位+後+內容\n例如：5分鐘後倒垃圾"}

def parse_time_reminder(text):
    """解析時間提醒"""
    time_pattern = r'(\d{1,2}):(\d{2})(.+)'
    match = re.search(time_pattern, text)
    
    if match:
        hours = int(match.group(1))
        minutes = int(match.group(2))
        content = match.group(3).strip()
        
        if not content:
            return {"is_valid": False, "error": "請輸入提醒內容"}
        
        if not (0 <= hours <= 23):
            return {"is_valid": False, "error": "小時請設定在 0-23 之間"}
        
        if not (0 <= minutes <= 59):
            return {"is_valid": False, "error": "分鐘請設定在 0-59 之間"}
        
        return {
            "is_valid": True,
            "hours": hours,
            "minutes": minutes,
            "time_string": f"{hours:02d}:{minutes:02d}",
            "content": content
        }
    
    return {"is_valid": False, "error": "格式不正確，請使用：HH:MM+內容\n例如：12:00倒垃圾"}

# ===== LINE API 函數 =====
def send_push_message(user_id, message_text):
    """發送推播訊息"""
    if not CHANNEL_ACCESS_TOKEN or not user_id:
        print(f"模擬推播給 {user_id}: {message_text} (台灣時間: {get_taiwan_time()})")
        return False
    
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {CHANNEL_ACCESS_TOKEN}'
    }
    
    data = {
        'to': user_id,
        'messages': [{
            'type': 'text',
            'text': message_text
        }]
    }
    
    try:
        response = requests.post(PUSH_API_URL, headers=headers, data=json.dumps(data))
        print(f"推播發送 - 狀態碼: {response.status_code} - 台灣時間: {get_taiwan_time()}")
        return response.status_code == 200
    except Exception as e:
        print(f"推播失敗: {e} - 台灣時間: {get_taiwan_time()}")
        return False

def reply_message(reply_token, message_text):
    """回覆訊息"""
    if not CHANNEL_ACCESS_TOKEN:
        print(f"模擬回覆: {message_text} (台灣時間: {get_taiwan_time()})")
        return False
    
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {CHANNEL_ACCESS_TOKEN}'
    }
    
    data = {
        'replyToken': reply_token,
        'messages': [{
            'type': 'text',
            'text': message_text
        }]
    }
    
    try:
        response = requests.post(LINE_API_URL, headers=headers, data=json.dumps(data))
        return response.status_code == 200
    except Exception as e:
        print(f"回覆失敗: {e} - 台灣時間: {get_taiwan_time()}")
        return False

# ===== 提醒系統函數 =====
def check_reminders():
    """檢查並發送提醒 - 改進版本"""
    while True:
        try:
            current_time = get_taiwan_time_hhmm()
            user_id = user_settings.get('user_id')
            taiwan_now = get_taiwan_datetime()
            
            print(f"🔍 提醒檢查 - 台灣時間: {get_taiwan_time()}")
            
            # 檢查定時提醒（每日早晚） - 改進：每次都提醒所有待辦事項
            if user_id and (current_time == user_settings['morning_time'] or current_time == user_settings['evening_time']):
                send_daily_reminder(user_id, current_time)
            
            # 檢查每月提醒 - 改進：前一天預告 + 當天提醒
            if current_time == user_settings['evening_time']:  # 晚上檢查明天的每月事項
                check_monthly_preview(taiwan_now, user_id)
            
            if current_time == "09:00":  # 早上檢查今天的每月事項
                check_monthly_reminders(taiwan_now, user_id)
            
            # 檢查短期提醒
            check_short_reminders(taiwan_now)
            
            # 檢查時間提醒
            check_time_reminders(taiwan_now)
            
            time.sleep(60)  # 每分鐘檢查一次
        except Exception as e:
            print(f"提醒檢查錯誤: {e} - 台灣時間: {get_taiwan_time()}")
            time.sleep(60)

def send_daily_reminder(user_id, current_time):
    """發送每日提醒 - 改進版本：每次都提醒所有待辦事項"""
    time_icon = '🌅' if current_time == user_settings['morning_time'] else '🌙'
    time_text = '早安' if current_time == user_settings['morning_time'] else '晚安'
    
    if todos:
        # 分類待辦事項
        pending_todos = [todo for todo in todos if not todo.get('completed', False)]
        completed_todos = [todo for todo in todos if todo.get('completed', False)]
        
        if pending_todos:
            message = f'{time_icon} {time_text}！您有 {len(pending_todos)} 項待辦事項：\n\n'
            
            # 顯示未完成的事項（最多5項）
            for i, todo in enumerate(pending_todos[:5], 1):
                date_info = f" 📅{todo.get('target_date', '')}" if todo.get('has_date') else ""
                message += f'{i}. ⭕ {todo["content"]}{date_info}\n'
            
            if len(pending_todos) > 5:
                message += f'\n...還有 {len(pending_todos) - 5} 項未完成\n'
            
            # 如果有已完成的事項，也顯示（最多2項）
            if completed_todos:
                message += f'\n✅ 已完成 {len(completed_todos)} 項：\n'
                for todo in completed_todos[:2]:
                    message += f'✅ {todo["content"]}\n'
                if len(completed_todos) > 2:
                    message += f'...還有 {len(completed_todos) - 2} 項已完成\n'
            
            if current_time == user_settings['morning_time']:
                message += f'\n💪 新的一天開始了！加油完成這些任務！'
            else:
                message += f'\n🌙 檢查一下今天的進度吧！記得為明天做準備！'
                
            message += f'\n🇹🇼 台灣時間: {get_taiwan_time_hhmm()}'
            
            send_push_message(user_id, message)
            print(f"✅ 已發送每日提醒 ({len(pending_todos)} 項待辦) - 台灣時間: {get_taiwan_time()}")
        else:
            # 所有事項都已完成
            if current_time == user_settings['morning_time']:
                message = f'{time_icon} {time_text}！🎉 太棒了！目前沒有待辦事項\n💡 可以新增今天要做的事情'
            else:
                message = f'{time_icon} {time_text}！🎉 太棒了！今天的任務都完成了\n😴 好好休息，為明天準備新的目標！'
            
            message += f'\n🇹🇼 台灣時間: {get_taiwan_time_hhmm()}'
            send_push_message(user_id, message)
            print(f"✅ 已發送每日提醒 (無待辦事項) - 台灣時間: {get_taiwan_time()}")
    else:
        # 完全沒有任何事項
        if current_time == user_settings['morning_time']:
            message = f'{time_icon} {time_text}！✨ 新的一天開始了！\n💡 輸入「新增 事項名稱」來建立今天的目標'
        else:
            message = f'{time_icon} {time_text}！😌 今天過得如何？\n💡 別忘了為明天規劃一些目標'
        
        message += f'\n🇹🇼 台灣時間: {get_taiwan_time_hhmm()}'
        send_push_message(user_id, message)
        print(f"✅ 已發送每日提醒 (首次使用) - 台灣時間: {get_taiwan_time()}")

def check_monthly_preview(taiwan_now, user_id):
    """檢查明天的每月提醒 - 新增功能：前一天預告"""
    if not monthly_todos or not user_id:
        return
    
    tomorrow = taiwan_now + timedelta(days=1)
    tomorrow_day = tomorrow.day
    
    # 檢查明天是否有每月事項
    monthly_items_tomorrow = []
    for item in monthly_todos:
        target_day = item.get('day', 1)
        if target_day == tomorrow_day:
            monthly_items_tomorrow.append(item)
    
    if monthly_items_tomorrow:
        message = f"📅 每月提醒預告！\n\n明天 ({tomorrow.strftime('%m/%d')}) 有 {len(monthly_items_tomorrow)} 項每月固定事項：\n\n"
        
        for i, item in enumerate(monthly_items_tomorrow, 1):
            message += f"{i}. 🔄 {item['content']}\n"
        
        message += f"\n💡 明天早上會自動加入待辦清單並提醒您\n🇹🇼 台灣時間: {get_taiwan_time_hhmm()}"
        
        send_push_message(user_id, message)
        print(f"✅ 已發送每月預告提醒，明天有 {len(monthly_items_tomorrow)} 項事項 - 台灣時間: {get_taiwan_time()}")

def check_monthly_reminders(taiwan_now, user_id):
    """檢查每月提醒 - 改進版本：當天正式提醒"""
    if not monthly_todos or not user_id:
        return
    
    current_day = taiwan_now.day
    
    # 檢查是否有符合今天日期的每月事項
    monthly_items_today = []
    for item in monthly_todos:
        target_day = item.get('day', 1)
        if target_day == current_day:
            monthly_items_today.append(item)
    
    if monthly_items_today:
        # 自動將每月事項加入今日待辦
        added_items = []
        for item in monthly_items_today:
            # 檢查是否已經加入過（避免重複）
            already_exists = any(
                todo['content'] == item['content'] and 
                todo.get('created_at', '').startswith(taiwan_now.strftime('%Y/%m/%d'))
                for todo in todos
            )
            
            if not already_exists:
                todo_item = {
                    'id': len(todos) + 1,
                    'content': item['content'],
                    'created_at': get_taiwan_time(),
                    'completed': False,
                    'has_date': True,
                    'target_date': taiwan_now.strftime('%Y/%m/%d'),
                    'date_string': f"{taiwan_now.month}/{taiwan_now.day}",
                    'from_monthly': True
                }
                todos.append(todo_item)
                added_items.append(item['content'])
        
        if added_items:
            # 發送每月提醒
            message = f"🔄 每月提醒！今天 ({taiwan_now.strftime('%m/%d')}) 的固定事項：\n\n"
            for i, content in enumerate(added_items, 1):
                message += f"{i}. 📅 {content}\n"
            
            message += f"\n✅ 已自動加入今日待辦清單"
            message += f"\n💡 昨天已經預告過，現在正式提醒！"
            message += f"\n🇹🇼 台灣時間: {get_taiwan_time_hhmm()}"
            
            send_push_message(user_id, message)
            print(f"✅ 已發送每月正式提醒，加入 {len(added_items)} 項事項 - 台灣時間: {get_taiwan_time()}")

def check_short_reminders(taiwan_now):
    """檢查短期提醒"""
    for reminder in short_reminders[:]:
        reminder_time_str = reminder['reminder_time']
        try:
            if '+' in reminder_time_str or reminder_time_str.endswith('Z'):
                reminder_time = datetime.fromisoformat(reminder_time_str.replace('Z', '+00:00'))
                reminder_time = reminder_time.astimezone(TAIWAN_TZ)
            else:
                reminder_time = TAIWAN_TZ.localize(datetime.fromisoformat(reminder_time_str))
        except:
            print(f"⚠️ 無法解析提醒時間: {reminder_time_str}")
            short_reminders.remove(reminder)
            continue
        
        if reminder_time <= taiwan_now:
            user_id = reminder.get('user_id') or user_settings.get('user_id')
            if user_id:
                message = f"⏰ 短期提醒時間到！\n\n📋 {reminder['content']}\n🎯 該去執行了！\n🇹🇼 台灣時間: {get_taiwan_time_hhmm()}"
                send_push_message(user_id, message)
                print(f"✅ 已發送短期提醒: {reminder['content']} - 台灣時間: {get_taiwan_time()}")
            short_reminders.remove(reminder)

def check_time_reminders(taiwan_now):
    """檢查時間提醒"""
    for reminder in time_reminders[:]:
        reminder_time_str = reminder['reminder_time']
        try:
            if '+' in reminder_time_str or reminder_time_str.endswith('Z'):
                reminder_time = datetime.fromisoformat(reminder_time_str.replace('Z', '+00:00'))
                reminder_time = reminder_time.astimezone(TAIWAN_TZ)
            else:
                reminder_time = TAIWAN_TZ.localize(datetime.fromisoformat(reminder_time_str))
        except:
            print(f"⚠️ 無法解析提醒時間: {reminder_time_str}")
            time_reminders.remove(reminder)
            continue
            
        if reminder_time <= taiwan_now:
            user_id = reminder.get('user_id') or user_settings.get('user_id')
            if user_id:
                message = f"🕐 時間提醒！\n\n📋 {reminder['content']}\n⏰ {reminder['time_string']}\n🎯 該去執行了！\n🇹🇼 台灣時間: {get_taiwan_time_hhmm()}"
                send_push_message(user_id, message)
                print(f"✅ 已發送時間提醒: {reminder['content']} - 台灣時間: {get_taiwan_time()}")
            time_reminders.remove(reminder)

# 啟動提醒檢查執行緒
reminder_thread = threading.Thread(target=check_reminders, daemon=True)
reminder_thread.start()

# 防休眠機制
def keep_alive():
    """防休眠機制"""
    base_url = os.getenv('BASE_URL', 'https://line-bot-python-v2.onrender.com')
    
    while True:
        try:
            time.sleep(240)  # 4 分鐘
            response = requests.get(f'{base_url}/health', timeout=15)
            
            if response.status_code == 200:
                print(f"✅ Keep-alive 成功 - 台灣時間: {get_taiwan_time()}")
            else:
                print(f"⚠️ Keep-alive 警告: {response.status_code} - 台灣時間: {get_taiwan_time()}")
                
        except requests.exceptions.RequestException as e:
            print(f"❌ Keep-alive 錯誤: {e} - 台灣時間: {get_taiwan_time()}")
            time.sleep(60)
        except Exception as e:
            print(f"❌ Keep-alive 意外錯誤: {e} - 台灣時間: {get_taiwan_time()}")
            time.sleep(60)

keep_alive_thread = threading.Thread(target=keep_alive, daemon=True)
keep_alive_thread.start()

# ===== Flask 路由 =====
@app.route('/')
def home():
    return f'LINE Todo Reminder Bot v3.0 - 股票記帳功能已加入！當前台灣時間: {get_taiwan_time()}'

@app.route('/health')
def health():
    """健康檢查端點"""
    taiwan_now = get_taiwan_datetime()
    
    try:
        next_morning = taiwan_now.replace(
            hour=int(user_settings['morning_time'].split(':')[0]),
            minute=int(user_settings['morning_time'].split(':')[1]),
            second=0, microsecond=0
        )
        if next_morning <= taiwan_now:
            next_morning += timedelta(days=1)
        
        next_evening = taiwan_now.replace(
            hour=int(user_settings['evening_time'].split(':')[0]),
            minute=int(user_settings['evening_time'].split(':')[1]),
            second=0, microsecond=0
        )
        if next_evening <= taiwan_now:
            next_evening += timedelta(days=1)
        
        next_reminder = min(next_morning, next_evening)
        next_reminder_str = next_reminder.strftime('%Y/%m/%d %H:%M')
    except:
        next_reminder_str = "計算錯誤"
    
    return {
        'status': 'healthy',
        'taiwan_time': get_taiwan_time(),
        'taiwan_time_hhmm': get_taiwan_time_hhmm(),
        'server_timezone': str(taiwan_now.tzinfo),
        'todos_count': len(todos),
        'monthly_todos_count': len(monthly_todos),
        'short_reminders': len(short_reminders),
        'time_reminders': len(time_reminders),
        'stock_accounts_count': len(stock_data['accounts']),
        'stock_transactions_count': len(stock_data['transactions']),
        'morning_time': user_settings['morning_time'],
        'evening_time': user_settings['evening_time'],
        'next_reminder': next_reminder_str,
        'has_user': user_settings['user_id'] is not None,
        'version': '3.0_stock_trading'
    }

@app.route('/webhook', methods=['POST'])
def webhook():
    """LINE Webhook 處理"""
    try:
        data = request.get_json()
        
        for event in data.get('events', []):
            if event['type'] == 'message' and event['message']['type'] == 'text':
                reply_token = event['replyToken']
                message_text = event['message']['text'].strip()
                user_id = event['source']['userId']
                
                # 儲存用戶ID
                user_settings['user_id'] = user_id
                
                print(f"用戶訊息: {message_text} - 台灣時間: {get_taiwan_time()}")
                
                # === 股票功能路由 ===
                if any(keyword in message_text for keyword in ['買入', '賣出', '入帳', '提款', '新增帳戶']):
                    reply_text = handle_stock_command(message_text, user_id)
                
                # 股票查詢功能
                elif message_text == '總覽':
                    reply_text = get_all_accounts_summary()
                
                elif message_text.endswith('查詢'):
                    account_name = message_text[:-2].strip()  # 去掉「查詢」
                    if account_name in ['股票', '帳戶']:
                        reply_text = get_all_accounts_summary()
                    else:
                        reply_text = get_account_summary(account_name)
                
                elif message_text == '交易記錄':
                    reply_text = get_transaction_history()
                
                elif message_text.startswith('交易記錄 '):
                    account_name = message_text[5:].strip()
                    reply_text = get_transaction_history(account_name)
                
                elif message_text.startswith('成本查詢 ') and ' ' in message_text[5:]:
                    parts = message_text[5:].strip().split(' ', 1)
                    if len(parts) == 2:
                        account_name, stock_code = parts
                        reply_text = get_stock_cost_analysis(account_name, stock_code)
                    else:
                        reply_text = "❌ 格式不正確\n💡 例如：成本查詢 爸爸 2330 台積電"
                
                elif message_text == '帳戶列表':
                    if stock_data['accounts']:
                        account_list = list(stock_data['accounts'].keys())
                        reply_text = f"👥 目前帳戶列表：\n\n" + "\n".join([f"👤 {name}" for name in account_list])
                    else:
                        reply_text = "📝 目前沒有任何帳戶"
                
                elif message_text == '股票幫助':
                    reply_text = """💰 多帳戶股票記帳功能：

📋 帳戶管理：
- 爸爸入帳 50000 - 入金
- 媽媽提款 10000 - 提款  
- 新增帳戶 奶奶 - 建立帳戶

📈 交易操作：
- 爸爸買入 2330 台積電 100股 實付50000元 2024/08/20
- 媽媽賣出 2317 鴻海 50股 實收5000元 2024/08/21

📊 查詢功能：
- 總覽 - 所有帳戶總覽
- 爸爸查詢 - 個人資金和持股
- 交易記錄 - 所有交易歷史
- 交易記錄 爸爸 - 個人交易記錄
- 成本查詢 爸爸 2330 台積電 - 持股成本分析
- 帳戶列表 - 查看所有帳戶

💡 v3.0 新功能：完整的多帳戶股票記帳！"""

                # === 待辦事項功能路由 (保持原有邏輯) ===
                # 查詢時間
                elif message_text == '查詢時間':
                    reply_text = f"🇹🇼 台灣當前時間：{get_taiwan_time()}\n⏰ 目前提醒時間設定：\n🌅 早上：{user_settings['morning_time']}\n🌙 晚上：{user_settings['evening_time']}\n\n✅ 時區已修正為台灣時間！"

                # 設定提醒時間
                elif message_text.startswith('早上時間 '):
                    time_str = message_text[5:].strip()
                    if is_valid_time_format(time_str):
                        user_settings['morning_time'] = time_str
                        reply_text = f"🌅 已設定早上提醒時間為：{time_str}\n🇹🇼 台灣時間"
                    else:
                        reply_text = "❌ 時間格式不正確，請使用 HH:MM 格式，例如：08:30"

                elif message_text.startswith('晚上時間 '):
                    time_str = message_text[5:].strip()
                    if is_valid_time_format(time_str):
                        user_settings['evening_time'] = time_str
                        reply_text = f"🌙 已設定晚上提醒時間為：{time_str}\n🇹🇼 台灣時間"
                    else:
                        reply_text = "❌ 時間格式不正確，請使用 HH:MM 格式，例如：19:00"

                # 短期提醒
                elif any(keyword in message_text for keyword in ['分鐘後', '小時後', '秒後']):
                    parsed = parse_short_reminder(message_text)
                    if parsed['is_valid']:
                        taiwan_now = get_taiwan_datetime()
                        reminder_time = taiwan_now + timedelta(minutes=parsed['minutes'])
                        reminder_item = {
                            'id': len(short_reminders) + 1,
                            'user_id': user_id,
                            'content': parsed['content'],
                            'reminder_time': reminder_time.isoformat(),
                            'original_value': parsed['original_value'],
                            'unit': parsed['unit']
                        }
                        short_reminders.append(reminder_item)
                        
                        reply_text = f"⏰ 已設定短期提醒：「{parsed['content']}」\n⏳ {parsed['original_value']}{parsed['unit']}後提醒\n📅 提醒時間：{reminder_time.strftime('%H:%M')}\n🇹🇼 台灣時間"
                    else:
                        reply_text = f"❌ {parsed['error']}"

                # 時間提醒
                elif re.match(r'^\d{1,2}:\d{2}.+', message_text):
                    parsed = parse_time_reminder(message_text)
                    if parsed['is_valid']:
                        taiwan_now = get_taiwan_datetime()
                        target_time = taiwan_now.replace(
                            hour=parsed['hours'], 
                            minute=parsed['minutes'], 
                            second=0, 
                            microsecond=0
                        )
                        
                        if target_time <= taiwan_now:
                            target_time += timedelta(days=1)
                        
                        reminder_item = {
                            'id': len(time_reminders) + 1,
                            'user_id': user_id,
                            'content': parsed['content'],
                            'time_string': parsed['time_string'],
                            'reminder_time': target_time.isoformat()
                        }
                        time_reminders.append(reminder_item)
                        
                        date_text = '今天' if target_time.date() == taiwan_now.date() else '明天'
                        reply_text = f"🕐 已設定時間提醒：「{parsed['content']}」\n⏰ {date_text} {parsed['time_string']} 提醒\n🇹🇼 台灣時間"
                    else:
                        reply_text = f"❌ {parsed['error']}"

                # 幫助訊息
                elif message_text in ['幫助', 'help', '說明']:
                    reply_text = """📋 LINE Todo Bot v3.0 完整功能：

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

💰 股票記帳：
- 爸爸入帳 50000 - 入金
- 爸爸買入 2330 台積電 100股 實付50000元 2024/08/20
- 總覽 - 查看所有帳戶
- 股票幫助 - 股票功能詳細說明

🆕 v3.0 新功能：完整的多帳戶股票記帳系統！"""

                # 待辦事項功能
                elif message_text.startswith('新增 '):
                    todo_text = message_text[3:].strip()
                    if todo_text:
                        parsed = parse_date(todo_text)
                        todo_item = {
                            'id': len(todos) + 1,
                            'content': parsed['content'],
                            'created_at': get_taiwan_time(),
                            'completed': False,
                            'has_date': parsed.get('has_date', False),
                            'target_date': parsed.get('date').strftime('%Y/%m/%d') if parsed.get('date') else None,
                            'date_string': parsed.get('date_string')
                        }
                        todos.append(todo_item)
                        
                        if parsed.get('has_date'):
                            reply_text = f"✅ 已新增待辦事項：「{parsed['content']}」\n📅 目標日期：{parsed['date'].strftime('%Y/%m/%d')}\n📋 目前共有 {len(todos)} 項\n🇹🇼 台灣時間建立"
                        else:
                            reply_text = f"✅ 已新增待辦事項：「{parsed['content']}」\n📋 目前共有 {len(todos)} 項\n🇹🇼 台灣時間建立"
                    else:
                        reply_text = "❌ 請輸入要新增的事項內容"

                elif message_text in ['查詢', '清單']:
                    if todos:
                        reply_text = f"📋 待辦事項清單 ({len(todos)} 項)：\n\n"
                        for i, todo in enumerate(todos, 1):
                            status = "✅" if todo.get('completed') else "⭕"
                            date_info = f" 📅{todo.get('target_date', '')}" if todo.get('has_date') else ""
                            reply_text += f"{i}. {status} {todo['content']}{date_info}\n"
                        reply_text += "\n💡 輸入「幫助」查看更多功能"
                    else:
                        reply_text = "📝 目前沒有待辦事項"

                elif message_text.startswith('刪除 '):
                    try:
                        index = int(message_text[3:].strip()) - 1
                        if 0 <= index < len(todos):
                            deleted_todo = todos.pop(index)
                            reply_text = f"🗑️ 已刪除：「{deleted_todo['content']}」"
                        else:
                            reply_text = f"❌ 編號不正確"
                    except:
                        reply_text = "❌ 請輸入正確編號"

                elif message_text.startswith('完成 '):
                    try:
                        index = int(message_text[3:].strip()) - 1
                        if 0 <= index < len(todos):
                            todos[index]['completed'] = True
                            reply_text = f"🎉 已完成：「{todos[index]['content']}」"
                        else:
                            reply_text = f"❌ 編號不正確"
                    except:
                        reply_text = "❌ 請輸入正確編號"

                # 每月功能
                elif message_text.startswith('每月新增 '):
                    todo_text = message_text[5:].strip()
                    if todo_text:
                        parsed = parse_date(todo_text)
                        print(f"DEBUG: 解析結果: {parsed}")
                        
                        # 完全修正：更智能的日期處理
                        if parsed.get('has_date'):
                            if parsed.get('day_only'):
                                # 只有日期的情況，例如：24號繳水電卡費
                                day = parsed['day_only']
                                date_display = f"{day}號"
                            elif parsed.get('date_string'):
                                # 有月/日的情況，例如：8/24繳水電卡費
                                try:
                                    day = int(parsed['date_string'].split('/')[1])
                                    date_display = f"{day}號"
                                except:
                                    day = 1
                                    date_display = "1號"
                            else:
                                day = 1
                                date_display = "1號"
                        else:
                            # 沒有指定日期，例如：每月新增 買菜
                            day = 1
                            date_display = "1號"
                        
                        monthly_item = {
                            'id': len(monthly_todos) + 1,
                            'content': parsed['content'],
                            'created_at': get_taiwan_time(),
                            'has_date': parsed.get('has_date', False),
                            'date_string': parsed.get('date_string'),
                            'day': day,
                            'date_display': date_display
                        }
                        monthly_todos.append(monthly_item)
                        print(f"DEBUG: 新增的每月事項: {monthly_item}")
                        
                        reply_text = f"🔄 已新增每月事項：「{parsed['content']}」\n📅 每月 {date_display} 提醒\n📋 目前共有 {len(monthly_todos)} 項每月事項\n💡 會在前一天預告 + 當天提醒"
                    else:
                        reply_text = "❌ 請輸入要新增的每月事項內容\n💡 例如：每月新增 24號繳水電卡費"

                elif message_text == '每月清單':
                    if monthly_todos:
                        # 清理舊資料：為沒有 date_display 的項目補充
                        for item in monthly_todos:
                            if not item.get('date_display'):
                                if item.get('has_date') and item.get('date_string'):
                                    try:
                                        day = int(item['date_string'].split('/')[1])
                                        item['date_display'] = f"{day}號"
                                    except:
                                        item['date_display'] = f"{item.get('day', 1)}號"
                                else:
                                    item['date_display'] = f"{item.get('day', 1)}號"
                        
                        reply_text = f"🔄 每月固定事項清單 ({len(monthly_todos)} 項)：\n\n"
                        for i, item in enumerate(monthly_todos, 1):
                            date_display = item.get('date_display', f"{item.get('day', 1)}號")
                            reply_text += f"{i}. 📅 每月 {date_display} - {item['content']}\n"
                        reply_text += f"\n💡 這些事項會在前一天晚上預告，當天早上自動加入待辦清單"
                    else:
                        reply_text = "📝 目前沒有每月固定事項\n💡 輸入「每月新增 5號繳卡費」來新增"

                # 新增：清理每月資料的指令
                elif message_text == '清理每月':
                    if monthly_todos:
                        # 修正所有每月事項的顯示格式
                        fixed_count = 0
                        for item in monthly_todos:
                            if not item.get('date_display') or 'every month' in str(item.get('date_display', '')):
                                if item.get('has_date') and item.get('date_string'):
                                    try:
                                        day = int(item['date_string'].split('/')[1])
                                        item['date_display'] = f"{day}號"
                                        fixed_count += 1
                                    except:
                                        item['date_display'] = f"{item.get('day', 1)}號"
                                        fixed_count += 1
                                else:
                                    item['date_display'] = f"{item.get('day', 1)}號"
                                    fixed_count += 1
                        
                        reply_text = f"🔧 已修正 {fixed_count} 項每月事項的顯示格式\n💡 現在輸入「每月清單」查看修正結果"
                    else:
                        reply_text = "📝 目前沒有每月固定事項需要清理"

                # 測試功能
                elif message_text == '測試':
                    reply_text = f"✅ 機器人正常運作！\n🇹🇼 當前台灣時間：{get_taiwan_time()}\n⏰ 待辦提醒功能已啟用\n💰 股票記帳功能已啟用\n💡 輸入「幫助」或「股票幫助」查看功能"

                # 預設回應
                else:
                    reply_text = f"您說：{message_text}\n🇹🇼 當前台灣時間：{get_taiwan_time_hhmm()}\n\n💡 輸入「幫助」查看待辦功能\n💰 輸入「股票幫助」查看股票功能"
                
                # 發送回覆
                reply_message(reply_token, reply_text)
        
        return 'OK', 200
    
    except Exception as e:
        print(f"Webhook 處理錯誤: {e} - 台灣時間: {get_taiwan_time()}")
        return 'OK', 200

if __name__ == '__main__':
    print(f"🚀 LINE Bot v3.0 啟動 - 台灣時間: {get_taiwan_time()}")
    print(f"📋 待辦事項功能：已啟用")
    print(f"💰 股票記帳功能：已啟用")
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port), message_text):
        account, code, quantity, amount, date = match.groups()
        # 轉換日期格式 0820 -> 2024/08/20
        year = datetime.now().year
        month = int(date[:2])
        day = int(date[2:])
        formatted_date = f"{year}/{month:02d}/{day:02d}"
        
        # 查找股票名稱（簡化版本，常見股票代碼對照）
        stock_names = {
            '2330': '台積電', '2317': '鴻海', '2454': '聯發科', '2308': '台達電',
            '2382': '廣達', '3711': '日月光', '2303': '聯電', '2881': '富邦金',
            '2412': '中華電', '1303': '南亞', '1301': '台塑', '2886': '兆豐金'
        }
        stock_name = stock_names.get(code, '未知股票')
        
        return {
            'type': 'buy',
            'account': account.strip(),
            'stock_code': f"{code} {stock_name}",
            'quantity': int(quantity),
            'amount': int(amount),
            'date': formatted_date
        }
    
    # 賣出（簡化版）：賣 媽媽 2317 50 5000 0821
    elif match := re.match(r'^賣\s+(.+?)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d{4})

def handle_stock_deposit(account_name, amount):
    """處理入帳"""
    is_new = get_or_create_account(account_name)
    stock_data['accounts'][account_name]['cash'] += amount
    
    # 記錄交易
    transaction = {
        'id': len(stock_data['transactions']) + 1,
        'type': '入帳',
        'account': account_name,
        'stock_code': None,
        'quantity': 0,
        'amount': amount,
        'price_per_share': 0,
        'date': get_taiwan_time().split(' ')[0],
        'cash_after': stock_data['accounts'][account_name]['cash'],
        'created_at': get_taiwan_time()
    }
    stock_data['transactions'].append(transaction)
    
    result_msg = f"💰 {account_name} 入帳成功！\n"
    if is_new:
        result_msg += f"🆕 已建立新帳戶\n"
    result_msg += f"💵 入帳金額：{amount:,}元\n"
    result_msg += f"💳 帳戶餘額：{stock_data['accounts'][account_name]['cash']:,}元"
    
    return result_msg

def handle_stock_withdraw(account_name, amount):
    """處理提款"""
    if account_name not in stock_data['accounts']:
        return f"❌ 帳戶「{account_name}」不存在"
    
    account = stock_data['accounts'][account_name]
    if account['cash'] < amount:
        return f"❌ 餘額不足！\n💳 目前餘額：{account['cash']:,}元\n💸 提款金額：{amount:,}元"
    
    account['cash'] -= amount
    
    # 記錄交易
    transaction = {
        'id': len(stock_data['transactions']) + 1,
        'type': '提款',
        'account': account_name,
        'stock_code': None,
        'quantity': 0,
        'amount': amount,
        'price_per_share': 0,
        'date': get_taiwan_time().split(' ')[0],
        'cash_after': account['cash'],
        'created_at': get_taiwan_time()
    }
    stock_data['transactions'].append(transaction)
    
    return f"💸 {account_name} 提款成功！\n💵 提款金額：{amount:,}元\n💳 帳戶餘額：{account['cash']:,}元"

def handle_stock_buy(account_name, stock_code, quantity, amount, date):
    """處理買入股票"""
    if account_name not in stock_data['accounts']:
        return f"❌ 帳戶「{account_name}」不存在"
    
    account = stock_data['accounts'][account_name]
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
        'id': len(stock_data['transactions']) + 1,
        'type': '買入',
        'account': account_name,
        'stock_code': stock_code,
        'quantity': quantity,
        'amount': amount,
        'price_per_share': price_per_share,
        'date': date,
        'cash_after': account['cash'],
        'created_at': get_taiwan_time()
    }
    stock_data['transactions'].append(transaction)
    
    stock_info = account['stocks'][stock_code]
    return f"📈 {account_name} 買入成功！\n\n🏷️ {stock_code}\n📊 買入：{quantity}股 @ {price_per_share}元\n💰 實付：{amount:,}元\n📅 日期：{date}\n\n📋 持股狀況：\n📊 總持股：{stock_info['quantity']}股\n💵 平均成本：{stock_info['avg_cost']}元/股\n💳 剩餘現金：{account['cash']:,}元"

def handle_stock_sell(account_name, stock_code, quantity, amount, date):
    """處理賣出股票"""
    if account_name not in stock_data['accounts']:
        return f"❌ 帳戶「{account_name}」不存在"
    
    account = stock_data['accounts'][account_name]
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
        'id': len(stock_data['transactions']) + 1,
        'type': '賣出',
        'account': account_name,
        'stock_code': stock_code,
        'quantity': quantity,
        'amount': amount,
        'price_per_share': price_per_share,
        'date': date,
        'cash_after': account['cash'],
        'created_at': get_taiwan_time(),
        'profit_loss': profit_loss
    }
    stock_data['transactions'].append(transaction)
    
    profit_text = f"💰 獲利：+{profit_loss:,}元" if profit_loss > 0 else f"💸 虧損：{profit_loss:,}元" if profit_loss < 0 else "💫 損益兩平"
    
    result = f"📉 {account_name} 賣出成功！\n\n🏷️ {stock_code}\n📊 賣出：{quantity}股 @ {price_per_share}元\n💰 實收：{amount:,}元\n📅 日期：{date}\n\n💹 本次交易：\n💵 成本：{sell_cost:,}元\n{profit_text}\n💳 現金餘額：{account['cash']:,}元"
    
    if remaining_quantity > 0:
        result += f"\n\n📋 剩餘持股：{remaining_quantity}股"
    else:
        result += f"\n\n✅ 已全部賣出 {stock_code}"
    
    return result

def get_account_summary(account_name):
    """獲取帳戶摘要"""
    if account_name not in stock_data['accounts']:
        return f"❌ 帳戶「{account_name}」不存在"
    
    account = stock_data['accounts'][account_name]
    
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

def get_all_accounts_summary():
    """獲取所有帳戶總覽"""
    if not stock_data['accounts']:
        return "📝 目前沒有任何帳戶\n💡 輸入「爸爸入帳 100000」來建立第一個帳戶"
    
    result = "🏦 家庭投資總覽：\n\n"
    
    total_cash = 0
    total_investment = 0
    all_stocks = {}
    
    for account_name, account in stock_data['accounts'].items():
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

def get_transaction_history(account_name=None, limit=10):
    """獲取交易記錄"""
    transactions = stock_data['transactions']
    
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

def get_stock_cost_analysis(account_name, stock_code):
    """獲取特定股票的成本分析"""
    if account_name not in stock_data['accounts']:
        return f"❌ 帳戶「{account_name}」不存在"
    
    account = stock_data['accounts'][account_name]
    if stock_code not in account['stocks']:
        return f"❌ {account_name} 沒有持有「{stock_code}」"
    
    holding = account['stocks'][stock_code]
    
    # 查找相關交易記錄
    related_transactions = [
        t for t in stock_data['transactions'] 
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

def handle_stock_command(message_text, user_id):
    """處理股票相關指令"""
    parsed = parse_stock_command(message_text)
    
    if not parsed:
        return "❌ 指令格式不正確\n💡 輸入「股票幫助」查看使用說明"
    
    try:
        if parsed['type'] == 'deposit':
            return handle_stock_deposit(parsed['account'], parsed['amount'])
        
        elif parsed['type'] == 'withdraw':
            return handle_stock_withdraw(parsed['account'], parsed['amount'])
        
        elif parsed['type'] == 'buy':
            return handle_stock_buy(
                parsed['account'], parsed['stock_code'], 
                parsed['quantity'], parsed['amount'], parsed['date']
            )
        
        elif parsed['type'] == 'sell':
            return handle_stock_sell(
                parsed['account'], parsed['stock_code'], 
                parsed['quantity'], parsed['amount'], parsed['date']
            )
        
        elif parsed['type'] == 'create_account':
            is_new = get_or_create_account(parsed['account'])
            if is_new:
                return f"🆕 已建立帳戶「{parsed['account']}」\n💡 可以開始入帳和交易了！"
            else:
                return f"ℹ️ 帳戶「{parsed['account']}」已存在"
        
    except Exception as e:
        return f"❌ 處理失敗：{str(e)}\n💡 請檢查指令格式"
    
    return "❌ 未知的指令類型"

# ===== 待辦事項功能函數 (保持原有) =====
def parse_date(text):
    """解析日期格式 - 改進版本，更好地處理每月事項"""
    taiwan_now = get_taiwan_datetime()
    current_year = taiwan_now.year
    
    # 改進的日期模式，更靈活地匹配
    patterns = [
        # 格式：24號繳水電卡費
        (r'(\d{1,2})號(.+)', 'day_only'),
        # 格式：8/24繳水電卡費 或 8/24號繳水電卡費
        (r'(\d{1,2})\/(\d{1,2})號?(.+)', 'month_day'),
        # 格式：繳水電卡費24號
        (r'(.+?)(\d{1,2})號', 'content_day'),
        # 格式：繳水電卡費8/24
        (r'(.+?)(\d{1,2})\/(\d{1,2})號?', 'content_month_day')
    ]
    
    for pattern, pattern_type in patterns:
        match = re.search(pattern, text)
        if match:
            print(f"DEBUG: 匹配到模式 {pattern_type}: {match.groups()}")
            
            if pattern_type == 'day_only':
                # 24號繳水電卡費
                day = int(match.group(1))
                content = match.group(2).strip()
                if 1 <= day <= 31 and content:
                    # 使用當前月份
                    month = taiwan_now.month
                    target_date = taiwan_now.replace(year=current_year, month=month, day=day,
                                                   hour=0, minute=0, second=0, microsecond=0)
                    if target_date < taiwan_now:
                        if month == 12:
                            target_date = target_date.replace(year=current_year + 1, month=1)
                        else:
                            target_date = target_date.replace(month=month + 1)
                    
                    return {
                        "has_date": True,
                        "date": target_date,
                        "content": content,
                        "date_string": f"{month}/{day}",
                        "day_only": day  # 新增：只有日期的情況
                    }
                    
            elif pattern_type == 'month_day':
                # 8/24繳水電卡費
                month = int(match.group(1))
                day = int(match.group(2))
                content = match.group(3).strip()
                
                if 1 <= month <= 12 and 1 <= day <= 31 and content:
                    target_date = taiwan_now.replace(year=current_year, month=month, day=day,
                                                   hour=0, minute=0, second=0, microsecond=0)
                    if target_date < taiwan_now:
                        target_date = target_date.replace(year=current_year + 1)
                    
                    return {
                        "has_date": True,
                        "date": target_date,
                        "content": content,
                        "date_string": f"{month}/{day}"
                    }
                    
            elif pattern_type == 'content_day':
                # 繳水電卡費24號
                content = match.group(1).strip()
                day = int(match.group(2))
                
                if 1 <= day <= 31 and content:
                    month = taiwan_now.month
                    target_date = taiwan_now.replace(year=current_year, month=month, day=day,
                                                   hour=0, minute=0, second=0, microsecond=0)
                    if target_date < taiwan_now:
                        if month == 12:
                            target_date = target_date.replace(year=current_year + 1, month=1)
                        else:
                            target_date = target_date.replace(month=month + 1)
                    
                    return {
                        "has_date": True,
                        "date": target_date,
                        "content": content,
                        "date_string": f"{month}/{day}",
                        "day_only": day
                    }
                    
            elif pattern_type == 'content_month_day':
                # 繳水電卡費8/24
                content = match.group(1).strip()
                month = int(match.group(2))
                day = int(match.group(3))
                
                if 1 <= month <= 12 and 1 <= day <= 31 and content:
                    target_date = taiwan_now.replace(year=current_year, month=month, day=day,
                                                   hour=0, minute=0, second=0, microsecond=0)
                    if target_date < taiwan_now:
                        target_date = target_date.replace(year=current_year + 1)
                    
                    return {
                        "has_date": True,
                        "date": target_date,
                        "content": content,
                        "date_string": f"{month}/{day}"
                    }
    
    print(f"DEBUG: 沒有匹配到任何日期模式，原文: {text}")
    return {"has_date": False, "content": text}

def parse_short_reminder(text):
    """解析短期提醒"""
    patterns = [
        (r'(\d+)分鐘後(.+)', '分鐘', 1),
        (r'(\d+)小時後(.+)', '小時', 60),
        (r'(\d+)秒後(.+)', '秒', 1/60)
    ]
    
    for pattern, unit, multiplier in patterns:
        match = re.search(pattern, text)
        if match:
            value = int(match.group(1))
            content = match.group(2).strip()
            
            if not content:
                return {"is_valid": False, "error": "請輸入提醒內容"}
            
            minutes = value * multiplier
            
            if unit == '分鐘' and not (1 <= value <= 1440):
                return {"is_valid": False, "error": "分鐘數請設定在 1-1440 之間"}
            elif unit == '小時' and not (1 <= value <= 24):
                return {"is_valid": False, "error": "小時數請設定在 1-24 之間"}
            elif unit == '秒' and not (10 <= value <= 3600):
                return {"is_valid": False, "error": "秒數請設定在 10-3600 之間"}
            
            return {
                "is_valid": True,
                "minutes": minutes,
                "original_value": value,
                "unit": unit,
                "content": content
            }
    
    return {"is_valid": False, "error": "格式不正確，請使用：數字+時間單位+後+內容\n例如：5分鐘後倒垃圾"}

def parse_time_reminder(text):
    """解析時間提醒"""
    time_pattern = r'(\d{1,2}):(\d{2})(.+)'
    match = re.search(time_pattern, text)
    
    if match:
        hours = int(match.group(1))
        minutes = int(match.group(2))
        content = match.group(3).strip()
        
        if not content:
            return {"is_valid": False, "error": "請輸入提醒內容"}
        
        if not (0 <= hours <= 23):
            return {"is_valid": False, "error": "小時請設定在 0-23 之間"}
        
        if not (0 <= minutes <= 59):
            return {"is_valid": False, "error": "分鐘請設定在 0-59 之間"}
        
        return {
            "is_valid": True,
            "hours": hours,
            "minutes": minutes,
            "time_string": f"{hours:02d}:{minutes:02d}",
            "content": content
        }
    
    return {"is_valid": False, "error": "格式不正確，請使用：HH:MM+內容\n例如：12:00倒垃圾"}

# ===== LINE API 函數 =====
def send_push_message(user_id, message_text):
    """發送推播訊息"""
    if not CHANNEL_ACCESS_TOKEN or not user_id:
        print(f"模擬推播給 {user_id}: {message_text} (台灣時間: {get_taiwan_time()})")
        return False
    
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {CHANNEL_ACCESS_TOKEN}'
    }
    
    data = {
        'to': user_id,
        'messages': [{
            'type': 'text',
            'text': message_text
        }]
    }
    
    try:
        response = requests.post(PUSH_API_URL, headers=headers, data=json.dumps(data))
        print(f"推播發送 - 狀態碼: {response.status_code} - 台灣時間: {get_taiwan_time()}")
        return response.status_code == 200
    except Exception as e:
        print(f"推播失敗: {e} - 台灣時間: {get_taiwan_time()}")
        return False

def reply_message(reply_token, message_text):
    """回覆訊息"""
    if not CHANNEL_ACCESS_TOKEN:
        print(f"模擬回覆: {message_text} (台灣時間: {get_taiwan_time()})")
        return False
    
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {CHANNEL_ACCESS_TOKEN}'
    }
    
    data = {
        'replyToken': reply_token,
        'messages': [{
            'type': 'text',
            'text': message_text
        }]
    }
    
    try:
        response = requests.post(LINE_API_URL, headers=headers, data=json.dumps(data))
        return response.status_code == 200
    except Exception as e:
        print(f"回覆失敗: {e} - 台灣時間: {get_taiwan_time()}")
        return False

# ===== 提醒系統函數 =====
def check_reminders():
    """檢查並發送提醒 - 改進版本"""
    while True:
        try:
            current_time = get_taiwan_time_hhmm()
            user_id = user_settings.get('user_id')
            taiwan_now = get_taiwan_datetime()
            
            print(f"🔍 提醒檢查 - 台灣時間: {get_taiwan_time()}")
            
            # 檢查定時提醒（每日早晚） - 改進：每次都提醒所有待辦事項
            if user_id and (current_time == user_settings['morning_time'] or current_time == user_settings['evening_time']):
                send_daily_reminder(user_id, current_time)
            
            # 檢查每月提醒 - 改進：前一天預告 + 當天提醒
            if current_time == user_settings['evening_time']:  # 晚上檢查明天的每月事項
                check_monthly_preview(taiwan_now, user_id)
            
            if current_time == "09:00":  # 早上檢查今天的每月事項
                check_monthly_reminders(taiwan_now, user_id)
            
            # 檢查短期提醒
            check_short_reminders(taiwan_now)
            
            # 檢查時間提醒
            check_time_reminders(taiwan_now)
            
            time.sleep(60)  # 每分鐘檢查一次
        except Exception as e:
            print(f"提醒檢查錯誤: {e} - 台灣時間: {get_taiwan_time()}")
            time.sleep(60)

def send_daily_reminder(user_id, current_time):
    """發送每日提醒 - 改進版本：每次都提醒所有待辦事項"""
    time_icon = '🌅' if current_time == user_settings['morning_time'] else '🌙'
    time_text = '早安' if current_time == user_settings['morning_time'] else '晚安'
    
    if todos:
        # 分類待辦事項
        pending_todos = [todo for todo in todos if not todo.get('completed', False)]
        completed_todos = [todo for todo in todos if todo.get('completed', False)]
        
        if pending_todos:
            message = f'{time_icon} {time_text}！您有 {len(pending_todos)} 項待辦事項：\n\n'
            
            # 顯示未完成的事項（最多5項）
            for i, todo in enumerate(pending_todos[:5], 1):
                date_info = f" 📅{todo.get('target_date', '')}" if todo.get('has_date') else ""
                message += f'{i}. ⭕ {todo["content"]}{date_info}\n'
            
            if len(pending_todos) > 5:
                message += f'\n...還有 {len(pending_todos) - 5} 項未完成\n'
            
            # 如果有已完成的事項，也顯示（最多2項）
            if completed_todos:
                message += f'\n✅ 已完成 {len(completed_todos)} 項：\n'
                for todo in completed_todos[:2]:
                    message += f'✅ {todo["content"]}\n'
                if len(completed_todos) > 2:
                    message += f'...還有 {len(completed_todos) - 2} 項已完成\n'
            
            if current_time == user_settings['morning_time']:
                message += f'\n💪 新的一天開始了！加油完成這些任務！'
            else:
                message += f'\n🌙 檢查一下今天的進度吧！記得為明天做準備！'
                
            message += f'\n🇹🇼 台灣時間: {get_taiwan_time_hhmm()}'
            
            send_push_message(user_id, message)
            print(f"✅ 已發送每日提醒 ({len(pending_todos)} 項待辦) - 台灣時間: {get_taiwan_time()}")
        else:
            # 所有事項都已完成
            if current_time == user_settings['morning_time']:
                message = f'{time_icon} {time_text}！🎉 太棒了！目前沒有待辦事項\n💡 可以新增今天要做的事情'
            else:
                message = f'{time_icon} {time_text}！🎉 太棒了！今天的任務都完成了\n😴 好好休息，為明天準備新的目標！'
            
            message += f'\n🇹🇼 台灣時間: {get_taiwan_time_hhmm()}'
            send_push_message(user_id, message)
            print(f"✅ 已發送每日提醒 (無待辦事項) - 台灣時間: {get_taiwan_time()}")
    else:
        # 完全沒有任何事項
        if current_time == user_settings['morning_time']:
            message = f'{time_icon} {time_text}！✨ 新的一天開始了！\n💡 輸入「新增 事項名稱」來建立今天的目標'
        else:
            message = f'{time_icon} {time_text}！😌 今天過得如何？\n💡 別忘了為明天規劃一些目標'
        
        message += f'\n🇹🇼 台灣時間: {get_taiwan_time_hhmm()}'
        send_push_message(user_id, message)
        print(f"✅ 已發送每日提醒 (首次使用) - 台灣時間: {get_taiwan_time()}")

def check_monthly_preview(taiwan_now, user_id):
    """檢查明天的每月提醒 - 新增功能：前一天預告"""
    if not monthly_todos or not user_id:
        return
    
    tomorrow = taiwan_now + timedelta(days=1)
    tomorrow_day = tomorrow.day
    
    # 檢查明天是否有每月事項
    monthly_items_tomorrow = []
    for item in monthly_todos:
        target_day = item.get('day', 1)
        if target_day == tomorrow_day:
            monthly_items_tomorrow.append(item)
    
    if monthly_items_tomorrow:
        message = f"📅 每月提醒預告！\n\n明天 ({tomorrow.strftime('%m/%d')}) 有 {len(monthly_items_tomorrow)} 項每月固定事項：\n\n"
        
        for i, item in enumerate(monthly_items_tomorrow, 1):
            message += f"{i}. 🔄 {item['content']}\n"
        
        message += f"\n💡 明天早上會自動加入待辦清單並提醒您\n🇹🇼 台灣時間: {get_taiwan_time_hhmm()}"
        
        send_push_message(user_id, message)
        print(f"✅ 已發送每月預告提醒，明天有 {len(monthly_items_tomorrow)} 項事項 - 台灣時間: {get_taiwan_time()}")

def check_monthly_reminders(taiwan_now, user_id):
    """檢查每月提醒 - 改進版本：當天正式提醒"""
    if not monthly_todos or not user_id:
        return
    
    current_day = taiwan_now.day
    
    # 檢查是否有符合今天日期的每月事項
    monthly_items_today = []
    for item in monthly_todos:
        target_day = item.get('day', 1)
        if target_day == current_day:
            monthly_items_today.append(item)
    
    if monthly_items_today:
        # 自動將每月事項加入今日待辦
        added_items = []
        for item in monthly_items_today:
            # 檢查是否已經加入過（避免重複）
            already_exists = any(
                todo['content'] == item['content'] and 
                todo.get('created_at', '').startswith(taiwan_now.strftime('%Y/%m/%d'))
                for todo in todos
            )
            
            if not already_exists:
                todo_item = {
                    'id': len(todos) + 1,
                    'content': item['content'],
                    'created_at': get_taiwan_time(),
                    'completed': False,
                    'has_date': True,
                    'target_date': taiwan_now.strftime('%Y/%m/%d'),
                    'date_string': f"{taiwan_now.month}/{taiwan_now.day}",
                    'from_monthly': True
                }
                todos.append(todo_item)
                added_items.append(item['content'])
        
        if added_items:
            # 發送每月提醒
            message = f"🔄 每月提醒！今天 ({taiwan_now.strftime('%m/%d')}) 的固定事項：\n\n"
            for i, content in enumerate(added_items, 1):
                message += f"{i}. 📅 {content}\n"
            
            message += f"\n✅ 已自動加入今日待辦清單"
            message += f"\n💡 昨天已經預告過，現在正式提醒！"
            message += f"\n🇹🇼 台灣時間: {get_taiwan_time_hhmm()}"
            
            send_push_message(user_id, message)
            print(f"✅ 已發送每月正式提醒，加入 {len(added_items)} 項事項 - 台灣時間: {get_taiwan_time()}")

def check_short_reminders(taiwan_now):
    """檢查短期提醒"""
    for reminder in short_reminders[:]:
        reminder_time_str = reminder['reminder_time']
        try:
            if '+' in reminder_time_str or reminder_time_str.endswith('Z'):
                reminder_time = datetime.fromisoformat(reminder_time_str.replace('Z', '+00:00'))
                reminder_time = reminder_time.astimezone(TAIWAN_TZ)
            else:
                reminder_time = TAIWAN_TZ.localize(datetime.fromisoformat(reminder_time_str))
        except:
            print(f"⚠️ 無法解析提醒時間: {reminder_time_str}")
            short_reminders.remove(reminder)
            continue
        
        if reminder_time <= taiwan_now:
            user_id = reminder.get('user_id') or user_settings.get('user_id')
            if user_id:
                message = f"⏰ 短期提醒時間到！\n\n📋 {reminder['content']}\n🎯 該去執行了！\n🇹🇼 台灣時間: {get_taiwan_time_hhmm()}"
                send_push_message(user_id, message)
                print(f"✅ 已發送短期提醒: {reminder['content']} - 台灣時間: {get_taiwan_time()}")
            short_reminders.remove(reminder)

def check_time_reminders(taiwan_now):
    """檢查時間提醒"""
    for reminder in time_reminders[:]:
        reminder_time_str = reminder['reminder_time']
        try:
            if '+' in reminder_time_str or reminder_time_str.endswith('Z'):
                reminder_time = datetime.fromisoformat(reminder_time_str.replace('Z', '+00:00'))
                reminder_time = reminder_time.astimezone(TAIWAN_TZ)
            else:
                reminder_time = TAIWAN_TZ.localize(datetime.fromisoformat(reminder_time_str))
        except:
            print(f"⚠️ 無法解析提醒時間: {reminder_time_str}")
            time_reminders.remove(reminder)
            continue
            
        if reminder_time <= taiwan_now:
            user_id = reminder.get('user_id') or user_settings.get('user_id')
            if user_id:
                message = f"🕐 時間提醒！\n\n📋 {reminder['content']}\n⏰ {reminder['time_string']}\n🎯 該去執行了！\n🇹🇼 台灣時間: {get_taiwan_time_hhmm()}"
                send_push_message(user_id, message)
                print(f"✅ 已發送時間提醒: {reminder['content']} - 台灣時間: {get_taiwan_time()}")
            time_reminders.remove(reminder)

# 啟動提醒檢查執行緒
reminder_thread = threading.Thread(target=check_reminders, daemon=True)
reminder_thread.start()

# 防休眠機制
def keep_alive():
    """防休眠機制"""
    base_url = os.getenv('BASE_URL', 'https://line-bot-python-v2.onrender.com')
    
    while True:
        try:
            time.sleep(240)  # 4 分鐘
            response = requests.get(f'{base_url}/health', timeout=15)
            
            if response.status_code == 200:
                print(f"✅ Keep-alive 成功 - 台灣時間: {get_taiwan_time()}")
            else:
                print(f"⚠️ Keep-alive 警告: {response.status_code} - 台灣時間: {get_taiwan_time()}")
                
        except requests.exceptions.RequestException as e:
            print(f"❌ Keep-alive 錯誤: {e} - 台灣時間: {get_taiwan_time()}")
            time.sleep(60)
        except Exception as e:
            print(f"❌ Keep-alive 意外錯誤: {e} - 台灣時間: {get_taiwan_time()}")
            time.sleep(60)

keep_alive_thread = threading.Thread(target=keep_alive, daemon=True)
keep_alive_thread.start()

# ===== Flask 路由 =====
@app.route('/')
def home():
    return f'LINE Todo Reminder Bot v3.0 - 股票記帳功能已加入！當前台灣時間: {get_taiwan_time()}'

@app.route('/health')
def health():
    """健康檢查端點"""
    taiwan_now = get_taiwan_datetime()
    
    try:
        next_morning = taiwan_now.replace(
            hour=int(user_settings['morning_time'].split(':')[0]),
            minute=int(user_settings['morning_time'].split(':')[1]),
            second=0, microsecond=0
        )
        if next_morning <= taiwan_now:
            next_morning += timedelta(days=1)
        
        next_evening = taiwan_now.replace(
            hour=int(user_settings['evening_time'].split(':')[0]),
            minute=int(user_settings['evening_time'].split(':')[1]),
            second=0, microsecond=0
        )
        if next_evening <= taiwan_now:
            next_evening += timedelta(days=1)
        
        next_reminder = min(next_morning, next_evening)
        next_reminder_str = next_reminder.strftime('%Y/%m/%d %H:%M')
    except:
        next_reminder_str = "計算錯誤"
    
    return {
        'status': 'healthy',
        'taiwan_time': get_taiwan_time(),
        'taiwan_time_hhmm': get_taiwan_time_hhmm(),
        'server_timezone': str(taiwan_now.tzinfo),
        'todos_count': len(todos),
        'monthly_todos_count': len(monthly_todos),
        'short_reminders': len(short_reminders),
        'time_reminders': len(time_reminders),
        'stock_accounts_count': len(stock_data['accounts']),
        'stock_transactions_count': len(stock_data['transactions']),
        'morning_time': user_settings['morning_time'],
        'evening_time': user_settings['evening_time'],
        'next_reminder': next_reminder_str,
        'has_user': user_settings['user_id'] is not None,
        'version': '3.0_stock_trading'
    }

@app.route('/webhook', methods=['POST'])
def webhook():
    """LINE Webhook 處理"""
    try:
        data = request.get_json()
        
        for event in data.get('events', []):
            if event['type'] == 'message' and event['message']['type'] == 'text':
                reply_token = event['replyToken']
                message_text = event['message']['text'].strip()
                user_id = event['source']['userId']
                
                # 儲存用戶ID
                user_settings['user_id'] = user_id
                
                print(f"用戶訊息: {message_text} - 台灣時間: {get_taiwan_time()}")
                
                # === 股票功能路由 ===
                if any(keyword in message_text for keyword in ['買入', '賣出', '入帳', '提款', '新增帳戶']):
                    reply_text = handle_stock_command(message_text, user_id)
                
                # 股票查詢功能
                elif message_text == '總覽':
                    reply_text = get_all_accounts_summary()
                
                elif message_text.endswith('查詢'):
                    account_name = message_text[:-2].strip()  # 去掉「查詢」
                    if account_name in ['股票', '帳戶']:
                        reply_text = get_all_accounts_summary()
                    else:
                        reply_text = get_account_summary(account_name)
                
                elif message_text == '交易記錄':
                    reply_text = get_transaction_history()
                
                elif message_text.startswith('交易記錄 '):
                    account_name = message_text[5:].strip()
                    reply_text = get_transaction_history(account_name)
                
                elif message_text.startswith('成本查詢 ') and ' ' in message_text[5:]:
                    parts = message_text[5:].strip().split(' ', 1)
                    if len(parts) == 2:
                        account_name, stock_code = parts
                        reply_text = get_stock_cost_analysis(account_name, stock_code)
                    else:
                        reply_text = "❌ 格式不正確\n💡 例如：成本查詢 爸爸 2330 台積電"
                
                elif message_text == '帳戶列表':
                    if stock_data['accounts']:
                        account_list = list(stock_data['accounts'].keys())
                        reply_text = f"👥 目前帳戶列表：\n\n" + "\n".join([f"👤 {name}" for name in account_list])
                    else:
                        reply_text = "📝 目前沒有任何帳戶"
                
                elif message_text == '股票幫助':
                    reply_text = """💰 多帳戶股票記帳功能：

📋 帳戶管理：
- 爸爸入帳 50000 - 入金
- 媽媽提款 10000 - 提款  
- 新增帳戶 奶奶 - 建立帳戶

📈 交易操作：
- 爸爸買入 2330 台積電 100股 實付50000元 2024/08/20
- 媽媽賣出 2317 鴻海 50股 實收5000元 2024/08/21

📊 查詢功能：
- 總覽 - 所有帳戶總覽
- 爸爸查詢 - 個人資金和持股
- 交易記錄 - 所有交易歷史
- 交易記錄 爸爸 - 個人交易記錄
- 成本查詢 爸爸 2330 台積電 - 持股成本分析
- 帳戶列表 - 查看所有帳戶

💡 v3.0 新功能：完整的多帳戶股票記帳！"""

                # === 待辦事項功能路由 (保持原有邏輯) ===
                # 查詢時間
                elif message_text == '查詢時間':
                    reply_text = f"🇹🇼 台灣當前時間：{get_taiwan_time()}\n⏰ 目前提醒時間設定：\n🌅 早上：{user_settings['morning_time']}\n🌙 晚上：{user_settings['evening_time']}\n\n✅ 時區已修正為台灣時間！"

                # 設定提醒時間
                elif message_text.startswith('早上時間 '):
                    time_str = message_text[5:].strip()
                    if is_valid_time_format(time_str):
                        user_settings['morning_time'] = time_str
                        reply_text = f"🌅 已設定早上提醒時間為：{time_str}\n🇹🇼 台灣時間"
                    else:
                        reply_text = "❌ 時間格式不正確，請使用 HH:MM 格式，例如：08:30"

                elif message_text.startswith('晚上時間 '):
                    time_str = message_text[5:].strip()
                    if is_valid_time_format(time_str):
                        user_settings['evening_time'] = time_str
                        reply_text = f"🌙 已設定晚上提醒時間為：{time_str}\n🇹🇼 台灣時間"
                    else:
                        reply_text = "❌ 時間格式不正確，請使用 HH:MM 格式，例如：19:00"

                # 短期提醒
                elif any(keyword in message_text for keyword in ['分鐘後', '小時後', '秒後']):
                    parsed = parse_short_reminder(message_text)
                    if parsed['is_valid']:
                        taiwan_now = get_taiwan_datetime()
                        reminder_time = taiwan_now + timedelta(minutes=parsed['minutes'])
                        reminder_item = {
                            'id': len(short_reminders) + 1,
                            'user_id': user_id,
                            'content': parsed['content'],
                            'reminder_time': reminder_time.isoformat(),
                            'original_value': parsed['original_value'],
                            'unit': parsed['unit']
                        }
                        short_reminders.append(reminder_item)
                        
                        reply_text = f"⏰ 已設定短期提醒：「{parsed['content']}」\n⏳ {parsed['original_value']}{parsed['unit']}後提醒\n📅 提醒時間：{reminder_time.strftime('%H:%M')}\n🇹🇼 台灣時間"
                    else:
                        reply_text = f"❌ {parsed['error']}"

                # 時間提醒
                elif re.match(r'^\d{1,2}:\d{2}.+', message_text):
                    parsed = parse_time_reminder(message_text)
                    if parsed['is_valid']:
                        taiwan_now = get_taiwan_datetime()
                        target_time = taiwan_now.replace(
                            hour=parsed['hours'], 
                            minute=parsed['minutes'], 
                            second=0, 
                            microsecond=0
                        )
                        
                        if target_time <= taiwan_now:
                            target_time += timedelta(days=1)
                        
                        reminder_item = {
                            'id': len(time_reminders) + 1,
                            'user_id': user_id,
                            'content': parsed['content'],
                            'time_string': parsed['time_string'],
                            'reminder_time': target_time.isoformat()
                        }
                        time_reminders.append(reminder_item)
                        
                        date_text = '今天' if target_time.date() == taiwan_now.date() else '明天'
                        reply_text = f"🕐 已設定時間提醒：「{parsed['content']}」\n⏰ {date_text} {parsed['time_string']} 提醒\n🇹🇼 台灣時間"
                    else:
                        reply_text = f"❌ {parsed['error']}"

                # 幫助訊息
                elif message_text in ['幫助', 'help', '說明']:
                    reply_text = """📋 LINE Todo Bot v3.0 完整功能：

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

💰 股票記帳：
- 爸爸入帳 50000 - 入金
- 爸爸買入 2330 台積電 100股 實付50000元 2024/08/20
- 總覽 - 查看所有帳戶
- 股票幫助 - 股票功能詳細說明

🆕 v3.0 新功能：完整的多帳戶股票記帳系統！"""

                # 待辦事項功能
                elif message_text.startswith('新增 '):
                    todo_text = message_text[3:].strip()
                    if todo_text:
                        parsed = parse_date(todo_text)
                        todo_item = {
                            'id': len(todos) + 1,
                            'content': parsed['content'],
                            'created_at': get_taiwan_time(),
                            'completed': False,
                            'has_date': parsed.get('has_date', False),
                            'target_date': parsed.get('date').strftime('%Y/%m/%d') if parsed.get('date') else None,
                            'date_string': parsed.get('date_string')
                        }
                        todos.append(todo_item)
                        
                        if parsed.get('has_date'):
                            reply_text = f"✅ 已新增待辦事項：「{parsed['content']}」\n📅 目標日期：{parsed['date'].strftime('%Y/%m/%d')}\n📋 目前共有 {len(todos)} 項\n🇹🇼 台灣時間建立"
                        else:
                            reply_text = f"✅ 已新增待辦事項：「{parsed['content']}」\n📋 目前共有 {len(todos)} 項\n🇹🇼 台灣時間建立"
                    else:
                        reply_text = "❌ 請輸入要新增的事項內容"

                elif message_text in ['查詢', '清單']:
                    if todos:
                        reply_text = f"📋 待辦事項清單 ({len(todos)} 項)：\n\n"
                        for i, todo in enumerate(todos, 1):
                            status = "✅" if todo.get('completed') else "⭕"
                            date_info = f" 📅{todo.get('target_date', '')}" if todo.get('has_date') else ""
                            reply_text += f"{i}. {status} {todo['content']}{date_info}\n"
                        reply_text += "\n💡 輸入「幫助」查看更多功能"
                    else:
                        reply_text = "📝 目前沒有待辦事項"

                elif message_text.startswith('刪除 '):
                    try:
                        index = int(message_text[3:].strip()) - 1
                        if 0 <= index < len(todos):
                            deleted_todo = todos.pop(index)
                            reply_text = f"🗑️ 已刪除：「{deleted_todo['content']}」"
                        else:
                            reply_text = f"❌ 編號不正確"
                    except:
                        reply_text = "❌ 請輸入正確編號"

                elif message_text.startswith('完成 '):
                    try:
                        index = int(message_text[3:].strip()) - 1
                        if 0 <= index < len(todos):
                            todos[index]['completed'] = True
                            reply_text = f"🎉 已完成：「{todos[index]['content']}」"
                        else:
                            reply_text = f"❌ 編號不正確"
                    except:
                        reply_text = "❌ 請輸入正確編號"

                # 每月功能
                elif message_text.startswith('每月新增 '):
                    todo_text = message_text[5:].strip()
                    if todo_text:
                        parsed = parse_date(todo_text)
                        print(f"DEBUG: 解析結果: {parsed}")
                        
                        # 完全修正：更智能的日期處理
                        if parsed.get('has_date'):
                            if parsed.get('day_only'):
                                # 只有日期的情況，例如：24號繳水電卡費
                                day = parsed['day_only']
                                date_display = f"{day}號"
                            elif parsed.get('date_string'):
                                # 有月/日的情況，例如：8/24繳水電卡費
                                try:
                                    day = int(parsed['date_string'].split('/')[1])
                                    date_display = f"{day}號"
                                except:
                                    day = 1
                                    date_display = "1號"
                            else:
                                day = 1
                                date_display = "1號"
                        else:
                            # 沒有指定日期，例如：每月新增 買菜
                            day = 1
                            date_display = "1號"
                        
                        monthly_item = {
                            'id': len(monthly_todos) + 1,
                            'content': parsed['content'],
                            'created_at': get_taiwan_time(),
                            'has_date': parsed.get('has_date', False),
                            'date_string': parsed.get('date_string'),
                            'day': day,
                            'date_display': date_display
                        }
                        monthly_todos.append(monthly_item)
                        print(f"DEBUG: 新增的每月事項: {monthly_item}")
                        
                        reply_text = f"🔄 已新增每月事項：「{parsed['content']}」\n📅 每月 {date_display} 提醒\n📋 目前共有 {len(monthly_todos)} 項每月事項\n💡 會在前一天預告 + 當天提醒"
                    else:
                        reply_text = "❌ 請輸入要新增的每月事項內容\n💡 例如：每月新增 24號繳水電卡費"

                elif message_text == '每月清單':
                    if monthly_todos:
                        # 清理舊資料：為沒有 date_display 的項目補充
                        for item in monthly_todos:
                            if not item.get('date_display'):
                                if item.get('has_date') and item.get('date_string'):
                                    try:
                                        day = int(item['date_string'].split('/')[1])
                                        item['date_display'] = f"{day}號"
                                    except:
                                        item['date_display'] = f"{item.get('day', 1)}號"
                                else:
                                    item['date_display'] = f"{item.get('day', 1)}號"
                        
                        reply_text = f"🔄 每月固定事項清單 ({len(monthly_todos)} 項)：\n\n"
                        for i, item in enumerate(monthly_todos, 1):
                            date_display = item.get('date_display', f"{item.get('day', 1)}號")
                            reply_text += f"{i}. 📅 每月 {date_display} - {item['content']}\n"
                        reply_text += f"\n💡 這些事項會在前一天晚上預告，當天早上自動加入待辦清單"
                    else:
                        reply_text = "📝 目前沒有每月固定事項\n💡 輸入「每月新增 5號繳卡費」來新增"

                # 新增：清理每月資料的指令
                elif message_text == '清理每月':
                    if monthly_todos:
                        # 修正所有每月事項的顯示格式
                        fixed_count = 0
                        for item in monthly_todos:
                            if not item.get('date_display') or 'every month' in str(item.get('date_display', '')):
                                if item.get('has_date') and item.get('date_string'):
                                    try:
                                        day = int(item['date_string'].split('/')[1])
                                        item['date_display'] = f"{day}號"
                                        fixed_count += 1
                                    except:
                                        item['date_display'] = f"{item.get('day', 1)}號"
                                        fixed_count += 1
                                else:
                                    item['date_display'] = f"{item.get('day', 1)}號"
                                    fixed_count += 1
                        
                        reply_text = f"🔧 已修正 {fixed_count} 項每月事項的顯示格式\n💡 現在輸入「每月清單」查看修正結果"
                    else:
                        reply_text = "📝 目前沒有每月固定事項需要清理"

                # 測試功能
                elif message_text == '測試':
                    reply_text = f"✅ 機器人正常運作！\n🇹🇼 當前台灣時間：{get_taiwan_time()}\n⏰ 待辦提醒功能已啟用\n💰 股票記帳功能已啟用\n💡 輸入「幫助」或「股票幫助」查看功能"

                # 預設回應
                else:
                    reply_text = f"您說：{message_text}\n🇹🇼 當前台灣時間：{get_taiwan_time_hhmm()}\n\n💡 輸入「幫助」查看待辦功能\n💰 輸入「股票幫助」查看股票功能"
                
                # 發送回覆
                reply_message(reply_token, reply_text)
        
        return 'OK', 200
    
    except Exception as e:
        print(f"Webhook 處理錯誤: {e} - 台灣時間: {get_taiwan_time()}")
        return 'OK', 200

if __name__ == '__main__':
    print(f"🚀 LINE Bot v3.0 啟動 - 台灣時間: {get_taiwan_time()}")
    print(f"📋 待辦事項功能：已啟用")
    print(f"💰 股票記帳功能：已啟用")
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port), message_text):
        account, code, quantity, amount, date = match.groups()
        # 轉換日期格式
        year = datetime.now().year
        month = int(date[:2])
        day = int(date[2:])
        formatted_date = f"{year}/{month:02d}/{day:02d}"
        
        # 查找股票名稱
        stock_names = {
            '2330': '台積電', '2317': '鴻海', '2454': '聯發科', '2308': '台達電',
            '2382': '廣達', '3711': '日月光', '2303': '聯電', '2881': '富邦金',
            '2412': '中華電', '1303': '南亞', '1301': '台塑', '2886': '兆豐金'
        }
        stock_name = stock_names.get(code, '未知股票')
        
        return {
            'type': 'sell',
            'account': account.strip(),
            'stock_code': f"{code} {stock_name}",
            'quantity': int(quantity),
            'amount': int(amount),
            'date': formatted_date
        }
    
    # 新增帳戶：新增帳戶 奶奶 (保持原格式，較少使用)
    elif match := re.match(r'新增帳戶\s*(.+)', message_text):
        account = match.group(1).strip()
        return {
            'type': 'create_account',
            'account': account
        }
    
    # === 舊格式兼容（向下相容）===
    # 入帳：爸爸入帳 50000
    elif match := re.match(r'(.+?)入帳\s*(\d+)', message_text):
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
    
    return None

def handle_stock_deposit(account_name, amount):
    """處理入帳"""
    is_new = get_or_create_account(account_name)
    stock_data['accounts'][account_name]['cash'] += amount
    
    # 記錄交易
    transaction = {
        'id': len(stock_data['transactions']) + 1,
        'type': '入帳',
        'account': account_name,
        'stock_code': None,
        'quantity': 0,
        'amount': amount,
        'price_per_share': 0,
        'date': get_taiwan_time().split(' ')[0],
        'cash_after': stock_data['accounts'][account_name]['cash'],
        'created_at': get_taiwan_time()
    }
    stock_data['transactions'].append(transaction)
    
    result_msg = f"💰 {account_name} 入帳成功！\n"
    if is_new:
        result_msg += f"🆕 已建立新帳戶\n"
    result_msg += f"💵 入帳金額：{amount:,}元\n"
    result_msg += f"💳 帳戶餘額：{stock_data['accounts'][account_name]['cash']:,}元"
    
    return result_msg

def handle_stock_withdraw(account_name, amount):
    """處理提款"""
    if account_name not in stock_data['accounts']:
        return f"❌ 帳戶「{account_name}」不存在"
    
    account = stock_data['accounts'][account_name]
    if account['cash'] < amount:
        return f"❌ 餘額不足！\n💳 目前餘額：{account['cash']:,}元\n💸 提款金額：{amount:,}元"
    
    account['cash'] -= amount
    
    # 記錄交易
    transaction = {
        'id': len(stock_data['transactions']) + 1,
        'type': '提款',
        'account': account_name,
        'stock_code': None,
        'quantity': 0,
        'amount': amount,
        'price_per_share': 0,
        'date': get_taiwan_time().split(' ')[0],
        'cash_after': account['cash'],
        'created_at': get_taiwan_time()
    }
    stock_data['transactions'].append(transaction)
    
    return f"💸 {account_name} 提款成功！\n💵 提款金額：{amount:,}元\n💳 帳戶餘額：{account['cash']:,}元"

def handle_stock_buy(account_name, stock_code, quantity, amount, date):
    """處理買入股票"""
    if account_name not in stock_data['accounts']:
        return f"❌ 帳戶「{account_name}」不存在"
    
    account = stock_data['accounts'][account_name]
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
        'id': len(stock_data['transactions']) + 1,
        'type': '買入',
        'account': account_name,
        'stock_code': stock_code,
        'quantity': quantity,
        'amount': amount,
        'price_per_share': price_per_share,
        'date': date,
        'cash_after': account['cash'],
        'created_at': get_taiwan_time()
    }
    stock_data['transactions'].append(transaction)
    
    stock_info = account['stocks'][stock_code]
    return f"📈 {account_name} 買入成功！\n\n🏷️ {stock_code}\n📊 買入：{quantity}股 @ {price_per_share}元\n💰 實付：{amount:,}元\n📅 日期：{date}\n\n📋 持股狀況：\n📊 總持股：{stock_info['quantity']}股\n💵 平均成本：{stock_info['avg_cost']}元/股\n💳 剩餘現金：{account['cash']:,}元"

def handle_stock_sell(account_name, stock_code, quantity, amount, date):
    """處理賣出股票"""
    if account_name not in stock_data['accounts']:
        return f"❌ 帳戶「{account_name}」不存在"
    
    account = stock_data['accounts'][account_name]
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
        'id': len(stock_data['transactions']) + 1,
        'type': '賣出',
        'account': account_name,
        'stock_code': stock_code,
        'quantity': quantity,
        'amount': amount,
        'price_per_share': price_per_share,
        'date': date,
        'cash_after': account['cash'],
        'created_at': get_taiwan_time(),
        'profit_loss': profit_loss
    }
    stock_data['transactions'].append(transaction)
    
    profit_text = f"💰 獲利：+{profit_loss:,}元" if profit_loss > 0 else f"💸 虧損：{profit_loss:,}元" if profit_loss < 0 else "💫 損益兩平"
    
    result = f"📉 {account_name} 賣出成功！\n\n🏷️ {stock_code}\n📊 賣出：{quantity}股 @ {price_per_share}元\n💰 實收：{amount:,}元\n📅 日期：{date}\n\n💹 本次交易：\n💵 成本：{sell_cost:,}元\n{profit_text}\n💳 現金餘額：{account['cash']:,}元"
    
    if remaining_quantity > 0:
        result += f"\n\n📋 剩餘持股：{remaining_quantity}股"
    else:
        result += f"\n\n✅ 已全部賣出 {stock_code}"
    
    return result

def get_account_summary(account_name):
    """獲取帳戶摘要"""
    if account_name not in stock_data['accounts']:
        return f"❌ 帳戶「{account_name}」不存在"
    
    account = stock_data['accounts'][account_name]
    
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

def get_all_accounts_summary():
    """獲取所有帳戶總覽"""
    if not stock_data['accounts']:
        return "📝 目前沒有任何帳戶\n💡 輸入「爸爸入帳 100000」來建立第一個帳戶"
    
    result = "🏦 家庭投資總覽：\n\n"
    
    total_cash = 0
    total_investment = 0
    all_stocks = {}
    
    for account_name, account in stock_data['accounts'].items():
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

def get_transaction_history(account_name=None, limit=10):
    """獲取交易記錄"""
    transactions = stock_data['transactions']
    
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

def get_stock_cost_analysis(account_name, stock_code):
    """獲取特定股票的成本分析"""
    if account_name not in stock_data['accounts']:
        return f"❌ 帳戶「{account_name}」不存在"
    
    account = stock_data['accounts'][account_name]
    if stock_code not in account['stocks']:
        return f"❌ {account_name} 沒有持有「{stock_code}」"
    
    holding = account['stocks'][stock_code]
    
    # 查找相關交易記錄
    related_transactions = [
        t for t in stock_data['transactions'] 
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

def handle_stock_command(message_text, user_id):
    """處理股票相關指令"""
    parsed = parse_stock_command(message_text)
    
    if not parsed:
        return "❌ 指令格式不正確\n💡 輸入「股票幫助」查看使用說明"
    
    try:
        if parsed['type'] == 'deposit':
            return handle_stock_deposit(parsed['account'], parsed['amount'])
        
        elif parsed['type'] == 'withdraw':
            return handle_stock_withdraw(parsed['account'], parsed['amount'])
        
        elif parsed['type'] == 'buy':
            return handle_stock_buy(
                parsed['account'], parsed['stock_code'], 
                parsed['quantity'], parsed['amount'], parsed['date']
            )
        
        elif parsed['type'] == 'sell':
            return handle_stock_sell(
                parsed['account'], parsed['stock_code'], 
                parsed['quantity'], parsed['amount'], parsed['date']
            )
        
        elif parsed['type'] == 'create_account':
            is_new = get_or_create_account(parsed['account'])
            if is_new:
                return f"🆕 已建立帳戶「{parsed['account']}」\n💡 可以開始入帳和交易了！"
            else:
                return f"ℹ️ 帳戶「{parsed['account']}」已存在"
        
    except Exception as e:
        return f"❌ 處理失敗：{str(e)}\n💡 請檢查指令格式"
    
    return "❌ 未知的指令類型"

# ===== 待辦事項功能函數 (保持原有) =====
def parse_date(text):
    """解析日期格式 - 改進版本，更好地處理每月事項"""
    taiwan_now = get_taiwan_datetime()
    current_year = taiwan_now.year
    
    # 改進的日期模式，更靈活地匹配
    patterns = [
        # 格式：24號繳水電卡費
        (r'(\d{1,2})號(.+)', 'day_only'),
        # 格式：8/24繳水電卡費 或 8/24號繳水電卡費
        (r'(\d{1,2})\/(\d{1,2})號?(.+)', 'month_day'),
        # 格式：繳水電卡費24號
        (r'(.+?)(\d{1,2})號', 'content_day'),
        # 格式：繳水電卡費8/24
        (r'(.+?)(\d{1,2})\/(\d{1,2})號?', 'content_month_day')
    ]
    
    for pattern, pattern_type in patterns:
        match = re.search(pattern, text)
        if match:
            print(f"DEBUG: 匹配到模式 {pattern_type}: {match.groups()}")
            
            if pattern_type == 'day_only':
                # 24號繳水電卡費
                day = int(match.group(1))
                content = match.group(2).strip()
                if 1 <= day <= 31 and content:
                    # 使用當前月份
                    month = taiwan_now.month
                    target_date = taiwan_now.replace(year=current_year, month=month, day=day,
                                                   hour=0, minute=0, second=0, microsecond=0)
                    if target_date < taiwan_now:
                        if month == 12:
                            target_date = target_date.replace(year=current_year + 1, month=1)
                        else:
                            target_date = target_date.replace(month=month + 1)
                    
                    return {
                        "has_date": True,
                        "date": target_date,
                        "content": content,
                        "date_string": f"{month}/{day}",
                        "day_only": day  # 新增：只有日期的情況
                    }
                    
            elif pattern_type == 'month_day':
                # 8/24繳水電卡費
                month = int(match.group(1))
                day = int(match.group(2))
                content = match.group(3).strip()
                
                if 1 <= month <= 12 and 1 <= day <= 31 and content:
                    target_date = taiwan_now.replace(year=current_year, month=month, day=day,
                                                   hour=0, minute=0, second=0, microsecond=0)
                    if target_date < taiwan_now:
                        target_date = target_date.replace(year=current_year + 1)
                    
                    return {
                        "has_date": True,
                        "date": target_date,
                        "content": content,
                        "date_string": f"{month}/{day}"
                    }
                    
            elif pattern_type == 'content_day':
                # 繳水電卡費24號
                content = match.group(1).strip()
                day = int(match.group(2))
                
                if 1 <= day <= 31 and content:
                    month = taiwan_now.month
                    target_date = taiwan_now.replace(year=current_year, month=month, day=day,
                                                   hour=0, minute=0, second=0, microsecond=0)
                    if target_date < taiwan_now:
                        if month == 12:
                            target_date = target_date.replace(year=current_year + 1, month=1)
                        else:
                            target_date = target_date.replace(month=month + 1)
                    
                    return {
                        "has_date": True,
                        "date": target_date,
                        "content": content,
                        "date_string": f"{month}/{day}",
                        "day_only": day
                    }
                    
            elif pattern_type == 'content_month_day':
                # 繳水電卡費8/24
                content = match.group(1).strip()
                month = int(match.group(2))
                day = int(match.group(3))
                
                if 1 <= month <= 12 and 1 <= day <= 31 and content:
                    target_date = taiwan_now.replace(year=current_year, month=month, day=day,
                                                   hour=0, minute=0, second=0, microsecond=0)
                    if target_date < taiwan_now:
                        target_date = target_date.replace(year=current_year + 1)
                    
                    return {
                        "has_date": True,
                        "date": target_date,
                        "content": content,
                        "date_string": f"{month}/{day}"
                    }
    
    print(f"DEBUG: 沒有匹配到任何日期模式，原文: {text}")
    return {"has_date": False, "content": text}

def parse_short_reminder(text):
    """解析短期提醒"""
    patterns = [
        (r'(\d+)分鐘後(.+)', '分鐘', 1),
        (r'(\d+)小時後(.+)', '小時', 60),
        (r'(\d+)秒後(.+)', '秒', 1/60)
    ]
    
    for pattern, unit, multiplier in patterns:
        match = re.search(pattern, text)
        if match:
            value = int(match.group(1))
            content = match.group(2).strip()
            
            if not content:
                return {"is_valid": False, "error": "請輸入提醒內容"}
            
            minutes = value * multiplier
            
            if unit == '分鐘' and not (1 <= value <= 1440):
                return {"is_valid": False, "error": "分鐘數請設定在 1-1440 之間"}
            elif unit == '小時' and not (1 <= value <= 24):
                return {"is_valid": False, "error": "小時數請設定在 1-24 之間"}
            elif unit == '秒' and not (10 <= value <= 3600):
                return {"is_valid": False, "error": "秒數請設定在 10-3600 之間"}
            
            return {
                "is_valid": True,
                "minutes": minutes,
                "original_value": value,
                "unit": unit,
                "content": content
            }
    
    return {"is_valid": False, "error": "格式不正確，請使用：數字+時間單位+後+內容\n例如：5分鐘後倒垃圾"}

def parse_time_reminder(text):
    """解析時間提醒"""
    time_pattern = r'(\d{1,2}):(\d{2})(.+)'
    match = re.search(time_pattern, text)
    
    if match:
        hours = int(match.group(1))
        minutes = int(match.group(2))
        content = match.group(3).strip()
        
        if not content:
            return {"is_valid": False, "error": "請輸入提醒內容"}
        
        if not (0 <= hours <= 23):
            return {"is_valid": False, "error": "小時請設定在 0-23 之間"}
        
        if not (0 <= minutes <= 59):
            return {"is_valid": False, "error": "分鐘請設定在 0-59 之間"}
        
        return {
            "is_valid": True,
            "hours": hours,
            "minutes": minutes,
            "time_string": f"{hours:02d}:{minutes:02d}",
            "content": content
        }
    
    return {"is_valid": False, "error": "格式不正確，請使用：HH:MM+內容\n例如：12:00倒垃圾"}

# ===== LINE API 函數 =====
def send_push_message(user_id, message_text):
    """發送推播訊息"""
    if not CHANNEL_ACCESS_TOKEN or not user_id:
        print(f"模擬推播給 {user_id}: {message_text} (台灣時間: {get_taiwan_time()})")
        return False
    
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {CHANNEL_ACCESS_TOKEN}'
    }
    
    data = {
        'to': user_id,
        'messages': [{
            'type': 'text',
            'text': message_text
        }]
    }
    
    try:
        response = requests.post(PUSH_API_URL, headers=headers, data=json.dumps(data))
        print(f"推播發送 - 狀態碼: {response.status_code} - 台灣時間: {get_taiwan_time()}")
        return response.status_code == 200
    except Exception as e:
        print(f"推播失敗: {e} - 台灣時間: {get_taiwan_time()}")
        return False

def reply_message(reply_token, message_text):
    """回覆訊息"""
    if not CHANNEL_ACCESS_TOKEN:
        print(f"模擬回覆: {message_text} (台灣時間: {get_taiwan_time()})")
        return False
    
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {CHANNEL_ACCESS_TOKEN}'
    }
    
    data = {
        'replyToken': reply_token,
        'messages': [{
            'type': 'text',
            'text': message_text
        }]
    }
    
    try:
        response = requests.post(LINE_API_URL, headers=headers, data=json.dumps(data))
        return response.status_code == 200
    except Exception as e:
        print(f"回覆失敗: {e} - 台灣時間: {get_taiwan_time()}")
        return False

# ===== 提醒系統函數 =====
def check_reminders():
    """檢查並發送提醒 - 改進版本"""
    while True:
        try:
            current_time = get_taiwan_time_hhmm()
            user_id = user_settings.get('user_id')
            taiwan_now = get_taiwan_datetime()
            
            print(f"🔍 提醒檢查 - 台灣時間: {get_taiwan_time()}")
            
            # 檢查定時提醒（每日早晚） - 改進：每次都提醒所有待辦事項
            if user_id and (current_time == user_settings['morning_time'] or current_time == user_settings['evening_time']):
                send_daily_reminder(user_id, current_time)
            
            # 檢查每月提醒 - 改進：前一天預告 + 當天提醒
            if current_time == user_settings['evening_time']:  # 晚上檢查明天的每月事項
                check_monthly_preview(taiwan_now, user_id)
            
            if current_time == "09:00":  # 早上檢查今天的每月事項
                check_monthly_reminders(taiwan_now, user_id)
            
            # 檢查短期提醒
            check_short_reminders(taiwan_now)
            
            # 檢查時間提醒
            check_time_reminders(taiwan_now)
            
            time.sleep(60)  # 每分鐘檢查一次
        except Exception as e:
            print(f"提醒檢查錯誤: {e} - 台灣時間: {get_taiwan_time()}")
            time.sleep(60)

def send_daily_reminder(user_id, current_time):
    """發送每日提醒 - 改進版本：每次都提醒所有待辦事項"""
    time_icon = '🌅' if current_time == user_settings['morning_time'] else '🌙'
    time_text = '早安' if current_time == user_settings['morning_time'] else '晚安'
    
    if todos:
        # 分類待辦事項
        pending_todos = [todo for todo in todos if not todo.get('completed', False)]
        completed_todos = [todo for todo in todos if todo.get('completed', False)]
        
        if pending_todos:
            message = f'{time_icon} {time_text}！您有 {len(pending_todos)} 項待辦事項：\n\n'
            
            # 顯示未完成的事項（最多5項）
            for i, todo in enumerate(pending_todos[:5], 1):
                date_info = f" 📅{todo.get('target_date', '')}" if todo.get('has_date') else ""
                message += f'{i}. ⭕ {todo["content"]}{date_info}\n'
            
            if len(pending_todos) > 5:
                message += f'\n...還有 {len(pending_todos) - 5} 項未完成\n'
            
            # 如果有已完成的事項，也顯示（最多2項）
            if completed_todos:
                message += f'\n✅ 已完成 {len(completed_todos)} 項：\n'
                for todo in completed_todos[:2]:
                    message += f'✅ {todo["content"]}\n'
                if len(completed_todos) > 2:
                    message += f'...還有 {len(completed_todos) - 2} 項已完成\n'
            
            if current_time == user_settings['morning_time']:
                message += f'\n💪 新的一天開始了！加油完成這些任務！'
            else:
                message += f'\n🌙 檢查一下今天的進度吧！記得為明天做準備！'
                
            message += f'\n🇹🇼 台灣時間: {get_taiwan_time_hhmm()}'
            
            send_push_message(user_id, message)
            print(f"✅ 已發送每日提醒 ({len(pending_todos)} 項待辦) - 台灣時間: {get_taiwan_time()}")
        else:
            # 所有事項都已完成
            if current_time == user_settings['morning_time']:
                message = f'{time_icon} {time_text}！🎉 太棒了！目前沒有待辦事項\n💡 可以新增今天要做的事情'
            else:
                message = f'{time_icon} {time_text}！🎉 太棒了！今天的任務都完成了\n😴 好好休息，為明天準備新的目標！'
            
            message += f'\n🇹🇼 台灣時間: {get_taiwan_time_hhmm()}'
            send_push_message(user_id, message)
            print(f"✅ 已發送每日提醒 (無待辦事項) - 台灣時間: {get_taiwan_time()}")
    else:
        # 完全沒有任何事項
        if current_time == user_settings['morning_time']:
            message = f'{time_icon} {time_text}！✨ 新的一天開始了！\n💡 輸入「新增 事項名稱」來建立今天的目標'
        else:
            message = f'{time_icon} {time_text}！😌 今天過得如何？\n💡 別忘了為明天規劃一些目標'
        
        message += f'\n🇹🇼 台灣時間: {get_taiwan_time_hhmm()}'
        send_push_message(user_id, message)
        print(f"✅ 已發送每日提醒 (首次使用) - 台灣時間: {get_taiwan_time()}")

def check_monthly_preview(taiwan_now, user_id):
    """檢查明天的每月提醒 - 新增功能：前一天預告"""
    if not monthly_todos or not user_id:
        return
    
    tomorrow = taiwan_now + timedelta(days=1)
    tomorrow_day = tomorrow.day
    
    # 檢查明天是否有每月事項
    monthly_items_tomorrow = []
    for item in monthly_todos:
        target_day = item.get('day', 1)
        if target_day == tomorrow_day:
            monthly_items_tomorrow.append(item)
    
    if monthly_items_tomorrow:
        message = f"📅 每月提醒預告！\n\n明天 ({tomorrow.strftime('%m/%d')}) 有 {len(monthly_items_tomorrow)} 項每月固定事項：\n\n"
        
        for i, item in enumerate(monthly_items_tomorrow, 1):
            message += f"{i}. 🔄 {item['content']}\n"
        
        message += f"\n💡 明天早上會自動加入待辦清單並提醒您\n🇹🇼 台灣時間: {get_taiwan_time_hhmm()}"
        
        send_push_message(user_id, message)
        print(f"✅ 已發送每月預告提醒，明天有 {len(monthly_items_tomorrow)} 項事項 - 台灣時間: {get_taiwan_time()}")

def check_monthly_reminders(taiwan_now, user_id):
    """檢查每月提醒 - 改進版本：當天正式提醒"""
    if not monthly_todos or not user_id:
        return
    
    current_day = taiwan_now.day
    
    # 檢查是否有符合今天日期的每月事項
    monthly_items_today = []
    for item in monthly_todos:
        target_day = item.get('day', 1)
        if target_day == current_day:
            monthly_items_today.append(item)
    
    if monthly_items_today:
        # 自動將每月事項加入今日待辦
        added_items = []
        for item in monthly_items_today:
            # 檢查是否已經加入過（避免重複）
            already_exists = any(
                todo['content'] == item['content'] and 
                todo.get('created_at', '').startswith(taiwan_now.strftime('%Y/%m/%d'))
                for todo in todos
            )
            
            if not already_exists:
                todo_item = {
                    'id': len(todos) + 1,
                    'content': item['content'],
                    'created_at': get_taiwan_time(),
                    'completed': False,
                    'has_date': True,
                    'target_date': taiwan_now.strftime('%Y/%m/%d'),
                    'date_string': f"{taiwan_now.month}/{taiwan_now.day}",
                    'from_monthly': True
                }
                todos.append(todo_item)
                added_items.append(item['content'])
        
        if added_items:
            # 發送每月提醒
            message = f"🔄 每月提醒！今天 ({taiwan_now.strftime('%m/%d')}) 的固定事項：\n\n"
            for i, content in enumerate(added_items, 1):
                message += f"{i}. 📅 {content}\n"
            
            message += f"\n✅ 已自動加入今日待辦清單"
            message += f"\n💡 昨天已經預告過，現在正式提醒！"
            message += f"\n🇹🇼 台灣時間: {get_taiwan_time_hhmm()}"
            
            send_push_message(user_id, message)
            print(f"✅ 已發送每月正式提醒，加入 {len(added_items)} 項事項 - 台灣時間: {get_taiwan_time()}")

def check_short_reminders(taiwan_now):
    """檢查短期提醒"""
    for reminder in short_reminders[:]:
        reminder_time_str = reminder['reminder_time']
        try:
            if '+' in reminder_time_str or reminder_time_str.endswith('Z'):
                reminder_time = datetime.fromisoformat(reminder_time_str.replace('Z', '+00:00'))
                reminder_time = reminder_time.astimezone(TAIWAN_TZ)
            else:
                reminder_time = TAIWAN_TZ.localize(datetime.fromisoformat(reminder_time_str))
        except:
            print(f"⚠️ 無法解析提醒時間: {reminder_time_str}")
            short_reminders.remove(reminder)
            continue
        
        if reminder_time <= taiwan_now:
            user_id = reminder.get('user_id') or user_settings.get('user_id')
            if user_id:
                message = f"⏰ 短期提醒時間到！\n\n📋 {reminder['content']}\n🎯 該去執行了！\n🇹🇼 台灣時間: {get_taiwan_time_hhmm()}"
                send_push_message(user_id, message)
                print(f"✅ 已發送短期提醒: {reminder['content']} - 台灣時間: {get_taiwan_time()}")
            short_reminders.remove(reminder)

def check_time_reminders(taiwan_now):
    """檢查時間提醒"""
    for reminder in time_reminders[:]:
        reminder_time_str = reminder['reminder_time']
        try:
            if '+' in reminder_time_str or reminder_time_str.endswith('Z'):
                reminder_time = datetime.fromisoformat(reminder_time_str.replace('Z', '+00:00'))
                reminder_time = reminder_time.astimezone(TAIWAN_TZ)
            else:
                reminder_time = TAIWAN_TZ.localize(datetime.fromisoformat(reminder_time_str))
        except:
            print(f"⚠️ 無法解析提醒時間: {reminder_time_str}")
            time_reminders.remove(reminder)
            continue
            
        if reminder_time <= taiwan_now:
            user_id = reminder.get('user_id') or user_settings.get('user_id')
            if user_id:
                message = f"🕐 時間提醒！\n\n📋 {reminder['content']}\n⏰ {reminder['time_string']}\n🎯 該去執行了！\n🇹🇼 台灣時間: {get_taiwan_time_hhmm()}"
                send_push_message(user_id, message)
                print(f"✅ 已發送時間提醒: {reminder['content']} - 台灣時間: {get_taiwan_time()}")
            time_reminders.remove(reminder)

# 啟動提醒檢查執行緒
reminder_thread = threading.Thread(target=check_reminders, daemon=True)
reminder_thread.start()

# 防休眠機制
def keep_alive():
    """防休眠機制"""
    base_url = os.getenv('BASE_URL', 'https://line-bot-python-v2.onrender.com')
    
    while True:
        try:
            time.sleep(240)  # 4 分鐘
            response = requests.get(f'{base_url}/health', timeout=15)
            
            if response.status_code == 200:
                print(f"✅ Keep-alive 成功 - 台灣時間: {get_taiwan_time()}")
            else:
                print(f"⚠️ Keep-alive 警告: {response.status_code} - 台灣時間: {get_taiwan_time()}")
                
        except requests.exceptions.RequestException as e:
            print(f"❌ Keep-alive 錯誤: {e} - 台灣時間: {get_taiwan_time()}")
            time.sleep(60)
        except Exception as e:
            print(f"❌ Keep-alive 意外錯誤: {e} - 台灣時間: {get_taiwan_time()}")
            time.sleep(60)

keep_alive_thread = threading.Thread(target=keep_alive, daemon=True)
keep_alive_thread.start()

# ===== Flask 路由 =====
@app.route('/')
def home():
    return f'LINE Todo Reminder Bot v3.0 - 股票記帳功能已加入！當前台灣時間: {get_taiwan_time()}'

@app.route('/health')
def health():
    """健康檢查端點"""
    taiwan_now = get_taiwan_datetime()
    
    try:
        next_morning = taiwan_now.replace(
            hour=int(user_settings['morning_time'].split(':')[0]),
            minute=int(user_settings['morning_time'].split(':')[1]),
            second=0, microsecond=0
        )
        if next_morning <= taiwan_now:
            next_morning += timedelta(days=1)
        
        next_evening = taiwan_now.replace(
            hour=int(user_settings['evening_time'].split(':')[0]),
            minute=int(user_settings['evening_time'].split(':')[1]),
            second=0, microsecond=0
        )
        if next_evening <= taiwan_now:
            next_evening += timedelta(days=1)
        
        next_reminder = min(next_morning, next_evening)
        next_reminder_str = next_reminder.strftime('%Y/%m/%d %H:%M')
    except:
        next_reminder_str = "計算錯誤"
    
    return {
        'status': 'healthy',
        'taiwan_time': get_taiwan_time(),
        'taiwan_time_hhmm': get_taiwan_time_hhmm(),
        'server_timezone': str(taiwan_now.tzinfo),
        'todos_count': len(todos),
        'monthly_todos_count': len(monthly_todos),
        'short_reminders': len(short_reminders),
        'time_reminders': len(time_reminders),
        'stock_accounts_count': len(stock_data['accounts']),
        'stock_transactions_count': len(stock_data['transactions']),
        'morning_time': user_settings['morning_time'],
        'evening_time': user_settings['evening_time'],
        'next_reminder': next_reminder_str,
        'has_user': user_settings['user_id'] is not None,
        'version': '3.0_stock_trading'
    }

@app.route('/webhook', methods=['POST'])
def webhook():
    """LINE Webhook 處理"""
    try:
        data = request.get_json()
        
        for event in data.get('events', []):
            if event['type'] == 'message' and event['message']['type'] == 'text':
                reply_token = event['replyToken']
                message_text = event['message']['text'].strip()
                user_id = event['source']['userId']
                
                # 儲存用戶ID
                user_settings['user_id'] = user_id
                
                print(f"用戶訊息: {message_text} - 台灣時間: {get_taiwan_time()}")
                
                # === 股票功能路由 ===
                if any(keyword in message_text for keyword in ['買入', '賣出', '入帳', '提款', '新增帳戶']):
                    reply_text = handle_stock_command(message_text, user_id)
                
                # 股票查詢功能
                elif message_text == '總覽':
                    reply_text = get_all_accounts_summary()
                
                elif message_text.endswith('查詢'):
                    account_name = message_text[:-2].strip()  # 去掉「查詢」
                    if account_name in ['股票', '帳戶']:
                        reply_text = get_all_accounts_summary()
                    else:
                        reply_text = get_account_summary(account_name)
                
                elif message_text == '交易記錄':
                    reply_text = get_transaction_history()
                
                elif message_text.startswith('交易記錄 '):
                    account_name = message_text[5:].strip()
                    reply_text = get_transaction_history(account_name)
                
                elif message_text.startswith('成本查詢 ') and ' ' in message_text[5:]:
                    parts = message_text[5:].strip().split(' ', 1)
                    if len(parts) == 2:
                        account_name, stock_code = parts
                        reply_text = get_stock_cost_analysis(account_name, stock_code)
                    else:
                        reply_text = "❌ 格式不正確\n💡 例如：成本查詢 爸爸 2330 台積電"
                
                elif message_text == '帳戶列表':
                    if stock_data['accounts']:
                        account_list = list(stock_data['accounts'].keys())
                        reply_text = f"👥 目前帳戶列表：\n\n" + "\n".join([f"👤 {name}" for name in account_list])
                    else:
                        reply_text = "📝 目前沒有任何帳戶"
                
                elif message_text == '股票幫助':
                    reply_text = """💰 多帳戶股票記帳功能：

📋 帳戶管理：
- 爸爸入帳 50000 - 入金
- 媽媽提款 10000 - 提款  
- 新增帳戶 奶奶 - 建立帳戶

📈 交易操作：
- 爸爸買入 2330 台積電 100股 實付50000元 2024/08/20
- 媽媽賣出 2317 鴻海 50股 實收5000元 2024/08/21

📊 查詢功能：
- 總覽 - 所有帳戶總覽
- 爸爸查詢 - 個人資金和持股
- 交易記錄 - 所有交易歷史
- 交易記錄 爸爸 - 個人交易記錄
- 成本查詢 爸爸 2330 台積電 - 持股成本分析
- 帳戶列表 - 查看所有帳戶

💡 v3.0 新功能：完整的多帳戶股票記帳！"""

                # === 待辦事項功能路由 (保持原有邏輯) ===
                # 查詢時間
                elif message_text == '查詢時間':
                    reply_text = f"🇹🇼 台灣當前時間：{get_taiwan_time()}\n⏰ 目前提醒時間設定：\n🌅 早上：{user_settings['morning_time']}\n🌙 晚上：{user_settings['evening_time']}\n\n✅ 時區已修正為台灣時間！"

                # 設定提醒時間
                elif message_text.startswith('早上時間 '):
                    time_str = message_text[5:].strip()
                    if is_valid_time_format(time_str):
                        user_settings['morning_time'] = time_str
                        reply_text = f"🌅 已設定早上提醒時間為：{time_str}\n🇹🇼 台灣時間"
                    else:
                        reply_text = "❌ 時間格式不正確，請使用 HH:MM 格式，例如：08:30"

                elif message_text.startswith('晚上時間 '):
                    time_str = message_text[5:].strip()
                    if is_valid_time_format(time_str):
                        user_settings['evening_time'] = time_str
                        reply_text = f"🌙 已設定晚上提醒時間為：{time_str}\n🇹🇼 台灣時間"
                    else:
                        reply_text = "❌ 時間格式不正確，請使用 HH:MM 格式，例如：19:00"

                # 短期提醒
                elif any(keyword in message_text for keyword in ['分鐘後', '小時後', '秒後']):
                    parsed = parse_short_reminder(message_text)
                    if parsed['is_valid']:
                        taiwan_now = get_taiwan_datetime()
                        reminder_time = taiwan_now + timedelta(minutes=parsed['minutes'])
                        reminder_item = {
                            'id': len(short_reminders) + 1,
                            'user_id': user_id,
                            'content': parsed['content'],
                            'reminder_time': reminder_time.isoformat(),
                            'original_value': parsed['original_value'],
                            'unit': parsed['unit']
                        }
                        short_reminders.append(reminder_item)
                        
                        reply_text = f"⏰ 已設定短期提醒：「{parsed['content']}」\n⏳ {parsed['original_value']}{parsed['unit']}後提醒\n📅 提醒時間：{reminder_time.strftime('%H:%M')}\n🇹🇼 台灣時間"
                    else:
                        reply_text = f"❌ {parsed['error']}"

                # 時間提醒
                elif re.match(r'^\d{1,2}:\d{2}.+', message_text):
                    parsed = parse_time_reminder(message_text)
                    if parsed['is_valid']:
                        taiwan_now = get_taiwan_datetime()
                        target_time = taiwan_now.replace(
                            hour=parsed['hours'], 
                            minute=parsed['minutes'], 
                            second=0, 
                            microsecond=0
                        )
                        
                        if target_time <= taiwan_now:
                            target_time += timedelta(days=1)
                        
                        reminder_item = {
                            'id': len(time_reminders) + 1,
                            'user_id': user_id,
                            'content': parsed['content'],
                            'time_string': parsed['time_string'],
                            'reminder_time': target_time.isoformat()
                        }
                        time_reminders.append(reminder_item)
                        
                        date_text = '今天' if target_time.date() == taiwan_now.date() else '明天'
                        reply_text = f"🕐 已設定時間提醒：「{parsed['content']}」\n⏰ {date_text} {parsed['time_string']} 提醒\n🇹🇼 台灣時間"
                    else:
                        reply_text = f"❌ {parsed['error']}"

                # 幫助訊息
                elif message_text in ['幫助', 'help', '說明']:
                    reply_text = """📋 LINE Todo Bot v3.0 完整功能：

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

💰 股票記帳：
- 爸爸入帳 50000 - 入金
- 爸爸買入 2330 台積電 100股 實付50000元 2024/08/20
- 總覽 - 查看所有帳戶
- 股票幫助 - 股票功能詳細說明

🆕 v3.0 新功能：完整的多帳戶股票記帳系統！"""

                # 待辦事項功能
                elif message_text.startswith('新增 '):
                    todo_text = message_text[3:].strip()
                    if todo_text:
                        parsed = parse_date(todo_text)
                        todo_item = {
                            'id': len(todos) + 1,
                            'content': parsed['content'],
                            'created_at': get_taiwan_time(),
                            'completed': False,
                            'has_date': parsed.get('has_date', False),
                            'target_date': parsed.get('date').strftime('%Y/%m/%d') if parsed.get('date') else None,
                            'date_string': parsed.get('date_string')
                        }
                        todos.append(todo_item)
                        
                        if parsed.get('has_date'):
                            reply_text = f"✅ 已新增待辦事項：「{parsed['content']}」\n📅 目標日期：{parsed['date'].strftime('%Y/%m/%d')}\n📋 目前共有 {len(todos)} 項\n🇹🇼 台灣時間建立"
                        else:
                            reply_text = f"✅ 已新增待辦事項：「{parsed['content']}」\n📋 目前共有 {len(todos)} 項\n🇹🇼 台灣時間建立"
                    else:
                        reply_text = "❌ 請輸入要新增的事項內容"

                elif message_text in ['查詢', '清單']:
                    if todos:
                        reply_text = f"📋 待辦事項清單 ({len(todos)} 項)：\n\n"
                        for i, todo in enumerate(todos, 1):
                            status = "✅" if todo.get('completed') else "⭕"
                            date_info = f" 📅{todo.get('target_date', '')}" if todo.get('has_date') else ""
                            reply_text += f"{i}. {status} {todo['content']}{date_info}\n"
                        reply_text += "\n💡 輸入「幫助」查看更多功能"
                    else:
                        reply_text = "📝 目前沒有待辦事項"

                elif message_text.startswith('刪除 '):
                    try:
                        index = int(message_text[3:].strip()) - 1
                        if 0 <= index < len(todos):
                            deleted_todo = todos.pop(index)
                            reply_text = f"🗑️ 已刪除：「{deleted_todo['content']}」"
                        else:
                            reply_text = f"❌ 編號不正確"
                    except:
                        reply_text = "❌ 請輸入正確編號"

                elif message_text.startswith('完成 '):
                    try:
                        index = int(message_text[3:].strip()) - 1
                        if 0 <= index < len(todos):
                            todos[index]['completed'] = True
                            reply_text = f"🎉 已完成：「{todos[index]['content']}」"
                        else:
                            reply_text = f"❌ 編號不正確"
                    except:
                        reply_text = "❌ 請輸入正確編號"

                # 每月功能
                elif message_text.startswith('每月新增 '):
                    todo_text = message_text[5:].strip()
                    if todo_text:
                        parsed = parse_date(todo_text)
                        print(f"DEBUG: 解析結果: {parsed}")
                        
                        # 完全修正：更智能的日期處理
                        if parsed.get('has_date'):
                            if parsed.get('day_only'):
                                # 只有日期的情況，例如：24號繳水電卡費
                                day = parsed['day_only']
                                date_display = f"{day}號"
                            elif parsed.get('date_string'):
                                # 有月/日的情況，例如：8/24繳水電卡費
                                try:
                                    day = int(parsed['date_string'].split('/')[1])
                                    date_display = f"{day}號"
                                except:
                                    day = 1
                                    date_display = "1號"
                            else:
                                day = 1
                                date_display = "1號"
                        else:
                            # 沒有指定日期，例如：每月新增 買菜
                            day = 1
                            date_display = "1號"
                        
                        monthly_item = {
                            'id': len(monthly_todos) + 1,
                            'content': parsed['content'],
                            'created_at': get_taiwan_time(),
                            'has_date': parsed.get('has_date', False),
                            'date_string': parsed.get('date_string'),
                            'day': day,
                            'date_display': date_display
                        }
                        monthly_todos.append(monthly_item)
                        print(f"DEBUG: 新增的每月事項: {monthly_item}")
                        
                        reply_text = f"🔄 已新增每月事項：「{parsed['content']}」\n📅 每月 {date_display} 提醒\n📋 目前共有 {len(monthly_todos)} 項每月事項\n💡 會在前一天預告 + 當天提醒"
                    else:
                        reply_text = "❌ 請輸入要新增的每月事項內容\n💡 例如：每月新增 24號繳水電卡費"

                elif message_text == '每月清單':
                    if monthly_todos:
                        # 清理舊資料：為沒有 date_display 的項目補充
                        for item in monthly_todos:
                            if not item.get('date_display'):
                                if item.get('has_date') and item.get('date_string'):
                                    try:
                                        day = int(item['date_string'].split('/')[1])
                                        item['date_display'] = f"{day}號"
                                    except:
                                        item['date_display'] = f"{item.get('day', 1)}號"
                                else:
                                    item['date_display'] = f"{item.get('day', 1)}號"
                        
                        reply_text = f"🔄 每月固定事項清單 ({len(monthly_todos)} 項)：\n\n"
                        for i, item in enumerate(monthly_todos, 1):
                            date_display = item.get('date_display', f"{item.get('day', 1)}號")
                            reply_text += f"{i}. 📅 每月 {date_display} - {item['content']}\n"
                        reply_text += f"\n💡 這些事項會在前一天晚上預告，當天早上自動加入待辦清單"
                    else:
                        reply_text = "📝 目前沒有每月固定事項\n💡 輸入「每月新增 5號繳卡費」來新增"

                # 新增：清理每月資料的指令
                elif message_text == '清理每月':
                    if monthly_todos:
                        # 修正所有每月事項的顯示格式
                        fixed_count = 0
                        for item in monthly_todos:
                            if not item.get('date_display') or 'every month' in str(item.get('date_display', '')):
                                if item.get('has_date') and item.get('date_string'):
                                    try:
                                        day = int(item['date_string'].split('/')[1])
                                        item['date_display'] = f"{day}號"
                                        fixed_count += 1
                                    except:
                                        item['date_display'] = f"{item.get('day', 1)}號"
                                        fixed_count += 1
                                else:
                                    item['date_display'] = f"{item.get('day', 1)}號"
                                    fixed_count += 1
                        
                        reply_text = f"🔧 已修正 {fixed_count} 項每月事項的顯示格式\n💡 現在輸入「每月清單」查看修正結果"
                    else:
                        reply_text = "📝 目前沒有每月固定事項需要清理"

                # 測試功能
                elif message_text == '測試':
                    reply_text = f"✅ 機器人正常運作！\n🇹🇼 當前台灣時間：{get_taiwan_time()}\n⏰ 待辦提醒功能已啟用\n💰 股票記帳功能已啟用\n💡 輸入「幫助」或「股票幫助」查看功能"

                # 預設回應
                else:
                    reply_text = f"您說：{message_text}\n🇹🇼 當前台灣時間：{get_taiwan_time_hhmm()}\n\n💡 輸入「幫助」查看待辦功能\n💰 輸入「股票幫助」查看股票功能"
                
                # 發送回覆
                reply_message(reply_token, reply_text)
        
        return 'OK', 200
    
    except Exception as e:
        print(f"Webhook 處理錯誤: {e} - 台灣時間: {get_taiwan_time()}")
        return 'OK', 200

if __name__ == '__main__':
    print(f"🚀 LINE Bot v3.0 啟動 - 台灣時間: {get_taiwan_time()}")
    print(f"📋 待辦事項功能：已啟用")
    print(f"💰 股票記帳功能：已啟用")
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port)
