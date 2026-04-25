"""
bot2.py — @Price_Lavanda_bot  (t.me/Price_Lavanda_bot)
Токен: 8577234476:AAFGUnl2FcZrybYx-0QZ7mIIo_IAbbrW2xg

Показує ТІЛЬКИ: SAVAHOME, Elizabeth, ЛАСП, GRANDDESIGN
Дані тягнуться з all_products.xlsx (спільний з bot1).
"""
import os
import logging
from pathlib import Path

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

# ============================================================
# Токен — читаємо з env або прямо звідси
# ============================================================
BOT2_TOKEN = "8577234476:AAFGUnl2FcZrybYx-0QZ7mIIo_IAbbrW2xg"

# ============================================================
# Цей бот показує ТІЛЬКИ ці постачальники
# ============================================================
ALLOWED_SUPPLIERS = ["SAVAHOME", "Elizabeth", "ЛАСП", "GRANDDESIGN"]

PAGE_SIZE = 8

# ============================================================
# Кеш даних (оновлюється командою /reload)
# ============================================================
_data: dict = {}


def data() -> dict:
    global _data
    if not _data:
        _data = load_all(allowed_suppliers=ALLOWED_SUPPLIERS)
    return _data


def reload_data() -> dict:
    global _data
    _data = {}
    return data()


# ============================================================
# UI helpers
# ============================================================

SUPPLIER_EMOJI = {
    "SAVAHOME":    "🏠",
    "Elizabeth":   "👑",
    "ЛАСП":        "🧵",
    "GRANDDESIGN": "🏭",
}


def supplier_emoji(name: str) -> str:
    return SUPPLIER_EMOJI.get(name, "🧵")


def build_main_keyboard(d: dict) -> InlineKeyboardMarkup:
    suppliers = [s for s in ALLOWED_SUPPLIERS if s in d]
    rows = []
    for i in range(0, len(suppliers), 2):
        row = []
        for s in suppliers[i : i + 2]:
            count = len(d[s])
            row.append(
                InlineKeyboardButton(
                    f"{supplier_emoji(s)} {s} ({count})",
                    callback_data=f"brand:{s}:0",
                )
            )
        rows.append(row)
    rows.append(
        [InlineKeyboardButton("🔍 Пошук по всіх брендах", callback_data="search")]
    )
    return InlineKeyboardMarkup(rows)


def build_brand_keyboard(supplier: str, items: list, page: int) -> InlineKeyboardMarkup:
    total_pages = (len(items) + PAGE_SIZE - 1) // PAGE_SIZE
    nav = []
    if page > 0:
        nav.append(
            InlineKeyboardButton("◀️ Назад", callback_data=f"page:{supplier}:{page - 1}")
        )
    if page < total_pages - 1:
        nav.append(
            InlineKeyboardButton("Далі ▶️", callback_data=f"page:{supplier}:{page + 1}")
        )
    btns = []
    if nav:
        btns.append(nav)
    btns.append(
        [
            InlineKeyboardButton("🔍 Пошук", callback_data="search"),
            InlineKeyboardButton("🏠 Головна", callback_data="main"),
        ]
    )
    return InlineKeyboardMarkup(btns)


def build_brand_text(supplier: str, items: list, page: int) -> str:
    start = page * PAGE_SIZE
    end   = min(start + PAGE_SIZE, len(items))
    total = len(items)
    emoji = supplier_emoji(supplier)

    text = f"{emoji} *{supplier}*\n"
    text += f"Показано {start + 1}–{end} з {total}\n\n"

    for row in items[start:end]:
        tag   = get_tag(row)
        sku   = str(row.get("sku") or row.get("name") or "?").strip()
        price = fmt_price(row)
        extra = get_extra(row)
        h     = row.get("height_cm")
        h_str = f" · {int(h)}см" if h and str(h).lstrip("-").isdigit() else (f" · {h}см" if h else "")

        line = f"{tag} `{sku}` — {price}{h_str}"
        if extra:
            line += f"\n   _{extra}_"
        text += line + "\n"

    return text


# ============================================================
# Handlers
# ============================================================

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    d     = data()
    total = sum(len(v) for v in d.values())
    text  = (
        "🛍 *Прайс — Штори та Тюль*\n\n"
        f"В базі: *{total} позицій* · *{len(d)} брендів*\n\n"
        "Оберіть бренд або скористайтесь пошуком:"
    )
    await update.message.reply_text(
        text, parse_mode="Markdown", reply_markup=build_main_keyboard(d)
    )


