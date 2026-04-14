import json
from flask import Blueprint, jsonify, request
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from werkzeug.security import generate_password_hash, check_password_hash
import psycopg2
from psycopg2.extras import RealDictCursor, Json
import os
from dotenv import load_dotenv

load_dotenv()

auth_bp = Blueprint("auth", __name__)

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


@auth_bp.route('/login', methods=['POST'])
def login():
    """
    Login ruta - prima email i password, vraća JWT token
    Primer request-a:
    {
        "email": "user@example.com",
        "password": "password123"
    }
    """
    try:
        data = request.get_json()
        
        if not data or not data.get('email') or not data.get('password'):
            return jsonify({"message": "Nedostaju email ili password"}), 400
        
        email = data.get('email')
        password = data.get('password')
        
        # Konektuj se na bazu i pronađi korisnika
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("SELECT id, email, password, ime, prezime, rola FROM users WHERE email = %s", (email,))
        user = cur.fetchone()
        cur.close()
        conn.close()
        
        # Provera da li korisnik sa taj email-om postoji
        if not user:
            return jsonify({"message": "Korisnik sa ovim email-om nije pronađen"}), 401
        
        # Provera da li je lozinka ispravna
        if not check_password_hash(user['password'], password):
            return jsonify({"message": "Lozinka je pogrešna"}), 401
        
        # Kreiraj JWT token (identity mora biti string)
        access_token = create_access_token(identity=str(user['id']))
        
        return jsonify({
            "message": "Uspešno ste se ulogovali",
            "access_token": access_token,
            "user": {
                "id": user['id'],
                "email": user['email'],
                "ime": user['ime'],
                "prezime": user['prezime'],
                "rola": user['rola']
            }
        }), 200
        
    except Exception as e:
        return jsonify({"message": f"Greška na serveru: {str(e)}"}), 500


@auth_bp.route('/protected', methods=['GET'])
@jwt_required()
def protected():
    """
    Zaštićena ruta - proverava JWT token i vraća rolu korisnika
    Header: Authorization: Bearer <token>
    """
    try:
        current_user_id = get_jwt_identity()
        
        # Uzmi korisnika iz baze
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("SELECT id, ime, prezime, email, rola FROM users WHERE id = %s", (int(current_user_id),))
        user = cur.fetchone()
        cur.close()
        conn.close()
        
        if not user:
            return jsonify({"message": "Korisnik nije pronađen"}), 404
        
        # Vrati samo rolu
        return jsonify({
            "rola": user['rola']
        }), 200
        
    except Exception as e:
        return jsonify({"message": f"Greška na serveru: {str(e)}"}), 500


@auth_bp.route('/signup', methods=['POST'])
def signup():
    """
    Registracija ruta - kreira novog korisnika sa svim detaljima
    
    Request:
    {
        "ime": "Marko",
        "prezime": "Marković",
        "email": "marko@example.com",
        "telefon": "06XX XXX XXXX",
        "adresa": "71000 Sarajevo, Zmaja od Bosne 10",
        "lozinka": "lozinka123"
    }
    
    Response (201):
    {
        "message": "Uspešno ste se registrovali",
        "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
        "user": {
            "id": 1,
            "ime": "Marko",
            "prezime": "Marković",
            "email": "marko@example.com",
            "telefon": "06XX XXX XXXX",
            "adresa": "71000 Sarajevo, Zmaja od Bosne 10",
            "rola": 0
        }
    }
    """
    try:
        data = request.get_json()
        
        # Validacija obaveznih polja
        if not data:
            return jsonify({"message": "Nedostaju podaci"}), 400
        
        ime = data.get('ime', '').strip()
        prezime = data.get('prezime', '').strip()
        email = data.get('email', '').strip()
        telefon = data.get('telefon', '').strip()
        adresa = data.get('adresa', '').strip()
        lozinka = data.get('lozinka', '').strip()
        
        # Provera obaveznih polja
        if not ime or not email or not lozinka:
            return jsonify({"message": "Nedostaju obavezna polja (ime, email, lozinka)"}), 400
        
        if len(lozinka) < 3:
            return jsonify({"message": "Lozinka mora imati najmanje 3 karaktera"}), 400
        
        # Heširaj lozinku
        hashed_password = generate_password_hash(lozinka)
        
        try:
            conn = get_db_connection()
            cur = conn.cursor(cursor_factory=RealDictCursor)
            
            # Kreiraj novog korisnika
            cur.execute(
                """INSERT INTO users (ime, prezime, email, telefon, adresa, password, rola) 
                   VALUES (%s, %s, %s, %s, %s, %s, %s)
                   RETURNING id, ime, prezime, email, telefon, adresa, rola""",
                (ime, prezime, email, telefon, adresa, hashed_password, 0)
            )
            
            novi_korisnik = cur.fetchone()
            conn.commit()
            cur.close()
            conn.close()
            
            # Kreiraj JWT token
            access_token = create_access_token(identity=str(novi_korisnik['id']))
            
            return jsonify({
                "message": "Uspešno ste se registrovali",
                "access_token": access_token,
                "user": dict(novi_korisnik)
            }), 201
            
        except psycopg2.IntegrityError:
            conn.rollback()
            cur.close()
            conn.close()
            return jsonify({"message": "Email je već registrovan"}), 409
            
    except Exception as e:
        return jsonify({"message": f"Greška na serveru: {str(e)}"}), 500



