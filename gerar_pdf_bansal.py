# -*- coding: utf-8 -*-
"""Gera bansal_metodo.pdf: o método da replicação de Bansal et al. (2022), passo a passo.

Cada passo diz a função do código que o executa e a fórmula do paper que ela implementa.
Contas, fórmulas das variáveis, adaptações e constantes são lidas dos próprios módulos,
para o PDF não divergir do código. Não traz resultados numéricos.
"""
import sqlite3
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, Frame, PageBreak, PageTemplate, Paragraph, Spacer, Table,
                                TableStyle)
from reportlab.platypus.tableofcontents import TableOfContents

import dsmlpi as dm
import painel_bansal as pb
import segundo_estagio as se

SAIDA = pb.PASTA / "bansal_metodo.pdf"
FONTES = Path(r"C:\Windows\Fonts")

pdfmetrics.registerFont(TTFont("Arial", str(FONTES / "arial.ttf")))
pdfmetrics.registerFont(TTFont("Arial-Bold", str(FONTES / "arialbd.ttf")))
pdfmetrics.registerFont(TTFont("Arial-Italic", str(FONTES / "ariali.ttf")))
pdfmetrics.registerFont(TTFont("Arial-BoldItalic", str(FONTES / "arialbi.ttf")))
pdfmetrics.registerFont(TTFont("Mono", str(FONTES / "consola.ttf")))
pdfmetrics.registerFontFamily("Arial", normal="Arial", bold="Arial-Bold", italic="Arial-Italic",
                              boldItalic="Arial-BoldItalic")

AZUL = colors.HexColor("#1F4E79")
CINZA = colors.HexColor("#F2F2F2")
AMARELO = colors.HexColor("#FFF2CC")

TXT = ParagraphStyle("txt", fontName="Arial", fontSize=9.5, leading=13, alignment=TA_JUSTIFY, spaceAfter=5)
H1 = ParagraphStyle("h1", fontName="Arial-Bold", fontSize=15, leading=19, textColor=AZUL, spaceBefore=14,
                    spaceAfter=8, keepWithNext=1)
H2 = ParagraphStyle("h2", fontName="Arial-Bold", fontSize=11.5, leading=15, textColor=AZUL, spaceBefore=8,
                    spaceAfter=4, keepWithNext=1)
EQ = ParagraphStyle("eq", fontName="Arial", fontSize=9.5, leading=15, leftIndent=0.8 * cm, spaceAfter=3)
CEL = ParagraphStyle("cel", fontName="Arial", fontSize=8, leading=10)
CEL_B = ParagraphStyle("celb", parent=CEL, fontName="Arial-Bold")
NOTA = ParagraphStyle("nota", parent=TXT, fontSize=9, leading=12, backColor=AMARELO, borderPadding=5,
                      leftIndent=5, rightIndent=5, spaceBefore=4, spaceAfter=8)
TITULO = ParagraphStyle("tit", fontName="Arial-Bold", fontSize=20, leading=25, textColor=AZUL, spaceAfter=12)
TOC1 = ParagraphStyle("toc1", fontName="Arial", fontSize=10, leading=15, leftIndent=0.3 * cm)
TOC2 = ParagraphStyle("toc2", fontName="Arial", fontSize=9, leading=12, leftIndent=1.0 * cm)


def c(nome):
    """Nome de função, constante ou arquivo do código."""
    return f'<font name="Mono" size="8.5" color="#833C0B">{escape(nome)}</font>'


def p(texto):
    return Paragraph(texto, TXT)


def eq(texto, numero=""):
    n = f'<font color="#1F4E79">&nbsp;&nbsp;&nbsp;&nbsp;{numero}</font>' if numero else ""
    return Paragraph(texto + n, EQ)


def nota(texto):
    return Paragraph(texto, NOTA)


def tabela(linhas, larguras, cabecalho=True):
    dados = [[Paragraph(str(x), CEL_B if (cabecalho and i == 0) else CEL) for x in linha]
             for i, linha in enumerate(linhas)]
    t = Table(dados, colWidths=larguras, repeatRows=1 if cabecalho else 0)
    estilo = [("GRID", (0, 0), (-1, -1), 0.4, colors.grey), ("VALIGN", (0, 0), (-1, -1), "TOP"),
              ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3)]
    if cabecalho:
        estilo.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DDEBF7")))
    t.setStyle(TableStyle(estilo))
    return t


def s(base, sup="", sub=""):
    """Símbolo com índice superior e inferior."""
    r = base
    if sup:
        r += f"<super>{sup}</super>"
    if sub:
        r += f"<sub>{sub}</sub>"
    return r


class Documento(BaseDocTemplate):
    def __init__(self, caminho):
        super().__init__(str(caminho), pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=2 * cm,
                         bottomMargin=2 * cm, title="Replicação de Bansal et al. (2022): método",
                         author="bacen_data")
        frame = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id="f")
        self.addPageTemplates([PageTemplate(id="p", frames=[frame], onPage=self._rodape)])

    def _rodape(self, canvas, doc):
        canvas.saveState()
        canvas.setFont("Arial", 8)
        canvas.setFillColor(colors.grey)
        canvas.drawString(2 * cm, 1.2 * cm, "Replicação de Bansal, Kumar, Mehra e Gulati (2022), Omega 107:102538")
        canvas.drawRightString(A4[0] - 2 * cm, 1.2 * cm, f"página {doc.page}")
        canvas.restoreState()

    def afterFlowable(self, f):
        if isinstance(f, Paragraph) and f.style.name in ("h1", "h2"):
            nivel = 0 if f.style.name == "h1" else 1
            texto = f.getPlainText()
            chave = f"s{self.seq.nextf('titulo')}"
            self.canv.bookmarkPage(chave)
            self.canv.addOutlineEntry(texto, chave, level=nivel)
            self.notify("TOCEntry", (nivel, texto, self.page, chave))


def nomes_contas():
    """Nome de cada conta no dicionário do IF.data (só leitura)."""
    try:
        con = pb.abrir_fonte()
        ph = ",".join("?" * len(pb.CONTAS))
        rows = con.execute(f"SELECT conta, num_relatorio, nome_coluna FROM contas WHERE conta IN ({ph})",
                           list(pb.CONTAS)).fetchall()
        con.close()
    except sqlite3.Error:
        return {}
    out = {}
    for conta, rel, nome in rows:
        if str(rel) == pb.CONTAS[str(conta)][0]:
            out[str(conta)] = " ".join(str(nome or "").split())
    return out


