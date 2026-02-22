import os
import json
import asyncio
import random
from datetime import datetime
from time import monotonic
from pathlib import Path

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F, Router, BaseMiddleware
from aiogram.filters import StateFilter
from aiogram.types import (
    Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from aiogram.types import InputMediaPhoto, InputMediaDocument, InputMediaAudio, InputMediaVideo
from aiogram.types import FSInputFile
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.enums import ChatMemberStatus

# ===================== ENV =====================
BASE_DIR = Path(__file__).resolve().parent
env_path = BASE_DIR / ".env"
load_dotenv(dotenv_path=env_path)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
INFO_ADMIN_ID = 7420305714  # @xolboyevv77 - ro'yxatdan o'tganlar
CARD_NUMBER = os.getenv("CARD_NUMBER", "9860080347733265")
CHANNEL = "@bilimulash_kanal"
DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE_DIR))).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)
USERS_FILE = DATA_DIR / "users.json"
EXPORT_FILE = DATA_DIR / "users_export.rtf"
LEGACY_USERS_FILE = BASE_DIR / "users.json"

if USERS_FILE != LEGACY_USERS_FILE and (not USERS_FILE.exists()) and LEGACY_USERS_FILE.exists():
    try:
        USERS_FILE.write_bytes(LEGACY_USERS_FILE.read_bytes())
    except Exception:
        pass

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is missing.")

bot = Bot(BOT_TOKEN)
dp = Dispatcher()
priority_router = Router()
reg_router = Router()  # ro'yxat orqaga qaytish — birinchi tekshiriladi

async def record_last_user_message(msg: Message, state: FSMContext):
    await state.update_data(last_user_chat_id=msg.chat.id, last_user_msg_id=msg.message_id)

async def delete_last_user_message(state: FSMContext):
    data = await state.get_data()
    chat_id = data.get('last_user_chat_id')
    message_id = data.get('last_user_msg_id')
    if chat_id and message_id:
        try:
            await bot.delete_message(chat_id, message_id)
        except Exception:
            pass
    await state.update_data(last_user_chat_id=None, last_user_msg_id=None)

class ThrottleMiddleware(BaseMiddleware):
    def __init__(self, min_interval: float = 0.7, warn_interval: float = 2.0):
        self.min_interval = min_interval
        self.warn_interval = warn_interval
        self.last_time: dict[int, float] = {}
        self.last_warn: dict[int, float] = {}

    async def __call__(self, handler, event, data):
        if isinstance(event, Message) and event.from_user:
            user_id = event.from_user.id
            if user_id != ADMIN_ID:
                now = monotonic()
                last = self.last_time.get(user_id, 0.0)
                if now - last < self.min_interval:
                    last_warn = self.last_warn.get(user_id, 0.0)
                    if now - last_warn > self.warn_interval:
                        try:
                            await event.answer("Iltimos, sekinroq yuboring.")
                        except Exception:
                            pass
                        self.last_warn[user_id] = now
                    return
                self.last_time[user_id] = now
        return await handler(event, data)

# ===================== BANNER (BotFatherda description qo'yiladi) =====================
BANNER = (
    "📌 **Bilim Ulash Bot**\n\n"
    "✅ Slayd tayyorlash (PDF, PPT, Word)\n"
    "✅ AI Video yaratish\n"
    "✅ Tez va sifatli xizmat\n\n"
    "Botdan to'liq foydalanish uchun quyidagi kanalga obuna bo'ling va /start bosing."
)

BOOK_CATEGORY_TOPICS: dict[str, list[str]] = {
    "Motivatsion kitoblar": [
        "O'z-o'zini rivojlantirish",
        "Irodani oshirish",
        "Maqsad qo'yish",
        "Boylik psixologiyasi",
    ],
    "Badiiy adabiyot (Art / Romanlar)": [
        "Romanlar",
        "Hikoyalar",
        "Detektiv",
        "Sarguzasht",
    ],
    "Biznes va Startap": [
        "Biznes boshlash",
        "Marketologiya",
        "Pul boshqaruvi",
        "Muloqot ko'nikmalari",
    ],
    "Psixologiya": [
        "Inson ruhiyati",
        "Stress boshqaruvi",
        "Munosabatlar",
        "Shaxsiyat",
    ],
    "Ilmiy-ommabop": [
        "Fizika",
        "Kosmos",
        "Tarix",
        "Biologiya",
    ],
}

BOOK_CATEGORY_EMOJI: dict[str, str] = {
    "Motivatsion kitoblar": "📘",
    "Badiiy adabiyot (Art / Romanlar)": "📙",
    "Biznes va Startap": "📕",
    "Psixologiya": "📗",
    "Ilmiy-ommabop": "📔",
}

def default_books_data() -> dict:
    online = {name: [] for name in BOOK_CATEGORY_TOPICS.keys()}
    audio = {name: [] for name in BOOK_CATEGORY_TOPICS.keys()}
    return {"online": online, "audio": audio, "numbered": {}}

def normalize_books_data(raw) -> dict:
    data = default_books_data()
    if not isinstance(raw, dict):
        return data

    for section in ("online", "audio"):
        section_raw = raw.get(section)
        if not isinstance(section_raw, dict):
            continue
        for cat_name, items in section_raw.items():
            if not isinstance(items, list):
                continue
            data[section][str(cat_name)] = [i for i in items if isinstance(i, dict)]

    numbered_raw = raw.get("numbered")
    if isinstance(numbered_raw, dict):
        cleaned = {}
        for k, v in numbered_raw.items():
            try:
                int(k)
            except Exception:
                continue
            if isinstance(v, dict):
                cleaned[str(k)] = v
        data["numbered"] = cleaned

    # Legacy: eski modelda kategoriya ichida number bilan saqlangan kitoblar bo'lsa
    # raqamli xaritaga ko'chirib qo'yamiz.
    for section in ("online", "audio"):
        for cat_name, items in list(data[section].items()):
            kept = []
            for item in items:
                number = item.get("number")
                if isinstance(number, int) and number > 0:
                    nkey = str(number)
                    if nkey not in data["numbered"]:
                        migrated = dict(item)
                        migrated["section"] = section
                        migrated["category"] = cat_name
                        data["numbered"][nkey] = migrated
                    migrated_item = dict(item)
                    migrated_item.pop("number", None)
                    kept.append(migrated_item)
                else:
                    kept.append(item)
            data[section][cat_name] = kept
    return data

# ===================== USER STORAGE =====================
def default_users_data() -> dict:
    return {
        "users": {},
        "next_status": 1,
        "bilim": {},
        "kino": {},
        "books": default_books_data(),
        "orders": [],
    }

def load_users():
    data = default_users_data()
    if USERS_FILE.exists():
        try:
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, dict):
                data["users"] = raw.get("users") if isinstance(raw.get("users"), dict) else {}
                data["bilim"] = raw.get("bilim") if isinstance(raw.get("bilim"), dict) else {}
                data["kino"] = raw.get("kino") if isinstance(raw.get("kino"), dict) else {}
                data["books"] = normalize_books_data(raw.get("books"))
                data["orders"] = raw.get("orders") if isinstance(raw.get("orders"), list) else []

                next_status = raw.get("next_status", 1)
                if isinstance(next_status, int) and next_status > 0:
                    data["next_status"] = next_status
                else:
                    max_status = 0
                    for u in data["users"].values():
                        if isinstance(u, dict):
                            status = u.get("status")
                            if isinstance(status, int) and status > max_status:
                                max_status = status
                    data["next_status"] = max_status + 1
        except Exception:
            return data
    return data

def save_users(data):
    USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_user_status(user_id: int) -> int | None:
    data = load_users()
    uid = str(user_id)
    if uid in data["users"]:
        return data["users"][uid].get("status")
    return None

