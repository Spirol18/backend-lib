from datetime import datetime, timezone
import json
import os

from flask import Flask, abort, jsonify, request, send_from_directory
from flask_cors import CORS
from werkzeug.security import check_password_hash, generate_password_hash

from preprocess import process_pdf
from pathlib import Path

app = Flask(__name__)
CORS(app)

AUDIO_DIR = "audio_files"
AUTH_FILE = "auth.json"


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
        # Treat invalid file as an empty store to keep API available.
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


@app.route("/")
def index():
    return "Audio File Server is running."

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@app.route("/upload", methods=["POST"])
def upload_pdf():
    try:
        with open("log.txt", "a") as f:
            f.write(f"Content-Type: {request.content_type}\n")
            f.write(f"Files: {request.files}\n")
            f.write(f"Form: {request.form}\n")
            f.write(f"Headers: {dict(request.headers)}\n")
            f.write("---\n")

        if "file" not in request.files:
            return _json_response("No file uploaded. Ensure the request is multipart/form-data and contains a 'file' field.", 400)

        file = request.files["file"]

        if file.filename == "":
            return _json_response("No file selected", 400)

        if not file.filename.lower().endswith(".pdf"):
            return _json_response("Only PDF files allowed", 400)

        filepath = os.path.join(UPLOAD_DIR, file.filename)
        file.save(filepath)


        try:
            stats = process_pdf(Path(filepath))
            if stats is None or not stats.get("success"):
                raise Exception(stats.get("error", "Unknown processing error"))
            
            final_txt_path = stats.get("file_path")
            with open(final_txt_path, "r", encoding="utf-8") as f:
                processed_text = f.read()

            import requests
            # Call the external TTS API on http://127.0.0.1:8000/message
            print(f"Sending text to TTS API on port 8000...")
            tts_response = requests.post(
                "http://127.0.0.1:8000/message", 
                json={"text": processed_text},
                timeout=120
            )
            
            # Save the returned audio
            if tts_response.status_code == 200:
                audio_id = str(int(datetime.now(timezone.utc).timestamp()))
                audio_filename = f"audio{audio_id}.wav"
                audio_filepath = os.path.join(AUDIO_DIR, audio_filename)
                
                with open(audio_filepath, "wb") as audio_file:
                    audio_file.write(tts_response.content)
                
                print(f"Audio generated and saved to {audio_filepath}")
            else:
                print(f"TTS API failed with status {tts_response.status_code}: {tts_response.text}")
                return _json_response("TTS API failed to generate audio.", 500)

        except Exception as e:
            print(f"Error processing PDF or calling TTS: {str(e)}")
            return _json_response(f"Error processing PDF: {str(e)}", 500)

        # Delete the uploaded PDF after successful processing
        try:
            os.remove(filepath)
            print(f"Deleted uploaded file: {filepath}")
        except Exception as e:
            print(f"Error deleting uploaded file: {e}")

        return _json_response(
            "File uploaded successfully",
            filename=file.filename,
            audio_url=f"/audio/{audio_id}",
            audio_id=audio_id
        )
    except Exception as e:
        print(f"Error during upload: {e}")
        return _json_response(f"An unexpected server error occurred: {str(e)}", 500)

@app.route("/signup", methods=["POST"])
def signup():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return _json_response("Request body must be valid JSON.", 400)

    name = data.get("name", "")
    email = _normalize_email(data.get("email"))
    password = data.get("password")

    if not isinstance(name, str) or len(name.strip()) < 2:
        return _json_response("Name must be at least 2 characters long.", 400)
    if not _is_valid_email(email):
        return _json_response("Invalid email format.", 400)
    if not isinstance(password, str) or len(password) < 8:
        return _json_response("Password must be at least 8 characters long.", 400)

    auth_store = _load_auth_store()
    if _find_user_by_email(auth_store, email):
        return _json_response("User already exists.", 409)

    auth_store["users"].append(
        {
            "name": name.strip(),
            "email": email,
            "password_hash": generate_password_hash(password),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    _save_auth_store(auth_store)
    return _json_response("Account created successfully.", 201)


@app.route("/signin", methods=["POST", "GET"])
def signin():
    if request.method == "GET":
        return _json_response("Signin endpoint is available.")

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return _json_response("Request body must be valid JSON.", 400)

    email = _normalize_email(data.get("email"))
    password = data.get("password")

    if not _is_valid_email(email):
        return _json_response("Invalid email format.", 400)
    if not isinstance(password, str) or len(password) < 8:
        return _json_response("Password must be at least 8 characters long.", 400)

    auth_store = _load_auth_store()
    user = _find_user_by_email(auth_store, email)
    if not user:
        return _json_response("Invalid email or password.", 401)

    if not check_password_hash(user.get("password_hash", ""), password):
        return _json_response("Invalid email or password.", 401)

    return _json_response("Authentication successful.")


@app.route("/audio/<string:audio_id>", methods=["GET"])
def get_audio(audio_id):
    filename = f"audio{audio_id}.wav"
    file_path = os.path.join(AUDIO_DIR, filename)

    if not os.path.exists(file_path):
        abort(404, description="Audio file not found")

    return send_from_directory(
        AUDIO_DIR,
        filename,
        mimetype="audio/wav",
        as_attachment=False,
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
