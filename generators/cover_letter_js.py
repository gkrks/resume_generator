"""Generate the cover_letter_<company>.js script and run it."""

from datetime import date

TEMPLATE = '''\
#!/usr/bin/env node
const {{
  Document, Packer, Paragraph, TextRun, AlignmentType,
}} = require("docx");
const PDFDocument = require("pdfkit");
const fs = require("fs");
const path = require("path");

const OUT_DIR = {out_dir_json};
const BASENAME = {basename_json};
const DOCX_PATH = path.join(OUT_DIR, BASENAME + ".docx");
const PDF_PATH = path.join(OUT_DIR, BASENAME + ".pdf");

const NAME = "Krithik Sai Sreenish Gopinath";
const LOCATION = "Mountain View, CA";
const PHONE = "8576939815";
const EMAIL = "krithiksaisreenishgopinath@gmail.com";
const LINKEDIN = "https://www.linkedin.com/in/krithiksai";
const WEBSITE = "https://krithik.xyz";

const DATE = {date_json};
const COMPANY = {company_json};
const ROLE = {role_json};

const PARA1 = {para1_json};
const PARA2 = {para2_json};

const PAGE_WIDTH = 12240;
const PAGE_HEIGHT = 15840;
const MARGIN = 1440;
const BODY_SIZE = 22;
const LINE_SPACING = 276;
const PDF_MARGIN = 72;
const PDF_PAGE_W = 612;
const PDF_USABLE_W = PDF_PAGE_W - 2 * PDF_MARGIN;

function buildDocx() {{
  const paragraphs = [];
  paragraphs.push(new Paragraph({{
    spacing: {{ after: 40, line: LINE_SPACING, lineRule: "auto" }},
    children: [new TextRun({{ text: NAME, bold: true, font: "Calibri", size: 28 }})],
  }}));
  paragraphs.push(new Paragraph({{
    spacing: {{ after: 20, line: LINE_SPACING, lineRule: "auto" }},
    children: [new TextRun({{ text: `${{LOCATION}} | ${{PHONE}} | ${{EMAIL}}`, font: "Calibri", size: 20 }})],
  }}));
  paragraphs.push(new Paragraph({{
    spacing: {{ after: 200, line: LINE_SPACING, lineRule: "auto" }},
    children: [new TextRun({{ text: `${{LINKEDIN}} | ${{WEBSITE}}`, font: "Calibri", size: 20 }})],
  }}));
  paragraphs.push(new Paragraph({{
    spacing: {{ after: 200, line: LINE_SPACING, lineRule: "auto" }},
    children: [new TextRun({{ text: DATE, font: "Calibri", size: BODY_SIZE }})],
  }}));
  paragraphs.push(new Paragraph({{
    spacing: {{ after: 40, line: LINE_SPACING, lineRule: "auto" }},
    children: [new TextRun({{ text: `Dear ${{COMPANY}} Hiring Team,`, font: "Calibri", size: BODY_SIZE }})],
  }}));
  paragraphs.push(new Paragraph({{
    spacing: {{ after: 200, line: LINE_SPACING, lineRule: "auto" }},
    children: [new TextRun({{ text: PARA1, font: "Calibri", size: BODY_SIZE }})],
  }}));
  paragraphs.push(new Paragraph({{
    spacing: {{ after: 200, line: LINE_SPACING, lineRule: "auto" }},
    children: [new TextRun({{ text: PARA2, font: "Calibri", size: BODY_SIZE }})],
  }}));
  paragraphs.push(new Paragraph({{
    spacing: {{ after: 40, line: LINE_SPACING, lineRule: "auto" }},
    children: [new TextRun({{ text: "Best,", font: "Calibri", size: BODY_SIZE }})],
  }}));
  paragraphs.push(new Paragraph({{
    spacing: {{ after: 0, line: LINE_SPACING, lineRule: "auto" }},
    children: [new TextRun({{ text: NAME, font: "Calibri", size: BODY_SIZE }})],
  }}));
  return new Document({{
    styles: {{ default: {{ document: {{ run: {{ font: "Calibri", size: BODY_SIZE }} }} }} }},
    sections: [{{
      properties: {{
        page: {{
          size: {{ width: PAGE_WIDTH, height: PAGE_HEIGHT }},
          margin: {{ top: MARGIN, right: MARGIN, bottom: MARGIN, left: MARGIN }},
        }},
      }},
      children: paragraphs,
    }}],
  }});
}}

function buildPdf() {{
  const doc = new PDFDocument({{
    size: "LETTER",
    margins: {{ top: PDF_MARGIN, bottom: PDF_MARGIN, left: PDF_MARGIN, right: PDF_MARGIN }},
  }});
  const stream = fs.createWriteStream(PDF_PATH);
  doc.pipe(stream);
  const FONT = "Helvetica";
  const FONT_BOLD = "Helvetica-Bold";
  const leftX = PDF_MARGIN;
  let y = PDF_MARGIN;

  doc.font(FONT_BOLD).fontSize(14);
  doc.text(NAME, leftX, y);
  y += doc.heightOfString(NAME) + 4;
  doc.font(FONT).fontSize(10);
  const contactLine = `${{LOCATION}} | ${{PHONE}} | ${{EMAIL}}`;
  doc.text(contactLine, leftX, y);
  y += doc.heightOfString(contactLine) + 2;
  const linksLine = `${{LINKEDIN}} | ${{WEBSITE}}`;
  doc.text(linksLine, leftX, y);
  y += doc.heightOfString(linksLine) + 20;
  doc.font(FONT).fontSize(11);
  doc.text(DATE, leftX, y);
  y += doc.heightOfString(DATE) + 20;
  doc.text(`Dear ${{COMPANY}} Hiring Team,`, leftX, y);
  y += doc.heightOfString(`Dear ${{COMPANY}} Hiring Team,`) + 10;
  doc.text(PARA1, leftX, y, {{ width: PDF_USABLE_W }});
  y += doc.heightOfString(PARA1, {{ width: PDF_USABLE_W }}) + 14;
  doc.text(PARA2, leftX, y, {{ width: PDF_USABLE_W }});
  y += doc.heightOfString(PARA2, {{ width: PDF_USABLE_W }}) + 20;
  doc.text("Best,", leftX, y);
  y += doc.heightOfString("Best,") + 4;
  doc.text(NAME, leftX, y);
  doc.end();
  return new Promise((resolve) => {{ stream.on("finish", () => resolve()); }});
}}

async function main() {{
  if (!fs.existsSync(OUT_DIR)) fs.mkdirSync(OUT_DIR, {{ recursive: true }});
  const docxDoc = buildDocx();
  const buffer = await Packer.toBuffer(docxDoc);
  fs.writeFileSync(DOCX_PATH, buffer);
  console.log("Wrote " + DOCX_PATH);
  await buildPdf();
  console.log("Wrote " + PDF_PATH);
}}
main().catch(err => {{ console.error("FATAL:", err); process.exit(1); }});
'''


def generate_cover_letter_js(
    company: str,
    role: str,
    para1: str,
    para2: str,
    output_dir: str,
) -> str:
    """Generate the cover_letter JS file content."""
    import json

    today = date.today()
    date_str = today.strftime("%B %d, %Y").replace(" 0", " ")

    basename = f"Cover_Letter_Krithik_Gopinath_{company}"

    js_content = TEMPLATE.format(
        out_dir_json=json.dumps(output_dir),
        basename_json=json.dumps(basename),
        date_json=json.dumps(date_str),
        company_json=json.dumps(company),
        role_json=json.dumps(role),
        para1_json=json.dumps(para1),
        para2_json=json.dumps(para2),
    )

    return js_content
