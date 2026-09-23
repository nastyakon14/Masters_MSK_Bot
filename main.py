import asyncio
import logging
import os
import traceback
from html import escape
from typing import Any, Callable

from aiogram import BaseMiddleware, Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    ErrorEvent,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    TelegramObject,
    User,
)
from dotenv import load_dotenv

from form import (
    Field,
    already_registered_keyboard,
    already_registered_text,
    answered_fields,
    admin_summary,
    custom_style_keyboard,
    edit_keyboard,
    event_title,
    field_by_id,
    fields_for,
    home_keyboard,
    payment_text,
    question_keyboard,
    registered_text,
    resume_keyboard,
    resume_text,
    style_options,
)
from persistence import persist
from validators import validate_contact, validate_custom_style

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ERROR_ADMIN_USER_ID = int(
    os.getenv("ERROR_ADMIN_USER_ID") or os.getenv("ADMIN_USER_ID", "1300450286")
)
PAYMENT_ADMIN_USER_ID = int(
    os.getenv("PAYMENT_ADMIN_USER_ID") or os.getenv("ADMIN_USER_ID", "1300450286")
)
PAYMENT_REQUISITES = os.getenv(
    "PAYMENT_REQUISITES",
    "Карта / СБП: укажите реквизиты в .env (PAYMENT_REQUISITES)\nПолучатель: ",
)

WELCOME_TEXT = (
    "<b>Привет!</b>\n\n"
    "Это бот для записи на <b>кастинг</b> в команду "
    "<b>Masters МСК</b> и на класс к <b>Саше Токаревой</b>.\n\n"
    "<blockquote>Мероприятия пройдут <b>10 октября</b></blockquote>\n\n"
    "<b>Общая информация:</b>\n\n"
    "Ищем таланты в <u>два состава</u>:\n\n"
    "• <b>PRO</b> — если вы уже уверенно чувствуете себя на паркете\n"
    "• <b>BEGINNERS</b> — если горите желанием расти и готовы впитывать базу\n\n"
    "<b>🗓 Когда:</b> 10 октября\n"
    "<b>🕕 Время:</b> с 18:00 до 22:00\n"
    "<b>💃 Класс:</b> 2 000 ₽\n"
    "<b>🎟 Кастинг:</b> 3 000 ₽\n"
    "<b>📍 Место:</b> <tg-spoiler>зал «Графит» 8count · м. Преображенская</tg-spoiler>"
)

INFO_TEXT = (
    "<b>Как будет проходить отбор</b>\n\n"
    "<b>1️⃣ Первый этап — класс</b>\n"
    "Обычный хорео-класс от Саши.\n"
    "Смотрю <i>технику</i>, <i>чистоту линий</i>, <i>музыкальность</i> "
    "и то, как быстро вы схватываете материал.\n\n"
    "<b>2️⃣ Второй этап — соло</b>\n"
    "Только для тех, кто пришёл на сам кастинг.\n\n"
    "• <b>PRO</b> — ваше лучшее соло\n"
    "• <b>BEGINNERS</b> — постановка может быть вашей или другого хореографа\n\n"
    "<blockquote>⏱ <b>Тайминг:</b> строго до 1,5 минут. "
    "Музыка должна быть нарезана заранее!</blockquote>\n\n"
    "Соло нужно подготовить <u>каждому</u>, кто идёт на кастинг.\n\n"
    "<b>📅 Дальнейший график тренировок</b>\n"
    "<i>Старт после утверждения составов</i>\n\n"
    "• <b>PRO:</b> Вт / Чт — 18:00–21:00\n"
    "• <b>BEGINNERS:</b> Вт / Чт — 21:00–23:00\n\n"
    "<b>📍 Место:</b> <tg-spoiler>8count · м. Преображенская</tg-spoiler>"
)

SIGNUP_TEXT = (
    "<b>Выберите, куда вы хотите попасть</b>\n\n"
    "• <b>Кастинг</b> — отбор в команду: класс + соло\n"
    "• <b>Класс</b> — без кастинга в команду, просто потанцевать"
)

bot_instance: Bot | None = None


class FormStates(StatesGroup):
    answering = State()
    adding_custom = State()
    waiting_payment = State()


