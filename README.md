# 🌱 Talhão em Dia

**Caderno de campo no celular pro pequeno produtor de café: cada aplicação registrada por talhão, aviso de quando a carência acaba e o histórico pronto quando a cooperativa ou a certificadora pedir.**

Este repositório continua o [Hanks-catalogue](https://github.com/joao-alegre07/Hanks-catalogue), o
catálogo de filmes do Tom Hanks, com todo o histórico. A arquitetura é a mesma (login, papéis, logs,
upload e pagamento); o que muda é o negócio. Por enquanto o código ainda é o do catálogo, e a troca
começa na atividade 10 (ver [Backlog](#backlog) e [Estado do código](#estado-do-código)).

## A dor

**Quem sofre:** o pequeno produtor de café da região de Garça, Pompeia e Marília, com 10 a 30
hectares divididos em poucos talhões, que toca o sítio com a família e um ou dois funcionários e é
atendido por um agrônomo de cooperativa ou de revenda que passa a cada 15 dias.

**Quando dói:**

- **Na véspera da colheita** (maio a agosto). Todo defensivo tem um intervalo de segurança, a
  carência, escrito na bula: colher antes disso deixa resíduo acima do limite no grão. Pra saber se o
  talhão 3 já está liberado, o produtor precisa lembrar o que foi aplicado lá, em que dia, e achar a
  bula.
- **Na visita da cooperativa ou da certificadora.** Os programas de certificação de café, que pagam
  ágio na saca, pedem o caderno de campo: o que foi aplicado, onde, quando, em que dose e com qual
  receituário agronômico. Hoje isso é montado de trás pra frente, juntando nota fiscal, foto de
  receita no WhatsApp e memória.
- **Na compra de insumo.** Sem saber o que sobrou no galpão, ele compra de novo o que já tinha, ou
  descobre no dia da aplicação que o produto acabou.

**Quanto custa hoje** (num sítio de 18 ha com 4 talhões):

| | |
|---|---|
| Tempo | 2 a 3 dias por ano reconstruindo o histórico pra auditoria e pra cooperativa |
| Dinheiro | defensivo comprado em dobro: um galão esquecido no galpão são algumas centenas de reais |
| Risco | colher um talhão dentro da carência pode fazer o lote ser recusado e custar a certificação, e o ágio, da safra inteira |

**Como resolve hoje:** caderno no galpão (quando alguém lembra de escrever), foto da receita no grupo
de WhatsApp e a memória do produtor.

## Persona

**Marcos, 52 anos, produtor de café em Garça.** Tem 18 hectares de arábica em 4 talhões, herdados do
pai. Trabalha com o filho, o Diego (24), e contrata dois diaristas na colheita. Acorda às 5h e passa
o dia entre o cafezal e o galpão. Quem pulveriza quase sempre é o Diego, com o trator. O agrônomo da
cooperativa passa a cada 15 dias, olha a lavoura e deixa a receita.

- **O que ele tenta fazer:** entrar num programa de certificação pra vender o café com ágio, e
  colher cada talhão no ponto sem arriscar o lote.
- **O que atrapalha:** o caderno fica no galpão e o Diego anota "quando dá", às vezes num papel que
  some, às vezes só manda uma foto no grupo da família. Na primeira auditoria o Marcos passou dois
  dias juntando nota fiscal e mensagem pra preencher a planilha da certificadora, e ainda ficou um
  buraco em março. Ele usa o celular pra WhatsApp e previsão do tempo, e não quer "sistema de fazenda
  grande".

## Concorrentes e alternativas

| Alternativa | Como é usada | O que faz mal |
|---|---|---|
| Caderno de papel no galpão | O jeito de sempre: anota quem lembrar, quando lembrar | Molha, some, a letra não se entende. Não avisa carência nem controla estoque, e pra auditoria alguém tem que passar tudo a limpo |
| Planilha (Excel ou Google Sheets) | O filho monta e preenche no computador de casa | Ninguém abre planilha no meio do cafezal, então ela é preenchida dias depois, de memória. Não avisa nada |
| Grupo de WhatsApp com o agrônomo e o funcionário | Foto da receita, "passei o fungicida no 3" | O histórico se perde no meio das mensagens. Não dá pra filtrar por talhão nem tirar um relatório |
| Software de gestão agrícola completo (Aegro e similares) | Fazenda com gerente e escritório: financeiro, máquinas, colheita, estoque | O pequeno produtor paga e aprende um sistema inteiro pra usar só o caderno de campo |

## Proposta de valor

Pro pequeno produtor que precisa manter o caderno de campo, o Talhão em Dia é o que o funcionário
consegue preencher no celular em meio minuto, logo depois de aplicar, e que avisa sozinho quando cada
talhão está liberado pra colher, sem precisar contratar e aprender um sistema de fazenda grande.

## Modelo de receita (Stripe)

A cobrança é por **propriedade**, não por usuário: quem assina é o produtor, e o funcionário e o
agrônomo entram de graça na propriedade dele.

| | Free | Pro |
|---|---|---|
| Preço | R$ 0 | **R$ 29,90/mês** por propriedade |
| Talhões | até 2 | sem limite |
| Quem acessa | só o produtor | produtor, funcionários e agrônomo |
| Registro de aplicação com foto da receita | ✅ | ✅ |
| Carência por talhão ("liberado pra colher em 12/06") | ✅ | ✅ |
| Aviso por e-mail quando a carência acaba | ❌ | ✅ |
| Estoque de defensivos com baixa automática | ❌ | ✅ |
| Relatório do caderno de campo em PDF | ❌ | ✅ |

**O que o Free limita e por quê:** 2 talhões dá pra testar com uma área de verdade, mas um sítio como
o do Marcos tem 4 ou mais. E quem aplica normalmente é o filho ou o funcionário, não o dono, então o
caderno só funciona de verdade quando mais de uma pessoa registra.

**Por que alguém pagaria o Pro:** R$ 29,90 é menos de R$ 1 por dia e menos que um galão de qualquer
defensivo. O relatório em PDF poupa os dias de montar o histórico antes da auditoria, e um lote que
deixa de ser recusado paga anos de assinatura.

**Cobrança:** Stripe Checkout em modo assinatura, o mesmo fluxo do Plano Premium do catálogo
(webhook com assinatura conferida, plano gravado pelo auth-service). Cancelou, volta pro Free: nada é
apagado e o histórico continua legível, mas só os 2 primeiros talhões aceitam registro novo.

O café tem safra, e o risco é o produtor cancelar na entressafra. Depois de validar o mensal, a ideia
é um plano anual com desconto.

## Métricas de sucesso

| Métrica | Como medir | Meta pro primeiro ano |
|---|---|---|
| Propriedades cadastradas | cadastros no auth-service | 200 |
| Propriedades ativas | pelo menos 1 aplicação registrada nos últimos 30 dias (log-service) | 60% das cadastradas |
| Conversão Free → Pro | assinantes ÷ propriedades cadastradas | 25% |
| Assinantes Pro | assinaturas ativas no Stripe (webhook) | 50 |
| MRR | assinantes × R$ 29,90 | R$ 1.495 |
| Churn mensal | cancelamentos ÷ assinantes no começo do mês | abaixo de 5%, olhando a entressafra separada |
| Registro no mesmo dia | aplicações registradas no dia em que foram feitas | 70% |

A última é a que mostra se o caderno saiu do papel: se o registro continua sendo feito dias depois,
de memória, o produto não resolveu a dor, mesmo com gente pagando.

## Lean Canvas

| Bloco | Talhão em Dia |
|---|---|
| **Problema** | 1. Histórico de aplicações perdido ou incompleto quando a cooperativa ou a certificadora pede. 2. Não saber com certeza se o talhão já passou da carência na hora de colher. 3. Comprar defensivo que já tinha no galpão, ou faltar no dia. Hoje: caderno no galpão, planilha, WhatsApp e memória. |
| **Segmentos de clientes** | Pequenos produtores de café (10 a 30 ha) da região de Garça, Pompeia e Marília. Primeiros a adotar: quem está entrando em certificação e os sítios onde um filho já cuida da parte "de celular". Junto deles, os agrônomos de cooperativa e de revenda que atendem dezenas desses produtores. |
| **Proposta única de valor** | O caderno de campo que o funcionário preenche no celular em meio minuto e que avisa quando o talhão está liberado pra colher, por menos de R$ 1 por dia. |
| **Solução** | 1. Registro da aplicação pelo celular (talhão, produto, dose, quem aplicou, foto da receita), que vira o relatório pronto. 2. Carência calculada por talhão: "liberado pra colher em 12/06". 3. Estoque que baixa sozinho a cada aplicação registrada. |
| **Canais** | Agrônomos de cooperativa e de revenda, que indicam pros produtores que atendem e passam a acompanhar as propriedades pelo app. A rede da Fatec Pompeia, que vive no meio do agro da região. Indicação de produtor pra produtor. O rodapé "gerado pelo Talhão em Dia" no relatório que chega na cooperativa. |
| **Fontes de receita** | Assinatura Pro de R$ 29,90/mês por propriedade, cobrada pelo Stripe (Checkout + webhook). Depois, um plano anual pra segurar a entressafra. |
| **Estrutura de custos** | Hoje roda no servidor da disciplina. Fora dele: uma VPS pequena (R$ 50 a R$ 100/mês), domínio .com.br (R$ 40/ano) e e-mail no plano grátis do Brevo (300 por dia) enquanto couber. Stripe: 3,99% + R$ 0,39 por cobrança no cartão, mais 0,7% do Billing, uns R$ 1,79 de cada R$ 29,90. O maior custo é tempo: visita a produtor e suporte. |
| **Métricas-chave** | Propriedades ativas, aplicações registradas no mesmo dia, conversão Free → Pro, assinantes, MRR e churn (separando a entressafra). |
| **Vantagem injusta** | Estudo na Fatec Pompeia, no meio do agro da região, com acesso a produtores e agrônomos que um app de fora não tem. E o histórico de cada talhão: quanto mais safras registradas, mais difícil é trocar de ferramenta. |

## Mapa de reaproveitamento

Nada da arquitetura do catálogo vai fora. Cada peça ganha um papel no negócio:

| Peça do projeto atual | O que vira no SaaS | No Talhão em Dia |
|---|---|---|
| Catálogo de filmes (TMDB) | Recurso principal do negócio | Propriedades, talhões (nome, área, cultura) e aplicações (produto, dose, data, carência). O TMDB sai; os produtos entram cadastrados pelo produtor, e dá pra avaliar a API do Agrofit (Embrapa) no lugar |
| Favoritos com limite no plano grátis | Limite do Free | Até 2 talhões no Free, conferido no backend do mesmo jeito que o limite de 5 favoritos |
| Comentários com moderação | Conversa sobre o recurso | Observações no talhão: o agrônomo deixa a recomendação, o produtor e o funcionário respondem; o autor apaga o próprio, admin modera |
| Microsserviço de login + RBAC | Papéis do negócio | `produtor` (dono da propriedade, assina o plano), `funcionario` (registra aplicação), `agronomo` (acompanha várias propriedades) e `admin` (plataforma). Continua no Padrão A: papel e plano atuais conferidos no auth-service |
| Recuperação de senha por e-mail (Brevo) | E-mail transacional | Continua, e ganha o aviso de carência terminando e de estoque baixo (Pro) |
| Logs e auditoria (Redis) | Eventos de negócio | `aplicacao_registrada`, `aplicacao_editada`, `talhao_criado`, `estoque_baixo`, `relatorio_gerado`, `plano_pro_ativado`. No caderno de campo o log vale mais ainda: mostra quem mudou um registro e quando |
| Upload e perfil (Garage) | Arquivos do domínio | Foto do receituário agronômico, da nota fiscal do defensivo e do talhão. Bucket privado e URL pré-assinada continuam fazendo sentido: são documentos da propriedade |
| Plano Premium (Stripe) | Assinatura | Plano Pro de R$ 29,90/mês por propriedade, mesmo checkout e mesmo webhook. O plano sai do usuário e vai pra propriedade |
| Swagger (extra) | API documentada | API de propriedades, talhões e aplicações em `/apidocs` |
| CI/CD (extra) | Deploy a cada push | Testes, imagens no GHCR e deploy com um clique, com as imagens renomeadas pra `talhao-em-dia-*` |
| Observabilidade (extra) | Saúde do sistema | `/health` e `/metrics` continuam; o painel do Grafana ganha aplicações registradas por dia |
| Documentação e SaaS/PaaS/IaaS (atividade 8) | Documentação do produto | `DOCUMENTACAO.md` reescrita pro domínio novo; a tabela de camadas continua a mesma, porque a infraestrutura não muda |

## Backlog

As próximas entregas estão nas [issues do repositório](https://github.com/joao-alegre07/talhao-em-dia/issues),
marcadas com `atividade 10` (o negócio no ar) e `atividade 11` (a assinatura com Stripe).

## Estado do código

Até a atividade 10 o código aqui é o do catálogo de filmes, e é ele que está no ar em
[joao-alegre-isw055.lapps.studio](https://joao-alegre-isw055.lapps.studio/): a stack do Portainer
ainda puxa do Hanks-catalogue. A descrição técnica dele (arquitetura, como rodar, CI/CD,
observabilidade) está no [README do repositório antigo](https://github.com/joao-alegre07/Hanks-catalogue#readme)
e em [DOCUMENTACAO.md](DOCUMENTACAO.md).

O GitHub Actions está desligado neste repositório até a troca da stack. O workflow publica as imagens
em `ghcr.io/joao-alegre07/hanks-catalogue-*`, que estão ligadas ao repositório antigo; se ele rodasse
aqui, os dois repositórios disputariam as mesmas imagens. Na atividade 10 as imagens ganham o nome do
produto e o pipeline volta a rodar a partir daqui.

---

Projeto para a aula do professor [@siriani](https://github.com/siriani) (ISW055, Introdução à
Computação em Nuvem, Fatec Pompeia).
