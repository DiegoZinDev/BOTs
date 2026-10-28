import re
import sys
import random
import time
from playwright.sync_api import sync_playwright
from database import init_db, salvar_produto, total_produtos, obter_asins_cadastrados

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

# Configurações do Afiliado e Busca
TAG_AFILIADO = "diego07306-20"  # Sua tag oficial de associado Amazon
COOKIES_AMAZON = "./data/sessaoAmazon"
TERMOS_BUSCA = [
    "perfumes masculinos importados",
    "perfumes femininos importados",
]


def limpar_preco(texto: str) -> float | None:
    """Converte 'R$ 189,90' ou '1.250,00' em float (ex: 189.90)."""
    if not texto:
        return None
    limpo = re.sub(r"[^\d,\.]", "", texto)
    if "," in limpo:
        limpo = limpo.replace(".", "").replace(",", ".")
    try:
        return float(limpo)
    except ValueError:
        return None


def limpar_nota(texto: str) -> float | None:
    """Extrai '4,6' de '4,6 de 5 estrelas' e converte para float 4.6."""
    if not texto:
        return None
    match = re.search(r"(\d+[.,]\d+)", texto)
    if match:
        return float(match.group(1).replace(",", "."))
    return None


def limpar_qtd_avaliacoes(texto: str) -> int | None:
    """Extrai quantidade de avaliações, tratando formatos como '29,8 mil' ou '1.450'."""
    if not texto:
        return None
    texto_lower = texto.lower()
    if "mil" in texto_lower:
        match = re.search(r"([\d,\.]+)", texto_lower)
        if match:
            num = float(match.group(1).replace(",", "."))
            return int(num * 1000)
    digitos = re.sub(r"\D", "", texto)
    return int(digitos) if digitos else None


# Palavras que confirmam que o produto é uma fragrância/perfume
TERMOS_POSITIVOS_PERFUME = [
    "perfume", "eau de parfum", "eau de toilette", "eau de cologne",
    " edp", " edt", " edc", "colônia", "colonia", "deo colônia", "deo colonia",
    "fragrância", "fragrancia", "fragrance", "parfum"
]

# Itens que a Amazon costuma misturar na busca e que DEVEM ser descartados
TERMOS_NEGATIVOS_PERFUME = [
    "shampoo", "condicionador", "sabonete", "desodorante", "antitranspirante",
    "creme corporal", "loção corporal", "locao corporal", "hidratante",
    "barbeador", "aparador", "escova", "difusor", "aromatizador",
    "vela aromática", "vela aromatica", "óleo essencial", "oleo essencial",
    "porta perfume", "porta-perfume", "frasco vazio", "atomizador recarregável", "atomizador recarregavel"
]


def eh_perfume(titulo: str, card_texto: str = "") -> bool:
    """Verifica se o item é legitimamente um perfume/fragrância e descarta produtos aleatórios."""
    alvo = f"{titulo} {card_texto}".lower()

    # 1. Se tiver termos estritamente indesejados (frascos vazios, shampoos, eletrônicos, etc.)
    for negativo in TERMOS_NEGATIVOS_PERFUME:
        if negativo in alvo:
            return False

    # 2. Precisa conter ao menos um termo característico de perfume
    for positivo in TERMOS_POSITIVOS_PERFUME:
        if positivo in alvo:
            return True

    return False




