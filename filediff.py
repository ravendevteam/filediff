import sys
import os
from PyQt5.QtCore import Qt, QFile, QTextStream
from PyQt5.QtGui import QFont, QTextOption, QTextCursor, QTextCharFormat, QColor
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QTextEdit, QLineEdit,
    QPushButton, QLabel, QMenuBar, QAction, QWidget, QFileDialog, QDialog,
    QFormLayout, QDialogButtonBox, QMessageBox
)
from itertools import zip_longest

def loadStyle():
    """Load CSS styles globally for the application."""
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

class FileDiff(QMainWindow):
    def __init__(self):
        super().__init__()

        self.color_same = "#FFFFFF"
        self.color_different = "#FDFF41"
        self.color_only_left = "#41FF43"
        self.color_only_right = "#FF4141"

        self.setWindowTitle("FileDiff")
        self.setGeometry(100, 100, 1000, 600)
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

        horizontal_layout = QHBoxLayout()

        left_layout = QVBoxLayout()
        self.path_input_left = QLineEdit()
        self.path_input_left.setPlaceholderText("Enter path for left file...")
        self.path_input_left.textChanged.connect(self.update_left_file_display)
        self.open_button_left = QPushButton("Open Left File")
        self.open_button_left.clicked.connect(self.open_file_left)
        self.text_edit_left = self.create_text_edit()
        left_layout.addWidget(self.path_input_left)
        left_layout.addWidget(self.open_button_left)
        left_layout.addWidget(self.text_edit_left)

        right_layout = QVBoxLayout()
        self.path_input_right = QLineEdit()
        self.path_input_right.setPlaceholderText("Enter path for right file...")
        self.path_input_right.textChanged.connect(self.update_right_file_display)
        self.open_button_right = QPushButton("Open Right File")
        self.open_button_right.clicked.connect(self.open_file_right)
        self.text_edit_right = self.create_text_edit()
        right_layout.addWidget(self.path_input_right)
        right_layout.addWidget(self.open_button_right)
        right_layout.addWidget(self.text_edit_right)

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

    def create_text_edit(self):
        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setWordWrapMode(QTextOption.NoWrap)
        font = QFont("Cascadia Code", 10)
        font.setStyleHint(QFont.TypeWriter)
        text_edit.setFont(font)
        return text_edit

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
            with open(file_path, 'r', encoding='utf-8') as file:
                content = file.read()
                line_count = len([line for line in content.splitlines() if line.strip()])
                char_count = len(content)
                if is_left:
                    self.text_edit_left.setPlainText(content)
                    self.status_bar_left.setText(f"Line count: {line_count} | Char count: {char_count} | Encoding: utf-8")
                else:
                    self.text_edit_right.setPlainText(content)
                    self.status_bar_right.setText(f"Line count: {line_count} | Char count: {char_count} | Encoding: utf-8")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load file: {e}")

    def update_left_file_display(self):
        file_path = self.path_input_left.text()
        if os.path.isfile(file_path):
            self.load_file(file_path, is_left=True)
        else:
            self.text_edit_left.clear()
            self.status_bar_left.setText("Line count: 0 | Char count: 0 | Encoding: None")

    def update_right_file_display(self):
        file_path = self.path_input_right.text()
        if os.path.isfile(file_path):
            self.load_file(file_path, is_left=False)
        else:
            self.text_edit_right.clear()
            self.status_bar_right.setText("Line count: 0 | Char count: 0 | Encoding: None")

    def compare_files(self):
        content_left = self.text_edit_left.toPlainText()
        content_right = self.text_edit_right.toPlainText()

        if not content_left or not content_right:
            QMessageBox.warning(self, "Comparison Error", "One or both files are empty. Please load both files.")
            return

        left_lines = content_left.splitlines()
        right_lines = content_right.splitlines()

        for i, (line_left, line_right) in enumerate(zip_longest(left_lines, right_lines, fillvalue='')):
            if line_left == line_right:
                continue
            elif line_left and line_right and line_left != line_right:
                self.highlight_line(self.text_edit_left, i, self.color_different)
                self.highlight_line(self.text_edit_right, i, self.color_different)
            elif line_left and not line_right:
                self.highlight_line(self.text_edit_left, i, self.color_only_left)
            elif line_right and not line_left:
                self.highlight_line(self.text_edit_right, i, self.color_only_right)

    def highlight_line(self, text_edit, line_index, hex_color):
        cursor = text_edit.textCursor()
        block = text_edit.document().findBlockByNumber(line_index)
        if block.isValid():
            cursor.setPosition(block.position())
            cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
            fmt = QTextCharFormat()
            fmt.setBackground(QColor(hex_color))
            cursor.setCharFormat(fmt)

    def clear_highlights(self):
        self.reset_highlight(self.text_edit_left)
        self.reset_highlight(self.text_edit_right)

    def reset_highlight(self, text_edit):
        cursor = text_edit.textCursor()
        cursor.setPosition(0)
        cursor.movePosition(QTextCursor.End, QTextCursor.KeepAnchor)
        fmt = QTextCharFormat()
        fmt.clearBackground()
        cursor.setCharFormat(fmt)

    def clear_fields(self):
        self.path_input_left.clear()
        self.path_input_right.clear()
        self.text_edit_left.clear()
        self.text_edit_right.clear()
        self.status_bar_left.setText("Line count: 0 | Char count: 0 | Encoding: None")
        self.status_bar_right.setText("Line count: 0 | Char count: 0 | Encoding: None")

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
        cursor_left = self.text_edit_left.textCursor()
        cursor_right = self.text_edit_right.textCursor()

        cursor_left.setPosition(0)
        cursor_right.setPosition(0)

        fmt = QTextCharFormat()
        fmt.setBackground(QColor("#FF8F1F"))

        while self.text_edit_left.find(search_term):
            self.text_edit_left.textCursor().mergeCharFormat(fmt)

        while self.text_edit_right.find(search_term):
            self.text_edit_right.textCursor().mergeCharFormat(fmt)

    def view_statistics(self):
        content_left = self.text_edit_left.toPlainText()
        content_right = self.text_edit_right.toPlainText()

        left_lines = content_left.splitlines()
        right_lines = content_right.splitlines()

        same_lines = 0
        different_lines = 0
        swapped_lines = 0

        for line_left, line_right in zip_longest(left_lines, right_lines, fillvalue=''):
            if line_left == line_right:
                same_lines += 1
            elif line_left and line_right:
                different_lines += 1
            elif line_left != line_right:
                swapped_lines += 1

        stats_dialog = QDialog(self)
        stats_dialog.setWindowTitle("View Statistics")
        layout = QFormLayout(stats_dialog)

        layout.addRow("Total Lines Left File:", QLabel(str(len(left_lines))))
        layout.addRow("Total Lines Right File:", QLabel(str(len(right_lines))))
        layout.addRow("Lines Same:", QLabel(str(same_lines)))
        layout.addRow("Lines Different:", QLabel(str(different_lines)))
        layout.addRow("Lines in Different Positions:", QLabel(str(swapped_lines)))
        layout.addRow("Character Count Left File:", QLabel(str(len(content_left))))
        layout.addRow("Character Count Right File:", QLabel(str(len(content_right))))

        stats_dialog.exec_()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    loadStyle()
    viewer = FileDiff()
    sys.exit(app.exec_())
