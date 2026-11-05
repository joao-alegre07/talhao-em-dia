import os

import boto3
from botocore.config import Config

URL_VALIDADE_SEGUNDOS = 600


def _endpoint():
    return os.environ["S3_ENDPOINT"].rstrip("/")


def _bucket():
    return os.environ["S3_BUCKET"]


def _cliente(config_extra=None):
    config = Config(signature_version="s3v4", s3={"addressing_style": "path"})
    if config_extra is not None:
        config = config.merge(config_extra)
    return boto3.client(
        "s3",
        endpoint_url=_endpoint(),
        aws_access_key_id=os.environ["S3_ACCESS_KEY"],
        aws_secret_access_key=os.environ["S3_SECRET_KEY"],
        region_name=os.environ.get("S3_REGION", "garage"),
        config=config,
    )


def conferir_bucket():
    # Usado pelo /health: só pergunta se o bucket existe, com timeout curto e
    # sem as tentativas extras que o boto3 faz por padrão.
    cliente = _cliente(Config(connect_timeout=2, read_timeout=2, retries={"max_attempts": 1}))
    cliente.head_bucket(Bucket=_bucket())


def enviar(chave, dados, content_type):
    _cliente().put_object(Bucket=_bucket(), Key=chave, Body=dados, ContentType=content_type)


def apagar(chave):
    _cliente().delete_object(Bucket=_bucket(), Key=chave)


def url_temporaria(chave):
    url = _cliente().generate_presigned_url(
        "get_object",
        Params={"Bucket": _bucket(), "Key": chave},
        ExpiresIn=URL_VALIDADE_SEGUNDOS,
    )
    # O Garage não tem porta publicada, então o navegador pede a URL assinada
    # pro app (rota /arquivos), que só repassa pro Garage do jeito que veio.
    return "/arquivos" + url[len(_endpoint()):]


def listar(prefixo=""):
    paginas = _cliente().get_paginator("list_objects_v2").paginate(Bucket=_bucket(), Prefix=prefixo)
    for pagina in paginas:
        yield from pagina.get("Contents", [])


def url_interna(caminho, query_string):
    return f"{_endpoint()}/{caminho}?{query_string}"
