import os
import secrets
from datetime import datetime, timedelta

from flasgger import Swagger
from flask import Flask, jsonify, request
from prometheus_flask_exporter import PrometheusMetrics
from werkzeug.security import check_password_hash, generate_password_hash

from auditoria import registrar
from db import get_connection
from mail import enviar_email_reset

app = Flask(__name__)
app.config["SWAGGER"] = {"title": "auth-service", "openapi": "3.0.3"}
Swagger(
    app,
    template={
        "info": {
            "title": "auth-service",
            "version": "1.0",
            "description": "Serviço interno de autenticação: cadastro, login, papéis e "
            "recuperação de senha. Sem porta pública: em produção só o app fala com ele, "
            "pela rede do Docker.",
        },
        "components": {
            "schemas": {
                "Erro": {
                    "type": "object",
                    "properties": {"erro": {"type": "string"}},
                },
                "Ok": {
                    "type": "object",
                    "properties": {"ok": {"type": "boolean", "example": True}},
                },
            }
        },
    },
)

PrometheusMetrics(app, group_by="url_rule", excluded_paths=["^/health"])

TOKEN_VALIDADE_MINUTOS = 30

# admin fica de fora: é papel da plataforma e só muda direto no banco.
PAPEIS_DO_CADASTRO = ("produtor", "funcionario", "agronomo")


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
    """Readiness: o serviço consegue falar com o MariaDB
    ---
    tags: [saúde]
    description: >
      É pra cá que aponta o HEALTHCHECK do Docker. Faz um `SELECT 1` no MariaDB com timeout de 2 segundos.
    responses:
      200:
        description: Tudo certo.
        content:
          application/json:
            example: {"status": "ok", "dependencias": {"mariadb": "ok"}}
      503:
        description: MariaDB fora do ar.
        content:
          application/json:
            example: {"status": "falhou", "dependencias": {"mariadb": "falhou: OperationalError"}}
    """
    try:
        conn = get_connection(connect_timeout=2)
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        finally:
            conn.close()
    except Exception as e:
        return jsonify(status="falhou", dependencias={"mariadb": f"falhou: {type(e).__name__}"}), 503

    return jsonify(status="ok", dependencias={"mariadb": "ok"})


@app.route("/cadastro", methods=["POST"])
def cadastro():
    """Cria uma conta nova com um dos papéis do negócio
    ---
    tags: [contas]
    description: >
      O papel é produtor, funcionario ou agronomo (sem papel, produtor). admin nunca nasce pelo
      cadastro. Quem decide se a pessoa pode ser funcionário é o app, que só manda esse papel
      depois de conferir o convite da propriedade.
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required: [nome, email, senha]
            properties:
              nome:
                type: string
                example: Marcos
              email:
                type: string
                example: marcos@exemplo.com
              senha:
                type: string
                example: umasenhaqualquer
              papel:
                type: string
                enum: [produtor, funcionario, agronomo]
                example: produtor
    responses:
      201:
        description: Conta criada.
        content:
          application/json:
            example: {"id": 7}
      400:
        description: Algum campo veio vazio ou o papel não existe.
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/Erro'
            examples:
              vazio:
                value: {"erro": "Preencha todos os campos."}
              papel:
                value: {"erro": "Papel inválido."}
      409:
        description: Já existe conta com esse e-mail.
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/Erro'
            example: {"erro": "E-mail já cadastrado."}
    """
    dados = request.get_json(force=True, silent=True) or {}
    nome = (dados.get("nome") or "").strip()
    email = (dados.get("email") or "").strip().lower()
    senha = dados.get("senha") or ""
    papel = dados.get("papel") or "produtor"

    if not nome or not email or not senha:
        return jsonify(erro="Preencha todos os campos."), 400
    if papel not in PAPEIS_DO_CADASTRO:
        return jsonify(erro="Papel inválido."), 400

    senha_hash = generate_password_hash(senha)

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM usuarios WHERE email = %s", (email,))
            if cur.fetchone():
                return jsonify(erro="E-mail já cadastrado."), 409

            cur.execute(
                "INSERT INTO usuarios (nome, email, senha_hash, role) "
                "VALUES (%s, %s, %s, %s)",
                (nome, email, senha_hash, papel),
            )
            usuario_id = cur.lastrowid
    finally:
        conn.close()

    return jsonify(id=usuario_id), 201


