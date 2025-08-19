const express = require('express');
const line = require('@line/bot-sdk');
const cron = require('node-cron');
const { MongoClient } = require('mongodb');

const app = express();
const PORT = process.env.PORT || 3000;

// LINE Bot 設定
const config = {
  channelAccessToken: process.env.CHANNEL_ACCESS_TOKEN || 'LShi8pcxKnQoE7akuvZPZGuXOVr6gPf0Wn/46cxYouM3hgsqY5+69vZW5lowsMEDh0E0FAqDoOPx2KtXn5EJ0xPgKJ3CVvo0O6Hh/el6zGRleP9SkY1J6aWFOjXIhj2l1H+almOBGt1pVfHGcIcitwdB04t89/1O/w1cDnyilFU=',
  channelSecret: process.env.CHANNEL_SECRET || '2157683f2cea90bd12c1702f18886238'
};

const client = new line.Client(config);

// MongoDB 設定
const MONGODB_URI = process.env.MONGODB_URI || 'mongodb://localhost:27017/linebot';
let db;
let mongoClient;

// 初始化資料結構
let userData = {};
let isDataLoaded = false;

// 短期提醒和時間提醒儲存 Map
let shortTermReminders = new Map();

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

// 解析每月事項的日期格式
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

// 解析短期提醒指令
function parseShortTermReminder(text) {
  const patterns = [
    /(\d+)分鐘後(.+)/,
    /(\d+)小時後(.+)/,
    /(\d+)秒後(.+)/
  ];
  
  for (let i = 0; i < patterns.length; i++) {
    const match = text.match(patterns[i]);
    if (match) {
      const value = parseInt(match[1]);
      const content = match[2].trim();
      
      if (!content) {
        return { isValid: false, error: '請輸入提醒內容' };
      }
      
      let minutes;
      let unit;
      
      switch (i) {
        case 0: // 分鐘
          minutes = value;
          unit = '分鐘';
          if (value < 1 || value > 1440) {
            return { isValid: false, error: '分鐘數請設定在 1-1440 之間' };
          }
          break;
        case 1: // 小時
          minutes = value * 60;
          unit = '小時';
          if (value < 1 || value > 24) {
            return { isValid: false, error: '小時數請設定在 1-24 之間' };
          }
          break;
        case 2: // 秒
          minutes = value / 60;
          unit = '秒';
          if (value < 10 || value > 3600) {
            return { isValid: false, error: '秒數請設定在 10-3600 之間' };
          }
          break;
      }
      
      return {
        isValid: true,
        minutes: minutes,
        originalValue: value,
        unit: unit,
        content: content
      };
    }
  }
  
  return { isValid: false, error: '格式不正確，請使用：數字+時間單位+後+內容\n例如：5分鐘後倒垃圾' };
}

// 解析時間提醒指令
function parseTimeReminder(text) {
  const timePattern = /(\d{1,2}):(\d{2})(.+)/;
  const match = text.match(timePattern);
  
  if (match) {
    const hours = parseInt(match[1]);
    const minutes = parseInt(match[2]);
    const content = match[3].trim();
    
    if (!content) {
      return { isValid: false, error: '請輸入提醒內容' };
    }
    
    // 驗證時間格式
    if (hours < 0 || hours > 23) {
      return { isValid: false, error: '小時請設定在 0-23 之間' };
    }
    
    if (minutes < 0 || minutes > 59) {
      return { isValid: false, error: '分鐘請設定在 0-59 之間' };
    }
    
    return {
      isValid: true,
      hours: hours,
      minutes: minutes,
      timeString: `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}`,
      content: content
    };
  }
  
  return { isValid: false, error: '格式不正確，請使用：HH:MM+內容\n例如：12:00倒垃圾' };
}

// 連接 MongoDB 資料庫
async function connectDatabase() {
  try {
    console.log('🔗 正在連接 MongoDB...');
    mongoClient = new MongoClient(MONGODB_URI);
    await mongoClient.connect();
    db = mongoClient.db('linebot');
    console.log('✅ MongoDB 連接成功');
    return true;
  } catch (error) {
    console.error('❌ MongoDB 連接失敗:', error);
    return false;
  }
}

// 從 MongoDB 載入資料
async function loadData() {
  try {
    if (!db) {
      throw new Error('資料庫未連接');
    }
    
    console.log('📥 從 MongoDB 載入用戶資料...');
    
    // 從 users 集合載入所有用戶資料
    const users = await db.collection('users').find({}).toArray();
    
    userData = {};
    for (const user of users) {
      userData[user.userId] = {
        todos: user.todos || [],
        monthlyTodos: user.monthlyTodos || [],
        shortTermReminders: user.shortTermReminders || [],
        timeReminders: user.timeReminders || [],
        morningReminderTime: user.morningReminderTime || '09:00',
        eveningReminderTime: user.eveningReminderTime || '18:00',
        timezone: user.timezone || 'Asia/Taipei'
      };
    }
    
    isDataLoaded = true;
    console.log(`✅ 資料載入成功，用戶數: ${Object.keys(userData).length}`);
    
    // 恢復提醒定時器
    await restoreAllReminders();
    
  } catch (error) {
    console.log('🔄 初始化空的用戶資料');
    userData = {};
    isDataLoaded = true;
  }
}

// 儲存資料到 MongoDB
let isSaving = false;
async function saveData() {
  if (isSaving) {
    console.log('正在儲存中，跳過重複儲存');
    return;
  }
  
  if (!db) {
    console.error('❌ 資料庫未連接，無法儲存');
    return;
  }
  
  isSaving = true;
  try {
    console.log('💾 儲存資料到 MongoDB...');
    
    // 批次更新所有用戶資料
    const bulkOps = [];
    
    for (const [userId, userInfo] of Object.entries(userData)) {
      bulkOps.push({
        updateOne: {
          filter: { userId: userId },
          update: { 
            $set: {
              userId: userId,
              todos: userInfo.todos,
              monthlyTodos: userInfo.monthlyTodos,
              shortTermReminders: userInfo.shortTermReminders,
              timeReminders: userInfo.timeReminders,
              morningReminderTime: userInfo.morningReminderTime,
              eveningReminderTime: userInfo.eveningReminderTime,
              timezone: userInfo.timezone,
              lastUpdated: new Date()
            }
          },
          upsert: true // 如果不存在則新增
        }
      });
    }
    
    if (bulkOps.length > 0) {
      await db.collection('users').bulkWrite(bulkOps);
    }
    
    console.log(`✅ 資料已儲存到 MongoDB，用戶數: ${Object.keys(userData).length}`);
  } catch (error) {
    console.error('❌ 儲存資料失敗:', error);
    throw error;
  } finally {
    isSaving = false;
  }
}

// 儲存單一用戶資料（效能優化）
async function saveUserData(userId) {
  if (!db || !userData[userId]) {
    return;
  }
  
  try {
    const userInfo = userData[userId];
    await db.collection('users').updateOne(
      { userId: userId },
      { 
        $set: {
          userId: userId,
          todos: userInfo.todos,
          monthlyTodos: userInfo.monthlyTodos,
          shortTermReminders: userInfo.shortTermReminders,
          timeReminders: userInfo.timeReminders,
          morningReminderTime: userInfo.morningReminderTime,
          eveningReminderTime: userInfo.eveningReminderTime,
          timezone: userInfo.timezone,
          lastUpdated: new Date()
        }
      },
      { upsert: true }
    );
    
    console.log(`✅ 用戶 ${userId} 資料已儲存`);
  } catch (error) {
    console.error(`❌ 儲存用戶 ${userId} 資料失敗:`, error);
  }
}

