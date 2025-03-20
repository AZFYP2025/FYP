import firebase_admin
from firebase_admin import credentials, db
import pandas as pd
import hashlib
import stanza  # NLP for Malay
from googleapiclient.discovery import build
from google.oauth2 import service_account
import logging
import re

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Initialize Firebase
def initialize_firebase():
    try:
        cred = credentials.Certificate("firebase-credentials.json")
        firebase_admin.initialize_app(cred, {"databaseURL": "https://safezone-660a9.firebaseio.com/"})
        logging.info("Firebase initialized successfully.")
    except Exception as e:
        logging.error(f"Error initializing Firebase: {e}")
        raise

# Google Sheets API Setup
SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']
SHEET_ID = "1CNo8eLCASEfd7ktOgiUrzT8KBkAWhW5sPON1BITBKvM"
RANGE_NAME = "Sheet1!A:D"

# Initialize NLP tools
def initialize_nlp():
    try:
        stanza.download("ms")  # Download Malay language model
        nlp = stanza.Pipeline("ms")
        logging.info("NLP pipeline initialized successfully.")
        return nlp
    except Exception as e:
        logging.error(f"Error initializing NLP pipeline: {e}")
        raise

# Fetch data from Google Sheets
def fetch_google_sheets():
    try:
        creds = service_account.Credentials.from_service_account_file("google-credentials.json", scopes=SCOPES)
        service = build("sheets", "v4", credentials=creds)
        sheet = service.spreadsheets()
        result = sheet.values().get(spreadsheetId=SHEET_ID, range=RANGE_NAME).execute()
        values = result.get("values", [])
        
        if not values:
            logging.warning("No data found in Google Sheets.")
            return pd.DataFrame()
        
        # Convert to DataFrame
        df = pd.DataFrame(values[1:], columns=values[0])
        logging.info(f"Fetched {len(df)} rows from Google Sheets.")
        return df
    except Exception as e:
        logging.error(f"Error fetching data from Google Sheets: {e}")
        return pd.DataFrame()

# Preprocess text (clean and normalize)
def preprocess_text(text):
    try:
        # Remove special characters, URLs, and extra spaces
        text = re.sub(r"http\S+|www\S+|https\S+", "", text, flags=re.MULTILINE)  # Remove URLs
        text = re.sub(r"\W", " ", text)  # Remove special characters
        text = re.sub(r"\s+", " ", text).strip()  # Remove extra spaces
        return text
    except Exception as e:
        logging.error(f"Error preprocessing text: {e}")
        return text

# Categorize crime based on text (dummy implementation)
def categorize_crime(text):
    try:
        # Dummy logic for categorization (replace with actual logic)
        if "curi" in text.lower():
            return "Theft", "Petty Theft"
        elif "rompak" in text.lower():
            return "Robbery", "Armed Robbery"
        else:
            return "Other", "Unknown"
    except Exception as e:
        logging.error(f"Error categorizing crime: {e}")
        return "Other", "Unknown"

# Generate Unique Row ID
def generate_row_id(row):
    try:
        unique_string = f"{row['Timestamp']}-{row['Tweet Text']}".encode('utf-8')
        return hashlib.md5(unique_string).hexdigest()
    except Exception as e:
        logging.error(f"Error generating row ID: {e}")
        return None

# Extract State and District from Text using NLP
def extract_location(text, nlp):
    try:
        doc = nlp(text)
        locations = [ent.text for ent in doc.ents if ent.type == "GPE"]
        return locations[0] if locations else "Unknown"
    except Exception as e:
        logging.error(f"Error extracting location: {e}")
        return "Unknown"

# Process and Upload Data
def process_and_upload():
    try:
        logging.info("Starting data processing and upload...")
        
        # Fetch data from Google Sheets
        df = fetch_google_sheets()
        if df.empty:
            logging.info("No data to process.")
            return

        # Get already processed IDs from Firebase
        processed_ref = db.reference("processed_ids")
        processed_ids = processed_ref.get() or {}

        # Filter new rows
        new_rows = []
        for _, row in df.iterrows():
            row_id = generate_row_id(row)
            if row_id and row_id not in processed_ids:
                new_rows.append(row)

        if not new_rows:
            logging.info("✅ No new data to process.")
            return

        # Process new rows
        new_df = pd.DataFrame(new_rows)
        new_df["Cleaned Text"] = new_df["Tweet Text"].apply(preprocess_text)
        new_df[["Crime Category", "Crime Type"]] = new_df["Cleaned Text"].apply(lambda x: pd.Series(categorize_crime(x)))
        new_df[["State", "District"]] = new_df["Tweet Text"].apply(lambda x: pd.Series(extract_location(x, nlp)))

        # Upload data to Firebase
        crime_ref = db.reference("crime_data")
        batch = {}
        
        for _, row in new_df.iterrows():
            row_id = generate_row_id(row)
            if row_id:
                crime_data = {
                    "state": row["State"],
                    "district": row["District"],
                    "category": row["Crime Category"],
                    "type": row["Crime Type"],
                    "date": row["Timestamp"]
                }
                batch[row_id] = crime_data
                processed_ids[row_id] = True  # Mark as processed

        # Atomic update to Firebase
        crime_ref.update(batch)
        processed_ref.update(processed_ids)
        logging.info(f"✅ Added {len(new_df)} new records to Firebase!")
    except Exception as e:
        logging.error(f"Error in process_and_upload: {e}")

# Main execution
if __name__ == "__main__":
    try:
        initialize_firebase()
        nlp = initialize_nlp()
        process_and_upload()
    except Exception as e:
        logging.error(f"Script failed: {e}")
