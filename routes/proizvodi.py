from flask import Blueprint, jsonify, request, send_from_directory
from flask_jwt_extended import jwt_required, get_jwt_identity
from psycopg2.extras import RealDictCursor
import psycopg2
import os
import json
import uuid
import base64
import string
import random
from dotenv import load_dotenv

load_dotenv()

proizvodi_bp = Blueprint("proizvodi", __name__)

def generiši_code_base(dužina=10):
    """Generiše random code_base sa malim slovima i brojevima"""
    karakteri = string.ascii_lowercase + string.digits
    return ''.join(random.choice(karakteri) for _ in range(dužina))

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


@proizvodi_bp.route('/post', methods=['POST'])
@jwt_required()
def dodaj_proizvod():
    """
    Dodaje jedan ili više proizvoda
    Request:
    [
        {
            "ime": "Štikla",
            "opis": "Elegantna štikla",
            "kategorija": "Štikle",
            "boja": "Roza",
            "velicina": "42",
            "stanje": 50,
            "cena": 5000,
            "popust": 10,
            "slike": [{"name": "slika.png", "base64": "data:image/png;base64,..."}],
            "fav": true
        }
    ]
    """
    try:
        current_user_id = get_jwt_identity()
        
        # Provera rola
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("SELECT rola FROM users WHERE id = %s", (int(current_user_id),))
        user = cur.fetchone()
        
        if not user or user['rola'] != 1:
            return jsonify({"message": "Nemate dozvolu za ovu akciju"}), 403
        
        data = request.get_json()
        
        if not data or not isinstance(data, list) or len(data) == 0:
            return jsonify({"message": "Payload mora biti neprazan JSON array"}), 400
        
        dodani_proizvodi = []
        
        # Generiši code_base samo jednom - koristi se za sve proizvode
        code_base = generiši_code_base(10)
        
        for proizvod_data in data:
            # Validacija obaveznih polja
            if not proizvod_data.get('ime') or not proizvod_data.get('kategorija'):
                return jsonify({"message": "Nedostaje ime ili kategorija za proizvod"}), 400
            
            # Pronađi kategoriju po nazivu
            cur.execute("SELECT id FROM kategorije WHERE kategorija = %s", (proizvod_data.get('kategorija'),))
            kategorija = cur.fetchone()
            
            if not kategorija:
                return jsonify({"message": f"Kategorija '{proizvod_data.get('kategorija')}' ne postoji"}), 404
            
            kategorija_id = kategorija['id']
            
            # code_variant je redni broj varijante (1, 2, 3...)
            code_variant = len(dodani_proizvodi) + 1
            
            ime = proizvod_data.get('ime')
            opis = proizvod_data.get('opis', '')
            boja = proizvod_data.get('boja', '')
            velicina = proizvod_data.get('velicina', '')
            stanje = proizvod_data.get('stanje', 0)
            cena = proizvod_data.get('cena', 0)
            popust = proizvod_data.get('popust', 0)
            fav = proizvod_data.get('fav', False)
            
            # Obrada slika - čuvanje na disk
            sacuvane_slike = []
            slike_data = proizvod_data.get('slike', [])
            
            for slika in slike_data:
                if slika.get('base64'):
                    try:
                        # Dekodira base64 i čuva fajl
                        base64_string = slika.get('base64')
                        
                        # Uklanja "data:image/...;base64," prefiks ako postoji
                        if ',' in base64_string:
                            base64_string = base64_string.split(',')[1]
                        
                        # Dekodira base64
                        image_data = base64.b64decode(base64_string)
                        
                        # Generiši jedinstveno ime fajla
                        originalno_ime = slika.get('name', 'image.png')
                        ime_bez_ekstenzije, ekstenzija = os.path.splitext(originalno_ime)
                        if ekstenzija == '':
                            ekstenzija = '.png'
                        
                        novo_ime_fajla = f"{uuid.uuid4()}{ekstenzija}"
                        
                        # Putanja do foldera sa slikama
                        slike_folder = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'slike')
                        os.makedirs(slike_folder, exist_ok=True)
                        
                        # Čuva fajl
                        fajl_putanja = os.path.join(slike_folder, novo_ime_fajla)
                        with open(fajl_putanja, 'wb') as f:
                            f.write(image_data)
                        
                        # Dodaj samo naziv u niz
                        sacuvane_slike.append(novo_ime_fajla)
                        
                    except Exception as e:
                        return jsonify({"message": f"Greška pri čuvanju slike: {str(e)}"}), 500
            
            # U bazu čuva samo imena slika
            slike_json = json.dumps(sacuvane_slike)
            
            # Umetni proizvod u bazu
            cur.execute(
                """INSERT INTO proizvodi 
                   (code_base, code_variant, ime, opis, stanje, boja, velicina, slike, fav, kategorija, cena, popust)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   RETURNING id, code_base, code_variant, ime, opis, stanje, boja, velicina, slike, fav, kategorija, cena, popust, created_at, updated_at""",
                (code_base, code_variant, ime, opis, stanje, boja, velicina, slike_json, fav, kategorija_id, cena, popust)
            )
            
            novi_proizvod = cur.fetchone()
            dodani_proizvodi.append(dict(novi_proizvod))
        
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({
            "message": f"{len(dodani_proizvodi)} proizvod(a) je uspešno dodan(o)",
            "proizvodi": dodani_proizvodi
        }), 201
        
    except Exception as e:
        return jsonify({"message": f"Greška na serveru: {str(e)}"}), 500


