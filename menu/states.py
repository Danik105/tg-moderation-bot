from aiogram.fsm.state import State, StatesGroup


class PostingFSM(StatesGroup):
    waiting_prompt = State()
    waiting_target = State()
    waiting_source = State()
    waiting_links_label = State()
    waiting_links_url = State()
    waiting_auth_phone = State()
    waiting_auth_code = State()
    waiting_auth_2fa = State()
    waiting_api_id = State()
    waiting_api_hash = State()
    editing_post = State()
