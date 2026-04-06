import os
import gradio as gr
import google.generativeai as genai
from tavily import TavilyClient
import tempfile
import sqlite3
import re
from datetime import datetime, timedelta
from fpdf import FPDF
import shutil

# --- 1. CONFIGURATION & DATABASE ---
# Load secrets from Environment Variables (Hf Secrets)
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY")
ACCESS_CODE = os.environ.get("ACCESS_CODE", "PSNDB")

# Verify essential secrets
if not GOOGLE_API_KEY or not TAVILY_API_KEY:
    raise ValueError("Missing API Keys! Ensure GOOGLE_API_KEY and TAVILY_API_KEY are in your Hf Space Secrets.")

# Configure Clients
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

# --- 2. LUXURY CSS (White-on-Black + Typography) ---
luxury_css = """
/* 1. Base Luxury Theme (White on Black) */
body, .gradio-container { background-color: #000000 !important; color: #FFFFFF !important; font-family: 'DM Sans', 'Inter', sans-serif !important; }
h1, h2, h3 { font-family: 'DM Serif Display', serif !important; letter-spacing: -0.02em; }
p, li, label, .gr-form-label { color: #CCCCCC !important; font-size: 1.05rem; }

/* 2. Remove standard Gradio borders and shadows for minimalist feel */
.gr-box, .gr-panel, .gr-form, .gr-block { border: none !important; box-shadow: none !important; background: transparent !important; }

/* 3. Luxury Input Fields (Subtle outlines, white text) */
input, textarea { background-color: #111111 !important; border: 1px solid #333333 !important; color: #FFFFFF !important; border-radius: 8px !important; padding: 12px !important; }
input:focus, textarea:focus { border-color: #008080 !important; box-shadow: 0 0 10px rgba(0, 128, 128, 0.4) !important; }

/* 4. Luxury Buttons (Minimalist, dark teal accent) */
.gr-button-primary { background-color: #008080 !important; color: #FFFFFF !important; border-radius: 50px !important; font-weight: 700 !important; text-transform: uppercase !important; letter-spacing: 1px !important; border: none !important; transition: all 0.3s ease !important; }
.gr-button-primary:hover { background-color: #00A3A3 !important; transform: translateY(-3px); }
.gr-button-secondary { background-color: #222222 !important; color: #CCCCCC !important; border-radius: 50px !important; border: 1px solid #444444 !important; }

/* 5. Dashboard Output Styling (Segmented white text) */
.output-tab { background-color: #111111; padding: 30px; border-radius: 12px; border: 1px solid #333333; margin-top: 20px; }
.sources-list { margin-top: 30px; border-top: 1px solid #333333; padding-top: 20px; }
.source-link { color: #00A3A3 !important; font-size: 0.9em; text-decoration: none; }

/* 6. Footer Minimalism */
footer { display: none !important; }
"""

# --- 3. CORE LOGIC ---

def clean_markdown(text):
    """Sanitizes AI text for better Markdown rendering."""
    # Remove excessive backticks and newlines
    text = re.sub(r'```[a-z]*', '', text)
    text = re.sub(r'```', '', text)
    text = text.replace('\xa0', ' ')
    return text.strip()

def check_rate_limit(request: gr.Request):
    """Checks if the user IP has exceeded 15 searches in the last 7 days."""
    if not request or not request.client:
        return True, 0 # Allow if IP is missing (e.g., local test)
    ip = request.client.host
    conn = sqlite3.connect("usage.db")
    c = conn.cursor()
    one_week_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S')
    c.execute("SELECT COUNT(*) FROM usage WHERE ip = ? AND timestamp > ?", (ip, one_week_ago))
    count = c.fetchone()[0]
    conn.close()
    return count < 15, count

