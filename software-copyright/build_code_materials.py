"""
Rebuild source code materials for 软著 submission.
Generates two .docx files:
  - 前30页 (backend-first): backend core, API entry, services, security
  - 后30页 (frontend): views, stores, rule engine, API clients, a11y

Requirements (from docs/23 §4.3):
  - Consolas 10pt, monochrome
  - A4 portrait, margins: top/bottom 2cm, left/right 2.5cm
  - Line numbers on left
  - ~48 lines per page
  - Header: software name + copyright holder + page X/N
  - Footer: file path + line range
"""
import os
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

BASE = r"D:\DC\DC-AIino"
SOFTWARE_NAME = "极端气候下粮食生产风险核心因子识别与韧性提升可视化决策系统"
COPYRIGHT_HOLDER = "潘妙齐"
LINES_PER_PAGE = 48
FONT_NAME = 'Consolas'
FONT_SIZE = 10

# Format: (path, description, start_line, end_line) — None = full file
FRONT_30_FILES = [
    ("backend/app.py", "Flask application factory, blueprint registration, CORS, limiter, security headers", None, None),
    ("backend/api/__init__.py", "API blueprint initialization", None, None),
    ("backend/api/predict.py", "Core prediction endpoint: 3-model inference, SHAP top-2, resilience recommendations", None, None),
    ("backend/services/inference.py", "ML inference service: 3-model lazy load, single/batch inference, preprocessing", None, None),
    ("backend/services/panel_repo.py", "Data access layer: Repository Pattern, SQLite+parquet dual storage (excerpt)", 1, 80),
    ("backend/security_headers.py", "HTTP security headers: CSP, HSTS, XFO, X-Content-Type-Options", None, None),
    ("backend/limiter.py", "IP-level rate limiting: 100 req/min via Flask-Limiter", None, None),
]

BACK_30_FILES = [
    ("frontend/src/main.ts", "Application entry point: Vue 3 app creation and mount", None, None),
    ("frontend/src/App.vue", "Root layout component: top navigation bar (M00-M05), global page frame (excerpt)", 1, 120),
    ("frontend/src/router/index.ts", "Vue Router configuration: 6 functional module routes", None, None),
    ("frontend/src/stores/useProvinceStore.ts", "Pinia state store: shared province selection, history cache (excerpt)", 1, 90),
    ("frontend/src/data/recommendation.ts", "Resilience rule engine: 11 rules + buildPathway synthesis (excerpt)", 1, 170),
    ("frontend/src/data/a11y.ts", "WCAG 2.2 AA accessibility configuration", None, None),
    ("frontend/src/api/http.ts", "Axios HTTP client base: baseURL, timeout, request/response interceptors", None, None),
    ("frontend/src/api/health.ts", "Backend health check API client", None, None),
    ("frontend/src/api/predict.ts", "Prediction API client: single/batch/3-model comparison", None, None),
    ("frontend/src/api/province.ts", "Province panel data API client: list, history, risk scores", None, None),
    ("frontend/src/api/shap.ts", "SHAP attribution API client: feature contribution data", None, None),
    ("frontend/src/api/admin.ts", "Admin/monitoring API client: inference log polling", None, None),
    ("frontend/src/views/Overview.vue", "M00 System Overview: KPI cards, 3-protocol R2, dual-perspective Top3 (excerpt)", 1, 110),
    ("frontend/src/views/RiskMap.vue", "M01 Risk Spatiotemporal Map: ECharts GeoJSON, year slider, province detail (excerpt)", 1, 110),
    ("frontend/src/views/ShapDashboard.vue", "M02 SHAP Attribution Dashboard: 11-dim horizontal bars, 4-view tabs (excerpt)", 1, 110),
    ("frontend/src/views/ScenarioSim.vue", "M03 Scenario Simulation: 5-param sliders, real-time estimation (excerpt)", 1, 110),
    ("frontend/src/views/ResiliencePath.vue", "M04 Resilience Pathway: 3-phase action cards, deviation (excerpt)", 1, 110),
    ("frontend/src/views/InferenceTrace.vue", "M05 Inference Monitor: 3s polling, ring buffer, expandable detail (excerpt)", 1, 110),
]

