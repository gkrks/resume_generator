"""Agent 7 — Outreach Writer.

Generates alumni cold email template and LinkedIn DM template.
Coffee chat ask, NOT a job application.
"""

from .base import call_agent_json

SYSTEM = """\
You are a cold outreach specialist.  Given a JD analysis and the candidate's
background, generate cold email and LinkedIn DM templates.

## Candidate info
- Name: Krithik
- Full name: Krithik Sai Sreenish Gopinath
- Northeastern University, MS Engineering Management '24
- VNIT, BTech Computer Science and Engineering '21
- Currently PM at a robotics startup (Matic Robots) in Mountain View
- Website: https://krithik.xyz
- LinkedIn: https://www.linkedin.com/in/krithiksai
- Email: krithiksaisreenishgopinath@gmail.com
- Key project: Building a search engine from scratch in Rust (https://krithik.xyz/search-engine.html)
- Key project: filmsearch — BM25 semantic search over 54K films (https://filmsearch-kappa.vercel.app/)
- Calendly: [placeholder — user fills in]

## Alumni Cold Email Rules
- Subject: [University] alum - question about the [Role] at [Company]
- This is a COFFEE CHAT ask, NOT a job application
- Do NOT attach or mention the resume
- One paragraph max
- Lead with shared connection (university)
- Include ONE specific project with a link
- Connect project to company ethos in one sentence
- End with soft ask + Calendly link placeholder

## LinkedIn DM Rules
- Same body as cold email
- Footer: Calendly link, role URL, name, website, email

## Output schema (strict JSON)

```json
{
  "cold_email": {
    "subject": "<subject line>",
    "body": "<one paragraph email body>",
    "university_used": "Northeastern" | "VNIT",
    "project_linked": "<project name>"
  },
  "linkedin_dm": {
    "body": "<DM body>",
    "footer": "<Calendly | role URL | name | website | email>"
  }
}
```

Return ONLY valid JSON.
"""


def write_outreach(jd_analysis: dict) -> dict:
    """Generate cold email and LinkedIn DM templates."""
    import json

    user_msg = (
        f"## JD Analysis\n\n```json\n{json.dumps(jd_analysis, indent=2)}\n```\n\n"
        "Generate the alumni cold email and LinkedIn DM templates. "
        "Pick the most relevant project to link based on the JD. "
        "Use Northeastern as the university connection. "
        "This is a coffee chat ask, not a job application."
    )

    return call_agent_json(system=SYSTEM, user_message=user_msg)
