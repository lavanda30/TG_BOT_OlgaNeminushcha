# 🤖 Telegram Price Bots — Штори та Тюль

Два боти, що тягнуть дані з одного файлу `all_products.xlsx`.

---

## 📁 Структура

```
telegram_bot/
  bot1.py          ← Бот 1 (OlgaNeminushcha_PriceBot) — всі бренди
  bot2.py          ← Бот 2 (існуючий) — тільки SAVAHOME/Elizabeth/ЛАСП/GRANDDESIGN
  data_loader.py   ← Спільний модуль завантаження XLSX
  requirements.txt ← python-telegram-bot + openpyxl
  config.env       ← Токени та URL (НЕ комітити у git!)
  README.md        ← Ця інструкція
```

---

## 🤖 Боти

| Бот | Посилання | Постачальники |
|-----|-----------|---------------|
| **Бот 1** | [@OlgaNeminushcha_PriceBot](https://t.me/OlgaNeminushcha_PriceBot) | Всі, КРІМ GRANDDESIGN і ЛАСП |
| **Бот 2** | (існуючий) | ТІЛЬКИ: SAVAHOME, Elizabeth, ЛАСП, GRANDDESIGN |

---

## ⚙️ Налаштування джерела даних

Обидва боти читають `all_products.xlsx`. Спосіб задання:

### Варіант А — URL (для Railway/хостингу)
```bash
export EXCEL_URL="https://your-railway-url.up.railway.app/all_products.xlsx"
```

### Варіант Б — локальний файл (для тестування)
```bash
export EXCEL_PATH="../all_products.xlsx"
```

Якщо нічого не задано — бот шукає `all_products.xlsx` поруч з папкою `telegram_bot/`.

---

## 🚀 Запуск локально

### Бот 1
```bash
cd telegram_bot
pip install -r requirements.txt

# Токен вже прописаний у bot1.py, або через змінну:
export BOT_TOKEN="8310562257:AAGF4d3bc4tje50YLeOJymKDrZbBguC3C3E"
export EXCEL_PATH="../all_products.xlsx"

python bot1.py
```

### Бот 2
```bash
export BOT2_TOKEN="<токен існуючого бота>"
export EXCEL_PATH="../all_products.xlsx"

python bot2.py
```

---

## 🚀 Деплой на Railway

1. Зайдіть на [railway.app](https://railway.app)
2. **New Project → Deploy from GitHub repo**
3. Завантажте репозиторій з цими файлами
4. Додайте змінні середовища:

### Для Бота 1:
| Змінна | Значення |
|--------|----------|
| `BOT_TOKEN` | `8310562257:AAGF4d3bc4tje50YLeOJymKDrZbBguC3C3E` |
| `EXCEL_URL` | URL вашого `all_products.xlsx` |

### Для Бота 2 (окремий сервіс):
| Змінна | Значення |
|--------|----------|
| `BOT2_TOKEN` | токен існуючого бота |
| `EXCEL_URL` | той самий URL |

**Startова команда:**
- Бот 1: `python bot1.py`
- Бот 2: `python bot2.py`

---

## 💡 Команди ботів

| Команда | Дія |
|---------|-----|
| `/start` | Головне меню з усіма брендами |
| `/search назва` | Пошук по артикулу або назві |
| `/reload` | Перезавантажити дані з Excel (без рестарту) |

---

## 🔄 Оновлення прайсів

1. Оновіть `all_products.xlsx` на Railway (або за URL)
2. Надішліть `/reload` в бот — дані оновляться без рестарту сервера

---

## 📊 Дані з Excel

Файл `all_products.xlsx` містить аркуші з такими колонками:
```
supplier | sku | name | category | fabric | color | width_cm | height_cm |
price | price_retail | currency | unit | in_stock | collection | contacts
```

- `price_retail` — ціна відріз (відображається в боті як основна)
- `price` — ціна рулону/опт (менша ціна)
- `currency` = `USD` → відображається як `5$  · ~205грн`
- `currency` = `грн` → відображається як `5.00 / 8.00 грн`
- `in_stock` = `sale` → 🔴, `order` → 📦, `out of stock` → ⛔
- `collection` = `НОВИНКА` → 🟢, `Зниження ціни` → 🟡
