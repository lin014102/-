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

// 載入資料 - 添加重試機制
async function loadData() {
  let retryCount = 0;
  const maxRetries = 3;
  
  while (retryCount < maxRetries) {
    try {
      const data = await fs.readFile(DATA_FILE, 'utf8');
      userData = JSON.parse(data);
      console.log(`資料載入成功，共有 ${Object.keys(userData).length} 個用戶`);
      return;
    } catch (error) {
      retryCount++;
      if (error.code === 'ENOENT') {
        console.log('資料檔案不存在，初始化空的資料檔案');
        userData = {};
        await saveData();
        return;
      } else if (retryCount < maxRetries) {
        console.log(`載入資料失敗，第 ${retryCount} 次重試...`);
        await new Promise(resolve => setTimeout(resolve, 1000));
      } else {
        console.error('載入資料失敗，使用空資料:', error);
        userData = {};
      }
    }
  }
}

// 儲存資料 - 添加重試機制和鎖定
let isSaving = false;
async function saveData() {
  if (isSaving) {
    console.log('正在儲存中，跳過此次儲存');
    return;
  }
  
  isSaving = true;
  try {
    const dataToSave = JSON.stringify(userData, null, 2);
    await fs.writeFile(DATA_FILE, dataToSave, 'utf8');
    console.log('資料儲存成功');
  } catch (error) {
    console.error('儲存資料失敗:', error);
    // 重試一次
    try {
      await new Promise(resolve => setTimeout(resolve, 500));
      const dataToSave = JSON.stringify(userData, null, 2);
      await fs.writeFile(DATA_FILE, dataToSave, 'utf8');
      console.log('重試儲存成功');
    } catch (retryError) {
      console.error('重試儲存也失敗:', retryError);
    }
  } finally {
    isSaving = false;
  }
}

// 初始化用戶資料 - 確保資料同步
function initUser(userId) {
  if (!userData[userId]) {
    userData[userId] = {
      todos: [],
      morningReminderTime: '09:00', // 早上提醒時間
      eveningReminderTime: '18:00', // 晚上提醒時間
      timezone: 'Asia/Taipei'
    };
    // 立即儲存新用戶資料
    saveData().catch(err => console.error('初始化用戶資料儲存失敗:', err));
    console.log(`初始化新用戶: ${userId}`);
  }
}

// 處理 LINE webhook
app.post('/webhook', line.middleware(config), (req, res) => {
  Promise
    .all(req.body.events.map(handleEvent))
    .then((result) => res.json(result))
    .catch((err) => {
      console.error(err);
      res.status(500).end();
    });
});

