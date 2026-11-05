from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from . import caderno, storage
from .acesso import exigir, pode, propriedades_do_usuario, usuario_atual
from .auth import login_required, nomes_dos_usuarios
from .caderno import Conflito, Invalido

telas_bp = Blueprint("telas", __name__)


# --- talhões ---------------------------------------------------------------


@telas_bp.route("/talhoes")
@login_required
def talhoes():
    usuario = usuario_atual()
    if usuario["papel"] == "admin":
        return redirect(url_for("admin.logs"))

    propriedades = propriedades_do_usuario(usuario["id"])
    if not propriedades and usuario["papel"] == "produtor":
        return redirect(url_for("propriedade.nova"))

    return render_template(
        "talhoes.html",
        propriedades=propriedades,
        talhoes=caderno.listar_talhoes(),
        pode_editar=pode(usuario, "talhoes"),
        pode_registrar=pode(usuario, "aplicacoes"),
    )


@telas_bp.route("/talhoes/novo", methods=["GET", "POST"])
@login_required
def novo_talhao():
    exigir("talhoes")
    if request.method == "POST":
        try:
            talhao_id = caderno.criar_talhao(request.form)
        except (Invalido, Conflito) as e:
            status = 409 if isinstance(e, Conflito) else 400
            return render_template("talhao_form.html", dados=request.form, erro=str(e)), status
        flash("Talhão cadastrado.")
        return redirect(url_for("telas.talhao", talhao_id=talhao_id))

    return render_template("talhao_form.html", dados={"cultura": "Café arábica"})


@telas_bp.route("/talhoes/<int:talhao_id>")
@login_required
def talhao(talhao_id):
    usuario = usuario_atual()
    talhao = caderno.obter_talhao(talhao_id)
    return render_template(
        "talhao.html",
        talhao=talhao,
        aplicacoes=caderno.listar_aplicacoes(talhao_id),
        pode_editar=pode(usuario, "talhoes") and talhao["dono_id"] == usuario["id"],
        pode_registrar=pode(usuario, "aplicacoes"),
    )


@telas_bp.route("/talhoes/<int:talhao_id>/editar", methods=["GET", "POST"])
@login_required
def editar_talhao(talhao_id):
    usuario = exigir("talhoes")
    talhao = caderno.obter_talhao(talhao_id)
    if talhao["dono_id"] != usuario["id"]:
        abort(403)

    if request.method == "POST":
        try:
            caderno.editar_talhao(talhao_id, request.form)
        except (Invalido, Conflito) as e:
            status = 409 if isinstance(e, Conflito) else 400
            return (
                render_template("talhao_form.html", talhao=talhao, dados=request.form, erro=str(e)),
                status,
            )
        flash("Talhão atualizado.")
        return redirect(url_for("telas.talhao", talhao_id=talhao_id))

    return render_template("talhao_form.html", talhao=talhao, dados=talhao)


@telas_bp.route("/talhoes/<int:talhao_id>/apagar", methods=["POST"])
@login_required
def apagar_talhao(talhao_id):
    try:
        caderno.apagar_talhao(talhao_id)
    except Conflito as e:
        flash(str(e), "erro")
        return redirect(url_for("telas.talhao", talhao_id=talhao_id))
    flash("Talhão apagado.")
    return redirect(url_for("telas.talhoes"))


# --- produtos --------------------------------------------------------------


@telas_bp.route("/produtos", methods=["GET", "POST"])
@login_required
def produtos():
    usuario = usuario_atual()
    erro, status, dados = None, 200, {"unidade": "L"}

    if request.method == "POST":
        try:
            caderno.criar_produto(request.form)
        except (Invalido, Conflito) as e:
            erro, dados = str(e), request.form
            status = 409 if isinstance(e, Conflito) else 400
        else:
            flash("Produto cadastrado.")
            return redirect(url_for("telas.produtos"))

    return (
        render_template(
            "produtos.html",
            produtos=caderno.listar_produtos(),
            pode_editar=pode(usuario, "produtos"),
            dados=dados,
            erro=erro,
        ),
        status,
    )


@telas_bp.route("/produtos/<int:produto_id>/editar", methods=["GET", "POST"])
@login_required
def editar_produto(produto_id):
    produto = caderno.obter_produto_para_editar(produto_id)

    if request.method == "POST":
        try:
            caderno.editar_produto(produto_id, request.form)
        except (Invalido, Conflito) as e:
            status = 409 if isinstance(e, Conflito) else 400
            return (
                render_template("produto_form.html", produto=produto, dados=request.form, erro=str(e)),
                status,
            )
        flash("Produto atualizado.")
        return redirect(url_for("telas.produtos"))

    return render_template("produto_form.html", produto=produto, dados=produto)


