import sqlite3

# 📌 Cambia el nombre si tu base se llama diferente
DB_NAME = "citas.db"

conn = sqlite3.connect(DB_NAME)
c = conn.cursor()

print("📋 Lista de peluqueros en el sistema:\n")
for row in c.execute("SELECT id, nombre, es_admin FROM peluqueros"):
    id_, nombre, es_admin = row
    rol = "Admin" if es_admin else "Peluquero"
    print(f"ID: {id_} | Nombre: {nombre} | Rol: {rol}")

print("\nOpciones:")
print("1. Asignar ADMIN a un usuario")
print("2. Quitar ADMIN a un usuario")
print("0. Salir")

try:
    opcion = int(input("\nSelecciona una opción: "))
    if opcion == 1:
        id_admin = int(input("ID del peluquero que será ADMIN: "))
        c.execute("UPDATE peluqueros SET es_admin = 1 WHERE id = ?", (id_admin,))
        conn.commit()
        print(f"\n✅ El peluquero con ID {id_admin} ahora es ADMIN.")
    elif opcion == 2:
        id_admin = int(input("ID del peluquero al que se le quitará ADMIN: "))
        c.execute("UPDATE peluqueros SET es_admin = 0 WHERE id = ?", (id_admin,))
        conn.commit()
        print(f"\n✅ El peluquero con ID {id_admin} ya NO es ADMIN.")
    elif opcion == 0:
        print("ℹ No se hicieron cambios.")
    else:
        print("❌ Opción no válida.")
except ValueError:
    print("❌ Entrada no válida. Debes poner un número.")

conn.close()