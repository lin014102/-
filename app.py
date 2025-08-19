"""
LINE Todo Reminder Bot - 模組化版本
"""
from flask import Flask, request, jsonify
import os

# 測試模組導入
try:
    from config.settings import settings
    from utils.date_utils import get_taiwan_time
    print("模組導入成功！")
except ImportError as e:
    print(f"模組導入失敗: {e}")
    # 備用方案
    class Settings:
        APP_NAME = "LINE Todo Reminder Bot"
        VERSION = "2.0.0"
        PORT = int(os.getenv('PORT', 8000))
        HOST = '0.0.0.0'
    settings = Settings()
    
    from datetime import datetime
    def get_taiwan_time():
        return datetime.now().strftime('%Y/%m/%d %H:%M:%S')

app = Flask(__name__)

@app.route('/')
def home():
    return f'{settings.APP_NAME} v{settings.VERSION} is running!'

@app.route('/health')
def health():
    return {
        'status': 'ok',
        'time': get_taiwan_time(),
        'app': settings.APP_NAME
    }

if __name__ == '__main__':
    app.run(host=settings.HOST, port=settings.PORT)
