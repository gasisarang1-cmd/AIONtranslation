import sys
import itertools
import time

from PIL import ImageGrab
from google import genai

from PyQt5.QtWidgets import (
    QApplication,
    QWidget,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QLabel,
    QMessageBox,
    QHBoxLayout,
)
from PyQt5.QtCore import Qt, QRect, QPainter, QBrush, QColor, QPen, QThread, pyqtSignal


# =========================================================
# Gemini API 키 5개
# =========================================================
# 사용자가 방금 제공한 5개 키를 그대로 사용합니다.
API_KEYS = [
    "AQ.Ab8RN6KxFr2blTx8G9ihWDkf_oRcU6GLXoSkGuUWvUPH1KInTg",
    "AQ.Ab8RN6IN-_oj4m5SYxmRCnEZTSdEVpFWGrMAzPOIHv3BzSr4Yg",
    "AQ.Ab8RN6Kew75CbQBJdn7LltIFJXMIOSPjJXFS_OmqUMw6O0oZsQ",
    "AQ.Ab8RN6L_92uzWEP5I5djNNbdfb6kLyMBf375rWq6dOwmaEhoJg",
    "AQ.Ab8RN6IEIy2W4qwLD0NqUxia-9HW_yhPaAs-HX4ZV2xyQnG3dA",
]

MODEL_NAME = "gemini-2.5-flash"


class ScreenCaptureTool(QWidget):
    """마우스로 화면에서 번역 영역을 지정하는 투명 창."""

    def __init__(self):
        super().__init__()

        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
        )
        self.setWindowOpacity(0.30)
        self.setCursor(Qt.CrossCursor)

        self.setGeometry(QApplication.desktop().geometry())

        self.begin = None
        self.end = None
        self.is_selecting = False

    def paintEvent(self, event):
        painter = QPainter(self)

        if self.is_selecting and self.begin and self.end:
            rect = QRect(self.begin, self.end).normalized()

            painter.setPen(QPen(QColor(255, 0, 0), 2))
            painter.setBrush(QBrush(QColor(255, 255, 255, 70)))
            painter.drawRect(rect)

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
        if self.begin is not None and self.end is not None:
            x1, y1 = self.begin.x(), self.begin.y()
            x2, y2 = self.end.x(), self.end.y()

            return (
                min(x1, x2),
                min(y1, y2),
                max(x1, x2),
                max(y1, y2),
            )

        return None


