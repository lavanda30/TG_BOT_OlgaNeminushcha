"""
bot1.py — OlgaNeminushcha_PriceBot  t.me/OlgaNeminushcha_PriceBot

Показує ВСІ постачальники з all_products.xlsx,
КРІМ GRANDDESIGN, ЛАСП, HATEM, МИ З УКРАЇНИ, ECOBELLA (ті — для бота 2).

Змінні середовища (Railway):
  BOT_TOKEN  — токен бота
  EXCEL_URL  — raw-посилання на all_products.xlsx
  WHITELIST  — telegram_id через кому (крім адміна)

Калькулятор пошиву:
  Формат: <запит> <число>M  (M/m — будь-яка мова)
  Наприклад: 1361 4.9M  або  Donna 5m
  Формула: метри × (ціна$ × UAH_RATE × 2 + SEW_PER_M)
"""
import os
import re
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes,
)
from data_loader import load_all, fmt_price, get_tag, get_extra, normalize

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

EXCLUDED_SUPPLIERS = {"GRANDDESIGN", "ЛАСП", "HATEM", "МИ З УКРАЇНИ", "ECOBELLA"}
PAGE_SIZE  = 8
UAH_RATE   = 45    # курс $ → грн для калькулятора
SEW_PER_M  = 250   # ціна пошиву за метр, грн
SHOW_LIMIT = 7     # максимум позицій в одному повідомленні

SHOP_NAME = "💫 Салон штор Ольги Неминущої"

# ── Whitelist ────────────────────────────────────────────────
ADMIN_ID = 1027792488

def _load_whitelist() -> set[int]:
    ids = {ADMIN_ID}
    for part in os.environ.get("WHITELIST", "").split(","):
        part = part.strip()
        if part.isdigit():
            ids.add(int(part))
    return ids

_whitelist: set[int] = _load_whitelist()

def is_allowed(user_id: int) -> bool:
    return user_id in _whitelist

BLOCKED_TEXT = (
    "🔒 Цей бот працює лише для авторизованих користувачів.\n\n"
    "Для отримання доступу зверніться до адміністратора."
)
# ─────────────────────────────────────────────────────────────

_data: dict = {}

def data() -> dict:
    global _data
    if not _data:
        _data = load_all()
        for excl in EXCLUDED_SUPPLIERS:
            _data.pop(excl, None)
    return _data

def reload_data() -> dict:
    global _data
    _data = {}
    return data()


# ═══════════════════════════════════════════════════════
# Калькулятор
# ═══════════════════════════════════════════════════════

# число + M/m/М/м (латиниця і кирилиця)
_METERS_RE = re.compile(r"(\d+[.,]\d+|\d+)\s*[MmМм](?:\b|$)")

def parse_calc_query(text: str):
    m = _METERS_RE.search(text)
    if not m:
        return text, None
    meters = float(m.group(1).replace(",", "."))
    query  = (text[:m.start()] + " " + text[m.end():]).strip()
    return query, meters

def get_usd_price(row: dict) -> float | None:
    cur = str(row.get("currency") or "").strip().upper()
    if cur not in ("USD", "У.Е.", "U.E.", "$", ""):
        return None
    val = row.get("price_retail") or row.get("price")
    try:
        return float(val)
    except (TypeError, ValueError):
        return None

def calc_sewing(price_usd: float, meters: float) -> float:
    return meters * (price_usd * UAH_RATE * 2 + SEW_PER_M)


# ═══════════════════════════════════════════════════════
# Форматування результатів
# ═══════════════════════════════════════════════════════

NUM_EMOJI = {1:"1️⃣",2:"2️⃣",3:"3️⃣",4:"4️⃣",5:"5️⃣",6:"6️⃣",7:"7️⃣"}

def pick_label(row: dict, query: str) -> str:
    """Показуємо sku або name залежно від того де знайдено запит."""
    sku  = str(row.get("sku")  or "").strip()
    name = str(row.get("name") or "").strip()
    q = query.lower()
    if q and q in sku.lower():
        return sku
    if q and name and q in name.lower():
        return name
    return sku if sku else name

