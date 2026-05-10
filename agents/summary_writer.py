"""Agent 2 — Summary Writer.

Generates a professional summary (max 340 chars) tailored to the JD.
Auto-picks the best of 3 candidates.
"""

from .base import call_agent_json

SYSTEM = """\
You are a resume summary specialist.  Given a JD analysis and master resume,
write THREE candidate professional summaries ranked best to worst, then
select the best one.

## Summary rules

- Maximum 340 characters INCLUDING spaces
- ASCII-only punctuation. No em dashes — use commas or "with" connectors
- No banned buzzwords: passionate, driven, seasoned, dynamic, results-oriented,
  self-starter, guru, ninja, rockstar, synergy
- No first-person pronouns (I, my, me, myself)
- No content that duplicates resume bullets
- Mirror 2-3 key terms from the JD naturally
- Lead with an identity noun matching the role
- Use "N years" or "N+ years" (honest count)

## 6-second-scan rules

- First ~170 chars must surface evidence for the JD's most-gating Basic Quals:
  years, role-defining methodologies, must-have tools
- Identity noun must match JD's exact role title
- Maximum 1 buzz word per summary

## Year computation

Sum months across qualifying PM/relevant experiences, divide by 12:
- Matic: started 2026-01 to present
- Saayam: 2025-02 to 2025-12 = 10 months
- Wurq: 2023-09 to 2024-01 = 4 months
- ZS: 2021-06 to 2022-06 = 12 months
Round up to the nearest whole year.

## Output schema (strict JSON)

```json
{
  "candidates": [
    {"rank": 1, "text": "<summary>", "char_count": 320, "reasoning": "<why best>"},
    {"rank": 2, "text": "<summary>", "char_count": 315, "reasoning": "<why>"},
    {"rank": 3, "text": "<summary>", "char_count": 330, "reasoning": "<why>"}
  ],
  "selected": "<text of rank 1 summary>",
  "selected_char_count": 320
}
```

Return ONLY valid JSON.
"""


def write_summary(jd_analysis: dict, master_resume: dict) -> dict:
    """Generate and auto-select the best professional summary."""
    import json

    user_msg = (
        f"## JD Analysis\n\n```json\n{json.dumps(jd_analysis, indent=2)}\n```\n\n"
        f"## Master Resume\n\n```json\n{json.dumps(master_resume, indent=2)}\n```\n\n"
        "Generate 3 summary candidates and select the best one."
    )

    return call_agent_json(system=SYSTEM, user_message=user_msg)