@proizvodi_bp.route('/slike/<filename>', methods=['GET'])
def preuzmi_sliku(filename):
    """
    Preuzima sliku po imenu
    """
    try:
        slike_folder = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'slike')
        return send_from_directory(slike_folder, filename)
    except Exception as e:
        return jsonify({"message": "Slika nije pronađena"}), 404


@proizvodi_bp.route('/get', methods=['GET'])
@jwt_required(optional=True)
def get_proizvodi():
    """
    Preuzima sve proizvode sa paginacijom
    Query parameters:
    - limit: broj proizvoda po stranici (default: 50, max: 100)
    - offset: od kog reda početi (default: 0)
    - code_base: filter po code_base (vraća sve varijante sa tim code_base)
    
    Primeri:
    - /get?limit=50&offset=0     # Првих 50
    - /get?limit=50&offset=50    # Sledećih 50 (stranica 2)
    - /get?limit=10&offset=0     # Првих 10
    - /get?code_base=du45m9vsuu  # Samo proizvodi sa tim code_base
    
    Napomena: Admini (rola=1) i staff (rola=2) vide sve proizvode uključujući one bez stanja.
              Ostali korisnici vide samo proizvode koji su na stanju.
    
    Response:
    {
        "proizvodi": [...],
        "pagination": {
            "limit": 50,
            "offset": 0,
            "ukupno_proizvoda": 150
        }
    }
    """
    try:
        # Proverava da li je korisnik admin ili staff
        current_user_id = get_jwt_identity()
        rola = 0  # Default rola za nekorisnike ili regular customers
        
        if current_user_id:
            conn_user = get_db_connection()
            cur_user = conn_user.cursor(cursor_factory=RealDictCursor)
            cur_user.execute("SELECT rola FROM users WHERE id = %s", (int(current_user_id),))
            user = cur_user.fetchone()
            if user:
                rola = user['rola']
            cur_user.close()
            conn_user.close()
        
        limit = request.args.get('limit', 20, type=int)
        offset = request.args.get('offset', 0, type=int)
        search = request.args.get('search', '').strip()
        sort_by = request.args.get('sort_by', 'created_at').lower()
        sort_order = request.args.get('sort_order', 'desc').lower()
        kategorije_str = request.args.get('kategorije', '').strip()
        boje_str = request.args.get('boje', '').strip()
        veličine_str = request.args.get('veličine', '').strip()
        group_by = request.args.get('group_by', '').strip().lower()
        code_base = request.args.get('code_base', '').strip()
        min_stanje = request.args.get('min_stanje', 1, type=int)
        
        if limit < 1:
            limit = 20
        if limit > 100:
            limit = 100
        if offset < 0:
            offset = 0
        
        if min_stanje < 0:
            min_stanje = 1
        
        allowed_sort_fields = ['ime', 'cena', 'popust', 'stanje', 'kategorija', 'created_at']
        if sort_by not in allowed_sort_fields:
            sort_by = 'created_at'
        
        if sort_order not in ['asc', 'desc']:
            sort_order = 'desc'
        
        allowed_group_by = ['code_base', '']
        if group_by not in allowed_group_by:
            group_by = ''
        
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        where_conditions = []
        params = []
        
        if search:
            # Ako search ima crticu, može biti format "code_base-code_variant"
            if '-' in search:
                parts = search.split('-')
                if len(parts) == 2:
                    code_base_search = parts[0].strip()
                    code_variant_search = parts[1].strip()
                    
                    # Proveravamo da li je code_variant broj
                    try:
                        code_variant_num = int(code_variant_search)
                        where_conditions.append("(p.code_base ILIKE %s AND p.code_variant = %s)")
                        search_pattern = f"%{code_base_search}%"
                        params.extend([search_pattern, code_variant_num])
                    except ValueError:
                        # Ako nije broj, pretražuj kao običan search
                        where_conditions.append("(p.ime ILIKE %s OR p.code_base ILIKE %s)")
                        search_pattern = f"%{search}%"
                        params.extend([search_pattern, search_pattern])
                else:
                    # Ako ima više crtice, pretražuj kao običan search
                    where_conditions.append("(p.ime ILIKE %s OR p.code_base ILIKE %s)")
                    search_pattern = f"%{search}%"
                    params.extend([search_pattern, search_pattern])
            else:
                # Običan search - po imenu ili code_base
                where_conditions.append("(p.ime ILIKE %s OR p.code_base ILIKE %s)")
                search_pattern = f"%{search}%"
                params.extend([search_pattern, search_pattern])
        
        if kategorije_str:
            kategorije_list = [k.strip() for k in kategorije_str.split(',') if k.strip()]
            if kategorije_list:
                placeholders = ','.join(['%s'] * len(kategorije_list))
                where_conditions.append(f"k.kategorija IN ({placeholders})")
                params.extend(kategorije_list)
        
        if boje_str:
            boje_list = [b.strip() for b in boje_str.split(',') if b.strip()]
            if boje_list:
                placeholders = ','.join(['%s'] * len(boje_list))
                where_conditions.append(f"p.boja IN ({placeholders})")
                params.extend(boje_list)
        
        if veličine_str:
            veličine_list = [v.strip() for v in veličine_str.split(',') if v.strip()]
            if veličine_list:
                placeholders = ','.join(['%s'] * len(veličine_list))
                where_conditions.append(f"p.velicina IN ({placeholders})")
                params.extend(veličine_list)
        
        if code_base:
            where_conditions.append("p.code_base = %s")
            params.append(code_base)
        
        # Grupisanje po code_base - prikaži samo prvu varijantu
        if group_by == 'code_base':
            where_conditions.append("p.code_variant = 1")
        
        # Filter po dostupnosti - samo za obične korisnike (rola 0) i nekorisnike
        # Admin (rola 1) i staff (rola 2) vide sve proizvode
        if rola not in [1, 2]:  # Ako NIJE admin ili staff
            where_conditions.append("p.stanje > 0")
        
        where_clause = ""
        if where_conditions:
            where_clause = "WHERE " + " AND ".join(where_conditions)
        
        count_query = f"SELECT COUNT(DISTINCT p.id) as ukupno FROM proizvodi p LEFT JOIN kategorije k ON p.kategorija = k.id {where_clause}"
        cur.execute(count_query, params)
        ukupno_proizvoda = cur.fetchone()['ukupno']
        
        if sort_by == 'kategorija':
            sort_field = f"k.kategorija {sort_order.upper()}"
        else:
            sort_field = f"p.{sort_by} {sort_order.upper()}"
        
        query = f"""SELECT p.id, p.code_base, p.code_variant, p.ime, p.opis, p.stanje, p.boja, p.velicina, p.slike, p.fav, 
                           k.kategorija, p.cena, p.popust, p.created_at, p.updated_at 
                    FROM proizvodi p
                    LEFT JOIN kategorije k ON p.kategorija = k.id
                    {where_clause}
                    ORDER BY {sort_field}, p.code_variant ASC
                    LIMIT %s OFFSET %s"""
        
        params.extend([limit, offset])
        cur.execute(query, params)
        proizvodi = cur.fetchall()
        cur.close()
        conn.close()
        
        return jsonify({
            "proizvodi": [dict(p) for p in proizvodi],
            "pagination": {
                "limit": limit,
                "offset": offset,
                "ukupno_proizvoda": ukupno_proizvoda
            }
        }), 200
        
    except Exception as e:
        return jsonify({"message": f"Greška na serveru: {str(e)}"}), 500


