# news_bot.py
import os
import requests
from datetime import datetime

class NewsBot:
    def __init__(self):
        self.token = os.getenv('NEWS_BOT_TOKEN')
        
    def send_test_message(self, user_id):
        url = 'https://api.line.me/v2/bot/message/push'
        headers = {
            'Authorization': f'Bearer {self.token}',
            'Content-Type': 'application/json'
        }
        
        data = {
            'to': user_id,
            'messages': [{
                'type': 'text',
                'text': f'新聞機器人測試 - {datetime.now().strftime("%Y-%m-%d %H:%M")}'
            }]
        }
        
        response = requests.post(url, headers=headers, json=data)
        return response.status_code == 200
