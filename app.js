const express = require('express');
const line = require('@line/bot-sdk');
const cron = require('node-cron');
const fs = require('fs').promises;
const path = require('path');

const app = express();
const PORT = process.env.PORT || 3000;

// LINE Bot 設定
const config = {
  channelAccessToken: process.env.CHANNEL_ACCESS_TOKEN || 'LShi8pcxKnQoE7akuvZPZGuXOVr6gPf0Wn/46cxYouM3hgsqY5+69vZW5lowsMEDh0E0FAqDoOPx2KtXn5EJ0xPgKJ3CVvo0O6Hh/el6zGRleP9SkY1J6aWFOjXIhj2l1H+almOBGt1pVfHGcIcitwdB04t89/1O/w1cDnyilFU=',
  channelSecret: process.env.CHANNEL_SECRET || '2157683f2cea90bd12c1702f18886238'
};

const client = new line.Client(config);

// 資料儲存檔案路徑
const DATA_FILE = path.join(__dirname, 'todos.json');

// 初始化資料結構
let userData = {};
let isDataLoaded = false;

// 請求去重機制
const processedMessages = new Set();

// 定期清理處理過的訊息ID（避免記憶體洩漏）
setInterval(() => {
  processedMessages.clear();
  console.log('已清理處理過的訊息記錄');
}, 3600000); // 1小時清理一次

// 獲取台灣時間
function getTaiwanTime() {
  return new Date().toLocaleString("zh-TW", {
    timeZone: "Asia/Taipei",
    hour12: false
  });
}

// 獲取台灣時間 HH:MM 格式
function getTaiwanTimeHHMM() {
  const now = new Date();
  const taiwanTime = new Date(now.toLocaleString("en-US", {timeZone: "Asia/Taipei"}));
  return `${String(taiwanTime.getHours()).padStart(2, '0')}:${String(taiwanTime.getMinutes()).padStart(2, '0')}`;
}

// 獲取台灣當前日期
function getTaiwanDate() {
  const now = new Date();
  const taiwanTime = new Date(now.toLocaleString("en-US", {timeZone: "Asia/Taipei"}));
  return taiwanTime;
}

// 解析日期格式 (支援 M/D 或 MM/DD 格式)
function parseDate(text) {
  const currentYear = getTaiwanDate().getFullYear();
  
  // 匹配 8/9號繳卡費 或 08/09號繳卡費 等格式
  const datePattern = /(\d{1,2})\/(\d{1,2})號?(.+)|(.+?)(\d{1,2})\/(\d{1,2})號?/;
  const match = text.match(datePattern);
  
  if (match) {
    let month, day, content;
    
    if (match[1] && match[2]) {
      // 日期在前面：8/9號繳卡費
      month = parseInt(match[1]);
      day = parseInt(match[2]);
      content = match[3].trim();
    } else if (match[5] && match[6]) {
      // 日期在後面：繳卡費8/9號
      month = parseInt(match[5]);
      day = parseInt(match[6]);
      content = match[4].trim();
    }
    
    if (month && day && content) {
      // 驗證日期合法性
      if (month >= 1 && month <= 12 && day >= 1 && day <= 31) {
        const targetDate = new Date(currentYear, month - 1, day);
        const today = getTaiwanDate();
        
        // 如果日期已過，設為明年
        if (targetDate < today) {
          targetDate.setFullYear(currentYear + 1);
        }
        
        return {
          hasDate: true,
          date: targetDate,
          content: content,
          dateString: `${month}/${day}`
        };
      }
    }
  }
  
  // 沒有找到日期格式，返回原內容
  return {
    hasDate: false,
    date: null,
    content: text,
    dateString: null
  };
}

async function loadData() {
  try {
    const data = await fs.readFile(DATA_FILE, 'utf8');
    userData = JSON.parse(data);
    isDataLoaded = true;
    console.log('資料載入成功，用戶數:', Object.keys(userData).length);
  } catch (error) {
    console.log('初始化空的資料檔案');
    userData = {};
    isDataLoaded = true;
    // 創建空檔案
    await saveData();
  }
}

