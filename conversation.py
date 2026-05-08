from enum import Enum, auto

class State(Enum):
    AWAITING_CITY = auto()
    AWAITING_CHECKIN = auto()
    AWAITING_CHECKOUT = auto()
    AWAITING_BUDGET = auto()
    AWAITING_GUESTS = auto()
    SHOWING_HOTELS = auto()
    AWAITING_BOOKING_NAME = auto()
    AWAITING_BOOKING_PHONE = auto()
    CONFIRM_BOOKING = auto()

user_states = {}
user_temp_data = {}

def set_state(user_id, state: State):
    user_states[user_id] = state

def get_state(user_id):
    return user_states.get(user_id, State.AWAITING_CITY)

def reset_state(user_id):
    user_states[user_id] = State.AWAITING_CITY
    clear_temp_data(user_id)

def get_temp_data(user_id):
    if user_id not in user_temp_data:
        user_temp_data[user_id] = {}
    return user_temp_data[user_id]

def clear_temp_data(user_id):
    user_temp_data[user_id] = {}