def register_user(user_id: int, name: str, age: str, region: str, phone: str) -> int:
    data = load_users()
    uid = str(user_id)
    if uid in data["users"]:
        return data["users"][uid]["status"]  # allaqachon ro'yxatdan o'tgan
    status = data["next_status"]
    data["users"][uid] = {
        "name": name,
        "age": age,
        "region": region,
        "phone": phone,
        "status": status,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    data["next_status"] = status + 1
    save_users(data)
    return status

def get_user_by_status(status: int) -> int | None:
    data = load_users()
    for uid, u in data["users"].items():
        if u.get("status") == status:
            return int(uid)
    return None

def is_registered(user_id: int) -> bool:
    return get_user_status(user_id) is not None

def add_bilim_number(number: int, message):
    data = load_users()
    data["bilim"][str(number)] = message
    save_users(data)

def delete_bilim_number(number: int) -> bool:
    data = load_users()
    key = str(number)
    if key in data["bilim"]:
        del data["bilim"][key]
        save_users(data)
        return True
    return False

def get_bilim_message(number: int):
    data = load_users()
    return data["bilim"].get(str(number))

def list_bilim_numbers() -> list[tuple[int, str]]:
    data = load_users()
    items = []
    for k, v in data["bilim"].items():
        try:
            items.append((int(k), v))
        except ValueError:
            continue
    return sorted(items, key=lambda x: x[0])

def add_kino_number(number: int, message):
    data = load_users()
    data["kino"][str(number)] = message
    save_users(data)

def delete_kino_number(number: int) -> bool:
    data = load_users()
    key = str(number)
    if key in data["kino"]:
        del data["kino"][key]
        save_users(data)
        return True
    return False

def get_kino_message(number: int):
    data = load_users()
    return data["kino"].get(str(number))

def list_kino_numbers() -> list[tuple[int, str]]:
    data = load_users()
    items = []
    for k, v in data["kino"].items():
        try:
            items.append((int(k), v))
        except ValueError:
            continue
    return sorted(items, key=lambda x: x[0])

def add_book_direction(direction_name: str):
    data = load_users()
    books = normalize_books_data(data.get("books"))
    for section in ("online", "audio"):
        if direction_name not in books[section]:
            books[section][direction_name] = []
    data["books"] = books
    save_users(data)

def list_book_categories(section: str) -> list[str]:
    data = load_users()
    books = normalize_books_data(data.get("books"))
    section_data = books.get(section, {})
    return list(section_data.keys()) if isinstance(section_data, dict) else []

def get_book_category_by_index(section: str, idx: int) -> str | None:
    cats = list_book_categories(section)
    if idx < 0 or idx >= len(cats):
        return None
    return cats[idx]

def add_book_item(section: str, category: str, cover_payload, info_text: str, file_payload) -> None:
    data = load_users()
    books = normalize_books_data(data.get("books"))
    section_data = books.setdefault(section, {})
    items = section_data.setdefault(category, [])
    book_item = {
        "cover": cover_payload,
        "info": info_text,
        "file": file_payload,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    items.append(book_item)
    data["books"] = books
    save_users(data)

def list_books_in_category(section: str, category: str) -> list[dict]:
    data = load_users()
    books = normalize_books_data(data.get("books"))
    section_data = books.get(section, {})
    items = section_data.get(category, []) if isinstance(section_data, dict) else []
    if not isinstance(items, list):
        return []
    return [i for i in items if isinstance(i, dict)]

def find_book_by_number(number: int):
    data = load_users()
    books = normalize_books_data(data.get("books"))
    item = books.get("numbered", {}).get(str(number))
    if isinstance(item, dict):
        return item
    return None

def add_numbered_book(number: int, cover_payload, info_text: str, file_payload, section: str | None = None, category: str | None = None):
    data = load_users()
    books = normalize_books_data(data.get("books"))
    item = {
        "cover": cover_payload,
        "info": info_text,
        "file": file_payload,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    if section:
        item["section"] = section
    if category:
        item["category"] = category
    books.setdefault("numbered", {})[str(number)] = item
    data["books"] = books
    save_users(data)

def list_numbered_books() -> list[tuple[int, dict]]:
    data = load_users()
    books = normalize_books_data(data.get("books"))
    out = []
    for k, v in books.get("numbered", {}).items():
        try:
            num = int(k)
        except Exception:
            continue
        if isinstance(v, dict):
            out.append((num, v))
    return sorted(out, key=lambda x: x[0])

def delete_numbered_book(number: int) -> bool:
    data = load_users()
    books = normalize_books_data(data.get("books"))
    key = str(number)
    if key in books.get("numbered", {}):
        del books["numbered"][key]
        data["books"] = books
        save_users(data)
        return True
    return False

def delete_book_by_index(section: str, category: str, idx: int) -> bool:
    data = load_users()
    books = normalize_books_data(data.get("books"))
    section_data = books.get(section, {})
    if not isinstance(section_data, dict):
        return False
    items = section_data.get(category, [])
    if not isinstance(items, list):
        return False
    if idx < 0 or idx >= len(items):
        return False
    del items[idx]
    section_data[category] = items
    books[section] = section_data
    data["books"] = books
    save_users(data)
    return True

def summarize_payload(payload) -> str:
    if isinstance(payload, dict):
        ptype = payload.get("type", "text")
        if ptype == "text":
            text = payload.get("text", "")
            return f"matn: {text[:30]}{'...' if len(text) > 30 else ''}"
        return ptype
    if isinstance(payload, list):
        return f"{len(payload)} ta xabar"
    return "matn"

def summarize_payload_list(payload) -> str:
    if isinstance(payload, list):
        counts = {"text": 0, "photo": 0, "video": 0, "document": 0, "voice": 0, "audio": 0, "other": 0}
        for item in payload:
            if isinstance(item, dict):
                counts[item.get("type", "other")] = counts.get(item.get("type", "other"), 0) + 1
            else:
                counts["text"] += 1
        parts = []
        if counts["text"]:
            parts.append(f"matn {counts['text']}")
        if counts["photo"]:
            parts.append(f"rasm {counts['photo']}")
        if counts["video"]:
            parts.append(f"video {counts['video']}")
        if counts["document"]:
            parts.append(f"fayl {counts['document']}")
        if counts["voice"]:
            parts.append(f"ovoz {counts['voice']}")
        if counts["audio"]:
            parts.append(f"audio {counts['audio']}")
        if counts["other"]:
            parts.append(f"boshqa {counts['other']}")
        return ", ".join(parts) if parts else "bo'sh"
    return summarize_payload(payload)

def build_payload_from_message(msg: Message) -> dict:
    if msg.photo:
        return {"type": "photo", "file_id": msg.photo[-1].file_id, "caption": msg.caption or ""}
    if msg.video:
        return {"type": "video", "file_id": msg.video.file_id, "caption": msg.caption or ""}
    if msg.document:
        return {"type": "document", "file_id": msg.document.file_id, "caption": msg.caption or ""}
    if msg.audio:
        return {"type": "audio", "file_id": msg.audio.file_id, "caption": msg.caption or ""}
    if msg.voice:
        return {"type": "voice", "file_id": msg.voice.file_id, "caption": msg.caption or ""}
    return {"type": "text", "text": msg.text or ""}

async def send_payload(msg: Message, payload):
    if isinstance(payload, dict):
        ptype = payload.get("type")
        if ptype == "photo":
            await msg.answer_photo(payload.get("file_id"), caption=payload.get("caption"))
        elif ptype == "video":
            await msg.answer_video(payload.get("file_id"), caption=payload.get("caption"))
        elif ptype == "document":
            await msg.answer_document(payload.get("file_id"), caption=payload.get("caption"))
        elif ptype == "audio":
            await msg.answer_audio(payload.get("file_id"), caption=payload.get("caption"))
        elif ptype == "voice":
            await msg.answer_voice(payload.get("file_id"), caption=payload.get("caption"))
        elif ptype == "text":
            await msg.answer(payload.get("text", ""))
        else:
            await msg.answer(payload.get("caption") or payload.get("text") or "")
    else:
        await msg.answer(str(payload))

def get_answer_value(msg: Message) -> str:
    if msg.text:
        return msg.text
    if msg.voice:
        return f"[voice:{msg.voice.file_id}]"
    if msg.audio:
        return f"[audio:{msg.audio.file_id}]"
    if msg.video_note:
        return f"[video_note:{msg.video_note.file_id}]"
    return ""

async def send_payload_to_chat(chat_id: int, payload, with_caption: bool = True):
    if not isinstance(payload, dict):
        return await bot.send_message(chat_id, str(payload))
    ptype = payload.get("type")
    if ptype == "photo":
        return await bot.send_photo(chat_id, payload.get("file_id"), caption=payload.get("caption") if with_caption else None)
    elif ptype == "video":
        return await bot.send_video(chat_id, payload.get("file_id"), caption=payload.get("caption") if with_caption else None)
    elif ptype == "document":
        return await bot.send_document(chat_id, payload.get("file_id"), caption=payload.get("caption") if with_caption else None)
    elif ptype == "audio":
        return await bot.send_audio(chat_id, payload.get("file_id"), caption=payload.get("caption") if with_caption else None)
    elif ptype == "voice":
        return await bot.send_voice(chat_id, payload.get("file_id"), caption=payload.get("caption") if with_caption else None)
    else:
        return await bot.send_message(chat_id, payload.get("text") or payload.get("caption") or "")

def record_paid_order(user_id: int, service: str):
    data = load_users()
    data["orders"].append({
        "user_id": int(user_id),
        "service": service,
        "paid_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })
    save_users(data)

def build_stats_text() -> str:
    data = load_users()
    orders = data.get("orders", [])
    total_paid = len(orders)
    users_total = len(data.get("users", {}))

    # unique users per service
    svc_users: dict[str, set[int]] = {}
    for o in orders:
        svc = o.get("service", "unknown")
        svc_users.setdefault(svc, set()).add(int(o.get("user_id")))

    slide_users = len(svc_users.get("slide", set()))
    video_users = len(svc_users.get("video", set()))

    lines = [
        "📊 Statistika",
        "",
        f"👥 Umumiy userlar: {users_total}",
        f"✅ To'lov tasdiqlangan buyurtmalar: {total_paid}",
        "",
        "Xizmatlar bo'yicha (unikal userlar):",
        f"📝 Slayd: {slide_users}",
        f"🎥 AI Video: {video_users}",
    ]
    return "\n".join(lines)

def _rtf_escape(text: str) -> str:
    out = []
    for ch in text:
        code = ord(ch)
        if ch in "\\{}":
            out.append("\\" + ch)
        elif code > 127:
            # RTF unicode escape
            out.append(f"\\u{code}?")
        else:
            out.append(ch)
    return "".join(out)

def build_users_rtf(users: dict) -> str:
    header = "{\\rtf1\\ansi\\deff0{\\fonttbl{\\f0 Arial;}}\\f0\\fs22 "
    lines = ["Userlar ro'yxati\\par", "\\par"]
    # sort by status
    items = sorted(users.items(), key=lambda kv: kv[1].get("status", 0))
    for uid, u in items:
        created_at = u.get("created_at", "-")
        lines.append(_rtf_escape(f"Tartib raqami: {u.get('status','-')}") + "\\par")
        lines.append(_rtf_escape(f"Ism: {u.get('name','-')}") + "\\par")
        lines.append(_rtf_escape(f"Yosh: {u.get('age','-')}") + "\\par")
        lines.append(_rtf_escape(f"Viloyat: {u.get('region','-')}") + "\\par")
        lines.append(_rtf_escape(f"Telefon: {u.get('phone','-')}") + "\\par")
        lines.append(_rtf_escape(f"ID: {uid}") + "\\par")
        lines.append(_rtf_escape(f"Ro'yxatdan o'tgan sana/soat: {created_at}") + "\\par")
        lines.append("\\par")
    return header + "".join(lines) + "}"

# ===================== STATES =====================
class SubState(StatesGroup):
    waiting_check = State()

class RegState(StatesGroup):
    name = State()
    age = State()
    region = State()
    phone = State()

class SlideState(StatesGroup):
    topic = State()
    pages = State()
    colors = State()
    text_amount = State()
    deadline = State()
    format = State()
    payment = State()

class VideoState(StatesGroup):
    menu = State()
    img_to_video_image = State()
    img_to_video_prompt = State()
    img_to_video_payment = State()
    image_gen_prompt = State()
    image_gen_format = State()
    image_gen_payment = State()
    custom_prompt = State()
    custom_payment = State()

class AdminSendState(StatesGroup):
    file = State()
    user_number = State()
    comment = State()

class AdminBroadcastState(StatesGroup):
    message = State()

class BilimUlashUserState(StatesGroup):
    user_number = State()

class BilimUlashAdminState(StatesGroup):
    add_number = State()
    add_message = State()
    del_number = State()

class KinoUserState(StatesGroup):
    user_number = State()

class KinoAdminState(StatesGroup):
    add_number = State()
    add_message = State()
    del_number = State()

class BookUserState(StatesGroup):
    menu = State()
    number_lookup = State()

class BookAdminState(StatesGroup):
    add_direction = State()
    add_book_cover = State()
    add_book_info = State()
    add_book_file = State()
    add_book_confirm = State()
    num_cover = State()
    num_info = State()
    num_file = State()
    num_number = State()
    num_confirm = State()
    num_delete_number = State()

# ===================== KEYBOARDS =====================
def menu_kb(is_admin: bool = False):
    rows = [
        [KeyboardButton(text="🧑‍💼 Admin bilan bog'lanish")],
        [KeyboardButton(text="📝 Slayd buyurtma"), KeyboardButton(text="🎥 AI Video")],
        [KeyboardButton(text="🎬 Kino kodlari"), KeyboardButton(text="📚 Foydali kodlar")],
        [KeyboardButton(text="📖 Kitoblar")],
        [KeyboardButton(text="🤖 Bot yaratib berish")],
    ]
    if is_admin:
        rows.append([KeyboardButton(text="⚙️ Admin panel")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)

def sub_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Obuna bo'lish", url="https://t.me/bilimulash_kanal")],
        [InlineKeyboardButton(text="Obuna boldim", callback_data="check_sub")],
    ])

def back_kb(callback_data: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Orqaga qaytish", callback_data=callback_data)],
    ])

def admin_panel_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Statistika", callback_data="admin_stats")],
        [InlineKeyboardButton(text="🧾 User info", callback_data="admin_users_export")],
        [InlineKeyboardButton(text="📣 Hammaga xabar", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="📚 Kitoblar", callback_data="admin_books_menu")],
        [InlineKeyboardButton(text="🔢 Raqamlar", callback_data="admin_numbers")],
        [InlineKeyboardButton(text="🎬 Kino raqam", callback_data="admin_kino_numbers")],
        [InlineKeyboardButton(text="📦 Buyurtma tayyor", callback_data="admin_order_ready")],
        [InlineKeyboardButton(text="⬅️ Orqaga qaytish", callback_data="admin_back_main")],
    ])

def admin_numbers_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Raqam qo'shish", callback_data="admin_numbers_add")],
        [InlineKeyboardButton(text="🗑️ Raqam o'chirish", callback_data="admin_numbers_delete")],
        [InlineKeyboardButton(text="⬅️ Orqaga qaytish", callback_data="admin_back_main")],
    ])

def admin_kino_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Raqam qo'shish", callback_data="admin_kino_add")],
        [InlineKeyboardButton(text="🗑️ Raqam o'chirish", callback_data="admin_kino_delete")],
        [InlineKeyboardButton(text="⬅️ Orqaga qaytish", callback_data="admin_back_main")],
    ])

def books_user_home_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📚 Online Kitoblar", callback_data="books_user_online")],
        [InlineKeyboardButton(text="🎧 Audio kitoblar", callback_data="books_user_audio")],
        [InlineKeyboardButton(text="🔢 Raqam orqali kitob topish", callback_data="books_user_number")],
        [InlineKeyboardButton(text="⬅️ Orqaga qaytish", callback_data="books_back_main")],
    ])

def books_user_categories_kb(section: str):
    rows = []
    for idx, cat_name in enumerate(list_book_categories(section)):
        rows.append([InlineKeyboardButton(text=category_title(cat_name), callback_data=f"books_user_cat_{section}_{idx}")])
    rows.append([InlineKeyboardButton(text="⬅️ Orqaga qaytish", callback_data="books_back_user_home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def admin_books_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📂 Barchasi", callback_data="admin_books_all")],
        [InlineKeyboardButton(text="🔢 Raqamli kitob", callback_data="admin_books_numbered_menu")],
        [InlineKeyboardButton(text="➕ Kitob qo'shish", callback_data="admin_books_add_book")],
        [InlineKeyboardButton(text="➕ Yo'nalish qo'shish", callback_data="admin_books_add_direction")],
        [InlineKeyboardButton(text="⬅️ Orqaga qaytish", callback_data="admin_back_main")],
    ])

def admin_books_section_kb(prefix: str, back_callback: str = "admin_books_menu"):
    rows = [
        [InlineKeyboardButton(text="📚 Online Kitoblar", callback_data=f"{prefix}_online")],
        [InlineKeyboardButton(text="🎧 Audio kitoblar", callback_data=f"{prefix}_audio")],
        [InlineKeyboardButton(text="⬅️ Orqaga qaytish", callback_data=back_callback)],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)

def admin_books_categories_kb(section: str, prefix: str, back_callback: str):
    rows = []
    for idx, cat_name in enumerate(list_book_categories(section)):
        rows.append([InlineKeyboardButton(text=category_title(cat_name), callback_data=f"{prefix}_{section}_{idx}")])
    rows.append([InlineKeyboardButton(text="⬅️ Orqaga qaytish", callback_data=back_callback)])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def section_title(section: str) -> str:
    return "📚 Online Kitoblar" if section == "online" else "🎧 Audio kitoblar"

def book_short_title(book_item: dict) -> str:
    info = (book_item.get("info") or "").strip()
    if not info:
        return "Nomi ko'rsatilmagan"
    first_line = info.splitlines()[0].strip()
    return first_line[:50] + ("..." if len(first_line) > 50 else "")

def category_title(name: str) -> str:
    return f"{BOOK_CATEGORY_EMOJI.get(name, '📘')} {name}"

def _payload_to_input_media(payload: dict, caption: str | None = None):
    ptype = payload.get("type")
    media = payload.get("file_id")
    if not media:
        return None
    if ptype == "photo":
        return InputMediaPhoto(media=media, caption=caption)
    if ptype == "document":
        return InputMediaDocument(media=media, caption=caption)
    if ptype == "audio":
        return InputMediaAudio(media=media, caption=caption)
    if ptype == "video":
        return InputMediaVideo(media=media, caption=caption)
    return None

async def send_book_item_block(chat_id: int, book_item: dict, preview: bool = False):
    number = book_item.get("lookup_number")
    info = (book_item.get("info") or "").strip()
    if preview:
        prefix = "📚 Yangi kitob preview"
    else:
        prefix = f"📚 Kitob #{number}" if number else "📚 Kitob"
    caption = f"{prefix}\n\n{info}" if info else prefix
    cover = book_item.get("cover")
    file_payload = book_item.get("file")

    if isinstance(cover, dict) and isinstance(file_payload, dict):
        m1 = _payload_to_input_media(cover, caption=caption)
        m2 = _payload_to_input_media(file_payload, caption=None)
        if m1 and m2:
            try:
                msgs = await bot.send_media_group(chat_id, media=[m1, m2])
                return [m.message_id for m in msgs]
            except Exception:
                pass

    if isinstance(file_payload, dict):
        p = dict(file_payload)
        if p.get("type") in {"photo", "document", "audio", "video", "voice"}:
            p["caption"] = caption
            m = await send_payload_to_chat(chat_id, p, with_caption=True)
            return [m.message_id] if hasattr(m, "message_id") else []

    if isinstance(cover, dict):
        p = dict(cover)
        p["caption"] = caption
        m = await send_payload_to_chat(chat_id, p, with_caption=True)
        return [m.message_id] if hasattr(m, "message_id") else []

    m = await bot.send_message(chat_id, caption)
    return [m.message_id]

