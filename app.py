import os
import gradio as gr
import google.generativeai as genai
from tavily import TavilyClient
import tempfile

# --- 1. AUTHENTICATION & STABLE CONFIG ---
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY")

if not GOOGLE_API_KEY or not TAVILY_API_KEY:
    raise ValueError("API Keys missing! Ensure GOOGLE_API_KEY and TAVILY_API_KEY are in Hugging Face Secrets.")

# CRITICAL FIX: Force the library to use the stable V1 API to kill the 404 error
os.environ["GOOGLE_API_VERSION"] = "v1"
genai.configure(api_key=GOOGLE_API_KEY)
tavily = TavilyClient(api_key=TAVILY_API_KEY)

# --- 2. THE LOGIC ---
def get_sales_intelligence(company_name, persona):
    if not company_name:
        return "### ⚠️ Please enter a company name.", None
    
    try:
        # 1. Search for real-time data
        query = f"{company_name} business strategy 2026, technology challenges for {persona}"
        search_res = tavily.search(query=query, search_depth="advanced", max_results=5)
        results = search_res.get('results', [])
        
        context = "\n".join([f"Source: {r['url']}\nContent: {r['content']}" for r in results])
        
        # 2. Initialize the model with the exact production path
        model = genai.GenerativeModel(model_name='models/gemini-1.5-flash')
        
        prompt = (
            f"Target: {persona} at {company_name}. Research Context: {context}. "
            "Task: Provide a high-level briefing for a sales professional. "
            "1. Identify Gaps/Challenges. "
            "2. Map to ADA Pillars: Identity, Personalization & Orchestration, Commerce, or Data & AI Foundation. "
            "3. Provide a catchy 2-sentence 'Hook' or opening line. "
            "Use clean Markdown and bullet points."
        )
        
        # 3. Generate content
        ai_res = model.generate_content(prompt)
        
        if hasattr(ai_res, 'text'):
            response_text = ai_res.text
        else:
            response_text = "### ⚠️ AI Research Blocked. Please check API quota or content safety."
        
        sources_list = "\n\n---\n**🔍 Research Sources:**\n" + "\n".join([f"• [{r['url'].split('//')[-1].split('/')[0]}]({r['url']})" for r in results])
        
        full_output = response_text + sources_list
        
        # 4. Generate Downloadable File
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".txt", mode="w", encoding="utf-8")
        temp_file.write(f"ADA SALES INTELLIGENCE REPORT\nTarget: {company_name} | {persona}\n" + "="*30 + f"\n\n{full_output}")
        temp_file.close()
        
        return full_output, temp_file.name

    except Exception as e:
        return f"### ❌ Error\n{str(e)}", None

# --- 3. INTERFACE ---
css = """
footer {visibility: hidden}
.gradio-container {background-color: #F8FAFC; font-family: 'Inter', sans-serif;}
.header-container {
    background: linear-gradient(135deg, #041E41 0%, #008080 100%);
    padding: 50px 20px;
    border-radius: 20px;
    color: white;
    text-align: center;
    margin-bottom: 30px;
    box-shadow: 0 15px 30px rgba(0,0,0,0.1);
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
    box-shadow: 0 4px 10px rgba(0,0,0,0.05);
    transition: all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275);
    border: 1px solid #EDF2F7;
}
.pillar-card:hover { 
    transform: translateY(-12px); 
    border-color: #008080;
    box-shadow: 0 15px 25px rgba(0,128,128,0.15);
}
.pillar-icon { font-size: 3em; margin-bottom: 15px; display: block; filter: drop-shadow(0 4px 4px rgba(0,0,0,0.1)); }
"""

with gr.Blocks(css=css, theme=gr.themes.Soft(primary_hue="teal", font=["Inter", "sans-serif"])) as demo:
    gr.HTML("""
    <div class="header-container">
        <h1 style="color: white; margin: 0; font-size: 3em; font-weight: 800;">ADA Sales Intelligence</h1>
        <p style="color: #E2E8F0; font-size: 1.2em; margin-top: 15px; max-width: 750px; margin-left: auto; margin-right: auto; line-height: 1.6;">
            Precision research for modern sales. Enter a prospect to generate actionable briefings mapped to ADA's core growth pillars.
        </p>
    </div>
    
    <div class="pillar-row">
        <div class="pillar-card"><span class="pillar-icon">🆔</span><b>Identity</b></div>
        <div class="pillar-card"><span class="pillar-icon">🎯</span><b>Personalization</b></div>
        <div class="pillar-card"><span class="pillar-icon">🛒</span><b>Commerce</b></div>
        <div class="pillar-card"><span class="pillar-icon">🤖</span><b>Data & AI</b></div>
    </div>
    """)
    
    with gr.Row(equal_height=False):
        with gr.Column(scale=1, variant="panel"):
            gr.Markdown("### 🛠️ **Research Parameters**")
            comp_input = gr.Textbox(label="Company Name", placeholder="e.g. Samsung Philippines", lines=1)
            pers_input = gr.Textbox(label="Prospect Persona", placeholder="e.g. Chief Marketing Officer", lines=1)
            run_btn = gr.Button("🔍 GENERATE BRIEFING", variant="primary", size="lg")
            
            gr.Markdown("---")
            download_btn = gr.File(label="📥 Export Briefing (.txt)", interactive=False)
            
        with gr.Column(scale=2):
            output_markdown = gr.Markdown(value="### 👋 *Your strategic briefing will appear here after research...*")

    gr.HTML("<p style='text-align:center; padding: 40px 0; color: #718096;'>Powered by <b>ADA Global</b> Sales Enablement</p>")

    # Single click to update both the UI and the download file
    run_btn.click(
        fn=get_sales_intelligence, 
        inputs=[comp_input, pers_input], 
        outputs=[output_markdown, download_btn]
    )

if __name__ == "__main__":
    demo.launch()
