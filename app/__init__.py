import os
from decimal import Decimal

import click
from flasgger import Swagger
from flask import Flask, jsonify, render_template, request
from prometheus_flask_exporter import PrometheusMetrics

from .acesso import NOMES_DOS_PAPEIS
from .auditoria import registrar
from .caderno import hoje

MENSAGENS_DE_ERRO = {
    400: "Pedido inválido.",
    403: "Seu papel não permite essa ação.",
    404: "Não encontrado.",
    413: "Arquivo grande demais: a receita pode ter no máximo 8 MB.",
    503: "Um serviço do sistema não respondeu agora. Tente de novo em instantes.",
}


def create_app():
    app = Flask(__name__, template_folder="../templates", static_folder="../static")
    app.secret_key = os.environ["SECRET_KEY"]
    # Teto do corpo da requisição inteira; o limite da receita em si (8 MB) é
    # conferido no caderno.
    app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024

    from .admin import admin_bp
    from .api import api_bp
    from .arquivos import arquivos_bp
    from .auth import auth_bp
    from .inicio import inicio_bp
    from .plano import plano_bp
    from .propriedade import propriedade_bp
    from .saude import saude_bp
    from .telas import telas_bp

    app.register_blueprint(inicio_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(propriedade_bp)
    app.register_blueprint(telas_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(plano_bp)
    app.register_blueprint(arquivos_bp)
    app.register_blueprint(saude_bp)

    # /metrics no formato do Prometheus. Agrupa pela regra da rota
    # (/talhoes/<int:talhao_id>) e não pelo caminho real, senão cada id vira
    # uma série nova. O /health fica de fora pra o healthcheck do Docker não
    # inflar a contagem de requisições.
    PrometheusMetrics(app, group_by="url_rule", excluded_paths=["^/health"])

    # As telas misturam página (GET) e formulário (POST) na mesma função, então
    # a spec fica num arquivo só em vez de docstring por rota.
    app.config["SWAGGER"] = {"title": "Talhão em Dia", "openapi": "3.0.3"}
    Swagger(app, template_file=os.path.join(os.path.dirname(__file__), "openapi.yml"))

    @app.context_processor
    def globais():
        return {"nomes_dos_papeis": NOMES_DOS_PAPEIS, "hoje": hoje()}

    @app.template_filter("num")
    def numero(valor):
        if isinstance(valor, (Decimal, float, int)) and not isinstance(valor, bool):
            return f"{valor:.2f}".replace(".", ",")
        return valor or ""

    @app.template_filter("data")
    def data(valor):
        return f"{valor:%d/%m/%Y}" if valor else ""

    def erro(e):
        codigo = getattr(e, "code", 500)
        mensagem = MENSAGENS_DE_ERRO.get(codigo, "Algo deu errado.")
        if request.path.startswith("/api/"):
            return jsonify(erro=mensagem), codigo
        return render_template("erro.html", codigo=codigo, mensagem=mensagem), codigo

    # Todo 403 passa por aqui, então nenhuma tentativa negada escapa do log,
    # não importa se veio da tela ou direto na API.
    @app.errorhandler(403)
    def acesso_negado(e):
        registrar("acesso_negado", detalhes=f"{request.method} {request.path}")
        return erro(e)

    for codigo in (400, 404, 413, 503):
        app.register_error_handler(codigo, erro)

    @app.cli.command("arquivos")
    @click.argument("prefixo", default="")
    def listar_arquivos(prefixo):
        """Lista o que está guardado no bucket (receitas das aplicações)."""
        from . import storage

        total = 0
        for obj in storage.listar(prefixo):
            total += 1
            click.echo(f"{obj['LastModified']:%d/%m/%Y %H:%M}  {obj['Size']:>9}  {obj['Key']}")
        click.echo(f"{total} arquivo(s)")

    return app
