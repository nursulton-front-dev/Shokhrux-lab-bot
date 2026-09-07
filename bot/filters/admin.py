from aiogram.filters import BaseFilter
from aiogram.types import Message, CallbackQuery
from bot.config import config

class IsAdmin(BaseFilter):
    async def __call__(self, event: Message | CallbackQuery) -> bool:
        user = event.from_user
        return user is not None and user.id in config.get_admin_ids
