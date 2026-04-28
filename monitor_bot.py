import logging
import asyncio
import subprocess
import os
import re
import glob
from datetime import datetime, timedelta
import pytz
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
import config
from ad_checker import ADChecker
from vpn_checker import VPNChecker
import json

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Часовой пояс Киев
KYIV_TZ = pytz.timezone('Europe/Kyiv')

ALERTS_FILE = '/app/data/sent_alerts.json'
LAST_CHECK_FILE = '/app/data/last_check.json'
LAST_CLEANUP_FILE = '/app/data/last_cleanup.txt'
LOG_PATH = '/app/logs'

def get_now():
    return datetime.now(KYIV_TZ)

def is_allowed_chat(chat_id):

    try:
        allowed = int(config.ALLOWED_CHAT_ID)
        return chat_id == allowed
    except:
        return False

def cleanup_old_logs():
    try:
        if not os.path.exists(LOG_PATH):
            return
        cutoff_date = get_now() - timedelta(days=7)
        deleted_count = 0
        for filename in os.listdir(LOG_PATH):
            filepath = os.path.join(LOG_PATH, filename)
            if os.path.isfile(filepath):
                file_mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
                file_mtime = KYIV_TZ.localize(file_mtime) if not file_mtime.tzinfo else file_mtime
                if file_mtime < cutoff_date:
                    os.remove(filepath)
                    deleted_count += 1
        if deleted_count > 0:
            logger.info(f"Cleaned up {deleted_count} old log files")
    except Exception as e:
        logger.error(f"Error cleaning up logs: {e}")

def load_sent_alerts():
    if os.path.exists(ALERTS_FILE):
        try:
            with open(ALERTS_FILE, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_sent_alerts(alerts):
    os.makedirs(os.path.dirname(ALERTS_FILE), exist_ok=True)
    with open(ALERTS_FILE, 'w') as f:
        json.dump(alerts, f)

def load_last_check():
    if os.path.exists(LAST_CHECK_FILE):
        try:
            with open(LAST_CHECK_FILE, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_last_check(data):
    os.makedirs(os.path.dirname(LAST_CHECK_FILE), exist_ok=True)
    with open(LAST_CHECK_FILE, 'w') as f:
        json.dump(data, f)

def load_last_cleanup():
    if os.path.exists(LAST_CLEANUP_FILE):
        try:
            with open(LAST_CLEANUP_FILE, 'r') as f:
                return datetime.strptime(f.read().strip(), '%Y-%m-%d').date()
        except:
            return None
    return None

def save_last_cleanup():
    os.makedirs(os.path.dirname(LAST_CLEANUP_FILE), exist_ok=True)
    with open(LAST_CLEANUP_FILE, 'w') as f:
        f.write(get_now().strftime('%Y-%m-%d'))

def cleanup_old_alerts():
    try:
        alerts = load_sent_alerts()
        if not alerts:
            return 0
        
        cutoff_date = (get_now() - timedelta(days=7)).date()
        old_count = 0
        new_alerts = {}
        
        for username, alert_date in alerts.items():
            try:
                alert_date_obj = datetime.strptime(alert_date, '%Y-%m-%d').date()
                if alert_date_obj >= cutoff_date:
                    new_alerts[username] = alert_date
                else:
                    old_count += 1
            except:
                pass
        
        if old_count > 0:
            save_sent_alerts(new_alerts)
            logger.info(f"Cleaned up {old_count} old alert records")
        
        return old_count
    except Exception as e:
        logger.error(f"Error cleaning up alerts: {e}")
        return 0

def should_cleanup_alerts():
    last_cleanup = load_last_cleanup()
    if last_cleanup is None:
        return True
    return (get_now().date() - last_cleanup).days >= 7

def is_weekend(date):
    return date.weekday() >= 5

def is_workday(date):
    return date.weekday() < 5

def count_workdays_without_login(last_login_date):
    if not last_login_date:
        return config.MAX_DAYS_WITHOUT_VPN + 1, []
    today = get_now().date()
    if last_login_date == today:
        return 0, []
    current_date = last_login_date + timedelta(days=1)
    days_without = 0
    missing_days = []
    while current_date <= today:
        if not is_weekend(current_date):
            days_without += 1
            missing_days.append(current_date.strftime('%d.%m'))
        current_date += timedelta(days=1)
    return days_without, missing_days

async def fetch_user_logs(username, chat_id, bot, message_id=None):
    try:
        if not is_allowed_chat(chat_id):
            return
        
        if message_id:
            await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=f"📡 Збираю логи для {username}...")
        else:
            status_msg = await bot.send_message(chat_id=chat_id, text=f"📡 Збираю логи для {username}...")
            message_id = status_msg.message_id
        
        fetch_process = subprocess.run(
            ['python', 'fetch_logs.py', username],
            capture_output=True,
            text=True,
            timeout=300
        )
        if fetch_process.returncode != 0:
            await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=f"❌ Помилка при зборі логів для {username}")
            return
        
        log_files = glob.glob(f"/app/logs/vpn_logs_{username}_*.csv")
        if not log_files:
            await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=f"❌ Не знайдено логів для {username}")
            return
        
        parse_process = subprocess.run(
            ['python', 'parse_logs.py', username],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        output_file = f"/app/logs/{username}.csv"
        if os.path.exists(output_file):
            await bot.delete_message(chat_id=chat_id, message_id=message_id)
            with open(output_file, 'rb') as f:
                await bot.send_document(
                    chat_id=chat_id,
                    document=f,
                    filename=f"{username}.csv",
                    caption=f"📊 Звіт по VPN активності для {username}"
                )
            for f in [output_file] + log_files:
                try:
                    if os.path.exists(f):
                        os.remove(f)
                except:
                    pass
        else:
            await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=f"❌ Не вдалося створити звіт для {username}")
    except Exception as e:
        logger.error(f"Error fetching logs for {username}: {e}")
        await bot.send_message(chat_id=chat_id, text=f"❌ Помилка: {str(e)[:200]}")
    cleanup_old_logs()

