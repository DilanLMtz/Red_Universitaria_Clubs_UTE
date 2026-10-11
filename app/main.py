from flask import Flask, render_template, request, jsonify
import mysql.connector
from dotenv import load_dotenv
import os
import pandas as pd
from werkzeug.utils import secure_filename

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
        estado_bd = "Conectado exitosamente a MySQL"
        conexion.close()
        
    return f"<h1>Red Universitaria de Clubs UTE</h1><p>Estado de la Base de Datos: <b>{estado_bd}</b></p>"

@app.route('/alumno')
def panel_alumno():
    """Panel donde el alumno verá su código QR o cámara."""
    return "Panel del Alumno: Aquí irá la interfaz para escanear el QR."

@app.route('/coordinador')
def panel_coordinador():
    """Muestra la vista para subir el Excel."""
    return render_template('subir_excel.html')

@app.route('/coordinador/subir-excel', methods=['POST'])
def procesar_excel_web():
    """Recibe el archivo Excel desde la web, lo procesa y guarda en MySQL."""
    if 'archivo_excel' not in request.files:
        return render_template('subir_excel.html', mensaje="No se seleccionó ningún archivo.")
    
    archivo = request.files['archivo_excel']
    
    if archivo.filename == '':
        return render_template('subir_excel.html', mensaje="Archivo sin nombre.")
    
    if archivo:
        # Asegurar nombre seguro para evitar errores
        filename = secure_filename(archivo.filename)
        
        try:
            # Leer el archivo Excel directamente desde la memoria RAM usando pandas
            df = pd.read_excel(archivo)
        except Exception as e:
            return render_template('subir_excel.html', mensaje=f"Error al leer el Excel: {e}")

        # Validar columnas requeridas (usando las de tu prueba: matricula, nombre_completo, nombre_club)
        columnas_requeridas = {'matricula', 'nombre_completo', 'nombre_club'}
        if not columnas_requeridas.issubset(df.columns):
            return render_template('subir_excel.html', mensaje=f"El Excel debe tener las columnas: {list(columnas_requeridas)}")

        conexion = obtener_conexion()
        if not conexion:
            return render_template('subir_excel.html', mensaje="Error de conexión con la Base de Datos.")
        
        cursor = conexion.cursor()
        registros_nuevos = 0
        inscripciones_nuevas = 0

        for _, row in df.iterrows():
            matricula = str(row['matricula']).strip()
            nombre = str(row['nombre_completo']).strip()
            nombre_club = str(row['nombre_club']).strip()

            # 1. Verificar o insertar al alumno
            cursor.execute("SELECT matricula FROM Alumnos WHERE matricula = %s", (matricula,))
            if not cursor.fetchone():
                cursor.execute("INSERT INTO Alumnos (matricula, nombre_completo, contrasena) VALUES (%s, %s, %s)", 
                               (matricula, nombre, matricula))
                registros_nuevos += 1

            # 2. Buscar el ID del club
            cursor.execute("SELECT id_club FROM Clubs WHERE nombre_club = %s", (nombre_club,))
            resultado_club = cursor.fetchone()

            if resultado_club:
                id_club = resultado_club[0]
                # 3. Verificar si ya está inscrito
                cursor.execute("SELECT id_inscripcion FROM Inscripciones WHERE matricula_alumno = %s AND id_club = %s", 
                               (matricula, id_club))
                if not cursor.fetchone():
                    cursor.execute("INSERT INTO Inscripciones (matricula_alumno, id_club) VALUES (%s, %s)", 
                                   (matricula, id_club))
                    inscripciones_nuevas += 1

        conexion.commit()
        cursor.close()
        conexion.close()

        mensaje_exito = f"¡Importación web exitosa! Alumnos nuevos: {registros_nuevos}, Nuevas inscripciones: {inscripciones_nuevas}"
        return render_template('subir_excel.html', mensaje=mensaje_exito)

# --- ARRANQUE DEL SERVIDOR ---
if __name__ == '__main__':
    app.run(debug=True, port=5000)