// 儲存資料（使用檔案鎖定機制）
let isSaving = false;
async function saveData() {
  if (isSaving) {
    console.log('正在儲存中，跳過重複儲存');
    return;
  }
  
  isSaving = true;
  try {
    const tempFile = DATA_FILE + '.tmp';
    await fs.writeFile(tempFile, JSON.stringify(userData, null, 2));
    await fs.rename(tempFile, DATA_FILE); // 原子性操作
    console.log('資料已儲存，目前用戶數:', Object.keys(userData).length);
  } catch (error) {
    console.error('儲存資料失敗:', error);
    throw error;
  } finally {
    isSaving = false;
  }
}

// 初始化用戶資料
function initUser(userId) {
  if (!userData[userId]) {
    userData[userId] = {
      todos: [],
      morningReminderTime: '09:00', // 早上提醒時間
      eveningReminderTime: '18:00', // 晚上提醒時間
      timezone: 'Asia/Taipei'
    };
    console.log(`初始化用戶: ${userId}`);
    saveData(); // 確保立即儲存新用戶資料
  }
}

// 處理 LINE webhook
app.post('/webhook', line.middleware(config), async (req, res) => {
  try {
    console.log('收到 webhook 請求:', req.body);
    
    const results = await Promise.all(req.body.events.map(handleEvent));
    
    // 立即回應 LINE 平台
    res.status(200).json({ success: true });
    
    console.log('Webhook 處理完成');
  } catch (err) {
    console.error('Webhook 處理錯誤:', err);
    res.status(200).json({ success: false, error: err.message });
  }
});

// 處理訊息事件
async function handleEvent(event) {
  if (event.type !== 'message' || event.message.type !== 'text') {
    return Promise.resolve(null);
  }

  const userId = event.source.userId;
  const userMessage = event.message.text.trim();
  const messageId = event.message.id;
  
  // 請求去重：檢查是否已處理過這個訊息
  if (processedMessages.has(messageId)) {
    console.log(`重複訊息被忽略: ${messageId} from ${userId}`);
    return null;
  }
  
  // 標記訊息已處理
  processedMessages.add(messageId);
  
  console.log(`用戶 ${userId} 發送訊息: ${userMessage} (ID: ${messageId})`);
  
  // 確保資料已載入
  if (!isDataLoaded) {
    console.log('資料尚未載入完成，等待...');
    try {
      await loadData();
    } catch (error) {
      console.error('載入資料失敗:', error);
      return client.replyMessage(event.replyToken, {
        type: 'text',
        text: '⚠️ 系統初始化中，請稍後再試'
      });
    }
  }
  
  initUser(userId);
  
  let replyMessage = '';

  try {
    // 解析用戶指令
    if (userMessage === '幫助' || userMessage === 'help') {
      replyMessage = getHelpMessage();
    } else if (userMessage === '查詢' || userMessage === '清單') {
      replyMessage = getTodoList(userId);
    } else if (userMessage.startsWith('新增 ')) {
      const todo = userMessage.substring(3).trim();
      replyMessage = await addTodo(userId, todo);
    } else if (userMessage.startsWith('刪除 ')) {
      const index = parseInt(userMessage.substring(3).trim()) - 1;
      replyMessage = await deleteTodo(userId, index);
    } else if (userMessage.startsWith('早上時間 ')) {
      const time = userMessage.substring(5).trim();
      replyMessage = await setMorningTime(userId, time);
    } else if (userMessage.startsWith('晚上時間 ')) {
      const time = userMessage.substring(5).trim();
      replyMessage = await setEveningTime(userId, time);
    } else if (userMessage === '查詢時間') {
      replyMessage = getReminderTimes(userId);
    } else if (userMessage === '狀態') {
      replyMessage = getSystemStatus(userId);
    } else {
      replyMessage = '指令不正確，請輸入「幫助」查看使用說明';
    }

    // 使用 replyMessage 回覆
    const response = await client.replyMessage(event.replyToken, {
      type: 'text',
      text: replyMessage
    });
    
    console.log(`成功回覆用戶 ${userId}: ${replyMessage.substring(0, 50)}...`);
    return response;
    
  } catch (error) {
    console.error(`處理用戶 ${userId} 訊息時發生錯誤:`, error);
    
    // 錯誤處理：嘗試回覆錯誤訊息
    try {
      await client.replyMessage(event.replyToken, {
        type: 'text',
        text: '抱歉，處理您的請求時發生錯誤，請稍後再試 🙏\n如果問題持續，請輸入「狀態」檢查系統狀態'
      });
    } catch (replyError) {
      console.error('回覆錯誤訊息失敗:', replyError);
    }
    
    return null;
  }
}

