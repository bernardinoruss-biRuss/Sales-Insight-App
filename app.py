import os
import gradio as gr
from google import genai
from tavily import TavilyClient
import tempfile
from fpdf import FPDF

# --- CONFIG ---
client = genai.Client(api_key=os.environ.get("GOOGLE_API_KEY"))
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY")
tavily = TavilyClient(api_key=TAVILY_API_KEY)
ACCESS_CODE = "PSNDB"

# --- LUXURY CSS ---
luxury_css = """
body, .gradio-container { background-color: #000000 !important; color: #FFFFFF !important; }
.luxury-text { text-align: center; color: white !important; }
.gr-button-primary { background: #008080 !important; border: none !important; border-radius: 40px !important; }
input, textarea { background: #111 !important; border: 1px solid #333 !important; color: white !important; }
.orb { width: 100px; height: 100px; background: radial-gradient(circle, #008080 0%, #000 70%); border-radius: 50%; box-shadow: 0 0 40px #008080; margin: 20px auto; animation: pulse 3s infinite; }
@keyframes pulse { 0%, 100% { transform: scale(1); opacity: 0.6; } 50% { transform: scale(1.1); opacity: 1; } }
"""

def get_intel(company, persona, code):
    if code != ACCESS_CODE: return gr.update(visible=False), "❌ Access Denied", None
    try:
        search = tavily.search(query=f"{company} {persona} priorities 2026", search_depth="advanced")
        context = "\\n".join([r['content'] for r in search['results']])
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=f"Strategic Briefing for {company} ({persona}): {context}"
        ).text
        
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=12)
        pdf.multi_cell(0, 10, txt=response.encode('latin-1', 'ignore').decode('latin-1'))
        path = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf").name
        pdf.output(path)
        return gr.update(visible=True), response, path
    except Exception as e:
        return gr.update(visible=False), f"Error: {str(e)}", None

with gr.Blocks(css=luxury_css, theme=gr.themes.Base()) as demo:
    gr.HTML("<div class='luxury-text'><h1>ADA STRATEGIC INTELLIGENCE</h1><p>2026 Premium Research</p></div>")
    gr.HTML("<div class='orb'></div>")
    
    with gr.Column() as login:
        pwd = gr.Textbox(label="ACCESS CODE", type="password")
        btn_login = gr.Button("INITIALIZE", variant="primary")

    with gr.Column(visible=False) as main_app:
        comp = gr.Textbox(label="COMPANY")
        pers = gr.Textbox(label="PERSONA")
        run = gr.Button("GENERATE BRIEFING", variant="primary")
        out = gr.Markdown()
        file = gr.File(label="DOWNLOAD PDF")

    btn_login.click(lambda x: gr.update(visible=x==ACCESS_CODE), [pwd], [main_app])
    run.click(get_intel, [comp, pers, pwd], [main_app, out, file])

if __name__ == "__main__":
    demo.launch()
