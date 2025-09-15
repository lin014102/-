"""
信用卡帳單分析器 - 雲端版本 (修正版)
整合 Google Vision OCR + Gemini LLM 進行帳單解析
修正日期顯示 null 和商家名稱截斷問題
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
            "dpi": 300,  # 提高解析度，改善 OCR 品質
            "remove_last_page": True,  # 是否移除最後一頁
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
            
            # 設定 Gemini
            genai.configure(api_key=self.gemini_api_key)
            self.gemini_model = genai.GenerativeModel('gemini-2.0-flash-exp')
            
            self.logger.info("API 設定完成")
            
        except Exception as e:
            self.logger.error(f"API 設定失敗: {e}")
            raise
    
    def analyze_pdf(self, pdf_content, bank_config, filename):
        """
        分析 PDF 帳單的完整流程 - 完整圖像處理版本
        
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
            
            # 輸出 OCR 原始結果到日誌 (調試用)
            self.logger.info(f"OCR 原始結果長度: {len(processed_text['raw_text'])}")
            self.logger.info(f"OCR 原始結果前500字元: {processed_text['raw_text'][:500]}")
            
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
            
            # 輸出 LLM 分析結果到日誌 (調試用)
            self.logger.info(f"LLM 分析結果: {json.dumps(analysis_result, ensure_ascii=False, indent=2)}")
            
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
        """將PDF轉換成圖片 - 完整功能版本"""
        try:
            self.logger.info(f"開始轉換 PDF: {pdf_path}")
            
            # 開啟 PDF
            pdf_document = fitz.open(pdf_path)
            
            # 如果有密碼保護，嘗試解鎖
            if pdf_document.needs_pass:
                if not pdf_document.authenticate(password):
                    raise Exception("PDF 密碼錯誤")
                self.logger.info("PDF 解鎖成功")
            
            images = []
            page_count = pdf_document.page_count
            
            # 決定要處理的頁面範圍
            end_page = page_count - 1 if self.settings["remove_last_page"] and page_count > 1 else page_count
            
            self.logger.info(f"PDF 共 {page_count} 頁，處理前 {end_page} 頁")
            
            # 轉換每一頁
            temp_dir = tempfile.gettempdir()
            for page_num in range(end_page):
                page = pdf_document[page_num]
                
                # 設定轉換參數 - 提高解析度
                mat = fitz.Matrix(self.settings["dpi"]/72, self.settings["dpi"]/72)
                pix = page.get_pixmap(matrix=mat)
                
                # 轉換成 PIL Image
                img_data = pix.tobytes("png")
                image = Image.open(io.BytesIO(img_data))
                
                # 儲存暫存圖片
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
                        ],
                        "imageContext": {
                            "languageHints": ["zh-TW", "en"]
                        }
                    }
                ]
            }
            
            # 發送請求
            headers = {"Content-Type": "application/json"}
            response = requests.post(url, headers=headers, json=request_body, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                self.logger.info(f"OCR 處理成功: {os.path.basename(image_path)}")
                return result
            else:
                self.logger.error(f"Vision API 請求失敗: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            self.logger.error(f"OCR 處理失敗: {e}")
            return None
    
    def process_ocr_results(self, ocr_results):
        """處理 OCR 結果，重組文字"""
        self.logger.info("處理 OCR 結果")
        
        all_text = ""
        structured_data = []
        
        try:
            for page_idx, result in enumerate(ocr_results):
                if not result or 'responses' not in result:
                    continue
                
                response = result['responses'][0]
                
                # 取得完整文字
                if 'fullTextAnnotation' in response:
                    page_text = response['fullTextAnnotation']['text']
                    all_text += f"\n=== 第 {page_idx + 1} 頁 ===\n{page_text}\n"
                
                # 取得結構化資料（包含座標）
                if 'textAnnotations' in response:
                    for annotation in response['textAnnotations'][1:]:  # 跳過第一個（全文）
                        text_info = {
                            'text': annotation['description'],
                            'confidence': annotation.get('confidence', 0),
                            'vertices': annotation['boundingPoly']['vertices'] if 'boundingPoly' in annotation else []
                        }
                        structured_data.append(text_info)
            
            # 根據座標重新排序（由上到下，由左到右）
            if structured_data:
                structured_data.sort(key=lambda x: (
                    x['vertices'][0]['y'] if x['vertices'] else 0,  # Y座標
                    x['vertices'][0]['x'] if x['vertices'] else 0   # X座標
                ))
                
                # 重組為段落
                reorganized_text = self.reorganize_by_coordinates(structured_data)
                all_text += f"\n=== 座標重組文字 ===\n{reorganized_text}"
            
            self.logger.info("OCR 結果處理完成")
            return {
                'raw_text': all_text,
                'structured_data': structured_data
            }
            
        except Exception as e:
            self.logger.error(f"OCR 結果處理失敗: {e}")
            return {'raw_text': all_text, 'structured_data': []}
    
    def reorganize_by_coordinates(self, structured_data):
        """根據座標重組文字為段落"""
        if not structured_data:
            return ""
        
        # 按Y座標分組（同一行）
        lines = {}
        for item in structured_data:
            if not item['vertices']:
                continue
                
            y_coord = item['vertices'][0]['y']
            # 容許一定的Y座標誤差，歸為同一行
            line_key = round(y_coord / 15) * 15  # 每15像素為一個群組
            
            if line_key not in lines:
                lines[line_key] = []
            lines[line_key].append(item)
        
        # 組合每一行的文字
        result_lines = []
        for y_coord in sorted(lines.keys()):
            line_items = sorted(lines[y_coord], key=lambda x: x['vertices'][0]['x'] if x['vertices'] else 0)
            line_text = ' '.join([item['text'] for item in line_items])
            result_lines.append(line_text)
        
        return '\n'.join(result_lines)
    
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
            
            # 輸出 prompt 到日誌 (調試用)
            self.logger.info(f"Gemini Prompt 長度: {len(prompt)}")
            
            # 使用 Gemini API
            response = self.gemini_model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.1,
                    max_output_tokens=4000,
                )
            )
            
            if response and response.text:
                # 輸出原始回應到日誌 (調試用)
                self.logger.info(f"Gemini 原始回應: {response.text[:1000]}...")
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
        """建立信用卡帳單分析提示詞 - 修正版"""
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
            "date": "YYYY/MM/DD",
            "merchant": "完整商家名稱", 
            "amount": "金額"
        }}
    ]
}}

