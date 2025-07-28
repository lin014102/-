from apscheduler.schedulers.background import BackgroundScheduler
from linebot.models import TextSendMessage

def schedule_daily_reminder(line_bot_api, user_id):
    def send_reminder():
        from db import get_todos
        todos = get_todos(user_id)
        msg = "🔔 每日提醒：\n" + "\n".join(f"- {t}" for t in todos) if todos else "✨ 今天沒有代辦事項，輕鬆一下！"
        line_bot_api.push_message(user_id, TextSendMessage(text=msg))

    scheduler = BackgroundScheduler()
    scheduler.add_job(send_reminder, 'cron', hour=8, minute=30)
    scheduler.start()
