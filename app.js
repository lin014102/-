// 在初始化用戶資料的部分，添加 monthlyTodos 欄位
function initUser(userId) {
  if (!userData[userId]) {
    userData[userId] = {
      todos: [],
      monthlyTodos: [], // 新增：每月固定事項
      morningReminderTime: '09:00',
      eveningReminderTime: '18:00',
      timezone: 'Asia/Taipei'
    };
    console.log(`初始化用戶: ${userId}`);
    saveData();
  }
  
  // 如果是舊用戶沒有 monthlyTodos，則添加
  if (!userData[userId].monthlyTodos) {
    userData[userId].monthlyTodos = [];
    saveData();
  }
}

// 在 handleEvent 函數中添加新的指令處理
async function handleEvent(event) {
  // ... 原有程式碼 ...
  
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
    // ... 其他原有指令 ...
    else {
      replyMessage = '指令不正確，請輸入「幫助」查看使用說明';
    }
    
    // ... 原有回覆程式碼 ...
  } catch (error) {
    // ... 原有錯誤處理 ...
  }
}

// 新增：解析每月事項的日期格式
function parseMonthlyDate(text) {
  // 匹配 "每月5號繳卡費" 或 "繳卡費每月5號" 等格式
  const monthlyPattern = /(?:每月)?(\d{1,2})號(.+)|(.+?)(?:每月)?(\d{1,2})號/;
  const match = text.match(monthlyPattern);
  
  if (match) {
    let day, content;
    
    if (match[1] && match[2]) {
      // 日期在前面：5號繳卡費
      day = parseInt(match[1]);
      content = match[2].trim();
    } else if (match[4] && match[3]) {
      // 日期在後面：繳卡費5號
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

// 新增：添加每月固定事項
async function addMonthlyTodo(userId, todo) {
  if (!todo) {
    return '請輸入要新增的每月固定事項\n格式：每月新增 [事項內容] 或 每月新增 5號繳卡費';
  }
  
  const parsed = parseMonthlyDate(todo);
  
  const monthlyTodoItem = {
    id: Date.now(),
    content: parsed.content,
    day: parsed.day, // 每月的第幾號（如果有的話）
    hasFixedDate: parsed.hasDate,
    createdAt: getTaiwanTime(),
    enabled: true
  };
  
  userData[userId].monthlyTodos.push(monthlyTodoItem);
  
  try {
    await saveData();
    console.log(`用戶 ${userId} 新增每月事項: ${parsed.content}, 總數: ${userData[userId].monthlyTodos.length}`);
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

// 新增：刪除每月固定事項
async function deleteMonthlyTodo(userId, index) {
  const monthlyTodos = userData[userId].monthlyTodos;
  
  if (index < 0 || index >= monthlyTodos.length) {
    return `❌ 編號不正確，請輸入 1 到 ${monthlyTodos.length} 之間的數字`;
  }
  
  const deletedTodo = monthlyTodos.splice(index, 1)[0];
  
  try {
    await saveData();
    console.log(`用戶 ${userId} 刪除每月事項: ${deletedTodo.content}, 剩餘: ${monthlyTodos.length}`);
  } catch (err) {
    console.error('刪除每月事項時儲存失敗:', err);
    monthlyTodos.splice(index, 0, deletedTodo);
    return '❌ 刪除失敗，請稍後再試';
  }
  
  return `🗑️ 已刪除每月固定事項：「${deletedTodo.content}」\n剩餘 ${monthlyTodos.length} 項每月固定事項`;
}

// 新增：獲取每月固定事項清單
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

// 新增：生成本月的固定事項
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
      // 有固定日期的事項
      const targetDate = new Date(currentYear, currentMonth - 1, monthlyTodo.day);
      
      // 檢查這個事項是否已經存在於本月
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
          id: Date.now() + Math.random(), // 避免ID重複
          content: monthlyTodo.content,
          createdAt: getTaiwanTime(),
          completed: false,
          hasDate: true,
          targetDate: targetDate.toISOString(),
          dateString: `${currentMonth}/${monthlyTodo.day}`,
          fromMonthly: true // 標記為從每月事項生成
        };
        
        userData[userId].todos.push(todoItem);
        message += `✅ ${monthlyTodo.content} (${currentMonth}/${monthlyTodo.day})\n`;
        generatedCount++;
      } else {
        message += `⚠️ ${monthlyTodo.content} (${currentMonth}/${monthlyTodo.day}) 已存在\n`;
      }
    } else {
      // 沒有固定日期的事項，直接加入
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
      await saveData();
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

// 修改：更新幫助訊息
function getHelpMessage() {
  return `📋 代辦事項機器人使用說明：

📝 基本功能：
• 新增 [事項] - 新增代辦事項
• 新增 8/9號繳卡費 - 新增有日期的事項
• 刪除 [編號] - 刪除指定代辦事項
• 查詢 或 清單 - 查看所有代辦事項

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
• 每月固定事項：需手動生成到代辦清單

🧪 測試功能：
• 狀態 - 查看系統狀態
• 測試提醒 - 立即測試提醒功能

💡 使用範例：
• 每月新增 5號繳信用卡費
• 每月新增 15號繳房租
• 每月新增 買日用品
• 生成本月

輸入「幫助」可重複查看此說明`;
}

// 新增：自動生成功能（可選）
// 可以在每月1號自動生成當月固定事項
cron.schedule('0 0 1 * *', async () => {
  console.log('🔄 每月自動生成固定事項...');
  
  for (const userId in userData) {
    try {
      const user = userData[userId];
      if (!user.monthlyTodos || user.monthlyTodos.length === 0) continue;
      
      // 自動生成（但不發送通知，只記錄在日誌）
      await generateMonthlyTodosForUser(userId);
      console.log(`✅ 已為用戶 ${userId} 自動生成每月事項`);
    } catch (error) {
      console.error(`❌ 用戶 ${userId} 自動生成失敗:`, error);
    }
  }
});

// 輔助函數：為特定用戶生成每月事項（不返回訊息）
async function generateMonthlyTodosForUser(userId) {
  const monthlyTodos = userData[userId].monthlyTodos.filter(todo => todo.enabled);
  const currentMonth = getTaiwanDate().getMonth() + 1;
  const currentYear = getTaiwanDate().getFullYear();
  
  let generatedCount = 0;
  
  for (const monthlyTodo of monthlyTodos) {
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
        const todoItem = {
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
        generatedCount++;
      }
    }
  }
  
  if (generatedCount > 0) {
    await saveData();
  }
  
  return generatedCount;
}