async def cmd_reload(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Оновлюю дані з Excel…")
    try:
        d     = reload_data()
        total = sum(len(v) for v in d.values())
        await update.message.reply_text(
            f"✅ Готово: {total} позицій · {len(d)} брендів",
            reply_markup=build_main_keyboard(d),
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Помилка: {e}")


async def cmd_search(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if ctx.args:
        update.message.text = " ".join(ctx.args)
        await on_text(update, ctx)
    else:
        await update.message.reply_text(
            "🔍 Введіть назву або артикул:\n"
            "Наприклад: `HARMONY`, `блекаут`, `FA1106`, `велюр`",
            parse_mode="Markdown",
        )


async def on_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    d   = data()
    cmd = q.data

    if cmd == "main":
        total = sum(len(v) for v in d.values())
        text  = (
            "🛍 *Прайс — Штори та Тюль*\n\n"
            f"В базі: *{total} позицій* · *{len(d)} брендів*\n\n"
            "Оберіть бренд або скористайтесь пошуком:"
        )
        await q.edit_message_text(
            text, parse_mode="Markdown", reply_markup=build_main_keyboard(d)
        )

    elif cmd.startswith("brand:") or cmd.startswith("page:"):
        parts    = cmd.split(":", 2)
        supplier = parts[1]
        page     = int(parts[2])
        items    = d.get(supplier)
        if not items:
            await q.edit_message_text("❌ Бренд не знайдено або порожній")
            return
        text = build_brand_text(supplier, items, page)
        kb   = build_brand_keyboard(supplier, items, page)
        await q.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)

    elif cmd == "search":
        await q.edit_message_text(
            "🔍 *Введіть назву або артикул* для пошуку:\n\n"
            "Наприклад: `HARMONY`, `блекаут`, `FA1106`, `велюр`",
            parse_mode="Markdown",
        )


async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query   = update.message.text.strip()
    q_lower = query.lower()
    q_norm  = normalize(query)

    results: list = []
    seen: set     = set()
    d = data()

    for supplier, items in d.items():
        for row in items:
            matched = False
            for field in ("sku", "name", "category", "fabric", "collection"):
                val = str(row.get(field) or "")
                if q_lower in val.lower() or (q_norm and q_norm in normalize(val)):
                    matched = True
                    break
            if matched:
                key = (supplier, str(row.get("sku") or row.get("name") or ""))
                if key not in seen:
                    seen.add(key)
                    results.append((supplier, row))

    if not results:
        await update.message.reply_text(
            f"❌ По запиту *{query}* нічого не знайдено\n\n"
            "💡 Спробуйте інший артикул або назву тканини",
            parse_mode="Markdown",
            reply_markup=build_main_keyboard(d),
        )
        return

    shown = results[:15]
    msg   = f"🔍 Знайдено *{len(results)}* по «{query}»:\n\n"

    for supplier, row in shown:
        tag      = get_tag(row)
        sku      = str(row.get("sku") or row.get("name") or "?").strip()
        price    = fmt_price(row)
        extra    = get_extra(row)
        extra_str = f" · _{extra}_" if extra else ""
        msg += f"{tag} [{supplier}] `{sku}` — {price}{extra_str}\n"

    if len(results) > 15:
        msg += f"\n_…ще {len(results) - 15}. Уточніть запит._"

    kb = InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("🔍 Новий пошук", callback_data="search"),
            InlineKeyboardButton("🏠 Головна",     callback_data="main"),
        ]]
    )
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=kb)


# ============================================================
# Main
# ============================================================

def main():
    token = (
        os.environ.get("BOT2_TOKEN")
        or os.environ.get("BOT_TOKEN")
        or BOT2_TOKEN
    )

    logger.info("Bot2 @Price_Lavanda_bot starting…")
    try:
        d = data()
        logger.info(f"Preloaded: {sum(len(v) for v in d.values())} rows, {len(d)} suppliers")
    except Exception as e:
        logger.warning(f"Could not preload data: {e}")

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("reload", cmd_reload))
    app.add_handler(CommandHandler("search", cmd_search))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    logger.info("Bot2 polling…")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