async def send_alert(bot, user_info, days_without, missing_days):
    last_conn = user_info.get('last_connection')
    last_conn_str = last_conn.strftime('%d.%m.%Y %H:%M') if last_conn else 'Немає даних'
    days_str = ', '.join(missing_days) if missing_days else 'всі дні'
    
    message = f"""🚨 *VPN MONITOR ALERT* 🚨

👤 *Користувач:* {user_info['display_name']}
🔑 *Логін:* {user_info['username']}

⚠️ *Статус:* Не підключався до VPN {days_without} робочих днів

📅 *Дні без підключення:* {days_str}

📅 *Останнє підключення:* {last_conn_str}"""
    
    keyboard = [[InlineKeyboardButton(f"📊 Отримати звіт для {user_info['username']}", callback_data=f"report_{user_info['username']}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await bot.send_message(chat_id=config.ALERT_CHAT_ID, text=message, parse_mode='Markdown', reply_markup=reply_markup)
        logger.info(f"Alert sent for {user_info['username']}")
        return True
    except Exception as e:
        logger.error(f"Failed to send alert: {e}")
        return False

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    # Проверяем, что чат разрешенный
    if not is_allowed_chat(query.message.chat_id):
        await query.message.reply_text("❌ Доступ заборонено. Бот працює тільки у визначеній групі.")
        return
    
    username = query.data.replace("report_", "")
    await fetch_user_logs(username, query.message.chat_id, context.bot, query.message.message_id)

async def check_and_send_alerts(bot, is_scheduled=False):
    logger.info("Starting user check...")
    sent_alerts = load_sent_alerts()
    today_str = get_now().strftime('%Y-%m-%d')
    ad_checker = None
    vpn_checker = None
    try:
        ad_checker = ADChecker()
        users = ad_checker.get_users_from_group()
        logger.info(f"Found {len(users)} users in group")
        if not users:
            logger.info("No users found")
            return
        vpn_checker = VPNChecker(config.VPN_SERVER, config.VPN_USERNAME, config.VPN_PASSWORD)
        if not vpn_checker.login():
            logger.error("Failed to login to VPN API")
            return
        for user in users:
            username = user['username']
            logger.info(f"Checking: {username}")
            last_login = vpn_checker.get_user_last_login(username)
            user['last_connection'] = last_login
            if last_login:
                days_without, missing_days = count_workdays_without_login(last_login.date())
                if days_without >= config.MAX_DAYS_WITHOUT_VPN:
                    last_alert_date = sent_alerts.get(username)
                    if last_alert_date != today_str:
                        logger.info(f"SENDING ALERT for {username}")
                        if await send_alert(bot, user, days_without, missing_days):
                            sent_alerts[username] = today_str
                            save_sent_alerts(sent_alerts)
                    else:
                        logger.info(f"SKIPPING alert for {username} (already sent today)")
                else:
                    if username in sent_alerts:
                        del sent_alerts[username]
                        save_sent_alerts(sent_alerts)
                        logger.info(f"Removed {username} from alert history (connected again)")
            else:
                days_without, missing_days = count_workdays_without_login(None)
                if days_without >= config.MAX_DAYS_WITHOUT_VPN:
                    last_alert_date = sent_alerts.get(username)
                    if last_alert_date != today_str:
                        logger.info(f"SENDING ALERT for {username} (no login data)")
                        if await send_alert(bot, user, days_without, missing_days):
                            sent_alerts[username] = today_str
                            save_sent_alerts(sent_alerts)
        logger.info("Check completed")
    except Exception as e:
        logger.error(f"Error: {e}")
    finally:
        if ad_checker:
            ad_checker.close()
        if vpn_checker:
            vpn_checker.close()
    cleanup_old_logs()

async def scheduled_checker(bot):
    while True:
        now = get_now()
        if is_workday(now):
            if now.hour in config.CHECK_HOURS and now.minute < 5:
                last_check = load_last_check()
                last_check_key = now.strftime('%Y-%m-%d-%H')
                if last_check.get(last_check_key) != now.strftime('%Y-%m-%d %H:00'):
                    logger.info(f"Scheduled check at {now.strftime('%Y-%m-%d %H:%M')} (Kyiv time)")
                    await check_and_send_alerts(bot, is_scheduled=True)
                    last_check[last_check_key] = now.strftime('%Y-%m-%d %H:00')
                    save_last_check(last_check)
        
        if now.hour == 0 and now.minute < 5:
            cleanup_old_logs()
            if should_cleanup_alerts():
                cleanup_old_alerts()
                save_last_cleanup()
        
        await asyncio.sleep(60)

async def handle_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    
    # Проверяем, что сообщение из разрешенного чата
    if not is_allowed_chat(update.message.chat_id):
        return
    
    if update.message.text.startswith('/'):
        return
    
    username = update.message.text.strip().lower()
    if not re.match(r'^[a-z0-9]+\.[a-z0-9]+$', username):
        await update.message.reply_text(
            "❌ Невірний формат. Використовуйте: `name.family`\n"
            "Наприклад: `petr.petrov`",
            parse_mode='Markdown'
        )
        return
    await fetch_user_logs(username, update.message.chat_id, context.bot)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    # Проверяем, что сообщение из разрешенного чата
    if not is_allowed_chat(update.message.chat_id):
        # Не отвечаем в ЛС
        return
    
    await update.message.reply_text(
        "🤖 *VPN Monitor Bot*\n\n"
        "Я відстежую підключення до VPN та надсилаю сповіщення, "
        "якщо користувач не підключався 2 та більше робочих днів.\n\n"
        "📊 *Отримати звіт по користувачу:*\n"
        "Просто надішліть його логін у форматі `name.family`\n\n"
        "📋 *Команди:*\n"
        "/list - показати список користувачів у групі моніторингу\n"
        "/help - допомога\n\n"
        "Наприклад: `petr.petrov`",
        parse_mode='Markdown'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    # Проверяем, что сообщение из разрешенного чата
    if not is_allowed_chat(update.message.chat_id):
        return
    
    await update.message.reply_text(
        "📚 *Довідка*\n\n"
        "🔍 *Отримати звіт:* надішліть логін у форматі `name.family`\n"
        "📋 *Список моніторингу:* `/list`\n"
        "⏰ *Час перевірки:* щодня о 10:00 та 17:00 (Київ, тільки робочі дні)\n"
        "📊 *Звіт містить:* хронологію подій: сесії VPN та timeout\n\n"
        "📋 *Приклад:* `petr.petrov`",
        parse_mode='Markdown'
    )

async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    # Проверяем, что сообщение из разрешенного чата
    if not is_allowed_chat(update.message.chat_id):
        return
    
    await update.message.reply_text("📊 *Отримую список користувачів...*", parse_mode='Markdown')
    
    ad_checker = None
    vpn_checker = None
    
    try:
        ad_checker = ADChecker()
        users = ad_checker.get_users_from_group()
        
        if not users:
            await update.message.reply_text("❌ Не знайдено користувачів у групі моніторингу")
            return
        
        vpn_checker = VPNChecker(config.VPN_SERVER, config.VPN_USERNAME, config.VPN_PASSWORD)
        vpn_checker.login()
        
        message = "📋 *Список користувачів у групі моніторингу:*\n\n"
        
        for user in users:
            username = user['username']
            display_name = user['display_name']
            
            last_login = vpn_checker.get_user_last_login(username)
            
            if last_login:
                days_without, _ = count_workdays_without_login(last_login.date())
                if days_without >= config.MAX_DAYS_WITHOUT_VPN:
                    status_icon = "🔴"
                    status_text = f"не підключався {days_without} днів"
                else:
                    status_icon = "🟢"
                    status_text = f"підключався {last_login.strftime('%d.%m.%Y')}"
            else:
                status_icon = "⚠️"
                status_text = "немає даних про входи"
            
            message += f"{status_icon} *{display_name}*\n"
            message += f"   📌 Логін: `{username}`\n"
            message += f"   📊 Статус: {status_text}\n\n"
        
        message += f"---\n"
        message += f"⏰ *Наступна перевірка:* сьогодні о 10:00 та 17:00\n"
        message += f"📅 *Робочі дні:* Пн-Пт\n"
        message += f"⚙️ *Поріг алерту:* {config.MAX_DAYS_WITHOUT_VPN} дні без підключення"
        
        await update.message.reply_text(message, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Error in list_users: {e}")
        await update.message.reply_text(f"❌ Помилка при отриманні списку: {str(e)[:200]}")
    finally:
        if ad_checker:
            ad_checker.close()
        if vpn_checker:
            vpn_checker.close()

async def main():
    bot = Bot(token=config.TELEGRAM_BOT_TOKEN)
    
    cleanup_old_logs()
    if should_cleanup_alerts():
        cleanup_old_alerts()
        save_last_cleanup()
    
    asyncio.create_task(scheduled_checker(bot))
    
    application = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("list", list_users))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_username))
    application.add_handler(CallbackQueryHandler(button_callback))
    
    await bot.send_message(
        chat_id=config.ALERT_CHAT_ID,
        text="✅ *VPN Monitor Bot запущено!*\n\n"
             "📅 Перевірка виконується щодня о 10:00 та 17:00 (Київ, тільки робочі дні)\n"
             "💡 Надішліть логін користувача, щоб отримати детальний звіт\n"
             "📋 Команда `/list` - показати список користувачів у моніторингу\n" 
             f"🕐 Поточний час сервера (Київ): {get_now().strftime('%Y-%m-%d %H:%M:%S')}",
        parse_mode='Markdown'
    )
    logger.info("VPN Monitor Bot started")
    
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    while True:
        await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())
