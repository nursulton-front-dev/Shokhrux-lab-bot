"""Optional Click tutorial asset; relative paths always use the project root."""
import asyncio
import logging
from pathlib import Path

from aiogram.types import FSInputFile
from bot.config import config

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[2]


async def tutorial_video() -> str | FSInputFile | None:
    if config.click_tutorial_video_id:
        return config.click_tutorial_video_id
    if not config.click_tutorial_video_path:
        return None
    path = Path(config.click_tutorial_video_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    def usable():
        try:
            return path.is_file() and 0 < path.stat().st_size < 50 * 1024 * 1024
        except OSError:
            return False
    if not await asyncio.to_thread(usable):
        logger.info('Click tutorial not available at %s; using text instructions', path)
        return None
    return FSInputFile(path)
