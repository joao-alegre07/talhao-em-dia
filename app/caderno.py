"""Regras do caderno de campo: talhões, produtos e aplicações.

As telas e a API chamam as mesmas funções daqui, então a checagem de papel
(403) e o filtro por propriedade (404) valem igual pros dois caminhos. Toda
consulta passa pela tabela membros: o que não é da propriedade de quem está
logado simplesmente não aparece, e pra quem pede é como se não existisse.
"""

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

import pymysql
from botocore.exceptions import BotoCoreError, ClientError
from flask import abort

from . import storage
from .acesso import exigir, propriedade_do_produtor, usuario_atual
from .auditoria import registrar
from .db import get_connection

BRASILIA = timezone(timedelta(hours=-3))
RECEITA_TAMANHO_MAX = 8 * 1024 * 1024
UNIDADES = ("L", "kg")
CARENCIA_MAX_DIAS = 365


class Invalido(Exception):
    """Dado que não passa na validação (400)."""


class Conflito(Exception):
    """A ação esbarra em outro registro (409)."""


def hoje():
    # O servidor roda em UTC; a carência é contada no dia de Brasília.
    return datetime.now(BRASILIA).date()


def br(valor):
    """2.5 -> "2,50", do jeito que o produtor escreve."""
    return f"{valor:.2f}".replace(".", ",")


# --- validação -------------------------------------------------------------


def _texto(dados, campo, nome, maximo, obrigatorio=True):
    valor = str(dados.get(campo) or "").strip()
    if obrigatorio and not valor:
        raise Invalido(f"Preencha {nome}.")
    if len(valor) > maximo:
        raise Invalido(f"{nome.capitalize()} pode ter no máximo {maximo} caracteres.")
    return valor


def _decimal(dados, campo, nome, maximo):
    bruto = str(dados.get(campo) if dados.get(campo) is not None else "").strip()
    try:
        valor = Decimal(bruto.replace(",", "."))
    except InvalidOperation:
        raise Invalido(f"Informe {nome} em número.")
    if not valor.is_finite() or valor <= 0 or valor > maximo:
        raise Invalido(f"{nome.capitalize()} tem que ser maior que zero e até {br(maximo)}.")
    return valor.quantize(Decimal("0.01"))


def _inteiro(dados, campo, nome):
    try:
        return int(str(dados.get(campo)).strip())
    except (TypeError, ValueError):
        raise Invalido(f"Escolha {nome}.")


def _data(dados, campo):
    try:
        valor = date.fromisoformat(str(dados.get(campo) or "").strip())
    except ValueError:
        raise Invalido("Informe a data da aplicação.")
    if valor > hoje():
        raise Invalido("A data da aplicação não pode ser no futuro.")
    return valor


def ler_talhao(dados):
    return {
        "nome": _texto(dados, "nome", "o nome", 60),
        "area_ha": _decimal(dados, "area_ha", "a área", Decimal("99999")),
        "cultura": _texto(dados, "cultura", "a cultura", 60),
    }


def ler_produto(dados):
    try:
        carencia = int(str(dados.get("carencia_dias")).strip())
    except (TypeError, ValueError):
        raise Invalido("Informe a carência em dias, como está na bula.")
    if not 0 <= carencia <= CARENCIA_MAX_DIAS:
        raise Invalido(f"A carência tem que ficar entre 0 e {CARENCIA_MAX_DIAS} dias.")

    unidade = str(dados.get("unidade") or "")
    if unidade not in UNIDADES:
        raise Invalido("Escolha a unidade da dose: L ou kg por hectare.")

    return {
        "nome": _texto(dados, "nome", "o nome do produto", 100),
        "carencia_dias": carencia,
        "unidade": unidade,
    }


def ler_aplicacao(dados):
    return {
        "talhao_id": _inteiro(dados, "talhao_id", "o talhão"),
        "produto_id": _inteiro(dados, "produto_id", "o produto"),
        "data_aplicacao": _data(dados, "data_aplicacao"),
        "dose": _decimal(dados, "dose", "a dose", Decimal("9999")),
        "aplicador": _texto(dados, "aplicador", "quem aplicou", 100),
        "observacao": _texto(dados, "observacao", "a observação", 500, obrigatorio=False),
    }


def _tipo_do_arquivo(dados):
    """Olha os primeiros bytes em vez de confiar na extensão ou no
    Content-Type, que o cliente controla."""
    if dados.startswith(b"\xff\xd8\xff"):
        return "jpg", "image/jpeg"
    if dados.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png", "image/png"
    if dados[:4] == b"RIFF" and dados[8:12] == b"WEBP":
        return "webp", "image/webp"
    if dados.startswith(b"%PDF-"):
        return "pdf", "application/pdf"
    return None


