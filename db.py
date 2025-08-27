# db.py
import os
import re
import psycopg2
import sqlite3

# Detectar si hay variable de entorno DATABASE_URL
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
USE_POSTGRES = DATABASE_URL.startswith("postgres://") or DATABASE_URL.startswith("postgresql://")

def get_conn():
    """Devuelve conexión según el entorno: PostgreSQL si hay DATABASE_URL, SQLite si no."""
    if USE_POSTGRES:
        return psycopg2.connect(DATABASE_URL, sslmode="require")
    else:
        db_path = os.path.join(os.path.dirname(__file__), "database.db")
        return sqlite3.connect(db_path, check_same_thread=False)

_qmark_pattern = re.compile(r'\?')

def adapt_query(sql: str) -> str:
    """Convierte placeholders '?' → '%s' solo cuando usamos PostgreSQL."""
    if USE_POSTGRES:
        return _qmark_pattern.sub('%s', sql)
    return sql

def init_schema():
    """Crea tablas y asegura un admin por defecto."""
    conn = get_conn()
    c = conn.cursor()

    # Peluqueros
    c.execute(adapt_query("""
    CREATE TABLE IF NOT EXISTS peluqueros (
        id SERIAL PRIMARY KEY,
        nombre VARCHAR(100) NOT NULL,
        password VARCHAR(100) NOT NULL,
        foto VARCHAR(255),
        es_admin BOOLEAN DEFAULT FALSE
    )
    """))

    # Horarios
    c.execute(adapt_query("""
    CREATE TABLE IF NOT EXISTS horarios (
        id SERIAL PRIMARY KEY,
        peluquero_id INTEGER NOT NULL,
        dia VARCHAR(20) NOT NULL,
        hora VARCHAR(5) NOT NULL,
        UNIQUE(peluquero_id, dia, hora)
    )
    """))

    # Citas
    c.execute(adapt_query("""
    CREATE TABLE IF NOT EXISTS citas (
        id SERIAL PRIMARY KEY,
        peluquero_id INTEGER NOT NULL,
        dia VARCHAR(20) NOT NULL,
        hora VARCHAR(5) NOT NULL,
        nombre VARCHAR(100) NOT NULL,
        telefono VARCHAR(30),
        UNIQUE(peluquero_id, dia, hora)
    )
    """))

    # Crear admin por defecto
    c.execute(adapt_query("SELECT COUNT(*) FROM peluqueros WHERE es_admin = ?"), (True,))
    count = c.fetchone()[0]
    if count == 0:
        c.execute(adapt_query(
            "INSERT INTO peluqueros (nombre, password, es_admin) VALUES (?, ?, ?)"
        ), ("admin", "admin", True))

    conn.commit()
    conn.close()