"""
Script para generar certificados SSL autofirmados para desarrollo local
Ejecutar: python generate_ssl_local.py
"""

import sys
import os
from pathlib import Path

try:
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from datetime import datetime, timedelta
    import ipaddress
except ImportError:
    print("ERROR: Necesitas instalar cryptography:")
    print("  pip install cryptography")
    sys.exit(1)

def generate_self_signed_cert():
    """Genera un certificado SSL autofirmado para localhost"""
    
    cert_dir = Path("ssl_certs")
    cert_dir.mkdir(exist_ok=True)
    
    cert_file = cert_dir / "cert.pem"
    key_file = cert_dir / "key.pem"
    
    # Si ya existen, preguntar si regenerar
    if cert_file.exists() and key_file.exists():
        print("Los certificados SSL ya existen.")
        respuesta = input("¿Deseas regenerarlos? (s/n): ").lower()
        if respuesta != 's':
            print("Usando certificados existentes.")
            return str(cert_file), str(key_file)
        else:
            # Eliminar los existentes
            cert_file.unlink()
            key_file.unlink()
    
    print("Generando certificados SSL autofirmados...")
    
    # Generar clave privada
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    
    # Crear certificado
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "Development"),
        x509.NameAttribute(NameOID.LOCALITY_NAME, "Local"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "ExtractorOCR"),
        x509.NameAttribute(NameOID.COMMON_NAME, "localhost"),
    ])
    
    cert = x509.CertificateBuilder().subject_name(
        subject
    ).issuer_name(
        issuer
    ).public_key(
        private_key.public_key()
    ).serial_number(
        x509.random_serial_number()
    ).not_valid_before(
        datetime.utcnow()
    ).not_valid_after(
        datetime.utcnow() + timedelta(days=365)
    ).add_extension(
        x509.SubjectAlternativeName([
            x509.DNSName("localhost"),
            x509.DNSName("127.0.0.1"),
            x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
        ]),
        critical=False,
    ).sign(private_key, hashes.SHA256())
    
    # Guardar certificado
    with open(cert_file, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    
    # Guardar clave privada
    with open(key_file, "wb") as f:
        f.write(private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        ))
    
    print(f"\nCertificados generados exitosamente:")
    print(f"  Certificado: {cert_file.absolute()}")
    print(f"  Clave privada: {key_file.absolute()}")
    print("\nNOTA: Estos son certificados autofirmados para desarrollo.")
    print("El navegador mostrara una advertencia de seguridad.")
    print("Puedes aceptarla para continuar con el desarrollo.")
    print("\nPara usar HTTPS, habilita 'api.ssl.enabled: true' en config.json")
    
    return str(cert_file), str(key_file)

if __name__ == "__main__":
    try:
        cert_path, key_path = generate_self_signed_cert()
        print(f"\nCertificados listos. Ahora puedes:")
        print("1. Editar config/config.json y poner 'api.ssl.enabled: true'")
        print("2. Reiniciar el servidor con: python api_server.py")
    except Exception as e:
        print(f"Error generando certificados: {e}")
        import traceback
        traceback.print_exc()

