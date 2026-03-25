import streamlit as st
import json
import os
from datetime import date
from utils import generate_pdf
from agent import (ask_clarifying_questions, generate_prep,
                   try_fetch_linkedin, extract_personal_highlights,
                   INDUSTRIES, FUNCTIONS)

st.set_page_config(page_title="Career Fair Prep Agent", page_icon="🎯", layout="centered")

# ── Rate limiting config ──────────────────────────────────────────────────────
MAX_SESSIONS    = 3     # max generations per browser session
DAILY_CAP       = 30    # max total generations per day across all users
COUNTER_FILE    = "/tmp/usage_counter.json"
ACCESS_CODE_KEY = "ACCESS_CODE"

def _load_counter():
    try:
        if os.path.exists(COUNTER_FILE):
            with open(COUNTER_FILE) as f:
                data = json.load(f)
            if data.get("date") == str(date.today()):
                return data
    except Exception:
        pass
    return {"date": str(date.today()), "count": 0}

def _save_counter(data):
    try:
        with open(COUNTER_FILE, "w") as f:
            json.dump(data, f)
    except Exception:
        pass

def _increment_counter():
    data = _load_counter()
    data["count"] += 1
    _save_counter(data)

def _daily_count():
    return _load_counter()["count"]

def _check_access_code(entered):
    try:
        return entered.strip() == st.secrets[ACCESS_CODE_KEY].strip()
    except Exception:
        return True  # local dev: no secret configured = open access

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=DM+Mono:wght@300;400;500&display=swap');
html, body, [class*="css"] { font-family: 'DM Mono', monospace; background-color: #0e0e0e; color: #e8e4dc; }
h1, h2, h3 { font-family: 'Syne', sans-serif; letter-spacing: -0.02em; }
.stTextArea textarea {
    background-color: #1a1a1a !important; color: #e8e4dc !important;
    border: 1px solid #2e2e2e !important; border-radius: 6px !important;
    font-family: 'DM Mono', monospace !important; font-size: 13px !important;
}
.stTextInput input {
    background-color: #1a1a1a !important; color: #e8e4dc !important;
    border: 1px solid #2e2e2e !important; border-radius: 6px !important;
    font-family: 'DM Mono', monospace !important;
}
.stButton > button {
    background-color: #c8f560 !important; color: #0e0e0e !important;
    font-family: 'Syne', sans-serif !important; font-weight: 700 !important;
    border: none !important; border-radius: 6px !important;
    padding: 0.6rem 1.4rem !important; transition: opacity 0.15s ease !important;
}
.stButton > button:hover { opacity: 0.85 !important; }
.output-block {
    background: #161616; border-left: 3px solid #c8f560; border-radius: 0 8px 8px 0;
    padding: 1.2rem 1.4rem; margin: 1rem 0; font-size: 14px; line-height: 1.7; white-space: pre-wrap;
}
.recruiter-block {
    background: #161616; border-left: 3px solid #7eb8f5; border-radius: 0 8px 8px 0;
    padding: 1.2rem 1.4rem; margin: 1rem 0; font-size: 14px; line-height: 1.7; white-space: pre-wrap;
}
.section-label {
    font-family: 'Syne', sans-serif; font-size: 11px; font-weight: 700;
    letter-spacing: 0.12em; text-transform: uppercase; color: #c8f560; margin-bottom: 0.4rem;
}
.recruiter-card { background: #1a1a1a; border: 1px solid #2a2a2a; border-radius: 8px; padding: 1rem 1.2rem; margin-bottom: 0.8rem; }
.fallback-card { background: #1a1212; border: 1px solid #3a2020; border-radius: 8px; padding: 1rem 1.2rem; margin-bottom: 0.8rem; }
.tag-pill {
    display: inline-block; background: #1e2a1e; border: 1px solid #2e4a2e;
    border-radius: 20px; padding: 3px 10px; font-size: 11px; color: #a8d878;
    margin: 3px 4px 3px 0; cursor: default;
}
.tag-sentence { font-size: 11px; color: #555; font-style: italic; margin: 2px 0 8px 4px; }
.status-ok { color: #c8f560; font-size: 12px; }
.status-fail { color: #e07070; font-size: 12px; }
.disclaimer { font-size: 11px; color: #555; margin-top: 1.5rem; padding: 0.8rem; border: 1px solid #1e1e1e; border-radius: 6px; }
hr { border-color: #1e1e1e !important; margin: 1.8rem 0 !important; }
</style>
""", unsafe_allow_html=True)

st.markdown("# 🎯 Career Fair Prep Agent")
st.markdown("<p style='color:#666; font-size:13px; margin-top:-0.5rem;'>Built for Tepper MBA · Career fair ready in 2 minutes</p>", unsafe_allow_html=True)
st.markdown("---")

defaults = {"step": "input", "questions": [], "resume": "", "jd": None,
            "firm_overview": None, "company_context": None, "recruiters": [], "answers": [],
            "authenticated": False, "session_generations": 0}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# # ── Access code gate ────────────────────────────────────────────────────────────
# if not st.session_state.authenticated:
#     st.markdown("<div class='section-label'>Access Code Required</div>", unsafe_allow_html=True)
#     st.markdown("<p style='color:#666; font-size:13px;'>This tool is shared with a limited group. Enter the access code to continue.</p>", unsafe_allow_html=True)
#     code_input = st.text_input("", placeholder="Enter access code...", type="password", label_visibility="collapsed")
#     if st.button("Unlock →"):
#         if _check_access_code(code_input):
#             st.session_state.authenticated = True
#             st.rerun()
#         else:
#             st.error("Incorrect access code. Ask Arun for the code.")
#     st.stop()

# ── Daily cap check ──────────────────────────────────────────────────────────────
if _daily_count() >= DAILY_CAP:
    st.warning(f"⚠️ This tool has hit its daily limit of {DAILY_CAP} generations. Check back tomorrow!")
    st.stop()

# ── Session limit display ──────────────────────────────────────────────────────
remaining = MAX_SESSIONS - st.session_state.session_generations
if remaining <= 0:
    st.error(f"You've used all {MAX_SESSIONS} generations for this session. Close and reopen the browser tab to start fresh.")
    st.stop()
if remaining < MAX_SESSIONS:
    st.markdown(f"<p style='color:#555; font-size:11px; text-align:right;'>{remaining} generation(s) remaining this session</p>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# STEP 1 — Input
# ══════════════════════════════════════════════════════════════════════════════
if st.session_state.step == "input":

    st.markdown("<div class='section-label'>Your Resume</div>", unsafe_allow_html=True)
    resume = st.text_area("", placeholder="Paste your resume text here...", height=200, key="resume_input", label_visibility="collapsed")
    st.markdown("---")

    st.markdown("<div class='section-label'>Company</div>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns(3)
    with col1:
        company_name = st.text_input("Company name", placeholder="e.g. EV bots Inc.")
    with col2:
        industry = st.selectbox("Industry", [""] + INDUSTRIES)
    with col3:
        function = st.selectbox("Target function", [""] + FUNCTIONS)
    focus_areas = st.text_input("Known focus areas (optional)", placeholder="e.g. AI-first product, affordability")
    st.markdown("---")

    st.markdown("<div class='section-label'>Role Context</div>", unsafe_allow_html=True)
    context_mode = st.radio("", ["Job description", "Firm overview / career fair blurb", "Neither — just company info above"],
                            horizontal=True, label_visibility="collapsed")
    jd, firm_overview = None, None
    if context_mode == "Job description":
        jd = st.text_area("", placeholder="Paste the job description here...", height=160, label_visibility="collapsed")
    elif context_mode == "Firm overview / career fair blurb":
        firm_overview = st.text_area("", placeholder="Paste any overview or recruiting blurb the firm shared...", height=160, label_visibility="collapsed")
    st.markdown("---")

    st.markdown("<div class='section-label'>Recruiters (optional)</div>", unsafe_allow_html=True)
    st.markdown("<p style='color:#555; font-size:12px; margin-top:-0.3rem;'>Add recruiters you expect to meet. We'll attempt to load LinkedIn profiles and surface personal interests you can connect on.</p>", unsafe_allow_html=True)

    num_recruiters = st.number_input("Number of recruiters", min_value=0, max_value=5, value=0, step=1)
    recruiter_inputs = []
    for i in range(int(num_recruiters)):
        with st.container():
            st.markdown(f"<div class='recruiter-card'><strong>Recruiter {i+1}</strong></div>", unsafe_allow_html=True)
            rc1, rc2 = st.columns(2)
            with rc1:
                rname = st.text_input("Name", key=f"rname_{i}", placeholder="e.g. Sameer Jain")
            with rc2:
                rrole = st.text_input("Role / Title", key=f"rrole_{i}", placeholder="e.g. Senior PM")
            rurl = st.text_input("LinkedIn URL (optional)", key=f"rurl_{i}", placeholder="https://linkedin.com/in/...")
            rnotes = st.text_input("Any other context", key=f"rnotes_{i}", placeholder="e.g. Tepper alum, focuses on Robotics team")
            recruiter_inputs.append({"name": rname, "role": rrole, "url": rurl, "notes": rnotes})

    st.markdown("<div class='disclaimer'>⚠️ Prototype — don't include sensitive personal info. Nothing is stored after your session.</div>", unsafe_allow_html=True)

    if st.button("Continue →"):
        if not resume.strip():
            st.warning("Please paste your resume.")
        elif not company_name.strip():
            st.warning("Please enter a company name.")
        else:
            recruiters = []
            if recruiter_inputs:
                with st.spinner("Attempting to load LinkedIn profiles..."):
                    for r in recruiter_inputs:
                        if not r["name"] and not r["url"]:
                            continue
                        linkedin_text = try_fetch_linkedin(r["url"]) if r["url"] else None
                        personal_highlights = {}
                        if linkedin_text:
                            personal_highlights = extract_personal_highlights(linkedin_text, r["name"])
                        recruiters.append({
                            **r,
                            "linkedin_text": linkedin_text,
                            "pasted_text": None,
                            "personal_highlights": personal_highlights,
                            "fetch_attempted": bool(r["url"]),
                            "fetch_success": bool(linkedin_text),
                        })

            # Check if any LinkedIn fetches failed
            failed = [r for r in recruiters if r["fetch_attempted"] and not r["fetch_success"]]

            st.session_state.resume = resume
            st.session_state.jd = jd
            st.session_state.firm_overview = firm_overview
            st.session_state.company_context = {"company": company_name, "industry": industry, "function": function, "focus_areas": focus_areas}
            st.session_state.recruiters = recruiters

            if failed:
                st.session_state.step = "linkedin_fallback"
            else:
                with st.spinner("Reading your materials..."):
                    st.session_state.questions = ask_clarifying_questions(
                        resume, jd=jd, firm_overview=firm_overview,
                        company_context=st.session_state.company_context
                    )
                st.session_state.step = "clarify"
            st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# STEP 1.5 — LinkedIn fallback (only shown when fetch failed)
# ══════════════════════════════════════════════════════════════════════════════
elif st.session_state.step == "linkedin_fallback":

    st.markdown("### LinkedIn profiles couldn't be loaded")
    st.markdown("<p style='color:#888; font-size:13px;'>LinkedIn blocks automated access. For the recruiters below, paste their profile text manually to get personalized tips — or skip and continue with what we have.</p>", unsafe_allow_html=True)
    st.markdown("")

    updated_recruiters = list(st.session_state.recruiters)

    for i, r in enumerate(updated_recruiters):
        if not r.get("fetch_attempted") or r.get("fetch_success"):
            continue  # Only show failed ones

        name = r.get("name") or f"Recruiter {i+1}"
        st.markdown(f"<div class='fallback-card'>", unsafe_allow_html=True)
        st.markdown(f"**{name}** <span class='status-fail'>✗ LinkedIn blocked</span>", unsafe_allow_html=True)
        if r.get("url"):
            st.markdown(f"<span style='font-size:11px; color:#444;'>{r['url']}</span>", unsafe_allow_html=True)
        st.markdown("<p style='font-size:12px; color:#666; margin-top:0.5rem;'>Open their LinkedIn profile, copy the text from their About section, experience, and any personal details, then paste below:</p>", unsafe_allow_html=True)
        pasted = st.text_area(
            "", height=140, key=f"paste_{i}",
            placeholder=f"Paste {name}'s LinkedIn profile text here (About, experience, interests, volunteering...)...",
            label_visibility="collapsed"
        )
        if pasted.strip():
            updated_recruiters[i]["pasted_text"] = pasted.strip()
            # Extract personal highlights from pasted text
            updated_recruiters[i]["personal_highlights"] = extract_personal_highlights(pasted.strip(), name)
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("")
    col1, col2 = st.columns([1, 3])
    with col1:
        if st.button("← Back"):
            st.session_state.step = "input"
            st.rerun()
    with col2:
        label = "Continue with pasted info →" if any(r.get("pasted_text") for r in updated_recruiters) else "Skip & continue →"
        if st.button(label):
            st.session_state.recruiters = updated_recruiters
            with st.spinner("Reading your materials..."):
                st.session_state.questions = ask_clarifying_questions(
                    st.session_state.resume,
                    jd=st.session_state.jd,
                    firm_overview=st.session_state.firm_overview,
                    company_context=st.session_state.company_context
                )
            st.session_state.step = "clarify"
            st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# STEP 2 — Clarifying questions
# ══════════════════════════════════════════════════════════════════════════════
elif st.session_state.step == "clarify":

    # Show recruiter status summary
    if st.session_state.recruiters:
        st.markdown("<div class='section-label'>Recruiter Profiles</div>", unsafe_allow_html=True)
        for r in st.session_state.recruiters:
            name = r.get("name") or "Unnamed"
            highlights = r.get("personal_highlights", {})
            tags = highlights.get("tags", [])
            sentences = highlights.get("sentences", {})

            has_profile = r.get("linkedin_text") or r.get("pasted_text")

            if has_profile:
                st.markdown(f"**{name}** <span class='status-ok'>✓ Profile loaded</span>", unsafe_allow_html=True)
            elif r.get("fetch_attempted"):
                st.markdown(f"**{name}** — using name, role & notes only", unsafe_allow_html=True)
            else:
                st.markdown(f"**{name}**", unsafe_allow_html=True)

            # Personal interest tags + source sentences
            if tags:
                st.markdown("<p style='font-size:11px; color:#555; margin: 4px 0 2px 0;'>Personal interests found:</p>", unsafe_allow_html=True)
                tag_html = ""
                for tag in tags:
                    tag_html += f"<span class='tag-pill'>🏷 {tag}</span>"
                st.markdown(tag_html, unsafe_allow_html=True)
                for tag in tags:
                    if tag in sentences:
                        st.markdown(f"<div class='tag-sentence'>\"{sentences[tag]}\"</div>", unsafe_allow_html=True)
            st.markdown("")
        st.markdown("---")

    st.markdown("### A couple of quick questions")
    st.markdown("<p style='color:#666; font-size:13px;'>Your answers help personalize the output.</p>", unsafe_allow_html=True)

    answers = []
    for i, q in enumerate(st.session_state.questions):
        st.markdown(f"<div class='section-label'>Question {i+1}</div>", unsafe_allow_html=True)
        st.markdown(f"**{q}**")
        ans = st.text_input("", key=f"ans_{i}", label_visibility="collapsed", placeholder="Your answer...")
        answers.append(ans)
        st.markdown("")

    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button("← Back"):
            st.session_state.step = "input"
            st.rerun()
    with col2:
        if st.button("Generate my prep →"):
            if any(not a.strip() for a in answers):
                st.warning("Please answer both questions.")
            else:
                st.session_state.answers = answers
                st.session_state.step = "output"
                st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# STEP 3 — Output
# ══════════════════════════════════════════════════════════════════════════════
elif st.session_state.step == "output":

    # Generate once and cache in session state — prevents re-generation on download clicks
    if "prep_result" not in st.session_state:
        _increment_counter()
        st.session_state.session_generations += 1
        with st.spinner("Generating your career fair prep..."):
            st.session_state.prep_result = generate_prep(
                st.session_state.resume,
                st.session_state.jd,
                st.session_state.firm_overview,
                st.session_state.company_context,
                st.session_state.recruiters,
                st.session_state.questions,
                st.session_state.answers,
            )
    result = st.session_state.prep_result

    company = st.session_state.company_context.get("company", "this company") if st.session_state.company_context else "this company"
    st.markdown(f"### Your prep for **{company}**")
    st.markdown("---")

    st.markdown("<div class='section-label'>01 · Tailored Talking Points</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='output-block'>{result['talking_points']}</div>", unsafe_allow_html=True)

    st.markdown("<div class='section-label'>02 · Likely Recruiter Questions + Suggested Answers</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='output-block'>{result['recruiter_questions']}</div>", unsafe_allow_html=True)

    st.markdown("<div class='section-label'>03 · Your Differentiating Angle + 30-Second Pitch</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='output-block'>{result['differentiating_angle']}</div>", unsafe_allow_html=True)

    if result.get("recruiter_tips"):
        st.markdown("<div class='section-label'>04 · Recruiter-Specific Tips</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='recruiter-block'>{result['recruiter_tips']}</div>", unsafe_allow_html=True)

    st.markdown("---")

    # ── Download as PDF ───────────────────────────────────────────────────────
    try:
        pdf_bytes = generate_pdf(company, result, st.session_state.recruiters)
        safe_name = company.lower().replace(" ", "_").replace("/", "-")
        st.download_button(
            label="⬇ Download prep as PDF",
            data=pdf_bytes,
            file_name=f"career_fair_prep_{safe_name}.pdf",
            mime="application/pdf",
        )
    except Exception as e:
        st.caption(f"PDF generation failed: {e}")

    if st.button("← Prep for another company"):
        for key in list(defaults.keys()) + ["prep_result"]:
            if key in st.session_state:
                del st.session_state[key]
        st.rerun()