def ler_receita(arquivo):
    """(bytes, extensão, content-type) da foto ou PDF da receita, ou None se
    nada foi enviado."""
    if arquivo is None or not arquivo.filename:
        return None
    dados = arquivo.read(RECEITA_TAMANHO_MAX + 1)
    if len(dados) > RECEITA_TAMANHO_MAX:
        raise Invalido(f"A receita pode ter no máximo {RECEITA_TAMANHO_MAX // (1024 * 1024)} MB.")
    tipo = _tipo_do_arquivo(dados)
    if tipo is None:
        raise Invalido("A receita tem que ser foto (JPG, PNG ou WebP) ou PDF.")
    return (dados, *tipo)


def _guardar_receita(receita, propriedade_id):
    dados, extensao, content_type = receita
    chave = f"propriedades/{propriedade_id}/receitas/{uuid.uuid4().hex}.{extensao}"
    try:
        storage.enviar(chave, dados, content_type)
    except (BotoCoreError, ClientError):
        abort(503)
    return chave


def _apagar_receita(chave):
    if not chave:
        return
    try:
        storage.apagar(chave)
    except (BotoCoreError, ClientError):
        pass


# --- talhões ---------------------------------------------------------------

_TALHOES = (
    "SELECT t.id, t.propriedade_id, t.nome, t.area_ha, t.cultura, "
    "pr.nome AS propriedade, pr.dono_id, COUNT(a.id) AS total_aplicacoes, "
    "MAX(DATE_ADD(a.data_aplicacao, INTERVAL p.carencia_dias DAY)) AS liberado_em "
    "FROM talhoes t "
    "JOIN propriedades pr ON pr.id = t.propriedade_id "
    "JOIN membros m ON m.propriedade_id = t.propriedade_id AND m.usuario_id = %s "
    "LEFT JOIN aplicacoes a ON a.talhao_id = t.id "
    "LEFT JOIN produtos p ON p.id = a.produto_id "
)


def _com_carencia(talhao):
    # Liberado pra colher no dia em que vence a carência mais longa entre
    # todas as aplicações registradas no talhão.
    liberado_em = talhao["liberado_em"]
    talhao["em_carencia"] = liberado_em is not None and liberado_em > hoje()
    talhao["dias_restantes"] = (liberado_em - hoje()).days if talhao["em_carencia"] else 0
    return talhao


def listar_talhoes():
    usuario = usuario_atual()
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(_TALHOES + "GROUP BY t.id ORDER BY pr.nome, t.nome", (usuario["id"],))
            return [_com_carencia(t) for t in cur.fetchall()]
    finally:
        conn.close()


def obter_talhao(talhao_id):
    usuario = usuario_atual()
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(_TALHOES + "WHERE t.id = %s GROUP BY t.id", (usuario["id"], talhao_id))
            talhao = cur.fetchone()
    finally:
        conn.close()
    if talhao is None:
        abort(404)
    return _com_carencia(talhao)


def _talhao_do_dono(cur, usuario, talhao_id):
    cur.execute(
        "SELECT t.id, t.nome, t.area_ha, t.cultura, pr.dono_id FROM talhoes t "
        "JOIN propriedades pr ON pr.id = t.propriedade_id "
        "JOIN membros m ON m.propriedade_id = t.propriedade_id AND m.usuario_id = %s "
        "WHERE t.id = %s",
        (usuario["id"], talhao_id),
    )
    talhao = cur.fetchone()
    if talhao is None:
        abort(404)
    if talhao["dono_id"] != usuario["id"]:
        abort(403)
    return talhao


def criar_talhao(dados):
    usuario = exigir("talhoes")
    campos = ler_talhao(dados)
    propriedade = propriedade_do_produtor(usuario["id"])
    if propriedade is None:
        raise Invalido("Cadastre a propriedade antes dos talhões.")

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO talhoes (propriedade_id, nome, area_ha, cultura) "
                "VALUES (%s, %s, %s, %s)",
                (propriedade["id"], campos["nome"], campos["area_ha"], campos["cultura"]),
            )
            talhao_id = cur.lastrowid
    except pymysql.err.IntegrityError:
        raise Conflito("Já existe um talhão com esse nome na propriedade.")
    finally:
        conn.close()

    registrar(
        "talhao_criado",
        detalhes=f"talhão {campos['nome']} ({talhao_id}), {br(campos['area_ha'])} ha de "
        f"{campos['cultura']}, na propriedade {propriedade['nome']} ({propriedade['id']})",
    )
    return talhao_id


