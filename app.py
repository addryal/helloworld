from flask import Flask, request, jsonify, render_template_string
from pdfminer.high_level import extract_text
import io, re

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB cap

# ---------- tiny layout helper (no Jinja inheritance) ----------
BASE = """
<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Counterparty Extractor</title>
<style>
  :root { font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial; }
  body { margin:0; background:#0b1020; color:#e9edf5 }
  .wrap{ max-width:680px; margin:48px auto; padding:0 16px }
  .card{ background:#151a2e; border-radius:16px; padding:24px; box-shadow:0 6px 24px rgba(0,0,0,.25) }
  h1{ margin:0 0 12px; font-size:22px }
  p{ color:#b8c0d9 }
  .row{ margin-top:16px; display:flex; gap:12px; align-items:center }
  input[type=file]{ padding:10px; background:#0f1430; border:1px solid #2a3154; border-radius:10px; color:#cfe1ff; width:100% }
  button{ background:#3b82f6; border:0; color:white; padding:10px 16px; border-radius:10px; cursor:pointer }
  .pill{ background:#0f1430; border:1px solid #2a3154; padding:6px 10px; border-radius:999px; display:inline-block; margin:6px 6px 0 0 }
  .muted{ color:#93a0c7; font-size:13px }
  .err{ background:#2a1330; border:1px solid #7a2a53; color:#ffd7e6; padding:10px; border-radius:10px; margin-top:12px }
  .ok{ background:#0f2a1a; border:1px solid #2c7a4b; color:#d7ffe7; padding:10px; border-radius:10px; margin-top:12px }
  .footer{ margin-top:18px; font-size:12px; color:#8ea0c8 }
  pre{ white-space:pre-wrap; word-wrap:break-word }
</style></head><body>
<div class="wrap"><div class="card">
{{ body|safe }}
</div><div class="footer">
Runs in memory. PDF limit 10 MB. Programmatic JSON available at <code>/extract</code>.
</div></div></body></html>
"""

def page(body_html: str):
    return render_template_string(BASE, body=body_html)

# ---------- simple bodies ----------
INDEX_BODY = """
<h1>Upload swap confirmation (PDF)</h1>
<p class="muted">This demo extracts the two <b>counterparties</b> from one document type.</p>
<form action="/extract" method="post" enctype="multipart/form-data">
  <div class="row">
    <input type="file" name="file" accept="application/pdf" required>
    <button>Extract</button>
  </div>
</form>
"""

RESULTS_BODY = """
<h1>Counterparties</h1>
{content}
<div class="row" style="margin-top:12px">
  <form action="/" method="get"><button>Upload another</button></form>
  <button onclick='navigator.clipboard.writeText(JSON.stringify({{"counterparties": %(json)s, "count": %(count)d}}, null, 2))'>
    Copy JSON
  </button>
</div>
<details style="margin-top:14px"><summary class="muted">Show raw JSON</summary>
<pre>{{ raw_json }}</pre></details>
"""

# ---------- extraction heuristics ----------
UPPERLINE = re.compile(r"^[A-Z][A-Z0-9 .,&'/-]{3,}$")
BETWEEN_BLOCK = re.compile(r"entered\s+into\s+between:\s*(.+?)\s*and\s*(.+?)(?:\n|\r)",
                           re.IGNORECASE | re.DOTALL)
PAREN_NAME = re.compile(r"\(\s*“?\"?(?:the\s+)?Counterparty", re.IGNORECASE)

def clean(s: str) -> str:
    s = re.sub(r"\s+", " ", s).strip()
    return s.replace(" .", ".").replace(" ,", ",")

def find_counterparties(txt: str):
    m = BETWEEN_BLOCK.search(txt)
    if m:
        left, right = clean(m.group(1)), clean(m.group(2))
        left = re.split(PAREN_NAME, left)[0].strip(" -•:;\n\r\t")
        right = re.split(PAREN_NAME, right)[0].strip(" -•:;\n\r\t")
        return [left, right]
    # fallback: uppercase entity-like lines
    out, seen = [], set()
    for line in txt.splitlines():
        line = line.strip()
        if UPPERLINE.match(line) and line not in seen:
            seen.add(line); out.append(line)
    return out[:2]

@app.route("/")
def index():
    return page(INDEX_BODY)

@app.route("/extract", methods=["POST"])
def extract_route():
    # API mode if Accept: application/json
    wants_json = "application/json" in request.headers.get("Accept", "")
    if "file" not in request.files:
        msg = "Upload a PDF in 'file' field"
        return (jsonify(error=msg), 400) if wants_json else page(INDEX_BODY + f'<div class="err">{msg}</div>')
    f = request.files["file"]
    if not f.filename.lower().endswith(".pdf"):
        msg = "Only .pdf files are allowed."
        return (jsonify(error=msg), 400) if wants_json else page(INDEX_BODY + f'<div class="err">{msg}</div>')

    try:
        text = extract_text(io.BytesIO(f.read())) or ""
    except Exception as e:
        msg = f"Failed to read PDF: {e}"
        return (jsonify(error=msg), 500) if wants_json else page(INDEX_BODY + f'<div class="err">{msg}</div>')

    parties = [p for p in find_counterparties(text) if len(p) > 2]
    if wants_json:
        return jsonify(counterparties=parties, count=len(parties))

    pills = "".join(f'<span class="pill">{p}</span>' for p in parties) if parties \
            else '<div class="err">No counterparties found.</div>'
    raw_json = jsonify(counterparties=parties, count=len(parties)).get_data(as_text=True)
    html = RESULTS_BODY.format(content=(pills if parties else pills)) % {
        "json": parties, "count": len(parties)
    }
    return render_template_string(BASE, body=html, raw_json=raw_json)

@app.route("/health")
def health():
    return "ok"
