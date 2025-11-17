import os, sys, subprocess, time, queue, re, logging, io, json
from decouple import config
from datetime import datetime, timedelta
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QTextEdit, QCheckBox, QCalendarWidget,
    QLineEdit, QFileDialog, QGroupBox, QSpacerItem, QSizePolicy,
    QMessageBox, QDialog, QListWidget, QProgressBar, QMenu, QToolButton
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
VERSION = "v2.3"

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
TARGET_FOLDER = os.path.join("data_files","Database")
CONFIG_FILE = os.path.join("data_files", "config.json")

# ====================== Worker Thread ======================
class ScraperThread(QThread):
    log_signal = pyqtSignal(str, str)  # message, level
    progress_signal = pyqtSignal(int)
    bytes_signal = pyqtSignal(int)
    finished_signal = pyqtSignal(bool)  # success

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
                    line = line.rstrip()
                    # Parse special markers
                    if line.startswith("BYTES_DOWNLOADED:"):
                        try:
                            bytes_val = int(line.split(":")[1])
                            self.bytes_signal.emit(bytes_val)
                        except:
                            pass
                    elif "ERROR" in line.upper() or "FAILED" in line.upper():
                        self.log_signal.emit(line, "ERROR")
                    elif "WARNING" in line.upper():
                        self.log_signal.emit(line, "WARNING")
                    elif "SUCCESS" in line.upper() or "COMPLETED" in line.upper():
                        self.log_signal.emit(line, "SUCCESS")
                    else:
                        self.log_signal.emit(line, "INFO")
            
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
                QPushButton#themeButton { background-color: #ff9500; padding: 8px; }
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
                QPushButton#themeButton { background-color: #ff9500; padding: 8px; }
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
        if self.dark_theme:
            self.btn_theme.setText("☀ Light Mode")
            self.append_log("Switched to Dark Theme", "INFO")
        else:
            self.btn_theme.setText("🌙 Dark Mode")
            self.append_log("Switched to Light Theme", "INFO")

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setSpacing(15)

        # ====================== LEFT PANEL ======================
        left_panel = QGroupBox("⚙ Control Panel")
        left_layout = QVBoxLayout()
        left_panel.setLayout(left_layout)
        
        left_layout.addSpacerItem(QSpacerItem(20, 10, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed))

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
            ("Last 7 Days", 7, "Select past week"),
            ("Last 30 Days", 30, "Select past month"),
            ("All Time", 365, "Select past year")
        ]
        for i, (label, days, tooltip) in enumerate(presets):
            btn = QPushButton(label)
            btn.setToolTip(tooltip)
            btn.clicked.connect(lambda checked, d=days: self.add_date_preset(d))
            preset_layout.addWidget(btn, i // 2, i % 2)
        left_layout.addLayout(preset_layout)
        
        self.calendar = QCalendarWidget()
        self.calendar.setGridVisible(True)
        self.calendar.setMaximumDate(QDate.currentDate().addDays(-1))
        self.calendar.clicked.connect(self.highlight_calendar_dates)
        left_layout.addWidget(self.calendar)
        
        date_btn_layout = QHBoxLayout()
        self.btn_add_date = QPushButton("➕ Add Date")
        self.btn_add_date.clicked.connect(self.add_selected_date)
        self.btn_add_date.setToolTip("Add selected date to the list")
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

        # Action Buttons
        action_layout = QHBoxLayout()
        self.btn_start = QPushButton("▶ START SCRAPING")
        self.btn_start.setObjectName("startButton")
        self.btn_start.clicked.connect(self.start_scraping)
        self.btn_start.setToolTip("Begin scraping selected groups and dates")
        action_layout.addWidget(self.btn_start)

        self.btn_stop = QPushButton("⏹ STOP")
        self.btn_stop.setObjectName("stopButton")
        self.btn_stop.clicked.connect(self.stop_scraping)
        self.btn_stop.setEnabled(False)
        self.btn_stop.setToolTip("Stop current scraping operation")
        action_layout.addWidget(self.btn_stop)
        left_layout.addLayout(action_layout)

        transcribe_layout = QHBoxLayout()
        self.btn_transcribe = QPushButton("🎙 Transcription")
        self.btn_transcribe.clicked.connect(self.start_transcription)
        self.btn_transcribe.setToolTip("Launch video transcription tool")
        transcribe_layout.addWidget(self.btn_transcribe)
        
        self.btn_fetch_news = QPushButton("📰 Fetch News")
        self.btn_fetch_news.clicked.connect(lambda: self.append_log("Fetch News - coming soon", "INFO"))
        self.btn_fetch_news.setToolTip("Fetch news articles (coming soon)")
        transcribe_layout.addWidget(self.btn_fetch_news)
        left_layout.addLayout(transcribe_layout)

        left_layout.addStretch()

        # ====================== MIDDLE COLUMN - LOG + STATUS ======================
        middle_column = QVBoxLayout()
        
        # Stats bar
        stats_panel = QGroupBox("📊 Statistics")
        stats_layout = QVBoxLayout()
        self.stats_label = QLabel("Groups: 0 | Dates: 0 | Data Types: None")
        self.stats_label.setObjectName("statsLabel")
        self.stats_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        stats_layout.addWidget(self.stats_label)
        stats_panel.setLayout(stats_layout)
        middle_column.addWidget(stats_panel)

        # Log panel
        log_panel = QGroupBox("Live Output Log")
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

        self.btn_check_updates = QPushButton("🔄 Check for Updates")
        self.btn_check_updates.clicked.connect(self.check_updates)
        self.btn_check_updates.setToolTip("Check for new version")
        settings_layout.addWidget(self.btn_check_updates)
        
        # Open folder button
        self.btn_open_folder = QPushButton("📁 Open Target Folder")
        self.btn_open_folder.clicked.connect(self.open_target_folder)
        self.btn_open_folder.setToolTip("Open target folder in file explorer")
        settings_layout.addWidget(self.btn_open_folder)


        settings_layout.addStretch()

        log_btn_layout = QHBoxLayout()
        self.btn_clear_log = QPushButton("🗑 Log")
        self.btn_clear_log.clicked.connect(self.clear_log)
        self.btn_clear_log.setToolTip("Clear all log entries")
        log_btn_layout.addWidget(self.btn_clear_log)
        
        self.btn_copy_log = QPushButton("📋 Log")
        self.btn_copy_log.clicked.connect(self.copy_log)
        self.btn_copy_log.setToolTip("Copy log to clipboard")
        log_btn_layout.addWidget(self.btn_copy_log)
        settings_layout.addLayout(log_btn_layout)

        # Theme toggle button at top
        self.btn_theme = QPushButton("☀ Light Mode")
        self.btn_theme.setObjectName("themeButton")
        self.btn_theme.clicked.connect(self.toggle_theme)
        self.btn_theme.setToolTip("Switch between Dark and Light themes")
        settings_layout.addWidget(self.btn_theme)
        
        # Version label at bottom
        version_label = QLabel(f"5AI Scraper {VERSION}")
        version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version_label.setStyleSheet("color: #888; font-size: 11px;")
        settings_layout.addWidget(version_label)
        
        settings_panel.setLayout(settings_layout)

        # ====================== FINAL LAYOUT ======================
        main_layout.addWidget(left_panel, 1)
        main_layout.addLayout(middle_column, 2)
        main_layout.addWidget(settings_panel, 1)

    # ====================== UTILITY METHODS ======================
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
                            if line.startswith('BASE_DIR='):
                                f.write(f'BASE_DIR={TARGET_FOLDER}\n')
                                found = True
                            else:
                                f.write(line)
                        if not found:
                            f.write(f'\nBASE_DIR={TARGET_FOLDER}\n')
                else:
                    with open(env_path, 'w') as f:
                        f.write(f'BASE_DIR={TARGET_FOLDER}\n')
                
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
        self.scraper_thread.finished_signal.connect(self.scraping_finished)
        self.scraper_thread.start()

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

    def start_transcription(self):
        try:
            script_path = 'updated_video_transcription.py'
            if os.path.exists(script_path):
                subprocess.Popen([sys.executable, script_path])
                self.append_log("✓ Transcription tool launched", "SUCCESS")
            else:
                self.append_log(f"✗ Script not found: {script_path}", "ERROR")
                QMessageBox.warning(self, "File Not Found", f"Transcription script not found:\n{script_path}")
        except Exception as e:
            self.append_log(f"✗ Failed to start transcription: {e}", "ERROR")