def editar_talhao(talhao_id, dados):
    usuario = exigir("talhoes")
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            atual = _talhao_do_dono(cur, usuario, talhao_id)
            campos = ler_talhao(dados)
            cur.execute(
                "UPDATE talhoes SET nome = %s, area_ha = %s, cultura = %s WHERE id = %s",
                (campos["nome"], campos["area_ha"], campos["cultura"], talhao_id),
            )
    except pymysql.err.IntegrityError:
        raise Conflito("Já existe um talhão com esse nome na propriedade.")
    finally:
        conn.close()

    mudancas = _diferencas(
        atual,
        campos,
        {"nome": "nome", "area_ha": "área", "cultura": "cultura"},
    )
    if mudancas:
        registrar("talhao_editado", detalhes=f"talhão {atual['nome']} ({talhao_id}): {mudancas}")


def apagar_talhao(talhao_id):
    usuario = exigir("talhoes")
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            talhao = _talhao_do_dono(cur, usuario, talhao_id)
            cur.execute("SELECT COUNT(*) AS total FROM aplicacoes WHERE talhao_id = %s", (talhao_id,))
            if cur.fetchone()["total"]:
                raise Conflito(
                    "Esse talhão tem aplicações no caderno. Pra não perder o histórico, apague "
                    "as aplicações antes."
                )
            cur.execute("DELETE FROM talhoes WHERE id = %s", (talhao_id,))
    finally:
        conn.close()

    registrar("talhao_apagado", detalhes=f"talhão {talhao['nome']} ({talhao_id})")


# --- produtos --------------------------------------------------------------


def listar_produtos():
    usuario = usuario_atual()
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT p.id, p.propriedade_id, p.nome, p.carencia_dias, p.unidade, "
                "pr.nome AS propriedade, "
                "(SELECT COUNT(*) FROM aplicacoes a WHERE a.produto_id = p.id) AS total_aplicacoes "
                "FROM produtos p "
                "JOIN propriedades pr ON pr.id = p.propriedade_id "
                "JOIN membros m ON m.propriedade_id = p.propriedade_id AND m.usuario_id = %s "
                "ORDER BY pr.nome, p.nome",
                (usuario["id"],),
            )
            return cur.fetchall()
    finally:
        conn.close()


def _produto_do_dono(cur, usuario, produto_id):
    cur.execute(
        "SELECT p.id, p.nome, p.carencia_dias, p.unidade, pr.dono_id FROM produtos p "
        "JOIN propriedades pr ON pr.id = p.propriedade_id "
        "JOIN membros m ON m.propriedade_id = p.propriedade_id AND m.usuario_id = %s "
        "WHERE p.id = %s",
        (usuario["id"], produto_id),
    )
    produto = cur.fetchone()
    if produto is None:
        abort(404)
    if produto["dono_id"] != usuario["id"]:
        abort(403)
    return produto


def obter_produto_para_editar(produto_id):
    usuario = exigir("produtos")
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            return _produto_do_dono(cur, usuario, produto_id)
    finally:
        conn.close()


def criar_produto(dados):
    usuario = exigir("produtos")
    campos = ler_produto(dados)
    propriedade = propriedade_do_produtor(usuario["id"])
    if propriedade is None:
        raise Invalido("Cadastre a propriedade antes dos produtos.")

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO produtos (propriedade_id, nome, carencia_dias, unidade) "
                "VALUES (%s, %s, %s, %s)",
                (propriedade["id"], campos["nome"], campos["carencia_dias"], campos["unidade"]),
            )
            produto_id = cur.lastrowid
    except pymysql.err.IntegrityError:
        raise Conflito("Esse produto já está cadastrado.")
    finally:
        conn.close()

    registrar(
        "produto_cadastrado",
        detalhes=f"produto {campos['nome']} ({produto_id}), carência de "
        f"{campos['carencia_dias']} dias",
    )
    return produto_id


def editar_produto(produto_id, dados):
    usuario = exigir("produtos")
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            atual = _produto_do_dono(cur, usuario, produto_id)
            campos = ler_produto(dados)
            cur.execute(
                "UPDATE produtos SET nome = %s, carencia_dias = %s, unidade = %s WHERE id = %s",
                (campos["nome"], campos["carencia_dias"], campos["unidade"], produto_id),
            )
    except pymysql.err.IntegrityError:
        raise Conflito("Esse produto já está cadastrado.")
    finally:
        conn.close()

    mudancas = _diferencas(
        atual, campos, {"nome": "nome", "carencia_dias": "carência", "unidade": "unidade"}
    )
    if mudancas:
        registrar("produto_editado", detalhes=f"produto {atual['nome']} ({produto_id}): {mudancas}")


