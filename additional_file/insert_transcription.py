import os
import sys
import pandas as pd
import sqlite3
import datetime

# Determine the base directory for the executable or script
base_dir = (
    os.path.dirname(sys.executable) if getattr(sys, 'frozen', False)
    else os.path.dirname(os.path.abspath(__file__))
)

# Base direc tory where the "Database" folder is located
database_dir = os.path.join(base_dir, "Database")

# Calculate the scraping date (e.g., 8 days ago)
scrape_date = datetime.date.today() - datetime.timedelta(days=8)
scrape_date_folder = os.path.join(database_dir, scrape_date.strftime("%Y-%m-%d"))

# List of groups
chats = ['Fall_of_the_Cabal', 'QDisclosure17', 'galactictruth']

# Check if scrape_date_folder exists
if os.path.exists(scrape_date_folder):
    print(f"Folder exists: {scrape_date_folder}")
else:
    print(f"Folder not found: {scrape_date_folder}")

# Create (or connect to) the SQLite database
conn = sqlite3.connect('transcription.db')
cur = conn.cursor()

# Create the table if it doesn't exist
cur.execute('''
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_name TEXT,
    date TEXT,
    content TEXT
)
''')

for chat in chats:
    print(f"Processing group: {chat}")
    
    # Define the folder paths
    chat_folder = os.path.join(scrape_date_folder, chat)
    text_folder = os.path.join(chat_folder, 'Text')
    transcription_folder = os.path.join(chat_folder, 'Videos', 'Transcription')

    print(f"Chat folder: {chat_folder}")
    print(f"Text folder: {text_folder}")
    print(f"Transcription folder: {transcription_folder}")

    # Process text messages from the Excel file
    if os.path.exists(text_folder):
        # Get the path to the Excel file with the correct format
        excel_file = os.path.join(text_folder, f"{chat}_messages.xlsx")
        
        if os.path.exists(excel_file):
            print(f"Processing Excel file: {excel_file}")
            df = pd.read_excel(excel_file)

            # Ensure the DataFrame has the necessary columns
            if 'text' in df.columns:
                # Insert each message into the database
                for idx, row in df.iterrows():
                    content = row['text']
                    date = scrape_date.strftime('%Y-%m-%d')  # Using scrape_date as message date
                    cur.execute(
                        'INSERT INTO messages (chat_name, date, content) VALUES (?, ?, ?)',
                        (chat, date, content)
                    )
            else:
                print(f"'text' column not found in Excel file for {chat}. Skipping...")
        else:
            print(f"Excel file not found for {chat}. Skipping...")
    else:
        print(f"Text folder not found for {chat}. Skipping...")

    # Process transcriptions from the Videos folder
    if os.path.exists(transcription_folder):
        for transcription_file in os.listdir(transcription_folder):
            if transcription_file.endswith('.txt'):
                transcription_path = os.path.join(transcription_folder, transcription_file)
                print(f"Processing transcription file: {transcription_path}")

                with open(transcription_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    date = scrape_date.strftime('%Y-%m-%d')  # Using scrape_date as message date
                    cur.execute(
                        'INSERT INTO messages (chat_name, date, content) VALUES (?, ?, ?)',
                        (chat, date, content)
                    )
    else:
        print(f"Transcription folder not found for {chat}. Skipping...")

# Commit the changes and close the database connection
conn.commit()
conn.close()

print("Data transfer to SQLite completed.")
