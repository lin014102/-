"""
credit_card_manager.py - 信用卡帳單管理模組
自動監控 Gmail 帳單 + OCR + LLM 處理 v2.0
新增：Google Sheets 動態設定 + Gmail 標籤管理 - 修復版
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

# 🆕 Google Sheets API
import gspread
from google.oauth2.service_account import Credentials

# LLM 和 OCR
import PyPDF2
from groq import Groq
from dotenv import load_dotenv

# 🆕 Google Vision OCR
try:
    from google.cloud import vision
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
SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.modify'  # 🆕 新增標籤管理權限
]

# 預設銀行監控設定（當 Sheets 載入失敗時使用）
BANK_CONFIGS_DEFAULT = {
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
    """信用卡帳單管理器 - 整合 Gmail 監控 + OCR + LLM + Sheets 動態設定"""
    
    def __init__(self):
        """初始化信用卡帳單管理器"""
        # 初始化資料結構
        self.bill_data = {
            'processed_bills': [],
            'processing_log': [],
            'bank_passwords': {},
            'last_check_time': None
        }
        
        # 🆕 Google Sheets 設定
        self.spreadsheet_url = "https://docs.google.com/spreadsheets/d/1EACr2Zu7_regqp3Po7AlNE4ZcjazKbgyvz-yYNYtcCs/edit?usp=sharing"
        self.gc = None
        self.sheet = None
        self.bank_configs = {}  # 🆕 動態載入的銀行設定
        self.sheets_enabled = False
        
        # Gmail API 設定
        self.gmail_service = None
        self.gmail_enabled = False
        
        # LLM 設定
        self.groq_client = None
        self.groq_enabled = False
        
        # Google Vision OCR 設定
        self.vision_client = None
        self.vision_enabled = False
        
        # 監控狀態
        self.monitoring_thread = None
        self.is_monitoring = False
        self.last_sync_time = None
        
        # 初始化各項服務
        self.init_gmail_api()
        self.init_groq_api()
        self.init_vision_ocr()
        
        # 🆕 初始化 Google Sheets 和載入設定
        self.init_google_sheets()
        self.load_bank_configs_from_sheets()
        
        # 🆕 建立 Gmail 標籤
        if self.gmail_enabled:
            self.create_credit_card_labels()
        
        self.load_bank_passwords()
        
        print("📧 信用卡帳單管理器初始化完成")
    
    def get_taiwan_time(self):
        """獲取台灣時間"""
        return datetime.now(TAIWAN_TZ).strftime('%Y/%m/%d %H:%M:%S')
    
    def get_taiwan_datetime(self):
        """獲取台灣時間物件"""
        return datetime.now(TAIWAN_TZ)
    
    def init_google_sheets(self):
        """🆕 初始化 Google Sheets 連接"""
        try:
            creds_json = os.getenv('GOOGLE_CREDENTIALS')
            
            if not creds_json:
                print("⚠️ 未找到 GOOGLE_CREDENTIALS，將使用預設銀行設定")
                return False
            
            creds_dict = json.loads(creds_json)
            credentials = Credentials.from_service_account_info(
                creds_dict,
                scopes=[
                    'https://spreadsheets.google.com/feeds',
                    'https://www.googleapis.com/auth/drive'
                ]
            )
            
            self.gc = gspread.authorize(credentials)
            self.sheet = self.gc.open_by_url(self.spreadsheet_url)
            
            print("✅ 信用卡 Google Sheets 連接成功")
            self.sheets_enabled = True
            return True
            
        except json.JSONDecodeError as e:
            print(f"❌ JSON 格式錯誤: {e}")
            print("📝 將使用預設銀行設定")
            return False
        except Exception as e:
            print(f"❌ 信用卡 Sheets 連接失敗: {e}")
            print("📝 將使用預設銀行設定")
            return False
    
    def load_bank_configs_from_sheets(self):
        """🆕 從 Google Sheets BankConfigs 分頁載入銀行設定 - 修復版本"""
        try:
            if not self.sheets_enabled or not self.gc or not self.sheet:
                print("📝 使用預設銀行設定")
                self.bank_configs = BANK_CONFIGS_DEFAULT
                return
            
            # 檢查是否有 BankConfigs 工作表
            worksheets = [ws.title for ws in self.sheet.worksheets()]
            if "BankConfigs" not in worksheets:
                print("⚠️ 找不到 BankConfigs 工作表，使用預設設定")
                self.bank_configs = BANK_CONFIGS_DEFAULT
                return
            
            configs_sheet = self.sheet.worksheet("BankConfigs")
            configs_data = configs_sheet.get_all_records()
            
            self.bank_configs = {}
            
            for row in configs_data:
                try:
                    # 🆕 安全地轉換為字串並處理 None 值和數字
                    bank_name = str(row.get('銀行名稱', '')).strip() if row.get('銀行名稱') not in [None, ''] else ''
                    if not bank_name:  # 跳過空行
                        continue
                    
                    enabled_value = str(row.get('啟用狀態', 'TRUE')).strip().upper()
                    enabled = enabled_value == 'TRUE'
                    
                    if enabled:  # 只載入啟用的銀行
                        # 🆕 安全地處理所有欄位，包括數字型別
                        sender_email = str(row.get('寄件者Email', '')).strip() if row.get('寄件者Email') not in [None, ''] else ''
                        sender_domain = str(row.get('寄件者網域', '')).strip() if row.get('寄件者網域') not in [None, ''] else ''
                        keywords_raw = str(row.get('主旨關鍵字', '')).strip() if row.get('主旨關鍵字') not in [None, ''] else ''
                        has_attachment_raw = str(row.get('需要附件', 'TRUE')).strip().upper()
                        pdf_password = str(row.get('PDF密碼', '')).strip() if row.get('PDF密碼') not in [None, ''] else ''
                        
                        # 處理主旨關鍵字
                        keyword_list = [kw.strip() for kw in keywords_raw.split(',') if kw.strip()] if keywords_raw else []
                        
                        self.bank_configs[bank_name] = {
                            "sender_email": sender_email,
                            "sender_domain": sender_domain,
                            "subject_keywords": keyword_list,
                            "has_attachment": has_attachment_raw == 'TRUE',
                            "password": pdf_password if pdf_password else None
                        }
                        
                        print(f"   ✅ 載入銀行: {bank_name} -> {sender_domain}")
                
                except Exception as row_error:
                    print(f"   ⚠️ 跳過問題行: {row_error}")
                    continue
            
            print(f"✅ 從 Sheets 載入 {len(self.bank_configs)} 個銀行設定")
            
            # 顯示載入結果
            for bank_name, config in self.bank_configs.items():
                # 檢查是否為測試銀行
                is_test = '測試' in bank_name or 'test' in bank_name.lower()
                test_flag = '🧪' if is_test else '🏦'
                print(f"   {test_flag} {bank_name}: {config['sender_domain']}")
            
            # 如果沒有載入任何設定，使用預設
            if not self.bank_configs:
                print("⚠️ 未載入任何銀行設定，使用預設設定")
                self.bank_configs = BANK_CONFIGS_DEFAULT
            
        except Exception as e:
            print(f"❌ 載入 Sheets 銀行設定失敗: {e}")
            print("📝 使用預設銀行設定作為後備")
            self.bank_configs = BANK_CONFIGS_DEFAULT
    
    def create_credit_card_labels(self):
        """🆕 暫時跳過標籤建立，因為服務帳戶無法存取個人 Gmail"""
        print("ℹ️ 偵測到服務帳戶模式，無法管理個人 Gmail 標籤")
        print("💡 系統將在無標籤模式下運作")
        print("💡 如需完整標籤功能，請改用 OAuth 用戶授權")
        return True  # 返回 True 讓系統繼續運作
    
    def add_label_to_message(self, message_id, label_name):
        """🆕 暫時跳過標籤管理"""
        print(f"   ⏭️ 跳過標籤管理: {label_name}（服務帳戶限制）")
        return True
    
    def remove_label_from_message(self, message_id, label_name):
        """🆕 暫時跳過標籤管理"""
        print(f"   ⏭️ 跳過標籤移除: {label_name}（服務帳戶限制）")
        return True
    
    def add_label_to_message(self, message_id, label_name):
        """🆕 為訊息加上標籤"""
        try:
            # 先獲取標籤ID
            labels = self.gmail_service.users().labels().list(userId='me').execute()
            label_id = None
            for label in labels.get('labels', []):
                if label['name'] == label_name:
                    label_id = label['id']
                    break
            
            if label_id:
                body = {'addLabelIds': [label_id]}
                self.gmail_service.users().messages().modify(
                    userId='me', id=message_id, body=body
                ).execute()
                print(f"   ✅ 已加上標籤: {label_name}")
                return True
            else:
                print(f"   ⚠️ 找不到標籤: {label_name}")
                return False
        except Exception as e:
            print(f"   ❌ 加標籤失敗: {e}")
            return False
    
    def remove_label_from_message(self, message_id, label_name):
        """🆕 從訊息移除標籤"""
        try:
            # 先獲取標籤ID
            labels = self.gmail_service.users().labels().list(userId='me').execute()
            label_id = None
            for label in labels.get('labels', []):
                if label['name'] == label_name:
                    label_id = label['id']
                    break
            
            if label_id:
                body = {'removeLabelIds': [label_id]}
                self.gmail_service.users().messages().modify(
                    userId='me', id=message_id, body=body
                ).execute()
                print(f"   ✅ 已移除標籤: {label_name}")
                return True
            else:
                print(f"   ⚠️ 找不到標籤: {label_name}")
                return False
        except Exception as e:
            print(f"   ❌ 移除標籤失敗: {e}")
            return False
    
    def init_gmail_api(self):
        """初始化 Gmail API 連接 - 完整支援 OAuth + 服務帳戶"""
        try:
            # 🆕 方法1: OAuth 2.0 憑證（環境變數）- 優先方案
            oauth_credentials_json = os.getenv('GOOGLE_OAUTH_CREDENTIALS')
            if oauth_credentials_json:
                try:
                    print("🔐 嘗試 OAuth 認證（環境變數）...")
                    
                    # 將 OAuth 憑證寫入臨時檔案
                    creds_dict = json.loads(oauth_credentials_json)
                    temp_creds_file = 'temp_credentials.json'
                    
                    with open(temp_creds_file, 'w') as f:
                        json.dump(creds_dict, f)
                    
                    creds = None
                    token_file = 'gmail_oauth_token.json'
                    
                    # 檢查是否有儲存的 OAuth token
                    if os.path.exists(token_file):
                        try:
                            from google.oauth2.credentials import Credentials as OAuthCredentials
                            with open(token_file, 'r') as token:
                                token_info = json.load(token)
                            creds = OAuthCredentials.from_authorized_user_info(token_info, SCOPES)
                            print("✅ 找到已儲存的 OAuth 認證")
                        except Exception as e:
                            print(f"⚠️ 讀取 OAuth token 失敗: {e}")
                    
                    # 如果沒有有效認證或需要刷新
                    if not creds or not creds.valid:
                        if creds and creds.expired and creds.refresh_token:
                            print("🔄 刷新 OAuth Token...")
                            creds.refresh(Request())
                        else:
                            print("🌐 開始新的 OAuth 授權流程...")
                            flow = InstalledAppFlow.from_client_secrets_file(
                                temp_creds_file, SCOPES)
                            
                            # 雲端環境使用 console 模式
                            try:
                                # 嘗試本地伺服器模式
                                creds = flow.run_local_server(port=0, open_browser=False)
                                print("✅ OAuth 本地伺服器授權成功")
                            except Exception as server_error:
                                # 如果失敗，跳過 OAuth 繼續用服務帳戶
                                print(f"💡 本地伺服器不可用: {server_error}")
                                print("⏭️ 跳過 OAuth，繼續使用服務帳戶模式")
                                # 不執行 run_console，直接跳到服務帳戶認證
                                raise Exception("Skip OAuth in cloud environment")
                        
                        # 儲存 token 供下次使用
                        try:
                            token_data = {
                                'token': creds.token,
                                'refresh_token': creds.refresh_token,
                                'token_uri': creds.token_uri,
                                'client_id': creds.client_id,
                                'client_secret': creds.client_secret,
                                'scopes': creds.scopes
                            }
                            with open(token_file, 'w') as token:
                                json.dump(token_data, token)
                            print("✅ OAuth token 已儲存")
                        except Exception as e:
                            print(f"⚠️ 儲存 OAuth token 失敗: {e}")
                    
                    # 清理臨時檔案
                    try:
                        os.remove(temp_creds_file)
                    except:
                        pass
                    
                    self.gmail_service = build('gmail', 'v1', credentials=creds)
                    self.gmail_enabled = True
                    print("✅ Gmail API 連接成功(OAuth 環境變數模式)")
                    return True
                    
                except Exception as e:
                    print(f"❌ OAuth 環境變數認證失敗: {e}")
            
            # 方法2: 服務帳戶認證（現有方案）
            google_credentials = os.getenv('GOOGLE_CREDENTIALS')
            if google_credentials:
                try:
                    print("🔐 嘗試服務帳戶認證...")
                    creds_dict = json.loads(google_credentials)
                    project_id = creds_dict.get('project_id', '未知')
                    print(f"📋 服務帳戶專案: {project_id}")
                    
                    from google.oauth2.service_account import Credentials
                    credentials = Credentials.from_service_account_info(
                        creds_dict, scopes=SCOPES
                    )
                    
                    self.gmail_service = build('gmail', 'v1', credentials=credentials)
                    self.gmail_enabled = True
                    print("✅ Gmail API 連接成功(服務帳戶模式)")
                    return True
                    
                except Exception as e:
                    print(f"❌ 服務帳戶認證失敗: {e}")
            
            # 方法3: 從環境變數載入 OAuth Token（Pickle格式）
            gmail_token_b64 = os.getenv('GMAIL_TOKEN')
            if gmail_token_b64:
                try:
                    print("🔐 嘗試環境變數 OAuth Token（Pickle）...")
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
                    print("✅ Gmail API 連接成功(環境變數 Pickle Token 模式)")
                    return True
                    
                except Exception as e:
                    print(f"❌ 環境變數 Pickle Token 認證失敗: {e}")
            
            # 方法4: 本地開發模式（credentials.json）
            creds = None
            
            # 檢查是否有儲存的認證
            if os.path.exists('gmail_token.pickle'):
                try:
                    with open('gmail_token.pickle', 'rb') as token:
                        creds = pickle.load(token)
                    print("✅ 找到本地 Pickle token")
                except Exception as e:
                    print(f"⚠️ 讀取本地 Pickle token 失敗: {e}")
            
            # 如果沒有有效認證，進行 OAuth 流程
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                    print("🔄 本地 token 已刷新")
                else:
                    if os.path.exists('credentials.json'):
                        print("🌐 使用本地 credentials.json 進行 OAuth...")
                        flow = InstalledAppFlow.from_client_secrets_file(
                            'credentials.json', SCOPES)
                        try:
                            creds = flow.run_local_server(port=0)
                            print("✅ 本地 OAuth 授權成功")
                        except:
                            creds = flow.run_console()
                            print("✅ 本地 OAuth 控制台授權成功")
                    else:
                        print("❌ 未找到任何有效的 Gmail 認證方式")
                        print("💡 請設定以下任一環境變數：")
                        print("   - GOOGLE_OAUTH_CREDENTIALS: OAuth 2.0 憑證 JSON")
                        print("   - GOOGLE_CREDENTIALS: 服務帳戶憑證 JSON")
                        print("   - GMAIL_TOKEN: Base64 編碼的 OAuth token")
                        print("💡 或在專案根目錄放置 credentials.json 檔案")
                        return False
                
                # 儲存認證以供下次使用
                try:
                    with open('gmail_token.pickle', 'wb') as token:
                        pickle.dump(creds, token)
                    print("✅ 本地認證已儲存")
                except Exception as e:
                    print(f"⚠️ 儲存本地認證失敗: {e}")
            
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
            
            # 使用現有的 GOOGLE_CREDENTIALS 環境變數
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
    
    def load_bank_passwords(self):
        """載入銀行密碼設定 - 🆕 優先從 Sheets 讀取"""
        try:
            # 優先從 Sheets 中的設定讀取密碼
            if self.bank_configs:
                for bank_name, config in self.bank_configs.items():
                    if config.get('password'):
                        self.bill_data['bank_passwords'][bank_name] = config['password']
                
                if self.bill_data['bank_passwords']:
                    print(f"✅ 從 Sheets 載入 {len(self.bill_data['bank_passwords'])} 個銀行密碼")
            
            # 補充從環境變數載入的密碼
            passwords_json = os.getenv('BANK_PASSWORDS')
            if passwords_json:
                env_passwords = json.loads(passwords_json)
                for bank_name, password in env_passwords.items():
                    if bank_name not in self.bill_data['bank_passwords']:
                        self.bill_data['bank_passwords'][bank_name] = password
                print(f"✅ 從環境變數補充載入密碼")
            
            if not self.bill_data['bank_passwords']:
                print("⚠️ 未設定銀行密碼，將無法自動解鎖PDF")
            
        except Exception as e:
            print(f"❌ 載入銀行密碼失敗: {e}")
    
    def set_bank_password(self, bank_name, password):
        """設定銀行PDF密碼"""
        self.bill_data['bank_passwords'][bank_name] = password
        return f"✅ 已設定 {bank_name} 的PDF密碼"
    
    def check_gmail_for_bills(self):
        """🆕 檢查 Gmail 中的信用卡帳單 - 排除已處理的標籤"""
        if not self.gmail_enabled:
            return "❌ Gmail API 未啟用"
        
        try:
            print(f"🔍 開始檢查信用卡帳單 - {self.get_taiwan_time()}")
            
            # 計算檢查範圍(過去24小時)
            yesterday = (self.get_taiwan_datetime() - timedelta(days=1)).strftime('%Y/%m/%d')
            print(f"📅 搜尋範圍：{yesterday} 之後的信件")
            
            found_bills = []
            
            # 🆕 檢查每家銀行（使用動態設定）
            for bank_name, config in self.bank_configs.items():
                print(f"🏦 檢查 {bank_name}...")
                print(f"   📧 寄件者網域: {config['sender_domain']}")
                print(f"   🏷️ 主旨關鍵字: {config['subject_keywords']}")
                
                # 🆕 建立搜尋查詢 - 排除已處理的標籤
                query_parts = []
                query_parts.append(f"from:{config['sender_domain']}")
                query_parts.append(f"after:{yesterday}")
                query_parts.append("has:attachment")
                query_parts.append("-label:信用卡/已處理")  # 🆕 排除已處理
                query_parts.append("-label:信用卡/處理失敗")  # 🆕 排除失敗的
                
                # 加入主旨關鍵字
                for keyword in config['subject_keywords']:
                    if keyword.strip():
                        query_parts.append(f'subject:"{keyword.strip()}"')
                
                query = " ".join(query_parts)
                print(f"   🔍 搜尋條件: {query}")
                
                try:
                    # 執行搜尋
                    results = self.gmail_service.users().messages().list(
                        userId='me', q=query, maxResults=10
                    ).execute()
                    
                    messages = results.get('messages', [])
                print(f"   📬 找到 {len(messages)} 封符合條件的郵件")
                
                # 🆕 如果是測試銀行且沒找到，嘗試更寬鬆的搜尋
                if bank_name == "測試銀行" and len(messages) == 0:
                    print(f"   🔄 測試銀行無結果，嘗試寬鬆搜尋...")
                    # 更寬鬆的搜尋條件
                    loose_query_parts = []
                    loose_query_parts.append(f"from:{config['sender_domain']}")
                    loose_query_parts.append(f"after:{yesterday}")
                    loose_query_parts.append("has:attachment")
                    # 不加主旨限制，看看能找到什麼
                    
                    loose_query = " ".join(loose_query_parts)
                    print(f"   🔍 寬鬆搜尋條件: {loose_query}")
                    
                    loose_results = self.gmail_service.users().messages().list(
                        userId='me', q=loose_query, maxResults=10
                    ).execute()
                    
                    loose_messages = loose_results.get('messages', [])
                    print(f"   📬 寬鬆搜尋找到 {len(loose_messages)} 封郵件")
                    
                    # 檢查這些郵件的主旨
                    for msg in loose_messages[:3]:  # 只檢查前3封
                        try:
                            msg_detail = self.gmail_service.users().messages().get(
                                userId='me', id=msg['id'], format='metadata'
                            ).execute()
                            
                            headers = msg_detail['payload'].get('headers', [])
                            subject = next((h['value'] for h in headers if h['name'] == 'Subject'), '無主旨')
                            sender = next((h['value'] for h in headers if h['name'] == 'From'), '無寄件者')
                            
                            print(f"     📧 郵件主旨: {subject}")
                            print(f"     📧 寄件者: {sender}")
                            
                        except Exception as e:
                            print(f"     ❌ 無法讀取郵件詳情: {e}")
                    
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
        """🆕 處理單封 Gmail 訊息 - 加入標籤管理"""
        try:
            # 獲取郵件詳細資訊
            message = self.gmail_service.users().messages().get(
                userId='me', id=message_id, format='full'
            ).execute()
            
            # 提取郵件基本資訊
            headers = message['payload'].get('headers', [])
            subject = next((h['value'] for h in headers if h['name'] == 'Subject'), '')
            date = next((h['value'] for h in headers if h['name'] == 'Date'), '')
            
            print(f"   📧 處理郵件: {subject[:50]}...")
            
            # 🆕 處理開始時加上「處理中」標籤
            self.add_label_to_message(message_id, "信用卡/處理中")
            
            # 檢查是否已處理過（雙重保險）
            if self.is_bill_already_processed(message_id):
                print(f"   ⏭️ 已處理過，跳過")
                self.remove_label_from_message(message_id, "信用卡/處理中")
                return None
            
            # 尋找PDF附件
            pdf_data = self.extract_pdf_attachment(message)
            if not pdf_data:
                print(f"   ⚠️ 未找到PDF附件")
                self.remove_label_from_message(message_id, "信用卡/處理中")
                self.add_label_to_message(message_id, "信用卡/已跳過")
                return None
            
            # 處理PDF
            bill_info = self.process_pdf_bill(pdf_data, bank_name, message_id, subject, date)
            
            # 🆕 根據處理結果加上對應標籤
            if bill_info and bill_info['status'] == '✅ 處理成功':
                self.remove_label_from_message(message_id, "信用卡/處理中")
                self.add_label_to_message(message_id, "信用卡/已處理")
            else:
                self.remove_label_from_message(message_id, "信用卡/處理中")
                self.add_label_to_message(message_id, "信用卡/處理失敗")
            
            return bill_info
            
        except Exception as e:
            print(f"   ❌ 處理郵件失敗: {e}")
            # 🆕 錯誤時也要移除處理中標籤
            try:
                self.remove_label_from_message(message_id, "信用卡/處理中")
                self.add_label_to_message(message_id, "信用卡/處理失敗")
            except:
                pass
            return None
    
    # ... 其他方法保持不變 ...
    
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
            
            # 嘗試解鎖PDF
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
            
            # 使用智能 OCR 處理
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
            
            # LLM處理
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
            
            # 儲存處理結果
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
                    
                    # 重新建立無密碼的PDF
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
            
            # 第1層：嘗試直接文字提取
            direct_text = self.pdf_to_text_backup(pdf_data)
            
            # 評估直接提取的品質
            if direct_text and self.is_text_quality_good(direct_text):
                print(f"   ✅ 直接文字提取成功，品質良好")
                return direct_text
            
            # 第2層：使用 Google Vision OCR
            if self.vision_enabled:
                print(f"   🔍 直接提取品質不佳，使用 Google Vision OCR...")
                ocr_text = self.google_vision_ocr(pdf_data)
                if ocr_text:
                    return ocr_text
            
            # 第3層：返回直接提取的結果（總比沒有好）
            print(f"   ⚠️ OCR 不可用，使用直接提取結果")
            return direct_text
            
        except Exception as e:
            print(f"   ❌ 智能文字提取失敗: {e}")
            return None
    
    def is_text_quality_good(self, text):
        """評估文字提取品質"""
        if not text or len(text.strip()) < 100:
            return False
        
        # 檢查是否包含常見的帳單關鍵字
        keywords = ['本期應繳', '應繳金額', '繳款期限', '信用卡', '帳單', '交易', '消費']
        keyword_count = sum(1 for keyword in keywords if keyword in text)
        
        # 至少要有2個關鍵字才認為品質良好
        return keyword_count >= 2
    
    def google_vision_ocr(self, pdf_data):
        """使用 Google Vision 進行 OCR"""
        try:
            if not self.vision_enabled:
                return None
            
            # PDF轉圖片
            images = convert_from_bytes(pdf_data, dpi=200, fmt='PNG')
            
            all_text = ""
            for i, image in enumerate(images):
                print(f"     📷 OCR處理第 {i+1} 頁...")
                
                # 將PIL圖片轉為bytes
                import io
                img_byte_arr = io.BytesIO()
                image.save(img_byte_arr, format='PNG')
                image_content = img_byte_arr.getvalue()
                
                # Google Vision OCR
                vision_image = vision.Image(content=image_content)
                response = self.vision_client.text_detection(image=vision_image)
                
                # 檢查錯誤
                if response.error.message:
                    print(f"     ❌ Google Vision API 錯誤: {response.error.message}")
                    continue
                
                # 提取文字
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
            
            # Groq LLM 處理邏輯（目前被停用）
            return self.basic_parse_bill(extracted_text, bank_name)
            
        except Exception as e:
            print(f"   ❌ LLM處理失敗: {e}")
            return self.basic_parse_bill(extracted_text, bank_name)
    
    def basic_parse_bill(self, extracted_text, bank_name):
        """基礎帳單解析方案(不使用LLM)"""
        try:
            print("   🔧 使用基礎解析方案")
            
            # 基本資料結構
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
            
            # 簡單的關鍵字匹配
            lines = extracted_text.split('\n')
            
            for line in lines:
                line = line.strip()
                
                # 查找金額
                if '本期應繳' in line or '應繳金額' in line:
                    amounts = re.findall(r'[\d,]+', line)
                    if amounts:
                        bill_data['total_amount'] = amounts[-1].replace(',', '')
                
                # 查找最低應繳
                elif '最低應繳' in line:
                    amounts = re.findall(r'[\d,]+', line)
                    if amounts:
                        bill_data['minimum_payment'] = amounts[-1].replace(',', '')
                
                # 查找繳款期限
                elif '繳款期限' in line or '到期日' in line:
                    dates = re.findall(r'\d{4}[/-]\d{1,2}[/-]\d{1,2}', line)
                    if dates:
                        bill_data['due_date'] = dates[0]
            
            # 如果找到了基本資訊就算成功
            if bill_data['total_amount'] or bill_data['minimum_payment']:
                print("   ✅ 基礎解析成功")
                return bill_data
            else:
                print("   ❌ 基礎解析失敗")
                return None
                
        except Exception as e:
            print(f"   ❌ 基礎解析失敗: {e}")
            return None
    
    def is_bill_already_processed(self, message_id):
        """檢查帳單是否已處理"""
        return any(bill['message_id'] == message_id for bill in self.bill_data['processed_bills'])
    
    def get_recent_bills(self, limit=5):
        """獲取最近處理的帳單"""
        if not self.bill_data['processed_bills']:
            return "📝 尚未處理任何帳單"
        
        recent_bills = sorted(
            self.bill_data['processed_bills'], 
            key=lambda x: x['processed_time'], 
            reverse=True
        )[:limit]
        
        result = f"📧 最近 {len(recent_bills)} 份帳單：\n\n"
        
        for i, bill in enumerate(recent_bills, 1):
            result += f"{i}. 🏦 {bill['bank_name']}\n"
            result += f"   📅 {bill['date'][:10] if bill['date'] else '未知日期'}\n"
            result += f"   {bill['status']}\n"
            result += f"   🕒 {bill['processed_time']}\n"
            
            if bill.get('bill_data') and bill['status'] == '✅ 處理成功':
                bill_info = bill['bill_data']
                result += f"   💰 應繳：{bill_info.get('total_amount', 'N/A')}\n"
                result += f"   📊 交易：{len(bill_info.get('transactions', []))} 筆\n"
            
            result += "\n"
        
        return result
    
    def get_bill_summary(self, bank_name=None):
        """獲取帳單摘要"""
        processed_bills = self.bill_data['processed_bills']
        
        if bank_name:
            processed_bills = [b for b in processed_bills if b['bank_name'] == bank_name]
            if not processed_bills:
                return f"📝 {bank_name} 尚未處理任何帳單"
        
        if not processed_bills:
            return "📝 尚未處理任何帳單"
        
        successful_bills = [b for b in processed_bills if b['status'] == '✅ 處理成功']
        
        result = f"📊 {'帳單處理摘要' if not bank_name else f'{bank_name} 帳單摘要'}：\n\n"
        result += f"📧 總處理數量：{len(processed_bills)} 份\n"
        result += f"✅ 成功處理：{len(successful_bills)} 份\n"
        result += f"❌ 處理失敗：{len(processed_bills) - len(successful_bills)} 份\n\n"
        
        if successful_bills:
            total_amount = 0
            total_transactions = 0
            
            for bill in successful_bills:
                if bill.get('bill_data'):
                    bill_info = bill['bill_data']
                    try:
                        amount = bill_info.get('total_amount', '0')
                        if isinstance(amount, str):
                            amount = re.sub(r'[^\d.]', '', amount)
                        total_amount += float(amount or 0)
                    except:
                        pass
                    
                    total_transactions += len(bill_info.get('transactions', []))
            
            result += f"💰 總應繳金額：{total_amount:,.0f} 元\n"
            result += f"📊 總交易筆數：{total_transactions} 筆\n"
        
        return result
    
    def start_monitoring_thread(self):
        """啟動背景監控執行緒"""
        if self.is_monitoring:
            return "⚠️ 監控已在執行中"
        
        def monitoring_loop():
            self.is_monitoring = True
            print("🔄 信用卡帳單監控執行緒已啟動")
            
            while self.is_monitoring:
                try:
                    # 每天 08:00 執行檢查
                    now = self.get_taiwan_datetime()
                    target_time = now.replace(hour=8, minute=0, second=0, microsecond=0)
                    
                    # 如果今天已過8點，設定為明天8點
                    if now > target_time:
                        target_time += timedelta(days=1)
                    
                    sleep_seconds = (target_time - now).total_seconds()
                    
                    print(f"💤 下次檢查時間：{target_time.strftime('%Y/%m/%d %H:%M')}")
                    
                    # 分段睡眠，以便可以中斷
                    while sleep_seconds > 0 and self.is_monitoring:
                        sleep_time = min(300, sleep_seconds)  # 每5分鐘檢查一次是否要停止
                        time.sleep(sleep_time)
                        sleep_seconds -= sleep_time
                    
                    if self.is_monitoring:
                        # 執行檢查
                        result = self.check_gmail_for_bills()
                        print(f"📧 定時檢查結果：{result}")
                
                except Exception as e:
                    print(f"❌ 監控執行緒錯誤: {e}")
                    time.sleep(300)  # 錯誤時等待5分鐘再繼續
        
        self.monitoring_thread = threading.Thread(target=monitoring_loop, daemon=True)
        self.monitoring_thread.start()
        
        return "✅ 信用卡帳單監控已啟動"
    
    def stop_monitoring(self):
        """停止背景監控"""
        self.is_monitoring = False
        return "⏹️ 信用卡帳單監控已停止"
    
    def get_monitoring_status(self):
        """🆕 獲取監控狀態 - 顯示動態銀行設定"""
        if not self.is_monitoring:
            return {
                'status': 'stopped',
                'gmail_enabled': self.gmail_enabled,
                'groq_enabled': self.groq_enabled,
                'vision_ocr_enabled': self.vision_enabled,
                'sheets_enabled': self.sheets_enabled,
                'monitored_banks': list(self.bank_configs.keys()),
                'last_check_time': self.bill_data.get('last_check_time'),
                'processed_bills_count': len(self.bill_data['processed_bills'])
            }
        else:
            return {
                'status': 'running',
                'gmail_enabled': self.gmail_enabled,
                'groq_enabled': self.groq_enabled,
                'vision_ocr_enabled': self.vision_enabled,
                'sheets_enabled': self.sheets_enabled,
                'monitored_banks': list(self.bank_configs.keys()),
                'last_check_time': self.bill_data.get('last_check_time'),
                'processed_bills_count': len(self.bill_data['processed_bills'])
            }
    
    def handle_command(self, message_text):
        """處理信用卡帳單相關指令"""
        message_text = message_text.strip()
        
        try:
            if message_text == '檢查帳單':
                return self.check_gmail_for_bills()
            
            elif message_text == '最近帳單':
                return self.get_recent_bills()
            
            elif message_text == '帳單摘要':
                return self.get_bill_summary()
            
            elif message_text.startswith('帳單摘要 '):
                bank_name = message_text[4:].strip()
                return self.get_bill_summary(bank_name)
            
            elif message_text == '帳單監控狀態':
                status = self.get_monitoring_status()
                result = f"📊 信用卡帳單監控狀態：\n\n"
                result += f"🔄 監控狀態：{'🟢 執行中' if status['status'] == 'running' else '🔴 已停止'}\n"
                result += f"📧 Gmail API：{'✅ 已啟用' if status['gmail_enabled'] else '❌ 未啟用'}\n"
                result += f"🤖 Groq LLM：{'✅ 已啟用' if status['groq_enabled'] else '❌ 未啟用'}\n"
                result += f"👁️ Google Vision OCR：{'✅ 已啟用' if status['vision_ocr_enabled'] else '⚠️ 未啟用'}\n"
                result += f"📊 Google Sheets：{'✅ 已啟用' if status['sheets_enabled'] else '⚠️ 未啟用'}\n\n"
                result += f"🏦 監控銀行：{', '.join(status['monitored_banks'])}\n"
                result += f"📊 已處理帳單：{status['processed_bills_count']} 份\n"
                if status['last_check_time']:
                    result += f"🕒 上次檢查：{status['last_check_time']}\n"
                return result
            
            elif match := re.match(r'設定密碼\s+(.+?)\s+(.+)', message_text):
                bank_name, password = match.groups()
                return self.set_bank_password(bank_name.strip(), password.strip())
            
            elif message_text == '帳單幫助':
                return self.get_help_text()
            
            else:
                return "❌ 指令格式不正確\n💡 輸入「帳單幫助」查看使用說明"
        
        except Exception as e:
            return f"❌ 處理失敗：{str(e)}\n💡 請檢查指令格式"
    
    def get_help_text(self):
        """🆕 獲取幫助訊息 - 更新版本"""
        return f"""💳 信用卡帳單自動監控功能 v2.0：

