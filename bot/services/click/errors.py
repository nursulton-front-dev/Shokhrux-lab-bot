"""Click SHOP API result codes.

Click reports every outcome inside an HTTP 200 body, so `error` carries all the
protocol meaning and the status code carries none. `error_note` is shown to the
payer in the Click app, so it stays short and free of internal detail.
"""

SUCCESS = 0
SIGN_CHECK_FAILED = -1
INCORRECT_AMOUNT = -2
ACTION_NOT_FOUND = -3
ALREADY_PAID = -4
ORDER_NOT_FOUND = -5
TRANSACTION_NOT_FOUND = -6
UPDATE_FAILED = -7
BAD_REQUEST = -8
TRANSACTION_CANCELLED = -9

NOTES: dict[int, str] = {
    SUCCESS: "Success",
    SIGN_CHECK_FAILED: "SIGN CHECK FAILED",
    INCORRECT_AMOUNT: "Incorrect parameter amount",
    ACTION_NOT_FOUND: "Action not found",
    ALREADY_PAID: "Already paid",
    ORDER_NOT_FOUND: "Order does not exist",
    TRANSACTION_NOT_FOUND: "Transaction does not exist",
    UPDATE_FAILED: "Failed to update order",
    BAD_REQUEST: "Error in request from click",
    TRANSACTION_CANCELLED: "Transaction cancelled",
}


class ClickError(Exception):
    """A failure that must be reported to Click as a negative `error` code.

    `note` replaces the generic code text when it helps the payer; `detail` is
    logged only, so an internal reason never reaches the Click app.
    """

    def __init__(self, code: int, detail: str | None = None, note: str | None = None) -> None:
        super().__init__(detail or NOTES.get(code, str(code)))
        self.code = code
        self.note = note or NOTES.get(code, "Unable to perform operation")
        self.detail = detail
