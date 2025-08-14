import json
import logging
import math
import os
from datetime import datetime, timezone
from pathlib import Path
import asyncio
from typing import Dict, List, Tuple, Optional

import requests  # blocking; we'll offload with asyncio.to_thread
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# ===================== CONFIG =====================
TOKEN = "8471322511:AAHPf0BkWLVZ8g7Y2Mh4BHHc2sQuENViG0c"              # <-- Bot tokeningizni yozing
ADMIN_ID = 5636501312                  # <-- O'zingizning Telegram user ID'ingiz
USERS_FILE = Path("users.json")

TWELVE_DATA_API_KEY = "9694c7ab6f53406f945981b7245a6a3e"  # <-- Twelve Data kalitingiz
NEWS_API_KEY = "23d297db82234c41b7d6bb1e349104bf"                # <-- (ixtiyoriy) NewsAPI.org kaliti; bo'sh bo'lsa yangilik filtri o'chadi

# 10 ta instrument (foydalanuvchi tanlamaydi — bot o'zi tanlaydi)
# Twelve Data symbol formatlari
SYMBOLS = {
    "XAUUSD": "XAU/USD",
    "EURUSD": "EUR/USD",
    "GBPUSD": "GBP/USD",
    "GBPJPY": "GBP/JPY",
    "USDJPY": "USD/JPY",
    "AUDUSD": "AUD/USD",
    "USDCHF": "USD/CHF",
    "USDCAD": "USD/CAD",
    "NZDUSD": "NZD/USD",
    # NASDAQ indeksini olishga urinamiz – bir nechta nomzod; birinchisi ishlamasa keyingisini sinaymiz
    "NASDAQ": ["IXIC", "NASDAQ", "NDX", "NAS100"]
}
INTERVAL = "5min"
OUTPUTSIZE = 300

# ===================== LOGGING =====================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("signal-bot")

# ===================== STORAGE (users) =====================

def load_users() -> set:
    if USERS_FILE.exists():
        try:
            return set(json.loads(USERS_FILE.read_text()))
        except Exception:
            logger.exception("users.json o'qishda xato, yangidan yarataman")
    return set()

def save_users(users: set) -> None:
    USERS_FILE.write_text(json.dumps(list(users), indent=2))

def add_user(user_id: int) -> None:
    users = load_users()
    if user_id not in users:
        users.add(user_id)
        save_users(users)

# ===================== INDICATORS =====================

def ema(values: List[float], period: int) -> List[Optional[float]]:
    n = len(values)
    if n < period:
        return [None]*n
    k = 2/(period+1)
    out = [None]*(period-1)
    sma = sum(values[:period])/period
    out.append(sma)
    for i in range(period, n):
        out.append(values[i]*k + out[-1]*(1-k))
    return out

def rsi(closes: List[float], period: int = 14) -> List[Optional[float]]:
    n = len(closes)
    if n < period+1:
        return [None]*n
    gains = [0.0]
    losses = [0.0]
    for i in range(1, n):
        diff = closes[i] - closes[i-1]
        gains.append(max(diff, 0.0))
        losses.append(max(-diff, 0.0))
    rsis = [None]*n
    avg_gain = sum(gains[1:period+1])/period
    avg_loss = sum(losses[1:period+1])/period
    rsis[period] = 100 if avg_loss == 0 else 100 - 100/(1 + (avg_gain/avg_loss))
    for i in range(period+1, n):
        avg_gain = (avg_gain*(period-1) + gains[i]) / period
        avg_loss = (avg_loss*(period-1) + losses[i]) / period
        if avg_loss == 0:
            rsis[i] = 100
        else:
            rs = avg_gain/avg_loss
            rsis[i] = 100 - 100/(1+rs)
    return rsis

def macd(closes: List[float], fast: int = 12, slow: int = 26, signal_p: int = 9) -> Tuple[List[Optional[float]], List[Optional[float]], List[Optional[float]]]:
    ema_fast = ema(closes, fast)
    ema_slow = ema(closes, slow)
    macd_line = [None]*len(closes)
    for i in range(len(closes)):
        if ema_fast[i] is not None and ema_slow[i] is not None:
            macd_line[i] = ema_fast[i] - ema_slow[i]
    signal_line = ema([x if x is not None else 0 for x in macd_line], signal_p)
    hist = [None]*len(closes)
    for i in range(len(closes)):
        if macd_line[i] is not None and signal_line[i] is not None:
            hist[i] = macd_line[i] - signal_line[i]
    return macd_line, signal_line, hist

