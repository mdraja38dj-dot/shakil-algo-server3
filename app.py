import os
import requests
import sqlite3
import yfinance as yf
import numpy as np
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

API_KEY = os.environ.get("GEMINI_API_KEY")

GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={API_KEY}"


# ================= DB =================
def init_db():
    conn = sqlite3.connect("signals.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            time TEXT,
            market TEXT,
            tf TEXT,
            signal TEXT,
            accuracy TEXT,
            reason TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()


# ================= DATA =================
def get_data(symbol, tf):
    try:
        if "BTC" in symbol:
            ticker = "BTC-USD"
        elif "XAU" in symbol:
            ticker = "GC=F"
        else:
            ticker = symbol + "=X"

        df = yf.download(ticker, period="2d", interval=f"{tf}m", progress=False)

        if df is None or df.empty:
            return None

        df = df.dropna()
        return df.tail(50)

    except:
        return None


# ================= CANDLE =================
def candle(df):
    last = df.iloc[-1]

    o, h, l, c = last["Open"], last["High"], last["Low"], last["Close"]

    body = abs(c - o)
    full = h - l if h != l else 1

    color = "GREEN" if c > o else "RED"

    score = 1 if color == "GREEN" else -1

    if body / full > 0.6:
        score += 2

    return score


# ================= SIGNAL =================
def signal_engine(df):
    ema20 = df["Close"].ewm(span=20).mean()
    ema50 = df["Close"].ewm(span=50).mean()

    trend = "UP" if ema20.iloc[-1] > ema50.iloc[-1] else "DOWN"

    score = 0
    score += 2 if trend == "UP" else -2
    score += candle(df)

    if score >= 3:
        return "CALL", score
    elif score <= -3:
        return "PUT", score
    else:
        return "WAIT", score


# ================= AI =================
def ai(text):
    try:
        r = requests.post(GEMINI_URL, json={
            "contents": [{"parts": [{"text": text}]}]
        })
        return r.json()["candidates"][0]["content"]["parts"][0]["text"]
    except:
        return "AI ERROR"


# ================= API =================
@app.route("/get_analysis")
def run():

    market = request.args.get("market", "EURUSD")
    tf = request.args.get("timeframe", "1")

    df = get_data(market, tf)

    if df is None:
        return jsonify({"signal": "WAIT", "reason": "No Data"})

    signal, score = signal_engine(df)

    prompt = f"Market {market}, signal {signal}, score {score}. Explain short."

    reason = ai(prompt)

    conn = sqlite3.connect("signals.db")
    c = conn.cursor()
    c.execute("""
        INSERT INTO signals (time, market, tf, signal, accuracy, reason)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        market,
        tf,
        signal,
        f"{min(100, abs(score)*20)}%",
        reason
    ))
    conn.commit()
    conn.close()

    return jsonify({
        "signal": signal,
        "score": score,
        "accuracy": f"{min(100, abs(score)*20)}%",
        "reason": reason
    })


# ================= RUN =================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