// 初始化用戶資料
function initUser(userId) {
  if (!userData[userId]) {
    userData[userId] = {
      todos: [],
      monthlyTodos: [],
      shortTermReminders: [],
      timeReminders: [],
      morningReminderTime: '09:00',
      eveningReminderTime: '18:00',
      timezone: 'Asia/Taipei'
    };
    console.log(`初始化用戶: ${userId}`);
    saveUserData(userId); // 立即儲存新用戶資料
  }
  
  // 為舊用戶添加新欄位
  if (!userData[userId].monthlyTodos) {
    userData[userId].monthlyTodos = [];
  }
  if (!userData[userId].shortTermReminders) {
    userData[userId].shortTermReminders = [];
  }
  if (!userData[userId].timeReminders) {
    userData[userId].timeReminders = [];
    saveUserData(userId);
  }
}

// 恢復所有提醒定時器
async function restoreAllReminders() {
  const currentTime = new Date();
  let restoredShortCount = 0;
  let restoredTimeCount = 0;
  let expiredCount = 0;
  
  console.log('🔄 開始恢復所有提醒...');
  
  for (const userId in userData) {
    const user = userData[userId];
    
    // 恢復短期提醒
    if (user.shortTermReminders) {
      for (let i = user.shortTermReminders.length - 1; i >= 0; i--) {
        const reminder = user.shortTermReminders[i];
        const reminderTime = new Date(reminder.reminderTime);
        const timeLeft = reminderTime - currentTime;
        
        if (timeLeft <= 0) {
          if (currentTime - reminderTime > 3600000) { // 1小時
            user.shortTermReminders.splice(i, 1);
            expiredCount++;
          }
          continue;
        }
        
        const reminderId = reminder.id;
        const timerId = setTimeout(async () => {
          await sendShortTermReminder(reminder);
          shortTermReminders.delete(reminderId);
          await removeShortTermReminderFromUser(userId, reminderId);
        }, timeLeft);
        
        shortTermReminders.set(reminderId, {
          ...reminder,
          timerId: timerId
        });
        
        restoredShortCount++;
      }
    }
    
    // 恢復時間提醒
    if (user.timeReminders) {
      for (let i = user.timeReminders.length - 1; i >= 0; i--) {
        const reminder = user.timeReminders[i];
        const reminderTime = new Date(reminder.reminderTime);
        const timeLeft = reminderTime - currentTime;
        
        if (timeLeft <= 0) {
          if (currentTime - reminderTime > 3600000) { // 1小時
            user.timeReminders.splice(i, 1);
            expiredCount++;
          }
          continue;
        }
        
        const reminderId = reminder.id;
        const timerId = setTimeout(async () => {
          await sendTimeReminder(reminder);
          shortTermReminders.delete(reminderId);
          await removeTimeReminderFromUser(userId, reminderId);
        }, timeLeft);
        
        shortTermReminders.set(reminderId, {
          ...reminder,
          timerId: timerId
        });
        
        restoredTimeCount++;
      }
    }
  }
  
  if (expiredCount > 0) {
    await saveData(); // 保存清理後的資料
  }
  
  console.log(`✅ 恢復提醒完成 - 短期: ${restoredShortCount} 項，時間: ${restoredTimeCount} 項，清理過期: ${expiredCount} 項`);
}

// 檢查是否需要提醒 - 調試版本
function shouldRemindTodo(todo) {
  const today = getTaiwanDate();
  
  console.log(`檢查事項: ${todo.content}, hasDate: ${todo.hasDate}`);
  
  if (!todo.hasDate) {
    console.log(`  -> 無日期事項，應該提醒: true`);
    return true;
  }
  
  const targetDate = new Date(todo.targetDate);
  const tomorrow = new Date(today);
  tomorrow.setDate(today.getDate() + 1);
  
  const shouldRemind = (
    tomorrow.getFullYear() === targetDate.getFullYear() &&
    tomorrow.getMonth() === targetDate.getMonth() &&
    tomorrow.getDate() === targetDate.getDate()
  );
  
  console.log(`  -> 有日期事項，目標: ${targetDate.toLocaleDateString()}, 明天: ${tomorrow.toLocaleDateString()}, 應該提醒: ${shouldRemind}`);
  
  return shouldRemind;
}

// 檢查代辦事項是否已過期
function isTodoExpired(todo) {
  if (!todo.hasDate) {
    return false; // 沒有日期的事項不會過期
  }
  
  const today = getTaiwanDate();
  const targetDate = new Date(todo.targetDate);
  
  // 如果目標日期已過，標記為過期
  return targetDate < today;
}

// 發送提醒訊息給單一用戶 - 調試版本
async function sendReminderToUser(userId, timeType) {
  try {
    const user = userData[userId];
    if (!user || !user.todos) {
      console.log(`❌ 用戶 ${userId} 資料不存在`);
      return;
    }
    
    console.log(`🔍 檢查用戶 ${userId} 的事項，總數: ${user.todos.length}`);
    
    // 打印所有事項的詳細信息
    user.todos.forEach((todo, index) => {
      console.log(`  事項 ${index + 1}: "${todo.content}", hasDate: ${todo.hasDate}, 應該提醒: ${shouldRemindTodo(todo)}`);
    });
    
    const todos = user.todos.filter(shouldRemindTodo);
    
    console.log(`📋 用戶 ${userId} 需要提醒的事項數量: ${todos.length}`);
    
    if (todos.length === 0) {
      console.log(`📝 用戶 ${userId} 沒有需要提醒的事項`);
      return;
    }
    
    const timeIcon = timeType === 'morning' ? '🌅' : '🌙';
    const timeText = timeType === 'morning' ? '早安' : '晚安';
    
    let message = `${timeIcon} ${timeText}！您有 ${todos.length} 項待辦事項：\n\n`;
    
    const datedTodos = todos.filter(todo => todo.hasDate);
    const regularTodos = todos.filter(todo => !todo.hasDate);
    
    console.log(`📊 分類結果 - 有日期: ${datedTodos.length}, 無日期: ${regularTodos.length}`);
    
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
    
    console.log(`📤 準備發送訊息給用戶 ${userId}:\n${message}`);
    
    await client.pushMessage(userId, {
      type: 'text',
      text: message
    });
    
    console.log(`✅ 已成功發送${timeText}提醒給用戶: ${userId}`);
  } catch (error) {
    console.error(`❌ 發送提醒失敗 ${userId}:`, error);
  }
}

