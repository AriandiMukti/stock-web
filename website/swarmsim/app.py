from flask import Flask, jsonify, render_template, request

from engine import run_experiment
from presets import public_presets

app = Flask(__name__)


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/presets")
def presets():
    return jsonify(public_presets())


@app.post("/api/simulate")
def simulate():
    return jsonify(run_experiment(request.get_json(force=True, silent=True) or {}))


if __name__ == "__main__":
    app.run(debug=True, port=5050)
