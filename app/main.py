# main.py
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
from fastapi.responses import JSONResponse
from app.daily_challenge_api import router as challenge_router
from app.db import Base, engine
from app import models
from app.auth_api import router as auth_router
from app.user_api import router as user_router
import random
import os

from app.handwriting_feedback_api import router as handwriting_router
#from app.paddleOCR_api import router as evaluate_router

BASE_DIR = Path(__file__).resolve().parent  # main.py가 있는 폴더.
Base.metadata.create_all(bind=engine)

app = FastAPI()
app.include_router(handwriting_router)
app.include_router(challenge_router)
app.include_router(auth_router)
app.include_router(user_router)
# app.include_router(evaluate_router)

sentences = [
    "저 넓은 세상에서 큰 꿈을 펼쳐라",
    "한글은 아름다운 문자입니다",
    "노력은 배신하지 않는다",
    "작은 실천이 큰 변화를 만든다"
]

# ─── 절대경로로 static mount ───────────────────────────
app.mount(
    "/static",
    StaticFiles(directory=BASE_DIR / "css"),
    name="static"
)


# main.html 서빙
@app.get("/", response_class=FileResponse)
def serve_index():
    return BASE_DIR / "public" / "main.html"

# test.html 서빙
@app.get("/test", response_class=FileResponse)
def serve_test():
    return BASE_DIR / "public" / "test.html"

# test.html 서빙
@app.get("/daily", response_class=FileResponse)
def serve_daily():
    return BASE_DIR / "public" / "daily_sentence.html"

# index.html 서빙
@app.get("/index", response_class=FileResponse)
def serve_main():
    return BASE_DIR / "public" / "index.html"

@app.get("/daily_sentence")
def get_daily_sentence():
    sentence = random.choice(sentences)
    return JSONResponse(content={"sentence": sentence})

@app.get("/login", response_class=FileResponse)
def serve_main():
    return BASE_DIR / "public" / "login.html"

@app.get("/profile", response_class=FileResponse)
def serve_main():
    return BASE_DIR / "public" / "profile.html"

# test.html 서빙
#@app.get("/test2", response_class=FileResponse)
#def serve_test2():
#    return BASE_DIR / "public" / "test2.html"
