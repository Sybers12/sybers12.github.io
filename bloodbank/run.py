import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from backend.database import init_db
from backend.routers.api import router as api_router
from backend.routers.pdf import router as pdf_router


def main():
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

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

    frontend_dir = os.path.join(BASE_DIR, "frontend")
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

    @app.get("/")
    def index():
        return FileResponse(os.path.join(frontend_dir, "index.html"))

    import uvicorn

    from backend import config

    uvicorn.run(app, host=config.HTTP_HOST, port=config.HTTP_PORT, log_level="info")


if __name__ == "__main__":
    main()
