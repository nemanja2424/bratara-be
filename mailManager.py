import os
import smtplib
from email.message import EmailMessage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
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


def send_html_email(to_email: str, subject: str, html_content: str, text_content: str = None):
    """
    Šalje HTML mejl sa tekstualnom verzijom kao fallback
    
    Args:
        to_email: Email adresa primatelja
        subject: Naslov mejla
        html_content: HTML verzija mejla
        text_content: Tekstualna verzija mejla (ako nije prosleđena, biće automatski generisana)
    """
    SMTP_SERVER = os.getenv("SMTP_SERVER")
    SMTP_PORT = int(os.getenv("SMTP_PORT", 465))
    EMAIL = os.getenv("EMAIL")
    EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
    
    if not all([SMTP_SERVER, SMTP_PORT, EMAIL, EMAIL_PASSWORD]):
        print("❌ Nedostaju SMTP varijable u .env")
        return
    
    # Kreiraj multipart poruku
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = EMAIL
    msg['To'] = to_email
    
    # Ako tekstualna verzija nije prosleđena, koristi HTML kao fallback
    if not text_content:
        text_content = "Отвори овај mejл у HTML-kompatibilnom klijentu"
    
    # Dodaj tekstualnu verziju
    text_part = MIMEText(text_content, 'plain', 'utf-8')
    msg.attach(text_part)
    
    # Dodaj HTML verziju
    html_part = MIMEText(html_content, 'html', 'utf-8')
    msg.attach(html_part)
    
    try:
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as smtp:
            smtp.login(EMAIL, EMAIL_PASSWORD)
            smtp.send_message(msg)
        print(f"✅ HTML mejl poslat na {to_email}")
        return True
    except Exception as e:
        print("❌ Greška pri slanju HTML mejla:", e)
        return False