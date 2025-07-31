from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger
from db import get_all_reminders
from datetime import datetime

def schedule_all_reminders(line_bot_api):
    scheduler = BackgroundScheduler()
    scheduler.start()

    for user, item, remind_time in get_all_reminders():
        if remind_time:
            dt = datetime.fromisoformat(remind_time)
            if dt > datetime.now():
                scheduler.add_job(
                    lambda u=user, i=item: line_bot_api.push_message(u, TextSendMessage(text=f"⏰ 提醒：{i}")),
                    trigger=DateTrigger(run_date=dt),
                    id=f"{user}_{item}_{dt}"
                )

from linebot.models import TextSendMessage
