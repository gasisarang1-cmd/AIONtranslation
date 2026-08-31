import sys
import os
import io
import numpy as np
from PIL import ImageGrab, Image
from google import genai
from google.genai import types
from PyQt5.QtWidgets import QApplication, QWidget, QLabel, QVBoxLayout, QPushButton, QHBoxLayout
from PyQt5.QtCore import Qt, QRect, QTimer
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
        self.target_coords = None
        self.prev_img_array = None
        self.is_processing = False
        
        # 실시간 캡처용 타이머 설정 (1500ms = 1.5초 주기)
        self.timer = QTimer(self)
        self.timer.setInterval(4000)
        self.timer.timeout.connect(self.capture_and_translate)
        
        self.initUI()

    def initUI(self):
        self.setWindowTitle("Gemini 실시간 화면 번역기")
        self.setGeometry(300, 300, 450, 300)
        self.setWindowFlags(Qt.WindowStaysOnTopHint)

        layout = QVBoxLayout()

        # 버튼 레이아웃
        btn_layout = QHBoxLayout()
        
        self.btn_select = QPushButton("영역 지정", self)
        self.btn_select.setFixedHeight(40)
        self.btn_select.clicked.connect(self.select_area)
        btn_layout.addWidget(self.btn_select)

        self.btn_toggle = QPushButton("실시간 번역 시작", self)
        self.btn_toggle.setFixedHeight(40)
        self.btn_toggle.setEnabled(False)
        self.btn_toggle.clicked.connect(self.toggle_realtime)
        btn_layout.addWidget(self.btn_toggle)

        layout.addLayout(btn_layout)

        self.lbl_status = QLabel("상태: 영역을 지정해 주세요.", self)
        self.lbl_status.setWordWrap(True)
        layout.addWidget(self.lbl_status)

        self.lbl_translated = QLabel("Gemini 번역 결과: -", self)
        self.lbl_translated.setWordWrap(True)
        layout.addWidget(self.lbl_translated)

        self.setLayout(layout)

    def select_area(self):
        if self.timer.isActive():
            self.toggle_realtime() # 영역 다시 잡을 땐 실시간 중지

        self.hide()
        self.cap_tool = ScreenCaptureTool()
        self.cap_tool.show()
        
        loop = QApplication.instance()
        while self.cap_tool.isVisible():
            loop.processEvents()
            
        coords = self.cap_tool.get_coordinates()
        self.show()

        if coords and (coords[2] - coords[0] > 10) and (coords[3] - coords[1] > 10):
            self.target_coords = coords
            self.lbl_status.setText(f"영역 설정 완료! (크기: {coords[2]-coords[0]}x{coords[3]-coords[1]})")
            self.btn_toggle.setEnabled(True)
            self.prev_img_array = None

    def toggle_realtime(self):
        if self.timer.isActive():
            self.timer.stop()
            self.btn_toggle.setText("실시간 번역 시작")
            self.lbl_status.setText("상태: 실시간 번역 일시정지")
        else:
            self.timer.start()
            self.btn_toggle.setText("실시간 번역 중지")
            self.lbl_status.setText("상태: 실시간 감지 중...")

    def capture_and_translate(self):
        # 이미 번역 API를 처리 중이면 중복 요청 방지
        if self.is_processing or not self.target_coords:
            return

        img = ImageGrab.grab(bbox=self.target_coords)
        img_rgb = img.convert("RGB")
        curr_img_array = np.array(img_rgb)

        # 1. 화면 변화 감지 (이전 이미지와 픽셀 차이 계산)
        if self.prev_img_array is not None:
            # 픽셀값 차이의 평균을 계산
            diff = np.mean(np.abs(curr_img_array.astype(float) - self.prev_img_array.astype(float)))
            if diff < 15.0: # 변화가 거의 없으면 API 통신 건너뜀 (속도/비용 최적화)
                return

        self.prev_img_array = curr_img_array
        self.is_processing = True
        self.lbl_status.setText("상태: 새 글자 감지! 번역 중...")

        # 2. 이미지 압축 및 API 전송
        buffer = io.BytesIO()
        img_rgb.save(buffer, format="JPEG", quality=75)
        image_bytes = buffer.getvalue()

        try:
            prompt = "이미지 속 중국어/외국어를 한국어로 번역해. 결과 문장만 짧고 정확하게 출력해."
            
            response = self.ai_client.models.generate_content(
                model='gemini-3.6-flash',
                contents=[
                    types.Part.from_bytes(data=image_bytes, mime_type='image/jpeg'),
                    prompt
                ],
                config=types.GenerateContentConfig(
                    max_output_tokens=200,
                    temperature=0.1
                )
            )
            self.lbl_translated.setText(f"Gemini 번역 결과:\n{response.text.strip()}")
            self.lbl_status.setText("상태: 실시간 감지 중...")
        except Exception as e:
            self.lbl_status.setText(f"오류: {e}")
        finally:
            self.is_processing = False

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = GeminiTranslatorApp()
    ex.show()
    sys.exit(app.exec_())
