""" Import necessary modules for the program to work """
import sys
import os
import difflib
import chardet
import html

from PyQt5.QtCore import Qt, QRect, QSize, QThread, pyqtSignal
from PyQt5.QtGui import QFont, QColor, QTextCharFormat, QPainter
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QLineEdit,
    QPushButton, QLabel, QAction, QWidget, QFileDialog, QDialog,
    QFormLayout, QDialogButtonBox, QMessageBox, QTextEdit, QProgressDialog
)



""" Establish limits """
MAX_TEXT_FILE_SIZE = 10 * 1024 * 1024
MAX_BINARY_BYTES = 1 * 1024 * 1024
CHUNK_SIZE = 256 * 1024



""" Utility function to load the CSS stylesheet """
def loadStyle():
    user_css_path = os.path.join(os.path.expanduser("~"), "fdstyle.css")
    stylesheet = None
    if os.path.exists(user_css_path):
        try:
            with open(user_css_path, 'r') as css_file:
                stylesheet = css_file.read()
            print(f"Loaded user CSS style from: {user_css_path}")
        except Exception as e:
            print(f"Error loading user CSS: {e}")
    else:
        css_file_path = os.path.join(os.path.dirname(__file__), 'style.css')
        if getattr(sys, 'frozen', False):
            css_file_path = os.path.join(sys._MEIPASS, 'style.css')
        try:
            with open(css_file_path, 'r') as css_file:
                stylesheet = css_file.read()
        except FileNotFoundError:
            print(f"Default CSS file not found: {css_file_path}")
    if stylesheet:
        app = QApplication.instance()
        if app:
            app.setStyleSheet(stylesheet)
        else:
            print("No QApplication instance found. Stylesheet not applied.")



""" Create a class for the worker thread """
class WorkerThread(QThread):
    progress = pyqtSignal(int)
    resultReady = pyqtSignal(object)
    errorOccurred = pyqtSignal(str)

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs

    def run(self):
        try:
            result = self.fn(*self.args, **self.kwargs)
            self.resultReady.emit(result)
        except Exception as e:
            self.errorOccurred.emit(str(e))



""" Create a class for the gutter """
class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.codeEditor = editor

    def sizeHint(self):
        return QSize(self.codeEditor.lineNumberAreaWidth(), 0)

    def paintEvent(self, event):
        self.codeEditor.lineNumberAreaPaintEvent(event)



