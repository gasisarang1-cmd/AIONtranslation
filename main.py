import sys
import io
import time
import itertools
import numpy as np
from PIL import ImageGrab
from google import genai
from google.genai import types
from PyQt5.QtWidgets import (QApplication, QWidget, QPushButton, 
                             QTextEdit, QVBoxLayout, QHBoxLayout, 
                             QLabel, QSpinBox)
from PyQt5.QtCore import Qt, QRect, QTimer
from PyQt5.QtGui import QPainter, QBrush, QColor, QPen

# =========================================================
# Gemini API 키 목록 (5개 로테이션 설정)
# =========================================================
API_KEYS = [
    "AQ.Ab8RN6KxFr2blTx8G9ihWDkf_oRcU6GLXoSkGuUWvUPH1KInTg",
    "AQ.Ab8RN6IN-_oj4m5SYxmRCnEZTSdEVpFWGrMAzPOIHv3BzSr4Yg",
    "AQ.Ab8RN6Kew75CbQBJdn7LltIFJXMIOSPjJXFS_OmqUMw6O0oZsQ",
    "AQ.Ab8RN6L_92uzWEP5I5djNNbdfb6kLyMBf375rWq6dOwmaEhoJg",
    "AQ.Ab8RN6IEIy2W4qwLD0NqUxia-9HW_yhPaAs-HX4ZV2xyQnG3dA",
]

# API 키 순환 객체
KEY_CYCLE = itertools.cycle(API_KEYS)

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

