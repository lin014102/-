"""
信用卡帳單分析器 - 改進版
採用第一份代碼的成功策略：簡潔 prompt + 重試機制 + Gemini 2.5
"""

import os
import json
import base64
import requests
import PyPDF2
import fitz  # PyMuPDF
from PIL import Image
import io
import logging
import time
from datetime import datetime
import re
import tempfile

class BillAnalyzer:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.setup_apis()
        
        # 處理設定
        self.settings = {
            "dpi": 300,
            "remove_last_page": True,
        }
        
        # 銀行識別規則
        self.bank_patterns = {
            "星展銀行": ["星展", "DBS", "DBS Bank", "DBS BANK"],
            "台新銀行": ["台新", "TAISHIN", "台新銀行", "TAISHIN BANK"],
            "永豐銀行": ["永豐", "SinoPac", "永豐銀行", "SINOPAC"],
            "國泰世華": ["國泰", "CATHAY", "國泰世華", "CATHAY UNITED BANK"],
            "聯邦銀行": ["聯邦", "UNION", "聯邦銀行", "UNION BANK"]
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
            
            # 4. 處理 OCR 結果 - 採用座標重組方式
            processed_text = self.process_ocr_with_coordinates(ocr_results)
            if not processed_text:
                raise Exception("文字處理失敗")
            
            # 5. 清理中文空格
            cleaned_text = self.clean_chinese_spacing(processed_text)
            
            self.logger.info(f"OCR 處理完成，文字長度: {len(cleaned_text)}")
            
            # 6. 識別文件類型
            document_type = self.identify_document_type(cleaned_text, filename)
            
            # 7. 識別銀行
            bank_name = bank_config.get('name', '') or self.identify_bank(cleaned_text)
            
            # 8. LLM 分析（採用第一份代碼的策略）
            analysis_result = self.gemini_analyze(cleaned_text, bank_name, document_type)
            
            if not analysis_result:
                raise Exception("LLM 分析失敗")
            
            self.logger.info(f"帳單分析成功: {filename}")
            return {
                'success': True,
                'data': {
                    'document_type': document_type,
                    'bank_name': bank_name,
                    'analysis_result': analysis_result,
                    'raw_text_length': len(cleaned_text)
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
        """將PDF轉換成圖片"""
        try:
            self.logger.info(f"開始轉換 PDF: {pdf_path}")
            
            pdf_document = fitz.open(pdf_path)
            
            if pdf_document.needs_pass:
                if not pdf_document.authenticate(password):
                    raise Exception("PDF 密碼錯誤")
                self.logger.info("PDF 解鎖成功")
            
            images = []
            page_count = pdf_document.page_count
            
            # 決定要處理的頁面範圍（移除最後一頁）
            end_page = page_count - 1 if self.settings["remove_last_page"] and page_count > 1 else page_count
            
            self.logger.info(f"PDF 共 {page_count} 頁，處理前 {end_page} 頁")
            
            temp_dir = tempfile.gettempdir()
            for page_num in range(end_page):
                page = pdf_document[page_num]
                mat = fitz.Matrix(self.settings["dpi"]/72, self.settings["dpi"]/72)
                pix = page.get_pixmap(matrix=mat)
                
                img_data = pix.tobytes("png")
                image = Image.open(io.BytesIO(img_data))
                
                temp_path = os.path.join(temp_dir, f"page_{page_num + 1}_{datetime.now().timestamp()}.png")
                image.save(temp_path, "PNG", quality=95)
                images.append(temp_path)
                
                self.logger.info(f"頁面 {page_num + 1} 轉換完成")
            
            pdf_document.close()
            self.logger.info(f"PDF 轉圖片完成，共 {len(images)} 張")
            return images
            
        except Exception as e:
            self.logger.error(f"PDF 轉圖片失敗: {e}")
            return []
    
    def image_to_base64(self, image_path):
        """將圖片轉換成 base64"""
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    
    def ocr_with_vision_api(self, image_path):
        """使用 Google Vision REST API 進行 OCR"""
        try:
            self.logger.info(f"開始 OCR 處理: {os.path.basename(image_path)}")
            
            url = f"https://vision.googleapis.com/v1/images:annotate?key={self.vision_api_key}"
            image_base64 = self.image_to_base64(image_path)
            
            request_body = {
                "requests": [{
                    "image": {"content": image_base64},
                    "features": [{"type": "DOCUMENT_TEXT_DETECTION"}],
                    "imageContext": {"languageHints": ["zh-TW", "en"]}
                }]
            }
            
            headers = {"Content-Type": "application/json"}
            response = requests.post(url, headers=headers, json=request_body, timeout=60)
            
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
    
    def is_chinese_char(self, char):
        """判斷是否為中文字符"""
        if not char:
            return False
        return '\u4e00' <= char[0] <= '\u9fff'
    
    def merge_words_intelligently(self, words):
        """智慧合併單詞，減少不必要的空格"""
        if not words:
            return ""
        
        result = []
        i = 0
        
        while i < len(words):
            current_word = words[i]
            
            if len(current_word) == 1 and self.is_chinese_char(current_word):
                combined = current_word
                j = i + 1
                
                while j < len(words) and len(words[j]) <= 2:
                    if self.is_chinese_char(words[j]) or words[j].isalpha():
                        combined += words[j]
                        j += 1
                    else:
                        break
                
                result.append(combined)
                i = j
            else:
                result.append(current_word)
                i += 1
        
        return ' '.join(result)
    
    def process_ocr_with_coordinates(self, ocr_results):
        """處理OCR結果，依據座標重組段落（採用第一份代碼的方法）"""
        try:
            processed_text = ""
            
            for page_idx, result in enumerate(ocr_results):
                if not result or 'responses' not in result or not result['responses']:
                    continue
                
                response = result['responses'][0]
                
                if "fullTextAnnotation" not in response:
                    continue
                
                full_text = response["fullTextAnnotation"]
                
                if "pages" in full_text:
                    for page in full_text["pages"]:
                        blocks = []
                        
                        if "blocks" in page:
                            for block in page["blocks"]:
                                if "paragraphs" in block:
                                    for paragraph in block["paragraphs"]:
                                        if "boundingBox" in paragraph:
                                            vertices = paragraph["boundingBox"]["vertices"]
                                            y_coord = vertices[0].get("y", 0)
                                            x_coord = vertices[0].get("x", 0)
                                        else:
                                            y_coord = 0
                                            x_coord = 0
                                        
                                        paragraph_text = ""
                                        if "words" in paragraph:
                                            words = []
                                            for word in paragraph["words"]:
                                                if "symbols" in word:
                                                    word_text = ""
                                                    for symbol in word["symbols"]:
                                                        if "text" in symbol:
                                                            word_text += symbol["text"]
                                                    if word_text.strip():
                                                        words.append(word_text.strip())
                                            
                                            if words:
                                                paragraph_text = self.merge_words_intelligently(words)
                                        
                                        blocks.append({
                                            "text": paragraph_text.strip(),
                                            "y": y_coord,
                                            "x": x_coord
                                        })
                        
                        blocks.sort(key=lambda b: (b["y"], b["x"]))
                        
                        page_text = ""
                        for block in blocks:
                            if block["text"]:
                                page_text += block["text"] + "\n"
                        
                        if page_text:
                            processed_text += f"\n=== 第 {page_idx + 1} 頁 ===\n{page_text}"
            
            # 基本預處理
            lines = processed_text.split('\n')
            cleaned_lines = []
            
            for line in lines:
                line = line.strip()
                if line and len(line) > 1:
                    cleaned_lines.append(line)
            
            return '\n'.join(cleaned_lines)
            
        except Exception as e:
            self.logger.error(f"座標處理失敗: {e}")
            return ""
    
    def clean_chinese_spacing(self, text):
        """清理中文詞彙間不必要的空格"""
        try:
            cleaned = re.sub(r'([\u4e00-\u9fff])\s+([\u4e00-\u9fff])', r'\1\2', text)
            cleaned = re.sub(r'\s+', ' ', cleaned)
            return cleaned
        except Exception as e:
            self.logger.error(f"清理中文空格失敗: {e}")
            return text
    
    def identify_document_type(self, text, filename):
        """識別文件類型"""
        text_upper = text.upper()
        filename_upper = filename.upper()
        
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
    
    def gemini_analyze(self, text, bank_name, document_type):
        """
        使用 Gemini 2.5 分析文字 - 採用第一份代碼的成功策略
        包含：簡潔 prompt + 重試機制 + 強硬語氣
        """
        self.logger.info(f"開始 Gemini 分析，文件類型: {document_type}")
        
        # 根據文件類型選擇 prompt
        if document_type == "交割憑單":
            prompt_text = self.create_trading_prompt(text)
        else:
            prompt_text = self.create_bill_prompt(text, bank_name)
        
        # 使用 Gemini 2.5 Flash
        url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
        headers = {
            "Content-Type": "application/json",
            "X-goog-api-key": self.gemini_api_key
        }
        
        payload = {
            "contents": [{"parts": [{"text": prompt_text}]}],
            "generationConfig": {"responseMimeType": "application/json"}
        }
        
        # 重試機制（採用第一份代碼的策略）
        max_retries = 5
        for retry in range(max_retries):
            try:
                response = requests.post(url, headers=headers, json=payload, timeout=60)
                response.raise_for_status()
                resp_json = response.json()
                
                # 檢查回應
                if 'candidates' not in resp_json or not resp_json['candidates']:
                    raise Exception("Gemini 回應為空")
                
                generated_text = resp_json["candidates"][0]["content"]["parts"][0]["text"]
                
                # 清理並解析 JSON
                json_text = self.clean_json_response(generated_text)
                result = json.loads(json_text)
                
                # 標準化格式
                result = self.normalize_response(result)
                
                self.logger.info(f"Gemini 分析成功（第 {retry + 1} 次嘗試）")
                return result
                
            except (requests.exceptions.RequestException, json.JSONDecodeError, KeyError) as e:
                self.logger.warning(f"Gemini API 第 {retry + 1} 次嘗試失敗: {e}")
                if retry < max_retries - 1:
                    wait_time = 2 ** retry
                    self.logger.info(f"等待 {wait_time} 秒後重試...")
                    time.sleep(wait_time)
                else:
                    self.logger.error("Gemini 分析失敗，已達最大重試次數")
        
        return None
    
    def create_trading_prompt(self, text):
        """建立交割憑單分析提示詞 - 簡潔版"""
        return f"""
分析以下交割憑單內容並提取重要資訊：

{text}

【嚴格要求】
1. 只能回傳純JSON格式，禁止任何解釋文字
2. 不可使用markdown標記如```json```
3. 直接以{{開始，以}}結束
4. 禁止回傳任何"以下是"、"根據"等開頭語句

單筆交易JSON結構：
{{
  "category": "類別",
  "stock_code": "股票代碼",
  "stock_name": "股票名稱",
  "quantity": 數字,
  "price": 數字,
  "amount": 數字,
  "commission": 數字,
  "tax": 數字,
  "total_amount": 數字
}}

多筆交易回傳陣列格式：[{{}}, {{}}, ...]

立即回傳JSON，不要任何其他內容：
"""
    
    def create_bill_prompt(self, text, bank_name):
        """建立信用卡帳單分析提示詞 - 簡潔強硬版（採用第一份代碼風格）"""
        return f"""
分析以下信用卡帳單內容並提取重要資訊：

{text}

【嚴格要求】
1. 只能回傳純JSON格式，禁止任何解釋文字
2. 不可使用markdown標記如```json```
3. 直接以{{開始，以}}結束
4. 所有日期格式統一為：YYYY/MM/DD（西元年）
5. 民國年請轉換：114年=2025年，113年=2024年
6. 禁止回傳任何"以下是"、"根據"等開頭語句

JSON結構（必須嚴格遵守）：
{{
  "bank_name": "銀行名稱",
  "card_type": "卡片類型或null",
  "statement_period": "帳單期間或null",
  "statement_date": "YYYY/MM/DD或null",
  "payment_due_date": "YYYY/MM/DD或null",
  "previous_balance": 數字或null,
  "payment_received": 數字或null,
  "current_charges": 數字或null,
  "total_amount_due": 數字或null,
  "minimum_payment": 數字或null,
  "transactions": [
    {{
      "date": "YYYY/MM/DD",
      "merchant": "完整商家名稱",
      "amount": 數字,
      "currency": "TWD"
    }}
  ]
}}

立即回傳JSON，不要任何其他內容：
"""
    
    def clean_json_response(self, generated_text):
        """清理 JSON 回應（採用第一份代碼的方法）"""
        json_text = generated_text.strip()
        
        # 移除 markdown 標記
        if json_text.startswith('```json'):
            json_text = json_text[7:]
        elif json_text.startswith('```'):
            json_text = json_text[3:]
        if json_text.endswith('```'):
            json_text = json_text[:-3]
        
        # 尋找 JSON 開始和結束
        json_start = json_text.find('{')
        json_end = json_text.rfind('}')
        
        if json_start >= 0 and json_end > json_start:
            json_text = json_text[json_start:json_end + 1]
        
        return json_text.strip()
    
    def normalize_date(self, date_str):
        """標準化日期格式為 YYYY/MM/DD"""
        if not date_str or date_str == "null":
            return None
        
        try:
            # 民國年格式 114/MM/DD
            if re.match(r'^\d{3}/\d{1,2}/\d{1,2}$', date_str):
                parts = date_str.split('/')
                year = int(parts[0]) + 1911
                month = parts[1].zfill(2)
                day = parts[2].zfill(2)
                return f"{year}/{month}/{day}"
            
            # MM/DD 格式（假設 2025 年）
            elif re.match(r'^\d{1,2}/\d{1,2}$', date_str):
                parts = date_str.split('/')
                month = parts[0].zfill(2)
                day = parts[1].zfill(2)
                return f"2025/{month}/{day}"
            
            # 已經是 YYYY/MM/DD 格式
            elif re.match(r'^\d{4}/\d{1,2}/\d{1,2}$', date_str):
                parts = date_str.split('/')
                year = parts[0]
                month = parts[1].zfill(2)
                day = parts[2].zfill(2)
                return f"{year}/{month}/{day}"
            
            return date_str
            
        except Exception as e:
            self.logger.error(f"日期標準化失敗: {e}")
            return date_str
    
    def normalize_currency(self, currency_str):
        """標準化幣別"""
        if not currency_str:
            return "TWD"
        
        currency_map = {
            'TW': 'TWD',
            'JP': 'JPY',
            'US': 'USD',
            'tw': 'TWD',
            'jp': 'JPY',
            'us': 'USD'
        }
        return currency_map.get(currency_str, currency_str)
    
    def normalize_response(self, data):
        """標準化回應格式（採用第一份代碼的方法）"""
        try:
            if not data:
                return data
            
            # 處理日期欄位
            date_fields = ['payment_due_date', 'statement_date']
            for field in date_fields:
                if field in data and data[field]:
                    data[field] = self.normalize_date(data[field])
            
            # 處理交易明細
            if 'transactions' in data and isinstance(data['transactions'], list):
                for transaction in data['transactions']:
                    if 'date' in transaction and transaction['date']:
                        transaction['date'] = self.normalize_date(transaction['date'])
                    
                    if 'currency' in transaction and transaction['currency']:
                        transaction['currency'] = self.normalize_currency(transaction['currency'])
                    else:
                        transaction['currency'] = 'TWD'
                    
                    # 清理商家名稱
                    if 'merchant' in transaction and transaction['merchant']:
                        merchant = transaction['merchant'].strip()
                        if merchant.startswith('null '):
                            merchant = merchant[5:]
                        transaction['merchant'] = ' '.join(merchant.split())
            
            return data
            
        except Exception as e:
            self.logger.error(f"標準化回應失敗: {e}")
            return data
    
    def cleanup_temp_files(self, file_paths):
        """清理暫存檔案"""
        for file_path in file_paths:
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    self.logger.info(f"清理暫存檔案: {os.path.basename(file_path)}")
                except Exception as e:
                    self.logger.error(f"清理暫存檔案失敗: {e}")
