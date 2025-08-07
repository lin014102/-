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

// 載入儲存的資料
async function loadData() {
  try {
    const data = await fs.readFile(DATA_FILE, 'utf8');
    userData = JSON.parse(data);
  } catch (error) {
    console.log('初始化空的資料檔案');
    userData = {};
  }
}

// 儲存資料
async function saveData() {
  try {
    await fs.writeFile(DATA_FILE, JSON.stringify(userData, null, 2));
  } catch (error) {
    console.error('儲存資料失敗:', error);
  }
}

// 初始化用戶資料
function initUser(userId) {
  if (!userData[userId]) {
    userData[userId] = {
      todos: [],
      reminderTime: '09:00', // 預設提醒時間
      timezone: 'Asia/Taipei',
      scheduledReminders: [] // 新增：排程提醒
    };
    saveData();
  }
  // 為現有用戶添加新功能
  if (!userData[userId].scheduledReminders) {
    userData[userId].scheduledReminders = [];
    saveData();
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

// 處理訊息事件
async function handleEvent(event) {
  if (event.type !== 'message' || event.message.type !== 'text') {
    return Promise.resolve(null);
  }

  const userId = event.source.userId;
  const userMessage = event.message.text.trim();
  
  initUser(userId);
  
  let replyMessage = '';

  // 解析用戶指令
  if (userMessage === '幫助' || userMessage === 'help') {
    replyMessage = getHelpMessage();
  } else if (userMessage === '查詢' || userMessage === '清單') {
    replyMessage = getTodoList(userId);
  } else if (userMessage === '日程' || userMessage === '提醒清單') {
    replyMessage = getScheduledReminders(userId);
  } else if (userMessage.startsWith('新增 ')) {
    const todo = userMessage.substring(3).trim();
    replyMessage = addTodo(userId, todo);
  } else if (userMessage.startsWith('刪除 ')) {
    const index = parseInt(userMessage.substring(3).trim()) - 1;
    replyMessage = deleteTodo(userId, index);
  } else if (userMessage.startsWith('提醒 ')) {
    const reminderText = userMessage.substring(3).trim();
    replyMessage = addScheduledReminder(userId, reminderText);
  } else if (userMessage.startsWith('刪除提醒 ')) {
    const index = parseInt(userMessage.substring(5).trim()) - 1;
    replyMessage = deleteScheduledReminder(userId, index);
  } else if (userMessage.startsWith('設定時間 ')) {
    const time = userMessage.substring(5).trim();
    replyMessage = setReminderTime(userId, time);
  } else if (userMessage === '查詢時間') {
    replyMessage = getReminderTime(userId);
  } else {
    replyMessage = '指令不正確，請輸入「幫助」查看使用說明';
  }

  return client.replyMessage(event.replyToken, {
    type: 'text',
    text: replyMessage
  });
}

// 獲取幫助訊息
function getHelpMessage() {
  return `📋 代辦事項機器人使用說明：

📝 基本功能：
• 新增 [事項] - 新增代辦事項
• 刪除 [編號] - 刪除指定代辦事項
• 查詢 或 清單 - 查看所有代辦事項

📅 日期提醒：
• 提醒 [日期] [事項] - 新增特定日期提醒
• 日程 或 提醒清單 - 查看所有提醒
• 刪除提醒 [編號] - 刪除指定提醒

⏰ 每日提醒設定：
• 設定時間 [HH:MM] - 設定每日提醒時間
• 查詢時間 - 查看目前提醒時間

💡 範例：
• 新增 買午餐
• 提醒 8/9 繳電話費
• 提醒 明天 開會
• 刪除 1
• 設定時間 08:30

輸入「幫助」可重複查看此說明`;
}

// 新增代辦事項
function addTodo(userId, todo) {
  if (!todo) {
    return '請輸入要新增的代辦事項\n格式：新增 [事項內容]';
  }
  
  userData[userId].todos.push({
    id: Date.now(),
    content: todo,
    createdAt: new Date().toISOString(),
    completed: false
  });
  
  saveData();
  return `✅ 已新增代辦事項：「${todo}」\n目前共有 ${userData[userId].todos.length} 項代辦事項`;
}

// 刪除代辦事項
function deleteTodo(userId, index) {
  const todos = userData[userId].todos;
  
  if (index < 0 || index >= todos.length) {
    return `❌ 編號不正確，請輸入 1 到 ${todos.length} 之間的數字`;
  }
  
  const deletedTodo = todos.splice(index, 1)[0];
  saveData();
  
  return `🗑️ 已刪除代辦事項：「${deletedTodo.content}」\n剩餘 ${todos.length} 項代辦事項`;
}

// 獲取代辦事項清單
function getTodoList(userId) {
  const todos = userData[userId].todos;
  
  if (todos.length === 0) {
    return '📝 目前沒有代辦事項\n輸入「新增 [事項]」來新增代辦事項';
  }
  
  let message = `📋 您的代辦事項清單 (${todos.length} 項)：\n\n`;
  todos.forEach((todo, index) => {
    const date = new Date(todo.createdAt).toLocaleDateString('zh-TW');
    message += `${index + 1}. ${todo.content}\n   📅 ${date}\n\n`;
  });
  
  message += '💡 輸入「刪除 [編號]」可刪除指定項目';
  return message;
}

// 設定提醒時間
function setReminderTime(userId, time) {
  const timeRegex = /^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$/;
  
  if (!timeRegex.test(time)) {
    return '❌ 時間格式不正確\n請使用 HH:MM 格式，例如：08:30';
  }
  
  userData[userId].reminderTime = time;
  saveData();
  
  return `⏰ 已設定每日提醒時間為：${time}\n將於每天 ${time} 提醒您的代辦事項`;
}

// 解析日期
function parseDate(dateStr) {
  const now = new Date();
  const currentYear = now.getFullYear();
  
  // 處理 "明天"、"後天" 等
  if (dateStr === '明天') {
    const tomorrow = new Date(now);
    tomorrow.setDate(now.getDate() + 1);
    return tomorrow;
  }
  
  if (dateStr === '後天') {
    const dayAfterTomorrow = new Date(now);
    dayAfterTomorrow.setDate(now.getDate() + 2);
    return dayAfterTomorrow;
  }
  
  // 處理 MM/DD 格式
  const mmddPattern = /^(\d{1,2})\/(\d{1,2})$/;
  const match = dateStr.match(mmddPattern);
  if (match) {
    const month = parseInt(match[1]) - 1; // JavaScript 月份從 0 開始
    const day = parseInt(match[2]);
    const targetDate = new Date(currentYear, month, day);
    
    // 如果日期已過，設定為明年
    if (targetDate < now) {
      targetDate.setFullYear(currentYear + 1);
    }
    
    return targetDate;
  }
  
  return null;
}

// 新增排程提醒
function addScheduledReminder(userId, reminderText) {
  const parts = reminderText.split(' ');
  if (parts.length < 2) {
    return '❌ 格式不正確\n請使用：提醒 [日期] [事項]\n例如：提醒 8/9 繳電話費';
  }
  
  const dateStr = parts[0];
  const content = parts.slice(1).join(' ');
  
  const targetDate = parseDate(dateStr);
  if (!targetDate) {
    return '❌ 日期格式不正確\n支援格式：MM/DD、明天、後天\n例如：8/9、明天';
  }
  
  const reminder = {
    id: Date.now(),
    content: content,
    date: targetDate.toISOString(),
    dateStr: `${targetDate.getMonth() + 1}/${targetDate.getDate()}`,
    completed: false,
    createdAt: new Date().toISOString()
  };
  
  userData[userId].scheduledReminders.push(reminder);
  saveData();
  
  return `📅 已新增提醒：「${content}」\n提醒日期：${reminder.dateStr}\n目前共有 ${userData[userId].scheduledReminders.length} 個提醒`;
}

// 獲取排程提醒清單
function getScheduledReminders(userId) {
  const reminders = userData[userId].scheduledReminders || [];
  
  if (reminders.length === 0) {
    return '📅 目前沒有排程提醒\n輸入「提醒 [日期] [事項]」來新增提醒';
  }
  
  // 依日期排序
  reminders.sort((a, b) => new Date(a.date) - new Date(b.date));
  
  let message = `📅 您的提醒清單 (${reminders.length} 項)：\n\n`;
  reminders.forEach((reminder, index) => {
    const date = new Date(reminder.date);
    const today = new Date();
    const diffTime = date - today;
    const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
    
    let dayText = '';
    if (diffDays === 0) dayText = ' (今天)';
    else if (diffDays === 1) dayText = ' (明天)';
    else if (diffDays < 0) dayText = ' (已過期)';
    
    message += `${index + 1}. ${reminder.content}\n   📅 ${reminder.dateStr}${dayText}\n\n`;
  });
  
  message += '💡 輸入「刪除提醒 [編號]」可刪除指定提醒';
  return message;
}

// 刪除排程提醒
function deleteScheduledReminder(userId, index) {
  const reminders = userData[userId].scheduledReminders || [];
  
  if (index < 0 || index >= reminders.length) {
    return `❌ 編號不正確，請輸入 1 到 ${reminders.length} 之間的數字`;
  }
  
  const deletedReminder = reminders.splice(index, 1)[0];
  saveData();
  
  return `🗑️ 已刪除提醒：「${deletedReminder.content}」\n剩餘 ${reminders.length} 個提醒`;
}

// 獲取提醒時間
function getReminderTime(userId) {
  const time = userData[userId].reminderTime;
  const now = new Date();
  const currentServerTime = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
  return `⏰ 目前每日提醒時間：${time}\n🕐 伺服器目前時間：${currentServerTime}\n輸入「設定時間 [HH:MM]」可修改提醒時間`;
}

// 發送排程提醒
async function checkScheduledReminders() {
  const today = new Date();
  today.setHours(0, 0, 0, 0); // 設定為當天 00:00:00
  
  for (const userId in userData) {
    const user = userData[userId];
    const reminders = user.scheduledReminders || [];
    
    // 找出今天要提醒的項目
    const todayReminders = reminders.filter(reminder => {
      const reminderDate = new Date(reminder.date);
      reminderDate.setHours(0, 0, 0, 0);
      return reminderDate.getTime() === today.getTime() && !reminder.completed;
    });
    
    if (todayReminders.length > 0) {
      let message = `📅 今日提醒 (${todayReminders.length} 項)：\n\n`;
      todayReminders.forEach((reminder, index) => {
        message += `${index + 1}. ${reminder.content}\n`;
      });
      message += '\n📝 記得完成這些事項喔！';
      
      try {
        await client.pushMessage(userId, {
          type: 'text',
          text: message
        });
        
        // 標記為已提醒
        todayReminders.forEach(reminder => {
          reminder.completed = true;
        });
        
        console.log(`已發送排程提醒給用戶: ${userId}`);
      } catch (error) {
        console.error(`發送排程提醒失敗 ${userId}:`, error);
      }
    }
  }
  
  saveData();
}
async function sendReminderToUser(userId) {
  try {
    const todos = userData[userId].todos;
    if (todos.length === 0) return;
    
    let message = `🔔 早安！您有 ${todos.length} 項代辦事項：\n\n`;
    todos.forEach((todo, index) => {
      message += `${index + 1}. ${todo.content}\n`;
    });
    message += '\n📝 祝您今天順利完成所有任務！';
    
    await client.pushMessage(userId, {
      type: 'text',
      text: message
    });
    
    console.log(`已發送提醒給用戶: ${userId}`);
  } catch (error) {
    console.error(`發送提醒失敗 ${userId}:`, error);
  }
}

// 發送每日提醒給所有用戶
async function sendDailyReminders() {
  const now = new Date();
  const currentTime = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
  
  console.log(`檢查提醒時間: ${currentTime}`);
  
  // 檢查排程提醒（每天 09:00 檢查一次）
  if (currentTime === '09:00') {
    await checkScheduledReminders();
  }
  
  // 檢查每日代辦事項提醒
  for (const userId in userData) {
    const user = userData[userId];
    if (user.reminderTime === currentTime && user.todos.length > 0) {
      await sendReminderToUser(userId);
    }
  }
}

// 設定定時任務 - 每分鐘檢查一次
cron.schedule('* * * * *', () => {
  sendDailyReminders();
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