def log_usage(request: gr.Request):
    """Logs the IP address for rate limiting."""
    if not request or not request.client:
        return
    ip = request.client.host
    conn = sqlite3.connect("usage.db")
    c = conn.cursor()
    c.execute("INSERT INTO usage VALUES (?, ?)", (ip, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    conn.commit()
    conn.close()

def generate_pdf(content, company):
    """Generates a high-quality PDF report."""
    # We create a cleaner version of the content for the PDF
    clean_text = content.replace("##", "").replace("**", "").replace("*", "-")
    
    # PDF generation using FPDF2
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", 'B', 16)
    pdf.cell(200, 10, txt=f"ADA Strategic Briefing: {company}", ln=True, align='C')
    pdf.ln(10)
    pdf.set_font("Helvetica", size=11)
    
    pdf.multi_cell(0, 10, txt=clean_text)
    
    # Save to a temp directory and ensure clean-up
    fd, temp_path = tempfile.mkstemp(suffix=".pdf", prefix=f"ADA_{company.replace(' ', '_')}_Report_")
    os.close(fd) # Close file descriptor but keep path
    shutil.copyfile(pdf.output(), temp_path) # Need copy to prevent deletion issues

    return temp_path

def get_sales_intelligence(company, persona, code, request: gr.Request):
    # Security: Access Code Check
    if code != ACCESS_CODE:
        return gr.update(visible=False), "### ❌ Incorrect Access Code. Contact Bernardinoruss for authorization.", None
    
    if not company:
        return gr.update(visible=False), "### ⚠️ Company Name required.", None

    # Security: Rate Limit Check
    allowed, count = check_rate_limit(request)
    if not allowed:
        return gr.update(visible=False), f"### ⚠️ Rate Limit Exceeded (15/week). Usage: {count}/15.", None

    try:
        # 1. INDUSTRY DETECTION (Is BFSI?)
        industry_query = f"{company} primary industry sector"
        industry_search = tavily.search(query=industry_query, search_depth="basic", max_results=3)
        is_bfsi = any(word in str(industry_search).lower() for word in ["bank", "insurance", "financial", "lending", "bfsi"])

        # 2. MAIN STRATEGIC RESEARCH (Ground in 2026)
        main_query = f"{company} {persona} 2026 business goals financial strategy triggers"
        search_res = tavily.search(query=main_query, search_depth="advanced", max_results=6)
        results = search_res.get('results', [])
        
        # Build Context with Citable Sources
        context = ""
        sources = []
        for i, r in enumerate(results):
            # Clean URL for display
            display_url = r['url'].split('//')[-1].split('/')[0]
            if len(display_url) > 25: display_url = display_url[:22] + "..."
            context += f"[Source {i+1}: {r['url']}]\n{r['content']}\n\n"
            sources.append(f"• [{display_url}]({r['url']})")

        # 3. AI STRATEGY GENERATION (Gemini 2.5 Flash)
        model = genai.GenerativeModel('gemini-2.5-flash')
        
        # Craft Prompt for segmented Output
        prompt = f"""
        Act as a Sales Director for ADA Global. Analyze {company} for {persona}.
        Research Context: {context}

        Provide a "Battle-Ready" strategic briefing, keeping a professional, low-hallucination tone. Format strictly into these 5 segments with clean markdown.

        ## Segment 1: Financial Health (Grounded 2026)
        Analyze recent revenue performance, 2026 earnings projections, and key financial triggers.

        ## Segment 2: 2026 News & Corporate Goals
        Summarize major news (M&A, new products, leadership changes) and big 2026 strategic priorities.

        ## Segment 3: Persona Strategy: {persona}
        How to approach them. The professional "angle." The 2-sentence opening "Hook" line for cold outreach.

        ## Segment 4: ADA Pillar Alignment
        Match {company}'s priorities to one or more ADA Pillars (Identity, Personalization & Orchestration, Commerce, Data & AI). Be specific.

        ## Segment 5: Meeting Preparation
        A "Discovery Question Checklist." Three high-impact questions to ask {persona}.
        """
        
        ai_raw = model.generate_content(prompt).text
        
        # Clean up output
        ai_clean = clean_markdown(ai_raw)
        
        # 4. Generate Export File
        pdf_path = generate_pdf(ai_clean, company)

        # 5. BUILD DISPLAY HTML
        
        # Split AI response to find sources in specific slots (depends on AI behavior)
        sections = ai_clean.split("##")
        briefing_text = sections[1] if len(sections) > 1 else ai_clean

        dashboard_html = f"""
        <div class="output-tab">
            <h3>📊 Strategic Briefing: {company}</h3>
            <p><i>Intelligence Mode: {'BFSI Sector specialized' if is_bfsi else 'Corporate Intelligence'}</i></p>
            <div style="color:#CCCCCC; margin-top:20px;">{briefing_text}</div>
            
            <div class="sources-list">
                <p><b>🔍 Critical Intelligence Sources</b></p>
                {"".join(sources[:4])}
            </div>
        </div>
        """
        
        # Log successful usage
        log_usage(request)
        
        return gr.update(visible=True), dashboard_html, pdf_path

    except Exception as e:
        # Error Output
        return gr.update(visible=False), f"### ❌ Error\n{str(e)}", None

# --- 4. LUXURY UI DESIGN (Gradio Blocks) ---

with gr.Blocks(css=luxury_css, title="ADA Sales Intel (Luxury)") as demo:
    # 1. High-End Title Header (Visible to all)
    gr.HTML("""
    <div style="text-align: center; margin-top: 50px;">
        <h1 style="color: #FFFFFF; font-size: 3.5em; font-weight: 700;">ADA Sales Intelligence</h1>
        <p style="color: #CCCCCC; font-size: 1.2em; font-family: 'DM Serif Display'; font-style: italic;">
            Access the deepest 2026 corporate research in seconds.
        </p>
    </div>
    """)
    
    # 2. Interactive 3D Abstract Orb representing AI Core
    # We use simple HTML/CSS to create a pulsing orb that feels AI-powered.
    gr.HTML("""
    <div style="display: flex; justify-content: center; margin: 40px 0 60px 0;">
        <div style="
            width: 150px; height: 150px;
            background: radial-gradient(circle, #008080 10%, #000000 60%);
            border-radius: 50%;
            box-shadow: 0 0 40px rgba(0, 128, 128, 0.6);
            animation: orb-pulse 2s infinite ease-in-out;
            position: relative;
        ">
            <div style="
                width: 130px; height: 130px;
                background: radial-gradient(circle, #00C2C2 5%, #000000 70%);
                border-radius: 50%;
                opacity: 0.8;
                position: absolute; top: 10px; left: 10px;
            "></div>
        </div>
    </div>
    
    <style>
    @keyframes orb-pulse {
        0% { transform: scale(1); opacity: 0.8; box-shadow: 0 0 40px rgba(0, 128, 128, 0.6); }
        50% { transform: scale(1.05); opacity: 1; box-shadow: 0 0 60px rgba(0, 200, 200, 0.8); }
        100% { transform: scale(1); opacity: 0.8; box-shadow: 0 0 40px rgba(0, 128, 128, 0.6); }
    }
    </style>
    """)
    
    # 3. Security Access Section
    with gr.Column(elem_id="security-form", visible=True) as security_area:
        gr.Markdown("<h2 style='text-align:center;'>Enter Access Code to Initialize Intelligence</h2>")
        access_input = gr.Textbox(label="🔐 Security Token", type="password", placeholder="Paste authorization code...", elem_id="access-input")
        unlock_btn = gr.Button("AUTHORIZE PLATFORM", variant="primary")
        auth_error = gr.Markdown(visible=False)

    # 4. Main Research Parameters (Hidden by default)
    with gr.Column(elem_id="main-app", visible=False) as app_area:
        gr.HTML("""<div style="border-bottom: 1px solid #333333; margin-bottom: 30px; padding-bottom: 10px; text-align: center;">
            <p style="text-transform:uppercase; letter-spacing: 2px;">Research Parameters: 2026 Strategy Mode</p>
        </div>""")
        
        with gr.Row():
            with gr.Column(scale=1):
                comp_input = gr.Textbox(label="Company Name", placeholder="e.g., Samsung Philippines", lines=1)
                pers_input = gr.Textbox(label="Persona to Target", placeholder="e.g., Chief Marketing Officer", lines=1)
                
                with gr.Row():
                    run_btn = gr.Button("🔍 GATHER INSIGHTS", variant="primary")
                    
                # Creative Loading State Section
                with gr.Row(visible=False, elem_id="loading-state") as load_row:
                    # Pulsing loading animation
                    gr.HTML("<div style='text-align:center; padding: 20px 0;'><div class='loading-orb'></div></div>")
                    # Rotating copy logic happens in frontend Python
                    load_txt = gr.Markdown("Initializing 2026 strategic engines...")

            with gr.Column(scale=2):
                # The Dashboard Output
                output_tabs = gr.Column(visible=False)
                with output_tabs:
                    out_content = gr.HTML(elem_id="output-dashboard") # Clean segmented HTML output
                    gr.Markdown("---")
                    download_area = gr.File(label="📥 Export Briefing (PDF)", visible=False)

    # 5. Creative Loading Style
    gr.HTML("""
    <style>
    .loading-orb {
        width: 30px; height: 30px;
        background: radial-gradient(circle, #CCCCCC 10%, #333333 90%);
        border-radius: 50%;
        animation: load-pulse 1.2s infinite ease-in-out;
    }
    @keyframes load-pulse {
        0%, 100% { transform: scale(0.8); opacity: 0.5; }
        50% { transform: scale(1.1); opacity: 1; }
    }
    </style>
    """)

    # 6. UI EVENT LOGIC

    # Logic to handle creative loading messages
    loading_messages = ["Searching live 2026 financials...", "Analyzing corporate priorities...", "Synthesizing ADA alignment strategy...", "Finalizing persona-coaching points...", "Almost ready..."]
    
    # Authorize button hides security form and shows main app if code is correct
    def authorize_and_unlock(code):
        if code == ACCESS_CODE:
            return gr.update(visible=False), gr.update(visible=True), ""
        else:
            return gr.update(visible=True), gr.update(visible=False), "### ❌ Incorrect Access Code. Contact your Administrator."

    unlock_btn.click(
        fn=authorize_and_unlock,
        inputs=[access_input],
        outputs=[security_area, app_area, auth_error]
    )

    # Main Research Chain with Loading State Simulation
    run_btn.click(
        fn=lambda: (gr.update(visible=True), gr.update(visible=False), gr.update(visible=False), "Initializing strategic engines..."),
        outputs=[load_row, output_tabs, download_area, load_txt]
    ).then(
        fn=get_sales_intelligence,
        inputs=[comp_input, pers_input, access_input],
        outputs=[output_tabs, out_content, download_area]
    ).then(
        # Hide loading row and rotating message when done
        fn=lambda: gr.update(visible=False),
        outputs=[load_row]
    ).then(
        # Ensure download area becomes visible
        fn=lambda: gr.update(visible=True),
        outputs=[download_area]
    )

if __name__ == "__main__":
    demo.launch()
