import os
import psycopg2
import sqlite3
import time
import threading
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import date, datetime, timedelta
from werkzeug.utils import secure_filename
from twilio.rest import Client
from zoneinfo import ZoneInfo

# --- zona horaria: America/Bogota
tz = ZoneInfo("America/Bogota")
ahora = datetime.now(tz)

ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP = os.getenv("TWILIO_WHATSAPP_NUMBER")

# 📂 Asegurar carpeta de imágenes
UPLOAD_FOLDER = os.path.join("static", "img_peluqueros")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app = Flask(__name__)
app.secret_key = "clave-secreta"

# ---------- CONFIG BD ----------
USE_POSTGRES = os.getenv("USE_POSTGRES", "False").lower() == "true"

if USE_POSTGRES:
    DB_NAME = os.getenv("POSTGRES_DB", "barberia")
    DB_USER = os.getenv("POSTGRES_USER", "postgres")
    DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")
    DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
    DB_PORT = os.getenv("POSTGRES_PORT", "5432")
else:
    DB_NAME = "barberia.db"

def get_conn():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise Exception("❌ No se encontró la variable DATABASE_URL")
    return psycopg2.connect(database_url)

def fecha_desde_dia(dia_semana, semana_offset=0):
    """
    dia_semana: 'lunes', 'martes', ..., 'domingo'
    semana_offset: 0 = esta semana, 1 = próxima semana
    """

    dias = {
        "lunes": 0,
        "martes": 1,
        "miercoles": 2,
        "jueves": 3,
        "viernes": 4,
        "sabado": 5,
        "domingo": 6
    }

    hoy = date.today()

    # lunes de la semana actual (SIEMPRE)
    inicio_semana = hoy - timedelta(days=hoy.weekday())

    # mover a la semana deseada
    inicio_semana += timedelta(weeks=semana_offset)

    return inicio_semana + timedelta(days=dias[dia_semana])

def adapt_query(query: str) -> str:
    return query.replace("?", "%s") if USE_POSTGRES else query

