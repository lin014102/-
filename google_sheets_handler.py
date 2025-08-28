"""
Google Sheets 操作處理器
負責讀取 CONFIG 和 DOWNLOAD sheet，更新處理狀態
"""

import os
import json
from datetime import datetime
from googleapiclient.discovery import build
from google.oauth2 import service_account
import logging

class GoogleSheetsHandler:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.service = self._build_service()
        self.spreadsheet_id = os.getenv('GOOGLE_SPREADSHEET_ID')
        
    def _build_service(self):
        """建立 Google Sheets API 服務"""
        try:
            # 從環境變數讀取服務帳號金鑰
            service_account_info = json.loads(os.getenv('GOOGLE_SERVICE_ACCOUNT_JSON'))
            
            credentials = service_account.Credentials.from_service_account_info(
                service_account_info,
                scopes=['https://www.googleapis.com/auth/spreadsheets']
            )
            
            return build('sheets', 'v4', credentials=credentials)
            
        except Exception as e:
            self.logger.error(f"Google Sheets API 初始化失敗: {e}")
            raise

    def get_bank_configs(self):
        """讀取 CONFIG sheet 的銀行設定"""
        try:
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range='CONFIG!A:G'
            ).execute()
            
            values = result.get('values', [])
            if not values:
                return []
            
            # 跳過標題列，只取啟用的機構
            configs = []
            for row in values[1:]:
                if len(row) >= 7 and row[6] == '啟用':  # G欄：啟用狀態
                    configs.append({
                        'code': row[0],      # A欄：機構代碼
                        'name': row[1],      # B欄：機構名稱
                        'type': row[2],      # C欄：類型
                        'sender': row[3],    # D欄：寄件者Email
                        'subject': row[4],   # E欄：主旨關鍵字
                        'password': row[5]   # F欄：PDF密碼
                    })
            
            self.logger.info(f"讀取到 {len(configs)} 個啟用的銀行設定")
            return configs
            
        except Exception as e:
            self.logger.error(f"讀取 CONFIG sheet 失敗: {e}")
            return []

    def get_pending_files(self):
        """讀取 DOWNLOAD sheet 中待處理的檔案"""
        try:
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range='DOWNLOAD!A:G'  # 改為 A:G，因為實際上 G 欄是處理狀態
            ).execute()
            
            values = result.get('values', [])
            if not values:
                return []
            
            # 找出狀態為「待處理」的檔案
            pending_files = []
            for i, row in enumerate(values[1:], start=2):  # 從第2列開始（跳過標題）
                if len(row) >= 7 and row[6] == '待處理':  # G欄：處理狀態
                    pending_files.append({
                        'row_index': i,
                        'download_date': row[0],    # A欄：下載日期
                        'sender': row[1],           # B欄：寄件者
                        'subject': row[2],          # C欄：標題
                        'filename': row[3],         # D欄：檔名
                        'file_id': row[4],          # E欄：Drive File ID
                        'status': row[6]            # G欄：處理狀態
                    })
            
            self.logger.info(f"找到 {len(pending_files)} 個待處理檔案")
            return pending_files
            
        except Exception as e:
            self.logger.error(f"讀取 DOWNLOAD sheet 失敗: {e}")
            return []

    def get_failed_files(self):
        """讀取 DOWNLOAD sheet 中解析失敗的檔案"""
        try:
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range='DOWNLOAD!A:J'
            ).execute()
            
            values = result.get('values', [])
            if not values:
                return []
            
            # 找出狀態為「解析失敗」的檔案
            failed_files = []
            for i, row in enumerate(values[1:], start=2):
                if len(row) >= 7 and row[6] == '解析失敗':  # G欄：處理狀態
                    failed_files.append({
                        'row_index': i,
                        'download_date': row[0],
                        'sender': row[1],
                        'subject': row[2],
                        'filename': row[3],
                        'file_id': row[4],
                        'status': row[6]
                    })
            
            return failed_files
            
        except Exception as e:
            self.logger.error(f"讀取失敗檔案失敗: {e}")
            return []

    def update_file_status(self, row_index, status, result_data=None):
        """更新檔案處理狀態"""
        try:
            # 更新處理狀態 (G欄)
            self.service.spreadsheets().values().update(
                spreadsheetId=self.spreadsheet_id,
                range=f'DOWNLOAD!G{row_index}',
                valueInputOption='RAW',
                body={'values': [[status]]}
            ).execute()
            
            # 如果有解析結果，更新到 H 欄
            if result_data and status == '已完成':
                result_json = json.dumps(result_data, ensure_ascii=False)
                self.service.spreadsheets().values().update(
                    spreadsheetId=self.spreadsheet_id,
                    range=f'DOWNLOAD!H{row_index}',
                    valueInputOption='RAW',
                    body={'values': [[result_json]]}
                ).execute()
            
            # 更新處理時間到 I 欄
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            self.service.spreadsheets().values().update(
                spreadsheetId=self.spreadsheet_id,
                range=f'DOWNLOAD!I{row_index}',
                valueInputOption='RAW',
                body={'values': [[current_time]]}
            ).execute()
            
            self.logger.info(f"更新檔案狀態成功：列 {row_index} -> {status}")
            
        except Exception as e:
            self.logger.error(f"更新檔案狀態失敗: {e}")

    def add_notification_columns_if_needed(self):
        """檢查並添加推播相關的欄位（如果不存在）"""
        try:
            # 讀取當前 DOWNLOAD sheet 的標題列
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range='DOWNLOAD!1:1'
            ).execute()
            
            values = result.get('values', [[]])
            headers = values[0] if values else []
            
            # 檢查是否需要添加欄位
            expected_headers = [
                'A:下載日期', 'B:寄件者', 'C:標題', 'D:檔名', 
                'E:Drive File ID', 'F:處理狀態', 'G:解析結果', 
                'H:更新時間', 'I:推播狀態'
            ]
            
            if len(headers) < len(expected_headers):
                self.logger.info("添加缺少的欄位標題")
                simple_headers = [
                    '下載日期', '寄件者', '標題', '檔名', 
                    'Drive File ID', '處理狀態', '解析結果', 
                    '更新時間', '推播狀態'
                ]
                
                self.service.spreadsheets().values().update(
                    spreadsheetId=self.spreadsheet_id,
                    range='DOWNLOAD!A1:I1',
                    valueInputOption='RAW',
                    body={'values': [simple_headers]}
                ).execute()
                
        except Exception as e:
            self.logger.error(f"添加欄位失敗: {e}")

    def get_notification_pending_files(self):
        """讀取需要推播的檔案（處理狀態=已完成 且 推播狀態!=已推播）"""
        try:
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range='DOWNLOAD!A:J'
            ).execute()
            
            values = result.get('values', [])
            if not values:
                return []
            
            notification_files = []
            for i, row in enumerate(values[1:], start=2):
                if len(row) >= 7 and row[6] == '已完成':  # G欄：處理狀態 = 已完成
                    notification_status = row[9] if len(row) > 9 else ''  # J欄：推播狀態
                    
                    if notification_status != '已推播':
                        notification_files.append({
                            'row_index': i,
                            'filename': row[3],
                            'file_id': row[4],
                            'analysis_result': row[7] if len(row) > 7 else '',  # H欄：解析結果
                            'notification_status': notification_status
                        })
            
            self.logger.info(f"找到 {len(notification_files)} 個需要推播的檔案")
            return notification_files
            
        except Exception as e:
            self.logger.error(f"讀取推播待處理檔案失敗: {e}")
            return []

    def update_notification_status(self, row_index, status):
        """更新推播狀態"""
        try:
            self.service.spreadsheets().values().update(
                spreadsheetId=self.spreadsheet_id,
                range=f'DOWNLOAD!J{row_index}',  # J欄：推播狀態
                valueInputOption='RAW',
                body={'values': [[status]]}
            ).execute()
            
            self.logger.info(f"更新推播狀態成功：列 {row_index} -> {status}")
            
        except Exception as e:
            self.logger.error(f"更新推播狀態失敗: {e}")

    def get_bank_config_by_filename(self, filename):
        """根據檔案名稱取得銀行設定"""
        try:
            # 從檔名提取機構代碼 (格式: CODE_YYYYMMDD_XXX.pdf)
            bank_code = filename.split('_')[0]
            
            configs = self.get_bank_configs()
            for config in configs:
                if config['code'] == bank_code:
                    return config
            
            self.logger.warning(f"找不到機構代碼 {bank_code} 的設定")
            return None
            
        except Exception as e:
            self.logger.error(f"取得銀行設定失敗: {e}")
            return None
