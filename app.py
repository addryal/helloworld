import os
from flask import Flask, request, render_template_string
from openai import AzureOpenAI
from PyPDF2 import PdfReader


AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_KEY")
AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini")

for v in ["AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_KEY", "AZURE_OPENAI_DEPLOYMENT"]:
    if not globals()[v]:
        raise RuntimeError(f"Missing required environment variable: {v}")

client = AzureOpenAI(
    api_key=AZURE_OPENAI_KEY,
    api_version="2024-08-01-preview",
    azure_endpoint=AZURE_OPENAI_ENDPOINT
)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB

TEMPLATE = """
<!DOCTYPE html><html><body>
  <h2>Upload a PDF</h2>
  <form method="POST" enctype="multipart/form-data">
    <input type="file" name="pdf" accept="application/pdf">
    <button type="submit">Upload</button>
  </form>
  {% if error %}<p style="color:red">{{ error }}</p>{% endif %}
  {% if entities %}<h3>Extracted Entities & Terms</h3><pre>{{ entities }}</pre>{% endif %}
</body></html>
"""

def extract_pdf_text(file_stream):
    reader = PdfReader(file_stream)
    return "".join((page.extract_text() or "") for page in reader.pages)

@app.route("/", methods=["GET", "POST"])
def index():
    error = None
    entities = None
    if request.method == "POST":
        pdf = request.files.get("pdf")
        if not pdf:
            error = "No file uploaded."
        else:
            try:
                text = extract_pdf_text(pdf)
                sample = text[:2000] if text else "No text extracted."
                resp = client.chat.completions.create(
                    model=AZURE_OPENAI_DEPLOYMENT,
                    messages=[
                        {"role":"system","content":"Extract key entities and important terms. Respond concisely."},
                        {"role":"user","content":f"Text:\n{sample}"}
                    ],
                    max_tokens=300
                )
                entities = resp.choices[0].message.content.strip()
            except Exception as e:
                error = f"{type(e).__name__}: {e}"
    return render_template_string(TEMPLATE, entities=entities, error=error)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
