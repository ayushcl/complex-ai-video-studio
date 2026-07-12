"""Generate the 'New Features — Test Plan' PDF for the VEO Ad Pipeline UI update.

Standalone reportlab build. Run: python ui/build_feature_pdf.py
Output: VEO_UI_New_Features_Test_Plan.pdf at the repo root.
"""

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT = REPO_ROOT / "VEO_UI_New_Features_Test_Plan.pdf"

# Neon-vice palette, toned for print legibility on white.
INK = colors.HexColor("#0f1830")
CYAN = colors.HexColor("#0072a3")
MAGENTA = colors.HexColor("#b3175f")
VIOLET = colors.HexColor("#5b3fb0")
MUTE = colors.HexColor("#5a6477")
RULE = colors.HexColor("#c9d3e0")
HEADBG = colors.HexColor("#13203f")
ZEBRA = colors.HexColor("#eef3fa")
OKBG = colors.HexColor("#e7f7ef")
WARNBG = colors.HexColor("#fdf2e2")

styles = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=styles["Title"], textColor=INK, fontSize=22, spaceAfter=2, leading=26)
SUB = ParagraphStyle("SUB", parent=styles["Normal"], textColor=MAGENTA, fontSize=11, spaceAfter=10, leading=14)
H2 = ParagraphStyle("H2", parent=styles["Heading2"], textColor=CYAN, fontSize=13.5, spaceBefore=14, spaceAfter=4, leading=16)
BODY = ParagraphStyle("BODY", parent=styles["Normal"], textColor=INK, fontSize=9.7, leading=13.5, spaceAfter=4)
SMALL = ParagraphStyle("SMALL", parent=styles["Normal"], textColor=MUTE, fontSize=8.3, leading=11)
CELL = ParagraphStyle("CELL", parent=styles["Normal"], textColor=INK, fontSize=8.7, leading=11.5)
CELLH = ParagraphStyle("CELLH", parent=CELL, textColor=colors.white, fontName="Helvetica-Bold", fontSize=8.7)
MONO = ParagraphStyle("MONO", parent=styles["Code"], textColor=INK, fontSize=8.5, leading=12, backColor=colors.HexColor("#f1f4fa"),
                      borderPadding=5, spaceAfter=6, spaceBefore=2)
TAG = ParagraphStyle("TAG", parent=BODY, fontSize=8.3, leading=11)


def tag(text, color):
    return f'<font color="#{color.hexval()[2:]}"><b>{text}</b></font>'


FREE = tag("FREE", CYAN)
PAID = tag("PAID", MAGENTA)


def feature_table(rows):
    """rows: list of (id, feature, how_to_test, expected). Adds a Result column."""
    data = [[
        Paragraph("#", CELLH), Paragraph("Feature", CELLH),
        Paragraph("How to test", CELLH), Paragraph("Expected result", CELLH),
        Paragraph("Pass / Fail", CELLH),
    ]]
    for r in rows:
        data.append([
            Paragraph(r[0], CELL), Paragraph(r[1], CELL),
            Paragraph(r[2], CELL), Paragraph(r[3], CELL), Paragraph("", CELL),
        ])
    table = Table(data, colWidths=[8 * mm, 33 * mm, 56 * mm, 50 * mm, 23 * mm], repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), HEADBG),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, RULE),
        ("LINEAFTER", (0, 0), (-2, -1), 0.4, RULE),
        ("BOX", (0, 0), (-1, -1), 0.6, RULE),
    ]
    for i in range(1, len(data)):
        if i % 2 == 0:
            style.append(("BACKGROUND", (0, i), (-1, i), ZEBRA))
    return Table(data, colWidths=[8 * mm, 33 * mm, 56 * mm, 50 * mm, 23 * mm], repeatRows=1,
                 style=TableStyle(style))


def callout(title, body, bg, edge):
    inner = [Paragraph(f"<b>{title}</b>", BODY), Paragraph(body, BODY)]
    t = Table([[inner]], colWidths=[170 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg),
        ("LINEBEFORE", (0, 0), (0, -1), 2.5, edge),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
    ]))
    return t