def welcome_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📋 Подробнее об отборе в команду",
                    callback_data="info",
                )
            ],
            [
                InlineKeyboardButton(
                    text="✍️ Записаться",
                    callback_data="signup",
                )
            ],
        ]
    )


def info_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✍️ Записаться",
                    callback_data="signup_from_info",
                )
            ],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_home")],
        ]
    )


def signup_keyboard(back_callback: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🎟 Кастинг", callback_data="choose_casting"),
                InlineKeyboardButton(text="💃 Класс", callback_data="choose_class"),
            ],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data=back_callback)],
        ]
    )


def describe_update(event: TelegramObject) -> dict[str, Any]:
    if isinstance(event, Message):
        return {
            "kind": "message",
            "text": event.text,
            "caption": event.caption,
            "has_photo": bool(event.photo),
            "has_document": bool(event.document),
        }
    if isinstance(event, CallbackQuery):
        return {"kind": "callback", "data": event.data}
    return {"kind": type(event).__name__}


async def notify_error(
    exc: BaseException,
    *,
    user: User | None = None,
    context: str = "",
    bot: Bot | None = None,
) -> None:
    logging.exception("%s", context or "Ошибка бота")
    details = {
        "context": context,
        "error": str(exc),
        "traceback": traceback.format_exc()[-3500:],
    }
    try:
        await asyncio.to_thread(persist.log, user, "error", details)
    except Exception:
        logging.exception("Не удалось записать ошибку в PostgreSQL")

    target_bot = bot or bot_instance
    if target_bot is None:
        return
    user_part = ""
    if user:
        username = f" @{user.username}" if user.username else ""
        user_part = f"Пользователь: {user.id}{username}\n"
    text = (
        "⚠️ <b>Ошибка в боте</b>\n\n"
        f"{escape(context)}\n"
        f"{user_part}"
        f"<code>{escape(str(exc))[:1000]}</code>\n\n"
        f"<pre>{escape(details['traceback'][-2500:])}</pre>"
    )
    try:
        await target_bot.send_message(ERROR_ADMIN_USER_ID, text[:4000])
    except Exception:
        logging.exception("Не удалось отправить ошибку администратору")


async def persist_log(
    user: User | None,
    action: str,
    details: dict | None = None,
) -> None:
    try:
        await asyncio.to_thread(persist.log, user, action, details)
    except Exception as exc:
        await notify_error(exc, user=user, context=f"log:{action}")


async def persist_state(
    user: User | None,
    data: dict,
    status: str | None = None,
) -> None:
    if not user or not data.get("event_type"):
        return
    event_type = data["event_type"]
    answers = data.get("answers") or {}
    current_index = int(data.get("current_index") or 0)
    if status is None:
        total = len(fields_for(event_type))
        status = "waiting_payment" if current_index >= total else "in_progress"
    try:
        await asyncio.to_thread(
            persist.save_registration,
            user,
            event_type=event_type,
            answers=answers,
            current_index=current_index,
            status=status,
        )
    except Exception as exc:
        await notify_error(exc, user=user, context="save_registration")


def can_resume(draft: dict | None) -> bool:
    if not draft or draft.get("status") == "registered":
        return False
    answers = draft.get("answers") or {}
    return bool(answers) or int(draft.get("current_index") or 0) > 0 or draft.get(
        "status"
    ) == "waiting_payment"


class ActionLogMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable,
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user: User | None = data.get("event_from_user")
        details = describe_update(event)
        try:
            result = await handler(event, data)
        except Exception as exc:
            await persist_log(user, "update_error", {**details, "error": str(exc)})
            raise
        await persist_log(user, "update", details)
        return result


def _is_not_modified(exc: TelegramBadRequest) -> bool:
    return "message is not modified" in str(exc)


async def send_or_edit(
    message: Message,
    text: str,
    markup: InlineKeyboardMarkup | None,
    as_edit: bool,
) -> None:
    if as_edit:
        try:
            await message.edit_text(text, reply_markup=markup)
            return
        except TelegramBadRequest as exc:
            if _is_not_modified(exc):
                return
    await message.answer(text, reply_markup=markup)