class TranslationWorker(QThread):
    """Gemini 호출을 별도 스레드에서 처리하여 GUI 멈춤을 방지."""

    result_ready = pyqtSignal(str)
    status_changed = pyqtSignal(str)
    error_signal = pyqtSignal(str)
    finished_signal = pyqtSignal()

    def __init__(self, image):
        super().__init__()
        self.image = image

    @staticmethod
    def classify_error(error):
        text = str(error).lower()

        if any(x in text for x in [
            "429",
            "resource_exhausted",
            "quota",
            "rate limit",
            "too many requests",
        ]):
            return "quota"

        if any(x in text for x in [
            "401",
            "403",
            "unauthenticated",
            "permission denied",
            "api key not valid",
            "invalid api key",
            "forbidden",
        ]):
            return "auth"

        if any(x in text for x in [
            "500",
            "502",
            "503",
            "504",
            "internal server error",
            "service unavailable",
            "timeout",
            "timed out",
            "connection",
        ]):
            return "temporary"

        return "other"

    def run(self):
        prompt = """
이 이미지 속 문장을 한국어로 번역해줘.

반드시 다음 규칙을 지켜줘.

1. 원문의 의미를 정확하게 유지하면서 자연스러운 한국어로 번역한다.
2. 한자(漢字)는 한글로 번역하지 말고 이미지에 표시된 한자를 그대로 유지한다.
3. 사람 이름, 캐릭터 이름, 아이디, 닉네임, 계정명, 서버명, 고유명사는 가능한 한 원문 그대로 유지한다.
4. 숫자, 특수문자, URL, 게임 내 코드와 같은 문자열은 임의로 변경하지 않는다.
5. 번역할 필요가 없는 고유명사는 원문을 유지한다.
6. 여러 줄의 문장이 있다면 원문의 줄 구성을 최대한 유지한다.
7. 원문 설명이나 분석은 하지 말고 번역 결과만 출력한다.
"""

        # 이번 번역 요청에서 사용할 키 순서.
        key_order = list(range(len(API_KEYS)))

        # 이전 요청에서 다음 키부터 시작하도록 하는 단순 순환 효과
        start = getattr(self.parent(), "next_key_index", 0) if self.parent() else 0
        key_order = key_order[start:] + key_order[:start]

        failed_keys = set()

        for attempt, key_index in enumerate(key_order, start=1):
            if key_index in failed_keys:
                continue

            api_key = API_KEYS[key_index]

            self.status_changed.emit(
                f"Gemini 번역 중... (API 키 {key_index + 1}/{len(API_KEYS)})"
            )

            try:
                client = genai.Client(api_key=api_key)

                response = client.models.generate_content(
                    model=MODEL_NAME,
                    contents=[self.image, prompt],
                )

                result = (response.text or "").strip()

                if not result:
                    raise RuntimeError(
                        "Gemini가 빈 응답을 반환했습니다."
                    )

                self.result_ready.emit(result)

                # 다음 요청은 다음 키부터 시작
                if self.parent():
                    self.parent().next_key_index = (
                        key_index + 1
                    ) % len(API_KEYS)

                self.status_changed.emit("번역 완료!")
                self.finished_signal.emit()
                return

            except Exception as error:
                error_type = self.classify_error(error)

                print(
                    f"\n[API 키 {key_index + 1} 실패]"
                    f"\n종류: {error_type}"
                    f"\n오류: {error}\n"
                )

                failed_keys.add(key_index)

                if error_type == "quota":
                    self.status_changed.emit(
                        f"API 키 {key_index + 1}: "
                        f"쿼터/429 → 다음 키로 전환"
                    )

                elif error_type == "auth":
                    self.status_changed.emit(
                        f"API 키 {key_index + 1}: "
                        f"인증/권한 오류 → 다음 키로 전환"
                    )

                elif error_type == "temporary":
                    self.status_changed.emit(
                        f"API 키 {key_index + 1}: "
                        f"일시 오류 → 다음 키로 전환"
                    )

                else:
                    self.status_changed.emit(
                        f"API 키 {key_index + 1}: "
                        f"요청 오류 → 다음 키로 전환"
                    )

                # 서버/네트워크 오류에는 짧은 대기
                if error_type == "temporary":
                    time.sleep(1.0)

                if attempt < len(API_KEYS):
                    QApplication.processEvents()

        self.error_signal.emit(
            "5개 API 키를 모두 사용했지만 번역에 실패했습니다.\n\n"
            "콘솔 창의 오류 내용을 확인해 주세요."
        )
        self.finished_signal.emit()


