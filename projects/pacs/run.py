import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from backend import config
from backend.database import init_db
from backend.dicom_server import start_dicom_server


def main():
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    from backend.routers.studies import router

    init_db()

    app = FastAPI(title="OpenPACS", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)

    frontend_dir = os.path.join(BASE_DIR, "frontend")
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

    @app.get("/")
    def index():
        return FileResponse(os.path.join(frontend_dir, "index.html"))

    start_dicom_server()

    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=config.HTTP_PORT, log_level="info")


if __name__ == "__main__":
    main()
