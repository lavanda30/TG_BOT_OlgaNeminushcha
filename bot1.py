"""
bot1.py — OlgaNeminushcha_PriceBot
t.me/OlgaNeminushcha_PriceBot

Показує ВСІ постачальники з all_products.xlsx,
КРІМ GRANDDESIGN та ЛАСП (ті — тільки для бота 2).

Змінні середовища (Railway):
  BOT_TOKEN  — токен бота
  EXCEL_URL  — raw-посилання на all_products.xlsx

Калькулятор пошиву:
  Формат: <запит тканини> <метри>M  (або m)
  Наприклад: 1361 4.9M  або  Donna 5m
  Формула: метри × (ціна$ × 90 + 250)
  де 90 = курс 45 × коефіцієнт 2, 250 = ціна пошиву за метр (грн)
"""
import os
import re
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)
from data_loader import load_all, fmt_price, get_tag, get_extra, normalize

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

EXCLUDED_SUPPLIERS = {'GRANDDESIGN', 'ЛАСП', 'GRANDDESIGN', 'HATEM', 'МИ З УКРАЇНИ'}
PAGE_SIZE = 8
UAH_RATE = 45   # курс для калькулятора
SEW_PER_M = 250  # ціна пошиву за метр, грн

_data: dict = {}


def data() -> dict:
    global _data
    if not _data:
        _data = load_all()
        for excl in EXCLUDED_SUPPLIERS:
            _data.pop(excl, None)
    return _data


def reload_data():
    global _data
    _data = {}
    return data()


# ═══════════════════════════════════════════════════════
# Калькулятор
# ═══════════════════════════════════════════════════════

# Патерн: число з крапкою або комою, потім M або m
_METERS_RE = re.compile(r'(\d+[.,]\d+|\d+)\s*[Mm](?:\b|$)')


def parse_calc_query(text: str):
    """
    Якщо в тексті є шаблон '<число>M', повертає (пошуковий_запит, метри).
    Інакше повертає (text, None).
    """
    m = _METERS_RE.search(text)
    if not m:
        return text, None
    meters_str = m.group(1).replace(',', '.')
    meters = float(meters_str)
    # Пошуковий запит — текст без знайденого шматка з метражем
    query = text[:m.start()].strip() + ' ' + text[m.end():].strip()
    query = query.strip()
    return query, meters


def get_usd_price(row: dict) -> float | None:
    """Повертає ціну в доларах або None якщо не USD."""
    currency = str(row.get('currency') or '').strip().upper()
    if currency not in ('USD', 'У.Е.', 'U.E.', '$', ''):
        return None
    # Беремо price_retail якщо є, інакше price
    val = row.get('price_retail') or row.get('price')
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def calc_sewing(price_usd: float, meters: float) -> float:
    return meters * (price_usd * UAH_RATE * 2 + SEW_PER_M)


def build_calc_message(query: str, meters: float, results: list) -> str:
    """Будує повідомлення з розрахунком для знайдених тканин."""
    msg = (
        f"Формула: метри × (ціна$ × {UAH_RATE} × 2 + {SEW_PER_M} грн)\n\n"
    )

    shown = results[:5]
    for supplier, row in shown:
        sku = str(row.get('sku') or row.get('name') or '?').strip()
        price_usd = get_usd_price(row)

        if price_usd is None:
            # Ціна не в доларах — показуємо без розрахунку
            msg += (
                f"🧵 *{supplier}* · `{sku}`\n"
                f"   ⚠️ Ціна не в USD, розрахунок недоступний\n\n"
            )
            continue

        total = calc_sewing(price_usd, meters)
        price_per_m = price_usd * UAH_RATE * 2
        extra = get_extra(row)
        extra_str = f" · _{extra}_" if extra else ""

        msg += (
            f"🧵 *{supplier}* · `{sku}`{extra_str}\n"
            f"   Ціна: *{price_usd}$*, *{total:,.0f} грн*\n\n"
        )

    if len(results) > 5:
        msg += f"_...ще {len(results)-5} збігів. Уточніть запит._\n"

    return msg


