from datetime import datetime, timezone
import json
import os

from flask import Flask, abort, jsonify, request, send_from_directory
from flask_cors import CORS
from flask_swagger_ui import get_swaggerui_blueprint
from werkzeug.security import check_password_hash, generate_password_hash

from preprocess import process_pdf
from pathlib import Path
from logger_config import get_logger

logger = get_logger("main")

app = Flask(__name__)
CORS(app)

# ── Swagger / OpenAPI docs ─────────────────────────────────────────────────────
SWAGGER_URL  = "/docs"
API_SPEC_URL = "/static/swagger.json"

swaggerui_blueprint = get_swaggerui_blueprint(
    SWAGGER_URL,
    API_SPEC_URL,
    config={
        "app_name": "Audio File Server API",
        "docExpansion": "list",
        "defaultModelsExpandDepth": -1,
        "displayRequestDuration": True,
        "filter": True,
    },
)
app.register_blueprint(swaggerui_blueprint)
# ──────────────────────────────────────────────────────────────────────────────

AUDIO_DIR      = "audio_files"
AUTH_FILE      = "auth.json"
ANALYTICS_FILE = "analytics.json"
BOOKS_FILE     = "books.json"          # metadata store: id → {title, author, image}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _json_response(message, status_code=200, **extra):
    return jsonify({"message": message, **extra}), status_code


def _normalize_email(value):
    if not isinstance(value, str):
        return ""
    return value.strip().lower()


def _is_valid_email(value):
    return bool(value and "@" in value and "." in value and len(value) >= 6)


