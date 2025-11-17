import os, sys, subprocess, logging, asyncio, argparse
from datetime import datetime, timedelta
from telethon.errors import SessionPasswordNeededError

# Determine the base directory for the executable or script
if getattr(sys, 'frozen', False):  # If the script is running as a frozen executable
    base_dir = os.path.dirname(sys.executable)
else:
    base_dir = os.path.dirname(os.path.abspath(__file__))

# List of required packages
required_packages = [
    'customtkinter', 'tkcalendar', 'requests', 'telethon', 'spacy', 'pandas', 'numpy'
]

# Function to install missing packages
def install(package):
    try:
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', package])
    except Exception as e:
        print(f"Failed to install {package}. Please ensure it's available. Error: {e}")

# Check and install each package if missing
for package in required_packages:
    try:
        __import__(package)
    except ImportError:
        print(f'{package} is missing. Installing...')
        install(package)

try:
    from Scrapper_main import start_scraping  # Importing the start_scraping function from updated_scraper.py
except ImportError as e:
    logging.error(f"Failed to import start_scraping from updated_scraper.py: {e}")
    sys.exit(1)

def load_selected_groups():
    # Load selected groups from file
    groups_file = os.path.join(base_dir, "selected_groups.txt")
    if os.path.exists(groups_file):
        with open(groups_file, "r") as f:
            groups = list(set(line.strip() for line in f if line.strip()))
        logging.info(f"Loaded {len(groups)} groups from {groups_file}.")
        return groups
    else:
        logging.error(
            f"Groups file not found at '{groups_file}'. Please create the file and list your Telegram groups."
        )
        return []

def load_selected_data_types():
    # Load selected data types from file
    data_types_file = os.path.join(base_dir, "selected_data_types.txt")
    if os.path.exists(data_types_file):
        with open(data_types_file, "r") as f:
            # Read lines, strip whitespace, and capitalize to ensure consistency
            data_types = [line.strip().capitalize() for line in f if line.strip()]
        logging.info(f"Loaded {len(data_types)} data types from {data_types_file}.")
        return data_types
    else:
        logging.error(
            f"Data types file not found at '{data_types_file}'. Please create the file and list your desired data types."
        )
        return []

def get_scrape_date(days):
    """
    Calculate the date to scrape based on the number of days back from today.

    Args:
        days (int): Number of days back to scrape. 1 for yesterday, 2 for day before yesterday, etc.

    Returns:
        datetime.date: The calculated scrape date.
    """
    return datetime.utcnow().date() - timedelta(days=days)

# Convert main to an async function
async def main():
    logging.info("Main process started.")

    # Load selected groups and data types
    selected_groups = load_selected_groups()
    selected_data_types = load_selected_data_types()

    # Validate loaded groups and data types
    if not selected_groups:
        logging.error(
            "No groups selected for scraping. Please add groups to 'selected_groups.txt'. Exiting."
        )
        sys.exit(1)
    if not selected_data_types:
        logging.error(
            "No data types selected for scraping. Please add data types to 'selected_data_types.txt'. Exiting."
        )
        sys.exit(1)

    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Main Script for Scraping Telegram Groups")
    parser.add_argument(
        "target_folder",
        nargs="?",
        default=None,
        help="Target folder for saving scraped data. If not provided, a default folder is used.",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=1,
        help="Number of days back to scrape (1 for yesterday, 2 for day before yesterday, etc.). Default is 1.",
    )
    args = parser.parse_args()

    # Determine the target folder
    target_folder = args.target_folder
    if target_folder:
        logging.info(f"Using target folder from command-line argument: {target_folder}")
    else:
        # Default target folder
        target_folder = os.path.join(base_dir, "Database")
        logging.info(f"No target folder specified. Using default: {target_folder}")

    # Ensure the target folder exists; if not, create it
    if not os.path.exists(target_folder):
        try:
            os.makedirs(target_folder)
            logging.info(f"Created target folder: {target_folder}")
        except Exception as e:
            logging.error(f"Failed to create target folder '{target_folder}': {e}")
            sys.exit(1)
    else:
        logging.info(f"Target folder exists: {target_folder}")

    # Determine the scrape date based on the '--days' argument
    days_back = args.days
    if days_back < 0:
        logging.error(f"Invalid '--days' value: {days_back}. It should be a positive integer.")
        sys.exit(1)
    scrape_date = get_scrape_date(days_back)
    logging.info(
        f"Scraping data for date: {scrape_date.strftime('%Y-%m-%d')} (Days back: {days_back})"
    )

    try:
        # Call the scraper with the selected groups, data types, scrape date, and target folder
        await start_scraping(
            selected_groups, selected_data_types, scrape_date, target_folder=target_folder
        )
    except SessionPasswordNeededError:
        logging.error(
            "Two-step verification is enabled for this Telegram account. Please provide your password."
        )
        # Implement secure password handling if necessary
        sys.exit(1)
    except Exception as e:
        logging.exception(f"An error occurred during scraping: {e}")
        sys.exit(1)

    logging.info("Main process completed successfully.")

# Use asyncio.run() to run the async main function
if __name__ == "__main__":
    # Configure logging to print to stdout
    logging.basicConfig(
        level=logging.INFO,  # Set to INFO to reduce verbosity; change to DEBUG if needed
        format="%(asctime)s - %(levelname)s - %(message)s",
        stream=sys.stdout,
    )

    try:
        asyncio.run(main())
    except Exception as e:
        logging.exception(f"An unexpected error occurred: {e}")
        sys.exit(1)
