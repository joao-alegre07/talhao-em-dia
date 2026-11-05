import os
from datetime import datetime, timezone

import redis
from flasgger import Swagger
from flask import Flask, jsonify, request
from prometheus_flask_exporter import PrometheusMetrics

app = Flask(__name__)
app.config["SWAGGER"] = {"title": "log-service", "openapi": "3.0.3"}
Swagger(
    app,
    template={
        "info": {
            "title": "log-service",
            "version": "1.0",
            "description": "Serviço interno de auditoria. Recebe eventos do app e do "
            "auth-service e guarda num Redis Stream. Sem porta pública: em produção só é "
            "alcançado pela rede do Docker.",
        },
        "components": {
            "schemas": {
                "Evento": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "example": "1759268412345-0"},
                        "usuario_id": {"type": "string", "example": "6"},
                        "acao": {"type": "string", "example": "aplicacao_registrada"},
                        "timestamp": {"type": "string", "example": "2026-09-30T21:40:12+00:00"},
                        "ip": {"type": "string", "example": "177.10.20.30"},
                        "servico": {"type": "string", "example": "app"},
                        "detalhes": {"type": "string", "example": "aplicação 12 no talhão Alto (3)"},
                    },
                },
                "Erro": {
                    "type": "object",
                    "properties": {"erro": {"type": "string"}},
                },
            }
        },
    },
)

STREAM = "auditoria"

PrometheusMetrics(app, group_by="url_rule", excluded_paths=["^/health"])

r = redis.Redis.from_url(
    os.environ.get("REDIS_URL", "redis://redis:6379/0"),
    decode_responses=True,
    socket_connect_timeout=2,
    socket_timeout=2,
)


@app.route("/health/live")
def live():
    """Liveness: o processo está de pé e respondendo
    ---
    tags: [saúde]
    description: Não testa nada além do próprio serviço; sempre 200 se o Flask responder.
    responses:
      200:
        description: Vivo.
        content:
          application/json:
            example: {"status": "ok"}
    """
    return jsonify(status="ok")


@app.route("/health")
def ready():
    """Readiness: o serviço consegue falar com o Redis
    ---
    tags: [saúde]
    description: >
      É pra cá que aponta o HEALTHCHECK do Docker. Manda um `PING` pro Redis, com timeout de 2 segundos.
    responses:
      200:
        description: Tudo certo.
        content:
          application/json:
            example: {"status": "ok", "dependencias": {"redis": "ok"}}
      503:
        description: Redis fora do ar.
        content:
          application/json:
            example: {"status": "falhou", "dependencias": {"redis": "falhou: ConnectionError"}}
    """
    try:
        r.ping()
    except redis.exceptions.RedisError as e:
        return jsonify(status="falhou", dependencias={"redis": f"falhou: {type(e).__name__}"}), 503

    return jsonify(status="ok", dependencias={"redis": "ok"})


@app.route("/eventos", methods=["POST"])
def registrar():
    """Registra um evento de auditoria
    ---
    tags: [eventos]
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required: [acao]
            properties:
              acao:
                type: string
                example: aplicacao_registrada
              usuario_id:
                type: integer
                nullable: true
                example: 6
              ip:
                type: string
                example: 177.10.20.30
              servico:
                type: string
                example: app
              detalhes:
                type: string
                example: aplicação 12 no talhão Alto (3)
    responses:
      201:
        description: Evento gravado. O timestamp é definido pelo log-service.
        content:
          application/json:
            example: {"id": "1759268412345-0"}
      400:
        description: Faltou o campo acao.
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/Erro'
            example: {"erro": "Campo 'acao' é obrigatório."}
    """
    dados = request.get_json(force=True, silent=True) or {}
    acao = (dados.get("acao") or "").strip()
    if not acao:
        return jsonify(erro="Campo 'acao' é obrigatório."), 400

    # O horário é sempre o do log-service, não o de quem mandou o evento --
    # assim todos os serviços ficam na mesma linha do tempo.
    evento = {
        "usuario_id": dados.get("usuario_id") or "",
        "acao": acao,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "ip": dados.get("ip") or "",
        "servico": dados.get("servico") or "",
        "detalhes": dados.get("detalhes") or "",
    }
    evento_id = r.xadd(STREAM, {k: str(v) for k, v in evento.items()})
    return jsonify(id=evento_id), 201


@app.route("/eventos", methods=["GET"])
def listar():
    """Lista os últimos eventos, do mais recente pro mais antigo
    ---
    tags: [eventos]
    parameters:
      - name: n
        in: query
        description: Quantidade de eventos (de 1 a 500; fora disso é ajustado pro limite).
        schema:
          type: integer
          default: 50
          minimum: 1
          maximum: 500
    responses:
      200:
        description: Lista de eventos.
        content:
          application/json:
            schema:
              type: array
              items:
                $ref: '#/components/schemas/Evento'
    """
    n = min(max(request.args.get("n", 50, type=int), 1), 500)
    eventos = [{"id": evento_id, **campos} for evento_id, campos in r.xrevrange(STREAM, count=n)]
    return jsonify(eventos)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5002)))