# ═══════════════════════════════════════════════════════
# UI helpers
# ═══════════════════════════════════════════════════════

SUPPLIER_EMOJI = {
    'Elizabeth': '👑', 'ADEKO': '🏭', 'LIBERTA': '🎪',
    'THE BEST': '⭐', 'SAVAHOME': '🏠', 'Edition': '📖',
    'AURUM DECOR': '🥇', 'RED DE LUXE': '❤️', 'Улюблений дім': '🏡',
    'LEON': '🦁', 'ENAS PRIME': '✨', 'Anro': '🧶',
    'CHANAN': '🌸', 'BR BRooKS': '🔵', 'CASARI': '🎭',
    'Artplay': '🎨', 'BY KAAN': '🇹🇷', 'DIZZARIO': '💫',
    'PRONTO': '🚀', 'NEVALYA': '🌟', 'МД СИМЬЕ': '🏷️',
    'МІРТЕКС': '🧵', 'INSAIT': '💡', 'ПРАЙС 01.10.2025': '📋',
    'ПіК': '📌', 'DECORAL': '🎀', 'MEGARA': '🏺',
    '12.05.2025': '🌙', 'UMUT (SPERANTA)': '🌙', 'HAS BOR': '🏗️',
    'NOPE': '🔷', 'MEVLANA': '🕌', 'ELIT HOME': '🏅',
    'SAM-TEX HOME': '🔴',
}
DEFAULT_EMOJI = '🧵'


def supplier_emoji(name: str) -> str:
    return SUPPLIER_EMOJI.get(name, DEFAULT_EMOJI)


def build_main_keyboard(d: dict) -> InlineKeyboardMarkup:
    suppliers = sorted(d.keys())
    rows = []
    for i in range(0, len(suppliers), 2):
        row = []
        for s in suppliers[i:i+2]:
            count = len(d[s])
            row.append(InlineKeyboardButton(
                f"{supplier_emoji(s)} {s} ({count})",
                callback_data=f"brand:{s}:0"
            ))
        rows.append(row)
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
    end = min(start + PAGE_SIZE, len(items))
    total = len(items)
    emoji = supplier_emoji(supplier)

    text = f"{emoji} *{supplier}*\n"
    text += f"Показано {start+1}–{end} з {total}\n\n"

    for row in items[start:end]:
        tag = get_tag(row)
        sku = str(row.get('sku') or row.get('name') or '?').strip()
        price_str = fmt_price(row)
        extra = get_extra(row)
        h = row.get('height_cm')
        height_str = f" · {int(h)}см" if h and str(h).isdigit() else (f" · {h}см" if h else "")

        line = f"{tag} `{sku}` — {price_str}{height_str}"
        if extra:
            line += f"\n   _{extra}_"
        text += line + "\n"

    return text


# ═══════════════════════════════════════════════════════
# Handlers
# ═══════════════════════════════════════════════════════

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    d = data()
    total = sum(len(v) for v in d.values())
    text = (
        "🛍 *Прайс — Штори та Тюль*\n\n"
        f"В базі: *{total} позицій* · *{len(d)} брендів*\n\n"
        "Оберіть бренд або скористайтесь пошуком:\n\n"
        "💡 *Калькулятор пошиву:* введіть артикул і метраж\n"
        "Наприклад: `1361 4.9M` або `Donna 5m`"
    )
    await update.message.reply_text(
        text, parse_mode="Markdown",
        reply_markup=build_main_keyboard(d)
    )