class ManualTranslatorApp(QWidget):
    """지정 영역을 캡처해서 Gemini로 번역하는 수동 번역기."""

    def __init__(self):
        super().__init__()

        self.target_coords = None
        self.cap_tool = None
        self.worker = None

        # 다음 요청에서 사용할 API 키
        self.next_key_index = 0

        self.initUI()

    def initUI(self):
        self.setWindowTitle("Gemini 원클릭 수동 번역기")
        self.setGeometry(100, 100, 520, 430)
        self.setWindowFlags(Qt.WindowStaysOnTopHint)

        layout = QVBoxLayout()

        self.btn_select = QPushButton(
            "1. 캡처 영역 지정 / 다시 지정",
            self,
        )
        self.btn_select.setFixedHeight(42)
        self.btn_select.setStyleSheet(
            "font-size: 13px;"
            "font-weight: bold;"
            "background-color: #2196F3;"
            "color: white;"
        )
        self.btn_select.clicked.connect(self.select_area)
        layout.addWidget(self.btn_select)

        self.btn_capture = QPushButton(
            "2. 지정 영역 캡처 후 번역",
            self,
        )
        self.btn_capture.setFixedHeight(48)
        self.btn_capture.setEnabled(False)
        self.btn_capture.setStyleSheet(
            "font-size: 14px;"
            "font-weight: bold;"
            "background-color: #4CAF50;"
            "color: white;"
        )
        self.btn_capture.clicked.connect(
            self.capture_and_translate
        )
        layout.addWidget(self.btn_capture)

        self.lbl_status = QLabel(
            "상태: 먼저 번역할 영역을 지정해 주세요.",
            self,
        )
        self.lbl_status.setStyleSheet(
            "color: #555555;"
            "padding: 5px;"
        )
        layout.addWidget(self.lbl_status)

        self.lbl_area = QLabel(
            "지정 영역: 없음",
            self,
        )
        self.lbl_area.setStyleSheet(
            "color: #777777;"
            "padding: 2px;"
        )
        layout.addWidget(self.lbl_area)

        self.txt_result = QTextEdit(self)
        self.txt_result.setPlaceholderText(
            "번역 결과가 여기에 표시됩니다."
        )
        self.txt_result.setReadOnly(True)
        self.txt_result.setStyleSheet(
            "font-size: 15px;"
        )
        layout.addWidget(self.txt_result)

        bottom_layout = QHBoxLayout()

        self.btn_clear = QPushButton(
            "결과 지우기",
            self,
        )
        self.btn_clear.clicked.connect(
            self.txt_result.clear
        )
        bottom_layout.addWidget(self.btn_clear)

        layout.addLayout(bottom_layout)

        self.setLayout(layout)

    def select_area(self):
        if self.worker and self.worker.isRunning():
            return

        self.hide()
        QApplication.processEvents()

        self.cap_tool = ScreenCaptureTool()
        self.cap_tool.show()
        self.cap_tool.raise_()
        self.cap_tool.activateWindow()

        while self.cap_tool.isVisible():
            QApplication.processEvents()

        coords = self.cap_tool.get_coordinates()

        self.show()
        self.raise_()
        self.activateWindow()

        if not coords:
            self.lbl_status.setText(
                "상태: 영역 지정이 취소되었습니다."
            )
            return

        width = coords[2] - coords[0]
        height = coords[3] - coords[1]

        if width <= 10 or height <= 10:
            self.lbl_status.setText(
                "상태: 영역이 너무 작습니다."
            )
            return

        self.target_coords = coords

        self.lbl_status.setText(
            "상태: 영역 설정 완료!"
        )

        self.lbl_area.setText(
            f"지정 영역: X={coords[0]}, Y={coords[1]}  "
            f"{width} x {height}px"
        )

        self.btn_capture.setEnabled(True)

    def capture_and_translate(self):
        if not self.target_coords:
            return

        if self.worker and self.worker.isRunning():
            return

        self.btn_capture.setEnabled(False)
        self.btn_select.setEnabled(False)

        self.lbl_status.setText(
            "상태: 지정 영역 캡처 중..."
        )
        QApplication.processEvents()

        try:
            image = ImageGrab.grab(
                bbox=self.target_coords
            )

            width, height = image.size

            # 작은 글씨의 OCR 정확도를 높이기 위한 2배 확대
            if width < 1600 and height < 1600:
                image = image.resize(
                    (width * 2, height * 2)
                )

            self.lbl_status.setText(
                "상태: Gemini 분석/번역 중..."
            )

            self.worker = TranslationWorker(image)

            self.worker.result_ready.connect(
                self.on_result
            )
            self.worker.status_changed.connect(
                self.on_status_changed
            )
            self.worker.error_signal.connect(
                self.on_error
            )
            self.worker.finished_signal.connect(
                self.on_worker_finished
            )

            self.worker.start()

        except Exception as error:
            self.on_error(
                "화면 캡처 중 오류가 발생했습니다.\n\n"
                + str(error)
            )
            self.on_worker_finished()

    def on_result(self, text):
        self.txt_result.setText(text)

    def on_status_changed(self, text):
        self.lbl_status.setText(
            "상태: " + text
        )

    def on_error(self, message):
        self.lbl_status.setText(
            "상태: 번역 실패"
        )

        QMessageBox.warning(
            self,
            "번역 오류",
            message,
        )

    def on_worker_finished(self):
        self.btn_capture.setEnabled(
            self.target_coords is not None
        )
        self.btn_select.setEnabled(True)

        if self.worker:
            self.worker.deleteLater()
            self.worker = None

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.quit()
            self.worker.wait(3000)

        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)

    try:
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
    except Exception:
        pass

    ex = ManualTranslatorApp()
    ex.show()

    sys.exit(app.exec_())