# ---------------------------------------------------------------- seções
def capa(h):
    h += [Paragraph("Replicação de Bansal et al. (2022) para bancos brasileiros S1 a S3", TITULO),
          p("<b>Método passo a passo:</b> o que cada parte do código faz e qual fórmula do paper ela implementa."),
          p("Paper replicado: Bansal, P., Kumar, S., Mehra, A. e Gulati, R. (2022). <i>Developing two dynamic "
            "Malmquist-Luenberger productivity indices: an illustrated application for assessing productivity "
            "performance of Indian banks</i>. Omega 107:102538."),
          p("Artigos-fonte usados na Tabela 5 e na Tabela 6: Chung, Färe e Grosskopf (1997), Journal of "
            "Environmental Management 51:229-240; Oh e Heshmati (2010), Energy Economics 32:1345-1355; "
            "Stiroh e Rumble (2006), Journal of Banking and Finance 30:2131-2161."),
          nota("<b>Regra deste documento.</b> Toda fórmula traz o número da equação, tabela ou seção do paper de "
               "onde vem. O que não está no paper aparece num quadro amarelo como este, marcado como "
               "<b>adaptação</b>, <b>decisão</b> ou <b>interpretação</b>, com o motivo. Este documento descreve só o "
               "método: não traz resultados numéricos."),
          Spacer(1, 8), Paragraph("Sumário", ParagraphStyle("sumario", parent=H2))]
    toc = TableOfContents()
    toc.levelStyles = [TOC1, TOC2]
    h += [toc, PageBreak()]


def secao1(h):
    h.append(Paragraph("1. Visão geral", H1))
    h.append(p("O objetivo é medir a mudança de produtividade dos bancos brasileiros entre 2015 e 2024 com os dois "
               "índices propostos por Bansal et al. (2022), que tratam o banco como uma rede de três divisões ligadas "
               "entre si e entre anos. Para comparação, calcula também os índices tradicionais sem rede (Tabela 5 "
               "do paper)."))
    h.append(Paragraph("1.1 Siglas", H2))
    siglas = [
        ["Sigla", "Descrição"],
        ["DMLPI", "Índice de produtividade Malmquist-Luenberger dinâmico em rede (modelo M1, fronteira do próprio ano)"],
        ["DSMLPI", "Índice de produtividade Malmquist-Luenberger dinâmico sequencial em rede (modelo M2, fronteira "
                   "com todos os anos até o ano avaliado)"],
        ["MLPI", "Índice de produtividade Malmquist-Luenberger tradicional, sem rede (Chung et al., 1997)"],
        ["SMLPI", "Índice de produtividade Malmquist-Luenberger sequencial, sem rede (Oh e Heshmati, 2010)"],
        ["DDF", "Função distância direcional: quanto o banco pode expandir o que é bom e contrair o que é ruim"],
        ["LP", "Programa linear (problema de otimização resolvido por banco e par de anos)"],
        ["DMU", "Unidade tomadora de decisão; aqui, cada banco"],
        ["EC", "Mudança de eficiência (aproximação do banco em relação à fronteira)"],
        ["TC", "Mudança técnica (deslocamento da fronteira)"],
        ["VRS / CRS", "Retornos variáveis / constantes de escala"],
        ["NPL", "Crédito inadimplente (níveis de risco E a H)"],
        ["PPS", "Conjunto de possibilidades de produção"],
        ["GMM", "Método generalizado dos momentos (regressão da Tabela 6)"],
        ["IF.data", "Base de dados contábeis das instituições do Banco Central"],
        ["SCR", "Sistema de Informações de Crédito do Banco Central (relatório 8 do IF.data)"],
        ["DRE", "Demonstração do resultado do exercício"],
        ["SGS", "Sistema Gerenciador de Séries Temporais do Banco Central"],
        ["ESTBAN", "Estatística Bancária Mensal por município (fonte do número de agências)"],
        ["CNPJ", "Cadastro Nacional da Pessoa Jurídica (aqui, a raiz de 8 dígitos)"],
        ["S1 a S3", "Segmentos prudenciais do Banco Central"],
        ["tcb", "Tipo de consolidado bancário do cadastro (B1 = banco comercial)"],
        ["PL", "Patrimônio líquido"],
    ]
    h.append(tabela(siglas, [2.4 * cm, 14.6 * cm]))
    h.append(Paragraph("1.2 Fluxo e arquivos", H2))
    fluxo = [
        ["Passo", "O que faz", "Onde está no código", "Base no paper"],
        ["1", "Seleciona a amostra e lê as contas", f"{c('painel_bansal.py')}: {c('amostra')}, {c('extrair_contas')}",
         "Seção 4.2"],
        ["2", "Monta os valores anuais e as 13 variáveis", f"{c('contas_anuais')}, {c('variaveis_nominais')}",
         "Tabela 1, seção 4.1"],
        ["3", "Deflaciona e normaliza por agência", f"{c('baixar_deflator')}, {c('baixar_estban')}, "
         f"{c('agencias')}, {c('montar_painel')}", "Seção 4.2"],
        ["4", "Estatísticas descritivas", c("tabela2"), "Tabela 2"],
        ["5", "Resolve os LPs do DMLPI e do DSMLPI", f"{c('dsmlpi.py')}: {c('calcular_rede')}",
         "Eq. (5)-(13) e (17)-(25)"],
        ["6", "Calcula EC, TC e o índice", c("indices"), "Eq. (14) e (26)"],
        ["7", "MLPI e SMLPI sem rede", c("calcular_ml"), "Seção 4.3.2; Chung (3.14)"],
        ["8", "Médias geométricas das tabelas", f"{c('tabela_por_ano')}, {c('tabela_por_banco')}, "
         f"{c('tabela_banco_ano')}", "Tabelas 3, 4, 5, B1, B2"],
        ["9", "Covariáveis do segundo estágio", f"{c('segundo_estagio.py')}: {c('covariaveis')}", "Seção 4.3.3"],
        ["10", "Tela. A planilha é gerada à parte", f"{c('app.py')} (aba Bansal) e {c('excel_bansal.py')}", "-"],
    ]
    h.append(tabela(fluxo, [1.1 * cm, 5.2 * cm, 6.7 * cm, 4.0 * cm]))
    h.append(p(f"A leitura e os downloads do deflator e da ESTBAN (Estatística Bancária Mensal por município) "
               f"usam {c('base_dados/base_dados.db')}. {c('abrir_fonte')} abre esse arquivo só em modo leitura; "
               f"{c('abrir_bansal')} grava o deflator e as agências."))