# ---------- INIT SCHEMA ----------
def init_schema():
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS peluqueros (
            id SERIAL PRIMARY KEY,
            nombre TEXT NOT NULL,
            usuario TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            foto TEXT,
            es_admin BOOLEAN DEFAULT 0
        );

    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS horarios (
            id SERIAL PRIMARY KEY,
            peluquero_id INTEGER NOT NULL REFERENCES peluqueros(id) ON DELETE CASCADE,
            dia TEXT NOT NULL,
            hora TEXT NOT NULL
        );
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS citas (
            id SERIAL PRIMARY KEY,
            peluquero_id INTEGER NOT NULL REFERENCES peluqueros(id) ON DELETE CASCADE,
            dia TEXT NOT NULL,
            hora TEXT NOT NULL,
            nombre TEXT NOT NULL,
            telefono TEXT NOT NULL
        );
    """)
    conn.commit()
    conn.close()



# ---------- FUNCIONES ----------

def enviar_notificacion_whatsapp(destinatario, mensaje):
    client = Client(ACCOUNT_SID, AUTH_TOKEN)
    try:
        client.messages.create(
            from_=TWILIO_WHATSAPP,
            to=f"whatsapp:{destinatario}",  # Ejemplo: whatsapp:+573001234567
            body=mensaje
        )
        print(f"✅ WhatsApp enviado a {destinatario}")
    except Exception as e:
        print(f"⚠️ Error enviando WhatsApp: {e}")
        
def cargar_horarios_40_minutos(peluquero_id):
    if not peluquero_id:
        return

    conn = get_conn()
    c = conn.cursor()
    try:
        
        dias = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]
        hora_actual = datetime.strptime("10:00", "%H:%M")
        fin = datetime.strptime("21:00", "%H:%M")

        for dia in dias:
            actual = hora_actual
            while actual <= fin:
                hora = actual.strftime("%I:%M %p")
                c.execute(adapt_query(
                    "SELECT 1 FROM horarios WHERE peluquero_id=%s AND dia=%s AND hora=%s"
                ), (peluquero_id, dia, hora))
                existe = c.fetchone()
                if not existe:
                    c.execute(adapt_query(
                        "INSERT INTO horarios (peluquero_id, dia, hora) VALUES (%s, %s, %s)"
                    ), (peluquero_id, dia, hora))
                actual += timedelta(minutes=40)

        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"❌ Error al cargar horarios para peluquero_id {peluquero_id}: {e}")
    finally:
        conn.close()

def init_db_legacy():
    conn = get_conn()
    c = conn.cursor()
    c.execute(adapt_query("SELECT COUNT(*) FROM peluqueros"))
    if c.fetchone()[0] == 0:
        # Admin
        c.execute(adapt_query(
            "INSERT INTO peluqueros (nombre, usuario, password, foto, es_admin) VALUES (%s, %s, %s, %s, %s)"
        ), ("Admin", "admin", generate_password_hash("admin123"), "/static/logo.png", 1))

        # Barberos de prueba
        c.execute(adapt_query(
            "INSERT INTO peluqueros (nombre, usuario, password, foto, es_admin) VALUES (%s, %s, %s, %s, %s)"
        ), ("Camilo", "camilo", generate_password_hash("1234"), "/static/camilo.png", 0))

        c.execute(adapt_query(
            "INSERT INTO peluqueros (nombre, usuario, password, foto, es_admin) VALUES (%s, %s, %s, %s, %s)"
        ), ("Luis", "luis", generate_password_hash("1234"), "/static/luis.png", 0))

        c.execute(adapt_query(
            "INSERT INTO peluqueros (nombre, usuario, password, foto, es_admin) VALUES (%s, %s, %s, %s, %s)"
        ), ("Manuel", "manuel", generate_password_hash("1234"), "/static/manuel.png", 0))

        c.execute(adapt_query(
            "INSERT INTO peluqueros (nombre, usuario, password, foto, es_admin) VALUES (%s, %s, %s, %s, %s)"
        ), ("Juan", "juan", generate_password_hash("1234"), "/static/juan.png", 0))

        conn.commit()
    conn.close()

with app.app_context():
    init_schema()
    init_db_legacy()
# ---------- RUTAS ----------
@app.route("/debug_peluqueros")
def debug_peluqueros():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, nombre, usuario, foto, es_admin FROM peluqueros")
    data = c.fetchall()
    conn.close()
    return {"peluqueros": data}

@app.route("/")
def index():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, nombre, foto FROM peluqueros WHERE es_admin=0 ORDER BY nombre ASC")
    peluqueros = c.fetchall()
    conn.close()
    return render_template("index.html", peluqueros=peluqueros)

# ==============================
# ✍️ Agendar cita (CLIENTE)
# ==============================
@app.route('/agendar', methods=['POST'])
def agendar():
    peluquero_id = request.form.get("peluquero_id")
    dia = request.form.get("dia")
    hora = request.form.get("hora")
    nombre = request.form.get("nombre")
    telefono = request.form.get("telefono")

    # ⬇️ semana_offset viene del frontend (0 o 1)
    semana_offset = int(request.form.get("semana_offset", 0))
    
    # 🔹 Calcular fecha real
    fecha_cita = fecha_desde_dia(dia, semana_offset)

    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT nombre FROM peluqueros WHERE id = %s", (peluquero_id,))
    row = c.fetchone()
    nombre_peluquero = row[0] if row else "desconocido"

    if not (peluquero_id and dia and hora and nombre and telefono):
        return "Faltan datos para agendar la cita", 400

    conn = get_conn()
    c = conn.cursor()

    # Verificar que sigue disponible
    c.execute("""
        SELECT COUNT(*)
        FROM citas
        WHERE peluquero_id=%s AND fecha=%s AND hora=%s
    """, (peluquero_id, fecha_cita, hora))
    if c.fetchone()[0] > 0:
        conn.close()
        return "Lo sentimos, ese horario ya fue tomado", 400

    # Guardar la cita
    c.execute(
        """
        INSERT INTO citas (peluquero_id, dia, hora, fecha, nombre, telefono)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (peluquero_id, dia, hora, fecha_cita, nombre, telefono)
    )
    conn.commit()
    conn.close()

     # ==============================
    # ✅ Enviar notificación WhatsApp
    # ==============================
    try:
        account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        from_whatsapp = os.getenv("TWILIO_WHATSAPP_NUMBER")

        client = Client(account_sid, auth_token)

        # 🔹 Obtener el número del barbero
        conn_p = get_conn()
        c_p = conn_p.cursor()
        c_p.execute("SELECT telefono FROM peluqueros WHERE id=%s", (peluquero_id,))
        result = c_p.fetchone()
        conn_p.close()

        if result and result[0]:
            telefono_barbero = result[0]
            to_number = f"whatsapp:{telefono_barbero}"

            mensaje = (
                f"💈 *Nueva cita agendada*\n\n"
                f"👤 Cliente: {nombre}\n"
                f"🗓 Día: {dia}\n"
                f"🕒 Hora: {hora}\n\n"
                f"Por favor revisa tu calendario desde el panel de administración."
            )

            msg = client.messages.create(
                from_=from_whatsapp,
                to=to_number,
                body=mensaje
            )
            print(f"✅ WhatsApp enviado con SID: {msg.sid}")

        else:
            print(f"⚠️ Peluquero {peluquero_id} sin número registrado.")

    except Exception as e:
        print(f"❌ Error enviando WhatsApp: {e}")

    return {"success": True,
            "message": (
                f"Tu cita fue agendada con exito el {dia} a las {hora} con {nombre_peluquero} \n"
                f"Te esperamos \n"
                f"Si deseas cancelar tu cita debes comunicarte con nosotros vía whatsapp"
            )
           }


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        usuario = (request.form.get('usuario') or '').strip()
        password = request.form.get('password') or ''

        if not usuario or not password:
            # si usas flash, puedes cambiar este return por un render con mensaje
            return "Faltan usuario o contraseña", 400

        conn = get_conn()
        c = conn.cursor()
        # Busca por usuario o por nombre (como venías usando)
        c.execute(
            adapt_query("SELECT id, nombre, usuario, password, es_admin FROM peluqueros WHERE usuario=%s OR nombre=%s"),
            (usuario, usuario)
        )
        row = c.fetchone()
        conn.close()

        if row:
            peluquero_id, nombre, usuario_db, stored_password, es_admin = row

            # Valida tanto hash como texto plano
            valido = False
            try:
                # Si stored_password es hash válido, esto devolverá True/False
                valido = check_password_hash(stored_password, password)
            except Exception:
                # Si no es un hash, caemos al plano
                valido = (stored_password == password)

            # También acepta el caso en que check_password_hash() devuelva False pero esté en plano
            if not valido and stored_password == password:
                valido = True

            if valido:
                session.clear()
                session['peluquero_id'] = peluquero_id
                session['usuario'] = usuario_db
                session['nombre'] = nombre
                session['es_admin'] = bool(es_admin)

                if session['es_admin']:
                    return redirect(url_for('admin_panel'))
                else:
                    return redirect(url_for('ver_calendario', peluquero_id=peluquero_id))

        # Si llegó aquí: credenciales incorrectas
        return "Usuario o contraseña incorrectos", 401

    # GET
    # Nota: si tu archivo se llama 'login.HTML' en Windows funciona, pero en Linux (deploy) es sensible a mayúsculas.
    # Renómbralo a 'login.html' para evitar errores en producción.
    return render_template('login.html')

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route('/cliente/<int:peluquero_id>/calendario')
def calendario_cliente(peluquero_id):
    conn = get_conn()
    c = conn.cursor()
    semana = int(request.args.get("semana", 0))

    # Nombre del peluquero
    c.execute("SELECT nombre FROM peluqueros WHERE id=%s", (peluquero_id,))
    row = c.fetchone()
    nombre_peluquero = row[0] if row else "Desconocido"

    ahora = datetime.now(tz)

    # inicio de la semana: lunes de la semana actual (independiente del día actual)
    # .weekday(): 0 = lunes ... 6 = domingo
    inicio_semana = (ahora - timedelta(days=ahora.weekday())) + timedelta(weeks=semana)
    inicio_semana = inicio_semana.replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    
    fin_semana = inicio_semana + timedelta(days=6)


    dias = ['lunes', 'martes', 'miercoles', 'jueves', 'viernes', 'sabado', 'domingo']


    dias_con_fechas = {
        d: (inicio_semana + timedelta(days=i)).strftime("%d %b %Y")  # "27", "28", etc.
        for i, d in enumerate(dias)
    }

    semana_offset = int(request.args.get("semana", 0))

    # Horas realmente existentes
    c.execute("""
        SELECT DISTINCT hora FROM horarios WHERE peluquero_id=%s
        UNION
        SELECT DISTINCT hora FROM citas WHERE peluquero_id=%s
    """, (peluquero_id, peluquero_id))
    horas = sorted({h for (h,) in c.fetchall()}, key=lambda h: datetime.strptime(h, "%I:%M %p"))
    
    # Disponibles = solo los NO bloqueados
    c.execute("""
        SELECT dia, hora
        FROM horarios
        WHERE peluquero_id=%s AND bloqueado = FALSE
    """, (peluquero_id,))
    disponibles = {(d, h) for d, h in c.fetchall()}
    
    # Ocupados (citas)
    c.execute("""
        SELECT dia, hora, nombre
        FROM citas
        WHERE peluquero_id=%s AND fecha BETWEEN %s AND %s
    """, (peluquero_id, inicio_semana, fin_semana))
    ocupados = {(d, h): n for d, h, n in c.fetchall()}
    
    # 🔹 Bloqueados = los que están marcados como bloqueados
    c.execute("""
        SELECT dia, hora
        FROM horarios
        WHERE peluquero_id=%s AND bloqueado = TRUE
    """, (peluquero_id,))
    bloqueados = {(d, h) for d, h in c.fetchall()}

    return render_template(
        "cliente_calendario.html",
        semana=semana,
        inicio_semana=inicio_semana,
        fin_semana=fin_semana,
        peluquero_id=peluquero_id,
        nombre_peluquero=nombre_peluquero,
        dias=dias,
        dias_con_fechas=dias_con_fechas,
        horas=horas,
        disponibles=disponibles,
        ocupados=ocupados,
        bloqueados=bloqueados,
        semana_offset=semana_offset
    )

