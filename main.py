import sys
import os
import io
from PIL import ImageGrab, Image
from google import genai
from google.genai import types
from PyQt5.QtWidgets import QApplication, QWidget, QLabel, QVBoxLayout, QPushButton
from PyQt5.QtCore import Qt, QRect
from PyQt5.QtGui import QPainter, QBrush, QColor, QPen

# =========================================================
# Gemini API 설정
GEMINI_API_KEY = "AQ.Ab8RN6IN-_oj4m5SYxmRCnEZTSdEVpFWGrMAzPOIHv3BzSr4Yg"
# =========================================================

class ScreenCaptureTool(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setWindowOpacity(0.3)
        self.setCursor(Qt.CrossCursor)
        
        screen_geometry = QApplication.primaryScreen().geometry()
        self.setGeometry(screen_geometry)
        
        self.begin = None
        self.end = None
        self.is_selecting = False

    def paintEvent(self, event):
        if self.is_selecting and self.begin and self.end:
            painter = QPainter(self)
            painter.setPen(QPen(QColor(255, 0, 0), 2))
            painter.setBrush(QBrush(QColor(255, 255, 255, 100)))
            rect = QRect(self.begin, self.end)
            painter.drawRect(rect.normalized())

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.begin = event.pos()
            self.end = self.begin
            self.is_selecting = True
            self.update()

    def mouseMoveEvent(self, event):
        if self.is_selecting:
            self.end = event.pos()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.is_selecting:
            self.end = event.pos()
            self.is_selecting = False
            self.close()

    def get_coordinates(self):
        if self.begin and self.end:
            x1, y1 = self.begin.x(), self.begin.y()
            x2, y2 = self.end.x(), self.end.y()
            return (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))
        return None

class GeminiTranslatorApp(QWidget):
    def __init__(self):
        super().__init__()
        self.ai_client = genai.Client(api_key=GEMINI_API_KEY)
        self.initUI()

    def initUI(self):
        self.setWindowTitle("Gemini 기반 화면 번역기")
        self.setGeometry(300, 300, 450, 280)
        self.setWindowFlags(Qt.WindowStaysOnTopHint)

        layout = QVBoxLayout()

        self.btn_capture = QPushButton("영역 선택 및 Gemini 번역", self)
        self.btn_capture.setFixedHeight(40)
        self.btn_capture.clicked.connect(self.start_capture)
        layout.addWidget(self.btn_capture)

        self.lbl_original = QLabel("상태: 대기 중", self)
        self.lbl_original.setWordWrap(True)
        layout.addWidget(self.lbl_original)

        self.lbl_translated = QLabel("Gemini 번역 결과: -", self)
        self.lbl_translated.setWordWrap(True)
        layout.addWidget(self.lbl_translated)

        self.setLayout(layout)

    def start_capture(self):
        self.hide()
        self.cap_tool = ScreenCaptureTool()
        self.cap_tool.show()
        
        loop = QApplication.instance()
        while self.cap_tool.isVisible():
            loop.processEvents()
            
        coords = self.cap_tool.get_coordinates()
        self.show()

        if coords and (coords[2] - coords[0] > 5) and (coords[3] - coords[1] > 5):
            img = ImageGrab.grab(bbox=coords)
            img_path = "temp_capture.png"
            img.save(img_path)
            self.process_vision_translate(img_path)

    def process_vision_translate(self, img_path):
        self.lbl_original.setText("분석 중...")
        self.lbl_translated.setText("번역 중...")
        QApplication.processEvents()

        try:
            # 1. 이미지용량 압축 (JPEG 경량화로 업로드 속도 단축)
            with Image.open(img_path) as img:
                img = img.convert("RGB")
                buffer = io.BytesIO()
                img.save(buffer, format="JPEG", quality=80)
                image_bytes = buffer.getvalue()

            prompt = "이미지 속 외국어를 즉시 한국어로 번역해서 결과 문장만 출력해."
            
            # 2. 3.6-flash 모델 + 연산 제어로 속도 최적화
            response = self.ai_client.models.generate_content(
                model='gemini-3.6-flash',
                contents=[
                    types.Part.from_bytes(data=image_bytes, mime_type='image/jpeg'),
                    prompt
                ],
                config=types.GenerateContentConfig(
                    max_output_tokens=300,
                    temperature=0.1
                )
            )
            self.lbl_original.setText("상태: 완료")
            self.lbl_translated.setText(f"Gemini 번역 결과:\n{response.text.strip()}")
        except Exception as e:
            self.lbl_translated.setText(f"번역 오류 발생: {e}")

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = GeminiTranslatorApp()
    ex.show()
    sys.exit(app.exec_())
