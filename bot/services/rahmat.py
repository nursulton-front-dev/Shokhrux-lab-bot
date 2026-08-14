# Rahmat Pay Integration Stub
import uuid

async def generate_invoice_link(amount: int, user_id: int, tariff_months: int) -> str:
    """
    Generates a mock payment link for Rahmat Pay.
    In the real integration, you would call Rahmat Pay API here.
    """
    invoice_id = str(uuid.uuid4())[:8]
    # For now, return a dummy URL that might act as an invoice
    return f"https://pay.rahmat.uz/mock?amount={amount}&uid={user_id}&inv={invoice_id}"