// 發送提醒給所有用戶 - 調試版本
async function sendReminders(timeType) {
  const currentTime = getTaiwanTimeHHMM();
  
  console.log(`🔔 檢查${timeType === 'morning' ? '早上' : '晚上'}提醒時間 (台灣時間): ${currentTime}`);
  console.log(`📊 目前總用戶數: ${Object.keys(userData).length}`);
  
  let remindersSent = 0;
  let usersChecked = 0;
  
  for (const userId in userData) {
    const user = userData[userId];
    if (!user) continue;
    
    usersChecked++;
    const targetTime = timeType === 'morning' ? user.morningReminderTime : user.eveningReminderTime;
    
    console.log(`👤 用戶 ${userId}: 目標時間=${targetTime}, 當前時間=${currentTime}, 待辦事項數=${user.todos?.length || 0}`);
    
    if (targetTime === currentTime) {
      console.log(`⏰ 時間匹配！為用戶 ${userId} 發送提醒`);
      await sendReminderToUser(userId, timeType);
      remindersSent++;
    } else {
      console.log(`⏭️ 時間不匹配，跳過用戶 ${userId}`);
    }
  }
  
  console.log(`📋 檢查完成 - 檢查用戶: ${usersChecked}, 發送提醒: ${remindersSent}`);
  
  if (remindersSent > 0) {
    console.log(`✅ 共發送了 ${remindersSent} 個${timeType === 'morning' ? '早上' : '晚上'}提醒`);
  }
}

// 新增一個專門的調試函數
async function debugUserReminders(userId) {
  console.log(`🐛 開始調試用戶 ${userId} 的提醒狀態`);
  
  const user = userData[userId];
  if (!user) {
    console.log(`❌ 用戶 ${userId} 不存在`);
    return;
  }
  
  console.log(`📊 用戶基本信息:`);
  console.log(`  - 早上提醒時間: ${user.morningReminderTime}`);
  console.log(`  - 晚上提醒時間: ${user.eveningReminderTime}`);
  console.log(`  - 代辦事項總數: ${user.todos?.length || 0}`);
  
  if (user.todos && user.todos.length > 0) {
    console.log(`📝 所有代辦事項詳情:`);
    user.todos.forEach((todo, index) => {
      console.log(`  ${index + 1}. "${todo.content}"`);
      console.log(`      - hasDate: ${todo.hasDate}`);
      console.log(`      - targetDate: ${todo.targetDate}`);
      console.log(`      - completed: ${todo.completed}`);
      console.log(`      - 應該提醒: ${shouldRemindTodo(todo)}`);
    });
  }
  
  const currentTime = getTaiwanTimeHHMM();
  console.log(`🕐 當前台灣時間: ${currentTime}`);
  
  // 模擬提醒檢查
  console.log(`🔍 模擬提醒檢查:`);
  if (user.morningReminderTime === currentTime) {
    console.log(`  ✅ 現在是早上提醒時間！`);
  } else if (user.eveningReminderTime === currentTime) {
    console.log(`  ✅ 現在是晚上提醒時間！`);
  } else {
    console.log(`  ⏭️ 現在不是提醒時間`);
    console.log(`  📅 下次早上提醒: ${user.morningReminderTime}`);
    console.log(`  🌙 下次晚上提醒: ${user.eveningReminderTime}`);
  }
}

// 創建短期提醒
async function createShortTermReminder(userId, reminderText) {
  const parsed = parseShortTermReminder(reminderText);
  
  if (!parsed.isValid) {
    return `❌ ${parsed.error}`;
  }
  
  const reminderId = `${userId}_short_${Date.now()}`;
  const reminderTime = new Date(Date.now() + (parsed.minutes * 60 * 1000));
  
  const reminderData = {
    id: reminderId,
    userId: userId,
    content: parsed.content,
    createdAt: getTaiwanTime(),
    reminderTime: reminderTime,
    minutes: parsed.minutes,
    originalValue: parsed.originalValue,
    unit: parsed.unit,
    completed: false,
    type: 'short'
  };
  
  // 設定定時器
  const timerId = setTimeout(async () => {
    await sendShortTermReminder(reminderData);
    shortTermReminders.delete(reminderId);
    removeShortTermReminderFromUser(userId, reminderId);
  }, parsed.minutes * 60 * 1000);
  
  // 儲存到記憶體 Map 中
  shortTermReminders.set(reminderId, {
    ...reminderData,
    timerId: timerId
  });
  
  // 儲存到用戶資料中
  userData[userId].shortTermReminders.push(reminderData);
  
  try {
    await saveUserData(userId);
    console.log(`用戶 ${userId} 設定短期提醒: ${parsed.content} (${parsed.originalValue}${parsed.unit}後)`);
  } catch (err) {
    console.error('設定短期提醒時儲存失敗:', err);
    clearTimeout(timerId);
    shortTermReminders.delete(reminderId);
    return '❌ 設定失敗，請稍後再試';
  }
  
  const reminderTimeStr = reminderTime.toLocaleString('zh-TW', {
    timeZone: 'Asia/Taipei',
    hour12: false,
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  });
  
  return `⏰ 已設定短期提醒：「${parsed.content}」\n⏳ ${parsed.originalValue}${parsed.unit}後提醒 (${reminderTimeStr})\n📝 輸入「短期清單」可查看所有短期提醒`;
}

// 創建時間提醒
async function createTimeReminder(userId, reminderText) {
  const parsed = parseTimeReminder(reminderText);
  
  if (!parsed.isValid) {
    return `❌ ${parsed.error}`;
  }
  
  const reminderId = `${userId}_time_${Date.now()}`;
  const now = getTaiwanDate();
  const targetTime = new Date(now);
  
  // 設定目標時間
  targetTime.setHours(parsed.hours, parsed.minutes, 0, 0);
  
  // 如果時間已過，設為明天
  if (targetTime <= now) {
    targetTime.setDate(targetTime.getDate() + 1);
  }
  
  const timeLeft = targetTime - now;
  
  const reminderData = {
    id: reminderId,
    userId: userId,
    content: parsed.content,
    timeString: parsed.timeString,
    createdAt: getTaiwanTime(),
    reminderTime: targetTime,
    completed: false,
    type: 'time'
  };
  
  // 設定定時器
  const timerId = setTimeout(async () => {
    await sendTimeReminder(reminderData);
    shortTermReminders.delete(reminderId);
    removeTimeReminderFromUser(userId, reminderId);
  }, timeLeft);
  
  // 儲存到記憶體 Map 中
  shortTermReminders.set(reminderId, {
    ...reminderData,
    timerId: timerId
  });
  
  // 儲存到用戶資料中
  userData[userId].timeReminders.push(reminderData);
  
  try {
    await saveUserData(userId);
    console.log(`用戶 ${userId} 設定時間提醒: ${parsed.content} (${parsed.timeString})`);
  } catch (err) {
    console.error('設定時間提醒時儲存失敗:', err);
    clearTimeout(timerId);
    shortTermReminders.delete(reminderId);
    return '❌ 設定失敗，請稍後再試';
  }
  
  const targetTimeStr = targetTime.toLocaleString('zh-TW', {
    timeZone: 'Asia/Taipei',
    hour12: false,
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  });
  
  const isToday = targetTime.toDateString() === now.toDateString();
  const dateText = isToday ? '今天' : '明天';
  
  return `⏰ 已設定時間提醒：「${parsed.content}」\n🕐 ${dateText} ${parsed.timeString} 提醒 (${targetTimeStr})\n📝 輸入「時間清單」可查看所有時間提醒`;
}

// 發送短期提醒
async function sendShortTermReminder(reminderData) {
  try {
    const message = `⏰ 短期提醒時間到！
    
📋 提醒事項：${reminderData.content}
⏳ 設定時間：${reminderData.createdAt}
🎯 現在該去執行了！`;

    await client.pushMessage(reminderData.userId, {
      type: 'text',
      text: message
    });
    
    console.log(`✅ 已發送短期提醒給用戶 ${reminderData.userId}: ${reminderData.content}`);
  } catch (error) {
    console.error(`❌ 發送短期提醒失敗 ${reminderData.userId}:`, error);
  }
}

