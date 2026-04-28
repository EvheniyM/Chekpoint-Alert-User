import os
from dotenv import load_dotenv

load_dotenv()

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
ALERT_CHAT_ID = os.getenv('ALERT_CHAT_ID')
ALLOWED_CHAT_ID = os.getenv('ALERT_CHAT_ID')

# Active Directory
AD_SERVER = os.getenv('AD_SERVER')
AD_USER = os.getenv('AD_USER')
AD_PASSWORD = os.getenv('AD_PASSWORD')
AD_BASE_DN = os.getenv('AD_BASE_DN')
MONITOR_GROUP_DN = os.getenv('MONITOR_GROUP_DN')

# VPN CheckPoint
VPN_SERVER = os.getenv('VPN_SERVER')
VPN_USERNAME = os.getenv('VPN_USERNAME')
VPN_PASSWORD = os.getenv('VPN_PASSWORD')

# Настройки
MAX_DAYS_WITHOUT_VPN = int(os.getenv('MAX_DAYS_WITHOUT_VPN', '2'))
CHECK_HOURS = [10, 17]

# Проверка обязательных переменных
required_vars = [
    'TELEGRAM_BOT_TOKEN', 'ALERT_CHAT_ID',
    'AD_SERVER', 'AD_USER', 'AD_PASSWORD', 'AD_BASE_DN', 'MONITOR_GROUP_DN',
    'VPN_SERVER', 'VPN_USERNAME', 'VPN_PASSWORD'
]

missing_vars = [var for var in required_vars if not os.getenv(var)]
if missing_vars:
    raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")
