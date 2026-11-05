"""Fixtures dos testes que precisam de banco.

Esses testes sobem o app e o auth-service de verdade, os dois falando com um
MariaDB de teste criado pelas migrações de db/. Só o log-service e o storage
são trocados por versões em memória. Localmente o MariaDB pode ser um
container qualquer (ver o README); no GitHub Actions ele é um service do job.
"""

import importlib.util
import os
import pathlib
import sys
from urllib.parse import urlsplit

import pymysql
import pytest
import requests

RAIZ = pathlib.Path(__file__).resolve().parents[1]

BANCO = {
    "DB_HOST": os.environ.get("TESTE_DB_HOST", "127.0.0.1"),
    "DB_PORT": os.environ.get("TESTE_DB_PORT", "3307"),
    "DB_USER": os.environ.get("TESTE_DB_USER", "teste"),
    "DB_PASSWORD": os.environ.get("TESTE_DB_PASSWORD", "teste"),
    "DB_NAME": os.environ.get("TESTE_DB_NAME", "talhao_teste"),
}

TABELAS = ["aplicacoes", "produtos", "talhoes", "convites", "membros", "propriedades", "reset_tokens", "usuarios"]


def _conectar():
    return pymysql.connect(
        host=BANCO["DB_HOST"],
        port=int(BANCO["DB_PORT"]),
        user=BANCO["DB_USER"],
        password=BANCO["DB_PASSWORD"],
        database=BANCO["DB_NAME"],
        autocommit=True,
        connect_timeout=3,
    )


@pytest.fixture(scope="session")
def schema():
    try:
        conn = _conectar()
    except pymysql.err.OperationalError:
        if os.environ.get("CI"):
            raise
        pytest.skip("MariaDB de teste fora do ar")

    # Recria do zero com as mesmas migrações que vão pra produção.
    with conn.cursor() as cur:
        cur.execute("SET FOREIGN_KEY_CHECKS = 0")
        for tabela in TABELAS + ["favoritos", "comentarios", "perfis"]:
            cur.execute(f"DROP TABLE IF EXISTS {tabela}")
        cur.execute("SET FOREIGN_KEY_CHECKS = 1")
        for arquivo in sorted((RAIZ / "db").glob("0*.sql")):
            for comando in arquivo.read_text(encoding="utf-8").split(";\n"):
                if comando.strip() and not all(
                    linha.startswith("--") for linha in comando.strip().splitlines()
                ):
                    cur.execute(comando)
    yield conn
    conn.close()


@pytest.fixture(scope="session")
def auth_service():
    # O auth-service é importado pelo caminho, com outro nome, porque o
    # módulo dele também se chama app.
    pasta = RAIZ / "auth-service"
    sys.path.insert(0, str(pasta))
    spec = importlib.util.spec_from_file_location("auth_service", pasta / "app.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo.app.test_client()


class Resposta:
    def __init__(self, status_code, dados):
        self.status_code = status_code
        self._dados = dados

    def json(self):
        return self._dados

    def raise_for_status(self):
        pass


class Mundo:
    """O que os testes precisam olhar depois: eventos que foram pro log e
    arquivos que foram pro storage."""

    def __init__(self):
        self.eventos = []
        self.arquivos = {}

    def acoes(self):
        return [e["acao"] for e in self.eventos]


@pytest.fixture
def mundo(schema, auth_service, monkeypatch):
    with schema.cursor() as cur:
        cur.execute("SET FOREIGN_KEY_CHECKS = 0")
        for tabela in TABELAS:
            cur.execute(f"TRUNCATE TABLE {tabela}")
        cur.execute("SET FOREIGN_KEY_CHECKS = 1")

    for chave, valor in BANCO.items():
        monkeypatch.setenv(chave, valor)
    monkeypatch.setenv("SECRET_KEY", "teste")
    monkeypatch.setenv("AUTH_SERVICE_URL", "http://auth:5001")
    monkeypatch.setenv("LOG_SERVICE_URL", "http://log:5002")
    monkeypatch.setenv("S3_ENDPOINT", "http://garage:3900")
    monkeypatch.setenv("S3_BUCKET", "receitas")
    monkeypatch.setenv("S3_ACCESS_KEY", "GKteste")
    monkeypatch.setenv("S3_SECRET_KEY", "teste")

    m = Mundo()

    # Chamada pro auth-service vai pro Flask dele em memória; evento pro
    # log-service fica anotado no mundo.
    def chamar(metodo):
        def chamada(url, params=None, json=None, timeout=None, **kwargs):
            partes = urlsplit(url)
            if partes.netloc == "auth:5001":
                resp = auth_service.open(partes.path, method=metodo, query_string=params, json=json)
                return Resposta(resp.status_code, resp.get_json())
            if partes.netloc == "log:5002" and metodo == "POST":
                m.eventos.append(json)
                return Resposta(201, {})
            if partes.netloc == "log:5002":
                eventos = [
                    dict(e, id=str(i), timestamp="2026-11-02T13:00:00+00:00", usuario_id=str(e["usuario_id"] or ""))
                    for i, e in enumerate(m.eventos)
                ]
                return Resposta(200, eventos[::-1])
            raise requests.exceptions.ConnectionError(url)

        return chamada

    monkeypatch.setattr(requests, "get", chamar("GET"))
    monkeypatch.setattr(requests, "post", chamar("POST"))
    monkeypatch.setattr(requests, "put", chamar("PUT"))

    from app import storage

    monkeypatch.setattr(storage, "enviar", lambda chave, dados, tipo: m.arquivos.__setitem__(chave, dados))
    monkeypatch.setattr(storage, "apagar", lambda chave: m.arquivos.pop(chave, None))
    return m


@pytest.fixture
def app(mundo):
    from app import create_app

    app = create_app()
    app.config["TESTING"] = True
    return app


@pytest.fixture
def pessoa(app):
    """pessoa("Marcos", "produtor") cadastra pela tela e devolve um client já
    logado com essa conta."""
    contador = iter(range(1, 1000))

    def criar(nome, papel="produtor"):
        client = app.test_client()
        email = f"{nome.lower()}{next(contador)}@teste.local"
        resp = client.post("/cadastro", data={"nome": nome, "email": email, "senha": "segredo1", "papel": papel})
        assert resp.status_code == 302, resp.get_data(as_text=True)
        entrar(client, email)
        client.email = email
        return client

    return criar


def entrar(client, email, senha="segredo1"):
    resp = client.post("/login", data={"email": email, "senha": senha})
    assert resp.status_code == 302, resp.get_data(as_text=True)
    return resp
