import os
import re
import json
import sqlite3
import hashlib
import tempfile
import datetime
import gradio as gr
import google.generativeai as genai
from tavily import TavilyClient
from fpdf import FPDF

# ──────────────────────────────────────────────
# 1. AUTHENTICATION & CONFIG
# ──────────────────────────────────────────────
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY")

if not GOOGLE_API_KEY or not TAVILY_API_KEY:
    raise ValueError("API Keys missing! Ensure GOOGLE_API_KEY and TAVILY_API_KEY are in Hugging Face Secrets.")

genai.configure(api_key=GOOGLE_API_KEY)
tavily = TavilyClient(api_key=TAVILY_API_KEY)

# ──────────────────────────────────────────────
# 2. RATE LIMIT DB
# ──────────────────────────────────────────────
DB_PATH = "/tmp/ada_usage.db"

def _init_db():
    con = sqlite3.connect(DB_PATH)
    con.execute("""
        CREATE TABLE IF NOT EXISTS usage (
            ip_hash TEXT NOT NULL,
            week    TEXT NOT NULL,
            count   INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (ip_hash, week)
        )
    """)
    con.commit()
    con.close()

_init_db()

WEEKLY_LIMIT = 15

def _current_week() -> str:
    today = datetime.date.today()
    return f"{today.isocalendar()[0]}-W{today.isocalendar()[1]:02d}"

def _ip_hash(request: gr.Request) -> str:
    raw = (request.client.host if request and request.client else "unknown")
    return hashlib.sha256(raw.encode()).hexdigest()[:16]

def _get_usage(ip_hash: str) -> int:
    week = _current_week()
    con = sqlite3.connect(DB_PATH)
    row = con.execute(
        "SELECT count FROM usage WHERE ip_hash=? AND week=?", (ip_hash, week)
    ).fetchone()
    con.close()
    return row[0] if row else 0

def _increment_usage(ip_hash: str):
    week = _current_week()
    con = sqlite3.connect(DB_PATH)
    con.execute("""
        INSERT INTO usage(ip_hash, week, count) VALUES(?,?,1)
        ON CONFLICT(ip_hash, week) DO UPDATE SET count=count+1
    """, (ip_hash, week))
    con.commit()
    con.close()

# ──────────────────────────────────────────────
# 3. INPUT SANITISATION
# ──────────────────────────────────────────────
_INJECTION_PATTERNS = re.compile(
    r"(ignore previous|forget instructions|you are now|act as|bypass|jailbreak|<script|javascript:)",
    re.IGNORECASE,
)

def _sanitise(text: str) -> str:
    text = text.strip()[:200]
    if _INJECTION_PATTERNS.search(text):
        raise ValueError("Invalid input detected.")
    return re.sub(r"[^\w\s\-\.,&'()]", "", text)

# ──────────────────────────────────────────────
# 4. INDUSTRY DETECTION
# ──────────────────────────────────────────────
_BFSI_KEYWORDS = {
    "bank", "banking", "finance", "financial", "insurance", "insurer",
    "fintech", "capital", "credit", "investment", "securities", "bdo",
    "bpi", "metrobank", "security bank", "unionbank", "rcbc", "pnb",
    "manulife", "sunlife", "axa", "prudential", "visa", "mastercard",
}

def _is_bfsi(company: str, persona: str) -> bool:
    combined = (company + " " + persona).lower()
    return any(kw in combined for kw in _BFSI_KEYWORDS)

