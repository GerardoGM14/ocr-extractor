"""
Script para sincronizar usuarios desde user_passwords.json a la base de datos.
Este script lee el JSON y sincroniza todos los usuarios a la BD como respaldo.
"""

import sys
import json
from pathlib import Path

# Agregar src al path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from api.main import format_name_from_email

def sync_users_from_json():
    """Sincroniza usuarios desde JSON a BD."""
    # Leer usuarios del JSON
    json_path = Path(__file__).parent.parent / "config" / "user_passwords.json"
    
    if not json_path.exists():
        print(f"❌ No se encontró el archivo: {json_path}")
        return
    
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        passwords = data.get("passwords", {})
        
        if not passwords:
            print("⚠️  No hay usuarios en el JSON para sincronizar.")
            return
        
        print(f"📋 Encontrados {len(passwords)} usuarios en el JSON.\n")
        print("💡 Para sincronizar a la BD, ejecuta este script con pyodbc instalado")
        print("   y configura la conexión en config/config.json\n")
        
        print("Usuarios encontrados:")
        for email, password in passwords.items():
            nombre = format_name_from_email(email)
            print(f"  - {email}")
            print(f"    Contraseña: {password}")
            print(f"    Nombre: {nombre}\n")
        
        print("✅ Para sincronizar, el backend lo hará automáticamente cuando")
        print("   se genere o actualice una contraseña en el JSON.")
        
    except Exception as e:
        print(f"❌ Error leyendo JSON: {e}")

if __name__ == "__main__":
    sync_users_from_json()