# ===================== START + BANNER + OBUNA =====================
@dp.message(F.text == "/start")
async def start(msg: Message, state: FSMContext):
    await state.clear()
    # Agar allaqachon ro'yxatdan o'tgan bo'lsa - menyu
    if is_registered(msg.from_user.id):
        await msg.answer("Xizmatni tanlang 👇", reply_markup=menu_kb(msg.from_user.id == ADMIN_ID))
        return
    # Banner (bot nima qiladi)
    await msg.answer(BANNER, parse_mode="Markdown")
    # Majburiy obuna
    await msg.answer(
        " Botdan to'liq foydalanish uchun kanalga obuna bo'ling:",
        reply_markup=sub_kb()
    )
    await state.set_state(SubState.waiting_check)


# ===================== ADMIN PANEL (START dan keyin, boshqa handlerlardan oldin) =====================
@dp.message((F.text == "/admin") | (F.text.contains("Admin panel")))
async def admin_panel_first(msg: Message, state: FSMContext):
    """Admin panel — faqat admin uchun."""
    if msg.from_user.id != ADMIN_ID:
        return
    await state.clear()
    await msg.answer(
        "⚙️ Admin panel\n\nQuyidagi tugmalardan birini tanlang:",
        reply_markup=admin_panel_kb()
    )

async def check_subscription(user_id: int) -> bool:
    try:
        m = await bot.get_chat_member(chat_id=CHANNEL, user_id=user_id)
        return m.status in (ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR)
    except Exception:
        return False

@dp.callback_query(SubState.waiting_check, F.data == "check_sub")
async def check_sub_cb(call: CallbackQuery, state: FSMContext):
    if await check_subscription(call.from_user.id):
        await call.message.edit_text("✅ Obuna tasdiqlandi! Endi ro'yxatdan o'ting.")
        await call.message.answer("👤  Ism va familiyangizni yozing:", reply_markup=back_kb("reg_back_sub"))
        await state.set_state(RegState.name)
    else:
        await call.answer("Siz kanalga obuna bo'lmagansiz. Avval obuna bo'ling.", show_alert=True)

# ===================== RO'YXATDAN O'TISH (Orqaga qaytish) =====================
# reg_router ga yoziladi — dp.include_router(reg_router) birinchi, shuning uchun birinchi tekshiriladi
@reg_router.callback_query(F.data.startswith("reg_back_"))
async def reg_back_any(call: CallbackQuery, state: FSMContext):
    await delete_last_user_message(state)
    await call.answer()  # darhol tugmani "yuklangan" holatdan chiqarish
    data = call.data.strip()

    if data == "reg_back_sub":
        await state.clear()
        await state.set_state(SubState.waiting_check)
        text = " Botdan to'liq foydalanish uchun kanalga obuna bo'ling:"
        markup = sub_kb()
    elif data == "reg_back_name":
        await state.update_data(age=None)
        await state.set_state(RegState.name)
        text = "👤  Ism va familiyangizni yozing:"
        markup = back_kb("reg_back_sub")
    elif data == "reg_back_age":
        await state.update_data(region=None)
        await state.set_state(RegState.age)
        text = "🎂  Yoshingiz nechida?"
        markup = back_kb("reg_back_name")
    elif data == "reg_back_region":
        await state.update_data(phone=None)
        await state.set_state(RegState.region)
        text = "📍  Qaysi viloyatdan?"
        markup = back_kb("reg_back_age")
    else:
        return

    try:
        await call.message.delete()
    except Exception:
        pass
    await call.message.answer(text, reply_markup=markup)


dp.include_router(priority_router)
dp.include_router(reg_router)  # ro'yxat orqaga qaytish birinchi tekshirilsin

# Anti-flood
dp.message.middleware(ThrottleMiddleware(min_interval=0.7, warn_interval=2.0))

# ===================== DEBUG =====================
@priority_router.message(F.text == "/ping")
async def debug_ping(msg: Message):
    await msg.answer("pong")

@dp.message(RegState.name)
async def reg_name(msg: Message, state: FSMContext):
    await record_last_user_message(msg, state)
    value = get_answer_value(msg)
    if not value:
        await msg.answer("Iltimos, javob yuboring.", reply_markup=back_kb("reg_back_name"))
        return
    await state.update_data(name=value)
    await msg.answer("🎂  Yoshingiz nechida?", reply_markup=back_kb("reg_back_name"))
    await state.set_state(RegState.age)

@dp.message(RegState.age)
async def reg_age(msg: Message, state: FSMContext):
    await record_last_user_message(msg, state)
    value = get_answer_value(msg)
    if not value:
        await msg.answer("Iltimos, javob yuboring.", reply_markup=back_kb("reg_back_age"))
        return
    await state.update_data(age=value)
    await msg.answer("📍  Qaysi viloyatdan?", reply_markup=back_kb("reg_back_age"))
    await state.set_state(RegState.region)

@dp.message(RegState.region)
async def reg_region(msg: Message, state: FSMContext):
    await record_last_user_message(msg, state)
    value = get_answer_value(msg)
    if not value:
        await msg.answer("Iltimos, javob yuboring.", reply_markup=back_kb("reg_back_region"))
        return
    await state.update_data(region=value)
    await msg.answer("📞  Telefon raqamingizni yozing:", reply_markup=back_kb("reg_back_region"))
    await state.set_state(RegState.phone)

@dp.message(RegState.phone)
async def reg_phone(msg: Message, state: FSMContext):
    await record_last_user_message(msg, state)
    data = await state.get_data()
    name = data["name"]
    age = data["age"]
    region = data["region"]
    phone = get_answer_value(msg)
    if not phone:
        await msg.answer("Iltimos, javob yuboring.", reply_markup=back_kb("reg_back_region"))
        return
    status = register_user(msg.from_user.id, name, age, region, phone)
    await state.clear()
    await msg.answer(
        f"🎉  Tabriklaymiz! Ro'yxatdan o'tdingiz.\n"
        f"📋 Sizning tartib raqamingiz: **{status}**\n\n"
        "? Endi xizmatlardan to'liq foydalanishingiz mumkin.",
        parse_mode="Markdown",
        reply_markup=menu_kb(msg.from_user.id == ADMIN_ID)
    )
    # Ma'lumotlarni @xolboyevv77 ga yuborish
    await bot.send_message(
        INFO_ADMIN_ID,
        f"🆕 Yangi ro'yxatdan o'tgan:\n\n"
        f"👤 Ism: {name}\n"
        f"🎂 Yosh: {age}\n"
        f"📍 Viloyat: {region}\n"
        f"📞 Tel: {phone}\n"
        f"🆔 User: @{msg.from_user.username or msg.from_user.id} (ID: {msg.from_user.id})\n"
        f"📋 Tartib raqami: {status}"
    )

# ===================== XIZMATLAR (faqat ro'yxatdan o'tganlar) =====================
# ====================================================
# ===================== FOYDALI KODLAR ==================
# ====================================================
@dp.message(F.text.contains("Foydali kodlar") | F.text.contains("Bilim Ulash"))
async def bilim_ulash_start(msg: Message, state: FSMContext):
    if not is_registered(msg.from_user.id):
        await msg.answer("🔒 Avval ro'yxatdan o'ting. /start bosing.", reply_markup=sub_kb())
        return
    await state.clear()
    await msg.answer("📋 Raqamni kiriting:", reply_markup=back_kb("back_bilim_menu"))
    await state.set_state(BilimUlashUserState.user_number)

@dp.message(BilimUlashUserState.user_number)
async def bilim_ulash_send(msg: Message, state: FSMContext):
    await record_last_user_message(msg, state)
    value = get_answer_value(msg)
    if not value.isdigit():
        await msg.answer("Raqamni to'g'ri kiriting (faqat son):", reply_markup=back_kb("back_bilim_menu"))
        return
    num = int(value)
    content = get_bilim_message(num)
    if content is None:
        await msg.answer("Bu raqam bo'yicha ma'lumot topilmadi. Qayta kiriting:", reply_markup=back_kb("back_bilim_menu"))
        return
    if isinstance(content, list):
        for item in content:
            await send_payload(msg, item)
    else:
        await send_payload(msg, content)
    await msg.answer("Xizmatni tanlang 👇", reply_markup=menu_kb(msg.from_user.id == ADMIN_ID))
    await state.clear()

# ===================== KINO KODLARI ==================
@dp.message(F.text.contains("Kino kodlari"))
async def kino_start(msg: Message, state: FSMContext):
    if not is_registered(msg.from_user.id):
        await msg.answer("🔒 Avval ro'yxatdan o'ting. /start bosing.", reply_markup=sub_kb())
        return
    await state.clear()
    await msg.answer("🎬 Kino raqamini kiriting:", reply_markup=back_kb("back_kino_menu"))
    await state.set_state(KinoUserState.user_number)

@dp.message(KinoUserState.user_number)
async def kino_send(msg: Message, state: FSMContext):
    await record_last_user_message(msg, state)
    value = get_answer_value(msg)
    if not value.isdigit():
        await msg.answer("Raqamni to'g'ri kiriting (faqat son):", reply_markup=back_kb("back_kino_menu"))
        return
    num = int(value)
    content = get_kino_message(num)
    if content is None:
        await msg.answer("Bu raqam bo'yicha ma'lumot topilmadi. Qayta kiriting:", reply_markup=back_kb("back_kino_menu"))
        return
    if isinstance(content, list):
        for item in content:
            await send_payload(msg, item)
    else:
        await send_payload(msg, content)
    await msg.answer("Xizmatni tanlang 👇", reply_markup=menu_kb(msg.from_user.id == ADMIN_ID))
    await state.clear()

@dp.callback_query(F.data == "back_kino_menu")
async def back_kino_menu(call: CallbackQuery, state: FSMContext):
    await delete_last_user_message(state)
    await state.clear()
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.message.answer("Xizmatni tanlang 👇", reply_markup=menu_kb(call.from_user.id == ADMIN_ID))
    await call.answer()

@dp.callback_query(F.data == "back_bilim_menu")
async def back_bilim_menu(call: CallbackQuery, state: FSMContext):
    await delete_last_user_message(state)
    await state.clear()
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.message.answer("Xizmatni tanlang 👇", reply_markup=menu_kb(call.from_user.id == ADMIN_ID))
    await call.answer()

# ===================== KITOBLAR ==================
@dp.message(StateFilter(None), F.text.contains("Kitoblar"))
async def books_start(msg: Message, state: FSMContext):
    if not is_registered(msg.from_user.id):
        await msg.answer("🔒 Avval ro'yxatdan o'ting. /start bosing.", reply_markup=sub_kb())
        return
    await state.clear()
    await state.set_state(BookUserState.menu)
    await msg.answer("📚 Kitoblar bo'limi:", reply_markup=books_user_home_kb())

@dp.callback_query(F.data == "books_back_main")
async def books_back_main(call: CallbackQuery, state: FSMContext):
    await delete_last_user_message(state)
    await state.clear()
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.message.answer("Xizmatni tanlang 👇", reply_markup=menu_kb(call.from_user.id == ADMIN_ID))
    await call.answer()

@dp.callback_query(F.data == "books_back_user_home")
async def books_back_user_home(call: CallbackQuery, state: FSMContext):
    await delete_last_user_message(state)
    await state.set_state(BookUserState.menu)
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.message.answer("📚 Kitoblar bo'limi:", reply_markup=books_user_home_kb())
    await call.answer()

@dp.callback_query(F.data == "books_user_online")
async def books_user_online(call: CallbackQuery, state: FSMContext):
    await delete_last_user_message(state)
    await state.set_state(BookUserState.menu)
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.message.answer(
        "📚 Online kitoblar yo'nalishini tanlang:",
        reply_markup=books_user_categories_kb("online")
    )
    await call.answer()

@dp.callback_query(F.data == "books_user_audio")
async def books_user_audio(call: CallbackQuery, state: FSMContext):
    await delete_last_user_message(state)
    await state.set_state(BookUserState.menu)
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.message.answer(
        "🎧 Audio kitoblar yo'nalishini tanlang:",
        reply_markup=books_user_categories_kb("audio")
    )
    await call.answer()

@dp.callback_query(F.data == "books_user_number")
async def books_user_number(call: CallbackQuery, state: FSMContext):
    await delete_last_user_message(state)
    await state.set_state(BookUserState.number_lookup)
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.message.answer(
        "🔢 Raqamli kitob raqamini yuboring:",
        reply_markup=back_kb("books_back_user_home")
    )
    await call.answer()

@dp.callback_query(F.data.startswith("books_user_cat_"))
async def books_user_category(call: CallbackQuery, state: FSMContext):
    await delete_last_user_message(state)
    parts = call.data.split("_")
    if len(parts) < 5:
        await call.answer()
        return
    section = parts[3]
    try:
        idx = int(parts[4])
    except ValueError:
        await call.answer()
        return
    category = get_book_category_by_index(section, idx)
    if not category:
        await call.answer()
        return

    topics = BOOK_CATEGORY_TOPICS.get(category, [])
    topic_lines = "\n".join([f"• {t}" for t in topics]) if topics else "• Mavzu qo'shilmagan"
    books = list_books_in_category(section, category)

    try:
        await call.message.delete()
    except Exception:
        pass

    header = (
        f"{section_title(section)}\n"
        f"{category_title(category)}\n\n"
        f"{topic_lines}\n\n"
        f"Jami kitob: {len(books)} ta"
    )
    await call.message.answer(header)

    if books:
        for item in books:
            await send_book_item_block(call.from_user.id, item)
            await asyncio.sleep(0.05)
    else:
        await call.message.answer("Hozircha bu yo'nalishda kitob yo'q.")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔢 Raqam orqali topish", callback_data="books_user_number")],
        [InlineKeyboardButton(text="⬅️ Orqaga qaytish", callback_data=f"books_user_{section}")],
        [InlineKeyboardButton(text="🏠 Menyuga qaytish", callback_data="books_back_main")],
    ])
    await call.message.answer("Kerakli kitobni raqam orqali ham topishingiz mumkin.", reply_markup=kb)
    await state.set_state(BookUserState.number_lookup)
    await state.update_data(book_last_section=section, book_last_category=category)
    await call.answer()