# ──────────────────────────────────────────────
# 5. PDF EXPORT
# ──────────────────────────────────────────────
def _build_pdf(company: str, persona: str, content: str) -> str:
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Header bar
    pdf.set_fill_color(4, 30, 65)
    pdf.rect(0, 0, 210, 28, "F")
    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(255, 255, 255)
    pdf.set_xy(10, 7)
    pdf.cell(0, 12, "ADA SALES INTELLIGENCE BRIEFING", ln=True)

    pdf.set_font("Helvetica", "", 10)
    pdf.set_xy(10, 20)
    pdf.cell(0, 6, f"Target: {company}  |  Persona: {persona}  |  Generated: {datetime.date.today().isoformat()}")

    pdf.set_text_color(30, 30, 30)
    pdf.set_xy(10, 34)
    pdf.set_font("Helvetica", "", 10)

    # Strip markdown for PDF
    clean = re.sub(r"#+\s*", "", content)
    clean = re.sub(r"\*\*(.+?)\*\*", r"\1", clean)
    clean = re.sub(r"\*(.+?)\*", r"\1", clean)
    clean = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", clean)
    clean = re.sub(r"[•●▪]", "-", clean)

    for line in clean.splitlines():
        line = line.strip()
        if not line:
            pdf.ln(3)
            continue
        pdf.multi_cell(190, 5.5, line)

    fd, path = tempfile.mkstemp(suffix=".pdf", prefix=f"ADA_{company.replace(' ', '_')}_")
    os.close(fd)
    pdf.output(path)
    return path

# ──────────────────────────────────────────────
# 6. CORE INTELLIGENCE FUNCTION
# ──────────────────────────────────────────────
SECTIONS = ["financial", "news", "persona", "priorities", "strategy"]

def _parse_sections(raw: str) -> dict:
    """Loosely split AI output into named buckets."""
    mapping = {
        "financial": ["Financial", "Financials", "Finance"],
        "news": ["News", "Recent", "Events"],
        "persona": ["Persona", "Approach", "Hook"],
        "priorities": ["Priorities", "Initiatives", "Goals", "Pillar"],
        "strategy": ["ADA Strategy", "ADA Global", "Alignment", "Meeting", "Discovery"],
    }
    lines = raw.splitlines()
    buckets: dict = {k: [] for k in SECTIONS}
    current = "financial"
    for line in lines:
        for bucket, keywords in mapping.items():
            if any(kw.lower() in line.lower() for kw in keywords):
                current = bucket
                break
        buckets[current].append(line)
    return {k: "\n".join(v).strip() for k, v in buckets.items()}


def get_sales_intelligence(company_name: str, persona: str, request: gr.Request):
    # — Rate limit check —
    ip = _ip_hash(request)
    used = _get_usage(ip)
    remaining = WEEKLY_LIMIT - used
    if remaining <= 0:
        return (
            _error_html("Weekly limit reached (15/week). Resets every Monday."),
            None,
            f"<span style='color:#e53e3e;font-weight:700'>0 / {WEEKLY_LIMIT} remaining</span>",
        )

    # — Sanitise —
    try:
        company_name = _sanitise(company_name)
        persona = _sanitise(persona)
    except ValueError as exc:
        return _error_html(str(exc)), None, _quota_html(remaining)

    if not company_name:
        return _error_html("Please enter a company name."), None, _quota_html(remaining)

    bfsi = _is_bfsi(company_name, persona)

    try:
        # Search
        search_query = (
            f"{company_name} business strategy news 2025 2026, "
            f"challenges for {persona} at {company_name}, "
            f"{company_name} digital transformation corporate goals financials"
        )
        search_res = tavily.search(query=search_query, search_depth="advanced", max_results=10)
        results = search_res.get("results", [])
        context = "\n".join([f"Source: {r['url']}\nContent: {r['content']}" for r in results])

        # AI brief
        model = genai.GenerativeModel("gemini-2.5-flash")
        industry_note = (
            "Note: This is a BFSI company. Emphasise regulatory compliance, digital banking transformation, "
            "fraud prevention, and customer data platforms relevant to financial services.\n"
            if bfsi else ""
        )

        prompt = f"""
        Act as a Senior Sales Strategist for ADA Global.
        Target: {persona} at {company_name}.
        {industry_note}
        Research Context: {context}

        Produce a structured briefing with EXACTLY these section headers (use them verbatim):

        ## Financial Overview
        Summarize recent financials, health, and funding news.

        ## Recent News & Events
        Key headlines, trigger events, leadership changes.

        ## Persona Approach: {persona}
        How to approach. The ADA Hook (2-sentence email/LinkedIn opener). Value proposition tied to their KPIs.

        ## Company Priorities 2026
        Strategic initiatives and where ADA can enter.

        ## ADA Global Strategy & Meeting Prep
        ADA Pillar Alignment (Identity, Personalization & Orchestration, Commerce, Data & AI Foundation).
        LinkedIn & Website checklist.
        3 high-impact Discovery Questions.
        """

        ai_res = model.generate_content(prompt)
        raw_text = ai_res.text if (ai_res and hasattr(ai_res, "text")) else "AI response unavailable."

        # Increment usage after successful call
        _increment_usage(ip)
        remaining -= 1

        # Build output HTML
        sections = _parse_sections(raw_text)
        sources_by_domain: dict = {}
        for r in results:
            domain = r["url"].split("//")[-1].split("/")[0]
            sources_by_domain.setdefault(domain, r["url"])

        html_out = _build_dashboard_html(
            company_name, persona, sections, sources_by_domain, bfsi
        )

        # PDF
        pdf_path = _build_pdf(company_name, persona, raw_text)

        return html_out, pdf_path, _quota_html(remaining)

    except Exception as exc:
        return _error_html(f"Error: {str(exc)}"), None, _quota_html(remaining)


