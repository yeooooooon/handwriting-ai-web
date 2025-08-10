from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import easyocr
import numpy as np
import base64
import cv2
from skimage.metrics import structural_similarity as ssim
from skimage.transform import resize
from app.ai_feedback import generate_ai_feedback
import os

router = APIRouter()

reader = easyocr.Reader(['ko'], gpu=False)

# 기준 폰트 설정
font_path = os.path.join(os.path.dirname(__file__), "fonts", "NotoSansKR-Regular.ttf")
if not os.path.exists(font_path):
    raise FileNotFoundError(f"폰트 파일을 찾을 수 없습니다: {font_path}")

standard_font = ImageFont.truetype(font_path, size=48)
resize_shape = (128, 128)
MAX_CHAR_LIMIT = 40  # 최대 글자 수 제한

# 점수 테이블을 HTML로 포맷
def format_score_list_html(score_list):
    rows = []
    total = len(score_list)
    for i in range(0, total, 3):
        row = score_list[i:i+3]
        cells = []
        for j, item in enumerate(row):
            is_last = (i + j == total - 1)
            display = item if is_last else f"{item},"
            cells.append(f"<td style='padding-right: 2em;'>{display}</td>")
        rows.append(f"<tr>{''.join(cells)}</tr>")
    return "<table style='border-spacing: 4px 8px; font-family: sans-serif; font-size: 16px;'>" + "".join(rows) + "</table>"

@router.post("/evaluate")
async def evaluate_handwriting(file: UploadFile = File(...)):
    if file.content_type not in ("image/png", "image/jpeg"):
        raise HTTPException(status_code=400, detail="이미지 파일만 업로드 가능합니다.")

    # 1. 원본 이미지 처리 및 이진화
    image = Image.open(file.file).convert("RGB")
    gray = np.array(image.convert("L"))
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    # 2. 글자 외곽선 추출
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    char_images = []
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        if w * h < 100:
            continue
        char_crop = binary[y:y+h, x:x+w]
        char_images.append((x, char_crop))

    # 3. 왼쪽부터 정렬
    char_images = [img for _, img in sorted(char_images, key=lambda x: x[0])]

    # 4. OCR로 텍스트 인식
    text_result = reader.readtext(np.array(image), detail=0)
    recognized_text = ''.join(text_result) if text_result else ""
    clean_text = ''.join([c for c in recognized_text if c.strip()])

    # 5. 최대 글자 수 초과 시 잘라내기
    notify_exceeded = False
    if len(clean_text) > MAX_CHAR_LIMIT:
        clean_text = clean_text[:MAX_CHAR_LIMIT]
        notify_exceeded = True

    # 6. 교정용 이미지 캔버스 사이즈 계산
    char_width = 60
    padding = 40
    line_height = 120
    canvas_width = padding * 2 + len(clean_text) * char_width
    canvas_height = line_height

    total_score = 0
    score_list = []
    perfect_chars, okay_chars, poor_chars = [], [], []
    feedback_list = []

    length = min(len(clean_text), len(char_images), MAX_CHAR_LIMIT)
    if length == 0:
        return JSONResponse(content={
            "score": 0,
            "feedback": "글자를 인식하지 못했습니다.",
            "corrected_image": "",
        })

    corrected_text = ""

    # 7. 각 글자 비교 및 점수 계산
    for i in range(length):
        ch = clean_text[i]
        char_img = char_images[i]

        # 사용자 글자 리사이즈
        char_resized = resize(char_img, resize_shape, preserve_range=True).astype("uint8")

        # 기준 글자 이미지 생성
        font_img = Image.new("L", resize_shape, color=255)
        draw_font = ImageDraw.Draw(font_img)
        bbox = standard_font.getbbox(ch)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        x = (resize_shape[1] - text_width) // 2
        y = (resize_shape[0] - text_height) // 2
        draw_font.text((x, y), ch, font=standard_font, fill=0)
        font_arr = np.array(font_img)

        try:
            sim = ssim(char_resized, font_arr)
        except:
            sim = 0.0

        # SSIM → 점수 보정
        def scale_score(sim):
            scaled = (sim - 0.1) / (0.6 - 0.1) * 50 + 50
            return max(0, min(100, scaled))

        score = int(scale_score(sim))
        total_score += score
        score_list.append(f"'{ch}': {int(score)}점")

        if ch.strip():
            if score < 70:
                poor_chars.append(ch)
            elif score < 90:
                okay_chars.append(ch)
            else:
                perfect_chars.append(ch)

        corrected_text += ch

    # 8. 피드백 구성
    if perfect_chars:
        feedback_list.append(f"{', '.join(repr(c) for c in perfect_chars)} 은(는) 완벽합니다.")
    if okay_chars:
        feedback_list.append(f"{', '.join(repr(c) for c in okay_chars)} 은(는) 조금 더 다듬으면 좋습니다.")
    if poor_chars:
        feedback_list.append(f"{', '.join(repr(c) for c in poor_chars)} 은(는) 기준과 많이 다릅니다.")

    avg_score = total_score / length if length > 0 else 0

    # 9. HTML 피드백 메시지 구성
    score_table_html = format_score_list_html(score_list)
    feedback_msg = "<br>".join(feedback_list)
    if notify_exceeded:
        feedback_msg += "<br><br><strong>⚠️ 최대 20글자까지만 분석됩니다. 이후 글자는 제외되었습니다.</strong>"
    feedback_msg += "<br><br><strong>점수 목록:</strong><br>" + score_table_html

    # 10. AI 피드백 생성을 위한 점수 dict 구성
    score_dict = {}
    for item in score_list:
        try:
            ch, score = item.split(":")
            ch = ch.strip().strip("'")
            score = int(score.strip().replace("점", ""))
            score_dict[ch] = score
        except:
            continue

    # 11. AI 피드백 생성 (LLM 연동)
    ai_feedback = generate_ai_feedback(clean_text, score_dict)

    # 12. 최종 결과 반환
    return JSONResponse(content={
        "recognized_text": clean_text,
        "corrected_text": corrected_text,
        "score": round(avg_score, 2),
        "feedback": feedback_msg,
        "ai_feedback": ai_feedback,
    })