def _load_auth_store():
    try:
        with open(AUTH_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
            if isinstance(data, dict) and isinstance(data.get("users"), list):
                return data
    except FileNotFoundError:
        pass
    except json.JSONDecodeError:
        pass
    return {"users": []}


def _save_auth_store(data):
    with open(AUTH_FILE, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2)


def _find_user_by_email(auth_store, email):
    for user in auth_store["users"]:
        if _normalize_email(user.get("email")) == email:
            return user
    return None


def _load_analytics_store():
    try:
        with open(ANALYTICS_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
            if isinstance(data, dict) and isinstance(data.get("records"), list):
                return data
    except FileNotFoundError:
        pass
    except json.JSONDecodeError:
        pass
    return {"records": []}


def _save_analytics_store(data):
    with open(ANALYTICS_FILE, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2)


def _load_books_store():
    """Return the books metadata dict: { audio_id: {title, author, image} }."""
    try:
        with open(BOOKS_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
            if isinstance(data, dict):
                return data
    except FileNotFoundError:
        pass
    except json.JSONDecodeError:
        pass
    return {}


def _save_books_store(data):
    with open(BOOKS_FILE, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2)


def _get_audio_duration_seconds(audio_id: str) -> float | None:
    """
    Return the duration of an audio file in seconds using the wave stdlib module.
    Returns None if the file cannot be read (e.g. not a plain PCM WAV).
    """
    import wave
    filepath = os.path.join(AUDIO_DIR, f"audio{audio_id}.wav")
    try:
        with wave.open(filepath, "rb") as wf:
            frames = wf.getnframes()
            rate   = wf.getframerate()
            return frames / float(rate) if rate else None
    except Exception:
        return None


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    logger.info("Health-check hit")
    return "Audio File Server is running."

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


@app.route("/upload", methods=["POST"])
def upload_pdf():
    try:
        logger.debug("Upload request received | Content-Type=%s", request.content_type)
        logger.debug("Upload request files=%s  form=%s", request.files, request.form)
        logger.debug("Upload request headers=%s", dict(request.headers))

        if "file" not in request.files:
            logger.warning("Upload rejected: no 'file' field in multipart form")
            return _json_response(
                "No file uploaded. Ensure the request is multipart/form-data and contains a 'file' field.", 400
            )

        file = request.files["file"]

        if file.filename == "":
            logger.warning("Upload rejected: empty filename")
            return _json_response("No file selected", 400)

        if not file.filename.lower().endswith(".pdf"):
            logger.warning("Upload rejected: non-PDF file '%s'", file.filename)
            return _json_response("Only PDF files allowed", 400)

        # Optional book metadata supplied by the client at upload time
        book_title  = request.form.get("title", "").strip() or os.path.splitext(file.filename)[0]
        book_author = request.form.get("author", "").strip() or "Unknown Author"
        book_image  = request.form.get("image", "").strip()

        filepath = os.path.join(UPLOAD_DIR, file.filename)
        file.save(filepath)
        logger.info("PDF saved to '%s'", filepath)

        try:
            logger.info("Starting PDF processing pipeline for '%s'", file.filename)
            stats = process_pdf(Path(filepath))
            if stats is None or not stats.get("success"):
                raise Exception(stats.get("error", "Unknown processing error"))

            logger.info("PDF processed: %d sentences extracted", stats.get("sentence_count", 0))

            final_txt_path = stats.get("file_path")
            with open(final_txt_path, "r", encoding="utf-8") as f:
                processed_text = f.read()

            import requests
            logger.info("Sending %d chars to TTS API on port 8000", len(processed_text))
            tts_response = requests.post(
                "http://127.0.0.1:8000/message",
                json={"text": processed_text},
                timeout=120,
            )

            if tts_response.status_code == 200:
                audio_id       = str(int(datetime.now(timezone.utc).timestamp()))
                audio_filename = f"audio{audio_id}.wav"
                audio_filepath = os.path.join(AUDIO_DIR, audio_filename)

                with open(audio_filepath, "wb") as audio_file:
                    audio_file.write(tts_response.content)

                logger.info(
                    "Audio generated and saved to '%s' (audio_id=%s)", audio_filepath, audio_id
                )

                # ── Persist book metadata so /getcurrentbook can look it up ──
                books = _load_books_store()
                books[audio_id] = {
                    "title":  book_title,
                    "author": book_author,
                    "image":  book_image,
                }
                _save_books_store(books)
                logger.info("Book metadata saved for audio_id='%s'", audio_id)

            else:
                logger.error(
                    "TTS API returned status %s: %s",
                    tts_response.status_code,
                    tts_response.text[:200],
                )
                return _json_response("TTS API failed to generate audio.", 500)

        except Exception as e:
            logger.exception("Error during PDF processing or TTS call: %s", e)
            return _json_response(f"Error processing PDF: {str(e)}", 500)

        # Delete the uploaded PDF after successful processing
        try:
            os.remove(filepath)
            logger.info("Deleted uploaded file: '%s'", filepath)
        except Exception as e:
            logger.warning("Could not delete uploaded file '%s': %s", filepath, e)

        return _json_response(
            "File uploaded successfully",
            filename=file.filename,
            audio_url=f"/audio/{audio_id}",
            audio_id=audio_id,
        )
    except Exception as e:
        logger.exception("Unexpected error in upload endpoint: %s", e)
        return _json_response(f"An unexpected server error occurred: {str(e)}", 500)


@app.route("/signup", methods=["POST"])
def signup():
    logger.debug("Signup request received")
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        logger.warning("Signup rejected: invalid JSON body")
        return _json_response("Request body must be valid JSON.", 400)

    name     = data.get("name", "")
    email    = _normalize_email(data.get("email"))
    password = data.get("password")

    if not isinstance(name, str) or len(name.strip()) < 2:
        logger.warning("Signup rejected: name too short")
        return _json_response("Name must be at least 2 characters long.", 400)
    if not _is_valid_email(email):
        logger.warning("Signup rejected: invalid email '%s'", email)
        return _json_response("Invalid email format.", 400)
    if not isinstance(password, str) or len(password) < 8:
        logger.warning("Signup rejected: password too short for email='%s'", email)
        return _json_response("Password must be at least 8 characters long.", 400)

    auth_store = _load_auth_store()
    if _find_user_by_email(auth_store, email):
        logger.info("Signup rejected: email already exists '%s'", email)
        return _json_response("User already exists.", 409)

    auth_store["users"].append(
        {
            "name":          name.strip(),
            "email":         email,
            "password_hash": generate_password_hash(password),
            "created_at":    datetime.now(timezone.utc).isoformat(),
        }
    )
    _save_auth_store(auth_store)
    logger.info("New user registered: email='%s'", email)
    return _json_response("Account created successfully.", 201)


@app.route("/signin", methods=["POST", "GET"])
def signin():
    if request.method == "GET":
        logger.debug("Signin health-check GET")
        return _json_response("Signin endpoint is available.")

    logger.debug("Signin request received")
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        logger.warning("Signin rejected: invalid JSON body")
        return _json_response("Request body must be valid JSON.", 400)

    email    = _normalize_email(data.get("email"))
    password = data.get("password")

    if not _is_valid_email(email):
        logger.warning("Signin rejected: invalid email format")
        return _json_response("Invalid email format.", 400)
    if not isinstance(password, str) or len(password) < 8:
        logger.warning("Signin rejected: password too short for email='%s'", email)
        return _json_response("Password must be at least 8 characters long.", 400)

    auth_store = _load_auth_store()
    user = _find_user_by_email(auth_store, email)
    if not user:
        logger.warning("Signin failed: unknown email='%s'", email)
        return _json_response("Invalid email or password.", 401)

    if not check_password_hash(user.get("password_hash", ""), password):
        logger.warning("Signin failed: wrong password for email='%s'", email)
        return _json_response("Invalid email or password.", 401)

    logger.info("User signed in successfully: email='%s'", email)
    return _json_response("Authentication successful.")


@app.route("/audio/<string:audio_id>", methods=["GET"])
def get_audio(audio_id):
    filename  = f"audio{audio_id}.wav"
    file_path = os.path.join(AUDIO_DIR, filename)
    logger.debug("Audio requested: audio_id='%s' -> file='%s'", audio_id, file_path)

    if not os.path.exists(file_path):
        logger.warning("Audio file not found: '%s'", file_path)
        abort(404, description="Audio file not found")

    logger.info("Serving audio file: '%s'", filename)
    return send_from_directory(
        AUDIO_DIR,
        filename,
        mimetype="audio/wav",
        as_attachment=False,
    )


@app.route("/analytics", methods=["POST"])
def analytics():
    logger.debug("Analytics request received")
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return _json_response("Request body must be valid JSON.", 400)

    email     = _normalize_email(data.get("email"))
    audio_id  = str(data.get("audio_id", ""))
    timestamp = data.get("timestamp")

    if not email or not audio_id or timestamp is None:
        return _json_response("Missing required fields: email, audio_id, timestamp.", 400)

    analytics_store = _load_analytics_store()
    
    # Ensure the new structure exists
    if "current_books" not in analytics_store:
        analytics_store["current_books"] = {}

    # Update the "Current Book" pointer for this specific user
    analytics_store["current_books"][email] = {
        "audio_id":    audio_id,
        "timestamp":   timestamp,
        "recorded_at": datetime.now(timezone.utc).isoformat()
    }

    _save_analytics_store(analytics_store)
    logger.info("Updated current book for %s to %s", email, audio_id)
    return _json_response("Analytics recorded successfully.", 200)

# ─── GET /getcurrentbook ──────────────────────────────────────────────────────

@app.route("/getcurrentbook", methods=["GET"])
def get_current_book():
    logger.debug("GetCurrentBook request received")
    email_filter = _normalize_email(request.args.get("email", ""))
    
    if not email_filter:
        return _json_response("Email parameter is required.", 400)

    try:
        analytics_store = _load_analytics_store()
        current_map = analytics_store.get("current_books", {})

        # Direct lookup via the email key
        user_data = current_map.get(email_filter)

        if not user_data:
            logger.info("No current book found for email='%s'", email_filter)
            return jsonify({"message": "No book in progress", "id": None}), 200

        audio_id         = user_data.get("audio_id")
        playback_seconds = float(user_data.get("timestamp", 0))

        # Check if file exists
        audio_path = os.path.join(AUDIO_DIR, f"audio{audio_id}.wav")
        if not os.path.exists(audio_path):
            return jsonify({"message": "Audio file missing", "id": None}), 200

        # Calculate progress
        duration_seconds = _get_audio_duration_seconds(audio_id)
        progress = min(playback_seconds / duration_seconds, 1.0) if duration_seconds > 0 else 0.0

        # Fetch metadata
        books    = _load_books_store()
        metadata = books.get(audio_id, {})
        
        return jsonify({
            "id":       audio_id,
            "timestamp": playback_seconds,
            "title":    metadata.get("title", "Unknown Title"),
            "author":   metadata.get("author", "Unknown Author"),
            "progress": round(progress, 4),
            "image":    metadata.get("image", "")
        }), 200

    except Exception as e:
        logger.exception("GetCurrentBook error: %s", e)
        return _json_response(f"Server error: {str(e)}", 500)
        
# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logger.info("Starting Flask server on port 5001")
    app.run(host="0.0.0.0", port=5001, debug=True)