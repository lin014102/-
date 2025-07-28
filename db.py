import sqlite3

def get_conn():
    return sqlite3.connect('todo.db', check_same_thread=False)

conn = get_conn()
cursor = conn.cursor()
cursor.execute('CREATE TABLE IF NOT EXISTS todos (user TEXT, item TEXT)')
conn.commit()

def add_todo(user, item):
    cursor.execute('INSERT INTO todos (user, item) VALUES (?, ?)', (user, item))
    conn.commit()

def remove_todo(user, item):
    cursor.execute('DELETE FROM todos WHERE user=? AND item=?', (user, item))
    conn.commit()

def get_todos(user):
    cursor.execute('SELECT item FROM todos WHERE user=?', (user,))
    return [row[0] for row in cursor.fetchall()]
