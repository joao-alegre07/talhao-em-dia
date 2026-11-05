import os

import requests
from flask import request, session


def ip_origem():
    # Atrás do proxy do servidor o IP real chega no X-Forwarded-For.
    encaminhado = request.headers.get("X-Forwarded-For", "")
    if encaminhado:
        return encaminhado.split(",")[0].strip()
    return request.remote_addr or ""


def registrar(acao, usuario_id=None, detalhes=""):
    if usuario_id is None:
        usuario_id = session.get("usuario_id")

    # Se o log-service estiver fora do ar, a ação do usuário não pode falhar
    # por causa disso -- o evento se perde, mas o app continua funcionando.
    try:
        requests.post(
            os.environ["LOG_SERVICE_URL"].rstrip("/") + "/eventos",
            json={
                "usuario_id": usuario_id,
                "acao": acao,
                "ip": ip_origem(),
                "servico": "app",
                "detalhes": detalhes,
            },
            timeout=2,
        )
    except (requests.exceptions.RequestException, KeyError):
        pass


def ultimos_eventos(n):
    resp = requests.get(
        os.environ["LOG_SERVICE_URL"].rstrip("/") + "/eventos",
        params={"n": n},
        timeout=5,
    )
    resp.raise_for_status()
    return resp.json()
