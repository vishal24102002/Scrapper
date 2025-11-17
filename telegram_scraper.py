# vishal.py
import os, sys, subprocess, time, queue, re, logging, io
from decouple import config
from datetime import datetime
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QTextEdit, QCheckBox, QCalendarWidget,
    QLineEdit, QFileDialog, QGroupBox, QSpacerItem, QSizePolicy,
    QMessageBox, QDialog
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QDate
from PyQt6.QtGui import QFont, QPalette, QColor

# Ensure stdout uses UTF-8 encoding
if not getattr(sys, 'frozen', False):
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
    else:
        sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)
        sys.stderr = open(sys.stderr.fileno(), mode='w', encoding='utf-8', buffering=1)

# ====================== PATH & LOGGING ======================
BASE_DIR = config("BASE_DIR")

logging.basicConfig(
    filename=os.path.join("data_files",'app.log'),
    level=logging.DEBUG,
    format='%(asctime)s %(levelname)s:%(message)s'
)

# ====================== GLOBALS ======================
scraping_active = False
selected_groups = []
selected_data_types = []
chats = []
current_process = None  # To hold subprocess for pause/kill

GROUPS_FILE_PATH = os.path.join("data_files",'selected_groups.txt')
DATA_TYPES_FILE_PATH = os.path.join("data_files",'selected_data_types.txt')
SELECTED_DATE_FILE_PATH = os.path.join("data_files",'selected_date.txt')
TARGET_FOLDER = os.path.join("data_files","Database")

# ====================== Worker Thread ======================
class ScraperThread(QThread):
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal()

    def __init__(self, cmd):
        super().__init__()
        self.cmd = cmd
        self._is_running = True

    def stop(self):
        self._is_running = False

    def run(self):
        global current_process
        try:
            current_process = subprocess.Popen(
                self.cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding='utf-8', bufsize=1
            )
            for line in iter(current_process.stdout.readline, ''):
                if not self._is_running:
                    break
                if line:
                    self.log_signal.emit(line.rstrip())
            current_process.wait()
            if self._is_running:
                status = "Scraping completed!" if current_process.returncode == 0 else f"Failed (code: {current_process.returncode})"
                self.log_signal.emit(status)
        except Exception as e:
            if self._is_running:
                self.log_signal.emit(f"Error: {e}")
        finally:
            self.finished_signal.emit()