@proizvodi_bp.route('/put', methods=['PUT'])
@jwt_required()
def azuriraj_proizvod():
    """
    Ažurira proizvod ili varijante proizvoda
    
    Opcija 1 - Ažuriranje po ID:
    {
        "id": 1,
        "ime": "Novi naziv",
        "boja": "Bela"
    }
    
    Opcija 2 - Ažuriranje varijanti po code_base:
    {
        "code_base": "PROD-001",
        "varijante": [
            {
                "ime": "Nike Patika",
                "opis": "...",
                "kategorija": "Obuća",
                "boja": "Crna",
                "velicina": "42",
                "stanje": 100,
                "slike": [...],
                "fav": true
            }
        ]
    }
    """
    try:
        current_user_id = get_jwt_identity()
        
        # Provera rola
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("SELECT rola FROM users WHERE id = %s", (int(current_user_id),))
        user = cur.fetchone()
        
        if not user or user['rola'] != 1:
            return jsonify({"message": "Nemate dozvolu za ovu akciju"}), 403
        
        data = request.get_json()
        
        if not data:
            return jsonify({"message": "Nedostaju podaci"}), 400
        
        # Opcija 2: Ažuriranje varijanti po code_base
        if data.get('code_base') and data.get('varijante'):
            code_base = data.get('code_base')
            varijante = data.get('varijante')
            
            if not isinstance(varijante, list) or len(varijante) == 0:
                return jsonify({"message": "Varijante mora biti neprazan JSON array"}), 400
            
            # Obriši sve postojeće varijante sa ovim code_base
            cur.execute("DELETE FROM proizvodi WHERE code_base = %s", (code_base,))
            conn.commit()
            
            azurirane_varijante = []
            
            for idx, varijanta in enumerate(varijante):
                code_variant = idx + 1
                
                # Pronađi kategoriju
                if not varijanta.get('kategorija'):
                    return jsonify({"message": "Svaka varijanta mora imati kategoriju"}), 400
                
                cur.execute("SELECT id FROM kategorije WHERE kategorija = %s", (varijanta.get('kategorija'),))
                kategorija = cur.fetchone()
                
                if not kategorija:
                    return jsonify({"message": f"Kategorija '{varijanta.get('kategorija')}' ne postoji"}), 404
                
                kategorija_id = kategorija['id']
                
                # Obrada slika
                sacuvane_slike = []
                if varijanta.get('slike'):
                    for slika in varijanta.get('slike', []):
                        if isinstance(slika, str):
                            # Ako je string (već sačuvana slika), prosledi dalje
                            sacuvane_slike.append(slika)
                        elif slika.get('base64'):
                            try:
                                base64_string = slika.get('base64')
                                
                                if ',' in base64_string:
                                    base64_string = base64_string.split(',')[1]
                                
                                image_data = base64.b64decode(base64_string)
                                
                                originalno_ime = slika.get('name', 'image.png')
                                ime_bez_ekstenzije, ekstenzija = os.path.splitext(originalno_ime)
                                if ekstenzija == '':
                                    ekstenzija = '.png'
                                
                                novo_ime_fajla = f"{uuid.uuid4()}{ekstenzija}"
                                
                                slike_folder = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'slike')
                                os.makedirs(slike_folder, exist_ok=True)
                                
                                fajl_putanja = os.path.join(slike_folder, novo_ime_fajla)
                                with open(fajl_putanja, 'wb') as f:
                                    f.write(image_data)
                                
                                sacuvane_slike.append(novo_ime_fajla)
                                
                            except Exception as e:
                                return jsonify({"message": f"Greška pri čuvanju slike: {str(e)}"}), 500
                
                slike_json = json.dumps(sacuvane_slike) if sacuvane_slike else '[]'
                
                # INSERT nova varijanta
                cur.execute(
                    """INSERT INTO proizvodi 
                       (code_base, code_variant, ime, opis, stanje, boja, velicina, slike, fav, kategorija, cena, popust)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                       RETURNING id, code_base, code_variant, ime, opis, stanje, boja, velicina, slike, fav, kategorija, cena, popust, created_at, updated_at""",
                    (code_base, code_variant, varijanta.get('ime'), varijanta.get('opis', ''),
                     varijanta.get('stanje', 0), varijanta.get('boja', ''),
                     varijanta.get('velicina', ''), slike_json, varijanta.get('fav', False), kategorija_id,
                     varijanta.get('cena', 0), varijanta.get('popust', 0))
                )
                
                rezultat = cur.fetchone()
                azurirane_varijante.append(dict(rezultat))
            
            conn.commit()
            cur.close()
            conn.close()
            
            return jsonify({
                "message": f"{len(azurirane_varijante)} varijanta(e) je uspešno ažuriran(o)",
                "varijante": azurirane_varijante
            }), 200
        
        # Opcija 1: Ažuriranje po ID
        elif data.get('id'):
            proizvod_id = data.get('id')
            
            # Provera da li proizvod postoji
            cur.execute("SELECT * FROM proizvodi WHERE id = %s", (proizvod_id,))
            proizvod = cur.fetchone()
            
            if not proizvod:
                return jsonify({"message": "Proizvod nije pronađen"}), 404
            
            # Pripremi podatke za ažuriranje
            fields_to_update = {}
            
            if data.get('ime'):
                fields_to_update['ime'] = data.get('ime')
            
            if data.get('opis') is not None:
                fields_to_update['opis'] = data.get('opis')
            
            if data.get('boja') is not None:
                fields_to_update['boja'] = data.get('boja')
            
            if data.get('velicina') is not None:
                fields_to_update['velicina'] = data.get('velicina')
            
            if data.get('stanje') is not None:
                fields_to_update['stanje'] = data.get('stanje')
            
            if data.get('fav') is not None:
                fields_to_update['fav'] = data.get('fav')
            
            if data.get('cena') is not None:
                fields_to_update['cena'] = data.get('cena')
            
            if data.get('popust') is not None:
                fields_to_update['popust'] = data.get('popust')
            
            # Obrada kategorije
            if data.get('kategorija'):
                cur.execute("SELECT id FROM kategorije WHERE kategorija = %s", (data.get('kategorija'),))
                kategorija = cur.fetchone()
                
                if not kategorija:
                    return jsonify({"message": f"Kategorija '{data.get('kategorija')}' ne postoji"}), 404
                
                fields_to_update['kategorija'] = kategorija['id']
            
            # Obrada slika
            if data.get('slike'):
                sacuvane_slike = []
                slike_data = data.get('slike', [])
                
                for slika in slike_data:
                    if slika.get('base64'):
                        try:
                            base64_string = slika.get('base64')
                            
                            if ',' in base64_string:
                                base64_string = base64_string.split(',')[1]
                            
                            image_data = base64.b64decode(base64_string)
                            
                            originalno_ime = slika.get('name', 'image.png')
                            ime_bez_ekstenzije, ekstenzija = os.path.splitext(originalno_ime)
                            if ekstenzija == '':
                                ekstenzija = '.png'
                            
                            novo_ime_fajla = f"{uuid.uuid4()}{ekstenzija}"
                            
                            slike_folder = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'slike')
                            os.makedirs(slike_folder, exist_ok=True)
                            
                            fajl_putanja = os.path.join(slike_folder, novo_ime_fajla)
                            with open(fajl_putanja, 'wb') as f:
                                f.write(image_data)
                            
                            sacuvane_slike.append(novo_ime_fajla)
                            
                        except Exception as e:
                            return jsonify({"message": f"Greška pri čuvanju slike: {str(e)}"}), 500
                
                fields_to_update['slike'] = json.dumps(sacuvane_slike)
            
            # Ako nema šta da se ažurira
            if not fields_to_update:
                return jsonify({"message": "Nema polja za ažuriranje"}), 400
            
            # Gradimo UPDATE query dinamički
            set_clause = ', '.join([f"{k} = %s" for k in fields_to_update.keys()])
            set_clause += ', updated_at = NOW()'
            
            query = f"UPDATE proizvodi SET {set_clause} WHERE id = %s RETURNING id, code_base, code_variant, ime, opis, stanje, boja, velicina, slike, fav, kategorija, cena, popust, created_at, updated_at"
            
            values = list(fields_to_update.values())
            values.append(proizvod_id)
            
            cur.execute(query, values)
            azuriran_proizvod = cur.fetchone()
            conn.commit()
            cur.close()
            conn.close()
            
            return jsonify({
                "message": "Proizvod je uspešno ažuriran",
                "proizvod": dict(azuriran_proizvod)
            }), 200
        
        else:
            return jsonify({"message": "Nedostaje id ili code_base sa varijantama"}), 400
        
    except Exception as e:
        return jsonify({"message": f"Greška na serveru: {str(e)}"}), 500


