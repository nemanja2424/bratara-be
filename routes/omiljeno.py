from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from psycopg2.extras import RealDictCursor
import psycopg2
import os
import json
from dotenv import load_dotenv

load_dotenv()

omiljeno_bp = Blueprint("omiljeno", __name__)

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


@omiljeno_bp.route('/get', methods=['GET'])
@jwt_required()
def get_omiljeno():
    """
    Preuzima omiljene proizvode trenutnog korisnika
    
    Header: Authorization: Bearer <access_token>
    
    Response (200):
    {
        "omiljeno": ["code_base_1", "code_base_2", "code_base_3"]
    }
    """
    try:
        current_user_id = get_jwt_identity()
        
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("SELECT omiljeno FROM users WHERE id = %s", (int(current_user_id),))
        user = cur.fetchone()
        cur.close()
        conn.close()
        
        if not user:
            return jsonify({"message": "Korisnik nije pronađen"}), 404
        
        omiljeno = user['omiljeno'] if isinstance(user['omiljeno'], list) else json.loads(user['omiljeno'] or '[]')
        
        return jsonify({
            "omiljeno": omiljeno
        }), 200
        
    except Exception as e:
        return jsonify({"message": f"Greška na serveru: {str(e)}"}), 500


@omiljeno_bp.route('/patch', methods=['PATCH'])
@jwt_required()
def patch_omiljeno():
    """
    Ažurira listu omiljenih proizvoda korisnika
    
    Header: Authorization: Bearer <access_token>
    
    Request:
    {
        "omiljeno": ["code_base_1", "code_base_2", "code_base_3"]
    }
    
    Response (200):
    {
        "message": "Omiljeni proizvodi su ažurirani",
        "omiljeno": ["code_base_1", "code_base_2", "code_base_3"]
    }
    """
    try:
        current_user_id = get_jwt_identity()
        data = request.get_json()
        
        if not data or 'omiljeno' not in data:
            return jsonify({"message": "Nedostaje 'omiljeno' polje"}), 400
        
        omiljeno = data.get('omiljeno', [])
        
        # Validacija - mora biti lista
        if not isinstance(omiljeno, list):
            return jsonify({"message": "'omiljeno' mora biti lista"}), 400
        
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Proveri da li korisnik postoji
        cur.execute("SELECT id FROM users WHERE id = %s", (int(current_user_id),))
        user = cur.fetchone()
        
        if not user:
            cur.close()
            conn.close()
            return jsonify({"message": "Korisnik nije pronađen"}), 404
        
        # Ažuriraj omiljeno polje
        cur.execute(
            "UPDATE users SET omiljeno = %s WHERE id = %s RETURNING omiljeno",
            (json.dumps(omiljeno), int(current_user_id))
        )
        
        result = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        
        updated_omiljeno = json.loads(result['omiljeno']) if isinstance(result['omiljeno'], str) else result['omiljeno']
        
        return jsonify({
            "message": "Omiljeni proizvodi su ažurirani",
            "omiljeno": updated_omiljeno
        }), 200
        
    except Exception as e:
        return jsonify({"message": f"Greška na serveru: {str(e)}"}), 500
