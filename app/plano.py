import json
import os

import requests
import stripe
from flask import Blueprint, jsonify, redirect, render_template, request, url_for

from .acesso import exigir, usuario_atual
from .auditoria import registrar
from .auth import login_required

plano_bp = Blueprint("plano", __name__)


def _url_publica(endpoint, **params):
    base = os.environ.get("PUBLIC_APP_URL", request.url_root).rstrip("/")
    return base + url_for(endpoint, **params)


def _mostrar(erro=None, status=200):
    usuario = usuario_atual()
    return (
        render_template(
            "plano.html",
            pro=usuario["premium"],
            pode_assinar=usuario["papel"] == "produtor",
            sucesso="sucesso" in request.args,
            cancelado="cancelado" in request.args,
            erro=erro,
        ),
        status,
    )


def _alterar_plano(usuario_id, pro, customer_id=None, subscription_id=None):
    try:
        resp = requests.put(
            os.environ["AUTH_SERVICE_URL"].rstrip("/") + f"/usuarios/{usuario_id}/plano",
            json={
                "premium": pro,
                "stripe_customer_id": customer_id,
                "stripe_subscription_id": subscription_id,
            },
            timeout=5,
        )
    except requests.exceptions.RequestException:
        return False
    return resp.status_code == 200


@plano_bp.route("/plano")
@login_required
def pagina():
    return _mostrar()


@plano_bp.route("/plano/assinar", methods=["POST"])
@login_required
def assinar():
    # Quem assina é o dono da propriedade; funcionário e agrônomo entram de
    # graça na propriedade dele.
    usuario = exigir("plano")
    if usuario["premium"]:
        return redirect(url_for("plano.pagina"))

    # O cartão é digitado na página do Stripe, não aqui. O app só diz qual
    # preço e quem está assinando; o client_reference_id volta no webhook e é
    # por ele que dá pra saber quem pagou.
    try:
        checkout = stripe.checkout.Session.create(
            api_key=os.environ["STRIPE_SECRET_KEY"],
            mode="subscription",
            line_items=[{"price": os.environ["STRIPE_PRICE_ID"], "quantity": 1}],
            client_reference_id=str(usuario["id"]),
            customer_email=usuario["email"],
            subscription_data={"metadata": {"usuario_id": str(usuario["id"])}},
            success_url=_url_publica("plano.pagina", sucesso=1),
            cancel_url=_url_publica("plano.pagina", cancelado=1),
        )
    except stripe.StripeError:
        return _mostrar(erro="Não foi possível abrir o pagamento agora. Tente de novo.", status=503)

    registrar("checkout_pro", detalhes=checkout.id)
    return redirect(checkout.url, code=303)


@plano_bp.route("/stripe/webhook", methods=["POST"])
def webhook():
    payload = request.get_data()

    # Qualquer um pode mandar um POST pra essa URL dizendo que pagou. O Stripe
    # assina o corpo (junto com o horário) com o segredo do endpoint, e só uma
    # assinatura que bate com esse segredo passa daqui. Sem o tolerance o
    # horário não é conferido e uma chamada antiga poderia ser reenviada.
    try:
        stripe.WebhookSignature.verify_header(
            payload,
            request.headers.get("Stripe-Signature"),
            os.environ["STRIPE_WEBHOOK_SECRET"],
            tolerance=stripe.Webhook.DEFAULT_TOLERANCE,
        )
    except stripe.SignatureVerificationError:
        registrar("webhook_recusado", detalhes="assinatura do Stripe inválida")
        return jsonify(erro="Assinatura inválida."), 400

    evento = json.loads(payload)
    tipo = evento["type"]
    objeto = evento["data"]["object"]

    # Se o auth não gravar, responde 503 e o Stripe manda o mesmo evento de
    # novo mais tarde. Gravar duas vezes não muda nada.
    if tipo == "checkout.session.completed" and objeto.get("payment_status") == "paid":
        usuario_id = objeto.get("client_reference_id")
        if usuario_id:
            if not _alterar_plano(
                int(usuario_id), True, objeto.get("customer"), objeto.get("subscription")
            ):
                return jsonify(erro="Não foi possível gravar o plano."), 503
            registrar(
                "pro_ativado",
                usuario_id=int(usuario_id),
                detalhes=f"assinatura {objeto.get('subscription')} ({evento['id']})",
            )

    elif tipo == "customer.subscription.deleted":
        usuario_id = (objeto.get("metadata") or {}).get("usuario_id")
        if usuario_id:
            if not _alterar_plano(int(usuario_id), False):
                return jsonify(erro="Não foi possível gravar o plano."), 503
            registrar(
                "pro_cancelado",
                usuario_id=int(usuario_id),
                detalhes=f"assinatura {objeto.get('id')} ({evento['id']})",
            )

    return jsonify(recebido=True)
