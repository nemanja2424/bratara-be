from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from psycopg2.extras import RealDictCursor
import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

preporuceno_bp = Blueprint("preporuceno", __name__)

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


@preporuceno_bp.route('/get', methods=['GET'])
def get_preporuceno():
    """
    Preuzima top 12 preporučenih proizvoda (kao /proizvodi/get ali samo preporučene)
    Vraća po jedan proizvod po code_base, sortiran po redosledu
    
    Response:
    {
        "preporuceni": [
            {
                "boja": "Crna",
                "cena": "12999.00",
                "code_base": "khnow5wc3a",
                "code_variant": 1,
                "created_at": "Mon, 06 Apr 2026 11:59:22 GMT",
                "fav": false,
                "id": 522,
                "ime": "Gucci Evening Gown",
                "kategorija": "Haljine",
                "opis": "Luksuzna haljina sa finom obradom",
                "popust": 40,
                "slike": [],
                "stanje": 20,
                "velicina": "XS",
                "updated_at": "Mon, 06 Apr 2026 11:59:22 GMT",
                "redosled": 1
            }
        ],
        "ukupno": 1
    }
    """
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Preuzmi preporučene proizvode sa redosledom
        # Koristi DISTINCT ON po code_base da biram best variant
        query = """
            SELECT DISTINCT ON (fp.redosled, p.code_base) 
                   p.id, p.code_base, p.code_variant, p.ime, p.opis, p.stanje, 
                   p.boja, p.velicina, p.slike, p.fav, k.kategorija, p.cena, p.popust, 
                   p.created_at, p.updated_at, fp.redosled
            FROM featured_products fp
            JOIN proizvodi p ON fp.code_base = p.code_base
            LEFT JOIN kategorije k ON p.kategorija = k.id
            ORDER BY fp.redosled ASC, p.code_base, p.stanje DESC NULLS LAST, p.code_variant ASC
        """
        
        cur.execute(query)
        proizvodi = cur.fetchall()
        cur.close()
        conn.close()
        
        return jsonify({
            "preporuceni": [dict(p) for p in proizvodi],
            "ukupno": len(proizvodi)
        }), 200
        
    except Exception as e:
        return jsonify({"message": f"Greška na serveru: {str(e)}"}), 500


