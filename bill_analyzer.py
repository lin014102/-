"""
信用卡帳單分析器 - 雲端版本
整合 Google Vision OCR + Gemini LLM 進行帳單解析
"""

import os
import json
import base64
import requests
# import fitz  # PyMuPDF - 暫時移除直到部署穩定
from PIL import Image
import io
import logging
from datetime import datetime
import re
import tempfile
import google.generativeai as genai

class BillAnalyzer:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.setup_apis()
        
        # 處理設定
        self.settings = {
            "dpi": 200,  # 圖片解析度
            "remove_last_page": True,  # 是否移除最後一頁
        }
        
        # 銀行識別規則
        self.bank_patterns = {
            "星展銀行": ["星展", "DBS", "DBS Bank", "DBS BANK"],
            "台新銀行": ["台新", "TAISHIN", "台新銀行", "TAISHIN BANK"],
            "永豐銀行": ["永豐", "SinoPac", "永豐銀行", "SINOPAC"],
            "國泰世華": ["國泰", "CATHAY", "國泰世華", "CATHAY UNITED BANK"]
        }
    
    def setup_apis(self):
        """設定各種 API"""
        try:
            # Google Vision API
            self.vision_api_key = os.getenv('GOOGLE_CLOUD_VISION_API_KEY')
            if not self.vision_api_key:
                raise ValueError("GOOGLE_CLOUD_VISION_API_KEY not found")
            
            # Gemini API
            self.gemini_api_key = os.getenv('GEMINI_API_KEY')
            if not self.gemini_api_key:
                raise ValueError("GEMINI_API_KEY not found")
            
            # 設定 Gemini
            genai.configure(api_key=self.gemini_api_key)
            self.gemini_model = genai.GenerativeModel('gemini-2.0-flash-exp')
            
            self.logger.info("API 設定完成")
            
        except Exception as e:
            self.logger.error(f"API 設定失敗: {e}")
            raise
    
    def analyze_pdf(self, pdf_content, bank_config, filename):
        """
        分析 PDF 帳單的完整流程
        
        Args:
            pdf_content: PDF 檔案內容 (bytes)
            bank_config: 銀行設定資訊
            filename: 檔案名稱
            
        Returns:
            dict: 分析結果，包含 success 和 data 或 error
        """
        self.logger.info(f"開始分析帳單: {filename}")
        
        temp_pdf_path = None
        temp_image_paths = []
        
        try:
            # 1. 儲存 PDF 到暫存檔案
            temp_pdf_path = self.save_temp_pdf(pdf_content, filename)
            if not temp_pdf_path:
                raise Exception("儲存暫存 PDF 失敗")
            
            # 2. PDF 轉圖片
            temp_image_paths = self.pdf_to_images(temp_pdf_path, bank_config.get('password', ''))
            if not temp_image_paths:
                raise Exception("PDF 轉圖片失敗")
            
            # 3. OCR 處理
            ocr_results = []
            for image_path in temp_image_paths:
                ocr_result = self.ocr_with_vision_api(image_path)
                if ocr_result:
                    ocr_results.append(ocr_result)
            
            if not ocr_results:
                raise Exception("OCR 處理失敗")
            
            # 4. 處理 OCR 結果
            processed_text = self.process_ocr_results(ocr_results)
            if not processed_text['raw_text']:
                raise Exception("文字處理失敗")
            
            # 5. 識別文件類型
            document_type = self.identify_document_type(processed_text['raw_text'], filename)
            
            # 6. 識別銀行
            bank_name = bank_config.get('name', '') or self.identify_bank(processed_text['raw_text'])
            
            # 7. LLM 分析
            analysis_result = self.analyze_with_gemini(
                processed_text['raw_text'], 
                bank_name, 
                document_type
            )
            
            if not analysis_result:
                raise Exception("LLM 分析失敗")
            
            self.logger.info(f"帳單分析成功: {filename}")
            return {
                'success': True,
                'data': {
                    'document_type': document_type,
                    'bank_name': bank_name,
                    'analysis_result': analysis_result,
                    'raw_text_length': len(processed_text['raw_text'])
                }
            }
            
        except Exception as e:
            self.logger.error(f"帳單分析失敗 {filename}: {e}")
            return {
                'success': False,
                'error': str(e)
            }
            
        finally:
            # 清理暫存檔案
            self.cleanup_temp_files([temp_pdf_path] + temp_image_paths)
    
    def save_temp_pdf(self, pdf_content, filename):
        """將 PDF 內容儲存到暫存檔案"""
        try:
            temp_dir = tempfile.gettempdir()
            temp_path = os.path.join(temp_dir, f"temp_{filename}")
            
            with open(temp_path, 'wb') as f:
                f.write(pdf_content)
            
            self.logger.info(f"PDF 儲存到暫存檔案: {temp_path}")
            return temp_path
            
        except Exception as e:
            self.logger.error(f"儲存暫存 PDF 失敗: {e}")
            return None
    
    def pdf_to_images(self, pdf_path, password=""):
        """將 PDF 轉換成圖片 - 暫時停用直到解決部署問題"""
        # 暫時停用 PDF 轉圖片功能，因為 PyMuPDF 在 Render 上有套件衝突
        # 可以先測試其他功能是否正常運作
        self.logger.warning("PDF 轉圖片功能暫時停用，等待部署問題解決")
        return []
        
        # 原本的程式碼留著，等部署穩定後再啟用
        # try:
        #     self.logger.info(f"開始轉換 PDF: {pdf_path}")
        #     
        #     # 開啟 PDF
        #     pdf_document = fitz.open(pdf_path)
        #     
        #     # 如果有密碼保護，嘗試解鎖
        #     if pdf_document.needs_pass:
        #         if not pdf_document.authenticate(password):
        #             raise Exception("PDF 密碼錯誤")
        #         self.logger.info("PDF 解鎖成功")
        #     
        #     images = []
        #     page_count = pdf_document.page_count
        #     
        #     # 決定要處理的頁面範圍
        #     end_page = page_count - 1 if self.settings["remove_last_page"] and page_count > 1 else page_count
        #     
        #     self.logger.info(f"PDF 共 {page_count} 頁，處理前 {end_page} 頁")
        #     
        #     # 轉換每一頁
        #     temp_dir = tempfile.gettempdir()
        #     for page_num in range(end_page):
        #         page = pdf_document[page_num]
        #         
        #         # 設定轉換參數
        #         mat = fitz.Matrix(self.settings["dpi"]/72, self.settings["dpi"]/72)
        #         pix = page.get_pixmap(matrix=mat)
        #         
        #         # 轉換成 PIL Image
        #         img_data = pix.tobytes("png")
        #         image = Image.open(io.BytesIO(img_data))
        #         
        #         # 儲存暫存圖片
        #         temp_path = os.path.join(temp_dir, f"page_{page_num + 1}_{datetime.now().timestamp()}.png")
        #         image.save(temp_path)
        #         images.append(temp_path)
        #         
        #         self.logger.info(f"頁面 {page_num + 1} 轉換完成")
        #     
        #     pdf_document.close()
        #     self.logger.info(f"PDF 轉圖片完成，共 {len(images)} 張")
        #     return images
        #     
        # except Exception as e:
        #     self.logger.error(f"PDF 轉圖片失敗: {e}")
        #     return []
    
    def image_to_base64(self, image_path):
        """將圖片轉換成 base64"""
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    
    def ocr_with_vision_api(self, image_path):
        """使用 Google Vision REST API 進行 OCR"""
        try:
            self.logger.info(f"開始 OCR 處理: {os.path.basename(image_path)}")
            
            url = f"https://vision.googleapis.com/v1/images:annotate?key={self.vision_api_key}"
            
            # 將圖片轉成 base64
            image_base64 = self.image_to_base64(image_path)
            
            # 請求 body
            request_body = {
                "requests": [
                    {
                        "image": {
                            "content": image_base64
                        },
                        "features": [
                            {
                                "type": "DOCUMENT_TEXT_DETECTION",
                                "maxResults": 1
                            }
                        ]
                    }
                ]
            }
            
            # 發送請求
            headers = {"Content-Type": "application/json"}
            response = requests.post(url, headers=headers, json=request_body)
            
            if response.status_code == 200:
                result = response.json()
                self.logger.info(f"OCR 處理成功: {os.path.basename(image_path)}")
                return result
            else:
                self.logger.error(f"Vision API 請求失敗: {response.status_code}")
                return None
                
        except Exception as e:
            self.logger.error(f"OCR 處理失敗: {e}")
            return None
    
    def process_ocr_results(self, ocr_results):
        """處理 OCR 結果，重組文字"""
        self.logger.info("處理 OCR 結果")
        
        all_text = ""
        
        try:
            for page_idx, result in enumerate(ocr_results):
                if not result or 'responses' not in result:
                    continue
                
                response = result['responses'][0]
                
                # 取得完整文字
                if 'fullTextAnnotation' in response:
                    page_text = response['fullTextAnnotation']['text']
                    all_text += f"\n=== 第 {page_idx + 1} 頁 ===\n{page_text}\n"
            
            self.logger.info("OCR 結果處理完成")
            return {
                'raw_text': all_text
            }
            
        except Exception as e:
            self.logger.error(f"OCR 結果處理失敗: {e}")
            return {'raw_text': ''}
    
    def identify_document_type(self, text, filename):
        """識別文件類型"""
        text_upper = text.upper()
        filename_upper = filename.upper()
        
        # 交割憑單關鍵字
        trading_keywords = ['交割', '憑單', '成交', '買進', '賣出', '證券', 'TRADING']
        
        if any(keyword in text_upper or keyword in filename_upper for keyword in trading_keywords):
            return "交割憑單"
        else:
            return "信用卡帳單"
    
    def identify_bank(self, text):
        """識別銀行類型"""
        text_upper = text.upper()
        
        for bank_name, patterns in self.bank_patterns.items():
            for pattern in patterns:
                if pattern.upper() in text_upper:
                    self.logger.info(f"識別銀行: {bank_name}")
                    return bank_name
        
        self.logger.warning("無法識別銀行，使用通用格式")
        return "未知銀行"
    
    def analyze_with_gemini(self, text, bank_name, document_type):
        """使用 Gemini 分析文字"""
        self.logger.info(f"開始 Gemini 分析，文件類型: {document_type}")
        
        try:
            if document_type == "交割憑單":
                prompt = self.create_trading_analysis_prompt(text)
            else:
                prompt = self.create_bill_analysis_prompt(text, bank_name)
            
            # 使用 Gemini API
            response = self.gemini_model.generate_content(prompt)
            
            if response and response.text:
                return self.parse_json_response(response.text)
            else:
                self.logger.error("Gemini 回應為空")
                return None
                
        except Exception as e:
            self.logger.error(f"Gemini 分析失敗: {e}")
            return None
    
    def create_trading_analysis_prompt(self, text):
        """建立交割憑單分析提示詞"""
        return f"""
請分析以下交割憑單內容，並以JSON格式回傳結構化資料。

如果憑單中包含多筆交易記錄，請回傳JSON陣列格式。
如果只有一筆交易記錄，請回傳單一JSON物件格式。

單筆交易的JSON格式：
{{
    "category": "類別",
    "stock_code": "股票代碼",
    "stock_name": "股票名稱", 
    "quantity": "數量",
    "price": "成交價",
    "amount": "價金",
    "commission": "手續費",
    "tax": "交易稅",
    "total_amount": "應付金額"
}}

注意事項:
1. 類別請填入"買進"或"賣出"
2. 金額請保留原始格式（包含逗號和貨幣符號）
3. 股票代碼通常是4-6位數字，如果找不到就填null
4. 數量請填入實際股數（數字）

交割憑單內容:
{text}

請務必回傳有效的JSON格式，不要包含其他說明文字或markdown語法。
"""
    
    def create_bill_analysis_prompt(self, text, bank_name):
        """建立信用卡帳單分析提示詞"""
        return f"""
請分析以下{bank_name}信用卡帳單內容，並以JSON格式回傳結構化資料。

請嚴格按照以下JSON格式回傳：

{{
    "bank_name": "{bank_name}",
    "card_type": "信用卡類型",
    "statement_period": "帳單期間",
    "statement_date": "結帳日",
    "payment_due_date": "繳款截止日", 
    "previous_balance": "上期應繳總金額",
    "payment_received": "已繳款金額",
    "current_charges": "本期金額合計",
    "total_amount_due": "本期應繳總金額",
    "minimum_payment": "本期最低應繳金額",
    "transactions": [
        {{
            "date": "交易日期",
            "merchant": "商家名稱", 
            "amount": "金額",
            "category": "消費類別"
        }}
    ]
}}

注意事項:
1. 金額請保留原始格式（包含逗號和貨幣符號）
2. 日期格式請統一為 YYYY/MM/DD
3. 如果是退款，金額請加上負號
4. 找不到的欄位填入null
5. 交易明細請按時間順序排列

帳單內容:
{text}

請務必回傳有效的JSON格式，不要包含其他說明文字或markdown語法。
"""
    
    def parse_json_response(self, content):
        """解析 LLM 回應中的 JSON 內容"""
        try:
            # 移除可能的 markdown 語法
            content = content.strip()
            if content.startswith('```json'):
                content = content[7:]
            if content.startswith('```'):
                content = content[3:]
            if content.endswith('```'):
                content = content[:-3]
            
            content = content.strip()
            
            # 嘗試直接解析 JSON
            analysis_result = json.loads(content)
            self.logger.info("JSON 解析成功")
            return analysis_result
                
        except json.JSONDecodeError as e:
            self.logger.error(f"JSON 解析失敗: {e}")
            
            # 嘗試提取 JSON 部分
            try:
                json_start_obj = content.find('{')
                json_start_arr = content.find('[')
                
                if json_start_obj >= 0 and (json_start_arr < 0 or json_start_obj < json_start_arr):
                    json_start = json_start_obj
                    json_end = content.rfind('}') + 1
                elif json_start_arr >= 0:
                    json_start = json_start_arr
                    json_end = content.rfind(']') + 1
                else:
                    return None
                
                if json_start >= 0 and json_end > json_start:
                    json_str = content[json_start:json_end]
                    analysis_result = json.loads(json_str)
                    self.logger.info("從混合內容中成功解析 JSON")
                    return analysis_result
                
            except json.JSONDecodeError:
                self.logger.error("無法從內容中提取有效的 JSON")
            
            return None
    
    def cleanup_temp_files(self, file_paths):
        """清理暫存檔案"""
        for file_path in file_paths:
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    self.logger.info(f"清理暫存檔案: {os.path.basename(file_path)}")
                except Exception as e:
                    self.logger.error(f"清理暫存檔案失敗: {e}")
