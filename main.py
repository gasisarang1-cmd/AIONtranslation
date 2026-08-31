import sys
import io
import itertools
from PIL import ImageGrab
from google import genai
from google.genai import types
from PyQt5.QtWidgets import (QApplication, QWidget, QPushButton, 
                             QTextEdit, QVBoxLayout, QLabel)
from PyQt5.QtCore import Qt, QRect
from PyQt5.QtGui import QPainter, QBrush, QColor, QPen

# =========================================================
# Gemini API 키 목록 (5개 로테이션)
# =========================================================
API_KEYS = [
    "AQ.Ab8RN6KxFr2blTx8G9ihWDkf_oRcU6GLXoSkGuUWvUPH1KInTg",
    "AQ.Ab8RN6IN-_oj4m5SYxmRCnEZTSdEVpFWGrMAzPOIHv3BzSr4Yg",
    "AQ.Ab8RN6Kew75CbQBJdn7LltIFJXMIOSPjJXFS_OmqUMw6O0oZsQ",
    "AQ.Ab8RN6L_92uzWEP5I5djNNbdfb6kLyMBf375rWq6dOwmaEhoJg",
    "AQ.Ab8RN6IEIy2W4qwLD0NqUxia-9HW_yhPaAs-HX4ZV2xyQnG3dA",
]

KEY_CYCLE = itertools.cycle(API_KEYS)

class ScreenCaptureTool(QWidget):
    """화면 드래그로 영역을 지정하는 투명 창"""
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

class ManualTranslatorApp(QWidget):
    """메인 번역기 프로그램 UI 및 API 연동"""
    def __init__(self):
        super().__init__()
        self.target_coords = None
        self.initUI()

    def initUI(self):
        self.setWindowTitle("Gemini 원클릭 수동 번역기")
        self.setGeometry(100, 100, 400, 350)
        self.setWindowFlags(Qt.WindowStaysOnTopHint)

        layout = QVBoxLayout()

        # 1. 영역 지정 버튼
        self.btn_select = QPushButton("1. 캡처 영역 지정 (1회)", self)
        self.btn_select.setFixedHeight(40)
        self.btn_select.setStyleSheet("font-size: 13px; font-weight: bold; background-color: #2196F3; color: white;")
        self.btn_select.clicked.connect(self.select_area)
        layout.addWidget(self.btn_select)

        # 2. 캡처 및 Gemini 전달 버튼
        self.btn_capture = QPushButton("2. 지정 영역 캡처 후 번역 요청", self)
        self.btn_capture.setFixedHeight(45)
        self.btn_capture.setEnabled(False)
        self.btn_capture.setStyleSheet("font-size: 14px; font-weight: bold; background-color: #4CAF50; color: white;")
        self.btn_capture.clicked.connect(self.capture_and_translate)
        layout.addWidget(self.btn_capture)

        # 상태 표시 레이블
        self.lbl_status = QLabel("상태: 먼저 번역할 영역을 지정해 주세요.", self)
        self.lbl_status.setStyleSheet("color: #555555;")
        layout.addWidget(self.lbl_status)

        # 결과 출력 창
        self.txt_result = QTextEdit(self)
        self.txt_result.setPlaceholderText("버튼을 누르면 해당 영역을 캡처하여 Gemini에게 보낸 뒤, 해석된 한국어 결과를 여기에 표시합니다.")
        self.txt_result.setReadOnly(True)
        layout.addWidget(self.txt_result)

        self.setLayout(layout)

    def select_area(self):
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
            self.lbl_status.setText(f"영역 설정 완료! ({coords[2]-coords[0]}x{coords[3]-coords[1]})")
            self.btn_capture.setEnabled(True)

    def capture_and_translate(self):
        if not self.target_coords:
            return

        self.btn_capture.setEnabled(False)
        self.lbl_status.setText("상태: 이미지 캡처 후 Gemini에 전달 중...")
        QApplication.processEvents()

        # 1. 화면 지정 영역 캡처 및 화질 보완 (2배 확대)
        img = ImageGrab.grab(bbox=self.target_coords)
        img_rgb = img.convert("RGB")
        w, h = img_rgb.size
        img_rgb = img_rgb.resize((w * 2, h * 2))

        buffer = io.BytesIO()
        img_rgb.save(buffer, format="JPEG", quality=95)
        image_bytes = buffer.getvalue()

        # 2. Gemini 프롬프트 작성
        prompt = """
        당신은 한국어와 중국어가 완벽한 게임 전문 번역가입니다.
        1. 이미지 안에 있는 모든 텍스트(중국어, 한자 닉네임, 한글, 숫자)를 정확히 읽어내세요.
        2. 한자 아이디나 닉네임은 한국식 한자음(예: 荷花小仙 -> 연화소선)으로 치환하거나 자연스럽게 의역하세요.
        3. 어떠한 부연 설명이나 인사말도 출력하지 말고, 오직 번역된 결과만 깔끔하게 줄바꿈하여 출력하세요.
        """

        max_retries = len(API_KEYS)
        success = False

        # 3. API 호출 및 해석본 수신
        for attempt in range(max_retries):
            current_key = next(KEY_CYCLE)
            try:
                client = genai.Client(api_key=current_key)
                
                response = client.models.generate_content(
                    model='gemini-3.6-flash',
                    contents=[
                        types.Part.from_bytes(data=image_bytes, mime_type='image/jpeg'),
                        prompt
                    ],
                    config=types.GenerateContentConfig(
                        max_output_tokens=400,
                        temperature=0.2
                    )
                )
                
                # 4. 받아온 번역 결과를 텍스트 창에 출력
                result_text = response.text.strip() if response.text else "인식된 텍스트가 없습니다."
                self.txt_result.setText(result_text)
                self.lbl_status.setText("상태: 번역 완료!")
                success = True
                break

            except Exception as e:
                err_msg = str(e)
                if attempt < max_retries - 1:
                    self.lbl_status.setText(f"⚠️ 요청 지연. 다른 키로 재시도 중... ({attempt + 1}/{max_retries})")
                    QApplication.processEvents()

        if not success:
            self.lbl_status.setText("⚠️ 번역 실패. 다시 시도해 주세요.")

        self.btn_capture.setEnabled(True)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = ManualTranslatorApp()
    ex.show()
    sys.exit(app.exec_())
