import os
import gradio as gr
import google.generativeai as genai
from tavily import TavilyClient
import tempfile
import sqlite3
from datetime import datetime, timedelta
from fpdf import FPDF

# --- 1. CONFIG ---
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY")
ACCESS_CODE = "PSNDB"

genai.configure(api_key=GOOGLE_API_KEY)
tavily = TavilyClient(api_key=TAVILY_API_KEY)

def init_db():
    conn = sqlite3.connect("usage.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS usage (ip TEXT, timestamp DATETIME)''')
    conn.commit()
    conn.close()

init_db()

# --- 2. LUXURY UI STYLE ---
luxury_css = """
body, .gradio-container { background-color: #000000 !important; color: #FFFFFF !important; font-family: 'Inter', sans-serif !important; }
.gr-button-primary { background: #008080 !important; border: none !important; border-radius: 40px !important; color: white !important; }
input, textarea { background: #111 !important; border: 1px solid #333 !important; color: white !important; }
.orb-container { display: flex; justify-content: center; margin: 40px 0; }
.orb { width: 100px; height: 100px; background: radial-gradient(circle, #008080 0%, #000 70%); border-radius: 50%; box-shadow: 0 0 40px #008080; animation: pulse 3s infinite; }
@keyframes pulse { 0%, 100% { transform: scale(1); opacity: 0.6; } 50% { transform: scale(1.1); opacity: 1; } }
"""

# --- 3. FUNCTIONS ---
def get_intel(company, persona, code, request: gr.Request):
    if code != ACCESS_CODE: return gr.update(visible=False), "❌ Access Denied", None
    
    try:
        search = tavily.search(query=f"{company} {persona} 2026 news priorities", search_depth="advanced")
        context = "\n".join([r['content'] for r in search['results']])
        
        model = genai.GenerativeModel('gemini-2.5-flash')
        response = model.generate_content(f"Sales Briefing for {company} ({persona}): {context}").text
        
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=12)
        pdf.multi_cell(0, 10, txt=response.encode('latin-1', 'ignore').decode('latin-1'))
        path = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf").name
        pdf.output(path)
        
        return gr.update(visible=True), response, path
    except Exception as e:
        return gr.update(visible=False), f"Error: {str(e)}", None

# --- 4. UI ---
with gr.Blocks(css=luxury_css) as demo:
    gr.HTML("<div style='text-align:center;'><h1>ADA STRATEGIC INTEL</h1><p>Premium 2026 Research</p></div>")
    gr.HTML("<div class='orb-container'><div class='orb'></div></div>")
    
    with gr.Column() as login:
        pwd = gr.Textbox(label="ACCESS CODE", type="password")
        btn_login = gr.Button("INITIALIZE", variant="primary")

    with gr.Column(visible=False) as app:
        comp = gr.Textbox(label="COMPANY")
        pers = gr.Textbox(label="PERSONA")
        run = gr.Button("GENERATE", variant="primary")
        out = gr.Markdown()
        file = gr.File(label="PDF Report")

    btn_login.click(lambda x: gr.update(visible=x=="PSNDB"), [pwd], [app])
    run.click(get_intel, [comp, pers, pwd], [app, out, file])

if __name__ == "__main__":
    demo.launch()
