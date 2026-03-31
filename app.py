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
        
        model = genai.GenerativeModel('gemini-1.5-flash')
        prompt = (
            f"Target: {persona} at {company_name}. Research: {context}. "
            "Task: Provide a brief briefing on Gaps, ADA Pillar fit (Identity, Personalization & Orchestration, "
            "Commerce, Data & AI Foundation), and a catchy 2-sentence hook. Use bullet points."
        )
        
        ai_res = model.generate_content(prompt)
        response_text = ai_res.text
        
        sources_list = "\n\n---\n**🔍 Sources:**\n" + "\n".join([f"• [{r['url'].split('//')[-1].split('/')[0]}]({r['url']})" for r in results])
        
        return response_text + sources_list

    except Exception as e:
        return f"### ❌ Error\n{str(e)}"

# --- 3. INTERFACE ---
css = """
footer {visibility: hidden}
.gradio-container {background-color: #F8FBFE; font-family: 'Inter', sans-serif;}
.header-container {
    background: linear-gradient(135deg, #041E41 0%, #008080 100%);
    padding: 30px;
    border-radius: 15px;
    color: white;
    text-align: center;
    margin-bottom: 20px;
}
.pillar-row {
    display: flex;
    gap: 15px;
    justify-content: center;
    margin-bottom: 20px;
    flex-wrap: wrap;
}
.pillar-card {
    background: white;
    border: 1px solid #E0E7ED;
    border-radius: 12px;
    padding: 15px;
    width: 140px;
    text-align: center;
    text-decoration: none !important;
    color: #041E41 !important;
    box-shadow: 0 4px 6px rgba(0,0,0,0.05);
    transition: all 0.3s ease;
}
.pillar-card:hover { transform: translateY(-5px); border-color: #008080; }
"""

with gr.Blocks(css=css, theme=gr.themes.Soft(primary_hue="teal")) as demo:
    gr.HTML("""
    <div class="header-container">
        <h1 style="color: white; margin: 0;">ADA Sales Intelligence</h1>
        <p style="color: #E0E7ED; opacity: 0.9; font-size: 1.1em; margin-top: 10px;">
            This app uses AI to generate research and insights that enable sales teams <br>
            to approach prospects with sharper strategy and context.
        </p>
    </div>
    <div class="pillar-row">
        <a href="https://adaglobal.com" target="_blank" class="pillar-card"><div>🔮</div><b>Identity</b></a>
        <a href="https://adaglobal.com" target="_blank" class="pillar-card"><div>🎯</div><b>Personalization</b></a>
        <a href="https://adaglobal.com" target="_blank" class="pillar-card"><div>🛒</div><b>Commerce</b></a>
        <a href="https://adaglobal.com" target="_blank" class="pillar-card"><div>🧬</div><b>Data & AI</b></a>
    </div>
    """)
    
    with gr.Row():
        with gr.Column(scale=1):
            comp_input = gr.Textbox(label="Company Name", placeholder="e.g. Samsung")
            pers_input = gr.Textbox(label="Prospect Persona", placeholder="e.g. Marketing Director")
            run_btn = gr.Button("REVEAL INSIGHTS", variant="primary")
            
        with gr.Column(scale=2):
            output = gr.Markdown(value="### 👋 Insights will appear here...")

    gr.HTML("<p style='text-align:center; padding-top:20px;'>Visit <a href='https://adaglobal.com' style='color: #008080;'>ADA Global</a></p>")

    run_btn.click(fn=get_sales_intelligence, inputs=[comp_input, pers_input], outputs=output)

if __name__ == "__main__":
    demo.launch()
