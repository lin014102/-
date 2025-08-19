from flask import Flask, request, jsonify
import os

app = Flask(__name__)

@app.route('/')
def home():
    return 'LINE Bot is running!'

@app.route('/health')
def health():
    return {'status': 'ok'}

@app.route("/webhook", methods=['POST'])
def webhook():
    # 暫時只是接收 webhook，不處理
    return 'OK'

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port)
