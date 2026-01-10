from telegram_scraper import ScraperGUI, QApplication
import sys
import cache

# ==================cache cleaning =================
cache.cache_clean("selected_dates.txt")
cache.cache_clean("selected_date.txt")
cache.cache_clean("selected_data_types.txt")

# ====================== MAIN ======================
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = ScraperGUI()
    window.show()
    sys.exit(app.exec())
