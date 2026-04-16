from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from flask_jwt_extended import JWTManager
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from mailManager import send_email
from datetime import timedelta

load_dotenv()

# PostgreSQL Konfiguracija
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

app = Flask(__name__)
CORS(app)

# JWT Konfiguracija
app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET', 'promeniti-tajni-kljuc')
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = False
jwt = JWTManager(app)

from routes.auth import auth_bp
app.register_blueprint(auth_bp, url_prefix="/api/auth")

from routes.kategorije import kategorije_bp
app.register_blueprint(kategorije_bp, url_prefix="/api/kategorije")

from routes.proizvodi import proizvodi_bp
app.register_blueprint(proizvodi_bp, url_prefix="/api/proizvodi")

from routes.kupci import kupci_bp
app.register_blueprint(kupci_bp, url_prefix="/api/kupci")

from routes.porudzbine import porudzbine_bp
app.register_blueprint(porudzbine_bp, url_prefix="/api/porudzbine")

from routes.omiljeno import omiljeno_bp
app.register_blueprint(omiljeno_bp, url_prefix="/api/omiljeno")

from routes.preporuceno import preporuceno_bp
app.register_blueprint(preporuceno_bp, url_prefix="/api/preporuceno")


# Pokretanje aplikacije
if __name__ == '__main__':
    app.run(debug=True)

    #za host na lokalnoj mrezi
    #app.run(host="0.0.0.0", port=5000, debug=True)