def apagar_produto(produto_id):
    usuario = exigir("produtos")
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            produto = _produto_do_dono(cur, usuario, produto_id)
            cur.execute("SELECT COUNT(*) AS total FROM aplicacoes WHERE produto_id = %s", (produto_id,))
            if cur.fetchone()["total"]:
                raise Conflito(
                    "Esse produto aparece em aplicações do caderno e não pode ser apagado."
                )
            cur.execute("DELETE FROM produtos WHERE id = %s", (produto_id,))
    finally:
        conn.close()

    registrar("produto_apagado", detalhes=f"produto {produto['nome']} ({produto_id})")


# --- aplicações ------------------------------------------------------------

_APLICACOES = (
    "SELECT a.id, a.talhao_id, a.produto_id, a.data_aplicacao, a.dose, a.aplicador, "
    "a.observacao, a.receita_key, a.registrado_por, a.criado_em, a.atualizado_em, "
    "t.nome AS talhao, t.propriedade_id, pr.nome AS propriedade, pr.dono_id, "
    "p.nome AS produto, p.unidade, p.carencia_dias, "
    "DATE_ADD(a.data_aplicacao, INTERVAL p.carencia_dias DAY) AS libera_em "
    "FROM aplicacoes a "
    "JOIN talhoes t ON t.id = a.talhao_id "
    "JOIN propriedades pr ON pr.id = t.propriedade_id "
    "JOIN produtos p ON p.id = a.produto_id "
    "JOIN membros m ON m.propriedade_id = t.propriedade_id AND m.usuario_id = %s "
)


def listar_aplicacoes(talhao_id=None):
    usuario = usuario_atual()
    sql = _APLICACOES
    params = [usuario["id"]]
    if talhao_id is not None:
        sql += "WHERE a.talhao_id = %s "
        params.append(talhao_id)

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql + "ORDER BY a.data_aplicacao DESC, a.id DESC", params)
            return cur.fetchall()
    finally:
        conn.close()


def obter_aplicacao(aplicacao_id):
    usuario = usuario_atual()
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(_APLICACOES + "WHERE a.id = %s", (usuario["id"], aplicacao_id))
            aplicacao = cur.fetchone()
    finally:
        conn.close()
    if aplicacao is None:
        abort(404)
    return aplicacao


def pode_alterar_aplicacao(usuario, aplicacao):
    # Produtor mexe em qualquer aplicação da propriedade dele; funcionário só
    # nas que ele mesmo registrou.
    if usuario["papel"] == "produtor":
        return aplicacao["dono_id"] == usuario["id"]
    if usuario["papel"] == "funcionario":
        return aplicacao["registrado_por"] == usuario["id"]
    return False


def _aplicacao_para_alterar(cur, usuario, aplicacao_id):
    cur.execute(_APLICACOES + "WHERE a.id = %s", (usuario["id"], aplicacao_id))
    aplicacao = cur.fetchone()
    if aplicacao is None:
        abort(404)
    if not pode_alterar_aplicacao(usuario, aplicacao):
        abort(403)
    return aplicacao


def _talhao_e_produto(cur, usuario, campos):
    """O talhão tem que ser de uma propriedade do usuário e o produto, da mesma
    propriedade do talhão. A mensagem é a mesma exista ou não o id, pra não
    contar nada sobre o que é dos outros."""
    cur.execute(
        "SELECT t.id, t.nome, t.propriedade_id FROM talhoes t "
        "JOIN membros m ON m.propriedade_id = t.propriedade_id AND m.usuario_id = %s "
        "WHERE t.id = %s",
        (usuario["id"], campos["talhao_id"]),
    )
    talhao = cur.fetchone()
    if talhao is None:
        raise Invalido("Escolha um talhão da sua propriedade.")

    cur.execute(
        "SELECT id, nome, unidade FROM produtos WHERE id = %s AND propriedade_id = %s",
        (campos["produto_id"], talhao["propriedade_id"]),
    )
    produto = cur.fetchone()
    if produto is None:
        raise Invalido("Escolha um produto cadastrado na propriedade do talhão.")
    return talhao, produto


