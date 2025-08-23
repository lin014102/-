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
                
                # 解析本期應繳金額
                if '本期應繳' in line or '應繳金額' in line:
                    amounts = re.findall(r'[\d,]+', line)
                    if amounts:
                        bill_data['total_amount'] = amounts[-1].replace(',', '')
                
                # 解析最低應繳金額
                elif '最低應繳' in line:
                    amounts = re.findall(r'[\d,]+', line)
                    if amounts:
                        bill_data['minimum_payment'] = amounts[-1].replace(',', '')
                
                # 解析繳款期限
                elif '繳款期限' in line or '到期日' in line:
                    dates = re.findall(r'\d{4}[/-]\d{1,2}[/-]\d{1,2}', line)
                    if dates:
                        bill_data['due_date'] = dates[0]
                
                # 解析帳單期間
                elif '帳單期間' in line or '結帳期間' in line:
                    dates = re.findall(r'\d{4}[/-]\d{1,2}[/-]\d{1,2}', line)
                    if len(dates) >= 2:
                        bill_data['statement_period'] = f"{dates[0]} ~ {dates[1]}"
                
                # 解析卡號
                elif '卡號' in line or '信用卡號' in line:
                    # 尋找卡號格式 (通常是 **** **** **** 1234)
                    card_numbers = re.findall(r'[\*\d]{4}[\s\-]?[\*\d]{4}[\s\-]?[\*\d]{4}[\s\-]?\d{4}', line)
                    if card_numbers:
                        bill_data['card_number'] = card_numbers[0]
            
            # 嘗試解析交易明細
            bill_data['transactions'] = self.extract_transactions(extracted_text)
            bill_data['summary']['transaction_count'] = len(bill_data['transactions'])
            
            # 計算總消費金額
            total_spending = 0
            for transaction in bill_data['transactions']:
                if transaction.get('amount'):
                    try:
                        amount = float(transaction['amount'].replace(',', ''))
                        total_spending += amount
                    except:
                        pass
            
            bill_data['summary']['total_spending'] = total_spending
            
            print(f"   ✅ 基礎解析完成：應繳 {bill_data.get('total_amount', '未知')} 元")
            return bill_data
            
        except Exception as e:
            print(f"   ❌ 基礎解析失敗: {e}")
            return None
    
    def extract_transactions(self, text):
        """從文字中提取交易明細"""
        try:
            transactions = []
            lines = text.split('\n')
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                # 尋找包含日期和金額的行（可能是交易記錄）
                # 格式範例：01/15 超商消費 150
                date_match = re.search(r'(\d{1,2}/\d{1,2})', line)
                amount_match = re.search(r'(\d{1,3}(?:,\d{3})*)', line)
                
                if date_match and amount_match:
                    # 提取商家名稱（日期和金額之間的文字）
                    date_pos = date_match.end()
                    amount_pos = amount_match.start()
                    
                    if amount_pos > date_pos:
                        merchant = line[date_pos:amount_pos].strip()
                        # 過濾掉過短的商家名稱
                        if len(merchant) >= 2:
                            transaction = {
                                'date': date_match.group(1),
                                'merchant': merchant,
                                'amount': amount_match.group(1)
                            }
                            transactions.append(transaction)
            
            return transactions[:20]  # 最多回傳20筆交易
            
        except Exception as e:
            print(f"   ⚠️ 交易明細提取失敗: {e}")
            return []
    
    def get_bill_summary(self):
        """獲取帳單處理摘要"""
        try:
            total_bills = len(self.bill_data['processed_bills'])
            
            if total_bills == 0:
                return "📊 帳單摘要：\n暫無已處理的帳單"
            
            summary = f"📊 帳單處理摘要 ({self.get_taiwan_time()})\n\n"
            summary += f"📈 總計處理：{total_bills} 份帳單\n\n"
            
            # 按銀行統計
            bank_stats = {}
            for bill in self.bill_data['processed_bills']:
                bank = bill['bank_name']
                if bank not in bank_stats:
                    bank_stats[bank] = {'count': 0, 'success': 0}
                bank_stats[bank]['count'] += 1
                if '成功' in bill['status']:
                    bank_stats[bank]['success'] += 1
            
            summary += "🏦 各銀行統計：\n"
            for bank, stats in bank_stats.items():
                summary += f"   {bank}：{stats['success']}/{stats['count']} 成功\n"
            
            # 最近處理的帳單
            summary += f"\n📋 最近處理：\n"
            recent_bills = sorted(self.bill_data['processed_bills'], 
                                key=lambda x: x['processed_time'], reverse=True)[:5]
            
            for bill in recent_bills:
                summary += f"   {bill['bank_name']} - {bill['status']}\n"
                summary += f"   {bill['processed_time']}\n\n"
            
            if self.bill_data['last_check_time']:
                summary += f"🕒 最後檢查：{self.bill_data['last_check_time']}\n"
            
            return summary
            
        except Exception as e:
            return f"❌ 摘要生成失敗: {e}"
    
    def start_monitoring(self):
        """啟動自動監控"""
        if self.is_monitoring:
            return "⚠️ 監控已在運行中"
        
        if not self.gmail_enabled:
            return "❌ Gmail API 未啟用，無法啟動監控"
        
        try:
            self.is_monitoring = True
            self.monitoring_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
            self.monitoring_thread.start()
            
            return f"✅ 自動監控已啟動\n🕒 啟動時間：{self.get_taiwan_time()}"
            
        except Exception as e:
            self.is_monitoring = False
            return f"❌ 監控啟動失敗: {e}"
    
    def stop_monitoring(self):
        """停止自動監控"""
        if not self.is_monitoring:
            return "⚠️ 監控未在運行"
        
        self.is_monitoring = False
        return f"⏹️ 自動監控已停止\n🕒 停止時間：{self.get_taiwan_time()}"
    
    def _monitoring_loop(self):
        """監控循環"""
        print("🔄 自動監控線程已啟動")
        
        while self.is_monitoring:
            try:
                # 每30分鐘檢查一次
                time.sleep(1800)  # 30 * 60 秒
                
                if not self.is_monitoring:
                    break
                
                print(f"🔄 定時檢查開始 - {self.get_taiwan_time()}")
                self.check_gmail_for_bills()
                self.last_sync_time = self.get_taiwan_time()
                
            except Exception as e:
                print(f"❌ 監控循環錯誤: {e}")
                time.sleep(300)  # 錯誤時等待5分鐘再重試
        
        print("⏹️ 自動監控線程已結束")
    
    def get_monitoring_status(self):
        """獲取監控狀態"""
        if self.is_monitoring:
            status = f"✅ 自動監控運行中\n"
            if self.last_sync_time:
                status += f"🕒 最後同步：{self.last_sync_time}\n"
            status += f"📧 Gmail API：{'✅ 正常' if self.gmail_enabled else '❌ 未連接'}\n"
            status += f"🔍 OCR服務：{'✅ 可用' if self.vision_enabled else '⚠️ 不可用'}\n"
            status += f"🤖 LLM服務：{'✅ 可用' if self.groq_enabled else '⚠️ 使用基礎解析'}\n"
        else:
            status = f"⏹️ 自動監控已停止\n"
            if self.bill_data['last_check_time']:
                status += f"🕒 最後檢查：{self.bill_data['last_check_time']}\n"
        
        return status


