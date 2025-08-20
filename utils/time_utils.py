"""
time_utils.py - 時間相關工具函數
從 app.py 拆分出來
"""
from datetime import datetime
import pytz

# 設定台灣時區
TAIWAN_TZ = pytz.timezone('Asia/Taipei')

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