def _resumo(aplicacao_id, talhao, produto, campos):
    return (
        f"aplicação {aplicacao_id}: {produto['nome']}, {br(campos['dose'])} "
        f"{produto['unidade']}/ha no talhão {talhao['nome']} ({talhao['id']}) em "
        f"{campos['data_aplicacao']:%d/%m/%Y}, aplicado por {campos['aplicador']}"
    )


def registrar_aplicacao(dados, arquivo=None):
    usuario = exigir("aplicacoes")
    campos = ler_aplicacao(dados)
    receita = ler_receita(arquivo)

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            talhao, produto = _talhao_e_produto(cur, usuario, campos)
            chave = _guardar_receita(receita, talhao["propriedade_id"]) if receita else None
            cur.execute(
                "INSERT INTO aplicacoes (talhao_id, produto_id, data_aplicacao, dose, aplicador, "
                "observacao, receita_key, registrado_por) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    talhao["id"],
                    produto["id"],
                    campos["data_aplicacao"],
                    campos["dose"],
                    campos["aplicador"],
                    campos["observacao"],
                    chave,
                    usuario["id"],
                ),
            )
            aplicacao_id = cur.lastrowid
    finally:
        conn.close()

    detalhes = _resumo(aplicacao_id, talhao, produto, campos)
    registrar("aplicacao_registrada", detalhes=detalhes + (", com receita" if chave else ""))
    return aplicacao_id


def editar_aplicacao(aplicacao_id, dados, arquivo=None):
    usuario = exigir("aplicacoes")
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            atual = _aplicacao_para_alterar(cur, usuario, aplicacao_id)
            campos = ler_aplicacao(dados)
            receita = ler_receita(arquivo)
            talhao, produto = _talhao_e_produto(cur, usuario, campos)
            if talhao["propriedade_id"] != atual["propriedade_id"]:
                raise Invalido("A aplicação não pode mudar de propriedade.")

            chave = _guardar_receita(receita, talhao["propriedade_id"]) if receita else None
            cur.execute(
                "UPDATE aplicacoes SET talhao_id = %s, produto_id = %s, data_aplicacao = %s, "
                "dose = %s, aplicador = %s, observacao = %s, "
                "receita_key = COALESCE(%s, receita_key) WHERE id = %s",
                (
                    talhao["id"],
                    produto["id"],
                    campos["data_aplicacao"],
                    campos["dose"],
                    campos["aplicador"],
                    campos["observacao"],
                    chave,
                    aplicacao_id,
                ),
            )
    finally:
        conn.close()

    # A receita antiga só sai do storage depois que o banco já aponta pra nova.
    if chave:
        _apagar_receita(atual["receita_key"])

    depois = dict(campos, talhao=talhao["nome"], produto=produto["nome"])
    mudancas = _diferencas(
        atual,
        depois,
        {
            "talhao": "talhão",
            "produto": "produto",
            "data_aplicacao": "data",
            "dose": "dose",
            "aplicador": "aplicado por",
            "observacao": "observação",
        },
    )
    if chave:
        mudancas = (mudancas + "; " if mudancas else "") + "receita nova"
    registrar(
        "aplicacao_editada",
        detalhes=f"aplicação {aplicacao_id}: {mudancas or 'nada mudou'}",
    )


def apagar_aplicacao(aplicacao_id):
    usuario = exigir("aplicacoes")
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            atual = _aplicacao_para_alterar(cur, usuario, aplicacao_id)
            cur.execute("DELETE FROM aplicacoes WHERE id = %s", (aplicacao_id,))
    finally:
        conn.close()

    _apagar_receita(atual["receita_key"])
    talhao = {"id": atual["talhao_id"], "nome": atual["talhao"]}
    produto = {"nome": atual["produto"], "unidade": atual["unidade"]}
    registrar("aplicacao_apagada", detalhes=_resumo(aplicacao_id, talhao, produto, atual))


def _diferencas(antes, depois, rotulos):
    """ "dose 2,50 → 3,00; data 27/10/2026 → 26/10/2026" com o que mudou."""
    partes = []
    for campo, rotulo in rotulos.items():
        a, d = antes[campo], depois[campo]
        if isinstance(a, Decimal) or isinstance(d, Decimal):
            if Decimal(a) == Decimal(d):
                continue
            a, d = br(Decimal(a)), br(Decimal(d))
        elif isinstance(a, date):
            if a == d:
                continue
            a, d = f"{a:%d/%m/%Y}", f"{d:%d/%m/%Y}"
        elif a == d:
            continue
        partes.append(f"{rotulo} {a or '—'} → {d or '—'}")
    return "; ".join(partes)
