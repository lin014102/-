# 使用最簡單的 Flask
from flask import Flask
import os

app = Flask(__name__)

@app.route('/')
def home():
    return 'LINE Bot is running!'

@app.route('/health')
def health():
    return {'status': 'ok'}

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port)
