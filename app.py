import os
import gradio as gr
import google.generativeai as genai
from tavily import TavilyClient
import tempfile
import sqlite3
import re
from datetime import datetime, timedelta
from fpdf import FPDF

# --- 1. CONFIGURATION ---
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY")
ACCESS_CODE = "PSNDB"

genai.configure(api_key=GOOGLE_API_KEY)
tavily = TavilyClient(api_key=TAVILY_API_KEY)

# Initialize Database for the 15-search limit
def init_db():
    conn = sqlite3.connect("usage.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS usage (ip TEXT, timestamp DATETIME)''')
    conn.commit()
    conn.close()

init_db()

# --- 2. LUXURY STYLING (White on Black) ---
luxury_css = """
body, .gradio-container { background-color: #000000 !important; color: #FFFFFF !important; font-family: 'Inter', sans-serif !important; }
.gr-button-primary { background: #008080 !important; border: none !important; border-radius: 40px !important; color: white !important; font-weight: bold !important; }
.gr-button-secondary { background: #1a1a1a !important; border: 1px solid #333 !important; border-radius: 40px !important; color: #888 !important; }
input, textarea { background: #111 !important; border: 1px solid #333 !important; color: white !important; }
.orb-container { display: flex; justify-content: center; margin: 40px 0; }
.orb { width: 120px; height: 120px; background: radial-gradient(circle, #008080 0%, #000 70%); border-radius: 50%; box-shadow: 0 0 50px #008080; animation: pulse 3s infinite ease-in-out; }
@keyframes pulse { 0% { transform: scale(1); opacity: 0.6; } 50% { transform: scale(1.1); opacity: 1; } 100% { transform: scale(1); opacity: 0.6; } }
"""

# --- 3. CORE FUNCTIONS ---
def check_limit(request: gr.Request):
    if not request: return True
    conn = sqlite3.connect("usage.db")
    c = conn.cursor()
    week_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S')
    c.execute("SELECT COUNT(*) FROM usage WHERE ip=? AND timestamp > ?", (request.client.host, week_ago))
    count = c.fetchone()[0]
    conn.close()
    return count < 15

def get_intel(company, persona, code, request: gr.Request):
    if code != ACCESS_CODE: return gr.update(visible=False), "❌ Invalid Access Code", None
    if not check_limit(request): return gr.update(visible=False), "⚠️ Limit reached (15/week)", None
    
    try:
        # Search & AI Logic
        search = tavily.search(query=f"{company} {persona} 2026 strategic priorities", search_depth="advanced")
        context = "\n".join([r['content'] for r in search['results']])
        
        model = genai.GenerativeModel('gemini-2.5-flash')
        response = model.generate_content(f"Provide a luxury sales briefing for {company} targeting {persona}. Data: {context}").text
        
        # Log usage
        conn = sqlite3.connect("usage.db")
        c = conn.cursor()
        c.execute("INSERT INTO usage VALUES (?,?)", (request.client.host, datetime.now()))
        conn.commit()
        conn.close()

        # PDF Export
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=12)
        pdf.multi_cell(0, 10, txt=response.encode('latin-1', 'ignore').decode('latin-1'))
        temp_pdf = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        pdf.output(temp_pdf.name)
        
        return gr.update(visible=True), response, temp_pdf.name
    except Exception as e:
        return gr.update(visible=False), f"Error: {str(e)}", None

# --- 4. INTERFACE ---
with gr.Blocks(css=luxury_css) as demo:
    gr.HTML("<div style='text-align:center; padding:30px;'> <h1 style='font-size:40px; letter-spacing:-1px;'>ADA STRATEGIC INTELLIGENCE</h1> <p style='color:#666;'>2026 Premium Research Engine</p> </div>")
    gr.HTML("<div class='orb-container'><div class='orb'></div></div>")
    
    with gr.Column(elem_id="login"):
        pwd = gr.Textbox(label="ACCESS CODE", type="password", placeholder="Enter PSNDB...")
        login_btn = gr.Button("INITIALIZE CORE", variant="primary")

    with gr.Column(visible=False) as main_app:
        with gr.Row():
            comp = gr.Textbox(label="COMPANY", placeholder="e.g. Samsung")
            pers = gr.Textbox(label="PERSONA", placeholder="e.g. CMO")
        run = gr.Button("GENERATE BRIEFING", variant="primary")
        output = gr.Markdown()
        pdf_file = gr.File(label="Download PDF Report")

    login_btn.click(lambda x: gr.update(visible=x=="PSNDB"), [pwd], [main_app])
    run.click(get_intel, [comp, pers, pwd], [main_app, output, pdf_file])

if __name__ == "__main__":
    demo.launch()