@auth_bp.route('/me', methods=['GET', 'PATCH'])
@jwt_required()
def me():
    """
    GET - Vraća podatke o trenutno ulogovanom korisniku
    PATCH - Menja podatke korisnika (ime, prezime, email, telefon, adresa)
    
    Header: Authorization: Bearer <token>
    
    GET Response:
    {
        "user": {
            "id": 1,
            "ime": "Nemanja",
            "prezime": "Jakovljevic",
            "email": "example@gmail.com",
            "telefon": "06XXXXXXXX",
            "adresa": "Beograd, Kumodreza 1",
            "korpa": [{"code": "du45m9vsuu", "kolicina": 2, ...}],
            "omiljeno": ["code_base_1", "code_base_2"]
        }
    }
    
    PATCH Request (sva polja opciona):
    {
        "ime": "Novo Ime",
        "prezime": "Novo Prezime",
        "email": "novi@email.com",
        "telefon": "0611111111",
        "adresa": "Nova Adresa 123",
        "korpa": [{"code": "du45m9vsuu", "kolicina": 2}],
        "omiljeno": ["code_base_1"]
    }
    
    PATCH Response:
    {
        "message": "Podaci su uspešno ažurirani",
        "user": {
            "id": 1,
            "ime": "Novo Ime",
            "prezime": "Novo Prezime",
            "email": "novi@email.com",
            "telefon": "0611111111",
            "adresa": "Nova Adresa 123",
            "korpa": [{...}],
            "omiljeno": ["code_base_1"],
            "rola": 0
        }
    }
    """
    try:
        current_user_id = get_jwt_identity()
        
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # GET metoda
        if request.method == 'GET':
            cur.execute(
                "SELECT id, ime, prezime, email, telefon, adresa, korpa, omiljeno, rola FROM users WHERE id = %s",
                (int(current_user_id),)
            )
            user = cur.fetchone()
            cur.close()
            conn.close()
            
            if not user:
                return jsonify({"message": "Korisnik nije pronađen"}), 404
            
            return jsonify({
                "user": dict(user)
            }), 200
        
        # PATCH metoda
        elif request.method == 'PATCH':
            data = request.get_json()
            
            if not data:
                cur.close()
                conn.close()
                return jsonify({"message": "Nedostaju podaci za ažuriranje"}), 400
            
            # Pronađi trenutnog korisnika
            cur.execute(
                "SELECT id, ime, prezime, email, telefon, adresa, korpa, omiljeno FROM users WHERE id = %s",
                (int(current_user_id),)
            )
            user = cur.fetchone()
            
            if not user:
                cur.close()
                conn.close()
                return jsonify({"message": "Korisnik nije pronađen"}), 404
            
            # Pripremi polja za ažuriranje
            fields_to_update = {}
            
            if data.get('ime'):
                fields_to_update['ime'] = data.get('ime')
            
            if data.get('prezime') is not None:
                fields_to_update['prezime'] = data.get('prezime')
            
            if data.get('telefon') is not None:
                fields_to_update['telefon'] = data.get('telefon').strip()
            
            if data.get('adresa') is not None:
                fields_to_update['adresa'] = data.get('adresa').strip()
            
            if data.get('korpa') is not None:
                korpa = data.get('korpa')
                if not isinstance(korpa, list):
                    cur.close()
                    conn.close()
                    return jsonify({"message": "'korpa' mora biti lista"}), 400
                fields_to_update['korpa'] = Json(korpa)
            
            if data.get('omiljeno') is not None:
                omiljeno = data.get('omiljeno')
                if not isinstance(omiljeno, list):
                    cur.close()
                    conn.close()
                    return jsonify({"message": "'omiljeno' mora biti lista"}), 400
                fields_to_update['omiljeno'] = Json(omiljeno)
            
            if data.get('email'):
                # Provera da li email već postoji (za drugog korisnika)
                cur.execute(
                    "SELECT id FROM users WHERE email = %s AND id != %s",
                    (data.get('email'), int(current_user_id))
                )
                existing_email = cur.fetchone()
                
                if existing_email:
                    cur.close()
                    conn.close()
                    return jsonify({"message": "Email je već registrovan"}), 409
                
                fields_to_update['email'] = data.get('email')
            
            # Ako nema šta da se ažurira
            if not fields_to_update:
                cur.close()
                conn.close()
                return jsonify({"message": "Nema polja za ažuriranje"}), 400
            
            # Gradimo UPDATE query dinamički
            set_clause = ', '.join([f"{k} = %s" for k in fields_to_update.keys()])
            
            query = f"UPDATE users SET {set_clause} WHERE id = %s RETURNING id, ime, prezime, email, telefon, adresa, korpa, omiljeno, rola"
            
            values = list(fields_to_update.values())
            values.append(int(current_user_id))
            
            cur.execute(query, values)
            azuriran_korisnik = cur.fetchone()
            conn.commit()
            cur.close()
            conn.close()
            
            return jsonify({
                "message": "Podaci su uspešno ažurirani",
                "user": dict(azuriran_korisnik)
            }), 200
        
    except Exception as e:
        return jsonify({"message": f"Greška na serveru: {str(e)}"}), 500


