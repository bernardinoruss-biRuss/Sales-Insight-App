import os
import gradio as gr
import google.generativeai as genai
from tavily import TavilyClient

# --- 1. AUTHENTICATION ---
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY")

if not GOOGLE_API_KEY or not TAVILY_API_KEY:
    raise ValueError("API Keys missing! Ensure GOOGLE_API_KEY and TAVILY_API_KEY are in Hugging Face Secrets.")

genai.configure(api_key=GOOGLE_API_KEY)
tavily = TavilyClient(api_key=TAVILY_API_KEY)

# --- 2. THE LOGIC ---
def get_sales_intelligence(company_name, persona):
    if not company_name:
        return "### ⚠️ Please enter a company name."
    
    try:
        query = f"{company_name} business strategy 2026, technology challenges for {persona}"
        search_res = tavily.search(query=query, search_depth="advanced", max_results=5)
        results = search_res.get('results', [])
        
        context = "\n".join([f"Source: {r['url']}\nContent: {r['content']}" for r in results])
        
        # Using gemini-1.5-flash for speed and reliability
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        prompt = (
            f"Target: {persona} at {company_name}. Research Context: {context}. "
            "Task: Provide a high-level briefing for a sales professional. "
            "1. Identify Gaps/Challenges. "
            "2. Map to ADA Pillars: Identity, Personalization & Orchestration, Commerce, or Data & AI Foundation. "
            "3. Provide a catchy 2-sentence 'Hook' or opening line. "
            "Use clean Markdown and bullet points."
        )
        
        ai_res = model.generate_content(prompt)
        response_text = ai_res.text
        
        sources_list = "\n\n---\n**🔍 Research Sources:**\n" + "\n".join([f"• [{r['url'].split('//')[-1].split('/')[0]}]({r['url']})" for r in results])
        
        return response_text + sources_list

    except Exception as e:
        return f"### ❌ Error\n{str(e)}"

# --- 3. INTERFACE ---
css = """
footer {visibility: hidden}
.gradio-container {background-color: #F0F4F8; font-family: 'Inter', sans-serif;}
.header-container {
    background: linear-gradient(135deg, #041E41 0%, #008080 100%);
    padding: 40px 20px;
    border-radius: 15px;
    color: white;
    text-align: center;
    margin-bottom: 30px;
    box-shadow: 0 10px 20px rgba(0,0,0,0.1);
}
.pillar-row {
    display: flex;
    gap: 20px;
    justify-content: center;
    margin-bottom: 30px;
    flex-wrap: wrap;
}
.pillar-card {
    background: white;
    border: 2px solid transparent;
    border-radius: 12px;
    padding: 20px;
    width: 160px;
    text-align: center;
    text-decoration: none !important;
    color: #041E41 !important;
    box-shadow: 0 4px 12px rgba(0,0,0,0.08);
    transition: all 0.3s ease;
}
.pillar-card:hover { 
    transform: translateY(-8px); 
    border-color: #008080; 
    box-shadow: 0 8px 16px rgba(0,0,0,0.15);
}
.pillar-card div { font-size: 2em; margin-bottom: 10px; }
"""

with gr.Blocks(css=css, theme=gr.themes.Soft(primary_hue="teal")) as demo:
    gr.HTML("""
    <div class="header-container">
        <h1 style="color: white; margin: 0; font-size: 2.5em;">ADA Sales Intelligence</h1>
        <p style="color: #E0E7ED; opacity: 0.9; font-size: 1.2em; margin-top: 15px; max-width: 800px; margin-left: auto; margin-right: auto;">
            Empowering sales teams with AI-driven research to approach prospects with sharper strategy and deep context.
        </p>
    </div>
    
    <div class="pillar-row">
        <a href="https://adaglobal.com" target="_blank" class="pillar-card"><div>🔮</div><b>Identity</b></a>
        <a href="https://adaglobal.com" target="_blank" class="pillar-card"><div>🎯</div><b>Personalization</b></a>
        <a href="https://adaglobal.com" target="_blank" class="pillar-card"><div>🛒</div><b>Commerce</b></a>
        <a href="https://adaglobal.com" target="_blank" class="pillar-card"><div>🧬</div><b>Data & AI</b></a>
    </div>
    """)
    
    with gr.Row(equal_height=False):
        with gr.Column(scale=1, variant="panel"):
            gr.Markdown("### 🏢 Prospect Target")
            comp_input = gr.Textbox(label="Company Name", placeholder="e.g. Samsung Philippines", lines=1)
            pers_input = gr.Textbox(label="Prospect Persona", placeholder="e.g. Chief Digital Officer", lines=1)
            run_btn = gr.Button("REVEAL INSIGHTS", variant="primary", size="lg")
            
        with gr.Column(scale=2):
            # FIXED: Removed container=True which caused the TypeError
            output = gr.Markdown(value="### 👋 *Your strategic briefing will appear here...*")

    gr.HTML("<p style='text-align:center; padding: 30px 0;'>Powered by <a href='https://adaglobal.com' target='_blank' style='color: #008080; font-weight: bold;'>ADA Global</a></p>")

    run_btn.click(fn=get_sales_intelligence, inputs=[comp_input, pers_input], outputs=output)

if __name__ == "__main__":
    demo.launch()
