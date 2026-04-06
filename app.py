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
# 1. SETUP & SECURITY
# ══════════════════════════════════════════════════════════════
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "")
_ACCESS_CODE_RAW = os.environ.get("ACCESS_CODE", "PSNDB")
ACCESS_CODE_HASH = hashlib.sha256(_ACCESS_CODE_RAW.strip().upper().encode()).hexdigest()
del _ACCESS_CODE_RAW

if not GOOGLE_API_KEY or not TAVILY_API_KEY:
    raise EnvironmentError("API Keys missing in HF Secrets.")

genai.configure(api_key=GOOGLE_API_KEY)
tavily = TavilyClient(api_key=TAVILY_API_KEY)

# DB Initialization for Rate Limiting
DB_PATH = "/tmp/ada_usage.db"
def _init_db():
    con = sqlite3.connect(DB_PATH)
    con.execute("CREATE TABLE IF NOT EXISTS usage (ip_hash TEXT, week TEXT, count INTEGER, PRIMARY KEY (ip_hash, week))")
    con.execute("CREATE TABLE IF NOT EXISTS access_attempts (ip_hash TEXT, window_start INTEGER, attempts INTEGER, PRIMARY KEY (ip_hash))")
    con.commit()
    con.close()
_init_db()

# ══════════════════════════════════════════════════════════════
# 2. PREMIUM UI STYLING (APP_CSS)
# ══════════════════════════════════════════════════════════════
APP_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700&family=Inter:wght@300;400;500;600&display=swap');

