"""
LINE Todo Reminder Bot - 完整回覆版本
"""
from flask import Flask, request, jsonify
import os
import requests
import json

app = Flask(__name__)

# 簡單的記憶體儲存
todos = []

# LINE Bot 設定
CHANNEL_ACCESS_TOKEN = os.getenv('CHANNEL_ACCESS_TOKEN', '')
LINE_API_URL = 'https://api.line.me/v2/bot/message/reply'

def reply_message(reply_token, message_text):
    """發送回覆訊息"""
    if not CHANNEL_ACCESS_TOKEN:
        print(f"模擬回覆: {message_text}")
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
        print(f"LINE API 回應: {response.status_code}")
        return response.status_code == 200
    except Exception as e:
        print(f"發送訊息失敗: {e}")
        return False

@app.route('/')
def home():
    return 'LINE Todo Reminder Bot v2.0 is running!'

@app.route('/health')
def health():
    return {
        'status': 'ok',
        'webhook_ready': True,
        'todos_count': len(todos),
        'token_configured': bool(CHANNEL_ACCESS_TOKEN)
    }

@app.route('/webhook', methods=['POST'])
def webhook():
    """LINE Webhook 處理"""
    try:
        print("=== 收到 Webhook 請求 ===")
        
        # 獲取資料
        data = request.get_json()
        print(f"收到資料: {data}")
        
        # 處理訊息事件
        for event in data.get('events', []):
            print(f"處理事件: {event['type']}")
            
            if event['type'] == 'message' and event['message']['type'] == 'text':
                reply_token = event['replyToken']
                message_text = event['message']['text']
                user_id = event['source']['userId']
                
                print(f"用戶 {user_id} 說: {message_text}")
                
                # 處理訊息
                if message_text == '測試':
                    reply_text = "✅ 測試成功！機器人正常運作！"
                elif message_text.startswith('新增 '):
                    content = message_text[3:].strip()
                    if content:
                        todos.append({'content': content, 'id': len(todos) + 1})
                        reply_text = f"✅ 已新增：{content}\n📋 目前共有 {len(todos)} 項待辦事項"
                    else:
                        reply_text = "❌ 請輸入要新增的事項內容"
                elif message_text == '查詢':
                    if todos:
                        reply_text = "📋 您的待辦事項：\n\n"
                        for i, todo in enumerate(todos, 1):
                            reply_text += f"{i}. {todo['content']}\n"
                    else:
                        reply_text = "📝 目前沒有待辦事項\n輸入「新增 [事項]」來新增"
                else:
                    reply_text = f"您說：{message_text}\n\n💡 可用指令：\n• 測試\n• 新增 [事項]\n• 查詢"
                
                # 發送回覆
                success = reply_message(reply_token, reply_text)
                print(f"回覆發送結果: {success}")
        
        return 'OK', 200
    
    except Exception as e:
        print(f"Webhook 處理錯誤: {e}")
        return 'OK', 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port)
