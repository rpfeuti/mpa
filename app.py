# -*- coding: utf-8 -*-
"""IF.data local. A consulta lê o SQLite. IF.data, deflator e ESTBAN só baixam na aba Download."""
from pathlib import Path

import pandas as pd
import sqlite3
import streamlit as st

import baixar_base_bacen as bacen
import dsmlpi as dm
import painel_bansal as pb

DB = Path(__file__).resolve().parent / "base_dados" / "base_dados.db"

PERIMETROS = {
    1: "1 — Conglomerado prudencial",
    2: "2 — Conglomerado financeiro",
    3: "3 — Instituição individual",
}


@st.cache_resource
def conexao(caminho):
    con = sqlite3.connect(f"file:{caminho}?mode=ro", uri=True, check_same_thread=False)
    return con


def q(sql, params=()):
    return pd.read_sql_query(sql, conexao(str(DB)), params=params)


def ja_gravado():
    return {
        (int(t), str(a), str(r))
        for t, a, r in conexao(str(DB)).execute(
            "SELECT tipo_instituicao, ano_mes, num_relatorio FROM controle WHERE status IN ('ok','vazio')"
        )
    }


def tarefas_pendentes(tipos, trimestres, relatorios):
    feitos = ja_gravado()
    return [
        (int(t), am, str(r))
        for t in tipos
        for am in trimestres
        for r in relatorios
        if (int(t), str(am), str(r)) not in feitos
    ]


def executar_download(tarefas, manter=True):
    """Baixa a lista recebida. Com manter=True, o cadastro só completa o que falta."""
    con = bacen.abrir_db(str(DB))
    barra = st.progress(0)
    etapa = st.empty()
    tabela = st.empty()
    linhas_log = []
    passos = max(2 + len(tarefas), 1)
    feito = 0
    try:
        etapa.write("Etapa 1 — lista de relatórios")
        bacen.baixar_relatorios(con)
        feito += 1
        barra.progress(feito / passos)

        falta_cad = bacen.trimestres_sem_cadastro(con) if manter else list(bacen.TRIMESTRES)
        if not falta_cad:
            etapa.write("Etapa 2 — cadastro já estava completo")
        for i, anomes in enumerate(falta_cad, 1):
            etapa.write(f"Etapa 2 — cadastro {i}/{len(falta_cad)} — {anomes}")
            n_inst = bacen.baixar_cadastro_um(con, anomes)
            linhas_log.append({
                "etapa": "cadastro", "perimetro": "", "ano_mes": anomes,
                "relatorio": "", "status": "ok" if n_inst else "vazio", "linhas": n_inst,
            })
            tabela.dataframe(pd.DataFrame(linhas_log).tail(12), hide_index=True)
        feito += 1
        barra.progress(min(feito / passos, 1))

        for i, (ti, am, rel) in enumerate(tarefas, 1):
            etapa.write(
                f"Etapa 3 — valores {i}/{len(tarefas)} — "
                f"{PERIMETROS.get(ti, ti)} — {am} — relatório {rel}"
            )
            status, n = bacen.baixar_uma(con, ti, am, rel)
            linhas_log.append({
                "etapa": "valores", "perimetro": ti, "ano_mes": am,
                "relatorio": rel, "status": status, "linhas": n,
            })
            tabela.dataframe(pd.DataFrame(linhas_log).tail(12), hide_index=True)
            feito += 1
            barra.progress(feito / passos)
    finally:
        con.close()
    if linhas_log:
        st.dataframe(pd.DataFrame(linhas_log), hide_index=True)
    if manter:
        st.success("Download encerrado. O que já estava gravado foi mantido.")
    else:
        st.success("Download encerrado. As chamadas desta execução substituíram o que já existia.")


# ---------------------------------------------------------------- aba Bansal
SIGLAS = (
    "DMLPI: índice de produtividade Malmquist-Luenberger dinâmico em rede (M1, fronteira do ano). "
    "DSMLPI: o mesmo com fronteira sequencial (M2). MLPI e SMLPI: Malmquist-Luenberger sem rede, "
    "fronteira do ano e sequencial. EC: mudança de eficiência. TC: mudança técnica. "
    "NPL: crédito inadimplente (níveis E a H). LP: programa linear. VRS e CRS: retornos variáveis e "
    "constantes de escala. S1 a S3: segmentos prudenciais do Banco Central."
)

