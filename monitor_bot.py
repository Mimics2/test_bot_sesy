import asyncio
import logging
import sqlite3
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telethon import TelegramClient, events
from telethon.sessions import StringSession
import re

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MonitorBot:
    def __init__(self, token: str):
        self.token = token
        self.app = Application.builder().token(token).build()
        self.active_monitors = {}
        self.setup_handlers()

    def setup_handlers(self):
        self.app.add_handler(CommandHandler("start", self.start))
        self.app.add_handler(CommandHandler("add_monitor", self.add_monitor))
        self.app.add_handler(CommandHandler("stop_monitor", self.stop_monitor))
        self.app.add_handler(CommandHandler("list_monitors", self.list_monitors))
        self.app.add_handler(CommandHandler("set_filter", self.set_filter))

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        welcome_text = """
👁️ **Бот мониторинга сообщений**

Доступные команды:
/add_monitor - Добавить сессию для мониторинга
/stop_monitor - Остановить мониторинг
/list_monitors - Список активных мониторингов
/set_filter - Настроить фильтры
        """
        await update.message.reply_text(welcome_text, parse_mode='Markdown')

    async def add_monitor(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        await update.message.reply_text(
            "📱 Отправьте session string для мониторинга:"
        )
        context.user_data['awaiting_session'] = True

    async def set_filter(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        # Получаем список сессий пользователя
        conn = sqlite3.connect('sessions.db')
        cursor = conn.cursor()
        
        sessions = cursor.execute(
            'SELECT session_name FROM user_sessions WHERE user_id = ? AND is_active = 1',
            (user_id,)
        ).fetchall()
        
        if not sessions:
            await update.message.reply_text("❌ У вас нет активных сессий.")
            return
            
        keyboard = []
        for session_name, in sessions:
            keyboard.append([f"filter_{session_name}"])
            
        await update.message.reply_text(
            "Выберите сессию для настройки фильтров:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        conn.close()

    async def start_monitoring(self, user_id: int, session_string: str, session_name: str):
        """Запускает мониторинг для конкретной сессии"""
        try:
            client = TelegramClient(StringSession(session_string), api_id=YOUR_API_ID, api_hash=YOUR_API_HASH)
            await client.start()
            
            @client.on(events.NewMessage)
            async def handler(event):
                if not event.is_private:
                    return
                    
                # Применяем фильтры
                if await self.apply_filters(user_id, session_name, event.message):
                    await self.forward_message(user_id, event.message, session_name)
            
            self.active_monitors[(user_id, session_name)] = client
            logger.info(f"Started monitoring for user {user_id}, session {session_name}")
            
        except Exception as e:
            logger.error(f"Error starting monitor: {e}")
            # Уведомляем пользователя об ошибке
            await self.app.bot.send_message(user_id, f"❌ Ошибка запуска мониторинга: {str(e)}")

    async def apply_filters(self, user_id: int, session_name: str, message):
        """Применяет фильтры к сообщению"""
        conn = sqlite3.connect('sessions.db')
        cursor = conn.cursor()
        
        filters = cursor.execute(
            'SELECT filter_type, filter_value FROM user_filters WHERE user_id = ? AND session_name = ?',
            (user_id, session_name)
        ).fetchall()
        
        conn.close()
        
        if not filters:
            return True  # Если фильтров нет, пропускаем все сообщения
            
        message_text = message.text or ""
        
        for filter_type, filter_value in filters:
            if filter_type == "keyword":
                if filter_value.lower() in message_text.lower():
                    return True
            elif filter_type == "regex":
                if re.search(filter_value, message_text, re.IGNORECASE):
                    return True
            elif filter_type == "sender":
                if str(message.sender_id) == filter_value:
                    return True
                    
        return False

    async def forward_message(self, user_id: int, message, session_name: str):
        """Пересылает отфильтрованное сообщение пользователю"""
        try:
            text = f"📨 **Сообщение из сессии {session_name}**\n\n"
            text += f"От: {message.sender_id}\n"
            text += f"Текст: {message.text}\n"
            text += f"Время: {message.date}"
            
            await self.app.bot.send_message(user_id, text, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Error forwarding message: {e}")

    async def stop_monitor(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        # Останавливаем все мониторы пользователя
        stopped = 0
        for key in list(self.active_monitors.keys()):
            if key[0] == user_id:
                await self.active_monitors[key].disconnect()
                del self.active_monitors[key]
                stopped += 1
                
        await update.message.reply_text(f"✅ Остановлено {stopped} мониторингов.")

    def run(self):
        self.app.run_polling()

# Замените на ваши данные
YOUR_API_ID = 1234567
YOUR_API_HASH = "your_api_hash_here"

if __name__ == "__main__":
    monitor_bot = MonitorBot("YOUR_MONITOR_BOT_TOKEN_HERE")
    monitor_bot.run()