def secao2(h):
    h.append(Paragraph("2. Amostra", H1))
    h.append(p("O paper usa bancos comerciais com dados completos em todos os anos, num painel balanceado "
               "(seção 4.2). A função " + c("amostra") + " aplica esses critérios ao cadastro do IF.data:"))
    h.append(tabela([
        ["Critério", "Implementação"],
        ["Perímetro", f"Conglomerado financeiro ({c('TIPO')} = {pb.TIPO}), o único com o relatório 8 do SCR, de "
                      "onde sai o NPL."],
        ["Segmento", f"Cadastro de {pb.ANO_REF} com sr em S1, S2 ou S3, td = 'C' e cod_inst = cod_cong_financeiro."],
        ["Banco comercial", "tcb = B1 (seção 4.2: bancos comerciais). Os demais saem com o motivo."],
        ["Painel completo", f"{c('faltas_por_banco')}: o banco sai se faltar qualquer saldo usado em qualquer ano de "
                            f"{pb.ANOS[0]} a {pb.ANOS[-1]}. Nada é preenchido."],
        ["Código C no meio da janela", f"{c('codigo_anterior')}: o semestre anterior vem do CNPJ do único banco "
                                       f"comercial (B1) ligado ao conglomerado, se o ativo total (78182) varia no "
                                       f"máximo {pb.LIMITE_ATIVO:.0%}. Outra empresa do grupo não entra no lugar."],
    ], [3.2 * cm, 13.8 * cm]))
    h.append(p("Grupos de propriedade, como no paper (público e privado), mais o grupo estrangeiro: " +
               ", ".join(f"tc = {k}: {v}" for k, v in pb.GRUPOS.items()) + "."))
    h.append(nota("<b>Decisão desta replicação (regra dos nulos do relatório 8).</b> Um nível de risco nulo no "
                  f"relatório 8 vira zero só quando a identidade AA + A + ... + H + Total Exterior (23383) = Total "
                  f"Geral (24454) fecha, com diferença menor que R$ 1 ({c('zeros_verificados_rel8')}). Sem a "
                  "identidade o nulo continua ausente, e o banco sai por painel incompleto. O paper não trata esse "
                  "caso porque usa outra fonte de dados."))
    h.append(nota("<b>Adaptação L7 e L8.</b> Painel balanceado com uma fronteira única para todos os bancos da "
                  "amostra, sem fronteiras separadas por grupo. O perímetro, o período e a fonte são brasileiros; o "
                  "paper usa 42 bancos indianos de 2010 a 2017."))
    h.append(Paragraph("2.1 Quem fica de fora", H2))
    con = pb.abrir_fonte()
    try:
        amo = pb.amostra(con)
    finally:
        con.close()
    fora = amo[amo["status"] != "incluído"].sort_values(["sr", "nome"])
    s1 = int((fora["sr"] == "S1").sum())
    frase = (f"O cadastro de {pb.ANO_REF} tem {len(amo)} conglomerados em S1, S2 ou S3. "
             f"{len(fora)} ficam de fora e {len(amo) - len(fora)} entram.")
    if s1 == 0:
        frase += " Nenhum S1 fica de fora."
    h.append(p(frase + f" O motivo é o de {c('motivo_exclusao')}:"))
    linhas = [["Segmento", "Banco", "Por quê"]]
    for r in fora.itertuples():
        linhas.append([escape(str(r.sr)), escape(str(r.nome)), escape(str(r.motivo))])
    h.append(tabela(linhas, [2.2 * cm, 4.4 * cm, 10.4 * cm]))


def secao3(h, nomes):
    h.append(Paragraph("3. Contas e variáveis (Tabela 1 do paper)", H1))
    h.append(p("O paper define as variáveis da rede na Tabela 1 e na seção 4.1. A tabela abaixo liga cada papel da "
               "Tabela 1 à fórmula de contas do IF.data que o código usa (" + c("VARIAVEIS") + ", " + c("TABELA1") +
               ")."))
    linhas = [["Papel na Tabela 1", "Variável", "Fórmula (contas do IF.data)", "Adaptação"]]
    for papel, v in pb.TABELA1:
        nome, formula, _, _ = pb.VARIAVEIS[v]
        linhas.append([papel, nome, formula, escape(pb.ADAPTACOES.get(v, ""))])
    h.append(tabela(linhas, [4.0 * cm, 3.6 * cm, 4.2 * cm, 5.2 * cm]))
    h.append(Paragraph("3.1 Contas lidas e regra de junho e dezembro", H2))
    h.append(p(f"{c('extrair_contas')} lê as contas abaixo em junho e dezembro de cada ano, filtra cada conta ao seu "
               "relatório (o mesmo código aparece em outros relatórios) e recusa saldos conflitantes para a mesma "
               f"chave. Depois, {c('contas_anuais')} monta o valor anual:"))
    h.append(eq("saldo (balanço): valor anual = saldo de dezembro"))
    h.append(eq("fluxo (DRE): valor anual = acumulado de junho + acumulado de dezembro"))
    h.append(nota("<b>Adaptação L11.</b> A DRE do IF.data é acumulada no semestre (junho cobre janeiro a junho, "
                  "dezembro cobre julho a dezembro). Por isso o fluxo anual soma os dois semestres. O ano de "
                  f"{pb.ANOS[0]} entra só como defasagem (t−1), e os índices vão de {pb.ANOS[1]}-{pb.ANOS[2]} a "
                  f"{pb.ANOS[-2]}-{pb.ANOS[-1]}."))
    linhas = [["Conta", "Relatório", "Tipo", "Nome no IF.data"]]
    for conta, (rel, tipo) in pb.CONTAS.items():
        linhas.append([conta, rel, tipo, escape(nomes.get(conta, ""))])
    h.append(tabela(linhas, [1.6 * cm, 1.8 * cm, 1.6 * cm, 12.0 * cm]))
    h.append(p(f"{c('variaveis_nominais')} aplica a fórmula de cada variável da tabela anterior aos valores anuais. "
               "Quando a fórmula tem valor absoluto (trabalho), o absoluto é aplicado ao total."))
    h.append(p("O capital próprio precisa ser positivo (seção 3.1 do paper, insumo quase-fixo). "
               f"{c('montar_painel')} lista qualquer banco-ano com PL ≤ 0 como pendência e não calcula."))