FIGURA2 = """
digraph G {
  rankdir=LR; node [shape=box, style=rounded, fontsize=11]; edge [fontsize=9];
  in1 [shape=plaintext, label="Trabalho\\nAtivo fixo\\nCapital próprio (quase-fixo)"];
  d1 [label="Divisão 1\\ncaptação", style="rounded,filled", fillcolor="#DDEBF7"];
  in2 [shape=plaintext, label="Empréstimos interbancários\\nNPL em t−1 (insumo indesejável)"];
  lag [shape=plaintext, label="Carryovers de t−1:\\nativos ociosos, lucro líquido"];
  d2 [label="Divisão 2\\naplicação", style="rounded,filled", fillcolor="#DDEBF7"];
  out2 [shape=plaintext, label="NPL em t (saída indesejável)"];
  car [shape=plaintext, label="Carryovers para t+1:\\nativos ociosos, lucro líquido"];
  in3 [shape=plaintext, label="Provisão para perdas"];
  d3 [label="Divisão 3\\nrentabilidade", style="rounded,filled", fillcolor="#DDEBF7"];
  out3 [shape=plaintext, label="Margem de juros\\nReceita não-juros"];
  in1 -> d1; d1 -> d2 [label="depósitos"]; in2 -> d2; lag -> d2;
  d2 -> out2; d2 -> car; d2 -> d3 [label="crédito adimplente\\ninvestimentos"];
  in3 -> d3; d3 -> out3;
}
"""


def versao_bansal():
    con_b = pb.abrir_bansal()
    try:
        base = con_b.execute(
            "SELECT (SELECT COUNT(*) || '|' || IFNULL(MAX(baixado_em), '') FROM deflator_pib), "
            "(SELECT COUNT(*) || '|' || IFNULL(MAX(baixado_em), '') FROM estban_controle)"
        ).fetchone()
        return (*base, pb.LIMITE_ATIVO)
    finally:
        con_b.close()


@st.cache_data(show_spinner="Montando o painel...")
def bansal_painel(versao):
    con_b = pb.abrir_bansal()
    try:
        mapa = pb.mapa_siglas(con_b)
        amo, anuais, nominal, norm, ag, defl, problemas, zeros = pb.montar_painel(conexao(str(DB)), con_b)
        est = pd.read_sql_query("SELECT ano, arquivo, linhas, baixado_em FROM estban_controle ORDER BY ano", con_b)
    finally:
        con_b.close()
    _, log8 = pb.extrair_contas(conexao(str(DB)), list(amo["cod_inst"]), com_log=True)
    log8 = pb.com_sigla(log8, mapa)
    contas = pb.extrair_contas(conexao(str(DB)), list(amo.loc[amo["status"] == "incluído", "cod_inst"]))
    contas = pb.com_sigla(contas, mapa, obrigatorio=norm is not None)
    return {"amo": amo, "anuais": anuais, "nominal": nominal, "norm": norm, "ag": ag, "defl": defl,
            "problemas": problemas, "zeros": zeros, "estban": est, "log8": log8, "contas": contas}


@st.cache_data(show_spinner="Resolvendo os LPs (programas lineares)...")
def bansal_calcular(norm):
    prep = dm.preparar(norm)
    dist, ind, avisos = [], [], []
    cond16 = pd.DataFrame()
    for mod in ("DMLPI", "DSMLPI"):
        d, i, a, c = dm.calcular_rede(prep, mod)
        dist.append(d); ind.append(i); avisos.append(a)
        if mod == "DSMLPI":
            cond16 = c
    for mod in ("MLPI", "SMLPI"):
        d, i = dm.calcular_ml(prep, mod)
        dist.append(d); ind.append(i)
    return {"prep": prep, "dist": pd.concat(dist, ignore_index=True), "ind": pd.concat(ind, ignore_index=True),
            "avisos": pd.concat(avisos, ignore_index=True), "cond16": cond16,
            "excl_t5": dm.amostra_tabela5(prep)[1]}