@dp.message(BookUserState.number_lookup)
async def books_number_lookup(msg: Message, state: FSMContext):
    await record_last_user_message(msg, state)
    value = get_answer_value(msg)
    if not value.isdigit():
        await msg.answer("Raqamni to'g'ri kiriting (faqat son):", reply_markup=back_kb("books_back_user_home"))
        return

    number = int(value)
    book_item = find_book_by_number(number)
    if not book_item:
        await msg.answer("Bu raqam bo'yicha kitob topilmadi. Qayta kiriting:", reply_markup=back_kb("books_back_user_home"))
        return

    section = book_item.get("section")
    category = book_item.get("category")
    if section and category:
        await msg.answer(f"✅ Topildi: {section_title(section)} / {category_title(category)}")
    else:
        await msg.answer("✅ Topildi.")
    display_item = dict(book_item)
    display_item["lookup_number"] = number
    await send_book_item_block(msg.chat.id, display_item)

    await msg.answer(
        "Yana kitob raqamini yuborishingiz mumkin.",
        reply_markup=back_kb("books_back_user_home")
    )

@dp.message(BookUserState.menu)
async def books_menu_fallback(msg: Message, state: FSMContext):
    await record_last_user_message(msg, state)
    await msg.answer("Tanlovni tugmalar orqali qiling.", reply_markup=books_user_home_kb())

# ===================== SLAYD =========================
# ====================================================
@dp.message(F.text.contains("Slayd buyurtma"))
async def slide_start(msg: Message, state: FSMContext):
    if not is_registered(msg.from_user.id):
        await msg.answer("🔒 Avval ro'yxatdan o'ting. /start bosing.", reply_markup=sub_kb())
        return
    await msg.answer("📌  Slayd mavzusini yozing:", reply_markup=back_kb("back_to_menu"))
    await state.set_state(SlideState.topic)

@dp.message(SlideState.topic)
async def slide_topic(msg: Message, state: FSMContext):
    await record_last_user_message(msg, state)
    value = get_answer_value(msg)
    if not value:
        await msg.answer("Iltimos, javob yuboring.", reply_markup=back_kb("back_to_menu"))
        return
    await state.update_data(topic=value)
    await msg.answer("📄  Necha varaq bo'lsin?", reply_markup=back_kb("back_slide_topic"))
    await state.set_state(SlideState.pages)

@dp.message(SlideState.pages)
async def slide_pages(msg: Message, state: FSMContext):
    await record_last_user_message(msg, state)
    value = get_answer_value(msg)
    if not value:
        await msg.answer("Iltimos, javob yuboring.", reply_markup=back_kb("back_slide_topic"))
        return
    await state.update_data(pages=value)
    await msg.answer("🎨  Qaysi ranglar ko'p bo'lsin?", reply_markup=back_kb("back_slide_pages"))
    await state.set_state(SlideState.colors)

@dp.message(SlideState.colors)
async def slide_colors(msg: Message, state: FSMContext):
    await record_last_user_message(msg, state)
    value = get_answer_value(msg)
    if not value:
        await msg.answer("Iltimos, javob yuboring.", reply_markup=back_kb("back_slide_pages"))
        return
    await state.update_data(colors=value)
    await msg.answer("📝  Matn qanchalik ko'p bo'lsin? (kam / o'rtacha / ko'p)", reply_markup=back_kb("back_slide_colors"))
    await state.set_state(SlideState.text_amount)

@dp.message(SlideState.text_amount)

async def slide_text(msg: Message, state: FSMContext):
    await record_last_user_message(msg, state)
    value = get_answer_value(msg)
    if not value:
        await msg.answer("Iltimos, javob yuboring.", reply_markup=back_kb("back_slide_colors"))
        return
    await state.update_data(text_amount=value)
    await msg.answer("⏰ ? Qancha vaqtda tayyor bo'lsin? (minimal 2 soat)", reply_markup=back_kb("back_slide_text"))
    await state.set_state(SlideState.deadline)

@dp.message(SlideState.deadline)
async def slide_deadline(msg: Message, state: FSMContext):
    await record_last_user_message(msg, state)
    value = get_answer_value(msg)
    if not value:
        await msg.answer("Iltimos, javob yuboring.", reply_markup=back_kb("back_slide_text"))
        return
    await state.update_data(deadline=value)
    await msg.answer("📂  Qaysi formatda bo'lsin? (pdf / ppt / word / boshqasi)", reply_markup=back_kb("back_slide_deadline"))
    await state.set_state(SlideState.format)

@dp.message(SlideState.format)
async def slide_format(msg: Message, state: FSMContext):
    await record_last_user_message(msg, state)
    value = get_answer_value(msg)
    if not value:
        await msg.answer("Iltimos, javob yuboring.", reply_markup=back_kb("back_slide_deadline"))
        return
    price = random.choice(range(15000, 20000 + 1, 1000))
    await state.update_data(format=value, price=price)
    await msg.answer(
        f"💰  To'lov: {price} so'm\n\n"
        f"💳  Karta: {CARD_NUMBER}\n\n"
        "⚠️  To'lov qilganingizdan keyin chekini yuboring.\n"
        "❌ ? Cheksiz to'lov qabul qilinmaydi.",
        reply_markup=back_kb("back_slide_format")
    )
    await state.set_state(SlideState.payment)

@dp.message(SlideState.payment, F.photo)
async def slide_payment_photo(msg: Message, state: FSMContext):
    await record_last_user_message(msg, state)
    await slide_payment_any(msg, state, msg.photo[-1].file_id)

@dp.message(SlideState.payment, F.document)
async def slide_payment_doc(msg: Message, state: FSMContext):
    await record_last_user_message(msg, state)
    await slide_payment_any(msg, state, None, msg.document.file_id)

@dp.message(SlideState.payment)
async def slide_payment_other(msg: Message, state: FSMContext):
    await record_last_user_message(msg, state)
    await msg.answer(" Chekni rasm yoki hujjat ko'rinishida yuboring.")

async def slide_payment_any(msg: Message, state: FSMContext, photo_id=None, doc_id=None):
    data = await state.get_data()
    status = get_user_status(msg.from_user.id)

    status_msg = await msg.answer(
        "⏳ ? Admin tekshirmoqda. Ish boshlanganda sizga xabar beramiz."
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="➕", callback_data=f"ok_slide_{msg.from_user.id}_{status_msg.message_id}"),
            InlineKeyboardButton(text="➖", callback_data=f"no_slide_{msg.from_user.id}_{status_msg.message_id}"),
        ]
    ])

    text = (
        f"🆕 SLAYD BUYURTMA | 📋 #{status}\n\n"
        f"👤 @{msg.from_user.username or msg.from_user.id}\n"
        f"📌 Mavzu: {data['topic']}\n"
        f"📄 Varaq: {data['pages']}\n"
        f"🎨 Ranglar: {data['colors']}\n"
        f"📝 Matn: {data['text_amount']}\n"
        f"⏰ Muddat: {data['deadline']}\n"
        f"📂 Format: {data['format']}\n"
        f"💰 {data['price']} so'm"
    )

    if photo_id:
        await bot.send_photo(ADMIN_ID, photo_id, caption=text, reply_markup=kb)
    elif doc_id:
        await bot.send_document(ADMIN_ID, doc_id, caption=text, reply_markup=kb)
    else:
        await bot.send_message(ADMIN_ID, text + "\n\n⚠️ Chek rasm yoki hujjat ko'rinishida yuborilmadi", reply_markup=kb)

    await state.clear()

# ===================== USER BACK HANDLERS (Slayd) =====================
@dp.callback_query(F.data.startswith("back_slide_"))
async def back_slide_handlers(call: CallbackQuery, state: FSMContext):
    await delete_last_user_message(state)
    data = call.data
    await call.answer()
    
    if data == "back_slide_topic":
        await state.set_state(SlideState.topic)
        try:
            await call.message.delete()
        except Exception:
            pass
        await call.message.answer("📌  Slayd mavzusini yozing:", reply_markup=back_kb("back_to_menu"))
    
    elif data == "back_slide_pages":
        await state.set_state(SlideState.pages)
        try:
            await call.message.delete()
        except Exception:
            pass
        await call.message.answer("📄  Necha varaq bo'lsin?", reply_markup=back_kb("back_slide_topic"))
        
    elif data == "back_slide_colors":
        await state.set_state(SlideState.colors)
        try:
            await call.message.delete()
        except Exception:
            pass
        await call.message.answer("  Qaysi ranglar ko'p bo'lsin?", reply_markup=back_kb("back_slide_pages"))
        
    elif data == "back_slide_text":

        await state.set_state(SlideState.text_amount)
        try:
            await call.message.delete()
        except Exception:
            pass
        await call.message.answer("📝  Matn qanchalik ko'p bo'lsin? (kam / o'rtacha / ko'p)", reply_markup=back_kb("back_slide_colors"))
        
    elif data == "back_slide_deadline":
        await state.set_state(SlideState.deadline)
        try:
            await call.message.delete()
        except Exception:
            pass
        await call.message.answer("⏰ ? Qancha vaqtda tayyor bo'lsin? (minimal 2 soat)", reply_markup=back_kb("back_slide_text"))
    
    elif data == "back_slide_format":
        await state.set_state(SlideState.format)
        try:
            await call.message.delete()
        except Exception:
            pass
        await call.message.answer("📂  Qaysi formatda bo'lsin? (pdf / ppt / word / boshqasi)", reply_markup=back_kb("back_slide_deadline"))

@dp.callback_query(F.data == "back_to_menu")
async def back_to_main_menu(call: CallbackQuery, state: FSMContext):
    await delete_last_user_message(state)
    await state.clear()
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.message.answer("Xizmatni tanlang 👇", reply_markup=menu_kb(call.from_user.id == ADMIN_ID))

# ===================== ADMIN CONTACT =====================
@priority_router.message(F.text.contains("Admin bilan bog'lanish") | F.text.contains("Admin bilan boglanish"))
async def admin_contact(msg: Message, state: FSMContext):
    await delete_last_user_message(state)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=" Adminga yozish", url=f"tg://user?id={ADMIN_ID}")]
    ])
    await msg.answer(
        " Taklif yoki muammo bo'lsa, adminga murojaat qiling.",
        reply_markup=kb
    )

# ===================== BOT YARATISH =====================
@priority_router.message(F.text.contains("Bot yaratib berish"))
async def bot_create_contact(msg: Message, state: FSMContext):
    await delete_last_user_message(state)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=" Adminga yozish", url=f"tg://user?id={ADMIN_ID}")]
    ])
    await msg.answer(
        " Bot yaratish bo'yicha adminga yozing.",
        reply_markup=kb
    )


# ====================================================
# ====================================================
# ===================== AI VIDEO =====================
# ====================================================
@dp.message(F.text.contains("AI Video"))
async def ai_video(msg: Message, state: FSMContext):
    if not is_registered(msg.from_user.id):
        await msg.answer("🔒 Avval ro'yxatdan o'ting. /start bosing.", reply_markup=sub_kb())
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🖼️ Rasmni video qilish", callback_data="ai_img_to_video")],
        [InlineKeyboardButton(text="🎨 Rasm yaratish", callback_data="ai_image_gen")],
        [InlineKeyboardButton(text="🎬 Men hohlagan video", callback_data="ai_custom_video")],
    ])
    await state.set_state(VideoState.menu)
    await msg.answer(
        "🎬 AI video xizmati.\n📌 Max 10 soniya.\n\n"
        "👇 Xizmat turini tanlang:",
        reply_markup=kb
    )

@dp.callback_query(F.data == "ai_img_to_video")
async def ai_img_to_video(call: CallbackQuery, state: FSMContext):
    await delete_last_user_message(state)
    await state.clear()
    await state.set_state(VideoState.img_to_video_image)
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.message.answer("? Video yaratmoqchi bo'lgan rasmni yuboring:", reply_markup=back_kb("back_ai_menu"))
    await call.answer()

@dp.callback_query(F.data == "ai_image_gen")
async def ai_image_gen(call: CallbackQuery, state: FSMContext):
    await delete_last_user_message(state)
    await state.clear()
    await state.set_state(VideoState.image_gen_prompt)
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.message.answer(
        " Yaratmoqchi bo'lgan rasmingizni shunchaki tasvirlab bering."
        "Misol uchun: bir yosh yigit korzinka supermarketi yonida qo'lida kamera bilan turibdi va futbolkasida instagram akkaunti nomi yozilgan..."
        "Shu kabi hohlagan narsangizni yozing, sifatli rasm tayyorlash mendan :)",
        reply_markup=back_kb("back_ai_menu")
    )
    await call.answer()

@dp.callback_query(F.data == "ai_custom_video")
async def ai_custom_video(call: CallbackQuery, state: FSMContext):
    await delete_last_user_message(state)
    await state.clear()
    try:
        await call.message.delete()
    except Exception:
        pass
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Adminga yozish", url=f"tg://user?id={INFO_ADMIN_ID}")]
    ])
    await call.message.answer(
        "Siz o'zingiz hohlagandek video tayyorlash uchun adminga yozing.",
        reply_markup=kb
    )
    await call.answer()

# -------- Rasmni video qilish --------
@dp.message(VideoState.img_to_video_image, F.photo)
async def ai_img_to_video_image(msg: Message, state: FSMContext):
    await record_last_user_message(msg, state)
    await state.update_data(image_file_id=msg.photo[-1].file_id)
    await msg.answer(
        " Sizga qanaqa video kerak? Shunchaki yozing."
        "Misol uchun: rasmdagi odam nimadir deb gapirsin.",
        reply_markup=back_kb("back_ai_image")
    )
    await state.set_state(VideoState.img_to_video_prompt)

