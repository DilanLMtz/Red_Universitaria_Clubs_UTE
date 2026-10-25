from flask import Flask, render_template, request, redirect, url_for, session
import mysql.connector
from dotenv import load_dotenv
import os
import pandas as pd
from werkzeug.utils import secure_filename
import qrcode
import io
import base64
from datetime import date
from flask import jsonify

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


@app.route('/')
def index():
    """Muestra el login principal o redirige si ya hay sesión activa."""
    if 'matricula' in session:
        return redirect(url_for('panel_alumno'))
    if 'id_usuario' in session:
        return redirect(url_for('panel_coordinador'))
    return render_template('index.html')

@app.route('/login', methods=['POST'])
def login():
    """Busca las credenciales primero en Alumnos y si no, en Coordinadores (Usuarios)."""
    identificador = request.form.get('identificador').strip()
    contrasena = request.form.get('contrasena').strip()

    conexion = obtener_conexion()
    cursor = conexion.cursor(dictionary=True)

    # 1. Intentar validar como Alumno (usando matrícula)
    cursor.execute("SELECT * FROM Alumnos WHERE matricula = %s AND contrasena = %s", (identificador, contrasena))
    alumno = cursor.fetchone()

    if alumno:
        cursor.close()
        conexion.close()
        session['matricula'] = alumno['matricula']
        session['nombre'] = alumno['nombre_completo']
        return redirect(url_for('panel_alumno'))

    # 2. Intentar validar como Coordinador (usando correo institucional)
    cursor.execute("SELECT * FROM Usuarios WHERE correo = %s AND contrasena = %s", (identificador, contrasena))
    coord = cursor.fetchone()
    cursor.close()
    conexion.close()

    if coord:
        session['id_usuario'] = coord['id_usuario']
        session['nombre'] = coord['nombre_completo']
        return redirect(url_for('panel_coordinador'))

    # Si ninguna coincide, mostrar error en el login
    return render_template('index.html', error="Credenciales incorrectas. Verifica tus datos.")

@app.route('/logout')
def logout():
    """Cierra la sesión actual."""
    session.clear()
    return redirect(url_for('index'))

# --- RUTAS PROTEGIDAS ('return' obligatorio para bloquear URLs) ---

@app.route('/alumno')
def panel_alumno():
    if 'matricula' not in session:
        return redirect(url_for('index'))  # ¡Bloquea el acceso directo si no hay sesión de alumno!
    return render_template('panel_alumno.html', nombre=session.get('nombre'))

@app.route('/alumno/escanear', methods=['POST'])
def registrar_asistencia():
    """Recibe el código QR escaneado, valida la inscripción y guarda la asistencia."""
    if 'matricula' not in session:
        return jsonify({'status': 'error', 'message': 'No hay sesión activa.'}), 401
    
    matricula_alumno = session['matricula']
    datos_json = request.get_json()
    qr_data = datos_json.get('qr_data', '')
    
    # El formato que definimos al generar el QR es: UTE_CLUB_{id_club}_DATE_{hoy}
    try:
        partes = qr_data.split('_')
        id_club_qr = int(partes[2])
        fecha_qr = partes[4]
    except (IndexError, ValueError):
        return jsonify({'status': 'error', 'message': 'Código QR inválido o desconocido.'}), 400
    
    conexion = obtener_conexion()
    if not conexion:
        return jsonify({'status': 'error', 'message': 'Error de conexión con la Base de Datos.'}), 500
    
    cursor = conexion.cursor(dictionary=True, buffered=True)
    
    # 1. Validar que el alumno esté inscrito en este club
    cursor.execute("SELECT * FROM Inscripciones WHERE matricula_alumno = %s AND id_club = %s", 
                   (matricula_alumno, id_club_qr))
    inscripcion = cursor.fetchone()
    
    if not inscripcion:
        cursor.close()
        conexion.close()
        return jsonify({'status': 'error', 'message': 'No estás inscrito en este club.'}), 403
    
    # 2. Validar si ya registró asistencia el día de hoy para este club
    cursor.execute("SELECT * FROM Asistencias WHERE matricula_alumno = %s AND id_club = %s AND fecha = %s", 
                   (matricula_alumno, id_club_qr, fecha_qr))
    asistencia_previa = cursor.fetchone()
    
    if asistencia_previa:
        cursor.close()
        conexion.close()
        return jsonify({'status': 'error', 'message': 'Ya habías registrado tu asistencia el día de hoy.'}), 400
    
    # 3. Registrar la asistencia en la base de datos
    cursor.execute("INSERT INTO Asistencias (matricula_alumno, id_club, fecha) VALUES (%s, %s, %s)", 
                   (matricula_alumno, id_club_qr, fecha_qr))
    conexion.commit()
    cursor.close()
    conexion.close()
    
    return jsonify({'status': 'success', 'message': '¡Asistencia registrada correctamente!'})

@app.route('/coordinador')
def panel_coordinador():
    if 'id_usuario' not in session:
        return redirect(url_for('index'))  # ¡Bloquea el acceso directo si no hay sesión de coordinador!
    return render_template('panel_coordinador.html', nombre=session.get('nombre'))

@app.route('/coordinador/generar-qr')
def generar_qr():
    """Genera un código QR dinámico para el club que coordina el usuario actual."""
    if 'id_usuario' not in session:
        return redirect(url_for('index'))
    
    id_usuario = session['id_usuario']
    
    conexion = obtener_conexion()
    if not conexion:
        return render_template('panel_coordinador.html', nombre=session.get('nombre'), error="Error de base de datos.")
    
    # Se agrega buffered=True para evitar el error "Unread result found"
    cursor = conexion.cursor(dictionary=True, buffered=True)
    cursor.execute("SELECT id_club, nombre_club FROM Clubs WHERE id_coordinador = %s", (id_usuario,))
    club = cursor.fetchone()
    cursor.close()
    conexion.close()
    
    if not club:
        return render_template('panel_coordinador.html', nombre=session.get('nombre'), error="No tienes ningún club asignado en el sistema.")
    
    hoy = date.today().isoformat()
    contenido_qr = f"UTE_CLUB_{club['id_club']}_DATE_{hoy}"
    
    img = qrcode.make(contenido_qr)
    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    qr_base64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
    
    return render_template('generar_qr.html', club=club, qr_base64=qr_base64, fecha=hoy)

@app.route('/coordinador/subir-excel', methods=['GET', 'POST'])
def vista_subir_excel():
    if 'id_usuario' not in session:
        return redirect(url_for('index'))  # ¡Bloquea el acceso directo!
    
    # Si entra por GET, muestra la vista
    if request.method == 'GET':
        return render_template('subir_excel.html')
    
    # Si entra por POST, procesa el archivo Excel 
    archivo = request.files.get('archivo_excel')
    if not archivo or archivo.filename == '':
        return render_template('subir_excel.html', mensaje=" No se seleccionó ningún archivo.")
    
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
    app.run(host='0.0.0.0', port=5000, debug=True)