def format_row(idx: int, supplier: str, row: dict, query: str, meters: float | None) -> str:
    """Один рядок результату. Якщо meters — ціна по формулі, інакше — звичайна."""
    num       = NUM_EMOJI.get(idx, f"{idx}.")
    label     = pick_label(row, query)
    price_usd = get_usd_price(row)

    if price_usd is None:
        price_str = fmt_price(row)
    elif meters is not None:
        total     = calc_sewing(price_usd, meters)
        price_str = f"*{price_usd}$* ≈ *{total:,.0f} грн*"
    else:
        price_uah = round(price_usd * UAH_RATE * 2)
        price_str = f"*{price_usd}$* ≈ *{price_uah} грн*"

    return f"{num} *{supplier}* · {label} · {price_str}"

def build_results_msg(results: list, query: str, meters: float | None) -> str:
    """Повідомлення з назвою магазину + до SHOW_LIMIT позицій."""
    msg = f"{SHOP_NAME}\n\n"
    for i, (supplier, row) in enumerate(results[:SHOW_LIMIT], 1):
        msg += format_row(i, supplier, row, query, meters) + "\n"
    if len(results) > SHOW_LIMIT:
        msg += f"_...ще {len(results)-SHOW_LIMIT}. Уточніть запит._\n"
    return msg


# ═══════════════════════════════════════════════════════
# UI helpers
# ═══════════════════════════════════════════════════════

SUPPLIER_EMOJI = {
    "Elizabeth":"👑","ADEKO":"🏭","LIBERTA":"🎪","THE BEST":"⭐",
    "SAVAHOME":"🏠","Edition":"📖","AURUM DECOR":"🥇","RED DE LUXE":"❤️",
    "Улюблений дім":"🏡","LEON":"🦁","ENAS PRIME":"✨","Anro":"🧶",
    "CHANAN":"🌸","BR BRooKS":"🔵","CASARI":"🎭","Artplay":"🎨",
    "BY KAAN":"🇹🇷","DIZZARIO":"💫","PRONTO":"🚀","NEVALYA":"🌟",
    "МД СИМЬЕ":"🏷️","МІРТЕКС":"🧵","INSAIT":"💡","ПРАЙС 01.10.2025":"📋",
    "ПіК":"📌","DECORAL":"🎀","MEGARA":"🏺","UMUT":"🌙",
    "UMUT (SPERANTA)":"🌙","HAS BOR":"🏗️","NOPE":"🔷","MEVLANA":"🕌",
    "ELIT HOME":"🏅","SAM-TEX RED 3":"🔴",
}
DEFAULT_EMOJI = "🧵"

def supplier_emoji(name: str) -> str:
    return SUPPLIER_EMOJI.get(name, DEFAULT_EMOJI)

def build_main_keyboard(d: dict) -> InlineKeyboardMarkup:
    rows = []
    for i, s in enumerate(sorted(d.keys())):
        if i % 2 == 0:
            rows.append([])
        rows[-1].append(InlineKeyboardButton(
            f"{supplier_emoji(s)} {s} ({len(d[s])})",
            callback_data=f"brand:{s}:0",
        ))
    rows.append([InlineKeyboardButton("🔍 Пошук по всіх брендах", callback_data="search")])
    return InlineKeyboardMarkup(rows)

def build_brand_keyboard(supplier: str, items: list, page: int) -> InlineKeyboardMarkup:
    total_pages = (len(items) + PAGE_SIZE - 1) // PAGE_SIZE
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️ Назад", callback_data=f"page:{supplier}:{page-1}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("Далі ▶️", callback_data=f"page:{supplier}:{page+1}"))
    btns = []
    if nav:
        btns.append(nav)
    btns.append([
        InlineKeyboardButton("🔍 Пошук", callback_data="search"),
        InlineKeyboardButton("🏠 Головна", callback_data="main"),
    ])
    return InlineKeyboardMarkup(btns)

