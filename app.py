import os
import gradio as gr
from google import genai
from tavily import TavilyClient
import tempfile
from fpdf import FPDF
import time
import random
import json

# --- SECURE CONFIG ---
client = genai.Client(api_key=os.environ.get("GOOGLE_API_KEY"))
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY")
tavily = TavilyClient(api_key=TAVILY_API_KEY)
ACCESS_CODE = os.environ.get("PORTAL_ACCESS_CODE")
USAGE_FILE = "usage_tracker.json"
WEEKLY_REPORT_LIMIT = 15 

# --- USAGE TRACKER LOGIC ---
def check_usage(username):
    if not os.path.exists(USAGE_FILE):
        with open(USAGE_FILE, "w") as f: json.dump({}, f)
    with open(USAGE_FILE, "r") as f:
        data = json.load(f)
    user_data = data.get(username, {"reports": 0, "last_reset": time.time()})
    if time.time() - user_data["last_reset"] > 604800:
        user_data = {"reports": 0, "last_reset": time.time()}
    if user_data["reports"] >= WEEKLY_REPORT_LIMIT:
        return False, user_data["reports"]
    user_data["reports"] += 1
    data[username] = user_data
    with open(USAGE_FILE, "w") as f:
        json.dump(data, f)
    return True, user_data["reports"]

# --- STABILITY WRAPPER ---
def safe_generate(prompt):
    for attempt in range(3):
        try:
            response = client.models.generate_content(model="gemini-2.0-flash-lite", contents=prompt)
            return response.text
        except Exception as e:
            if "429" in str(e): raise e
            if attempt < 2:
                time.sleep(2 + random.random())
                continue
            raise e

# --- PREMIUM UI CSS ---
luxury_css = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;700;800&display=swap');
body, .gradio-container { 
    background-color: #FF99AC !important;
    background-image: radial-gradient(at 0% 0%, hsla(253,16%,7%,1) 0px, transparent 50%), radial-gradient(at 50% 0%, hsla(225,39%,30%,1) 0px, transparent 50%), radial-gradient(at 100% 0%, hsla(339,49%,30%,1) 0px, transparent 50%) !important;
    background-size: 200% 200% !important; animation: meshGradient 18s ease infinite !important; font-family: 'Inter', sans-serif !important; 
}
@keyframes meshGradient { 0% { background-position: 0% 50%; } 50% { background-position: 100% 50%; } 100% { background-position: 0% 50%; } }
.sidebar, .main-card { background: rgba(255, 255, 255, 0.85) !important; backdrop-filter: blur(25px); border-radius: 32px !important; padding: 30px !important; border: 1px solid rgba(255, 255, 255, 0.4) !important; }
.ada-branding { font-size: 48px !important; font-weight: 800 !important; color: #003366 !important; letter-spacing: -2px !important; margin: 0 !important; line-height: 1; }
.sales-tagline { font-size: 13px !important; font-weight: 700 !important; color: #003366 !important; opacity: 0.8; margin-top: 5px !important; }

.robot-loader {
    width: 60px; height: 50px; background: #003366; border-radius: 12px;
    position: relative; animation: robotFloat 2s ease-in-out infinite;
}
.robot-loader::before, .robot-loader::after {
    content: ''; position: absolute; width: 10px; height: 10px; 
    background: #FF99AC; border-radius: 50%; top: 15px; animation: blink 1.5s infinite;
}
.robot-loader::before { left: 12px; }
.robot-loader::after { right: 12px; }
@keyframes robotFloat { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-10px); } }
@keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }

