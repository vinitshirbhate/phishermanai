from __future__ import print_function
import os
import time
import base64
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import requests
from twilio.rest import Client
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Gmail API scope
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

# Twilio configuration
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_PHONE_NUMBER = os.getenv('TWILIO_PHONE_NUMBER')
RECIPIENT_PHONE_NUMBER = os.getenv('RECIPIENT_PHONE_NUMBER')

def get_message_body(message):
    """Extract plain text body from Gmail message payload"""
    payload = message.get('payload', {})
    parts = payload.get('parts', [])
    if parts:
        for part in parts:
            if part.get('mimeType') == 'text/plain':
                data = part.get('body', {}).get('data')
                if data:
                    return base64.urlsafe_b64decode(data).decode('utf-8')
    else:
        data = payload.get('body', {}).get('data')
        if data:
            return base64.urlsafe_b64decode(data).decode('utf-8')
    return "(No text body found)"

def get_gmail_service():
    """Authenticate and return Gmail API service"""
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=8080)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    return build('gmail', 'v1', credentials=creds)

def send_sms_via_twilio(message_text: str):
    """Send SMS via Twilio"""
    if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER, RECIPIENT_PHONE_NUMBER]):
        print("⚠️ Twilio credentials missing — skipping SMS.")
        return

    try:
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        message = client.messages.create(
            body=message_text,
            from_=TWILIO_PHONE_NUMBER,
            to=RECIPIENT_PHONE_NUMBER
        )
        print(f"📱 SMS sent successfully! SID: {message.sid}")
    except Exception as e:
        print(f"⚠️ Failed to send SMS: {e}")

def fetch_latest_email(service):
    """Fetch the single latest email"""
    results = service.users().messages().list(userId='me', maxResults=1).execute()
    messages = results.get('messages', [])
    if not messages:
        return None

    msg_id = messages[0]['id']
    m = service.users().messages().get(
        userId='me',
        id=msg_id,
        format='full'
    ).execute()

    headers = m.get('payload', {}).get('headers', [])
    subject = next((h['value'] for h in headers if h['name'] == 'Subject'), '(No Subject)')
    sender = next((h['value'] for h in headers if h['name'] == 'From'), '(Unknown Sender)')
    body = get_message_body(m)

    print(f"\n📧 New Email Detected!")
    print(f"From: {sender}")
    print(f"Subject: {subject}")
    print(f"Body:\n{body.strip()[:400]}")
    print('-' * 70)

    # Send to your phishing-detection endpoint
    try:
        res = requests.post(
            'https://fraud-detect-1-6er0.onrender.com/detect',
            json={"text": body},
            timeout=15
        )
        res.raise_for_status()
        print(f"✅ Email forwarded to detection API. Status: {res.status_code}")
        data = res.json()
        print(f"Response: {data}")

        # Check if phishing is detected - only send SMS for phishing, not for safe messages
        if 'message' in data:
            message_text = data['message'].upper()
            # Only send SMS if message does NOT contain "SAFE" (i.e., phishing detected)
            if 'SAFE' not in message_text:
                print("🚨 Phishing detected! Sending SMS alert...")
                send_sms_via_twilio(data['message'])
            else:
                print("✅ Email is safe. No SMS sent.")
        else:
            # If no message field, skip SMS
            print("⚠️ No message field in response. Skipping SMS.")

    except Exception as e:
        print(f"⚠️ Error forwarding to detection API: {e}")

    return msg_id

def main():
    service = get_gmail_service()
    print("📬 Gmail Live Monitor Started...")

    # Fetch and show the latest email once
    last_seen_id = fetch_latest_email(service)

    print("\n🔁 Monitoring for new emails...\n")

    # Keep polling for new ones
    while True:
        time.sleep(12)
        results = service.users().messages().list(userId='me', maxResults=1).execute()
        messages = results.get('messages', [])
        if not messages:
            continue

        latest_id = messages[0]['id']

        # Check if a new email arrived
        if latest_id != last_seen_id:
            last_seen_id = fetch_latest_email(service)
            print("✅ New email processed.\n")

if __name__ == '__main__':
    main()