import logging
import json
import pytz
from datetime import datetime
from bot_instance import bot
from database import db_manager

logger = logging.getLogger(__name__)

async def send_morning_digest():
    """Отправляет утренний дайджест всем администраторам."""
    dnd_enabled = await db_manager.get_setting("dnd_enabled", "0")
    if dnd_enabled != "1":
        return

    admins = await db_manager.get_admins()
    if not admins:
        return

    snapshot_str = await db_manager.get_latest_snapshot()
    if not snapshot_str:
        return

    try:
        data = json.loads(snapshot_str)
        if not data:
            return
            
        message_lines = [
            "🌅 <b>Доброе утро! Тихий час окончен.</b>\nЗа ночь мы собрали для вас актуальные цены:\n"
        ]
        
        # Группируем по категории -> сроку
        from collections import defaultdict
        grouped = defaultdict(lambda: defaultdict(list))
        for item in data:
            grouped[item["ai_category"]][item["duration"]].append(item)
            
        for category, durations in grouped.items():
            message_lines.append(f"🤖 <b>{category}</b>")
            for duration, items in durations.items():
                message_lines.append(f"  ⏳ <i>{duration}</i>")
                # Берём только лучшую цену
                best_item = min(items, key=lambda x: x["price_usd"])
                drop_text = f" 📉 (Упало на {best_item['price_drop']} $)" if best_item.get('price_drop', 0) > 0 else ""
                message_lines.append(f"      💰 {best_item['price_rub']} ₽ (~{best_item['price_usd']} $) на {best_item['platform']}{drop_text}")
            message_lines.append("")
            
        text = "\n".join(message_lines)
        # Ограничиваем длину сообщения
        if len(text) > 4000:
            text = text[:4000] + "...\n(показана только часть данных)"
            
        for admin_id in admins:
            try:
                await bot.send_message(
                    chat_id=admin_id,
                    text=text,
                    parse_mode="HTML",
                    disable_web_page_preview=True
                )
            except Exception as e:
                logger.error(f"Не удалось отправить дайджест админу {admin_id}: {e}")
                
    except Exception as e:
        logger.error(f"Ошибка при формировании утреннего дайджеста: {e}", exc_info=True)


async def update_digest_job():
    """Обновляет задачу утреннего дайджеста в планировщике."""
    from scheduler_instance import scheduler
    
    dnd_enabled = await db_manager.get_setting("dnd_enabled", "0")
    dnd_end = await db_manager.get_setting("dnd_end", "08:00")
    
    job_id = "morning_digest_job"
    
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
        
    if dnd_enabled == "1":
        try:
            hour, minute = map(int, dnd_end.split(":"))
            scheduler.add_job(
                send_morning_digest,
                "cron",
                hour=hour,
                minute=minute,
                id=job_id
            )
            logger.info(f"Задача утреннего дайджеста запланирована на {hour:02d}:{minute:02d} (Europe/Berlin)")
        except ValueError:
            logger.error(f"Некорректный формат времени dnd_end: {dnd_end}")
