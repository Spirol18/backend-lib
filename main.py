from flask import Flask, send_from_directory, abort
from flask_cors import CORS
import os

app = Flask(__name__)
CORS(app)

# Directory where audio files are stored
AUDIO_DIR = "audio_files"  # e.g., audio_files/123.wav

@app.route("/audio/<string:audio_id>", methods=["GET"])
def get_audio(audio_id):
    # Allow only specific extensions if needed
    filename = f"audio{audio_id}.wav"   # or .mp3, .ogg, etc.
    file_path = os.path.join(AUDIO_DIR, filename)

    if not os.path.exists(file_path):
        abort(404, description="Audio file not found")

    return send_from_directory(
        AUDIO_DIR,
        filename,
        mimetype="audio/wav",  # change based on format
        as_attachment=False
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