@app.route("/admin")
def admin_panel():
    if "peluquero_id" not in session or not session.get("es_admin"):
        return redirect(url_for("login"))

    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, nombre, usuario, foto FROM peluqueros WHERE es_admin=0")
    peluqueros = c.fetchall()
    conn.close()

    return render_template("admin.html", peluqueros=peluqueros)

# ==============================
# 📌 Panel de gestión de peluqueros (SOLO admin)
# ==============================
@app.route("/admin/peluqueros", methods=["GET", "POST"])
def admin_peluqueros():
    if "es_admin" not in session or not session["es_admin"]:
        return redirect(url_for("login"))

    conn = get_conn()
    c = conn.cursor()

    if request.method == "POST":
        accion = request.form.get("accion")

        # ➕ Crear peluquero
        if accion == "crear":
            nombre = request.form["nombre"]
            usuario = request.form["usuario"]
            password = request.form["password"]
            foto = request.form["foto"]
            ruta_db = f"/static/img_peluqueros/{foto}"
            c.execute(
                "UPDATE peluqueros SET foto=%s WHERE id=%s",
                (ruta_db, id)
            )
            c.execute(adapt_query(
                "INSERT INTO peluqueros (nombre, usuario, password, foto, es_admin) VALUES (%s, %s, %s, %s, %s)"
            ), (nombre, usuario, password, foto, 0))

        # ✏️ Editar peluquero
        elif accion == "editar":
            peluquero_id = request.form["id"]
            nombre = request.form["nombre"]
            usuario = request.form["usuario"]
            foto = request.form["foto"]
            ruta_db = f"/static/img_peluqueros/{foto}"
            c.execute(
                "UPDATE peluqueros SET foto=%s WHERE id=%s",
                (ruta_db, id)
            )
            c.execute(adapt_query(
                "UPDATE peluqueros SET nombre=%s, usuario=%s, foto=%s WHERE id=%s"
            ), (nombre, usuario, foto, peluquero_id))

        # 🔑 Cambiar contraseña
        elif accion == "password":
            peluquero_id = request.form["id"]
            password = request.form["password"]
            c.execute(adapt_query(
                "UPDATE peluqueros SET password=%s WHERE id=%s"
            ), (password, peluquero_id))

        # 🗑️ Eliminar peluquero
        elif accion == "eliminar":
            peluquero_id = request.form["id"]
            c.execute(adapt_query("DELETE FROM peluqueros WHERE id=%s"), (peluquero_id,))

        conn.commit()

    # 📋 Listado de peluqueros
    c.execute("SELECT id, nombre, es_admin, foto FROM peluqueros")
    peluqueros = c.fetchall()
    conn.close()

    return render_template("admin_peluqueros.html", peluqueros=peluqueros)

# 📌 Ruta para agregar un nuevo peluquero
@app.route("/admin/peluqueros/agregar", methods=["POST"])
def agregar_peluquero():
    if 'peluquero_id' not in session or not session.get('es_admin'):
        return redirect(url_for('login'))

    nombre   = request.form.get("nombre")
    usuario  = request.form.get("usuario")
    password = request.form.get("password")
    telefono = request.form.get("telefono")
    es_admin = 1 if request.form.get("es_admin") else 0
    foto     = None

    if 'foto' in request.files:
        file = request.files['foto']
        if file and file.filename != "":
            filename = secure_filename(file.filename)
            file.save(os.path.join("static/img_peluqueros", filename))
            foto = f"/static/img_peluqueros/{filename}"

    conn = get_conn()
    c = conn.cursor()

    # ➤ Insertar peluquero
    c.execute("""
        INSERT INTO peluqueros (nombre, usuario, password, es_admin, foto, telefono)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
    """, (nombre, usuario, password, es_admin, foto, telefono))
    nuevo_id = c.fetchone()[0]

    # ➤ Solo si NO es admin: crear horarios base 10:00–21:00 cada 40 min
    if not es_admin:
        dias = ['lunes','martes','miercoles','jueves','viernes','sabado','domingo']
        hora_actual = datetime.strptime("10:00", "%H:%M")
        fin = datetime.strptime("21:00", "%H:%M")

        while hora_actual <= fin:
            hora_str = hora_actual.strftime("%I:%M %p")
            for d in dias:
                c.execute(
                    "INSERT INTO horarios (peluquero_id, dia, hora) VALUES (%s, %s, %s)",
                    (nuevo_id, d, hora_str)
                )
            hora_actual += timedelta(minutes=40)

    conn.commit()
    conn.close()

    return redirect(url_for('admin_peluqueros'))


