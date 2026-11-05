"""Наборы допустимых значений. Проверяются на бэкенде и продублированы
списками во фронтенде — держать их в одном месте дешевле, чем искать по роутерам."""

VALID_AVATARS = {
    "fox", "cat", "dog", "owl", "bear", "panda", "penguin", "koala",
    "lion", "tiger", "rabbit", "hamster", "mouse", "frog", "monkey", "chick",
    "unicorn", "dragon", "wolf", "hedgehog", "pig", "cow", "elephant", "octopus",
    "whale", "turtle", "butterfly", "parrot", "deer", "raccoon", "crab", "dolphin",
}

VALID_THEMES = {"dark", "light"}

ATTRIBUTE_KINDS = {"select", "text"}

# Знак количества в движении задаётся видом операции, а не тем, что пришло из формы.
MOVEMENT_SIGNS = {
    "receipt": 1,    # приход от поставщика
    "return": 1,     # возврат от покупателя
    "sale": -1,      # продажа
    "writeoff": -1,  # брак, потеря, подарок, витрина
    "adjust": 0,     # инвентаризация: знак зависит от расхождения
}

MOVEMENT_LABELS = {
    "receipt": "Приход",
    "return": "Возврат",
    "sale": "Продажа",
    "writeoff": "Списание",
    "adjust": "Корректировка",
}

# Операции, которые пользователь заводит руками со страницы товара.
MANUAL_MOVEMENT_KINDS = {"receipt", "writeoff", "adjust"}

PAYMENT_METHODS = {"cash": "Наличные", "card": "Карта", "transfer": "Перевод"}

CURRENCY = "BYN"
