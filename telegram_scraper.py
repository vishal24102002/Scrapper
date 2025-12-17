import os, sys, subprocess, time, queue, re, logging, io, json
from decouple import config
from datetime import datetime, timedelta
from pathlib import Path
from update import GitHubPuller
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QTextEdit, QCheckBox, QCalendarWidget,
    QLineEdit, QFileDialog, QGroupBox, QSpacerItem, QSizePolicy,
    QMessageBox, QDialog, QListWidget, QProgressBar, QMenu, QToolButton,
    QInputDialog
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QDate, QSettings, QSize
from PyQt6.QtGui import QFont, QPalette, QColor, QTextCursor, QIcon, QAction, QTextCharFormat

try:
    from plyer import notification
    NOTIFICATIONS_AVAILABLE = True
except ImportError:
    NOTIFICATIONS_AVAILABLE = False

# Ensure stdout uses UTF-8 encoding
if not getattr(sys, 'frozen', False):
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
    else:
        sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)
        sys.stderr = open(sys.stderr.fileno(), mode='w', encoding='utf-8', buffering=1)

# ====================== PATH & LOGGING ======================
BASE_DIR = config("BASE_DIR", default=os.getcwd())
VERSION = "v0.4"

os.makedirs("data_files", exist_ok=True)
logging.basicConfig(
    filename=os.path.join("data_files",'app.log'),
    level=logging.DEBUG,
    format='%(asctime)s %(levelname)s:%(message)s'
)

# ====================== GLOBALS ======================
scraping_active = False
selected_groups = []
selected_data_types = []
selected_dates = []
chats = []
current_process = None
total_bytes_downloaded = 0
download_start_time = 0

GROUPS_FILE_PATH = os.path.join(BASE_DIR,"data_files",'selected_groups.txt')
DATA_TYPES_FILE_PATH = os.path.join("data_files",'selected_data_types.txt')
SELECTED_DATES_FILE_PATH = os.path.join("data_files",'selected_dates.txt')
TARGET_FOLDER =config("TAR_DIR", default=os.getcwd())
CONFIG_FILE = os.path.join("data_files", "config.json")

# ====================== Worker Thread ======================
class ScraperThread(QThread):
    log_signal = pyqtSignal(str, str)  # message, level
    progress_signal = pyqtSignal(int)
    bytes_signal = pyqtSignal(int)
    finished_signal = pyqtSignal(bool)  # success
    input_required_signal = pyqtSignal(str)  # prompt message
    
    def __init__(self, cmd):
        super().__init__()
        self.cmd = cmd
        self._is_running = True
        self.user_input = None
        self.input_event = None

    def stop(self):
        self._is_running = False

    def provide_input(self, user_input):
        """Called from main thread to provide user input"""
        if current_process and current_process.stdin and current_process.poll() is None:
            input_text = user_input.strip() + '\n'
            current_process.stdin.write(input_text)
            current_process.stdin.flush()
            self.log_signal.emit(f"✓ Input sent: {user_input.strip()}", "SUCCESS")
        else:
            self.log_signal.emit("✗ Failed to send input — process not running", "ERROR")

    def run(self):
        global current_process
        try:
            current_process = subprocess.Popen(
                self.cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.STDOUT,
                stdin=subprocess.PIPE,  # Enable stdin for input
                text=True, 
                encoding='utf-8', 
                bufsize=1
            )
            
            for line in iter(current_process.stdout.readline, ''):
                line = line.rstrip('\n')
                if not line:
                    continue

                # Always log normal lines
                self.log_signal.emit(line, "INFO")

                # === DETECT GUI INPUT REQUESTS ===
                if line == "GUI_NEEDS_INPUT:PHONE":
                    self.input_required_signal.emit("PHONE")
                elif line == "GUI_NEEDS_INPUT:CODE":
                    self.input_required_signal.emit("CODE")
                elif line == "GUI_NEEDS_INPUT:PASSWORD":
                    self.input_required_signal.emit("PASSWORD")
                elif line == "GUI_AUTH_SUCCESS":
                    self.log_signal.emit("✓ Signed in successfully to Telegram!", "SUCCESS")
                elif line.startswith("GUI_AUTH_FAILED:"):
                    error = line[len("GUI_AUTH_FAILED:"):]
                    self.log_signal.emit(f"✗ Authentication failed: {error}", "ERROR")

                # Your existing BYTES_DOWNLOADED handling
                elif line.startswith("BYTES_DOWNLOADED:"):
                    try:
                        bytes_val = int(line.split(":")[1])
                        self.bytes_signal.emit(bytes_val)
                    except:
                        pass

            current_process.wait()
            success = current_process.returncode == 0
            if self._is_running:
                if success:
                    self.log_signal.emit("✓ Scraping completed successfully!", "SUCCESS")
                else:
                    self.log_signal.emit(f"✗ Scraping failed with exit code: {current_process.returncode}", "ERROR")
            self.finished_signal.emit(success)
        except Exception as e:
            if self._is_running:
                self.log_signal.emit(f"✗ Critical Error: {e}", "ERROR")
            self.finished_signal.emit(False)

# ====================== Git Update Thread ======================
class GitUpdateThread(QThread):
    log_signal = pyqtSignal(str, str)  # message, level
    finished_signal = pyqtSignal(bool, str)  # success, message
    
    def __init__(self, password, repo_path='.'):
        super().__init__()
        self.password = password
        self.repo_path = repo_path
    
    def run(self):
        try:
            from update import GitHubPuller
            
            self.log_signal.emit("🔄 Initializing GitHub puller...", "INFO")
            puller = GitHubPuller('sqlite.db')
            
            self.log_signal.emit("🔐 Authenticating...", "INFO")
            result = puller.pull_and_update(self.password, self.repo_path)
            
            if result['success']:
                self.log_signal.emit("✓ " + result['message'], "SUCCESS")
                if 'output' in result and result['output']:
                    self.log_signal.emit(f"Git output: {result['output']}", "INFO")
                self.finished_signal.emit(True, result['message'])
            else:
                self.log_signal.emit("✗ " + result['message'], "ERROR")
                self.finished_signal.emit(False, result['message'])
                
        except Exception as e:
            self.log_signal.emit(f"✗ Update error: {str(e)}", "ERROR")
            self.finished_signal.emit(False, str(e))


