# catalog.py

import pandas as pd
from pathlib import Path

# Change this if you renamed the CSV
CSV_FILE = "Survey on Restaurant around Seri Iskandar (Responses) - Form Responses 1.csv"


def load_catalog():
    """
    Load the CSV and return a raw DataFrame.
    For now, no renaming or scoring – just to confirm it works.
    """
    csv_path = Path(__file__).parent / CSV_FILE
    df = pd.read_csv(csv_path)
    return df
