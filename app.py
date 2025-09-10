from flask import Flask
app = Flask(__name__)

@app.route("/")
def root():
    return "Hello, World from Azure App Service! ✨"

# For local testing only; Azure will use gunicorn
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