📧 監控功能：
- 檢查帳單 - 立即檢查Gmail新帳單
- 帳單監控狀態 - 查看監控系統狀態
- 最近帳單 - 顯示最近處理的帳單
- 帳單摘要 - 所有帳單處理摘要
- 帳單摘要 永豐銀行 - 特定銀行帳單摘要

🔧 設定功能：
- 設定密碼 永豐銀行 your_password - 設定PDF密碼
- 設定密碼 台新銀行 your_password - 設定PDF密碼
- 設定密碼 星展銀行 your_password - 設定PDF密碼

🏦 目前監控銀行：
{chr(10).join(f"- {bank} ({config['sender_domain']})" for bank, config in self.bank_configs.items())}

⚙️ 系統功能：
- 📧 自動監控Gmail信用卡帳單
- 🏷️ Gmail標籤管理（防重複處理）
- 📊 Google Sheets動態銀行設定
- 🔓 自動解鎖PDF密碼保護
- 📄 PDF智能文字提取
- 🤖 LLM智能解析(Groq + Llama)
- 📊 結構化數據提取
- 💾 帳單記錄保存

🕒 監控時間：
- 每天早上08:00自動檢查Gmail
- 檢查過去24小時的新郵件
- 自動處理符合條件的帳單

🏷️ Gmail標籤系統：
- 信用卡/已處理 - 成功處理的帳單
- 信用卡/處理失敗 - 處理失敗的帳單
- 信用卡/處理中 - 正在處理中
- 信用卡/已跳過 - 跳過的郵件

