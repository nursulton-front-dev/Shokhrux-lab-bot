from aiogram.fsm.state import State, StatesGroup

class SupportState(StatesGroup):
    waiting_for_ticket_text = State()
    in_ticket_session = State()

class AdminTicketState(StatesGroup):
    in_ticket_session = State()
    waiting_for_reply = State()
