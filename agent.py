import anthropic
import json
import re
import urllib.request

client = anthropic.Anthropic()
MODEL = "claude-sonnet-4-20250514"

INDUSTRIES = [
    "Technology", "Healthcare / Pharma", "Finance / Banking", "Consulting",
    "Energy / Utilities", "Consumer Goods / Retail", "Media / Entertainment",
    "Real Estate", "Non-profit / Government", "Other"
]

FUNCTIONS = [
    "Product Management", "Strategy & Consulting", "Investment Banking",
    "Private Equity / VC", "Corporate Finance / FP&A", "Data & Analytics",
    "Marketing", "Operations / Supply Chain", "General Management", "Other"
]


def try_fetch_linkedin(url: str):
    """Attempt best-effort LinkedIn fetch. Returns text or None."""
    if not url or "linkedin.com" not in url:
        return None
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        }
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=6) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
            text = re.sub(r"<[^>]+>", " ", html)
            text = re.sub(r"\s+", " ", text).strip()
            return text[:4000] if len(text) > 200 else None
    except Exception:
        return None


def extract_personal_highlights(profile_text: str, recruiter_name: str) -> dict:
    """
    Extract hobbies, volunteering, personal interests from profile text.
    Returns dict with 'tags' (short labels) and 'sentences' (source sentences per tag).
    """
    if not profile_text or len(profile_text.strip()) < 50:
        return {"tags": [], "sentences": {}}

    prompt = f"""You are analyzing a LinkedIn profile to find personal, non-professional details about {recruiter_name}.

From the profile text below, extract any mentions of:
- Hobbies or personal interests (sports, music, reading, cooking, travel, etc.)
- Volunteering or community work
- Causes they care about
- Side projects unrelated to their job
- Personal values or passions mentioned

For each item found, return:
1. A short tag label (2-4 words, e.g. "Marathon Running", "Food Bank Volunteer")
2. The exact sentence or phrase from the profile that mentions it

Return ONLY a JSON object in this exact format, no preamble, no markdown:
{{
  "highlights": [
    {{"tag": "Short Label", "sentence": "Exact sentence from profile that mentions this"}},
    ...
  ]
}}

If nothing personal is found, return: {{"highlights": []}}

PROFILE TEXT:
{profile_text[:3000]}
"""
    message = client.messages.create(
        model=MODEL, max_tokens=600,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = re.sub(r"^```(?:json)?|```$", "", message.content[0].text.strip(), flags=re.MULTILINE).strip()
    try:
        data = json.loads(raw)
        highlights = data.get("highlights", [])
        tags = [h["tag"] for h in highlights if "tag" in h]
        sentences = {h["tag"]: h["sentence"] for h in highlights if "tag" in h and "sentence" in h}
        return {"tags": tags, "sentences": sentences}
    except Exception:
        return {"tags": [], "sentences": {}}


def _build_context_block(jd, firm_overview, company_context):
    parts = []
    if jd:
        parts.append(f"JOB DESCRIPTION:\n{jd}")
    if firm_overview:
        parts.append(f"FIRM OVERVIEW / CAREER FAIR BLURB:\n{firm_overview}")
    if not jd and not firm_overview and company_context:
        parts.append(
            "COMPANY CONTEXT (no JD or overview available):\n"
            f"Company: {company_context.get('company', 'Unknown')}\n"
            f"Industry: {company_context.get('industry', 'Unknown')}\n"
            f"Function: {company_context.get('function', 'Unknown')}\n"
            f"Known focus areas: {company_context.get('focus_areas', 'Not specified')}\n\n"
            "Use your knowledge of this company, industry and function to infer "
            "what they typically look for in MBA candidates."
        )
    elif company_context:
        parts.append(
            f"COMPANY: {company_context.get('company', '')}, "
            f"INDUSTRY: {company_context.get('industry', '')}, "
            f"TARGET FUNCTION: {company_context.get('function', '')}"
        )
    return "\n\n".join(parts) if parts else "No company context provided."


def _build_recruiter_block(recruiters: list) -> str:
    if not recruiters:
        return ""
    lines = ["RECRUITER PROFILES:"]
    for i, r in enumerate(recruiters, 1):
        lines.append(f"\nRecruiter {i}: {r.get('name', 'Unknown')}")
        if r.get("role"):
            lines.append(f"  Role: {r['role']}")
        profile_text = r.get("linkedin_text") or r.get("pasted_text")
        if profile_text:
            lines.append(f"  Profile info: {profile_text[:1000]}")
        elif r.get("url"):
            lines.append(f"  LinkedIn URL provided but could not be scraped.")
        if r.get("notes"):
            lines.append(f"  Additional notes: {r['notes']}")
        if r.get("personal_highlights", {}).get("tags"):
            lines.append(f"  Personal interests: {', '.join(r['personal_highlights']['tags'])}")
    return "\n".join(lines)


def ask_clarifying_questions(resume, jd=None, firm_overview=None, company_context=None):
    context_block = _build_context_block(jd, firm_overview, company_context)
    prompt = f"""You are a career coach helping an MBA student prep for a career fair.

Given their resume and context below, generate exactly 2 clarifying questions to personalize their prep.

Question 1: what specifically excites them about this company or opportunity.
Question 2: the single most important thing they want the recruiter to remember about them.

Keep questions concise and conversational. Return ONLY a JSON array of 2 strings. No preamble, no markdown fences.

RESUME:
{resume}

{context_block}
"""
    # Build messages with cache_control on the resume block (largest static chunk)
    user_content = [
        {
            "type": "text",
            "text": f"RESUME:\n{resume}",
            "cache_control": {"type": "ephemeral"},  # cache for 5 min
        },
        {
            "type": "text",
            "text": prompt.replace(f"RESUME:\n{resume}", "").strip(),
        },
    ]
    message = client.messages.create(
        model=MODEL, max_tokens=300,
        messages=[{"role": "user", "content": user_content}],
        betas=["prompt-caching-2024-07-31"],
    )
    raw = re.sub(r"^```(?:json)?|```$", "", message.content[0].text.strip(), flags=re.MULTILINE).strip()
    try:
        questions = json.loads(raw)
        if isinstance(questions, list) and len(questions) >= 2:
            return questions[:2]
    except Exception:
        pass
    return [
        "What excites you most about this company — their mission, the team, or the type of work?",
        "What's the one thing from your background you most want this recruiter to remember?"
    ]


def generate_prep(resume, jd, firm_overview, company_context, recruiters, questions, answers):
    context_block = _build_context_block(jd, firm_overview, company_context)
    recruiter_block = _build_recruiter_block(recruiters)
    qa_block = "\n".join([f"Q: {q}\nA: {a}" for q, a in zip(questions, answers)])

    has_recruiters = bool(recruiters)
    names = [r.get("name", f"Recruiter {i+1}") for i, r in enumerate(recruiters)] if has_recruiters else []
    recruiter_instruction = f"""
  "recruiter_tips": "For each recruiter, give 2-3 specific conversation tips based on their background, role, school, or personal interests. If they have personal interests listed, suggest a natural way to bring up any overlap. Format as [Name]: tip. tip. Separated by line breaks. Names: {', '.join(names)}",""" if has_recruiters else ""

    fn = company_context.get('function', 'MBA role') if company_context else 'MBA role'

    prompt = f"""You are an expert career coach for MBA students targeting roles across any industry or function.

Generate career fair prep based on the candidate's resume, company context, and their answers.

RESUME:
{resume}

{context_block}

{recruiter_block}

CANDIDATE'S ANSWERS:
{qa_block}

Generate a JSON object with these keys. Plain text with line breaks — no markdown, no bullet symbols beyond a dash.

{{
  "talking_points": "3 strong talking points connecting specific resume achievements to this company's needs. Tailor to {fn}. Numbered, separated by line breaks.",
  "recruiter_questions": "3 likely questions this recruiter will ask, each with a suggested answer grounded in the candidate's actual experience. Format as Q: ... then A: ... separated by line breaks.",
  "differentiating_angle": "3-4 sentences on what genuinely sets this candidate apart from the typical MBA applicant pool for this company and function. End with a 30-second pitch they can deliver at the booth."{recruiter_instruction}
}}

Return ONLY the JSON object. No preamble, no markdown fences.
"""

    user_content = [
        {
            "type": "text",
            "text": f"RESUME:\n{resume}",
            "cache_control": {"type": "ephemeral"},
        },
        {
            "type": "text",
            "text": prompt.replace(f"RESUME:\n{resume}", "").strip(),
        },
    ]
    message = client.messages.create(
        model=MODEL, max_tokens=2000,
        messages=[{"role": "user", "content": user_content}],
        betas=["prompt-caching-2024-07-31"],
    )
    raw = re.sub(r"^```(?:json)?|```$", "", message.content[0].text.strip(), flags=re.MULTILINE).strip()
    try:
        result = json.loads(raw)
        for key in ["talking_points", "recruiter_questions", "differentiating_angle"]:
            if key not in result:
                result[key] = "Could not generate this section. Please try again."
        return result
    except Exception:
        return {
            "talking_points": raw,
            "recruiter_questions": "Could not parse output. Please try again.",
            "differentiating_angle": "Could not parse output. Please try again.",
        }