@proizvodi_bp.route('/delete/<int:proizvod_id>', methods=['DELETE'])
@jwt_required()
def obrisi_proizvod(proizvod_id):
    """
    Briše proizvo po ID-u
    
    Request:
    DELETE /delete/{id}
    
    Response:
    {
        "message": "Proizvod je uspešno obrisan",
        "proizvod": {
            "id": 1,
            "ime": "Proizvod",
            "code_base": "abc123xyz",
            "code_variant": 1,
            ...
        }
    }
    """
    try:
        current_user_id = get_jwt_identity()
        
        # Provera rola
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("SELECT rola FROM users WHERE id = %s", (int(current_user_id),))
        user = cur.fetchone()
        
        if not user or user['rola'] != 1:
            cur.close()
            conn.close()
            return jsonify({"message": "Nemate dozvolu za ovu akciju"}), 403
        
        # Pronađi proizvod
        cur.execute(
            "SELECT id, code_base, code_variant, ime, opis, stanje, boja, velicina, slike, fav, kategorija, cena, popust, created_at, updated_at FROM proizvodi WHERE id = %s",
            (proizvod_id,)
        )
        proizvod = cur.fetchone()
        
        if not proizvod:
            cur.close()
            conn.close()
            return jsonify({"message": "Proizvod nije pronađen"}), 404
        
        # Obriši proizvod iz baze
        cur.execute("DELETE FROM proizvodi WHERE id = %s", (proizvod_id,))
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({
            "message": "Proizvod je uspešno obrisan",
            "proizvod": dict(proizvod)
        }), 200
        
    except Exception as e:
        return jsonify({"message": f"Greška na serveru: {str(e)}"}), 500