def current_field(data: dict) -> Field:
    fields = fields_for(data["event_type"])
    editing_id = data.get("editing_id")
    if editing_id:
        return field_by_id(fields, editing_id)
    return fields[data["current_index"]]


def question_view(data: dict) -> tuple[str, InlineKeyboardMarkup]:
    field = current_field(data)
    fields = fields_for(data["event_type"])
    editing = bool(data.get("editing_id"))
    show_edit = not editing and data.get("current_index", 0) > 0

    if editing:
        header = f"✏️ <b>Изменение ответа</b>\n<i>{field.title}</i>\n\n"
    else:
        step = data["current_index"] + 1
        header = (
            f"✍️ <b>Анкета · {event_title(data['event_type'])}</b>\n"
            f"Шаг {step} из {len(fields)}\n\n"
        )

    text = header + field.question
    pending = data.get("pending_styles") or []
    if field.type == "multi" and pending:
        text += "\n\n<b>Выбрано:</b> " + ", ".join(escape(item) for item in pending)

    markup = question_keyboard(
        field,
        show_edit=show_edit,
        editing=editing,
        pending_styles=pending,
    )
    return text, markup


async def ensure_pending_styles(state: FSMContext, data: dict) -> dict:
    field = current_field(data)
    if field.type == "multi" and data.get("pending_styles") is None:
        answers = data.get("answers", {})
        await state.update_data(pending_styles=list(answers.get(field.id, [])))
        return await state.get_data()
    return data


async def present_question(
    message: Message,
    state: FSMContext,
    *,
    as_edit: bool = False,
) -> None:
    data = await ensure_pending_styles(state, await state.get_data())
    text, markup = question_view(data)
    await send_or_edit(message, text, markup, as_edit)


async def save_and_continue(
    message: Message,
    state: FSMContext,
    value: object,
    *,
    as_edit: bool = False,
    user: User | None = None,
) -> None:
    actor = user or message.from_user
    data = await state.get_data()
    answers = dict(data.get("answers", {}))
    field = current_field(data)
    answers[field.id] = value

    if data.get("editing_id"):
        await state.update_data(
            answers=answers,
            editing_id=None,
            pending_styles=None,
        )
        await persist_log(
            actor,
            "form_edit_answer",
            {"field": field.id, "value": value, "event_type": data.get("event_type")},
        )
        await persist_state(actor, await state.get_data())
        await present_question(message, state, as_edit=as_edit)
        return

    next_index = data["current_index"] + 1
    await state.update_data(
        answers=answers,
        current_index=next_index,
        pending_styles=None,
    )
    await persist_log(
        actor,
        "form_answer",
        {
            "field": field.id,
            "value": value,
            "event_type": data.get("event_type"),
            "step": next_index,
        },
    )
    updated = await state.get_data()
    if next_index >= len(fields_for(data["event_type"])):
        await state.set_state(FormStates.waiting_payment)
        await persist_state(actor, updated, status="waiting_payment")
        await send_or_edit(
            message,
            payment_text(data["event_type"], PAYMENT_REQUISITES),
            None,
            as_edit,
        )
        return

    await persist_state(actor, updated)
    await present_question(message, state, as_edit=as_edit)


def user_line(user: User | None) -> str:
    if not user:
        return "Пользователь неизвестен"
    mention = f'<a href="tg://user?id={user.id}">{user.full_name}</a>'
    username = f" @{user.username}" if user.username else ""
    return f"{mention}{username}\n<code>{user.id}</code>"


async def send_welcome(message: Message) -> None:
    await message.answer(WELCOME_TEXT, reply_markup=welcome_keyboard())


async def render_signup(target: Message, back_callback: str) -> None:
    try:
        await target.edit_text(SIGNUP_TEXT, reply_markup=signup_keyboard(back_callback))
    except TelegramBadRequest as exc:
        if not _is_not_modified(exc):
            raise


async def begin_form(
    message: Message,
    state: FSMContext,
    *,
    event_type: str,
    signup_back: str,
    user: User,
    as_edit: bool = True,
) -> None:
    await state.set_state(FormStates.answering)
    await state.update_data(
        event_type=event_type,
        signup_back=signup_back,
        answers={},
        current_index=0,
        editing_id=None,
        pending_styles=None,
    )
    await persist_log(user, "form_start", {"event_type": event_type})
    await persist_state(user, await state.get_data(), status="in_progress")
    await present_question(message, state, as_edit=as_edit)