# 📌 Ruta para editar un peluquero existente
@app.route("/admin/peluqueros/<int:id>/editar", methods=["POST"])
def editar_peluquero(id):
    if 'peluquero_id' not in session or not session.get('es_admin'):
        return redirect(url_for('login'))

    nombre = request.form.get("nombre")
    usuario = request.form.get("usuario")
    password = request.form.get("password")
    es_admin = 1 if request.form.get("es_admin") else 0

    conn = get_conn()
    c = conn.cursor()

    # ✅ 1. Obtener la foto actual de la base
    c.execute("SELECT foto, telefono FROM peluqueros WHERE id=%s", (id,))
    foto_actual, telefono_actual = c.fetchone()

    # ✅ 2. Solo reemplazar si se subió una nueva
    foto_path = foto_actual
    if 'foto' in request.files:
        file = request.files['foto']
        if file and file.filename != "":
            from werkzeug.utils import secure_filename
            filename = secure_filename(file.filename)
            file.save(os.path.join("static/img_peluqueros", filename))
            foto_path = f"/static/img_peluqueros/{filename}"

    # Si el formulario no envía teléfono, usar el existente
    telefono_nuevo = request.form.get("telefono")
    if not telefono_nuevo:
        telefono_nuevo = telefono_actual

    # ✅ 3. Actualizar
    if password:  # si cambia contraseña
        c.execute("""
            UPDATE peluqueros
            SET nombre=%s, usuario=%s, password=%s, es_admin=%s, foto=%s, telefono=%s
            WHERE id=%s
        """, (nombre, usuario, password, es_admin, foto_path, telefono_nuevo, id))
    else:
        c.execute("""
            UPDATE peluqueros
            SET nombre=%s, usuario=%s, es_admin=%s, foto=%s, telefono=%s
            WHERE id=%s
        """, (nombre, usuario, es_admin, foto_path, telefono_nuevo, id))

    conn.commit()
    conn.close()
    return redirect(url_for('admin_peluqueros'))


# 📌 Ruta para eliminar un peluquero
@app.route("/admin/peluqueros/<int:id>/eliminar", methods=["GET"])
def eliminar_peluquero(id):
    if 'peluquero_id' not in session or not session.get('es_admin'):
        return redirect(url_for('login'))

    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM peluqueros WHERE id=%s", (id,))
    conn.commit()
    conn.close()

    return redirect(url_for('admin_peluqueros'))


# 📅 Calendario visto desde el ADMIN (puede bloquear y desbloquear horarios)
@app.route("/admin/peluquero/<int:peluquero_id>/calendario")
def ver_calendario_admin(peluquero_id):
    if 'peluquero_id' not in session or not session.get('es_admin'):
        return redirect(url_for('login'))

    from datetime import datetime
    conn = get_conn()
    c = conn.cursor()

    semana = int(request.args.get("semana", 0))  # 0 = actual, 1 = siguiente
    semana_offset = int(request.args.get("semana", 0))

    # ✅ Cancelar cita (solo admin)
    cancelar_dia = request.args.get('cancelar_dia')
    cancelar_hora = request.args.get('cancelar_hora')
    if cancelar_dia and cancelar_hora:
        c.execute("DELETE FROM citas WHERE peluquero_id=%s AND dia=%s AND hora=%s",
                  (peluquero_id, cancelar_dia, cancelar_hora))
        conn.commit()

       # ✅ Bloquear horario (marcar como bloqueado)
    bloquear_dia = request.args.get('bloquear_dia')
    bloquear_hora = request.args.get('bloquear_hora')
    
    
    if bloquear_dia and bloquear_hora:
        fecha = fecha_desde_dia(bloquear_dia, semana_offset)
        c.execute("""
            INSERT INTO horarios (peluquero_id, dia, hora, fecha, bloqueado)
            VALUES (%s, %s, %s, %s, TRUE)
            ON CONFLICT (peluquero_id, dia, hora, fecha)
            DO UPDATE SET bloqueado = TRUE
        """, (peluquero_id, bloquear_dia, bloquear_hora, fecha))
        conn.commit()
    
    # ✅ Reactivar horario (quitar el bloqueo)
    activar_dia = request.args.get("activar_dia") or request.args.get("reactivar_dia")
    activar_hora = request.args.get("activar_hora") or request.args.get("reactivar_hora")
    
    if activar_dia and activar_hora:
        fecha = fecha_desde_dia(reactivar_dia, semana_offset)
        c.execute("""
            UPDATE horarios
            SET bloqueado = FALSE
            WHERE peluquero_id=%s
              AND dia=%s
              AND hora=%s
              AND fecha=%s
        """, (peluquero_id, reactivar_dia, reactivar_hora, fecha))
        conn.commit()
    
    # Datos del peluquero
    c.execute("SELECT nombre FROM peluqueros WHERE id=%s", (peluquero_id,))
    peluquero = c.fetchone()
    if not peluquero:
        conn.close()
        return "Peluquero no encontrado"
    nombre = peluquero[0]

    ahora = datetime.now(tz)

    # inicio de la semana: lunes de la semana actual (independiente del día actual)
    # .weekday(): 0 = lunes ... 6 = domingo
    inicio_semana = (ahora - timedelta(days=ahora.weekday())) + timedelta(weeks=semana)
    inicio_semana = inicio_semana.replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    
    fin_semana = inicio_semana + timedelta(days=6)


    dias = ['lunes', 'martes', 'miercoles', 'jueves', 'viernes', 'sabado', 'domingo']

    dias_con_fechas = {
        d: (inicio_semana + timedelta(days=i)).strftime("%d %b %Y")  # "27", "28", etc.
        for i, d in enumerate(dias)
    }

    semana_offset = int(request.args.get("semana", 0))
    fecha = inicio_semana.date()

    # 🔹 Obtener solo las horas que realmente existan en la DB (horarios o citas)
    c.execute("""
        SELECT DISTINCT hora FROM horarios WHERE peluquero_id=%s
        UNION
        SELECT DISTINCT hora FROM citas    WHERE peluquero_id=%s
    """, (peluquero_id, peluquero_id))
    horas = sorted(
        {row[0] for row in c.fetchall()},
        key=lambda h: datetime.strptime(h, "%I:%M %p")
    )

    # Solo horarios NO bloqueados
    c.execute("""
        SELECT dia, hora
        FROM horarios
        WHERE peluquero_id=%s AND bloqueado=FALSE
    """, (peluquero_id,))
    disponibles = {(d, h) for d, h in c.fetchall()}

    # Horarios bloqueados
    fecha_inicio = inicio_semana.date()
    fecha_fin = fecha_inicio + timedelta(days=6)
    
    c.execute("""
        SELECT dia, hora
        FROM horarios
        WHERE peluquero_id=%s
          AND bloqueado=TRUE
          AND fecha BETWEEN %s AND %s
    """, (peluquero_id, fecha_inicio, fecha_fin))
    bloqueados = {(d, h) for d, h in c.fetchall()}

    # Ocupados
    c.execute("""
        SELECT id, dia, hora, nombre, telefono, fijo
        FROM citas
        WHERE peluquero_id=%s AND fecha BETWEEN %s AND %s
    """, (peluquero_id, inicio_semana, fin_semana))
    ocupados = {
        (row[1], row[2]): {
            "id": row[0],
            "nombre": row[3],
            "telefono": row[4],
            "fijo": row[5]
        }
        for row in c.fetchall()
    }

    conn.close()


    return render_template(
        "calendario.html",
        semana=semana,
        inicio_semana=inicio_semana,
        fin_semana=fin_semana,
        nombre=nombre,
        peluquero_id=peluquero_id,
        dias=dias,
        dias_con_fechas=dias_con_fechas,
        horas=horas,
        disponibles=disponibles,
        ocupados=ocupados,
        bloqueados=bloqueados,
        semana_offset=semana_offset,
        es_admin=True
    )

