"""Inline checkout buttons shared by the tariff screen and renewal reminders.

Kept out of the handler module so the scheduler can build the same row without
importing `bot.handlers.user`, which would close an import cycle.
"""
from aiogram.types import InlineKeyboardButton

from bot.config import config

# Brand names, identical in both interface languages.
PAYME_LABEL = "💳 Payme"
CLICK_LABEL = "💳 Click"


def gateway_buttons(months: int, *, use_cashback: bool) -> list[InlineKeyboardButton]:
    """Quick-checkout buttons for one tariff, skipping unconfigured merchants.

    They reuse the `pay_payme_*` / `pay_click_*` handlers, so the order is minted
    only when the payer actually taps one — a reminder never creates an order.
    """
    suffix = f"{months}_{int(use_cashback)}"
    row: list[InlineKeyboardButton] = []
    if config.payme_enabled:
        row.append(InlineKeyboardButton(text=PAYME_LABEL, callback_data=f"pay_payme_{suffix}"))
    if config.click_enabled:
        row.append(InlineKeyboardButton(text=CLICK_LABEL, callback_data=f"pay_click_{suffix}"))
    return row
