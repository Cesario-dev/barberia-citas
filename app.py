import os
import psycopg2
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename

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
    c.execute("SELECT COUNT(*) FROM citas WHERE peluquero_id=%s AND dia=%s AND hora=%s", 
              (peluquero_id, dia, hora))
    if c.fetchone()[0] > 0:
        conn.close()
        return "Lo sentimos, ese horario ya fue tomado", 400

    # Guardar la cita
    c.execute(
        "INSERT INTO citas (peluquero_id, dia, hora, nombre, telefono) VALUES (%s, %s, %s, %s, %s)",
        (peluquero_id, dia, hora, nombre, telefono)
    )
    conn.commit()
    conn.close()

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

    # Nombre del peluquero
    c.execute("SELECT nombre FROM peluqueros WHERE id=%s", (peluquero_id,))
    row = c.fetchone()
    nombre_peluquero = row[0] if row else "Desconocido"

    dias = ['lunes', 'martes', 'miercoles', 'jueves', 'viernes', 'sabado', 'domingo']

    # 🔹 Obtener solo las horas que realmente existen en la DB
    c.execute("""
        SELECT DISTINCT hora FROM horarios WHERE peluquero_id=%s
        UNION
        SELECT DISTINCT hora FROM citas    WHERE peluquero_id=%s
    """, (peluquero_id, peluquero_id))
    horas = sorted(
        {row[0] for row in c.fetchall()},
        key=lambda h: datetime.strptime(h, "%I:%M %p")
    )

    # Horarios disponibles
    c.execute("SELECT dia, hora FROM horarios WHERE peluquero_id=%s", (peluquero_id,))
    disponibles = {(row[0], row[1]) for row in c.fetchall()}

    # Citas ocupadas
    c.execute("SELECT dia, hora, nombre FROM citas WHERE peluquero_id=%s", (peluquero_id,))
    ocupados = {(row[0], row[1]): row[2] for row in c.fetchall()}

    conn.close()

    return render_template(
        "cliente_calendario.html",
        peluquero_id=peluquero_id,
        nombre_peluquero=nombre_peluquero,
        dias=dias,
        horas=horas,
        disponibles=disponibles,
        ocupados=ocupados
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
        c.execute("""
            UPDATE horarios
            SET bloqueado = TRUE
            WHERE peluquero_id=%s AND dia=%s AND hora=%s
        """, (peluquero_id, bloquear_dia, bloquear_hora))
        conn.commit()
    
    # ✅ Reactivar horario (quitar el bloqueo)
    activar_dia = request.args.get("activar_dia")
    activar_hora = request.args.get("activar_hora")
    if activar_dia and activar_hora:
        c.execute("""
            INSERT INTO horarios (peluquero_id, dia, hora, bloqueado)
            VALUES (%s, %s, %s, FALSE)
            ON CONFLICT (peluquero_id, dia, hora)
            DO UPDATE SET bloqueado = FALSE;
        """, (peluquero_id, activar_dia, activar_hora))
        conn.commit()
    
    # Datos del peluquero
    c.execute("SELECT nombre FROM peluqueros WHERE id=%s", (peluquero_id,))
    peluquero = c.fetchone()
    if not peluquero:
        conn.close()
        return "Peluquero no encontrado"
    nombre = peluquero[0]

    dias = ['lunes', 'martes', 'miercoles', 'jueves', 'viernes', 'sabado', 'domingo']

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
    c.execute("""
        SELECT dia, hora
        FROM horarios
        WHERE peluquero_id=%s AND bloqueado=TRUE
    """, (peluquero_id,))
    bloqueados = {(d, h) for d, h in c.fetchall()}

    # Ocupados
    c.execute("""
        SELECT id, dia, hora, nombre, telefono, fijo
        FROM citas
        WHERE peluquero_id=%s
    """, (peluquero_id,))
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

    # 🔹 Bloqueados: solo las celdas que existan en la DB
    #    (es decir, horas presentes en 'horas', pero no en disponibles ni ocupados)
    bloqueados = set(
        (d, h) for d in dias for h in horas
        if (d, h) not in disponibles and (d, h) not in ocupados
    )

    return render_template(
        "calendario.html",
        nombre=nombre,
        peluquero_id=peluquero_id,
        dias=dias,
        horas=horas,
        disponibles=disponibles,
        ocupados=ocupados,
        bloqueados=bloqueados,
        es_admin=True
    )


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
            c.execute(
                adapt_query("""
                    UPDATE horarios
                    SET bloqueado = TRUE
                    WHERE peluquero_id=%s AND dia=%s AND hora=%s
                """),
                (peluquero_id, bloquear_dia, bloquear_hora)
            )
            conn.commit()

        reactivar_dia = request.args.get('reactivar_dia')
        reactivar_hora = request.args.get('reactivar_hora')
        if reactivar_dia and reactivar_hora:
            c.execute("""
                INSERT INTO horarios (peluquero_id, dia, hora, bloqueado)
                VALUES (%s, %s, %s, FALSE)
                ON CONFLICT (peluquero_id, dia, hora)
                DO UPDATE SET bloqueado = FALSE;
            """, (peluquero_id, reactivar_dia, reactivar_hora))
            conn.commit()

    # ✅ Obtener nombre del peluquero
    c.execute(adapt_query("SELECT nombre FROM peluqueros WHERE id=%s"), (peluquero_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return "Peluquero no encontrado"
    nombre = row[0]

    dias = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]

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
        WHERE peluquero_id=%s
    """), (peluquero_id,))
    ocupados = {
        (d, h): {"nombre": n, "telefono": t}
        for d, h, n, t in c.fetchall()
    }

    # ✅ Bloqueados: solo los que están marcados como bloqueados
    c.execute(adapt_query("""
        SELECT dia, hora
        FROM horarios
        WHERE peluquero_id=%s AND bloqueado = TRUE
    """), (peluquero_id,))
    bloqueados = {(d, h) for d, h in c.fetchall()}

    conn.close()

    return render_template(
        "calendario.html",
        nombre=nombre,
        peluquero_id=peluquero_id,
        dias=dias,
        horas=horas,
        disponibles=disponibles,
        ocupados=ocupados,
        bloqueados=bloqueados,
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

    # 1️⃣  Guardar los horarios de las citas no fijas ANTES de borrarlas
    c.execute("""
        SELECT dia, hora
        FROM citas
        WHERE peluquero_id = %s AND (fijo IS NULL OR fijo = FALSE)
    """, (peluquero_id,))
    horarios_a_liberar = c.fetchall()   # lista de tuplas (dia, hora)

    # 2️⃣  Eliminar esas citas
    c.execute("""
        DELETE FROM citas
        WHERE peluquero_id = %s AND (fijo IS NULL OR fijo = FALSE)
    """, (peluquero_id,))

    # 3️⃣  Volver a insertar SOLO en horarios los huecos que
    #     a) acaban de quedar libres y
    #     b) NO estén ya disponibles (para evitar duplicados)
    for dia, hora in horarios_a_liberar:
        c.execute("""
            INSERT INTO horarios (peluquero_id, dia, hora)
            SELECT %s, %s, %s
            WHERE NOT EXISTS (
                SELECT 1 FROM horarios
                WHERE peluquero_id = %s AND dia = %s AND hora = %s
            )
        """, (peluquero_id, dia, hora, peluquero_id, dia, hora))

    conn.commit()
    conn.close()

    return redirect(url_for('ver_calendario_admin', peluquero_id=peluquero_id))

@app.route("/admin/gestionar_turno_global", methods=["POST"])
def gestionar_turno_global():
    if 'peluquero_id' not in session or not session.get('es_admin'):
        return redirect(url_for('login'))

    dia = request.form.get("dia").lower()
    hora = request.form.get("hora")          # viene como '08:40' o '8:40'
    am_pm = request.form.get("am_pm")        # 'AM' o 'PM'

    # ✅ Normalizar a formato %I:%M %p (ej: "08:40 PM")
    hora_norm = datetime.strptime(f"{hora} {am_pm}", "%I:%M %p").strftime("%I:%M %p")

    accion = request.form.get("accion")

    dias_semana = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]
    dias_a_insertar = dias_semana if dia == "todos" else [dia]

    conn = get_conn()
    c = conn.cursor()

     # ✅ Obtener peluqueros NO administradores una sola vez
    c.execute("SELECT id FROM peluqueros WHERE es_admin = 0")
    peluqueros = [row[0] for row in c.fetchall()]

    if accion == "agregar":
        for pid in peluqueros:
            for d in dias_a_insertar:     # ✅ usa d, no dia
                try:
                    c.execute(
                        "INSERT INTO horarios (peluquero_id, dia, hora) VALUES (%s, %s, %s)",
                        (pid, d, hora_norm)
                    )
                except:
                    conn.rollback()
                    continue

    elif accion == "eliminar":
        if dia == "todos":
            for d in dias_semana:
                c.execute(
                    "DELETE FROM horarios WHERE dia=%s AND hora=%s",
                    (d, hora_norm)
                )
        else:
            c.execute(
                "DELETE FROM horarios WHERE dia=%s AND hora=%s",
                (dia, hora_norm)
            )

    conn.commit()
    conn.close()

    return redirect(url_for('admin_panel'))  # o a la página de admin que prefieras

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