def secao4(h):
    h.append(Paragraph("4. Deflação e normalização (seção 4.2)", H1))
    h.append(p("O paper deflaciona todas as variáveis, exceto o trabalho, pelo deflator implícito do PIB e divide "
               "todas pelo número de agências, seguindo Denizer et al. (seção 4.2)."))
    h.append(Paragraph("4.1 Deflator", H2))
    h.append(p(f"{c('baixar_deflator')} baixa a série SGS 1211 (variação anual % do deflator implícito do PIB) e monta "
               f"o índice com {pb.ANO_BASE_PRECOS} = 1, de trás para frente:"))
    h.append(eq(f"{s('P', sub=str(pb.ANO_BASE_PRECOS))} = 1"))
    h.append(eq(f"{s('P', sub='y−1')} = {s('P', sub='y')} / (1 + {s('v', sub='y')} / 100)"))
    h.append(p("em que v<sub>y</sub> é a variação % do ano y. O valor real é o valor nominal dividido por "
               "P<sub>y</sub>."))
    h.append(nota(f"<b>Adaptação.</b> Base de preços {pb.ANO_BASE_PRECOS} (o paper usa 2011-12 = 100). O "
                  "trabalho aqui é despesa de pessoal, em reais, e por isso também é deflacionado (L1). No paper o "
                  "trabalho é número de empregados e não é deflacionado."))
    h.append(Paragraph("4.2 Agências", H2))
    h.append(p(f"{c('baixar_estban')} lê a lista oficial de arquivos da página da ESTBAN ({c('URL_LISTA_ESTBAN')}), "
               f"baixa o arquivo de dezembro de cada ano e soma, por CNPJ, as colunas AGEN_ESPERADAS e "
               f"AGEN_PROCESSADAS de todos os municípios. {c('ler_estban')} localiza a linha de cabeçalho em vez de "
               f"supor quantas linhas pular e confere as colunas {', '.join(pb.COLS_ESTBAN)}."))
    h.append(p(f"{c('agencias')} liga cada CNPJ (cadastro, td = 'I', dezembro) ao seu conglomerado pelo "
               "cod_cong_financeiro daquele ano e soma:"))
    h.append(eq("agências<sub>banco, ano</sub> = Σ<sub>CNPJ do conglomerado</sub> AGEN_PROCESSADAS"))
    h.append(nota("<b>Decisão do usuário.</b> CNPJ com zero agência processada entra com 1 agência. Um banco não "
                  "opera com zero agência, e o zero é defeito do arquivo. O caso aparece listado na aba."))
    h.append(Paragraph("4.3 Normalização e unidade", H2))
    h.append(p(f"{c('montar_painel')} junta as variáveis nominais, o índice e as agências:"))
    h.append(eq(f"valor normalizado = valor nominal / P<sub>y</sub> / {pb.UNIDADE:,.0f} / agências"
                .replace(",", ".")))
    h.append(eq(f"trabalho = valor nominal / P<sub>y</sub> / {pb.UNIDADE:,.0f} (sem dividir por agências)"
                .replace(",", ".")))
    h.append(nota(f"<b>Decisão desta replicação (unidade).</b> {escape(pb.UNIDADE_NOME)}. A unidade importa, "
                  "porque as constantes subtrativas π e δ valem 1 na mesma unidade dos dados (seção 4.3.1). Com "
                  "outra unidade, os resultados mudam."))


def secao5(h):
    h.append(Paragraph("5. Estatísticas descritivas (Tabela 2)", H1))
    h.append(p(f"{c('tabela2')} calcula, para as 13 variáveis normalizadas, as mesmas colunas da Tabela 2 do paper:"))
    h.append(tabela([
        ["Coluna", "Fórmula"],
        ["Média", "x̄ = Σ x / n"],
        ["σ", "desvio-padrão amostral, √(Σ (x − x̄)² / (n − 1))"],
        ["Curtose", "curtose em excesso amostral (a mesma do CURT do Excel)"],
        ["Assimetria", "assimetria amostral (a mesma do DISTORÇÃO do Excel)"],
        ["Mediana, máximo, mínimo", "estatísticas de ordem"],
    ], [4 * cm, 13 * cm]))
    h.append(nota("<b>Interpretação.</b> O paper não diz se a curtose é em excesso nem se as fórmulas são "
                  "amostrais. O código usa as versões amostrais do pandas, que coincidem com as do Excel."))


def _restricoes_m1():
    lam = s("λ", "t+a", "jk")
    ob = lambda v, t="t+b": s(v, t, "ok")
    fr = lambda v, t="t+a": s(v, t, "jk")
    beta = s("β", "a,b", "o")
    return [
        ("(5)", f"Σ<sub>j</sub> {lam} {s('x', 't+a', 'ijk')} ≤ {s('x', 't+b', 'iok')} − {beta} "
                f"({s('x', 't+b', 'iok')} + {s('μ', 't+a', 'ik')})", "insumos desejáveis",
         "labor e fixed (λ1), interbank (λ2), llp (λ3)"),
        ("(6)", f"Σ<sub>j</sub> ({lam} + {s('φ', 't+a', 'jk')}) {s('v', 't+a', 'fjk')} ≤ {s('v', 't+b', 'fok')}",
         "insumo quase-fixo", "equity (λ1 + φ1)"),
        ("(7)", f"Σ<sub>j</sub> {lam} {fr('w')} ≥ {ob('w')} + {beta} ({ob('w')} − {s('ρ', 't+a', 'k')})",
         "insumo indesejável", "npl_lag (λ2)"),
        ("(8)", f"Σ<sub>j</sub> {lam} {s('y', 't+a', 'rjk')} ≥ {s('y', 't+b', 'rok')} + {beta} "
                f"({s('y', 't+b', 'rok')} − {s('ν', 't+a', 'rk')})", "saídas desejáveis", "nii, nonii (λ3)"),
        ("(9)", f"Σ<sub>j</sub> {lam} {s('u', 't+a', 'pjk')} ≤ {s('u', 't+b', 'pok')} − {beta} "
                f"({s('u', 't+b', 'pok')} + {s('ω', 't+a', 'pk')})", "saída indesejável", "npl (λ2)"),
        ("(10)", f"Σ<sub>j</sub> {lam} {fr('c')} ≥ {ob('c')} + {beta} ({ob('c')} − {s('γ', 't+a', 'k')})",
         "carryover desejável em t (saída)", "unused, profit (λ2)"),
        ("(11)", f"Σ<sub>j</sub> {lam} {fr('c', 't+a−1')} ≤ {ob('c', 't+b−1')} − {beta} "
                 f"({ob('c', 't+b−1')} + {s('α', 't+a−1', 'k')})", "carryover desejável em t−1 (insumo)",
         "unused_lag, profit_lag (λ2)"),
        ("(12)", f"Σ<sub>j</sub> {lam} {s('z', 't+a', 'gjk')} = Σ<sub>j</sub> {s('λ', 't+a', 'j,k+1')} "
                 f"{s('z', 't+a', 'gjk')}, k = 1, ..., K−1", "ligações entre divisões",
         "deposits (λ1 = λ2); performing, invest (λ2 = λ3)"),
        ("(13)", f"Σ<sub>j</sub> {lam} = 1, k = 1, ..., K; {beta} livre (qualquer real); "
                 f"{lam}, {s('φ', 't+a', 'jk')} ≥ 0",
         "convexidade (VRS) por divisão", "Σλ1 = Σλ2 = Σλ3 = 1; β livre"),
    ]