def gravar_csv_dsmlpi(norm, prep):
    """Uma linha por banco e ano do DSMLPI, só com as variáveis que entram no LP."""
    pasta = pb.PASTA / "output"
    pasta.mkdir(exist_ok=True)
    caminho = pasta / "dsmlpi.csv"
    nomes = dict(zip(norm["sigla"], norm["nome"]))
    grupos = dict(zip(norm["sigla"], norm["grupo"]))
    segmentos = dict(zip(norm["sigla"], norm["sr"]))
    linhas = []
    for i, ano in enumerate(prep["anos"]):
        for j, cod in enumerate(prep["bancos"]):
            linha = {
                "sigla": cod,
                "nome": nomes.get(cod, cod),
                "ano": int(ano),
                "sr": segmentos.get(cod, ""),
                "grupo": grupos.get(cod, ""),
            }
            for v in dm.CAMPOS:
                linha[v] = float(prep["dados"][v][i, j])
            linhas.append(linha)
    pd.DataFrame(linhas).to_csv(caminho, index=False, encoding="utf-8-sig")
    return caminho


def _nivel_acumulado(sub, anos):
    """Produto dos índices anuais. O ano anterior ao primeiro vale 1. Para no primeiro ano sem solução."""
    por_ano = {int(a): v for a, v in zip(sub["ano"], sub["IDX"])}
    acc = 1.0
    saida = {int(anos[0]) - 1: 1.0}
    for ano in anos:
        v = por_ano.get(int(ano))
        if acc is None or v is None or pd.isna(v) or float(v) <= 0:
            acc = None
            saida[int(ano)] = float("nan")
        else:
            acc *= float(v)
            saida[int(ano)] = acc
    return saida


def _series_acumuladas(ind, modelo, nomes):
    """Longa para o gráfico (ano, banco, nível) e larga para a tabela (banco × ano)."""
    sub = ind[ind["modelo"] == modelo]
    anos = sorted(int(a) for a in sub["ano"].unique())
    if not anos:
        return pd.DataFrame(columns=["ano", "banco", "nível"]), pd.DataFrame()
    longas, largas = [], []
    for cod in sorted(sub["sigla"].unique(), key=lambda c: nomes.get(c, c)):
        nome = nomes.get(cod, cod)
        niveis = _nivel_acumulado(sub[sub["sigla"] == cod], anos)
        linha = {"Banco": nome}
        for ano, nivel in niveis.items():
            longas.append({"ano": ano, "banco": nome, "nível": nivel})
            linha[str(ano)] = nivel
        largas.append(linha)
    return pd.DataFrame(longas), pd.DataFrame(largas)


def graficos_indices(ind, nomes, quatro, fora):
    """Trajetória acumulada dos quatro índices e, para um banco, a mudança de cada ano."""
    st.subheader("Trajetória acumulada")
    st.caption(
        "Começa em 1 em 2014 e multiplica o índice de cada ano. O valor de 2024 é o quanto a "
        "produtividade acumulou desde o início. Se um ano não tem solução, a linha daquele banco para ali. "
        "O índice de produtividade Malmquist-Luenberger (MLPI) e o sequencial sem rede (SMLPI) entram só com "
        f"margem de juros positiva em todos os anos. Fora desses dois: {fora}."
    )
    tabelas = {}
    for mo in quatro:
        st.write(f"**{mo}**")
        longa, larga = _series_acumuladas(ind, mo, nomes)
        tabelas[mo] = larga
        if longa.empty:
            st.write("Sem trajetória.")
            continue
        st.line_chart(longa, x="ano", y="nível", color="banco", height=420)

    bancos = sorted(ind["sigla"].unique(), key=lambda c: nomes.get(c, c))
    rotulos = [nomes.get(c, c) for c in bancos]
    padrao = rotulos[0]
    larga_ds = tabelas.get("DSMLPI")
    if larga_ds is not None and not larga_ds.empty:
        anos_cols = [c for c in larga_ds.columns if c != "Banco"]
        if anos_cols:
            ultimo = anos_cols[-1]
            ok = larga_ds.dropna(subset=[ultimo])
            if len(ok):
                padrao = ok.loc[ok[ultimo].idxmax(), "Banco"]
    escolha = st.selectbox("Banco", rotulos, index=rotulos.index(padrao) if padrao in rotulos else 0)
    cod = bancos[rotulos.index(escolha)]

    st.subheader(escolha)
    st.caption(
        "Mudança de cada ano. Acima de 1 avança naquele ano; abaixo de 1 recua. "
        "Esse fator é o que multiplica a trajetória acumulada dos gráficos acima."
    )
    serie = (ind[ind["sigla"] == cod]
             .pivot(index="ano", columns="modelo", values="IDX")
             .reindex(columns=quatro)
             .reset_index())
    st.line_chart(serie, x="ano", y=quatro)

    qual = st.selectbox("Índice para a decomposição", quatro, index=quatro.index("DSMLPI"))
    st.caption(
        "O índice do ano é o produto da mudança de eficiência (EC) pela mudança técnica (TC). "
        "A série 1 é a referência."
    )
    um = (ind[(ind["sigla"] == cod) & (ind["modelo"] == qual)][["ano", "EC", "TC", "IDX"]]
          .sort_values("ano")
          .rename(columns={"EC": "mudança de eficiência", "TC": "mudança técnica", "IDX": "índice"}))
    um["1"] = 1.0
    st.line_chart(um, x="ano", y=["mudança de eficiência", "mudança técnica", "índice", "1"])

    st.subheader(f"Índice acumulado · {qual}")
    st.caption("Os mesmos valores do gráfico desse índice: banco nas linhas, anos nas colunas. 2014 vale 1.")
    mostrar(tabelas[qual])


