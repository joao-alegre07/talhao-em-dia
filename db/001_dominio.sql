-- Domínio do Talhão em Dia: propriedades, equipe, talhões, produtos e o
-- caderno de aplicações. Dá pra rodar de novo sem estragar nada.

-- Os papéis antigos (usuario e admin) dão lugar aos do negócio. Quem tinha
-- conta comum vira produtor; admin continua sendo da plataforma.
UPDATE usuarios SET role = 'produtor' WHERE role = 'usuario';
ALTER TABLE usuarios ALTER COLUMN role SET DEFAULT 'produtor';

-- Tabelas do sistema anterior que não servem mais pra nada.
DROP TABLE IF EXISTS favoritos;
DROP TABLE IF EXISTS comentarios;
DROP TABLE IF EXISTS perfis;

-- A propriedade (o sítio) é o cliente do SaaS: todo dado abaixo dela só é
-- visto por quem faz parte dela. Quem cria é o produtor, que fica de dono.
CREATE TABLE IF NOT EXISTS propriedades (
  id INT AUTO_INCREMENT PRIMARY KEY,
  dono_id INT NOT NULL,
  nome VARCHAR(100) NOT NULL,
  municipio VARCHAR(100) NOT NULL,
  criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (dono_id) REFERENCES usuarios(id)
);

-- Quem enxerga cada propriedade: o dono, e os funcionários e agrônomos que
-- entraram por convite.
CREATE TABLE IF NOT EXISTS membros (
  propriedade_id INT NOT NULL,
  usuario_id INT NOT NULL,
  entrou_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (propriedade_id, usuario_id),
  FOREIGN KEY (propriedade_id) REFERENCES propriedades(id),
  FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
);

-- Link que o produtor manda pelo WhatsApp. Vale 7 dias e uma vez só.
CREATE TABLE IF NOT EXISTS convites (
  token VARCHAR(64) PRIMARY KEY,
  propriedade_id INT NOT NULL,
  papel VARCHAR(20) NOT NULL,
  criado_por INT NOT NULL,
  criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  expira_em DATETIME NOT NULL,
  usado_por INT,
  usado_em DATETIME,
  FOREIGN KEY (propriedade_id) REFERENCES propriedades(id),
  FOREIGN KEY (criado_por) REFERENCES usuarios(id),
  FOREIGN KEY (usado_por) REFERENCES usuarios(id)
);

CREATE TABLE IF NOT EXISTS talhoes (
  id INT AUTO_INCREMENT PRIMARY KEY,
  propriedade_id INT NOT NULL,
  nome VARCHAR(60) NOT NULL,
  area_ha DECIMAL(7,2) NOT NULL,
  cultura VARCHAR(60) NOT NULL,
  criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (propriedade_id, nome),
  FOREIGN KEY (propriedade_id) REFERENCES propriedades(id)
);

-- Defensivos que a propriedade usa, com a carência que está na bula.
CREATE TABLE IF NOT EXISTS produtos (
  id INT AUTO_INCREMENT PRIMARY KEY,
  propriedade_id INT NOT NULL,
  nome VARCHAR(100) NOT NULL,
  carencia_dias INT NOT NULL,
  unidade VARCHAR(5) NOT NULL,
  criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (propriedade_id, nome),
  FOREIGN KEY (propriedade_id) REFERENCES propriedades(id)
);

-- Cada linha é uma anotação do caderno de campo. Quem aplicou pode ser um
-- diarista sem conta, por isso é texto; quem registrou é sempre um usuário.
-- A dose é por hectare, na unidade do produto. A receita (foto ou PDF) fica
-- no object storage e aqui vai só a chave.
CREATE TABLE IF NOT EXISTS aplicacoes (
  id INT AUTO_INCREMENT PRIMARY KEY,
  talhao_id INT NOT NULL,
  produto_id INT NOT NULL,
  data_aplicacao DATE NOT NULL,
  dose DECIMAL(8,2) NOT NULL,
  aplicador VARCHAR(100) NOT NULL,
  observacao VARCHAR(500) NOT NULL DEFAULT '',
  receita_key VARCHAR(255),
  registrado_por INT NOT NULL,
  criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  atualizado_em TIMESTAMP NULL DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP,
  INDEX (talhao_id, data_aplicacao),
  FOREIGN KEY (talhao_id) REFERENCES talhoes(id),
  FOREIGN KEY (produto_id) REFERENCES produtos(id),
  FOREIGN KEY (registrado_por) REFERENCES usuarios(id)
);