def secao6(h):
    h.append(Paragraph("6. Modelo M1: DMLPI, eq. (5) a (13)", H1))
    h.append(p("Para cada banco o (DMU<sub>o</sub>), cada par de anos (t, t+1) e cada combinação de a e b iguais a 0 ou 1, o "
               "modelo (M1)<sup>a,b</sup> calcula a DDF D<super>t+a</super>(dados de t+b): a distância do banco, "
               "com os dados do ano t+b, até a fronteira formada pelos bancos do ano t+a. São quatro LPs por banco e "
               "par de anos."))
    h.append(eq(f"D<super>t+a</super>(X<super>t+b</super>, V<super>t+b</super>, W<super>t+b</super>, "
                f"Y<super>t+b</super>, U<super>t+b</super>, C<super>t+b</super>) = max {s('β', 'a,b', 'o')}  "
                "sujeito a (5) a (13)"))
    h.append(Paragraph("6.1 Restrições", H2))
    h.append(p("j percorre os n bancos da fronteira, k as três divisões (K = 3). A última coluna diz quais variáveis "
               f"do código entram em cada restrição e com qual λ ({c('X_DIV')}, {c('V1')}, {c('W2')}, {c('Y3')}, "
               f"{c('U2')}, {c('C2')}, {c('C2_LAG')}, {c('Z12')}, {c('Z23')})."))
    linhas = [["Eq.", "Restrição do paper", "Papel", "No código"]]
    for n, r, papel, cod in _restricoes_m1():
        linhas.append([n, r, papel, cod])
    h.append(tabela(linhas, [1.0 * cm, 8.8 * cm, 3.1 * cm, 4.1 * cm]))
    h.append(p("As três divisões são a captação (1), o crédito (2) e a receita (3), como na Fig. 2 do paper. O φ só "
               "aparece na divisão 1, porque só ela tem insumo quase-fixo. O λ de cada divisão é um vetor com um "
               "peso por banco da fronteira."))
    h.append(Paragraph("6.2 Vetores de direção", H2))
    h.append(p(f"{c('direcoes')} calcula os vetores sobre os bancos da fronteira (seção 3.2), com as constantes da "
               f"seção 4.3.1: ξ = ξ′ = ξ″ = {dm.XI:g} e π = π′ = π″ = {dm.PI:g} ({c('XI')}, {c('PI')})."))
    for linha in [
        f"{s('μ', 't', 'ik')} = ξ × max<sub>j</sub> |{s('x', 't', 'ijk')}|",
        f"{s('ρ', 't', 'k')} = min<sub>j</sub> {s('w', 't', 'jk')} − π",
        f"{s('ν', 't', 'rk')} = min<sub>j</sub> {s('y', 't', 'rjk')} − π′",
        f"{s('ω', 't', 'pk')} = ξ′ × max<sub>j</sub> |{s('u', 't', 'pjk')}|",
        f"{s('γ', 't', 'k')} = min<sub>j</sub> {s('c', 't', 'jk')} − π″",
        f"{s('α', 't', 'k')} = ξ″ × max<sub>j</sub> |{s('c', 't', 'jk')}|",
    ]:
        h.append(eq(linha))
    h.append(p("O paper exige que os termos (x<sub>o</sub> + μ), (w<sub>o</sub> − ρ), (y<sub>o</sub> − ν), "
               "(u<sub>o</sub> + ω), (c<sub>o</sub> − γ) e (c<sub>o</sub><super>t+b−1</super> + α) sejam positivos "
               f"(texto após a eq. 13). {c('termos_direcao')} verifica cada termo em cada LP e a aba lista os que "
               "ficam ≤ 0. Nesses casos o Teorema 1 não vale e o LP pode ficar sem solução."))
    h.append(nota("<b>Interpretação (α da eq. 11).</b> A eq. (11) usa α<super>t+a−1</super>. O código calcula α "
                  "sobre os carryovers defasados dos bancos da fronteira do ano t+a, que são exatamente os valores do "
                  "ano t+a−1. No M1 isso coincide com a definição, porque ξ″ é o mesmo nos dois anos."))
    h.append(Paragraph("6.3 Como o LP é montado e resolvido", H2))
    h.append(p(f"As variáveis do LP são β, λ1, λ2, λ3 e φ1 ({c('montar_lp_rede')}). O programa maximiza β. "
               f"{c('resolver_lp')} minimiza −β, que é a mesma busca. Cada restrição é reescrita com β do lado esquerdo. "
               "Por exemplo, a eq. (5) vira β(x<sub>o</sub> + μ) + Σ λ x ≤ x<sub>o</sub>, e a eq. (7), que é ≥, "
               "é multiplicada por −1: β(w<sub>o</sub> − ρ) − Σ λ w ≤ −w<sub>o</sub>."))
    h.append(p("O paper resolve esse programa no LINGO e não descreve o algoritmo. Esta replicação usa um simplex "
               "em duas fases, escrito em Python, sem biblioteca. O objetivo e as restrições são os das equações. "
               "O algoritmo é uma adaptação."))
    h.append(p("β é livre e entra como β+ − β−, com as duas partes ≥ 0. Cada desigualdade vira igualdade com uma "
               "variável de folga. Cada igualdade recebe uma variável artificial na fase 1. A fase 1 minimiza a soma "
               "das artificiais. Se esse mínimo fica acima de zero, o programa não tem solução. A fase 2 minimiza −β, "
               "isto é, aumenta β."))
    h.append(p(f"O pivô é a eliminação de Gauss no quadro da base ({c('_pivota')}). A cada 20 pivôs a base é "
               f"reinvertida por eliminação de Gauss com pivô parcial ({c('_inverter')}). Empate usa a regra de Bland: "
               "entra a primeira coluna com custo reduzido negativo e, na saída, a de menor índice."))
    h.append(p(f"{c('otimo')} devolve β e os pesos. EC (mudança de eficiência), TC (mudança técnica) e o índice "
               f"ficam nas fórmulas das eq. (14) e (26), fora do programa linear. O programa da Tabela 5 "
               f"(Chung et al., 1997, eq. 3.14) usa o mesmo simplex, com variáveis β e z ({c('montar_lp_ml')})."))
    h.append(nota("<b>Decisão desta replicação (solver).</b> O paper usa LINGO. Aqui o mesmo programa linear é "
                  "resolvido por simplex em duas fases, na linha de comando. bansal.xlsx não executa o simplex: "
                  "liga ao arquivo solucoes.xlsx."))


