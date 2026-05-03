from aiogram.fsm.state import State, StatesGroup


class ModerationFSM(StatesGroup):
    choosing_chat = State()
    waiting_for_username = State()
    selected_chat = State()
