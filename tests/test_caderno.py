import io
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

from app.caderno import hoje
from conftest import entrar

JPG = b"\xff\xd8\xff\xe0" + b"0" * 200


def dias_atras(n):
    return (hoje() - timedelta(days=n)).isoformat()


def montar_sitio(client, carencia=30):
    resp = client.post("/propriedade/nova", data={"nome": "Sítio Boa Vista", "municipio": "Garça"})
    assert resp.status_code == 302
    talhao = client.post("/api/talhoes", json={"nome": "Alto", "area_ha": "4,5", "cultura": "Café arábica"})
    assert talhao.status_code == 201, talhao.get_json()
    produto = client.post(
        "/api/produtos", json={"nome": "Fungicida", "carencia_dias": carencia, "unidade": "L"}
    )
    assert produto.status_code == 201, produto.get_json()
    return talhao.get_json(), produto.get_json()


def aplicacao(talhao, produto, **outros):
    dados = {
        "talhao_id": talhao["id"],
        "produto_id": produto["id"],
        "data_aplicacao": dias_atras(5),
        "dose": "2,5",
        "aplicador": "Diego",
    }
    dados.update(outros)
    return dados


def registrar(client, talhao, produto, **outros):
    resp = client.post("/api/aplicacoes", json=aplicacao(talhao, produto, **outros))
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()


def convite(client, papel):
    resp = client.post("/equipe/convites", data={"papel": papel})
    assert resp.status_code == 302
    return parse_qs(urlsplit(resp.headers["Location"]).query)["novo"][0]


# --- landing e cadastro ----------------------------------------------------


def test_landing_abre_sem_login_com_botao_de_criar_conta(app):
    resp = app.test_client().get("/")
    texto = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert "Criar conta grátis" in texto
    assert 'href="/cadastro"' in texto


def test_cadastro_aberto_nao_cria_funcionario(app):
    resp = app.test_client().post(
        "/cadastro", data={"nome": "X", "email": "x@teste.local", "senha": "segredo1", "papel": "funcionario"}
    )
    assert resp.status_code == 400


def test_produtor_sem_propriedade_vai_cadastrar_a_dele(pessoa):
    marcos = pessoa("Marcos")
    resp = marcos.get("/talhoes")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/propriedade/nova")


def test_api_sem_login_da_401(app):
    resp = app.test_client().get("/api/talhoes")
    assert resp.status_code == 401


# --- CRUD do recurso principal -----------------------------------------------


def test_crud_da_aplicacao_pela_api_com_receita(pessoa, mundo):
    marcos = pessoa("Marcos")
    talhao, produto = montar_sitio(marcos)

    dados = aplicacao(talhao, produto)
    dados["receita"] = (io.BytesIO(JPG), "receita.jpg")
    resp = marcos.post("/api/aplicacoes", data=dados, content_type="multipart/form-data")
    assert resp.status_code == 201, resp.get_json()
    criada = resp.get_json()
    assert criada["dose"] == 2.5
    assert criada["receita_url"].startswith("/arquivos/")
    [chave] = mundo.arquivos
    assert chave.startswith(f"propriedades/{talhao['propriedade_id']}/receitas/")

    assert marcos.get(f"/api/aplicacoes/{criada['id']}").status_code == 200
    assert len(marcos.get("/api/aplicacoes").get_json()) == 1

    resp = marcos.put(f"/api/aplicacoes/{criada['id']}", json=aplicacao(talhao, produto, dose=3))
    assert resp.status_code == 200
    assert resp.get_json()["dose"] == 3.0
    assert resp.get_json()["receita_url"], "editar sem mandar receita mantém a que já tinha"

    assert marcos.delete(f"/api/aplicacoes/{criada['id']}").status_code == 204
    assert marcos.get(f"/api/aplicacoes/{criada['id']}").status_code == 404
    assert mundo.arquivos == {}

    acoes = mundo.acoes()
    for acao in ["propriedade_criada", "talhao_criado", "produto_cadastrado",
                 "aplicacao_registrada", "aplicacao_editada", "aplicacao_apagada"]:
        assert acao in acoes
    editada = next(e for e in mundo.eventos if e["acao"] == "aplicacao_editada")
    assert "dose 2,50 → 3,00" in editada["detalhes"]
    assert editada["usuario_id"] is not None


