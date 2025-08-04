from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse
from PIL import Image, ImageDraw, ImageFont
from skimage.metrics import structural_similarity as ssim
from skimage.transform import resize
from app.ai_feedback import generate_ai_feedback
import easyocr
import numpy as np
import os
import cv2

router = APIRouter()

reader = easyocr.Reader(['ko'], gpu=False)

font_path = os.path.join(os.path.dirname(__file__), "fonts", "NotoSansKR-Regular.ttf")
if not os.path.exists(font_path):
    raise FileNotFoundError(f"폰트 파일을 찾을 수 없습니다: {font_path}")

standard_font = ImageFont.truetype(font_path, size=48)
resize_shape = (128, 128)
MAX_CHAR_LIMIT = 20  # 최대 글자 수 제한

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
async def evaluate_handwriting(file: UploadFile = File(...), target: str = Form(...)):
    if file.content_type not in ("image/png", "image/jpeg"):
        raise HTTPException(status_code=400, detail="이미지 파일만 업로드 가능합니다.")

    image = Image.open(file.file).convert("RGB")
    gray = np.array(image.convert("L"))
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    char_images = []
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        if w * h < 100:
            continue
        char_crop = binary[y:y+h, x:x+w]
        char_images.append((x, char_crop))

    char_images = [img for _, img in sorted(char_images, key=lambda x: x[0])]

    text_result = reader.readtext(np.array(image), detail=0)
    recognized_text = ''.join(text_result) if text_result else ""
    clean_text = ''.join([c for c in recognized_text if c.strip()])
    target_clean = ''.join([c for c in target if c.strip()])

    if clean_text != target_clean:
        return JSONResponse(content={
            "match": False,
            "message": "문장이 일치하지 않아 채점이 불가합니다.",
            "recognized_text": clean_text
        })

    total_score = 0
    score_list = []
    perfect_chars, okay_chars, poor_chars = [], [], []
    feedback_list = []

    length = min(len(clean_text), len(char_images), MAX_CHAR_LIMIT)
    if length == 0:
        return JSONResponse(content={
            "score": 0,
            "feedback": "글자를 인식하지 못했습니다.",
            "corrected_text": "",
        })

    corrected_text = ""

    for i in range(length):
        ch = clean_text[i]
        char_img = char_images[i]

        char_resized = resize(char_img, resize_shape, preserve_range=True).astype("uint8")

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

    if perfect_chars:
        feedback_list.append(f"{', '.join(repr(c) for c in perfect_chars)} 은(는) 완벽합니다.")
    if okay_chars:
        feedback_list.append(f"{', '.join(repr(c) for c in okay_chars)} 은(는) 조금 더 다듬으면 좋습니다.")
    if poor_chars:
        feedback_list.append(f"{', '.join(repr(c) for c in poor_chars)} 은(는) 기준과 많이 다릅니다.")

    avg_score = total_score / length if length > 0 else 0

    score_table_html = format_score_list_html(score_list)
    feedback_msg = "<br>".join(feedback_list)
    feedback_msg += "<br><br><strong>점수 목록:</strong><br>" + score_table_html

    score_dict = {}
    for item in score_list:
        try:
            ch, score = item.split(":")
            ch = ch.strip().strip("'")
            score = int(score.strip().replace("점", ""))
            score_dict[ch] = score
        except:
            continue

    ai_feedback = generate_ai_feedback(clean_text, score_dict)

    return JSONResponse(content={
        "recognized_text": clean_text,
        "corrected_text": corrected_text,
        "score": round(avg_score, 2),
        "feedback": feedback_msg,
        "ai_feedback": ai_feedback,
        "match": True
    })