def header_footer(canvas, doc):
    canvas.saveState()
    # top accent bar: violet base with a cyan half-overlay (the brand gradient)
    canvas.setFillColor(VIOLET)
    canvas.rect(0, A4[1] - 6 * mm, A4[0], 6 * mm, fill=1, stroke=0)
    canvas.setFillColor(CYAN)
    canvas.rect(0, A4[1] - 6 * mm, A4[0] * 0.5, 6 * mm, fill=1, stroke=0)
    # footer
    canvas.setFillColor(MUTE)
    canvas.setFont("Helvetica", 7.5)
    canvas.drawString(18 * mm, 10 * mm, "VEO Ad Pipeline — New Features Test Plan")
    canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Page {doc.page}")
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.4)
    canvas.line(18 * mm, 13 * mm, A4[0] - 18 * mm, 13 * mm)
    canvas.restoreState()


def build():
    doc = BaseDocTemplate(
        str(OUTPUT), pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm, topMargin=20 * mm, bottomMargin=16 * mm,
        title="VEO Ad Pipeline — New Features Test Plan", author="VEO Ad Pipeline UI",
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="main")
    doc.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=header_footer)])

    s = []
    s.append(Paragraph("VEO Ad Pipeline", H1))
    s.append(Paragraph("New Features &mdash; Engineer Test Plan", SUB))
    s.append(HRFlowable(width="100%", thickness=1, color=RULE, spaceAfter=8))
    s.append(Paragraph(
        "This release adds a guided <b>Simple mode</b> (document &rarr; draft video &rarr; high-quality video), "
        "in-app API-key management, and capability-aware degradation, while preserving the existing "
        "wizard behind an <b>Administrator</b> toggle. Branch: <b>feature/matt-ui</b>. "
        "Use the checklist below to verify each feature; mark Pass/Fail in the right-hand column.", BODY))

    s.append(Paragraph("Getting started", H2))
    s.append(Paragraph("From the repository root, start the server (no install needed for the free paths):", BODY))
    s.append(Paragraph("python ui/server.py", MONO))
    s.append(Paragraph("Then open <b>http://127.0.0.1:8765</b>. Run the automated suite with:", BODY))
    s.append(Paragraph("python -m unittest discover -s ui/tests", MONO))

    s.append(callout(
        "Free vs paid — read before testing",
        f'Actions tagged {FREE} (building jobs, document parsing, dry-run previews, the full engine plan) cost nothing. '
        f'Actions tagged {PAID} call real APIs and spend money; every one requires typing the word '
        f'<b>SPEND</b> in a confirmation dialog and passes a full server-side gate sequence. '
        "You can verify the entire flow up to the SPEND dialog without spending anything &mdash; cancel there.",
        WARNBG, MAGENTA))

    s.append(callout(
        "What the paid stages need (Administrator &rarr; Settings)",
        "The app runs with no API keys. To exercise a real generation you need: a <b>Gemini</b> key, "
        "<b>ffmpeg</b> on PATH, and a one-time <font face='Courier'>pip install requests python-dotenv google-genai</font>. "
        "An <b>ElevenLabs</b> key is only for voice (presenter) jobs and is never required by Simple mode. "
        "The header chips show what is currently missing.",
        OKBG, CYAN))

    # ---- Simple mode ----
    s.append(Paragraph("1 &nbsp; Simple mode (the new default page)", H2))
    s.append(feature_table([
        ("1.1", "Document paste", "Paste scene text using <font face='Courier'>Scene 1:</font> / <font face='Courier'>Scene 2:</font> markers; click <b>Build the job</b> " + FREE + ".",
         "Review section appears: correct scene count, prompts, estimated length; &ldquo;Job is valid&rdquo;. Nothing spent."),
        ("1.2", "Document upload", "Click <b>Upload document</b>; choose a .txt, .md, .docx or .pdf file; Build.",
         "File name shows with a remove button; the textarea disables; Build extracts the text and produces scenes."),
        ("1.3", "Five formats", "Repeat 1.2 once per format: .txt, .md, .json, .docx, .pdf.",
         "Each extracts readable text. Image-only PDFs report a clear &ldquo;paste text instead&rdquo; message (not a crash)."),
        ("1.4", "AI extraction", "With a Gemini key set, build from a loosely-written brief (no explicit Scene markers).",
         "&ldquo;built with: AI extraction (Gemini)&rdquo;; scenes are coherent prompts derived from the brief."),
        ("1.5", "No-AI fallback", "With no Gemini key (or AI extraction off in Settings), build the same brief.",
         "&ldquo;built with: basic parser&rdquo; plus a warning; the app still produces a usable job."),
        ("1.6", "Paste JSON artifact", "Paste a raw scenes JSON array/object; Build.",
         "&ldquo;built with: JSON artifact (used as-is)&rdquo;; scene count matches the JSON."),
        ("1.7", "Seed image (auto)", "Build any job without supplying a seed image.",
         "Warning notes a generated placeholder seeds scene 1; &ldquo;View seed image&rdquo; shows a gradient."),
        ("1.8", "Seed image (real)", "Set a seed image path (Browse) to an in-repo .png/.jpg; Build.",
         "No placeholder warning; the chosen image is used as the seed."),
        ("1.9", "Spend cap", "In Review, change &ldquo;Scenes to generate&rdquo; before generating.",
         "The draft confirmation reflects the chosen number of paid scenes."),
        ("1.10", "Recent jobs", "Build a job, then click its chip under &ldquo;Recent&rdquo;.",
         "Job reopens with a freshly re-validated status (delete an artifact on disk &rarr; it shows invalid)."),
    ]))

    s.append(Paragraph("2 &nbsp; Draft &amp; high-quality generation " + PAID, H2))
    s.append(feature_table([
        ("2.1", "Draft preview", "After a valid build, click <b>Generate draft preview</b> " + PAID + "; type SPEND; confirm.",
         "Per-stage progress (video &rarr; music &rarr; assemble); the draft video plays in-app on success."),
        ("2.2", "SPEND gate", "Click <b>Generate draft preview</b> but type the wrong word, or Cancel.",
         "Confirm button stays disabled until exactly &ldquo;SPEND&rdquo;; cancelling spends nothing and shows no error."),
        ("2.3", "Validation-first", "Build a job, delete its storyboard.json on disk, then try to generate.",
         "&ldquo;Validation failed &mdash; nothing was spent&rdquo;; no API call is made."),
        ("2.4", "HQ locked until draft", "Before any draft succeeds, look at <b>Generate high quality</b>.",
         "Button is disabled with a &ldquo;Generate a draft first&rdquo; tooltip."),
        ("2.5", "HQ pass", "After a successful draft, click <b>Generate high quality</b> " + PAID + "; confirm.",
         "Runs the same prompts with the HQ model/resolution; both draft and final videos remain visible."),
        ("2.6", "Truthful status / failures", "Trigger or observe a failed run (e.g. missing ffmpeg).",
         "Failure report and stderr are shown verbatim; a music safe-fallback prompt shows a review warning."),
    ]))

    s.append(Paragraph("3 &nbsp; Administrator console", H2))
    s.append(feature_table([
        ("3.1", "Mode toggle", "Click <b>Administrator</b> in the header; then <b>&larr; Simple mode</b>.",
         "Switches between Simple and the full wizard; header chips and admin buttons change accordingly."),
        ("3.2", "Wizard intact", "In Admin, walk Job &rarr; Voice &rarr; Preview &rarr; Launch.",
         "All prior behaviour works: conditional fields, voice-pick gating, dry-run, spend gates, run history."),
    ]))

    s.append(Paragraph("4 &nbsp; Settings &amp; API keys (Administrator &rarr; Settings)", H2))
    s.append(feature_table([
        ("4.1", "Add a key", "Open Settings; paste a value into Gemini or ElevenLabs; click <b>Save</b>.",
         "Chip flips to &ldquo;configured&rdquo;. The value is never displayed back anywhere."),
        ("4.2", "Write-only secrecy", "After saving, inspect the page / network responses for the value.",
         "The key value appears in no response, no chip, and no log &mdash; only presence booleans."),
        ("4.3", "Clear a key", "Click <b>Clear</b> next to a configured key.",
         "Chip flips to &ldquo;not set&rdquo;; the entry is removed from the server&rsquo;s .env."),
        ("4.4", "Configurable models", "Change the draft / HQ model or resolution; Save settings.",
         "Subsequent generations use the new model/resolution (visible in the SPEND dialog)."),
        ("4.5", "Dependency readout", "Read the &ldquo;Engine python packages&rdquo; row.",
         "Shows which of requests / python-dotenv / google-genai are installed."),
    ]))

    s.append(Paragraph("5 &nbsp; Runs-without-keys &amp; capability awareness", H2))
    s.append(feature_table([
        ("5.1", "Runs with zero keys", "With no keys configured, build a job and run a dry-run.",
         "Building and dry-runs work; the app never hard-fails for lack of keys."),
        ("5.2", "Capability chips", "Read the header chips in Simple mode.",
         "Chips state what each paid stage needs (e.g. &ldquo;Video: add Gemini API key&hellip;&rdquo;) rather than bare ticks."),
        ("5.3", "Voice is optional", "With no ElevenLabs key, use Simple mode end to end.",
         "Voice chip says &ldquo;not needed here&rdquo;; nothing about Simple mode is blocked."),
    ]))

    s.append(Paragraph("6 &nbsp; Visual / UX", H2))
    s.append(feature_table([
        ("6.1", "Subtler motion", "Move the mouse across the background in both modes.",
         "Fluid effect is gentle and dim (not bright/intense); pauses when the tab is hidden."),
        ("6.2", "Larger main panel", "Compare Simple mode text size to the Administrator console.",
         "Simple mode uses noticeably larger type; the admin console stays compact."),
        ("6.3", "Reduced motion", "Enable the OS &ldquo;reduce motion&rdquo; setting and reload.",
         "The fluid background is disabled; the UI is fully usable."),
    ]))

    s.append(Paragraph("7 &nbsp; Robustness (hardening fixes to confirm)", H2))
    s.append(feature_table([
        ("7.1", "Malformed PDF", "Upload an image-only or odd PDF; Build.",
         "Clear &ldquo;could not extract / paste text instead&rdquo; message &mdash; no crash, no hang."),
        ("7.2", "Oversized document", "Upload a document over 20 MB.",
         "Rejected cleanly with a size-cap message."),
        ("7.3", "Wrong file type", "Try to upload a .exe or image as the document.",
         "Rejected: &ldquo;Unsupported file type&hellip;&rdquo;."),
        ("7.4", "Automated suite", "Run <font face='Courier'>python -m unittest discover -s ui/tests</font>.",
         "All tests pass (67 at time of writing), covering parsing, gates, and key handling."),
    ]))

    s.append(Spacer(1, 10))
    s.append(HRFlowable(width="100%", thickness=0.6, color=RULE, spaceAfter=6))
    s.append(Paragraph(
        "Notes: Simple mode produces silent brand videos (music is the soundtrack &mdash; no voiceover). "
        "The assembled output always carries the generated music; the audio-free intermediate is "
        "<font face='Courier'>video/final_silent.mp4</font> in the run directory. All operator-supplied paths are "
        "constrained to the repository root. Runtime data (jobs, uploads, settings, run ledger, audit log) lives "
        "under <font face='Courier'>ui/data/</font> and is gitignored.", SMALL))

    doc.build(s)
    print(f"Wrote {OUTPUT} ({OUTPUT.stat().st_size} bytes)")


if __name__ == "__main__":
    build()
