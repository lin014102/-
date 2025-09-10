# news_bot.py
import os
import requests
import threading
import time
from datetime import datetime
from utils.time_utils import get_taiwan_time
from utils.line_api import send_push_message

class NewsBot:
    def __init__(self):
        self.token = os.getenv('NEWS_BOT_TOKEN')
        self.last_news_id = None
        self.user_id = None  # 設定推播對象
        self.news_thread = None
        self.is_running = False
        
    def set_user_id(self, user_id):
        """設定要推播的用戶ID"""
        self.user_id = user_id
        print(f"已設定新聞推播用戶: {user_id}")
        
    def fetch_cnyes_news(self):
        """抓取鉅亨網新聞"""
        try:
            url = "https://api.cnyes.com/media/api/v1/newslist/category/headline"
            params = {
                'limit': 10,
                'page': 1
            }
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = requests.get(url, params=params, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if 'items' in data and 'data' in data['items']:
                    news_list = data['items']['data']
                    print(f"成功抓取 {len(news_list)} 則新聞 - {get_taiwan_time()}")
                    return news_list
                else:
                    print(f"新聞數據格式異常 - {get_taiwan_time()}")
                    return []
            else:
                print(f"抓取新聞失敗，狀態碼: {response.status_code} - {get_taiwan_time()}")
                return []
                
        except Exception as e:
            print(f"抓取新聞發生錯誤: {e} - {get_taiwan_time()}")
            return []
    
    def check_new_news(self):
        """檢查是否有新新聞"""
        news_list = self.fetch_cnyes_news()
        
        if not news_list:
            return None
            
        # 取得最新的新聞
        latest_news = news_list[0]
        latest_news_id = latest_news.get('newsId')
        
        # 如果是第一次執行，記錄當前最新新聞ID但不推播
        if self.last_news_id is None:
            self.last_news_id = latest_news_id
            print(f"初始化完成，記錄最新新聞ID: {latest_news_id} - {get_taiwan_time()}")
            return None
        
        # 檢查是否有新新聞
        if latest_news_id != self.last_news_id:
            print(f"發現新新聞: {latest_news_id} - {get_taiwan_time()}")
            self.last_news_id = latest_news_id
            return latest_news
        
        return None
    
    def format_news_message(self, news_data):
        """格式化新聞訊息"""
        try:
            title = news_data.get('title', '無標題')
            summary = news_data.get('summary', '').strip()
            news_id = news_data.get('newsId', '')
            publish_time = news_data.get('publishAt', '')
            
            # 格式化發布時間
            if publish_time:
                try:
                    # 假設時間格式是timestamp
                    if isinstance(publish_time, (int, float)):
                        publish_dt = datetime.fromtimestamp(publish_time)
                        formatted_time = publish_dt.strftime('%H:%M')
                    else:
                        # 如果是字串格式，嘗試解析
                        formatted_time = str(publish_time)[:5]  # 簡單截取前5字符
                except:
                    formatted_time = "未知時間"
            else:
                formatted_time = "未知時間"
            
            # 構建訊息
            message = f"📰 財經即時新聞\n\n"
            message += f"📌 {title}\n\n"
            
            if summary:
                # 限制摘要長度
                if len(summary) > 100:
                    summary = summary[:100] + "..."
                message += f"📄 {summary}\n\n"
            
            message += f"🕐 {formatted_time}\n"
            message += f"📰 來源：鉅亨網\n"
            message += f"🔗 新聞ID：{news_id}"
            
            return message
            
        except Exception as e:
            print(f"格式化新聞訊息失敗: {e}")
            return "新聞格式化失敗"
    
    def send_news_notification(self, news_data):
        """發送新聞推播"""
        if not self.user_id:
            print("未設定推播用戶ID")
            return False
            
        message = self.format_news_message(news_data)
        success = send_push_message(self.user_id, message, bot_type='news')
        
        if success:
            print(f"新聞推播成功 - {get_taiwan_time()}")
        else:
            print(f"新聞推播失敗 - {get_taiwan_time()}")
            
        return success
    
    def news_check_loop(self):
        """新聞檢查循環"""
        print(f"新聞檢查循環開始 - {get_taiwan_time()}")
        
        while self.is_running:
            try:
                new_news = self.check_new_news()
                
                if new_news:
                    title = new_news.get('title', '無標題')
                    print(f"發現新新聞: {title} - {get_taiwan_time()}")
                    self.send_news_notification(new_news)
                
                # 每5分鐘檢查一次
                time.sleep(300)
                
            except Exception as e:
                print(f"新聞檢查循環錯誤: {e} - {get_taiwan_time()}")
                time.sleep(60)  # 發生錯誤時等待1分鐘再重試
    
    def start_news_monitoring(self, user_id):
        """開始新聞監控"""
        self.set_user_id(user_id)
        
        if self.news_thread and self.news_thread.is_alive():
            print("新聞監控已在運行中")
            return "新聞監控已在運行中"
        
        self.is_running = True
        self.news_thread = threading.Thread(target=self.news_check_loop, daemon=True)
        self.news_thread.start()
        
        return f"✅ 新聞監控已啟動\n📰 每5分鐘檢查鉅亨網最新財經新聞\n🔔 有新新聞時將自動推播\n🕐 {get_taiwan_time()}"
    
    def stop_news_monitoring(self):
        """停止新聞監控"""
        self.is_running = False
        return f"⏹️ 新聞監控已停止\n🕐 {get_taiwan_time()}"
    
    def get_news_status(self):
        """獲取新聞監控狀態"""
        status = "運行中" if self.is_running else "已停止"
        user_info = f"推播對象: {self.user_id}" if self.user_id else "未設定推播對象"
        last_news_info = f"最後新聞ID: {self.last_news_id}" if self.last_news_id else "尚未抓取過新聞"
        
        return f"📊 新聞監控狀態\n\n🔄 狀態: {status}\n👤 {user_info}\n📰 {last_news_info}\n🕐 {get_taiwan_time()}"
    
    def send_test_message(self, user_id):
        """發送測試訊息"""
        url = 'https://api.line.me/v2/bot/message/push'
        headers = {
            'Authorization': f'Bearer {self.token}',
            'Content-Type': 'application/json'
        }
        
        data = {
            'to': user_id,
            'messages': [{
                'type': 'text',
                'text': f'新聞機器人測試 - {datetime.now().strftime("%Y-%m-%d %H:%M")}'
            }]
        }
        
        response = requests.post(url, headers=headers, json=data)
        return response.status_code == 200