def mostrar(df, casas=4):
    fmt = {c: st.column_config.NumberColumn(format=f"%.{casas}f") for c in df.columns if df[c].dtype.kind == "f"}
    st.dataframe(df, hide_index=True, width="stretch", column_config=fmt)


def ler_downloads_externos():
    con_b = pb.abrir_bansal()
    try:
        defl = pb.deflator(con_b)
        est = pd.read_sql_query(
            "SELECT ano, arquivo, linhas, baixado_em FROM estban_controle ORDER BY ano", con_b
        )
    finally:
        con_b.close()
    return defl, est


def secao_ifdata():
    st.subheader("IF.data")
    st.write(
        "Base contábil do Banco Central. Baixa os três perímetros, de 201403 a 202412, "
        "em todos os relatórios que a API (interface de programação) listar."
    )
    manter = st.checkbox("Manter o que já está baixado", value=True)
    rels_db = q("SELECT numero FROM relatorios ORDER BY CAST(numero AS INTEGER)")
    rel_opts = list(rels_db["numero"]) if not rels_db.empty else [str(i) for i in range(1, 17)]
    if manter:
        tarefas = tarefas_pendentes(list(PERIMETROS), bacen.TRIMESTRES, rel_opts)
    else:
        tarefas = [
            (int(t), am, str(r))
            for t in PERIMETROS
            for am in bacen.TRIMESTRES
            for r in rel_opts
        ]
    if manter and not tarefas:
        st.write("Nada pendente. O que já está gravado cobre esse recorte.")
    else:
        st.write(f"Chamadas de valores nesta execução: **{len(tarefas)}**.")
    if st.button("Baixar IF.data", type="primary", disabled=manter and not tarefas):
        executar_download(tarefas, manter=manter)


def secao_deflator():
    st.subheader("Deflator implícito do PIB")
    st.write(
        "PIB: produto interno bruto. Série SGS 1211 (Sistema Gerenciador de Séries Temporais), "
        "índice com 2024 = 1. Grava em base_dados/base_dados.db."
    )
    if st.button("Baixar deflator"):
        con_b = pb.abrir_bansal()
        try:
            with st.spinner("Baixando SGS 1211..."):
                pb.baixar_deflator(con_b)
            st.success("Deflator gravado em base_dados/base_dados.db.")
        except Exception as e:
            st.error(f"Deflator não gravado: {e}")
        finally:
            con_b.close()
    defl, _ = ler_downloads_externos()
    if defl.empty:
        st.info("Deflator ainda não baixado.")
    else:
        st.caption(f"{len(defl)} anos gravados em base_dados/base_dados.db.")
        mostrar(defl, 6)


