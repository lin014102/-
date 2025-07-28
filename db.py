import sqlite3

def get_conn():
    return sqlite3.connect('todo.db', check_same_thread=False)

conn = get_conn()
cursor = conn.cursor()

# ✅ 改為三欄：user, item, date
cursor.execute('CREATE TABLE IF NOT EXISTS todos (user TEXT, item TEXT, date TEXT)')
conn.commit()

def add_todo(user, item, date=None):  # ✅ 可選的日期欄位
    cursor.execute('INSERT INTO todos (user, item, date) VALUES (?, ?, ?)', (user, item, date))
    conn.commit()

def remove_todo(user, item):
    cursor.execute('DELETE FROM todos WHERE user=? AND item=?', (user, item))
    conn.commit()

def get_todos(user):
    cursor.execute('SELECT item FROM todos WHERE user=? AND date IS NULL', (user,))
    return [row[0] for row in cursor.fetchall()]

# ✅ 取得所有有指定日期的事項（提醒用）
def get_all_todos_with_date(user):
    cursor.execute('SELECT item, date FROM todos WHERE user=? AND date IS NOT NULL', (user,))
    return cursor.fetchall()

