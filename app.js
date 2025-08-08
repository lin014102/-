// ========== 第1段：資料結構和解析函數 ==========

// 在 initUser 函數中添加 timerReminders 欄位
function initUser(userId) {
  if (!userData[userId]) {
    userData[userId] = {
      todos: [],
      monthlyTodos: [],
      timerReminders: [], // 新增：定時提醒列表
      morningReminderTime: '09:00',
      eveningReminderTime: '18:00',
      timezone: 'Asia/Taipei'
    };
    console.log(`初始化用戶: ${userId}`);
    saveData();
  }
  
  // 為舊用戶添加新欄位
  if (!userData[userId].monthlyTodos) {
    userData[userId].monthlyTodos = [];
  }
  if (!userData[userId].timerReminders) { // 新增
    userData[userId].timerReminders = [];
    saveData();
  }
}

// 新增：解析定時提醒格式
function parseTimerReminder(text) {
  // 支援格式：
  // "5分鐘後倒垃圾" 或 "倒垃圾5分鐘後" 
  // "30分鐘後開會" 或 "開會30分鐘後"
  // "1小時後打電話" 或 "打電話1小時後"
  // "2小時30分鐘後去接小孩"
  
  const patterns = [
    // 時間在前：5分鐘後倒垃圾, 1小時30分鐘後開會
    /^(\d+)小時(?:(\d+)分鐘)?後(.+)$/,
    /^(\d+)分鐘後(.+)$/,
    // 時間在後：倒垃圾5分鐘後, 開會1小時30分鐘後  
    /^(.+?)(\d+)小時(?:(\d+)分鐘)?後$/,
    /^(.+?)(\d+)分鐘後$/
  ];
  
  for (let i = 0; i < patterns.length; i++) {
    const match = text.match(patterns[i]);
    if (match) {
      let hours = 0, minutes = 0, content = '';
      
      if (i === 0) { // 小時分鐘在前
        hours = parseInt(match[1]);
        minutes = match[2] ? parseInt(match[2]) : 0;
        content = match[3].trim();
      } else if (i === 1) { // 分鐘在前
        minutes = parseInt(match[1]);
        content = match[2].trim();
      } else if (i === 2) { // 小時分鐘在後
        content = match[1].trim();
        hours = parseInt(match[2]);
        minutes = match[3] ? parseInt(match[3]) : 0;
      } else if (i === 3) { // 分鐘在後
        content = match[1].trim();
        minutes = parseInt(match[2]);
      }
      
      // 計算總分鐘數
      const totalMinutes = hours * 60 + minutes;
      
      // 驗證合理性（最大24小時）
      if (totalMinutes > 0 && totalMinutes <= 1440 && content) {
        // 計算提醒時間
        const remindTime = new Date();
        remindTime.setMinutes(remindTime.getMinutes() + totalMinutes);
        
        return {
          isTimer: true,
          content: content,
          minutes: totalMinutes,
          hours: hours,
          remindTime: remindTime,
          timeText: hours > 0 ? `${hours}小時${minutes > 0 ? minutes + '分鐘' : ''}` : `${minutes}分鐘`
        };
      }
    }
  }
  
  return {
    isTimer: false,
    content: text,
    minutes: 0,
    hours: 0,
    remindTime: null,
    timeText: ''
  };
}

// 新增：格式化剩餘時間顯示
function formatRemainingTime(remindTime) {
  const now = new Date();
  const diffMs = remindTime.getTime() - now.getTime();
  
  if (diffMs <= 0) {
    return '已過期';
  }
  
  const diffMinutes = Math.ceil(diffMs / (1000 * 60));
  const hours = Math.floor(diffMinutes / 60);
  const minutes = diffMinutes % 60;
  
  if (hours > 0) {
    return minutes > 0 ? `${hours}小時${minutes}分鐘` : `${hours}小時`;
  } else {
    return `${minutes}分鐘`;
  }
}
// ========== 第2段：定時提醒管理函數 ==========

// 新增：添加定時提醒
async function addTimerReminder(userId, content, totalMinutes, remindTime, timeText) {
  const timerItem = {
    id: Date.now(),
    content: content,
    totalMinutes: totalMinutes,
    remindTime: remindTime.toISOString(),
    timeText: timeText,
    createdAt: getTaiwanTime(),
    completed: false,
    notified: false
  };
  
  userData[userId].timerReminders.push(timerItem);
  
  try {
    await saveData();
    console.log(`用戶 ${userId} 新增定時提醒: ${content}, ${timeText}後`);
  } catch (err) {
    console.error('新增定時提醒時儲存失敗:', err);
    throw err;
  }
  
  const remindTimeStr = remindTime.toLocaleString('zh-TW', { timeZone: 'Asia/Taipei' });
  
  return `⏰ 已設定定時提醒：「${content}」
🕐 將在 ${timeText} 後提醒您
📅 提醒時間：${remindTimeStr}
🆔 提醒編號：${userData[userId].timerReminders.length}

💡 輸入「定時清單」可查看所有定時提醒
💡 輸入「取消定時 [編號]」可取消提醒`;
}