// 處理訊息事件 - 加強錯誤處理和日誌
async function handleEvent(event) {
  if (event.type !== 'message' || event.message.type !== 'text') {
    return Promise.resolve(null);
  }

  const userId = event.source.userId;
  const userMessage = event.message.text.trim();
  
  console.log(`收到用戶 ${userId} 的訊息: "${userMessage}"`);
  
  // 確保用戶初始化
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
      replyMessage = addTodo(userId, todo);
    } else if (userMessage.startsWith('刪除 ')) {
      const index = parseInt(userMessage.substring(3).trim()) - 1;
      replyMessage = deleteTodo(userId, index);
    } else if (userMessage.startsWith('早上時間 ')) {
      const time = userMessage.substring(5).trim();
      replyMessage = setMorningTime(userId, time);
    } else if (userMessage.startsWith('晚上時間 ')) {
      const time = userMessage.substring(5).trim();
      replyMessage = setEveningTime(userId, time);
    } else if (userMessage === '查詢時間') {
      replyMessage = getReminderTimes(userId);
    } else if (userMessage === '狀態') {
      // 添加狀態檢查指令
      replyMessage = getStatusMessage(userId);
    } else {
      replyMessage = '指令不正確，請輸入「幫助」查看使用說明';
    }

    console.log(`回覆用戶 ${userId}: "${replyMessage.substring(0, 50)}..."`);
    
    return client.replyMessage(event.replyToken, {
      type: 'text',
      text: replyMessage
    });
  } catch (error) {
    console.error('處理訊息時發生錯誤:', error);
    return client.replyMessage(event.replyToken, {
      type: 'text',
      text: '處理您的訊息時發生錯誤，請稍後再試或輸入「幫助」查看使用說明'
    });
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

// 新增代辦事項 - 加強錯誤處理和日誌
function addTodo(userId, todo) {
  if (!todo) {
    return '請輸入要新增的代辦事項\n格式：新增 [事項內容] 或 新增 8/9號[事項內容]';
  }
  
  const parsed = parseDate(todo);
  console.log(`用戶 ${userId} 新增事項:`, { parsed, originalTodo: todo });
  
  const todoItem = {
    id: Date.now(),
    content: parsed.content,
    createdAt: getTaiwanTime(),
    completed: false,
    hasDate: parsed.hasDate,
    targetDate: parsed.date ? parsed.date.toISOString() : null,
    dateString: parsed.dateString
  };
  
  // 確保用戶存在
  if (!userData[userId]) {
    initUser(userId);
  }
  
  userData[userId].todos.push(todoItem);
  console.log(`新增後用戶 ${userId} 的代辦事項數量: ${userData[userId].todos.length}`);
  
  // 立即儲存資料
  saveData().catch(err => console.error('新增代辦事項儲存失敗:', err));
  
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

// 刪除代辦事項 - 加強錯誤處理
function deleteTodo(userId, index) {
  if (!userData[userId]) {
    initUser(userId);
  }
  
  const todos = userData[userId].todos;
  
  if (index < 0 || index >= todos.length) {
    return `❌ 編號不正確，請輸入 1 到 ${todos.length} 之間的數字`;
  }
  
  const deletedTodo = todos.splice(index, 1)[0];
  console.log(`用戶 ${userId} 刪除事項: ${deletedTodo.content}`);
  
  // 立即儲存資料
  saveData().catch(err => console.error('刪除代辦事項儲存失敗:', err));
  
  return `🗑️ 已刪除代辦事項：「${deletedTodo.content}」\n剩餘 ${todos.length} 項代辦事項`;
}

// 狀態檢查功能
function getStatusMessage(userId) {
  if (!userData[userId]) {
    initUser(userId);
  }
  
  const user = userData[userId];
  const currentTime = getTaiwanTimeHHMM();
  
  return `📊 系統狀態：
👤 用戶ID: ${userId.substring(0, 8)}...
📋 代辦事項數量: ${user.todos.length}
🌅 早上提醒時間: ${user.morningReminderTime}
🌙 晚上提醒時間: ${user.eveningReminderTime}
🕐 目前台灣時間: ${currentTime}
💾 資料載入狀態: 正常

如果發現資料不同步，請聯繫管理員`;
}

// 獲取代辦事項清單 - 加強錯誤處理
function getTodoList(userId) {
  // 確保用戶資料存在
  if (!userData[userId]) {
    console.log(`用戶 ${userId} 不存在，初始化中...`);
    initUser(userId);
  }
  
  const todos = userData[userId].todos;
  console.log(`查詢用戶 ${userId} 的代辦事項，共 ${todos.length} 項`);
  
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
      message += `${index}. ${todo.content}\n   📅 ${targetDate} (前一天提醒)\n\n`;
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
function setMorningTime(userId, time) {
  const timeRegex = /^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$/;
  
  if (!timeRegex.test(time)) {
    return '❌ 時間格式不正確\n請使用 HH:MM 格式，例如：08:30';
  }
  
  if (!userData[userId]) {
    initUser(userId);
  }
  
  userData[userId].morningReminderTime = time;
  saveData().catch(err => console.error('設定早上時間儲存失敗:', err));
  
  return `🌅 已設定早上提醒時間為：${time}`;
}

// 設定晚上提醒時間
function setEveningTime(userId, time) {
  const timeRegex = /^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$/;
  
  if (!timeRegex.test(time)) {
    return '❌ 時間格式不正確\n請使用 HH:MM 格式，例如：19:00';
  }
  
  if (!userData[userId]) {
    initUser(userId);
  }
  
  userData[userId].eveningReminderTime = time;
  saveData().catch(err => console.error('設定晚上時間儲存失敗:', err));
  
  return `🌙 已設定晚上提醒時間為：${time}`;
}

// 獲取提醒時間
function getReminderTimes(userId) {
  if (!userData[userId]) {
    initUser(userId);
  }
  
  const morningTime = userData[userId].morningReminderTime;
  const eveningTime = userData[userId].eveningReminderTime;
  const currentTaiwanTime = getTaiwanTimeHHMM();
  
  return `⏰ 目前提醒時間設定：
🌅 早上：${morningTime}
🌙 晚上：${eveningTime}
🕐 台灣目前時間：${currentTaiwanTime}

輸入「早上時間 [HH:MM]」或「晚上時間 [HH:MM]」可修改提醒時間`;
}

// 檢查是否需要提醒
function shouldRemindTodo(todo) {
  const today = getTaiwanDate();
  
  if (!todo.hasDate) {
    // 沒有日期的事項，每天提醒
    return true;
  }
  
  // 有日期的事項，只在前一天提醒
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

// 發送提醒訊息給單一用戶
async function sendReminderToUser(userId, timeType) {
  try {
    const user = userData[userId];
    const todos = user.todos.filter(shouldRemindTodo);
    
    if (todos.length === 0) return;
    
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
    
    console.log(`已發送${timeText}提醒給用戶: ${userId}`);
  } catch (error) {
    console.error(`發送提醒失敗 ${userId}:`, error);
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
    users: Object.keys(userData).length 
  });
});

// 匯出模組 (用於測試)
module.exports = { app, userData };






