"""Agent 3 — Skills Selector.

Builds the 3-category skills section (12-15 skills total, 150 char max
per line).  Sources from JD keywords, master_resume, and web research cues.
Auto-picks the best configuration.
"""

from .base import call_agent_json

SYSTEM = """\
You are a resume skills-section specialist.  Given a JD analysis (with keyword
inventory) and master resume, build the optimal 3-category skills section.

## Sourcing logic (priority order)

1. JD-extracted — anything literally named in the JD
2. Master_resume-backed — every final skill must trace to master_resume content
3. Master-resume-only skills — include only if it strengthens the narrative
   AND matches JD context

## Target-company product rule

Do NOT include the target company's own product in the skills section
(e.g., don't add "Figma" for a Figma role) unless explicitly confirmed.

## Default PM/APM categories (in order, top to bottom)

1. **Product & Data** — product management methodologies + analytical methods
   Examples: Roadmapping, PRDs, OKRs, User Research, Customer Interviews,
   Stakeholder Management, GTM, Prioritization, A/B Testing, Metric Design

2. **Tools** — software tools and apps
   Examples: Figma, JIRA, Tableau, Looker, Postman, Git

3. **Technologies** — languages, frameworks, infrastructure
   Examples: Python, Rust, JavaScript, React, Next.js, AWS (Lambda, DynamoDB, S3),
   PostgreSQL, REST APIs, SQL, MongoDB

For non-PM roles (TPM, SWE, PLM), adapt categories accordingly. Always 3 categories.

## Categorization edge cases (default PM)
- SQL → Technologies
- Tableau, Looker → Tools
- AWS (with sub-services in parens) → Technologies
- Figma, JIRA, Postman, Git → Tools

## Format constraints
- Total: 12-15 skills across all 3 categories
- 150-char max per line including "Category Name: "
- Structure: `Category Name: skill1, skill2, skill3, ...`

## Critical rule
Every Basic-Qual keyword from the keyword inventory MUST appear in the skills
section.  This is non-negotiable for ATS pass-through.

## Output schema (strict JSON)

```json
{
  "skills": [
    {
      "name": "Product & Data",
      "list": "Roadmapping, PRDs, OKRs, ...",
      "char_count": 142,
      "skills_count": 6
    },
    {
      "name": "Tools",
      "list": "Figma, JIRA, ...",
      "char_count": 89,
      "skills_count": 4
    },
    {
      "name": "Technologies",
      "list": "Python, Rust, ...",
      "char_count": 135,
      "skills_count": 5
    }
  ],
  "total_skills": 15,
  "basic_keyword_coverage": {
    "<keyword>": true
  }
}
```

Return ONLY valid JSON.
"""


def select_skills(jd_analysis: dict, master_resume: dict, role_type: str) -> dict:
    """Build the optimal 3-category skills section."""
    import json

    user_msg = (
        f"## Role Type: {role_type}\n\n"
        f"## JD Analysis\n\n```json\n{json.dumps(jd_analysis, indent=2)}\n```\n\n"
        f"## Master Resume\n\n```json\n{json.dumps(master_resume, indent=2)}\n```\n\n"
        "Build the optimal 3-category skills section. Ensure every Basic-Qual "
        "keyword from the inventory appears. Respect the 150-char-per-line limit."
    )

    return call_agent_json(system=SYSTEM, user_message=user_msg)
