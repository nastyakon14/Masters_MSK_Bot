from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import Callable, Literal

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from validators import (
    validate_age,
    validate_contact,
    validate_fio,
    validate_short_text,
    validate_socials,
)

FieldType = Literal["text", "multi", "single", "yesno", "scale"]
Validator = Callable[[str], str | None]

EVENT_TITLES = {
    "class": "класс",
    "casting": "кастинг",
}
PRICES = {
    "class": 2_000,
    "casting": 3_000,
}
DANCE_STYLES = [
    "Hip-Hop",
    "Jazz-Funk",
    "High Heels",
    "Contemporary",
    "House",
    "Dancehall",
    "Vogue",
    "Waacking",
    "Breaking",
    "Commercial",
    "Lady Style",
    "Stretching",
]


@dataclass(frozen=True)
class Field:
    id: str
    title: str
    question: str
    error: str
    type: FieldType = "text"
    validate: Validator | None = None


CLASS_FIELDS = [
    Field(
        id="fio",
        title="ФИО",
        question="Введите ваше <b>ФИО</b> — фамилию и имя, отчество по желанию.\n\n"
        "<i>Например: Иванова Анна Сергеевна</i>",
        error="Нужны <b>фамилия и имя</b>, можно с отчеством. Только буквы, без цифр и смайликов.",
        validate=validate_fio,
    ),
    Field(
        id="contact",
        title="Телефон",
        question="Оставьте <b>номер телефона</b>.\n\n"
        "<i>Например: +7 999 123-45-67</i>",
        error="Пришлите российский номер телефона. Например: <code>+7 999 123-45-67</code>.",
        validate=validate_contact,
    ),
]

CASTING_FIELDS = [
    Field(
        id="fio",
        title="ФИО",
        question="Введите ваше <b>ФИО</b> — фамилию и имя, отчество по желанию.\n\n"
        "<i>Например: Иванова Анна Сергеевна</i>",
        error="Нужны <b>фамилия и имя</b>, можно с отчеством. Только буквы, без цифр и смайликов.",
        validate=validate_fio,
    ),
    Field(
        id="age",
        title="Возраст",
        question="Сколько вам <b>лет</b>? Напишите целое число.\n\n<i>Например: 23</i>",
        error="Возраст — целое число от 10 до 70. Например: <code>23</code>.",
        validate=validate_age,
    ),
    Field(
        id="contact",
        title="Телефон",
        question="Оставьте <b>номер телефона</b>.\n\n"
        "<i>Например: +7 999 123-45-67</i>",
        error="Пришлите российский номер телефона. Например: <code>+7 999 123-45-67</code>.",
        validate=validate_contact,
    ),
    Field(
        id="socials",
        title="Соцсети",
        question="Пришлите ссылки на соцсети: <b>Instagram</b>, <b>Telegram</b> и любые другие — как удобно, в любом формате.",
        error="Напишите ответ текстом.",
        validate=validate_socials,
    ),
    Field(
        id="experience",
        title="Опыт в танцах",
        question="Как давно вы занимаетесь танцами?",
        error="Напишите ответ текстом.",
        validate=lambda text: text.strip() or None,
    ),
    Field(
        id="main_styles",
        title="Основной стиль",
        question="Какой ваш <b>основной</b> стиль танца?\n"
        "Выберите <u>только один</u> или добавьте свой вариант.",
        error="Выберите один основной стиль.",
        type="single",
    ),
    Field(
        id="other_styles",
        title="Другие стили",
        question="В каких ещё стилях танцуете <b>помимо основного</b>?\n"
        "Можно выбрать несколько, добавить свой или отметить «Нет».",
        error="Выберите хотя бы один вариант.",
        type="multi",
    ),
    Field(
        id="team_exp",
        title="Командный опыт",
        question="Есть ли опыт <b>командной работы</b> или участия в проектах?",
        error="Выберите «Да» или «Нет».",
        type="yesno",
    ),
    Field(
        id="events",
        title="Чемпионаты и съёмки",
        question="Участвовали ли в <b>чемпионатах, баттлах, концертах и съёмках</b>?",
        error="Выберите «Да» или «Нет».",
        type="yesno",
    ),
    Field(
        id="knows",
        title="Знакомы с творчеством",
        question="Знакомы ли вы с творчеством <b>Саши Токаревой</b>?",
        error="Выберите «Да» или «Нет».",
        type="yesno",
    ),
    Field(
        id="why",
        title="Почему в команду",
        question="Почему хотите попасть в команду к Саше?",
        error="Напишите ответ текстом.",
        validate=lambda text: validate_short_text(text, min_len=2, max_len=700),
    ),
    Field(
        id="goals",
        title="Цели на год",
        question="Каковы ваши главные цели на ближайший год?\n\n"
        "<i>Например: выступления на чемпионатах, развитие медийности, техника.</i>",
        error="Напишите ответ текстом.",
        validate=lambda text: validate_short_text(text, min_len=2, max_len=700),
    ),
    Field(
        id="time",
        title="Время на тренировки",
        question="Сколько времени вы готовы уделять тренировкам?",
        error="Напишите понятный ответ. Например: <i>2 раза в неделю по 3 часа</i>.",
        validate=lambda text: validate_short_text(text, min_len=4, max_len=300),
    ),
    Field(
        id="money",
        title="Финансовая готовность",
        question="Насколько вы готовы к дополнительным финансовым затратам?\n"
        "Костюмы, взносы на чемпионаты, оплата зала, поездки в другие города.\n\n"
        "<blockquote>Важный вопрос, чтобы избежать недоразумений.</blockquote>\n\n"
        "<b>1</b> — не готов(а) · <b>10</b> — полностью готов(а)",
        error="Выберите оценку от 1 до 10.",
        type="scale",
    ),
]