@app.route("/admin/peluquero/<int:peluquero_id>/bloquear_dia_completo", methods=["POST"])
def bloquear_dia_completo(peluquero_id):
    if 'peluquero_id' not in session or not session.get('es_admin'):
        return redirect(url_for('login'))

    dia = request.form.get("dia")
    if not dia:
        return "Día no especificado", 400

    conn = get_conn()
    c = conn.cursor()
    

    # ✅ Bloquear todas las horas disponibles de ese día (sin tocar las citas existentes)
    c.execute("""
        UPDATE horarios
        SET bloqueado = TRUE
        WHERE peluquero_id = %s AND dia = %s
    """, (peluquero_id, dia))

    conn.commit()
    conn.close()

    flash(f"Se han bloqueado todos los horarios del día {dia}.", "success")
    return redirect(url_for('ver_calendario_admin', peluquero_id=peluquero_id))

@app.route("/admin/<int:peluquero_id>/calendario")
def ver_calendario(peluquero_id):
    if "peluquero_id" not in session:
        return redirect(url_for("login"))

    # Permitir que admin vea cualquier calendario
    if not session.get("es_admin") and session["peluquero_id"] != peluquero_id:
        return redirect(url_for("login"))

    from datetime import datetime
    conn = get_conn()
    c = conn.cursor()

    semana = int(request.args.get("semana", 0))  # 0 = actual, 1 = siguiente

    # ✅ Cancelar cita solo si es admin
    if session.get("es_admin"):
        cancelar_dia = request.args.get("cancelar_dia")
        cancelar_hora = request.args.get("cancelar_hora")
        if cancelar_dia and cancelar_hora:
            c.execute(
                adapt_query("""
                    DELETE FROM citas
                    WHERE peluquero_id=%s AND dia=%s AND hora=%s
                """),
                (peluquero_id, cancelar_dia, cancelar_hora)
            )
            conn.commit()

    # ✅ Bloquear / Reactivar (solo admin) usando la columna 'bloqueado'
    if session.get("es_admin"):
        bloquear_dia = request.args.get("bloquear_dia")
        bloquear_hora = request.args.get("bloquear_hora")
        
        if bloquear_dia and bloquear_hora:
            fecha = fecha_desde_dia(bloquear_dia, semana_offset)
            c.execute("""
                INSERT INTO horarios (peluquero_id, dia, hora, fecha, bloqueado)
                VALUES (%s, %s, %s, %s, TRUE)
                ON CONFLICT (peluquero_id, dia, hora, fecha)
                DO UPDATE SET bloqueado = TRUE
            """, (peluquero_id, bloquear_dia, bloquear_hora, fecha))
            conn.commit()

        reactivar_dia = request.args.get('reactivar_dia')
        reactivar_hora = request.args.get('reactivar_hora')
        
        if reactivar_dia and reactivar_hora:
            fecha = fecha_desde_dia(reactivar_dia, semana_offset)
            c.execute("""
                UPDATE horarios
                SET bloqueado = FALSE
                WHERE peluquero_id=%s
                  AND dia=%s
                  AND hora=%s
                  AND fecha=%s
            """, (peluquero_id, reactivar_dia, reactivar_hora, fecha))
            conn.commit()

    # ✅ Obtener nombre del peluquero
    c.execute(adapt_query("SELECT nombre FROM peluqueros WHERE id=%s"), (peluquero_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return "Peluquero no encontrado"
    nombre = row[0]
    ahora = datetime.now(tz)

    # inicio de la semana: lunes de la semana actual (independiente del día actual)
    # .weekday(): 0 = lunes ... 6 = domingo
    inicio_semana = (ahora - timedelta(days=ahora.weekday())) + timedelta(weeks=semana)
    inicio_semana = inicio_semana.replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    
    fin_semana = inicio_semana + timedelta(days=6)



    dias = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]

    dias_con_fechas = {
        d: (inicio_semana + timedelta(days=i)).strftime("%d %b %Y")  # "27", "28", etc.
        for i, d in enumerate(dias)
    }

    semana_offset = int(request.args.get("semana", 0))
    fecha = inicio_semana.date()

    # ✅ Horas realmente existentes (en horarios o citas)
    c.execute(adapt_query("""
        SELECT DISTINCT hora FROM horarios WHERE peluquero_id=%s
        UNION
        SELECT DISTINCT hora FROM citas    WHERE peluquero_id=%s
    """), (peluquero_id, peluquero_id))
    horas = sorted(
        {h for (h,) in c.fetchall()},
        key=lambda h: datetime.strptime(h, "%I:%M %p")
    )

    # ✅ Disponibles: solo los NO bloqueados
    c.execute(adapt_query("""
        SELECT dia, hora
        FROM horarios
        WHERE peluquero_id=%s AND bloqueado = FALSE
    """), (peluquero_id,))
    disponibles = {(d, h) for d, h in c.fetchall()}

    # ✅ Ocupados
    c.execute(adapt_query("""
        SELECT dia, hora, nombre, telefono
        FROM citas
        WHERE peluquero_id=%s AND fecha BETWEEN %s AND %s
    """), (peluquero_id, inicio_semana, fin_semana))
    ocupados = {
        (d, h): {"nombre": n, "telefono": t}
        for d, h, n, t in c.fetchall()
    }

    # ✅ Bloqueados: solo los que están marcados como bloqueados
    fecha_inicio = inicio_semana.date()
    fecha_fin = fecha_inicio + timedelta(days=6)
    
    c.execute(adapt_query("""
        SELECT dia, hora
        FROM horarios
        WHERE peluquero_id=%s
          AND bloqueado=TRUE
          AND fecha BETWEEN %s AND %s
    """), (peluquero_id, fechainicio, fecha_fin))
    bloqueados = {(d, h) for d, h in c.fetchall()}

    conn.close()

    return render_template(
        "calendario.html",
        semana=semana,
        inicio_semana=inicio_semana,
        fin_semana=fin_semana,
        nombre=nombre,
        peluquero_id=peluquero_id,
        dias=dias,
        dias_con_fechas=dias_con_fechas,
        horas=horas,
        disponibles=disponibles,
        ocupados=ocupados,
        bloqueados=bloqueados,
        semana_offset=semana_offset,
        es_admin=session.get("es_admin", False)
    )

@app.route('/admin/toggle_fijo/<int:cita_id>', methods=['POST'])
def toggle_fijo(cita_id):
    conn = get_conn()
    c = conn.cursor()
    # Obtener valor actual
    c.execute("SELECT fijo, peluquero_id FROM citas WHERE id = %s", (cita_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return redirect(request.referrer or url_for('index'))

    fijo_actual, peluquero_id = row
    # Invertir el valor
    nuevo_valor = not fijo_actual

    c.execute("UPDATE citas SET fijo = %s WHERE id = %s", (nuevo_valor, cita_id))
    conn.commit()
    conn.close()
    return redirect(url_for('ver_calendario_admin', peluquero_id=peluquero_id))

@app.route("/admin/liberar_todo/<int:peluquero_id>", methods=["POST"])
def liberar_todo(peluquero_id):
    if 'peluquero_id' not in session or not session.get('es_admin'):
        return redirect(url_for('login'))

    conn = get_conn()
    c = conn.cursor()

    # 1️⃣ Guardar los horarios de las citas NO fijas
    c.execute("""
        SELECT dia, hora
        FROM citas
        WHERE peluquero_id = %s AND (fijo IS NULL OR fijo = FALSE)
    """, (peluquero_id,))
    horarios_a_liberar = c.fetchall()   # [(dia, hora), ...]

    # 2️⃣ Eliminar esas citas
    c.execute("""
        DELETE FROM citas
        WHERE peluquero_id = %s AND (fijo IS NULL OR fijo = FALSE)
    """, (peluquero_id,))

    # 3️⃣ Marcar esos horarios como disponibles (bloqueado = FALSE)
    #     Solo si la fila ya existe en horarios
    for dia, hora in horarios_a_liberar:
        c.execute("""
            UPDATE horarios
            SET bloqueado = FALSE
            WHERE peluquero_id = %s AND dia = %s AND hora = %s
        """, (peluquero_id, dia, hora))

    conn.commit()
    conn.close()

    return redirect(url_for('ver_calendario_admin', peluquero_id=peluquero_id))

@app.route("/contabilidad", methods=["GET", "POST"])
def contabilidad_barbero():
    if 'peluquero_id' not in session:
        return redirect(url_for('login'))

     # Si el admin accede con ?peluquero_id=ID, usar ese
    peluquero_id = request.args.get("peluquero_id") or session['peluquero_id']
    es_admin = session.get('es_admin', False)

    conn = get_conn()
    c = conn.cursor()

    # ✅ Registrar un nuevo movimiento (venta o consumo)
    if request.method == "POST":
        tipo = request.form.get("tipo")
        categoria = request.form.get("categoria")
        descripcion = request.form.get("descripcion")
        valor = float(request.form.get("valor", 0))

        c.execute("""
            INSERT INTO contabilidad (peluquero_id, tipo, categoria, descripcion, valor, fecha)
            VALUES (%s, %s, %s, %s, %s, NOW())
        """, (peluquero_id, tipo, categoria, descripcion, valor))
        conn.commit()

    # ✅ Calcular rango de la semana (lunes a domingo)
    from datetime import date, timedelta
    hoy = date.today()
    inicio_semana = hoy - timedelta(days=hoy.weekday())
    fin_semana = inicio_semana + timedelta(days=6)

    # ✅ Obtener movimientos de la semana
    c.execute("""
        SELECT id, fecha, tipo, categoria, descripcion, valor
        FROM contabilidad
        WHERE peluquero_id = %s AND fecha::date BETWEEN %s AND %s
        ORDER BY fecha DESC
    """, (peluquero_id, inicio_semana, fin_semana))

    registros = [
        {
            "id": r[0],
            "fecha": r[1].strftime("%d/%m/%Y"),
            "tipo": r[2],
            "categoria": r[3],
            "descripcion": r[4],
            "valor": float(r[5]),
        }
        for r in c.fetchall()
    ]

    # ✅ Calcular totales
    total_ingresos = sum(r["valor"] for r in registros if r["tipo"] == "venta")
    total_consumos = sum(r["valor"] for r in registros if r["tipo"] == "consumo")
    total_neto = total_ingresos - total_consumos

    conn.close()

    # ✅ Renderizar correctamente
    return render_template(
        "contabilidad.html",
        registros=registros,
        total_ingresos=total_ingresos,
        total_consumos=total_consumos,
        total_neto=total_neto,
        inicio_semana=inicio_semana,
        fin_semana=fin_semana,
        es_admin=es_admin
    )

@app.route("/admin/contabilidad", methods=["GET", "POST"])
def admin_contabilidad():
    if 'peluquero_id' not in session or not session.get('es_admin'):
        return redirect(url_for('login'))

    conn = get_conn()
    c = conn.cursor()

    # Rangos de lunes a domingo de la semana actual
    from datetime import date, timedelta
    hoy = date.today()
    inicio_semana = hoy - timedelta(days=hoy.weekday())  # lunes
    fin_semana = inicio_semana + timedelta(days=6)       # domingo

    # Traer todos los barberos (excluyendo admin)
    c.execute("""
        SELECT id, nombre, porcentaje
        FROM peluqueros
        WHERE es_admin = 0
        ORDER BY nombre
    """)
    barberos = c.fetchall()

    reporte = []
    total_barberia = 0

    for (pid, nombre, porcentaje) in barberos:

        # Obtener movimientos del barbero de esta semana
        c.execute("""
            SELECT tipo, categoria, valor
            FROM contabilidad
            WHERE peluquero_id = %s
            AND fecha::date BETWEEN %s AND %s
        """, (pid, inicio_semana, fin_semana))

        registros = c.fetchall()

        # Cálculos
        total_cortes = sum(v for (t, cat, v) in registros if t == 'venta' and cat == 'cortes')
        ventas_barberia = sum(v for (t, cat, v) in registros if t == 'venta' and cat != 'cortes')
        consumos = sum(v for (t, cat, v) in registros if t == 'consumo')
        adelantos = sum(v for (t, cat, v) in registros if t == 'adelanto')

        pago_por_cortes = total_cortes * (porcentaje / 100)
        total_neto = pago_por_cortes - consumos - adelantos
        ganancia_barberia = ventas_barberia + (total_cortes - pago_por_cortes)

        total_barberia += ganancia_barberia

        reporte.append({
            "id": pid,
            "nombre": nombre,
            "porcentaje": porcentaje,
            "total_cortes": total_cortes,
            "ventas_barberia": ventas_barberia,
            "consumos": consumos,
            "adelantos": adelantos,
            "pago_por_cortes": pago_por_cortes,
            "total_neto": total_neto,
            "ganancia_barberia": ganancia_barberia
        })

    conn.close()

    return render_template(
        "admin_contabilidad.html",
        reporte=reporte,
        total_barberia=total_barberia,
        inicio_semana=inicio_semana,
        fin_semana=fin_semana,
    )

@app.route("/contabilidad/eliminar/<int:id>", methods=["POST"])
def eliminar_movimiento(id):
    if 'peluquero_id' not in session:
        return redirect(url_for('login'))

    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM contabilidad WHERE id = %s", (id,))
    conn.commit()
    conn.close()

    return redirect(url_for('contabilidad_barbero'))

    # Redirigir a su propia contabilidad
    if es_admin:
        return redirect(url_for('admin_contabilidad'))
    else:
        return redirect(url_for('contabilidad_barbero', peluquero_id=peluquero_id))

@app.route("/admin/contabilidad_historial")
def ver_contabilidad_historial():
    if 'peluquero_id' not in session or not session.get('es_admin'):
        return redirect(url_for('login'))

    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT semana_inicio, semana_fin, nombre_peluquero,
               SUM(CASE WHEN tipo='venta' AND categoria='cortes' THEN valor ELSE 0 END) AS total_cortes,
               SUM(CASE WHEN tipo='venta' AND categoria='barberia' THEN valor ELSE 0 END) AS total_barberia,
               SUM(CASE WHEN tipo='consumo' THEN valor ELSE 0 END) AS total_consumos
        FROM contabilidad_historial
        GROUP BY semana_inicio, semana_fin, nombre_peluquero
        ORDER BY semana_fin DESC
    """)
    historial = c.fetchall()
    conn.close()

    return render_template("admin_contabilidad_historial.html", historial=historial)

@app.route("/admin/gestionar_turno_global", methods=["POST"])
def gestionar_turno_global():
    if "peluquero_id" not in session or not session.get("es_admin"):
        return redirect(url_for("login"))

    dia = request.form.get("dia").lower()
    hora = request.form.get("hora")      # ej: '08:40'
    am_pm = request.form.get("am_pm")    # 'AM' o 'PM'
    accion = request.form.get("accion")  # 'agregar' o 'eliminar'

    # Normalizar a formato %I:%M %p (ej: "08:40 PM")
    from datetime import datetime
    hora_norm = datetime.strptime(f"{hora} {am_pm}", "%I:%M %p").strftime("%I:%M %p")

    # Si el admin eligió “TODOS” los días, usar toda la semana
    dias_semana = ["lunes", "martes", "miercoles", "jueves",
                   "viernes", "sabado", "domingo"]
    dias_a_usar = dias_semana if dia == "todos" else [dia]

    conn = get_conn()
    c = conn.cursor()

    # Obtener todos los peluqueros que NO son administradores
    c.execute("SELECT id FROM peluqueros WHERE es_admin = 0")
    peluqueros = [row[0] for row in c.fetchall()]

    if accion == "agregar":
        # Inserta el turno para todos los barberos (reactiva si existía y estaba bloqueado)
        for pid in peluqueros:
            for d in dias_a_usar:
                c.execute("""
                    INSERT INTO horarios (peluquero_id, dia, hora, bloqueado)
                    VALUES (%s, %s, %s, FALSE)
                    ON CONFLICT (peluquero_id, dia, hora)
                    DO UPDATE SET bloqueado = FALSE
                """, (pid, d, hora_norm))

    elif accion == "eliminar":
        # Borra por completo la fila de cada barbero
        for pid in peluqueros:
            for d in dias_a_usar:
                c.execute("""
                    DELETE FROM horarios
                    WHERE peluquero_id = %s AND dia = %s AND hora = %s
                """, (pid, d, hora_norm))

    conn.commit()
    conn.close()

    return redirect(url_for("admin_panel"))

def cierre_automatico_semanal():
    """
    Cierra automáticamente la semana cada domingo a las 11:59 PM.
    Copia los registros de 'contabilidad' a 'contabilidad_historial'
    y luego limpia la tabla principal.
    """
    while True:
        try:
            ahora = datetime.now()
            # Calcular próximo domingo a las 11:59 PM
            dias_hasta_domingo = (6 - ahora.weekday()) % 7  # 0=Lunes, 6=Domingo
            proximo_domingo = ahora + timedelta(days=dias_hasta_domingo)
            fecha_cierre = proximo_domingo.replace(hour=23, minute=59, second=0, microsecond=0)

            espera = (fecha_cierre - ahora).total_seconds()
            print(f"🕒 Próximo cierre semanal programado para: {fecha_cierre}")
            time.sleep(espera)

            conn = get_conn()
            c = conn.cursor()

            fin_semana = datetime.now().date()
            inicio_semana = fin_semana - timedelta(days=6)

            # Copiar registros actuales
            c.execute("""
                INSERT INTO contabilidad_historial (peluquero_id, nombre_peluquero, tipo, categoria,
                                                    nombre_item, valor, semana_inicio, semana_fin)
                SELECT peluquero_id, nombre_peluquero, tipo, categoria, nombre_item, valor,
                       %s, %s
                FROM contabilidad
            """, (inicio_semana, fin_semana))

            # Limpiar tabla principal
            c.execute("DELETE FROM contabilidad")
            conn.commit()
            conn.close()
            print("✅ Cierre semanal automático ejecutado correctamente.")

        except Exception as e:
            print(f"❌ Error en cierre semanal: {e}")
            time.sleep(60)  # evitar bucles en caso de error

def enviar_recordatorios():
    while True:
        try:
            conn = get_conn()
            c = conn.cursor()

            # Hora actual
            ahora = datetime.now()

            # Buscamos citas dentro de la próxima hora que aún no tengan recordatorio enviado
            c.execute("""
                SELECT id, nombre, telefono, dia, hora, peluquero_id
                FROM citas
                WHERE recordatorio_enviado = FALSE
            """)
            citas = c.fetchall()

            for id_cita, nombre, telefono, dia, hora, peluquero_id in citas:
                try:
                    # Convertir hora de texto ("02:00 PM") a datetime de hoy
                    hora_cita = datetime.strptime(hora, "%I:%M %p")

                    # Obtener el próximo día correspondiente (ej: lunes → fecha exacta)
                    from zoneinfo import ZoneInfo
                    tz = ZoneInfo("America/Bogota")
                    ahora_local = ahora.astimezone(tz)

                    # Saltar si ya pasó la cita
                    if hora_cita.hour < ahora_local.hour - 1:
                        continue

                    # Diferencia de tiempo
                    diferencia = abs((hora_cita.hour - ahora_local.hour) * 60 + (hora_cita.minute - ahora_local.minute))

                    if diferencia <= 60:  # dentro de una hora
                        # Obtener el nombre del peluquero
                        c2 = conn.cursor()
                        c2.execute("SELECT nombre FROM peluqueros WHERE id=%s", (peluquero_id,))
                        row = c2.fetchone()
                        nombre_peluquero = row[0] if row else "tu barbero"
                        c2.close()

                        # Enviar mensaje
                        account_sid = os.getenv("TWILIO_ACCOUNT_SID")
                        auth_token = os.getenv("TWILIO_AUTH_TOKEN")
                        from_whatsapp = os.getenv("TWILIO_WHATSAPP_NUMBER")

                        client = Client(account_sid, auth_token)
                        to_number = f"whatsapp:+57{telefono}"

                        mensaje = (
                            f"⏰ *Recuerda tu cita*\n\n"
                            f"Hola {nombre}, te recordamos tu cita con *{nombre_peluquero}* "
                            f"programada para hoy a las *{hora}*.\n\n"
                            f"💈 ¡Te esperamos en VIP BARBER TOP!"
                        )

                        client.messages.create(
                            from_=from_whatsapp,
                            to=to_number,
                            body=mensaje
                        )

                        # Marcar como recordatorio enviado
                        c.execute("UPDATE citas SET recordatorio_enviado = TRUE WHERE id=%s", (id_cita,))
                        conn.commit()

                        print(f"✅ Recordatorio enviado a {nombre} ({telefono})")

                except Exception as e:
                    print(f"⚠️ Error procesando cita {id_cita}: {e}")

            conn.close()

        except Exception as e:
            print(f"❌ Error en tarea de recordatorios: {e}")

        # Esperar 5 minutos antes de revisar de nuevo
        time.sleep(300)

# Iniciar hilo en segundo plano para enviar recordatorios
threading.Thread(target=enviar_recordatorios, daemon=True).start()

# 🔁 Lanzar hilo automático de cierre semanal
threading.Thread(target=cierre_automatico_semanal, daemon=True).start()

# ---------- ARRANQUE ----------
if __name__ == "__main__":
    init_schema()
    init_db_legacy()

    conn = get_conn()
    c = conn.cursor()
    c.execute(adapt_query("SELECT id FROM peluqueros"))
    peluqueros_ids = [row[0] for row in c.fetchall()]
    conn.close()

    for pid in peluqueros_ids:
        if pid:
            cargar_horarios_40_minutos(pid)

    print("✅ Base de datos lista y horarios cargados")
    app.run(debug=True)
