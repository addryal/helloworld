import os
from flask import Flask, request, render_template_string
from openai import AzureOpenAI
from PyPDF2 import PdfReader

# Read from environment variables
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_KEY")
AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini")

client = AzureOpenAI(
    api_key=AZURE_OPENAI_KEY,
    api_version="2024-08-01-preview",
    azure_endpoint=AZURE_OPENAI_ENDPOINT
)

app = Flask(__name__)

TEMPLATE = """
<!DOCTYPE html>
<html>
  <head><title>PDF Entity Extractor</title></head>
  <body>
    <h2>Upload a PDF</h2>
    <form method="POST" enctype="multipart/form-data">
      <input type="file" name="pdf">
      <input type="submit" value="Upload">
    </form>
    {% if entities %}
      <h3>Extracted Entities & Terms:</h3>
      <pre>{{ entities }}</pre>
    {% endif %}
  </body>
</html>
"""

def extract_pdf_text(file_stream):
    reader = PdfReader(file_stream)
    text = ""
    for page in reader.pages:
        text += page.extract_text() or ""
    return text

@app.route("/", methods=["GET", "POST"])
def index():
    entities = None
    if request.method == "POST":
        pdf_file = request.files.get("pdf")
        if pdf_file:
            text = extract_pdf_text(pdf_file)
            sample_text = text[:2000]  # limit to first 2000 chars for demo
            response = client.chat.completions.create(
                model=AZURE_OPENAI_DEPLOYMENT,
                messages=[
                    {"role": "system", "content": "You are an assistant that extracts key entities and important terms from documents."},
                    {"role": "user", "content": f"Extract the key entities and important terms from the following text:\n\n{sample_text}"}
                ],
                max_tokens=300
            )
            entities = response.choices[0].message.content.strip()
    return render_template_string(TEMPLATE, entities=entities)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
