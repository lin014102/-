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

// 新增：定時提醒追蹤器
const scheduledReminders = new Map();

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

// 新增：解析時間提醒格式
function parseTimeReminder(text) {
  const currentTime = getTaiwanDate();
  
  // 匹配相對時間格式：N分鐘後/N小時後 + 內容
  const relativePatterns = [
    /(\d+)分鐘?後\s*(.+)/,
    /(\d+)小時後\s*(.+)/,
    /(.+?)\s*(\d+)分鐘?後/,
    /(.+?)\s*(\d+)小時後/
  ];
  
  for (const pattern of relativePatterns) {
    const match = text.match(pattern);
    if (match) {
      let value, content, unit;
      
      if (match[1] && isNaN(match[1])) {
        // 內容在前，時間在後
        content = match[1].trim();
        value = parseInt(match[2]);
        unit = text.includes('小時') ? 'hour' : 'minute';
      } else {
        // 時間在前，內容在後
        value = parseInt(match[1]);
        content = match[2] ? match[2].trim() : match[1].trim();
        unit = text.includes('小時') ? 'hour' : 'minute';
      }
      
      if (value && content && value > 0 && value <= 1440) { // 最多24小時
        const reminderTime = new Date(currentTime);
        if (unit === 'hour') {
          reminderTime.setHours(reminderTime.getHours() + value);
        } else {
          reminderTime.setMinutes(reminderTime.getMinutes() + value);
        }
        
        return {
          hasTimeReminder: true,
          reminderTime: reminderTime,
          content: content,
          relativeText: `${value}${unit === 'hour' ? '小時' : '分鐘'}後`,
          isRelative: true
        };
      }
    }
  }
  
  // 匹配絕對時間格式：HH:MM + 內容
  const absolutePatterns = [
    /(\d{1,2}):(\d{2})\s*(.+)/,
    /(.+?)\s*(\d{1,2}):(\d{2})/
  ];
  
  for (const pattern of absolutePatterns) {
    const match = text.match(pattern);
    if (match) {
      let hour, minute, content;
      
      if (match[3]) {
        // 時間在前：14:30倒垃圾
        hour = parseInt(match[1]);
        minute = parseInt(match[2]);
        content = match[3].trim();
      } else {
        // 時間在後：倒垃圾14:30
        hour = parseInt(match[2]);
        minute = parseInt(match[3]);
        content = match[1].trim();
      }
      
      if (hour >= 0 && hour <= 23 && minute >= 0 && minute <= 59 && content) {
        const reminderTime = new Date(currentTime);
        reminderTime.setHours(hour, minute, 0, 0);
        
        // 如果時間已過，設為明天
        if (reminderTime <= currentTime) {
          reminderTime.setDate(reminderTime.getDate() + 1);
        }
        
        return {
          hasTimeReminder: true,
          reminderTime: reminderTime,
          content: content,
          timeText: `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`,
          isRelative: false
        };
      }
    }
  }
  
  return {
    hasTimeReminder: false,
    reminderTime: null,
    content: text,
    timeText: null,
    isRelative: false
  };
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

// 新增：解析每月事項的日期格式
function parseMonthlyDate(text) {
  const monthlyPattern = /(?:每月)?(\d{1,2})號(.+)|(.+?)(?:每月)?(\d{1,2})號/;
  const match = text.match(monthlyPattern);
  
  if (match) {
    let day, content;
    
    if (match[1] && match[2]) {
      day = parseInt(match[1]);
      content = match[2].trim();
    } else if (match[4] && match[3]) {
      day = parseInt(match[4]);
      content = match[3].trim();
    }
    
    if (day && content && day >= 1 && day <= 31) {
      return {
        hasDate: true,
        day: day,
        content: content
      };
    }
  }
  
  return {
    hasDate: false,
    day: null,
    content: text
  };
}

async function loadData() {
  try {
    const data = await fs.readFile(DATA_FILE, 'utf8');
    userData = JSON.parse(data);
    isDataLoaded = true;
    console.log('資料載入成功，用戶數:', Object.keys(userData).length);
    
    // 重新設定時間提醒
    await restoreScheduledReminders();
  } catch (error) {
    console.log('初始化空的資料檔案');
    userData = {};
    isDataLoaded = true;
    // 創建空檔案
    await saveData();
  }
}

// 新增：恢復排程提醒
async function restoreScheduledReminders() {
  const currentTime = getTaiwanDate();
  
  for (const userId in userData) {
    const user = userData[userId];
    if (!user.todos) continue;
    
    user.todos.forEach(todo => {
      if (todo.hasTimeReminder && todo.reminderTime) {
        const reminderTime = new Date(todo.reminderTime);
        if (reminderTime > currentTime) {
          scheduleTimeReminder(userId, todo);
        }
      }
    });
  }
  
  console.log(`恢復了 ${scheduledReminders.size} 個定時提醒`);
}

// 新增：設定定時提醒
function scheduleTimeReminder(userId, todo) {
  const reminderKey = `${userId}-${todo.id}`;
  
  // 如果已存在相同的提醒，先清除
  if (scheduledReminders.has(reminderKey)) {
    clearTimeout(scheduledReminders.get(reminderKey));
  }
  
  const reminderTime = new Date(todo.reminderTime);
  const currentTime = getTaiwanDate();
  const delay = reminderTime.getTime() - currentTime.getTime();
  
  if (delay <= 0) {
    console.log(`提醒時間已過：${todo.content}`);
    return;
  }
  
  const timeoutId = setTimeout(async () => {
    try {
      await sendTimeReminder(userId, todo);
      scheduledReminders.delete(reminderKey);
      console.log(`✅ 定時提醒已發送並清理：${todo.content}`);
    } catch (error) {
      console.error(`❌ 發送定時提醒失敗：`, error);
    }
  }, delay);
  
  scheduledReminders.set(reminderKey, timeoutId);
  
  const reminderTimeStr = reminderTime.toLocaleString('zh-TW', { timeZone: 'Asia/Taipei' });
  console.log(`⏰ 設定定時提醒：${todo.content} 於 ${reminderTimeStr} (延遲${Math.round(delay/1000/60)}分鐘)`);
}

// 新增：發送定時提醒
async function sendTimeReminder(userId, todo) {
  try {
    const message = `⏰ 時間提醒！\n\n📝 ${todo.content}\n\n⏱️ 提醒時間：${new Date(todo.reminderTime).toLocaleString('zh-TW', { timeZone: 'Asia/Taipei' })}\n\n💡 此提醒會自動從清單中移除`;
    
    await client.pushMessage(userId, {
      type: 'text',
      text: message
    });
    
    // 從用戶代辦清單中移除已提醒的項目
    const user = userData[userId];
    if (user && user.todos) {
      user.todos = user.todos.filter(t => t.id !== todo.id);
      await saveData();
      console.log(`定時提醒完成並移除項目：${todo.content}`);
    }
  } catch (error) {
    console.error('發送定時提醒失敗:', error);
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

// 修改：初始化用戶資料（新增 monthlyTodos）
function initUser(userId) {
  if (!userData[userId]) {
    userData[userId] = {
      todos: [],
      monthlyTodos: [], // 新增：每月固定事項
      morningReminderTime: '09:00', // 早上提醒時間
      eveningReminderTime: '18:00', // 晚上提醒時間
      timezone: 'Asia/Taipei'
    };
    console.log(`初始化用戶: ${userId}`);
    saveData(); // 確保立即儲存新用戶資料
  }
  
  // 為舊用戶添加 monthlyTodos 欄位
  if (!userData[userId].monthlyTodos) {
    userData[userId].monthlyTodos = [];
    saveData();
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

// 修改：處理訊息事件（新增時間提醒指令）
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
    } else if (userMessage === '測試提醒') {
      replyMessage = await testReminder(userId);
    } else if (userMessage.startsWith('測試時間 ')) {
      const time = userMessage.substring(5).trim();
      replyMessage = await testTimeReminder(userId, time);
    }
    // 新增：每月固定事項指令
    else if (userMessage.startsWith('每月新增 ')) {
      const todo = userMessage.substring(5).trim();
      replyMessage = await addMonthlyTodo(userId, todo);
    } else if (userMessage.startsWith('每月刪除 ')) {
      const index = parseInt(userMessage.substring(5).trim()) - 1;
      replyMessage = await deleteMonthlyTodo(userId, index);
    } else if (userMessage === '每月清單') {
      replyMessage = getMonthlyTodoList(userId);
    } else if (userMessage === '生成本月') {
      replyMessage = await generateMonthlyTodos(userId);
    } 
    // 新增：定時提醒管理指令
    else if (userMessage === '定時清單') {
      replyMessage = getTimeReminderList(userId);
    } else if (userMessage.startsWith('取消定時 ')) {
      const index = parseInt(userMessage.substring(5).trim()) - 1;
      replyMessage = await cancelTimeReminder(userId, index);
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

// 修改：獲取幫助訊息（新增時間提醒說明）
function getHelpMessage() {
  return `📋 代辦事項機器人使用說明：

📝 基本功能：
• 新增 [事項] - 新增代辦事項
• 新增 8/9號繳卡費 - 新增有日期的事項
• 刪除 [編號] - 刪除指定代辦事項
• 查詢 或 清單 - 查看所有代辦事項

⏰ 定時提醒功能：
• 新增 5分鐘後倒垃圾 - 相對時間提醒
• 新增 30分鐘後開會 - 30分鐘後提醒
• 新增 2小時後休息 - 2小時後提醒
• 新增 14:30倒垃圾 - 絕對時間提醒
• 新增 吃藥18:00 - 今天18:00提醒
• 定時清單 - 查看所有定時提醒
• 取消定時 [編號] - 取消指定定時提醒

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

🔔 智能提醒規則：
• 定時提醒：到時間自動提醒並移除
• 有日期的事項：只在前一天提醒
• 沒日期的事項：每天提醒
• 每月固定事項：需手動生成到代辦清單

🧪 測試功能：
• 狀態 - 查看系統狀態
• 測試提醒 - 立即測試提醒功能
• 測試時間 [HH:MM] - 測試特定時間提醒

💡 使用範例：
• 新增 10分鐘後打電話給媽媽
• 新增 1小時後關電腦
• 新增 明天開會14:00
• 新增 吃藥19:30
• 每月新增 5號繳信用卡費
• 生成本月

輸入「幫助」可重複查看此說明`;
}

// 修改：新增代辦事項（支援時間提醒）
async function addTodo(userId, todo) {
  if (!todo) {
    return '請輸入要新增的代辦事項\n格式：新增 [事項內容]\n或：新增 5分鐘後[事項內容]\n或：新增 14:30[事項內容]';
  }
  
  // 先嘗試解析時間提醒
  const timeParsed = parseTimeReminder(todo);
  
  if (timeParsed.hasTimeReminder) {
    // 處理時間提醒
    const todoItem = {
      id: Date.now(),
      content: timeParsed.content,
      createdAt: getTaiwanTime(),
      completed: false,
      hasTimeReminder: true,
      reminderTime: timeParsed.reminderTime.toISOString(),
      isRelative: timeParsed.isRelative,
      timeText: timeParsed.relativeText || timeParsed.timeText
    };
    
    userData[userId].todos.push(todoItem);
    
    try {
      await saveData();
      // 設定定時提醒
      scheduleTimeReminder(userId, todoItem);
      console.log(`用戶 ${userId} 新增定時事項: ${timeParsed.content}, 提醒時間: ${timeParsed.reminderTime}`);
    } catch (err) {
      console.error('新增定時事項時儲存失敗:', err);
      return '❌ 新增失敗，請稍後再試';
    }
    
    const reminderTimeStr = timeParsed.reminderTime.toLocaleString('zh-TW', { timeZone: 'Asia/Taipei' });
    let message = `⏰ 已設定定時提醒：「${timeParsed.content}」\n`;
    message += `🕐 提醒時間：${reminderTimeStr}\n`;
    message += `📱 到時間會自動提醒並從清單移除`;
    message += `\n目前共有 ${userData[userId].todos.length} 項代辦事項`;
    
    return message;
  }
  
  // 沒有時間提醒，按原邏輯處理日期
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

// 新增：獲取定時提醒清單
function getTimeReminderList(userId) {
  const todos = userData[userId].todos;
  const timeReminders = todos.filter(todo => todo.hasTimeReminder);
  
  if (timeReminders.length === 0) {
    return '⏰ 目前沒有定時提醒\n\n💡 輸入「新增 10分鐘後倒垃圾」來設定定時提醒\n或輸入「新增 14:30開會」來設定今日特定時間提醒';
  }
  
  let message = `⏰ 定時提醒清單 (${timeReminders.length} 項)：\n\n`;
  
  timeReminders.forEach((todo, index) => {
    const reminderTime = new Date(todo.reminderTime);
    const now = getTaiwanDate();
    const diff = reminderTime.getTime() - now.getTime();
    
    let statusText = '';
    if (diff <= 0) {
      statusText = ' ⚠️ (已過期)';
    } else {
      const minutes = Math.ceil(diff / 60000);
      if (minutes < 60) {
        statusText = ` (${minutes}分鐘後)`;
      } else {
        const hours = Math.floor(minutes / 60);
        const mins = minutes % 60;
        statusText = ` (${hours}小時${mins > 0 ? mins + '分鐘' : ''}後)`;
      }
    }
    
    const timeStr = reminderTime.toLocaleString('zh-TW', { 
      timeZone: 'Asia/Taipei',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
    
    message += `
