import sys
import os
from PIL import ImageGrab
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
        print("Gemini 클라이언트 로딩 중...")
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
        self.lbl_original.setText("이미지 분석 및 번역 중...")
        self.lbl_translated.setText("Gemini 처리 중...")
        QApplication.processEvents()

        try:
            # 캡처한 이미지를 Gemini Vision 모델에 직접 전달
            with open(img_path, 'rb') as f:
                image_bytes = f.read()

            prompt = "이 이미지에 있는 외국어(중국어 등) 글자를 읽고, 매끄러운 한국어로 번역해줘. 오직 번역된 한국어 결과만 출력해."
            
            response = self.ai_client.models.generate_content(
                model='gemini-2.5-flash',
                contents=[
                    types.Part.from_bytes(data=image_bytes, mime_type='image/png'),
                    prompt
                ]
            )
            self.lbl_original.setText("상태: 분석 완료")
            self.lbl_translated.setText(f"Gemini 번역 결과:\n{response.text.strip()}")
        except Exception as e:
            self.lbl_translated.setText(f"번역 오류 발생: {e}")

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = GeminiTranslatorApp()
    ex.show()
    sys.exit(app.exec_())
