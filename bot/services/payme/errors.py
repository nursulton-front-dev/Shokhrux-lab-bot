"""Payme JSON-RPC error codes and their localized messages.

Payme requires every error message to be an object keyed by locale, so the
merchant cabinet can render the failure to the payer in their own language.
"""
from typing import Any

# Transport-level codes (JSON-RPC 2.0 plus Payme's authentication code).
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INSUFFICIENT_PRIVILEGE = -32504

# Business-level codes defined by the Merchant API.
WRONG_AMOUNT = -31001
TRANSACTION_NOT_FOUND = -31003
CANNOT_CANCEL_PERFORMED = -31007
UNABLE_TO_PERFORM = -31008
# Payme reserves -31050..-31099 for `account` field errors; -31050 is the
# conventional "unknown order" code and carries the field name in `data`.
ORDER_NOT_FOUND = -31050

ACCOUNT_FIELD = "order_id"


class PaymeError(Exception):
    """A failure that must be reported to Payme as a JSON-RPC error object."""

    def __init__(self, code: int, message: dict[str, str], data: str | None = None) -> None:
        super().__init__(message.get("en", str(code)))
        self.code = code
        self.message = message
        self.data = data

    def as_error_object(self) -> dict[str, Any]:
        error: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.data is not None:
            error["data"] = self.data
        return error


def _message(ru: str, uz: str, en: str) -> dict[str, str]:
    return {"ru": ru, "uz": uz, "en": en}


def parse_error() -> PaymeError:
    return PaymeError(PARSE_ERROR, _message(
        "Ошибка разбора JSON", "JSON tahlil qilishda xatolik", "JSON parse error"))


def invalid_request() -> PaymeError:
    return PaymeError(INVALID_REQUEST, _message(
        "Некорректный запрос", "Noto'g'ri so'rov", "Invalid request"))


def method_not_found(method: object) -> PaymeError:
    return PaymeError(METHOD_NOT_FOUND, _message(
        "Метод не найден", "Metod topilmadi", "Method not found"), data=str(method))


def invalid_params(field: str | None = None) -> PaymeError:
    return PaymeError(INVALID_PARAMS, _message(
        "Некорректные параметры", "Noto'g'ri parametrlar", "Invalid params"), data=field)


def insufficient_privilege() -> PaymeError:
    return PaymeError(INSUFFICIENT_PRIVILEGE, _message(
        "Недостаточно привилегий для выполнения метода",
        "Metodni bajarish uchun huquqlar yetarli emas",
        "Insufficient privilege to perform this method"))


def order_not_found() -> PaymeError:
    return PaymeError(ORDER_NOT_FOUND, _message(
        "Заказ не найден", "Buyurtma topilmadi", "Order not found"), data=ACCOUNT_FIELD)


def wrong_amount() -> PaymeError:
    return PaymeError(WRONG_AMOUNT, _message(
        "Неверная сумма", "Noto'g'ri summa", "Wrong amount"))


def transaction_not_found() -> PaymeError:
    return PaymeError(TRANSACTION_NOT_FOUND, _message(
        "Транзакция не найдена", "Tranzaksiya topilmadi", "Transaction not found"))


def unable_to_perform(detail: str | None = None) -> PaymeError:
    return PaymeError(UNABLE_TO_PERFORM, _message(
        "Невозможно выполнить операцию", "Operatsiyani bajarib bo'lmaydi",
        "Unable to perform operation"), data=detail)


def cannot_cancel_performed() -> PaymeError:
    return PaymeError(CANNOT_CANCEL_PERFORMED, _message(
        "Заказ выполнен. Отмена невозможна",
        "Buyurtma bajarilgan. Bekor qilib bo'lmaydi",
        "Order has been delivered. Cancellation is not possible"))