def build_brand_text(supplier: str, items: list, page: int) -> str:
    start = page * PAGE_SIZE
    end   = min(start + PAGE_SIZE, len(items))
    emoji = supplier_emoji(supplier)
    text  = f"{emoji} *{supplier}*\nПоказано {start+1}–{end} з {len(items)}\n\n"
    for row in items[start:end]:
        tag   = get_tag(row)
        sku   = str(row.get("sku") or row.get("name") or "?").strip()
        extra = get_extra(row)
        h     = row.get("height_cm")
        h_str = f" · {int(h)}см" if h and str(h).lstrip("-").isdigit() else (f" · {h}см" if h else "")
        line  = f"{tag} `{sku}` — {fmt_price(row)}{h_str}"
        if extra:
            line += f"\n   _{extra}_"
        text += line + "\n"
    return text

def nav_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🔍 Новий пошук", callback_data="search"),
        InlineKeyboardButton("🏠 Головна",     callback_data="main"),
    ]])


# ═══════════════════════════════════════════════════════
# Пошук
# ═══════════════════════════════════════════════════════

def search_results(query: str, d: dict) -> list:
    q_lower = query.lower()
    q_norm  = normalize(query)
    results, seen = [], set()
    for supplier, items in d.items():
        for row in items:
            for field in ("sku", "name", "category", "fabric", "collection"):
                val = str(row.get(field) or "")
                if q_lower in val.lower() or (q_norm and q_norm in normalize(val)):
                    key = (supplier, str(row.get("sku") or row.get("name") or ""))
                    if key not in seen:
                        seen.add(key)
                        results.append((supplier, row))
                    break
    return results


# ═══════════════════════════════════════════════════════
# Handlers
# ═══════════════════════════════════════════════════════

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_allowed(user.id):
        await update.message.reply_text(BLOCKED_TEXT)
        return
    d     = data()
    total = sum(len(v) for v in d.values())
    await update.message.reply_text(
        f"🛍 *Прайс — Штори та Тюль*\n\n"
        f"В базі: *{total} позицій* · *{len(d)} брендів*\n\n"
        "Оберіть бренд або введіть назву/артикул.\n"
        "Для розрахунку пошиву додайте метраж: `Donna 5m`",
        parse_mode="Markdown",
        reply_markup=build_main_keyboard(d),
    )

