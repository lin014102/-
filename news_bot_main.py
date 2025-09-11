# news_bot.py - 完整正確版本
import os
import requests
import threading
import time
from datetime import datetime, time as dt_time
from utils.time_utils import get_taiwan_time, get_taiwan_datetime
from utils.line_api import send_push_message

class NewsBot:
    def __init__(self):
        self.token = os.getenv('NEWS_BOT_TOKEN')
        self.last_news_id = None
        self.last_check_time = None
        self.user_id = None
        self.news_thread = None
        self.is_running = False
        
        # 設定選項
        self.check_interval = 300
        self.news_category = 'headline'
        self.start_time = dt_time(9, 0)
        self.end_time = dt_time(21, 0)
        self.weekend_enabled = False
        
    def set_user_id(self, user_id):
        """設定要推播的用戶ID"""
        self.user_id = user_id
        print(f"已設定新聞推播用戶: {user_id}")
        
    def set_check_interval(self, minutes):
        """設定檢查間隔（分鐘）"""
        if 1 <= minutes <= 60:
            self.check_interval = minutes * 60
            return f"已設定檢查間隔為 {minutes} 分鐘"
        else:
            return "檢查間隔請設定在 1-60 分鐘之間"
    
    def set_time_range(self, start_hour, start_minute, end_hour, end_minute):
        """設定推播時間範圍"""
        try:
            self.start_time = dt_time(start_hour, start_minute)
            self.end_time = dt_time(end_hour, end_minute)
            return f"已設定推播時間：{start_hour:02d}:{start_minute:02d} - {end_hour:02d}:{end_minute:02d}"
        except:
            return "時間格式錯誤"
    
    def set_news_category(self, category):
        """設定新聞分類"""
        valid_categories = {
            'headline': '綜合頭條',
            'tw_stock': '台股新聞', 
            'us_stock': '美股新聞',
            'revenue': '台股營收',
            'earnings': '財報資訊',
            'forex': '外匯新聞',
            'futures': '期貨新聞'
        }
        
        if category in valid_categories:
            self.news_category = category
            return f"已設定新聞分類為：{valid_categories[category]}"
        else:
            return f"❌ 無效的分類，可用分類：{', '.join(valid_categories.keys())}"
    
    def get_category_help(self):
        """取得分類說明"""
        return """📰 新聞分類說明

🔢 可用分類：
• headline - 綜合頭條新聞
• tw_stock - 台股專區新聞  
• us_stock - 美股專區新聞
• forex - 外匯新聞
• futures - 期貨新聞

💡 使用方式：
• 台股模式 - 切換到台股新聞
• 美股模式 - 切換到美股新聞
• 綜合模式 - 切換到綜合新聞

📊 當前分類：""" + self.news_category
    
    def toggle_weekend(self):
        """切換週末推播設定"""
        self.weekend_enabled = not self.weekend_enabled
        status = "啟用" if self.weekend_enabled else "停用"
        return f"週末推播已{status}"
    
    def is_in_push_time(self):
        """檢查是否在推播時間範圍內"""
        taiwan_now = get_taiwan_datetime()
        current_time = taiwan_now.time()
        current_weekday = taiwan_now.weekday()
        
        if current_weekday >= 5 and not self.weekend_enabled:
            return False, "週末推播已停用"
        
        if self.start_time <= self.end_time:
            if not (self.start_time <= current_time <= self.end_time):
                return False, f"不在推播時間內 ({self.start_time.strftime('%H:%M')}-{self.end_time.strftime('%H:%M')})"
        else:
            if not (current_time >= self.start_time or current_time <= self.end_time):
                return False, f"不在推播時間內 ({self.start_time.strftime('%H:%M')}-{self.end_time.strftime('%H:%M')})"
        
        return True, "在推播時間內"
        
    def fetch_cnyes_news(self):
        """抓取鉅亨網新聞 - 除錯版本"""
        try:
            print(f"開始抓取新聞 - {get_taiwan_time()}")
            print(f"使用分類: {self.news_category}")
            
            url = f"https://api.cnyes.com/media/api/v1/newslist/category/{self.news_category}"
            params = {'limit': 10, 'page': 1}
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            
            print(f"請求URL: {url}")
            
            response = requests.get(url, params=params, headers=headers, timeout=10)
            
            print(f"回應狀態碼: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"JSON 解析成功")
                
                if 'items' in data and 'data' in data['items']:
                    news_list = data['items']['data']
                    print(f"成功取得 {len(news_list)} 則新聞")
                    return news_list
                else:
                    print(f"資料結構異常")
                    return []
            else:
                print(f"HTTP 錯誤: {response.status_code}")
                return []
                
        except Exception as e:
            print(f"抓取新聞例外錯誤: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def format_single_news(self, news_data):
        """格式化單則新聞"""
        try:
            print(f"開始格式化新聞")
            
            # 處理標題
            title = news_data.get('title', '無標題')
            if isinstance(title, str):
                try:
                    import json
                    title = json.loads(f'"{title}"')
                except:
                    pass
            
            print(f"處理標題完成: {title[:50]}")
            
            news_id = news_data.get('newsId', '')
            publish_time = news_data.get('publishAt', '')
            
            # 格式化發布時間
            formatted_time = "未知時間"
            if publish_time:
                try:
                    if isinstance(publish_time, (int, float)):
                        if 1577836800 <= publish_time <= 1893456000:
                            publish_dt = datetime.fromtimestamp(publish_time)
                            formatted_time = publish_dt.strftime('%H:%M')
                        else:
                            formatted_time = f"時間戳:{publish_time}"
                    else:
                        formatted_time = str(publish_time)[:10]
                except Exception as e:
                    formatted_time = f"時間解析錯誤"
            
            # 處理內容摘要
            content_summary = ""
            summary = news_data.get('summary')
            if summary and str(summary).strip():
                content_summary = str(summary).strip()
            elif news_data.get('content'):
                content = news_data.get('content', '')
                if content:
                    import re
                    content = re.sub(r'&lt;[^&gt;]+&gt;', '', content)
                    content = re.sub(r'&[a-zA-Z0-9]+;', '', content)
                    content_summary = content.strip()
            
            # 處理Unicode編碼
            if content_summary:
                try:
                    import json
                    content_summary = json.loads(f'"{content_summary}"')
                except:
                    pass
                
                if len(content_summary) > 180:
                    content_summary = content_summary[:180] + "..."
            
            # 構建訊息
            message = f"📰 財經即時新聞\n\n"
            message += f"📌 {title}\n\n"
            
            if content_summary:
                message += f"📄 {content_summary}\n\n"
            
            # 生成新聞連結
            if news_id:
                news_link = f"https://news.cnyes.com/news/id/{news_id}"
                message += f"🔗 {news_link}\n\n"
            
            message += f"🕐 {formatted_time}\n"
            message += f"📰 來源：鉅亨網 ({self.news_category})"
            
            print(f"格式化完成，訊息長度: {len(message)}")
            return message
            
        except Exception as e:
            print(f"格式化新聞失敗: {e}")
            import traceback
            traceback.print_exc()
            return f"新聞格式化失敗: {e}"
    
    def send_news_notification(self, news_data):
        """發送新聞推播"""
        if not self.user_id:
            print("未設定推播用戶ID")
            return False
        
        message = self.format_single_news(news_data)
        success = send_push_message(self.user_id, message, bot_type='news')
        
        if success:
            print(f"新聞推播成功 - {get_taiwan_time()}")
        else:
            print(f"新聞推播失敗 - {get_taiwan_time()}")
            
        return success
    
    def check_new_news(self):
        """檢查是否有新新聞"""
        news_list = self.fetch_cnyes_news()
        
        if not news_list:
            return None
        
        # 簡化邏輯：總是返回最新新聞用於測試
        latest_news = news_list[0]
        latest_news_id = latest_news.get('newsId')
        
        if self.last_news_id is None:
            self.last_news_id = latest_news_id
            return latest_news
        
        if latest_news_id != self.last_news_id:
            self.last_news_id = latest_news_id
            return latest_news
        
        return None
    
    def news_check_loop(self):
        """新聞檢查循環"""
        print(f"新聞檢查循環開始，間隔{self.check_interval//60}分鐘 - {get_taiwan_time()}")
        
        while self.is_running:
            try:
                new_news = self.check_new_news()
                
                if new_news:
                    title = new_news.get('title', '無標題')
                    print(f"發現新新聞並推播: {title} - {get_taiwan_time()}")
                    self.send_news_notification(new_news)
                
                time.sleep(self.check_interval)
                
            except Exception as e:
                print(f"新聞檢查循環錯誤: {e} - {get_taiwan_time()}")
                time.sleep(60)
    
    def start_news_monitoring(self, user_id):
        """開始新聞監控"""
        self.set_user_id(user_id)
        
        if self.news_thread and self.news_thread.is_alive():
            return "新聞監控已在運行中"
        
        self.is_running = True
        self.news_thread = threading.Thread(target=self.news_check_loop, daemon=True)
        self.news_thread.start()
        
        return f"✅ 新聞監控已啟動\n📰 {self.news_category} 新聞自動推播\n🕐 {get_taiwan_time()}"
    
    def stop_news_monitoring(self):
        """停止新聞監控"""
        self.is_running = False
        return f"⏹️ 新聞監控已停止\n🕐 {get_taiwan_time()}"
    
    def get_news_status(self):
        """獲取新聞監控狀態"""
        status = "運行中" if self.is_running else "已停止"
        user_info = f"推播對象: {self.user_id}" if self.user_id else "未設定推播對象"
        
        return f"""📊 新聞監控狀態

🔄 監控狀態: {status}
👤 {user_info}
📰 新聞分類: {self.news_category}
⏰ 推播時間: {self.start_time.strftime('%H:%M')} - {self.end_time.strftime('%H:%M')}
🔄 檢查間隔: {self.check_interval//60} 分鐘

🕐 {get_taiwan_time()}"""
    
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
