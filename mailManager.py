import os
import smtplib
from email.message import EmailMessage
from dotenv import load_dotenv

# Učitaj .env fajl
load_dotenv(dotenv_path='../.env')

def send_email(to_email: str, subject: str, content: str):
    """
    Funkcija koja šalje mejl koristeći SMTP podatke iz .env
    """
    SMTP_SERVER = os.getenv("SMTP_SERVER")
    SMTP_PORT = int(os.getenv("SMTP_PORT", 465))
    EMAIL = os.getenv("EMAIL")
    EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
    
    if not all([SMTP_SERVER, SMTP_PORT, EMAIL, EMAIL_PASSWORD]):
        print("❌ Nedostaju SMTP varijable u .env")
        return
    
    msg = EmailMessage()
    msg.set_content(content)
    msg["Subject"] = subject
    msg["From"] = EMAIL
    msg["To"] = to_email
    
    try:
        print(EMAIL, EMAIL_PASSWORD)
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as smtp:
            smtp.login(EMAIL, EMAIL_PASSWORD)
            smtp.send_message(msg)
        print(f"✅ Mejl poslat na {to_email}")
    except Exception as e:
        print("❌ Greška pri slanju mejla:", e)