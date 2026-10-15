from __future__ import annotations

import re
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, Preformatted, SimpleDocTemplate, Spacer


DOCS_DIR = Path(__file__).resolve().parent
INPUT_FILES = [
    DOCS_DIR / "Client-Installation-Manual.md",
    DOCS_DIR / "User-Manual.md",
]


def _normalize_inline(text: str) -> str:
    text = text.replace("\t", "    ")
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", text)
    text = text.replace("`", "")
    return escape(text)


def _build_story(markdown_text: str):
    styles = getSampleStyleSheet()
    body_style = ParagraphStyle(
        "Body",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10.5,
        leading=14,
        spaceAfter=4,
    )
    h1_style = ParagraphStyle(
        "H1",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=17,
        leading=22,
        textColor=colors.HexColor("#16325c"),
        spaceAfter=8,
    )
    h2_style = ParagraphStyle(
        "H2",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=13.5,
        leading=18,
        textColor=colors.HexColor("#1d4f91"),
        spaceBefore=6,
        spaceAfter=6,
    )
    h3_style = ParagraphStyle(
        "H3",
        parent=styles["Heading3"],
        fontName="Helvetica-Bold",
        fontSize=11.5,
        leading=15,
        textColor=colors.HexColor("#285d9b"),
        spaceBefore=4,
        spaceAfter=4,
    )
    bullet_style = ParagraphStyle(
        "Bullet",
        parent=body_style,
        leftIndent=14,
        firstLineIndent=-8,
        spaceAfter=2,
    )
    code_style = ParagraphStyle(
        "Code",
        fontName="Courier",
        fontSize=9,
        leading=12,
        backColor=colors.HexColor("#f4f7fb"),
        borderPadding=6,
    )

    lines = markdown_text.splitlines()
    story = []
    paragraph_buffer: list[str] = []
    in_code = False
    code_buffer: list[str] = []

    def flush_paragraph():
        nonlocal paragraph_buffer
        if paragraph_buffer:
            text = _normalize_inline(" ".join(x.strip() for x in paragraph_buffer))
            story.append(Paragraph(text, body_style))
            paragraph_buffer = []

    def flush_code():
        nonlocal code_buffer
        if code_buffer:
            story.append(Preformatted("\n".join(code_buffer), code_style))
            story.append(Spacer(1, 3))
            code_buffer = []

    for raw_line in lines:
        line = raw_line.rstrip("\n")
        stripped = line.strip()

        if stripped.startswith("```"):
            flush_paragraph()
            if in_code:
                flush_code()
                in_code = False
            else:
                in_code = True
            continue

        if in_code:
            code_buffer.append(line)
            continue

        if not stripped:
            flush_paragraph()
            story.append(Spacer(1, 4))
            continue

        if stripped in {"---", "***", "___"}:
            flush_paragraph()
            story.append(Spacer(1, 4))
            continue

        if stripped.startswith("# "):
            flush_paragraph()
            story.append(Paragraph(_normalize_inline(stripped[2:]), h1_style))
            continue
        if stripped.startswith("## "):
            flush_paragraph()
            story.append(Paragraph(_normalize_inline(stripped[3:]), h2_style))
            continue
        if stripped.startswith("### "):
            flush_paragraph()
            story.append(Paragraph(_normalize_inline(stripped[4:]), h3_style))
            continue

        if re.match(r"^[-*]\s+", stripped):
            flush_paragraph()
            bullet_text = re.sub(r"^[-*]\s+", "", stripped)
            story.append(Paragraph(f"• {_normalize_inline(bullet_text)}", bullet_style))
            continue

        if re.match(r"^\d+\.\s+", stripped):
            flush_paragraph()
            story.append(Paragraph(_normalize_inline(stripped), bullet_style))
            continue

        paragraph_buffer.append(stripped)

    flush_paragraph()
    if in_code:
        flush_code()

    return story


def generate_pdf(input_path: Path) -> Path:
    output_path = input_path.with_suffix(".pdf")
    content = input_path.read_text(encoding="utf-8")

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title=input_path.stem,
    )
    story = _build_story(content)
    doc.build(story)
    return output_path


def main():
    generated: list[Path] = []
    for md_file in INPUT_FILES:
        if not md_file.exists():
            raise FileNotFoundError(f"Manual file not found: {md_file}")
        generated.append(generate_pdf(md_file))

    print("Generated PDF manuals:")
    for pdf in generated:
        print(f" - {pdf}")


if __name__ == "__main__":
    main()