def secao7(h):
    h.append(Paragraph("7. Modelo M2: DSMLPI, eq. (17) a (25)", H1))
    h.append(p("O M2 troca a fronteira do ano pela fronteira sequencial: todos os bancos de todos os anos de τ = 1 "
               "até t+a entram na fronteira (conjunto de produção sequencial, eq. 15). As restrições têm a mesma "
               "forma do M1, com Σ<sub>τ=1</sub><super>t+a</super> Σ<sub>j</sub> no lugar de Σ<sub>j</sub>, e a "
               f"convexidade (25) soma todos os λ<super>τ</super> de cada divisão. No código, {c('calcular_rede')} "
               f"passa a {c('fronteira')} os anos 0 a t+a do painel (o primeiro índice é "
               f"{pb.ANOS[1]}, que é τ = 1)."))
    h.append(eq(f"(17) Σ<sub>τ=1</sub><super>t+a</super> Σ<sub>j</sub> {s('λ', 'τ', 'jk')} {s('x', 'τ', 'ijk')} ≤ "
                f"{s('x', 't+b', 'iok')} − β ({s('x', 't+b', 'iok')} + {s('μ', 't+a', 'ik')})"))
    h.append(p("As eq. (18) a (22) e (24) repetem (6) a (10) e (12) com a soma em τ. As direções usam o máximo e o "
               "mínimo sobre todos os bancos e todos os anos até t (seção 3.3):"))
    h.append(eq(f"{s('μ', 't', 'ik')} = η × max<sub>j, τ ≤ t</sub> |{s('x', 'τ', 'ijk')}|,   "
                f"{s('ρ', 't', 'k')} = min<sub>j, τ ≤ t</sub> {s('w', 'τ', 'jk')} − δ,   e assim por diante"))
    br = lambda x: f"{x:g}".replace(".", ",")
    h.append(p(f"Constantes da seção 4.3.1: η = η′ = η″ = {br(dm.ETA_T)} e δ = δ′ = δ″ = {br(dm.DELTA)} para a "
               f"fronteira de t (a = 0); η = {br(dm.ETA_T1)} e δ = {br(dm.DELTA)} para a fronteira de t+1 (a = 1) "
               f"({c('ETA_T')}, {c('ETA_T1')}, {c('DELTA')})."))
    h.append(nota("<b>Interpretação (constantes por período).</b> O paper diz \"para o período t\" e \"para o período "
                  "t+1\". O código aplica o η de cada fronteira avaliada (a = 0 ou a = 1) a todas as direções dela, "
                  "inclusive ao α<super>t+a−1</super> da eq. (23)."))
    h.append(Paragraph("7.1 Eq. (23): carryover defasado", H2))
    h.append(p("O paper imprime a eq. (23) assim:"))
    h.append(eq(f"Σ<sub>τ</sub> Σ<sub>j</sub> {s('λ', 'τ', 'jk')} {s('c', 'τ', 'jk')} ≤ {s('c', 't+b−1', 'ok')} − β "
                f"({s('c', 't+b−1', 'ok')} + {s('α', 't+a−1', 'k')})", "(23) impressa"))
    h.append(p("O código implementa:"))
    h.append(eq(f"Σ<sub>τ</sub> Σ<sub>j</sub> {s('λ', 'τ', 'jk')} {s('c', 'τ−1', 'jk')} ≤ {s('c', 't+b−1', 'ok')} − β "
                f"({s('c', 't+b−1', 'ok')} + {s('α', 't+a−1', 'k')})", "(23) implementada"))
    h.append(nota("<b>Interpretação (erro de impressão).</b> O lado esquerdo impresso compara o carryover de t da "
                  "fronteira com o carryover de t−1 do banco avaliado. O conjunto sequencial da eq. (15) define "
                  "C<super>t−1</super> ≥ Σ Σ λ<super>τ</super> C<super>τ−1</super>, e a eq. (11) do M1 usa "
                  "c<super>t+a−1</super> dos dois lados. Por isso o código usa c<super>τ−1</super>."))
    h.append(Paragraph("7.2 Condição (16)", H2))
    h.append(p("O paper exige que as direções da fronteira de t+1 sejam mais apertadas que as de t, para garantir TC ≥ 1:"))
    h.append(eq(f"{s('μ', 't+1')} &lt; {s('μ', 't')},  {s('ρ', 't+1')} &gt; {s('ρ', 't')},  "
                f"{s('ν', 't+1')} &gt; {s('ν', 't')},  {s('ω', 't+1')} &lt; {s('ω', 't')},  "
                f"{s('γ', 't+1')} &gt; {s('γ', 't')},  {s('α', 't+1')} &lt; {s('α', 't')}", "(16)"))
    h.append(p(f"{c('calcular_rede')} compara as direções das duas fronteiras de cada par de anos e registra cada "
               "comparação. Com δ = 1 fixo pelo paper, as direções de mínimo (ρ, ν, γ) não mudam quando o mínimo da "
               "fronteira não muda, e a condição pode falhar. A falha é registrada na aba, sem ajuste das constantes, "
               "porque o paper fixa os valores."))