async def restore_form(
    message: Message,
    state: FSMContext,
    *,
    draft: dict,
    signup_back: str,
    user: User,
) -> None:
    event_type = draft["event_type"]
    answers = draft.get("answers") or {}
    current_index = int(draft.get("current_index") or 0)
    status = draft.get("status") or "in_progress"
    await state.update_data(
        event_type=event_type,
        signup_back=signup_back,
        answers=answers,
        current_index=current_index,
        editing_id=None,
        pending_styles=None,
    )
    await persist_log(
        user,
        "form_resume",
        {"event_type": event_type, "step": current_index, "status": status},
    )
    if status == "waiting_payment" or current_index >= len(fields_for(event_type)):
        await state.set_state(FormStates.waiting_payment)
        await persist_state(user, await state.get_data(), status="waiting_payment")
        await send_or_edit(
            message,
            payment_text(event_type, PAYMENT_REQUISITES),
            None,
            True,
        )
        return
    await state.set_state(FormStates.answering)
    await present_question(message, state, as_edit=True)


dp = Dispatcher(storage=MemoryStorage())
dp.message.middleware(ActionLogMiddleware())
dp.callback_query.middleware(ActionLogMiddleware())


@dp.error()
async def on_error(event: ErrorEvent, bot: Bot) -> None:
    user = None
    if event.update.message:
        user = event.update.message.from_user
    elif event.update.callback_query:
        user = event.update.callback_query.from_user
    await notify_error(
        event.exception,
        user=user,
        context="handler",
        bot=bot,
    )


@dp.message(CommandStart())
async def start(message: Message, state: FSMContext) -> None:
    await persist_log(message.from_user, "start")
    await state.clear()
    await send_welcome(message)


@dp.callback_query(F.data == "info")
async def show_info(callback: CallbackQuery, state: FSMContext) -> None:
    await persist_log(callback.from_user, "open_info")
    await state.clear()
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(INFO_TEXT, reply_markup=info_keyboard())


async def show_signup_screen(
    callback: CallbackQuery,
    state: FSMContext,
    back_callback: str,
) -> None:
    signup_back = back_callback
    await persist_log(callback.from_user, "open_signup")
    await state.clear()
    await state.update_data(signup_back=signup_back)
    await callback.answer()
    if callback.message:
        await render_signup(callback.message, back_callback)


@dp.callback_query(F.data == "signup")
async def show_signup(callback: CallbackQuery, state: FSMContext) -> None:
    await show_signup_screen(callback, state, back_callback="back_home")


@dp.callback_query(F.data == "signup_from_info")
async def show_signup_from_info(callback: CallbackQuery, state: FSMContext) -> None:
    await show_signup_screen(callback, state, back_callback="info")


@dp.callback_query(F.data.in_({"choose_casting", "choose_class"}))
async def start_form(callback: CallbackQuery, state: FSMContext) -> None:
    event_type = "casting" if callback.data == "choose_casting" else "class"
    signup_back = (await state.get_data()).get("signup_back", "back_home")
    user = callback.from_user
    await callback.answer()
    if not user or not callback.message:
        return

    try:
        draft = await asyncio.to_thread(persist.get_draft, user.id, event_type)
    except Exception as exc:
        await notify_error(exc, user=user, context="get_draft")
        draft = None

    if draft and draft.get("status") == "registered":
        await persist_log(user, "already_registered", {"event_type": event_type})
        await callback.message.edit_text(
            already_registered_text(event_type),
            reply_markup=already_registered_keyboard(),
        )
        return

    if can_resume(draft):
        await state.update_data(signup_back=signup_back)
        await persist_log(user, "form_resume_offered", {"event_type": event_type})
        await callback.message.edit_text(
            resume_text(event_type, draft),
            reply_markup=resume_keyboard(event_type),
        )
        return

    await begin_form(
        callback.message,
        state,
        event_type=event_type,
        signup_back=signup_back,
        user=user,
    )