// 發送時間提醒
async function sendTimeReminder(reminderData) {
  try {
    const message = `⏰ 時間提醒！
    
📋 提醒事項：${reminderData.content}
🕐 設定時間：${reminderData.timeString}
⏳ 建立時間：${reminderData.createdAt}
🎯 現在該去執行了！`;

    await client.pushMessage(reminderData.userId, {
      type: 'text',
      text: message
    });
    
    console.log(`✅ 已發送時間提醒給用戶 ${reminderData.userId}: ${reminderData.content}`);
  } catch (error) {
    console.error(`❌ 發送時間提醒失敗 ${reminderData.userId}:`, error);
  }
}

// 從用戶資料中移除已完成的短期提醒
async function removeShortTermReminderFromUser(userId, reminderId) {
  if (userData[userId] && userData[userId].shortTermReminders) {
    userData[userId].shortTermReminders = userData[userId].shortTermReminders.filter(
      reminder => reminder.id !== reminderId
    );
    try {
      await saveUserData(userId);
    } catch (err) {
      console.error('移除短期提醒時儲存失敗:', err);
    }
  }
}

// 從用戶資料中移除已完成的時間提醒
async function removeTimeReminderFromUser(userId, reminderId) {
  if (userData[userId] && userData[userId].timeReminders) {
    userData[userId].timeReminders = userData[userId].timeReminders.filter(
      reminder => reminder.id !== reminderId
    );
    try {
      await saveUserData(userId);
    } catch (err) {
      console.error('移除時間提醒時儲存失敗:', err);
    }
  }
}

// 獲取短期提醒清單
function getShortTermReminderList(userId) {
  const reminders = userData[userId].shortTermReminders || [];
  
  if (reminders.length === 0) {
    return '📝 目前沒有短期提醒\n輸入格式：「5分鐘後倒垃圾」來設定短期提醒\n\n⏰ 支援格式：\n• X分鐘後[事項] (1-1440分鐘)\n• X小時後[事項] (1-24小時)\n• X秒後[事項] (10-3600秒)';
  }
  
  let message = `⏰ 短期提醒清單 (${reminders.length} 項)：\n\n`;
  
  const currentTime = new Date();
  
  reminders.forEach((reminder, index) => {
    const reminderTime = new Date(reminder.reminderTime);
    const timeLeft = reminderTime - currentTime;
    const isExpired = timeLeft <= 0;
    
    const reminderTimeStr = reminderTime.toLocaleString('zh-TW', {
      timeZone: 'Asia/Taipei',
      hour12: false,
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit'
    });
    
    let timeLeftStr = '';
    if (isExpired) {
      timeLeftStr = '⏰ 已到期';
    } else {
      const minutesLeft = Math.ceil(timeLeft / 60000);
      if (minutesLeft < 60) {
        timeLeftStr = `⏳ 剩餘 ${minutesLeft} 分鐘`;
      } else {
        const hoursLeft = Math.floor(minutesLeft / 60);
        const minsLeft = minutesLeft % 60;
        timeLeftStr = `⏳ 剩餘 ${hoursLeft}小時${minsLeft}分鐘`;
      }
    }
    
    message += `${index + 1}. ${reminder.content}\n`;
    message += `   📅 ${reminderTimeStr}\n`;
    message += `   ${timeLeftStr}\n\n`;
  });
  
  message += '💡 輸入「短期刪除 [編號]」可取消提醒\n💡 輸入「清理短期」可清理已過期的提醒';
  
  return message;
}

// 獲取時間提醒清單
function getTimeReminderList(userId) {
  const reminders = userData[userId].timeReminders || [];
  
  if (reminders.length === 0) {
    return '📝 目前沒有時間提醒\n輸入格式：「12:00倒垃圾」來設定時間提醒\n\n🕐 支援格式：\n• HH:MM+事項內容\n• 例如：14:30開會、09:00運動';
  }
  
  let message = `🕐 時間提醒清單 (${reminders.length} 項)：\n\n`;
  
  const currentTime = new Date();
  
  reminders.forEach((reminder, index) => {
    const reminderTime = new Date(reminder.reminderTime);
    const timeLeft = reminderTime - currentTime;
    const isExpired = timeLeft <= 0;
    
    const reminderTimeStr = reminderTime.toLocaleString('zh-TW', {
      timeZone: 'Asia/Taipei',
      hour12: false,
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit'
    });
    
    let timeLeftStr = '';
    if (isExpired) {
      timeLeftStr = '⏰ 已到期';
    } else {
      const hoursLeft = Math.floor(timeLeft / 3600000);
      const minutesLeft = Math.floor((timeLeft % 3600000) / 60000);
      
      if (hoursLeft > 0) {
        timeLeftStr = `⏳ 剩餘 ${hoursLeft}小時${minutesLeft}分鐘`;
      } else {
        timeLeftStr = `⏳ 剩餘 ${minutesLeft}分鐘`;
      }
    }
    
    message += `${index + 1}. ${reminder.content}\n`;
    message += `   🕐 ${reminderTimeStr}\n`;
    message += `   ${timeLeftStr}\n\n`;
  });
  
  message += '💡 輸入「時間刪除 [編號]」可取消提醒\n💡 輸入「清理時間」可清理已過期的提醒';
  
  return message;
}

// 取消短期提醒
async function cancelShortTermReminder(userId, index) {
  const reminders = userData[userId].shortTermReminders || [];
  
  if (index < 0 || index >= reminders.length) {
    return `❌ 編號不正確，請輸入 1 到 ${reminders.length} 之間的數字`;
  }
  
  const reminder = reminders[index];
  const reminderId = reminder.id;
  
  // 清理記憶體中的定時器
  if (shortTermReminders.has(reminderId)) {
    const timerData = shortTermReminders.get(reminderId);
    clearTimeout(timerData.timerId);
    shortTermReminders.delete(reminderId);
  }
  
  // 從用戶資料中移除
  reminders.splice(index, 1);
  
  try {
    await saveUserData(userId);
    console.log(`用戶 ${userId} 取消短期提醒: ${reminder.content}`);
  } catch (err) {
    console.error('取消短期提醒時儲存失敗:', err);
    return '❌ 取消失敗，請稍後再試';
  }
  
  return `🗑️ 已取消短期提醒：「${reminder.content}」\n剩餘 ${reminders.length} 項短期提醒`;
}

// 取消時間提醒
async function cancelTimeReminder(userId, index) {
  const reminders = userData[userId].timeReminders || [];
  
  if (index < 0 || index >= reminders.length) {
    return `❌ 編號不正確，請輸入 1 到 ${reminders.length} 之間的數字`;
  }
  
  const reminder = reminders[index];
  const reminderId = reminder.id;
  
  // 清理記憶體中的定時器
  if (shortTermReminders.has(reminderId)) {
    const timerData = shortTermReminders.get(reminderId);
    clearTimeout(timerData.timerId);
    shortTermReminders.delete(reminderId);
  }
  
  // 從用戶資料中移除
  reminders.splice(index, 1);
  
  try {
    await saveUserData(userId);
    console.log(`用戶 ${userId} 取消時間提醒: ${reminder.content}`);
  } catch (err) {
    console.error('取消時間提醒時儲存失敗:', err);
    return '❌ 取消失敗，請稍後再試';
  }
  
  return `🗑️ 已取消時間提醒：「${reminder.content}」(${reminder.timeString})\n剩餘 ${reminders.length} 項時間提醒`;
}

