from flask import Blueprint, jsonify

from . import storage
from .db import get_connection

saude_bp = Blueprint("saude", __name__)


def _mariadb():
    conn = get_connection(connect_timeout=2)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
    finally:
        conn.close()


# Só entram aqui as dependências que o app acessa direto. O auth e o log
# têm o próprio /health; e o log fora do ar nem impede o app de funcionar.
DEPENDENCIAS = {
    "mariadb": _mariadb,
    "garage": storage.conferir_bucket,
}


@saude_bp.route("/health/live")
def live():
    return jsonify(status="ok")


@saude_bp.route("/health")
def ready():
    resultado = {}
    for nome, conferir in DEPENDENCIAS.items():
        try:
            conferir()
            resultado[nome] = "ok"
        except Exception as e:
            resultado[nome] = f"falhou: {type(e).__name__}"

    tudo_ok = all(v == "ok" for v in resultado.values())
    return jsonify(status="ok" if tudo_ok else "falhou", dependencias=resultado), (200 if tudo_ok else 503)
