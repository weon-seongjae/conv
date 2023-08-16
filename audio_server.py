from flask import Flask, Response, send_from_directory
from flask_cors import CORS
import os

app = Flask(__name__, static_url_path='/static', static_folder='.')
CORS(app)

audio_directory = './audio'

if not os.path.exists(audio_directory):
    os.makedirs(audio_directory)

@app.route('/audio/<path:filename>', methods=['GET'])
def download(filename):
    return send_from_directory(audio_directory, filename)

@app.route('/delete/audio/<path:filename>', methods=['POST'])
def delete_file(filename):
    file_path = os.path.join(audio_directory, filename)
    try:
        os.remove(file_path)
        return Response(status=204)  # 204 No Content, 성공적인 삭제
    except FileNotFoundError:
        return Response(status=404)  # 파일이 없으면 404 Not Found

if __name__ == "__main__":
    print("Server is running on http://127.0.0.1:8001")
    app.run(port=8001, debug=True)  # 애플리케이션 실행