def secao_estban():
    st.subheader("ESTBAN — agências")
    st.write(
        "ESTBAN: Estatística Bancária Mensal por município. Dezembro de 2014 a 2024, "
        "somado por instituição. Grava em base_dados/base_dados.db."
    )
    if st.button("Baixar agências (ESTBAN)"):
        con_b = pb.abrir_bansal()
        barra = st.progress(0.0)
        try:
            pb.baixar_estban(con_b, progresso=lambda f, t: barra.progress(f, text=t))
            st.success("ESTBAN gravada em base_dados/base_dados.db.")
        except Exception as e:
            st.error(f"ESTBAN interrompida: {e}")
        finally:
            con_b.close()
    _, est = ler_downloads_externos()
    if est.empty:
        st.info("ESTBAN ainda não baixada.")
    else:
        st.caption(f"{len(est)} arquivos gravados em base_dados/base_dados.db.")
        st.dataframe(est, hide_index=True, width="stretch")


def aba_download():
    st.caption("Nada é baixado sozinho. Cada botão chama uma fonte do Banco Central uma vez.")
    secao_ifdata()
    st.divider()
    secao_deflator()
    st.divider()
    secao_estban()


def bansal_amostra(P):
    st.subheader("Amostra")
    amo = P["amo"]
    inc = amo[amo["status"] == "incluído"]
    c = st.columns(4)
    c[0].metric("Candidatos S1 a S3", len(amo))
    c[1].metric("Incluídos", len(inc))
    c[2].metric("Excluídos", len(amo) - len(inc))
    c[3].metric("Grupos (público / privado / estrangeiro)",
                " / ".join(str((inc["grupo"] == g).sum()) for g in pb.GRUPOS.values()))
    st.dataframe(amo[["nome", "sigla", "sr", "grupo", "tcb", "cnpj_anterior", "status", "motivo"]],
                 hide_index=True, width="stretch")
    st.caption("tcb: tipo de consolidado bancário (B1 = banco comercial). Perímetro: conglomerado financeiro, cadastro de 202412. "
               "cnpj_anterior: CNPJ do banco comercial que publicou o conglomerado financeiro até o código C existir, "
               f"quando o ativo total varia no máximo {pb.LIMITE_ATIVO:.0%} na troca de semestre.")
    with st.expander("Relatório 8 (carteira por nível de risco): nulos convertidos em zero"):
        st.write("Um nível de risco nulo vira zero só se AA a H mais o Total Exterior (23383) fecha o Total Geral (24454). "
                 "Sem essa identidade o nulo continua ausente e o banco sai por painel incompleto.")
        st.dataframe(P["log8"], hide_index=True, width="stretch")


def bansal_status(P):
    zeros = P["zeros"]
    if len(zeros):
        st.info("CNPJ com zero agência processada na ESTBAN entrou com 1 agência:")
        st.dataframe(zeros, hide_index=True, width="stretch")
    if P["problemas"]:
        st.warning("O cálculo não roda enquanto houver pendências:")
        for p in P["problemas"]:
            st.write(f"- {p}")


def bansal_tabela1():
    st.subheader("Tabela 1 · variáveis e adaptações")
    linhas = [{"Papel no modelo": papel, "Variável": pb.VARIAVEIS[v][0], "Fórmula (contas IF.data)": pb.VARIAVEIS[v][1],
               "Adaptação": pb.ADAPTACOES.get(v, "")} for papel, v in pb.TABELA1]
    st.dataframe(pd.DataFrame(linhas), hide_index=True, width="stretch")
    st.subheader("Figura 2 · estrutura em rede com três divisões")
    st.graphviz_chart(FIGURA2)


