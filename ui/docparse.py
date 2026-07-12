"""Document text extraction + heuristic scene parsing for simple mode.

Stdlib only, by design (the UI must run with zero pip installs):

  .txt / .md  - read as UTF-8 text (lenient decoding)
  .json       - pretty-printed back to text, or recognized directly as a
                scenes/storyboard artifact by the caller
  .docx       - a zip; text pulled from word/document.xml (w:t runs,
                paragraphs as newlines)
  .pdf        - best-effort: FlateDecode streams are inflated and text-showing
                operators (Tj / TJ / ') harvested. Works for simple text PDFs;
                fails loudly (not silently) on image-only or exotic encodings.

The heuristic scene splitter is the no-AI fallback: when no Gemini key is
configured, simple mode still works by splitting the document into scenes on
headings / "Scene N" markers / numbered lists / --- separators.
"""

from __future__ import annotations

import json
import re
import zipfile
import zlib
from io import BytesIO
from xml.etree import ElementTree

try:
    import negative_library as _negative_library
except Exception:
    _negative_library = None


class DocParseError(Exception):
    """Operator-facing extraction failure. Message is safe to show."""


TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".json"}
SUPPORTED_EXTENSIONS = TEXT_EXTENSIONS | {".docx", ".pdf"}
MAX_DOC_BYTES = 20 * 1024 * 1024
# Decompressed-output caps. The input cap above bounds the COMPRESSED bytes;
# DEFLATE allows ~1000:1, so a small upload can inflate to gigabytes. These cap
# what we actually materialize, defeating zip/flate bombs in docx and pdf.
MAX_DOCX_XML_BYTES = 64 * 1024 * 1024
MAX_PDF_INFLATED_BYTES = 48 * 1024 * 1024