.info-icon-wrapper { position: absolute; top: 20px; right: 20px; cursor: help; z-index: 100; }
.info-icon { background: #003366; color: white; width: 24px; height: 24px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: bold; font-size: 14px; }
.tooltip-content { 
    visibility: hidden; width: 280px; background-color: #001a33; color: white !important; text-align: left; border-radius: 12px; padding: 15px; 
    position: absolute; z-index: 101; right: 0; top: 30px; opacity: 0; transition: opacity 0.3s; font-size: 12px; line-height: 1.5; 
    border: 1px solid #FF99AC; text-shadow: 0px 1px 2px rgba(0,0,0,0.5);
}
.info-icon-wrapper:hover .tooltip-content { visibility: visible; opacity: 1; }

.loader-container { display: flex; flex-direction: column; align-items: center; padding: 30px; }
.progress-bar-bg { width: 100%; max-width: 300px; height: 8px; background: rgba(0, 51, 102, 0.1); border-radius: 10px; overflow: hidden; margin-top: 20px; }
.progress-bar-fill { width: 0%; height: 100%; background: #003366; animation: progressFill 5s infinite; }
@keyframes progressFill { 0% { width: 0%; } 100% { width: 100%; } }
.st-button { background: linear-gradient(90deg, #001a33, #003366) !important; border-radius: 50px !important; color: white !important; font-weight: 800 !important; height: 50px; }
"""

def generate_pdf(content):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("helvetica", 'B', 16)
    pdf.cell(0, 10, "ADA STRATEGIC BRIEFING", new_x="LMARGIN", new_y="NEXT", align='C')
    pdf.ln(10)
    pdf.set_font("helvetica", size=10)
    clean_text = content.replace("## ", "").replace("### ", "").replace("---", "________________")
    pdf.multi_cell(0, 7, txt=clean_text)
    path = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf").name
    pdf.output(path)
    return path

def run_ada_research(company, persona, code):
    if not company or not persona or not code:
        yield "⚠️ Missing Fields", None, "❌ Error"
        return

    if code != ACCESS_CODE:
        yield "🚫 Access Denied", None, "🚫 Code Incorrect"
        return
    
    # --- 🛡️ 1. PRE-FLIGHT QUOTA CHECK ---
    try:
        client.models.generate_content(model="gemini-2.0-flash-lite", contents="ping")
    except Exception as e:
        if "429" in str(e):
            yield "⚠️ AI Quota Empty. Please swap GOOGLE_API_KEY.", None, "❌ AI Blocked"
            return
        yield f"⚠️ Connection Error: {str(e)}", None, "❌ Error"
        return

    # --- 🚦 2. USAGE TRACKER ---
    allowed, current_count = check_usage(persona.strip().lower())
    if not allowed:
        yield f"⚠️ Weekly Limit Reached. ({current_count}/{WEEKLY_REPORT_LIMIT})", None, "❌ Limit Reached"
        return

    loading_html = f"""
    <div class="loader-container">
        <div class="robot-loader"></div>
        <div class="progress-bar-bg"><div class="progress-bar-fill"></div></div>
        <div style="margin-top:15px; font-weight:700; color:#003366; font-size:12px;">ADA ROBOT ANALYZING {company.upper()}...</div>
    </div>
    """
    yield loading_html, None, "⚡ Processing..."
    
    try:
        query = f"{company} technology stack 2025"
        search = tavily.search(query=query, search_depth="advanced")
        context = "\n".join([r['content'] for r in search['results']])[:2500] 
        sources = "## 🔗 SOURCES\n" + "\n".join([f"* [{r['title']}]({r['url']})" for r in search['results']])
        
        prompt = f"Act as a Senior Strategist at ADA Global. Create a detailed Strategic Brief for {company} and {persona}. Data: {context}"
        response_text = safe_generate(prompt)
        full_report = f"# ADA STRATEGIC BRIEFING\n\n{response_text}\n\n---\n{sources}"
        pdf_file = generate_pdf(full_report)
        yield full_report, pdf_file, "✅ Completed"
    except Exception as e:
        yield f"⚠️ System Busy. Error: {str(e)}", None, "❌ Error"

# --- INTERFACE ---
with gr.Blocks() as demo:
    with gr.Row():
        with gr.Column(scale=1, elem_classes="sidebar"):
            gr.HTML("<div style='text-align:center;'><h1 class='ada-branding'>ADA</h1><p class='sales-tagline'>Sales Intelligence Tool</p></div>")
            comp_input = gr.Textbox(label="COMPANY", placeholder="e.g. DBS Bank")
            pers_input = gr.Textbox(label="PERSONA", placeholder="Your Name")
            code_input = gr.Textbox(label="ACCESS CODE", type="password")
            main_btn = gr.Button("🔍 RUN RESEARCH", elem_classes="st-button")
            status = gr.Markdown("Ready.")
        with gr.Column(scale=2, elem_classes="main-card"):
            gr.HTML(f"""
                <div class="info-icon-wrapper">
                    <div class="info-icon">i</div>
                    <div class="tooltip-content">
                        <b>ADA Usage Guidelines:</b><br>
                        • <b>Tavily Protection:</b> App pings AI first to save credits.<br>
                        • <b>Weekly Limit:</b> {WEEKLY_REPORT_LIMIT} Reports per person.<br>
                        • <b>Model:</b> Gemini 2.0 Flash-Lite.<br>
                        • <b>Robot UI:</b> Pulsing eyes = active processing.
                    </div>
                </div>
            """)
            gr.HTML("<div style='text-align:center; margin-bottom: 20px;'><h2 style='margin:0;'>Strategic Brief powered by AI</h2></div>")
            brief_output = gr.Markdown("Ready for research...", elem_id="strategy-output")
            download_btn = gr.File(label="📥 Download Strategy PDF")
    
    # Force direct concurrency to prevent button hanging
    main_btn.click(
        fn=run_ada_research, 
        inputs=[comp_input, pers_input, code_input], 
        outputs=[brief_output, download_btn, status],
        concurrency_id="research_queue"
    )

if __name__ == "__main__":
    # Disable SSR mode and enable queueing to fix button unresponsiveness
    demo.queue(default_concurrency_limit=10).launch(css=luxury_css, ssr_mode=False)