def test_telas_de_listar_criar_detalhar_e_editar(pessoa):
    marcos = pessoa("Marcos")
    talhao, produto = montar_sitio(marcos)

    assert "Registrar aplicação" in marcos.get("/aplicacoes/nova").get_data(as_text=True)
    resp = marcos.post(
        "/aplicacoes/nova",
        data=dict(aplicacao(talhao, produto), receita=(io.BytesIO(JPG), "r.jpg")),
        content_type="multipart/form-data",
    )
    assert resp.status_code == 302
    detalhe = resp.headers["Location"]

    texto = marcos.get(detalhe).get_data(as_text=True)
    assert "Fungicida" in texto and "/arquivos/" in texto

    assert marcos.get(detalhe + "/editar").status_code == 200
    resp = marcos.post(detalhe + "/editar", data=aplicacao(talhao, produto, aplicador="Marcos"))
    assert resp.status_code == 302

    assert "Marcos" in marcos.get("/aplicacoes").get_data(as_text=True)
    assert "em carência até" in marcos.get("/talhoes").get_data(as_text=True)


def test_receita_que_nao_e_imagem_nem_pdf_e_recusada(pessoa, mundo):
    marcos = pessoa("Marcos")
    talhao, produto = montar_sitio(marcos)
    dados = dict(aplicacao(talhao, produto), receita=(io.BytesIO(b"MZ isso e um exe"), "receita.jpg"))

    resp = marcos.post("/api/aplicacoes", data=dados, content_type="multipart/form-data")

    assert resp.status_code == 400
    assert "foto" in resp.get_json()["erro"]
    assert mundo.arquivos == {}


def test_receita_em_pdf_e_aceita(pessoa, mundo):
    marcos = pessoa("Marcos")
    talhao, produto = montar_sitio(marcos)
    dados = dict(aplicacao(talhao, produto), receita=(io.BytesIO(b"%PDF-1.7\n..."), "receita.pdf"))

    resp = marcos.post("/api/aplicacoes", data=dados, content_type="multipart/form-data")

    assert resp.status_code == 201
    assert list(mundo.arquivos)[0].endswith(".pdf")


def test_aplicacao_no_futuro_e_recusada(pessoa):
    marcos = pessoa("Marcos")
    talhao, produto = montar_sitio(marcos)
    amanha = (hoje() + timedelta(days=1)).isoformat()
    resp = marcos.post("/api/aplicacoes", json=aplicacao(talhao, produto, data_aplicacao=amanha))
    assert resp.status_code == 400


def test_talhao_com_aplicacao_nao_pode_ser_apagado(pessoa):
    marcos = pessoa("Marcos")
    talhao, produto = montar_sitio(marcos)
    registrar(marcos, talhao, produto)
    assert marcos.delete(f"/api/talhoes/{talhao['id']}").status_code == 409


# --- carência ----------------------------------------------------------------


def test_talhao_fica_em_carencia_ate_a_aplicacao_mais_longa_vencer(pessoa):
    marcos = pessoa("Marcos")
    talhao, longo = montar_sitio(marcos, carencia=30)
    curto = marcos.post("/api/produtos", json={"nome": "Cobre", "carencia_dias": 7, "unidade": "kg"}).get_json()

    registrar(marcos, talhao, longo, data_aplicacao=dias_atras(10))
    registrar(marcos, talhao, curto, data_aplicacao=dias_atras(1))

    dados = marcos.get(f"/api/talhoes/{talhao['id']}").get_json()
    assert dados["liberado_em"] == (hoje() + timedelta(days=20)).isoformat()
    assert dados["em_carencia"] is True
    assert dados["dias_restantes"] == 20


def test_talhao_liberado_depois_da_carencia(pessoa):
    marcos = pessoa("Marcos")
    talhao, produto = montar_sitio(marcos, carencia=7)
    registrar(marcos, talhao, produto, data_aplicacao=dias_atras(30))
    assert marcos.get(f"/api/talhoes/{talhao['id']}").get_json()["em_carencia"] is False


# --- isolamento entre propriedades -------------------------------------------