💡 使用提示：
- 銀行設定可在 Google Sheets BankConfigs 分頁管理
- 首次使用請先設定各銀行PDF密碼
- 系統會自動跳過已處理的帳單（透過Gmail標籤）
- 處理結果會保存在系統記憶中

🔧 技術架構：
- Gmail API：郵件監控和標籤管理
- Google Sheets：動態銀行設定管理
- PyPDF2：PDF文字提取
- Google Vision OCR：圖片文字識別
- Groq LLM：智能內容解析
- 背景執行緒：定時自動監控

📊 資料格式：
- 帳單週期、繳款期限
- 本期應繳、最低應繳金額
- 交易明細(日期、商家、金額)
- 消費統計和分析

🆕 v2.0 新功能：
- Google Sheets 動態設定管理
- Gmail 標籤系統防重複處理
- 支援測試銀行設定"""


# 建立全域實例
credit_card_manager = CreditCardManager()


# 對外接口函數，供 main.py 使用
def handle_credit_card_command(message_text):
    """處理信用卡帳單指令 - 對外接口"""
    return credit_card_manager.handle_command(message_text)


def get_credit_card_summary():
    """獲取信用卡帳單摘要 - 對外接口"""
    return credit_card_manager.get_bill_summary()


def get_recent_bills(limit=5):
    """獲取最近帳單 - 對外接口"""
    return credit_card_manager.get_recent_bills(limit)


def start_credit_card_monitor():
    """啟動信用卡帳單監控 - 對外接口"""
    return credit_card_manager.start_monitoring_thread()


def stop_credit_card_monitor():
    """停止信用卡帳單監控 - 對外接口"""
    return credit_card_manager.stop_monitoring()


def get_credit_card_status():
    """獲取監控狀態 - 對外接口"""
    return credit_card_manager.get_monitoring_status()


def is_credit_card_command(message_text):
    """判斷是否為信用卡帳單指令 - 對外接口"""
    credit_card_keywords = [
        '檢查帳單', '最近帳單', '帳單摘要', '帳單監控狀態', 
        '設定密碼', '帳單幫助'
    ]
    return any(keyword in message_text for keyword in credit_card_keywords)


def is_credit_card_query(message_text):
    """判斷是否為信用卡查詢指令 - 對外接口"""
    query_patterns = [
        '最近帳單', '帳單摘要', '帳單監控狀態', '帳單幫助'
    ]
    return any(pattern in message_text for pattern in query_patterns)


if __name__ == "__main__":
    # 測試功能
    ccm = CreditCardManager()
    print("=== 測試信用卡帳單監控 v2.0 ===")
    print(ccm.handle_command("帳單監控狀態"))
    print()
    print("=== 測試檢查帳單 ===")
    print(ccm.handle_command("檢查帳單"))
    print()
    print("=== 測試幫助 ===")
    print(ccm.handle_command("帳單幫助"))