@preporuceno_bp.route('/post', methods=['POST'])
@jwt_required()
def post_preporuceno():
    """
    Dodaje proizvod u preporučene (samo admin)
    Dodaje se na kraj, ali može biti do 12 proizvoda
    
    Request:
    {
        "code_base": "du45m9vsuu"
    }
    
    Response:
    {
        "message": "Proizvod je dodan u preporučene",
        "preporuceni": {
            "id": 1,
            "code_base": "du45m9vsuu",
            "redosled": 3,
            "created_at": "2026-04-16 10:30:00"
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
            return jsonify({"message": "Nemate dozvolu za ovu akciju"}), 403
        
        data = request.get_json()
        
        if not data or not data.get('code_base'):
            return jsonify({"message": "Nedostaje code_base"}), 400
        
        code_base = data.get('code_base')
        
        # Provjeri da li code_base postoji
        cur.execute("SELECT COUNT(*) as cnt FROM proizvodi WHERE code_base = %s", (code_base,))
        if cur.fetchone()['cnt'] == 0:
            return jsonify({"message": "Proizvod sa ovim code_base nije pronađen"}), 404
        
        # Provjeri da li već postoji
        cur.execute("SELECT id FROM featured_products WHERE code_base = %s", (code_base,))
        if cur.fetchone():
            return jsonify({"message": "Proizvod je već u preporučenima"}), 400
        
        # Provjeri limit (max 12)
        cur.execute("SELECT COUNT(*) as cnt FROM featured_products")
        if cur.fetchone()['cnt'] >= 12:
            return jsonify({"message": "Maksimalno 12 preporučenih proizvoda. Obriši neki prije nego dodaš novi."}), 400
        
        # Pronađi sljedeći redosled
        cur.execute("SELECT MAX(redosled) as max_redosled FROM featured_products")
        max_redosled = cur.fetchone()['max_redosled']
        novi_redosled = (max_redosled or 0) + 1
        
        # Dodaj u preporučene
        cur.execute(
            "INSERT INTO featured_products (code_base, redosled) VALUES (%s, %s) RETURNING id, code_base, redosled, created_at",
            (code_base, novi_redosled)
        )
        
        novi_preporuceni = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({
            "message": "Proizvod je dodan u preporučene",
            "preporuceni": dict(novi_preporuceni)
        }), 201
        
    except Exception as e:
        return jsonify({"message": f"Greška na serveru: {str(e)}"}), 500


@preporuceno_bp.route('/delete', methods=['DELETE'])
@jwt_required()
def delete_preporuceno():
    """
    Briše proizvod iz preporučenih
    
    Request:
    {
        "code_base": "du45m9vsuu"
    }
    ili
    {
        "redosled": 3
    }
    
    Response:
    {
        "message": "Proizvod je obrisan iz preporučenih",
        "preporuceni": {
            "id": 1,
            "code_base": "du45m9vsuu",
            "redosled": 3
        }
    }
    """
    try:
        current_user_id = get_jwt_identity()
        
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("SELECT rola FROM users WHERE id = %s", (int(current_user_id),))
        user = cur.fetchone()
        
        if not user or user['rola'] != 1:
            return jsonify({"message": "Nemate dozvolu za ovu akciju"}), 403
        
        data = request.get_json()
        
        if not data or (not data.get('code_base') and not data.get('redosled')):
            return jsonify({"message": "Nedostaje code_base ili redosled"}), 400
        
        if data.get('code_base'):
            code_base = data.get('code_base')
            cur.execute(
                "DELETE FROM featured_products WHERE code_base = %s RETURNING id, code_base, redosled",
                (code_base,)
            )
        else:
            redosled = data.get('redosled')
            cur.execute(
                "DELETE FROM featured_products WHERE redosled = %s RETURNING id, code_base, redosled",
                (redosled,)
            )
        
        obrisan = cur.fetchone()
        
        if not obrisan:
            return jsonify({"message": "Proizvod nije pronađen"}), 404
        
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({
            "message": "Proizvod je obrisan iz preporučenih",
            "preporuceni": dict(obrisan)
        }), 200
        
    except Exception as e:
        return jsonify({"message": f"Greška na serveru: {str(e)}"}), 500


@preporuceno_bp.route('/patch', methods=['PATCH'])
@jwt_required()
def patch_preporuceno():
    """
    Ažurira redosled preporučenih proizvoda
    
    Request - opcija 1 (zamijeni dva):
    {
        "redosled_1": 1,
        "redosled_2": 3
    }
    
    Request - opcija 2 (postavi na određeni redosled):
    {
        "code_base": "du45m9vsuu",
        "redosled": 5
    }
    
    Response:
    {
        "message": "Redosled je ažuriran",
        "preporuceni": [
            {"id": 1, "code_base": "...", "redosled": 1},
            {"id": 2, "code_base": "...", "redosled": 2}
        ]
    }
    """
    try:
        current_user_id = get_jwt_identity()
        
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("SELECT rola FROM users WHERE id = %s", (int(current_user_id),))
        user = cur.fetchone()
        
        if not user or user['rola'] != 1:
            return jsonify({"message": "Nemate dozvolu za ovu akciju"}), 403
        
        data = request.get_json()
        
        if not data:
            return jsonify({"message": "Nedostaju podaci"}), 400
        
        # Opcija 1: Zamijeni dva redosleda
        if 'redosled_1' in data and 'redosled_2' in data:
            redosled_1 = data.get('redosled_1')
            redosled_2 = data.get('redosled_2')
            
            # Zamijeni redoslede
            cur.execute(
                "UPDATE featured_products SET redosled = -1 WHERE redosled = %s",
                (redosled_1,)
            )
            cur.execute(
                "UPDATE featured_products SET redosled = %s WHERE redosled = %s",
                (redosled_1, redosled_2)
            )
            cur.execute(
                "UPDATE featured_products SET redosled = %s WHERE redosled = -1",
                (redosled_2,)
            )
        
        # Opcija 2: Postavi code_base na novi redosled
        elif 'code_base' in data and 'redosled' in data:
            code_base = data.get('code_base')
            novi_redosled = data.get('redosled')
            
            # Pronađi stari redosled
            cur.execute(
                "SELECT redosled FROM featured_products WHERE code_base = %s",
                (code_base,)
            )
            result = cur.fetchone()
            
            if not result:
                return jsonify({"message": "Proizvod nije pronađen"}), 404
            
            stari_redosled = result['redosled']
            
            if stari_redosled == novi_redosled:
                return jsonify({"message": "Redosled je isti"}), 400
            
            # Pomjeri sve između
            if stari_redosled < novi_redosled:
                cur.execute(
                    "UPDATE featured_products SET redosled = redosled - 1 WHERE redosled > %s AND redosled <= %s",
                    (stari_redosled, novi_redosled)
                )
            else:
                cur.execute(
                    "UPDATE featured_products SET redosled = redosled + 1 WHERE redosled >= %s AND redosled < %s",
                    (novi_redosled, stari_redosled)
                )
            
            cur.execute(
                "UPDATE featured_products SET redosled = %s WHERE code_base = %s",
                (novi_redosled, code_base)
            )
        else:
            return jsonify({"message": "Nedostaju parametri. Trebaju: redosled_1+redosled_2 ILI code_base+redosled"}), 400
        
        conn.commit()
        
        # Preuzmi sve preporučene nakon update-a
        cur.execute(
            "SELECT id, code_base, redosled FROM featured_products ORDER BY redosled ASC"
        )
        rezultat = cur.fetchall()
        cur.close()
        conn.close()
        
        return jsonify({
            "message": "Redosled je ažuriran",
            "preporuceni": [dict(r) for r in rezultat]
        }), 200
        
    except Exception as e:
        return jsonify({"message": f"Greška na serveru: {str(e)}"}), 500
