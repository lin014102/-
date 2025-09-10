# news_bot.py - 完整版本支援新聞分類
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
        self.user_id = None
        self.news_thread = None
        self.is_running = False
        
        # 新增設定選項
        self.check_interval = 300  # 預設5分鐘(300秒)
        self.news_category = 'headline'  # 預設綜合新聞
        self.start_time = dt_time(9, 0)   # 推播開始時間 9:00
        self.end_time = dt_time(21, 0)    # 推播結束時間 21:00
        self.weekend_enabled = False      # 週末是否推播
        
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
        current_weekday = taiwan_now.weekday()  # 0=Monday, 6=Sunday
        
        # 檢查週末設定
        if current_weekday >= 5 and not self.weekend_enabled:  # 5=Saturday, 6=Sunday
            return False, "週末推播已停用"
        
        # 檢查時間範圍
        if self.start_time <= self.end_time:
            # 正常時間範圍 (例如 9:00-21:00)
            if not (self.start_time <= current_time <= self.end_time):
                return False, f"不在推播時間內 ({self.start_time.strftime('%H:%M')}-{self.end_time.strftime('%H:%M')})"
        else:
            # 跨日時間範圍 (例如 21:00-09:00)
            if not (current_time >= self.start_time or current_time <= self.end_time):
                return False, f"不在推播時間內 ({self.start_time.strftime('%H:%M')}-{self.end_time.strftime('%H:%M')})"
        
        return True, "在推播時間內"
        
    def fetch_cnyes_news(self):
        """抓取鉅亨網新聞"""
        try:
            if self.multi_categories:
                # 精選模式：抓取多個分類
                all_news = []
                for category in self.multi_categories:
                    news_list = self._fetch_single_category(category)
                    if news_list:
                        # 為每則新聞標記分類
                        for news in news_list:
                            news['_category'] = category
                        all_news.extend(news_list)
                
                # 按時間排序，取最新的10則
                if all_news:
                    all_news.sort(key=lambda x: x.get('publishAt', 0), reverse=True)
                    return all_news[:10]
                return []
            else:
                # 單一分類模式 - 使用原始邏輯
                return self._fetch_single_category(self.news_category)
                
        except Exception as e:
            print(f"抓取新聞發生錯誤: {e} - {get_taiwan_time()}")
            return []
    
    def _fetch_single_category(self, category):
        """抓取單一分類新聞"""
        try:
            url = f"https://api.cnyes.com/media/api/v1/newslist/category/{category}"
            params = {
                'limit': 10,  # 改回10
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
                    print(f"成功抓取 {len(news_list)} 則{category}新聞 - {get_taiwan_time()}")
                    return news_list
                else:
                    print(f"{category}新聞數據格式異常 - {get_taiwan_time()}")
                    return []
            else:
                print(f"抓取{category}新聞失敗，狀態碼: {response.status_code} - {get_taiwan_time()}")
                return []
                
        except Exception as e:
            print(f"抓取{category}新聞發生錯誤: {e} - {get_taiwan_time()}")
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
            
            # 檢查推播時間
            time_ok, time_msg = self.is_in_push_time()
            if not time_ok:
                print(f"跳過推播: {time_msg}")
                self.last_news_id = latest_news_id  # 仍要更新ID避免重複檢查
                return None
            
            print(f"通過時間檢查，準備推播")
            self.last_news_id = latest_news_id
            return latest_news
        
        return None
    
    def format_news_message(self, news_data):
        """格式化新聞訊息"""
        try:
            # 處理 Unicode 編碼的標題
            title = news_data.get('title', '無標題')
            if isinstance(title, str):
                try:
                    # 嘗試 JSON 解碼處理 Unicode
                    import json
                    title = json.loads(f'"{title}"')
                except:
                    pass  # 如果解碼失敗，使用原始標題
            
            # 處理摘要 - 注意可能是 null
            summary = news_data.get('summary')
            if summary is None:
                summary = ""
            else:
                summary = str(summary).strip()
                if isinstance(summary, str):
                    try:
                        import json
                        summary = json.loads(f'"{summary}"')
                    except:
                        pass
            
            news_id = news_data.get('newsId', '')
            publish_time = news_data.get('publishAt', '')
            
            # 格式化發布時間
            formatted_time = "未知時間"
            if publish_time:
                try:
                    if isinstance(publish_time, (int, float)):
                        # 檢查時間戳是否合理（2020-2030年之間）
                        if 1577836800 <= publish_time <= 1893456000:  # 2020-01-01 到 2030-01-01
                            publish_dt = datetime.fromtimestamp(publish_time)
                            formatted_time = publish_dt.strftime('%H:%M')
                        else:
                            # 如果時間戳異常，顯示原始值
                            formatted_time = f"時間戳:{publish_time}"
                    else:
                        formatted_time = str(publish_time)[:10]  # 增加長度避免截斷
                except Exception as e:
                    formatted_time = f"時間解析錯誤:{str(e)[:20]}"
            
            # 構建訊息
            message = f"📰 財經即時新聞\n\n"
            message += f"📌 {title}\n\n"
            
            # 處理內容摘要
            content_summary = ""
            if summary:
                content_summary = summary
            elif news_data.get('content'):
                # 從content欄位提取內容
                content = news_data.get('content', '')
                if content:
                    try:
                        import re
                        # 移除HTML標籤
                        content = re.sub(r'&lt;[^&gt;]+&gt;', '', content)
                        content = re.sub(r'&[a-zA-Z0-9]+;', '', content)  # 移除HTML實體
                        # 處理Unicode
                        import json
                        try:
                            content = json.loads(f'"{content}"')
                        except:
                            pass
                        content_summary = content.strip()
                    except:
                        content_summary = ""
            
            if content_summary:
                if len(content_summary) > 150:
                    content_summary = content_summary[:150] + "..."
                message += f"📄 {content_summary}\n\n"
            
            message += f"🕐 {formatted_time}\n"
            message += f"📰 來源：鉅亨網 ({self.news_category})\n"
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
        print(f"新聞檢查循環開始，間隔{self.check_interval//60}分鐘 - {get_taiwan_time()}")
        
        while self.is_running:
            try:
                new_news = self.check_new_news()
                
                if new_news:
                    if isinstance(new_news, list):
                        count = len(new_news)
                        titles = [news.get('title', '無標題')[:30] for news in new_news]
                        print(f"發現 {count} 則新新聞並推播: {', '.join(titles)} - {get_taiwan_time()}")
                    else:
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
        
        category_names = {
            'headline': '綜合頭條',
            'tw_stock': '台股新聞',
            'us_stock': '美股新聞',
            'forex': '外匯新聞',
            'futures': '期貨新聞'
        }
        
        current_category = category_names.get(self.news_category, self.news_category)
        
        settings_info = f"\n📰 新聞分類：{current_category}"
        settings_info += f"\n⏰ 推播時間：{self.start_time.strftime('%H:%M')} - {self.end_time.strftime('%H:%M')}"
        settings_info += f"\n📅 週末推播：{'啟用' if self.weekend_enabled else '停用'}"
        settings_info += f"\n🔄 檢查間隔：{self.check_interval//60} 分鐘"
        
        return f"✅ 新聞監控已啟動\n📰 鉅亨網財經新聞自動推播{settings_info}\n🕐 {get_taiwan_time()}"
    
    def stop_news_monitoring(self):
        """停止新聞監控"""
        self.is_running = False
        return f"⏹️ 新聞監控已停止\n🕐 {get_taiwan_time()}"
    
    def get_news_status(self):
        """獲取新聞監控狀態"""
        status = "運行中" if self.is_running else "已停止"
        user_info = f"推播對象: {self.user_id}" if self.user_id else "未設定推播對象"
        last_news_info = f"最後新聞ID: {self.last_news_id}" if self.last_news_id else "尚未抓取過新聞"
        
        time_ok, time_msg = self.is_in_push_time()
        time_status = f"推播狀態: {time_msg}"
        
        category_names = {
            'headline': '綜合頭條',
            'tw_stock': '台股新聞',
            'us_stock': '美股新聞',
            'forex': '外匯新聞',
            'futures': '期貨新聞'
        }
        
        current_category = category_names.get(self.news_category, self.news_category)
        
        settings = f"""📊 新聞監控狀態

🔄 監控狀態: {status}
👤 {user_info}
📰 {last_news_info}
⏰ {time_status}

⚙️ 設定資訊:
📰 新聞分類: {current_category}
⏰ 推播時間: {self.start_time.strftime('%H:%M')} - {self.end_time.strftime('%H:%M')}
📅 週末推播: {'啟用' if self.weekend_enabled else '停用'}
🔄 檢查間隔: {self.check_interval//60} 分鐘

🕐 {get_taiwan_time()}"""
        
        return settings
    
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