@dp.callback_query(F.data.startswith("form_resume:"))
async def resume_form(callback: CallbackQuery, state: FSMContext) -> None:
    event_type = (callback.data or "").split(":", 1)[1]
    signup_back = (await state.get_data()).get("signup_back", "back_home")
    user = callback.from_user
    await callback.answer()
    if not user or not callback.message:
        return
    try:
        draft = await asyncio.to_thread(persist.get_draft, user.id, event_type)
    except Exception as exc:
        await notify_error(exc, user=user, context="form_resume")
        draft = None
    if not can_resume(draft):
        await begin_form(
            callback.message,
            state,
            event_type=event_type,
            signup_back=signup_back,
            user=user,
        )
        return
    await restore_form(
        callback.message,
        state,
        draft=draft,
        signup_back=signup_back,
        user=user,
    )


@dp.callback_query(F.data.startswith("form_restart:"))
async def restart_form(callback: CallbackQuery, state: FSMContext) -> None:
    event_type = (callback.data or "").split(":", 1)[1]
    signup_back = (await state.get_data()).get("signup_back", "back_home")
    user = callback.from_user
    await callback.answer()
    if not user or not callback.message:
        return
    await persist_log(user, "form_restart", {"event_type": event_type})
    await begin_form(
        callback.message,
        state,
        event_type=event_type,
        signup_back=signup_back,
        user=user,
    )


@dp.message(FormStates.answering, F.contact)
async def form_shared_contact(message: Message, state: FSMContext) -> None:
    field = current_field(await state.get_data())
    if field.id != "contact" or field.type != "text":
        await message.answer("Сейчас нужен ответ на вопрос выше.")
        return
    contact = validate_contact(message.contact.phone_number if message.contact else "")
    if not contact:
        await message.answer(field.error)
        return
    await save_and_continue(message, state, contact)


@dp.message(FormStates.answering, F.text)
async def form_text_answer(message: Message, state: FSMContext) -> None:
    field = current_field(await state.get_data())
    if field.type != "text" or not field.validate:
        await message.answer("Выберите вариант кнопкой под сообщением.")
        return
    value = field.validate(message.text or "")
    if not value:
        await message.answer(field.error)
        return
    await save_and_continue(message, state, value)


@dp.message(FormStates.answering)
async def form_unexpected(message: Message, state: FSMContext) -> None:
    field = current_field(await state.get_data())
    if field.type == "text":
        await message.answer(field.error)
        return
    await message.answer("Выберите вариант кнопкой под сообщением.")


@dp.callback_query(F.data.in_({"yn:yes", "yn:no"}), StateFilter(FormStates.answering))
async def form_yesno(callback: CallbackQuery, state: FSMContext) -> None:
    field = current_field(await state.get_data())
    if field.type != "yesno":
        await callback.answer()
        return
    value = "Да" if callback.data == "yn:yes" else "Нет"
    await callback.answer()
    if callback.message:
        await save_and_continue(
            callback.message,
            state,
            value,
            as_edit=True,
            user=callback.from_user,
        )


@dp.callback_query(F.data.startswith("sc:"), StateFilter(FormStates.answering))
async def form_scale(callback: CallbackQuery, state: FSMContext) -> None:
    field = current_field(await state.get_data())
    if field.type != "scale" or not callback.data:
        await callback.answer()
        return
    score = callback.data.split(":", 1)[1]
    if score not in {str(i) for i in range(1, 11)}:
        await callback.answer()
        return
    await callback.answer()
    if callback.message:
        await save_and_continue(
            callback.message,
            state,
            f"{score}/10",
            as_edit=True,
            user=callback.from_user,
        )


