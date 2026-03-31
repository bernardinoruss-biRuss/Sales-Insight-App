import os
import gradio as gr
import google.generativeai as genai
from tavily import TavilyClient
import tempfile

# --- 1. AUTHENTICATION & CONFIG ---
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY")

if not GOOGLE_API_KEY or not TAVILY_API_KEY:
    raise ValueError("API Keys missing! Ensure GOOGLE_API_KEY and TAVILY_API_KEY are in Hugging Face Secrets.")

# FORCE V1 STABLE API to stop the 404/v1beta error
os.environ["GOOGLE_API_VERSION"] = "v1"
genai.configure(api_key=GOOGLE_API_KEY)
tavily = TavilyClient(api_key=TAVILY_API_KEY)

# --- 2. THE LOGIC ---
def get_sales_intelligence(company_name, persona):
    if not company_name:
        return "### ⚠️ Please enter a company name.", None
    
    try:
        query = f"{company_name} business strategy 2026, technology challenges for {persona}"
        search_res = tavily.search(query=query, search_depth="advanced", max_results=5)
        results = search_res.get('results', [])
        
        context = "\n".join([f"Source: {r['url']}\nContent: {r['content']}" for r in results])
        
        # Using specific model path to bypass versioning issues
        model = genai.GenerativeModel(model_name='models/gemini-1.5-flash')
        
        prompt = (
            f"Target: {persona} at {company_name}. Research Context: {context}. "
            "Task: Provide a high-level briefing for a sales professional. "
            "1. Identify Gaps/Challenges. "
            "2. Map to ADA Pillars: Identity, Personalization & Orchestration, Commerce, or Data & AI Foundation. "
            "3. Provide a catchy 2-sentence 'Hook' or opening line. "
            "Use clean Markdown and bullet points."
        )
        
        ai_res = model.generate_content(prompt)
        
        if hasattr(ai_res, 'text'):
            response_text = ai_res.text
        else:
            response_text = "### ⚠️ AI could not generate a response. Please check API quota."
        
        sources_list = "\n\n---\n**🔍 Research Sources:**\n" + "\n".join([f"• [{r['url'].split('//')[-1].split('/')[0]}]({r['url']})" for r in results])
        
        full_output = response_text + sources_list
        
        # Generate temporary file for download
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".txt", mode="w", encoding="utf-8")
        temp_file.write(f"ADA SALES INTELLIGENCE REPORT\nTarget: {company_name} - {persona}\n\n{full_output}")
        temp_file.close()
        
        return full_output, temp_file.name

    except Exception as e:
        return f"### ❌ Error\n{str(e)}", None

# --- 3. INTERFACE ---
css = """
footer {visibility: hidden}
.gradio-container {background-color: #F4F7F9; font-family: 'Inter', sans-serif;}
.header-container {
    background: linear-gradient(135deg, #041E41 0%, #008080 100%);
    padding: 45px 20px;
    border-radius: 20px;
    color: white;
    text-align: center;
    margin-bottom: 30px;
    box-shadow: 0 12px 24px rgba(0,0,0,0.15);
}
.pillar-row {
    display: flex;
    gap: 15px;
    justify-content: center;
    margin-bottom: 30px;
    flex-wrap: wrap;
}
.pillar-card {
    background: white;
    border-radius: 16px;
    padding: 20px;
    width: 170px;
    text-align: center;
    text-decoration: none !important;
    color: #041E41 !important;
    box-shadow: 0 6px 12px rgba(0,0,0,0.05);
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    border: 1px solid #E0E7ED;
}
.pillar-card:hover { 
    transform: translateY(-10px); 
    border-color: #008080;
    box-shadow: 0 12px 20px rgba(0,128,128,0.2);
}
.pillar-icon { font-size: 2.8em; margin-bottom: 12px; display: block; }
.download-box { margin-top: 20px; }
"""

with gr.Blocks(css=css, theme=gr.themes.Soft(primary_hue="teal")) as demo:
    gr.HTML("""
    <div class="header-container">
        <h1 style="color: white; margin: 0; font-size: 2.8em; letter-spacing: -1px;">ADA Sales Intelligence</h1>
        <p style="color: #E0E7ED; opacity: 0.9; font-size: 1.2em; margin-top: 15px; max-width: 700px; margin-left: auto; margin-right: auto;">
            Strategic prospect research powered by AI. Extract insights, map to ADA pillars, and win the meeting.
        </p>
    </div>
    
    <div class="pillar-row">
        <a href="https://adaglobal.com" target="_blank" class="pillar-card"><span class="pillar-icon">🆔</span><b>Identity</b></a>
        <a href="https://adaglobal.com" target="_blank" class="pillar-card"><span class="pillar-icon">🎯</span><b>Personalization</b></a>
        <a href="https://adaglobal.com" target="_blank" class="pillar-card"><span class="pillar-icon">🛒</span><b>Commerce</b></a>
        <a href="https://adaglobal.com" target="_blank" class="pillar-card"><span class="pillar-icon">🤖</span><b>Data & AI</b></a>
    </div>
    """)
    
    with gr.Row(equal_height=False):
        with gr.Column(scale=1, variant="panel"):
            gr.Markdown("### 🔍 **Command Center**")
            comp_input = gr.Textbox(label="Company Name", placeholder="e.g. Samsung Philippines", lines=1)
            pers_input = gr.Textbox(label="Prospect Persona", placeholder="e.g. Chief Digital Officer", lines=1)
            run_btn = gr.Button("🚀 REVEAL INSIGHTS", variant="primary", size="lg")
            
            gr.Markdown("---")
            download_component = gr.File(label="📥 Download Briefing", interactive=False)
            
        with gr.Column(scale=2):
            output_display = gr.Markdown(value="### 👋 *Ready to research. Enter details on the left.*")

    gr.HTML("<p style='text-align:center; padding: 40px 0; opacity: 0.7;'>Built for ADA Sales Teams | <a href='https://adaglobal.com' target='_blank' style='color: #008080;'>adaglobal.com</a></p>")

    # Logic to handle both the text display and the file generation
    run_btn.click(
        fn=get_sales_intelligence, 
        inputs=[comp_input, pers_input], 
        outputs=[output_display, download_component]
    )

if __name__ == "__main__":
    demo.launch()
