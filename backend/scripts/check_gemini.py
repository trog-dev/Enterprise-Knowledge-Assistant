import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.core.config import get_settings


def main():
    settings = get_settings()
    api_key = settings.gemini_api_key.strip()

    if not api_key:
        raise SystemExit(
            "Chưa đọc được GEMINI_API_KEY. Kiểm tra file .env."
        )

    request = Request(
        "https://generativelanguage.googleapis.com/v1beta/models",
        headers={
            "x-goog-api-key": api_key,
            "Accept": "application/json",
        },
    )

    try:
        with urlopen(request, timeout=30) as response:
            data = json.load(response)

    except HTTPError as error:
        print(f"Gemini HTTP error: {error.code}")
        print("Kiểm tra API key, quyền truy cập và project.")
        return

    except URLError:
        print("Không kết nối được Gemini. Kiểm tra mạng.")
        return

    models = [
        model["name"]
        for model in data.get("models", [])
        if "generateContent"
        in model.get("supportedGenerationMethods", [])
    ]

    print("Gemini connection OK")
    print("Text generation models in this response:")

    for name in models:
        print("-", name)


if __name__ == "__main__":
    main()