@dp.callback_query(F.data.startswith("st:"), StateFilter(FormStates.answering))
async def form_toggle_style(callback: CallbackQuery, state: FSMContext) -> None:
    data = await ensure_pending_styles(state, await state.get_data())
    field = current_field(data)
    if field.type not in {"multi", "single"} or not callback.data:
        await callback.answer()
        return
    try:
        index = int(callback.data.split(":", 1)[1])
    except ValueError:
        await callback.answer()
        return
    pending = list(data.get("pending_styles") or [])
    options = style_options(field.id, pending)
    if not 0 <= index < len(options):
        await callback.answer()
        return
    option = options[index]
    if field.type == "single":
        await callback.answer()
        if callback.message:
            await save_and_continue(
                callback.message,
                state,
                option,
                as_edit=True,
                user=callback.from_user,
            )
        return
    if option == "Нет других стилей":
        pending = ["Нет других стилей"]
    else:
        pending = [item for item in pending if item != "Нет других стилей"]
        if option in pending:
            pending.remove(option)
        else:
            pending.append(option)
    await state.update_data(pending_styles=pending)
    await persist_log(
        callback.from_user,
        "form_style_toggle",
        {"field": field.id, "pending": pending},
    )
    await callback.answer()
    if callback.message:
        await present_question(callback.message, state, as_edit=True)


@dp.callback_query(F.data == "form_multi_done", StateFilter(FormStates.answering))
async def form_multi_done(callback: CallbackQuery, state: FSMContext) -> None:
    data = await ensure_pending_styles(state, await state.get_data())
    field = current_field(data)
    pending = list(data.get("pending_styles") or [])
    if field.type != "multi" or not pending:
        await callback.answer("Выберите хотя бы один вариант", show_alert=True)
        return
    await callback.answer()
    if callback.message:
        await save_and_continue(
            callback.message,
            state,
            pending,
            as_edit=True,
            user=callback.from_user,
        )


@dp.callback_query(F.data == "form_custom", StateFilter(FormStates.answering))
async def form_custom(callback: CallbackQuery, state: FSMContext) -> None:
    field = current_field(await state.get_data())
    if field.type not in {"multi", "single"}:
        await callback.answer()
        return
    await state.set_state(FormStates.adding_custom)
    await persist_log(callback.from_user, "form_custom_start", {"field": field.id})
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(
            "Напишите свой стиль — одним коротким названием.",
            reply_markup=custom_style_keyboard(),
        )


