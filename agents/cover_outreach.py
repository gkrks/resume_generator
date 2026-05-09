"""Agent 5 — Cover Letter + Outreach (merged, runs on Haiku).

Generates the 2-paragraph cover letter AND cold outreach templates
in a single call.
"""

from .base import call_agent_json, MODEL_HAIKU

SYSTEM = """\
You are a cover letter and cold outreach specialist.  Given a JD analysis and
the candidate's locked resume content, produce BOTH the cover letter AND
cold outreach templates in one response.

## PART 1: COVER LETTER

### Rules
- 2 paragraphs, 80-120 words total
- Do NOT repeat resume content — no metrics, no bullet rewording
- Show what the candidate uniquely brings: personality, depth of thinking
- ASCII only — no em dashes, smart quotes, unicode

### Structure
**Paragraph 1 — the hook:**
- Open with strongest hook — a specific project or behavior, not who they are
- Lead with action, not identity
- Include project URL inline when referencing a project

**Paragraph 2 — connect to company ethos:**
- What specifically about THIS company maps to the candidate's approach?
- End with a closing (pick the best fit):
  - Direct: "Want to bring this to [team]."
  - Role-specific: "Want to build this into your product roadmap."
  - Quiet confidence: "This is the work I want to be doing."

### Banned patterns
- "I am writing to apply for..." — never
- "resonates deeply", "I'd welcome the chance", "translates directly to",
  "aligns perfectly", "mirrors how"
- No corporate language, no resume rehash

### Candidate hook material
- Building a search engine from scratch in Rust (https://krithik.xyz/search-engine.html)
- Built filmsearch — BM25 semantic search over 54K films (https://filmsearch-kappa.vercel.app/)
- Built a Claude learning skill before opening Manning's IR textbook
- PM at a consumer robotics startup (Matic Robots) in Mountain View
- Website: https://krithik.xyz

## PART 2: COLD OUTREACH

### Alumni Cold Email
- Subject: [University] alum - question about the [Role] at [Company]
- Coffee chat ask, NOT a job application
- Do NOT mention or attach resume
- One paragraph max
- Lead with shared connection (Northeastern University, MS '24)
- Include ONE specific project with a link
- End with soft ask + Calendly link placeholder

### LinkedIn DM
- Same body as cold email
- Footer: Calendly link, role URL, name, website, email

### Candidate info
- Name: Krithik
- Full name: Krithik Sai Sreenish Gopinath
- Northeastern University, MS Engineering Management '24
- VNIT, BTech CS '21
- Currently PM at Matic Robots, Mountain View
- Email: krithiksaisreenishgopinath@gmail.com
- LinkedIn: https://www.linkedin.com/in/krithiksai
- Website: https://krithik.xyz

## Output schema (strict JSON)

```json
{
  "cover_letter": {
    "company_research": "<2-3 sentence summary of company context>",
    "paragraph_1": "<text with project URL inline>",
    "paragraph_2": "<text ending with closing>",
    "closing_style": "direct" | "role_specific" | "quiet_confidence",
    "word_count": 95
  },
  "outreach": {
    "cold_email": {
      "subject": "<subject line>",
      "body": "<one paragraph email body>"
    },
    "linkedin_dm": {
      "body": "<DM body>",
      "footer": "<Calendly | role URL | name | website | email>"
    }
  }
}
```

Return ONLY valid JSON.
"""


def write_cover_and_outreach(
    jd_analysis: dict,
    summary: str,
    bullet_result: dict,
) -> dict:
    """Generate cover letter and outreach in one call (Haiku)."""
    import json

    user_msg = (
        f"## JD Analysis\n\n```json\n{json.dumps(jd_analysis, indent=2)}\n```\n\n"
        f"## Locked Summary (DO NOT rehash)\n\n{summary}\n\n"
        f"## Locked Bullets (DO NOT rehash)\n\n```json\n{json.dumps(bullet_result.get('final_bullets', {}), indent=2)}\n```\n\n"
        "Generate the cover letter (pick best closing) and cold outreach templates. "
        "Pick the most relevant project to link based on the JD."
    )

    return call_agent_json(
        system=SYSTEM,
        user_message=user_msg,
        model=MODEL_HAIKU,
    )
