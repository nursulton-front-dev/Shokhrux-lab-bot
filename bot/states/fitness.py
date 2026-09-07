from aiogram.fsm.state import State, StatesGroup

class FitnessStates(StatesGroup):
    waiting_for_profile_goal = State()
    waiting_for_profile_weight = State()
    waiting_for_profile_gender = State()
    waiting_for_profile_height = State()
    waiting_for_profile_photo = State()
    waiting_for_photo = State()
    waiting_for_food_photo = State()
    waiting_for_weight = State()
    in_ai_nutritionist = State()