@dp.callback_query(F.data == "form_custom_back", StateFilter(FormStates.adding_custom))
async def form_custom_back(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(FormStates.answering)
    await callback.answer()
    if callback.message:
        await present_question(callback.message, state, as_edit=True)


@dp.message(FormStates.adding_custom, F.text)
async def form_custom_text(message: Message, state: FSMContext) -> None:
    style = validate_custom_style(message.text or "")
    if not style:
        await message.answer(
            "Не похоже на название стиля. Коротко, без смайликов. Например: <i>Afro</i>.",
            reply_markup=custom_style_keyboard(),
        )
        return
    field = current_field(await state.get_data())
    await state.set_state(FormStates.answering)
    if field.type == "single":
        await save_and_continue(message, state, style)
        return
    data = await ensure_pending_styles(state, await state.get_data())
    pending = list(data.get("pending_styles") or [])
    pending = [item for item in pending if item != "Нет других стилей"]
    if style not in pending:
        pending.append(style)
    await state.update_data(pending_styles=pending)
    await present_question(message, state)


@dp.message(FormStates.adding_custom)
async def form_custom_invalid(message: Message) -> None:
    await message.answer(
        "Пришлите название стиля текстом.",
        reply_markup=custom_style_keyboard(),
    )


@dp.callback_query(F.data == "form_edit", StateFilter(FormStates.answering))
async def form_edit(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    fields = answered_fields(
        data["event_type"],
        data.get("answers", {}),
        data.get("current_index", 0),
    )
    if not fields:
        await callback.answer("Пока нечего менять", show_alert=True)
        return
    await persist_log(callback.from_user, "form_edit_open")
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(
            "Какой ответ хотите изменить?",
            reply_markup=edit_keyboard(fields),
        )


@dp.callback_query(F.data.startswith("ed:"), StateFilter(FormStates.answering))
async def form_edit_pick(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.data:
        await callback.answer()
        return
    field_id = callback.data.split(":", 1)[1]
    data = await state.get_data()
    try:
        field_by_id(fields_for(data["event_type"]), field_id)
    except KeyError:
        await callback.answer()
        return
    await state.update_data(editing_id=field_id, pending_styles=None)
    await persist_log(callback.from_user, "form_edit_pick", {"field": field_id})
    await callback.answer()
    if callback.message:
        await present_question(callback.message, state, as_edit=True)


@dp.callback_query(F.data == "form_edit_back", StateFilter(FormStates.answering))
async def form_edit_back(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(editing_id=None, pending_styles=None)
    await callback.answer()
    if callback.message:
        await present_question(callback.message, state, as_edit=True)


@dp.callback_query(F.data == "form_cancel")
async def form_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    back_callback = data.get("signup_back", "back_home")
    await persist_log(
        callback.from_user,
        "form_cancel",
        {
            "event_type": data.get("event_type"),
            "step": data.get("current_index"),
        },
    )
    if data.get("event_type"):
        await persist_state(callback.from_user, data)
    await state.clear()
    await state.update_data(signup_back=back_callback)
    await callback.answer("Анкета отменена")
    if callback.message:
        await render_signup(callback.message, back_callback)


@dp.message(FormStates.waiting_payment, F.photo)
async def payment_photo(message: Message, state: FSMContext, bot: Bot) -> None:
    await confirm_payment(message, state, bot, message.message_id)


@dp.message(FormStates.waiting_payment, F.document)
async def payment_document(message: Message, state: FSMContext, bot: Bot) -> None:
    document = message.document
    if not document or not (document.mime_type or "").startswith("image/"):
        await message.answer("Пришлите именно скриншот оплаты — фото или картинку.")
        return
    await confirm_payment(message, state, bot, message.message_id)


@dp.message(FormStates.waiting_payment)
async def payment_not_screenshot(message: Message) -> None:
    await persist_log(message.from_user, "payment_not_screenshot")
    await message.answer(
        "Нужен <b>скриншот оплаты</b>.\n"
        "Пока он не получен, запись не подтверждается."
    )


async def confirm_payment(
    message: Message,
    state: FSMContext,
    bot: Bot,
    screenshot_message_id: int,
) -> None:
    data = await state.get_data()
    event_type = data["event_type"]
    answers = data.get("answers", {})
    summary = admin_summary(event_type, answers, user_line(message.from_user))
    await persist_log(
        message.from_user,
        "payment_screenshot",
        {"event_type": event_type},
    )

    try:
        await bot.forward_message(
            chat_id=PAYMENT_ADMIN_USER_ID,
            from_chat_id=message.chat.id,
            message_id=screenshot_message_id,
        )
        await bot.send_message(PAYMENT_ADMIN_USER_ID, summary)
    except (TelegramBadRequest, TelegramForbiddenError):
        try:
            await bot.send_message(PAYMENT_ADMIN_USER_ID, summary)
            await bot.copy_message(
                chat_id=PAYMENT_ADMIN_USER_ID,
                from_chat_id=message.chat.id,
                message_id=screenshot_message_id,
            )
        except (TelegramBadRequest, TelegramForbiddenError) as exc:
            await notify_error(exc, user=message.from_user, context="forward_payment")
            await message.answer(
                "Скрин получен, но не получилось отправить его организатору. "
                "Напишите в личные сообщения и приложите чек ещё раз."
            )
            return

    await persist_state(message.from_user, data, status="registered")
    await persist_log(message.from_user, "registered", {"event_type": event_type})
    await state.clear()
    await message.answer(
        registered_text(event_type, answers),
        reply_markup=home_keyboard(),
    )


@dp.callback_query(StateFilter(FormStates.waiting_payment))
async def payment_old_buttons(callback: CallbackQuery) -> None:
    await callback.answer(
        "Сначала пришлите скриншот оплаты в чат",
        show_alert=True,
    )


@dp.callback_query(F.data == "back_home")
async def back_home(callback: CallbackQuery, state: FSMContext) -> None:
    await persist_log(callback.from_user, "back_home")
    await state.clear()
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(
            WELCOME_TEXT,
            reply_markup=welcome_keyboard(),
        )


async def main() -> None:
    global bot_instance
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN не задан в .env")

    logging.basicConfig(level=logging.INFO)
    bot_instance = Bot(
        token=TELEGRAM_BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    try:
        await asyncio.to_thread(persist.init)
        await persist_log(None, "bot_started")
    except Exception as exc:
        await notify_error(exc, context="init_database", bot=bot_instance)
        raise
    await dp.start_polling(bot_instance)


if __name__ == "__main__":
    asyncio.run(main())
