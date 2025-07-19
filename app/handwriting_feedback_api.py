from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import easyocr
import numpy as np
import base64
import cv2
from skimage.metrics import structural_similarity as ssim
import os

router = APIRouter()

# EasyOCR: 한글만 인식
reader = easyocr.Reader(['ko'], gpu=False)

# 기준 폰트 설정 (NotoSansKR)
font_path = os.path.join(os.path.dirname(__file__), "fonts", "NotoSansKR-Regular.ttf")
if not os.path.exists(font_path):
    raise FileNotFoundError(f"폰트 파일을 찾을 수 없습니다: {font_path}")

standard_font = ImageFont.truetype(font_path, size=48)

@router.post("/evaluate")
async def evaluate_handwriting(file: UploadFile = File(...)):
    if file.content_type not in ("image/png", "image/jpeg"):
        raise HTTPException(status_code=400, detail="이미지 파일만 업로드 가능합니다.")

    # 이미지 로딩 및 이진화 처리
    image = Image.open(file.file).convert("RGB")
    gray = np.array(image.convert("L"))
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    # 외곽선 탐지로 글자 영역 추출
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    char_images = []
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        if w * h < 100:
            continue
        char_crop = binary[y:y+h, x:x+w]
        char_images.append((x, char_crop))

    # 왼쪽부터 정렬
    char_images = [img for _, img in sorted(char_images, key=lambda x: x[0])]

    # EasyOCR로 텍스트 인식
    text_result = reader.readtext(np.array(image), detail=0)
    recognized_text = ''.join(text_result) if text_result else ""
    clean_text = ''.join([c for c in recognized_text if c.strip()])

    # 교정 이미지 생성
    corrected_image = Image.new("RGB", image.size, (255, 255, 255))
    draw = ImageDraw.Draw(corrected_image)

    # 피드백 생성
    total_score = 0.0
    feedback_list = []

    length = min(len(clean_text), len(char_images))
    for i in range(length):
        ch = clean_text[i]
        char_img = char_images[i]

        h, w = char_img.shape
        font_img = Image.new("L", (w, h), color=255)
        d = ImageDraw.Draw(font_img)
        d.text((0, 0), ch, font=standard_font, fill=0)

        font_arr = np.array(font_img)
        try:
            sim = ssim(char_img, font_arr)
        except:
            sim = np.mean(char_img == font_arr)

        score = sim * 100
        total_score += score

        if ch.strip():  # 공백 제외
            if score < 70:
                feedback_list.append(f"'{ch}' 글자가 기준과 많이 다릅니다.")
            elif score < 90:
                feedback_list.append(f"'{ch}' 글자를 조금 더 다듬으면 좋습니다.")

        # 이미지에 문자 쓰기
        draw.text((10 + i * 50, 10), ch, font=standard_font, fill=(0, 0, 0))

    # 평균 점수 및 피드백
    avg_score = total_score / length if length > 0 else 0
    feedback_msg = " ".join(feedback_list) if feedback_list else "대체로 잘 쓰셨습니다."

    # base64로 이미지 전송
    buf = BytesIO()
    corrected_image.save(buf, format="PNG")
    img_base64 = base64.b64encode(buf.getvalue()).decode("utf-8")

    return JSONResponse(content={
        "recognized_text": clean_text,
        "score": round(avg_score, 2),
        "feedback": feedback_msg,
        "corrected_image": f"data:image/png;base64,{img_base64}"
    })
