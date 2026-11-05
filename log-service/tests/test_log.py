import fakeredis
import pytest

import app as log


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(log, "r", fakeredis.FakeRedis(decode_responses=True))
    log.app.config["TESTING"] = True
    return log.app.test_client()


def test_evento_sem_acao_da_400(client):
    resp = client.post("/eventos", json={"usuario_id": 1})
    assert resp.status_code == 400


def test_eventos_voltam_do_mais_recente_pro_mais_antigo(client):
    for acao in ["login", "aplicacao_registrada", "logout"]:
        assert client.post("/eventos", json={"acao": acao, "usuario_id": 3}).status_code == 201

    eventos = client.get("/eventos").get_json()

    assert [e["acao"] for e in eventos] == ["logout", "aplicacao_registrada", "login"]
    assert all(e["timestamp"] for e in eventos)


def test_parametro_n_fica_entre_1_e_500(client):
    for i in range(3):
        client.post("/eventos", json={"acao": f"a{i}"})

    assert len(client.get("/eventos?n=0").get_json()) == 1
    assert len(client.get("/eventos?n=2").get_json()) == 2
    assert len(client.get("/eventos?n=9999").get_json()) == 3
