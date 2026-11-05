from datetime import date, datetime
from decimal import Decimal

from flask import Blueprint, jsonify, request, url_for

from . import caderno, storage
from .auth import login_required

api_bp = Blueprint("api", __name__, url_prefix="/api")


@api_bp.errorhandler(caderno.Invalido)
def invalido(e):
    return jsonify(erro=str(e)), 400


@api_bp.errorhandler(caderno.Conflito)
def conflito(e):
    return jsonify(erro=str(e)), 409


def _dados():
    # Aceita JSON ou formulário: com receita, a aplicação vai em multipart.
    if request.is_json:
        return request.get_json(silent=True) or {}
    return request.form


def _json(registro):
    saida = {}
    for campo, valor in registro.items():
        if campo in ("dono_id", "receita_key"):
            continue
        if isinstance(valor, Decimal):
            valor = float(valor)
        elif isinstance(valor, (date, datetime)):
            valor = valor.isoformat()
        saida[campo] = valor
    if "receita_key" in registro:
        chave = registro["receita_key"]
        saida["receita_url"] = storage.url_temporaria(chave) if chave else None
    return saida


# --- talhões ---------------------------------------------------------------


@api_bp.route("/talhoes", methods=["GET"])
@login_required
def listar_talhoes():
    return jsonify([_json(t) for t in caderno.listar_talhoes()])


@api_bp.route("/talhoes", methods=["POST"])
@login_required
def criar_talhao():
    talhao_id = caderno.criar_talhao(_dados())
    resp = jsonify(_json(caderno.obter_talhao(talhao_id)))
    return resp, 201, {"Location": url_for("api.obter_talhao", talhao_id=talhao_id)}


@api_bp.route("/talhoes/<int:talhao_id>", methods=["GET"])
@login_required
def obter_talhao(talhao_id):
    return jsonify(_json(caderno.obter_talhao(talhao_id)))


@api_bp.route("/talhoes/<int:talhao_id>", methods=["PUT"])
@login_required
def editar_talhao(talhao_id):
    caderno.editar_talhao(talhao_id, _dados())
    return jsonify(_json(caderno.obter_talhao(talhao_id)))


@api_bp.route("/talhoes/<int:talhao_id>", methods=["DELETE"])
@login_required
def apagar_talhao(talhao_id):
    caderno.apagar_talhao(talhao_id)
    return "", 204


# --- produtos --------------------------------------------------------------


@api_bp.route("/produtos", methods=["GET"])
@login_required
def listar_produtos():
    return jsonify([_json(p) for p in caderno.listar_produtos()])


@api_bp.route("/produtos", methods=["POST"])
@login_required
def criar_produto():
    produto_id = caderno.criar_produto(_dados())
    produto = caderno.obter_produto_para_editar(produto_id)
    return jsonify(_json(produto)), 201


@api_bp.route("/produtos/<int:produto_id>", methods=["PUT"])
@login_required
def editar_produto(produto_id):
    caderno.editar_produto(produto_id, _dados())
    return jsonify(_json(caderno.obter_produto_para_editar(produto_id)))


@api_bp.route("/produtos/<int:produto_id>", methods=["DELETE"])
@login_required
def apagar_produto(produto_id):
    caderno.apagar_produto(produto_id)
    return "", 204


# --- aplicações ------------------------------------------------------------


@api_bp.route("/aplicacoes", methods=["GET"])
@login_required
def listar_aplicacoes():
    talhao_id = request.args.get("talhao_id", type=int)
    return jsonify([_json(a) for a in caderno.listar_aplicacoes(talhao_id)])


@api_bp.route("/aplicacoes", methods=["POST"])
@login_required
def registrar_aplicacao():
    aplicacao_id = caderno.registrar_aplicacao(_dados(), request.files.get("receita"))
    resp = jsonify(_json(caderno.obter_aplicacao(aplicacao_id)))
    return resp, 201, {"Location": url_for("api.obter_aplicacao", aplicacao_id=aplicacao_id)}


@api_bp.route("/aplicacoes/<int:aplicacao_id>", methods=["GET"])
@login_required
def obter_aplicacao(aplicacao_id):
    return jsonify(_json(caderno.obter_aplicacao(aplicacao_id)))


@api_bp.route("/aplicacoes/<int:aplicacao_id>", methods=["PUT"])
@login_required
def editar_aplicacao(aplicacao_id):
    caderno.editar_aplicacao(aplicacao_id, _dados(), request.files.get("receita"))
    return jsonify(_json(caderno.obter_aplicacao(aplicacao_id)))


@api_bp.route("/aplicacoes/<int:aplicacao_id>", methods=["DELETE"])
@login_required
def apagar_aplicacao(aplicacao_id):
    caderno.apagar_aplicacao(aplicacao_id)
    return "", 204
