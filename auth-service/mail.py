import os
import smtplib
from email.mime.text import MIMEText


def enviar_email_reset(destinatario, link):
    corpo = (
        "Você pediu para redefinir sua senha no Talhão em Dia.\n\n"
        f"Clique no link abaixo para escolher uma nova senha (válido por 30 minutos):\n{link}\n\n"
        "Se você não pediu isso, ignore este e-mail."
    )

    msg = MIMEText(corpo, "plain", "utf-8")
    msg["Subject"] = "Redefinição de senha — Talhão em Dia"
    msg["From"] = os.environ.get("MAIL_FROM", "no-reply@talhaoemdia.local")
    msg["To"] = destinatario

    with smtplib.SMTP(os.environ["SMTP_HOST"], int(os.environ["SMTP_PORT"])) as smtp:
        smtp.starttls()
        smtp.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
        smtp.send_message(msg)
