"""
應用程式配置設定
"""
import os

class Settings:
    """應用程式設定類"""
    
    # LINE Bot 配置
    CHANNEL_ACCESS_TOKEN = os.getenv('CHANNEL_ACCESS_TOKEN', '')
    CHANNEL_SECRET = os.getenv('CHANNEL_SECRET', '')
    
    # 伺服器配置
    PORT = int(os.getenv('PORT', 8000))
    HOST = os.getenv('HOST', '0.0.0.0')
    DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'
    
    # 應用程式設定
    APP_NAME = "LINE Todo Reminder Bot"
    VERSION = "2.0.0"

# 創建設定實例
settings = Settings()