@app.route("/login", methods=["POST"])
def login():
    """Confere e-mail e senha
    ---
    tags: [contas]
    description: Toda tentativa, certa ou errada, vira um evento no log-service.
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required: [email, senha]
            properties:
              email:
                type: string
                example: maria@exemplo.com
              senha:
                type: string
                example: umasenhaqualquer
              ip:
                type: string
                description: IP de quem tentou logar, repassado pelo app pro log.
                example: 177.10.20.30
    responses:
      200:
        description: Login certo.
        content:
          application/json:
            example: {"usuario_id": 7, "nome": "Maria", "role": "produtor"}
      401:
        description: E-mail não cadastrado ou senha errada (mesma resposta nos dois casos).
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/Erro'
            example: {"erro": "E-mail ou senha inválidos."}
    """
    dados = request.get_json(force=True, silent=True) or {}
    email = (dados.get("email") or "").strip().lower()
    senha = dados.get("senha") or ""
    ip = dados.get("ip") or ""

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, nome, senha_hash, role FROM usuarios WHERE email = %s",
                (email,),
            )
            usuario = cur.fetchone()
    finally:
        conn.close()

    if usuario is None or not check_password_hash(usuario["senha_hash"], senha):
        registrar(
            "login_falhou",
            usuario_id=usuario["id"] if usuario else None,
            ip=ip,
            detalhes=email,
        )
        return jsonify(erro="E-mail ou senha inválidos."), 401

    registrar("login", usuario_id=usuario["id"], ip=ip)
    return jsonify(usuario_id=usuario["id"], nome=usuario["nome"], role=usuario["role"])


@app.route("/usuarios", methods=["GET"])
def listar_usuarios():
    """Nome e papel de vários usuários de uma vez
    ---
    tags: [contas]
    description: >
      Usada pelo app pra mostrar nomes na equipe da propriedade e no log, sem uma chamada por pessoa.
      Não devolve e-mail.
    parameters:
      - name: ids
        in: query
        required: true
        description: Ids separados por vírgula (até 200).
        schema:
          type: string
          example: 7,8,12
    responses:
      200:
        description: Os usuários encontrados; ids que não existem ficam de fora.
        content:
          application/json:
            example: [{"id": 7, "nome": "Marcos", "role": "produtor"}, {"id": 8, "nome": "Diego", "role": "funcionario"}]
    """
    ids = []
    for parte in request.args.get("ids", "").split(","):
        if parte.strip().isdigit():
            ids.append(int(parte))
    ids = sorted(set(ids))[:200]
    if not ids:
        return jsonify([])

    marcadores = ", ".join(["%s"] * len(ids))
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT id, nome, role FROM usuarios WHERE id IN ({marcadores})", ids)
            usuarios = cur.fetchall()
    finally:
        conn.close()

    return jsonify(usuarios)