// 新增：取消定時提醒
async function cancelTimerReminder(userId, index) {
  const timerReminders = userData[userId].timerReminders;
  
  if (index < 0 || index >= timerReminders.length) {
    return `❌ 編號不正確，請輸入 1 到 ${timerReminders.length} 之間的數字`;
  }
  
  const cancelledTimer = timerReminders.splice(index, 1)[0];
  
  try {
    await saveData();
    console.log(`用戶 ${userId} 取消定時提醒: ${cancelledTimer.content}`);
  } catch (err) {
    console.error('取消定時提醒時儲存失敗:', err);
    // 如果儲存失敗，恢復刪除的項目
    timerReminders.splice(index, 0, cancelledTimer);
    return '❌ 取消失敗，請稍後再試';
  }
  
  return `🗑️ 已取消定時提醒：「${cancelledTimer.content}」
剩餘 ${timerReminders.length} 個定時提醒`;
}

// 新增：獲取定時提醒清單
function getTimerReminderList(userId) {
  const timerReminders = userData[userId].timerReminders;
  const now = new Date();
  
  // 過濾掉已過期且已通知的提醒
  const activeTimers = timerReminders.filter(timer => {
    const remindTime = new Date(timer.remindTime);
    return remindTime > now || !timer.notified;
  });
  
  console.log(`用戶 ${userId} 查詢定時清單，活躍數: ${activeTimers.length}`);
  
  if (activeTimers.length === 0) {
    return '⏰ 目前沒有定時提醒\n💡 輸入「5分鐘後倒垃圾」來設定定時提醒\n💡 也可以用「1小時30分鐘後開會」等格式';
  }
  
  let message = `⏰ 定時提醒清單 (${activeTimers.length} 項)：\n\n`;
  
  // 按時間排序
  activeTimers.sort((a, b) => new Date(a.remindTime) - new Date(b.remindTime));
  
  activeTimers.forEach((timer, index) => {
    const remindTime = new Date(timer.remindTime);
    const remainingTime = formatRemainingTime(remindTime);
    const remindTimeStr = remindTime.toLocaleString('zh-TW', { 
      timeZone: 'Asia/Taipei',
      month: 'numeric',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
    
    const statusIcon = timer.notified ? '✅' : (remainingTime === '已過期' ? '⏰' : '🕐');
    const statusText = timer.notified ? '(已提醒)' : (remainingTime === '已過期' ? '(待提醒)' : `(剩餘${remainingTime})`);
    
    message += `${index + 1}. ${statusIcon} ${timer.content}\n`;
    message += `   📅 ${remindTimeStr} ${statusText}\n\n`;
  });
  
  message += '💡 輸入「取消定時 [編號]」可取消指定提醒';
  
  return message;
}

// 新增：清理過期的定時提醒
async function cleanupExpiredTimers() {
  let totalCleaned = 0;
  const now = new Date();
  const oneDayAgo = new Date(now.getTime() - 24 * 60 * 60 * 1000); // 24小時前
  
  for (const userId in userData) {
    const user = userData[userId];
    if (!user.timerReminders) continue;
    
    const originalLength = user.timerReminders.length;
    
    // 清理超過24小時且已通知的提醒
    user.timerReminders = user.timerReminders.filter(timer => {
      const remindTime = new Date(timer.remindTime);
      return remindTime > oneDayAgo || !timer.notified;
    });
    
    totalCleaned += (originalLength - user.timerReminders.length);
  }
  
  if (totalCleaned > 0) {
    await saveData();
    console.log(`🧹 清理了 ${totalCleaned} 個過期定時提醒`);
  }
  
  return totalCleaned;
}
// ========== 第3段：修改指令處理邏輯 ==========

// 在 handleEvent 函數的指令解析部分添加以下代碼
// 找到現有的 else if 語句，在適當位置插入：

// 新增定時提醒相關指令（插入到現有指令處理中）
else if (userMessage.startsWith('取消定時 ')) {
  const index = parseInt(userMessage.substring(5).trim()) - 1;
  replyMessage = await cancelTimerReminder(userId, index);
} else if (userMessage === '定時清單') {
  replyMessage = getTimerReminderList(userId);
} else if (userMessage === '清理定時') {
  const cleaned = await cleanupExpiredTimers();
  replyMessage = `🧹 清理完成！共清理了 ${cleaned} 個過期定時提醒`;
}
// 檢查是否為定時提醒格式（這個要放在最後的 else 之前）
else {
  // 首先檢查是否為定時提醒格式
  const timerParsed = parseTimerReminder(userMessage);
  if (timerParsed.isTimer) {
    try {
      replyMessage = await addTimerReminder(
        userId, 
        timerParsed.content, 
        timerParsed.minutes, 
        timerParsed.remindTime, 
        timerParsed.timeText
      );
    } catch (error) {
      console.error(`添加定時提醒失敗:`, error);
      replyMessage = '❌ 設定定時提醒失敗，請稍後再試';
    }
  } else {
    replyMessage = '指令不正確，請輸入「幫助」查看使用說明';
  }
}

// 修改幫助訊息函數，添加定時提醒說明
function getHelpMessage() {
  return `📋 代辦事項機器人使用說明：

📝 基本功能：
• 新增 [事項] - 新增代辦事項
• 新增 8/9號繳卡費 - 新增有日期的事項
• 刪除 [編號] - 刪除指定代辦事項
• 查詢 或 清單 - 查看所有代辦事項

⏰ 定時提醒（新功能！）：
• 5分鐘後倒垃圾 - 5分鐘後提醒倒垃圾
• 1小時後開會 - 1小時後提醒開會  
• 2小時30分鐘後接小孩 - 指定時間後提醒
• 定時清單 - 查看所有定時提醒
• 取消定時 [編號] - 取消指定定時提醒
• 清理定時 - 清理過期的定時提醒

🔄 每月固定事項：
• 每月新增 [事項] - 新增每月固定事項
• 每月新增 5號繳卡費 - 新增每月固定日期事項
• 每月刪除 [編號] - 刪除每月固定事項
• 每月清單 - 查看每月固定事項
• 生成本月 - 將本月固定事項加入代辦清單

⏰ 提醒設定：
• 早上時間 [HH:MM] - 設定早上提醒時間
• 晚上時間 [HH:MM] - 設定晚上提醒時間
• 查詢時間 - 查看目前提醒時間

🔔 智能提醒：
• 有日期的事項：只在前一天提醒
• 沒日期的事項：每天提醒
• 定時提醒：到指定時間立即提醒
• 每月固定事項：需手動生成到代辦清單

🧪 測試功能：
• 狀態 - 查看系統狀態
• 測試提醒 - 立即測試提醒功能
• 測試時間 [HH:MM] - 測試特定時間提醒

💡 使用範例：
• 每月新增 5號繳信用卡費
• 30分鐘後開會
• 倒垃圾5分鐘後
• 2小時後打電話給媽媽
• 1小時30分鐘後去接小孩
• 新增 8/15號繳電費
• 早上時間 08:30

輸入「幫助」可重複查看此說明`;
}
// ========== 第4段：定時檢查和發送提醒 ==========

// 新增：檢查並發送定時提醒
async function checkAndSendTimerReminders() {
  const now = new Date();
  let remindersSent = 0;
  
  for (const userId in userData) {
    const user = userData[userId];
    if (!user.timerReminders || user.timerReminders.length === 0) continue;
    
    // 找到需要提醒的項目
    const pendingReminders = user.timerReminders.filter(timer => {
      const remindTime = new Date(timer.remindTime);
      return !timer.notified && remindTime <= now;
    });
    
    if (pendingReminders.length === 0) continue;
    
    // 為每個用戶發送提醒
    for (const timer of pendingReminders) {
      try {
        const message = `⏰ 定時提醒到了！

🎯 提醒事項：${timer.content}
🕐 原設定：${timer.timeText}後提醒
📅 提醒時間：${now.toLocaleString('zh-TW', { timeZone: 'Asia/Taipei' })}

✅ 完成後可輸入「定時清單」查看其他提醒`;

        await client.pushMessage(userId, {
          type: 'text',
          text: message
        });
        
        // 標記為已通知
        timer.notified = true;
        console.log(`✅ 已發送定時提醒給用戶 ${userId}: ${timer.content}`);
        remindersSent++;
        
      } catch (error) {
        console.error(`❌ 發送定時提醒失敗 ${userId}:`, error);
      }
    }
  }
  
  // 如果有發送提醒，儲存狀態
  if (remindersSent > 0) {
    try {
      await saveData();
      console.log(`✅ 共發送了 ${remindersSent} 個定時提醒`);
    } catch (error) {
      console.error('儲存定時提醒狀態失敗:', error);
    }
  }
  
  return remindersSent;
}

// 修改現有的定時任務，在每分鐘檢查中添加定時提醒檢查
// 找到現有的 cron.schedule('* * * * *', ...) 並修改：

cron.schedule('* * * * *', async () => {
  try {
    const currentTime = getTaiwanTimeHHMM();
    const currentDate = getTaiwanTime();
    
    // 每5分鐘顯示一次詳細狀態
    const minute = new Date().getMinutes();
    const showDetailedLog = minute % 5 === 0;
    
    if (showDetailedLog) {
      console.log(`📅 定時檢查 - ${currentDate} (${currentTime})`);
      console.log(`📊 系統狀態 - 資料載入:${isDataLoaded}, 用戶數:${Object.keys(userData).length}`);
    }
    
    if (!isDataLoaded) {
      if (showDetailedLog) {
        console.log('⚠️ 資料尚未載入，跳過提醒檢查');
      }
      return;
    }
    
    if (Object.keys(userData).length === 0) {
      if (showDetailedLog) {
        console.log('📝 沒有用戶資料，跳過提醒檢查');
      }
      return;
    }
    
    // 檢查定時提醒（新增）
    const timerRemindersSent = await checkAndSendTimerReminders();
    if (timerRemindersSent > 0) {
      console.log(`⏰ 定時提醒 - 發送數量: ${timerRemindersSent}`);
    }
    
    // 檢查是否有用戶需要在這個時間提醒（原有的日常提醒）
    let needsReminder = false;
    for (const userId in userData) {
      const user = userData[userId];
      if (user.morningReminderTime === currentTime || user.eveningReminderTime === currentTime) {
        needsReminder = true;
        break;
      }
    }
    
    if (needsReminder || showDetailedLog) {
      console.log(`🔔 檢查提醒 - 時間:${currentTime}, 需要提醒:${needsReminder}`);
    }
    
    await sendReminders('morning');
    await sendReminders('evening');
    
  } catch (error) {
    console.error('❌ 定時任務執行錯誤:', error);
  }
});

// 新增：每小時自動清理過期定時提醒
cron.schedule('0 * * * *', async () => {
  try {
    console.log('🧹 執行定時提醒清理...');
    const cleaned = await cleanupExpiredTimers();
    if (cleaned > 0) {
      console.log(`✅ 清理了 ${cleaned} 個過期定時提醒`);
    }
  } catch (error) {
    console.error('❌ 清理定時提醒失敗:', error);
  }
});
// ========== 第5段：更新狀態檢查和測試功能 ==========

// 修改 getSystemStatus 函數，添加定時提醒統計
function getSystemStatus(userId) {
  const user = userData[userId];
  const todos = user.todos;
  const monthlyTodos = user.monthlyTodos || [];
  const timerReminders = user.timerReminders || []; // 新增
  
  const activeTodos = todos.filter(todo => !isTodoExpired(todo) || !todo.hasDate);
  const expiredTodos = todos.filter(todo => isTodoExpired(todo));
  const remindableTodos = todos.filter(shouldRemindTodo);
  
  // 新增：定時提醒統計
  const now = new Date();
  const activeTimers = timerReminders.filter(timer => {
    const remindTime = new Date(timer.remindTime);
    return remindTime > now && !timer.notified;
  });
  const expiredTimers = timerReminders.filter(timer => {
    const remindTime = new Date(timer.remindTime);
    return remindTime <= now && !timer.notified;
  });
  const notifiedTimers = timerReminders.filter(timer => timer.notified);
  
  return `🔧 系統狀態：
📊 資料統計：
• 總代辦事項：${todos.length} 項
• 每月固定事項：${monthlyTodos.length} 項
• 定時提醒：${timerReminders.length} 項 (新功能！)
• 活躍事項：${activeTodos.length} 項
• 過期事項：${expiredTodos.length} 項
• 今日可提醒：${remindableTodos.length} 項

⏰ 定時提醒詳情：
• 等待中：${activeTimers.length} 項
• 待提醒：${expiredTimers.length} 項  
• 已完成：${notifiedTimers.length} 項

⏰ 提醒設定：
• 早上：${user.morningReminderTime}
• 晚上：${user.eveningReminderTime}

🕐 目前時間：${getTaiwanTimeHHMM()} (台灣)
💾 資料載入：${isDataLoaded ? '✅' : '❌'}

📋 可提醒事項詳情：
${remindableTodos.map((todo, i) => `${i+1}. ${todo.content} ${todo.hasDate ? '(有日期)' : '(每日)'}`).join('\n') || '無'}

⏰ 等待中的定時提醒：
${activeTimers.map((timer, i) => {
  const remainingTime = formatRemainingTime(new Date(timer.remindTime));
  return `${i+1}. ${timer.content} (剩餘${remainingTime})`;
}).join('\n') || '無'}

🔄 每月固定事項：
${monthlyTodos.map((todo, i) => `${i+1}. ${todo.content} ${todo.hasFixedDate ? `(每月${todo.day}號)` : '(手動)'}`).join('\n') || '無'}

如有問題請聯繫管理員`;
}

// 修改健康檢查端點，添加定時提醒統計
app.get('/health', (req, res) => {
  const totalTimerReminders = Object.values(userData).reduce((sum, user) => 
    sum + (user.timerReminders?.length || 0), 0);
  const activeTimerReminders = Object.values(userData).reduce((sum, user) => {
    if (!user.timerReminders) return sum;
    const now = new Date();
    return sum + user.timerReminders.filter(timer => {
      const remindTime = new Date(timer.remindTime);
      return remindTime > now && !timer.notified;
    }).length;
  }, 0);
  
  res.json({ 
    status: 'ok', 
    timestamp: new Date().toISOString(),
    users: Object.keys(userData).length,
    totalTodos: Object.values(userData).reduce((sum, user) => sum + (user.todos?.length || 0), 0),
    totalMonthlyTodos: Object.values(userData).reduce((sum, user) => sum + (user.monthlyTodos?.length || 0), 0),
    totalTimerReminders: totalTimerReminders, // 新增
    activeTimerReminders: activeTimerReminders // 新增
  });
});

// 新增：測試定時提醒功能
async function testTimerReminder(userId) {
  console.log(`🧪 用戶 ${userId} 測試定時提醒功能`);
  
  // 創建一個1分鐘後的測試提醒
  const testRemindTime = new Date();
  testRemindTime.setMinutes(testRemindTime.getMinutes() + 1);
  
  try {
    const result = await addTimerReminder(userId, '測試提醒功能', 1, testRemindTime, '1分鐘');
    return `🧪 ${result}\n\n⚠️ 這是測試提醒，將在1分鐘後收到通知！`;
  } catch (error) {
    console.error('測試定時提醒失敗:', error);
    return '❌ 測試定時提醒功能失敗，請稍後再試';
  }
}

// 在指令處理中添加測試指令
// 找到現有的測試相關指令，添加：
else if (userMessage === '測試定時') {
  replyMessage = await testTimerReminder(userId);
}

// 新增：手動觸發定時提醒檢查的端點（用於測試和調試）
app.get('/force-timer-check', async (req, res) => {
  try {
    console.log('🔧 手動觸發定時提醒檢查...');
    const remindersSent = await checkAndSendTimerReminders();
    const cleaned = await cleanupExpiredTimers();
    
    res.json({
      success: true,
      message: '定時提醒檢查已執行',
      remindersSent: remindersSent,
      cleaned: cleaned,
      currentTime: getTaiwanTimeHHMM(),
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    res.json({
      success: false,
      error: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// 新增：獲取所有用戶定時提醒統計的端點
app.get('/timer-stats', (req, res) => {
  try {
    const now = new Date();
    let totalTimers = 0;
    let activeTimers = 0;
    let pendingTimers = 0;
    let notifiedTimers = 0;
    
    const userStats = {};
    
    for (const userId in userData) {
      const user = userData[userId];
      if (!user.timerReminders) continue;
      
      const userActive = user.timerReminders.filter(timer => {
        const remindTime = new Date(timer.remindTime);
        return remindTime > now && !timer.notified;
      }).length;
      
      const userPending = user.timerReminders.filter(timer => {
        const remindTime = new Date(timer.remindTime);
        return remindTime <= now && !timer.notified;
      }).length;
      
      const userNotified = user.timerReminders.filter(timer => timer.notified).length;
      
      userStats[userId] = {
        total: user.timerReminders.length,
        active: userActive,
        pending: userPending,
        notified: userNotified
      };
      
      totalTimers += user.timerReminders.length;
      activeTimers += userActive;
      pendingTimers += userPending;
      notifiedTimers += userNotified;
    }
    
    res.json({
      success: true,
      summary: {
        totalTimers,
        activeTimers,
        pendingTimers,
        notifiedTimers
      },
      userStats,
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    res.json({
      success: false,
      error: error.message,
      timestamp: new Date().toISOString()
    });
  }
});