// 清理過期的短期提醒
async function cleanupExpiredShortTermReminders(userId) {
  const reminders = userData[userId].shortTermReminders || [];
  const currentTime = new Date();
  
  let cleanedCount = 0;
  let i = reminders.length - 1;
  
  while (i >= 0) {
    const reminder = reminders[i];
    const reminderTime = new Date(reminder.reminderTime);
    
    if (reminderTime < currentTime - 3600000) { // 3600000ms = 1小時
      const reminderId = reminder.id;
      
      if (shortTermReminders.has(reminderId)) {
        const timerData = shortTermReminders.get(reminderId);
        clearTimeout(timerData.timerId);
        shortTermReminders.delete(reminderId);
      }
      
      reminders.splice(i, 1);
      cleanedCount++;
    }
    i--;
  }
  
  if (cleanedCount > 0) {
    try {
      await saveUserData(userId);
      console.log(`用戶 ${userId} 清理過期短期提醒: ${cleanedCount} 項`);
    } catch (err) {
      console.error('清理短期提醒時儲存失敗:', err);
      return '❌ 清理失敗，請稍後再試';
    }
    
    return `🧹 已清理 ${cleanedCount} 項過期的短期提醒\n剩餘 ${reminders.length} 項短期提醒`;
  } else {
    return `✨ 沒有需要清理的過期提醒\n目前有 ${reminders.length} 項短期提醒`;
  }
}

// 清理過期的時間提醒
async function cleanupExpiredTimeReminders(userId) {
  const reminders = userData[userId].timeReminders || [];
  const currentTime = new Date();
  
  let cleanedCount = 0;
  let i = reminders.length - 1;
  
  while (i >= 0) {
    const reminder = reminders[i];
    const reminderTime = new Date(reminder.reminderTime);
    
    if (reminderTime < currentTime - 3600000) {
      const reminderId = reminder.id;
      
      if (shortTermReminders.has(reminderId)) {
        const timerData = shortTermReminders.get(reminderId);
        clearTimeout(timerData.timerId);
        shortTermReminders.delete(reminderId);
      }
      
      reminders.splice(i, 1);
      cleanedCount++;
    }
    i--;
  }
  
  if (cleanedCount > 0) {
    try {
      await saveUserData(userId);
      console.log(`用戶 ${userId} 清理過期時間提醒: ${cleanedCount} 項`);
    } catch (err) {
      console.error('清理時間提醒時儲存失敗:', err);
      return '❌ 清理失敗，請稍後再試';
    }
    
    return `🧹 已清理 ${cleanedCount} 項過期的時間提醒\n剩餘 ${reminders.length} 項時間提醒`;
  } else {
    return `✨ 沒有需要清理的過期提醒\n目前有 ${reminders.length} 項時間提醒`;
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
    } else if (userMessage === '測試提醒') {
      replyMessage = await testReminder(userId);
    } else if (userMessage.startsWith('測試時間 ')) {
      const time = userMessage.substring(5).trim();
      replyMessage = await testTimeReminder(userId, time);
    }
    // 每月固定事項指令
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
    // 短期提醒指令
    else if (userMessage.includes('分鐘後') || userMessage.includes('小時後') || userMessage.includes('秒後')) {
      replyMessage = await createShortTermReminder(userId, userMessage);
    } else if (userMessage === '短期清單' || userMessage === '短期查詢') {
      replyMessage = getShortTermReminderList(userId);
    } else if (userMessage.startsWith('短期刪除 ')) {
      const index = parseInt(userMessage.substring(5).trim()) - 1;
      replyMessage = await cancelShortTermReminder(userId, index);
    } else if (userMessage === '清理短期') {
      replyMessage = await cleanupExpiredShortTermReminders(userId);
    } 
    // 時間提醒指令
    else if (/^\d{1,2}:\d{2}.+/.test(userMessage)) {
      replyMessage = await createTimeReminder(userId, userMessage);
    } else if (userMessage === '時間清單' || userMessage === '時間查詢') {
      replyMessage = getTimeReminderList(userId);
    } else if (userMessage.startsWith('時間刪除 ')) {
      const index = parseInt(userMessage.substring(5).trim()) - 1;
      replyMessage = await cancelTimeReminder(userId, index);
    } else if (userMessage === '清理時間') {
      replyMessage = await cleanupExpiredTimeReminders(userId);
    } else if (userMessage === '調試提醒') {
      await debugUserReminders(userId);
      replyMessage = '調試信息已輸出到控制台，請檢查伺服器日誌\n\n如果您是在本地測試，請查看終端機的輸出\n如果是在雲端伺服器，請查看伺服器日誌';
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

⏰ 短期提醒：
• [時間]後[事項] - 設定短期提醒
• 短期清單 - 查看短期提醒清單
• 短期刪除 [編號] - 取消短期提醒
• 清理短期 - 清理過期的短期提醒

🕐 時間提醒：
• [HH:MM][事項] - 設定時間提醒
• 時間清單 - 查看時間提醒清單
• 時間刪除 [編號] - 取消時間提醒
• 清理時間 - 清理過期的時間提醒

🔄 每月固定事項：
• 每月新增 [事項] - 新增每月固定事項
• 每月新增 5號繳卡費 - 新增每月固定日期事項
• 每月刪除 [編號] - 刪除每月固定事項
• 每月清單 - 查看每月固定事項
• 生成本月 - 將本月固定事項加入代辦清單

⏰ 定時提醒設定：
• 早上時間 [HH:MM] - 設定早上提醒時間
• 晚上時間 [HH:MM] - 設定晚上提醒時間
• 查詢時間 - 查看目前提醒時間
• 調試提醒 - 檢查提醒狀態（調試用）

🔔 智能提醒說明：
• 短期提醒：立即設定，到時間自動提醒
• 時間提醒：今天指定時間提醒（過時則明天）
• 有日期的事項：只在前一天提醒
• 沒日期的事項：每天提醒
• 每月固定事項：需手動生成到代辦清單

🧪 測試功能：
• 狀態 - 查看系統狀態
• 測試提醒 - 立即測試提醒功能
• 測試時間 [HH:MM] - 測試特定時間提醒

💡 提醒範例：
短期提醒：5分鐘後倒垃圾、1小時後開會
時間提醒：12:00倒垃圾、14:30開會
日期提醒：8/15號繳電費
每月提醒：每月5號繳信用卡費

💾 資料安全：
使用 MongoDB 雲端資料庫，永不遺失

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
  
  try {
    await saveUserData(userId);
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

// 添加每月固定事項
async function addMonthlyTodo(userId, todo) {
  if (!todo) {
    return '請輸入要新增的每月固定事項\n格式：每月新增 [事項內容] 或 每月新增 5號繳卡費';
  }
  
  const parsed = parseMonthlyDate(todo);
  
  const monthlyTodoItem = {
    id: Date.now(),
    content: parsed.content,
    day: parsed.day,
    hasFixedDate: parsed.hasDate,
    createdAt: getTaiwanTime(),
    enabled: true
  };
  
  userData[userId].monthlyTodos.push(monthlyTodoItem);
  
  try {
    await saveUserData(userId);
    console.log(`用戶 ${userId} 新增每月事項: ${parsed.content}`);
  } catch (err) {
    console.error('新增每月事項時儲存失敗:', err);
    return '❌ 新增失敗，請稍後再試';
  }
  
  let message = `✅ 已新增每月固定事項：「${parsed.content}」\n`;
  
  if (parsed.hasDate) {
    message += `📅 每月 ${parsed.day} 號執行\n`;
  } else {
    message += `📅 每月需要手動生成\n`;
  }
  
  message += `🔄 輸入「生成本月」可將此事項加入本月代辦清單`;
  message += `\n目前共有 ${userData[userId].monthlyTodos.length} 項每月固定事項`;
  
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
    await saveUserData(userId);
    console.log(`用戶 ${userId} 刪除事項: ${deletedTodo.content}, 剩餘: ${todos.length}`);
  } catch (err) {
    console.error('刪除事項時儲存失敗:', err);
    // 如果儲存失敗，恢復刪除的項目
    todos.splice(index, 0, deletedTodo);
    return '❌ 刪除失敗，請稍後再試';
  }
  
  return `🗑️ 已刪除代辦事項：「${deletedTodo.content}」\n剩餘 ${todos.length} 項代辦事項`;
}

// 刪除每月固定事項
async function deleteMonthlyTodo(userId, index) {
  const monthlyTodos = userData[userId].monthlyTodos;
  
  if (index < 0 || index >= monthlyTodos.length) {
    return `❌ 編號不正確，請輸入 1 到 ${monthlyTodos.length} 之間的數字`;
  }
  
  const deletedTodo = monthlyTodos.splice(index, 1)[0];
  
  try {
    await saveUserData(userId);
    console.log(`用戶 ${userId} 刪除每月事項: ${deletedTodo.content}`);
  } catch (err) {
    console.error('刪除每月事項時儲存失敗:', err);
    monthlyTodos.splice(index, 0, deletedTodo);
    return '❌ 刪除失敗，請稍後再試';
  }
  
  return `🗑️ 已刪除每月固定事項：「${deletedTodo.content}」\n剩餘 ${monthlyTodos.length} 項每月固定事項`;
}

// 獲取代辦事項清單
function getTodoList(userId) {
  const todos = userData[userId].todos;
  
  console.log(`用戶 ${userId} 查詢清單，總數: ${todos.length}`);
  
  if (todos.length === 0) {
    return '📝 目前沒有代辦事項\n輸入「新增 [事項]」來新增代辦事項\n也可以輸入「新增 8/9號繳卡費」來新增有日期的事項\n或輸入「每月新增 5號繳卡費」來新增每月固定事項\n或輸入「5分鐘後倒垃圾」來設定短期提醒\n或輸入「12:00倒垃圾」來設定時間提醒';
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
      const fromMonthlyText = todo.fromMonthly ? ' 🔄' : '';
      
      message += `${index}. ${todo.content}${fromMonthlyText}\n   ${statusIcon} ${targetDate} ${statusText}\n\n`;
      index++;
    });
  }
  
  if (regularTodos.length > 0) {
    message += '🔄 每日提醒事項：\n';
    regularTodos.forEach((todo) => {
      const date = todo.createdAt.includes('/') ? todo.createdAt.split(' ')[0] : new Date(todo.createdAt).toLocaleDateString('zh-TW');
      const fromMonthlyText = todo.fromMonthly ? ' 🔄' : '';
      message += `${index}. ${todo.content}${fromMonthlyText}\n   📅 建立於 ${date}\n\n`;
      index++;
    });
  }
  
  message += '💡 輸入「刪除 [編號]」可刪除指定項目\n💡 輸入「每月清單」查看每月固定事項\n💡 輸入「短期清單」查看短期提醒\n💡 輸入「時間清單」查看時間提醒';
  return message;
}

