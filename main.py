"""
LINE Todo Reminder Bot - Python 版本
主程式入口
"""
import os
import logging
from fastapi import FastAPI

# 設定日誌
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 創建 FastAPI 應用程式
app = FastAPI(title="LINE Todo Reminder Bot")

# 基本設定
PORT = int(os.getenv('PORT', 8000))

@app.get("/")
async def root():
    return {"message": "LINE Todo Reminder Bot is running"}

@app.get("/health")
async def health():
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=PORT)
