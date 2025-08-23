"""
credit_card_manager.py - 信用卡帳單管理模組
自動監控 Gmail 帳單 + OCR + LLM 處理 v1.1 + Gmail 標籤管理
"""
import re
import os
import json
import base64
import threading
import time
import pickle
from datetime import datetime, timedelta
import pytz
import traceback

# Gmail API
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

# LLM 和 OCR
import PyPDF2
from groq import Groq
from dotenv import load_dotenv

# Google Vision OCR
try:
    from google.cloud import vision
    from google.oauth2.service_account import Credentials
    from pdf2image import convert_from_bytes
    VISION_AVAILABLE = True
except ImportError:
    VISION_AVAILABLE = False
    print("⚠️ Google Vision 或 pdf2image 套件未安裝")

# 載入環境變數
load_dotenv()

# 設定台灣時區
TAIWAN_TZ = pytz.timezone('Asia/Taipei')

# Gmail API 權限範圍
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly', 'https://www.googleapis.com/auth/gmail.modify']

# 銀行監控設定
BANK_CONFIGS = {
    "永豐銀行": {
        "sender_email": "ebillservice@newebill.banksinopac.com.tw",
        "sender_domain": "newebill.banksinopac.com.tw",
        "subject_keywords": ["永豐銀行信用卡", "電子帳單通知"],
        "has_attachment": True
    },
    "台新銀行": {
        "sender_email": "webmaster@bhurecv.taishinbank.com.tw", 
        "sender_domain": "bhurecv.taishinbank.com.tw",
        "subject_keywords": ["台新信用卡電子帳單"],
        "has_attachment": True
    },
    "星展銀行": {
        "sender_email": "eservicetw@dbs.com",
        "sender_domain": "dbs.com", 
        "subject_keywords": ["星展銀行", "信用卡電子對帳單"],
        "has_attachment": True
    }
}

