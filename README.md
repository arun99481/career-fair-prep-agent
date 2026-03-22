# Career Fair Prep Agent

An AI-powered prep tool for MBA students heading into career fairs.
Paste your resume + JD, answer 2 quick questions, get tailored talking points, likely recruiter questions, and your differentiating angle.

---

## Local Setup

```bash
# 1. Clone or download this folder

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set your Anthropic API key
export ANTHROPIC_API_KEY=your_key_here

# 4. Run the app
streamlit run app.py
```

App opens at http://localhost:8501

---

## Deploy on Streamlit Community Cloud (Free, shareable link)

1. Push this folder to a **public or private GitHub repo**
2. Go to https://share.streamlit.io → "New app"
3. Connect your repo, set `app.py` as the entry point
4. Under **Advanced settings → Secrets**, add:
   ```
   ANTHROPIC_API_KEY = "your_key_here"
   ```
5. Click Deploy → you get a shareable link instantly

> Update `agent.py` line 6 to read from secrets in production:
> ```python
> client = anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])
> ```

---

## Project Structure

```
career_fair_prep/
├── app.py            # Streamlit UI + conversation flow
├── agent.py          # Anthropic API calls + prompts
├── requirements.txt
└── README.md
```

---

## Estimated API Cost

~$0.01–0.03 per user session at current Claude Sonnet pricing.
For 15 users = cents, not dollars.