# --------------------------------------------------------------------------- #
# Per-format extractors                                                        #
# --------------------------------------------------------------------------- #
def _decode_text(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def extract_docx(data: bytes) -> str:
    try:
        with zipfile.ZipFile(BytesIO(data)) as archive:
            try:
                info = archive.getinfo("word/document.xml")
            except KeyError as exc:
                raise DocParseError(f"Not a readable .docx file: {exc}")
            # Bounded read: stop decompression at the cap instead of trusting
            # the (attacker-controlled) declared size. Reading cap+1 lets us
            # detect overflow without ever materializing the full bomb.
            with archive.open(info) as member:
                xml_bytes = member.read(MAX_DOCX_XML_BYTES + 1)
            if len(xml_bytes) > MAX_DOCX_XML_BYTES:
                raise DocParseError("The .docx document body is too large to process.")
    except zipfile.BadZipFile as exc:
        raise DocParseError(f"Not a readable .docx file: {exc}")
    # Neutralize XML entity-expansion (billion-laughs) on older expat builds:
    # legitimate .docx bodies never carry a DOCTYPE/DTD.
    if b"<!DOCTYPE" in xml_bytes[:4096] or b"<!ENTITY" in xml_bytes[:4096]:
        raise DocParseError("The .docx contains a document-type declaration and was refused.")
    try:
        root = ElementTree.fromstring(xml_bytes)
    except ElementTree.ParseError as exc:
        raise DocParseError(f"Could not parse the .docx document XML: {exc}")

    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    paragraphs = []
    for paragraph in root.iter(f"{ns}p"):
        runs = [node.text or "" for node in paragraph.iter(f"{ns}t")]
        paragraphs.append("".join(runs))
    text = "\n".join(paragraphs).strip()
    if not text:
        raise DocParseError("The .docx contained no extractable text.")
    return text


_PDF_ESCAPES = {
    b"n": b"\n", b"r": b"\r", b"t": b"\t", b"b": b"\b", b"f": b"\f",
    b"(": b"(", b")": b")", b"\\": b"\\",
}


def _pdf_literal_string(raw: bytes) -> bytes:
    """Decode a PDF literal string body (the bytes between unescaped parens)."""
    out = bytearray()
    i = 0
    while i < len(raw):
        ch = raw[i:i + 1]
        if ch == b"\\" and i + 1 < len(raw):
            nxt = raw[i + 1:i + 2]
            if nxt in _PDF_ESCAPES:
                out += _PDF_ESCAPES[nxt]
                i += 2
                continue
            if nxt.isdigit():  # octal escape \ddd
                digits = raw[i + 1:i + 4]
                octal = b""
                for d in digits:
                    if 48 <= d <= 55:
                        octal += bytes([d])
                    else:
                        break
                if octal:
                    out.append(int(octal, 8) & 0xFF)
                    i += 1 + len(octal)
                    continue
            i += 2
            continue
        out += ch
        i += 1
    return bytes(out)


# Bounded quantifiers ({0,N} not *) keep matching LINEAR. Unbounded * here
# backtracks O(n^2) on adversarial input (many unclosed "\(" sequences) and,
# with no per-thread timeout on Windows, would pin a worker for hours. Real PDF
# strings are short, so truncating absurd ones is fine for best-effort text.
_PDF_STRING_RE = re.compile(rb"\((?:[^()\\]|\\.){0,8192}\)")
_PDF_TEXT_OP_RE = re.compile(
    rb"(\((?:[^()\\]|\\.){0,8192}\)|\[(?:[^\]\\]|\\.){0,8192}\])\s*(Tj|TJ|')"
)
_PDF_LINE_OP_RE = re.compile(rb"(?:T\*|Td|TD|TL)\b")


def extract_pdf(data: bytes) -> str:
    """Best-effort text from a PDF: inflate FlateDecode streams, harvest the
    text-showing operators. Raises DocParseError when nothing usable emerges."""
    if not data.startswith(b"%PDF"):
        raise DocParseError("Not a PDF file (missing %PDF header).")

    def _inflate_bounded(raw: bytes, remaining: int) -> bytes:
        """Inflate at most `remaining` bytes. Raises on a flate bomb instead
        of materializing gigabytes."""
        decompressor = zlib.decompressobj()
        out = decompressor.decompress(raw, remaining + 1)
        if len(out) > remaining or decompressor.unconsumed_tail:
            raise DocParseError(
                "This PDF expands to an unreasonable size when decompressed and was refused. "
                "Paste the text directly instead."
            )
        return out

    streams = []
    budget = MAX_PDF_INFLATED_BYTES
    for match in re.finditer(rb"stream\r?\n(.*?)endstream", data, re.DOTALL):
        raw = match.group(1)
        try:
            chunk = _inflate_bounded(raw, budget)
        except zlib.error:
            chunk = raw  # uncompressed content stream
        budget -= len(chunk)
        streams.append(chunk)
        if budget <= 0:
            raise DocParseError(
                "This PDF contains too much content to parse safely. Paste the text directly instead."
            )

    pieces = []
    for content in streams:
        if b"Tj" not in content and b"TJ" not in content and b"'" not in content:
            continue
        # Insert newlines roughly where the PDF moves the text cursor.
        for chunk in _PDF_LINE_OP_RE.split(content):
            line_parts = []
            for op_match in _PDF_TEXT_OP_RE.finditer(chunk):
                arg = op_match.group(1)
                if arg.startswith(b"("):
                    line_parts.append(_pdf_literal_string(arg[1:-1]))
                else:  # TJ array: harvest each literal string inside
                    for s in _PDF_STRING_RE.finditer(arg):
                        line_parts.append(_pdf_literal_string(s.group(0)[1:-1]))
            if line_parts:
                pieces.append(b"".join(line_parts))

    text = _decode_text(b"\n".join(pieces)).strip()
    if not text:
        raise DocParseError(
            "Could not extract text from this PDF (it may be image-only or use "
            "an exotic encoding). Paste the text directly instead."
        )
    # Sanity check: mostly printable, or the font encoding defeated us.
    printable = sum(1 for c in text if c.isprintable() or c in "\n\t")
    if printable / max(1, len(text)) < 0.7:
        raise DocParseError(
            "This PDF's text encoding could not be decoded reliably. "
            "Paste the text directly instead."
        )
    return text


def extract_text(data: bytes, extension: str) -> str:
    """Dispatch on extension. Returns plain text; raises DocParseError."""
    ext = extension.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise DocParseError(
            f"Unsupported format {ext!r}. Accepted: .txt, .md, .json, .docx, .pdf."
        )
    if len(data) > MAX_DOC_BYTES:
        raise DocParseError("Document is too large (20 MB cap).")
    if ext == ".docx":
        return extract_docx(data)
    if ext == ".pdf":
        return extract_pdf(data)
    text = _decode_text(data).strip()
    if not text:
        raise DocParseError("The document is empty.")
    return text


# --------------------------------------------------------------------------- #
# Heuristic scene splitting (the no-AI fallback)                               #
# --------------------------------------------------------------------------- #
_SCENE_MARKER_RE = re.compile(
    r"^\s*(?:#{1,4}\s*)?(?:scene|shot)\s*[#:\-]?\s*\d+\b.*$", re.IGNORECASE
)
_HEADING_RE = re.compile(r"^\s*#{1,4}\s+\S")
_NUMBERED_RE = re.compile(r"^\s*\d+[.)]\s+\S")
_SEPARATOR_RE = re.compile(r"^\s*(?:---+|\*\*\*+|===+)\s*$")


def _split_blocks(text: str, marker) -> list:
    blocks, current = [], []
    for line in text.splitlines():
        if marker(line) and current:
            blocks.append("\n".join(current).strip())
            current = [line]
        else:
            current.append(line)
    if current:
        blocks.append("\n".join(current).strip())
    return [b for b in blocks if b]


def split_scenes(text: str) -> list:
    """Split a document into scene description blocks. Tries, in order:
    'Scene N' markers, markdown headings, numbered lists, --- separators.
    A leading preamble (title, brand notes) before the first marker is NOT a
    scene and is dropped from the scene list (it still informs the storyboard,
    which is built from the full text). Falls back to the whole document."""
    for marker in (
        lambda l: bool(_SCENE_MARKER_RE.match(l)),
        lambda l: bool(_HEADING_RE.match(l)),
        lambda l: bool(_NUMBERED_RE.match(l)),
    ):
        blocks = _split_blocks(text, marker)
        marker_led = [b for b in blocks if marker(b.splitlines()[0])]
        if len(marker_led) > 1:
            return marker_led

    # --- separators split *between* blocks rather than leading them.
    parts = [p.strip() for p in re.split(r"(?m)^\s*(?:---+|\*\*\*+|===+)\s*$", text) if p.strip()]
    if len(parts) > 1:
        return parts

    return [text.strip()]


_DEFAULT_NEGATIVE_FALLBACK = (
    "readable text, captions, subtitles, watermarks, logos, brand marks, "
    "identifiable faces, distortion, low quality, camera shake"
)
try:
    if _negative_library is None:
        raise RuntimeError("negative_library unavailable")
    _DEFAULT_NEGATIVE = _negative_library.compose_negative(
        _negative_library.DEFAULT_GROUPS
    )
except Exception:
    _DEFAULT_NEGATIVE = _DEFAULT_NEGATIVE_FALLBACK


def _clean_scene_prompt(block: str) -> str:
    """Strip the marker line if it carries no content beyond the marker."""
    lines = block.splitlines()
    if lines and (_SCENE_MARKER_RE.match(lines[0]) or _HEADING_RE.match(lines[0])):
        head = lines[0]
        rest = "\n".join(lines[1:]).strip()
        head_text = re.sub(r"^\s*#{1,4}\s*", "", head)
        head_text = re.sub(r"^\s*(?:scene|shot)\s*[#:\-]?\s*\d+\s*[:\-.]?\s*", "", head_text, flags=re.IGNORECASE).strip()
        if rest:
            return (head_text + "\n" + rest).strip() if head_text else rest
        return head_text or block.strip()
    return re.sub(r"^\s*\d+[.)]\s*", "", block).strip()


def heuristic_author(text: str, job_name: str) -> dict:
    """Build scenes + storyboard dicts from raw text without any AI call.
    Deliberately conservative; flags itself for human review."""
    blocks = split_scenes(text)
    scenes = []
    for block in blocks:
        prompt = _clean_scene_prompt(block)
        if prompt:
            scenes.append({"prompt": prompt, "negative_prompt": _DEFAULT_NEGATIVE})
    if not scenes:
        raise DocParseError("No scene descriptions could be found in the document.")

    first_line = next((l.strip() for l in text.splitlines() if l.strip()), job_name)
    storyboard = {
        "project_name": job_name,
        "brand_name": re.sub(r"^#+\s*", "", first_line)[:80],
        "region": "UK",
        "target_duration_seconds": 6 + 7 * (len(scenes) - 1),
        "format": "Silent brand video. The music is the entire audio layer; there is no speech.",
        "scene": {
            "description": " ".join(text.split())[:400],
            "spoken_line": "",
            "mood": "modern, premium, confident",
        },
        "music_direction": {
            "intent": "A present, polished instrumental bed that carries the clip on its own.",
            "instrumentation": "warm synth foundation, soft electronic pulse, light piano motif",
            "energy": "steady with a gentle build, no aggressive movement",
            "vocal_policy": "instrumental only, no vocals",
            "fade": "gentle fade in, clean fade out",
            "avoid": ["vocals", "lyrics", "commercial jingle", "stock-library cliche",
                      "any reference to a specific artist or song"],
        },
        "notes": "Auto-generated by the basic (no-AI) parser from the operator's document - review before relying on it.",
    }
    return {"scenes": scenes, "storyboard": storyboard, "method": "heuristic"}


def try_parse_artifact_json(text: str):
    """If the pasted document is itself a JSON artifact, recognize it.
    Returns (scenes_list_or_None, storyboard_dict_or_None)."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None, None
    scenes = None
    storyboard = None
    if isinstance(data, list) and data and all(isinstance(s, dict) for s in data):
        if any("prompt" in s for s in data):
            scenes = data
    elif isinstance(data, dict):
        if isinstance(data.get("scenes"), list):
            scenes = data["scenes"]
        if isinstance(data.get("storyboard"), dict):
            storyboard = data["storyboard"]
        elif "music_direction" in data or ("scene" in data and "project_name" in data):
            storyboard = data
    return scenes, storyboard