class CreditCardManager:
    """信用卡帳單管理器 - 整合 Gmail 監控 + OCR + LLM + 標籤管理"""
    
    def __init__(self):
        """初始化信用卡帳單管理器"""
        # 初始化資料結構
        self.bill_data = {
            'processed_bills': [],
            'processing_log': [],
            'bank_passwords': {},
            'last_check_time': None
        }
        
        # Gmail API 設定
        self.gmail_service = None
        self.gmail_enabled = False
        self.processed_label_id = None
        
        # Google Vision OCR 設定
        self.vision_client = None
        self.vision_enabled = False
        
        # LLM 設定
        self.groq_client = None
        self.groq_enabled = False
        
        # 監控狀態
        self.monitoring_thread = None
        self.is_monitoring = False
        self.last_sync_time = None
        
        # 初始化各項服務
        self.init_gmail_api()
        self.init_groq_api()
        self.init_vision_ocr()
        self.load_bank_passwords()
        
        # 初始化 Gmail 標籤
        if self.gmail_enabled:
            self.init_gmail_labels()
        
        print("📧 信用卡帳單管理器初始化完成")
    
    def get_taiwan_time(self):
        """獲取台灣時間"""
        return datetime.now(TAIWAN_TZ).strftime('%Y/%m/%d %H:%M:%S')
    
    def get_taiwan_datetime(self):
        """獲取台灣時間物件"""
        return datetime.now(TAIWAN_TZ)
    
    def init_gmail_api(self):
        """初始化 Gmail API 連接(支援 Render 雲端環境)"""
        try:
            # 方法1: 從環境變數載入服務帳戶憑證
            google_credentials = os.getenv('GOOGLE_CREDENTIALS')
            if google_credentials:
                try:
                    from google.oauth2.service_account import Credentials
                    creds_dict = json.loads(google_credentials)
                    credentials = Credentials.from_service_account_info(
                        creds_dict, scopes=SCOPES
                    )
                    
                    self.gmail_service = build('gmail', 'v1', credentials=credentials)
                    self.gmail_enabled = True
                    print("✅ Gmail API 連接成功(服務帳戶模式)")
                    return True
                    
                except Exception as e:
                    print(f"❌ 服務帳戶認證失敗: {e}")
            
            # 方法2: 從環境變數載入 OAuth Token
            gmail_token_b64 = os.getenv('GMAIL_TOKEN')
            if gmail_token_b64:
                try:
                    import base64
                    token_data = base64.b64decode(gmail_token_b64)
                    
                    # 載入 pickle 格式的認證
                    creds = pickle.loads(token_data)
                    
                    # 檢查是否需要刷新
                    if creds.expired and creds.refresh_token:
                        creds.refresh(Request())
                        print("🔄 Token 已刷新")
                    
                    self.gmail_service = build('gmail', 'v1', credentials=creds)
                    self.gmail_enabled = True
                    print("✅ Gmail API 連接成功(OAuth Token 模式)")
                    return True
                    
                except Exception as e:
                    print(f"❌ OAuth Token 認證失敗: {e}")
            
            # 方法3: 本地開發模式
            creds = None
            
            if os.path.exists('gmail_token.pickle'):
                with open('gmail_token.pickle', 'rb') as token:
                    creds = pickle.load(token)
            
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    if os.path.exists('credentials.json'):
                        flow = InstalledAppFlow.from_client_secrets_file(
                            'credentials.json', SCOPES)
                        creds = flow.run_local_server(port=0)
                    else:
                        print("❌ 未找到任何有效的 Gmail 認證方式")
                        return False
                
                with open('gmail_token.pickle', 'wb') as token:
                    pickle.dump(creds, token)
            
            self.gmail_service = build('gmail', 'v1', credentials=creds)
            self.gmail_enabled = True
            print("✅ Gmail API 連接成功(本地 OAuth 模式)")
            return True
            
        except Exception as e:
            print(f"❌ Gmail API 連接失敗: {e}")
            return False
    
    def init_groq_api(self):
        """初始化 Groq API"""
        try:
            groq_key = os.getenv('GROQ_API_KEY')
            if not groq_key:
                print("⚠️ 未找到 GROQ_API_KEY 環境變數")
                self.groq_enabled = False
                return False
            
            print("💡 暫時跳過 Groq API，使用基礎解析方案")
            print("🔧 這是為了避免 Render 環境的 proxies 參數衝突")
            self.groq_enabled = False
            return False
            
        except Exception as e:
            print(f"❌ Groq API 連接失敗: {e}")
            print("💡 將使用備用方案處理帳單")
            self.groq_enabled = False
            return False
    
    def init_vision_ocr(self):
        """初始化 Google Vision OCR"""
        try:
            if not VISION_AVAILABLE:
                print("⚠️ Google Vision 套件未安裝，OCR 功能不可用")
                return False
            
            google_credentials = os.getenv('GOOGLE_CREDENTIALS')
            if google_credentials:
                try:
                    creds_dict = json.loads(google_credentials)
                    credentials = Credentials.from_service_account_info(creds_dict)
                    self.vision_client = vision.ImageAnnotatorClient(credentials=credentials)
                    self.vision_enabled = True
                    print("✅ Google Vision OCR 初始化成功")
                    return True
                except Exception as e:
                    print(f"❌ Google Vision OCR 憑證載入失敗: {e}")
                    return False
            else:
                print("⚠️ 未找到 GOOGLE_CREDENTIALS，OCR 功能不可用")
                return False
                
        except Exception as e:
            print(f"❌ Google Vision OCR 初始化失敗: {e}")
            return False
    
    def init_gmail_labels(self):
        """初始化 Gmail 標籤系統"""
        try:
            labels_result = self.gmail_service.users().labels().list(userId='me').execute()
            labels = labels_result.get('labels', [])
            
            label_name = '信用卡帳單已處理'
            existing_label = None
            
            for label in labels:
                if label['name'] == label_name:
                    existing_label = label
                    break
            
            if existing_label:
                self.processed_label_id = existing_label['id']
                print(f"✅ 找到現有標籤：{label_name}")
            else:
                label_object = {
                    'name': label_name,
                    'messageListVisibility': 'show',
                    'labelListVisibility': 'labelShow',
                    'color': {
                        'textColor': '#ffffff',
                        'backgroundColor': '#16a085'
                    }
                }
                
                created_label = self.gmail_service.users().labels().create(
                    userId='me', body=label_object
                ).execute()
                
                self.processed_label_id = created_label['id']
                print(f"✅ 建立新標籤：{label_name}")
            
            return True
            
        except Exception as e:
            print(f"❌ Gmail 標籤初始化失敗: {e}")
            return False
    
    def load_bank_passwords(self):
        """載入銀行密碼設定"""
        try:
            passwords_json = os.getenv('BANK_PASSWORDS')
            if passwords_json:
                self.bill_data['bank_passwords'] = json.loads(passwords_json)
                print(f"✅ 載入 {len(self.bill_data['bank_passwords'])} 個銀行密碼")
            else:
                print("⚠️ 未設定銀行密碼，將無法自動解鎖PDF")
            
        except Exception as e:
            print(f"❌ 載入銀行密碼失敗: {e}")
    
    def set_bank_password(self, bank_name, password):
        """設定銀行PDF密碼"""
        self.bill_data['bank_passwords'][bank_name] = password
        return f"✅ 已設定 {bank_name} 的PDF密碼"
    
    def is_bill_already_processed(self, message_id):
        """檢查帳單是否已處理(通過標籤和記憶體記錄)"""
        try:
            # 方法1: 檢查記憶體中的記錄
            if any(bill['message_id'] == message_id for bill in self.bill_data['processed_bills']):
                return True
            
            # 方法2: 檢查 Gmail 標籤
            if self.processed_label_id:
                message = self.gmail_service.users().messages().get(
                    userId='me', id=message_id, format='minimal'
                ).execute()
                
                label_ids = message.get('labelIds', [])
                if self.processed_label_id in label_ids:
                    print(f"   ⏭️ 郵件已有處理標籤，跳過")
                    return True
            
            return False
            
        except Exception as e:
            print(f"   ⚠️ 檢查處理狀態失敗: {e}")
            return False
    
    def mark_bill_as_processed(self, message_id):
        """標記帳單為已處理"""
        try:
            if self.processed_label_id:
                self.gmail_service.users().messages().modify(
                    userId='me',
                    id=message_id,
                    body={'addLabelIds': [self.processed_label_id]}
                ).execute()
                print(f"   🏷️ 已標記郵件為已處理")
                return True
            return False
            
        except Exception as e:
            print(f"   ❌ 標記失敗: {e}")
            return False
    
    def check_gmail_for_bills(self):
        """檢查 Gmail 中的信用卡帳單"""
        if not self.gmail_enabled:
            return "❌ Gmail API 未啟用"
        
        try:
            print(f"🔍 開始檢查信用卡帳單 - {self.get_taiwan_time()}")
            
            yesterday = (self.get_taiwan_datetime() - timedelta(days=1)).strftime('%Y/%m/%d')
            
            found_bills = []
            
            for bank_name, config in BANK_CONFIGS.items():
                print(f"🏦 檢查 {bank_name}...")
                
                query_parts = []
                
                # 搜尋原始銀行寄件者 OR 轉發郵件
                sender_queries = [
                    f"from:{config['sender_domain']}",
                    f"from:jiayu8227@gmail.com"
                ]
                query_parts.append(f"({' OR '.join(sender_queries)})")
                
                query_parts.append(f"after:{yesterday}")
                query_parts.append("has:attachment")
                
                # 加入主旨關鍵字(包含轉發格式)
                subject_keywords = []
                for keyword in config['subject_keywords']:
                    subject_keywords.append(f'subject:"{keyword}"')
                    subject_keywords.append(f'subject:"Fwd: {keyword}"')
                
                if subject_keywords:
                    query_parts.append(f"({' OR '.join(subject_keywords)})")
                
                # 排除已處理的郵件
                exclude_processed = ""
                if self.processed_label_id:
                    exclude_processed = f" -label:{self.processed_label_id}"
                
                query = " ".join(query_parts) + exclude_processed
                
                try:
                    results = self.gmail_service.users().messages().list(
                        userId='me', q=query, maxResults=10
                    ).execute()
                    
                    messages = results.get('messages', [])
                    print(f"   找到 {len(messages)} 封可能的帳單郵件")
                    
                    for message in messages:
                        bill_info = self.process_gmail_message(message['id'], bank_name)
                        if bill_info:
                            found_bills.append(bill_info)
                
                except Exception as e:
                    print(f"   ❌ {bank_name} 搜尋失敗: {e}")
            
            self.bill_data['last_check_time'] = self.get_taiwan_time()
            
            if found_bills:
                result = f"📧 找到 {len(found_bills)} 份新帳單：\n\n"
                for bill in found_bills:
                    result += f"🏦 {bill['bank_name']}\n"
                    result += f"📅 {bill['date']}\n"
                    result += f"📄 {bill['status']}\n\n"
                return result
            else:
                return f"📧 檢查完成，暫無新帳單\n🕒 檢查時間：{self.get_taiwan_time()}"
        
        except Exception as e:
            error_msg = f"❌ Gmail 檢查失敗: {e}"
            print(error_msg)
            return error_msg
    
    def process_gmail_message(self, message_id, bank_name):
        """處理單封 Gmail 訊息"""
        try:
            message = self.gmail_service.users().messages().get(
                userId='me', id=message_id, format='full'
            ).execute()
            
            headers = message['payload'].get('headers', [])
            subject = next((h['value'] for h in headers if h['name'] == 'Subject'), '')
            date = next((h['value'] for h in headers if h['name'] == 'Date'), '')
            
            print(f"   📧 處理郵件: {subject[:50]}...")
            
            if self.is_bill_already_processed(message_id):
                print(f"   ⏭️ 已處理過，跳過")
                return None
            
            pdf_data = self.extract_pdf_attachment(message)
            if not pdf_data:
                print(f"   ⚠️ 未找到PDF附件")
                return None
            
            bill_info = self.process_pdf_bill(pdf_data, bank_name, message_id, subject, date)
            
            return bill_info
            
        except Exception as e:
            print(f"   ❌ 處理郵件失敗: {e}")
            return None
    
    def extract_pdf_attachment(self, message):
        """從郵件中提取PDF附件"""
        try:
            def extract_attachments(payload):
                attachments = []
                
                if 'parts' in payload:
                    for part in payload['parts']:
                        attachments.extend(extract_attachments(part))
                elif 'body' in payload and 'attachmentId' in payload['body']:
                    if payload.get('filename', '').lower().endswith('.pdf'):
                        attachment_id = payload['body']['attachmentId']
                        attachment = self.gmail_service.users().messages().attachments().get(
                            userId='me', messageId=message['id'], id=attachment_id
                        ).execute()
                        
                        data = base64.urlsafe_b64decode(attachment['data'])
                        attachments.append({
                            'filename': payload['filename'],
                            'data': data
                        })
                
                return attachments
            
            attachments = extract_attachments(message['payload'])
            
            for attachment in attachments:
                if attachment['filename'].lower().endswith('.pdf'):
                    print(f"   📎 找到PDF附件: {attachment['filename']}")
                    return attachment['data']
            
            return None
            
        except Exception as e:
            print(f"   ❌ 提取附件失敗: {e}")
            return None
    
    def process_pdf_bill(self, pdf_data, bank_name, message_id, subject, date):
        """處理PDF帳單"""
        try:
            print(f"   🔓 嘗試解鎖PDF...")
            
            unlocked_pdf = self.unlock_pdf(pdf_data, bank_name)
            if not unlocked_pdf:
                return {
                    'bank_name': bank_name,
                    'message_id': message_id,
                    'subject': subject,
                    'date': date,
                    'status': '❌ PDF解鎖失敗',
                    'processed_time': self.get_taiwan_time()
                }
            
            print(f"   📄 提取PDF文字...")
            
            extracted_text = self.pdf_to_text_with_smart_ocr(unlocked_pdf)
            if not extracted_text:
                return {
                    'bank_name': bank_name,
                    'message_id': message_id,
                    'subject': subject,
                    'date': date,
                    'status': '❌ 文字提取失敗',
                    'processed_time': self.get_taiwan_time()
                }
            
            print(f"   🤖 LLM分析中...")
            
            structured_data = self.llm_parse_bill(extracted_text, bank_name)
            if not structured_data:
                return {
                    'bank_name': bank_name,
                    'message_id': message_id,
                    'subject': subject,
                    'date': date,
                    'status': '❌ LLM解析失敗',
                    'processed_time': self.get_taiwan_time()
                }
            
            bill_info = {
                'bank_name': bank_name,
                'message_id': message_id,
                'subject': subject,
                'date': date,
                'status': '✅ 處理成功',
                'processed_time': self.get_taiwan_time(),
                'bill_data': structured_data
            }
            
            self.bill_data['processed_bills'].append(bill_info)
            
            # 標記為已處理
            self.mark_bill_as_processed(message_id)
            
            print(f"   ✅ 帳單處理完成")
            return bill_info
            
        except Exception as e:
            print(f"   ❌ PDF處理失敗: {e}")
            return {
                'bank_name': bank_name,
                'message_id': message_id,
                'subject': subject,
                'date': date,
                'status': f'❌ 處理失敗: {str(e)}',
                'processed_time': self.get_taiwan_time()
            }
    
    def unlock_pdf(self, pdf_data, bank_name):
        """解鎖PDF文件"""
        try:
            password = self.bill_data['bank_passwords'].get(bank_name)
            if not password:
                print(f"   ⚠️ 未設定 {bank_name} 的PDF密碼")
                return None
            
            import io
            reader = PyPDF2.PdfReader(io.BytesIO(pdf_data))
            
            if reader.is_encrypted:
                if reader.decrypt(password):
                    print(f"   🔓 PDF解鎖成功")
                    
                    writer = PyPDF2.PdfWriter()
                    for page in reader.pages:
                        writer.add_page(page)
                    
                    output_stream = io.BytesIO()
                    writer.write(output_stream)
                    return output_stream.getvalue()
                else:
                    print(f"   ❌ PDF密碼錯誤")
                    return None
            else:
                print(f"   ℹ️ PDF無密碼保護")
                return pdf_data
                
        except Exception as e:
            print(f"   ❌ PDF解鎖失敗: {e}")
            return None
    
    def pdf_to_text_with_smart_ocr(self, pdf_data):
        """智能PDF文字提取(直接提取 + OCR)"""
        try:
            print(f"   📄 開始智能文字提取...")
            
            direct_text = self.pdf_to_text_backup(pdf_data)
            
            if direct_text and self.is_text_quality_good(direct_text):
                print(f"   ✅ 直接文字提取成功，品質良好")
                return direct_text
            
            if self.vision_enabled:
                print(f"   🔍 直接提取品質不佳，使用 Google Vision OCR...")
                ocr_text = self.google_vision_ocr(pdf_data)
                if ocr_text:
                    return ocr_text
            
            print(f"   ⚠️ OCR 不可用，使用直接提取結果")
            return direct_text
            
        except Exception as e:
            print(f"   ❌ 智能文字提取失敗: {e}")
            return None
    
    def is_text_quality_good(self, text):
        """評估文字提取品質"""
        if not text or len(text.strip()) < 100:
            return False
        
        keywords = ['本期應繳', '應繳金額', '繳款期限', '信用卡', '帳單', '交易', '消費']
        keyword_count = sum(1 for keyword in keywords if keyword in text)
        
        return keyword_count >= 2
    
    def google_vision_ocr(self, pdf_data):
        """使用 Google Vision 進行 OCR"""
        try:
            if not self.vision_enabled:
                return None
            
            images = convert_from_bytes(pdf_data, dpi=200, fmt='PNG')
            
            all_text = ""
            for i, image in enumerate(images):
                print(f"     📷 OCR處理第 {i+1} 頁...")
                
                import io
                img_byte_arr = io.BytesIO()
                image.save(img_byte_arr, format='PNG')
                image_content = img_byte_arr.getvalue()
                
                vision_image = vision.Image(content=image_content)
                response = self.vision_client.text_detection(image=vision_image)
                
                if response.error.message:
                    print(f"     ❌ Google Vision API 錯誤: {response.error.message}")
                    continue
                
                if response.text_annotations:
                    page_text = response.text_annotations[0].description
                    all_text += f"\n--- 第 {i+1} 頁 (OCR) ---\n{page_text}\n"
                    print(f"     ✅ 第 {i+1} 頁 OCR 完成")
                else:
                    print(f"     ⚠️ 第 {i+1} 頁未識別到文字")
            
            if all_text.strip():
                print(f"   ✅ Google Vision OCR 完成，識別 {len(all_text)} 個字元")
                return all_text
            else:
                print(f"   ❌ Google Vision OCR 未識別到任何文字")
                return None
                
        except Exception as e:
            print(f"   ❌ Google Vision OCR 失敗: {e}")
            return None
    
    def pdf_to_text_backup(self, pdf_data):
        """PDF轉文字備用方案(直接提取文字)"""
        try:
            import io
            reader = PyPDF2.PdfReader(io.BytesIO(pdf_data))
            
            all_text = ""
            for i, page in enumerate(reader.pages):
                text = page.extract_text()
                all_text += f"\n--- 第 {i+1} 頁 ---\n{text}\n"
            
            if all_text.strip():
                print(f"   ✅ 文字提取成功，提取 {len(all_text)} 個字元")
                return all_text
            else:
                print("   ❌ 文字提取失敗，PDF可能是圖片格式")
                return None
                
        except Exception as e:
            print(f"   ❌ 文字提取失敗: {e}")
            return None
    
    def llm_parse_bill(self, extracted_text, bank_name):
        """使用LLM解析帳單內容"""
        try:
            if not self.groq_enabled:
                print("⚠️ Groq API 不可用，使用基礎解析方案")
                return self.basic_parse_bill(extracted_text, bank_name)
            
            # Groq 處理邏輯（目前跳過）
            return self.basic_parse_bill(extracted_text, bank_name)
            
        except Exception as e:
            print(f"   ❌ LLM處理失敗: {e}")
            return self.basic_parse_bill(extracted_text, bank_name)
    
    def basic_parse_bill(self, extracted_text, bank_name):
        """基礎帳單解析方案(不使用LLM)"""
        try:
            print("   🔧 使用基礎解析方案")
            
            bill_data = {
                "bank_name": bank_name,
                "card_number": None,
                "statement_period": None,
                "due_date": None,
                "total_amount": None,
                "minimum_payment": None,
                "transactions": [],
                "summary": {
                    "transaction_count": 0,
                    "total_spending": 0
                }
            }
            
            lines = extracted_text.split('\n')
            
            for line in lines:
                line = line.strip()
                
                if '本期應繳' in line or '應繳金額' in line:
                    amounts = re.findall(r'[\d,]+', line)
                    if amounts:
                        bill_data['total_amount'] = amounts[-1].replace(',', '')
                
                elif '最低應繳' in line:
                    amounts = re.findall(r'[\d,]+', line)
                    if amounts:
                        bill_data['minimum_payment'] = amounts[-1].replace(',', '')
                
                elif '繳款期限' in line or '到期日' in line:
                    dates = re.findall(r'\d{4}[/-]\d{1,2}[/-]\d{1,2}', line)
                    if dates:
                        bill_data['due_date'] = dates[0]
                
                elif '帳單期間' in line or '對帳單期間' in line:
                    dates = re.findall(r'\d{4}[/-]\d{1,2}[/-]\d{1,2}', line)
                    if len(dates) >= 2:
                        bill_data['statement_period'] = f"{dates[0]} ~ {dates[1]}"
                
                elif '卡號' in line and ('****' in line or '*' in line):
                    card_nums = re.findall(r'[\d*]{4,}', line)
                    if card_nums:
                        bill_data['card_number'] = card_nums[0]
            
            # 簡單統計
            if bill_data['total_amount']:
                bill_data['summary']['total_spending'] = int(bill_data['total_amount'])
            
            print(f"   ✅ 基礎解析完成")
            print(f"      應繳金額: {bill_data['total_amount']}")
            print(f"      繳款期限: {bill_data['due_date']}")
            
            return bill_data
            
        except Exception as e:
            print(f"   ❌ 基礎解析失敗: {e}")
            return None
    
    def get_processed_bills(self):
        """獲取已處理的帳單列表"""
        return self.bill_data['processed_bills']
    
    def get_processing_log(self):
        """獲取處理日誌"""
        return self.bill_data['processing_log']
    
    def get_system_status(self):
        """獲取系統狀態"""
        status = {
            'gmail_enabled': self.gmail_enabled,
            'vision_enabled': self.vision_enabled,
            'groq_enabled': self.groq_enabled,
            'processed_bills_count': len(self.bill_data['processed_bills']),
            'last_check_time': self.bill_data.get('last_check_time'),
            'bank_passwords_count': len(self.bill_data['bank_passwords']),
            'is_monitoring': self.is_monitoring
        }
        return status
    
    def start_monitoring(self, interval_minutes=60):
        """開始自動監控"""
        if self.is_monitoring:
            return "⚠️ 監控已在運行中"
        
        if not self.gmail_enabled:
            return "❌ Gmail API 未啟用，無法開始監控"
        
        self.is_monitoring = True
        
        def monitoring_loop():
            while self.is_monitoring:
                try:
                    print(f"🔄 自動監控檢查 - {self.get_taiwan_time()}")
                    self.check_gmail_for_bills()
                    time.sleep(interval_minutes * 60)  # 轉換為秒
                except Exception as e:
                    print(f"❌ 監控循環錯誤: {e}")
                    time.sleep(60)  # 錯誤時等待1分鐘再試
        
        self.monitoring_thread = threading.Thread(target=monitoring_loop, daemon=True)
        self.monitoring_thread.start()
        
        return f"✅ 開始自動監控，間隔 {interval_minutes} 分鐘"
    
    def stop_monitoring(self):
        """停止自動監控"""
        if not self.is_monitoring:
            return "⚠️ 監控未在運行"
        
        self.is_monitoring = False
        
        if self.monitoring_thread and self.monitoring_thread.is_alive():
            print("🛑 停止監控中...")
            # 等待監控線程結束（最多等30秒）
            self.monitoring_thread.join(timeout=30)
        
        return "✅ 自動監控已停止"
    
    def manual_process_bill(self, pdf_file_path, bank_name):
        """手動處理單份帳單文件"""
        try:
            if not os.path.exists(pdf_file_path):
                return "❌ 檔案不存在"
            
            with open(pdf_file_path, 'rb') as f:
                pdf_data = f.read()
            
            print(f"📄 手動處理帳單: {pdf_file_path}")
            
            # 解鎖PDF
            unlocked_pdf = self.unlock_pdf(pdf_data, bank_name)
            if not unlocked_pdf:
                return "❌ PDF解鎖失敗，請檢查密碼設定"
            
            # 提取文字
            extracted_text = self.pdf_to_text_with_smart_ocr(unlocked_pdf)
            if not extracted_text:
                return "❌ 文字提取失敗"
            
            # LLM解析
            structured_data = self.llm_parse_bill(extracted_text, bank_name)
            if not structured_data:
                return "❌ 帳單解析失敗"
            
            # 儲存結果
            bill_info = {
                'bank_name': bank_name,
                'message_id': f'manual_{int(time.time())}',
                'subject': f'手動處理 - {os.path.basename(pdf_file_path)}',
                'date': self.get_taiwan_time(),
                'status': '✅ 手動處理成功',
                'processed_time': self.get_taiwan_time(),
                'bill_data': structured_data
            }
            
            self.bill_data['processed_bills'].append(bill_info)
            
            return f"✅ 手動處理完成\n應繳金額: {structured_data.get('total_amount', '未識別')}\n繳款期限: {structured_data.get('due_date', '未識別')}"
            
        except Exception as e:
            return f"❌ 手動處理失敗: {e}"
    
    def export_bills_to_json(self, file_path=None):
        """匯出帳單資料為JSON"""
        try:
            if not file_path:
                file_path = f"bills_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            
            export_data = {
                'export_time': self.get_taiwan_time(),
                'total_bills': len(self.bill_data['processed_bills']),
                'bills': self.bill_data['processed_bills'],
                'system_status': self.get_system_status()
            }
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, ensure_ascii=False, indent=2)
            
            return f"✅ 帳單資料已匯出至: {file_path}"
            
        except Exception as e:
            return f"❌ 匯出失敗: {e}"
    
    def clear_processed_bills(self):
        """清空已處理的帳單記錄"""
        count = len(self.bill_data['processed_bills'])
        self.bill_data['processed_bills'] = []
        self.bill_data['processing_log'] = []
        return f"✅ 已清空 {count} 份帳單記錄"
    
    def get_bills_summary(self):
        """獲取帳單摘要統計"""
        try:
            bills = self.bill_data['processed_bills']
            
            if not bills:
                return "📊 暫無帳單資料"
            
            summary = {
                'total_bills': len(bills),
                'banks': {},
                'total_amount': 0,
                'recent_bills': []
            }
            
            for bill in bills:
                bank = bill['bank_name']
                if bank not in summary['banks']:
                    summary['banks'][bank] = {'count': 0, 'total_amount': 0}
                
                summary['banks'][bank]['count'] += 1
                
                if bill.get('bill_data') and bill['bill_data'].get('total_amount'):
                    try:
                        amount = int(bill['bill_data']['total_amount'])
                        summary['banks'][bank]['total_amount'] += amount
                        summary['total_amount'] += amount
                    except:
                        pass
                
                # 最近5份帳單
                if len(summary['recent_bills']) < 5:
                    summary['recent_bills'].append({
                        'bank': bank,
                        'date': bill.get('processed_time', '未知'),
                        'amount': bill.get('bill_data', {}).get('total_amount', '未知'),
                        'status': bill.get('status', '未知')
                    })
            
            result = f"📊 帳單統計摘要\n"
            result += f"📄 總帳單數: {summary['total_bills']}\n"
            result += f"💰 總金額: NT$ {summary['total_amount']:,}\n\n"
            
            result += "🏦 各銀行統計:\n"
            for bank, data in summary['banks'].items():
                result += f"   {bank}: {data['count']}份, NT$ {data['total_amount']:,}\n"
            
            if summary['recent_bills']:
                result += "\n📋 最近處理的帳單:\n"
                for bill in summary['recent_bills']:
                    result += f"   {bill['bank']} - {bill['date'][:10]} - NT$ {bill['amount']} - {bill['status']}\n"
            
            return result
            
        except Exception as e:
            return f"❌ 統計摘要生成失敗: {e}"


