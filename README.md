# Scrapper
![Version](https://img.shields.io/badge/version-v0.0.1-red) ![system](https://img.shields.io/badge/system-Windows,linux-blue) ![Author](https://img.shields.io/badge/Author-Vishal24102002-orange) 

---
## Introduction
This is a telegram scrapper that can be used to scrap various types of data from the telegram itself use your own telegram api key

---
### Features
- live data scrapper
- authentication
- Fully Automatic 

---
## Installation Guide

- **Step1** : cloning the project from the repo
```bash
git clone https://github.com/vishal24102002/Scrapper.git
```

- **Step2** : setting up the virtual environment for python to run
  
**For Linux**
  ```bash
  python3 -m venv venv
  source venv/bin/activate
  pip install -r requirements.txt
  ```
**For Windows**
  ```shell
  python -m venv venv
  venv\scripts\activate
  pip install -r requirements.txt
  ```

- **Step3** : Setup the .env file 

<pre type="sh">
# Scrapper main.py .env file structure
api_id = //telegram api key
api_hash = //telegram api hash 
chats = //channel names

BASE_DIR=/home/itm/Desktop/personal_task/Scrapper/Scrapper/
TAR_DIR=/home/itm/Desktop/personal_task/Scrapper/Scrapper/data_files/Database
API_KEY = //(optional but make the variable)
CH_USER = 

#updated_fetch_important_topics.py
youtube_api_key = //(optional but make the variable)
twitter_bearer_token = //(optional but make the variable)

Vosk_Model= //vosk model path if dont then keep it empty as well
</pre>

- **Step4** : run the main.py
```bash
python main.py
```
