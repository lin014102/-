"""
LINE Bot 服務
"""
import requests
import json
import hmac
import hashlib
import base64

class LineService:
    """LINE Bot 服務類"""
    
    def __init__(self, channel_access_token, channel_secret):
        self.channel_access_token = channel_access_token
        self.channel_secret = channel_secret
        self.line_api_url = 'https://api.line.me/v2/bot/message/reply'
    
    def verify_signature(self, body, signature):
        """驗證 LINE 簽名"""
        if not self.channel_secret:
            return True  # 開發模式下跳過驗證
        
        hash = hmac.new(
            self.channel_secret.encode('utf-8'),
            body.encode('utf-8'), 
            hashlib.sha256
        ).digest()
        expected_signature = base64.b64encode(hash).decode('utf-8')
        
        return signature == expected_signature
    
    def reply_message(self, reply_token, message_text):
        """回覆訊息"""
        if not self.channel_access_token:
            print(f"模擬回覆: {message_text}")
            return True
        
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.channel_access_token}'
        }
        
        data = {
            'replyToken': reply_token,
            'messages': [{
                'type': 'text',
                'text': message_text
            }]
        }
        
        try:
            response = requests.post(self.line_api_url, headers=headers, data=json.dumps(data))
            return response.status_code == 200
        except Exception as e:
            print(f"發送訊息失敗: {e}")
            return False

# 全域實例（暫時用空的 token）
line_service = LineService("", "")
