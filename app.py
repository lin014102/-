"""
LINE Todo Reminder Bot - 簡化版本
"""
from flask import Flask, request, jsonify
import os

app = Flask(__name__)

# 簡單的記憶體儲存
todos = []

@app.route('/')
def home():
    return 'LINE Todo Reminder Bot v2.0 is running!'

@app.route('/health')
def health():
    return {
        'status': 'ok',
        'webhook_ready': True,
        'todos_count': len(todos)
    }

@app.route('/webhook', methods=['POST'])
def webhook():
    """LINE Webhook 處理"""
    try:
        print("收到 Webhook 請求")
        
        # 獲取資料
        data = request.get_json()
        
        # 處理訊息事件
        for event in data.get('events', []):
            if event['type'] == 'message' and event['message']['type'] == 'text':
                reply_token = event['replyToken']
                message_text = event['message']['text']
                user_id = event['source']['userId']
                
                print(f"收到訊息: {message_text}")
                
                # 簡單的回覆處理
                if message_text == '測試':
                    reply_text = "測試成功！機器人正常運作！"
                elif message_text.startswith('新增 '):
                    content = message_text[3:].strip()
                    todos.append({'content': content, 'id': len(todos) + 1})
                    reply_text = f"已新增：{content}\n目前共有 {len(todos)} 項"
                elif message_text == '查詢':
                    if todos:
                        reply_text = "📋 待辦事項：\n" + "\n".join([f"{i+1}. {todo['content']}" for i, todo in enumerate(todos)])
                    else:
                        reply_text = "目前沒有待辦事項"
                else:
                    reply_text = f"您說：{message_text}\n\n可用指令：\n• 測試\n• 新增 [事項]\n• 查詢"
                
                # 模擬回覆（因為沒有 LINE SDK）
                print(f"回覆: {reply_text}")
        
        return 'OK', 200
    
    except Exception as e:
        print(f"Webhook 處理錯誤: {e}")
        return 'OK', 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port)
