"""
PDF generation from Markdown content.
Uses markdown + weasyprint for high-quality PDF output.
"""

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# Lazy import to avoid startup cost if never used
_weasyprint_available = None


def _check_weasyprint() -> bool:
    global _weasyprint_available
    if _weasyprint_available is not None:
        return _weasyprint_available
    try:
        from weasyprint import HTML  # noqa: F401
        _weasyprint_available = True
    except ImportError:
        logger.warning("weasyprint not installed; PDF generation disabled")
        _weasyprint_available = False
    return _weasyprint_available


def markdown_to_html(content: str) -> str:
    """Convert markdown to HTML with basic extensions."""
    try:
        import markdown
        md = markdown.Markdown(extensions=["tables", "fenced_code", "nl2br"])
        return md.convert(content)
    except ImportError:
        # Fallback: simple regex-based conversion
        html = content
        html = re.sub(r"^### (.+)$", r"<h3>\1</h3>", html, flags=re.MULTILINE)
        html = re.sub(r"^## (.+)$", r"<h2>\1</h2>", html, flags=re.MULTILINE)
        html = re.sub(r"^# (.+)$", r"<h1>\1</h1>", html, flags=re.MULTILINE)
        html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
        html = re.sub(r"\*(.+?)\*", r"<em>\1</em>", html)
        html = re.sub(r"\[(\d+)\]", r'<sup class="ref">[\1]</sup>', html)
        html = re.sub(r"^- (.+)$", r"<li>\1</li>", html, flags=re.MULTILINE)
        html = re.sub(r"^\* (.+)$", r"<li>\1</li>", html, flags=re.MULTILINE)
        html = re.sub(r"^\d+\. (.+)$", r"<li>\1</li>", html, flags=re.MULTILINE)
        html = re.sub(r"\n\n", "</p><p>", html)
        html = re.sub(r"\n", "<br>", html)
        return f"<p>{html}</p>"


def generate_pdf(content: str, title: str = "OMINIS Report") -> Optional[bytes]:
    """
    Generate a PDF from markdown content.
    Returns PDF bytes or None if generation fails.
    """
    if not _check_weasyprint():
        return None

    try:
        from weasyprint import HTML

        body_html = markdown_to_html(content)
        # Wrap in full document with print styles
        html_doc = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>{_escape_html(title)}</title>
<style>
  @page {{ margin: 25mm 20mm 20mm 20mm; }}
  body {{
    font-family: Helvetica, Arial, sans-serif;
    max-width: 720px;
    margin: 0 auto;
    padding: 0 20px;
    color: #1a1a1a;
    font-size: 11pt;
    line-height: 1.55;
  }}
  h1 {{ font-size: 20pt; color: #111; border-bottom: 2px solid #222; padding-bottom: 6px; margin: 0 0 12px 0; }}
  h2 {{ font-size: 14pt; color: #333; margin: 16px 0 6px 0; padding-bottom: 3px; border-bottom: 1px solid #eee; }}
  h3 {{ font-size: 12pt; color: #444; margin: 12px 0 4px 0; }}
  p {{ margin: 0 0 8px 0; }}
  ul, ol {{ margin: 4px 0 8px 20px; padding: 0; }}
  li {{ margin: 2px 0; }}
  table {{ border-collapse: collapse; width: 100%; margin: 12px 0; }}
  th, td {{ border: 1px solid #ddd; padding: 6px 10px; text-align: left; }}
  th {{ background: #f5f5f5; font-weight: 600; }}
  sup.ref {{ color: #1a5fb4; font-size: 8pt; font-weight: 600; }}
  strong {{ color: #111; }}
  a {{ color: #1a5fb4; text-decoration: none; }}
  .footer {{ font-size: 8pt; color: #999; margin-top: 24px; padding-top: 8px; border-top: 1px solid #eee; }}
</style>
</head>
<body>
{body_html}
<div class="footer">Generado con ia.ominis.org · Una iniciativa de FUNSALUD</div>
</body>
</html>"""

        pdf_bytes = HTML(string=html_doc).write_pdf()
        return pdf_bytes

    except Exception as e:
        logger.error(f"PDF generation failed: {e}", exc_info=True)
        return None


def _escape_html(s: str) -> str:
    """Escape HTML special characters."""
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