async def cmd_reload(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Оновлюю дані з Excel...")
    try:
        d = reload_data()
        total = sum(len(v) for v in d.values())
        await update.message.reply_text(
            f"✅ Дані оновлено: {total} позицій · {len(d)} брендів",
            reply_markup=build_main_keyboard(d)
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
            "Наприклад: `Donna`, `8132`, `блекаут`, `l205`\n\n"
            "💡 Для калькулятора додайте метраж: `1361 4.9M`",
            parse_mode="Markdown"
        )


async def on_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    d = data()
    cmd = q.data

    if cmd == "main":
        total = sum(len(v) for v in d.values())
        text = (
            "🛍 *Прайс — Штори та Тюль*\n\n"
            f"В базі: *{total} позицій* · *{len(d)} брендів*\n\n"
            "Оберіть бренд або скористайтесь пошуком:"
        )
        await q.edit_message_text(text, parse_mode="Markdown", reply_markup=build_main_keyboard(d))

    elif cmd.startswith("brand:") or cmd.startswith("page:"):
        parts = cmd.split(":", 2)
        supplier = parts[1]
        page = int(parts[2])
        items = d.get(supplier)
        if not items:
            await q.edit_message_text("❌ Бренд не знайдено або порожній")
            return
        text = build_brand_text(supplier, items, page)
        kb = build_brand_keyboard(supplier, items, page)
        await q.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)

    elif cmd == "search":
        await q.edit_message_text(
            "🔍 *Введіть назву або артикул* для пошуку:\n\n"
            "Наприклад: `блекаут`, `Donna`, `8132`, `l205`\n"
            "💡 З метражем для розрахунку: `1361 4.9M`",
            parse_mode="Markdown"
        )


async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    raw = update.message.text.strip()

    # ── Перевіряємо чи є метраж у запиті ──
    query, meters = parse_calc_query(raw)

    q_lower = query.lower()
    q_norm = normalize(query)

    results = []
    seen = set()
    d = data()

    for supplier, items in d.items():
        for row in items:
            matched = False
            for field in ('sku', 'name', 'category', 'fabric', 'collection'):
                val = str(row.get(field) or '')
                if q_lower in val.lower() or (q_norm and q_norm in normalize(val)):
                    matched = True
                    break
            if matched:
                key = (supplier, str(row.get('sku') or row.get('name') or ''))
                if key not in seen:
                    seen.add(key)
                    results.append((supplier, row))

    # ── Режим калькулятора ──
    if meters is not None:
        if not results:
            await update.message.reply_text(
                f"❌ По запиту *{query}* нічого не знайдено\n\n"
                "💡 Спробуйте інший артикул, наприклад: `1361 4.9M`",
                parse_mode="Markdown",
                reply_markup=build_main_keyboard(d)
            )
            return

        msg = build_calc_message(query, meters, results)
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("🔍 Новий пошук", callback_data="search"),
            InlineKeyboardButton("🏠 Головна", callback_data="main"),
        ]])
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=kb)
        return

    # ── Звичайний пошук ──
    if not results:
        await update.message.reply_text(
            f"❌ По запиту *{query}* нічого не знайдено\n\n"
            "💡 Спробуйте без пробілів: `l205`, або назву тканини",
            parse_mode="Markdown",
            reply_markup=build_main_keyboard(d)
        )
        return

    shown = results[:15]
    msg = f"🔍 Знайдено *{len(results)}* по «{query}»:\n\n"

    for supplier, row in shown:
        tag = get_tag(row)
        sku = str(row.get('sku') or row.get('name') or '?').strip()
        price_str = fmt_price(row)
        extra = get_extra(row)
        extra_str = f" · _{extra}_" if extra else ""
        msg += f"{tag} [{supplier}] `{sku}` — {price_str}{extra_str}\n"

    if len(results) > 15:
        msg += f"\n_...ще {len(results)-15}. Уточніть запит._"

    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("🔍 Новий пошук", callback_data="search"),
        InlineKeyboardButton("🏠 Головна", callback_data="main"),
    ]])
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=kb)


# ═══════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════

def main():
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise ValueError("BOT_TOKEN не встановлено! Додайте змінну середовища на Railway.")

    logger.info("Bot1 (OlgaNeminushcha_PriceBot) starting...")
    try:
        d = data()
        logger.info(f"Loaded {sum(len(v) for v in d.values())} rows, {len(d)} suppliers")
    except Exception as e:
        logger.warning(f"Could not preload data: {e}")

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("reload", cmd_reload))
    app.add_handler(CommandHandler("search", cmd_search))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    logger.info("Bot1 polling...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