// 獲取每月固定事項清單
function getMonthlyTodoList(userId) {
  const monthlyTodos = userData[userId].monthlyTodos;
  
  if (monthlyTodos.length === 0) {
    return '📝 目前沒有每月固定事項\n輸入「每月新增 [事項]」來新增每月固定事項\n例如：每月新增 5號繳卡費';
  }
  
  let message = `🔄 每月固定事項清單 (${monthlyTodos.length} 項)：\n\n`;
  
  monthlyTodos.forEach((todo, index) => {
    const statusIcon = todo.enabled ? '✅' : '⏸️';
    const dateText = todo.hasFixedDate ? `每月 ${todo.day} 號` : '手動生成';
    message += `${index + 1}. ${statusIcon} ${todo.content}\n   📅 ${dateText}\n\n`;
  });
  
  message += '💡 輸入「每月刪除 [編號]」可刪除指定項目\n';
  message += '🔄 輸入「生成本月」可將固定事項加入本月代辦';
  
  return message;
}

// 生成本月的固定事項
async function generateMonthlyTodos(userId) {
  const monthlyTodos = userData[userId].monthlyTodos.filter(todo => todo.enabled);
  const currentMonth = getTaiwanDate().getMonth() + 1;
  const currentYear = getTaiwanDate().getFullYear();
  
  if (monthlyTodos.length === 0) {
    return '📝 沒有啟用的每月固定事項\n請先使用「每月新增」來新增固定事項';
  }
  
  let generatedCount = 0;
  let message = `🔄 生成 ${currentYear}/${currentMonth} 月的固定事項：\n\n`;
  
  for (const monthlyTodo of monthlyTodos) {
    let todoItem;
    
    if (monthlyTodo.hasFixedDate) {
      const targetDate = new Date(currentYear, currentMonth - 1, monthlyTodo.day);
      
      const exists = userData[userId].todos.some(todo => {
        if (!todo.hasDate) return false;
        const todoDate = new Date(todo.targetDate);
        return todoDate.getFullYear() === currentYear &&
               todoDate.getMonth() === currentMonth - 1 &&
               todoDate.getDate() === monthlyTodo.day &&
               todo.content === monthlyTodo.content;
      });
      
      if (!exists) {
        todoItem = {
          id: Date.now() + Math.random(),
          content: monthlyTodo.content,
          createdAt: getTaiwanTime(),
          completed: false,
          hasDate: true,
          targetDate: targetDate.toISOString(),
          dateString: `${currentMonth}/${monthlyTodo.day}`,
          fromMonthly: true
        };
        
        userData[userId].todos.push(todoItem);
        message += `✅ ${monthlyTodo.content} (${currentMonth}/${monthlyTodo.day})\n`;
        generatedCount++;
      } else {
        message += `⚠️ ${monthlyTodo.content} (${currentMonth}/${monthlyTodo.day}) 已存在\n`;
      }
    } else {
      todoItem = {
        id: Date.now() + Math.random(),
        content: monthlyTodo.content,
        createdAt: getTaiwanTime(),
        completed: false,
        hasDate: false,
        targetDate: null,
        dateString: null,
        fromMonthly: true
      };
      
      userData[userId].todos.push(todoItem);
      message += `✅ ${monthlyTodo.content} (每日提醒)\n`;
      generatedCount++;
    }
  }
  
  if (generatedCount > 0) {
    try {
      await saveUserData(userId);
      message += `\n🎉 成功生成 ${generatedCount} 項代辦事項！`;
      message += `\n📋 輸入「查詢」可查看完整代辦清單`;
    } catch (err) {
      console.error('生成每月事項時儲存失敗:', err);
      return '❌ 生成失敗，請稍後再試';
    }
  } else {
    message += '\n📝 沒有新增任何事項（可能都已存在）';
  }
  
  return message;
}

