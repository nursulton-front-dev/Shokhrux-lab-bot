from aiogram.fsm.state import State, StatesGroup

class AdminBroadcast(StatesGroup):
    waiting_for_audience = State()
    waiting_for_message = State()
    waiting_for_confirm = State()

class AdminUserSearch(StatesGroup):
    waiting_for_query = State()
    managing_user = State()
    waiting_for_extend_days = State()
