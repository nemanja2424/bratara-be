from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from psycopg2.extras import RealDictCursor
import psycopg2
import os
import json
from datetime import datetime
from dotenv import load_dotenv

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
        "poruka": "Porudzbina uspešno kreirana",
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
            cena = proizvod['cena']
            popust = proizvod['popust'] if proizvod['popust'] else 0
            cena_sa_popustom = cena - (cena * popust / 100)
            cena_stavke = cena_sa_popustom * kolicina
            
            ukupna_cena += cena_stavke
            
            validna_korpa.append({
                "code": code,
                "proizvod_id": proizvod['id'],
                "kolicina": kolicina,
                "cena_po_komadu": cena,
                "popust": popust,
                "cena_sa_popustom": cena_sa_popustom,
                "ukupno": cena_stavke
            })
        
        # Konvertuј cenu u integer (dinare)
        ukupna_cena = int(ukupna_cena)
        
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
        cur.close()
        conn.close()
        
        return jsonify({
            "id": porudzbina_id,
            "poruka": "Porudzbina uspešno kreirana",
            "cena": ukupna_cena,
            "broj_stavki": len(validna_korpa),
            "korpa": validna_korpa
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
        
        return jsonify({
            "porudzbine": result_porudzbine,
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
        "poruka": "Status ažuriran uspešno",
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
        
        # Samo admin (1) i zaposleni (2) mogu menjati status
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
        
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({
            "poruka": "Status ažuriran uspešno",
            "id": result['id'],
            "status": result['status'],
            "updated_at": result['updated_at']
        }), 200
        
    except Exception as e:
        return jsonify({"message": f"Greška na serveru: {str(e)}"}), 500

