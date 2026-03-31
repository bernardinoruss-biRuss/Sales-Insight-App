import os
import gradio as gr
import google.generativeai as genai
from tavily import TavilyClient

# --- 1. AUTHENTICATION & SETUP ---
# Hugging Face uses os.environ to access the Secrets you saved in Settings
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY")

if not GOOGLE_API_KEY or not TAVILY_API_KEY:
    raise ValueError("API Keys missing! Add GOOGLE_API_KEY and TAVILY_API_KEY to Space Secrets.")

genai.configure(api_key=GOOGLE_API_KEY)
tavily = TavilyClient(api_key=TAVILY_API_KEY)

# --- 2. THE LOGIC FUNCTION ---
def get_sales_intelligence(company_name, persona):
    if not company_name:
        return "Please enter a company name."
    
    try:
        # Search for fresh intel
        query = f"{company_name} business strategy 2026, technology challenges for {persona}"
        search_res = tavily.search(query=query, search_depth="advanced", max_results=5)
        results = search_res.get('results', [])
        
        context = "\n".join([f"Source: {r['url']}\nContent: {r['content']}" for r in results])
        
        # AI Analysis using Gemini
        model = genai.GenerativeModel('gemini-1.5-flash')
        prompt = (
            f"Target: {persona} at {company_name}. "
            f"Research Context: {context}. "
            "Task: Provide a brief briefing on Gaps, ADA Pillar fit (Identity, Personalization & Orchestration, "
            "Commerce, Data & AI Foundation), and a catchy 2-sentence hook for a sales call. "
            "Format with clear headings and bullet points."
        )
        
        ai_res = model.generate_content(prompt)
        response_text = ai_res.text
        
        # Format sources for the UI
        sources_list = "\n\n**Sources:**\n" + "\n".join([f"• [{r['url'].split('//')[-1].split('/')[0]}]({r['url']})" for r in results])
        
        return response_text + sources_list

    except Exception as e:
        return f"An error occurred: {str(e)}"

# --- 3. CUSTOM INTERFACE (ADA BRANDING) ---
# ADA Global Brand Colors: Navy (#041E41) and Teal (#008080)
css = """
footer {visibility: hidden}
.gradio-container {background-color: #F8FBFE; font-family: 'Inter', sans-serif;}
.header-container {
    background: linear-gradient(135deg, #041E41 0%, #008080 100%);
    padding: 20px;
    border-radius: 15px;
    color: white;
    text-align: center;
    margin-bottom: 20px;
}
.pillar-row {
    display: flex;
    gap: 10px;
    justify-content: center;
    margin-bottom: 20px;
}
.pillar-card {
    background: white;
    border: 1px solid #E0E7ED;
    border-radius: 10px;
    padding: 10px;
    width: 120px;
    text-align: center;
    font-size: 12px;
    box-shadow: 0 4px 6px rgba(0,0,0,0.05);
}
"""

with gr.Blocks(css=css, theme=gr.themes.Soft(primary_hue="teal")) as demo:
    # Header Section
    gr.HTML("""
    <div class="header-container">
        <h1>AI Sales Intelligence</h1>
        <p>Research and provide insights for clients and prospects using AI.</p>
    </div>
    <div class="pillar-row">
        <div class="pillar-card">🆔<br><b>Identity</b></div>
        <div class="pillar-card">🎯<br><b>Personalization</b></div>
        <div class="pillar-card">🛒<br><b>Commerce</b></div>
        <div class="pillar-card">🤖<br><b>Data & AI</b></div>
    </div>
    """)
    
    with gr.Row():
        with gr.Column(scale=1):
            comp_input = gr.Textbox(label="Company Name", placeholder="e.g. Samsung", lines=1)
            pers_input = gr.Textbox(label="Prospect Persona", placeholder="e.g. Marketing Director", lines=1)
            run_btn = gr.Button("REVEAL INSIGHTS", variant="primary")
            
        with gr.Column(scale=2):
            output = gr.Markdown(label="Intelligence Brief")

    # Link button to ADA Global Website
    gr.HTML("<p style='text-align:center;'>Explore more at <a href='https://adaglobal.com' target='_blank'>adaglobal.com</a></p>")

    # Trigger action
    run_btn.click(fn=get_sales_intelligence, inputs=[comp_input, pers_input], outputs=output)

# Launch the app
if __name__ == "__main__":
    demo.launch()