# 主要命令處理函數
def handle_credit_card_command(command, manager=None):
    """處理信用卡相關指令的主要函數"""
    
    # 如果沒有傳入管理器，創建一個新的
    if manager is None:
        manager = CreditCardManager()
    
    command = command.strip().lower()
    
    try:
        if command in ['check', 'check_bills', '檢查帳單', '檢查']:
            return manager.check_gmail_for_bills()
        
        elif command in ['status', '狀態', '系統狀態']:
            status = manager.get_system_status()
            result = "🖥️ 系統狀態\n"
            result += f"Gmail API: {'✅ 已連接' if status['gmail_enabled'] else '❌ 未連接'}\n"
            result += f"Vision OCR: {'✅ 可用' if status['vision_enabled'] else '❌ 不可用'}\n"
            result += f"Groq LLM: {'✅ 可用' if status['groq_enabled'] else '❌ 不可用'}\n"
            result += f"已處理帳單: {status['processed_bills_count']} 份\n"
            result += f"銀行密碼數: {status['bank_passwords_count']} 個\n"
            result += f"最後檢查: {status.get('last_check_time', '尚未檢查')}\n"
            result += f"自動監控: {'🔄 運行中' if status['is_monitoring'] else '⏸️ 已停止'}"
            return result
        
        elif command in ['summary', 'bills', '帳單摘要', '摘要']:
            return manager.get_bills_summary()
        
        elif command in ['start_monitor', 'monitor', '開始監控', '監控']:
            return manager.start_monitoring()
        
        elif command in ['stop_monitor', '停止監控']:
            return manager.stop_monitoring()
        
        elif command in ['clear', 'clear_bills', '清空', '清空帳單']:
            return manager.clear_processed_bills()
        
        elif command in ['export', 'export_bills', '匯出', '匯出帳單']:
            return manager.export_bills_to_json()
        
        elif command.startswith('set_password '):
            # 格式: set_password 永豐銀行 password123
            parts = command.split(' ', 2)
            if len(parts) >= 3:
                bank_name = parts[1]
                password = parts[2]
                return manager.set_bank_password(bank_name, password)
            else:
                return "❌ 格式錯誤，請使用：set_password 銀行名稱 密碼"
        
        elif command.startswith('process '):
            # 格式: process /path/to/file.pdf 永豐銀行
            parts = command.split(' ', 2)
            if len(parts) >= 3:
                file_path = parts[1]
                bank_name = parts[2]
                return manager.manual_process_bill(file_path, bank_name)
            else:
                return "❌ 格式錯誤，請使用：process 檔案路徑 銀行名稱"
        
        elif command in ['help', '幫助', '說明']:
            help_text = """
📧 信用卡帳單管理器指令說明

基本指令：
• check, 檢查 - 檢查新帳單
• status, 狀態 - 查看系統狀態
• summary, 摘要 - 帳單統計摘要
• help, 幫助 - 顯示此說明

監控指令：
• start_monitor, 監控 - 開始自動監控
• stop_monitor, 停止監控 - 停止自動監控

管理指令：
• clear, 清空 - 清空已處理帳單
• export, 匯出 - 匯出帳單資料

設定指令：
• set_password 銀行名稱 密碼 - 設定PDF密碼
• process 檔案路徑 銀行名稱 - 手動處理帳單

支援的銀行：永豐銀行、台新銀行、星展銀行
            """.strip()
            return help_text
        
        else:
            return f"❌ 未知指令：{command}\n請使用 'help' 查看可用指令"
    
    except Exception as e:
        return f"❌ 指令執行失敗：{str(e)}"