// 獲取幫助訊息
function getHelpMessage() {
  return `📋 代辦事項機器人使用說明：

📝 基本功能：
• 新增 [事項] - 新增代辦事項
• 新增 8/9號繳卡費 - 新增有日期的事項
• 刪除 [編號] - 刪除指定代辦事項
• 查詢 或 清單 - 查看所有代辦事項

⏰ 提醒設定：
• 早上時間 [HH:MM] - 設定早上提醒時間
• 晚上時間 [HH:MM] - 設定晚上提醒時間
• 查詢時間 - 查看目前提醒時間

🔔 智能提醒：
• 有日期的事項：只在前一天提醒
• 沒日期的事項：每天提醒
• 每天早晚各提醒一次

💡 範例：
• 新增 8/15號繳電費
• 新增 買午餐
• 早上時間 08:30
• 晚上時間 19:00

輸入「幫助」可重複查看此說明`;
}

// 新增代辦事項
async function addTodo(userId, todo) {
  if (!todo) {
    return '請輸入要新增的代辦事項\n格式：新增 [事項內容] 或 新增 8/9號[事項內容]';
  }
  
  const parsed = parseDate(todo);
  
  const todoItem = {
    id: Date.now(),
    content: parsed.content,
    createdAt: getTaiwanTime(),
    completed: false,
    hasDate: parsed.hasDate,
    targetDate: parsed.date ? parsed.date.toISOString() : null,
    dateString: parsed.dateString
  };
  
  userData[userId].todos.push(todoItem);
  
  // 立即儲存並等待完成
  try {
    await saveData();
    console.log(`用戶 ${userId} 新增事項: ${parsed.content}, 總數: ${userData[userId].todos.length}`);
  } catch (err) {
    console.error('新增事項時儲存失敗:', err);
    return '❌ 新增失敗，請稍後再試';
  }
  
  let message = `✅ 已新增代辦事項：「${parsed.content}」\n`;
  
  if (parsed.hasDate) {
    const targetDate = parsed.date.toLocaleDateString('zh-TW');
    message += `📅 目標日期：${targetDate}\n🔔 將在前一天提醒您`;
  } else {
    message += `🔔 將每天提醒您`;
  }
  
  message += `\n目前共有 ${userData[userId].todos.length} 項代辦事項`;
  
  return message;
}

// 刪除代辦事項
async function deleteTodo(userId, index) {
  const todos = userData[userId].todos;
  
  if (index < 0 || index >= todos.length) {
    return `❌ 編號不正確，請輸入 1 到 ${todos.length} 之間的數字`;
  }
  
  const deletedTodo = todos.splice(index, 1)[0];
  
  try {
    await saveData();
    console.log(`用戶 ${userId} 刪除事項: ${deletedTodo.content}, 剩餘: ${todos.length}`);
  } catch (err) {
    console.error('刪除事項時儲存失敗:', err);
    // 如果儲存失敗，恢復刪除的項目
    todos.splice(index, 0, deletedTodo);
    return '❌ 刪除失敗，請稍後再試';
  }
  
  return `🗑️ 已刪除代辦事項：「${deletedTodo.content}」\n剩餘 ${todos.length} 項代辦事項`;
}