async def cmd_reload(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        return
    await update.message.reply_text("⏳ Оновлюю дані з Excel...")
    try:
        d     = reload_data()
        total = sum(len(v) for v in d.values())
        await update.message.reply_text(
            f"✅ Дані оновлено: {total} позицій · {len(d)} брендів",
            reply_markup=build_main_keyboard(d),
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Помилка: {e}")

async def cmd_search(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        await update.message.reply_text(BLOCKED_TEXT)
        return
    if ctx.args:
        update.message.text = " ".join(ctx.args)
        await on_text(update, ctx)
    else:
        await update.message.reply_text(
            "🔍 Введіть назву або артикул.\nДля розрахунку додайте метраж: `1361 4.9M`",
            parse_mode="Markdown",
        )

async def cmd_adduser(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not ctx.args or not ctx.args[0].isdigit():
        await update.message.reply_text("Використання: /adduser <telegram_id>")
        return
    uid = int(ctx.args[0])
    _whitelist.add(uid)
    await update.message.reply_text(f"✅ `{uid}` додано", parse_mode="Markdown")

async def cmd_removeuser(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not ctx.args or not ctx.args[0].isdigit():
        await update.message.reply_text("Використання: /removeuser <telegram_id>")
        return
    uid = int(ctx.args[0])
    if uid == ADMIN_ID:
        await update.message.reply_text("❌ Не можна видалити адміна")
        return
    _whitelist.discard(uid)
    await update.message.reply_text(f"✅ `{uid}` видалено", parse_mode="Markdown")

async def cmd_listusers(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    ids = sorted(_whitelist)
    await update.message.reply_text(
        f"👥 *Whitelist ({len(ids)}):*\n" + "\n".join(f"• `{i}`" for i in ids),
        parse_mode="Markdown",
    )

async def on_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_allowed(q.from_user.id):
        await q.edit_message_text(BLOCKED_TEXT)
        return

    d   = data()
    cmd = q.data

    if cmd == "main":
        total = sum(len(v) for v in d.values())
        await q.edit_message_text(
            f"🛍 *Прайс — Штори та Тюль*\n\nВ базі: *{total} позицій* · *{len(d)} брендів*\n\nОберіть бренд:",
            parse_mode="Markdown",
            reply_markup=build_main_keyboard(d),
        )

    elif cmd.startswith("brand:") or cmd.startswith("page:"):
        _, supplier, page = cmd.split(":", 2)
        items = d.get(supplier)
        if not items:
            await q.edit_message_text("❌ Бренд не знайдено")
            return
        await q.edit_message_text(
            build_brand_text(supplier, items, int(page)),
            parse_mode="Markdown",
            reply_markup=build_brand_keyboard(supplier, items, int(page)),
        )

    elif cmd.startswith("sqfilter:"):
        # sqfilter:<query>:<meters_or_none>:<supplier>
        parts    = cmd.split(":", 3)
        query    = parts[1]
        meters   = float(parts[2]) if parts[2] != "none" else None
        sup      = parts[3]
        filtered = [(sup, row) for row in d.get(sup, [])
                    if any(query.lower() in str(row.get(f) or "").lower()
                           for f in ("sku","name","category","fabric","collection"))]
        if not filtered:
            await q.edit_message_text("❌ Нічого не знайдено")
            return
        await q.edit_message_text(
            build_results_msg(filtered, query, meters),
            parse_mode="Markdown",
            reply_markup=nav_kb(),
        )

    elif cmd == "search":
        await q.edit_message_text(
            "🔍 Введіть назву або артикул.\nДля розрахунку додайте метраж: `1361 4.9M`",
            parse_mode="Markdown",
        )

async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        await update.message.reply_text(BLOCKED_TEXT)
        return

    raw          = update.message.text.strip()
    query, meters = parse_calc_query(raw)
    d            = data()
    results      = search_results(query, d)

    if not results:
        await update.message.reply_text(
            "❌ Нічого не знайдено. Спробуйте інший артикул або назву.",
            reply_markup=build_main_keyboard(d),
        )
        return

    # Більше SHOW_LIMIT — пропонуємо вибрати постачальника
    if len(results) > SHOW_LIMIT:
        by_supplier: dict = {}
        for sup, row in results:
            by_supplier.setdefault(sup, []).append(row)

        meters_str = str(meters) if meters is not None else "none"
        buttons = []
        for sup in sorted(by_supplier):
            buttons.append([InlineKeyboardButton(
                f"{supplier_emoji(sup)} {sup} ({len(by_supplier[sup])})",
                callback_data=f"sqfilter:{query}:{meters_str}:{sup}",
            )])
        buttons.append([
            InlineKeyboardButton("🔍 Новий пошук", callback_data="search"),
            InlineKeyboardButton("🏠 Головна",     callback_data="main"),
        ])
        await update.message.reply_text(
            f"{SHOP_NAME}\n\nОберіть постачальника:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        return

    # До SHOW_LIMIT — одразу вивід
    await update.message.reply_text(
        build_results_msg(results, query, meters),
        parse_mode="Markdown",
        reply_markup=nav_kb(),
    )


# ═══════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════

def main():
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise ValueError("BOT_TOKEN не встановлено!")

    logger.info("Bot1 starting...")
    try:
        d = data()
        logger.info(f"Loaded {sum(len(v) for v in d.values())} rows, {len(d)} suppliers")
    except Exception as e:
        logger.warning(f"Could not preload data: {e}")

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start",      cmd_start))
    app.add_handler(CommandHandler("reload",     cmd_reload))
    app.add_handler(CommandHandler("search",     cmd_search))
    app.add_handler(CommandHandler("adduser",    cmd_adduser))
    app.add_handler(CommandHandler("removeuser", cmd_removeuser))
    app.add_handler(CommandHandler("listusers",  cmd_listusers))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    logger.info("Bot1 polling...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
