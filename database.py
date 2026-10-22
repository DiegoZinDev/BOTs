import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "produtos.db")


def get_connection():
    """Retorna uma conexão ativa com o banco SQLite."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Permite acessar colunas por nome: row['titulo']
    return conn


def init_db():
    """Cria a tabela de ofertas se ela ainda não existir."""
    query = """
    CREATE TABLE IF NOT EXISTS produtos_ofertas (
        asin TEXT PRIMARY KEY,
        titulo TEXT NOT NULL,
        link_afiliado TEXT NOT NULL,
        imagem_url TEXT,
        
        -- Preços e Desconto
        preco_atual REAL NOT NULL,
        preco_original REAL,
        desconto_pct INTEGER DEFAULT 0,
        
        -- Prova Social e Selos
        avaliacao_nota REAL,
        avaliacao_qtd INTEGER,
        vendas_mes TEXT,
        is_prime INTEGER DEFAULT 0,  -- 0 para False, 1 para True
        badge TEXT,                   -- 'Mais vendido', 'Escolha da Amazon', etc.
        
        -- Controle do Bot
        postado INTEGER DEFAULT 0,    -- 0 para Não, 1 para Sim
        data_ultima_postagem TEXT,
        atualizado_em TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query)
        # Índice para agilizar a busca de ofertas não postadas
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_ofertas_pendentes ON produtos_ofertas (postado, desconto_pct);"
        )
        conn.commit()
    print(f"Banco de dados inicializado em: {DB_PATH}")


def salvar_produto(produto: dict) -> bool:
    """
    Insere ou atualiza um produto no banco (UPSERT).
    Se o produto já existir, atualiza preço, desconto e notas, 
    mas MANTÉM o status de postado para evitar duplicar envio no grupo.
    """
    query = """
    INSERT INTO produtos_ofertas (
        asin, titulo, link_afiliado, imagem_url,
        preco_atual, preco_original, desconto_pct,
        avaliacao_nota, avaliacao_qtd, vendas_mes,
        is_prime, badge, atualizado_em
    ) VALUES (
        :asin, :titulo, :link_afiliado, :imagem_url,
        :preco_atual, :preco_original, :desconto_pct,
        :avaliacao_nota, :avaliacao_qtd, :vendas_mes,
        :is_prime, :badge, datetime('now', 'localtime')
    )
    ON CONFLICT(asin) DO UPDATE SET
        titulo = excluded.titulo,
        link_afiliado = excluded.link_afiliado,
        imagem_url = excluded.imagem_url,
        preco_atual = excluded.preco_atual,
        preco_original = excluded.preco_original,
        desconto_pct = excluded.desconto_pct,
        avaliacao_nota = excluded.avaliacao_nota,
        avaliacao_qtd = excluded.avaliacao_qtd,
        vendas_mes = excluded.vendas_mes,
        is_prime = excluded.is_prime,
        badge = excluded.badge,
        atualizado_em = datetime('now', 'localtime');
    """
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, produto)
            conn.commit()
            return True
    except Exception as e:
        print(f"Erro ao salvar produto {produto.get('asin')}: {e}")
        return False


def obter_proxima_oferta(filtro_ouro: bool = True, intervalo_dias: int = 2):
    """
    Retorna a melhor oferta elegível para postagem.
    Regra de Cooldown:
      - Só seleciona produtos nunca postados (data_ultima_postagem IS NULL)
      - OU produtos postados há mais de `intervalo_dias` (ex: 2 dias atrás).
    Se filtro_ouro=True, aplica os critérios de conversão:
      - Nota >= 4.3
      - Avaliações >= 100
      - Desconto >= 10% OU selo de destaque
    """
    condicoes = [
        f"(data_ultima_postagem IS NULL OR data_ultima_postagem <= datetime('now', '-{intervalo_dias} days', 'localtime'))"
    ]
    
    if filtro_ouro:
        condicoes.append("avaliacao_nota >= 4.3")
        condicoes.append("avaliacao_qtd >= 100")
        condicoes.append("(desconto_pct >= 10 OR badge IS NOT NULL OR vendas_mes IS NOT NULL)")

    where_clause = " AND ".join(condicoes)
    query = f"""
    SELECT * FROM produtos_ofertas
    WHERE {where_clause}
    ORDER BY 
        CASE WHEN data_ultima_postagem IS NULL THEN 0 ELSE 1 END,
        CASE WHEN badge = 'Mais vendido' OR badge = '1º Mais Vendido' THEN 1 ELSE 2 END,
        desconto_pct DESC,
        avaliacao_qtd DESC
    LIMIT 1;
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query)
        row = cursor.fetchone()
        return dict(row) if row else None


def marcar_como_postado(asin: str):
    """Marca o produto como postado e registra a data/hora atual."""
    query = """
    UPDATE produtos_ofertas
    SET postado = 1,
        data_ultima_postagem = datetime('now', 'localtime')
    WHERE asin = ?;
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, (asin,))
        conn.commit()


def total_produtos(intervalo_dias: int = 2):
    """Retorna estatísticas rápidas do banco considerando o intervalo de dias."""
    query = f"""
    SELECT 
        COUNT(*) as total,
        COALESCE(SUM(CASE WHEN data_ultima_postagem IS NULL OR data_ultima_postagem <= datetime('now', '-{intervalo_dias} days', 'localtime') THEN 1 ELSE 0 END), 0) as disponiveis,
        COALESCE(SUM(CASE WHEN data_ultima_postagem IS NOT NULL AND data_ultima_postagem > datetime('now', '-{intervalo_dias} days', 'localtime') THEN 1 ELSE 0 END), 0) as em_cooldown
    FROM produtos_ofertas;
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query)
        return dict(cursor.fetchone())


def obter_asins_cadastrados() -> set[str]:
    """Retorna um conjunto (set) com todos os ASINs que já estão no banco de dados."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT asin FROM produtos_ofertas;")
        return {row["asin"] for row in cursor.fetchall()}


if __name__ == "__main__":
    init_db()
    stats = total_produtos()
    print(f"Status do banco: {stats}")
    print(f"Total de ASINs cadastrados: {len(obter_asins_cadastrados())}")