@app.route("/usuarios/<int:usuario_id>", methods=["GET"])
def obter_usuario(usuario_id):
    """Dados e papel atual de um usuário
    ---
    tags: [contas]
    description: O app chama essa rota a cada ação que depende do papel, pra conferir o papel atual na hora.
    parameters:
      - name: usuario_id
        in: path
        required: true
        schema:
          type: integer
          example: 7
    responses:
      200:
        description: Usuário encontrado.
        content:
          application/json:
            example: {"id": 7, "nome": "Maria", "email": "maria@exemplo.com", "role": "produtor", "premium": false}
      404:
        description: Não existe usuário com esse id.
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/Erro'
            example: {"erro": "Usuário não encontrado."}
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, nome, email, role, premium FROM usuarios WHERE id = %s",
                (usuario_id,),
            )
            usuario = cur.fetchone()
    finally:
        conn.close()

    if usuario is None:
        return jsonify(erro="Usuário não encontrado."), 404

    usuario["premium"] = bool(usuario["premium"])
    return jsonify(usuario)


@app.route("/usuarios/<int:usuario_id>/plano", methods=["PUT"])
def alterar_plano(usuario_id):
    """Liga ou desliga o premium de um usuário
    ---
    tags: [contas]
    description: >
      Chamada pelo app depois de validar a assinatura de um webhook do Stripe. Guarda só os
      IDs do cliente e da assinatura no Stripe, nunca dado de cartão. Repetir a mesma chamada não
      muda nada (o Stripe pode entregar o mesmo evento mais de uma vez).
    parameters:
      - name: usuario_id
        in: path
        required: true
        schema:
          type: integer
          example: 7
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required: [premium]
            properties:
              premium:
                type: boolean
                example: true
              stripe_customer_id:
                type: string
                example: cus_R2x9aB3cD4eF5g
              stripe_subscription_id:
                type: string
                example: sub_1Q8xYz2eZvKYlo2C
    responses:
      200:
        description: Plano atualizado.
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/Ok'
      400:
        description: Faltou o campo premium.
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/Erro'
            example: {"erro": "Informe premium: true ou false."}
      404:
        description: Não existe usuário com esse id.
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/Erro'
            example: {"erro": "Usuário não encontrado."}
    """
    dados = request.get_json(force=True, silent=True) or {}
    if not isinstance(dados.get("premium"), bool):
        return jsonify(erro="Informe premium: true ou false."), 400

    premium = dados["premium"]
    customer_id = dados.get("stripe_customer_id")
    subscription_id = dados.get("stripe_subscription_id") if premium else None

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM usuarios WHERE id = %s", (usuario_id,))
            if cur.fetchone() is None:
                return jsonify(erro="Usuário não encontrado."), 404

            # Ao cancelar, só a assinatura sai; o id do cliente no Stripe fica.
            cur.execute(
                "UPDATE usuarios SET premium = %s, "
                "stripe_customer_id = COALESCE(%s, stripe_customer_id), "
                "stripe_subscription_id = %s WHERE id = %s",
                (premium, customer_id, subscription_id, usuario_id),
            )
    finally:
        conn.close()

    return jsonify(ok=True)


@app.route("/esqueci-senha", methods=["POST"])
def esqueci_senha():
    """Pede um link de redefinição de senha
    ---
    tags: [senha]
    description: >
      Se o e-mail existir, gera um token válido por 30 minutos e manda o link por e-mail.
      A resposta é sempre a mesma, exista ou não a conta.
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required: [email, base_url]
            properties:
              email:
                type: string
                example: maria@exemplo.com
              base_url:
                type: string
                description: Endereço público do app, usado pra montar o link.
                example: https://joao-alegre-isw055.lapps.studio
    responses:
      200:
        description: Pedido recebido.
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/Ok'
    """
    dados = request.get_json(force=True, silent=True) or {}
    email = (dados.get("email") or "").strip().lower()
    base_url = (dados.get("base_url") or "").rstrip("/")

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM usuarios WHERE email = %s", (email,))
            usuario = cur.fetchone()

            if usuario is not None:
                token = secrets.token_urlsafe(32)
                expira_em = datetime.utcnow() + timedelta(minutes=TOKEN_VALIDADE_MINUTOS)
                cur.execute(
                    "INSERT INTO reset_tokens (token, usuario_id, expira_em) "
                    "VALUES (%s, %s, %s)",
                    (token, usuario["id"], expira_em),
                )
    finally:
        conn.close()

    # Sempre responde OK, exista ou não o e-mail — evita confirmar pra quem
    # está tentando adivinhar contas cadastradas se um e-mail existe ou não.
    if usuario is not None:
        link = f"{base_url}/resetar-senha?token={token}"
        enviar_email_reset(email, link)

    return jsonify(ok=True)


@app.route("/resetar-senha", methods=["POST"])
def resetar_senha():
    """Troca a senha usando o token do e-mail
    ---
    tags: [senha]
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required: [token, nova_senha]
            properties:
              token:
                type: string
                example: 3q2-7w9Jd0x...
              nova_senha:
                type: string
                example: outrasenha
    responses:
      200:
        description: Senha trocada; o token não serve mais.
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/Ok'
      400:
        description: Faltou campo, ou o token não existe, já foi usado ou expirou.
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/Erro'
            examples:
              incompleto:
                value: {"erro": "Dados incompletos."}
              invalido:
                value: {"erro": "Link inválido."}
              usado:
                value: {"erro": "Esse link já foi usado."}
              expirado:
                value: {"erro": "Esse link expirou. Peça um novo."}
    """
    dados = request.get_json(force=True, silent=True) or {}
    token = dados.get("token") or ""
    nova_senha = dados.get("nova_senha") or ""

    if not token or not nova_senha:
        return jsonify(erro="Dados incompletos."), 400

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT usuario_id, expira_em, usado FROM reset_tokens WHERE token = %s",
                (token,),
            )
            registro = cur.fetchone()

            if registro is None:
                return jsonify(erro="Link inválido."), 400
            if registro["usado"]:
                return jsonify(erro="Esse link já foi usado."), 400
            if registro["expira_em"] < datetime.utcnow():
                return jsonify(erro="Esse link expirou. Peça um novo."), 400

            senha_hash = generate_password_hash(nova_senha)
            cur.execute(
                "UPDATE usuarios SET senha_hash = %s WHERE id = %s",
                (senha_hash, registro["usuario_id"]),
            )
            cur.execute(
                "UPDATE reset_tokens SET usado = TRUE WHERE token = %s", (token,)
            )
    finally:
        conn.close()

    return jsonify(ok=True)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5001)))