# 全域實例
credit_card_manager = None

def init_credit_card_manager():
    """初始化全域信用卡管理器實例"""
    global credit_card_manager
    if credit_card_manager is None:
        credit_card_manager = CreditCardManager()
    return credit_card_manager

def handle_credit_card_command(command):
    """處理信用卡相關指令"""
    try:
        manager = init_credit_card_manager()
        
        # 正規化指令
        command = command.strip().lower()
        
        # 檢查帳單指令
        if any(keyword in command for keyword in ['檢查帳單', '查詢帳單', 'check bills', 'check gmail']):
            return manager.check_gmail_for_bills()
        
        # 帳單摘要指令
        elif any(keyword in command for keyword in ['帳單摘要', '摘要', 'summary', '統計']):
            return manager.get_bill_summary()
        
        # 啟動監控指令
        elif any(keyword in command for keyword in ['啟動監控', '開始監控', 'start monitoring']):
            return manager.start_monitoring()
        
        # 停止監控指令
        elif any(keyword in command for keyword in ['停止監控', '結束監控', 'stop monitoring']):
            return manager.stop_monitoring()
        
        # 監控狀態指令
        elif any(keyword in command for keyword in ['監控狀態', '狀態', 'monitoring status', 'status']):
            return manager.get_monitoring_status()
        
        # 設定銀行密碼指令
        elif '設定密碼' in command or 'set password' in command:
            return handle_password_setting(command, manager)
        
        # 幫助指令
        elif any(keyword in command for keyword in ['幫助', 'help', '指令']):
            return get_help_message()
        
        # 預設回應
        else:
            return get_default_response()
    
    except Exception as e:
        error_msg = f"❌ 指令處理失敗: {e}"
        print(f"Error in handle_credit_card_command: {e}")
        print(f"Command: {command}")
        import traceback
        traceback.print_exc()
        return error_msg

