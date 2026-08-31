import sys
from rapidocr_onnxruntime import RapidOCR
from PIL import ImageGrab
from google import genai
from PyQt5.QtWidgets import QApplication, QWidget, QLabel, QVBoxLayout, QPushButton
from PyQt5.QtCore import Qt, QRect
from PyQt5.QtGui import QPainter, QBrush, QColor, QPen

# =========================================================
# Gemini API 설정 (발급받은 API 키를 여기에 입력하세요)
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
        print("OCR 엔진 및 Gemini 클라이언트 로딩 중...")
        # RapidOCR 초기화 (기본적으로 중국어/영어 모델 자동 포함)
        self.ocr_engine = RapidOCR()
        
        self.ai_client = genai.Client(api_key=GEMINI_API_KEY)
        
        self.initUI()

    def initUI(self):
        self.setWindowTitle("Gemini 기반 중국어 화면 번역기")
        self.setGeometry(300, 300, 450, 280)
        self.setWindowFlags(Qt.WindowStaysOnTopHint)

        layout = QVBoxLayout()

        self.btn_capture = QPushButton("영역 선택 및 Gemini 번역", self)
        self.btn_capture.setFixedHeight(40)
        self.btn_capture.clicked.connect(self.start_capture)
        layout.addWidget(self.btn_capture)

        self.lbl_original = QLabel("인식된 중국어: -", self)
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
            img.save("temp_capture.png")
            self.process_ocr_and_translate("temp_capture.png")

    def process_ocr_and_translate(self, img_path):
        # RapidOCR 인식 수행
        result, _ = self.ocr_engine(img_path)
        
        extracted_text = ""
        if result:
            # 인식 결과 추출 (bbox, text, score 중 text만 결합)
            extracted_text = " ".join([line[1] for line in result])
        
        if not extracted_text.strip():
            self.lbl_original.setText("인식된 중국어: (인식된 글자 없음)")
            self.lbl_translated.setText("Gemini 번역 결과: -")
            return

        self.lbl_original.setText(f"인식된 중국어: {extracted_text}")
        self.lbl_translated.setText("Gemini 번역 중...")
        QApplication.processEvents()

        try:
            prompt = f"다음 중국어 문장을 문맥에 맞게 매끄러운 한국어로 번역해줘. 오직 번역 결과만 출력해:\n{extracted_text}"
            response = self.ai_client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
            )
            self.lbl_translated.setText(f"Gemini 번역 결과:\n{response.text.strip()}")
        except Exception as e:
            self.lbl_translated.setText(f"번역 오류 발생: {e}")

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = GeminiTranslatorApp()
    ex.show()
    sys.exit(app.exec_())