// 獲取代辦事項清單
function getTodoList(userId) {
  const todos = userData[userId].todos;
  
  console.log(`用戶 ${userId} 查詢清單，總數: ${todos.length}`);
  
  if (todos.length === 0) {
    return '📝 目前沒有代辦事項\n輸入「新增 [事項]」來新增代辦事項\n也可以輸入「新增 8/9號繳卡費」來新增有日期的事項';
  }
  
  let message = `📋 您的代辦事項清單 (${todos.length} 項)：\n\n`;
  
  // 分類顯示：有日期的和沒日期的
  const datedTodos = todos.filter(todo => todo.hasDate);
  const regularTodos = todos.filter(todo => !todo.hasDate);
  
  let index = 1;
  
  if (datedTodos.length > 0) {
    message += '📅 有日期的事項：\n';
    datedTodos.forEach((todo) => {
      const targetDate = new Date(todo.targetDate).toLocaleDateString('zh-TW');
      const isExpired = isTodoExpired(todo);
      const statusIcon = isExpired ? '⏰' : '📅';
      const statusText = isExpired ? '(已到期)' : '(前一天提醒)';
      
      message += `${index}. ${todo.content}\n   ${statusIcon} ${targetDate} ${statusText}\n\n`;
      index++;
    });
  }
  
  if (regularTodos.length > 0) {
    message += '🔄 每日提醒事項：\n';
    regularTodos.forEach((todo) => {
      const date = todo.createdAt.includes('/') ? todo.createdAt.split(' ')[0] : new Date(todo.createdAt).toLocaleDateString('zh-TW');
      message += `${index}. ${todo.content}\n   📅 建立於 ${date}\n\n`;
      index++;
    });
  }
  
  message += '💡 輸入「刪除 [編號]」可刪除指定項目';
  return message;
}

// 設定早上提醒時間
async function setMorningTime(userId, time) {
  const timeRegex = /^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$/;
  
  if (!timeRegex.test(time)) {
    return '❌ 時間格式不正確\n請使用 HH:MM 格式，例如：08:30';
  }
  
  userData[userId].morningReminderTime = time;
  
  try {
    await saveData();
    console.log(`用戶 ${userId} 設定早上提醒時間: ${time}`);
  } catch (err) {
    console.error('設定提醒時間時儲存失敗:', err);
    return '❌ 設定失敗，請稍後再試';
  }
  
  return `🌅 已設定早上提醒時間為：${time}`;
}

// 設定晚上提醒時間
async function setEveningTime(userId, time) {
  const timeRegex = /^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$/;
  
  if (!timeRegex.test(time)) {
    return '❌ 時間格式不正確\n請使用 HH:MM 格式，例如：19:00';
  }
  
  userData[userId].eveningReminderTime = time;
  
  try {
    await saveData();
    console.log(`用戶 ${userId} 設定晚上提醒時間: ${time}`);
  } catch (err) {
    console.error('設定提醒時間時儲存失敗:', err);
    return '❌ 設定失敗，請稍後再試';
  }
  
  return `🌙 已設定晚上提醒時間為：${time}`;
}

// 獲取提醒時間
function getReminderTimes(userId) {
  const morningTime = userData[userId].morningReminderTime;
  const eveningTime = userData[userId].eveningReminderTime;
  const currentTaiwanTime = getTaiwanTimeHHMM();
  
  return `⏰ 目前提醒時間設定：
🌅 早上：${morningTime}
🌙 晚上：${eveningTime}
🕐 台灣目前時間：${currentTaiwanTime}

輸入「早上時間 [HH:MM]」或「晚上時間 [HH:MM]」可修改提醒時間`;
}

// 檢查是否需要提醒（修正版本 - 不會刪除代辦事項）
function shouldRemindTodo(todo) {
  const today = getTaiwanDate();
  
  if (!todo.hasDate) {
    // 沒有日期的事項，每天提醒
    return true;
  }
  
  // 有日期的事項，只在前一天提醒，但不刪除
  const targetDate = new Date(todo.targetDate);
  const tomorrow = new Date(today);
  tomorrow.setDate(today.getDate() + 1);
  
  // 檢查明天是否是目標日期
  return (
    tomorrow.getFullYear() === targetDate.getFullYear() &&
    tomorrow.getMonth() === targetDate.getMonth() &&
    tomorrow.getDate() === targetDate.getDate()
  );
}

// 新增：檢查代辦事項是否已過期（用於顯示）
function isTodoExpired(todo) {
  if (!todo.hasDate) {
    return false; // 沒有日期的事項不會過期
  }
  
  const today = getTaiwanDate();
  const targetDate = new Date(todo.targetDate);
  
  // 如果目標日期已過，標記為過期
  return targetDate < today;
}

