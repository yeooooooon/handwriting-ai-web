# main.py
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
import os

from app.handwriting_feedback_api import router as handwriting_router

BASE_DIR = Path(__file__).resolve().parent  # main.py가 있는 폴더.

app = FastAPI()
app.include_router(handwriting_router)

# ─── 절대경로로 static mount ───────────────────────────
app.mount(
    "/static",
    StaticFiles(directory=BASE_DIR / "css"),
    name="static"
)

# index.html 서빙
@app.get("/", response_class=FileResponse)
def serve_index():
    return BASE_DIR / "public" / "index.html"

# test.html 서빙
@app.get("/test", response_class=FileResponse)
def serve_test():
    return BASE_DIR / "public" / "test.html"
