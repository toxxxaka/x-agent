import os
import secrets
from functools import wraps

from flask import Flask, jsonify, request

from .posts import create_post, create_thread, reply_to_post, status

app = Flask(__name__)
TOKEN = os.environ.get("X_AGENT_SERVICE_TOKEN")


def _require_token(handler):
    @wraps(handler)
    def wrapped(*args, **kwargs):
        if not TOKEN or not secrets.compare_digest(request.headers.get("Authorization", ""), f"Bearer {TOKEN}"):
            return jsonify({"success": False, "error": "unauthorized"}), 401
        return handler(*args, **kwargs)
    return wrapped


@app.errorhandler(ValueError)
@app.errorhandler(RuntimeError)
def handle_error(error):
    return jsonify({"success": False, "error": str(error)}), 400


@app.get("/status")
@_require_token
def get_status():
    return jsonify({"success": True, **status()})


@app.post("/post")
@_require_token
def post():
    return jsonify(create_post(request.get_json(force=True)["text"]))


@app.post("/thread")
@_require_token
def thread():
    return jsonify(create_thread(request.get_json(force=True)["posts"]))


@app.post("/reply")
@_require_token
def reply():
    body = request.get_json(force=True)
    return jsonify(reply_to_post(body["post_url"], body["text"]))


def main() -> None:
    if not TOKEN:
        raise SystemExit("X_AGENT_SERVICE_TOKEN is required")
    app.run(host="127.0.0.1", port=8765, debug=False)
