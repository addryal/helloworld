import os
from flask import Flask, request, render_template_string
from openai import AzureOpenAI
from pypdf import PdfReader

# ----- Azure OpenAI config (from environment) -----
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "https://openatest.openai.azure.com/")
AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_KEY")  # REQUIRED: set in App Service config
AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")

if not AZURE_OPENAI_KEY:
    # Fail fast with a clear message if the key isn't provided
    raise RuntimeError("Missing AZURE_OPENAI_KEY environment variable.")

# Azure OpenAI client
client = AzureOpenAI(
    api_version=AZURE_OPENAI_API_VERSION,
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
    api_key=AZURE_OPENAI_KEY,
)

# ----- Flask app -----
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB upload limit

HTML = """
<!DOCTYPE html>
<html>
  <head><meta charset="utf-8"><title>PDF Entity Extractor</title></head>
  <body style="font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; max-width: 900px; margin: 2rem auto;">
    <h2>PDF Entity & Key-Term Extractor</h2>
    <form method="POST" enctype="multipart/form-data" style="margin: 1rem 0;">
      <input type="file" name="pdf" accept="application/pdf">
      <button type="submit">Upload</button>
    </form>

    {% if meta %}
      <div style="margin: 1rem 0; font-size: 0.95rem; color: #555;">
        <div><strong>Endpoint:</strong> {{ meta.endpoint }}</div>
        <div><strong>Deployment:</strong> {{ meta.deployment }}</div>
        <div><strong>API Version:</strong> {{ meta.api_version }}</div>
      </div>
    {% endif %}

    {% if error %}
      <div style="padding: 0.75rem 1rem; background:#ffecec; color:#a30000; border:1px solid #ffb3b3; border-radius: 6px;">
        <strong>Error:</strong> {{ error }}
      </div>
    {% endif %}

    {% if entities %}
      <h3>Extracted Entities & Terms</h3>
      <pre style="white-space: pre-wrap; background:#f6f8fa; padding:1rem; border-radius:6px;">{{ entities }}</pre>
    {% endif %}
  </body>
</html>
"""

def extract_pdf_text(file_storage) -> str:
    """Extract plain text from a PDF upload."""
    reader = PdfReader(file_storage)
    text_parts = []
    for page in reader.pages:
        text_parts.append(page.extract_text() or "")
    return "".join(text_parts)

@app.route("/", methods=["GET", "POST"])
def index():
    error = None
    entities = None
    meta = {
        "endpoint": AZURE_OPENAI_ENDPOINT,
        "deployment": AZURE_OPENAI_DEPLOYMENT,
        "api_version": AZURE_OPENAI_API_VERSION,
    }

    if request.method == "POST":
        pdf = request.files.get("pdf")
        if not pdf:
            error = "No file uploaded. Please choose a PDF."
        else:
            try:
                # Extract and truncate text for the demo
                text = extract_pdf_text(pdf)
                if not text.strip():
                    error = "No extractable text found in the PDF."
                else:
                    sample_text = text[:4000]  # keep prompt size reasonable for demo

                    # Ask the model to extract entities/terms
                    prompt = (
                        "Extract the key named entities and important domain terms from the following text. "
                        "Summarize concisely. Group findings by categories where possible "
                        "(e.g., Organizations, People, Locations, Dates, Amounts, Products, Technical Terms). "
                        "Text:\n\n" + sample_text
                    )

                    resp = client.chat.completions.create(
                        model=AZURE_OPENAI_DEPLOYMENT,
                        messages=[
                            {"role": "system", "content": "You are an assistant that extracts key entities and important terms from documents."},
                            {"role": "user", "content": prompt},
                        ],
                        max_tokens=500,
                        temperature=0.4,
                        top_p=1.0,
                    )
                    entities = (resp.choices[0].message.content or "").strip()

            except Exception as e:
                # Surface the exact error so you can debug (safe for demo; redact keys are never shown)
                error = f"{type(e).__name__}: {e}"

    return render_template_string(HTML, entities=entities, error=error, meta=meta)

if __name__ == "__main__":
    # Local dev run (on Azure App Service, use gunicorn via startup command)
    app.run(host="0.0.0.0", port=5000, debug=True)
