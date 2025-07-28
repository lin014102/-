from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from dotenv import load_dotenv
import os
from db import add_todo, remove_todo, get_todos
from scheduler import schedule_daily_reminder

load_dotenv()
app = Flask(__name__)

line_bot_api = LineBotApi(os.getenv("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("LINE_CHANNEL_SECRET"))

schedule_daily_reminder(line_bot_api, os.getenv("YOUR_USER_ID"))

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except Exception as e:
        print(f"Error: {e}")
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    text = event.message.text.strip()
    user_id = event.source.user_id

    if text.startswith("新增 "):
        item = text[3:]
        add_todo(user_id, item)
        reply = f"✅ 已新增：{item}"
    elif text.startswith("刪除 "):
        item = text[3:]
        remove_todo(user_id, item)
        reply = f"🗑️ 已刪除：{item}"
    elif text == "查詢":
        todos = get_todos(user_id)
        reply = "📝 你的代辦事項：\n" + "\n".join(f"- {t}" for t in todos) if todos else "✨ 沒有代辦事項～"
    else:
        reply = "請輸入：\n➡ 新增 xxx\n➡ 刪除 xxx\n➡ 查詢"

    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
    @handler.add(FollowEvent)
def handle_follow(event):
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text="👋 歡迎使用代辦提醒機器人！\n輸入：\n➡ 新增 xxx\n➡ 查詢\n➡ 刪除 xxx")
    )

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=10000)
