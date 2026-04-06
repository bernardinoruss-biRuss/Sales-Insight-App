import os
import re
import time
import sqlite3
import hashlib
import secrets
import tempfile
import datetime
import gradio as gr
import google.generativeai as genai
from tavily import TavilyClient
from fpdf import FPDF

# ══════════════════════════════════════════════════════════════
# 1. ENVIRONMENT & API KEYS
# ══════════════════════════════════════════════════════════════
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "")
_ACCESS_CODE_RAW = os.environ.get("ACCESS_CODE", "PSNDB")
ACCESS_CODE_HASH = hashlib.sha256(_ACCESS_CODE_RAW.strip().upper().encode()).hexdigest()
del _ACCESS_CODE_RAW

if not GOOGLE_API_KEY or not TAVILY_API_KEY:
    raise EnvironmentError("Missing API keys. Set GOOGLE_API_KEY and TAVILY_API_KEY in HF Secrets.")

genai.configure(api_key=GOOGLE_API_KEY)
tavily = TavilyClient(api_key=TAVILY_API_KEY)

# ══════════════════════════════════════════════════════════════
# 2. SQLITE — Rate Limiting
# ══════════════════════════════════════════════════════════════
DB_PATH = "/tmp/ada_usage.db"

def _init_db():
    con = sqlite3.connect(DB_PATH)
    con.execute("CREATE TABLE IF NOT EXISTS usage (ip_hash TEXT, week TEXT, count INTEGER, PRIMARY KEY (ip_hash, week))")
    con.execute("CREATE TABLE IF NOT EXISTS access_attempts (ip_hash TEXT, window_start INTEGER, attempts INTEGER, PRIMARY KEY (ip_hash))")
    con.commit()
    con.close()

_init_db()

WEEKLY_LIMIT = 15
MAX_CODE_TRIES = 5
LOCKOUT_SECS = 900

def _current_week():
    today = datetime.date.today()
    return f"{today.isocalendar()[0]}-W{today.isocalendar()[1]:02d}"

def _ip_hash(request: gr.Request):
    raw = (request.client.host if request and request.client else "unknown")
    return hashlib.sha256(raw.encode()).hexdigest()[:20]

def _get_usage(ip_hash):
    con = sqlite3.connect(DB_PATH)
    row = con.execute("SELECT count FROM usage WHERE ip_hash=? AND week=?", (ip_hash, _current_week())).fetchone()
    con.close()
    return row[0] if row else 0

def _increment_usage(ip_hash):
    con = sqlite3.connect(DB_PATH)
    con.execute("INSERT INTO usage(ip_hash, week, count) VALUES(?,?,1) ON CONFLICT(ip_hash, week) DO UPDATE SET count=count+1", (ip_hash, _current_week()))
    con.commit()
    con.close()

def _check_lockout(ip_hash):
    now = int(time.time())
    con = sqlite3.connect(DB_PATH)
    row = con.execute("SELECT window_start, attempts FROM access_attempts WHERE ip_hash=?", (ip_hash,)).fetchone()
    con.close()
    if not row: return False, MAX_CODE_TRIES
    ws, att = row
    if now - ws > LOCKOUT_SECS: return False, MAX_CODE_TRIES
    if att >= MAX_CODE_TRIES: return True, LOCKOUT_SECS - (now - ws)
    return False, MAX_CODE_TRIES - att

def _record_failed_attempt(ip_hash):
    now = int(time.time())
    con = sqlite3.connect(DB_PATH)
    con.execute("INSERT INTO access_attempts(ip_hash, window_start, attempts) VALUES(?,?,1) ON CONFLICT(ip_hash) DO UPDATE SET attempts=attempts+1", (ip_hash, now))
    con.commit()
    con.close()

def _reset_attempts(ip_hash):
    con = sqlite3.connect(DB_PATH)
    con.execute("DELETE FROM access_attempts WHERE ip_hash=?", (ip_hash,))
    con.commit()
    con.close()

# ══════════════════════════════════════════════════════════════
# 3. VERIFICATION & SANITIZATION
# ══════════════════════════════════════════════════════════════
def _verify_code(entered, request: gr.Request):
    ip = _ip_hash(request)
    locked, info