@dp.message(VideoState.img_to_video_image)
async def ai_img_to_video_image_other(msg: Message, state: FSMContext):
    await record_last_user_message(msg, state)
    await msg.answer("Iltimos, rasm yuboring.", reply_markup=back_kb("back_ai_menu"))

@dp.message(VideoState.img_to_video_prompt)
async def ai_img_to_video_prompt(msg: Message, state: FSMContext):
    await record_last_user_message(msg, state)
    value = get_answer_value(msg)
    if not value:
        await msg.answer("Iltimos, javob yuboring.", reply_markup=back_kb("back_ai_image"))
        return
    price = random.choice(range(15000, 25001, 1000))
    await state.update_data(kind="img_to_video", prompt=value, price=price)
    await msg.answer(
        "Tushundim, endi ishni boshlashim uchun to'lov qilishingiz kerak bo'ladi.\n\n"
        f"💰 To'lov miqdori: {price} so'm\n"
        f"💳 Karta raqam: {CARD_NUMBER}\n"
        "🧾 Shu karta raqamga to'lov qilib chekini yuboring.\n"
        "❌ Eslatib o'tamiz, cheksiz to'lov qabul qilinmaydi!",
        reply_markup=back_kb("back_ai_prompt")
    )
    await state.set_state(VideoState.img_to_video_payment)

# -------- Rasm yaratish --------
@dp.message(VideoState.image_gen_prompt)
async def ai_image_gen_prompt(msg: Message, state: FSMContext):
    await record_last_user_message(msg, state)
    value = get_answer_value(msg)
    if not value:
        await msg.answer("Iltimos, javob yuboring.", reply_markup=back_kb("back_ai_imagegen_prompt"))
        return
    await state.update_data(prompt=value)
    await msg.answer(
        "Rasm qanaqa formatda bo'lsin? (Instagram stories / kvadrat / YouTube format va hokazo)",
        reply_markup=back_kb("back_ai_imagegen_prompt")
    )
    await state.set_state(VideoState.image_gen_format)

@dp.message(VideoState.image_gen_format)
async def ai_image_gen_format(msg: Message, state: FSMContext):
    await record_last_user_message(msg, state)
    value = get_answer_value(msg)
    if not value:
        await msg.answer("Iltimos, javob yuboring.", reply_markup=back_kb("back_ai_imagegen_format"))
        return
    price = random.choice(range(8000, 15001, 1000))
    await state.update_data(kind="image_gen", format=value, price=price)
    await msg.answer(
        "Tushundim, endi ishni boshlashim uchun to'lov qilishingiz kerak bo'ladi.\n\n"
        f"💰 To'lov miqdori: {price} so'm\n"
        f"💳 Karta raqam: {CARD_NUMBER}\n"
        "🧾 Shu karta raqamga to'lov qilib chekini yuboring.\n"
        "❌ Eslatib o'tamiz, cheksiz to'lov qabul qilinmaydi!",
        reply_markup=back_kb("back_ai_imagegen_format")
    )
    await state.set_state(VideoState.image_gen_payment)

# -------- Men hohlagan video --------
@dp.message(VideoState.custom_prompt)
async def ai_custom_prompt(msg: Message, state: FSMContext):
    await record_last_user_message(msg, state)
    value = get_answer_value(msg)
    if not value:
        await msg.answer("Iltimos, javob yuboring.", reply_markup=back_kb("back_ai_custom"))
        return
    price = random.choice(range(15000, 25001, 1000))
    await state.update_data(kind="custom_video", prompt=value, price=price)
    await msg.answer(
        "Tushundim, endi ishni boshlashim uchun to'lov qilishingiz kerak bo'ladi.\n\n"
        f"💰 To'lov miqdori: {price} so'm\n"
        f"💳 Karta raqam: {CARD_NUMBER}\n"
        "🧾 Shu karta raqamga to'lov qilib chekini yuboring.\n"
        "❌ Eslatib o'tamiz, cheksiz to'lov qabul qilinmaydi!",
        reply_markup=back_kb("back_ai_custom")
    )
    await state.set_state(VideoState.custom_payment)

# --------  To'lov (umumiy) --------
@dp.message(VideoState.img_to_video_payment, F.photo)
@dp.message(VideoState.image_gen_payment, F.photo)
@dp.message(VideoState.custom_payment, F.photo)
async def ai_payment_photo(msg: Message, state: FSMContext):
    await record_last_user_message(msg, state)
    await ai_payment_any(msg, state, msg.photo[-1].file_id)

@dp.message(VideoState.img_to_video_payment, F.document)
@dp.message(VideoState.image_gen_payment, F.document)
@dp.message(VideoState.custom_payment, F.document)
async def ai_payment_doc(msg: Message, state: FSMContext):
    await record_last_user_message(msg, state)
    await ai_payment_any(msg, state, None, msg.document.file_id)

@dp.message(VideoState.img_to_video_payment)
@dp.message(VideoState.image_gen_payment)
@dp.message(VideoState.custom_payment)
async def ai_payment_other(msg: Message, state: FSMContext):
    await record_last_user_message(msg, state)
    await msg.answer(" Chekni rasm yoki hujjat ko'rinishida yuboring.")

async def ai_payment_any(msg: Message, state: FSMContext, photo_id=None, doc_id=None):
    data = await state.get_data()
    status = get_user_status(msg.from_user.id)
    kind = data.get("kind")

    status_msg = await msg.answer(
        "? ? Admin tekshirmoqda. Ish boshlanganda sizga xabar beramiz."
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="➕", callback_data=f"ok_video_{msg.from_user.id}_{status_msg.message_id}"),
            InlineKeyboardButton(text="➖", callback_data=f"no_video_{msg.from_user.id}_{status_msg.message_id}"),
        ]
    ])

    if kind == "img_to_video":
        text = (
            f" AI VIDEO BUYURTMA |  #{status}"
            f" @{msg.from_user.username or msg.from_user.id}"
            "? Tur: Rasmni video qilish"
            f" Matn: {data.get('prompt')}"
            f" {data.get('price')} so'm"
        )
    elif kind == "image_gen":
        text = (
            f" AI VIDEO BUYURTMA |  #{status}"
            f" @{msg.from_user.username or msg.from_user.id}"
            " Tur: Rasm yaratish"
            f" Tavsif: {data.get('prompt')}"
            f" Format: {data.get('format')}"
            f" {data.get('price')} so'm"
        )
    else:
        text = (
            f" AI VIDEO BUYURTMA |  #{status}"
            f" @{msg.from_user.username or msg.from_user.id}"
            " Tur: Men hohlagan video"
            f" Matn: {data.get('prompt')}"
            f" {data.get('price')} so'm"
        )

    if photo_id:
        await bot.send_photo(ADMIN_ID, photo_id, caption=text, reply_markup=kb)
    elif doc_id:
        await bot.send_document(ADMIN_ID, doc_id, caption=text, reply_markup=kb)
    else:
        await bot.send_message(ADMIN_ID, text + " Chek rasm yoki hujjat ko'rinishida yuborilmadi", reply_markup=kb)

    if kind == "img_to_video" and data.get("image_file_id"):
        try:
            await bot.send_photo(ADMIN_ID, data.get("image_file_id"), caption="? Manba rasm")
        except Exception:
            pass

    await state.clear()

# ===================== USER BACK HANDLERS (Video) =====================
@dp.callback_query(F.data == "back_ai_menu")
async def back_ai_menu(call: CallbackQuery, state: FSMContext):
    await delete_last_user_message(state)
    await state.set_state(VideoState.menu)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="? Rasmni video qilish", callback_data="ai_img_to_video")],
        [InlineKeyboardButton(text=" Rasm yaratish", callback_data="ai_image_gen")],
        [InlineKeyboardButton(text=" Men hohlagan video", callback_data="ai_custom_video")],
    ])
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.message.answer(" Xizmat turini tanlang:", reply_markup=kb)
    await call.answer()

@dp.callback_query(F.data == "back_ai_image")
async def back_ai_image(call: CallbackQuery, state: FSMContext):
    await delete_last_user_message(state)
    await state.set_state(VideoState.img_to_video_image)
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.message.answer("? Video yaratmoqchi bo'lgan rasmni yuboring:", reply_markup=back_kb("back_ai_menu"))
    await call.answer()

@dp.callback_query(F.data == "back_ai_prompt")
async def back_ai_prompt(call: CallbackQuery, state: FSMContext):
    await delete_last_user_message(state)
    await state.set_state(VideoState.img_to_video_prompt)
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.message.answer(
        " Sizga qanaqa video kerak? Shunchaki yozing."
        "Misol uchun: rasmdagi odam nimadir deb gapirsin.",
        reply_markup=back_kb("back_ai_image")
    )
    await call.answer()

@dp.callback_query(F.data == "back_ai_imagegen_prompt")
async def back_ai_imagegen_prompt(call: CallbackQuery, state: FSMContext):
    await delete_last_user_message(state)
    await state.set_state(VideoState.image_gen_prompt)
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.message.answer(
        " Yaratmoqchi bo'lgan rasmingizni shunchaki tasvirlab bering."
        "Misol uchun: bir yosh yigit korzinka supermarketi yonida qo'lida kamera bilan turibdi va futbolkasida instagram akkaunti nomi yozilgan..."
        "Shu kabi hohlagan narsangizni yozing, sifatli rasm tayyorlash mendan :)",
        reply_markup=back_kb("back_ai_menu")
    )
    await call.answer()

@dp.callback_query(F.data == "back_ai_imagegen_format")
async def back_ai_imagegen_format(call: CallbackQuery, state: FSMContext):
    await delete_last_user_message(state)
    await state.set_state(VideoState.image_gen_format)
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.message.answer(
        "Rasm qanaqa formatda bo'lsin? (Instagram stories / kvadrat / YouTube format va hokazo)",
        reply_markup=back_kb("back_ai_imagegen_prompt")
    )
    await call.answer()

@dp.callback_query(F.data == "back_ai_custom")
async def back_ai_custom(call: CallbackQuery, state: FSMContext):
    await delete_last_user_message(state)
    await state.set_state(VideoState.custom_prompt)
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.message.answer(
        "  Video haqida xohishingizni yozing."
        "  Qisqa va tushunarli yozing.",
        reply_markup=back_kb("back_ai_menu")
    )
    await call.answer()

# ===================== ADMIN CALLBACK (➕/➖) =====================
@dp.callback_query(F.data.startswith("ok_"))
async def approve(call: CallbackQuery):
    parts = call.data.split("_")
    _, kind, user_id_str, msg_id_str = parts
    user_id = int(user_id_str)
    status_message_id = int(msg_id_str)

    if kind == "slide":
        record_paid_order(user_id, "slide")
        text = "✅  To'lovingiz qabul qilindi.\n📝 Slayd tayyorlashni boshladik.\n📂 Tayyor bo'lganda slayd faylini yuboraman."
    else:
        record_paid_order(user_id, "video")
        text = "✅  To'lovingiz qabul qilindi.\n🎬 Videoni tayyorlashni boshladik.\n📂 Tayyor bo'lganda video faylini yuboraman."

    await bot.edit_message_text(text, chat_id=user_id, message_id=status_message_id)
    await call.answer("Tasdiqlandi")

@dp.callback_query(F.data.startswith("no_"))
async def decline(call: CallbackQuery):
    parts = call.data.split("_")
    _, kind, user_id_str, msg_id_str = parts
    user_id = int(user_id_str)
    status_message_id = int(msg_id_str)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=" Adminga yozish", url=f"tg://user?id={ADMIN_ID}")]
    ])
    text = (
        "❌  To'lov qabul qilinmadi.\n"
        "Soxta chek yoki boshqa muammo yuz bergan bo'lishi mumkin (afsuski slayd tayyorlashni boshlay olmayman).\n\n"
        "Agar sizda shikoyat bo'lsa, adminga murojaat qilishingiz mumkin."
    )
    await bot.edit_message_text(text, chat_id=user_id, message_id=status_message_id, reply_markup=kb)
    await call.answer("Rad etildi")

# ===================== ADMIN PANEL (callback'lar) =====================
@dp.callback_query(F.data == "admin_numbers")
async def admin_numbers(call: CallbackQuery, state: FSMContext):
    await delete_last_user_message(state)
    if call.from_user.id != ADMIN_ID:
        await call.answer()
        return
    await state.clear()
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.message.answer("🔢 Raqamlar boshqaruvi", reply_markup=admin_numbers_kb())
    await call.answer()

@dp.callback_query(F.data == "admin_kino_numbers")
async def admin_kino_numbers(call: CallbackQuery, state: FSMContext):
    await delete_last_user_message(state)
    if call.from_user.id != ADMIN_ID:
        await call.answer()
        return
    await state.clear()
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.message.answer("🎬 Kino raqamlar boshqaruvi", reply_markup=admin_kino_kb())
    await call.answer()

@dp.callback_query(F.data == "admin_kino_add")
async def admin_kino_add(call: CallbackQuery, state: FSMContext):
    await delete_last_user_message(state)
    if call.from_user.id != ADMIN_ID:
        await call.answer()
        return
    await state.clear()
    await state.set_state(KinoAdminState.add_number)
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.message.answer("🎬 Yangi kino raqamini kiriting:", reply_markup=back_kb("admin_kino_menu"))
    await call.answer()

@dp.callback_query(F.data == "admin_kino_menu")
async def admin_kino_menu(call: CallbackQuery, state: FSMContext):
    await delete_last_user_message(state)
    if call.from_user.id != ADMIN_ID:
        await call.answer()
        return
    await state.clear()
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.message.answer("🎬 Kino raqamlar boshqaruvi", reply_markup=admin_kino_kb())
    await call.answer()

