import os
from decouple import config

base=config("BASE_DIR")

def cache_clean(file_name):
    # Clear a text file by opening it in write mode
    with open(os.path.join(base,"data_files",file_name), 'w') as file:
        pass