# ====================== Main Window ======================
class ScraperGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("5AI Scrapper")
        self.setGeometry(100, 100, 1600, 720)
        self.selected_date = QDate.currentDate().addDays(-1)
        self.start_time = 0
        self.text_queue = queue.Queue()

        self.init_ui()
        self.apply_modern_style()
        self.load_saved_data()

        self.log_timer = QTimer()
        self.log_timer.timeout.connect(self.update_log_from_queue)
        self.log_timer.start(100)

        self.elapsed_timer = QTimer()
        self.elapsed_timer.timeout.connect(self.update_elapsed_time)
        self.elapsed_timer.start(1000)

    def apply_modern_style(self):
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor(30, 30, 40))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(230, 230, 230))
        palette.setColor(QPalette.ColorRole.Base, QColor(40, 40, 55))
        palette.setColor(QPalette.ColorRole.Text, QColor(220, 220, 220))
        palette.setColor(QPalette.ColorRole.Button, QColor(50, 50, 70))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor(255, 255, 255))
        palette.setColor(QPalette.ColorRole.Highlight, QColor(100, 180, 255))
        self.setPalette(palette)

        self.setStyleSheet("""
            QPushButton {
                background-color: #5a7bff;
                color: white;
                border: none;
                padding: 14px;
                border-radius: 8px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover { background-color: #6b8aff; }
            QPushButton:pressed { background-color: #4a6bdf; }
            QPushButton#startButton { background-color: #00cc00; }
            QPushButton#startButton:hover { background-color: #00e600; }
            QPushButton#pauseButton { background-color: #ff9500; }
            QPushButton#pauseButton:hover { background-color: #ffb733; }
            QTextEdit, QLineEdit {
                background-color: #2a2a38;
                color: #e0e0e0;
                border: 1px solid #444;
                border-radius: 6px;
                padding: 8px;
            }
            QGroupBox {
                font-weight: bold;
                border: 2px solid #555;
                border-radius: 10px;
                margin: 15px;
                padding-top: 10px;
                font-size: 16px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 20px;
                padding: 0 12px;
                color: #a0a0ff;
            }
            QLabel#statusLabel { font-size: 16px; font-weight: bold; color: #ffdd44; }
            QLabel#elapsedLabel { font-size: 16px; color: #88ff88; }
        """)

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setSpacing(20)

        # ====================== LEFT PANEL (Even Spacing) ======================
        left_panel = QGroupBox("Scraping Control Panel")
        left_layout = QVBoxLayout()
        left_panel.setLayout(left_layout)

        # Add stretchable space between buttons
        buttons = [
            ("1. Select Groups", self.open_group_selector),
            ("2. Select Data Types", self.open_data_type_selector),
            ("3. Browse Target Folder", self.browse_folder),
        ]
        for text, func in buttons:
            btn = QPushButton(text)
            btn.clicked.connect(func)
            left_layout.addWidget(btn)
            left_layout.addSpacerItem(QSpacerItem(20, 15, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed))

        self.folder_display = QLineEdit(f"Default: {TARGET_FOLDER}")
        self.folder_display.setReadOnly(True)
        left_layout.addWidget(self.folder_display)
        left_layout.addSpacerItem(QSpacerItem(20, 15, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed))

        left_layout.addWidget(QLabel("4. Select Date"))
        self.calendar = QCalendarWidget()
        self.calendar.setGridVisible(True)
        self.calendar.setMaximumDate(QDate.currentDate().addDays(-1))
        self.calendar.clicked.connect(self.on_date_selected)
        left_layout.addWidget(self.calendar)
        left_layout.addSpacerItem(QSpacerItem(20, 20, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed))

        # Action Buttons
        action_layout = QHBoxLayout()
        self.btn_start = QPushButton("5. START SCRAPING")
        self.btn_start.setObjectName("startButton")
        self.btn_start.clicked.connect(self.start_scraping)
        action_layout.addWidget(self.btn_start)

        self.btn_transcribe = QPushButton("Start Transcription")
        self.btn_transcribe.clicked.connect(self.start_transcription)
        action_layout.addWidget(self.btn_transcribe)
        left_layout.addLayout(action_layout)

        left_layout.addSpacerItem(QSpacerItem(20, 20, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed))
        self.btn_fetch_news = QPushButton("Fetch News (Coming Soon)")
        self.btn_fetch_news.clicked.connect(lambda: self.append_log("Fetch News - coming soon"))
        left_layout.addWidget(self.btn_fetch_news)

        left_layout.addStretch()  # Push everything up evenly

        # ====================== LOG + STATUS ======================
        log_panel = QGroupBox("Live Output Log")
        log_layout = QVBoxLayout()
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 10))
        log_layout.addWidget(self.log_text)
        log_panel.setLayout(log_layout)

        status_panel = QGroupBox("Status")
        status_layout = QVBoxLayout()
        status_hbox = QHBoxLayout()
        status_hbox.setSpacing(25)

        self.status_light = QLabel("●")
        self.status_light.setStyleSheet("color: #ff4444; font-size: 36px;")
        self.status_light.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_hbox.addWidget(self.status_light)

        self.status_label = QLabel("Status: Idle")
        self.status_label.setObjectName("statusLabel")
        status_hbox.addWidget(self.status_label)

        status_hbox.addStretch()

        self.elapsed_label = QLabel("Time Elapsed: 00:00:00")
        self.elapsed_label.setObjectName("elapsedLabel")
        status_hbox.addWidget(self.elapsed_label)

        status_layout.addLayout(status_hbox)
        status_panel.setLayout(status_layout)

        # ====================== SETTINGS PANEL ======================
        settings_panel = QGroupBox("Settings")
        settings_layout = QVBoxLayout()

        self.btn_set_default_top = QPushButton("Set Current Folder as Default Directory")
        self.btn_set_default_top.clicked.connect(self.set_default_directory)
        self.btn_set_default_top.setStyleSheet("background-color: #ff6b6b; padding: 14px;")
        settings_layout.addWidget(self.btn_set_default_top)

        settings_layout.addSpacerItem(QSpacerItem(20, 15, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed))

        settings_layout.addWidget(QLabel("Add/Remove Telegram Group:"))
        self.group_input = QLineEdit()
        self.group_input.setPlaceholderText("https://t.me/channel-link")
        settings_layout.addWidget(self.group_input)

        btn_grid = QGridLayout()
        btn_add = QPushButton("Add Group")
        btn_add.clicked.connect(self.add_group)
        btn_grid.addWidget(btn_add, 0, 0)
        btn_remove = QPushButton("Remove Group")
        btn_remove.clicked.connect(self.remove_group)
        btn_grid.addWidget(btn_remove, 0, 1)
        settings_layout.addLayout(btn_grid)

        # Play/Pause Button
        self.btn_pause = QPushButton("PAUSE SCRAPING")
        self.btn_pause.setObjectName("pauseButton")
        self.btn_pause.clicked.connect(self.toggle_pause)
        self.btn_pause.setEnabled(False)  # Disabled until scraping starts
        settings_layout.addWidget(self.btn_pause)

        settings_layout.addStretch()
        settings_panel.setLayout(settings_layout)

        # ====================== FINAL LAYOUT ======================
        right_column = QVBoxLayout()
        right_column.addWidget(log_panel, 3)
        right_column.addWidget(status_panel, 1)

        main_layout.addWidget(left_panel, 1)
        main_layout.addLayout(right_column, 2)
        main_layout.addWidget(settings_panel, 1)

    # ====================== DATA & UI METHODS ======================
    def load_saved_data(self):
        global chats, selected_data_types
        if os.path.exists(GROUPS_FILE_PATH):
            with open(GROUPS_FILE_PATH, "r", encoding="utf-8") as f:
                chats = [line.strip() for line in f if line.strip()]
        else:
            chats = ['Fall_of_the_Cabal', 'QDisclosure17', 'galactictruth', 'STFNREPORT', 'realKarliBonne', 'LauraAbolichannel']
            self.save_groups()

        if os.path.exists(DATA_TYPES_FILE_PATH):
            with open(DATA_TYPES_FILE_PATH, "r", encoding="utf-8") as f:
                selected_data_types.extend([line.strip() for line in f if line.strip()])

        if os.path.exists(SELECTED_DATE_FILE_PATH):
            with open(SELECTED_DATE_FILE_PATH, "r") as f:
                date_str = f.read().strip()
                if date_str:
                    self.selected_date = QDate.fromString(date_str, "yyyy-MM-dd")
                    self.calendar.setSelectedDate(self.selected_date)

    def save_groups(self):
        with open(GROUPS_FILE_PATH, "w", encoding="utf-8") as f:
            f.write("\n".join(chats))

    def add_group(self):
        link = self.group_input.text().strip()
        if not link.startswith("https://t.me/") and not link.startswith("t.me/"):
            self.append_log("Invalid link! Use https://t.me/...")
            return
        name = link.split("/")[-1]
        if name not in chats:
            chats.append(name)
            self.save_groups()
            self.append_log(f"Added: {name}")
            if name not in selected_groups:
                selected_groups.append(name)
        else:
            self.append_log("Already exists")
        self.group_input.clear()

    def remove_group(self):
        link = self.group_input.text().strip()
        name = link.split("/")[-1] if "/" in link else link
        if name in chats:
            chats.remove(name)
            if name in selected_groups: selected_groups.remove(name)
            self.save_groups()
            self.append_log(f"Removed: {name}")
        else:
            self.append_log("Group not found")
        self.group_input.clear()

    def open_group_selector(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Select Groups")
        dialog.resize(420, 560)
        layout = QVBoxLayout()
        checkboxes = {}
        for group in chats:
            cb = QCheckBox(group)
            cb.setChecked(group in selected_groups)
            checkboxes[group] = cb
            layout.addWidget(cb)

        def confirm():
            selected_groups.clear()
            for group, cb in checkboxes.items():
                if cb.isChecked():
                    selected_groups.append(group)
            self.append_log(f"Selected: {', '.join(selected_groups)}")
            dialog.accept()

        btn = QPushButton("Confirm Selection")
        btn.clicked.connect(confirm)
        layout.addWidget(btn)
        dialog.setLayout(layout)
        dialog.exec()

    def open_data_type_selector(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Select Data Types")
        layout = QVBoxLayout()
        options = ["Images", "Videos", "Audios", "Text", "Links"]
        vars_dict = {}
        for opt in options:
            cb = QCheckBox(opt)
            cb.setChecked(opt in selected_data_types)
            vars_dict[opt] = cb
            layout.addWidget(cb)

        def confirm():
            global selected_data_types
            selected_data_types = [opt for opt, cb in vars_dict.items() if cb.isChecked()]
            with open(DATA_TYPES_FILE_PATH, "w", encoding="utf-8") as f:
                f.write("\n".join(selected_data_types))
            self.append_log(f"Data types: {', '.join(selected_data_types)}")
            dialog.accept()

        btn = QPushButton("Confirm")
        btn.clicked.connect(confirm)
        layout.addWidget(btn)
        dialog.setLayout(layout)
        dialog.exec()

    def on_date_selected(self, qdate):
        self.selected_date = qdate
        date_str = qdate.toString("yyyy-MM-dd")
        with open(SELECTED_DATE_FILE_PATH, "w") as f:
            f.write(date_str)
        self.append_log(f"Selected date: {date_str}")

    def browse_folder(self):
        global TARGET_FOLDER
        folder = QFileDialog.getExistingDirectory(self, "Select Target Folder", TARGET_FOLDER)
        if folder:
            TARGET_FOLDER = folder
            self.folder_display.setText(TARGET_FOLDER)

    def set_default_directory(self):
        global BASE_DIR
        BASE_DIR = TARGET_FOLDER
        QMessageBox.information(self, "Success", f"Default directory updated!\n\n{TARGET_FOLDER}")

    def toggle_pause(self):
        global scraping_active, current_process
        if not scraping_active:
            return

        if self.btn_pause.text() == "PAUSE SCRAPING":
            if current_process:
                current_process.terminate()
                self.append_log("Scraping PAUSED by user.")
            self.btn_pause.setText("RESUME SCRAPING")
            self.status_label.setText("Status: Paused")
            self.status_light.setStyleSheet("color: #ff9500; font-size: 36px;")
        else:
            self.btn_pause.setText("PAUSE SCRAPING")
            self.status_label.setText("Status: Running")
            self.status_light.setStyleSheet("color: #00ff00; font-size: 36px;")
            self.start_scraping()  # Restart

    def append_log(self, text):
        if text.startswith("BYTES_DOWNLOADED:"): return
        text = re.sub(r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d+,\d+ - INFO - ', '', text)
        if "Download Speed:" in text or "Time Elapsed:" in text: return
        self.log_text.append(text)

    def update_log_from_queue(self):
        try:
            while True:
                text = self.text_queue.get_nowait()
                self.append_log(text)
        except queue.Empty:
            pass

    def update_elapsed_time(self):
        if scraping_active and self.start_time:
            elapsed = int(time.time() - self.start_time)
            h, rem = divmod(elapsed, 3600)
            m, s = divmod(rem, 60)
            self.elapsed_label.setText(f"Time Elapsed: {h:02d}:{m:02d}:{s:02d}")
        else:
            self.elapsed_label.setText("Time Elapsed: 00:00:00")

    def start_scraping(self):
        global scraping_active, start_time, current_process
        if scraping_active:
            self.append_log("Scraping already in progress!")
            return
        if not selected_groups or not selected_data_types or not self.selected_date:
            self.append_log("Select groups, data types, and date!")
            return
        if self.selected_date >= QDate.currentDate():
            self.append_log("Cannot scrape today/future!")
            return

        scraping_active = True
        start_time = time.time()
        self.start_time = start_time
        self.status_light.setStyleSheet("color: #00ff00; font-size: 36px;")
        self.status_label.setText("Status: Running")
        self.btn_pause.setEnabled(True)
        self.btn_pause.setText("PAUSE SCRAPING")
        self.append_log("Scraping started...")

        self.append_log(f"base dir -> {BASE_DIR}")

        cmd = [
            "python", 'Scrapper_main.py',
            '--groups', ','.join(selected_groups),
            '--datatypes', ','.join(selected_data_types),
            '--dates', self.selected_date.toString("yyyy-MM-dd"),
            '--target_folder', TARGET_FOLDER
        ]

        self.scraper_thread = ScraperThread(cmd)
        self.scraper_thread.log_signal.connect(self.text_queue.put)
        self.scraper_thread.finished_signal.connect(self.scraping_finished)
        self.scraper_thread.start()

    def scraping_finished(self):
        global scraping_active, current_process
        scraping_active = False
        current_process = None
        self.status_light.setStyleSheet("color: #ff4444; font-size: 36px;")
        self.status_label.setText("Status: Idle")
        self.btn_pause.setEnabled(False)
        self.btn_pause.setText("PAUSE SCRAPING")

    def start_transcription(self):
        try:
            script_path = 'updated_video_transcription.py'
            subprocess.Popen([sys.executable, script_path])
            self.append_log("Transcription script launched...")
        except Exception as e:
            self.append_log(f"Failed to start transcription: {e}")