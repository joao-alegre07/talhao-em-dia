from flask import abort, g, session

from .auth import consultar_usuario
from .db import get_connection

# O que cada papel pode alterar. Ver os dados de uma propriedade é liberado pra
# qualquer membro dela; o resto depende do papel, e o papel é perguntado ao
# auth-service em toda requisição (Padrão A), nunca lido da sessão.
PERMISSOES = {
    "produtor": {"talhoes", "produtos", "aplicacoes", "equipe", "plano"},
    "funcionario": {"aplicacoes"},
    "agronomo": set(),
    "admin": {"logs"},
}

NOMES_DOS_PAPEIS = {
    "produtor": "Produtor",
    "funcionario": "Funcionário",
    "agronomo": "Agrônomo",
    "admin": "Admin",
}


def usuario_atual():
    """Id, nome e papel atual de quem está logado. Se o auth-service não
    responder, a requisição para com 503: sem saber o papel, não dá pra
    decidir nada."""
    if "usuario" not in g:
        dados = consultar_usuario(session["usuario_id"])
        if dados is None:
            abort(503)
        g.usuario = {
            "id": dados["id"],
            "nome": dados["nome"],
            "email": dados.get("email"),
            "papel": dados["role"],
            "premium": bool(dados.get("premium")),
        }
    return g.usuario


def pode(usuario, permissao):
    return permissao in PERMISSOES.get(usuario["papel"], set())


def exigir(permissao):
    """Barra com 403 quem não tem a permissão, antes de olhar qualquer
    registro. Assim o papel errado leva 403 mesmo com um id que existe."""
    usuario = usuario_atual()
    if not pode(usuario, permissao):
        abort(403)
    return usuario


def propriedades_do_usuario(usuario_id):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT p.id, p.nome, p.municipio, p.dono_id FROM propriedades p "
                "JOIN membros m ON m.propriedade_id = p.id "
                "WHERE m.usuario_id = %s ORDER BY p.nome",
                (usuario_id,),
            )
            return cur.fetchall()
    finally:
        conn.close()


def propriedade_do_produtor(usuario_id):
    """A propriedade de que o produtor é dono (por enquanto, uma por produtor)."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, nome, municipio, dono_id FROM propriedades "
                "WHERE dono_id = %s ORDER BY id LIMIT 1",
                (usuario_id,),
            )
            return cur.fetchone()
    finally:
        conn.close()