// 自動生成每月事項的函數（不發送訊息給用戶）
async function generateMonthlyTodosAuto(userId) {
  const monthlyTodos = userData[userId].monthlyTodos?.filter(todo => todo.enabled) || [];
  const currentMonth = getTaiwanDate().getMonth() + 1;
  const currentYear = getTaiwanDate().getFullYear();
  
  if (monthlyTodos.length === 0) {
    return { generatedCount: 0, message: '沒有啟用的每月固定事項' };
  }
  
  let generatedCount = 0;
  
  for (const monthlyTodo of monthlyTodos) {
    let todoItem;
    
    if (monthlyTodo.hasFixedDate) {
      const targetDate = new Date(currentYear, currentMonth - 1, monthlyTodo.day);
      
      // 檢查是否已存在相同的事項
      const exists = userData[userId].todos.some(todo => {
        if (!todo.hasDate) return false;
        const todoDate = new Date(todo.targetDate);
        return todoDate.getFullYear() === currentYear &&
               todoDate.getMonth() === currentMonth - 1 &&
               todoDate.getDate() === monthlyTodo.day &&
               todo.content === monthlyTodo.content;
      });
      
      if (!exists) {
        todoItem = {
          id: Date.now() + Math.random(),
          content: monthlyTodo.content,
          createdAt: getTaiwanTime(),
          completed: false,
          hasDate: true,
          targetDate: targetDate.toISOString(),
          dateString: `${currentMonth}/${monthlyTodo.day}`,
          fromMonthly: true,
          autoGenerated: true // 標記為自動生成
        };
        
        userData[userId].todos.push(todoItem);
        generatedCount++;
      }
    } else {
      // 檢查是否已存在相同的無日期事項
      const exists = userData[userId].todos.some(todo => 
        !todo.hasDate && 
        todo.content === monthlyTodo.content && 
        todo.fromMonthly
      );
      
      if (!exists) {
        todoItem = {
          id: Date.now() + Math.random(),
          content: monthlyTodo.content,
          createdAt: getTaiwanTime(),
          completed: false,
          hasDate: false,
          targetDate: null,
          dateString: null,
          fromMonthly: true,
          autoGenerated: true // 標記為自動生成
        };
        
        userData[userId].todos.push(todoItem);
        generatedCount++;
      }
    }
  }
  
  if (generatedCount > 0) {
    try {
      await saveUserData(userId);
    } catch (err) {
      console.error('自動生成每月事項時儲存失敗:', err);
      throw err;
    }
  }
  
  return { 
    generatedCount: generatedCount,
    message: generatedCount > 0 ? 
      `成功自動生成 ${generatedCount} 項代辦事項` : 
      '沒有新增任何事項（可能都已存在）'
  };
}

