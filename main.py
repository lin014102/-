# ===== 在 main.py 中新增以下測試端點 =====
# 放在其他測試端點附近

@app.route('/test/bill-amounts')
def test_bill_amounts():
    """測試帳單金額查詢功能"""
    try:
        banks = ['永豐', '台新', '國泰', '星展', '匯豐', '玉山', '聯邦']
        results = {}
        
        for bank in banks:
            bill_info = reminder_bot.get_bill_amount(bank)
            results[bank] = bill_info
        
        return jsonify({
            'success': True,
            'data': results,
            'timestamp': get_taiwan_time()
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': get_taiwan_time()
        })

@app.route('/test/add-test-bill')
def test_add_bill():
    """手動新增測試帳單金額"""
    try:
        # 新增一筆測試資料
        success = reminder_bot.update_bill_amount(
            bank_name="永豐銀行",
            amount="NT$15,234",
            due_date="2025/01/24",
            statement_date="2025/01/01"
        )
        
        if success:
            return jsonify({
                'success': True,
                'message': '測試帳單金額新增成功',
                'test_data': {
                    'bank': '永豐銀行',
                    'amount': 'NT$15,234',
                    'due_date': '2025/01/24'
                },
                'timestamp': get_taiwan_time()
            })
        else:
            return jsonify({
                'success': False,
                'error': '新增失敗',
                'timestamp': get_taiwan_time()
            })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': get_taiwan_time()
        })

@app.route('/test/enhanced-reminder')
def test_enhanced_reminder():
    """測試增強版提醒訊息顯示"""
    try:
        # 測試不同的待辦事項內容
        test_todos = [
            "繳永豐卡費",
            "繳台新卡費", 
            "繳國泰卡費",
            "買菜",
            "繳星展卡費"
        ]
        
        results = {}
        for todo in test_todos:
            enhanced = reminder_bot._enhance_todo_with_bill_amount(todo)
            results[todo] = enhanced
        
        return jsonify({
            'success': True,
            'data': results,
            'timestamp': get_taiwan_time()
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': get_taiwan_time()
        })

@app.route('/test/bank-mapping')
def test_bank_mapping():
    """測試銀行名稱標準化"""
    try:
        test_banks = [
            "永豐銀行",
            "SinoPac", 
            "台新銀行",
            "TAISHIN",
            "星展銀行",
            "DBS Bank",
            "國泰世華",
            "CATHAY",
            "未知銀行"
        ]
        
        results = {}
        for bank in test_banks:
            normalized = reminder_bot._normalize_bank_name(bank)
            results[bank] = normalized
        
        return jsonify({
            'success': True,
            'data': results,
            'timestamp': get_taiwan_time()
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': get_taiwan_time()
        })

# ===== 修改 health 端點，加入帳單金額功能狀態 =====
# 在現有的 health() 函數的 'modules' 字典中新增：

# 找到原本的 health() 函數，在 'modules' 字典中新增以下內容：
'''
'bill_amount_integration': {
    'mongodb_enabled': reminder_bot.use_mongodb,
    'collection_ready': hasattr(reminder_bot, 'bill_amounts_collection') if reminder_bot.use_mongodb else True,
    'test_banks': ['永豐', '台新', '國泰', '星展', '匯豐', '玉山', '聯邦'],
    'features': ['bank_name_normalization', 'amount_storage', 'enhanced_reminders']
}
'''

# 完整的測試流程建議：
"""
1. 部署修改後的程式碼
2. 訪問 /health 確認系統正常運行
3. 使用 /test/bank-mapping 測試銀行名稱對應
4. 使用 /test/add-test-bill 新增測試資料
5. 使用 /test/bill-amounts 確認資料已儲存
6. 使用 /test/enhanced-reminder 測試提醒顯示
7. 等待實際帳單分析完成，觀察自動同步效果
"""