@dp.callback_query(F.data == "admin_kino_delete")
async def admin_kino_delete(call: CallbackQuery, state: FSMContext):
    await delete_last_user_message(state)
    if call.from_user.id != ADMIN_ID:
        await call.answer()
        return
    await state.clear()
    items = list_kino_numbers()
    lines = []
    for n, t in items:
        summary = summarize_payload_list(t)
        lines.append(f"{n} - {summary}")
    text = "Mavjud kino raqamlar:\n" + ("\n".join(lines) if lines else "(bo'sh)")
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.message.answer(text + "\n\nO'chirish uchun raqamni kiriting:", reply_markup=back_kb("admin_kino_menu"))
    await state.set_state(KinoAdminState.del_number)
    await call.answer()

@dp.message(KinoAdminState.add_number, F.text)
async def admin_kino_add_number(msg: Message, state: FSMContext):
    await record_last_user_message(msg, state)
    if msg.from_user.id != ADMIN_ID:
        return
    if not msg.text.isdigit():
        await msg.answer("Raqamni to'g'ri kiriting (faqat son):", reply_markup=back_kb("admin_kino_menu"))
        return
    await state.update_data(add_number=int(msg.text))
    await state.set_state(KinoAdminState.add_message)
    await state.update_data(kino_pending=[])
    await msg.answer("Kino raqamiga ulanadigan habarni yuboring:", reply_markup=back_kb("admin_kino_menu"))

@dp.message(KinoAdminState.add_message)
async def admin_kino_add_message_any(msg: Message, state: FSMContext):
    await record_last_user_message(msg, state)
    if msg.from_user.id != ADMIN_ID:
        return
    data = await state.get_data()
    number = data.get('add_number')
    if number is None:
        await msg.answer("Avval raqamni kiriting.", reply_markup=back_kb("admin_kino_menu"))
        await state.set_state(KinoAdminState.add_number)
        return
    payload = build_payload_from_message(msg)
    pending = data.get("kino_pending", [])
    item_id = f"k{msg.message_id}"
    pending.append({"id": item_id, "payload": payload, "msg_id": msg.message_id})
    await state.update_data(kino_pending=pending)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="➖", callback_data=f"kino_del_{item_id}"),
            InlineKeyboardButton(text="➕", callback_data="kino_add_more"),
            InlineKeyboardButton(text="✅", callback_data="kino_add_done"),
        ]
    ])
    await msg.answer("Habar qo'shildi. Davom etasizmi?", reply_markup=kb)

@dp.message(KinoAdminState.del_number, F.text)
async def admin_kino_delete_number(msg: Message, state: FSMContext):
    await record_last_user_message(msg, state)
    if msg.from_user.id != ADMIN_ID:
        return
    if not msg.text.isdigit():
        await msg.answer("Raqamni to'g'ri kiriting (faqat son):", reply_markup=back_kb("admin_kino_menu"))
        return
    num = int(msg.text)
    if delete_kino_number(num):
        await msg.answer("✅ Kino raqami o'chirildi.", reply_markup=admin_kino_kb())
        await state.clear()
    else:
        await msg.answer("Bunday raqam topilmadi. Qayta kiriting:", reply_markup=back_kb("admin_kino_menu"))

@dp.callback_query(F.data == "kino_add_more")
async def kino_add_more(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        await call.answer()
        return
    await call.answer("Yana habar yuboring.")

@dp.callback_query(F.data == "kino_add_done")
async def kino_add_done(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        await call.answer()
        return
    data = await state.get_data()
    number = data.get("add_number")
    pending = data.get("kino_pending", [])
    if not number or not pending:
        await call.answer()
        await call.message.answer("Habar topilmadi. Avval habar yuboring.")
        return
    payloads = [p["payload"] for p in pending]
    add_kino_number(int(number), payloads)
    await state.clear()
    await call.message.answer("✅ Kino raqamiga habarlar biriktirildi.", reply_markup=admin_kino_kb())
    await call.answer()

@dp.callback_query(F.data.startswith("kino_del_"))
async def kino_del_item(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        await call.answer()
        return
    item_id = call.data.replace("kino_del_", "")
    data = await state.get_data()
    pending = data.get("kino_pending", [])
    new_pending = []
    msg_id = None
    for item in pending:
        if item.get("id") == item_id:
            msg_id = item.get("msg_id")
            continue
        new_pending.append(item)
    await state.update_data(kino_pending=new_pending)
    try:
        if msg_id:
            await bot.delete_message(call.from_user.id, msg_id)
        await call.message.delete()
    except Exception:
        pass
    await call.answer("O'chirildi")

@dp.callback_query(F.data == "admin_users_export")
async def admin_users_export(call: CallbackQuery, state: FSMContext):
    await delete_last_user_message(state)
    if call.from_user.id != ADMIN_ID:
        await call.answer()
        return
    data = load_users()
    users = data.get("users", {})
    if not users:
        await call.message.answer("Ro'yxatdan o'tgan user topilmadi.")
        await call.answer()
        return
    rtf_content = build_users_rtf(users)
    export_path = EXPORT_FILE
    export_path.write_text(rtf_content, encoding="utf-8")
    await call.message.answer_document(
        FSInputFile(str(export_path)),
        caption="🧾 Ro'yxatdan o'tgan userlar"
    )
    await call.answer()

@dp.callback_query(F.data == "admin_stats")
async def admin_stats(call: CallbackQuery, state: FSMContext):
    await delete_last_user_message(state)
    if call.from_user.id != ADMIN_ID:
        await call.answer()
        return
    await call.message.answer(build_stats_text())
    await call.answer()

@dp.callback_query(F.data == "admin_broadcast")
async def admin_broadcast_start(call: CallbackQuery, state: FSMContext):
    await delete_last_user_message(state)
    if call.from_user.id != ADMIN_ID:
        await call.answer()
        return
    await state.clear()
    await state.set_state(AdminBroadcastState.message)
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.message.answer(
        "📣 Hammaga yuboriladigan xabarni yuboring (matn, rasm, video, hujjat yoki ovoz).",
        reply_markup=back_kb("admin_back_send")
    )
    await call.answer()

@dp.message(AdminBroadcastState.message)
async def admin_broadcast_send(msg: Message, state: FSMContext):
    await record_last_user_message(msg, state)
    if msg.from_user.id != ADMIN_ID:
        return

    payload = build_payload_from_message(msg)
    if payload.get("type") == "text" and not payload.get("text"):
        await msg.answer("Iltimos, matn/rasm/video/hujjat/ovoz yuboring.", reply_markup=back_kb("admin_back_send"))
        return

    users = load_users().get("users", {})
    user_ids = [int(uid) for uid in users.keys()]
    if not user_ids:
        await msg.answer("Ro'yxatdan o'tgan user topilmadi.", reply_markup=admin_panel_kb())
        await state.clear()
        return

    progress = await msg.answer(f"📤 Yuborish boshlandi: {len(user_ids)} ta user.")
    sent = 0
    failed = 0

    for user_id in user_ids:
        try:
            await send_payload_to_chat(user_id, payload, with_caption=True)
            sent += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)

    await msg.answer(
        f"✅ Yakunlandi.\n📨 Yuborildi: {sent}\n❌ Xato: {failed}",
        reply_markup=admin_panel_kb()
    )
    try:
        await progress.delete()
    except Exception:
        pass
    await state.clear()

@dp.callback_query(F.data == "admin_books_menu")
async def admin_books_menu(call: CallbackQuery, state: FSMContext):
    await delete_last_user_message(state)
    if call.from_user.id != ADMIN_ID:
        await call.answer()
        return
    await state.clear()
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.message.answer("📚 Kitoblar boshqaruvi", reply_markup=admin_books_menu_kb())
    await call.answer()

@dp.callback_query(F.data == "admin_books_all")
async def admin_books_all(call: CallbackQuery, state: FSMContext):
    await delete_last_user_message(state)
    if call.from_user.id != ADMIN_ID:
        await call.answer()
        return
    await state.clear()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📚 Online Kitoblar", callback_data="admin_books_view_section_online")],
        [InlineKeyboardButton(text="🎧 Audio kitoblar", callback_data="admin_books_view_section_audio")],
        [InlineKeyboardButton(text="🔢 Raqamli kitoblar ro'yxati", callback_data="admin_books_num_list")],
        [InlineKeyboardButton(text="🗑️ Raqamli kitobni o'chirish", callback_data="admin_books_num_delete_start")],
        [InlineKeyboardButton(text="➕ Kitob qo'shish", callback_data="admin_books_add_book")],
        [InlineKeyboardButton(text="➕ Yo'nalish qo'shish", callback_data="admin_books_add_direction")],
        [InlineKeyboardButton(text="⬅️ Orqaga qaytish", callback_data="admin_books_menu")],
    ])
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.message.answer("📂 Barchasi: bo'limni tanlang", reply_markup=kb)
    await call.answer()

@dp.callback_query(F.data.startswith("admin_books_view_section_"))
async def admin_books_view_section(call: CallbackQuery, state: FSMContext):
    await delete_last_user_message(state)
    if call.from_user.id != ADMIN_ID:
        await call.answer()
        return
    section = call.data.replace("admin_books_view_section_", "")
    if section not in {"online", "audio"}:
        await call.answer()
        return
    kb = admin_books_categories_kb(section, "admin_books_view_cat", "admin_books_all")
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.message.answer(f"{section_title(section)} yo'nalishlari:", reply_markup=kb)
    await call.answer()

@dp.callback_query(F.data.startswith("admin_books_view_cat_"))
async def admin_books_view_category(call: CallbackQuery, state: FSMContext):
    await delete_last_user_message(state)
    if call.from_user.id != ADMIN_ID:
        await call.answer()
        return
    parts = call.data.split("_")
    if len(parts) < 6:
        await call.answer()
        return
    section = parts[4]
    try:
        cat_idx = int(parts[5])
    except ValueError:
        await call.answer()
        return
    category = get_book_category_by_index(section, cat_idx)
    if not category:
        await call.answer()
        return

    books = list_books_in_category(section, category)
    if books:
        lines = [f"{idx + 1} - {book_short_title(b)}" for idx, b in enumerate(books)]
        text = f"{section_title(section)}\n{category_title(category)}\n\n" + "\n".join(lines)
    else:
        text = f"{section_title(section)}\n{category_title(category)}\n\n(hozircha bo'sh)"

    rows = []
    for idx, _ in enumerate(books):
        rows.append([InlineKeyboardButton(text=f"🗑️ {idx + 1}-kitobni o'chirish", callback_data=f"admin_books_del_{section}_{cat_idx}_{idx}")])
    rows.append([InlineKeyboardButton(text="⬅️ Orqaga qaytish", callback_data=f"admin_books_view_section_{section}")])
    rows.append([InlineKeyboardButton(text="🏠 Kitoblar menyusi", callback_data="admin_books_menu")])
    kb = InlineKeyboardMarkup(inline_keyboard=rows)

    try:
        await call.message.delete()
    except Exception:
        pass
    await call.message.answer(text, reply_markup=kb)
    await call.answer()

@dp.callback_query(F.data.startswith("admin_books_del_"))
async def admin_books_delete(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        await call.answer()
        return
    parts = call.data.split("_")
    if len(parts) < 6:
        await call.answer()
        return
    section = parts[3]
    try:
        cat_idx = int(parts[4])
        item_idx = int(parts[5])
    except ValueError:
        await call.answer()
        return
    category = get_book_category_by_index(section, cat_idx)
    if not category:
        await call.answer()
        return
    ok = delete_book_by_index(section, category, item_idx)
    if ok:
        await call.answer("Kitob o'chirildi.")
    else:
        await call.answer("Kitob topilmadi.", show_alert=True)

    books = list_books_in_category(section, category)
    if books:
        lines = [f"{idx + 1} - {book_short_title(b)}" for idx, b in enumerate(books)]
        text = f"{section_title(section)}\n{category_title(category)}\n\n" + "\n".join(lines)
    else:
        text = f"{section_title(section)}\n{category_title(category)}\n\n(hozircha bo'sh)"
    rows = []
    for idx, _ in enumerate(books):
        rows.append([InlineKeyboardButton(text=f"🗑️ {idx + 1}-kitobni o'chirish", callback_data=f"admin_books_del_{section}_{cat_idx}_{idx}")])
    rows.append([InlineKeyboardButton(text="⬅️ Orqaga qaytish", callback_data=f"admin_books_view_section_{section}")])
    rows.append([InlineKeyboardButton(text="🏠 Kitoblar menyusi", callback_data="admin_books_menu")])
    kb = InlineKeyboardMarkup(inline_keyboard=rows)
    try:
        await call.message.edit_text(text, reply_markup=kb)
    except Exception:
        await call.message.answer(text, reply_markup=kb)

@dp.callback_query(F.data == "admin_books_add_direction")
async def admin_books_add_direction_start(call: CallbackQuery, state: FSMContext):
    await delete_last_user_message(state)
    if call.from_user.id != ADMIN_ID:
        await call.answer()
        return
    await state.clear()
    await state.set_state(BookAdminState.add_direction)
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.message.answer(
        "➕ Yangi yo'nalish nomini yuboring:",
        reply_markup=back_kb("admin_books_menu")
    )
    await call.answer()

@dp.message(BookAdminState.add_direction)
async def admin_books_add_direction_submit(msg: Message, state: FSMContext):
    await record_last_user_message(msg, state)
    if msg.from_user.id != ADMIN_ID:
        return
    direction_name = (msg.text or "").strip()
    if not direction_name:
        await msg.answer("Yo'nalish nomini yozing.", reply_markup=back_kb("admin_books_menu"))
        return
    add_book_direction(direction_name)
    await state.clear()
    await msg.answer(f"✅ Yo'nalish qo'shildi: {direction_name}", reply_markup=admin_books_menu_kb())

@dp.callback_query(F.data == "admin_books_num_list")
async def admin_books_num_list(call: CallbackQuery, state: FSMContext):
    await delete_last_user_message(state)
    if call.from_user.id != ADMIN_ID:
        await call.answer()
        return
    await state.clear()
    items = list_numbered_books()
    if items:
        lines = [f"{n} - {book_short_title(item)}" for n, item in items]
        text = "🔢 Raqamli kitoblar ro'yxati:\n\n" + "\n".join(lines)
    else:
        text = "🔢 Hozircha raqamli kitob yo'q."
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Orqaga qaytish", callback_data="admin_books_all")]
    ])
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.message.answer(text, reply_markup=kb)
    await call.answer()

