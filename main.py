from telegram_scraper import ScraperGUI, QApplication
import sys


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = ScraperGUI()
    win.show()
    sys.exit(app.exec())