def atr(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> List[Optional[float]]:
    n = len(closes)
    trs = [None]*n
    for i in range(1, n):
        hl = highs[i] - lows[i]
        hc = abs(highs[i] - closes[i-1])
        lc = abs(lows[i] - closes[i-1])
        trs[i] = max(hl, hc, lc)
    if n < period+1:
        return [None]*n
    atrs = [None]*n
    first = sum([x for x in trs[1:period+1] if x is not None])/period
    atrs[period] = first
    for i in range(period+1, n):
        atrs[i] = (atrs[i-1]*(period-1) + (trs[i] or 0)) / period
    return atrs

# ===================== DATA FETCH (Twelve Data + News) =====================

TD_BASE = "https://api.twelvedata.com/time_series"
NEWS_BASE = "https://newsapi.org/v2/everything"


def _fetch_td_symbol(symbol_code: str) -> Dict:
    url = (
        f"{TD_BASE}?symbol={symbol_code}&interval={INTERVAL}"
        f"&outputsize={OUTPUTSIZE}&apikey={TWELVE_DATA_API_KEY}&format=JSON"
    )
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    return r.json()

async def fetch_timeseries(symbol_key: str) -> Optional[Tuple[List[str], List[float], List[float], List[float], List[float]]]:
    if not TWELVE_DATA_API_KEY:
        return None
    code = SYMBOLS[symbol_key]
    json_data = None
    if isinstance(code, list):
        # NASDAQ uchun nomzodlar
        for c in code:
            try:
                json_data = await asyncio.to_thread(_fetch_td_symbol, c)
                if "values" in json_data:
                    break
            except Exception:
                continue
    else:
        json_data = await asyncio.to_thread(_fetch_td_symbol, code)

    if not json_data or "values" not in json_data:
        return None
    values = json_data["values"][::-1]  # eski->yangi
    times = [v["datetime"] for v in values]
    opens = [float(v["open"]) for v in values]
    highs = [float(v["high"]) for v in values]
    lows  = [float(v["low"]) for v in values]
    closes = [float(v["close"]) for v in values]
    return times, opens, highs, lows, closes

POS_WORDS = {"beats", "beat", "growth", "bullish", "rally", "up", "surge", "strong", "cooling inflation", "rate cut"}
NEG_WORDS = {"miss", "misses", "fall", "falls", "down", "drop", "bearish", "risk", "war", "hike", "inflation hot", "recession"}


def _fetch_news(query: str) -> Dict:
    url = f"{NEWS_BASE}?q={query}&pageSize=10&language=en&sortBy=publishedAt&apiKey={NEWS_API_KEY}"
    r = requests.get(url, timeout=15)
    r.raise_for_status()
    return r.json()

async def news_sentiment(symbol_key: str) -> Optional[Tuple[str, int]]:
    """Return (label, score[-5..+5]) or None if NEWS_API_KEY is empty."""
    if not NEWS_API_KEY:
        return None
    # Querylarni soddalashtiramiz
    queries = {
        "XAUUSD": "gold XAU USD",
        "EURUSD": "EUR USD euro dollar forex",
        "GBPUSD": "GBP USD pound dollar forex",
        "GBPJPY": "GBP JPY pound yen forex",
        "USDJPY": "USD JPY dollar yen forex",
        "AUDUSD": "AUD USD aussie dollar forex",
        "USDCHF": "USD CHF dollar franc forex",
        "USDCAD": "USD CAD dollar loonie forex",
        "NZDUSD": "NZD USD kiwi dollar forex",
        "NASDAQ": "Nasdaq index tech stocks"
    }
    query = queries.get(symbol_key, symbol_key)
    try:
        data = await asyncio.to_thread(_fetch_news, query)
        arts = data.get("articles", [])
        score = 0
        for a in arts:
            text = f"{a.get('title','')} {a.get('description','')}".lower()
            if any(w in text for w in POS_WORDS):
                score += 1
            if any(w in text for w in NEG_WORDS):
                score -= 1
        label = "Ijobiy" if score > 1 else ("Salbiy" if score < -1 else "Betaraf")
        score = max(-5, min(5, score))
        return label, score
    except Exception as e:
        logger.warning(f"News fetch failed for {symbol_key}: {e}")
        return None

# ===================== STRATEGY & SIGNAL =====================

class Signal:
    def __init__(self, symbol: str, direction: Optional[str] = None, entry: Optional[float] = None,
                 tp: Optional[float] = None, sl: Optional[float] = None, probability: int = 0,
                 reason: str = "", news_note: str = ""):
        self.symbol = symbol
        self.direction = direction
        self.entry = entry
        self.tp = tp
        self.sl = sl
        self.probability = probability
        self.reason = reason
        self.news_note = news_note

    def is_valid(self):
        return self.direction is not None and self.entry is not None and self.tp is not None and self.sl is not None


def recent_swing_high(highs: List[float], lookback: int = 12) -> float:
    return max(highs[-lookback:])

def recent_swing_low(lows: List[float], lookback: int = 12) -> float:
    return min(lows[-lookback:])


def analyze_symbol(symbol_key: str, times: List[str], opens: List[float], highs: List[float], lows: List[float], closes: List[float], news: Optional[Tuple[str,int]]) -> Signal:
    # Indikatorlar
    ema20 = ema(closes, 20)
    ema200 = ema(closes, 200)
    rsi14 = rsi(closes, 14)
    macd_line, macd_sig, macd_hist = macd(closes)
    atr14 = atr(highs, lows, closes, 14)

    i = len(closes) - 1
    c = closes[i]
    e20 = ema20[i]
    e200 = ema200[i]
    rsi_v = rsi14[i]
    macd_v = macd_line[i]
    macd_s = macd_sig[i]
    atr_v = atr14[i]

    if any(x is None for x in [e20, e200, rsi_v, macd_v, macd_s, atr_v]):
        return Signal(symbol_key)  # no signal

    score = 50  # bazaviy ehtimol (foiz)
    direction = None
    reason = []

    # Trend filtr (EMA200)
    if c > e200:
        score += 8
        trend = "up"
    else:
        score += 0
        trend = "down"

    # Momentum (RSI)
    if rsi_v > 55:
        score += 7
    elif rsi_v < 45:
        score += 7

    # MACD krossover
    prev_macd = macd_line[i-1]
    prev_sig = macd_sig[i-1]
    if prev_macd is not None and prev_sig is not None:
        cross_up = prev_macd <= prev_sig and macd_v > macd_s
        cross_dn = prev_macd >= prev_sig and macd_v < macd_s
    else:
        cross_up = cross_dn = False

    # Triger yo'nalishi (EMA20 bilan pullback + MACD krossover)
    prev_c = closes[i-1]
    prev_e20 = ema20[i-1]
    cross_e_up = prev_c <= prev_e20 and c > e20
    cross_e_dn = prev_c >= prev_e20 and c < e20

    if (trend == "up" and rsi_v > 50 and (cross_up or cross_e_up)):
        direction = "BUY"
        score += 10
        reason.append("Trend(UP)+RSI>50+krossover")
    elif (trend == "down" and rsi_v < 50 and (cross_dn or cross_e_dn)):
        direction = "SELL"
        score += 10
        reason.append("Trend(DOWN)+RSI<50+krossover")

    # Volatilitet filtri (ATR nisbati)
    atr_ratio = atr_v / c
    if atr_ratio < 0.0006:  # juda past volatil – signal kuchsiz
        score -= 6
        reason.append("ATR past")
    elif atr_ratio > 0.0025:  # juda baland – xatar yuqori
        score -= 4
        reason.append("ATR juda yuqori")

    # Yangiliklar ta'siri (ixtiyoriy)
    news_note = ""
    if news is not None:
        label, s = news
        news_note = f"📰 Yangiliklar: {label}"
        score += int(s * 2)  # -10..+10 oralig'ida ta'sir
        reason.append(f"News {label} ({s:+d})")

    # SL/TP – ATR va swinglar asosida
    rr = 1.5
    if direction == "BUY":
        sl = min(recent_swing_low(lows, 12), c - atr_v*1.2)
        risk = c - sl
        tp = c + risk*rr
    elif direction == "SELL":
        sl = max(recent_swing_high(highs, 12), c + atr_v*1.2)
        risk = sl - c
        tp = c - risk*rr
    else:
        return Signal(symbol_key)  # yetarli shart yo'q

    prob = max(50, min(95, int(score)))
    return Signal(symbol_key, direction, c, tp, sl, prob, ", ".join(reason), news_note)


async def build_best_signal() -> Optional[Signal]:
    candidates: List[Signal] = []
    for sym in SYMBOLS.keys():
        try:
            ts = await fetch_timeseries(sym)
            if not ts:
                logger.warning(f"Time series yo'q: {sym}")
                continue
            times, opens, highs, lows, closes = ts
            news = await news_sentiment(sym)
            sig = analyze_symbol(sym, times, opens, highs, lows, closes, news)
            if sig.is_valid():
                candidates.append(sig)
        except Exception as e:
            logger.warning(f"{sym} tahlilida xato: {e}")
            continue

    if not candidates:
        return None

    # Eng yuqori probability tanlanadi; agar teng bo'lsa, eng yuqori RR (tp/SL masofa balansiga yaqin) ko'rib chiqiladi
    candidates.sort(key=lambda s: (s.probability, abs(s.tp - s.entry)), reverse=True)
    best = candidates[0]
    return best

# ===================== UI =====================

def main_menu():
    kb = [
        [InlineKeyboardButton("📊 Signal olish", callback_data="get_signal")],
        [InlineKeyboardButton("ℹ️ Yordam", callback_data="help")],
    ]
    return InlineKeyboardMarkup(kb)


def format_signal_msg(sig: Signal, interval: str = INTERVAL) -> str:
    lines = [
        f"📊 *{sig.symbol} — {interval} SIGNAL*",
        f"Yo‘nalish: *{sig.direction}*",
        f"Entry: *{sig.entry:.5f}*" if sig.entry < 100 else f"Entry: *{sig.entry:.2f}*",
        f"🎯 TP: *{sig.tp:.5f}*" if sig.tp < 100 else f"🎯 TP: *{sig.tp:.2f}*",
        f"🛑 SL: *{sig.sl:.5f}*" if sig.sl < 100 else f"🛑 SL: *{sig.sl:.2f}*",
        f"📌 Ehtimol: *{sig.probability}%*",
    ]
    if sig.news_note:
        lines.append(sig.news_note)
    # sabablar qisqa ko'rinishda
    if sig.reason:
        lines.append("")
        lines.append(f"Izoh: {sig.reason}")
    lines.append("")
    lines.append("Risk: balansning 1% dan ortig'ini xatar qilmang.")
    return "\n".join(lines)

# ===================== HANDLERS =====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user:
        add_user(user.id)
    text = (
        "👋 Salom!\n\n"
        "\- '📊 Signal olish' tugmasini bosing — bot 10 ta instrumentni tahlil qilib, eng yaxshi imkoniyatni yuboradi.\n"
        "\- Admin broadcast: /broadcast MATN\n"
    )
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=main_menu())


