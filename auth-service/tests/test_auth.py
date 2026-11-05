import pytest
from werkzeug.security import generate_password_hash

import app as auth


class ConexaoFalsa:
    """Imita o pymysql só no que o auth-service usa: cursor(), execute(),
    fetchone() e close(). Cada SELECT devolve o próximo item da fila."""

    def __init__(self, resultados):
        self.resultados = list(resultados)
        self.consultas = []

    def cursor(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=None):
        self.consultas.append((sql, params))

    def fetchone(self):
        return self.resultados.pop(0) if self.resultados else None

    def fetchall(self):
        return self.resultados.pop(0) if self.resultados else []

    @property
    def lastrowid(self):
        return 42

    def close(self):
        pass


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("LOG_SERVICE_URL", raising=False)
    auth.app.config["TESTING"] = True
    return auth.app.test_client()


def usar_banco(monkeypatch, *resultados):
    conexao = ConexaoFalsa(resultados)
    monkeypatch.setattr(auth, "get_connection", lambda: conexao)
    return conexao


def test_cadastro_sem_campos_da_400(client):
    resp = client.post("/cadastro", json={"nome": "", "email": "a@a.com", "senha": ""})
    assert resp.status_code == 400


def test_cadastro_sem_papel_entra_como_produtor(client, monkeypatch):
    banco = usar_banco(monkeypatch, None)

    resp = client.post("/cadastro", json={"nome": "Maria", "email": "Maria@Exemplo.com", "senha": "x"})

    assert resp.status_code == 201
    _, params = banco.consultas[-1]
    assert params[1] == "maria@exemplo.com"
    assert params[2] != "x"
    assert params[3] == "produtor"


def test_cadastro_de_agronomo(client, monkeypatch):
    banco = usar_banco(monkeypatch, None)

    resp = client.post(
        "/cadastro", json={"nome": "Ana", "email": "ana@exemplo.com", "senha": "x", "papel": "agronomo"}
    )

    assert resp.status_code == 201
    assert banco.consultas[-1][1][3] == "agronomo"


def test_cadastro_nao_cria_admin(client, monkeypatch):
    banco = usar_banco(monkeypatch, None)

    resp = client.post(
        "/cadastro", json={"nome": "Eu", "email": "eu@exemplo.com", "senha": "x", "papel": "admin"}
    )

    assert resp.status_code == 400
    assert banco.consultas == []


def test_cadastro_com_email_repetido_da_409(client, monkeypatch):
    usar_banco(monkeypatch, {"id": 1})
    resp = client.post("/cadastro", json={"nome": "Maria", "email": "maria@exemplo.com", "senha": "x"})
    assert resp.status_code == 409


def test_login_com_senha_errada_da_401(client, monkeypatch):
    usar_banco(
        monkeypatch,
        {"id": 7, "nome": "Maria", "senha_hash": generate_password_hash("certa"), "role": "produtor"},
    )
    resp = client.post("/login", json={"email": "maria@exemplo.com", "senha": "errada"})
    assert resp.status_code == 401


def test_login_certo_devolve_o_papel(client, monkeypatch):
    usar_banco(
        monkeypatch,
        {"id": 7, "nome": "Maria", "senha_hash": generate_password_hash("certa"), "role": "admin"},
    )
    resp = client.post("/login", json={"email": "maria@exemplo.com", "senha": "certa"})
    assert resp.status_code == 200
    assert resp.get_json() == {"usuario_id": 7, "nome": "Maria", "role": "admin"}


def test_resetar_senha_com_token_usado_da_400(client, monkeypatch):
    usar_banco(monkeypatch, {"usuario_id": 7, "expira_em": None, "usado": True})
    resp = client.post("/resetar-senha", json={"token": "abc", "nova_senha": "nova"})
    assert resp.status_code == 400
    assert "usado" in resp.get_json()["erro"]


def test_usuario_vem_com_o_plano(client, monkeypatch):
    usar_banco(
        monkeypatch,
        {"id": 7, "nome": "Maria", "email": "maria@exemplo.com", "role": "produtor", "premium": 1},
    )
    resp = client.get("/usuarios/7")
    assert resp.get_json()["premium"] is True


def test_alterar_plano_sem_premium_da_400(client):
    resp = client.put("/usuarios/7/plano", json={"stripe_customer_id": "cus_x"})
    assert resp.status_code == 400


def test_alterar_plano_de_usuario_que_nao_existe_da_404(client, monkeypatch):
    usar_banco(monkeypatch, None)
    resp = client.put("/usuarios/99/plano", json={"premium": True})
    assert resp.status_code == 404


def test_cancelar_premium_tira_a_assinatura_e_mantem_o_cliente(client, monkeypatch):
    banco = usar_banco(monkeypatch, {"id": 7})

    resp = client.put(
        "/usuarios/7/plano",
        json={"premium": False, "stripe_subscription_id": "sub_x"},
    )

    assert resp.status_code == 200
    update, params = banco.consultas[-1]
    assert "COALESCE" in update
    assert params == (False, None, None, 7)


def test_usuarios_em_lote_ignora_lixo_nos_ids(client, monkeypatch):
    banco = usar_banco(monkeypatch, [{"id": 7, "nome": "Marcos", "role": "produtor"}])

    resp = client.get("/usuarios?ids=7,abc,7,,8")

    assert resp.status_code == 200
    assert resp.get_json() == [{"id": 7, "nome": "Marcos", "role": "produtor"}]
    _, params = banco.consultas[-1]
    assert params == [7, 8]


def test_usuarios_em_lote_sem_ids_nem_vai_no_banco(client, monkeypatch):
    banco = usar_banco(monkeypatch)
    assert client.get("/usuarios").get_json() == []
    assert banco.consultas == []
