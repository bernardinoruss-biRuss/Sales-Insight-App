import os
import gradio as gr
import google.generativeai as genai
from tavily import TavilyClient
import tempfile
import sqlite3
from datetime import datetime, timedelta
from fpdf import FPDF

# --- 1. AUTHENTICATION & DATABASE ---
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY")
ACCESS_CODE = "PSNDB"

genai.configure(api_key=GOOGLE_API_KEY)
tavily = TavilyClient(api_key=TAVILY_API_KEY)

# Initialize Rate-Limit Database
def init_db():
    conn = sqlite3.connect("usage.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS usage 
                 (ip TEXT, timestamp DATETIME)''')
    conn.commit()
    conn.close()

init_db()

# --- 2. CORE LOGIC & SECURITY ---

def check_rate_limit(request: gr.Request):
    """Checks if the user IP has exceeded 15 searches in the last 7 days."""
    ip = request.client.host
    conn = sqlite3.connect("usage.db")
    c = conn.cursor()
    one_week_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S')
    c.execute("SELECT COUNT(*) FROM usage WHERE ip = ? AND timestamp > ?", (ip, one_week_ago))
    count = c.fetchone()[0]
    conn.close()
    return count < 15, count

def log_usage(request: gr.Request):
    ip = request.client.host
    conn = sqlite3.connect("usage.db")
    c = conn.cursor()
    c.execute("INSERT INTO usage VALUES (?, ?)", (ip, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    conn.commit()
    conn.close()

def generate_pdf(content, company):
    """Generates a professional PDF report."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(200, 10, txt=f"ADA Strategic Briefing: {company}", ln=True, align='C')
    pdf.ln(10)
    pdf.set_font("Arial", size=11)
    # Clean up markdown symbols for PDF compatibility
    clean_text = content.replace("##", "").replace("**", "").replace("*", "-")
    pdf.multi_cell(0, 10, txt=clean_text)
    
    path = os.path.join(tempfile.gettempdir(), f"ADA_Report_{company}.pdf")
    pdf.output(path)
    return path

def get_sales_intelligence(company, persona, code, request: gr.Request):
    # Security: Access Code Check
    if code != ACCESS_CODE:
        return gr.update(visible=False), "### ❌ Incorrect Access Code.", None
    
    # Security: Rate Limit Check
    allowed, count = check_rate_limit(request)
    if not allowed:
        return gr.update(visible=False), f"### ⚠️ Rate Limit Exceeded (15/week). Current: {count}", None

    try:
        # 1. Search (BFSI Detection)
        search_query = f"{company} industry sector 2026 financial report"
        search_res = tavily.search(query=search_query, search_depth="basic")
        is_bfsi = any(word in str(search_res).lower() for word in ["bank", "insurance", "financial", "lending"])

        # 2. Main Strategic Research
        main_query = f"strategic priorities {company} {persona} 2026 challenges news"
        res = tavily.search(query=main_query, search_depth="advanced", max_results=6)
        context = "\n".join([f"[{r['url']}] {r['content']}" for r in res.get('results', [])])

        # 3. AI Generation
        model = genai.GenerativeModel('gemini-2.5-flash')
        prompt = f"Act as a Sales Director. Analyze {company} for {persona}. Context: {context}. Respond in 5 segments: Financials, News, Approach, Priorities, ADA Strategy."
        ai_res = model.generate_content(prompt).text

        # Log success
        log_usage(request)
        
        # UI Theme Adjustment (Logic returns different HTML blocks based on BFSI)
        theme_color = "#041E41" if not is_bfsi else "#004a99" # Deeper blue for BFSI
        
        # Split AI response into sections for the Dashboard
        sections = ai_res.split("##")
        
        pdf_path = generate_pdf(ai_res, company)

        # Build Dashboard HTML
        dashboard_html = f"""
        <div style="border-left: 10px solid {theme_color}; padding-left: 20px;">
            <h2 style="color:{theme_color};">📊 {company} Intelligence Dashboard</h2>
            <p><i>Industry: {'Banking/Finance' if is_bfsi else 'Corporate'} | Data Grounded in 2026 Reports</i></p>
        </div>
        """
        
        return gr.update(visible=True), ai_res, pdf_path

    except Exception as e:
        return gr.update(visible=False), f"Error: {str(e)}", None

# --- 3. UI DESIGN (Gradio Blocks) ---

custom_css = """
.gradio-container { background-color: #fcfcfc; }
.loading-box { text-align: center; padding: 50px; }
.pulsing-brain { font-size: 50px; animation: pulse 1.5s infinite; }
@keyframes pulse { 0% { transform: scale(1); opacity: 1; } 50% { transform: scale(1.2); opacity: 0.7; } 100% { transform: scale(1); opacity: 1; } }
.tab-nav { display: flex; justify-content: space-around; border-bottom: 2px solid #ddd; margin-bottom: 20px; }
"""

with gr.Blocks(css=custom_css, title="ADA Sales Intel") as demo:
    # 1. Header & Access
    gr.HTML("""
    <div style="background: linear-gradient(90deg, #041E41, #008080); padding: 40px; border-radius: 15px; color: white; text-align: center;">
        <h1 style="margin:0;">ADA GLOBAL STRATEGIC INTELLIGENCE</h1>
        <p>Advanced 2026 Persona-Based Coaching Dashboard</p>
    </div>
    """)
    
    with gr.Row():
        with gr.Column(scale=1):
            access_input = gr.Textbox(label="🔐 Access Code", type="password", placeholder="Enter code to unlock...")
            comp_input = gr.Textbox(label="Company Name", placeholder="e.g., Goldman Sachs")
            pers_input = gr.Textbox(label="Target Persona", placeholder="e.g., Head of Digital")
            
            with gr.Row():
                run_btn = gr.Button("🔍 GENERATE INSIGHTS", variant="primary")
                info_btn = gr.Button("ℹ️", variant="secondary", size="sm", min_width=10)
            
            download_area = gr.File(label="📥 Download PDF Report")

        with gr.Column(scale=2):
            # The Dashboard Output
            with gr.Tabs(visible=False) as output_tabs:
                with gr.Tab("📋 Strategic Briefing"):
                    out_content = gr.Markdown()
                with gr.Tab("📈 Financials & News"):
                    gr.Markdown("Deep-dive financial triggers and 2026 news events.")
                with gr.Tab("💡 Approach Strategy"):
                    gr.Markdown("Persona-specific hooks and discovery questions.")

    # 4. Loading State Simulation
    load_html = gr.HTML("""
        <div class='loading-box'>
            <div class='pulsing-brain'>🧠</div>
            <h3 id='loading-text'>Analyzing 2026 Financial Reports...</h3>
        </div>
    """, visible=False)

    # UI Event Logic
    run_btn.click(
        fn=lambda: (gr.update(visible=True), gr.update(visible=False)),
        outputs=[load_html, output_tabs]
    ).then(
        fn=get_sales_intelligence,
        inputs=[comp_input, pers_input, access_input],
        outputs=[output_tabs, out_content, download_area]
    ).then(
        fn=lambda: gr.update(visible=False),
        outputs=[load_html]
    )

    info_btn.click(fn=lambda: gr.Info("Beta Limit: 15 searches per week per user."))

if __name__ == "__main__":
    demo.launch()