OTHER_STYLES_EXTRA = ["Нет других стилей"]


def fields_for(event_type: str) -> list[Field]:
    return CASTING_FIELDS if event_type == "casting" else CLASS_FIELDS


def field_by_id(fields: list[Field], field_id: str) -> Field:
    for field in fields:
        if field.id == field_id:
            return field
    raise KeyError(field_id)


def event_title(event_type: str) -> str:
    return EVENT_TITLES.get(event_type, "запись")


def price_for(event_type: str) -> int:
    return PRICES[event_type]


def format_price(amount: int) -> str:
    return f"{amount:,}".replace(",", " ") + " ₽"


def display_value(value: object) -> str:
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return str(value)


def format_answers(event_type: str, answers: dict) -> str:
    lines = []
    for field in fields_for(event_type):
        if field.id not in answers:
            continue
        value = escape(display_value(answers[field.id])).replace("\n", "\n")
        lines.append(f"<b>{escape(field.title)}:</b> {value}")
    return "\n".join(lines)


def answered_fields(event_type: str, answers: dict, current_index: int) -> list[Field]:
    fields = fields_for(event_type)
    result = []
    for index, field in enumerate(fields):
        if index < current_index and field.id in answers:
            result.append(field)
    return result


def style_options(field_id: str, pending: list[str]) -> list[str]:
    base = list(DANCE_STYLES)
    if field_id == "other_styles":
        base = OTHER_STYLES_EXTRA + base
    extras = [item for item in pending if item not in base]
    return base + extras


def nav_rows(show_edit: bool, editing: bool) -> list[list[InlineKeyboardButton]]:
    rows: list[list[InlineKeyboardButton]] = []
    if editing:
        rows.append(
            [InlineKeyboardButton(text="⬅️ К анкете", callback_data="form_edit_back")]
        )
    elif show_edit:
        rows.append(
            [
                InlineKeyboardButton(
                    text="✏️ Изменить предыдущий ответ",
                    callback_data="form_edit",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="Отмена", callback_data="form_cancel")])
    return rows