// 設定早上提醒時間
async function setMorningTime(userId, time) {
  const timeRegex = /^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$/;
  
  if (!timeRegex.test(time)) {
    return '❌ 時間格式不正確\n請使用 HH:MM 格式，例如：08:30';
  }
  
  userData[userId].morningReminderTime = time;
  
  try {
    await saveUserData(userId);
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
    await saveUserData(userId);
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

// 測試提醒功能
async function testReminder(userId) {
  console.log(`🧪 用戶 ${userId} 測試提醒功能`);
  
  // 發送測試提醒
  await sendReminderToUser(userId, 'morning');
  
  return `🧪 測試提醒已發送！\n如果沒有收到提醒，可能是因為：\n• 沒有可提醒的代辦事項\n• LINE 推播訊息延遲\n\n輸入「狀態」可查看系統詳情`;
}

// 測試特定時間提醒
async function testTimeReminder(userId, time) {
  const timeRegex = /^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$/;
  
  if (!timeRegex.test(time)) {
    return '❌ 時間格式不正確\n請使用 HH:MM 格式，例如：14:30';
  }
  
  const currentTime = getTaiwanTimeHHMM();
  console.log(`🧪 用戶 ${userId} 測試時間 ${time} 提醒，目前時間 ${currentTime}`);
  
  if (time === currentTime) {
    await sendReminderToUser(userId, 'morning');
    return `🎯 時間匹配！測試提醒已發送 (${time})`;
  } else {
    return `⏰ 測試時間：${time}\n目前時間：${currentTime}\n時間不匹配，未發送提醒\n\n💡 提示：您可以等到 ${time} 時自動收到提醒，或輸入「測試提醒」立即測試`;
  }
}

// 系統狀態檢查
function getSystemStatus(userId) {
  const user = userData[userId];
  const todos = user.todos;
  const monthlyTodos = user.monthlyTodos || [];
  const shortTermReminders = user.shortTermReminders || [];
  const timeReminders = user.timeReminders || [];
  const activeTodos = todos.filter(todo => !isTodoExpired(todo) || !todo.hasDate);
  const expiredTodos = todos.filter(todo => isTodoExpired(todo));
  const remindableTodos = todos.filter(shouldRemindTodo);
  
  // 短期提醒和時間提醒統計
  const currentTime = new Date();
  const activeShortReminders = shortTermReminders.filter(reminder => 
    new Date(reminder.reminderTime) > currentTime
  );
  const expiredShortReminders = shortTermReminders.filter(reminder => 
    new Date(reminder.reminderTime) <= currentTime
  );
  const activeTimeReminders = timeReminders.filter(reminder => 
    new Date(reminder.reminderTime) > currentTime
  );
  const expiredTimeReminders = timeReminders.filter(reminder => 
    new Date(reminder.reminderTime) <= currentTime
  );
  
  return `🔧 系統狀態：
📊 資料統計：
- 總代辦事項：${todos.length} 項
- 每月固定事項：${monthlyTodos.length} 項
- 短期提醒：${shortTermReminders.length} 項
- 時間提醒：${timeReminders.length} 項
- 活躍代辦：${activeTodos.length} 項
- 過期代辦：${expiredTodos.length} 項
- 活躍短期提醒：${activeShortReminders.length} 項
- 過期短期提醒：${expiredShortReminders.length} 項
- 活躍時間提醒：${activeTimeReminders.length} 項
- 過期時間提醒：${expiredTimeReminders.length} 項
- 今日可提醒：${remindableTodos.length} 項

⏰ 提醒設定：
- 早上：${user.morningReminderTime}
- 晚上：${user.eveningReminderTime}

🕐 目前時間：${getTaiwanTimeHHMM()} (台灣)
💾 資料載入：${isDataLoaded ? '✅' : '❌'}
🗄️ 資料庫連線：${db ? '✅' : '❌'}
🗂️ 記憶體中提醒：${shortTermReminders.size} 項

💾 資料安全：使用 MongoDB 雲端資料庫

如有問題請聯繫管理員`;
}

// 設定定時任務 - 每分鐘檢查一次
cron.schedule('* * * * *', async () => {
  try {
    const currentTime = getTaiwanTimeHHMM();
    const currentDate = getTaiwanTime();
    const taiwanDate = getTaiwanDate();
    
    // 每5分鐘顯示一次詳細狀態（避免日誌太多）
    const minute = new Date().getMinutes();
    const showDetailedLog = minute % 5 === 0;
    
    if (showDetailedLog) {
      console.log(`📅 定時檢查 - ${currentDate} (${currentTime})`);
      console.log(`📊 系統狀態 - 資料載入:${isDataLoaded}, 資料庫:${db ? '已連接' : '未連接'}, 用戶數:${Object.keys(userData).length}`);
    }
    
    if (!isDataLoaded || !db) {
      if (showDetailedLog) {
        console.log('⚠️ 系統尚未就緒，跳過提醒檢查');
      }
      return;
    }
    
    if (Object.keys(userData).length === 0) {
      if (showDetailedLog) {
        console.log('📝 沒有用戶資料，跳過提醒檢查');
      }
      return;
    }
    
    // 每月自動生成檢查（每天上午9:00執行一次）
    if (currentTime === '09:00') {
      const currentDay = taiwanDate.getDate();
      
      // 檢查是否為每月1號
      if (currentDay === 1) {
        console.log('🔄 每月1號，開始自動生成所有用戶的每月固定事項...');
        
        let totalGenerated = 0;
        
        for (const userId in userData) {
          try {
            const result = await generateMonthlyTodosAuto(userId);
            if (result.generatedCount > 0) {
              totalGenerated += result.generatedCount;
              console.log(`✅ 用戶 ${userId} 自動生成 ${result.generatedCount} 項每月事項`);
            }
          } catch (error) {
            console.error(`❌ 用戶 ${userId} 自動生成每月事項失敗:`, error);
          }
        }
        
        if (totalGenerated > 0) {
          console.log(`🎉 每月自動生成完成！總共生成 ${totalGenerated} 項事項`);
        } else {
          console.log('📝 本月沒有需要生成的每月固定事項');
        }
      }
    }
    
    // 檢查是否有用戶需要在這個時間提醒
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

// 啟動伺服器
app.listen(PORT, async () => {
  console.log(`LINE Bot 伺服器運行於 port ${PORT}`);
  
  // 先連接資料庫
  const dbConnected = await connectDatabase();
  if (!dbConnected) {
    console.error('❌ 無法連接資料庫，伺服器將以離線模式運行');
  }
  
  // 載入資料
  await loadData();
  console.log('✅ 系統初始化完成');
});

// 健康檢查端點
app.get('/health', (req, res) => {
  const totalShortReminders = Object.values(userData).reduce(
    (sum, user) => sum + (user.shortTermReminders?.length || 0), 0
  );
  const totalTimeReminders = Object.values(userData).reduce(
    (sum, user) => sum + (user.timeReminders?.length || 0), 0
  );
  
  res.json({ 
    status: 'ok', 
    timestamp: new Date().toISOString(),
    taiwanTime: getTaiwanTime(),
    database: db ? 'connected' : 'disconnected',
    users: Object.keys(userData).length,
    totalTodos: Object.values(userData).reduce((sum, user) => sum + (user.todos?.length || 0), 0),
    totalMonthlyTodos: Object.values(userData).reduce((sum, user) => sum + (user.monthlyTodos?.length || 0), 0),
    totalShortTermReminders: totalShortReminders,
    totalTimeReminders: totalTimeReminders,
    activeReminders: shortTermReminders.size,
    uptime: process.uptime(),
    memoryUsage: process.memoryUsage()
  });
});

// Ping 端點
app.get('/ping', (req, res) => {
  res.json({ 
    pong: true, 
    timestamp: new Date().toISOString(),
    taiwanTime: getTaiwanTime(),
    uptime: process.uptime(),
    database: db ? 'connected' : 'disconnected'
  });
});

// 喚醒端點
app.get('/wake', (req, res) => {
  console.log('🌅 收到喚醒請求');
  res.json({ 
    message: '機器人已喚醒',
    timestamp: new Date().toISOString(),
    taiwanTime: getTaiwanTime(),
    isDataLoaded: isDataLoaded,
    databaseConnected: !!db,
    activeTimers: shortTermReminders.size,
    uptime: process.uptime(),
    users: Object.keys(userData).length
  });
});

// 資料庫狀態檢查端點
app.get('/db-status', async (req, res) => {
  try {
    if (!db) {
      return res.json({
        status: 'disconnected',
        message: '資料庫未連接'
      });
    }
    
    // 測試資料庫連線
    await db.admin().ping();
    
    res.json({
      status: 'connected',
      message: '資料庫連接正常',
      users: Object.keys(userData).length
    });
  } catch (error) {
    res.json({
      status: 'error',
      message: error.message
    });
  }
});

// Keep-Alive 機制
const KEEP_ALIVE_URL = process.env.KEEP_ALIVE_URL || `http://localhost:${PORT}/health`;

if (process.env.NODE_ENV !== 'development' && process.env.NODE_ENV !== 'dev') {
  console.log('🔄 啟用 Keep-Alive 機制，每10分鐘自動喚醒');
  
  setInterval(async () => {
    try {
      const response = await fetch(KEEP_ALIVE_URL);
      const uptime = Math.floor(process.uptime() / 60);
      const dbStatus = db ? '✅' : '❌';
      console.log(`🟢 Keep-Alive: ${new Date().toLocaleString('zh-TW', {timeZone: 'Asia/Taipei'})} - Status: ${response.status} - 運行: ${uptime}分鐘 - DB: ${dbStatus}`);
    } catch (error) {
      console.log(`🔴 Keep-Alive 失敗: ${error.message}`);
    }
  }, 10 * 60 * 1000); // 10分鐘
}

// 記憶體清理
setInterval(() => {
  const oldSize = processedMessages.size;
  processedMessages.clear();
  
  const currentTime = new Date();
  let cleanedCount = 0;
  
  for (const [id, data] of shortTermReminders.entries()) {
    const reminderTime = new Date(data.reminderTime);
    if (reminderTime < currentTime - 1800000) { // 30分鐘
      if (data.timerId) {
        clearTimeout(data.timerId);
      }
      shortTermReminders.delete(id);
      cleanedCount++;
    }
  }
  
  const memUsage = process.memoryUsage();
  const memUsageMB = Math.round(memUsage.heapUsed / 1024 / 1024 * 100) / 100;
  const dbStatus = db ? '✅' : '❌';
  
// 程序退出時的清理
process.on('SIGTERM', async () => {
  console.log('收到 SIGTERM，正在清理資源...');
  
  for (const [id, data] of shortTermReminders.entries()) {
    if (data.timerId) {
      clearTimeout(data.timerId);
    }
  }
  shortTermReminders.clear();
  
  if (mongoClient) {
    await mongoClient.close();
    console.log('✅ 資料庫連線已關閉');
  }
  
  console.log('✅ 資源清理完成');
  process.exit(0);
});

process.on('SIGINT', async () => {
  console.log('收到 SIGINT (Ctrl+C)，正在清理資源...');
  
  for (const [id, data] of shortTermReminders.entries()) {
    if (data.timerId) {
      clearTimeout(data.timerId);
    }
  }
  shortTermReminders.clear();
  
  if (mongoClient) {
    await mongoClient.close();
    console.log('✅ 資料庫連線已關閉');
  }
  
  console.log('✅ 資源清理完成');
  process.exit(0);
});

console.log('🚀 LINE Bot 系統已啟動');
console.log('💾 MongoDB 資料庫整合完成');
console.log('🕐 時間提醒功能已就緒');
console.log('💡 輸入「12:00倒垃圾」設定時間提醒');
console.log('📊 輸入「狀態」查看系統資訊');
console.log('🐛 輸入「調試提醒」進行詳細調試');
