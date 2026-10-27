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
from flask import send_file
import json
from datetime import date
import os

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

@app.route('/cambiar-contrasena', methods=['GET', 'POST'])
def cambiar_contrasena():
    if 'id_usuario' not in session and 'matricula' not in session:
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        nueva_pass = request.form.get('nueva_password')
        conexion = obtener_conexion()
        if conexion:
            cursor = conexion.cursor()
            if 'id_usuario' in session:
                # Es coordinador (tabla Usuarios)
                cursor.execute("UPDATE Usuarios SET contrasena = %s WHERE id_usuario = %s", (nueva_pass, session['id_usuario']))
            else:
                # Es alumno (tabla Alumnos)
                cursor.execute("UPDATE Alumnos SET contrasena = %s WHERE matricula = %s", (nueva_pass, session['matricula']))
            conexion.commit()
            cursor.close()
            conexion.close()
            return redirect(url_for('panel_coordinador') if 'id_usuario' in session else url_for('panel_alumno'))
            
    return render_template('cambiar_contrasena.html')

@app.route('/alumno')
def panel_alumno():
    if 'matricula' not in session:
        return redirect(url_for('index'))
    
    matricula_alumno = session['matricula']
    conexion = obtener_conexion()
    if not conexion:
        return "Error de base de datos", 500
        
    cursor = conexion.cursor(dictionary=True, buffered=True)
    
    # Obtener nombre y carrera del alumno
    cursor.execute("SELECT nombre_completo, carrera FROM Alumnos WHERE matricula = %s", (matricula_alumno,))
    alumno = cursor.fetchone()
    
    # Obtener el club y sus múltiples horarios usando la tabla 'horarios'
    cursor.execute("""
        SELECT c.nombre_club, h.dia_semana, h.hora_inicio, h.hora_fin, h.lugar 
        FROM Inscripciones i 
        JOIN Clubs c ON i.id_club = c.id_club 
        LEFT JOIN horarios h ON c.id_club = h.id_club 
        WHERE i.matricula_alumno = %s
    """, (matricula_alumno,))
    horarios_club = cursor.fetchall()
    
    cursor.close()
    conexion.close()
    
    nombre = alumno['nombre_completo'] if alumno else "Alumno"
    carrera = alumno['carrera'] if alumno and alumno['carrera'] else "No especificada"
    
    return render_template('panel_alumno.html', nombre=nombre, carrera=carrera, horarios_club=horarios_club)

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
    cursor.execute("SELECT * FROM Asistencias WHERE matricula_alumno = %s AND id_club = %s AND DATE(fecha_hora) = %s", 
               (matricula_alumno, id_club_qr, fecha_qr))
    asistencia_previa = cursor.fetchone()
    
    if asistencia_previa:
        cursor.close()
        conexion.close()
        return jsonify({'status': 'error', 'message': 'Ya habías registrado tu asistencia el día de hoy.'}), 400
    
    # 3. Registrar la asistencia en la base de datos
    cursor.execute("INSERT INTO Asistencias (matricula_alumno, id_club, fecha_hora) VALUES (%s, %s, NOW())", 
               (matricula_alumno, id_club_qr))
    conexion.commit()
    cursor.close()
    conexion.close()
    
    return jsonify({'status': 'success', 'message': '¡Asistencia registrada correctamente!'})

@app.route('/coordinador')
def panel_coordinador():
    if 'id_usuario' not in session:
        return redirect(url_for('index'))  # ¡Bloquea el acceso directo si no hay sesión de coordinador!
    return render_template('panel_coordinador.html', nombre=session.get('nombre'))

