"""
Google Sheets 操作處理器 - 修正版
負責讀取 CONFIG 和 DOWNLOAD sheet，更新處理狀態
修正了與 GAS 程式的欄位對應問題
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
        
        # 自動檢查並修正欄位結構
        self._ensure_sheet_structure()
        
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

    def _ensure_sheet_structure(self):
        """確保工作表有正確的欄位結構"""
        try:
            # 檢查 DOWNLOAD sheet 的標題列
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range='DOWNLOAD!1:1'
            ).execute()
            
            values = result.get('values', [[]])
            headers = values[0] if values else []
            
            # 定義正確的欄位結構（與 GAS 對應）
            expected_headers = [
                '下載日期',     # A欄
                '寄件者',       # B欄
                '標題',         # C欄
                '檔名',         # D欄
                'Drive File ID', # E欄
                '機構名稱',     # F欄
                '處理狀態',     # G欄
                '解析結果',     # H欄
                '更新時間',     # I欄
                '推播狀態'      # J欄
            ]
            
            # 如果標題不完整或不正確，更新標題列
            if len(headers) < len(expected_headers) or headers != expected_headers:
                self.logger.info("更新 DOWNLOAD sheet 標題列")
                self.service.spreadsheets().values().update(
                    spreadsheetId=self.spreadsheet_id,
                    range='DOWNLOAD!A1:J1',
                    valueInputOption='RAW',
                    body={'values': [expected_headers]}
                ).execute()
                
        except Exception as e:
            self.logger.warning(f"無法檢查工作表結構: {e}")

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
        """讀取 DOWNLOAD sheet 中待處理的檔案 - 修正版"""
        try:
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range='DOWNLOAD!A:J'  # 讀取完整範圍
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
                        'download_date': row[0],           # A欄：下載日期
                        'sender': row[1],                  # B欄：寄件者
                        'subject': row[2],                 # C欄：標題
                        'filename': row[3],                # D欄：檔名
                        'file_id': row[4],                 # E欄：Drive File ID
                        'institution_name': row[5] if len(row) > 5 else '',  # F欄：機構名稱
                        'status': row[6]                   # G欄：處理狀態
                    })
            
            self.logger.info(f"找到 {len(pending_files)} 個待處理檔案")
            
            # 除錯資訊：顯示找到的檔案
            if pending_files:
                self.logger.info("待處理檔案清單:")
                for file_info in pending_files:
                    self.logger.info(f"  - {file_info['filename']} ({file_info['institution_name']}) - 列{file_info['row_index']}")
            
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
            
            # 找出狀態為「解析失敗」的檔案且推播狀態不是「已推播」的檔案
            failed_files = []
            for i, row in enumerate(values[1:], start=2):
                if len(row) >= 7 and row[6] == '解析失敗':  # G欄：處理狀態
                    # 🆕 檢查推播狀態
                    notification_status = row[9] if len(row) > 9 else ''  # J欄：推播狀態
                    # 🆕 只加入未推播的失敗檔案
                    if notification_status != '已推播':
                        failed_files.append({
                            'row_index': i,
                            'download_date': row[0],            # A欄：下載日期
                            'sender': row[1],                   # B欄：寄件者
                            'subject': row[2],                  # C欄：標題
                            'filename': row[3],                 # D欄：檔名
                            'file_id': row[4],                  # E欄：Drive File ID
                            'institution_name': row[5] if len(row) > 5 else '',  # F欄：機構名稱
                            'status': row[6]                    # G欄：處理狀態
                        })
            
            self.logger.info(f"找到 {len(failed_files)} 個未推播的失敗檔案")
            return failed_files
            
        except Exception as e:
            self.logger.error(f"讀取失敗檔案失敗: {e}")
            return []

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
                            'download_date': row[0],       # A欄：下載日期
                            'sender': row[1],              # B欄：寄件者
                            'subject': row[2],             # C欄：標題
                            'filename': row[3],            # D欄：檔名
                            'file_id': row[4],             # E欄：Drive File ID
                            'institution_name': row[5] if len(row) > 5 else '',  # F欄：機構名稱
                            'analysis_result': row[7] if len(row) > 7 else '',  # H欄：解析結果
                            'notification_status': notification_status           # J欄：推播狀態
                        })
            
            self.logger.info(f"找到 {len(notification_files)} 個需要推播的檔案")
            
            # 除錯資訊：顯示找到的推播檔案
            if notification_files:
                self.logger.info("待推播檔案清單:")
                for file_info in notification_files:
                    self.logger.info(f"  - {file_info['filename']} ({file_info['institution_name']}) - 列{file_info['row_index']}")
            
            return notification_files
            
        except Exception as e:
            self.logger.error(f"讀取推播待處理檔案失敗: {e}")
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
                
                # 設定推播狀態為待推播 (J欄)
                self.service.spreadsheets().values().update(
                    spreadsheetId=self.spreadsheet_id,
                    range=f'DOWNLOAD!J{row_index}',
                    valueInputOption='RAW',
                    body={'values': [['待推播']]}
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

    def update_notification_status(self, row_index, status):
        """更新推播狀態"""
        try:
            # 更新推播狀態 (J欄)
            self.service.spreadsheets().values().update(
                spreadsheetId=self.spreadsheet_id,
                range=f'DOWNLOAD!J{row_index}',
                valueInputOption='RAW',
                body={'values': [[status]]}
            ).execute()
            
            # 同時更新推播時間 (可以考慮加入 K欄 記錄推播時間)
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            try:
                self.service.spreadsheets().values().update(
                    spreadsheetId=self.spreadsheet_id,
                    range=f'DOWNLOAD!K{row_index}',
                    valueInputOption='RAW',
                    body={'values': [[current_time]]}
                ).execute()
            except:
                pass  # K欄可能不存在，忽略錯誤
            
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
                    self.logger.info(f"找到機構設定: {bank_code} -> {config['name']}")
                    return config
            
            self.logger.warning(f"找不到機構代碼 {bank_code} 的設定")
            
            # 嘗試從 DOWNLOAD sheet 中的機構名稱反查
            return self._fallback_bank_config_lookup(filename)
            
        except Exception as e:
            self.logger.error(f"取得銀行設定失敗: {e}")
            return None

    def _fallback_bank_config_lookup(self, filename):
        """備用方法：從 DOWNLOAD sheet 中查找對應的機構設定"""
        try:
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range='DOWNLOAD!A:J'
            ).execute()
            
            values = result.get('values', [])
            
            # 在 DOWNLOAD sheet 中找到此檔案的記錄
            for row in values[1:]:
                if len(row) >= 6 and row[3] == filename:  # D欄是檔名
                    institution_name = row[5]  # F欄是機構名稱
                    
                    # 用機構名稱去 CONFIG 中查找
                    configs = self.get_bank_configs()
                    for config in configs:
                        if config['name'] == institution_name:
                            self.logger.info(f"備用查找成功: {filename} -> {institution_name}")
                            return config
            
            return None
            
        except Exception as e:
            self.logger.error(f"備用查找失敗: {e}")
            return None

    def debug_sheet_content(self, sheet_name='DOWNLOAD', max_rows=10):
        """除錯用：顯示工作表內容"""
        try:
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=f'{sheet_name}!A:J'
            ).execute()
            
            values = result.get('values', [])
            
            self.logger.info(f"=== {sheet_name} Sheet 內容 ===")
            self.logger.info(f"總列數: {len(values)}")
            
            if values:
                self.logger.info("標題列:")
                self.logger.info(f"  {values[0]}")
                
                self.logger.info(f"資料列 (顯示前{max_rows}列):")
                for i, row in enumerate(values[1:max_rows+1], start=2):
                    self.logger.info(f"  列{i}: {row}")
            
        except Exception as e:
            self.logger.error(f"除錯顯示失敗: {e}")

    def get_all_files_summary(self):
        """取得所有檔案的狀態摘要"""
        try:
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range='DOWNLOAD!A:J'
            ).execute()
            
            values = result.get('values', [])
            if not values:
                return {'total': 0, 'pending': 0, 'completed': 0, 'failed': 0, 'notification_pending': 0}
            
            summary = {
                'total': len(values) - 1,  # 扣除標題列
                'pending': 0,
                'completed': 0, 
                'failed': 0,
                'notification_pending': 0
            }
            
            for row in values[1:]:
                if len(row) >= 7:
                    status = row[6]  # G欄：處理狀態
                    
                    if status == '待處理':
                        summary['pending'] += 1
                    elif status == '已完成':
                        summary['completed'] += 1
                        
                        # 檢查是否需要推播
                        notification_status = row[9] if len(row) > 9 else ''
                        if notification_status != '已推播':
                            summary['notification_pending'] += 1
                    elif status == '解析失敗':
                        summary['failed'] += 1
            
            return summary
            
        except Exception as e:
            self.logger.error(f"取得檔案摘要失敗: {e}")
            return {'total': 0, 'pending': 0, 'completed': 0, 'failed': 0, 'notification_pending': 0}
