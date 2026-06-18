from apscheduler.schedulers.asyncio import AsyncIOScheduler
import pytz

# Инициализируем планировщик с часовым поясом Германии
tz = pytz.timezone('Europe/Berlin')
scheduler = AsyncIOScheduler(timezone=tz)