@app.route('/coordinador/asistencias')
def ver_asistencias():
    """Muestra la lista de alumnos del club y su estatus de asistencia según la fecha seleccionada."""
    if 'id_usuario' not in session:
        return redirect(url_for('index'))
    
    id_usuario = session['id_usuario']
    conexion = obtener_conexion()
    if not conexion:
        return render_template('panel_coordinador.html', error="Error de base de datos.")
    
    cursor = conexion.cursor(dictionary=True, buffered=True)
    cursor.execute("SELECT id_club, nombre_club FROM Clubs WHERE id_coordinador = %s", (id_usuario,))
    club = cursor.fetchone()
    
    if not club:
        cursor.close()
        conexion.close()
        return render_template('panel_coordinador.html', error="No tienes ningún club asignado.")
    
    id_club = club['id_club']
    
    # Extraemos las fechas únicas usando DATE() de fecha_hora para el historial tipo calendario
    cursor.execute("SELECT DISTINCT DATE(fecha_hora) AS fecha FROM Asistencias WHERE id_club = %s ORDER BY fecha DESC", (id_club,))
    fechas_registradas = [str(row['fecha']) for row in cursor.fetchall() if row['fecha']]
    
    fecha_seleccionada = request.args.get('fecha', date.today().isoformat())
    
    # Obtener la lista completa de alumnos inscritos
    cursor.execute("""
        SELECT a.matricula, a.nombre_completo AS nombre, a.carrera 
        FROM Alumnos a 
        JOIN Inscripciones i ON a.matricula = i.matricula_alumno 
        WHERE i.id_club = %s
    """, (id_club,))
    alumnos = cursor.fetchall()
    
    cursor.execute("SELECT matricula_alumno FROM Asistencias WHERE id_club = %s AND DATE(fecha_hora) = %s", (id_club, fecha_seleccionada))
    asistencias_dia = {row['matricula_alumno'] for row in cursor.fetchall()}
    
    cursor.close()
    conexion.close()
    
    lista_asistencia = []
    for alumno in alumnos:
        asistio = alumno['matricula'] in asistencias_dia
        lista_asistencia.append({
            'matricula': alumno['matricula'],
            'nombre': alumno['nombre'],
            'carrera': alumno['carrera'], 
            'asistio': asistio
        })
        
    return render_template('asistencias_club.html', 
                           club=club, 
                           lista_asistencia=lista_asistencia, 
                           fechas=fechas_registradas, 
                           fecha_seleccionada=fecha_seleccionada)


@app.route('/coordinador/exportar-excel/<fecha>')
def exportar_excel(fecha):
    """Genera y descarga un archivo de Excel con el reporte de asistencia de una fecha específica."""
    if 'id_usuario' not in session:
        return redirect(url_for('index'))
    
    id_usuario = session['id_usuario']
    conexion = obtener_conexion()
    if not conexion:
        return "Error de base de datos", 500
        
    cursor = conexion.cursor(dictionary=True, buffered=True)
    cursor.execute("SELECT id_club, nombre_club FROM Clubs WHERE id_coordinador = %s", (id_usuario,))
    club = cursor.fetchone()
    
    if not club:
        cursor.close()
        conexion.close()
        return "Club no encontrado", 404
        
    id_club = club['id_club']
    
    # Consulta corregida utilizando nombre_completo
    cursor.execute("""
        SELECT a.matricula, a.nombre_completo AS nombre, a.carrera 
        FROM Alumnos a 
        JOIN Inscripciones i ON a.matricula = i.matricula_alumno 
        WHERE i.id_club = %s
    """, (id_club,))
    alumnos = cursor.fetchall()
    
    cursor.execute("SELECT matricula_alumno FROM Asistencias WHERE id_club = %s AND DATE(fecha_hora) = %s", (id_club, fecha))
    asistencias_dia = {row['matricula_alumno'] for row in cursor.fetchall()}
    
    cursor.close()
    conexion.close()
    
    datos_excel = []
    for alumno in alumnos:
        estado = "Asistió" if alumno['matricula'] in asistencias_dia else "Faltó"
        datos_excel.append({
            'Matrícula': alumno['matricula'],
            'Nombre del Alumno': alumno['nombre'],
            'Carrera': alumno['carrera'], 
            'Fecha de Sesión': fecha,
            'Asistencia': estado
        })
        
    df = pd.DataFrame(datos_excel)
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Reporte Asistencia')
    output.seek(0)
    
    nombre_archivo = f"Asistencia_{club['nombre_club'].replace(' ', '_')}_{fecha}.xlsx"
    
    return send_file(output, 
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                     as_attachment=True, 
                     download_name=nombre_archivo)

