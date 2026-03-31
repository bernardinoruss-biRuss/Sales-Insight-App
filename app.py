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

genai.configure(api_key=GOOGLE_API_KEY)
tavily = TavilyClient(api_key=TAVILY_API_KEY)

# --- 2. THE LOGIC ---
def get_sales_intelligence(company_name, persona):
    if not company_name:
        return "### ⚠️ Please enter a company name.", None
    
    try:
        # 1. STRATEGIC SEARCH
        search_query = (
            f"{company_name} business strategy news 2025 2026, "
            f"challenges for {persona} at {company_name}, "
            f"{company_name} digital transformation and corporate goals"
        )
        
        search_res = tavily.search(query=search_query, search_depth="advanced", max_results=8)
        results = search_res.get('results', [])
        
        context = "\n".join([f"Source: {r['url']}\nContent: {r['content']}" for r in results])
        
        # 2. GENERATE BRIEFING (Updated to Gemini 2.5 Flash for 2026 compatibility)
        model = genai.GenerativeModel('gemini-2.5-flash')
        
        prompt = f"""
        Act as a Senior Sales Strategist for ADA Global. 
        Target: {persona} at {company_name}. 
        Research Context: {context}

        Provide a "Battle-Ready" Strategic Briefing using this exact structure:

        ## 🏢 Company Intelligence
        * **Financials & News:** Summarize recent health and major news.
        * **Strategic Initiatives:** What are their big 2026 goals?
        * **Market Entry Point:** Where is the "gap" ADA can fill?

        ## 🎯 Persona Strategy: {persona}
        * **How to Approach:** Professional "angle" for this persona.
        * **The ADA Hook:** A 2-sentence opening line for email/LinkedIn.
        * **The Value Proposition:** Frame ADA's offerings for their KPIs.

        ## 💎 ADA Pillar Alignment
        1. **Identity**
        2. **Personalization & Orchestration**
        3. **Commerce**
        4. **Data & AI Foundation**

        ## 🛠️ Meeting Preparation
        * **LinkedIn Checklist**
        * **Website Recon**
        * **Discovery Questions:** 3 high-impact questions.
        """

        ai_res = model.generate_content(prompt)
        
        if ai_res and hasattr(ai_res, 'text'):
            response_text = ai_res.text
        else:
            response_text = "### ⚠️ AI Research Blocked. Please check content safety filters."
        
        sources_list = "\n\n---\n**🔍 Intelligence Sources:**\n" + \
                       "\n".join([f"• [{r['url'].split('//')[-1].split('/')[0]}]({r['url']})" for r in results])
        
        full_output = response_text + sources_list
        
        # 3. Generate Downloadable File
        fd, temp_path = tempfile.mkstemp(suffix=".txt", prefix=f"ADA_{company_name.replace(' ', '_')}_")
        with os.fdopen(fd, 'w', encoding="utf-8") as temp_file:
            temp_file.write(f"ADA STRATEGIC BRIEFING\nTarget: {company_name} | {persona}\n" + "="*40 + f"\n\n{full_output}")
        
        return full_output, temp_path

    except Exception as e:
        return f"### ❌ Error\n{str(e)}", None

# --- 3. INTERFACE (CSS & Gradio Blocks) ---
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
    max-width: 1100px;
    margin-left: auto;
    margin-right: auto;
}

.pillar-row {
    display: flex;
    gap: 15px;
    justify-content: center;
    margin: -60px auto 40px auto; /* Pulls pillars up to overlap header */
    max-width: 1000px; /* Aligns with header width */
    flex-wrap: nowrap;
    padding: 0 10px;
}

.pillar-card {
    background: white;
    border-radius: 16px;
    padding: 20px 10px;
    flex: 1; /* Forces all 4 cards to be equal width */
    text-align: center;
    text-decoration: none !important;
    color: #041E41 !important;
    box-shadow: 0 10px 15px rgba(0,0,0,0.05);
    transition: all 0.4s ease;
    border: 1px solid #EDF2F7;
    min-width: 140px;
    display: block;
}

.pillar-card:hover { 
    transform: translateY(-10px); 
    border-color: #008080;
    box-shadow: 0 15px 25px rgba(0,128,128,0.15);
}

.pillar-icon { font-size: 2.5em; margin-bottom: 10px; display: block; }

@media (max-width: 768px) {
    .pillar-row { flex-wrap: wrap; margin-top: 20px; }
}
"""

with gr.Blocks(css=css, theme=gr.themes.Soft(primary_hue="teal")) as demo:
    # Header with Clickable Pillars
    gr.HTML("""
    <div class="header-container">
        <h1 style="color: white; margin: 0; font-size: 3em; font-weight: 800;">ADA Sales Intelligence</h1>
        <p style="color: #E2E8F0; font-size: 1.1em; margin-top: 15px; max-width: 750px; margin-left: auto; margin-right: auto; line-height: 1.6;">
            Senior Sales Strategist Mode: Real-time financial data, trigger events, and persona-based coaching.
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
            gr.Markdown("### 🛠️ **Research Parameters**")
            comp_input = gr.Textbox(label="Company Name", placeholder="e.g. Samsung Philippines", lines=1)
            pers_input = gr.Textbox(label="Prospect Persona", placeholder="e.g. Chief Marketing Officer", lines=1)
            run_btn = gr.Button("🔍 GENERATE BRIEFING", variant="primary", size="lg")
            
            gr.Markdown("---")
            download_btn = gr.File(label="📥 Export Briefing (.txt)", interactive=False)
            
        with gr.Column(scale=2):
            output_markdown = gr.Markdown(value="### 👋 *Your strategic briefing will appear here...*")

    gr.HTML("<p style='text-align:center; padding: 40px 0; color: #718096;'>Powered by <b>ADA Global</b> Sales Enablement</p>")

    run_btn.click(
        fn=get_sales_intelligence, 
        inputs=[comp_input, pers_input], 
        outputs=[output_markdown, download_btn]
    )

if __name__ == "__main__":
    demo.launch()