footer { visibility: hidden !important; }
.gradio-container {
    background: radial-gradient(circle at top left, #0f172a 0%, #020617 100%) !important;
    min-height: 100vh !important;
    font-family: 'Inter', sans-serif !important;
}

/* Glassmorphism Cards */
.gr-group, .gr-box, .gradio-group {
    background: rgba(255, 255, 255, 0.03) !important;
    border: 1px solid rgba(255, 255, 255, 0.08) !important;
    border-radius: 24px !important;
    backdrop-filter: blur(12px) !important;
}

/* Typography */
h1 { font-family: 'Playfair Display', serif !important; color: white !important; }
label { color: #94a3b8 !important; font-weight: 600 !important; font-size: 0.8em !important; text-transform: uppercase; }

/* Inputs */
input[type=text], textarea {
    background: rgba(15, 23, 42, 0.8) !important;
    border: 1px solid rgba(255, 255, 255, 0.1) !important;
    color: white !important;
    border-radius: 12px !important;
}

/* The Premium Blue Button */
.gr-button-primary, button.primary {
    background: linear-gradient(135deg, #0ea5e9 0%, #2563eb 100%) !important;
    border: none !important;
    box-shadow: 0 10px 25px -5px rgba(37, 99, 235, 0.4) !important;
    transition: all 0.3s ease !important;
}
.gr-button-primary:hover { transform: translateY(-2px) !important; }
"""

# ══════════════════════════════════════════════════════════════
# 3. PDF GENERATOR (Fixes Unicode/Helvetica Errors)
# ══════════════════════════════════════════════════════════════
def _build_pdf(company, persona, content):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_fill_color(15, 23, 42)
    pdf.rect(0, 0, 210, 30, "F")
    
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(255, 255, 255)
    pdf.set_xy(10, 10)
    pdf.cell(0, 10, "ADA STRATEGIC BRIEFING")
    
    # Character Sanitizer for Helvetica
    rep = {'–': '-', '—': '-', '‘': "'", '’': "'", '“': '"', '”': '"', '•': '-', '…': '...'}
    clean_text = content
    for old, new in rep.items():
        clean_text = clean_text.replace(old, new)
    clean_text = clean_text.encode('latin-1', 'ignore').decode('latin-1')

    pdf.set_xy(10, 35)
    pdf.set_text_color(40, 40, 40)
    pdf.set_font("Helvetica", "", 10)
    
    for line in clean_text.splitlines():
        if not line.strip(): pdf.ln(4)
        else: pdf.multi_cell(190, 6, line.strip())

    path = os.path.join(tempfile.gettempdir(), f"Briefing_{secrets.token_hex(4)}.pdf")
    pdf.output(path)
    return path

# ══════════════════════════════════════════════════════════════
# 4. CORE ENGINE
# ══════════════════════════════════════════════════════════════
def _ip_hash(req: gr.Request):
    return hashlib.sha256((req.client.host if req else "local").encode()).hexdigest()[:16]

def _verify_code(entered, request: gr.Request):
    ip = _ip_hash(request)
    h = hashlib.sha256(entered.strip().upper().encode()).hexdigest()
    if secrets.compare_digest(h, ACCESS_CODE_HASH):
        return True, "✅ Access Granted"
    return False, "❌ Invalid Code"

def _md_to_html(text):
    text = text.replace("**", "<strong>").replace("**", "</strong>")
    return text.replace("\n", "<br>")

def _build_dashboard_html(company, persona, sections):
    html = f"""
    <div style='color: white; padding: 10px;'>
        <span style='color: #38bdf8; letter-spacing: 2px; font-size: 0.7em; font-weight: 700;'>MARKET INTELLIGENCE</span>
        <h2 style='font-family: "Playfair Display", serif; font-size: 2.2em; margin: 10px 0;'>{company}</h2>
        <div style='display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin-top: 20px;'>
            <div style='background: rgba(255,255,255,0.05); padding: 20px; border-radius: 15px; border: 1px solid rgba(255,255,255,0.1);'>
                <h4 style='color: #38bdf8; margin-bottom: 10px; font-size: 0.8em;'>FINANCIALS</h4>
                <p style='font-size: 0.9em; line-height: 1.6; color: #cbd5e0;'>{_md_to_html(sections.get("financial", ""))}</p>
            </div>
            <div style='background: rgba(255,255,255,0.05); padding: 20px; border-radius: 15px; border: 1px solid rgba(255,255,255,0.1);'>
                <h4 style='color: #38bdf8; margin-bottom: 10px; font-size: 0.8em;'>STRATEGY</h4>
                <p style='font-size: 0.9em; line-height: 1.6; color: #cbd5e0;'>{_md_to_html(sections.get("strategy", ""))}</p>
            </div>
        </div>
    </div>
    """
    return html

def run_research(company, persona, request: gr.Request):
    try:
        search = tavily.search(query=f"{company} 2026 business strategy {persona}", max_results=5)
        context = "\n".join([r['content'] for r in search['results']])
        
        model = genai.GenerativeModel("gemini-1.5-flash")
        prompt = f"Target: {persona} at {company}. Context: {context}. Provide two sections: ## Financial and ## Strategy."
        response = model.generate_content(prompt).text
        
        # Simple parser
        parts = response.split("##")
        sec = {"financial": parts[1] if len(parts)>1 else "", "strategy": parts[2] if len(parts)>2 else ""}
        
        html = _build_dashboard_html(company, persona, sec)
        pdf = _build_pdf(company, persona, response)
        return html, pdf
    except Exception as e:
        return f"<div style='color:red'>Error: {str(e)}</div>", None

# ══════════════════════════════════════════════════════════════
# 5. GRADIO INTERFACE
# ══════════════════════════════════════════════════════════════
with gr.Blocks(css=APP_CSS, title="ADA Intelligence") as demo:
    # State for access
    access_granted = gr.State(False)

    # ── GATE SCREEN ──
    with gr.Column(visible=True) as gate_screen:
        gr.HTML("<div style='text-align:center; padding: 100px 0;'><h1 style='font-size:3em;'>ADA Global</h1><p style='color:#94a3b8;'>Internal Sales Intelligence Portal</p></div>")
        with gr.Row():
            with gr.Column(scale=1): pass
            with gr.Column(scale=2):
                code_in = gr.Textbox(label="Access Code", type="password", placeholder="••••")
                login_btn = gr.Button("Enter Portal", variant="primary")
                login_msg = gr.HTML("")
            with gr.Column(scale=1): pass

    # ── MAIN DASHBOARD ──
    with gr.Column(visible=False) as main_screen:
        gr.HTML("<div style='padding: 20px 0;'><h1 style='font-size:1.8em;'>Sales Intelligence Dashboard</h1></div>")
        with gr.Row():
            with gr.Column(scale=1):
                comp_input = gr.Textbox(label="Company Name", placeholder="e.g. Samsung")
                pers_input = gr.Textbox(label="Target Persona", placeholder="e.g. CMO")
                gen_btn = gr.Button("Generate Briefing", variant="primary")
                pdf_down = gr.File(label="Download Briefing")
            with gr.Column(scale=2):
                output_html = gr.HTML("<div style='text-align:center; padding: 50px; color: #475569;'>Ready for research...</div>")

    # ── LOGIC ──
    def handle_login(code, req: gr.Request):
        ok, msg = _verify_code(code, req)
        if ok: return gr.update(visible=False), gr.update(visible=True), True
        return gr.update(visible=True), gr.update(visible=False), False

    login_btn.click(handle_login, [code_in], [gate_screen, main_screen, access_granted])
    gen_btn.click(run_research, [comp_input, pers_input], [output_html, pdf_down])

demo.launch()