# 全域管理器實例
_global_manager = None

def get_credit_card_manager():
    """獲取全域信用卡管理器實例"""
    global _global_manager
    if _global_manager is None:
        _global_manager = CreditCardManager()
    return _global_manager


def initialize_credit_card_manager():
    """初始化信用卡管理器"""
    return get_credit_card_manager()


def check_new_bills():
    """檢查新帳單的快捷函數"""
    manager = get_credit_card_manager()
    return manager.check_gmail_for_bills()


def get_system_status():
    """獲取系統狀態的快捷函數"""
    manager = get_credit_card_manager()
    return manager.get_system_status()


def start_auto_monitoring():
    """開始自動監控的快捷函數"""
    manager = get_credit_card_manager()
    return manager.start_monitoring()


def stop_auto_monitoring():
    """停止自動監控的快捷函數"""
    manager = get_credit_card_manager()
    return manager.stop_monitoring()


def is_credit_card_command(message):
    """判斷是否為信用卡相關指令"""
    if not message or not isinstance(message, str):
        return False
    
    message_lower = message.strip().lower()
    
    # 信用卡相關關鍵字
    credit_card_keywords = [
        # 基本指令
        'check', 'check_bills', '檢查帳單', '檢查', '帳單',
        'status', '狀態', '系統狀態',
        'summary', 'bills', '帳單摘要', '摘要',
        'help', '幫助', '說明',
        
        # 監控指令
        'start_monitor', 'monitor', '開始監控', '監控',
        'stop_monitor', '停止監控',
        
        # 管理指令
        'clear', 'clear_bills', '清空', '清空帳單',
        'export', 'export_bills', '匯出', '匯出帳單',
        
        # 設定指令
        'set_password', '設定密碼', 'process', '處理帳單',
        
        # 銀行名稱
        '永豐銀行', '台新銀行', '星展銀行',
        
        # 信用卡相關詞彙
        '信用卡', 'credit card', '帳單', 'bill', 'gmail',
        'pdf', 'ocr', '解析', 'parse', '監控'
    ]
    
    # 檢查是否包含信用卡相關關鍵字
    for keyword in credit_card_keywords:
        if keyword in message_lower:
            return True
    
    # 檢查是否以特定格式開始
    command_prefixes = [
        'set_password ',
        'process ',
        '設定密碼 ',
        '處理帳單 '
    ]
    
    for prefix in command_prefixes:
        if message_lower.startswith(prefix):
            return True
    
    return False


