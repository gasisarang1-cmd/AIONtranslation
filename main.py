import sys
import io
from PIL import ImageGrab, Image
from google import genai
from google.genai import types
from PyQt5.QtWidgets import (QApplication, QWidget, QPushButton, 
                             QTextEdit, QVBoxLayout, QMessageBox)
from PyQt5.QtCore import Qt, QRect
from PyQt5.QtGui import QPainter, QBrush, QColor, QPen

# =========================================================
# Gemini API 키 설정
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

class MiniTranslatorApp(QWidget):
    def __init__(self):
        super().__init__()
        self.ai_client = genai.Client(api_key=GEMINI_API_KEY)
        self.initUI()

    def initUI(self):
        self.setWindowTitle("Gemini 캡처 번역")
        self.setGeometry(100, 100, 320, 220)
        self.setWindowFlags(Qt.WindowStaysOnTopHint) # 항상 위에 표시

        layout = QVBoxLayout()

        # 1. 캡처 시작 버튼
        self.btn_capture = QPushButton("📸 화면 영역 캡처 번역", self)
        self.btn_capture.setFixedHeight(45)
        self.btn_capture.setStyleSheet("font-size: 14px; font-weight: bold; background-color: #4CAF50; color: white;")
        self.btn_capture.clicked.connect(self.start_capture)
        layout.addWidget(self.btn_capture)

        # 2. 번역 결과 출력 창 (복사 가능하도록 TextEdit 적용)
        self.txt_result = QTextEdit(self)
        self.txt_result.setPlaceholderText("캡처 버튼을 누르고 화면의 글자 영역을 드래그하세요.")
        self.txt_result.setReadOnly(True)
        layout.addWidget(self.txt_result)

        self.setLayout(layout)

    def start_capture(self):
        self.hide() # 캡처할 때 앱 창 숨김
        self.cap_tool = ScreenCaptureTool()
        self.cap_tool.show()
        
        loop = QApplication.instance()
        while self.cap_tool.isVisible():
            loop.processEvents()
            
        coords = self.cap_tool.get_coordinates()
        self.show() # 캡처 끝나면 앱 창 다시 표시

        if coords and (coords[2] - coords[0] > 10) and (coords[3] - coords[1] > 10):
            img = ImageGrab.grab(bbox=coords)
            self.translate_image(img)

    def translate_image(self, img):
        self.txt_result.setText("⚡ Gemini 분석 및 번역 중...")
        QApplication.processEvents()

        try:
            # 이미지 압축 전송
            img_rgb = img.convert("RGB")
            buffer = io.BytesIO()
            img_rgb.save(buffer, format="JPEG", quality=80)
            image_bytes = buffer.getvalue()

            prompt = "이미지 속에 있는 중국어/외국어를 한국어로 매끄럽게 번역해줘. 오직 번역된 결과 한국어 문장만 출력해."

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
            
            # 결과 표시
            self.txt_result.setText(response.text.strip())
            
        except Exception as e:
            self.txt_result.setText(f"오류 발생: {e}")

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = MiniTranslatorApp()
    ex.show()
    sys.exit(app.exec_())