@proizvodi_bp.route('/delete-all-variants/<code_base>', methods=['DELETE'])
@jwt_required()
def obrisi_sve_varijante(code_base):
    """
    Briše sve varijante proizvoda sa datim code_base
    
    Request:
    DELETE /delete-all-variants/{code_base}
    
    Response:
    {
        "message": "3 varijante su uspešno obrisane",
        "obrisane_varijante": [
            {
                "id": 1,
                "ime": "Proizvod",
                "code_base": "abc123xyz",
                "code_variant": 1,
                ...
            },
            ...
        ]
    }
    """
    try:
        current_user_id = get_jwt_identity()
        
        # Provera rola
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("SELECT rola FROM users WHERE id = %s", (int(current_user_id),))
        user = cur.fetchone()
        
        if not user or user['rola'] != 1:
            cur.close()
            conn.close()
            return jsonify({"message": "Nemate dozvolu za ovu akciju"}), 403
        
        # Pronađi sve varijante sa ovim code_base
        cur.execute(
            "SELECT id, code_base, code_variant, ime, opis, stanje, boja, velicina, slike, fav, kategorija, cena, popust, created_at, updated_at FROM proizvodi WHERE code_base = %s ORDER BY code_variant",
            (code_base,)
        )
        varijante = cur.fetchall()
        
        if not varijante:
            cur.close()
            conn.close()
            return jsonify({"message": f"Nijedan proizvod sa code_base '{code_base}' nije pronađen"}), 404
        
        # Obriši sve varijante sa ovim code_base
        cur.execute("DELETE FROM proizvodi WHERE code_base = %s", (code_base,))
        conn.commit()
        cur.close()
        conn.close()
        
        broj_obrisanih = len(varijante)
        
        return jsonify({
            "message": f"{broj_obrisanih} varijanta(e) je uspešno obrisano",
            "obrisane_varijante": [dict(v) for v in varijante]
        }), 200
        
    except Exception as e:
        return jsonify({"message": f"Greška na serveru: {str(e)}"}), 500
