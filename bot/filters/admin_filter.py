from aiogram.filters import BaseFilter
from aiogram.types import Message, CallbackQuery
from database import db_manager
from typing import Union

class IsAdminFilter(BaseFilter):
    async def __call__(self, event: Union[Message, CallbackQuery]) -> bool:
        user_id = event.from_user.id
        # Проверяем, есть ли пользователь в списке админов
        return await db_manager.is_admin(user_id)
