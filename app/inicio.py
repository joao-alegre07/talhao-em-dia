from flask import Blueprint, redirect, render_template, session

from .auth import pagina_inicial

inicio_bp = Blueprint("inicio", __name__)


@inicio_bp.route("/")
def landing():
    # Página aberta: quem já entrou vai direto pro que usa no dia a dia.
    if "usuario_id" in session:
        return redirect(pagina_inicial(session.get("role")))
    return render_template("inicio.html")