def secao8(h):
    h.append(Paragraph("8. Índices e decomposição, eq. (14) e (26)", H1))
    h.append(p(f"Com os quatro β de cada banco e par de anos, {c('indices')} calcula, com "
               "D<sub>ab</sub> = D<super>t+a</super>(dados de t+b):"))
    h.append(eq("índice = [ (1 + D<sub>00</sub>) / (1 + D<sub>01</sub>) × (1 + D<sub>10</sub>) / "
                "(1 + D<sub>11</sub>) ]<super>1/2</super>", "(14), (26)"))
    h.append(eq("EC = (1 + D<sub>00</sub>) / (1 + D<sub>11</sub>)"))
    h.append(eq("TC = [ (1 + D<sub>11</sub>) / (1 + D<sub>01</sub>) × (1 + D<sub>10</sub>) / "
                "(1 + D<sub>00</sub>) ]<super>1/2</super>"))
    h.append(p("índice = EC × TC. Índice maior que 1 é ganho de produtividade, menor que 1 é perda. O mesmo "
               "cálculo vale para DMLPI (eq. 14), DSMLPI (eq. 26), MLPI (Chung, eq. 3.5 a 3.7) e SMLPI "
               "(Oh e Heshmati, eq. 9 e 10)."))
    h.append(nota("<b>Decisão desta replicação (LP sem solução).</b> Os Teoremas 1 e 2 garantem β &gt; −1 quando os "
                  "termos de direção são positivos. Se algum dos quatro LPs não tem ótimo, ou se algum 1 + D ≤ 0, o "
                  "índice do banco naquele par fica vazio. Nada é estimado no lugar."))


def secao9(h):
    h.append(Paragraph("9. Tabela 5: MLPI e SMLPI sem rede", H1))
    h.append(p("Na seção 4.3.2 o paper compara os índices em rede com os índices tradicionais: ignora as divisões, usa "
               "os insumos da divisão 1, as saídas da divisão 3 e o NPL como saída indesejável, \"com direções de "
               f"insumos e produtos observados\". No código ({c('ML_X')}, {c('ML_Y')}, {c('ML_B')}):"))
    h.append(eq(f"insumos x = {', '.join(dm.ML_X)};  saídas y = {', '.join(dm.ML_Y)};  saída indesejável b = "
                f"{', '.join(dm.ML_B)}"))
    h.append(p(f"{c('resolver_ml')} resolve o LP de Chung et al. (1997), eq. (3.14), com z<sub>k</sub> os pesos dos "
               "bancos da fronteira:"))
    h.append(eq("max β  sujeito a"))
    h.append(eq("Σ<sub>k</sub> z<sub>k</sub> y<sub>km</sub> ≥ (1 + β) y<sub>k′m</sub>,  m = 1, ..., M"))
    h.append(eq("Σ<sub>k</sub> z<sub>k</sub> b<sub>ki</sub> = (1 − β) b<sub>k′i</sub>,  i = 1, ..., I"))
    h.append(eq("Σ<sub>k</sub> z<sub>k</sub> x<sub>kn</sub> ≤ (1 − β) x<sub>k′n</sub>,  n = 1, ..., N"))
    h.append(eq("z<sub>k</sub> ≥ 0", "(3.14)"))
    h.append(p("Sem restrição Σ z = 1: é CRS, como em Chung (nota da p. 235) e em Oh e Heshmati. O MLPI usa a "
               "fronteira do ano; o SMLPI (Oh e Heshmati, eq. 9 a 11) usa a fronteira sequencial com todos os anos "
               f"até t+a ({c('calcular_ml')})."))
    h.append(nota("<b>Decisões C1, P5 e P7.</b> CRS, como nos artigos-fonte (C1). Direção (−x, y, −b), com insumos "
                  "contraídos por (1 − β), pela \"direção de insumos e produtos observados\" do paper e pela eq. (3.14) "
                  f"(P7). A Tabela 5 usa só os bancos com margem de juros positiva em todos os anos ({c('amostra_tabela5')}, "
                  "P5), porque o modelo de Chung supõe saídas não negativas."))


def secao10(h):
    h.append(Paragraph("10. Agregação: Tabelas 3, 4, B1 e B2", H1))
    h.append(p("O paper apresenta médias geométricas dos índices e componentes (seção 4.3.1):"))
    h.append(eq("média geométrica = exp( Σ ln(índice) / n )"))
    h.append(tabela([
        ["Tabela", "Agregação", "Função"],
        ["3 e 5", "por ano e no período inteiro, por grupo: todos (Painel A), públicos (B), privados nacionais (C)",
         c("tabela_por_ano")],
        ["4", "por banco no período inteiro, com a média do grupo", c("tabela_por_banco")],
        ["B1 e B2", "banco × ano, sem agregação (B1 públicos, B2 privados nacionais)", c("tabela_banco_ano")],
    ], [2 * cm, 11 * cm, 4 * cm]))
    h.append(p("Num painel balanceado, a média geométrica do período é igual à média geométrica de todos os "
               "bancos-ano, que é o que o código calcula."))
    h.append(nota("<b>Decisão desta replicação (sem solução e extensões).</b> A média usa só os bancos-ano com "
                  f"solução ({c('gmean')}), e a coluna \"sem solução\" conta os que ficaram de fora ({c('sem_solucao')}). "
                  "Painéis extras, declarados como extensão: bancos estrangeiros e segmentos S1, S2 e S3."))
    h.append(nota("<b>Limitação.</b> O Painel D da Tabela 3 (teste de Li para comparar as distribuições de públicos e "
                  "privados) não foi implementado. O paper não traz a fórmula, e o artigo de Li (1996) não foi obtido "
                  "(pendência P1)."))


def secao11(h):
    h.append(Paragraph("11. Tabela 6: segundo estágio (seção 4.3.3)", H1))
    h.append(p("O paper regride cada índice e componente contra as covariáveis por GMM sistema em dois passos "
               "(Blundell e Bond, com correção de Windmeijer):"))
    h.append(eq("X<sub>jt</sub> = ϕ<sub>0</sub> + ϕ<sub>1</sub> X<sub>jt−1</sub> + Σ<sub>k=2</sub><super>K</super> "
                "ϕ<sub>k</sub> ln(Z<super>k</super>)<sub>jt</sub> + ε<sub>jt</sub>", "(seção 4.3.3)"))
    h.append(p(f"{c('covariaveis')} calcula as covariáveis a partir das contas anuais nominais (razões não dependem do "
               "deflator), para os anos de 2015 em diante:"))
    linhas = [["Covariável", "Definição no código"]]
    for k, v in se.COVARIAVEIS.items():
        linhas.append([k, escape(v)])
    h.append(tabela(linhas, [3.5 * cm, 13.5 * cm]))
    h.append(p("Stiroh e Rumble (2006), eq. (1) e (2): SH<sub>NET</sub> = NET / (NET + NON) e SH<sub>NON</sub> = "
               "NON / (NET + NON), com NET a margem de juros (78215 − 78213) e NON a receita não-juros "
               "(78216 + 78217)."))
    h.append(nota("<b>Limitação: a regressão GMM não foi estimada.</b> Pendências:<br/>" +
                  "<br/>".join(f"• {escape(x)}" for x in se.PENDENCIAS_GMM)))


