import sqlite3
from datetime import datetime, timedelta

conn = sqlite3.connect('todo.db', check_same_thread=False)
cursor = conn.cursor()
cursor.execute('CREATE TABLE IF NOT EXISTS todos (user TEXT, item TEXT, remind_at TEXT)')
conn.commit()

def add_todo(user, item):
    try:
        date_part, content = item.split(" ", 1)
        due = datetime.strptime(date_part, "%m/%d").replace(year=datetime.now().year)
        remind_time = due - timedelta(days=1)
        remind_time = remind_time.replace(hour=14, minute=30)
    except:
        content = item
        remind_time = None

    cursor.execute("INSERT INTO todos (user, item, remind_at) VALUES (?, ?, ?)", (user, content, remind_time.isoformat() if remind_time else None))
    conn.commit()

def get_todos(user):
    cursor.execute("SELECT item FROM todos WHERE user=?", (user,))
    return [row[0] for row in cursor.fetchall()]

def remove_todo(user, item):
    cursor.execute("DELETE FROM todos WHERE user=? AND item=?", (user, item))
    conn.commit()

def get_all_reminders():
    cursor.execute("SELECT user, item, remind_at FROM todos WHERE remind_at IS NOT NULL")
    return cursor.fetchall()
