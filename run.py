from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

from app import create_app

app = create_app()


if __name__ == "__main__":
    app.run(
        host=os.getenv("FLASK_RUN_HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "5000")),
        debug=os.getenv("FLASK_DEBUG", "").strip().lower() in {"1", "true", "yes"},
    )
