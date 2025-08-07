# app.py
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from dotenv import load_dotenv
import os
from db import add_todo, remove_todo, get_todos, add_reminder
from scheduler import schedule_all_reminders, add_single_reminder
from datetime import datetime, timedelta

load_dotenv()
app = Flask(__name__)

line_bot_api = LineBotApi(os.getenv("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("LINE_CHANNEL_SECRET"))

# 啟動時排入所有提醒
schedule_all_reminders(line_bot_api)

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

    if text.startswith("新增 ") and " " in text[3:]:
        # 格式：新增 7/14 繳卡費
        try:
            parts = text[3:].split(" ", 1)
            date_str, item = parts[0], parts[1]
            task_date = datetime.strptime(date_str, "%m/%d")
            now = datetime.now()
            # 加入今年作為完整時間
            task_datetime = datetime(year=now.year, month=task_date.month, day=task_date.day)
            # 前一天 14:30 通知
            remind_time = task_datetime - timedelta(days=1)
            remind_time = remind_time.replace(hour=14, minute=30)

            add_todo(user_id, item)
            add_reminder(user_id, item, remind_time.isoformat())
            add_single_reminder(line_bot_api, user_id, item, remind_time)

            reply = f"✅ 已新增：{item}（將於 {remind_time.strftime('%m/%d %H:%M')} 提醒）"
        except Exception as e:
            print("日期解析錯誤：", e)
            reply = "⚠️ 新增格式錯誤，請使用：新增 月/日 事項（例如：新增 7/14 繳卡費）"

    elif text.startswith("刪除 "):
        item = text[3:]
        remove_todo(user_id, item)
        reply = f"🗑️ 已刪除：{item}"
    elif text == "查詢":
        todos = get_todos(user_id)
        reply = "📝 你的代辦事項：\n" + "\n".join(f"- {t}" for t in todos) if todos else "✨ 沒有代辦事項～"
    else:
        reply = "請輸入：\n➡ 新增 月/日 事項\n➡ 刪除 xxx\n➡ 查詢"

    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=10000)