def bansal_resultados(P, R):
    norm, ind, dist = P["norm"], R["ind"], R["dist"]
    nomes = dict(zip(norm["sigla"], norm["nome"]))
    quatro = ["MLPI", "SMLPI", "DMLPI", "DSMLPI"]

    excl = R["excl_t5"]
    fora = ", ".join(nomes.get(c, c) for c in excl) or "nenhum"
    graficos_indices(ind, nomes, quatro, fora)

    st.subheader("Verificações")
    sem = dist.assign(sem=dist["status"] != 0).groupby("modelo")["sem"].sum().astype(int)
    c = st.columns(4)
    for k, mod in enumerate(("DMLPI", "DSMLPI", "MLPI", "SMLPI")):
        c[k].metric(f"LPs sem ótimo · {mod}", f"{sem.get(mod, 0)} de {(dist['modelo'] == mod).sum()}")
    beta_neg = dist[dist["beta"] <= -1]
    tc_ds = ind[(ind["modelo"] == "DSMLPI") & (ind["TC"] < 1)]
    st.write(f"- β ≤ −1 (1 + D ≤ 0, o índice do banco no ano fica indefinido e a trajetória para nesse ano): "
             f"**{len(beta_neg)}**.")
    if len(beta_neg):
        with st.expander("LPs com β ≤ −1"):
            mostrar(beta_neg.assign(banco=beta_neg["sigla"].map(nomes)), 6)
    st.write(f"- DSMLPI com TC < 1 (a fronteira sequencial não regride): **{len(tc_ds)}**.")
    c16 = R["cond16"]
    falhas = c16[~c16["atende"]] if not c16.empty else c16
    st.write(f"- Condição (16) do DSMLPI com δ = 1: **{len(falhas)}** falhas de {len(c16)}. "
             "O paper fixa δ = 1; a falha fica registrada, sem ajuste.")
    if len(falhas):
        with st.expander("Falhas da condição (16)"):
            mostrar(falhas, 6)
    av = R["avisos"]
    st.write(f"- Termos de direção ≤ 0 (y − ν, c − γ, w − ρ; tornam o LP inviável): **{len(av)}**.")
    if len(av):
        with st.expander("Termos de direção ≤ 0"):
            mostrar(av.assign(banco=av["sigla"].map(nomes)), 6)
    it = P["contas"]
    it = it[(it["sigla"] == "ITAU") & (it["ano"] == 2024) & (it["conta"] == "78187")]
    if len(it) == 2:
        jun, dez = (float(it.loc[it["mes"] == m, "saldo"].iloc[0]) / 1e9 for m in ("06", "12"))
        st.write(f"- Lucro líquido do Itaú em 2024 (conta 78187): junho {jun:,.2f} bi + dezembro {dez:,.2f} bi "
                 f"= **{jun + dez:,.2f} bi**. O plano esperava 19,21 + 19,42 bi.")


def aba_bansal_conteudo():
    st.write("Replicação de Bansal, Kumar, Mehra e Gulati (2022), Omega 107:102538, para conglomerados financeiros S1 a S3, 2014 a 2024.")
    st.caption(SIGLAS)
    P = bansal_painel(versao_bansal())
    bansal_status(P)
    bansal_amostra(P)
    bansal_tabela1()
    norm = P["norm"]
    if norm is None:
        st.info("A Tabela 2 e os quatro índices aparecem depois que as pendências acima forem resolvidas.")
        return
    st.subheader("Tabela 2 · estatísticas descritivas")
    st.caption(f"Unidade: {pb.UNIDADE_NOME}. Curtose em excesso e assimetria amostrais.")
    mostrar(pb.tabela2(norm))
    if st.button("Calcular", type="primary"):
        st.session_state["bansal_calcular"] = True
    if not st.session_state.get("bansal_calcular"):
        return
    R = bansal_calcular(norm)
    try:
        gravar_csv_dsmlpi(norm, R["prep"])
        st.caption("Valores usados no DSMLPI gravados em output/dsmlpi.csv.")
    except PermissionError:
        st.error("output/dsmlpi.csv está aberto em outro programa. Feche o arquivo e calcule de novo.")
    bansal_resultados(P, R)


st.set_page_config(page_title="IF.data local", layout="wide")
st.title("IF.data local")
st.caption(
    "Nada é baixado ao abrir esta página. IF.data, o deflator do PIB (produto interno bruto) "
    "e a ESTBAN (Estatística Bancária Mensal por município) só baixam pelos botões da aba Download."
)

if not DB.exists():
    st.error(f"Banco não encontrado: {DB}")
    st.stop()

aba_down, aba_bansal = st.tabs(["Download", "Bansal"])

with aba_down:
    aba_download()

with aba_bansal:
    aba_bansal_conteudo()