@dp.callback_query(F.data == "admin_books_num_delete_start")
async def admin_books_num_delete_start(call: CallbackQuery, state: FSMContext):
    await delete_last_user_message(state)
    if call.from_user.id != ADMIN_ID:
        await call.answer()
        return
    await state.clear()
    items = list_numbered_books()
    if items:
        lines = [f"{n} - {book_short_title(item)}" for n, item in items]
        text = "🗑️ O'chirish uchun mavjud raqamli kitoblar:\n\n" + "\n".join(lines)
    else:
        text = "🔢 Hozircha raqamli kitob yo'q."
    await state.set_state(BookAdminState.num_delete_number)
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.message.answer(
        text + "\n\nO'chirish uchun raqamni yuboring:",
        reply_markup=back_kb("admin_books_all")
    )
    await call.answer()

@dp.message(BookAdminState.num_delete_number)
async def admin_books_num_delete_number(msg: Message, state: FSMContext):
    await record_last_user_message(msg, state)
    if msg.from_user.id != ADMIN_ID:
        return
    value = (msg.text or "").strip()
    if not value.isdigit():
        await msg.answer("Raqamni to'g'ri kiriting (faqat son).", reply_markup=back_kb("admin_books_all"))
        return
    number = int(value)
    if delete_numbered_book(number):
        await msg.answer(f"✅ {number} raqamli kitob o'chirildi.", reply_markup=admin_books_menu_kb())
        await state.clear()
        return
    await msg.answer("❌ Bu raqam bo'yicha kitob topilmadi. Qayta kiriting:", reply_markup=back_kb("admin_books_all"))

@dp.callback_query(F.data == "admin_books_numbered_menu")
async def admin_books_numbered_menu(call: CallbackQuery, state: FSMContext):
    await delete_last_user_message(state)
    if call.from_user.id != ADMIN_ID:
        await call.answer()
        return
    await state.clear()
    await state.update_data(num_preview_ids=[])
    try:
        await call.message.delete()
    except Exception:
        pass

    numbered = list_numbered_books()
    if numbered:
        lines = [f"{num} - {book_short_title(item)}" for num, item in numbered]
        await call.message.answer("🔢 Mavjud raqamli kitoblar:\n" + "\n".join(lines))
    else:
        await call.message.answer("🔢 Hozircha raqamli kitoblar yo'q.")

    await state.set_state(BookAdminState.num_cover)
    await call.message.answer(
        "📷 Raqamli kitob rasmini yuboring:",
        reply_markup=back_kb("admin_books_menu")
    )
    await call.answer()

@dp.message(BookAdminState.num_cover, F.photo)
async def admin_books_num_cover(msg: Message, state: FSMContext):
    await record_last_user_message(msg, state)
    if msg.from_user.id != ADMIN_ID:
        return
    await state.update_data(num_cover=build_payload_from_message(msg))
    await state.set_state(BookAdminState.num_info)
    await msg.answer("📝 Raqamli kitob ma'lumotini yozing:", reply_markup=back_kb("admin_books_menu"))

@dp.message(BookAdminState.num_cover)
async def admin_books_num_cover_other(msg: Message, state: FSMContext):
    await record_last_user_message(msg, state)
    await msg.answer("Iltimos, rasm yuboring.", reply_markup=back_kb("admin_books_menu"))

@dp.message(BookAdminState.num_info)
async def admin_books_num_info(msg: Message, state: FSMContext):
    await record_last_user_message(msg, state)
    if msg.from_user.id != ADMIN_ID:
        return
    info = (msg.text or "").strip()
    if not info:
        await msg.answer("Iltimos, kitob ma'lumotini yozing.", reply_markup=back_kb("admin_books_menu"))
        return
    await state.update_data(num_info=info)
    await state.set_state(BookAdminState.num_file)
    await msg.answer("📄 Kitob faylini yuboring (hujjat/audio/ovoz/video):", reply_markup=back_kb("admin_books_menu"))

@dp.message(BookAdminState.num_file)
async def admin_books_num_file(msg: Message, state: FSMContext):
    await record_last_user_message(msg, state)
    if msg.from_user.id != ADMIN_ID:
        return
    payload = build_payload_from_message(msg)
    if payload.get("type") not in {"document", "audio", "voice", "video"}:
        await msg.answer("Iltimos, kitob faylini hujjat/audio/ovoz/video ko'rinishida yuboring.", reply_markup=back_kb("admin_books_menu"))
        return
    await state.update_data(num_file=payload)
    await state.set_state(BookAdminState.num_number)
    await msg.answer("🔢 Endi kitob ulanadigan raqamni yuboring (masalan: 1):", reply_markup=back_kb("admin_books_menu"))

@dp.message(BookAdminState.num_number)
async def admin_books_num_number(msg: Message, state: FSMContext):
    await record_last_user_message(msg, state)
    if msg.from_user.id != ADMIN_ID:
        return
    value = (msg.text or "").strip()
    if not value.isdigit():
        await msg.answer("Raqamni to'g'ri kiriting (faqat son).", reply_markup=back_kb("admin_books_menu"))
        return
    number = int(value)

    data = await state.get_data()
    cover = data.get("num_cover")
    info = data.get("num_info")
    file_payload = data.get("num_file")
    if not isinstance(cover, dict) or not isinstance(file_payload, dict) or not info:
        await msg.answer("Ma'lumotlar to'liq emas. Qaytadan boshlang.", reply_markup=admin_books_menu_kb())
        await state.clear()
        return

    preview_item = {
        "lookup_number": number,
        "cover": cover,
        "info": info,
        "file": file_payload,
    }
    preview_ids = await send_book_item_block(msg.chat.id, preview_item, preview=True)
    control_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="➕", callback_data="admin_books_num_confirm"),
            InlineKeyboardButton(text="➖", callback_data="admin_books_num_cancel"),
        ]
    ])
    ctrl_msg = await msg.answer(
        f"Raqam: {number}\nTasdiqlaysizmi? (mavjud bo'lsa yangilanadi)",
        reply_markup=control_kb
    )
    preview_ids.append(ctrl_msg.message_id)
    await state.update_data(num_number=number, num_preview_ids=preview_ids)
    await state.set_state(BookAdminState.num_confirm)

@dp.callback_query(F.data == "admin_books_num_confirm")
async def admin_books_num_confirm(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        await call.answer()
        return
    data = await state.get_data()
    number = data.get("num_number")
    cover = data.get("num_cover")
    info = data.get("num_info")
    file_payload = data.get("num_file")
    if not isinstance(number, int) or not isinstance(cover, dict) or not isinstance(file_payload, dict) or not info:
        await call.answer("Ma'lumotlar topilmadi.", show_alert=True)
        return
    add_numbered_book(number, cover, info, file_payload)
    await state.clear()
    await call.message.answer(f"✅ Raqamli kitob saqlandi: {number}", reply_markup=admin_books_menu_kb())
    await call.answer("Saqlandi")

@dp.callback_query(F.data == "admin_books_num_cancel")
async def admin_books_num_cancel(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        await call.answer()
        return
    data = await state.get_data()
    for msg_id in data.get("num_preview_ids", []):
        try:
            await bot.delete_message(call.from_user.id, msg_id)
        except Exception:
            pass
    await state.clear()
    await call.message.answer("❌ Raqamli kitob qo'shish bekor qilindi.", reply_markup=admin_books_menu_kb())
    await call.answer("Bekor qilindi")

@dp.callback_query(F.data == "admin_books_add_book")
async def admin_books_add_book_start(call: CallbackQuery, state: FSMContext):
    await delete_last_user_message(state)
    if call.from_user.id != ADMIN_ID:
        await call.answer()
        return
    await state.clear()
    await state.update_data(book_add_section=None, book_add_category=None, book_pending=None, book_preview_ids=[])
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.message.answer(
        "Kitob qo'shish uchun bo'limni tanlang:",
        reply_markup=admin_books_section_kb("admin_books_addbook_section", "admin_books_menu")
    )
    await call.answer()

@dp.callback_query(F.data.startswith("admin_books_addbook_section_"))
async def admin_books_add_book_section(call: CallbackQuery, state: FSMContext):
    await delete_last_user_message(state)
    if call.from_user.id != ADMIN_ID:
        await call.answer()
        return
    section = call.data.replace("admin_books_addbook_section_", "")
    if section not in {"online", "audio"}:
        await call.answer()
        return
    await state.update_data(book_add_section=section)
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.message.answer(
        "Yo'nalishni tanlang:",
        reply_markup=admin_books_categories_kb(section, "admin_books_addbook_cat", "admin_books_add_book")
    )
    await call.answer()

@dp.callback_query(F.data.startswith("admin_books_addbook_cat_"))
async def admin_books_add_book_category(call: CallbackQuery, state: FSMContext):
    await delete_last_user_message(state)
    if call.from_user.id != ADMIN_ID:
        await call.answer()
        return
    parts = call.data.split("_")
    if len(parts) < 6:
        await call.answer()
        return
    section = parts[4]
    try:
        cat_idx = int(parts[5])
    except ValueError:
        await call.answer()
        return
    category = get_book_category_by_index(section, cat_idx)
    if not category:
        await call.answer()
        return
    await state.update_data(book_add_section=section, book_add_category=category)
    await state.set_state(BookAdminState.add_book_cover)
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.message.answer("📷 Kitob rasmini yuboring:", reply_markup=back_kb("admin_books_add_book"))
    await call.answer()

@dp.message(BookAdminState.add_book_cover, F.photo)
async def admin_books_add_book_cover(msg: Message, state: FSMContext):
    await record_last_user_message(msg, state)
    if msg.from_user.id != ADMIN_ID:
        return
    await state.update_data(book_cover=build_payload_from_message(msg))
    await state.set_state(BookAdminState.add_book_info)
    await msg.answer("📝 Kitob uchun ma'lumot yozing:", reply_markup=back_kb("admin_books_add_book"))

@dp.message(BookAdminState.add_book_cover)
async def admin_books_add_book_cover_other(msg: Message, state: FSMContext):
    await record_last_user_message(msg, state)
    await msg.answer("Iltimos, kitob rasmini yuboring.", reply_markup=back_kb("admin_books_add_book"))

@dp.message(BookAdminState.add_book_info)
async def admin_books_add_book_info(msg: Message, state: FSMContext):
    await record_last_user_message(msg, state)
    if msg.from_user.id != ADMIN_ID:
        return
    info = (msg.text or "").strip()
    if not info:
        await msg.answer("Iltimos, kitob ma'lumotini yozing.", reply_markup=back_kb("admin_books_add_book"))
        return
    await state.update_data(book_info=info)
    await state.set_state(BookAdminState.add_book_file)
    await msg.answer("📄 Kitob faylini yuboring (hujjat yoki audio):", reply_markup=back_kb("admin_books_add_book"))

@dp.message(BookAdminState.add_book_file)
async def admin_books_add_book_file(msg: Message, state: FSMContext):
    await record_last_user_message(msg, state)
    if msg.from_user.id != ADMIN_ID:
        return
    payload = build_payload_from_message(msg)
    if payload.get("type") not in {"document", "audio", "voice", "video"}:
        await msg.answer("Iltimos, kitob faylini hujjat/audio/ovoz/video ko'rinishida yuboring.", reply_markup=back_kb("admin_books_add_book"))
        return

    data = await state.get_data()
    section = data.get("book_add_section")
    category = data.get("book_add_category")
    cover = data.get("book_cover")
    info = data.get("book_info")
    if not section or not category or not info or not isinstance(cover, dict):
        await msg.answer("Ma'lumotlar to'liq emas. Qaytadan boshlang.", reply_markup=admin_books_menu_kb())
        await state.clear()
        return

    await state.update_data(book_file=payload)
    preview_item = {
        "number": "-",
        "cover": cover,
        "info": f"{section_title(section)} / {category_title(category)}\n\n{info}",
        "file": payload,
    }
    preview_ids = await send_book_item_block(msg.chat.id, preview_item, preview=True)

    control_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="➕", callback_data="admin_books_add_confirm"),
            InlineKeyboardButton(text="➖", callback_data="admin_books_add_cancel"),
        ]
    ])
    ctrl_msg = await msg.answer("Kitobni saqlaysizmi?", reply_markup=control_kb)
    preview_ids.append(ctrl_msg.message_id)
    await state.update_data(book_preview_ids=preview_ids)
    await state.set_state(BookAdminState.add_book_confirm)

