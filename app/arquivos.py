import requests
from flask import Blueprint, Response, abort, request

from . import storage

arquivos_bp = Blueprint("arquivos", __name__)


@arquivos_bp.route("/arquivos/<path:caminho>")
def arquivo(caminho):
    # Só repassa a URL assinada pro storage. Quem confere a assinatura e se ela
    # já expirou é o próprio Garage; sem assinatura válida ele responde 403.
    try:
        resp = requests.get(
            storage.url_interna(caminho, request.query_string.decode()),
            timeout=10,
        )
    except requests.exceptions.RequestException:
        abort(503)

    if resp.status_code != 200:
        abort(404 if resp.status_code == 404 else 403)

    return Response(
        resp.content,
        content_type=resp.headers.get("Content-Type", "application/octet-stream"),
        headers={"Cache-Control": f"private, max-age={storage.URL_VALIDADE_SEGUNDOS}"},
    )