def handle_password_setting(command, manager):
    """處理密碼設定指令"""
    try:
        # 簡單的密碼設定格式解析
        # 格式: 設定密碼 銀行名稱 密碼
        parts = command.split()
        if len(parts) >= 3:
            bank_name = parts[1]
            password = parts[2]
            
            # 映射銀行名稱
            bank_mapping = {
                '永豐': '永豐銀行',
                '台新': '台新銀行', 
                '星展': '星展銀行',
                'sinopac': '永豐銀行',
                'taishin': '台新銀行',
                'dbs': '星展銀行'
            }
            
            actual_bank = bank_mapping.get(bank_name, bank_name)
            return manager.set_bank_password(actual_bank, password)
        else:
            return "❌ 密碼設定格式錯誤\n正確格式：設定密碼 [銀行名稱] [密碼]\n例如：設定密碼 永豐 123456"
    
    except Exception as e:
        return f"❌ 密碼設定失敗: {e}"

def get_help_message():
    """獲取幫助訊息"""
    return """📖 信用卡帳單管理器 - 指令說明

🔍 帳單相關指令：
   • 檢查帳單 / check bills - 檢查Gmail新帳單
   • 帳單摘要 / summary - 顯示處理摘要統計

🔄 監控相關指令：  
   • 啟動監控 / start monitoring - 開始自動監控
   • 停止監控 / stop monitoring - 停止自動監控
   • 監控狀態 / status - 查看目前狀態

🔧 設定相關指令：
   • 設定密碼 [銀行] [密碼] - 設定PDF解鎖密碼
   • 例如：設定密碼 永豐 123456

💡 支援的銀行：
   • 永豐銀行 (永豐/sinopac)
   • 台新銀行 (台新/taishin)  
   • 星展銀行 (星展/dbs)

ℹ️ 其他指令：
   • 幫助 / help - 顯示此說明"""

def get_default_response():
    """預設回應"""
    manager = init_credit_card_manager()
    status_info = []
    
    # 系統狀態
    status_info.append("📧 信用卡帳單管理器")
    status_info.append(f"🕒 目前時間：{manager.get_taiwan_time()}")
    
    # 服務狀態
    services = []
    services.append(f"Gmail API：{'✅' if manager.gmail_enabled else '❌'}")
    services.append(f"OCR服務：{'✅' if manager.vision_enabled else '⚠️'}")
    services.append(f"LLM服務：{'✅' if manager.groq_enabled else '⚠️'}")
    status_info.append("🔧 服務狀態：" + " | ".join(services))
    
    # 監控狀態
    if manager.is_monitoring:
        status_info.append("📊 狀態：✅ 自動監控運行中")
    else:
        status_info.append("📊 狀態：⏹️ 監控已停止")
    
    # 統計資訊
    total_bills = len(manager.bill_data['processed_bills'])
    status_info.append(f"📈 已處理帳單：{total_bills} 份")
    
    if manager.bill_data['last_check_time']:
        status_info.append(f"🔍 最後檢查：{manager.bill_data['last_check_time']}")
    
    status_info.append("\n💡 輸入「幫助」查看可用指令")
    
    return "\n".join(status_info)