def test_outro_produtor_nao_ve_nem_mexe_nos_registros(pessoa):
    marcos = pessoa("Marcos")
    talhao, produto = montar_sitio(marcos)
    aplicada = registrar(marcos, talhao, produto)

    rita = pessoa("Rita")
    rita.post("/propriedade/nova", data={"nome": "Sítio São José", "municipio": "Pompeia"})

    for url in [
        f"/talhoes/{talhao['id']}",
        f"/aplicacoes/{aplicada['id']}",
        f"/aplicacoes/{aplicada['id']}/editar",
        f"/api/talhoes/{talhao['id']}",
        f"/api/aplicacoes/{aplicada['id']}",
    ]:
        assert rita.get(url).status_code == 404, url

    assert rita.put(f"/api/aplicacoes/{aplicada['id']}", json=aplicacao(talhao, produto)).status_code == 404
    assert rita.delete(f"/api/aplicacoes/{aplicada['id']}").status_code == 404
    assert rita.delete(f"/api/talhoes/{talhao['id']}").status_code == 404
    assert rita.get("/api/talhoes").get_json() == []
    assert rita.get("/api/aplicacoes").get_json() == []

    # Nem registrando com o id do talhão dele.
    resp = rita.post("/api/aplicacoes", json=aplicacao(talhao, produto))
    assert resp.status_code == 400
    assert marcos.get(f"/api/aplicacoes/{aplicada['id']}").status_code == 200


# --- papéis ------------------------------------------------------------------


def test_agronomo_leva_403_direto_na_api_e_vai_pro_log(pessoa, mundo):
    ana = pessoa("Ana", "agronomo")

    resp = ana.post("/api/aplicacoes", json={"talhao_id": 1, "produto_id": 1})
    assert resp.status_code == 403
    assert resp.get_json() == {"erro": "Seu papel não permite essa ação."}
    assert ana.post("/api/talhoes", json={"nome": "X", "area_ha": 1, "cultura": "Café"}).status_code == 403

    negados = [e for e in mundo.eventos if e["acao"] == "acesso_negado"]
    assert negados[0]["detalhes"] == "POST /api/aplicacoes"


def test_funcionario_convidado_registra_mas_nao_mexe_no_que_e_do_produtor(pessoa, app, mundo):
    marcos = pessoa("Marcos")
    talhao, produto = montar_sitio(marcos)
    do_marcos = registrar(marcos, talhao, produto)
    token = convite(marcos, "funcionario")

    diego = app.test_client()
    assert "Sítio Boa Vista" in diego.get(f"/convite/{token}").get_data(as_text=True)
    resp = diego.post(f"/convite/{token}", data={"nome": "Diego", "email": "diego@teste.local", "senha": "segredo1"})
    assert resp.status_code == 302
    entrar(diego, "diego@teste.local")

    assert [t["nome"] for t in diego.get("/api/talhoes").get_json()] == ["Alto"]
    do_diego = registrar(diego, talhao, produto, aplicador="Diego")
    assert diego.put(f"/api/aplicacoes/{do_diego['id']}", json=aplicacao(talhao, produto, dose=1)).status_code == 200

    assert diego.put(f"/api/aplicacoes/{do_marcos['id']}", json=aplicacao(talhao, produto)).status_code == 403
    assert diego.delete(f"/api/talhoes/{talhao['id']}").status_code == 403
    assert diego.post("/api/produtos", json={"nome": "X", "carencia_dias": 1, "unidade": "L"}).status_code == 403
    assert diego.get("/equipe").status_code == 403

    # O link é de uso único.
    assert app.test_client().get(f"/convite/{token}").status_code == 404
    assert "convite_aceito" in mundo.acoes()


def test_agronomo_aceita_convite_e_so_acompanha(pessoa):
    marcos = pessoa("Marcos")
    talhao, produto = montar_sitio(marcos)
    token = convite(marcos, "agronomo")

    ana = pessoa("Ana", "agronomo")
    assert ana.get("/api/talhoes").get_json() == []
    assert ana.post(f"/convite/{token}").status_code == 302

    assert len(ana.get("/api/talhoes").get_json()) == 1
    assert ana.post("/api/aplicacoes", json=aplicacao(talhao, produto)).status_code == 403


def test_so_admin_ve_o_log_com_quem_e_o_que(pessoa, schema, mundo):
    marcos = pessoa("Marcos")
    talhao, produto = montar_sitio(marcos)
    registrar(marcos, talhao, produto)
    assert marcos.get("/admin/logs").status_code == 403

    admin = pessoa("Admin")
    with schema.cursor() as cur:
        cur.execute("UPDATE usuarios SET role = 'admin' WHERE email = %s", (admin.email,))

    texto = admin.get("/admin/logs?tipo=negocio").get_data(as_text=True)
    assert "aplicacao_registrada" in texto
    assert "Marcos" in texto
    assert "acesso_negado" not in texto
