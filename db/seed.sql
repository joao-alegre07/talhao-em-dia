-- Dados de exemplo pra rodar local (docker-compose.dev.yml). NÃO rodar em
-- produção: as contas abaixo têm senha conhecida.
--
-- Todas as contas usam a senha talhao123.
--   admin@talhaoemdia.local   admin
--   marcos@talhaoemdia.local  produtor, dono do Sítio Boa Vista (Garça)
--   diego@talhaoemdia.local   funcionário do Sítio Boa Vista
--   ana@talhaoemdia.local     agrônoma, acompanha o Sítio Boa Vista
--   rita@talhaoemdia.local    produtora, dona do Sítio São José (Pompeia)
--
-- Os produtos e as carências são só exemplo, não foram tirados de bula.
-- As datas são contadas a partir de hoje, pra sempre ter talhão em carência
-- e talhão liberado.

INSERT INTO usuarios (id, nome, email, senha_hash, role) VALUES
  (1, 'Admin', 'admin@talhaoemdia.local', 'scrypt:32768:8:1$lCEgLAwUQhTJWOl6$490f66179ca1223b9a65d2cd9e0e556d9984d3de395d42fad916c6088400c51b4c97dd49fa335d98903fb04b5e0828b65a8a91963ba55a60572bb17b4f90a00d', 'admin'),
  (2, 'Marcos', 'marcos@talhaoemdia.local', 'scrypt:32768:8:1$lCEgLAwUQhTJWOl6$490f66179ca1223b9a65d2cd9e0e556d9984d3de395d42fad916c6088400c51b4c97dd49fa335d98903fb04b5e0828b65a8a91963ba55a60572bb17b4f90a00d', 'produtor'),
  (3, 'Diego', 'diego@talhaoemdia.local', 'scrypt:32768:8:1$lCEgLAwUQhTJWOl6$490f66179ca1223b9a65d2cd9e0e556d9984d3de395d42fad916c6088400c51b4c97dd49fa335d98903fb04b5e0828b65a8a91963ba55a60572bb17b4f90a00d', 'funcionario'),
  (4, 'Ana', 'ana@talhaoemdia.local', 'scrypt:32768:8:1$lCEgLAwUQhTJWOl6$490f66179ca1223b9a65d2cd9e0e556d9984d3de395d42fad916c6088400c51b4c97dd49fa335d98903fb04b5e0828b65a8a91963ba55a60572bb17b4f90a00d', 'agronomo'),
  (5, 'Rita', 'rita@talhaoemdia.local', 'scrypt:32768:8:1$lCEgLAwUQhTJWOl6$490f66179ca1223b9a65d2cd9e0e556d9984d3de395d42fad916c6088400c51b4c97dd49fa335d98903fb04b5e0828b65a8a91963ba55a60572bb17b4f90a00d', 'produtor');

INSERT INTO propriedades (id, dono_id, nome, municipio) VALUES
  (1, 2, 'Sítio Boa Vista', 'Garça'),
  (2, 5, 'Sítio São José', 'Pompeia');

INSERT INTO membros (propriedade_id, usuario_id) VALUES
  (1, 2), (1, 3), (1, 4),
  (2, 5);

INSERT INTO talhoes (id, propriedade_id, nome, area_ha, cultura) VALUES
  (1, 1, 'Baixada', 4.50, 'Café arábica'),
  (2, 1, 'Alto', 5.00, 'Café arábica'),
  (3, 1, 'Represa', 3.50, 'Café arábica'),
  (4, 1, 'Divisa', 5.00, 'Café arábica'),
  (5, 2, 'Talhão único', 12.00, 'Café arábica');

INSERT INTO produtos (id, propriedade_id, nome, carencia_dias, unidade) VALUES
  (1, 1, 'Fungicida cúprico', 7, 'kg'),
  (2, 1, 'Inseticida para bicho-mineiro', 30, 'L'),
  (3, 1, 'Fungicida para ferrugem', 45, 'L'),
  (4, 1, 'Herbicida pós-emergente', 15, 'L'),
  (5, 2, 'Fungicida cúprico', 7, 'kg');

INSERT INTO aplicacoes (talhao_id, produto_id, data_aplicacao, dose, aplicador, observacao, registrado_por) VALUES
  (1, 3, CURDATE() - INTERVAL 12 DAY, 0.75, 'Diego', '', 3),
  (1, 1, CURDATE() - INTERVAL 40 DAY, 2.00, 'Diego', 'Depois da chuva de pedra.', 3),
  (2, 1, CURDATE() - INTERVAL 20 DAY, 2.00, 'Diego', '', 3),
  (3, 2, CURDATE() - INTERVAL 5 DAY, 0.50, 'Marcos', 'Mancha de bicho-mineiro na parte de cima.', 2),
  (5, 5, CURDATE() - INTERVAL 3 DAY, 2.50, 'Rita', '', 5);