@auth_bp.route('/lozinka', methods=['PATCH'])
@jwt_required()
def promeni_lozinku():
    """
    Menja lozinku korisnika
    Header: Authorization: Bearer <token>
    
    Request:
    {
        "old_pwd": "nemanja123",
        "new_pwd": "nemanja1234"
    }
    
    Response:
    {
        "message": "Lozinka je uspešno promenjena"
    }
    """
    try:
        current_user_id = get_jwt_identity()
        data = request.get_json()
        
        if not data or not data.get('old_pwd') or not data.get('new_pwd'):
            return jsonify({"message": "Nedostaju old_pwd ili new_pwd"}), 400
        
        old_pwd = data.get('old_pwd')
        new_pwd = data.get('new_pwd')
        
        # Validacija nove lozinke
        if len(new_pwd) < 3:
            return jsonify({"message": "Nova lozinka mora imati najmanje 3 karaktera"}), 400
        
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Pronađi korisnika
        cur.execute("SELECT id, password FROM users WHERE id = %s", (int(current_user_id),))
        user = cur.fetchone()
        
        if not user:
            cur.close()
            conn.close()
            return jsonify({"message": "Korisnik nije pronađen"}), 404
        
        # Provera da li je stara lozinka ispravna
        if not check_password_hash(user['password'], old_pwd):
            cur.close()
            conn.close()
            return jsonify({"message": "Stara lozinka je pogrešna"}), 401
        
        # Heširaj novu lozinku
        hashed_new_pwd = generate_password_hash(new_pwd)
        
        # Ažuriraj lozinku
        cur.execute(
            "UPDATE users SET password = %s WHERE id = %s",
            (hashed_new_pwd, int(current_user_id))
        )
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({
            "message": "Lozinka je uspešno promenjena"
        }), 200
        
    except Exception as e:
        return jsonify({"message": f"Greška na serveru: {str(e)}"}), 500