@app.route('/coordinador/inscribir-alumno', methods=['POST'])
def inscribir_alumno():
    if 'id_usuario' not in session:
        return redirect(url_for('index'))
    
    matricula = request.form.get('matricula').strip()
    nombre = request.form.get('nombre').strip()
    carrera = request.form.get('carrera').strip() # <-- Nuevo campo
    
    id_usuario = session['id_usuario']
    conexion = obtener_conexion()
    if not conexion:
        return redirect(url_for('ver_asistencias'))
        
    cursor = conexion.cursor(dictionary=True, buffered=True)
    cursor.execute("SELECT id_club FROM Clubs WHERE id_coordinador = %s", (id_usuario,))
    club = cursor.fetchone()
    
    if not club:
        cursor.close()
        conexion.close()
        return redirect(url_for('ver_asistencias'))
        
    id_club = club['id_club']
    
    # Verificar si el alumno ya existe
    cursor.execute("SELECT * FROM Alumnos WHERE matricula = %s", (matricula,))
    alumno = cursor.fetchone()
    
    if not alumno:
        # Si no existe, lo creamos con su carrera
        cursor.execute("INSERT INTO Alumnos (matricula, nombre_completo, carrera, contrasena) VALUES (%s, %s, %s, %s)",
                       (matricula, nombre, carrera, matricula))
    else:
        # Si ya existe, actualizamos su nombre y carrera por si acaso cambiaron
        cursor.execute("UPDATE Alumnos SET nombre_completo = %s, carrera = %s WHERE matricula = %s",
                       (nombre, carrera, matricula))
        
    conexion.commit()
    
    # Gestionar inscripción al club
    cursor.execute("SELECT * FROM Inscripciones WHERE matricula_alumno = %s", (matricula,))
    inscripcion_previa = cursor.fetchone()
    
    if inscripcion_previa:
        cursor.execute("UPDATE Inscripciones SET id_club = %s WHERE matricula_alumno = %s", (id_club, matricula))
    else:
        cursor.execute("INSERT INTO Inscripciones (matricula_alumno, id_club) VALUES (%s, %s)", (matricula, id_club))
        
    conexion.commit()
    cursor.close()
    conexion.close()
    
    return redirect(url_for('ver_asistencias'))

@app.route('/coordinador/baja-alumno/<matricula>')
def baja_alumno(matricula):
    """Da de baja a un alumno del club del coordinador actual eliminando su inscripción."""
    if 'id_usuario' not in session:
        return redirect(url_for('index'))
    
    id_usuario = session['id_usuario']
    conexion = obtener_conexion()
    if not conexion:
        return "Error de base de datos", 500
        
    cursor = conexion.cursor(dictionary=True, buffered=True)
    
    # Obtener el club que administra este coordinador
    cursor.execute("SELECT id_club FROM Clubs WHERE id_coordinador = %s", (id_usuario,))
    club = cursor.fetchone()
    
    if club:
        id_club = club['id_club']
        # Eliminar únicamente la inscripción (el alumno sigue existiendo en la tabla Alumnos)
        cursor.execute("DELETE FROM Inscripciones WHERE matricula_alumno = %s AND id_club = %s", (matricula, id_club))
        conexion.commit()
        
    cursor.close()
    conexion.close()
    
    return redirect(url_for('ver_asistencias'))

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

@app.route('/coordinador/reiniciar-ciclo', methods=['POST'])
def reiniciar_ciclo():
    if 'id_usuario' not in session:
        return redirect(url_for('index'))
    
    #  LEER LA FECHA DE INICIO DESDE EL ARCHIVO DE CONFIGURACIÓN
    if os.path.exists('config_cuatri.json'):
        with open('config_cuatri.json', 'r') as f:
            config = json.load(f)
            fecha_str = config.get("fecha_inicio_cuatri")
            fecha_inicio_cuatri = date.fromisoformat(fecha_str)
    else:
        # Valor de respaldo por si acaso no se ha importado ningún Excel todavía
        fecha_inicio_cuatri = date.today()
    
    # Calcular días transcurridos desde que se importó el Excel
    dias_transcurridos = (date.today() - fecha_inicio_cuatri).days
    
    # Bloqueo de seguridad si no han pasado al menos 100 días
    if dias_transcurridos < 100:
        return f"""
            <script>
                alert(' Acción bloqueada: El cuatrimestre inició el {fecha_inicio_cuatri} y apenas han pasado {dias_transcurridos} días. El botón se habilitará al cumplirse los 100 días.');
                window.history.back();
            </script>
        """
    
    conexion = obtener_conexion()
    if not conexion:
        return "Error de base de datos", 500
        
    cursor = conexion.cursor()
    try:
        # Limpiar inscripciones protegiendo alumnos y asistencias históricas
        cursor.execute("DELETE FROM Inscripciones")
        conexion.commit()
    except Exception as e:
        conexion.rollback()
    finally:
        cursor.close()
        conexion.close()
        
    return """
        <script>
            alert(' ¡Ciclo cuatrimestral finalizado con éxito! Las inscripciones se han reiniciado.');
            window.location.href = '/coordinador/asistencias';
        </script>
    """

@app.route('/coordinador/subir-excel', methods=['GET', 'POST'])
def vista_subir_excel():

    config_data = {
        "fecha_inicio_cuatri": date.today().isoformat() # Guarda la fecha de hoy (Ej: "2026-10-26")
    }
    
    with open('config_cuatri.json', 'w') as f:
        json.dump(config_data, f)

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