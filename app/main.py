from flask import Flask, render_template, request, jsonify
import mysql.connector
from dotenv import load_dotenv
import os

# Cargar las variables de entorno desde el archivo .env
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "clave_super_secreta_desarrollo")

# --- CONFIGURACIÓN DE BASE DE DATOS ---
def obtener_conexion():
    """Crea y retorna la conexión a MySQL usando variables de entorno."""
    try:
        conexion = mysql.connector.connect(
            host=os.getenv("DB_HOST", "localhost"),
            user=os.getenv("DB_USER", "root"),
            password=os.getenv("DB_PASSWORD", ""),
            database=os.getenv("DB_NAME", "clubs_ute")
        )
        return conexion
    except mysql.connector.Error as err:
        print(f"Error de conexión a la BD: {err}")
        return None

# --- RUTAS DE LA APLICACIÓN WEB ---

@app.route('/')
def index():
    """Página principal / Login de usuarios."""
    # Probemos si la base de datos responde haciendo una consulta simple
    conexion = obtener_conexion()
    estado_bd = "Desconectado de MySQL"
    if conexion:
        estado_bd = "Conectado exitosamente a MySQL 🚀"
        conexion.close()
        
    return f"<h1>Red Universitaria de Clubs UTE</h1><p>Estado de la Base de Datos: <b>{estado_bd}</b></p>"

@app.route('/alumno')
def panel_alumno():
    """Panel donde el alumno verá su código QR o cámara."""
    return "Panel del Alumno: Aquí irá la interfaz para escanear el QR."

@app.route('/coordinador')
def panel_coordinador():
    """Panel donde el coordinador generará el código QR."""
    return "Panel del Coordinador: Aquí se generará el QR de la sesión."

# --- ARRANQUE DEL SERVIDOR ---
if __name__ == '__main__':
    app.run(debug=True, port=5000)