@dp.callback_query(F.data == "admin_books_add_confirm")
async def admin_books_add_confirm(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        await call.answer()
        return
    data = await state.get_data()
    section = data.get("book_add_section")
    category = data.get("book_add_category")
    cover = data.get("book_cover")
    info = data.get("book_info")
    file_payload = data.get("book_file")
    if not section or not category or not info or not isinstance(cover, dict) or not isinstance(file_payload, dict):
        await call.answer("Ma'lumotlar topilmadi.", show_alert=True)
        return
    add_book_item(section, category, cover, info, file_payload)
    await state.clear()
    await call.message.answer("✅ Kitob saqlandi.", reply_markup=admin_books_menu_kb())
    await call.answer("Saqlandi")

@dp.callback_query(F.data == "admin_books_add_cancel")
async def admin_books_add_cancel(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        await call.answer()
        return
    data = await state.get_data()
    for msg_id in data.get("book_preview_ids", []):
        try:
            await bot.delete_message(call.from_user.id, msg_id)
        except Exception:
            pass
    await state.clear()
    await call.message.answer("❌ Kitob qo'shish bekor qilindi.", reply_markup=admin_books_menu_kb())
    await call.answer("Bekor qilindi")

@dp.callback_query(F.data == "admin_numbers_menu")
async def admin_numbers_menu(call: CallbackQuery, state: FSMContext):
    await delete_last_user_message(state)
    if call.from_user.id != ADMIN_ID:
        await call.answer()
        return
    await state.clear()
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.message.answer("🔢 Raqamlar boshqaruvi", reply_markup=admin_numbers_kb())
    await call.answer()

@dp.callback_query(F.data == "admin_numbers_add")
async def admin_numbers_add(call: CallbackQuery, state: FSMContext):
    await delete_last_user_message(state)
    if call.from_user.id != ADMIN_ID:
        await call.answer()
        return
    await state.clear()
    await state.set_state(BilimUlashAdminState.add_number)
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.message.answer("➕ Yangi raqamni kiriting:", reply_markup=back_kb("admin_numbers_menu"))
    await call.answer()

@dp.message(BilimUlashAdminState.add_number, F.text)
async def admin_numbers_add_number(msg: Message, state: FSMContext):
    await record_last_user_message(msg, state)
    if msg.from_user.id != ADMIN_ID:
        return
    if not msg.text.isdigit():
        await msg.answer("Raqamni to'g'ri kiriting (faqat son):", reply_markup=back_kb("admin_numbers_menu"))
        return
    await state.update_data(add_number=int(msg.text))
    await state.set_state(BilimUlashAdminState.add_message)
    await state.update_data(bilim_pending=[])
    await msg.answer("Raqamga ulanadigan habarni yuboring:", reply_markup=back_kb("admin_numbers_menu"))

@dp.message(BilimUlashAdminState.add_message)
async def admin_numbers_add_message_any(msg: Message, state: FSMContext):
    await record_last_user_message(msg, state)
    if msg.from_user.id != ADMIN_ID:
        return
    data = await state.get_data()
    number = data.get('add_number')
    if number is None:
        await msg.answer("Avval raqamni kiriting.", reply_markup=back_kb("admin_numbers_menu"))
        await state.set_state(BilimUlashAdminState.add_number)
        return
    payload = build_payload_from_message(msg)
    pending = data.get("bilim_pending", [])
    item_id = f"b{msg.message_id}"
    pending.append({"id": item_id, "payload": payload, "msg_id": msg.message_id})
    await state.update_data(bilim_pending=pending)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="➖", callback_data=f"bilim_del_{item_id}"),
            InlineKeyboardButton(text="➕", callback_data="bilim_add_more"),
            InlineKeyboardButton(text="✅", callback_data="bilim_add_done"),
        ]
    ])
    await msg.answer("Habar qo'shildi. Davom etasizmi?", reply_markup=kb)

@dp.callback_query(F.data == "admin_numbers_delete")
async def admin_numbers_delete(call: CallbackQuery, state: FSMContext):
    await delete_last_user_message(state)
    if call.from_user.id != ADMIN_ID:
        await call.answer()
        return
    await state.clear()
    items = list_bilim_numbers()
    lines = []
    for n, t in items:
        summary = summarize_payload_list(t)
        lines.append(f"{n} - {summary}")
    text = "Mavjud raqamlar:\n" + ("\n".join(lines) if lines else "(bo'sh)")
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.message.answer(text + "\n\nO'chirish uchun raqamni kiriting:", reply_markup=back_kb("admin_numbers_menu"))
    await state.set_state(BilimUlashAdminState.del_number)
    await call.answer()

@dp.callback_query(F.data == "bilim_add_more")
async def bilim_add_more(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        await call.answer()
        return
    await call.answer("Yana habar yuboring.")

@dp.callback_query(F.data == "bilim_add_done")
async def bilim_add_done(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        await call.answer()
        return
    data = await state.get_data()
    number = data.get("add_number")
    pending = data.get("bilim_pending", [])
    if not number or not pending:
        await call.answer()
        await call.message.answer("Habar topilmadi. Avval habar yuboring.")
        return
    payloads = [p["payload"] for p in pending]
    add_bilim_number(int(number), payloads)
    await state.clear()
    await call.message.answer("✅ Raqamga habarlar biriktirildi.", reply_markup=admin_numbers_kb())
    await call.answer()

@dp.callback_query(F.data.startswith("bilim_del_"))
async def bilim_del_item(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        await call.answer()
        return
    item_id = call.data.replace("bilim_del_", "")
    data = await state.get_data()
    pending = data.get("bilim_pending", [])
    new_pending = []
    msg_id = None
    for item in pending:
        if item.get("id") == item_id:
            msg_id = item.get("msg_id")
            continue
        new_pending.append(item)
    await state.update_data(bilim_pending=new_pending)
    try:
        if msg_id:
            await bot.delete_message(call.from_user.id, msg_id)
        await call.message.delete()
    except Exception:
        pass
    await call.answer("O'chirildi")

@dp.message(BilimUlashAdminState.del_number, F.text)
async def admin_numbers_delete_number(msg: Message, state: FSMContext):
    await record_last_user_message(msg, state)
    if msg.from_user.id != ADMIN_ID:
        return
    if not msg.text.isdigit():
        await msg.answer("Raqamni to'g'ri kiriting (faqat son):", reply_markup=back_kb("admin_numbers_menu"))
        return
    num = int(msg.text)
    if delete_bilim_number(num):
        await msg.answer("? Raqam o'chirildi.", reply_markup=admin_numbers_kb())
        await state.clear()
    else:
        await msg.answer("Bunday raqam topilmadi. Qayta kiriting:", reply_markup=back_kb("admin_numbers_menu"))

@dp.callback_query(F.data == "admin_back_main")
async def admin_back_main(call: CallbackQuery, state: FSMContext):
    await delete_last_user_message(state)
    if call.from_user.id != ADMIN_ID:
        await call.answer()
        return
    await state.clear()
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.message.answer("Xizmatni tanlang 👇", reply_markup=menu_kb(is_admin=True))
    await call.answer()

@dp.callback_query(F.data == "admin_order_ready")
async def admin_order_ready(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        await call.answer()
        return
    await state.update_data(ready_payloads=[])
    await state.set_state(AdminSendState.file)
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.message.answer("📦 Faylni yuboring (video, foto, hujjat):", reply_markup=back_kb("admin_back_send"))
    await call.answer()

@dp.callback_query(F.data == "admin_back_send")
async def admin_back_from_file(call: CallbackQuery, state: FSMContext):
    await delete_last_user_message(state)
    if call.from_user.id != ADMIN_ID:
        await call.answer()
        return
    await state.clear()
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.message.answer("⚙️ Admin panel", reply_markup=admin_panel_kb())
    await call.answer()

@dp.callback_query(F.data == "admin_back_file")
async def admin_back_from_number(call: CallbackQuery, state: FSMContext):
    await delete_last_user_message(state)
    if call.from_user.id != ADMIN_ID:
        await call.answer()
        return
    await state.update_data(file_id=None, file_type=None, ready_payloads=[])
    await state.set_state(AdminSendState.file)
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.message.answer("📦 Faylni yuboring (video, foto, hujjat):", reply_markup=back_kb("admin_back_send"))
    await call.answer()

@dp.callback_query(F.data == "admin_back_comment")
async def admin_back_from_comment(call: CallbackQuery, state: FSMContext):
    await delete_last_user_message(state)
    if call.from_user.id != ADMIN_ID:
        await call.answer()
        return
    await state.update_data(user_number=None, target_user_id=None)
    await state.set_state(AdminSendState.user_number)
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.message.answer("📋 User tartib raqamini yuboring:", reply_markup=back_kb("admin_back_file"))
    await call.answer()

@dp.message(AdminSendState.file, F.photo)
async def admin_send_file_photo(msg: Message, state: FSMContext):
    await record_last_user_message(msg, state)
    payload = {"type": "photo", "file_id": msg.photo[-1].file_id, "caption": msg.caption or ""}
    data = await state.get_data()
    pending = data.get("ready_payloads", [])
    item_id = f"r{msg.message_id}"
    pending.append({"id": item_id, "payload": payload, "msg_id": msg.message_id})
    await state.update_data(ready_payloads=pending)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="➖", callback_data=f"ready_del_{item_id}"),
            InlineKeyboardButton(text="➕", callback_data="ready_add_more"),
            InlineKeyboardButton(text="✅", callback_data="ready_done"),
        ]
    ])
    await msg.answer("Fayl qo'shildi. Davom etasizmi?", reply_markup=kb)

@dp.message(AdminSendState.file, F.video)
async def admin_send_file_video(msg: Message, state: FSMContext):
    await record_last_user_message(msg, state)
    payload = {"type": "video", "file_id": msg.video.file_id, "caption": msg.caption or ""}
    data = await state.get_data()
    pending = data.get("ready_payloads", [])
    item_id = f"r{msg.message_id}"
    pending.append({"id": item_id, "payload": payload, "msg_id": msg.message_id})
    await state.update_data(ready_payloads=pending)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="➖", callback_data=f"ready_del_{item_id}"),
            InlineKeyboardButton(text="➕", callback_data="ready_add_more"),
            InlineKeyboardButton(text="✅", callback_data="ready_done"),
        ]
    ])
    await msg.answer("Fayl qo'shildi. Davom etasizmi?", reply_markup=kb)

@dp.message(AdminSendState.file, F.document)
async def admin_send_file_document(msg: Message, state: FSMContext):
    await record_last_user_message(msg, state)
    payload = {"type": "document", "file_id": msg.document.file_id, "caption": msg.caption or ""}
    data = await state.get_data()
    pending = data.get("ready_payloads", [])
    item_id = f"r{msg.message_id}"
    pending.append({"id": item_id, "payload": payload, "msg_id": msg.message_id})
    await state.update_data(ready_payloads=pending)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="➖", callback_data=f"ready_del_{item_id}"),
            InlineKeyboardButton(text="➕", callback_data="ready_add_more"),
            InlineKeyboardButton(text="✅", callback_data="ready_done"),
        ]
    ])
    await msg.answer("Fayl qo'shildi. Davom etasizmi?", reply_markup=kb)

@dp.message(AdminSendState.file)
async def admin_send_file_other(msg: Message, state: FSMContext):
    await record_last_user_message(msg, state)
    await msg.answer("Iltimos, video, rasm yoki hujjat yuboring.", reply_markup=back_kb("admin_back_send"))

@dp.callback_query(F.data == "ready_add_more")
async def ready_add_more(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        await call.answer()
        return
    await call.answer("Yana fayl yuboring.")

@dp.callback_query(F.data == "ready_done")
async def ready_done(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        await call.answer()
        return
    data = await state.get_data()
    pending = data.get("ready_payloads", [])
    if not pending:
        await call.answer()
        await call.message.answer("Fayl topilmadi. Avval fayl yuboring.")
        return
    await state.set_state(AdminSendState.user_number)
    await call.message.answer("📋 User tartib raqamini yuboring:", reply_markup=back_kb("admin_back_file"))
    await call.answer()

@dp.callback_query(F.data.startswith("ready_del_"))
async def ready_del_item(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        await call.answer()
        return
    item_id = call.data.replace("ready_del_", "")
    data = await state.get_data()
    pending = data.get("ready_payloads", [])
    new_pending = []
    msg_id = None
    for item in pending:
        if item.get("id") == item_id:
            msg_id = item.get("msg_id")
            continue
        new_pending.append(item)
    await state.update_data(ready_payloads=new_pending)
    try:
        if msg_id:
            await bot.delete_message(call.from_user.id, msg_id)
        await call.message.delete()
    except Exception:
        pass
    await call.answer("O'chirildi")

@dp.message(AdminSendState.user_number, F.text)
async def admin_send_user_number(msg: Message, state: FSMContext):
    await record_last_user_message(msg, state)
    if not msg.text.isdigit():
        await msg.answer("Tartib raqamini to'g'ri kiriting (faqat son):", reply_markup=back_kb("admin_back_file"))
        return
    num = int(msg.text)
    user_id = get_user_by_status(num)
    if user_id is None:
        await msg.answer("Bunday tartib raqamli user topilmadi. Qayta kiriting:", reply_markup=back_kb("admin_back_file"))
        return
    await state.update_data(user_number=num, target_user_id=user_id)
    await msg.answer("✍️ Userga izoh yozing (masalan: Buyurtma sizga yoqdimi):", reply_markup=back_kb("admin_back_comment"))
    await state.set_state(AdminSendState.comment)

@dp.message(AdminSendState.comment, F.text)
async def admin_send_comment(msg: Message, state: FSMContext):
    await record_last_user_message(msg, state)
    data = await state.get_data()
    target_user_id = data["target_user_id"]
    comment = msg.text
    pending = data.get("ready_payloads", [])

    caption = f"✅ Buyurtmangiz tayyor!\n\n💬 Izoh: {comment}"

    try:
        await bot.send_message(target_user_id, caption)
        for item in pending:
            await send_payload_to_chat(target_user_id, item.get("payload"), with_caption=True)
        await msg.answer("✅ Fayllar userga yuborildi.", reply_markup=menu_kb(is_admin=True))
    except Exception as e:
        await msg.answer(f"❌ Xatolik: {e}", reply_markup=menu_kb(is_admin=True))
    await state.clear()

# ===================== /start qayta bosilganda (ro'yxatdan o'tgan) =====================
# SubState da qolgan user /start qayta bosganda - qayta obuna ko'rsatamiz
# (yuqorida /start allaqachon bor)

# ===================== RUN =====================
async def main():
    print("Bot ishga tushdi...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
