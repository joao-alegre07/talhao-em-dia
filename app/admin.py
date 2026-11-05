from datetime import datetime

import requests
from flask import Blueprint, render_template, request

from .acesso import exigir
from .auditoria import ultimos_eventos
from .auth import login_required, nomes_dos_usuarios
from .caderno import BRASILIA

admin_bp = Blueprint("admin", __name__)

# O que aconteceu no negócio, separado de login, logout e erro.
EVENTOS_DE_NEGOCIO = {
    "conta_criada",
    "propriedade_criada",
    "convite_criado",
    "convite_aceito",
    "talhao_criado",
    "talhao_editado",
    "talhao_apagado",
    "produto_cadastrado",
    "produto_editado",
    "produto_apagado",
    "aplicacao_registrada",
    "aplicacao_editada",
    "aplicacao_apagada",
    "checkout_pro",
    "pro_ativado",
    "pro_cancelado",
}


def _horario_de_brasilia(timestamp):
    try:
        return datetime.fromisoformat(timestamp).astimezone(BRASILIA).strftime("%d/%m/%Y %H:%M:%S")
    except ValueError:
        return timestamp


@admin_bp.route("/admin/logs")
@login_required
def logs():
    exigir("logs")

    n = min(max(request.args.get("n", 50, type=int), 1), 500)
    so_negocio = request.args.get("tipo") == "negocio"
    try:
        eventos = ultimos_eventos(n)
        erro = None
    except requests.exceptions.RequestException:
        eventos = []
        erro = "Serviço de logs indisponível."

    if so_negocio:
        eventos = [e for e in eventos if e["acao"] in EVENTOS_DE_NEGOCIO]

    nomes = nomes_dos_usuarios([e["usuario_id"] for e in eventos])
    for e in eventos:
        e["quando"] = _horario_de_brasilia(e["timestamp"])
        e["quem"] = nomes.get(int(e["usuario_id"])) if e["usuario_id"].isdigit() else None
        e["negocio"] = e["acao"] in EVENTOS_DE_NEGOCIO

    return render_template("logs.html", eventos=eventos, n=n, so_negocio=so_negocio, erro=erro)
