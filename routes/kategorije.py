from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from psycopg2.extras import RealDictCursor
import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

kategorije_bp = Blueprint("kategorije", __name__)

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


@kategorije_bp.route('/get', methods=['GET'])
def get_kategorije():
    """
    Preuzima sve kategorije iz baze sa opcionalno filteriranjem po statusu
    
    Query parameters:
    - active: filter po statusu (true/false/ne prosleđuje = sve)
    
    Primeri:
    - /get → sve kategorije
    - /get?active=true → samo aktivne kategorije
    - /get?active=false → samo neaktivne kategorije
    
    Response:
    {
        "kategorije": [
            {"id": 1, "kategorija": "Patike", "active": true, "created_at": "..."},
            {"id": 2, "kategorija": "Duksevi", "active": true, "created_at": "..."}
        ]
    }
    """
    try:
        # Preuzmi opcionalni active parametar
        active_param = request.args.get('active', '').lower()
        
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Gradim WHERE clause na osnovu parametra
        where_clause = ""
        if active_param == 'true':
            where_clause = "WHERE active = true"
        elif active_param == 'false':
            where_clause = "WHERE active = false"
        # Ako active_param nije prosleđen ili je neka druga vrednost, ne dodajemo WHERE
        
        query = f"SELECT id, kategorija, active, parent, created_at FROM kategorije {where_clause}"
        cur.execute(query)
        kategorije = cur.fetchall()
        cur.close()
        conn.close()
        
        return jsonify({
            "kategorije": kategorije
        }), 200
        
    except Exception as e:
        return jsonify({"message": f"Greška na serveru: {str(e)}"}), 500


@kategorije_bp.route('/post', methods=['POST'])
@jwt_required()
def post_kategorije():
    """
    Kreira novu kategoriju
    Request:
    {
        "kategorija": "Patike",
        "parent": "Obuća"  (obavezno - mora biti jedna od: "Odeća", "Obuća", "Torbe")
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
        
        if not data or not data.get('kategorija'):
            return jsonify({"message": "Nedostaje naziv kategorije"}), 400
        
        if not data.get('parent'):
            return jsonify({"message": "Nedostaje parent (mora biti: Odeća, Obuća ili Torbe)"}), 400
        
        kategorija = data.get('kategorija')
        parent = data.get('parent')
        
        # Validacija parent-a
        valid_parents = ['Odeća', 'Obuća', 'Torbe']
        if parent not in valid_parents:
            return jsonify({"message": f"Nevažeći parent. Mora biti jedan od: {', '.join(valid_parents)}"}), 400
        
        cur.execute("INSERT INTO kategorije (kategorija, parent) VALUES (%s, %s) RETURNING id, kategorija, active, parent, created_at", (kategorija, parent))
        nova_kategorija = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({
            "message": "Kategorija je uspešno kreirana",
            "kategorija": dict(nova_kategorija)
        }), 201
        
    except Exception as e:
        return jsonify({"message": f"Greška na serveru: {str(e)}"}), 500


@kategorije_bp.route('/delete', methods=['DELETE'])
@jwt_required()
def delete_kategorije():
    """
    Briše kategoriju po ID-u ili po nazivu
    Request:
    {
        "id": 1
    }
    ili
    {
        "kategorija": "Patike"
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
        
        if not data or (not data.get('id') and not data.get('kategorija')):
            return jsonify({"message": "Nedostaje id ili naziv kategorije"}), 400
        
        if data.get('id'):
            kategorijaId = data.get('id')
            cur.execute("DELETE FROM kategorije WHERE id = %s RETURNING id, kategorija, active, created_at", (kategorijaId,))
        elif data.get('kategorija'):
            kategorija = data.get('kategorija')
            cur.execute("DELETE FROM kategorije WHERE kategorija = %s RETURNING id, kategorija, active, created_at", (kategorija,))
        
        obrisana_kategorija = cur.fetchone()
        conn.commit()
        
        if not obrisana_kategorija:
            return jsonify({"message": "Kategorija nije pronađena"}), 404
        
        cur.close()
        conn.close()
        
        return jsonify({
            "message": "Kategorija je uspešno obrisana",
            "kategorija": dict(obrisana_kategorija)
        }), 200
        
    except Exception as e:
        return jsonify({"message": f"Greška na serveru: {str(e)}"}), 500


@kategorije_bp.route('/put', methods=['PUT'])
@jwt_required()
def edit_kategorije():
    """
    Menja naziv, parent i/ili active status kategorije
    Request:
    {
        "id": 1,
        "kategorija": "Novi naziv",
        "parent": "Odeća",
        "active": false
    }
    parent - opciono, mora biti jedan od: "Odeća", "Obuća", "Torbe"
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
        
        if not data or not data.get('id'):
            return jsonify({"message": "Nedostaje id kategorije"}), 400
        
        kategorijaId = data.get('id')
        nova_kategorija = data.get('kategorija')
        parent = data.get('parent')
        active = data.get('active')
        
        # Ako nemamo šta da menjamo
        if nova_kategorija is None and parent is None and active is None:
            return jsonify({"message": "Nedostaje novo naziv, parent ili active status"}), 400
        
        # Validacija parent-a
        valid_parents = ['Odeća', 'Obuća', 'Torbe']
        if parent is not None and parent not in valid_parents:
            return jsonify({"message": f"Nevažeći parent. Mora biti jedan od: {', '.join(valid_parents)}"}), 400
        
        # Gradimo dinamički query
        update_fields = []
        params = []
        
        if nova_kategorija is not None:
            update_fields.append("kategorija = %s")
            params.append(nova_kategorija)
        
        if parent is not None:
            update_fields.append("parent = %s")
            params.append(parent)
        
        if active is not None:
            update_fields.append("active = %s")
            params.append(active)
        
        params.append(kategorijaId)
        
        query = f"UPDATE kategorije SET {', '.join(update_fields)} WHERE id = %s RETURNING id, kategorija, active, parent, created_at"
        cur.execute(query, params)
        
        azurirana_kategorija = cur.fetchone()
        conn.commit()
        
        if not azurirana_kategorija:
            return jsonify({"message": "Kategorija nije pronađena"}), 404
        
        cur.close()
        conn.close()
        
        return jsonify({
            "message": "Kategorija je uspešno ažurirana",
            "kategorija": dict(azurirana_kategorija)
        }), 200
        
    except Exception as e:
        return jsonify({"message": f"Greška na serveru: {str(e)}"}), 500