#====================== Add this class at the top of your file (outside the main GUI class) =======================================
class TranscriptionThread(QThread):
    log_signal = pyqtSignal(str, str)  # (message, log_type)
    finished_signal = pyqtSignal(bool)  # True if successful, False if failed
    
    def __init__(self, script_path, target_folder):
        super().__init__()
        self.script_path = script_path
        self.target_folder = target_folder
        self._is_running = True
    
    def run(self):
        try:
            process = subprocess.Popen(
                [sys.executable, self.script_path, self.target_folder],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            # Read output line by line in real-time
            while self._is_running:
                line = process.stdout.readline()
                if not line:
                    break
                line = line.strip()
                if line:
                    self.log_signal.emit(line, "INFO")
            
            process.wait()
            
            if process.returncode == 0:
                self.log_signal.emit("✓ Transcription completed successfully!", "SUCCESS")
                self.finished_signal.emit(True)
            else:
                self.log_signal.emit(f"✗ Transcription failed with exit code {process.returncode}", "ERROR")
                self.finished_signal.emit(False)
                
        except Exception as e:
            self.log_signal.emit(f"✗ Transcription error: {str(e)}", "ERROR")
            self.finished_signal.emit(False)
    
    def stop(self):
        self._is_running = False

# ====================== Main Window ======================
class ScraperGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"5AI Scraper {VERSION}")
        self.dark_theme = True
        self.start_time = 0
        self.text_queue = queue.Queue()
        self.files_downloaded = 0
        
        # Settings for window geometry
        self.settings = QSettings("5AI", "Scraper")
        
        self.init_ui()
        self.apply_theme()
        self.load_saved_data()
        self.restore_geometry_from_settings()

        self.log_timer = QTimer()
        self.log_timer.timeout.connect(self.update_log_from_queue)
        self.log_timer.start(100)

        self.elapsed_timer = QTimer()
        self.elapsed_timer.timeout.connect(self.update_elapsed_time)
        self.elapsed_timer.start(1000)

    def closeEvent(self, event):
        if scraping_active:
            reply = QMessageBox.question(
                self, 'Confirm Exit',
                "Scraping is in progress. Are you sure you want to exit?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                event.ignore()
                return
        
        # Save window geometry
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("windowState", self.saveState())
        event.accept()

    def restore_geometry_from_settings(self):
        geometry = self.settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)
        else:
            self.setGeometry(100, 100, 1700, 900)
        
        state = self.settings.value("windowState")
        if state:
            self.restoreState(state)

    def apply_theme(self):
        if self.dark_theme:
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
                    padding: 12px;
                    border-radius: 8px;
                    font-weight: bold;
                    font-size: 13px;
                }
                QPushButton:hover { background-color: #6b8aff; }
                QPushButton:pressed { background-color: #4a6bdf; }
                QPushButton:disabled { background-color: #3a3a50; color: #888; }
                QPushButton#startButton { background-color: #00cc00; }
                QPushButton#startButton:hover { background-color: #00e600; }
                QPushButton#stopButton { background-color: #ff3333; }
                QPushButton#stopButton:hover { background-color: #ff5555; }
                QPushButton#themeButton { background-color: #222; padding: 8px; border-radius: 6px; }
                QTextEdit, QLineEdit {
                    background-color: #2a2a38;
                    color: #e0e0e0;
                    border: 1px solid #444;
                    border-radius: 6px;
                    padding: 8px;
                }
                QListWidget {
                    background-color: #2a2a38;
                    color: #e0e0e0;
                    border: 1px solid #444;
                    border-radius: 6px;
                    padding: 4px;
                }
                QProgressBar {
                    border: 1px solid #444;
                    border-radius: 6px;
                    text-align: center;
                    background-color: #2a2a38;
                    color: white;
                    font-weight: bold;
                }
                QProgressBar::chunk {
                    background-color: #5a7bff;
                    border-radius: 5px;
                }
                QGroupBox {
                    font-weight: bold;
                    border: 2px solid #555;
                    border-radius: 10px;
                    margin: 15px;
                    padding-top: 10px;
                    font-size: 16px;
                    color: #d0d0ff;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    left: 20px;
                    padding: 0 12px;
                    color: #a0a0ff;
                }
                QLabel#statusLabel { font-size: 16px; font-weight: bold; color: #ffdd44; }
                QLabel#elapsedLabel { font-size: 14px; color: #88ff88; }
                QLabel#statsLabel { font-size: 13px; color: #88ddff; }
                QCalendarWidget QAbstractItemView:enabled {
                    background-color: #2a2a38;
                    selection-background-color: #5a7bff;
                    color: #e0e0e0;
                }
                QCalendarWidget QWidget {
                    alternate-background-color: #3a3a48;
                }
            """)
        else:
            # Light theme
            palette = QPalette()
            palette.setColor(QPalette.ColorRole.Window, QColor(240, 240, 245))
            palette.setColor(QPalette.ColorRole.WindowText, QColor(30, 30, 30))
            palette.setColor(QPalette.ColorRole.Base, QColor(255, 255, 255))
            palette.setColor(QPalette.ColorRole.Text, QColor(30, 30, 30))
            palette.setColor(QPalette.ColorRole.Button, QColor(230, 230, 240))
            palette.setColor(QPalette.ColorRole.ButtonText, QColor(30, 30, 30))
            palette.setColor(QPalette.ColorRole.Highlight, QColor(100, 180, 255))
            self.setPalette(palette)

            self.setStyleSheet("""
                QPushButton {
                    background-color: #5a7bff;
                    color: white;
                    border: none;
                    padding: 12px;
                    border-radius: 8px;
                    font-weight: bold;
                    font-size: 13px;
                }
                QPushButton:hover { background-color: #6b8aff; }
                QPushButton:pressed { background-color: #4a6bdf; }
                QPushButton:disabled { background-color: #d0d0d0; color: #888; }
                QPushButton#startButton { background-color: #00cc00; }
                QPushButton#startButton:hover { background-color: #00e600; }
                QPushButton#stopButton { background-color: #ff3333; }
                QPushButton#stopButton:hover { background-color: #ff5555; }
                QPushButton#themeButton { background-color: #f0f0f0; padding: 8px; border-radius: 6px; color: #222; }
                QTextEdit, QLineEdit {
                    background-color: white;
                    color: #222;
                    border: 1px solid #ccc;
                    border-radius: 6px;
                    padding: 8px;
                }
                QListWidget {
                    background-color: white;
                    color: #222;
                    border: 1px solid #ccc;
                    border-radius: 6px;
                }
                QProgressBar {
                    border: 1px solid #ccc;
                    border-radius: 6px;
                    text-align: center;
                    background-color: white;
                    color: #222;
                    font-weight: bold;
                }
                QProgressBar::chunk {
                    background-color: #5a7bff;
                    border-radius: 5px;
                }
                QGroupBox {
                    font-weight: bold;
                    border: 2px solid #bbb;
                    border-radius: 10px;
                    margin: 15px;
                    padding-top: 10px;
                    font-size: 16px;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    left: 20px;
                    padding: 0 12px;
                    color: #5a7bff;
                }
                QLabel#statusLabel { font-size: 16px; font-weight: bold; color: #ff8800; }
                QLabel#elapsedLabel { font-size: 14px; color: #008800; }
                QLabel#statsLabel { font-size: 13px; color: #0088cc; }
            """)

    def toggle_theme(self):
        self.dark_theme = not self.dark_theme
        self.apply_theme()
        self.append_log(f"Switched to {'Dark' if self.dark_theme else 'Light'} Theme", "INFO")

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setSpacing(15)

        # ====================== LEFT PANEL ======================
        left_panel = QGroupBox("⚙ Control Panel")
        left_layout = QVBoxLayout()
        left_panel.setLayout(left_layout)

        left_layout.addSpacerItem(QSpacerItem(20, 5, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed))

        # Main control buttons
        buttons = [
            ("1. Select Groups", self.open_group_selector, "Choose which Telegram groups to scrape"),
            ("2. Select Data Types", self.open_data_type_selector, "Choose what content to download (Images, Videos, etc.)"),
            ("3. Browse Target Folder", self.browse_folder, "Select where downloaded files will be saved"),
        ]
        for text, func, tooltip in buttons:
            btn = QPushButton(text)
            btn.clicked.connect(func)
            btn.setToolTip(tooltip)
            left_layout.addWidget(btn)
            left_layout.addSpacerItem(QSpacerItem(20, 8, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed))

        self.folder_display = QLineEdit(f"{TARGET_FOLDER}")
        self.folder_display.setReadOnly(True)
        self.folder_display.setToolTip("Current target folder for downloads")
        left_layout.addWidget(self.folder_display)
        
        left_layout.addSpacerItem(QSpacerItem(20, 10, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed))

        # ====================== DATE SELECTION ======================
        left_layout.addWidget(QLabel("4. Select Dates"))
        
        # Quick preset buttons
        preset_layout = QGridLayout()
        presets = [
            ("Yesterday", 1, "Select yesterday's date"),
            ("Last 30 Days", 30, "Select past month"),
            ("Last 2 years", 730, "Select past 2 years"),
            ("Custom", 0, "Select custom dates from calendar")
        ]
        for i, (label, days, tooltip) in enumerate(presets):
            btn = QPushButton(label)
            btn.setToolTip(tooltip)
            if days == 0:
                btn.setStyleSheet("background-color: #ff9500;")
                btn.clicked.connect(self.show_custom_calendar)
            else:
                btn.clicked.connect(lambda checked, d=days: self.add_date_preset(d))
            preset_layout.addWidget(btn, i // 2, i % 2)
        left_layout.addLayout(preset_layout)
        
        # Calendar widget (hidden by default)
        self.calendar = QCalendarWidget()
        self.calendar.setGridVisible(True)
        self.calendar.setMaximumDate(QDate.currentDate().addDays(-1))
        self.calendar.clicked.connect(self.highlight_calendar_dates)
        self.calendar.setVisible(False)  # Hidden by default
        left_layout.addWidget(self.calendar)
        
        
        date_btn_layout = QHBoxLayout()
        self.btn_add_date = QPushButton("➕ Add Date")
        self.btn_add_date.clicked.connect(self.add_selected_date)
        self.btn_add_date.setToolTip("Add selected date to the list")
        self.btn_add_date.setVisible(False)  # Hidden by default
        date_btn_layout.addWidget(self.btn_add_date)
        
        self.btn_clear_dates = QPushButton("🗑 Clear All")
        self.btn_clear_dates.clicked.connect(self.clear_all_dates)
        self.btn_clear_dates.setToolTip("Remove all selected dates")
        date_btn_layout.addWidget(self.btn_clear_dates)
        left_layout.addLayout(date_btn_layout)
        
        left_layout.addWidget(QLabel("Selected Dates:"))
        self.dates_list = QListWidget()
        self.dates_list.setMaximumHeight(100)
        self.dates_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.dates_list.customContextMenuRequested.connect(self.show_dates_context_menu)
        self.dates_list.setToolTip("Right-click to remove individual dates")
        left_layout.addWidget(self.dates_list)
        
        left_layout.addSpacerItem(QSpacerItem(20, 15, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed))
        
        # === AUTO TRANSCRIPTION CHECKBOX ===
        self.auto_transcribe_checkbox = QCheckBox("Auto-transcribe videos after scraping")
        self.auto_transcribe_checkbox.setChecked(True)  # Optional: default on
        self.auto_transcribe_checkbox.setStyleSheet("""
            QCheckBox {
                font-size: 14px;
                font-weight: bold;
                color: #00ffaa;
                spacing: 10px;
            }
            QCheckBox::indicator {
                width: 20px;
                height: 20px;
            }
        """)
        self.auto_transcribe_checkbox.setToolTip("If checked, videos will be automatically transcribed after scraping completes")
        left_layout.addWidget(self.auto_transcribe_checkbox)

        left_layout.addSpacerItem(QSpacerItem(20, 15, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed))

        # Action Buttons
        action_layout = QHBoxLayout()
        self.btn_start = QPushButton("▶ START SCRAPING")
        self.btn_start.setObjectName("startButton")
        self.btn_start.clicked.connect(self.start_scraping)
        self.btn_start.setToolTip("Begin scraping selected groups and dates")
        action_layout.addWidget(self.btn_start)

        self.btn_stop = QPushButton("🛑 STOP")
        self.btn_stop.setObjectName("stopButton")
        self.btn_stop.clicked.connect(self.stop_scraping)
        self.btn_stop.setEnabled(False)
        self.btn_stop.setToolTip("Stop current scraping operation")
        action_layout.addWidget(self.btn_stop)
        left_layout.addLayout(action_layout)
        
        # Auth setup button
        self.btn_setup_auth = QPushButton("🔐 Setup Telegram Auth")
        self.btn_setup_auth.clicked.connect(self.setup_telegram_auth)
        self.btn_setup_auth.setToolTip("Setup Telegram authentication for first-time use")
        self.btn_setup_auth.setStyleSheet("background-color: #9500ff;")
        left_layout.addWidget(self.btn_setup_auth)

        self.btn_fetch_news = QPushButton("Fetch News")
        self.btn_fetch_news.clicked.connect(lambda: self.append_log("Fetch News - coming soon", "INFO"))
        self.btn_fetch_news.setToolTip("Fetch news articles (coming soon)")
        left_layout.addWidget(self.btn_fetch_news)

        left_layout.addStretch()

        # ====================== MIDDLE COLUMN - LOG + STATUS ======================
        middle_column = QVBoxLayout()
        
        # Stats bar
        stats_panel = QGroupBox("📈 Statistics")
        stats_layout = QVBoxLayout()
        self.stats_label = QLabel("Groups: 0 | Dates: 0 | Data Types: None")
        self.stats_label.setObjectName("statsLabel")
        self.stats_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        stats_layout.addWidget(self.stats_label)
        stats_panel.setLayout(stats_layout)
        middle_column.addWidget(stats_panel)

        # Log panel
        log_panel = QGroupBox("📝 Live Output Log")
        log_layout = QVBoxLayout()
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 10))
        log_layout.addWidget(self.log_text)
        log_panel.setLayout(log_layout)
        middle_column.addWidget(log_panel, 3)

        # Status panel
        status_panel = QGroupBox("📡 Status")
        status_layout = QVBoxLayout()
        
        status_hbox = QHBoxLayout()
        self.status_light = QLabel("●")
        self.status_light.setStyleSheet("color: #ff4444; font-size: 36px;")
        self.status_light.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_hbox.addWidget(self.status_light)

        self.status_label = QLabel("Status: Idle")
        self.status_label.setObjectName("statusLabel")
        status_hbox.addWidget(self.status_label)
        status_hbox.addStretch()

        self.elapsed_label = QLabel("Time: 00:00:00")
        self.elapsed_label.setObjectName("elapsedLabel")
        status_hbox.addWidget(self.elapsed_label)
        status_layout.addLayout(status_hbox)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Progress: %p%")
        status_layout.addWidget(self.progress_bar)

        # Speed and stats
        speed_layout = QHBoxLayout()
        self.speed_label = QLabel("Speed: 0 MB/s")
        self.speed_label.setObjectName("elapsedLabel")
        speed_layout.addWidget(self.speed_label)
        
        self.files_label = QLabel("Files: 0")
        self.files_label.setObjectName("elapsedLabel")
        speed_layout.addWidget(self.files_label)
        
        self.size_label = QLabel("Downloaded: 0 MB")
        self.size_label.setObjectName("elapsedLabel")
        speed_layout.addWidget(self.size_label)
        speed_layout.addStretch()
        status_layout.addLayout(speed_layout)

        status_panel.setLayout(status_layout)
        middle_column.addWidget(status_panel)

        # ====================== RIGHT PANEL - SETTINGS ======================
        settings_panel = QGroupBox("⚙ Settings")
        settings_layout = QVBoxLayout()

        self.btn_export = QPushButton("📤 Export Config")
        self.btn_export.clicked.connect(self.export_config)
        self.btn_export.setToolTip("Export current configuration to JSON file")
        settings_layout.addWidget(self.btn_export)

        self.btn_import = QPushButton("📥 Import Config")
        self.btn_import.clicked.connect(self.import_config)
        self.btn_import.setToolTip("Import configuration from JSON file")
        settings_layout.addWidget(self.btn_import)

        settings_layout.addSpacerItem(QSpacerItem(20, 10, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed))

        self.btn_set_default = QPushButton("💾 Set as Default Directory")
        self.btn_set_default.clicked.connect(self.set_default_directory)
        self.btn_set_default.setToolTip("Set current folder as default in .env file")
        self.btn_set_default.setStyleSheet("background-color: #ff6b6b; padding: 12px;")
        settings_layout.addWidget(self.btn_set_default)

        settings_layout.addSpacerItem(QSpacerItem(20, 15, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed))

        settings_layout.addWidget(QLabel("Manage Telegram Groups:"))
        self.group_input = QLineEdit()
        self.group_input.setPlaceholderText("https://t.me/channel-link")
        self.group_input.setToolTip("Enter Telegram group link")
        settings_layout.addWidget(self.group_input)

        btn_grid = QGridLayout()
        btn_add = QPushButton("➕ Add")
        btn_add.clicked.connect(self.add_group)
        btn_add.setToolTip("Add group to the list")
        btn_grid.addWidget(btn_add, 0, 0)
        
        btn_remove = QPushButton("➖ Remove")
        btn_remove.clicked.connect(self.remove_group)
        btn_remove.setToolTip("Remove group from the list")
        btn_grid.addWidget(btn_remove, 0, 1)
        settings_layout.addLayout(btn_grid)

        settings_layout.addSpacerItem(QSpacerItem(20, 15, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed))

        self.btn_open_folder = QPushButton("📁 Open Target Folder")
        self.btn_open_folder.clicked.connect(self.open_target_folder)
        self.btn_open_folder.setToolTip("Open target folder in file explorer")
        settings_layout.addWidget(self.btn_open_folder)

        settings_layout.addSpacerItem(QSpacerItem(20, 10, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed))
        
        log_grid=QGridLayout()
        # Log control buttons
        self.btn_clear_log = QPushButton("🗑 Clear Log")
        self.btn_clear_log.clicked.connect(self.clear_log)
        self.btn_clear_log.setToolTip("Clear all log entries")
        log_grid.addWidget(self.btn_clear_log,0,0)
        
        self.btn_copy_log = QPushButton("📋 Copy Log")
        self.btn_copy_log.clicked.connect(self.copy_log)
        self.btn_copy_log.setToolTip("Copy log to clipboard")
        log_grid.addWidget(self.btn_copy_log,0,1)

        settings_layout.addLayout(log_grid)

        settings_layout.addStretch()

        self.btn_setup_git = QPushButton("🔐 Setup Git Password")
        self.btn_setup_git.clicked.connect(self.setup_git_password)
        self.btn_setup_git.setToolTip("Configure password for git updates (first time)")
        settings_layout.addWidget(self.btn_setup_git)

        self.btn_check_updates = QPushButton("🔄 Check for Updates")
        self.btn_check_updates.clicked.connect(self.check_updates)
        self.btn_check_updates.setToolTip("Check for new version")
        settings_layout.addWidget(self.btn_check_updates)

        # Create a horizontal container for both widgets
        bottom_row = QHBoxLayout()

        # Theme toggle button with eye icon (compact)
        self.btn_theme = QPushButton("👁")
        self.btn_theme.setObjectName("themeButton")
        self.btn_theme.clicked.connect(self.toggle_theme)
        self.btn_theme.setToolTip("Toggle Dark/Light Mode")
        self.btn_theme.setMaximumSize(50, 40)
        bottom_row.addWidget(self.btn_theme)

        # Version label
        version_label = QLabel(f"5AI Scraper {VERSION}")
        version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version_label.setStyleSheet("color: #FFFFFF; font-size: 11px; font-weight: bold;")
        bottom_row.addWidget(version_label)

        # Add the horizontal layout to your settings layout
        settings_layout.addLayout(bottom_row)

        
        settings_panel.setLayout(settings_layout)

        # ====================== FINAL LAYOUT ======================
        main_layout.addWidget(left_panel, 1)
        main_layout.addLayout(middle_column, 2)
        main_layout.addWidget(settings_panel, 1)

    # ====================== UTILITY METHODS ======================
    def show_custom_calendar(self):
        """Toggle calendar visibility for custom date selection"""
        is_visible = self.calendar.isVisible()
        self.calendar.setVisible(not is_visible)
        self.btn_add_date.setVisible(not is_visible)
        if not is_visible:
            self.append_log("Custom date selection enabled - use calendar below", "INFO")
        else:
            self.append_log("Custom date selection disabled", "INFO")

    def update_stats(self):
        groups_count = len(selected_groups)
        dates_count = len(selected_dates)
        types_str = ", ".join(selected_data_types) if selected_data_types else "None"
        self.stats_label.setText(f"Groups: {groups_count} | Dates: {dates_count} | Data Types: {types_str}")

    def open_target_folder(self):
        if os.path.exists(TARGET_FOLDER):
            if sys.platform == 'win32':
                os.startfile(TARGET_FOLDER)
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', TARGET_FOLDER])
            else:
                subprocess.Popen(['xdg-open', TARGET_FOLDER])
            self.append_log(f"Opened folder: {TARGET_FOLDER}", "INFO")
        else:
            self.append_log("Target folder does not exist yet", "WARNING")

    def check_updates(self):
        import webbrowser
        webbrowser.open("https://github.com/your-repo/5ai-scraper")
        self.append_log("Opening update page in browser...", "INFO")

    def export_config(self):
        config_data = {
            "groups": chats,
            "selected_groups": selected_groups,
            "data_types": selected_data_types,
            "dates": selected_dates,
            "target_folder": TARGET_FOLDER,
            "base_dir": BASE_DIR
        }
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Export Configuration", "config.json", "JSON Files (*.json)"
        )
        if filepath:
            try:
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(config_data, f, indent=4)
                self.append_log(f"Configuration exported to {filepath}", "SUCCESS")
            except Exception as e:
                self.append_log(f"Export failed: {e}", "ERROR")

    def import_config(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Import Configuration", "", "JSON Files (*.json)"
        )
        if filepath:
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    config_data = json.load(f)
                
                global chats, selected_groups, selected_data_types, selected_dates, TARGET_FOLDER, BASE_DIR
                chats = config_data.get("groups", chats)
                selected_groups.clear()
                selected_groups.extend(config_data.get("selected_groups", []))
                selected_data_types.clear()
                selected_data_types.extend(config_data.get("data_types", []))
                selected_dates.clear()
                selected_dates.extend(config_data.get("dates", []))
                TARGET_FOLDER = config_data.get("target_folder", TARGET_FOLDER)
                BASE_DIR = config_data.get("base_dir", BASE_DIR)
                
                self.folder_display.setText(TARGET_FOLDER)
                self.update_dates_list()
                self.save_groups()
                self.save_data_types()
                self.save_dates()
                self.update_stats()
                
                self.append_log(f"Configuration imported from {filepath}", "SUCCESS")
            except Exception as e:
                self.append_log(f"Import failed: {e}", "ERROR")

    def clear_log(self):
        self.log_text.clear()
        self.append_log("Log cleared", "INFO")

    def copy_log(self):
        QApplication.clipboard().setText(self.log_text.toPlainText())
        self.append_log("Log copied to clipboard", "SUCCESS")

    # ====================== DATE MANAGEMENT ======================
    def add_date_preset(self, days):
        global selected_dates
        today = QDate.currentDate()
        added = 0
        for i in range(1, days + 1):
            date = today.addDays(-i)
            date_str = date.toString("yyyy-MM-dd")
            if date_str not in selected_dates:
                selected_dates.append(date_str)
                added += 1
        
        if added > 0:
            selected_dates.sort(reverse=True)
            self.update_dates_list()
            self.save_dates()
            self.update_stats()
            self.highlight_calendar_dates()
            self.append_log(f"Added {added} dates from preset", "SUCCESS")
        else:
            self.append_log("All preset dates already selected", "INFO")

    def add_selected_date(self):
        global selected_dates
        selected_qdate = self.calendar.selectedDate()
        
        if selected_qdate >= QDate.currentDate():
            self.append_log("Cannot select today or future dates!", "WARNING")
            return
        
        date_str = selected_qdate.toString("yyyy-MM-dd")
        
        if date_str not in selected_dates:
            selected_dates.append(date_str)
            selected_dates.sort(reverse=True)
            self.update_dates_list()
            self.save_dates()
            self.update_stats()
            self.highlight_calendar_dates()
            self.append_log(f"Added date: {date_str}", "SUCCESS")
        else:
            self.append_log(f"Date {date_str} already selected!", "WARNING")

    def clear_all_dates(self):
        global selected_dates
        if not selected_dates:
            self.append_log("No dates to clear", "INFO")
            return
        
        reply = QMessageBox.question(
            self, 'Confirm Clear',
            f"Remove all {len(selected_dates)} selected dates?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            selected_dates.clear()
            self.update_dates_list()
            self.save_dates()
            self.update_stats()
            self.highlight_calendar_dates()
            self.append_log("All dates cleared", "SUCCESS")

    def show_dates_context_menu(self, position):
        menu = QMenu()
        remove_action = menu.addAction("🗑 Remove this date")
        action = menu.exec(self.dates_list.mapToGlobal(position))
        
        if action == remove_action:
            current_item = self.dates_list.currentItem()
            if current_item:
                date_to_remove = current_item.text()
                if date_to_remove in selected_dates:
                    selected_dates.remove(date_to_remove)
                    self.update_dates_list()
                    self.save_dates()
                    self.update_stats()
                    self.highlight_calendar_dates()
                    self.append_log(f"Removed date: {date_to_remove}", "SUCCESS")

    def update_dates_list(self):
        self.dates_list.clear()
        for date in selected_dates:
            self.dates_list.addItem(date)

    def highlight_calendar_dates(self):
        # Reset all dates to default
        date_format = QTextCharFormat()
        self.calendar.setDateTextFormat(QDate(), date_format)
        
        # Highlight selected dates
        highlight_format = QTextCharFormat()
        highlight_format.setBackground(QColor(100, 180, 255, 100))
        highlight_format.setForeground(QColor(255, 255, 255))
        
        for date_str in selected_dates:
            date = QDate.fromString(date_str, "yyyy-MM-dd")
            self.calendar.setDateTextFormat(date, highlight_format)

    def save_dates(self):
        with open(SELECTED_DATES_FILE_PATH, "w") as f:
            f.write("\n".join(selected_dates))

    # ====================== GROUP MANAGEMENT ======================
    def load_saved_data(self):
        global chats, selected_data_types, selected_dates
        if os.path.exists(GROUPS_FILE_PATH):
            with open(GROUPS_FILE_PATH, "r", encoding="utf-8") as f:
                chats.extend([line.strip() for line in f if line.strip()])
        else:
            chats.extend(['Fall_of_the_Cabal', 'QDisclosure17', 'galactictruth', 
                         'STFNREPORT', 'realKarliBonne', 'LauraAbolichannel'])
            self.save_groups()

        if os.path.exists(DATA_TYPES_FILE_PATH):
            with open(DATA_TYPES_FILE_PATH, "r", encoding="utf-8") as f:
                selected_data_types.extend([line.strip() for line in f if line.strip()])

        if os.path.exists(SELECTED_DATES_FILE_PATH):
            with open(SELECTED_DATES_FILE_PATH, "r") as f:
                selected_dates.extend([line.strip() for line in f if line.strip()])
            self.update_dates_list()
        
        self.update_stats()
        self.highlight_calendar_dates()

    def save_groups(self):
        with open(GROUPS_FILE_PATH, "w", encoding="utf-8") as f:
            f.write("\n".join(chats))

    def save_data_types(self):
        with open(DATA_TYPES_FILE_PATH, "w", encoding="utf-8") as f:
            f.write("\n".join(selected_data_types))

    def add_group(self):
        link = self.group_input.text().strip()
        if not link:
            self.append_log("Please enter a group link", "WARNING")
            return
        if not link.startswith("https://t.me/") and not link.startswith("t.me/"):
            self.append_log("Invalid link! Use https://t.me/...", "ERROR")
            return
        name = link.split("/")[-1]
        if name not in chats:
            chats.append(name)
            self.save_groups()
            self.append_log(f"✓ Added group: {name}", "SUCCESS")
            if name not in selected_groups:
                selected_groups.append(name)
                self.update_stats()
        else:
            self.append_log(f"Group '{name}' already exists", "WARNING")
        self.group_input.clear()

    def remove_group(self):
        link = self.group_input.text().strip()
        if not link:
            self.append_log("Please enter a group link or name", "WARNING")
            return
        name = link.split("/")[-1] if "/" in link else link
        if name in chats:
            chats.remove(name)
            if name in selected_groups:
                selected_groups.remove(name)
                self.update_stats()
            self.save_groups()
            self.append_log(f"✓ Removed group: {name}", "SUCCESS")
        else:
            self.append_log(f"Group '{name}' not found", "ERROR")
        self.group_input.clear()

    def open_group_selector(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Select Groups to Scrape")
        dialog.resize(500, 650)
        layout = QVBoxLayout()
        
        # Search bar
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("🔍 Search:"))
        search_input = QLineEdit()
        search_input.setPlaceholderText("Filter groups...")
        search_layout.addWidget(search_input)
        layout.addLayout(search_layout)
        
        # Checkboxes container
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        
        checkboxes = {}
        for group in sorted(chats):
            cb = QCheckBox(group)
            cb.setChecked(group in selected_groups)
            checkboxes[group] = cb
            scroll_layout.addWidget(cb)
        
        # Search functionality
        def filter_groups(text):
            text = text.lower()
            for group, cb in checkboxes.items():
                cb.setVisible(text in group.lower())
        
        search_input.textChanged.connect(filter_groups)
        layout.addWidget(scroll_widget)

        # Select/Deselect all buttons
        btn_layout = QHBoxLayout()
        btn_select_all = QPushButton("✓ Select All")
        btn_select_all.clicked.connect(lambda: [cb.setChecked(True) for cb in checkboxes.values()])
        btn_layout.addWidget(btn_select_all)
        
        btn_deselect_all = QPushButton("✗ Deselect All")
        btn_deselect_all.clicked.connect(lambda: [cb.setChecked(False) for cb in checkboxes.values()])
        btn_layout.addWidget(btn_deselect_all)
        layout.addLayout(btn_layout)

        def confirm():
            selected_groups.clear()
            for group, cb in checkboxes.items():
                if cb.isChecked():
                    selected_groups.append(group)
            self.update_stats()
            self.append_log(f"✓ Selected {len(selected_groups)} groups", "SUCCESS")
            dialog.accept()

        btn_confirm = QPushButton("✓ Confirm Selection")
        btn_confirm.clicked.connect(confirm)
        btn_confirm.setStyleSheet("background-color: #00cc00; padding: 12px;")
        layout.addWidget(btn_confirm)
        
        dialog.setLayout(layout)
        dialog.exec()

    def open_data_type_selector(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Select Data Types to Download")
        dialog.resize(400, 350)
        layout = QVBoxLayout()
        
        layout.addWidget(QLabel("Choose what types of content to download:"))
        layout.addSpacerItem(QSpacerItem(20, 10, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed))
        
        options = ["Images", "Videos", "Audios", "Text", "Links"]
        icons = ["🖼", "🎥", "🎵", "📝", "🔗"]
        vars_dict = {}
        
        for opt, icon in zip(options, icons):
            cb = QCheckBox(f"{icon} {opt}")
            cb.setChecked(opt in selected_data_types)
            vars_dict[opt] = cb
            layout.addWidget(cb)
        
        layout.addSpacerItem(QSpacerItem(20, 20, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))

        def confirm():
            global selected_data_types
            selected_data_types.clear()
            selected_data_types.extend([opt for opt, cb in vars_dict.items() if cb.isChecked()])
            self.save_data_types()
            self.update_stats()
            self.append_log(f"✓ Data types: {', '.join(selected_data_types)}", "SUCCESS")
            dialog.accept()

        btn_confirm = QPushButton("✓ Confirm")
        btn_confirm.setStyleSheet("background-color: #00cc00; padding: 12px;")
        btn_confirm.clicked.connect(confirm)
        layout.addWidget(btn_confirm)
        
        dialog.setLayout(layout)
        dialog.exec()

    def browse_folder(self):
        global TARGET_FOLDER
        folder = QFileDialog.getExistingDirectory(self, "Select Target Folder", TARGET_FOLDER)
        if folder:
            TARGET_FOLDER = folder
            self.folder_display.setText(TARGET_FOLDER)
            self.append_log(f"Target folder set to: {TARGET_FOLDER}", "SUCCESS")

    def set_default_directory(self):
        global BASE_DIR
        reply = QMessageBox.question(
            self, 'Confirm',
            f"Set this as default directory?\n\n{TARGET_FOLDER}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            BASE_DIR = TARGET_FOLDER
            # Update .env file
            env_path = os.path.join(os.getcwd(), '.env')
            try:
                if os.path.exists(env_path):
                    with open(env_path, 'r') as f:
                        lines = f.readlines()
                    
                    with open(env_path, 'w') as f:
                        found = False
                        for line in lines:
                            if line.startswith('TAR_DIR='):
                                f.write(f'TAR_DIR={TARGET_FOLDER}\n')
                                found = True
                            else:
                                f.write(line)
                        if not found:
                            f.write(f'\nTAR_DIR={TARGET_FOLDER}\n')
                else:
                    with open(env_path, 'w') as f:
                        f.write(f'TAR_DIR={TARGET_FOLDER}\n')
                
                self.append_log(f"✓ Default directory updated in .env", "SUCCESS")
                QMessageBox.information(self, "Success", f"Default directory updated!\n\n{TARGET_FOLDER}")
            except Exception as e:
                self.append_log(f"✗ Failed to update .env: {e}", "ERROR")

    # ====================== LOGGING ======================
    def append_log(self, text, level="INFO"):
        if text.startswith("BYTES_DOWNLOADED:"): 
            return
        
        # Filter out unwanted lines
        if any(skip in text for skip in ["Download Speed:", "Time Elapsed:", "INFO -"]):
            return
        
        # Clean up log line
        text = re.sub(r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d+,\d+ - \w+ - ', '', text)
        
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        
        # Color coding
        if level == "ERROR":
            color = "#ff4444" if self.dark_theme else "#cc0000"
            icon = "✗"
        elif level == "WARNING":
            color = "#ff9500" if self.dark_theme else "#ff8800"
            icon = "⚠"
        elif level == "SUCCESS":
            color = "#00ff00" if self.dark_theme else "#00aa00"
            icon = "✓"
        else:
            color = "#e0e0e0" if self.dark_theme else "#222222"
            icon = "ℹ"
        
        html = f'<span style="color: #888;">[{timestamp}]</span> <span style="color: {color};">{icon} {text}</span><br>'
        cursor.insertHtml(html)
        
        # Auto-scroll to bottom
        self.log_text.setTextCursor(cursor)
        self.log_text.ensureCursorVisible()

    def update_log_from_queue(self):
        try:
            while True:
                text, level = self.text_queue.get_nowait()
                self.append_log(text, level)
        except queue.Empty:
            pass

    # ====================== SCRAPING CONTROL ======================
    def update_elapsed_time(self):
        if scraping_active and self.start_time:
            elapsed = int(time.time() - self.start_time)
            h, rem = divmod(elapsed, 3600)
            m, s = divmod(rem, 60)
            self.elapsed_label.setText(f"Time: {h:02d}:{m:02d}:{s:02d}")
            
            # Update speed
            global total_bytes_downloaded, download_start_time
            if download_start_time > 0 and elapsed > 0:
                speed_mbps = (total_bytes_downloaded / (1024 * 1024)) / elapsed
                self.speed_label.setText(f"Speed: {speed_mbps:.2f} MB/s")
                
                size_mb = total_bytes_downloaded / (1024 * 1024)
                if size_mb >= 1024:
                    self.size_label.setText(f"Downloaded: {size_mb/1024:.2f} GB")
                else:
                    self.size_label.setText(f"Downloaded: {size_mb:.1f} MB")
        else:
            self.elapsed_label.setText("Time: 00:00:00")

    def update_bytes_downloaded(self, bytes_val):
        global total_bytes_downloaded, download_start_time
        if download_start_time == 0:
            download_start_time = time.time()
        total_bytes_downloaded += bytes_val
        self.files_downloaded += 1
        self.files_label.setText(f"Files: {self.files_downloaded}")

    def start_scraping(self):
        global scraping_active, start_time, current_process, total_bytes_downloaded, download_start_time
        
        if scraping_active:
            self.append_log("Scraping already in progress!", "WARNING")
            return
        
        if not selected_groups:
            self.append_log("⚠ Please select at least one group!", "WARNING")
            QMessageBox.warning(self, "Missing Selection", "Please select at least one group to scrape.")
            return
        
        if not selected_data_types:
            self.append_log("⚠ Please select at least one data type!", "WARNING")
            QMessageBox.warning(self, "Missing Selection", "Please select at least one data type.")
            return
        
        if not selected_dates:
            self.append_log("⚠ Please select at least one date!", "WARNING")
            QMessageBox.warning(self, "Missing Selection", "Please select at least one date to scrape.")
            return

        scraping_active = True
        start_time = time.time()
        self.start_time = start_time
        total_bytes_downloaded = 0
        download_start_time = 0
        self.files_downloaded = 0
        
        self.status_light.setStyleSheet("color: #00ff00; font-size: 36px;")
        self.status_label.setText("Status: Running")
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.progress_bar.setValue(0)
        
        self.append_log("=" * 50, "INFO")
        self.append_log("🚀 Starting scraping operation...", "SUCCESS")
        self.append_log(f"Groups: {len(selected_groups)} | Dates: {len(selected_dates)}", "INFO")
        self.append_log(f"Data Types: {', '.join(selected_data_types)}", "INFO")
        self.append_log(f"Target: {TARGET_FOLDER}", "INFO")
        self.append_log("=" * 50, "INFO")

        dates_str = ','.join(selected_dates)

        cmd = [
            sys.executable, 'Scrapper_main.py',
            '--groups', ','.join(selected_groups),
            '--datatypes', ','.join(selected_data_types),
            '--dates', dates_str,
            '--target_folder', TARGET_FOLDER
        ]

        self.scraper_thread = ScraperThread(cmd)
        self.scraper_thread.log_signal.connect(lambda msg, lvl: self.text_queue.put((msg, lvl)))
        self.scraper_thread.bytes_signal.connect(self.update_bytes_downloaded)
        self.scraper_thread.input_required_signal.connect(self.handle_input_request)
        self.scraper_thread.finished_signal.connect(self.scraping_finished)
        self.scraper_thread.start()

    def handle_input_request(self, input_type):
        prompts = {
            "PHONE": ("Telegram Login - Phone Number", "Enter your phone number (with country code):\nExample: +919876543210", "+91", QLineEdit.EchoMode.Normal),
            "CODE": ("Verification Code", "Enter the code you received on Telegram:", "", QLineEdit.EchoMode.Normal),
            "PASSWORD": ("2FA Password", "Enter your 2FA password (if enabled):", "", QLineEdit.EchoMode.Password),
        }

        if input_type not in prompts:
            return

        title, label, default, echo_mode = prompts[input_type]

        text, ok = QInputDialog.getText(
            self, title, label, echo_mode, default
        )

        if ok and text.strip():
            self.scraper_thread.provide_input(text.strip())
            self.append_log(f"✓ {input_type} submitted", "SUCCESS")
        else:
            self.scraper_thread.provide_input("")  # Send empty line if cancelled
            self.append_log("✗ Input cancelled or empty", "WARNING")

    def stop_scraping(self):
        global scraping_active, current_process
        if not scraping_active:
            return
        
        reply = QMessageBox.question(
            self, 'Confirm Stop',
            "Are you sure you want to stop scraping?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            if current_process:
                current_process.terminate()
                self.append_log("⏹ Scraping stopped by user", "WARNING")
            if hasattr(self, 'scraper_thread'):
                self.scraper_thread.stop()
                self.scraper_thread.wait()

    # Update your existing methods in the main GUI class:

    def scraping_finished(self, success):
        global scraping_active, current_process
        scraping_active = False
        current_process = None
        
        self.status_light.setStyleSheet("color: #ff4444; font-size: 36px;")
        self.status_label.setText("Status: Idle")
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.progress_bar.setValue(100 if success else 0)
        
        elapsed = int(time.time() - self.start_time) if self.start_time else 0
        h, rem = divmod(elapsed, 3600)
        m, s = divmod(rem, 60)
        
        self.append_log("=" * 50, "INFO")
        if success:
            self.append_log(f"✓ Scraping completed in {h:02d}:{m:02d}:{s:02d}", "SUCCESS")
        else:
            self.append_log(f"✗ Scraping terminated", "ERROR")
        self.append_log(f"Files downloaded: {self.files_downloaded}", "INFO")
        size_mb = total_bytes_downloaded / (1024 * 1024)
        if size_mb >= 1024:
            self.append_log(f"Total size: {size_mb/1024:.2f} GB", "INFO")
        else:
            self.append_log(f"Total size: {size_mb:.1f} MB", "INFO")
        self.append_log("=" * 50, "INFO")
        
        # Desktop notification
        if NOTIFICATIONS_AVAILABLE:
            try:
                notification.notify(
                    title="5AI Scraper",
                    message=f"Scraping {'completed' if success else 'stopped'}! Downloaded {self.files_downloaded} files.",
                    app_name="5AI Scraper",
                    timeout=10
                )
            except:
                pass
        
        if success and self.auto_transcribe_checkbox.isChecked():
            self.append_log("Auto-transcription enabled → Starting transcription of downloaded videos...", "SUCCESS")
            QTimer.singleShot(2000, self.start_transcription)

    def start_transcription(self):
        try:
            script_path = 'updated_video_transcription.py'
            
            if not os.path.exists(script_path):
                self.append_log(f"✗ Script not found: {script_path}", "ERROR")
                QMessageBox.warning(self, "File Not Found", f"Transcription script not found:\n{script_path}")
                return
            
            # Check if transcription is already running
            if hasattr(self, 'transcription_thread') and self.transcription_thread.isRunning():
                self.append_log("⚠ Transcription already in progress!", "WARNING")
                return
            
            self.append_log("=" * 50, "INFO")
            self.append_log("Starting video transcription in background...", "SUCCESS")
            self.append_log(f"Processing folders from: {TARGET_FOLDER}", "INFO")
            self.append_log("=" * 50, "INFO")
            
            # Create and start transcription thread
            self.transcription_thread = TranscriptionThread(script_path, TARGET_FOLDER)
            self.transcription_thread.log_signal.connect(self.append_log)
            self.transcription_thread.finished_signal.connect(self.on_transcription_finished)
            self.transcription_thread.start()
            
        except Exception as e:
            self.append_log(f"✗ Failed to start transcription: {str(e)}", "ERROR")
            QMessageBox.critical(self, "Error", f"Failed to start transcription:\n{str(e)}")

    def on_transcription_finished(self, success):
        """Called when transcription thread completes"""
        self.append_log("=" * 50, "INFO")
        if success:
            self.append_log("✓ All video transcriptions completed successfully!", "SUCCESS")
            
            # Desktop notification for transcription completion
            if NOTIFICATIONS_AVAILABLE:
                try:
                    notification.notify(
                        title="5AI Scraper - Transcription",
                        message="Video transcription completed successfully!",
                        app_name="5AI Scraper",
                        timeout=10
                    )
                except:
                    pass
        else:
            self.append_log("⚠ Transcription completed with errors. Check logs above.", "WARNING")
        self.append_log("=" * 50, "INFO")

    def setup_telegram_auth(self):
        """Guide user through Telegram authentication setup"""
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setWindowTitle("Telegram Authentication Setup")
        msg.setText(
            "First-time Telegram Setup\n\n"
            "This will authenticate your Telegram account for scraping.\n\n"
            "You will need:\n"
            "• Your phone number (with country code)\n"
            "• Access to your Telegram app for OTP\n"
            "• 2FA password (if enabled)\n\n"
            "The authentication will happen automatically when you start scraping.\n"
            "Input dialogs will appear when needed."
        )
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg.exec()
        
        self.append_log("=" * 50, "INFO")
        self.append_log("ℹ When you start scraping, authentication dialogs will appear if needed", "INFO")
        self.append_log("=" * 50, "INFO")


    def setup_git_password(self):
        """Setup password for git updates (first time only)"""
        try:
            from update import GitHubPuller
            
            puller = GitHubPuller('sqlite.db')
            
            # Check if password already exists
            try:
                # Try to verify with empty password to check if one exists
                conn = sqlite3.connect('sqlite.db')
                cursor = conn.cursor()
                cursor.execute('SELECT id FROM auth_config WHERE id = 1')
                exists = cursor.fetchone() is not None
                conn.close()
                
                if exists:
                    QMessageBox.information(
                        self, 
                        "Already Configured",
                        "Git update password is already configured.\n\nUse 'Check for Updates' to update your repository."
                    )
                    return
            except:
                pass
            
            # Prompt for new password
            password, ok = QInputDialog.getText(
                self,
                "Setup Git Update Password",
                "Enter a secure password for git updates:\n(This password cannot be changed later)",
                QLineEdit.EchoMode.Password
            )
            
            if not ok or not password:
                return
            
            if len(password) < 6:
                QMessageBox.warning(self, "Weak Password", "Password must be at least 6 characters long")
                return
            
            # Confirm password
            confirm, ok = QInputDialog.getText(
                self,
                "Confirm Password",
                "Re-enter password to confirm:",
                QLineEdit.EchoMode.Password
            )
            
            if not ok or password != confirm:
                QMessageBox.warning(self, "Mismatch", "Passwords do not match!")
                return
            
            # Set password
            puller.set_initial_password(password)
            self.append_log("✓ Git update password configured successfully!", "SUCCESS")
            QMessageBox.information(
                self,
                "Success",
                "Git update password has been set!\n\n⚠️ This password CANNOT be changed.\n\nUse 'Check for Updates' button to pull latest changes."
            )
            
        except Exception as e:
            self.append_log(f"✗ Failed to setup git password: {str(e)}", "ERROR")
            QMessageBox.critical(self, "Error", f"Failed to setup password:\n{str(e)}")


    def check_updates(self):
        """Check and pull updates from GitHub"""
        try:
            import sqlite3
            from update import GitHubPuller
            
            # Check if password is configured
            try:
                conn = sqlite3.connect('sqlite.db')
                cursor = conn.cursor()
                cursor.execute('SELECT id FROM auth_config WHERE id = 1')
                exists = cursor.fetchone() is not None
                conn.close()
                
                if not exists:
                    reply = QMessageBox.question(
                        self,
                        "Password Not Set",
                        "Git update password is not configured.\n\nWould you like to set it up now?",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                    )
                    if reply == QMessageBox.StandardButton.Yes:
                        self.setup_git_password()
                    return
            except:
                pass
            
            # Prompt for password
            password, ok = QInputDialog.getText(
                self,
                "Authenticate",
                "Enter your git update password:",
                QLineEdit.EchoMode.Password
            )
            
            if not ok or not password:
                return
            
            self.append_log("=" * 50, "INFO")
            self.append_log("🔄 Checking for updates from GitHub...", "INFO")
            
            # Disable update button during operation
            self.btn_check_updates.setEnabled(False)
            self.btn_check_updates.setText("⏳ Updating...")
            
            # Start update thread
            self.git_update_thread = GitUpdateThread(password, os.getcwd())
            self.git_update_thread.log_signal.connect(lambda msg, lvl: self.append_log(msg, lvl))
            self.git_update_thread.finished_signal.connect(self.on_update_finished)
            self.git_update_thread.start()
            
        except Exception as e:
            self.append_log(f"✗ Update failed: {str(e)}", "ERROR")
            QMessageBox.critical(self, "Error", f"Update failed:\n{str(e)}")
            self.btn_check_updates.setEnabled(True)
            self.btn_check_updates.setText("🔄 Check for Updates")


    def on_update_finished(self, success, message):
        """Called when git update completes"""
        self.btn_check_updates.setEnabled(True)
        self.btn_check_updates.setText("🔄 Check for Updates")
        
        self.append_log("=" * 50, "INFO")
        
        if success:
            QMessageBox.information(
                self,
                "Update Successful",
                f"{message}\n\nThe application has been updated!\n\nPlease restart the application for changes to take effect."
            )
            
            # Ask if user wants to restart
            reply = QMessageBox.question(
                self,
                "Restart Application?",
                "Would you like to restart the application now?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                QApplication.quit()
                os.execl(sys.executable, sys.executable, *sys.argv)
        else:
            QMessageBox.warning(
                self,
                "Update Failed",
                f"Failed to update:\n\n{message}\n\nPlease check your internet connection and try again."
            )
