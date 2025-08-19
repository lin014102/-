"""
日期和時間相關工具函數
"""
from datetime import datetime

def get_taiwan_time():
    """獲取台灣時間字串"""
    return datetime.now().strftime('%Y/%m/%d %H:%M:%S')

def get_taiwan_time_hhmm():
    """獲取台灣時間 HH:MM 格式"""
    return datetime.now().strftime('%H:%M')
