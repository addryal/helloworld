from flask import Flask, request, jsonify, render_template_string, redirect, url_for
from pdfminer.high_level import extract_text
import io, re

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB upload cap

# ---------- HTML (inline to keep it 1-file simple) ----------
BASE = """
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Counterparty Extractor</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  :root { font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, 'Helvetica Neue', Arial; }
  body { margin: 0; background:#0b1020; color:#e9edf5; }
  .wrap { max-width: 680px; margin: 48px auto; padding: 0 16px; }
  .card { background:#151a2e; border-radius:16px; padding:24px; box-shadow: 0 6px 24px rgba(0,0,0,.25); }
  h1 { margin: 0 0 12px; font-size: 22px; }
  p { color:#b8c0d9 }
  .row { margin-top:16px; display:flex; gap:12px; align-items:center; }
  input[type=file] { padding:10px; background:#0f1430; border:1px solid #2a3154; border-radius:10px; color:#cfe1ff; width:100%; }
  button { background:#3b82f6; border:0; color:white; padding:10px 16px; border-radius:10px; cursor:pointer; }
  button:disabled { opacity:.6; cursor:not-allowed; }
  .pill { background:#0f1430; border:1px solid #2a3154; padding:6px 10px; border-radius:999px; display:inline-block; margin:6px 6px 0 0; }
  .muted { color:#93a0c7; font-size:13px; }
  .err { background:#2a1330; border:1px solid #7a2a53; color:#ffd7e6; padding:10px; border-radius:10px; margin-top:12px;}
  .ok { background:#0f2a1a; border:1px solid #2c7a4b; color:#d7ffe7; padding:10px; border-radius:10px; margin-top:12px;}
  .footer { margin-top:18px; font-size:12px; color:#8ea0c8; }
  pre { white-space: pre-wrap; word-wrap: break-word; }
</style>
</head>
<body>
<div class="wrap">
<div class="card">
  {% block body %}{% endblock %}
</div>
<div class="footer">Runs entirely in memory. PDF limit 10 MB. Returns JSON at <code>/extract</code> if requested via API.</div>
</div>
</body>
</html>
"""

INDEX_HTML = """
{% extends base %}
{% block body %}
  <h1>Upload swap confirmation (PDF)</h1>
  <p class="muted">This demo extracts just the two <b>counterparties</b> from a single document type.</p>

  <form action="{{ url_for('extract_route') }}" method="post" enctype="multipart/form-data">
    <div class="row">
      <input type="file" name="file" accept="application/pdf" required>
      <button>Extract</button>
    </div>
  </form>

  {% if error %}<div class="err">{{ error }}</div>{% endif %}
{% endblock %}
"""

RESULTS_HTML = """
{% extends base %}
{% block body %}
  <h1>Counterparties</h1>

  {% if parties %}
    {% for p in parties %}
      <span class="pill">{{ p }}</span>
    {% endfor %}
    <div class="ok">Found {{ parties|length }} counterparty{{ '' if parties|length==1 else 'ies' }}.</div>
  {% else %}
    <div class="err">No counterparties found. Try a different file or adjust heuristics.</div>
  {% endif %}

  <div class="row">
    <form action="{{ url_for('index') }}" method="get"><button>Upload another</button></form>
    <button onclick="navigator.clipboard.writeText(JSON.stringify({counterparties: {{ parties|tojson }}, count: {{ parties|length }}}, null, 2))">Copy JSON</button>
  </div>

  <details style="margin-top:14px">
    <summary class="muted">Show raw JSON</summary>
    <pre>{{ {'counterparties': parties, 'count': parties|length} | tojson(indent=2) }}</pre>
  </details>
{% endblock %}
"""

# ---------- Heuristics / patterns ----------
UPPERLINE = re.compile(r"^[A-Z][A-Z0-9 .,&'/-]{3,}$")
BETWEEN_BLOCK = re.compile(
    r"entered\s+into\s+between:\s*(.+?)\s*and\s*(.+?)(?:\n|\r)",
    re.IGNORECASE | re.DOTALL
)
PAREN_NAME = re.compile(r"\(\s*“?\"?(?:the\s+)?Counterparty", re.IGNORECASE)

def clean(s: str) -> str:
    s = re.sub(r"\s+", " ", s).strip()
    return s.replace(" .", ".").replace(" ,", ",")

def find_counterparties(txt: str):
    m = BETWEEN_BLOCK.search(txt)
    if m:
        left = clean(m.group(1))
        right = clean(m.group(2))
        left = re.split(PAREN_NAME, left)[0].strip(" -•:;\n\r\t")
        right = re.split(PAREN_NAME, right)[0].strip(" -•:;\n\r\t")
        return [left, right]

    # Fallback: uppercase “entity-like” lines
    lines = [l.rstrip() for l in txt.splitlines()]
    candidates = []
    for line in lines:
        if UPPERLINE.match(line):
            candidates.append(line.strip(" -•:;\t"))
    # unique and take top 2
    out, seen = [], set()
    for c in candidates:
        if c and c not in seen:
            seen.add(c); out.append(c)
    return out[:2]

@app.route("/")
def index():
    return render_template_string(INDEX_HTML, base=BASE, error=None)

@app.route("/extract", methods=["POST"])
def extract_route():
    # If someone calls via API (e.g., curl), honor JSON response
    wants_json = "application/json" in request.headers.get("Accept", "")
    if "file" not in request.files:
        return (jsonify(error="Upload a PDF in 'file' field"), 400) if wants_json \
               else render_template_string(INDEX_HTML, base=BASE, error="Please choose a PDF to upload.")

    # Basic type guard (relies on browser-provided type)
    f = request.files["file"]
    if not f.filename.lower().endswith(".pdf"):
        return (jsonify(error="Only .pdf allowed"), 400) if wants_json \
               else render_template_string(INDEX_HTML, base=BASE, error="Only .pdf files are allowed.")

    pdf_bytes = f.read()
    try:
        text = extract_text(io.BytesIO(pdf_bytes)) or ""
    except Exception as e:
        return (jsonify(error=f"Failed to read PDF: {e}"), 500) if wants_json \
               else render_template_string(INDEX_HTML, base=BASE, error=f"Failed to read PDF: {e}")

    parties = [p for p in find_counterparties(text) if len(p) > 2]

    if wants_json:
        return jsonify(counterparties=parties, count=len(parties))

    return render_template_string(RESULTS_HTML, base=BASE, parties=parties)

# Local only; on Azure, gunicorn will serve app:app
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
