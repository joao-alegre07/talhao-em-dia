import os
from functools import wraps

import requests
from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

from .auditoria import ip_origem, registrar

auth_bp = Blueprint("auth", __name__)

# Quem se cadastra pela página aberta escolhe entre esses dois. Funcionário só
# entra pelo convite de uma propriedade, e admin nunca nasce pelo cadastro.
PAPEIS_DO_CADASTRO = {"produtor": "Sou produtor", "agronomo": "Sou agrônomo"}


def _auth_url(caminho):
    return os.environ["AUTH_SERVICE_URL"].rstrip("/") + caminho


def consultar_usuario(usuario_id):
    """Papel e plano atuais do usuário, direto do auth-service (Padrão A: nada
    disso é lido da sessão). None se o serviço não respondeu."""
    try:
        resp = requests.get(_auth_url(f"/usuarios/{usuario_id}"), timeout=5)
    except requests.exceptions.RequestException:
        return None

    if resp.status_code != 200:
        return None
    return resp.json()


def usuarios_por_id(ids):
    """{id: {nome, role}} de vários usuários numa chamada só. Se o auth-service
    não responder, volta vazio e a tela mostra só os ids."""
    ids = sorted({int(i) for i in ids if str(i).isdigit()})
    if not ids:
        return {}
    try:
        resp = requests.get(
            _auth_url("/usuarios"), params={"ids": ",".join(map(str, ids))}, timeout=5
        )
    except requests.exceptions.RequestException:
        return {}
    if resp.status_code != 200:
        return {}
    return {u["id"]: u for u in resp.json()}


def nomes_dos_usuarios(ids):
    return {i: u["nome"] for i, u in usuarios_por_id(ids).items()}


def criar_conta(nome, email, senha, papel):
    """Cadastra no auth-service. Devolve (id, None) ou (None, mensagem de erro)."""
    if not nome or not email or not senha:
        return None, "Preencha todos os campos."
    try:
        resp = requests.post(
            _auth_url("/cadastro"),
            json={"nome": nome, "email": email, "senha": senha, "papel": papel},
            timeout=5,
        )
    except requests.exceptions.RequestException:
        return None, "Serviço de login indisponível. Tente de novo."

    if resp.status_code == 201:
        return resp.json()["id"], None
    return None, resp.json().get("erro", "Não foi possível cadastrar.")


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "usuario_id" not in session:
            if request.path.startswith("/api/"):
                return jsonify(erro="Faça login primeiro."), 401
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)

    return wrapped


def pagina_inicial(papel):
    return url_for("admin.logs") if papel == "admin" else url_for("telas.talhoes")


@auth_bp.route("/cadastro", methods=["GET", "POST"])
def cadastro():
    if request.method == "GET":
        papel = request.args.get("papel", "produtor")
        return render_template("cadastro.html", papeis=PAPEIS_DO_CADASTRO, papel=papel)

    nome = request.form["nome"].strip()
    email = request.form["email"].strip().lower()
    senha = request.form["senha"]
    papel = request.form.get("papel", "produtor")

    if papel not in PAPEIS_DO_CADASTRO:
        return render_template(
            "cadastro.html", papeis=PAPEIS_DO_CADASTRO, papel="produtor", erro="Escolha um papel."
        ), 400

    usuario_id, erro = criar_conta(nome, email, senha, papel)
    if erro:
        return render_template("cadastro.html", papeis=PAPEIS_DO_CADASTRO, papel=papel, erro=erro)

    registrar("conta_criada", usuario_id=usuario_id, detalhes=papel)
    return redirect(url_for("auth.login", criada=1))


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html", proximo=request.args.get("proximo", ""))

    email = request.form["email"].strip().lower()
    senha = request.form["senha"]
    proximo = request.form.get("proximo", "")

    try:
        resp = requests.post(
            _auth_url("/login"),
            json={"email": email, "senha": senha, "ip": ip_origem()},
            timeout=5,
        )
    except requests.exceptions.RequestException:
        return render_template("login.html", erro="Serviço de login indisponível. Tente de novo.")

    if resp.status_code != 200:
        erro = resp.json().get("erro", "E-mail ou senha inválidos.")
        return render_template("login.html", erro=erro, proximo=proximo)

    dados = resp.json()
    session.clear()
    session["usuario_id"] = dados["usuario_id"]
    session["nome"] = dados["nome"]
    session["role"] = dados["role"]

    # Só volta pra um caminho do próprio site (o link do convite, por exemplo).
    if proximo.startswith("/") and not proximo.startswith(("//", "/\\")):
        return redirect(proximo)
    return redirect(pagina_inicial(dados["role"]))


@auth_bp.route("/logout")
def logout():
    if "usuario_id" in session:
        registrar("logout")
    session.clear()
    return redirect(url_for("inicio.landing"))


@auth_bp.route("/esqueci-senha", methods=["GET", "POST"])
def esqueci_senha():
    if request.method == "GET":
        return render_template("esqueci_senha.html")

    email = request.form["email"].strip().lower()
    base_url = os.environ.get("PUBLIC_APP_URL", request.url_root).rstrip("/")

    try:
        requests.post(
            _auth_url("/esqueci-senha"),
            json={"email": email, "base_url": base_url},
            timeout=5,
        )
    except requests.exceptions.RequestException:
        pass

    # Sempre mostra a mesma mensagem, exista ou não o e-mail cadastrado.
    return render_template(
        "esqueci_senha.html",
        mensagem="Se esse e-mail estiver cadastrado, você vai receber um link em instantes.",
    )


@auth_bp.route("/resetar-senha", methods=["GET", "POST"])
def resetar_senha():
    if request.method == "GET":
        token = request.args.get("token", "")
        return render_template("resetar_senha.html", token=token)

    token = request.form["token"]
    nova_senha = request.form["nova_senha"]

    try:
        resp = requests.post(
            _auth_url("/resetar-senha"),
            json={"token": token, "nova_senha": nova_senha},
            timeout=5,
        )
    except requests.exceptions.RequestException:
        return render_template(
            "resetar_senha.html", token=token, erro="Serviço de login indisponível. Tente de novo."
        )

    if resp.status_code != 200:
        erro = resp.json().get("erro", "Não foi possível trocar a senha.")
        return render_template("resetar_senha.html", token=token, erro=erro)

    return redirect(url_for("auth.login", redefinida=1))
