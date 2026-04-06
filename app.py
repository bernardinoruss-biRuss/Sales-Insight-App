import os
import gradio as gr
from google import genai
from tavily import TavilyClient
import tempfile
from fpdf import FPDF
import time

# --- CONFIG ---
client = genai.Client(api_key=os.environ.get("GOOGLE_API_KEY"))
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY")
tavily = TavilyClient(api_key=TAVILY_API_KEY)
ACCESS_CODE = "PSNDB"

# --- THE "DYNAMIC MESH + PARTICLES" CSS ---
luxury_css = """
/* 1. The Vibrant Animated Mesh Background (Matches Reference) */
body, .gradio-container { 
    background-color: #FF99AC !important;
    background-image: 
        radial-gradient(at 0% 0%, hsla(253,16%,7%,1) 0px, transparent 50%), 
        radial-gradient(at 50% 0%, hsla(225,39%,30%,1) 0px, transparent 50%), 
        radial-gradient(at 100% 0%, hsla(339,49%,30%,1) 0px, transparent 50%), 
        radial-gradient(at 0% 100%, hsla(339,49%,30%,1) 0px, transparent 50%), 
        radial-gradient(at 100% 100%, hsla(253,16%,7%,1) 0px, transparent 50%) !important;
    background-size: 200% 200% !important;
    animation: meshGradient 18s ease infinite !important;
    font-family: 'Inter', sans-serif !important; 
}
@keyframes meshGradient { 0% { background-position: 0% 50%; } 50% { background-position: 100% 50%; } 100% { background-position: 0% 50%; } }

/* 2. Frosted Glass Panels */
.sidebar, .main-card { 
    background: rgba(255, 255, 255, 0.7) !important; 
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
    border-radius: 32px !important; 
    border: 1px solid rgba(255, 255, 255, 0.4) !important;
    box-shadow: 0 10px 40px rgba(0,0,0,0.15) !important; 
}

/* 3. The Vibrant Coral Button with Dynamic Feedback */
.st-button { 
    background: linear-gradient(90deg, #FF8E6E, #FF6B4A) !important; 
    border: none !important; 
    border-radius: 50px !important; 
    color: white !important; 
    font-weight: 800 !important; 
    height: 52px;
    box-shadow: 0 6px 20px rgba(255, 142, 110, 0.4) !important;
    transition: 0.3s !important;
}
.st-button:hover { transform: translateY(-2px); filter: brightness(1.1); }
.st-button:active { transform: scale(0.96); opacity: 0.8; }

/* 4. Pulsing Loading Indicator */
.loading-box { 
    text-align: center; 
    color: #2D3E33; 
    font-weight: 700; 
    padding: 25px; 
    background: rgba(255, 255, 255, 0.6);
    border-radius: 20px; 
    border: 2px dashed #FF9F80;
    animation: pulseLoader 2s infinite alternate;
}
@keyframes pulseLoader { from { opacity: 0.6; } to { opacity: 1; } }

#particles-js {
    position: fixed;
    width: 100%;
    height: 100%;
    top: 0;
    left: 0;
    z-index: -1;
}
"""

def generate_pdf(content):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.multi_cell(0, 10, txt=content.encode('latin-1', 'ignore').decode('latin-1'))
    path = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf").name
    pdf.output(path)
    return path

def run_ada_intel(company, persona, code):
    if code != ACCESS_CODE:
        return gr.update(visible=False), "🚫 Access Denied", None, ""

    loading_messages = [
        "🌐 Connecting to Global Intelligence Nodes...",
        f"🔍 Analyzing 2026 Strategic Mandates for {company}...",
        "🧠 Mapping Insights to ADA's Identity & AI Pillars...",
        "✨ Weaving your Sales Brief..."
    ]
    
    for msg in loading_messages:
        yield gr.update(visible=True), f"<div class='loading-box'>{msg}</div>", None, "⚙️ Processing..."
        time.sleep(1.5)

    try:
        query = f"{company} {persona} 2026 strategic priorities business news"
        search = tavily.search(query=query, search_depth="advanced")
        context = "\\n".join([r['content'] for r in search['results']])
        
        prompt = f"Act as a Senior Sales Strategist at ADA Global. Create a premium Sales Brief for {company} and {persona} using: {context}. Align to ADA's 4 Pillars."
        response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt).text
        pdf_file = generate_pdf(response)
        
        yield gr.update(visible=True), response, pdf_file, "✅ Ready"
        
    except Exception as e:
        yield gr.update(visible=True), f"### Error: {str(e)}", None, "❌ Failed"

with gr.Blocks(css=luxury_css) as demo:
    # 5. Particle Script Integration
    gr.HTML('''
    <div id="particles-js"></div>
    <script src="https://cdn.jsdelivr.net/particles.js/2.0.0/particles.min.js"></script>
    <script>
        particlesJS("particles-js", {
            "particles": {
                "number": { "value": 60, "density": { "enable": true, "value_area": 800 } },
                "color": { "value": "#ffffff" },
                "shape": { "type": "circle" },
                "opacity": { "value": 0.3, "random": true },
                "size": { "value": 2, "random": true },
                "line_linked": { "enable": true, "distance": 150, "color": "#ffffff", "opacity": 0.2, "width": 1 },
                "move": { "enable": true, "speed": 1.5, "direction": "none", "out_mode": "out" }
            },
            "interactivity": { "events": { "onhover": { "enable": true, "mode": "grab" } } },
            "retina_detect": true
        });
    </script>
    ''')

    with gr.Row():
        with gr.Column(scale=1, elem_classes="sidebar"):
            gr.HTML("<h1 style='color:#2D3E33; margin:0;'>ADA</h1><p style='color:#4F6F52;'>Strategic Intelligence</p>")
            comp = gr.Textbox(label="COMPANY", placeholder="e.g. Samsung Philippines")
            pers = gr.Textbox(label="PERSONA", placeholder="e.g. Chief Marketing Officer")
            pwd = gr.Textbox(label="ACCESS CODE", type="password")
            gen_btn = gr.Button("GENERATE BRIEFING", elem_classes="st-button")
            status_label = gr.Markdown("")
            
        with gr.Column(scale=2, elem_classes="main-card"):
            output_md = gr.Markdown("### Intelligence Dashboard Ready\\n*Input parameters to begin.*")
            download_btn = gr.File(label="📥 Download Strategy PDF")

    gen_btn.click(run_ada_intel, [comp, pers, pwd], [output_md, output_md, download_btn, status_label])

if __name__ == "__main__":
    demo.launch()
