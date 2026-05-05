from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from psycopg2.extras import RealDictCursor
import psycopg2
import os
import json
from datetime import datetime
from decimal import Decimal
import threading
from dotenv import load_dotenv
from mailManager import send_html_email

load_dotenv()

porudzbine_bp = Blueprint("porudzbine", __name__)

def get_db_connection():
    """Kreira konekciju sa PostgreSQL bazom"""
    conn = psycopg2.connect(
        host=os.getenv('VPS', 'localhost'),
        database=os.getenv('DATABASE', 'shop'),
        user=os.getenv('DB_USER', 'postgres'),
        password=os.getenv('DB_PASSWORD', ''),
        port=os.getenv('PORT', 5432)
    )
    return conn


def convert_decimal_to_float(obj):
    """Konvertuje sve Decimal objekte u float za JSON serijalizaciju"""
    if isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, dict):
        return {k: convert_decimal_to_float(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_decimal_to_float(item) for item in obj]
    return obj


def create_order_email_html(porudzbina_id, ime, prezime, email, telefon, adresa, korpa, cena, is_admin=False):
    """
    Kreira HTML mejl sa detaljima narudžbine (bosanski, sa code-variant prikazom)
    is_admin=True: link ide na admin panel (butikirna.com/admin/porudzbine/id)
    is_admin=False: link ide na kupčinu stranicu (butikirna.com/narudzbina/id)
    """
    # Odredi link na osnovu tipa korisnika
    if is_admin:
        pregled_link = f"https://butikirna.com/admin/porudzbine/{porudzbina_id}"
    else:
        pregled_link = f"https://butikirna.com/narudzbina/{porudzbina_id}"
    
    stavke_html = ""
    for stavka in korpa:
        code = stavka.get('code', 'N/A')
        kolicina = stavka.get('kolicina', 0)
        cena_po_komadu = stavka.get('cena_po_komadu', 0)
        popust = stavka.get('popust', 0)
        ukupno = stavka.get('ukupno', 0)
        
        link = f"https://butikirna.com/proizvodi/{code.split('-')[0] if '-' in code else code}"
        
        popust_text = f"({popust}% popusta)" if popust > 0 else ""
        
        stavke_html += f"""
        <tr>
            <td style="border: 1px solid #ddd; padding: 10px; text-align: center;">
                <a href="{link}" style="color: #0066cc; text-decoration: none;">{code}</a>
            </td>
            <td style="border: 1px solid #ddd; padding: 10px; text-align: center;">{kolicina}</td>
            <td style="border: 1px solid #ddd; padding: 10px; text-align: right;">{cena_po_komadu:.2f} KM {popust_text}</td>
            <td style="border: 1px solid #ddd; padding: 10px; text-align: right;">{ukupno:.2f} KM</td>
        </tr>
        """
    
    html_content = f"""
    <html dir="ltr" lang="bs">
    <head>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: Arial, sans-serif; background-color: #f5f5f5; }}
            .container {{ max-width: 600px; margin: 20px auto; background-color: white; padding: 20px; border-radius: 8px; }}
            .header {{ background-color: #333; color: white; padding: 20px; text-align: center; border-radius: 8px; }}
            .content {{ padding: 20px; }}
            .order-info {{ background-color: #f9f9f9; padding: 15px; border-left: 4px solid #0066cc; margin: 15px 0; }}
            .customer-info {{ background-color: #f0f0f0; padding: 15px; margin: 15px 0; border-radius: 5px; }}
            table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
            th {{ background-color: #0066cc; color: white; padding: 10px; text-align: left; }}
            td {{ border: 1px solid #ddd; padding: 10px; }}
            .total {{ font-size: 18px; font-weight: bold; text-align: right; padding: 10px; background-color: #f0f0f0; }}
            .footer {{ text-align: center; padding: 20px; font-size: 12px; color: #666; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>✉️ Nova narudžba je primljena</h1>
            </div>
            
            <div class="content">
                <div class="order-info">
                    <p><strong>ID narudžbe:</strong> <span style="font-size: 18px; color: #0066cc;">#{porudzbina_id}</span></p>
                    <p><strong>Datum:</strong> {datetime.now().strftime('%d.%m.%Y. %H:%M')}</p>
                </div>
                
                <h3>📋 Informacije o kupcu</h3>
                <div class="customer-info">
                    <p><strong>Ime:</strong> {ime} {prezime}</p>
                    <p><strong>Email:</strong> {email}</p>
                    <p><strong>Telefon:</strong> {telefon}</p>
                    <p><strong>Adresa:</strong> {adresa}</p>
                </div>
                
                <h3>📦 Stavke u narudžbi</h3>
                <table>
                    <tr>
                        <th>Proizvod (Kod)</th>
                        <th>Količina</th>
                        <th>Cijena po komadu</th>
                        <th>Ukupno</th>
                    </tr>
                    {stavke_html}
                    <tr style="background-color: #f0f0f0; font-weight: bold;">
                        <td colspan="3" style="text-align: right; padding: 15px;">UKUPNA CIJENA:</td>
                        <td style="text-align: right; padding: 15px; font-size: 16px;">{cena:.2f} KM</td>
                    </tr>
                </table>
                
                <p>Status narudžbe: <strong style="color: #ff9900;">U pripremi</strong></p>
                <p><a href="{pregled_link}" style="background-color: #0066cc; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; display: inline-block;">Pregled narudžbe</a></p>
            </div>
            
            <div class="footer">
                <p>Ovo je automatska poruka. Molimo vas ne odgovarajte direktno na ovaj email.</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    text_content = f"""
    NOVA NARUDŽBA
    
    ID narudžbe: #{porudzbina_id}
    Datum: {datetime.now().strftime('%d.%m.%Y. %H:%M')}
    
    INFORMACIJE O KUPCU
    Ime: {ime} {prezime}
    Email: {email}
    Telefon: {telefon}
    Adresa: {adresa}
    
    STAVKE U NARUDŽBI
    """
    
    for stavka in korpa:
        code = stavka.get('code', 'N/A')
        kolicina = stavka.get('kolicina', 0)
        cena_po_komadu = stavka.get('cena_po_komadu', 0)
        popust = stavka.get('popust', 0)
        ukupno = stavka.get('ukupno', 0)
        popust_text = f"({popust}% popusta)" if popust > 0 else ""
        text_content += f"\n- {code}: {kolicina}x {cena_po_komadu:.2f} KM {popust_text} = {ukupno:.2f} KM"
    
    text_content += f"\n\nUKUPNA CIJENA: {cena:.2f} KM\n\nStatus: U pripremi\n\nPregled narudžbe: {pregled_link}"
    
    return html_content, text_content


def create_status_email_html(porudzbina_id, ime, prezime, status):
    """
    Kreira HTML mejl za obaveštavanje kupca o promijeni statusa narudžbine
    Status opcije: 'u_pripremi', 'u_tranzitu', 'dostavljeno', 'nedostavljeno'
    """
    pregled_link = f"https://butikirna.com/narudzbina/{porudzbina_id}"
    
    # Definiši poruke i boje po statusu
    status_info = {
        'u_pripremi': {
            'naslov': '⏳ Vaša narudžbina je u pripremi',
            'poruka': 'Vaša narudžbina se trenutno priprema za slanje. Čim bude spremna, izvešćemo vas!',
            'boja': '#ff9900',
            'emoji': '⏳'
        },
        'u_tranzitu': {
            'naslov': '🚚 Vaša narudžbina je u tranzitu!',
            'poruka': 'Vaša narudžbina je otpremljena i na putu prema vama!',
            'boja': '#0099ff',
            'emoji': '🚚'
        },
        'dostavljeno': {
            'naslov': '✅ Vaša narudžbina je dostavljena!',
            'poruka': 'Vaša narudžbina je uspješno dostavljena. Hvala što ste kupili kod nas!',
            'boja': '#00cc00',
            'emoji': '✅'
        },
        'nedostavljeno': {
            'naslov': '⚠️ Vaša narudžbina nije preuzeta',
            'poruka': 'Narudžbina nije preuzeta. Molimo vas da kontaktirate našu službu za klijente.',
            'boja': '#ff3333',
            'emoji': '⚠️'
        }
    }
    
    info = status_info.get(status, status_info['u_pripremi'])
    
    html_content = f"""
    <html dir="ltr" lang="bs">
    <head>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: Arial, sans-serif; background-color: #f5f5f5; }}
            .container {{ max-width: 600px; margin: 20px auto; background-color: white; padding: 20px; border-radius: 8px; }}
            .header {{ background-color: #333; color: white; padding: 20px; text-align: center; border-radius: 8px; }}
            .content {{ padding: 20px; }}
            .status-box {{ background-color: #f9f9f9; padding: 20px; border-left: 5px solid {info['boja']}; margin: 20px 0; border-radius: 5px; }}
            .status-message {{ font-size: 18px; font-weight: bold; color: {info['boja']}; margin-bottom: 10px; }}
            .order-info {{ background-color: #f0f0f0; padding: 15px; border-radius: 5px; margin: 20px 0; }}
            .footer {{ text-align: center; padding: 20px; font-size: 12px; color: #666; }}
            .button {{ background-color: #0066cc; color: white !important; padding: 12px 30px; text-decoration: none; border-radius: 5px; display: inline-block; margin-top: 15px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>{info['emoji']} {info['naslov']}</h1>
            </div>
            
            <div class="content">
                <div class="status-box">
                    <p class="status-message">{info['poruka']}</p>
                    
                    <div class="order-info">
                        <p><strong>Broj narudžbe:</strong> #{porudzbina_id}</p>
                        <p><strong>Datum:</strong> {datetime.now().strftime('%d.%m.%Y. %H:%M')}</p>
                    </div>
                    
                    <p>Ime: <strong>{ime} {prezime}</strong></p>
                </div>
                
                <p><a href="{pregled_link}" class="button">Pregled narudžbe</a></p>
                
                <p style="margin-top: 20px; font-size: 14px; color: #666;">
                    Ako imate pitanja, molimo vas kontaktirajte našu službu za klijente.
                </p>
            </div>
            
            <div class="footer">
                <p>Ovo je automatska poruka. Molimo vas ne odgovarajte direktno na ovaj email.</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    text_content = f"""
    {info['naslov']}
    
    {info['poruka']}
    
    Broj narudžbe: #{porudzbina_id}
    Datum: {datetime.now().strftime('%d.%m.%Y. %H:%M')}
    
    Ime: {ime} {prezime}
    
    Pregled narudžbe: {pregled_link}
    
    Ako imate pitanja, molimo vas kontaktirajte našu službu za klijente.
    """
    
    return html_content, text_content


def send_order_emails_async(porudzbina_id, ime, prezime, email, telefon, adresa, validna_korpa, ukupna_cena):
    """
    Šalje mejlove asinhrono - pokrenuto u posebnom thread-u
    """
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Pripremi email sadržaj
        html_content_admin, text_content_admin = create_order_email_html(
            porudzbina_id, ime, prezime, email, telefon, adresa, validna_korpa, ukupna_cena, is_admin=True
        )
        
        html_content_kupac, text_content_kupac = create_order_email_html(
            porudzbina_id, ime, prezime, email, telefon, adresa, validna_korpa, ukupna_cena, is_admin=False
        )
        
        # Pošalji mejl svim adminama (role = 1)
        try:
            cur.execute("SELECT email FROM users WHERE rola = 1")
            admini = cur.fetchall()
            
            if admini:
                print(f"📧 Slanje mejla adminama:")
                for admin in admini:
                    admin_email = admin['email']
                    print(f"   → {admin_email}")
                    send_html_email(
                        to_email=admin_email,
                        subject=f"🎉 Nova narudžbina - {ime} {prezime}",
                        html_content=html_content_admin,
                        text_content=text_content_admin
                    )
        except Exception as e:
            print(f"⚠️ Greška pri slanju mejla adminama: {str(e)}")
        
        # Pošalji mejl i kupcu na email iz payloada
        if email:
            try:
                print(f"📧 Slanje mejla kupcu:")
                print(f"   → {email}")
                send_html_email(
                    to_email=email,
                    subject=f"✅ Vaša narudžbina je primljena",
                    html_content=html_content_kupac,
                    text_content=text_content_kupac
                )
            except Exception as e:
                print(f"⚠️ Greška pri slanju mejla kupcu: {str(e)}")
        
        cur.close()
        conn.close()
        print(f"✅ Svi mejlovi za porudžbinu #{porudzbina_id} su poslani")
        
    except Exception as e:
        print(f"❌ Greška pri slanju mejlova: {str(e)}")


def send_status_email_async(porudzbina_id, ime, prezime, email, novi_status):
    """
    Šalje status mejl asinhrono - pokrenuto u posebnom thread-u
    """
    try:
        if email:
            html_content, text_content = create_status_email_html(
                porudzbina_id,
                ime,
                prezime,
                novi_status
            )
            
            send_html_email(
                to_email=email,
                subject=f"Status vašne narudžbe - {novi_status.replace('_', ' ').title()}",
                html_content=html_content,
                text_content=text_content
            )
            print(f"📧 Status mejl poslat kupcu: {email}")
        
    except Exception as e:
        print(f"⚠️ Greška pri slanju status mejla: {str(e)}")


@porudzbine_bp.route('/post', methods=['POST'])
def dodaj_porudzbinu():
    """
    Pravi novu porudzbinu
    
    Request:
    {
        "ime": "Petar",
        "prezime": "Petrović",
        "telefon": "06312345678",
        "email": "petar@example.com",
        "adresa": "Bulevar Kumodreza 123, Voždovac, Beograd",
        "userId": 1,  # Opciono
        "korpa": [
            {
                "code": "du45m9vsuu",
                "kolicina": 2
            },
            {
                "code": "as12df34gh",
                "kolicina": 1
            }
        ]
    }
    
    Response:
    {
        "id": 1,
        "poruka": "Porudzbina uspješno kreirana",
        "cena": 25998,
        "korpa": [...]
    }
    """
    try:
        data = request.get_json()
        
        # Validacija obaveznih polja
        if not data:
            return jsonify({"message": "Nedostaju podaci"}), 400
        
        ime = data.get('ime', '').strip()
        prezime = data.get('prezime', '').strip()
        telefon = data.get('telefon', '').strip()
        email = data.get('email', '').strip()
        adresa = data.get('adresa', '').strip()
        user_id = data.get('userId')
        korpa = data.get('korpa', [])
        
        # Validacija obaveznih polja
        if not ime or not prezime:
            return jsonify({"message": "Ime i prezime su obavezni"}), 400
        
        if not korpa or not isinstance(korpa, list) or len(korpa) == 0:
            return jsonify({"message": "Korpa mora biti neprazan niz"}), 400
        
        # Validacija svake stavke u korpi
        for stavka in korpa:
            if not isinstance(stavka, dict):
                return jsonify({"message": "Svaka stavka u korpi mora biti objekat"}), 400
            
            if 'code' not in stavka or not stavka['code']:
                return jsonify({"message": "Svaka stavka mora imati 'code'"}), 400
            
            if 'kolicina' not in stavka:
                return jsonify({"message": "Svaka stavka mora imati 'kolicina'"}), 400
            
            try:
                kolicina = int(stavka['kolicina'])
                if kolicina < 1:
                    return jsonify({"message": "Kolicina mora biti >= 1"}), 400
            except (ValueError, TypeError):
                return jsonify({"message": "Kolicina mora biti broj"}), 400
        
        # Konektuj se na bazu
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # PRVO: Validacija stanja za SVE stavke u korpi
        print("🔍 Provjeravamo stanje proizvoda...")
        for stavka in korpa:
            code = stavka['code'].strip()
            kolicina = int(stavka['kolicina'])
            
            # Pronađi proizvod
            if '-' in code:
                parts = code.split('-')
                if len(parts) == 2:
                    code_base = parts[0].strip()
                    try:
                        code_variant = int(parts[1].strip())
                        cur.execute(
                            "SELECT id, stanje, ime FROM proizvodi WHERE code_base = %s AND code_variant = %s",
                            (code_base, code_variant)
                        )
                    except ValueError:
                        cur.close()
                        conn.close()
                        return jsonify({"message": f"Neispravan format koda: {code}"}), 400
                else:
                    cur.close()
                    conn.close()
                    return jsonify({"message": f"Neispravan format koda: {code}"}), 400
            else:
                cur.execute(
                    "SELECT id, stanje, ime FROM proizvodi WHERE code_base = %s ORDER BY code_variant ASC LIMIT 1",
                    (code,)
                )
            
            proizvod = cur.fetchone()
            
            if not proizvod:
                cur.close()
                conn.close()
                return jsonify({"message": f"Proizvod sa kodom '{code}' ne postoji"}), 404
            
            # KRITIČNO: Proveri dostupnost
            if proizvod['stanje'] < kolicina:
                cur.close()
                conn.close()
                shortage = kolicina - proizvod['stanje']
                print(f"❌ NEDOSTAJE STANJA: {proizvod['ime']} ({code}) - dostupno: {proizvod['stanje']}, traženo: {kolicina}")
                return jsonify({
                    "error": "insufficient_stock",
                    "message": "Nema dovoljno komada!",
                    "product": {
                        "code": code,
                        "name": proizvod['ime'],
                        "available": proizvod['stanje'],
                        "requested": kolicina,
                        "shortage": shortage
                    }
                }), 409
            
            print(f"✅ OK: {proizvod['ime']} ({code}) - dostupno {proizvod['stanje']} kom")
        
        # Validiraj i izračunaj cenu svih stavki
        ukupna_cena = 0
        validna_korpa = []
        
        for stavka in korpa:
            code = stavka['code'].strip()
            kolicina = int(stavka['kolicina'])
            
            # Pronađi proizvod po code_base ili po code_base-code_variant
            if '-' in code:
                # Format: "du45m9vsuu-1"
                parts = code.split('-')
                if len(parts) == 2:
                    code_base = parts[0].strip()
                    try:
                        code_variant = int(parts[1].strip())
                        cur.execute(
                            "SELECT id, cena, popust FROM proizvodi WHERE code_base = %s AND code_variant = %s",
                            (code_base, code_variant)
                        )
                    except ValueError:
                        return jsonify({"message": f"Neispravan format koda: {code}"}), 400
                else:
                    return jsonify({"message": f"Neispravan format koda: {code}"}), 400
            else:
                # Samo code_base - uzmi prvi proizvod sa tim code_base
                cur.execute(
                    "SELECT id, cena, popust FROM proizvodi WHERE code_base = %s ORDER BY code_variant ASC LIMIT 1",
                    (code,)
                )
            
            proizvod = cur.fetchone()
            
            if not proizvod:
                return jsonify({"message": f"Proizvod sa kodom '{code}' ne postoji"}), 404
            
            # Izračunaj cenu sa popustom
            cena = float(proizvod['cena']) if isinstance(proizvod['cena'], Decimal) else proizvod['cena']
            popust = float(proizvod['popust']) if isinstance(proizvod['popust'], Decimal) else (proizvod['popust'] if proizvod['popust'] else 0)
            cena_sa_popustom = cena - (cena * popust / 100)
            cena_stavke = cena_sa_popustom * kolicina
            
            ukupna_cena += cena_stavke
            
            validna_korpa.append({
                "code": code,
                "proizvod_id": proizvod['id'],
                "kolicina": kolicina,
                "cena_po_komadu": round(cena, 2),
                "popust": round(popust, 2),
                "cena_sa_popustom": round(cena_sa_popustom, 2),
                "ukupno": round(cena_stavke, 2)
            })
        
        # Zaokruži cenu na 2 decimale
        ukupna_cena = round(float(ukupna_cena), 2)
        
        # Dodaj trošak dostave
        ukupna_cena += 10
        
        # Konvertuj sve Decimal vrednosti u validnoj korpi u float
        validna_korpa = convert_decimal_to_float(validna_korpa)
        
        # Ako je user_id prosleđen, validiraj da korisnik postoji
        if user_id:
            try:
                user_id = int(user_id)
                cur.execute("SELECT id FROM users WHERE id = %s", (user_id,))
                if not cur.fetchone():
                    return jsonify({"message": f"Korisnik sa ID-om {user_id} ne postoji"}), 404
            except (ValueError, TypeError):
                return jsonify({"message": "userId mora biti broj"}), 400
        else:
            user_id = None
        
        # Umesti porudzbinu u bazu
        cur.execute(
            """INSERT INTO porudzbine (ime, prezime, telefon, email, adresa, user_id, korpa, cena)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
               RETURNING id""",
            (ime, prezime, telefon, email, adresa, user_id, json.dumps(validna_korpa), ukupna_cena)
        )
        
        porudzbina_id = cur.fetchone()['id']
        
        conn.commit()
        
        # ODUZI STANJE iz proizvoda za svaku stavku u porudžbini
        print(f"📦 Ažuriramo stanje za porudžbinu #{porudzbina_id}...")
        for stavka in validna_korpa:
            try:
                cur.execute(
                    "UPDATE proizvodi SET stanje = stanje - %s WHERE id = %s",
                    (stavka['kolicina'], stavka['proizvod_id'])
                )
                print(f"✅ Stanje ažurirano: proizvod_id={stavka['proizvod_id']}, oduzeto={stavka['kolicina']} kom")
            except Exception as e:
                print(f"⚠️ Greška pri ažuriranju stanja: {str(e)}")
                # Nastavi sa sledećom stavkom - ne blokira proces
        
        conn.commit()
        
        # Pokreni asinhrono slanje mejlova u posebnom thread-u
        email_thread = threading.Thread(
            target=send_order_emails_async,
            args=(porudzbina_id, ime, prezime, email, telefon, adresa, validna_korpa, ukupna_cena),
            daemon=True
        )
        email_thread.start()
        
        cur.close()
        conn.close()
        
        # Konvertuj Decimal u float za JSON
        cena_json = convert_decimal_to_float(ukupna_cena)
        korpa_json = convert_decimal_to_float(validna_korpa)
        
        return jsonify({
            "id": porudzbina_id,
            "poruka": "Porudzbina uspješno kreirana",
            "cena": cena_json,
            "broj_stavki": len(validna_korpa),
            "korpa": korpa_json
        }), 201
        
    except Exception as e:
        return jsonify({"message": f"Greška na serveru: {str(e)}"}), 500


@porudzbine_bp.route('/get', methods=['GET'])
@jwt_required()
def get_porudzbine():
    """
    Preuzima porudžbine sa naprednim filtriranjem, sortiranjem i paginacijom
    
    ROLE-BASED PRISTUP:
    - role=0 (korisnik): samo njegove porudžbine
    - role=1,2 (admin/zaposleni): SVE porudžbine
    
    QUERY PARAMETRI:
    - id: specifična porudžbina po ID
    - limit: stavki po stranici (default: 20, max: 100)
    - offset: od koje stavke (default: 0)
    - sort_by: "id", "ime", "email", "cena", "status", "adresa", "created_at" (default: "created_at")
    - sort_order: "asc" ili "desc" (default: "desc")
    - search: pretraga u ime, prezime, email (ILIKE)
    - status: filter po statusu (u_pripremi, u_tranzitu, dostavljeno, nedostavljeno)
    - date_from: filter od datuma (YYYY-MM-DD)
    - date_to: filter do datuma (YYYY-MM-DD)
    
    PRIMERI:
    - /api/porudzbine/get
    - /api/porudzbine/get?limit=10&offset=0
    - /api/porudzbine/get?search=Petar
    - /api/porudzbine/get?sort_by=cena&sort_order=asc
    - /api/porudzbine/get?sort_by=adresa
    - /api/porudzbine/get?status=u_tranzitu
    - /api/porudzbine/get?date_from=2026-04-01&date_to=2026-04-08
    - /api/porudzbine/get?id=5
    - /api/porudzbine/get?status=dostavljeno&sort_by=created_at&sort_order=desc
    """
    try:
        current_user_id = get_jwt_identity()
        
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Pročitaj rolu
        cur.execute("SELECT rola FROM users WHERE id = %s", (int(current_user_id),))
        user = cur.fetchone()
        if not user:
            return jsonify({"message": "Korisnik ne postoji"}), 404
        
        user_role = user['rola']
        
        # Parametri
        porudzbina_id = request.args.get('id', None, type=int)
        limit = request.args.get('limit', 20, type=int)
        offset = request.args.get('offset', 0, type=int)
        sort_by = request.args.get('sort_by', 'created_at').lower()
        sort_order = request.args.get('sort_order', 'desc').lower()
        search = request.args.get('search', '').strip()
        date_from = request.args.get('date_from', '').strip()
        date_to = request.args.get('date_to', '').strip()
        filter_status = request.args.get('status', '').strip().lower()
        
        # Validacija
        if limit < 1:
            limit = 20
        if limit > 100:
            limit = 100
        if offset < 0:
            offset = 0
        
        allowed_sort_fields = ['id', 'ime', 'email', 'cena', 'status', 'created_at', 'adresa']
        if sort_by not in allowed_sort_fields:
            sort_by = 'created_at'
        if sort_order not in ['asc', 'desc']:
            sort_order = 'desc'
        
        # Specifična porudžbina po ID
        if porudzbina_id:
            where_clause = "WHERE p.id = %s"
            params = [porudzbina_id]
            
            if user_role == 0:  # Obični korisnik
                where_clause += " AND p.user_id = %s"
                params.append(int(current_user_id))
            
            cur.execute(
                f"""SELECT p.id, p.ime, p.prezime, p.telefon, p.email, p.adresa, p.user_id, 
                           p.korpa, p.cena, p.status, p.created_at, p.updated_at FROM porudzbine p {where_clause}""",
                tuple(params)
            )
            porudzbina = cur.fetchone()
            if not porudzbina:
                return jsonify({"message": "Porudžbina ne postoji ili joj nemate pristup"}), 403
            
            porudzbine = [porudzbina]
            ukupno = 1
        else:
            # Sve porudžbine sa filtriranjem
            where_conditions = []
            params = []
            
            # Role-based filter
            if user_role == 0:
                where_conditions.append("p.user_id = %s")
                params.append(int(current_user_id))
            
            # Search
            if search:
                search_pattern = f"%{search}%"
                where_conditions.append("(p.ime ILIKE %s OR p.prezime ILIKE %s OR p.email ILIKE %s OR p.adresa ILIKE %s)")
                params.extend([search_pattern, search_pattern, search_pattern, search_pattern])
            
            # Date filters
            if date_from:
                try:
                    datetime.strptime(date_from, '%Y-%m-%d')
                    where_conditions.append("p.created_at::date >= %s")
                    params.append(date_from)
                except ValueError:
                    return jsonify({"message": "date_from mora biti YYYY-MM-DD"}), 400
            
            if date_to:
                try:
                    datetime.strptime(date_to, '%Y-%m-%d')
                    where_conditions.append("p.created_at::date <= %s")
                    params.append(date_to)
                except ValueError:
                    return jsonify({"message": "date_to mora biti YYYY-MM-DD"}), 400
            
            # Status filter
            allowed_statuses = ['u_pripremi', 'u_tranzitu', 'dostavljeno', 'nedostavljeno']
            if filter_status:
                if filter_status not in allowed_statuses:
                    return jsonify({
                        "message": f"Neispravan status. Dozvoljeni statusi: {', '.join(allowed_statuses)}"
                    }), 400
                where_conditions.append("p.status = %s")
                params.append(filter_status)
            
            where_clause = "WHERE " + " AND ".join(where_conditions) if where_conditions else ""
            
            # Prebroj
            count_query = f"SELECT COUNT(*) as ukupno FROM porudzbine p {where_clause}"
            cur.execute(count_query, tuple(params))
            ukupno = cur.fetchone()['ukupno']
            
            # Sort
            sort_field = f"p.{sort_by}" if sort_by in allowed_sort_fields else "p.created_at"
            order_by = f"{sort_field} {sort_order.upper()}"
            
            # Query
            query = f"""SELECT p.id, p.ime, p.prezime, p.telefon, p.email, p.adresa, p.user_id, 
                               p.korpa, p.cena, p.status, p.created_at, p.updated_at FROM porudzbine p {where_clause}
                        ORDER BY {order_by} LIMIT %s OFFSET %s"""
            
            params.extend([limit, offset])
            cur.execute(query, tuple(params))
            porudzbine = cur.fetchall()
        
        # Ekspanzija korpe
        result_porudzbine = []
        for p in porudzbine:
            korpa_data = p['korpa'] if isinstance(p['korpa'], list) else json.loads(p['korpa'])
            expanded_korpa = []
            for stavka in korpa_data:
                cur.execute(
                    "SELECT id, code_base, code_variant, ime, opis, stanje, boja, velicina, slike, fav, kategorija, cena, popust, created_at, updated_at FROM proizvodi WHERE id = %s",
                    (stavka['proizvod_id'],)
                )
                proizvod = cur.fetchone()
                if proizvod:
                    stavka['proizvod'] = dict(proizvod)
                expanded_korpa.append(stavka)
            
            p['korpa'] = expanded_korpa
            result_porudzbine.append(dict(p))
        
        cur.close()
        conn.close()
        
        # Paginacija
        ukupno_strana = (ukupno + limit - 1) // limit if limit > 0 else 1
        trenutna_strana = (offset // limit + 1) if limit > 0 else 1
        
        # Konvertuj Decimal u float za JSON
        result_porudzbine_json = convert_decimal_to_float(result_porudzbine)
        
        return jsonify({
            "porudzbine": result_porudzbine_json,
            "pagination": {
                "limit": limit,
                "offset": offset,
                "ukupno": ukupno,
                "strana": trenutna_strana,
                "ukupno_strana": ukupno_strana
            }
        }), 200
        
    except Exception as e:
        return jsonify({"message": f"Greška na serveru: {str(e)}"}), 500


@porudzbine_bp.route('/status', methods=['PATCH'])
@jwt_required()
def azuriraj_status_porudzbine():
    """
    Ažurira status porudžbine
    
    Samo rola 1 (admin) i rola 2 (zaposleni) mogu koristiti ovaj endpoint
    
    Request:
    {
        "id": 5,
        "status": "u_tranzitu"
    }
    
    Dozvoljeni statusi (SRPSKI):
    - u_pripremi: U pripremi
    - u_tranzitu: U tranzitu
    - dostavljeno: Dostavljeno
    - nedostavljeno: Nije preuzeto
    
    Response:
    {
        "poruka": "Status ažuriran uspješno",
        "id": 5,
        "status": "u_tranzitu",
        "updated_at": "2026-04-09T20:30:45"
    }
    """
    try:
        current_user_id = get_jwt_identity()
        
        # Pročitaj rolu
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("SELECT rola FROM users WHERE id = %s", (int(current_user_id),))
        user = cur.fetchone()
        
        if not user:
            return jsonify({"message": "Korisnik ne postoji"}), 404
        
        user_role = user['rola']
        
        # Samo admin (1) i zaposleni (2) mogu mijenjati status
        if user_role not in [1, 2]:
            return jsonify({"message": "Nemate dozvolu za ovu akciju"}), 403
        
        data = request.get_json()
        
        if not data:
            return jsonify({"message": "Nedostaju podaci"}), 400
        
        porudzbina_id = data.get('id')
        novi_status = data.get('status', '').strip().lower()
        
        if not porudzbina_id:
            return jsonify({"message": "Nedostaje ID porudžbine"}), 400
        
        if not novi_status:
            return jsonify({"message": "Nedostaje status"}), 400
        
        # Dozvoljeni statusi - SAMO srpske vrednosti
        allowed_statuses = ['u_pripremi', 'u_tranzitu', 'dostavljeno', 'nedostavljeno']
        
        if novi_status not in allowed_statuses:
            return jsonify({
                "message": f"Neispravan status. Dozvoljeni statusi: {', '.join(allowed_statuses)}"
            }), 400
        
        # Proveri da li porudžbina postoji
        cur.execute("SELECT id, status FROM porudzbine WHERE id = %s", (porudzbina_id,))
        porudzbina = cur.fetchone()
        
        if not porudzbina:
            return jsonify({"message": f"Porudžbina sa ID-om {porudzbina_id} ne postoji"}), 404
        
        stari_status = porudzbina['status']
        
        # Ako je isti status, nema potrebe za update
        if stari_status == novi_status:
            return jsonify({
                "poruka": "Status je već isti",
                "id": porudzbina_id,
                "status": novi_status
            }), 200
        
        # Ažuriraj status
        update_query = """UPDATE porudzbine 
                         SET status = %s, updated_at = NOW()
                         WHERE id = %s
                         RETURNING id, status, updated_at"""
        
        cur.execute(update_query, (novi_status, porudzbina_id))
        result = cur.fetchone()
        
        # Pročitaj podatke kupca za email
        cur.execute("SELECT ime, prezime, email FROM porudzbine WHERE id = %s", (porudzbina_id,))
        kupac_podaci = cur.fetchone()
        
        conn.commit()
        
        # Pokreni asinhrono slanje status mejla u posebnom thread-u (ako ima email)
        if kupac_podaci and kupac_podaci['email']:
            email_thread = threading.Thread(
                target=send_status_email_async,
                args=(porudzbina_id, kupac_podaci['ime'], kupac_podaci['prezime'], kupac_podaci['email'], novi_status),
                daemon=True
            )
            email_thread.start()
        
        cur.close()
        conn.close()
        
        return jsonify({
            "poruka": "Status ažuriran uspješno",
            "id": result['id'],
            "status": result['status'],
            "updated_at": result['updated_at']
        }), 200
        
    except Exception as e:
        return jsonify({"message": f"Greška na serveru: {str(e)}"}), 500