def is_credit_card_query(message):
    """判斷是否為信用卡相關查詢（is_credit_card_command 的別名）"""
    return is_credit_card_command(message)


def get_credit_card_summary():
    """獲取信用卡帳單摘要的快捷函數"""
    manager = get_credit_card_manager()
    return manager.get_bills_summary()


def process_credit_card_query(query):
    """處理信用卡查詢的快捷函數"""
    return handle_credit_card_command(query)


def get_bill_data():
    """獲取帳單資料的快捷函數"""
    manager = get_credit_card_manager()
    return manager.get_processed_bills()


def get_bill_summary():
    """獲取帳單摘要的快捷函數（get_credit_card_summary 的別名）"""
    return get_credit_card_summary()


def check_bills():
    """檢查帳單的快捷函數"""
    return check_new_bills()


def init_credit_card_system():
    """初始化信用卡系統的快捷函數"""
    return initialize_credit_card_manager()


def credit_card_status():
    """獲取信用卡系統狀態的快捷函數"""
    return get_system_status()


def handle_credit_card_query(query):
    """處理信用卡查詢（handle_credit_card_command 的別名）"""
    return handle_credit_card_command(query)


def start_credit_card_monitor():
    """啟動信用卡監控的快捷函數"""
    manager = get_credit_card_manager()
    return manager.start_monitoring()


def get_credit_card_status():
    """獲取信用卡系統狀態的快捷函數"""
    try:
        manager = get_credit_card_manager()
        status = manager.get_system_status()
        
        # 格式化狀態以符合 main.py 的期望
        formatted_status = {
            'status': 'running' if status['gmail_enabled'] else 'limited',
            'gmail_enabled': status['gmail_enabled'],
            'groq_enabled': status['groq_enabled'],
            'tesseract_enabled': status.get('tesseract_enabled', False),  # 添加 OCR 狀態
            'vision_enabled': status.get('vision_enabled', False),
            'monitored_banks': list(BANK_CONFIGS.keys()),
            'processed_bills_count': status['processed_bills_count'],
            'last_check_time': status.get('last_check_time'),
            'is_monitoring': status['is_monitoring']
        }
        
        return formatted_status
        
    except Exception as e:
        return {
            'status': 'error',
            'error': str(e),
            'gmail_enabled': False,
            'groq_enabled': False,
            'tesseract_enabled': False,
            'vision_enabled': False,
            'monitored_banks': [],
            'processed_bills_count': 0,
            'last_check_time': None,
            'is_monitoring': False
        }