@telas_bp.route("/produtos/<int:produto_id>/apagar", methods=["POST"])
@login_required
def apagar_produto(produto_id):
    try:
        caderno.apagar_produto(produto_id)
    except Conflito as e:
        flash(str(e), "erro")
    else:
        flash("Produto apagado.")
    return redirect(url_for("telas.produtos"))


# --- aplicações ------------------------------------------------------------


@telas_bp.route("/aplicacoes")
@login_required
def aplicacoes():
    usuario = usuario_atual()
    talhao_id = request.args.get("talhao_id", type=int)
    return render_template(
        "aplicacoes.html",
        aplicacoes=caderno.listar_aplicacoes(talhao_id),
        talhoes=caderno.listar_talhoes(),
        talhao_id=talhao_id,
        pode_registrar=pode(usuario, "aplicacoes"),
    )


def _form_aplicacao(dados, aplicacao=None, erro=None, status=200):
    return (
        render_template(
            "aplicacao_form.html",
            aplicacao=aplicacao,
            dados=dados,
            talhoes=caderno.listar_talhoes(),
            produtos=caderno.listar_produtos(),
            receita_max_mb=caderno.RECEITA_TAMANHO_MAX // (1024 * 1024),
            erro=erro,
        ),
        status,
    )


@telas_bp.route("/aplicacoes/nova", methods=["GET", "POST"])
@login_required
def nova_aplicacao():
    usuario = exigir("aplicacoes")
    if request.method == "POST":
        try:
            aplicacao_id = caderno.registrar_aplicacao(request.form, request.files.get("receita"))
        except Invalido as e:
            return _form_aplicacao(request.form, erro=str(e), status=400)
        flash("Aplicação registrada no caderno.")
        return redirect(url_for("telas.aplicacao", aplicacao_id=aplicacao_id))

    return _form_aplicacao(
        {
            "talhao_id": request.args.get("talhao_id", type=int),
            "data_aplicacao": caderno.hoje().isoformat(),
            "aplicador": usuario["nome"],
        }
    )


@telas_bp.route("/aplicacoes/<int:aplicacao_id>")
@login_required
def aplicacao(aplicacao_id):
    usuario = usuario_atual()
    aplicacao = caderno.obter_aplicacao(aplicacao_id)
    receita_url = storage.url_temporaria(aplicacao["receita_key"]) if aplicacao["receita_key"] else None
    return render_template(
        "aplicacao.html",
        aplicacao=aplicacao,
        receita_url=receita_url,
        receita_pdf=(aplicacao["receita_key"] or "").endswith(".pdf"),
        registrado_por=nomes_dos_usuarios([aplicacao["registrado_por"]]).get(aplicacao["registrado_por"]),
        pode_alterar=caderno.pode_alterar_aplicacao(usuario, aplicacao),
        em_carencia=aplicacao["libera_em"] > caderno.hoje(),
    )


@telas_bp.route("/aplicacoes/<int:aplicacao_id>/editar", methods=["GET", "POST"])
@login_required
def editar_aplicacao(aplicacao_id):
    usuario = exigir("aplicacoes")
    aplicacao = caderno.obter_aplicacao(aplicacao_id)
    if not caderno.pode_alterar_aplicacao(usuario, aplicacao):
        abort(403)

    if request.method == "POST":
        try:
            caderno.editar_aplicacao(aplicacao_id, request.form, request.files.get("receita"))
        except Invalido as e:
            return _form_aplicacao(request.form, aplicacao, erro=str(e), status=400)
        flash("Aplicação atualizada.")
        return redirect(url_for("telas.aplicacao", aplicacao_id=aplicacao_id))

    dados = dict(aplicacao, data_aplicacao=aplicacao["data_aplicacao"].isoformat())
    return _form_aplicacao(dados, aplicacao)


@telas_bp.route("/aplicacoes/<int:aplicacao_id>/apagar", methods=["POST"])
@login_required
def apagar_aplicacao(aplicacao_id):
    caderno.apagar_aplicacao(aplicacao_id)
    flash("Aplicação apagada do caderno.")
    return redirect(url_for("telas.aplicacoes"))