def read_file_lines(filepath, start_line=None, end_line=None):
    """Read file, return list of (line_number, line_text). Optionally restrict to line range."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            raw = f.readlines()
    except UnicodeDecodeError:
        with open(filepath, 'r', encoding='gbk') as f:
            raw = f.readlines()

    if start_line is not None:
        raw = raw[start_line - 1:]  # start_line is 1-indexed
    if end_line is not None:
        raw = raw[:end_line - (start_line or 1) + 1]

    start_lineno = start_line or 1
    result = []
    for i, line in enumerate(raw, start_lineno):
        stripped = line.rstrip('\n\r')
        result.append((i, stripped if stripped.strip() else ''))
    return result

def build_code_docx(file_list, output_path, part_label):
    """Build a .docx with source code, properly paginated."""
    doc = Document()

    section = doc.sections[0]
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(2.0)
    section.bottom_margin = Cm(2.0)
    section.left_margin = Cm(2.5)
    section.right_margin = Cm(2.5)

    style = doc.styles['Normal']
    style.font.name = FONT_NAME
    style.font.size = Pt(FONT_SIZE)
    style.paragraph_format.space_after = Pt(0)
    style.paragraph_format.space_before = Pt(0)
    style.paragraph_format.line_spacing = 1.0

    all_pages = []
    current_page_lines = []
    current_page_line_count = 0

    for rel_path, description, start_line, end_line in file_list:
        full_path = os.path.join(BASE, rel_path)
        if not os.path.exists(full_path):
            print(f"  WARNING: File not found: {full_path}")
            continue

        file_lines = read_file_lines(full_path, start_line, end_line)

        range_info = ""
        if start_line and end_line:
            range_info = f" (lines {start_line}-{end_line})"
        elif start_line:
            range_info = f" (from line {start_line})"

        file_header = f"// File: {rel_path}{range_info}"
        file_desc = f"// {description}"
        file_sep = f"// {'-' * 70}"

        for header_line in [file_sep, file_header, file_desc, file_sep, '']:
            if current_page_line_count >= LINES_PER_PAGE:
                all_pages.append(list(current_page_lines))
                current_page_lines = []
                current_page_line_count = 0
            current_page_lines.append((header_line, None))
            current_page_line_count += 1

        for orig_lineno, text in file_lines:
            if current_page_line_count >= LINES_PER_PAGE:
                all_pages.append(list(current_page_lines))
                current_page_lines = []
                current_page_line_count = 0

            if len(text) > 120:
                text = text[:117] + '...'

            display = f"{orig_lineno:4d}  {text}"
            source_info = f"{rel_path} 第{orig_lineno}行"
            current_page_lines.append((display, source_info))
            current_page_line_count += 1

    if current_page_lines:
        all_pages.append(list(current_page_lines))

    total_pages = len(all_pages)
    print(f"  Pages: {total_pages}")

    for page_idx, page_lines in enumerate(all_pages):
        page_num = page_idx + 1

        if page_idx > 0:
            doc.add_section()
            new_section = doc.sections[-1]
            new_section.page_width = Cm(21.0)
            new_section.page_height = Cm(29.7)
            new_section.top_margin = Cm(2.0)
            new_section.bottom_margin = Cm(2.0)
            new_section.left_margin = Cm(2.5)
            new_section.right_margin = Cm(2.5)

        current_section = doc.sections[-1]
        header = current_section.header
        header.is_linked_to_previous = False
        hp = header.paragraphs[0] if header.paragraphs else header.add_paragraph()
        hp.clear()
        hp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        hr = hp.add_run(
            f"{SOFTWARE_NAME} V1.0 — 第一著作权人:{COPYRIGHT_HOLDER} — "
            f"源代码材料({part_label}) — 第 {page_num} 页 / 共 {total_pages} 页"
        )
        hr.font.size = Pt(7)
        hr.font.name = 'SimSun'
        hr.font.color.rgb = RGBColor(80, 80, 80)

        footer = current_section.footer
        footer.is_linked_to_previous = False
        fp = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
        fp.clear()
        fp.alignment = WD_ALIGN_PARAGRAPH.LEFT
        first_source = page_lines[0][1] if page_lines and page_lines[0][1] else "-"
        fr = fp.add_run(first_source)
        fr.font.size = Pt(6.5)
        fr.font.name = 'SimSun'
        fr.font.color.rgb = RGBColor(100, 100, 100)

        for display_text, source_info in page_lines:
            p = doc.add_paragraph()
            p.paragraph_format.space_after = Pt(0)
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.line_spacing = 1.0
            run = p.add_run(display_text)
            run.font.name = FONT_NAME
            run.font.size = Pt(FONT_SIZE)
            run.font.color.rgb = RGBColor(0, 0, 0)

    doc.save(output_path)
    print(f"  Saved: {os.path.basename(output_path)} ({os.path.getsize(output_path)} bytes)")
    return total_pages

def main():
    out_dir = os.path.join(BASE, "software-copyright", "正式资料")
    os.makedirs(out_dir, exist_ok=True)

    print("=" * 60)
    print("Building 源代码材料(前30页) - Backend-first")
    print("=" * 60)
    for f, desc, sl, el in FRONT_30_FILES:
        full = os.path.join(BASE, f)
        exists = "OK" if os.path.exists(full) else "MISSING"
        print(f"  [{exists}] {f}")

    front_path = os.path.join(out_dir, f"{SOFTWARE_NAME}-代码(前30页).docx")
    front_pages = build_code_docx(FRONT_30_FILES, front_path, "前30页")

    print()
    print("=" * 60)
    print("Building 源代码材料(后30页) - Frontend core")
    print("=" * 60)
    for f, desc, sl, el in BACK_30_FILES:
        full = os.path.join(BASE, f)
        exists = "OK" if os.path.exists(full) else "MISSING"
        print(f"  [{exists}] {f}")

    back_path = os.path.join(out_dir, f"{SOFTWARE_NAME}-代码(后30页).docx")
    back_pages = build_code_docx(BACK_30_FILES, back_path, "后30页")

    print()
    print("=" * 60)
    print(f"SUMMARY: 前30页={front_pages}p, 后30页={back_pages}p, Total={front_pages+back_pages}p")
    print(f"         Files: {len(FRONT_30_FILES)} backend + {len(BACK_30_FILES)} frontend")
    print("=" * 60)

if __name__ == '__main__':
    main()
