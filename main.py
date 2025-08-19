from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import os

app = Flask(__name__)

# LINE Bot 設定 (暫時用假的值)
line_bot_api = LineBotApi('your_channel_access_token')
handler = WebhookHandler('your_channel_secret')

@app.route('/')
def home():
    return 'LINE Bot is running!'

@app.route('/health')
def health():
    return {'status': 'ok'}

@app.route("/webhook", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    # 簡單的回音功能
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text="你說：" + event.message.text)
    )

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port)