""" Create a class for the file content displays """
class CodeEditor(QTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.lineNumberArea = LineNumberArea(self)
        self.lineStatus = {}
        self.document().blockCountChanged.connect(self.updateLineNumberAreaWidth)
        self.textChanged.connect(self.updateLineNumberArea)
        self.verticalScrollBar().valueChanged.connect(self.updateLineNumberArea)
        self.setReadOnly(True)
        self.setAcceptRichText(True)
        self.setLineWrapMode(QTextEdit.NoWrap)
        font = QFont("Cascadia Code", 10)
        font.setStyleHint(QFont.TypeWriter)
        self.setFont(font)
        self.setStyleSheet(
            "QTextEdit {"
            "  background-color: #FAFAFA;"
            "  border: 1px solid #DDD;"
            "  padding: 6px 6px;"
            "}"
        )
        self.updateLineNumberAreaWidth(0)

    def lineNumberAreaWidth(self):
        digits = 1
        max_val = max(1, self.document().blockCount())
        while max_val >= 10:
            max_val //= 10
            digits += 1
        space = 3 + self.fontMetrics().width('9') * digits
        return space + 16

    def updateLineNumberAreaWidth(self, _):
        self.setViewportMargins(self.lineNumberAreaWidth(), 0, 0, 0)

    def updateLineNumberArea(self, *args):
        cr = self.contentsRect()
        self.lineNumberArea.setGeometry(cr.left(), cr.top(), self.lineNumberAreaWidth(), cr.height())
        self.lineNumberArea.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.updateLineNumberArea()

    def lineNumberAreaPaintEvent(self, event):
        painter = QPainter(self.lineNumberArea)
        painter.fillRect(event.rect(), QColor("#EEEEEE"))
        block = self.document().begin()
        blockNumber = 0
        viewport_offset = self.verticalScrollBar().value()
        line_height = self.fontMetrics().lineSpacing()
        while block.isValid():
            block_top = int(self.document().documentLayout().blockBoundingRect(block).top()) - viewport_offset
            block_bottom = block_top + int(self.document().documentLayout().blockBoundingRect(block).height())
            if block.isVisible() and (block_bottom >= event.rect().top()) and (block_top <= event.rect().bottom()):
                line_status = self.lineStatus.get(blockNumber, "equal")
                number_str = str(blockNumber + 1)
                left_padding = 14
                painter.setPen(QColor("#666666"))
                painter.drawText(
                    left_padding,
                    block_top,
                    self.lineNumberArea.width() - left_padding - 2,
                    line_height,
                    Qt.AlignLeft,
                    number_str
                )
                symbol = None
                color_symbol = Qt.darkGray
                if line_status == "added":
                    symbol = "+"
                    color_symbol = QColor("#4CAF50")
                elif line_status == "removed":
                    symbol = "–"
                    color_symbol = QColor("#F44336")
                elif line_status == "replaced":
                    symbol = "≈"
                    color_symbol = QColor("#FF9800")
                if symbol:
                    painter.setPen(color_symbol)
                    painter.drawText(
                        0,
                        block_top,
                        left_padding - 2,
                        line_height,
                        Qt.AlignCenter,
                        symbol
                    )
            block = block.next()
            blockNumber += 1



""" Create a class for the main window """
class FileDiff(QMainWindow):
    def __init__(self):
        super().__init__()

        self.color_line_added    = "#C8E6C9"
        self.color_line_removed  = "#FFCDD2"
        self.color_line_replaced = "#BBDEFB"
        self.color_line_equal    = "#FAFAFA"
        self.color_inline_diff   = "#FFE082"
        self.setWindowTitle("FileDiff")
        self.setGeometry(100, 100, 1000, 600)
        self.diff_worker = None
        self.binary_worker_left = None
        self.binary_worker_right = None
        self.init_ui()

    def init_ui(self):
        main_widget = QWidget(self)
        main_layout = QVBoxLayout(main_widget)
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("File")
        clear_action = QAction("Clear Fields", self)
        clear_action.triggered.connect(self.clear_fields)
        file_menu.addAction(clear_action)
        view_stats_action = QAction("View Statistics", self)
        view_stats_action.triggered.connect(self.view_statistics)
        file_menu.addAction(view_stats_action)
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        edit_menu = menu_bar.addMenu("Edit")
        compare_action = QAction("Compare Files", self)
        compare_action.triggered.connect(self.compare_files)
        edit_menu.addAction(compare_action)
        find_action = QAction("Find", self)
        find_action.triggered.connect(self.open_find_dialog)
        edit_menu.addAction(find_action)
        clear_highlights_action = QAction("Clear Highlights", self)
        clear_highlights_action.triggered.connect(self.clear_highlights)
        edit_menu.addAction(clear_highlights_action)
        view_menu = menu_bar.addMenu("View")
        self.binary_view_action = QAction("Binary View", self, checkable=True)
        self.binary_view_action.triggered.connect(self.toggle_binary_view)
        view_menu.addAction(self.binary_view_action)
        self.join_scrollbars_action = QAction("Join Scrollbars", self, checkable=True)
        self.join_scrollbars_action.triggered.connect(self.toggle_join_scrollbars)
        view_menu.addAction(self.join_scrollbars_action)
        horizontal_layout = QHBoxLayout()
        left_layout = QVBoxLayout()
        self.path_input_left = QLineEdit()
        self.path_input_left.setPlaceholderText("Enter path for left file...")
        self.path_input_left.textChanged.connect(self.update_left_file_display)
        self.open_button_left = QPushButton("Open Left File")
        self.open_button_left.clicked.connect(self.open_file_left)
        self.editor_left = CodeEditor()
        left_layout.addWidget(self.path_input_left)
        left_layout.addWidget(self.open_button_left)
        left_layout.addWidget(self.editor_left)
        right_layout = QVBoxLayout()
        self.path_input_right = QLineEdit()
        self.path_input_right.setPlaceholderText("Enter path for right file...")
        self.path_input_right.textChanged.connect(self.update_right_file_display)
        self.open_button_right = QPushButton("Open Right File")
        self.open_button_right.clicked.connect(self.open_file_right)
        self.editor_right = CodeEditor()
        right_layout.addWidget(self.path_input_right)
        right_layout.addWidget(self.open_button_right)
        right_layout.addWidget(self.editor_right)
        horizontal_layout.addLayout(left_layout)
        horizontal_layout.addLayout(right_layout)
        self.status_bar_left = QLabel("Line count: 0 | Char count: 0 | Encoding: None")
        self.status_bar_right = QLabel("Line count: 0 | Char count: 0 | Encoding: None")
        status_layout = QHBoxLayout()
        status_layout.addWidget(self.status_bar_left)
        status_layout.addWidget(self.status_bar_right)
        main_layout.addLayout(horizontal_layout)
        main_layout.addLayout(status_layout)
        self.setCentralWidget(main_widget)
        self.show()

    def open_file_left(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Open Left File")
        if file_path:
            self.path_input_left.setText(file_path)
            self.load_file(file_path, is_left=True)

    def open_file_right(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Open Right File")
        if file_path:
            self.path_input_right.setText(file_path)
            self.load_file(file_path, is_left=False)

    def load_file(self, file_path, is_left):
        try:
            file_size = os.path.getsize(file_path)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not get file size: {e}")
            return
        if file_size > MAX_TEXT_FILE_SIZE:
            self.toggle_binary_view_helper()
            return
        try:
            with open(file_path, 'rb') as f:
                raw_data = f.read()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to read file in binary mode: {e}")
            return
        detected = chardet.detect(raw_data)
        encoding = detected.get('encoding')
        if not encoding:
            self.toggle_binary_view_helper()
            return
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                content = f.read()
        except UnicodeDecodeError:
            encoding, ok = self.get_encoding_from_user()
            if not ok:
                return
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    content = f.read()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load file with provided encoding: {e}")
                return
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load file: {e}")
            return
        line_count = len(content.splitlines())
        char_count = len(content)
        if is_left:
            self.editor_left.setHtml(self.buildHtmlForUnhighlighted(content))
            self.status_bar_left.setText(f"Line count: {line_count} | Char count: {char_count} | Encoding: {encoding}")
        else:
            self.editor_right.setHtml(self.buildHtmlForUnhighlighted(content))
            self.status_bar_right.setText(f"Line count: {line_count} | Char count: {char_count} | Encoding: {encoding}")

    def buildHtmlForUnhighlighted(self, text):
        lines = text.splitlines()
        html_lines = []
        for line in lines:
            safe_line = html.escape(line)
            html_lines.append(
                f'<p style="margin:0; background-color:{self.color_line_equal}; white-space:pre;">'
                f'{safe_line}</p>'
            )
        return "\n".join(html_lines)

    def get_encoding_from_user(self):
        encodings = [
            "utf-8", "latin-1", "ascii", "utf-16", "utf-16le",
            "utf-16be", "utf-32", "utf-32le", "utf-32be"
        ]
        dialog = QDialog(self)
        dialog.setWindowTitle("Select Encoding")
        layout = QVBoxLayout(dialog)
        label = QLabel("File could not be read. Select an encoding:")
        layout.addWidget(label)
        encoding_input = QLineEdit()
        encoding_input.setPlaceholderText("Enter encoding (e.g., utf-8, latin-1)...")
        layout.addWidget(encoding_input)
        dropdown = QPushButton("Show Common Encodings")
        layout.addWidget(dropdown)
        encoding_list = QWidget()
        encoding_layout = QVBoxLayout(encoding_list)
        encoding_list.setLayout(encoding_layout)
        for enc in encodings:
            btn = QPushButton(enc)
            btn.clicked.connect(lambda _, e=enc: encoding_input.setText(e))
            encoding_layout.addWidget(btn)
        encoding_list.setVisible(False)
        dropdown.clicked.connect(lambda: encoding_list.setVisible(not encoding_list.isVisible()))
        layout.addWidget(encoding_list)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        layout.addWidget(buttons)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        if dialog.exec_() == QDialog.Accepted:
            return encoding_input.text(), True
        return None, False

    def update_left_file_display(self):
        file_path = self.path_input_left.text()
        if os.path.isfile(file_path):
            if self.binary_view_action.isChecked():
                self.toggle_binary_view_helper()
            else:
                self.load_file(file_path, is_left=True)
        else:
            self.editor_left.clear()
            self.status_bar_left.setText("Line count: 0 | Char count: 0 | Encoding: None")

    def update_right_file_display(self):
        file_path = self.path_input_right.text()
        if os.path.isfile(file_path):
            if self.binary_view_action.isChecked():
                self.toggle_binary_view_helper()
            else:
                self.load_file(file_path, is_left=False)
        else:
            self.editor_right.clear()
            self.status_bar_right.setText("Line count: 0 | Char count: 0 | Encoding: None")

    def compare_files(self):
        left_text = self.getEditorPlainText(self.editor_left)
        right_text = self.getEditorPlainText(self.editor_right)
        if not left_text or not right_text:
            QMessageBox.warning(self, "Comparison Error", "One or both files are empty. Please load both files.")
            return

        progress_dialog = QProgressDialog("Comparing files...", None, 0, 0, self)
        progress_dialog.setWindowTitle("Processing")
        progress_dialog.setWindowModality(Qt.ApplicationModal)
        progress_dialog.setCancelButton(None)
        progress_dialog.setMinimumDuration(0)
        progress_dialog.show()

        self.diff_worker = WorkerThread(self.perform_diff, left_text, right_text)
        self.diff_worker.resultReady.connect(lambda result: self.on_compare_done(result, progress_dialog))
        self.diff_worker.errorOccurred.connect(lambda err: self.on_worker_error(err, progress_dialog))
        self.diff_worker.start()

    def perform_diff(self, left_text, right_text):
        left_lines = left_text.splitlines()
        right_lines = right_text.splitlines()
        aligned_left = []
        aligned_right = []
        statuses_left = []
        statuses_right = []
        top_matcher = difflib.SequenceMatcher(None, left_lines, right_lines)
        for tag, i1, i2, j1, j2 in top_matcher.get_opcodes():
            if tag == 'equal':
                for offset in range(i2 - i1):
                    aligned_left.append(left_lines[i1 + offset])
                    aligned_right.append(right_lines[j1 + offset])
                    statuses_left.append("equal")
                    statuses_right.append("equal")
            elif tag == 'delete':
                for offset in range(i2 - i1):
                    aligned_left.append(left_lines[i1 + offset])
                    aligned_right.append("")
                    statuses_left.append("removed")
                    statuses_right.append("equal")
            elif tag == 'insert':
                for offset in range(j2 - j1):
                    aligned_left.append("")
                    aligned_right.append(right_lines[j1 + offset])
                    statuses_left.append("equal")
                    statuses_right.append("added")
            elif tag == 'replace':
                left_block = left_lines[i1:i2]
                right_block = right_lines[j1:j2]
                sub_matcher = difflib.SequenceMatcher(None, left_block, right_block)
                for st, si1, si2, sj1, sj2 in sub_matcher.get_opcodes():
                    if st == 'equal':
                        for offset in range(si2 - si1):
                            aligned_left.append(left_block[si1 + offset])
                            aligned_right.append(right_block[sj1 + offset])
                            statuses_left.append("equal")
                            statuses_right.append("equal")
                    elif st == 'delete':
                        for offset in range(si2 - si1):
                            aligned_left.append(left_block[si1 + offset])
                            aligned_right.append("")
                            statuses_left.append("removed")
                            statuses_right.append("equal")
                    elif st == 'insert':
                        for offset in range(sj2 - sj1):
                            aligned_left.append("")
                            aligned_right.append(right_block[sj1 + offset])
                            statuses_left.append("equal")
                            statuses_right.append("added")
                    elif st == 'replace':
                        count = max(si2 - si1, sj2 - sj1)
                        for offset in range(count):
                            l_line = left_block[si1 + offset] if offset < (si2 - si1) else ""
                            r_line = right_block[sj1 + offset] if offset < (sj2 - sj1) else ""
                            aligned_left.append(l_line)
                            aligned_right.append(r_line)
                            if l_line and r_line:
                                statuses_left.append("replaced")
                                statuses_right.append("replaced")
                            elif l_line and not r_line:
                                statuses_left.append("removed")
                                statuses_right.append("equal")
                            elif r_line and not l_line:
                                statuses_left.append("equal")
                                statuses_right.append("added")
                            else:
                                statuses_left.append("equal")
                                statuses_right.append("equal")
        final_left_html = []
        final_right_html = []
        for i, (l_line, r_line) in enumerate(zip(aligned_left, aligned_right)):
            l_stat = statuses_left[i]
            r_stat = statuses_right[i]
            if l_stat == "equal" and r_stat == "equal":
                left_html = self.htmlLine(l_line, self.color_line_equal)
                right_html = self.htmlLine(r_line, self.color_line_equal)
            elif l_stat == "removed":
                left_html = self.htmlLine(l_line, self.color_line_removed)
                right_html = self.htmlLine(r_line, self.color_line_equal)
            elif r_stat == "added":
                left_html = self.htmlLine(l_line, self.color_line_equal)
                right_html = self.htmlLine(r_line, self.color_line_added)
            else:
                if l_line and r_line:
                    left_html, right_html = self.buildInlineDiff(l_line, r_line)
                else:
                    left_html = self.htmlLine(l_line, self.color_line_replaced)
                    right_html = self.htmlLine(r_line, self.color_line_replaced)
            final_left_html.append(left_html)
            final_right_html.append(right_html)
        return (final_left_html, final_right_html, statuses_left, statuses_right)

    def on_compare_done(self, result, progress_dialog):
        progress_dialog.cancel()
        final_left_html, final_right_html, statuses_left, statuses_right = result
        self.editor_left.setHtml("\n".join(final_left_html))
        self.editor_right.setHtml("\n".join(final_right_html))
        self.editor_left.lineStatus.clear()
        self.editor_right.lineStatus.clear()
        block_count = max(len(final_left_html), len(final_right_html))
        for i in range(block_count):
            self.editor_left.lineStatus[i] = statuses_left[i] if i < len(statuses_left) else "equal"
            self.editor_right.lineStatus[i] = statuses_right[i] if i < len(statuses_right) else "equal"
        self.editor_left.viewport().update()
        self.editor_right.viewport().update()
        if self.diff_worker is not None:
            self.diff_worker.wait()
            self.diff_worker = None

    def on_worker_error(self, err, progress_dialog):
        progress_dialog.cancel()
        QMessageBox.critical(self, "Error", f"An error occurred: {err}")
        if self.diff_worker is not None:
            self.diff_worker.wait()
            self.diff_worker = None
        if self.binary_worker_left is not None:
            self.binary_worker_left.wait()
            self.binary_worker_left = None
        if self.binary_worker_right is not None:
            self.binary_worker_right.wait()
            self.binary_worker_right = None

    def htmlLine(self, text, bg_color):
        safe_line = html.escape(text)
        return (f'<p style="margin:0; background-color:{bg_color}; white-space:pre;">'
                f'{safe_line}</p>')

    def buildInlineDiff(self, left_line, right_line):
        s = difflib.SequenceMatcher(None, left_line, right_line)
        def wrapSpan(txt):
            return f'<span style="background-color:{self.color_inline_diff};">{html.escape(txt)}</span>'
        left_parts = []
        right_parts = []
        for tag, i1, i2, j1, j2 in s.get_opcodes():
            l_sub = left_line[i1:i2]
            r_sub = right_line[j1:j2]
            if tag == 'equal':
                left_parts.append(html.escape(l_sub))
                right_parts.append(html.escape(r_sub))
            elif tag in ('delete', 'replace'):
                left_parts.append(wrapSpan(l_sub))
            if tag in ('insert', 'replace'):
                right_parts.append(wrapSpan(r_sub))
        left_line_html = (f'<p style="margin:0; background-color:{self.color_line_replaced}; white-space:pre;">'
                          + "".join(left_parts) + '</p>')
        right_line_html = (f'<p style="margin:0; background-color:{self.color_line_replaced}; white-space:pre;">'
                           + "".join(right_parts) + '</p>')
        return left_line_html, right_line_html

    def getEditorPlainText(self, editor):
        doc = editor.document()
        lines = []
        block = doc.begin()
        while block.isValid():
            lines.append(block.text())
            block = block.next()
        return "\n".join(lines)

    def clear_highlights(self):
        self.reset_highlight(self.editor_left)
        self.reset_highlight(self.editor_right)

    def reset_highlight(self, editor):
        text = self.getEditorPlainText(editor)
        editor.setHtml(self.buildHtmlForUnhighlighted(text))
        editor.lineStatus.clear()

    def process_binary_view(self, file_path):
        file_size = os.path.getsize(file_path)
        bytes_to_read = min(file_size, MAX_BINARY_BYTES)

        hex_lines = []
        with open(file_path, 'rb') as f:
            total_read = 0
            offset = 0
            while total_read < bytes_to_read:
                chunk_read = min(CHUNK_SIZE, bytes_to_read - total_read)
                chunk_data = f.read(chunk_read)
                if not chunk_data:
                    break
                for i in range(0, len(chunk_data), 16):
                    line_chunk = chunk_data[i:i+16]
                    hex_part = ' '.join(f"{byte:02X}" for byte in line_chunk)
                    ascii_part = ''.join(chr(byte) if 32 <= byte < 127 else '.' for byte in line_chunk)
                    line_offset = offset + i
                    hex_lines.append(f"{line_offset:08X}  {hex_part:<47}  {ascii_part}")
                offset += len(chunk_data)
                total_read += chunk_read
        truncated = (file_size > MAX_BINARY_BYTES)
        if truncated:
            hex_lines.append("[... truncated]")
        hex_dump = "\n".join(hex_lines)
        html_output = (
            f'<pre style="margin:0; background-color:{self.color_line_equal}; white-space:pre;">'
            f'{html.escape(hex_dump)}'
            '</pre>'
        )
        return html_output

    def process_binary_view_for_both(self):
        left_path = self.path_input_left.text()
        right_path = self.path_input_right.text()
        progress_dialog = QProgressDialog("Processing binary files...", None, 0, 2, self)
        progress_dialog.setWindowTitle("Processing")
        progress_dialog.setWindowModality(Qt.ApplicationModal)
        progress_dialog.setCancelButton(None)
        progress_dialog.setMinimumDuration(0)
        progress_dialog.setValue(0)
        progress_dialog.show()
        if os.path.isfile(left_path):
            self.binary_worker_left = WorkerThread(self.process_binary_view, left_path)
            self.binary_worker_left.resultReady.connect(
                lambda result: self.on_binary_done_aggregated(result, 'left', progress_dialog)
            )
            self.binary_worker_left.errorOccurred.connect(
                lambda err: self.on_worker_error(err, progress_dialog)
            )
            self.binary_worker_left.start()
        else:
            self.editor_left.clear()
            progress_dialog.setValue(progress_dialog.value() + 1)
        if os.path.isfile(right_path):
            self.binary_worker_right = WorkerThread(self.process_binary_view, right_path)
            self.binary_worker_right.resultReady.connect(
                lambda result: self.on_binary_done_aggregated(result, 'right', progress_dialog)
            )
            self.binary_worker_right.errorOccurred.connect(
                lambda err: self.on_worker_error(err, progress_dialog)
            )
            self.binary_worker_right.start()
        else:
            self.editor_right.clear()
            progress_dialog.setValue(progress_dialog.value() + 1)

    def on_binary_done_aggregated(self, result, side, progress_dialog):
        if side == 'left':
            self.editor_left.setHtml(result)
            if self.binary_worker_left is not None:
                self.binary_worker_left.wait()
                self.binary_worker_left = None
        elif side == 'right':
            self.editor_right.setHtml(result)
            if self.binary_worker_right is not None:
                self.binary_worker_right.wait()
                self.binary_worker_right = None

        progress_dialog.setValue(progress_dialog.value() + 1)
        if progress_dialog.value() >= progress_dialog.maximum():
            progress_dialog.close()

    def toggle_binary_view_helper(self):
        self.clear_highlights()
        self.process_binary_view_for_both()

    def toggle_binary_view(self):
        self.clear_highlights()
        if self.binary_view_action.isChecked():
            self.toggle_binary_view_helper()
        else:
            self.clear_highlights()
            self.update_left_file_display()
            self.update_right_file_display()

    def open_find_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Find")
        layout = QFormLayout(dialog)
        search_input = QLineEdit()
        layout.addRow("Search for:", search_input)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        layout.addWidget(buttons)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        if dialog.exec_() == QDialog.Accepted:
            search_term = search_input.text()
            self.find_in_files(search_term)

    def find_in_files(self, search_term):
        fmt = QTextCharFormat()
        fmt.setBackground(QColor("#FF8F1F"))
        cursor = self.editor_left.textCursor()
        cursor.movePosition(cursor.Start)
        while self.editor_left.find(search_term):
            self.editor_left.textCursor().mergeCharFormat(fmt)
        cursor = self.editor_right.textCursor()
        cursor.movePosition(cursor.Start)
        while self.editor_right.find(search_term):
            self.editor_right.textCursor().mergeCharFormat(fmt)

    def view_statistics(self):
        left_text = self.getEditorPlainText(self.editor_left)
        right_text = self.getEditorPlainText(self.editor_right)
        left_lines = left_text.splitlines()
        right_lines = right_text.splitlines()
        same_lines = 0
        different_lines = 0
        swapped_lines = 0
        from itertools import zip_longest
        for l, r in zip_longest(left_lines, right_lines, fillvalue=''):
            if l == r:
                same_lines += 1
            elif l and r:
                different_lines += 1
            else:
                swapped_lines += 1
        stats_dialog = QDialog(self)
        stats_dialog.setWindowTitle("View Statistics")
        layout = QFormLayout(stats_dialog)
        layout.addRow("Total Lines Left File:", QLabel(str(len(left_lines))))
        layout.addRow("Total Lines Right File:", QLabel(str(len(right_lines))))
        layout.addRow("Lines Same:", QLabel(str(same_lines)))
        layout.addRow("Lines Different:", QLabel(str(different_lines)))
        layout.addRow("Lines in Different Positions:", QLabel(str(swapped_lines)))
        layout.addRow("Character Count Left File:", QLabel(str(len(left_text))))
        layout.addRow("Character Count Right File:", QLabel(str(len(right_text))))
        stats_dialog.exec_()

    def toggle_join_scrollbars(self):
        if self.join_scrollbars_action.isChecked():
            self.editor_right.verticalScrollBar().valueChanged.connect(self.sync_scroll_left)
            self.editor_left.verticalScrollBar().valueChanged.connect(self.sync_scroll_right)
        else:
            try:
                self.editor_right.verticalScrollBar().valueChanged.disconnect(self.sync_scroll_left)
                self.editor_left.verticalScrollBar().valueChanged.disconnect(self.sync_scroll_right)
            except Exception:
                pass

    def sync_scroll_left(self, value):
        self.editor_left.verticalScrollBar().setValue(value)

    def sync_scroll_right(self, value):
        self.editor_right.verticalScrollBar().setValue(value)

    def clear_fields(self):
        self.path_input_left.clear()
        self.path_input_right.clear()
        self.editor_left.clear()
        self.editor_right.clear()
        self.status_bar_left.setText("Line count: 0 | Char count: 0 | Encoding: None")
        self.status_bar_right.setText("Line count: 0 | Char count: 0 | Encoding: None")



""" Start the program """
if __name__ == '__main__':
    app = QApplication(sys.argv)
    loadStyle()
    viewer = FileDiff()
    sys.exit(app.exec_())