def extrair_dados_card(card) -> dict | None:
    """Extrai todas as informações de um card de produto no resultado de busca."""
    try:
        asin = card.get_attribute("data-asin")
        if not asin or len(asin.strip()) == 0:
            return None  # Não é um produto real (espaçador publicitário)

        # 1. Título
        titulo_el = card.locator("h2 a span, h2 span, h2").first
        titulo = titulo_el.inner_text().strip() if titulo_el.count() > 0 else "Sem título"

        # 2. Link canônico com tag de afiliado (limpo e sem parâmetros de rastreamento da busca)
        link_afiliado = f"https://www.amazon.com.br/dp/{asin}?tag={TAG_AFILIADO}"

        # 3. Imagem
        img_el = card.locator("img.s-image").first
        imagem_url = img_el.get_attribute("src") if img_el.count() > 0 else None

        # 4. Preço Atual ("Por")
        preco_atual = None
        preco_atual_el = card.locator("span.a-price:not(.a-text-price) span.a-offscreen").first
        if preco_atual_el.count() > 0:
            preco_atual = limpar_preco(preco_atual_el.inner_text())

        if not preco_atual:
            # Sem preço disponível (esgotado ou formato diferente)
            return None

        # 5. Preço Original Riscado ("De")
        preco_original = None
        preco_orig_el = card.locator("span.a-price.a-text-price span.a-offscreen").first
        if preco_orig_el.count() > 0:
            preco_original = limpar_preco(preco_orig_el.inner_text())

        # 6. Cálculo de Desconto (% OFF)
        desconto_pct = 0
        if preco_original and preco_original > preco_atual:
            desconto_pct = round(((preco_original - preco_atual) / preco_original) * 100)

        # 7. Nota Média (Estrelas)
        nota = None
        nota_el = card.locator("i.a-icon-star-small span.a-icon-alt, span.a-icon-alt").first
        if nota_el.count() > 0:
            nota = limpar_nota(nota_el.inner_text())

        # 8. Qtd de Avaliações
        qtd_avaliacoes = None
        qtd_el = card.locator("span.a-size-base.s-underline-text, a[href*='#customerReviews'] span").first
        if qtd_el.count() > 0:
            qtd_avaliacoes = limpar_qtd_avaliacoes(qtd_el.inner_text())

        # 9. Vendas Recentes ("Mais de X compras no mês passado")
        vendas_mes = None
        card_text = card.inner_text()
        vendas_match = re.search(r"(Mais de [\d\w\s]+ compras no m[êe]s passado)", card_text, re.IGNORECASE)
        if vendas_match:
            vendas_mes = vendas_match.group(1).strip()

        # 10. Selo Amazon Prime
        is_prime = 1 if card.locator("i.a-icon-prime, span[aria-label*='Prime']").count() > 0 else 0

        # 11. Selos / Badges Oficiais
        badge = None
        badge_el = card.locator("span.a-badge-text, span.a-badge-label").first
        if badge_el.count() > 0:
            badge = badge_el.inner_text().strip()
        elif "mais vendido" in card_text.lower():
            badge = "1º Mais Vendido"
        elif "escolha da amazon" in card_text.lower():
            badge = "Escolha da Amazon"

        return {
            "asin": asin,
            "titulo": titulo,
            "link_afiliado": link_afiliado,
            "imagem_url": imagem_url,
            "preco_atual": preco_atual,
            "preco_original": preco_original,
            "desconto_pct": desconto_pct,
            "avaliacao_nota": nota,
            "avaliacao_qtd": qtd_avaliacoes,
            "vendas_mes": vendas_mes,
            "is_prime": is_prime,
            "badge": badge,
        }
    except Exception as e:
        print(f"Erro ao processar card: {e}")
        return None


