"""
Google Drive 操作處理器
負責從 Drive File ID 下載 PDF 檔案
"""

import os
import json
import io
from googleapiclient.discovery import build
from google.oauth2 import service_account
import logging

class GoogleDriveHandler:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.service = self._build_service()
        
    def _build_service(self):
        """建立 Google Drive API 服務"""
        try:
            # 從環境變數讀取服務帳號金鑰
            service_account_info = json.loads(os.getenv('GOOGLE_SERVICE_ACCOUNT_JSON'))
            
            credentials = service_account.Credentials.from_service_account_info(
                service_account_info,
                scopes=['https://www.googleapis.com/auth/drive.readonly']
            )
            
            return build('drive', 'v3', credentials=credentials)
            
        except Exception as e:
            self.logger.error(f"Google Drive API 初始化失敗: {e}")
            raise

    def download_file(self, file_id, filename=None):
        """
        下載檔案並回傳檔案內容
        
        Args:
            file_id: Google Drive 檔案 ID
            filename: 檔案名稱（用於日誌）
            
        Returns:
            bytes: 檔案內容，如果失敗回傳 None
        """
        try:
            self.logger.info(f"開始下載檔案: {filename or file_id}")
            
            # 取得檔案資訊
            file_info = self.service.files().get(fileId=file_id).execute()
            self.logger.info(f"檔案資訊: {file_info.get('name', 'Unknown')} ({file_info.get('size', 'Unknown size')} bytes)")
            
            # 下載檔案內容
            request = self.service.files().get_media(fileId=file_id)
            file_content = io.BytesIO()
            
            # 執行下載
            downloader = request.execute()
            if downloader:
                self.logger.info(f"檔案下載成功: {filename or file_id}")
                return downloader
            else:
                self.logger.error(f"檔案下載失敗，無內容: {filename or file_id}")
                return None
                
        except Exception as e:
            self.logger.error(f"下載檔案失敗 {filename or file_id}: {e}")
            return None

    def get_file_info(self, file_id):
        """
        取得檔案資訊
        
        Args:
            file_id: Google Drive 檔案 ID
            
        Returns:
            dict: 檔案資訊，如果失敗回傳 None
        """
        try:
            file_info = self.service.files().get(
                fileId=file_id,
                fields='id,name,size,mimeType,createdTime,modifiedTime'
            ).execute()
            
            return {
                'id': file_info.get('id'),
                'name': file_info.get('name'),
                'size': file_info.get('size'),
                'mime_type': file_info.get('mimeType'),
                'created_time': file_info.get('createdTime'),
                'modified_time': file_info.get('modifiedTime')
            }
            
        except Exception as e:
            self.logger.error(f"取得檔案資訊失敗 {file_id}: {e}")
            return None

    def check_file_exists(self, file_id):
        """
        檢查檔案是否存在
        
        Args:
            file_id: Google Drive 檔案 ID
            
        Returns:
            bool: 檔案是否存在
        """
        try:
            self.service.files().get(fileId=file_id).execute()
            return True
        except Exception as e:
            self.logger.warning(f"檔案不存在或無權限 {file_id}: {e}")
            return False

    def save_file_to_temp(self, file_content, filename):
        """
        將檔案內容儲存到暫存目錄
        
        Args:
            file_content: 檔案內容 (bytes)
            filename: 檔案名稱
            
        Returns:
            str: 暫存檔案路徑，如果失敗回傳 None
        """
        try:
            # 建立暫存目錄
            temp_dir = "/tmp"  # Render 環境使用 /tmp
            if not os.path.exists(temp_dir):
                os.makedirs(temp_dir)
            
            temp_file_path = os.path.join(temp_dir, filename)
            
            with open(temp_file_path, 'wb') as f:
                f.write(file_content)
            
            self.logger.info(f"檔案儲存到暫存目錄: {temp_file_path}")
            return temp_file_path
            
        except Exception as e:
            self.logger.error(f"儲存暫存檔案失敗: {e}")
            return None

    def cleanup_temp_file(self, temp_file_path):
        """
        清理暫存檔案
        
        Args:
            temp_file_path: 暫存檔案路徑
        """
        try:
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)
                self.logger.info(f"清理暫存檔案: {temp_file_path}")
        except Exception as e:
            self.logger.error(f"清理暫存檔案失敗: {e}")
