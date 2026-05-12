"""Generate the working_resume JSON consumed by fill_resume.js."""

import json
from datetime import date


def build_working_resume(
    master_resume: dict,
    jd_analysis: dict,
    summary: str,
    skills_result: dict,
    bullet_result: dict,
) -> dict:
    """Assemble the working resume JSON from all locked artifacts."""

    # Build experience id -> master data lookup
    exp_lookup = {e["id"]: e for e in master_resume["experiences"]}
    proj_lookup = {p["id"]: p for p in master_resume["projects"]}

    # Build skills override
    skills_override = []
    for s in skills_result["skills"]:
        skills_override.append({"name": s["name"], "list": s["list"]})

    # Build experiences
    experiences = []
    for sel in jd_analysis["selected_experiences"]:
        exp_id = sel["id"]
        master_exp = exp_lookup[exp_id]
        raw_bullets = bullet_result["final_bullets"].get(exp_id, [])
        # Guard: only accept bullets that actually belong to this experience
        final_bullets = [fb for fb in raw_bullets if fb["bullet_id"].startswith(exp_id)]

        # Use rewritten bullets if available, otherwise fall back to master
        bullets = []
        for fb in final_bullets:
            bullets.append({"id": fb["bullet_id"], "text": fb["text"]})

        # If no bullets matched (shouldn't happen), use top N from master
        if not bullets:
            n = sel.get("bullets_allocated", 2)
            for b in master_exp["bullets"][:n]:
                bullets.append({"id": b["id"], "text": b["text"]})

        experiences.append({
            "id": exp_id,
            "role": sel["role_title"],
            "company": master_exp["company"],
            "location": master_exp["location"],
            "start_date": master_exp["start_date"],
            "end_date": master_exp["end_date"],
            "bullets": bullets,
        })

    # Build projects
    projects = []
    for sel in jd_analysis["selected_projects"]:
        proj_id = sel["id"]
        master_proj = proj_lookup[proj_id]
        raw_bullets = bullet_result["final_bullets"].get(proj_id, [])
        # Guard: only accept bullets that actually belong to this project
        final_bullets = [fb for fb in raw_bullets if fb["bullet_id"].startswith(proj_id)]

        bullets = []
        for fb in final_bullets:
            bullets.append({"id": fb["bullet_id"], "text": fb["text"]})

        if not bullets:
            n = sel.get("bullets_allocated", 2)
            for b in master_proj["bullets"][:n]:
                bullets.append({"id": b["id"], "text": b["text"]})

        projects.append({
            "id": proj_id,
            "name": master_proj["name"],
            "description": master_proj["description"],
            "url": master_proj.get("url", ""),
            "bullets": bullets,
        })

    # Build education
    education = []
    for e in master_resume["education"]:
        education.append({
            "degree": e["major"] and f"{e['degree']}, {e['major']}" or e["degree"],
            "university": e["university"],
            "start_date": e["start_date"],
            "end_date": e["end_date"],
        })

    # Determine email
    email = master_resume["contact"].get("primary_email") or "krithiksaisreenishgopinath@gmail.com"

    return {
        "schema_version": 2,
        "last_updated": date.today().isoformat(),
        "__title_override": jd_analysis.get("title_line"),
        "__summary_override": summary,
        "__skills_override": skills_override,
        "__email_override": email,
        "contact": master_resume["contact"],
        "experiences": experiences,
        "projects": projects,
        "education": education,
    }


def save_working_resume(working_resume: dict, output_path: str) -> str:
    """Save the working resume JSON to disk."""
    with open(output_path, "w") as f:
        json.dump(working_resume, f, indent=2)
    return output_path
