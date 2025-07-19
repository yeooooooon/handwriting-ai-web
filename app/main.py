# # main.py
# from fastapi import FastAPI

# app = FastAPI()

# @app.get("/")
# def read_root():
#     return {"message": "AI 손글씨 교정 API입니다"}

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from io import BytesIO
from PIL import Image
import os

from app.handwriting_feedback_api import router as handwriting_router

app = FastAPI()
app.include_router(handwriting_router)

# # ✅ 하위 FastAPI 앱 통합 (라우트 등록)
#app.mount("/evaluate", handwriting_app)

# 정적 파일(css, js 등) 서빙
app.mount("/static", StaticFiles(directory="app/css"), name="static")

# index.html 서빙
@app.get("/")
def serve_index():
    return FileResponse(os.path.join("app/public", "index.html"))

# test.html 서빙
@app.get("/test")
def serve_test():
    return FileResponse(os.path.join("app/public", "test.html"))