重要格式要求:
1. 日期必須轉換為西元年格式 YYYY/MM/DD
   - 民國114年 = 西元2025年
   - 民國113年 = 西元2024年
   - 格式如 "08/21 07/20" 請取後面日期並轉換：07/20 → 2025/07/20
   - 格式如 "08/21" 請轉換為：2025/08/21

2. 商家名稱處理規則:
   - 保持完整商家名稱，不要截斷
   - 不要在商家名稱前加入 "null" 或其他前綴
   - 移除多餘的空格和符號
   - 如果是外幣交易，保留完整的商家名稱和地區資訊

3. 金額處理:
   - 保留原始格式（包含逗號和負號）
   - 退款金額請加上負號 "-"
   - 不要包含貨幣符號除非原始資料有

4. 其他要求:
   - 找不到的欄位填入null
   - 交易明細請按時間順序排列
   - 繳款截止日期也要轉換為西元年格式

特別注意聯邦銀行帳單格式:
- 交易記錄格式通常為: "入帳日 消費日 商家名稱 金額"
- 有些記錄前面會有 "+" 號表示外幣交易
- 國外交易會有手續費記錄

帳單內容:
{text}

請務必回傳有效的JSON格式，不要包含其他說明文字或markdown語法。
"""
    
    def parse_json_response(self, content):
        """解析 LLM 回應中的 JSON 內容 - 增強版"""
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
            
            # 後處理：確保日期格式正確
            analysis_result = self.post_process_analysis_result(analysis_result)
            
            self.logger.info("JSON 解析成功")
            return analysis_result
                
        except json.JSONDecodeError as e:
            self.logger.error(f"JSON 解析失敗: {e}")
            self.logger.error(f"原始內容: {content[:500]}...")
            
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
                    analysis_result = self.post_process_analysis_result(analysis_result)
                    self.logger.info("從混合內容中成功解析 JSON")
                    return analysis_result
                
            except json.JSONDecodeError:
                self.logger.error("無法從內容中提取有效的 JSON")
            
            return None
    
    def post_process_analysis_result(self, result):
        """後處理分析結果，確保格式正確"""
        try:
            if not result:
                return result
            
            # 處理交易明細中的日期和商家名稱
            if 'transactions' in result and isinstance(result['transactions'], list):
                for transaction in result['transactions']:
                    # 修正日期格式
                    if 'date' in transaction and transaction['date']:
                        transaction['date'] = self.normalize_date(transaction['date'])
                    
                    # 清理商家名稱
                    if 'merchant' in transaction and transaction['merchant']:
                        merchant = transaction['merchant']
                        # 移除 null 前綴
                        if merchant.startswith('null '):
                            merchant = merchant[5:]
                        # 清理多餘空格
                        merchant = ' '.join(merchant.split())
                        transaction['merchant'] = merchant
            
            # 處理繳款截止日期
            if 'payment_due_date' in result and result['payment_due_date']:
                result['payment_due_date'] = self.normalize_date(result['payment_due_date'])
            
            # 處理結帳日期
            if 'statement_date' in result and result['statement_date']:
                result['statement_date'] = self.normalize_date(result['statement_date'])
            
            return result
            
        except Exception as e:
            self.logger.error(f"後處理分析結果失敗: {e}")
            return result
    
    def normalize_date(self, date_str):
        """標準化日期格式為西元年 YYYY/MM/DD"""
        try:
            if not date_str or date_str.lower() == 'null':
                return None
            
            # 處理 114/09/24 格式 (民國年)
            if re.match(r'^\d{3}/\d{1,2}/\d{1,2}$', date_str):
                parts = date_str.split('/')
                year = int(parts[0]) + 1911
                month = parts[1].zfill(2)
                day = parts[2].zfill(2)
                return f"{year}/{month}/{day}"
            
            # 處理 08/21 格式 (假設是2025年)
            elif re.match(r'^\d{1,2}/\d{1,2}$', date_str):
                parts = date_str.split('/')
                month = parts[0].zfill(2)
                day = parts[1].zfill(2)
                return f"2025/{month}/{day}"
            
            # 處理已經是西元年格式
            elif re.match(r'^\d{4}/\d{1,2}/\d{1,2}$', date_str):
                parts = date_str.split('/')
                year = parts[0]
                month = parts[1].zfill(2)
                day = parts[2].zfill(2)
                return f"{year}/{month}/{day}"
            
            # 其他格式嘗試解析
            else:
                # 嘗試找到日期模式
                date_patterns = [
                    r'(\d{3})/(\d{1,2})/(\d{1,2})',  # 民國年
                    r'(\d{1,2})/(\d{1,2})',          # MM/DD
                    r'(\d{4})/(\d{1,2})/(\d{1,2})',  # 西元年
                ]
                
                for pattern in date_patterns:
                    match = re.search(pattern, date_str)
                    if match:
                        groups = match.groups()
                        if len(groups) == 3:
                            year, month, day = groups
                            if len(year) == 3:  # 民國年
                                year = int(year) + 1911
                            month = month.zfill(2)
                            day = day.zfill(2)
                            return f"{year}/{month}/{day}"
                        elif len(groups) == 2:  # MM/DD
                            month, day = groups
                            month = month.zfill(2)
                            day = day.zfill(2)
                            return f"2025/{month}/{day}"
                
                return date_str  # 無法解析，回傳原始值
                
        except Exception as e:
            self.logger.error(f"日期格式化失敗: {e} - 原始日期: {date_str}")
            return date_str
    
    def cleanup_temp_files(self, file_paths):
        """清理暫存檔案"""
        for file_path in file_paths:
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    self.logger.info(f"清理暫存檔案: {os.path.basename(file_path)}")
                except Exception as e:
                    self.logger.error(f"清理暫存檔案失敗: {e}")
