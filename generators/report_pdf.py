"""Generates a consolidated ATS / Recruiter / Hiring Manager evaluation PDF."""

from fpdf import FPDF
from datetime import date


# ── Colors ───────────────────────────────────────────────────────
_GREEN = (34, 139, 34)
_RED = (200, 30, 30)
_AMBER = (210, 140, 0)
_DARK = (30, 30, 30)
_GRAY = (100, 100, 100)
_LIGHT_GREEN_BG = (230, 255, 230)
_LIGHT_RED_BG = (255, 230, 230)
_LIGHT_AMBER_BG = (255, 245, 220)
_WHITE = (255, 255, 255)
_HEADER_BG = (40, 40, 60)
_SECTION_BG = (240, 240, 248)
_LINK_BLUE = (30, 80, 180)
_INFO_BG = (245, 248, 255)


def _status_color(status: str):
    s = status.upper()
    if s in ("PASS", "PROCEED", "COVERED", "TRUE"):
        return _GREEN
    if s in ("FAIL", "FIX_REQUIRED", "CRITICAL", "FALSE", "YES"):
        return _RED
    return _AMBER


def _status_bg(status: str):
    s = status.upper()
    if s in ("PASS", "PROCEED", "COVERED", "TRUE"):
        return _LIGHT_GREEN_BG
    if s in ("FAIL", "FIX_REQUIRED", "CRITICAL", "FALSE", "YES"):
        return _LIGHT_RED_BG
    return _LIGHT_AMBER_BG


