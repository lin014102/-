"""
bill_scheduler.py - 信用卡帳單自動分析定時任務 + 帳單金額同步 (完整修正版)
負責每日 03:30 分析帳單，15:15 推播結果，並同步金額到提醒系統
支援民國年日期轉換和完整金額格式處理
修正日期顯示 null 和商家名稱截斷問題
"""

import os
import json
import threading
import time
import logging
import re
from datetime import datetime, timedelta
from google_sheets_handler import GoogleSheetsHandler
from google_drive_handler import GoogleDriveHandler
from bill_analyzer import BillAnalyzer
from utils.time_utils import get_taiwan_datetime, get_taiwan_time_hhmm, TAIWAN_TZ
from utils.line_api import send_push_message


class BillScheduler:
    """信用卡帳單分析定時任務管理器 + 帳單金額同步 (完整修正版)"""
    
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
        self.analysis_time = "17:12"  # 每日分析時間
        self.notification_time = "17:15"  # 每日推播時間
        
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
                
                # 檢查是否需要執行帳單分析 (17:12)
                if (current_time == self.analysis_time and 
                    self.last_analysis_date != today_date):
                    self.logger.info("開始執行每日帳單分析任務")
                    self._run_daily_analysis()
                    self.last_analysis_date = today_date
                
                # 檢查是否需要執行推播任務 (17:15)
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
        """發送成功分析通知（完整整合版 - 包含帳單金額同步到提醒系統）"""
        try:
            sync_success_count = 0
            sync_failed_count = 0
            
            for file_info in success_files:
                try:
                    if file_info.get('analysis_result'):
                        analysis_data = json.loads(file_info['analysis_result'])
                        
                        # 1. 原本的推播邏輯
                        message = self._format_analysis_message(
                            file_info['filename'], 
                            analysis_data
                        )
                        send_push_message(notification_user_id, message)
                        
                        # 2. 如果是信用卡帳單，同步金額到提醒系統（修正版）
                        if analysis_data.get('document_type') != "交割憑單":
                            sync_result = self._sync_bill_amount_to_reminder(
                                analysis_data, 
                                file_info['filename']
                            )
                            if sync_result['success']:
                                sync_success_count += 1
                            else:
                                sync_failed_count += 1
                        
                        # 3. 原本的狀態更新
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
                    sync_failed_count += 1
            
            # 統計同步結果
            if sync_success_count > 0 or sync_failed_count > 0:
                self.logger.info(f"📊 帳單金額同步統計 - 成功: {sync_success_count}, 失敗: {sync_failed_count}")
                    
        except Exception as e:
            self.logger.error(f"發送成功通知錯誤: {e}")
    
    def _sync_bill_amount_to_reminder(self, analysis_data, filename):
        """完整修正版：將帳單金額同步到提醒系統，支援民國年和金額格式處理"""
        try:
            self.logger.info(f"🔄 開始同步帳單金額: {filename}")
            
            # 1. 提取分析結果
            result = analysis_data.get('analysis_result', {})
            bank_name = analysis_data.get('bank_name', '')
            total_due = result.get('total_amount_due', '')
            due_date = result.get('payment_due_date', '')
            statement_date = result.get('statement_date', '')
            
            # 2. 資料完整性檢查
            missing_fields = []
            if not bank_name:
                missing_fields.append('bank_name')
            if not total_due:
                missing_fields.append('total_amount_due')
            if not due_date:
                missing_fields.append('payment_due_date')
            
            if missing_fields:
                error_msg = f"缺少必要欄位: {missing_fields}"
                self.logger.warning(f"⚠️ 同步帳單金額跳過 - {error_msg} - 檔案: {filename}")
                return {
                    'success': False,
                    'error': error_msg,
                    'missing_fields': missing_fields
                }
            
            # 3. 資料格式標準化（修正版）
            normalized_data = self._normalize_bill_data(bank_name, total_due, due_date, statement_date)
            
            if not normalized_data['success']:
                self.logger.error(f"❌ 資料格式化失敗: {normalized_data['error']} - 檔案: {filename}")
                return normalized_data
            
            # 4. 呼叫提醒系統的儲存函數
            success = self.reminder_bot.update_bill_amount(
                normalized_data['bank_name'], 
                normalized_data['amount'], 
                normalized_data['due_date'],
                normalized_data['statement_date']
            )
            
            if success:
                self.logger.info(f"✅ 同步帳單金額成功: {normalized_data['bank_name']} - {normalized_data['amount']} - 截止: {normalized_data['due_date']}")
                return {
                    'success': True,
                    'bank_name': normalized_data['bank_name'],
                    'amount': normalized_data['amount'],
                    'due_date': normalized_data['due_date']
                }
            else:
                error_msg = f"MongoDB 寫入失敗"
                self.logger.error(f"❌ 同步帳單金額失敗: {error_msg} - {normalized_data['bank_name']}")
                return {
                    'success': False,
                    'error': error_msg
                }
                
        except Exception as e:
            error_msg = f"同步異常: {str(e)}"
            self.logger.error(f"❌ 同步帳單金額異常: {error_msg} - 檔案: {filename}")
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'error': error_msg
            }
    
    def _normalize_bill_data(self, bank_name, total_due, due_date, statement_date=None):
        """標準化帳單資料格式（完全修正版 - 支援民國年和完整金額處理）"""
        try:
            # 1. 銀行名稱標準化 (使用 ReminderBot 的方法)
            normalized_bank = self.reminder_bot._normalize_bank_name(bank_name)
            
            # 2. 金額格式標準化（完整版）
            if isinstance(total_due, (int, float)):
                # 如果是數字，轉換為標準格式
                formatted_amount = f"NT${int(total_due):,}"
            else:
                # 如果是字串，進行完整清理和標準化
                amount_str = str(total_due).strip()
                
                # 移除所有空格
                amount_str = re.sub(r'\s+', '', amount_str)
                
                # 檢查是否已有貨幣符號
                if any(currency in amount_str.upper() for currency in ['NT$', 'TWD', '$']):
                    # 已有貨幣符號，提取數字部分重新格式化
                    numbers = re.findall(r'[\d,]+', amount_str)
                    if numbers:
                        clean_number = numbers[0].replace(',', '')
                        if clean_number.isdigit():
                            formatted_amount = f"NT${int(clean_number):,}"
                        else:
                            formatted_amount = amount_str
                    else:
                        formatted_amount = amount_str
                else:
                    # 沒有貨幣符號，只有數字和逗號
                    clean_number = re.sub(r'[^\d]', '', amount_str)
                    if clean_number.isdigit() and len(clean_number) > 0:
                        formatted_amount = f"NT${int(clean_number):,}"
                    else:
                        # 如果無法解析，至少加上前綴
                        formatted_amount = f"NT${amount_str}"
            
            # 3. 日期格式標準化（支援民國年）
            normalized_due_date = self._normalize_date_format(due_date)
            if not normalized_due_date or '/' not in normalized_due_date:
                return {
                    'success': False,
                    'error': f"無效的到期日格式: {due_date}"
                }
            
            normalized_statement_date = None
            if statement_date:
                normalized_statement_date = self._normalize_date_format(statement_date)
            
            return {
                'success': True,
                'bank_name': normalized_bank,
                'amount': formatted_amount,
                'due_date': normalized_due_date,
                'statement_date': normalized_statement_date
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f"資料標準化失敗: {str(e)}"
            }
    
    def _normalize_date_format(self, date_str):
        """統一日期格式為 YYYY/MM/DD，支援民國年轉換（完整版）- 增強錯誤處理"""
        if not date_str or str(date_str).lower() in ['null', 'none', '']:
            return None
        
        try:
            date_str = str(date_str).strip()
            
            # 檢查是否為民國年格式 (例如: 114/09/24, 114/9/24)
            if '/' in date_str:
                parts = date_str.split('/')
                if len(parts) == 3:
                    year_str = parts[0].strip()
                    month_str = parts[1].strip()
                    day_str = parts[2].strip()
                    
                    # 如果年份是 2-3 位數，可能是民國年
                    if len(year_str) <= 3 and year_str.isdigit():
                        roc_year = int(year_str)
                        # 民國年轉西元年 (民國元年 = 西元1912年)
                        # 合理的民國年範圍：1-200年 (西元1912-2112年)
                        if 1 <= roc_year <= 200:
                            west_year = roc_year + 1911
                            month = month_str.zfill(2)
                            day = day_str.zfill(2)
                            converted_date = f"{west_year}/{month}/{day}"
                            self.logger.debug(f"民國年轉換: {date_str} -> {converted_date}")
                            return converted_date
                    
                    # 檢查是否已是西元年格式
                    elif len(year_str) == 4 and year_str.isdigit():
                        year = year_str
                        month = month_str.zfill(2)
                        day = day_str.zfill(2)
                        return f"{year}/{month}/{day}"
            
            # 嘗試各種標準日期格式
            date_formats = [
                '%Y/%m/%d',
                '%Y-%m-%d', 
                '%m/%d/%Y',
                '%d/%m/%Y'
            ]
            
            parsed_date = None
            for fmt in date_formats:
                try:
                    parsed_date = datetime.strptime(date_str, fmt)
                    break
                except ValueError:
                    continue
            
            if parsed_date:
                formatted_date = parsed_date.strftime('%Y/%m/%d')
                self.logger.debug(f"日期格式標準化: {date_str} -> {formatted_date}")
                return formatted_date
            else:
                self.logger.warning(f"無法解析日期格式，保持原樣: {date_str}")
                return str(date_str)  # 保持原樣
                
        except Exception as e:
            self.logger.error(f"日期格式化錯誤: {e} - 原始: {date_str}")
            return str(date_str)  # 保持原樣
    
    def _format_analysis_message(self, filename, analysis_data):
        """格式化分析結果訊息 (更新版 - 顯示同步狀態)"""
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
        """格式化信用卡帳單訊息 - 完全修正版（解決日期 null 和商家名稱截斷問題）"""
        message = f"💳 信用卡帳單分析完成\n🏦 {bank_name}\n📄 {filename}\n"
        
        total_due = result.get('total_amount_due', '')
        min_payment = result.get('minimum_payment', '')
        due_date = result.get('payment_due_date', '')
        
        if total_due:
            message += f"💰 本期應繳: {total_due}\n"
        if min_payment:
            message += f"💳 最低應繳: {min_payment}\n"
        if due_date:
            # 確保日期格式正確
            normalized_due_date = self._normalize_date_format(due_date)
            message += f"⏰ 繳款期限: {normalized_due_date}\n"
        
        # 顯示同步狀態
        if total_due and due_date:
            message += f"📊 ✅ 已同步到智能提醒系統\n"
            message += f"🔔 系統將在截止前自動提醒具體金額\n"
        else:
            message += f"⚠️ 部分資料不完整，可能影響提醒功能\n"
        
        transactions = result.get('transactions', [])
        if transactions:
            message += f"\n🛍️ 消費筆數: {len(transactions)}筆\n"
            
            # 顯示前20筆交易（格式：日期(西元) 商家名稱 金額）
            display_count = min(20, len(transactions))
            message += f"消費明細 (前{display_count}筆):\n"
            
            for i, trans in enumerate(transactions[:20], 1):
                date = trans.get('date', '')
                merchant = trans.get('merchant', '')
                amount = trans.get('amount', '')
                
                # 處理日期格式
                display_date = ''
                if date and date.lower() != 'null':
                    normalized_date = self._normalize_date_format(date)
                    if normalized_date:
                        display_date = normalized_date
                
                # 處理商家名稱
                display_merchant = ''
                if merchant and merchant.lower() != 'null':
                    # 移除 null 前綴（如果有）
                    if merchant.startswith('null '):
                        merchant = merchant[5:]
                    # 清理多餘空格
                    merchant = ' '.join(merchant.split())
                    # 限制長度但不截斷重要資訊
                    display_merchant = merchant[:35] + "..." if len(merchant) > 35 else merchant
                
                # 處理金額
                display_amount = amount if amount else ''
                
                # 組合顯示 - 確保格式一致：日期 商家名稱 金額
                line_parts = []
                if display_date:
                    line_parts.append(display_date)
                if display_merchant:
                    line_parts.append(display_merchant)
                if display_amount:
                    line_parts.append(display_amount)
                
                if line_parts:
                    message += f"{i}. {' '.join(line_parts)}\n"
            
            # 如果還有更多交易，顯示提示
            if len(transactions) > 20:
                remaining = len(transactions) - 20
                message += f"\n📋 還有 {remaining} 筆交易未顯示"
        
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
