from flask import Flask, render_template, request, jsonify
import mysql.connector
from dotenv import load_dotenv
import os
import pandas as pd
from werkzeug.utils import secure_filename

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "clave_super_secreta_desarrollo")

def obtener_conexion():
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

# --- RUTAS PRINCIPALES DE VISTAS ---

@app.route('/')
def index():
    """Página principal del sistema."""
    return render_template('index.html')

@app.route('/alumno')
def panel_alumno():
    """Panel principal del alumno."""
    return render_template('panel_alumno.html')

@app.route('/coordinador')
def panel_coordinador():
    """Panel principal del coordinador."""
    return render_template('panel_coordinador.html')

@app.route('/coordinador/subir-excel')
def vista_subir_excel():
    """Muestra la vista para subir el Excel."""
    return render_template('subir_excel.html')

# --- RUTA DE PROCESAMIENTO DE EXCEL ---

@app.route('/coordinador/subir-excel', methods=['POST'])
def procesar_excel_web():
    if 'archivo_excel' not in request.files:
        return render_template('subir_excel.html', mensaje=" No se seleccionó ningún archivo.")
    
    archivo = request.files['archivo_excel']
    if archivo.filename == '':
        return render_template('subir_excel.html', mensaje=" Archivo sin nombre.")
    
    if archivo:
        try:
            df = pd.read_excel(archivo)
        except Exception as e:
            return render_template('subir_excel.html', mensaje=f" Error al leer el Excel: {e}")

        columnas_requeridas = {'matricula', 'nombre_completo', 'nombre_club'}
        if not columnas_requeridas.issubset(df.columns):
            return render_template('subir_excel.html', mensaje=f" El Excel debe tener las columnas: {list(columnas_requeridas)}")

        conexion = obtener_conexion()
        if not conexion:
            return render_template('subir_excel.html', mensaje=" Error de conexión con la Base de Datos.")
        
        cursor = conexion.cursor()
        registros_nuevos = 0
        inscripciones_nuevas = 0

        for _, row in df.iterrows():
            matricula = str(row['matricula']).strip()
            nombre = str(row['nombre_completo']).strip()
            nombre_club = str(row['nombre_club']).strip()

            cursor.execute("SELECT matricula FROM Alumnos WHERE matricula = %s", (matricula,))
            if not cursor.fetchone():
                cursor.execute("INSERT INTO Alumnos (matricula, nombre_completo, contrasena) VALUES (%s, %s, %s)", 
                               (matricula, nombre, matricula))
                registros_nuevos += 1

            cursor.execute("SELECT id_club FROM Clubs WHERE nombre_club = %s", (nombre_club,))
            resultado_club = cursor.fetchone()

            if resultado_club:
                id_club = resultado_club[0]
                cursor.execute("SELECT id_inscripcion FROM Inscripciones WHERE matricula_alumno = %s AND id_club = %s", 
                               (matricula, id_club))
                if not cursor.fetchone():
                    cursor.execute("INSERT INTO Inscripciones (matricula_alumno, id_club) VALUES (%s, %s)", 
                                   (matricula, id_club))
                    inscripciones_nuevas += 1

        conexion.commit()
        cursor.close()
        conexion.close()

        mensaje_exito = f" ¡Importación web exitosa! Alumnos nuevos: {registros_nuevos}, Nuevas inscripciones: {inscripciones_nuevas}"
        return render_template('subir_excel.html', mensaje=mensaje_exito)

if __name__ == '__main__':
    app.run(debug=True, port=5000)