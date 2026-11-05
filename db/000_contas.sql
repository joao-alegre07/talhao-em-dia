-- Contas e senhas, do auth-service. É o que já existia antes do domínio do
-- Talhão em Dia; as migrações seguintes partem daqui.
CREATE TABLE IF NOT EXISTS usuarios (
  id INT AUTO_INCREMENT PRIMARY KEY,
  nome VARCHAR(100) NOT NULL,
  email VARCHAR(150) UNIQUE NOT NULL,
  senha_hash VARCHAR(255) NOT NULL,
  role VARCHAR(20) NOT NULL DEFAULT 'usuario',
  criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Plano pago (Stripe). Do pagamento, o banco guarda só os IDs do cliente e da
-- assinatura no Stripe -- nada de cartão.
ALTER TABLE usuarios
  ADD COLUMN IF NOT EXISTS premium BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS stripe_customer_id VARCHAR(255),
  ADD COLUMN IF NOT EXISTS stripe_subscription_id VARCHAR(255);

CREATE TABLE IF NOT EXISTS reset_tokens (
  token VARCHAR(64) PRIMARY KEY,
  usuario_id INT NOT NULL,
  criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  expira_em TIMESTAMP NOT NULL,
  usado BOOLEAN NOT NULL DEFAULT FALSE,
  FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
);