async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "get_signal":
        chat_id = query.message.chat_id
        # Yangi xabar sifatida 'tahlil ketyapti' deb yozamiz
        wait_msg = await context.bot.send_message(chat_id=chat_id, text="⏳ 10 ta instrument tahlil qilinyapti...")
        try:
            sig = await build_best_signal()
            if not sig:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=("🤖 Hozircha aniq signal topilmadi. Bozor sust yoki shartlar to'liq emas.\n"
                          "Keyinroq yana urinib ko'ring."),
                    reply_markup=main_menu()
                )
            else:
                text = format_signal_msg(sig)
                await context.bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown", reply_markup=main_menu())
        except Exception as e:
            logger.exception("Signal yaratishda xato")
            await context.bot.send_message(chat_id=chat_id, text=f"❌ Xatolik: {e}")
        finally:
            # kutish xabarini tozalab qo'yamiz (agar xohlasangiz qoldirishingiz mumkin)
            try:
                await wait_msg.delete()
            except Exception:
                pass

    elif query.data == "help":
        await query.edit_message_text(
            "ℹ️ Yordam\n\n"
            "— '📊 Signal olish' bosilganda bot XAUUSD, EURUSD, GBPUSD, NASDAQ, GBPJPY, USDJPY, AUDUSD, USDCHF, USDCAD, NZDUSD bo'yicha tahlil qiladi.\n"
            "— Strategiya: Trend(EMA200) + Momentum(RSI) + MACD krossover + ATR filtri + (ixtiyoriy) yangilik sentimenti.\n"
            "— Signal matni sodda va tushunarli.\n"
            "— Admin: /broadcast MATN – barcha foydalanuvchilarga xabar yuboradi.",
            reply_markup=main_menu()
        )


async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Ruxsat yo'q.")
        return

    msg = " ".join(context.args) if context.args else ""
    if not msg:
        await update.message.reply_text("Foydalanish: /broadcast MATN")
        return

    users = load_users()
    if not users:
        await update.message.reply_text("Hali obunachilar yo'q.")
        return

    ok = 0
    for uid in list(users):
        try:
            await context.bot.send_message(chat_id=uid, text=f"📢 *Admin xabari:*\n{msg}", parse_mode="Markdown")
            ok += 1
        except Exception as e:
            logger.warning(f"{uid} ga yuborilmadi: {e}")
    await update.message.reply_text(f"✅ {ok} ta foydalanuvchiga yuborildi.")


# ===================== BOOT =====================

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CallbackQueryHandler(on_button))

    logger.info("🤖 Bot ishga tushdi...")
    app.run_polling()


if __name__ == "__main__":
    main()