class PersistentAutoTranslatorApp(QWidget):
    def __init__(self):
        super().__init__()
        self.target_coords = None
        self.prev_img_array = None
        self.is_processing = False
        
        # 지속적 자동 캡처 타이머
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.auto_capture_and_translate)
        
        self.initUI()

    def initUI(self):
        self.setWindowTitle("Gemini 미니 지속 번역기")
        self.setGeometry(100, 100, 380, 360)
        self.setWindowFlags(Qt.WindowStaysOnTopHint)

        layout = QVBoxLayout()

        # 1. 고정 캡처 영역 지정 버튼
        self.btn_select = QPushButton("1. 캡처 영역 지정 (1회 설정)", self)
        self.btn_select.setFixedHeight(40)
        self.btn_select.setStyleSheet("font-size: 13px; font-weight: bold; background-color: #2196F3; color: white;")
        self.btn_select.clicked.connect(self.select_area)
        layout.addWidget(self.btn_select)

        # 2. 캡처 반복 주기 설정
        timer_layout = QHBoxLayout()
        lbl_timer = QLabel("캡처 주기(초):", self)
        
        self.spin_interval = QSpinBox(self)
        self.spin_interval.setRange(2, 60)
        self.spin_interval.setValue(5)
        
        timer_layout.addWidget(lbl_timer)
        timer_layout.addWidget(self.spin_interval)
        layout.addLayout(timer_layout)

        # 3. 지속 캡처 시작/중지 버튼
        self.btn_toggle = QPushButton("2. 지정 영역 지속 캡처 시작", self)
        self.btn_toggle.setFixedHeight(40)
        self.btn_toggle.setEnabled(False)
        self.btn_toggle.setStyleSheet("font-size: 13px; font-weight: bold; background-color: #4CAF50; color: white;")
        self.btn_toggle.clicked.connect(self.toggle_auto_translate)
        layout.addWidget(self.btn_toggle)

        # 상태 안내
        self.lbl_status = QLabel("상태: 번역할 영역을 먼저 지정해 주세요.", self)
        self.lbl_status.setStyleSheet("color: #555555;")
        layout.addWidget(self.lbl_status)

        # 번역 결과창
        self.txt_result = QTextEdit(self)
        self.txt_result.setPlaceholderText("지정된 영역의 화면 변경이 감지되면 매끄러운 한국어 번역 결과가 표시됩니다.")
        self.txt_result.setReadOnly(True)
        layout.addWidget(self.txt_result)

        self.setLayout(layout)

    def select_area(self):
        if self.timer.isActive():
            self.toggle_auto_translate()

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
            self.lbl_status.setText(f"영역 고정 완료! ({coords[2]-coords[0]}x{coords[3]-coords[1]})")
            self.btn_toggle.setEnabled(True)
            self.prev_img_array = None

    def toggle_auto_translate(self):
        if self.timer.isActive():
            self.timer.stop()
            self.spin_interval.setEnabled(True)
            self.btn_select.setEnabled(True)
            self.btn_toggle.setText("2. 지정 영역 지속 캡처 시작")
            self.btn_toggle.setStyleSheet("font-size: 13px; font-weight: bold; background-color: #4CAF50; color: white;")
            self.lbl_status.setText("상태: 지속 캡처 중지됨")
        else:
            interval_ms = self.spin_interval.value() * 1000
            self.timer.start(interval_ms)
            self.spin_interval.setEnabled(False)
            self.btn_select.setEnabled(False)
            self.btn_toggle.setText("지속 캡처 중지")
            self.btn_toggle.setStyleSheet("font-size: 13px; font-weight: bold; background-color: #f44336; color: white;")
            self.lbl_status.setText(f"상태: 고정 영역을 {self.spin_interval.value()}초 간격으로 감지 중...")

    def auto_capture_and_translate(self):
        if self.is_processing or not self.target_coords:
            return

        # 1. 설정된 고정 영역 캡처
        img = ImageGrab.grab(bbox=self.target_coords)
        img_rgb = img.convert("RGB")
        curr_img_array = np.array(img_rgb)

        # 2. 화면 변화 감지
        if self.prev_img_array is not None:
            diff = np.mean(np.abs(curr_img_array.astype(float) - self.prev_img_array.astype(float)))
            if diff < 18.0:
                return

        self.prev_img_array = curr_img_array
        self.is_processing = True
        self.lbl_status.setText("상태: 영역 변화 감지! Gemini 분석 중...")

        buffer = io.BytesIO()
        img_rgb.save(buffer, format="JPEG", quality=90)
        image_bytes = buffer.getvalue()

        prompt = """
        너는 전문 번역가야.
        이미지 속에 있는 외국어(중국어, 영어 등)를 한국어로 매끄럽고 자연스럽게 번역해줘.

        [지침]
        1. 의성어, 의태어, 게임 용어, 문맥상의 의미를 고려해서 가장 자연스러운 한국어로 의역해줘.
        2. 오직 자연스럽게 번역된 한국어 텍스트만 깔끔하게 출력해줘.
        """

        # 등록된 키 개수만큼 로테이션 시도
        max_retries = len(API_KEYS)

        for attempt in range(max_retries):
            current_key = next(KEY_CYCLE)
            try:
                # 요청 시마다 현재 순번의 API 키로 클라이언트 생성
                client = genai.Client(api_key=current_key)
                
                # 모델명 수정: gemini-1.5-flash
                response = client.models.generate_content(
                    model='gemini-1.5-flash',
                    contents=[
                        types.Part.from_bytes(data=image_bytes, mime_type='image/jpeg'),
                        prompt
                    ],
                    config=types.GenerateContentConfig(
                        max_output_tokens=300,
                        temperature=0.7
                    )
                )
                self.txt_result.setText(response.text.strip())
                self.lbl_status.setText(f"상태: 고정 영역을 {self.spin_interval.value()}초 간격으로 감지 중...")
                break # 성공 시 루프 탈출

            except Exception as e:
                err_msg = str(e)
                if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
                    print(f"[429 감지] API 키({current_key[:10]}...) 한도 초과. 다음 키로 자동 전환합니다.")
                    if attempt < max_retries - 1:
                        self.lbl_status.setText(f"⚠️ 429 제한 발생. 다음 키로 재시도 중... ({attempt + 1}/{max_retries})")
                        QApplication.processEvents()
                        time.sleep(1)
                    else:
                        self.lbl_status.setText("⚠️ 등록된 모든 API 키의 사용 한도가 초과되었습니다.")
                else:
                    self.lbl_status.setText(f"오류 발생: {e}")
                    break
        
        self.is_processing = False

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = PersistentAutoTranslatorApp()
    ex.show()
    sys.exit(app.exec_())