def secao12(h):
    h.append(Paragraph("12. Verificações e planilha", H1))
    h.append(Paragraph("12.1 Verificações da aba", H2))
    h.append(tabela([
        ["Verificação", "O que prova", "Base"],
        ["LPs sem ótimo por modelo", "quantos LPs não tiveram solução", "Teoremas 1 e 2"],
        ["β ≤ −1", "casos em que 1 + D ≤ 0 e o índice fica indefinido", "Teoremas 1 e 2"],
        ["TC &lt; 1 no DSMLPI", "a fronteira sequencial não regride", "seção 3.3 e 4.3.1"],
        ["Condição (16)", "cada comparação das direções entre t e t+1", "eq. (16)"],
        ["Termos de direção ≤ 0", "onde a hipótese do Teorema 1 falha", "texto após a eq. (13)"],
        ["Lucro do Itaú 2024", "mostra junho, dezembro e a soma dos dois semestres da conta 78187",
         "regra da DRE semestral"],
        ["Nulos do relatório 8", "cada nulo convertido e a identidade usada", "decisão desta replicação"],
        ["Agências zeradas", "cada CNPJ que entrou com 1 agência", "decisão do usuário"],
    ], [4.2 * cm, 8.6 * cm, 4.2 * cm]))
    h.append(Paragraph("12.2 Planilha", H2))
    h.append(p(f"{c('gerar_excel')} grava {c('bansal.xlsx')}. Contas, deflator, agências, painel, direções, restrições, "
               "índices e tabelas são fórmula. β, λ, φ e z são número em solucoes.xlsx, gravado por "
               f"{c('python excel_bansal.py --solucionar')}, que executa o simplex da seção 6.3 ({c('otimo')}). "
               "A aba Solucao de bansal.xlsx liga a esse arquivo."))
    h.append(tabela([
        ["Planilha", "Conteúdo"],
        ["Contas", "saldos de junho e dezembro; o valor anual dos fluxos é fórmula (junho + dezembro)"],
        ["Deflator", "variação do SGS 1211 e o índice por fórmula, de trás para frente a partir de 2024 = 1"],
        ["Agencias", "agências por conglomerado e ano, com os CNPJs somados"],
        ["Painel", "variáveis nominais por fórmula a partir de Contas; normalizadas = nominal / índice / 10<super>6</super> "
                   "/ agências; defasagens apontando para a linha do ano anterior"],
        ["Fronteiras", "uma fronteira por modelo, par de anos e a, com fórmula para o Painel"],
        ["Direcoes", "μ, ρ, ν, ω, γ e α por MAX e MIN, com as constantes do paper"],
        ["Obs", "o banco avaliado, na ordem dos campos do programa linear"],
        ["Solucao", "ligação para solucoes.xlsx: β, status e pesos na mesma linha"],
        ["Restricoes", "lado esquerdo (SOMARPRODUTO), lado direito e folga de cada restrição, para todos os bancos e anos. "
                       "Folga ≥ 0, ou 0 na igualdade, prova a restrição"],
        ["Condicao16", "compara as direções do DSMLPI em t e em t+1"],
        ["Indices", "1 + D, EC, TC e índice pelas eq. (14) e (26), e os logaritmos, a partir do β da Solucao"],
        ["Tabelas", "Tabelas 2, 3, 4, 5, B1 e B2 por fórmula"],
    ], [3 * cm, 14 * cm]))
    h.append(nota("<b>Limitação.</b> Sem solucoes.xlsx na mesma pasta, a ligação da aba Solucao fica sem valor. "
                  "O Excel pede para atualizar as ligações ao abrir bansal.xlsx."))


def secao13(h):
    h.append(Paragraph("13. Limitações consolidadas", H1))
    h.append(p("Tudo o que diverge do paper ou não foi feito, num só lugar:"))
    h.append(tabela([
        ["Ponto", "O que acontece aqui", "Motivo"],
        ["Trabalho (L1)", "despesa de pessoal deflacionada, sem dividir por agências", "o IF.data não tem número de "
                                                                                     "empregados por conglomerado"],
        ["Empréstimos interbancários (L3)", "interfinanceiros + empréstimos e repasses", "estrutura do balanço brasileiro"],
        ["NPL (L4)", "carteira SCR nos níveis E a H, só o livro doméstico", "o relatório 8 não separa o exterior por nível"],
        ["Ativos ociosos (L5)", "o compulsório fica dentro", "o IF.data não separa o compulsório"],
        ["Margem de juros (L6)", "resultado de intermediação antes da PCLD, com derivativos e câmbio",
         "o IF.data não separa receita e despesa de juros puras"],
        ["Amostra e período (L7, L8, L11)", "painel balanceado brasileiro, 2014 a 2024, fronteira única",
         "fonte e período diferentes do paper"],
        ["Código C no meio da janela", "semestres anteriores no CNPJ do banco comercial, se o ativo total varia no máximo 15%",
         "o IF.data passa a publicar o conglomerado financeiro num código C"],
        ["Nulos do relatório 8", "zero só com a identidade de totais", "decisão desta replicação"],
        ["Agências zeradas", "entram com 1", "decisão do usuário"],
        ["Unidade", escape(pb.UNIDADE_NOME), "π e δ = 1 dependem da unidade"],
        ["Eq. (23)", "c<super>τ−1</super> no lado esquerdo", "erro de impressão, ver seção 7.1"],
        ["Condição (16)", "pode falhar com δ = 1; registrada, sem ajuste", "o paper fixa as constantes"],
        ["Tabela 5", "CRS, direção (−x, y, −b), só bancos com margem positiva", "decisões C1, P7 e P5"],
        ["Painel D da Tabela 3", "não implementado", "sem acesso a Li (1996), pendência P1"],
        ["Tabela 6", "só as covariáveis; GMM não estimado; PRIORITY fora", "pendências do segundo estágio"],
        ["Solver", "simplex em duas fases; o paper usa LINGO", "o paper não descreve o algoritmo"],
    ], [3.8 * cm, 7.2 * cm, 6.0 * cm]))


def main():
    doc = Documento(SAIDA)
    h = []
    capa(h)
    secao1(h)
    secao2(h)
    secao3(h, nomes_contas())
    secao4(h)
    secao5(h)
    secao6(h)
    secao7(h)
    secao8(h)
    secao9(h)
    secao10(h)
    secao11(h)
    secao12(h)
    secao13(h)
    doc.multiBuild(h)
    print(f"Gravado em {SAIDA}")


if __name__ == "__main__":
    main()
