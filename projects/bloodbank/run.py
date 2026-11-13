import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from database import init_db
from api import router as api_router
from pdf import router as pdf_router


def main():
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import FileResponse
    from uvicorn import run as uvicorn_run

    import config

    init_db()

    app = FastAPI(title="NBTS Blood Bank System", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router)
    app.include_router(pdf_router)

    @app.get("/")
    def index():
        return FileResponse(os.path.join(BASE_DIR, "index.html"))

    @app.get("/static/style.css")
    def style_css():
        return FileResponse(os.path.join(BASE_DIR, "style.css"), media_type="text/css")

    @app.get("/static/app.js")
    def app_js():
        return FileResponse(os.path.join(BASE_DIR, "app.js"), media_type="application/javascript")

    uvicorn_run(app, host=config.HTTP_HOST, port=config.HTTP_PORT, log_level="info")


if __name__ == "__main__":
    main()