class ReportPDF(FPDF):

    def __init__(self, company: str, role: str):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.company = company
        self.role = role
        self.set_auto_page_break(auto=True, margin=12)

    def header(self):
        self.set_fill_color(*_HEADER_BG)
        self.rect(0, 0, 210, 24, "F")
        self.set_font("Helvetica", "B", 14)
        self.set_text_color(*_WHITE)
        self.set_y(5)
        self.cell(0, 7, "Resume Evaluation Report", align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "", 9)
        self.cell(0, 5, f"{self.role}  @  {self.company}   |   {date.today().isoformat()}", align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(5)

    def footer(self):
        self.set_y(-10)
        self.set_font("Helvetica", "I", 7)
        self.set_text_color(*_GRAY)
        self.cell(0, 6, f"Page {self.page_no()}/{{nb}}", align="C")

    # ── Drawing helpers ──────────────────────────────────────────

    def section_title(self, title: str):
        self.set_fill_color(*_SECTION_BG)
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(*_DARK)
        self.cell(0, 7, f"  {title}", fill=True, new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

    def verdict_banner(self, verdict: str):
        bg = _LIGHT_GREEN_BG if verdict.upper() == "PROCEED" else _LIGHT_RED_BG
        fg = _GREEN if verdict.upper() == "PROCEED" else _RED
        self.set_fill_color(*bg)
        self.set_font("Helvetica", "B", 16)
        self.set_text_color(*fg)
        label = "PASS  -  Ready to Submit" if verdict.upper() == "PROCEED" else "NEEDS FIXES  -  Do Not Submit"
        self.cell(0, 12, label, align="C", fill=True, new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(*_DARK)
        self.ln(3)

    def info_row(self, label: str, value: str, is_url: bool = False):
        """Compact key-value row for the job details card."""
        self.set_font("Helvetica", "B", 7.5)
        self.set_text_color(*_GRAY)
        self.cell(28, 4.5, label, new_x="RIGHT")
        self.set_font("Helvetica", "", 7.5)
        if is_url and value:
            self.set_text_color(*_LINK_BLUE)
            self.cell(0, 4.5, value[:85], new_x="LMARGIN", new_y="NEXT")
        else:
            self.set_text_color(*_DARK)
            self.cell(0, 4.5, value[:90], new_x="LMARGIN", new_y="NEXT")

    def kv_row(self, key: str, value: str, status: str | None = None):
        self.set_font("Helvetica", "B", 8)
        self.set_text_color(*_DARK)
        self.cell(50, 5, key, new_x="RIGHT")
        if status:
            color = _status_color(status)
            bg = _status_bg(status)
            self.set_fill_color(*bg)
            self.set_font("Helvetica", "B", 8)
            self.set_text_color(*color)
            self.cell(14, 5, status.upper(), fill=True, align="C", new_x="RIGHT")
            self.cell(2, 5, "", new_x="RIGHT")
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*_DARK)
        self.multi_cell(0, 5, value, new_x="LMARGIN", new_y="NEXT")

    def table_header(self, cols: list[tuple[str, int]]):
        self.set_fill_color(*_HEADER_BG)
        self.set_text_color(*_WHITE)
        self.set_font("Helvetica", "B", 7)
        for name, w in cols:
            self.cell(w, 5, name, fill=True, align="C", new_x="RIGHT")
        self.ln()
        self.set_text_color(*_DARK)

    def table_row(self, cells: list[tuple[str, int]], status_col: int | None = None):
        self.set_font("Helvetica", "", 7)
        for i, (text, w) in enumerate(cells):
            if status_col is not None and i == status_col:
                color = _status_color(text)
                bg = _status_bg(text)
                self.set_fill_color(*bg)
                self.set_text_color(*color)
                self.set_font("Helvetica", "B", 7)
                self.cell(w, 4.5, text, fill=True, align="C", new_x="RIGHT")
                self.set_text_color(*_DARK)
                self.set_font("Helvetica", "", 7)
            else:
                self.cell(w, 4.5, str(text)[:int(w / 1.6)], new_x="RIGHT")
        self.ln()

    def bullet_item(self, text: str):
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*_DARK)
        self.cell(5, 4, "-", new_x="RIGHT")
        self.multi_cell(0, 4, text, new_x="LMARGIN", new_y="NEXT")


def generate_report_pdf(
    coverage_result: dict,
    jd_analysis: dict,
    output_path: str,
    job_meta: dict | None = None,
) -> str:
    """Generate the consolidated evaluation PDF.

    Args:
        coverage_result: Output from the coverage_checker agent.
        jd_analysis: Output from the jd_analyzer agent.
        output_path: Where to write the PDF.
        job_meta: Optional dict with queue/listing metadata:
            role_url, posted_date, location, yoe_min, yoe_max,
            ats_platform, apm_signal, listing_id, queue_id,
            seniority, employment_type

    Returns:
        The output_path.
    """
    company = jd_analysis.get("company", "Unknown")
    role = jd_analysis.get("role_title", "Unknown")
    verdict = coverage_result.get("verdict", "UNKNOWN")
    meta = job_meta or {}

    pdf = ReportPDF(company=company, role=role)
    pdf.alias_nb_pages()
    pdf.add_page()

    # ── Job Details Card (2-column layout) ─────────────────────────
    ROW_H = 4.2
    LEFT_X = pdf.l_margin
    COL2_X = 105  # start of right column
    LBL_W = 22
    VAL_W_L = COL2_X - LEFT_X - LBL_W - 2  # left col value width
    VAL_W_R = 210 - pdf.r_margin - COL2_X - LBL_W - 2  # right col value width

    def _info(x: float, label: str, value: str, is_url: bool = False):
        pdf.set_xy(x, pdf.get_y())
        pdf.set_font("Helvetica", "B", 7)
        pdf.set_text_color(*_GRAY)
        pdf.cell(LBL_W, ROW_H, label, new_x="RIGHT")
        val_w = VAL_W_L if x < COL2_X else VAL_W_R
        pdf.set_font("Helvetica", "", 7)
        if is_url and value:
            pdf.set_text_color(*_LINK_BLUE)
        else:
            pdf.set_text_color(*_DARK)
        pdf.cell(val_w, ROW_H, value[:int(val_w / 1.4)], new_x="RIGHT")

    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(*_DARK)
    pdf.cell(0, 5, "  Job Details", new_x="LMARGIN", new_y="NEXT")

    # Gather values
    role_url = meta.get("role_url", jd_analysis.get("role_url", ""))
    location = meta.get("location", jd_analysis.get("location", ""))
    yoe_min = meta.get("yoe_min")
    yoe_max = meta.get("yoe_max")
    yoe_range = jd_analysis.get("yoe_range", "")
    if yoe_min or yoe_max:
        yoe_str = f"{yoe_min or '?'}-{yoe_max or '?'} yrs"
    elif yoe_range:
        yoe_str = f"{yoe_range} yrs"
    else:
        yoe_str = ""
    posted = str(meta.get("posted_date", ""))
    seniority = meta.get("seniority", "")
    emp_type = meta.get("employment_type", "")
    level_type = " | ".join(p for p in [seniority, emp_type] if p)
    ats = meta.get("ats_platform", "")
    layout = jd_analysis.get("layout", "")
    if layout == "3+":
        layout_str = "3+ (4 exp + 1 proj)"
    elif layout == "swe":
        layout_str = "swe (4 exp + 2 proj)"
    elif layout == "0-2":
        layout_str = "0-2 (3 exp + 2 proj)"
    elif layout:
        layout_str = layout
    else:
        layout_str = ""
    listing_id = meta.get("listing_id", "")
    queue_id = meta.get("queue_id", "")

    # Row 1: Role | Location
    row_y = pdf.get_y()
    _info(LEFT_X, "Role:", role)
    pdf.set_xy(COL2_X, row_y)
    _info(COL2_X, "Location:", location)
    pdf.ln(ROW_H)

    # Row 2: Company | Experience
    row_y = pdf.get_y()
    _info(LEFT_X, "Company:", company)
    if yoe_str:
        pdf.set_xy(COL2_X, row_y)
        _info(COL2_X, "YOE:", yoe_str)
    pdf.ln(ROW_H)

    # Row 3: URL (full width)
    if role_url:
        pdf.set_font("Helvetica", "B", 7)
        pdf.set_text_color(*_GRAY)
        pdf.cell(LBL_W, ROW_H, "URL:", new_x="RIGHT")
        pdf.set_font("Helvetica", "", 7)
        pdf.set_text_color(*_LINK_BLUE)
        pdf.cell(0, ROW_H, role_url[:95], new_x="LMARGIN", new_y="NEXT")

    # Row 4: Posted | Level/Type
    row_y = pdf.get_y()
    if posted:
        _info(LEFT_X, "Posted:", posted)
    if level_type:
        pdf.set_xy(COL2_X, row_y)
        _info(COL2_X, "Level:", level_type)
    if posted or level_type:
        pdf.ln(ROW_H)

    # Row 5: ATS | Layout | IDs
    row_y = pdf.get_y()
    if ats:
        _info(LEFT_X, "ATS:", ats)
    if layout_str:
        pdf.set_xy(COL2_X, row_y)
        _info(COL2_X, "Layout:", layout_str)
    if ats or layout_str:
        pdf.ln(ROW_H)

    if listing_id or queue_id:
        id_parts = []
        if listing_id:
            id_parts.append(f"L:{listing_id[:8]}")
        if queue_id:
            id_parts.append(f"Q:{queue_id[:8]}")
        pdf.set_font("Helvetica", "B", 7)
        pdf.set_text_color(*_GRAY)
        pdf.cell(LBL_W, ROW_H, "IDs:", new_x="RIGHT")
        pdf.set_font("Helvetica", "", 7)
        pdf.set_text_color(*_DARK)
        pdf.cell(0, ROW_H, " | ".join(id_parts), new_x="LMARGIN", new_y="NEXT")

    pdf.ln(2)

    # ── Overall Verdict Banner ───────────────────────────────────
    pdf.verdict_banner(verdict)

    # ── Section 1: ATS Keyword Coverage ──────────────────────────
    pdf.section_title("1.  ATS Keyword Coverage")

    dp = coverage_result.get("coverage_report", {}).get("basic_keyword_double_presence", [])
    if dp:
        cols = [("Keyword", 42), ("In Skills", 22), ("In Bullet", 22), ("Status", 22)]
        pdf.table_header(cols)
        for k in dp:
            in_s = "YES" if k.get("in_skills") else "NO"
            in_b = "YES" if k.get("in_bullet") else "NO"
            status = k.get("status", "?")
            pdf.table_row([(k.get("keyword", ""), 42), (in_s, 22), (in_b, 22), (status, 22)], status_col=3)
        pdf.ln(1)

    total_kw = len(dp)
    passed_kw = sum(1 for k in dp if k.get("status", "").upper() == "PASS")
    pdf.kv_row("ATS Keyword Score", f"{passed_kw}/{total_kw} keywords pass double-presence",
               "PASS" if passed_kw == total_kw else "FAIL")
    pdf.ln(2)

    # ── Section 2: Requirement Coverage ──────────────────────────
    pdf.section_title("2.  Requirement Coverage")

    req_cov = coverage_result.get("coverage_report", {}).get("requirement_coverage", [])
    if req_cov:
        cols = [("#", 7), ("Requirement", 68), ("Type", 20), ("Status", 16), ("Coverage", 48)]
        pdf.table_header(cols)
        for r in req_cov:
            pdf.table_row([
                (str(r.get("req_id", "")), 7),
                (r.get("requirement", "")[:42], 68),
                (r.get("type", ""), 20),
                (r.get("status", ""), 16),
                (r.get("coverage", "")[:28], 48),
            ], status_col=3)
        pdf.ln(1)

    basic_total = sum(1 for r in req_cov if r.get("type") == "Basic")
    basic_covered = sum(1 for r in req_cov if r.get("type") == "Basic" and r.get("status", "").lower() == "covered")
    pdf.kv_row("Basic Quals", f"{basic_covered}/{basic_total} covered",
               "PASS" if basic_covered == basic_total else "FAIL")
    pdf.ln(2)

    # ── Section 3: Recruiter 6-Second Scan ───────────────────────
    pdf.section_title("3.  Recruiter 6-Second Scan  (Top 1/3 of Page)")

    re = coverage_result.get("recruiter_eval", {})

    tm = re.get("title_match", {})
    pdf.kv_row("Title Match", tm.get("detail", ""), tm.get("status", "?"))

    bq = re.get("basic_qual_top_third", {})
    pdf.kv_row("Basic Quals in Top 1/3",
               f"{bq.get('covered', 0)}/{bq.get('total', 0)} visible in scan zone",
               "PASS" if bq.get("covered", 0) == bq.get("total", 0) else "FAIL")
    for gap in bq.get("gaps", []):
        pdf.bullet_item(f"GAP: {gap}")

    pdf.ln(1)
    pdf.set_font("Helvetica", "B", 8)
    pdf.cell(0, 5, "Top 3 Rejection Risks:", new_x="LMARGIN", new_y="NEXT")
    for reason in re.get("top_3_reject_reasons", []):
        pdf.bullet_item(reason)
    pdf.ln(2)

    # ── Section 4: Hiring Manager Deep Read ──────────────────────
    pdf.section_title("4.  Hiring Manager Deep Read")

    hm = coverage_result.get("hm_eval", {})

    pdf.set_font("Helvetica", "B", 8)
    pdf.cell(0, 5, "Metric Plausibility:", new_x="LMARGIN", new_y="NEXT")
    for m in hm.get("metric_plausibility", []):
        bullet_text = m.get("bullet", "")[:45]
        note = m.get("note", "")
        status = m.get("status", "PASS")
        pdf.kv_row(f"  {bullet_text}...", note, status)

    ss = hm.get("scope_seniority", {})
    pdf.kv_row("Scope-Seniority Match", ss.get("detail", ""), ss.get("status", "?"))

    td = hm.get("technical_depth", {})
    pdf.kv_row("Technical Depth", td.get("detail", ""), td.get("status", "?"))

    pdf.ln(1)
    pdf.set_font("Helvetica", "B", 8)
    pdf.cell(0, 5, "Day-1 Readiness:", new_x="LMARGIN", new_y="NEXT")
    for d in hm.get("day1_readiness", []):
        resp = d.get("responsibility", "")[:35]
        proof = d.get("proof_bullet", "N/A")[:35]
        status = d.get("status", "gap")
        s = "PASS" if status.lower() in ("covered", "pass") else "FAIL"
        pdf.kv_row(f"  {resp}", f"Proof: {proof}", s)
    pdf.ln(2)

    # ── Section 5: Critical Fixes (if any) ───────────────────────
    fixes = coverage_result.get("critical_fixes", [])
    if fixes:
        pdf.section_title("5.  Required Fixes Before Submission")
        for i, fix in enumerate(fixes, 1):
            pdf.set_font("Helvetica", "B", 8)
            pdf.set_text_color(*_RED)
            pdf.cell(0, 5, f"  Fix #{i}: {fix.get('issue', '')}", new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(*_DARK)
            pdf.set_font("Helvetica", "", 8)
            pdf.cell(0, 5, f"    Action: {fix.get('fix', '')}  |  Target: {fix.get('target_step', '')}", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

    # ── Section 5/6: Skills Coverage ─────────────────────────────
    skills_cov = coverage_result.get("coverage_report", {}).get("skills_coverage", [])
    if skills_cov:
        section_num = "6" if fixes else "5"
        pdf.section_title(f"{section_num}.  Skills Surface Coverage")
        cols = [("Skill", 38), ("Where It Appears", 95), ("Gap?", 18)]
        pdf.table_header(cols)
        for s in skills_cov:
            where = ", ".join(s.get("where", []))[:55]
            gap = "YES" if s.get("gap") else ""
            pdf.table_row([(s.get("skill", ""), 38), (where, 95), (gap, 18)],
                          status_col=2 if gap else None)

    pdf.output(output_path)
    return output_path
