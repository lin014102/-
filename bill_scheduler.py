"""
bill_scheduler.py - 信用卡帳單自動分析定時任務 + 帳單金額同步
負責每日 03:30 分析帳單，15:15 推播結果，並同步金額到提醒系統
"""

import os
import json
import threading
import time
import logging
from datetime import datetime, timedelta
from google_sheets_handler import GoogleSheetsHandler
from google_drive_handler import GoogleDriveHandler
from bill_analyzer import BillAnalyzer
from utils.time_utils import get_taiwan_datetime, get_taiwan_time_hhmm, TAIWAN_TZ
from utils.line_api import send_push_message


class BillScheduler:
    """信用卡帳單分析定時任務管理器 + 帳單金額同步"""
    
    def __init__(self, reminder_bot):
        self.logger = logging.getLogger(__name__)
        
        # 保存 reminder_bot 實例以獲取用戶 ID 並同步帳單金額
        self.reminder_bot = reminder_bot
        
        # 初始化各個處理器
        try:
            self.sheets_handler = GoogleSheetsHandler()
            self.drive_handler = GoogleDriveHandler()
            self.bill_analyzer = BillAnalyzer()
            self.logger.info("帳單分析器初始化成功")
        except Exception as e:
            self.logger.error(f"帳單分析器初始化失敗: {e}")
            raise
        
        # 定時任務設定
        self.analysis_time = "03:30"  # 每日分析時間
        self.notification_time = "15:15"  # 每日推播時間
        
        # 防重複執行標記
        self.last_analysis_date = None
        self.last_notification_date = None
        
        self.scheduler_thread = None

    def get_notification_user_id(self):
        """從現有提醒系統獲取用戶 ID"""
        return self.reminder_bot.user_settings.get('user_id')
    
    def start_scheduler(self):
        """啟動定時任務"""
        if self.scheduler_thread is None or not self.scheduler_thread.is_alive():
            self.scheduler_thread = threading.Thread(target=self._scheduler_loop, daemon=True)
            self.scheduler_thread.start()
            self.logger.info("帳單分析定時任務已啟動")
            return True
        return False
    
    def _scheduler_loop(self):
        """主定時循環"""
        while True:
            try:
                taiwan_now = get_taiwan_datetime()
                current_time = get_taiwan_time_hhmm()
                today_date = taiwan_now.strftime('%Y-%m-%d')
                
                self.logger.debug(f"定時任務檢查 - 台灣時間: {taiwan_now.strftime('%Y-%m-%d %H:%M:%S')}")
                
                # 檢查是否需要執行帳單分析 (03:30 測試時間)
                if (current_time == self.analysis_time and 
                    self.last_analysis_date != today_date):
                    self.logger.info("開始執行每日帳單分析任務")
                    self._run_daily_analysis()
                    self.last_analysis_date = today_date
                
                # 檢查是否需要執行推播任務 (15:15 測試時間)
                elif (current_time == self.notification_time and 
                      self.last_notification_date != today_date):
                    self.logger.info("開始執行每日推播任務")
                    self._run_daily_notifications()
                    self.last_notification_date = today_date
                
                # 每分鐘檢查一次
                time.sleep(60)
                
            except Exception as e:
                self.logger.error(f"定時任務循環錯誤: {e}")
                time.sleep(60)
    
    def _run_daily_analysis(self):
        """執行每日帳單分析任務"""
        try:
            self.logger.info("=== 開始每日帳單分析 ===")
            
            # 1. 從 Google Sheets 讀取待處理檔案
            pending_files = self.sheets_handler.get_pending_files()
            self.logger.info(f"找到 {len(pending_files)} 個待處理檔案")
            
            if not pending_files:
                self.logger.info("沒有待處理檔案，分析任務結束")
                return
            
            # 2. 逐個處理檔案
            processed_count = 0
            failed_count = 0
            
            for file_info in pending_files:
                try:
                    self.logger.info(f"處理檔案: {file_info['filename']}")
                    
                    # 下載檔案
                    file_content = self.drive_handler.download_file(
                        file_info['file_id'], 
                        file_info['filename']
                    )
                    
                    if not file_content:
                        self._update_file_failed(file_info, "檔案下載失敗")
                        failed_count += 1
                        continue
                    
                    # 取得銀行設定
                    bank_config = self.sheets_handler.get_bank_config_by_filename(
                        file_info['filename']
                    )
                    
                    if not bank_config:
                        self._update_file_failed(file_info, "找不到銀行設定")
                        failed_count += 1
                        continue
                    
                    # 執行分析
                    analysis_result = self.bill_analyzer.analyze_pdf(
                        file_content, 
                        bank_config, 
                        file_info['filename']
                    )
                    
                    # 更新結果
                    if analysis_result['success']:
                        self.sheets_handler.update_file_status(
                            file_info['row_index'], 
                            '已完成', 
                            analysis_result['data']
                        )
                        processed_count += 1
                        self.logger.info(f"檔案處理成功: {file_info['filename']}")
                    else:
                        self._update_file_failed(file_info, analysis_result['error'])
                        failed_count += 1
                
                except Exception as e:
                    self.logger.error(f"處理檔案失敗 {file_info['filename']}: {e}")
                    self._update_file_failed(file_info, f"處理異常: {str(e)}")
                    failed_count += 1
                
                # 避免 API 頻率限制
                time.sleep(2)
            
            self.logger.info(f"=== 每日分析完成 - 成功: {processed_count}, 失敗: {failed_count} ===")
            
        except Exception as e:
            self.logger.error(f"每日分析任務執行失敗: {e}")
    
    def _update_file_failed(self, file_info, error_message):
        """更新檔案為失敗狀態"""
        try:
            self.sheets_handler.update_file_status(
                file_info['row_index'], 
                '解析失敗'
            )
            self.logger.error(f"檔案處理失敗 {file_info['filename']}: {error_message}")
        except Exception as e:
            self.logger.error(f"更新失敗狀態失敗: {e}")
    
    def _run_daily_notifications(self):
        """執行每日推播任務"""
        try:
            self.logger.info("=== 開始每日推播任務 ===")
            
            # 從現有系統獲取用戶 ID
            notification_user_id = self.get_notification_user_id()
            
            if not notification_user_id:
                self.logger.warning("未設定推播對象，跳過推播任務")
                return
            
            # 1. 檢查解析失敗的檔案
            failed_files = self.sheets_handler.get_failed_files()
            if failed_files:
                self._send_failed_notification(failed_files, notification_user_id)
            
            # 2. 檢查需要推播的成功檔案
            success_files = self.sheets_handler.get_notification_pending_files()
            if success_files:
                self._send_success_notifications(success_files, notification_user_id)
            
            self.logger.info("=== 每日推播任務完成 ===")
            
        except Exception as e:
            self.logger.error(f"每日推播任務執行失敗: {e}")
    
    def _send_failed_notification(self, failed_files, notification_user_id):
        """發送解析失敗通知"""
        try:
            message = f"❌ 帳單解析失敗通知\n\n共 {len(failed_files)} 個檔案處理失敗：\n\n"
            
            for i, file_info in enumerate(failed_files[:5], 1):  # 最多顯示5個
                filename = file_info['filename']
                bank_code = filename.split('_')[0] if '_' in filename else '未知'
                message += f"{i}. {bank_code} - {filename}\n"
            
            if len(failed_files) > 5:
                message += f"\n...還有 {len(failed_files) - 5} 個檔案\n"
            
            message += f"\n💡 系統將在明天再次嘗試處理"
            message += f"\n🕒 {get_taiwan_time_hhmm()}"
            
            send_push_message(notification_user_id, message)
            self.logger.info(f"已發送失敗通知，共 {len(failed_files)} 個檔案")
            
        except Exception as e:
            self.logger.error(f"發送失敗通知錯誤: {e}")
    
    def _send_success_notifications(self, success_files, notification_user_id):
        """發送成功分析通知（修改版，包含帳單金額同步）"""
        try:
            for file_info in success_files:
                try:
                    if file_info.get('analysis_result'):
                        analysis_data = json.loads(file_info['analysis_result'])
                        
                        # 原本的推播邏輯
                        message = self._format_analysis_message(
                            file_info['filename'], 
                            analysis_data
                        )
                        send_push_message(notification_user_id, message)
                        
                        # 🆕 新增：如果是信用卡帳單，同步金額到提醒系統
                        if analysis_data.get('document_type') != "交割憑單":
                            self._sync_bill_amount_to_reminder(analysis_data, file_info['filename'])
                        
                        # 原本的狀態更新
                        self.sheets_handler.update_notification_status(
                            file_info['row_index'], 
                            '已推播'
                        )
                        
                        self.logger.info(f"已推播帳單分析結果: {file_info['filename']}")
                        time.sleep(1)  # 避免推播過快
                    
                except Exception as e:
                    self.logger.error(f"推播單個檔案失敗 {file_info['filename']}: {e}")
                    self.sheets_handler.update_notification_status(
                        file_info['row_index'], 
                        '推播失敗'
                    )
                    
        except Exception as e:
            self.logger.error(f"發送成功通知錯誤: {e}")
    
    def _sync_bill_amount_to_reminder(self, analysis_data, filename):
        """🆕 新增：將帳單金額同步到提醒系統"""
        try:
            result = analysis_data.get('analysis_result', {})
            bank_name = analysis_data.get('bank_name', '')
            total_due = result.get('total_amount_due', '')
            due_date = result.get('payment_due_date', '')
            statement_date = result.get('statement_date', '')
            
            if bank_name and total_due and due_date:
                # 呼叫提醒系統的儲存函數
                success = self.reminder_bot.update_bill_amount(
                    bank_name, 
                    total_due, 
                    due_date,
                    statement_date
                )
                
                if success:
                    self.logger.info(f"✅ 同步帳單金額成功: {bank_name} - {total_due}")
                else:
                    self.logger.error(f"❌ 同步帳單金額失敗: {bank_name}")
            else:
                missing_fields = []
                if not bank_name:
                    missing_fields.append('bank_name')
                if not total_due:
                    missing_fields.append('total_amount_due')
                if not due_date:
                    missing_fields.append('payment_due_date')
                
                self.logger.warning(f"⚠️ 同步帳單金額跳過，缺少欄位: {missing_fields} - 檔案: {filename}")
                
        except Exception as e:
            self.logger.error(f"❌ 同步帳單金額異常: {e} - 檔案: {filename}")
    
    def _format_analysis_message(self, filename, analysis_data):
        """格式化分析結果訊息"""
        try:
            bank_code = filename.split('_')[0] if '_' in filename else '未知銀行'
            result = analysis_data.get('analysis_result', {})
            document_type = analysis_data.get('document_type', '未知類型')
            bank_name = analysis_data.get('bank_name', bank_code)
            
            if document_type == "交割憑單":
                return self._format_trading_message(filename, bank_name, result)
            else:
                return self._format_credit_card_message(filename, bank_name, result)
                
        except Exception as e:
            self.logger.error(f"格式化訊息失敗: {e}")
            return f"💳 帳單分析完成\n\n📄 檔案: {filename}\n❌ 格式化失敗，請查看詳細資料"
    
    def _format_trading_message(self, filename, bank_name, result):
        """格式化交割憑單訊息"""
        message = f"📈 交割憑單分析完成\n\n🏦 {bank_name}\n📄 {filename}\n\n"
        
        if isinstance(result, list):
            message += f"共 {len(result)} 筆交易:\n\n"
            for i, trade in enumerate(result[:3], 1):
                message += self._format_single_trade(i, trade)
            
            if len(result) > 3:
                message += f"...還有 {len(result) - 3} 筆交易\n"
        else:
            message += self._format_single_trade(1, result)
        
        return message
    
    def _format_single_trade(self, index, trade):
        """格式化單筆交易"""
        text = f"{index}. "
        
        category = trade.get('category', '')
        if category:
            text += f"{'📈' if category == '買進' else '📉'} {category} "
        
        stock_name = trade.get('stock_name', '')
        stock_code = trade.get('stock_code', '')
        if stock_name or stock_code:
            text += f"{stock_name} ({stock_code}) "
        
        quantity = trade.get('quantity', '')
        price = trade.get('price', '')
        if quantity and price:
            text += f"{quantity}股 @ {price}"
        
        total_amount = trade.get('total_amount', '')
        if total_amount:
            text += f"\n💰 {total_amount}"
        
        return text + "\n\n"
    
    def _format_credit_card_message(self, filename, bank_name, result):
        """格式化信用卡帳單訊息 - 改良版（顯示前30筆明細）+ 同步提示"""
        message = f"💳 信用卡帳單分析完成\n\n🏦 {bank_name}\n📄 {filename}\n\n"
        
        total_due = result.get('total_amount_due', '')
        min_payment = result.get('minimum_payment', '')
        due_date = result.get('payment_due_date', '')
        
        if total_due:
            message += f"💰 本期應繳: {total_due}\n"
        if min_payment:
            message += f"💳 最低應繳: {min_payment}\n"
        if due_date:
            message += f"⏰ 繳款期限: {due_date}\n"
        
        # 🆕 新增同步提示
        if total_due and due_date:
            message += f"📊 已同步到提醒系統，下次提醒會顯示具體金額\n"
        
        transactions = result.get('transactions', [])
        if transactions:
            message += f"🛍️ 消費筆數: {len(transactions)}筆\n"
            
            # 顯示前30筆交易（從原本的8筆增加）
            display_count = min(30, len(transactions))
            message += f"\n消費明細 (前{display_count}筆):\n"
            
            for i, trans in enumerate(transactions[:30], 1):
                date = trans.get('date', '')
                merchant = trans.get('merchant', '')
                amount = trans.get('amount', '')
                
                if date or merchant or amount:
                    message += f"{i}. "
                    if date:
                        message += f"{date} "
                    if merchant:
                        # 限制商家名稱長度避免訊息過長
                        merchant_display = merchant[:25] + "..." if len(merchant) > 25 else merchant
                        message += f"{merchant_display} "
                    if amount:
                        message += f"{amount}"
                    message += "\n"
            
            # 如果還有更多交易，顯示提示
            if len(transactions) > 30:
                remaining = len(transactions) - 30
                message += f"\n📋 還有 {remaining} 筆交易未顯示"
                message += f"\n💡 如需查看完整明細，請聯繫系統管理員"
        
        return message
    
    def get_status(self):
        """獲取定時任務狀態"""
        return {
            'scheduler_running': self.scheduler_thread is not None and self.scheduler_thread.is_alive(),
            'analysis_time': self.analysis_time,
            'notification_time': self.notification_time,
            'last_analysis_date': self.last_analysis_date,
            'last_notification_date': self.last_notification_date,
            'notification_enabled': self.get_notification_user_id() is not None
        }
