"""
stock_notifier.py - 股票到價提醒模組
整合到 reminder_bot 機制，提供股票相關提醒功能
"""
import os
import time
from datetime import datetime
from pymongo import MongoClient
from utils.line_api import send_push_message
from stock_analyzer import stock_analyzer

class StockNotifier:
    """股票提醒管理器"""
    
    def __init__(self):
        """初始化股票提醒"""
        # 初始化 MongoDB
        mongodb_uri = os.getenv('MONGODB_URI')
        if mongodb_uri:
            try:
                self.client = MongoClient(mongodb_uri)
                self.db = self.client.get_default_database()
                self.alerts_collection = self.db.stock_alerts
                self.use_mongodb = True
                print("✅ StockNotifier 成功連接到 MongoDB")
            except Exception as e:
                print(f"❌ StockNotifier MongoDB 連接失敗: {e}")
                self._alerts = []
                self.use_mongodb = False
        else:
            self._alerts = []
            self.use_mongodb = False
    
    def add_price_alert(self, user_id, stock_code, stock_name, target_price, alert_type='above'):
        """新增價格提醒
        
        Args:
            user_id: LINE 用戶ID
            stock_code: 股票代號
            stock_name: 股票名稱
            target_price: 目標價格
            alert_type: 'above' (突破) 或 'below' (跌破)
        """
        try:
            alert = {
                'id': self._get_next_alert_id(),
                'user_id': user_id,
                'stock_code': stock_code,
                'stock_name': stock_name,
                'target_price': float(target_price),
                'alert_type': alert_type,
                'is_active': True,
                'created_at': datetime.now().isoformat(),
                'triggered_at': None
            }
            
            if self.use_mongodb:
                self.alerts_collection.insert_one(alert)
            else:
                self._alerts.append(alert)
            
            type_text = "突破" if alert_type == 'above' else "跌破"
            return f"✅ 已設定價格提醒\n📊 {stock_name} ({stock_code})\n🎯 目標價：{target_price}元\n💡 當股價{type_text} {target_price}元時通知您"
            
        except Exception as e:
            print(f"新增價格提醒失敗: {e}")
            return "❌ 設定提醒失敗，請稍後再試"
    
    def add_support_resistance_alert(self, user_id, stock_code, stock_name):
        """新增支撐壓力提醒（自動計算）"""
        try:
            # 快速分析取得支撐壓力
            analysis = stock_analyzer.quick_analysis(stock_code, stock_name)
            
            if not analysis:
                return f"❌ 無法分析 {stock_name} ({stock_code})"
            
            alerts_added = []
            
            # 設定壓力位提醒
            if analysis['resistance']:
                self.add_price_alert(user_id, stock_code, stock_name, 
                                    analysis['resistance'], 'above')
                alerts_added.append(f"壓力 {analysis['resistance']}元")
            
            # 設定支撐位提醒
            if analysis['support']:
                self.add_price_alert(user_id, stock_code, stock_name, 
                                    analysis['support'], 'below')
                alerts_added.append(f"支撐 {analysis['support']}元")
            
            if alerts_added:
                result = f"✅ 已自動設定技術分析提醒\n📊 {stock_name} ({stock_code})\n💹 目前價格：{analysis['current_price']}元\n\n🔔 提醒點位：\n"
                result += "\n".join([f"• {alert}" for alert in alerts_added])
                return result
            else:
                return f"⚠️ {stock_name} 暫無明確支撐壓力位"
                
        except Exception as e:
            print(f"設定支撐壓力提醒失敗: {e}")
            return "❌ 設定提醒失敗，請稍後再試"
    
    def check_price_alerts(self):
        """檢查所有價格提醒"""
        try:
            alerts = self._get_active_alerts()
            
            for alert in alerts:
                try:
                    # 取得即時股價
                    from stock_manager import stock_manager
                    current_price = stock_manager.get_stock_price(alert['stock_code'])
                    
                    if not current_price:
                        continue
                    
                    # 檢查是否觸發
                    should_trigger = False
                    if alert['alert_type'] == 'above' and current_price >= alert['target_price']:
                        should_trigger = True
                        trigger_text = "突破"
                    elif alert['alert_type'] == 'below' and current_price <= alert['target_price']:
                        should_trigger = True
                        trigger_text = "跌破"
                    
                    if should_trigger:
                        # 發送通知
                        message = f"🔔 股票價格提醒！\n\n"
                        message += f"📊 {alert['stock_name']} ({alert['stock_code']})\n"
                        message += f"💹 目前價格：{current_price}元\n"
                        message += f"🎯 已{trigger_text}目標價：{alert['target_price']}元\n"
                        message += f"⏰ 提醒時間：{datetime.now().strftime('%Y/%m/%d %H:%M')}"
                        
                        send_push_message(alert['user_id'], message)
                        
                        # 標記為已觸發
                        self._mark_alert_triggered(alert['id'])
                        print(f"✅ 已發送價格提醒：{alert['stock_name']} {trigger_text} {alert['target_price']}")
                
                except Exception as e:
                    print(f"檢查提醒失敗 {alert.get('stock_name', 'unknown')}: {e}")
                    continue
        
        except Exception as e:
            print(f"檢查價格提醒失敗: {e}")
    
    def get_user_alerts(self, user_id):
        """取得用戶的所有提醒"""
        try:
            if self.use_mongodb:
                alerts = list(self.alerts_collection.find({
                    'user_id': user_id,
                    'is_active': True
                }))
            else:
                alerts = [a for a in self._alerts 
                         if a['user_id'] == user_id and a['is_active']]
            
            if not alerts:
                return "📝 目前沒有任何股票提醒"
            
            result = "🔔 股票提醒列表：\n\n"
            for alert in alerts:
                type_text = "突破" if alert['alert_type'] == 'above' else "跌破"
                result += f"📊 {alert['stock_name']} ({alert['stock_code']})\n"
                result += f"   🎯 {type_text} {alert['target_price']}元\n\n"
            
            result += f"💡 共 {len(alerts)} 個提醒"
            return result
            
        except Exception as e:
            print(f"取得提醒列表失敗: {e}")
            return "❌ 取得提醒列表失敗"
    
    def delete_alert(self, user_id, stock_code):
        """刪除指定股票的提醒"""
        try:
            if self.use_mongodb:
                result = self.alerts_collection.update_many(
                    {'user_id': user_id, 'stock_code': stock_code, 'is_active': True},
                    {'$set': {'is_active': False}}
                )
                deleted_count = result.modified_count
            else:
                deleted_count = 0
                for alert in self._alerts:
                    if (alert['user_id'] == user_id and 
                        alert['stock_code'] == stock_code and 
                        alert['is_active']):
                        alert['is_active'] = False
                        deleted_count += 1
            
            if deleted_count > 0:
                return f"✅ 已刪除 {stock_code} 的 {deleted_count} 個提醒"
            else:
                return f"❌ 找不到 {stock_code} 的提醒"
                
        except Exception as e:
            print(f"刪除提醒失敗: {e}")
            return "❌ 刪除提醒失敗"
    
    def _get_active_alerts(self):
        """取得所有啟用的提醒"""
        if self.use_mongodb:
            return list(self.alerts_collection.find({'is_active': True}))
        else:
            return [a for a in self._alerts if a.get('is_active', True)]
    
    def _get_next_alert_id(self):
        """取得下一個提醒ID"""
        if self.use_mongodb:
            last_alert = self.alerts_collection.find_one(
                sort=[('id', -1)]
            )
            return (last_alert['id'] + 1) if last_alert else 1
        else:
            return max([a['id'] for a in self._alerts], default=0) + 1
    
    def _mark_alert_triggered(self, alert_id):
        """標記提醒為已觸發"""
        if self.use_mongodb:
            self.alerts_collection.update_one(
                {'id': alert_id},
                {'$set': {
                    'is_active': False,
                    'triggered_at': datetime.now().isoformat()
                }}
            )
        else:
            for alert in self._alerts:
                if alert['id'] == alert_id:
                    alert['is_active'] = False
                    alert['triggered_at'] = datetime.now().isoformat()
                    break


# 建立全域實例
stock_notifier = StockNotifier()

# 對外接口
def add_stock_price_alert(user_id, stock_code, stock_name, target_price, alert_type='above'):
    """新增價格提醒 - 對外接口"""
    return stock_notifier.add_price_alert(user_id, stock_code, stock_name, target_price, alert_type)

def add_stock_technical_alert(user_id, stock_code, stock_name):
    """新增技術分析提醒 - 對外接口"""
    return stock_notifier.add_support_resistance_alert(user_id, stock_code, stock_name)

def get_stock_alerts(user_id):
    """取得用戶提醒 - 對外接口"""
    return stock_notifier.get_user_alerts(user_id)

def delete_stock_alert(user_id, stock_code):
    """刪除提醒 - 對外接口"""
    return stock_notifier.delete_alert(user_id, stock_code)

def check_stock_alerts():
    """檢查所有提醒 - 對外接口（供定時任務使用）"""
    stock_notifier.check_price_alerts()