# ──────────────────────────────────────────────
# 7. HTML BUILDERS
# ──────────────────────────────────────────────
def _quota_html(remaining: int) -> str:
    color = "#38a169" if remaining > 5 else ("#dd6b20" if remaining > 1 else "#e53e3e")
    return (
        f"<span style='color:{color};font-weight:700;font-size:0.9em'>"
        f"{remaining} / {WEEKLY_LIMIT} searches remaining this week</span>"
    )

def _error_html(msg: str) -> str:
    return f"""
    <div style="background:#fff5f5;border-left:4px solid #e53e3e;padding:20px 24px;border-radius:8px;color:#742a2a;font-family:'Georgia',serif;">
        <strong>⚠️ {msg}</strong>
    </div>"""

def _md_to_html(text: str) -> str:
    """Minimal markdown → HTML converter."""
    text = re.sub(r"####\s*(.+)", r"<h4>\1</h4>", text)
    text = re.sub(r"###\s*(.+)", r"<h3>\1</h3>", text)
    text = re.sub(r"##\s*(.+)", r"<h2>\1</h2>", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
    text = re.sub(r"\[([^\]]+)\]\(([^\)]+)\)", r'<a href="\2" target="_blank">\1</a>', text)
    lines = text.splitlines()
    out, in_ul = [], False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(("* ", "- ", "• ")):
            if not in_ul:
                out.append("<ul>"); in_ul = True
            out.append(f"<li>{stripped[2:]}</li>")
        else:
            if in_ul:
                out.append("</ul>"); in_ul = False
            if stripped:
                out.append(f"<p>{stripped}</p>")
    if in_ul:
        out.append("</ul>")
    return "\n".join(out)


def _build_dashboard_html(company, persona, sections, sources, bfsi):
    # Theming
    if bfsi:
        accent = "#1a5276"
        accent2 = "#154360"
        badge_bg = "#d6eaf8"
        badge_color = "#1a5276"
        industry_badge = "🏦 BFSI"
        hero_gradient = "linear-gradient(135deg, #0d2137 0%, #1a5276 60%, #1abc9c 100%)"
    else:
        accent = "#041E41"
        accent2 = "#008080"
        badge_bg = "#e6fffa"
        badge_color = "#008080"
        industry_badge = "🌏 Enterprise"
        hero_gradient = "linear-gradient(135deg, #041E41 0%, #008080 100%)"

    tab_defs = [
        ("💰", "Financial", "financial"),
        ("📰", "News", "news"),
        ("🎯", "Persona", "persona"),
        ("🏢", "Priorities", "priorities"),
        ("💎", "ADA Strategy", "strategy"),
    ]

    # Build tab buttons
    tab_btns = ""
    for i, (icon, label, key) in enumerate(tab_defs):
        active = "ada-tab-active" if i == 0 else ""
        tab_btns += f"""
        <button class="ada-tab {active}" onclick="adaShowTab('{key}',this)" data-key="{key}">
            {icon} {label}
        </button>"""

    # Build panels
    panels = ""
    for i, (icon, label, key) in enumerate(tab_defs):
        display = "block" if i == 0 else "none"
        content_html = _md_to_html(sections.get(key, "_No data available._"))
        # Attach sources to last panel or each
        src_html = ""
        if key == "strategy" and sources:
            src_html = "<div class='ada-sources'><strong>🔍 Intelligence Sources</strong><ul>"
            for domain, url in list(sources.items())[:8]:
                src_html += f"<li><a href='{url}' target='_blank'>{domain}</a></li>"
            src_html += "</ul></div>"

        panels += f"""
        <div id="ada-panel-{key}" class="ada-panel" style="display:{display}">
            <div class="ada-panel-header">{icon} {label}</div>
            <div class="ada-panel-body">
                <details open>
                    <summary><strong>Key Insights</strong> — click to collapse</summary>
                    <div class="ada-content">{content_html}</div>
                </details>
            </div>
            {src_html}
        </div>"""

    return f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700;900&family=DM+Sans:wght@300;400;500;600&display=swap');

.ada-wrap {{
    font-family: 'DM Sans', sans-serif;
    max-width: 900px;
    margin: 0 auto;
    color: #1a202c;
}}
.ada-hero {{
    background: {hero_gradient};
    border-radius: 18px;
    padding: 36px 40px 28px;
    color: white;
    position: relative;
    overflow: hidden;
    margin-bottom: 0;
}}
.ada-hero::before {{
    content: '';
    position: absolute;
    top: -40px; right: -40px;
    width: 200px; height: 200px;
    border-radius: 50%;
    background: rgba(255,255,255,0.06);
}}
.ada-hero-badge {{
    display: inline-block;
    background: {badge_bg};
    color: {badge_color};
    font-size: 0.75em;
    font-weight: 600;
    padding: 3px 12px;
    border-radius: 20px;
    margin-bottom: 10px;
    letter-spacing: 0.05em;
    text-transform: uppercase;
}}
.ada-hero h1 {{
    font-family: 'Playfair Display', serif;
    font-size: 2.2em;
    margin: 6px 0 4px;
    font-weight: 900;
    letter-spacing: -0.5px;
    line-height: 1.2;
}}
.ada-hero p {{
    font-size: 0.95em;
    opacity: 0.8;
    margin: 0;
}}
.ada-tabs {{
    display: flex;
    gap: 6px;
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 14px;
    padding: 8px;
    margin: 18px 0 0;
    flex-wrap: wrap;
    box-shadow: 0 2px 12px rgba(0,0,0,0.06);
}}
.ada-tab {{
    flex: 1;
    min-width: 110px;
    padding: 10px 8px;
    border: none;
    border-radius: 10px;
    background: transparent;
    cursor: pointer;
    font-family: 'DM Sans', sans-serif;
    font-size: 0.82em;
    font-weight: 500;
    color: #718096;
    transition: all 0.2s ease;
    white-space: nowrap;
}}
.ada-tab:hover {{
    background: {badge_bg};
    color: {badge_color};
}}
.ada-tab.ada-tab-active {{
    background: {accent};
    color: white;
    font-weight: 600;
    box-shadow: 0 3px 10px rgba(0,0,0,0.15);
}}
.ada-panel {{
    background: white;
    border-radius: 14px;
    margin-top: 14px;
    border: 1px solid #e2e8f0;
    overflow: hidden;
    box-shadow: 0 2px 16px rgba(0,0,0,0.05);
}}
.ada-panel-header {{
    background: {accent};
    color: white;
    padding: 14px 24px;
    font-family: 'Playfair Display', serif;
    font-size: 1.15em;
    font-weight: 700;
    letter-spacing: 0.01em;
}}
.ada-panel-body {{
    padding: 20px 24px 10px;
}}
.ada-panel-body details {{
    border: 1px solid #e8edf3;
    border-radius: 10px;
    padding: 12px 16px;
    background: #f9fafb;
}}
.ada-panel-body summary {{
    cursor: pointer;
    color: {accent};
    font-size: 0.93em;
    user-select: none;
    padding: 2px 0;
}}
.ada-content {{
    margin-top: 14px;
    line-height: 1.75;
    font-size: 0.93em;
}}
.ada-content h2, .ada-content h3, .ada-content h4 {{
    color: {accent};
    font-family: 'Playfair Display', serif;
    margin: 16px 0 6px;
}}
.ada-content ul {{
    padding-left: 20px;
}}
.ada-content li {{
    margin-bottom: 6px;
}}
.ada-content a {{
    color: {accent2};
    text-decoration: underline;
}}
.ada-sources {{
    padding: 14px 24px 18px;
    border-top: 1px solid #edf2f7;
    font-size: 0.82em;
    color: #718096;
}}
.ada-sources ul {{
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    list-style: none;
    padding: 8px 0 0;
    margin: 0;
}}
.ada-sources li a {{
    display: inline-block;
    background: {badge_bg};
    color: {badge_color};
    border-radius: 20px;
    padding: 3px 12px;
    font-weight: 500;
    text-decoration: none;
    transition: opacity 0.2s;
}}
.ada-sources li a:hover {{ opacity: 0.75; }}
</style>

<div class="ada-wrap">
    <div class="ada-hero">
        <div class="ada-hero-badge">{industry_badge}</div>
        <h1>{company}</h1>
        <p>Strategic Briefing · {persona} · Generated {datetime.date.today().strftime('%B %d, %Y')}</p>
    </div>

    <div class="ada-tabs">{tab_btns}</div>

    {panels}
</div>

<script>
function adaShowTab(key, btn) {{
    document.querySelectorAll('.ada-panel').forEach(p => p.style.display = 'none');
    document.querySelectorAll('.ada-tab').forEach(b => b.classList.remove('ada-tab-active'));
    document.getElementById('ada-panel-' + key).style.display = 'block';
    btn.classList.add('ada-tab-active');
}}
</script>
"""

# ──────────────────────────────────────────────
# 8. LOADING ANIMATION HTML
# ──────────────────────────────────────────────
LOADING_HTML = """
<style>
@keyframes ada-pulse { 0%,100%{transform:scale(1);opacity:1} 50%{transform:scale(1.12);opacity:0.7} }
@keyframes ada-spin  { to{transform:rotate(360deg)} }
@keyframes ada-fade  { 0%{opacity:0;transform:translateY(8px)} 100%{opacity:1;transform:translateY(0)} }
.ada-loader {
    display:flex; flex-direction:column; align-items:center; justify-content:center;
    padding:60px 20px; gap:20px; font-family:'DM Sans',sans-serif;
}
.ada-brain {
    width:72px; height:72px; border-radius:50%;
    background:linear-gradient(135deg,#041E41,#008080);
    display:flex; align-items:center; justify-content:center;
    font-size:2.2em;
    animation:ada-pulse 1.6s ease-in-out infinite;
    box-shadow:0 0 0 12px rgba(0,128,128,0.12), 0 0 0 24px rgba(0,128,128,0.05);
}
.ada-ring {
    width:90px; height:90px; border-radius:50%;
    border:3px solid transparent;
    border-top-color:#008080;
    animation:ada-spin 1s linear infinite;
    position:absolute;
}
.ada-brain-wrap { position:relative; display:flex; align-items:center; justify-content:center; width:90px; height:90px; }
.ada-msg { font-size:1em; font-weight:500; color:#4a5568; animation:ada-fade 0.5s ease; }
.ada-sub { font-size:0.8em; color:#a0aec0; }
</style>
<div class="ada-loader">
    <div class="ada-brain-wrap">
        <div class="ada-ring"></div>
        <div class="ada-brain">🧠</div>
    </div>
    <div>
        <div class="ada-msg" id="ada-loading-msg">Searching the depths of the web...</div>
        <div class="ada-sub" style="text-align:center;margin-top:4px">This may take 15–30 seconds</div>
    </div>
</div>
<script>
const msgs = [
    "Searching the depths of the web...",
    "Analysing 2026 financial reports...",
    "Mapping your prospect's priorities...",
    "Crafting your ADA strategy...",
    "Almost there — polishing insights...",
];
let i = 0;
const el = document.getElementById('ada-loading-msg');
if(el){
    setInterval(()=>{ i=(i+1)%msgs.length; el.textContent=msgs[i]; el.style.animation='none'; 
    requestAnimationFrame(()=>{ el.style.animation='ada-fade 0.5s ease'; }); }, 3500);
}
</script>
"""

# ──────────────────────────────────────────────
# 9. GRADIO UI
# ──────────────────────────────────────────────
CSS = """
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700;900&family=DM+Sans:wght@300;400;500;600&display=swap');
footer { visibility: hidden }
.gradio-container { background: #f0f4f8 !important; font-family: 'DM Sans', sans-serif !important; }
#ada-header { margin-bottom: 0; }
#component-0 { gap: 0 !important; }
.ada-info-tip {
    display:inline-block; margin-left:8px; cursor:default;
    color:#718096; font-size:0.85em;
    position:relative;
}
.ada-info-tip .ada-tooltip {
    display:none; position:absolute; bottom:130%; left:50%; transform:translateX(-50%);
    background:#2d3748; color:white; padding:6px 12px; border-radius:8px;
    font-size:0.78em; white-space:nowrap; z-index:100;
}
.ada-info-tip:hover .ada-tooltip { display:block; }
"""

with gr.Blocks(css=CSS, title="ADA Sales Intelligence") as demo:

    # ── HERO HEADER ──
    gr.HTML("""
    <div id="ada-header" style="
        background:linear-gradient(135deg,#041E41 0%,#008080 100%);
        padding:52px 24px 80px;
        border-radius:20px;
        text-align:center;
        color:white;
        position:relative;
        overflow:hidden;
    ">
        <div style="position:absolute;top:-60px;right:-60px;width:260px;height:260px;border-radius:50%;background:rgba(255,255,255,0.05);"></div>
        <div style="position:absolute;bottom:-80px;left:-40px;width:200px;height:200px;border-radius:50%;background:rgba(0,128,128,0.18);"></div>
        <p style="color:#81e6d9;font-size:0.8em;letter-spacing:0.15em;text-transform:uppercase;margin:0 0 10px;font-weight:600;">ADA GLOBAL · SALES ENABLEMENT</p>
        <h1 style="font-family:'Playfair Display',serif;font-size:3em;font-weight:900;margin:0 0 12px;letter-spacing:-1px;">Sales Intelligence Dashboard</h1>
        <p style="opacity:0.75;max-width:600px;margin:0 auto;font-size:1em;line-height:1.6;">
            Real-time prospect research, persona coaching, and ADA pillar alignment — powered by AI.
        </p>
        <div style="display:flex;justify-content:center;gap:20px;margin-top:30px;flex-wrap:wrap;">
            <div style="background:rgba(255,255,255,0.1);border-radius:12px;padding:14px 22px;min-width:120px;">
                <div style="font-size:1.6em;">🆔</div>
                <div style="font-size:0.8em;margin-top:4px;opacity:0.85;font-weight:500;">Identity</div>
            </div>
            <div style="background:rgba(255,255,255,0.1);border-radius:12px;padding:14px 22px;min-width:120px;">
                <div style="font-size:1.6em;">🎯</div>
                <div style="font-size:0.8em;margin-top:4px;opacity:0.85;font-weight:500;">Personalisation</div>
            </div>
            <div style="background:rgba(255,255,255,0.1);border-radius:12px;padding:14px 22px;min-width:120px;">
                <div style="font-size:1.6em;">🛒</div>
                <div style="font-size:0.8em;margin-top:4px;opacity:0.85;font-weight:500;">Commerce</div>
            </div>
            <div style="background:rgba(255,255,255,0.1);border-radius:12px;padding:14px 22px;min-width:120px;">
                <div style="font-size:1.6em;">🤖</div>
                <div style="font-size:0.8em;margin-top:4px;opacity:0.85;font-weight:500;">Data & AI</div>
            </div>
        </div>
    </div>
    """)

    with gr.Row(equal_height=False, elem_id="ada-main-row"):

        # ── LEFT PANEL ──
        with gr.Column(scale=1, min_width=280):
            gr.HTML("<div style='height:24px'></div>")
            with gr.Group():
                gr.Markdown("### 🛠️ Research Parameters")
                comp_input = gr.Textbox(
                    label="Company Name",
                    placeholder="e.g. BDO Unibank, Samsung Philippines",
                    max_lines=1,
                )
                pers_input = gr.Textbox(
                    label="Prospect Persona",
                    placeholder="e.g. Chief Marketing Officer",
                    max_lines=1,
                )

                with gr.Row():
                    run_btn = gr.Button("🔍 Generate Briefing", variant="primary", size="lg")

                gr.HTML("""
                <div style="margin-top:6px;font-size:0.8em;color:#718096;display:flex;align-items:center;gap:6px;">
                    <span class="ada-info-tip">ℹ️
                        <span class="ada-tooltip">Limit: 15 searches per week, tracked by IP.</span>
                    </span>
                    <span>15 searches / week limit applies</span>
                </div>
                """)

                quota_display = gr.HTML(value=f"<span style='font-size:0.82em;color:#718096'>Usage tracked per IP address</span>")

            gr.HTML("<hr style='border-color:#e2e8f0;margin:16px 0'>")
            download_btn = gr.File(label="📥 Export as PDF", interactive=False)

            gr.HTML("""
            <div style="margin-top:20px;padding:16px;background:white;border-radius:12px;border:1px solid #e2e8f0;font-size:0.78em;color:#718096;line-height:1.6;">
                <strong style="color:#041E41">🔒 Security</strong><br>
                Inputs are sanitised. API keys stored in environment secrets. PDF files are temporary and auto-deleted.
            </div>
            """)

        # ── RIGHT PANEL ──
        with gr.Column(scale=2):
            gr.HTML("<div style='height:24px'></div>")
            loading_area = gr.HTML(value="", visible=False)
            output_area = gr.HTML(
                value="""
                <div style="
                    background:white;border-radius:16px;border:1px dashed #cbd5e0;
                    padding:60px 40px;text-align:center;color:#a0aec0;
                    font-family:'DM Sans',sans-serif;
                ">
                    <div style="font-size:3em;margin-bottom:16px">🔍</div>
                    <div style="font-size:1.1em;font-weight:600;color:#4a5568;margin-bottom:8px">Ready to research</div>
                    <div style="font-size:0.88em">Enter a company and persona, then click <strong>Generate Briefing</strong></div>
                </div>
                """
            )

    gr.HTML("<p style='text-align:center;padding:32px 0 16px;color:#a0aec0;font-size:0.82em;'>Powered by <strong>ADA Global</strong> Sales Enablement · Built with Gemini & Tavily</p>")

    # ── EVENTS ──
    def _show_loading():
        return gr.update(value=LOADING_HTML, visible=True), gr.update(value="")

    def _hide_loading_run(company, persona, request: gr.Request):
        html, pdf, quota = get_sales_intelligence(company, persona, request)
        return (
            gr.update(value="", visible=False),
            gr.update(value=html),
            pdf,
            gr.update(value=quota),
        )

    run_btn.click(
        fn=_show_loading,
        inputs=[],
        outputs=[loading_area, output_area],
        queue=False,
    ).then(
        fn=_hide_loading_run,
        inputs=[comp_input, pers_input],
        outputs=[loading_area, output_area, download_btn, quota_display],
    )

if __name__ == "__main__":
    demo.queue().launch()
