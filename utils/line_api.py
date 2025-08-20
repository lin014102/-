"""
line_api.py - LINE API 相關工具函數
從 app.py 拆分出來
"""
import os
import requests
import json
from .time_utils import get_taiwan_time

# LINE Bot 設定
CHANNEL_ACCESS_TOKEN = os.getenv('CHANNEL_ACCESS_TOKEN', '')
LINE_API_URL = 'https://api.line.me/v2/bot/message/reply'
PUSH_API_URL = 'https://api.line.me/v2/bot/message/push'

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
