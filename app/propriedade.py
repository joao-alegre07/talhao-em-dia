import os
import secrets
from datetime import datetime, timedelta, timezone

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for

from .acesso import NOMES_DOS_PAPEIS, exigir, propriedade_do_produtor, usuario_atual
from .auditoria import registrar
from .auth import criar_conta, login_required, usuarios_por_id
from .db import get_connection

propriedade_bp = Blueprint("propriedade", __name__)

CONVITE_VALIDADE_DIAS = 7
PAPEIS_DO_CONVITE = ("funcionario", "agronomo")


def _agora():
    # Igual ao banco: UTC, sem fuso na coluna.
    return datetime.now(timezone.utc).replace(tzinfo=None)


@propriedade_bp.route("/propriedade/nova", methods=["GET", "POST"])
@login_required
def nova():
    usuario = usuario_atual()
    if usuario["papel"] != "produtor":
        abort(403)
    if propriedade_do_produtor(usuario["id"]) is not None:
        return redirect(url_for("telas.talhoes"))

    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        municipio = request.form.get("municipio", "").strip()
        if not nome or not municipio or len(nome) > 100 or len(municipio) > 100:
            return render_template(
                "propriedade_nova.html", dados=request.form, erro="Preencha o nome e o município."
            ), 400

        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO propriedades (dono_id, nome, municipio) VALUES (%s, %s, %s)",
                    (usuario["id"], nome, municipio),
                )
                propriedade_id = cur.lastrowid
                cur.execute(
                    "INSERT INTO membros (propriedade_id, usuario_id) VALUES (%s, %s)",
                    (propriedade_id, usuario["id"]),
                )
        finally:
            conn.close()

        registrar("propriedade_criada", detalhes=f"propriedade {nome} ({propriedade_id}), {municipio}")
        flash("Propriedade cadastrada. Agora cadastre os talhões.")
        return redirect(url_for("telas.novo_talhao"))

    return render_template("propriedade_nova.html", dados={})


def _link_do_convite(token):
    base = os.environ.get("PUBLIC_APP_URL", request.url_root).rstrip("/")
    return base + url_for("propriedade.convite", token=token)


@propriedade_bp.route("/equipe")
@login_required
def equipe():
    usuario = exigir("equipe")
    propriedade = propriedade_do_produtor(usuario["id"])
    if propriedade is None:
        return redirect(url_for("propriedade.nova"))

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT usuario_id, entrou_em FROM membros WHERE propriedade_id = %s ORDER BY entrou_em",
                (propriedade["id"],),
            )
            membros = cur.fetchall()
            cur.execute(
                "SELECT token, papel, expira_em FROM convites "
                "WHERE propriedade_id = %s AND usado_por IS NULL AND expira_em > %s "
                "ORDER BY criado_em DESC",
                (propriedade["id"], _agora()),
            )
            convites = cur.fetchall()
    finally:
        conn.close()

    # Nome e papel moram no auth-service; aqui só tem o id de cada membro.
    usuarios = usuarios_por_id([m["usuario_id"] for m in membros])
    for m in membros:
        dados = usuarios.get(m["usuario_id"], {})
        m["nome"] = dados.get("nome", f"usuário {m['usuario_id']}")
        m["papel"] = dados.get("role")
        m["dono"] = m["usuario_id"] == propriedade["dono_id"]
    for c in convites:
        c["link"] = _link_do_convite(c["token"])

    return render_template(
        "equipe.html",
        propriedade=propriedade,
        membros=membros,
        convites=convites,
        papeis=NOMES_DOS_PAPEIS,
        novo=request.args.get("novo"),
    )


@propriedade_bp.route("/equipe/convites", methods=["POST"])
@login_required
def convidar():
    usuario = exigir("equipe")
    propriedade = propriedade_do_produtor(usuario["id"])
    papel = request.form.get("papel")
    if propriedade is None or papel not in PAPEIS_DO_CONVITE:
        abort(400)

    token = secrets.token_urlsafe(24)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO convites (token, propriedade_id, papel, criado_por, expira_em) "
                "VALUES (%s, %s, %s, %s, %s)",
                (
                    token,
                    propriedade["id"],
                    papel,
                    usuario["id"],
                    _agora() + timedelta(days=CONVITE_VALIDADE_DIAS),
                ),
            )
    finally:
        conn.close()

    registrar(
        "convite_criado",
        detalhes=f"{papel} na propriedade {propriedade['nome']} ({propriedade['id']})",
    )
    return redirect(url_for("propriedade.equipe", novo=token))


def _convite_valido(cur, token):
    cur.execute(
        "SELECT c.token, c.propriedade_id, c.papel, c.expira_em, c.usado_por, "
        "p.nome AS propriedade, p.municipio FROM convites c "
        "JOIN propriedades p ON p.id = c.propriedade_id WHERE c.token = %s",
        (token,),
    )
    convite = cur.fetchone()
    if convite is None or convite["usado_por"] is not None or convite["expira_em"] < _agora():
        return None
    return convite


def _entrar_na_propriedade(cur, convite, usuario_id):
    cur.execute(
        "INSERT IGNORE INTO membros (propriedade_id, usuario_id) VALUES (%s, %s)",
        (convite["propriedade_id"], usuario_id),
    )
    cur.execute(
        "UPDATE convites SET usado_por = %s, usado_em = %s WHERE token = %s",
        (usuario_id, _agora(), convite["token"]),
    )


@propriedade_bp.route("/convite/<token>", methods=["GET", "POST"])
def convite(token):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            convite = _convite_valido(cur, token)
            if convite is None:
                return render_template("convite.html", convite=None), 404

            logado = "usuario_id" in session
            # Agrônomo que já tem conta só aceita: ele acompanha várias
            # propriedades com o mesmo login.
            if logado:
                usuario = usuario_atual()
                if request.method == "POST" and convite["papel"] == "agronomo" == usuario["papel"]:
                    _entrar_na_propriedade(cur, convite, usuario["id"])
                    registrar(
                        "convite_aceito",
                        detalhes=f"agronomo na propriedade {convite['propriedade']} "
                        f"({convite['propriedade_id']})",
                    )
                    flash(f"Agora você acompanha a propriedade {convite['propriedade']}.")
                    return redirect(url_for("telas.talhoes"))
                return render_template("convite.html", convite=convite, usuario=usuario)

            if request.method == "POST":
                nome = request.form.get("nome", "").strip()
                email = request.form.get("email", "").strip().lower()
                senha = request.form.get("senha", "")
                usuario_id, erro = criar_conta(nome, email, senha, convite["papel"])
                if erro:
                    return render_template("convite.html", convite=convite, dados=request.form, erro=erro)
                _entrar_na_propriedade(cur, convite, usuario_id)
                registrar(
                    "convite_aceito",
                    usuario_id=usuario_id,
                    detalhes=f"{convite['papel']} na propriedade {convite['propriedade']} "
                    f"({convite['propriedade_id']})",
                )
                return redirect(url_for("auth.login", criada=1))

            return render_template("convite.html", convite=convite, dados={})
    finally:
        conn.close()