def raspar_busca(termo_busca: str, max_paginas: int = 10):
    """
    Abre a busca na Amazon, coleta os produtos página por página
    até atingir `max_paginas` (padrão 10) ou acabar os resultados.
    """
    init_db()

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            COOKIES_AMAZON,
            headless=False,
            slow_mo=200
        )

        page = context.pages[0] if context.pages else context.new_page()

        print("Acessando Amazon Brasil...")
        page.goto("https://www.amazon.com.br")

        # Localiza a barra de pesquisa
        barra_pesquisa = page.locator("#twotabsearchtextbox")
        barra_pesquisa.wait_for(state="visible", timeout=15000)

        print(f"Pesquisando por: '{termo_busca}'")
        barra_pesquisa.fill("")
        barra_pesquisa.press_sequentially(termo_busca, delay=random.randint(20, 60))
        barra_pesquisa.press("Enter")

        # Carrega os ASINs que já estão no banco para não processar nem poluir o banco
        asins_existentes = obter_asins_cadastrados()
        print(f"Total de produtos já cadastrados no banco: {len(asins_existentes)}")

        selector_card = 'div[data-component-type="s-search-result"]'
        novos_inseridos_total = 0
        pulados_total = 0
        nao_perfumes_total = 0

        for pagina_atual in range(1, max_paginas + 1):
            print(f"\n==========================================")
            print(f"📖 Processando Página {pagina_atual} de {max_paginas}...")
            print(f"==========================================")

            # Aguarda os resultados da página carregarem
            page.wait_for_selector(selector_card, state="visible", timeout=20000)

            # Rola a página suavemente para carregar imagens e o rodapé com paginação
            page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
            time.sleep(1)
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(1.5)

            cards = page.locator(selector_card)
            total_cards = cards.count()
            print(f"Encontrados {total_cards} cards de produtos na página {pagina_atual}!\n")

            novos_na_pagina = 0
            pulados_na_pagina = 0

            for i in range(total_cards):
                card = cards.nth(i)
                asin = card.get_attribute("data-asin")

                if not asin or len(asin.strip()) == 0:
                    continue

                # Se o produto já foi pego antes, pula imediatamente sem gastar processamento
                if asin in asins_existentes:
                    pulados_na_pagina += 1
                    pulados_total += 1
                    print(f"⏩ [Já cadastrado]: ASIN {asin} já está no banco. Pulando...")
                    continue

                # Extrai os dados do card
                dados = extrair_dados_card(card)

                if dados:
                    # Filtro de Nicho: descarta produtos que não sejam fragrâncias/perfumes
                    card_texto = card.inner_text()
                    if not eh_perfume(dados["titulo"], card_texto):
                        nao_perfumes_total += 1
                        print(f"🚫 [Descartado - Não é perfume]: {dados['titulo'][:45]}...")
                        continue

                    sucesso = salvar_produto(dados)
                    if sucesso:
                        novos_na_pagina += 1
                        novos_inseridos_total += 1
                        asins_existentes.add(asin)  # Registra no set para evitar repetições
                        desconto_str = f"({dados['desconto_pct']}% OFF)" if dados['desconto_pct'] > 0 else ""
                        nota_str = f"⭐ {dados['avaliacao_nota']}" if dados['avaliacao_nota'] else "S/Nota"
                        badge_str = f"[{dados['badge']}]" if dados['badge'] else ""
                        print(f"✨ [Novo Salvo]: {dados['titulo'][:40]}... | R$ {dados['preco_atual']} {desconto_str} | {nota_str} {badge_str}")

            print(f"\n--> Resumo Página {pagina_atual}: +{novos_na_pagina} novos salvos | {pulados_na_pagina} pulados")

            # Se atingiu o limite de páginas estipulado, para por aqui
            if pagina_atual >= max_paginas:
                print(f"🛑 Limite de {max_paginas} páginas atingido com sucesso.")
                break

            # Localiza o botão 'Próximo' (na Amazon é a tag <a> com classe s-pagination-next)
            btn_proximo = page.locator("a.s-pagination-next, a[aria-label*='próxima página'], a:has-text('Próximo')").first

            # Se o botão não existir ou for um <span> desabilitado, significa que é a última página
            if btn_proximo.count() == 0 or not btn_proximo.is_visible():
                print("🛑 Botão 'Próximo' não disponível. Chegamos ao fim dos resultados na Amazon.")
                break

            classes = btn_proximo.get_attribute("class") or ""
            if "s-pagination-disabled" in classes:
                print("🛑 Última página da Amazon atingida.")
                break

            print(f"➡️ Navegando para a página {pagina_atual + 1}...")
            btn_proximo.click()
            time.sleep(random.uniform(2, 3.5))  # Pausa humanizada entre páginas

        print("\n==========================================")
        print(f"Relatório Final da busca '{termo_busca}':")
        print(f" - Total de novos perfumes adicionados: {novos_inseridos_total}")
        print(f" - Total de produtos repetidos pulados: {pulados_total}")
        print(f" - Itens aleatórios descartados (não perfumes): {nao_perfumes_total}")
        stats = total_produtos()
        print(f" - Situação geral do banco: {stats}")
        print("==========================================\n")

        context.close()


if __name__ == "__main__":
    # Executa a busca paginando até a página 10
    raspar_busca("perfumes masculinos importados", max_paginas=25)