def question_keyboard(
    field: Field,
    *,
    show_edit: bool,
    editing: bool,
    pending_styles: list[str] | None = None,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if field.type == "yesno":
        rows.append(
            [
                InlineKeyboardButton(text="Да", callback_data="yn:yes"),
                InlineKeyboardButton(text="Нет", callback_data="yn:no"),
            ]
        )
    elif field.type == "scale":
        numbers = [str(i) for i in range(1, 11)]
        rows.append(
            [
                InlineKeyboardButton(text=num, callback_data=f"sc:{num}")
                for num in numbers[:5]
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(text=num, callback_data=f"sc:{num}")
                for num in numbers[5:]
            ]
        )
    elif field.type in {"multi", "single"}:
        selected = set(pending_styles or [])
        options = style_options(field.id, pending_styles or [])
        row: list[InlineKeyboardButton] = []
        for index, option in enumerate(options):
            mark = "✓ " if field.type == "multi" and option in selected else ""
            row.append(
                InlineKeyboardButton(
                    text=f"{mark}{option}",
                    callback_data=f"st:{index}",
                )
            )
            if len(row) == 2:
                rows.append(row)
                row = []
        if row:
            rows.append(row)
        rows.append(
            [InlineKeyboardButton(text="➕ Свой вариант", callback_data="form_custom")]
        )
        if field.type == "multi":
            rows.append(
                [InlineKeyboardButton(text="Готово", callback_data="form_multi_done")]
            )
    rows.extend(nav_rows(show_edit, editing))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def edit_keyboard(fields: list[Field]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=field.title, callback_data=f"ed:{field.id}")]
        for field in fields
    ]
    rows.append([InlineKeyboardButton(text="⬅️ К анкете", callback_data="form_edit_back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def custom_style_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ К выбору стилей", callback_data="form_custom_back")]
        ]
    )


def home_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏠 На главную", callback_data="back_home")]
        ]
    )


def resume_keyboard(event_type: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="▶️ Продолжить",
                    callback_data=f"form_resume:{event_type}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔄 Начать сначала",
                    callback_data=f"form_restart:{event_type}",
                )
            ],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="signup")],
        ]
    )


def already_registered_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="signup")]
        ]
    )


def resume_text(event_type: str, draft: dict) -> str:
    title = event_title(event_type)
    fields = fields_for(event_type)
    if draft.get("status") == "waiting_payment":
        return (
            f"Анкета на <b>{title}</b> уже заполнена, осталась оплата.\n\n"
            "Продолжить с оплаты или заполнить заново?"
        )
    step = min(int(draft.get("current_index") or 0) + 1, len(fields))
    return (
        f"Есть незаконченная анкета на <b>{title}</b>.\n"
        f"Сейчас шаг {step} из {len(fields)}.\n\n"
        "Продолжить с того места, где остановились, или начать сначала?"
    )


def already_registered_text(event_type: str) -> str:
    title = event_title(event_type)
    return (
        f"Вы уже записаны на <b>{title}</b>.\n"
        "Если нужно что-то поменять — напишите Саше @atkrevalexa."
    )


def payment_text(event_type: str, requisites: str) -> str:
    title = event_title(event_type)
    amount = format_price(price_for(event_type))
    return (
        "💳 <b>Оплата записи</b>\n\n"
        f"Формат: <b>{title}</b>\n"
        f"Сумма: <b>{amount}</b>\n\n"
        "<b>Реквизиты для перевода:</b>\n"
        f"{requisites}\n\n"
        "После оплаты <b>пришлите скриншот чека</b> в этот чат.\n\n"
        "<blockquote>Запись будет подтверждена только после оплаты. "
        "Пока скрин не получен, место не бронируем.</blockquote>"
    )


def registered_text(event_type: str, answers: dict) -> str:
    title = event_title(event_type)
    amount = format_price(price_for(event_type))
    fio = escape(str(answers.get("fio", "")))
    extra = ""
    if event_type == "casting":
        extra = (
            "\nНе забудьте подготовить соло <b>до 1,5 минут</b> — "
            "музыка должна быть нарезана заранее.\n"
        )
    return (
        f"✅ <b>Вы записаны на {title}!</b>\n\n"
        f"<b>ФИО:</b> {fio}\n"
        f"<b>Формат:</b> {title}\n"
        f"<b>Сумма:</b> {amount}\n"
        "<b>Когда:</b> 10 октября, 18:00–22:00\n"
        "<b>Где:</b> зал «Графит» 8count · м. Преображенская\n"
        f"{extra}\n"
        "Ждём тебя 10 октября. Если планы изменятся — напишите Саше @atkrevalexa."
    )


def admin_summary(event_type: str, answers: dict, user_line: str) -> str:
    title = event_title(event_type)
    amount = format_price(price_for(event_type))
    return (
        "💰 <b>Скрин оплаты</b>\n\n"
        f"{user_line}\n"
        f"<b>Формат:</b> {title}\n"
        f"<b>Сумма:</b> {amount}\n\n"
        f"{format_answers(event_type, answers)}"
    )