// 發送提醒訊息給單一用戶
async function sendReminderToUser(userId, timeType) {
  try {
    const user = userData[userId];
    if (!user || !user.todos) {
      console.log(`用戶 ${userId} 資料不存在`);
      return;
    }
    
    const todos = user.todos.filter(shouldRemindTodo);
    
    console.log(`用戶 ${userId} 需要提醒的事項數量: ${todos.length}`);
    
    if (todos.length === 0) {
      console.log(`用戶 ${userId} 沒有需要提醒的事項`);
      return;
    }
    
    const timeIcon = timeType === 'morning' ? '🌅' : '🌙';
    const timeText = timeType === 'morning' ? '早安' : '晚安';
    
    let message = `${timeIcon} ${timeText}！您有 ${todos.length} 項待辦事項：\n\n`;
    
    // 分類顯示
    const datedTodos = todos.filter(todo => todo.hasDate);
    const regularTodos = todos.filter(todo => !todo.hasDate);
    
    if (datedTodos.length > 0) {
      message += '📅 明天要做的事：\n';
      datedTodos.forEach((todo, index) => {
        message += `${index + 1}. ${todo.content}\n`;
      });
      message += '\n';
    }
    
    if (regularTodos.length > 0) {
      message += '🔄 每日待辦：\n';
      regularTodos.forEach((todo, index) => {
        message += `${datedTodos.length + index + 1}. ${todo.content}\n`;
      });
    }
    
    message += '\n📝 祝您順利完成所有任務！';
    
    await client.pushMessage(userId, {
      type: 'text',
      text: message
    });
    
    console.log(`✅ 已發送${timeText}提醒給用戶: ${userId}`);
  } catch (error) {
    console.error(`❌ 發送提醒失敗 ${userId}:`, error);
  }
}

// 發送提醒給所有用戶
async function sendReminders(timeType) {
  const currentTime = getTaiwanTimeHHMM();
  
  console.log(`檢查${timeType === 'morning' ? '早上' : '晚上'}提醒時間 (台灣時間): ${currentTime}`);
  
  for (const userId in userData) {
    const user = userData[userId];
    const targetTime = timeType === 'morning' ? user.morningReminderTime : user.eveningReminderTime;
    
    if (targetTime === currentTime) {
      await sendReminderToUser(userId, timeType);
    }
  }
}

// 設定定時任務 - 每分鐘檢查一次
cron.schedule('* * * * *', () => {
  sendReminders('morning');
  sendReminders('evening');
});

// 啟動伺服器
app.listen(PORT, async () => {
  console.log(`LINE Bot 伺服器運行於 port ${PORT}`);
  await loadData();
  console.log('資料載入完成');
});

// 健康檢查端點
app.get('/health', (req, res) => {
  res.json({ 
    status: 'ok', 
    timestamp: new Date().toISOString(),
    users: Object.keys(userData).length,
    totalTodos: Object.values(userData).reduce((sum, user) => sum + (user.todos?.length || 0), 0)
  });
});

// 新增調試端點
app.get('/debug', (req, res) => {
  res.json({
    userData: userData,
    dataFile: DATA_FILE,
    timestamp: new Date().toISOString(),
    isDataLoaded: isDataLoaded,
    processedMessagesCount: processedMessages.size
  });
});

// 新增清理過期事項的端點（手動觸發）
app.get('/cleanup', async (req, res) => {
  let totalCleaned = 0;
  
  for (const userId in userData) {
    const user = userData[userId];
    const originalLength = user.todos.length;
    
    // 可選：清理超過30天的過期事項
    const thirtyDaysAgo = new Date();
    thirtyDaysAgo.setDate(thirtyDaysAgo.getDate() - 30);
    
    user.todos = user.todos.filter(todo => {
      if (!todo.hasDate) return true; // 保留沒日期的事項
      
      const targetDate = new Date(todo.targetDate);
      return targetDate >= thirtyDaysAgo; // 保留30天內的事項
    });
    
    totalCleaned += (originalLength - user.todos.length);
  }
  
  if (totalCleaned > 0) {
    await saveData();
  }
  
  res.json({
    success: true,
    cleaned: totalCleaned,
    timestamp: new Date().toISOString()
  });
});

// 匯出模組 (用於測試)
module.exports = { app, userData };







