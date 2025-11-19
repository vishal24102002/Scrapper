from telegram_scraper import ScraperGUI, QApplication
import sys

# ====================== MAIN ======================
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = ScraperGUI()
    window.show()
    sys.exit(app.exec())