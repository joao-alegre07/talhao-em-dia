import hashlib
import hmac
import json
import time

import pytest
import requests

from app import create_app


class RespostaFalsa:
    def __init__(self, status_code, dados):
        self.status_code = status_code
        self._dados = dados

    def json(self):
        return self._dados


@pytest.fixture
def chamadas(monkeypatch):
    # O webhook não depende do banco: toda chamada HTTP de saída é anotada aqui
    # e respondida com o que o teste pedir.
    feitas = []
    respostas = {}

    def chamada_falsa(url, **kwargs):
        feitas.append(url)
        for final, resposta in respostas.items():
            if url.endswith(final):
                return resposta
        raise requests.exceptions.ConnectionError(url)

    monkeypatch.setattr(requests, "get", chamada_falsa)
    monkeypatch.setattr(requests, "post", chamada_falsa)
    monkeypatch.setattr(requests, "put", chamada_falsa)
    return feitas, respostas


@pytest.fixture
def client(monkeypatch, chamadas):
    monkeypatch.setenv("SECRET_KEY", "teste")
    monkeypatch.setenv("AUTH_SERVICE_URL", "http://auth:5001")
    monkeypatch.setenv("LOG_SERVICE_URL", "http://log:5002")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_teste")
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def assinatura_stripe(corpo, segredo, t=None):
    t = t or int(time.time())
    v1 = hmac.new(segredo.encode(), f"{t}.{corpo}".encode(), hashlib.sha256).hexdigest()
    return f"t={t},v1={v1}"


EVENTO_PAGO = json.dumps(
    {
        "id": "evt_teste",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_test_1",
                "client_reference_id": "7",
                "payment_status": "paid",
                "customer": "cus_teste",
                "subscription": "sub_teste",
            }
        },
    }
)


def test_swagger_responde_com_a_api_do_caderno(client):
    resp = client.get("/apispec_1.json")
    assert resp.status_code == 200
    assert "/api/aplicacoes/{aplicacao_id}" in resp.get_json()["paths"]


def test_so_produtor_assina_o_pro(client, chamadas):
    _, respostas = chamadas
    respostas["/usuarios/3"] = RespostaFalsa(200, {"id": 3, "nome": "Diego", "role": "funcionario"})
    with client.session_transaction() as s:
        s["usuario_id"] = 3

    assert client.post("/plano/assinar").status_code == 403


def test_webhook_sem_assinatura_e_recusado(client, chamadas):
    feitas, _ = chamadas
    resp = client.post("/stripe/webhook", data=EVENTO_PAGO, content_type="application/json")
    assert resp.status_code == 400
    assert not any(url.endswith("/plano") for url in feitas)


def test_webhook_assinado_com_outro_segredo_e_recusado(client, chamadas):
    feitas, _ = chamadas
    resp = client.post(
        "/stripe/webhook",
        data=EVENTO_PAGO,
        content_type="application/json",
        headers={"Stripe-Signature": assinatura_stripe(EVENTO_PAGO, "whsec_outro")},
    )
    assert resp.status_code == 400
    assert not any(url.endswith("/plano") for url in feitas)


def test_webhook_antigo_reenviado_e_recusado(client, chamadas):
    feitas, _ = chamadas
    uma_hora_atras = int(time.time()) - 3600
    resp = client.post(
        "/stripe/webhook",
        data=EVENTO_PAGO,
        content_type="application/json",
        headers={"Stripe-Signature": assinatura_stripe(EVENTO_PAGO, "whsec_teste", uma_hora_atras)},
    )
    assert resp.status_code == 400
    assert not any(url.endswith("/plano") for url in feitas)


def test_webhook_de_pagamento_liga_o_pro(client, chamadas):
    feitas, respostas = chamadas
    respostas["/usuarios/7/plano"] = RespostaFalsa(200, {"ok": True})

    resp = client.post(
        "/stripe/webhook",
        data=EVENTO_PAGO,
        content_type="application/json",
        headers={"Stripe-Signature": assinatura_stripe(EVENTO_PAGO, "whsec_teste")},
    )

    assert resp.status_code == 200
    assert "http://auth:5001/usuarios/7/plano" in feitas


def test_webhook_com_auth_fora_do_ar_pede_pro_stripe_tentar_de_novo(client, chamadas):
    resp = client.post(
        "/stripe/webhook",
        data=EVENTO_PAGO,
        content_type="application/json",
        headers={"Stripe-Signature": assinatura_stripe(EVENTO_PAGO, "whsec_teste")},
    )
    assert resp.status_code == 503
