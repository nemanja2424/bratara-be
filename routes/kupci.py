from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from psycopg2.extras import RealDictCursor
import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

kupci_bp = Blueprint("kupci", __name__)

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


@kupci_bp.route('/get', methods=['GET'])
@jwt_required()
def get_kupci():
    """
    Vraća sve kupce (korisnike sa rola=0) sa paginacijom
    Requires: JWT token + rola=1 (admin)
    
    Query parameters:
    - limit: broj kupaca po stranici (default: 50, max: 100)
    - offset: od kog reda početi (default: 0)
    
    Primeri:
    - /get?limit=50&offset=0     # Prvих 50
    - /get?limit=50&offset=50    # Sledećih 50 (stranica 2)
    - /get?limit=10&offset=0     # Prvих 10
    - /get                       # Default (50 kupaca, stranica 1)
    
    Response:
    {
        "kupci": [
            {
                "id": 1,
                "ime": "Nemanja",
                "prezime": "Jakovljevic",
                "email": "njakovlje@gmail.com",
                "telefon": "+381631234567",
                "adresa": "Kneza Milaša 5, Beograd"
            },
            {
                "id": 2,
                "ime": "Marko",
                "prezime": "Marković",
                "email": "marko@gmail.com",
                "telefon": "+381601234567",
                "adresa": "Terazije 10, Beograd"
            }
        ],
        "pagination": {
            "limit": 50,
            "offset": 0,
            "ukupno_kupaca": 150
        }
    }
    """
    try:
        current_user_id = get_jwt_identity()
        
        # Provera rola - samo admin može videti sve kupce
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("SELECT rola FROM users WHERE id = %s", (int(current_user_id),))
        user = cur.fetchone()
        
        if not user or user['rola'] != 1:
            cur.close()
            conn.close()
            return jsonify({"message": "Nemate dozvolu za ovu akciju"}), 403
        
        # Preuzmi limit i offset parametare
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)
        
        # Validacija
        if limit < 1:
            limit = 50
        if limit > 100:  # Max 100 kupaca po query
            limit = 100
        if offset < 0:
            offset = 0
        
        # Preuzmi ukupan broj kupaca (samo rola = 0)
        cur.execute("SELECT COUNT(*) as ukupno FROM users WHERE rola = 0")
        ukupno_kupaca = cur.fetchone()['ukupno']
        
        # Preuzmi kupce (isključi lozinku i admin korisnike)
        cur.execute(
            """SELECT id, ime, prezime, email, telefon, adresa 
               FROM users 
               WHERE rola = 0
               ORDER BY created_at DESC 
               LIMIT %s OFFSET %s""",
            (limit, offset)
        )
        kupci = cur.fetchall()
        cur.close()
        conn.close()
        
        return jsonify({
            "kupci": [dict(k) for k in kupci],
            "pagination": {
                "limit": limit,
                "offset": offset,
                "ukupno_kupaca": ukupno_kupaca
            }
        }), 200
        
    except Exception as e:
        return jsonify({"message": f"Greška na serveru: {str(e)}"}), 500
