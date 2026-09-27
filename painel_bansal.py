# -*- coding: utf-8 -*-
"""Painel da replicação de Bansal et al. (2022) para conglomerados financeiros S1 a S3.

Lê e grava em `base_dados/base_dados.db`. `abrir_fonte` abre esse arquivo só em modo leitura.
Os downloads (deflator e ESTBAN) só rodam quando as funções `baixar_*` são chamadas
pelos botões da aba Download.
"""
import io
import sqlite3
import zipfile
from pathlib import Path

import pandas as pd

PASTA = Path(__file__).resolve().parent
PASTA_DB = PASTA / "base_dados"
DB_FONTE = PASTA_DB / "base_dados.db"
DB_BANSAL = PASTA_DB / "base_dados.db"

TIPO = 2
ANO_REF = "202412"
ANOS = list(range(2014, 2025))
ANO_BASE_PRECOS = 2024
UNIDADE = 1e6
UNIDADE_NOME = "R$ milhões de 2024 por agência (trabalho: R$ milhões de 2024, sem normalizar)"

GRUPOS = {"1": "Público", "2": "Privado nacional", "3": "Estrangeiro"}

# Cadastro sigla_banco: o IF.data continua na chave cod_inst; o cálculo usa a sigla.
PARES_SIGLA = (
    ("C0010045", "BRAD"),
    ("C0010069", "ITAU"),
    ("C0010083", "SAFR"),
    ("C0020152", "MERC"),
    ("C0030159", "BNES"),
    ("C0030173", "BSUL"),
    ("C0030290", "BMG"),
    ("C0030379", "SANT"),
    ("C0030403", "CITI"),
    ("C0031873", "SOFI"),
    ("C0031976", "BRB"),
    ("C0041856", "ABC"),
    ("C0049906", "BB"),
    ("C0050201", "MAST"),
    ("C0051011", "VOTO"),
    ("C0051255", "BOFA"),
    ("C0051750", "SICO"),
    ("C0051884", "INTE"),
    ("C0020107", "JPM"),
    ("C0030771", "UBS"),
    ("C0032119", "CCB"),
    ("C0049944", "BTG"),
    ("C0050304", "PINE"),
)

# conta: (relatório, tipo). "saldo" usa dezembro; "fluxo" soma junho e dezembro,
# porque a DRE do IF.data é acumulada no semestre.
CONTAS = {
    "78182": ("1", "saldo"),
    "78186": ("1", "saldo"),
    "78187": ("4", "fluxo"),
    "78190": ("2", "saldo"),
    "78193": ("2", "saldo"),
    "78198": ("2", "saldo"),
    "78201": ("2", "saldo"),
    "78284": ("3", "saldo"),
    "78287": ("3", "saldo"),
    "78295": ("3", "saldo"),
    "78213": ("4", "fluxo"),
    "78215": ("4", "fluxo"),
    "78216": ("4", "fluxo"),
    "78217": ("4", "fluxo"),
    "78218": ("4", "fluxo"),
    "78219": ("4", "fluxo"),
    "78220": ("4", "fluxo"),
    "78223": ("4", "fluxo"),
    "23349": ("8", "saldo"),
    "23350": ("8", "saldo"),
    "23351": ("8", "saldo"),
    "23352": ("8", "saldo"),
    "23353": ("8", "saldo"),
    "23354": ("8", "saldo"),
    "23355": ("8", "saldo"),
    "23356": ("8", "saldo"),
    "23357": ("8", "saldo"),
}

# variável: (nome na tela, fórmula legível, termos (sinal, conta), abs no total)
VARIAVEIS = {
    "labor": ("Trabalho (despesa de pessoal)", "abs(78218)", [(1, "78218")], True),
    "fixed": ("Ativo fixo", "78201", [(1, "78201")], False),
    "equity": ("Capital próprio", "78186", [(1, "78186")], False),
    "deposits": ("Depósitos", "78287 − 78284", [(1, "78287"), (-1, "78284")], False),
    "interbank": ("Empréstimos interbancários", "78284 + 78295", [(1, "78284"), (1, "78295")], False),
    "npl": ("NPL (níveis E a H)", "23354 + 23355 + 23356 + 23357",
            [(1, "23354"), (1, "23355"), (1, "23356"), (1, "23357")], False),
    "unused": ("Ativos ociosos", "78182 − 78201 − 78193 − 78198 − 78190",
               [(1, "78182"), (-1, "78201"), (-1, "78193"), (-1, "78198"), (-1, "78190")], False),
    "profit": ("Lucro líquido", "78187", [(1, "78187")], False),
    "performing": ("Crédito adimplente (AA a D)", "23350 + 23349 + 23351 + 23352 + 23353",
                   [(1, "23350"), (1, "23349"), (1, "23351"), (1, "23352"), (1, "23353")], False),
    "invest": ("Investimentos", "78190", [(1, "78190")], False),
    "llp": ("Provisão para perdas", "−78213", [(-1, "78213")], False),
    "nii": ("Margem de juros", "78215 − 78213", [(1, "78215"), (-1, "78213")], False),
    "nonii": ("Receita não-juros", "78216 + 78217", [(1, "78216"), (1, "78217")], False),
}
VARS_MODELO = list(VARIAVEIS)
VARS_SEM_NORMALIZAR = {"labor"}

TABELA1 = [
    ("Insumos desejáveis da divisão 1", "labor"),
    ("Insumos desejáveis da divisão 1", "fixed"),
    ("Insumo quase-fixo da divisão 1", "equity"),
    ("Ligação entre as divisões 1 e 2", "deposits"),
    ("Insumo desejável da divisão 2", "interbank"),
    ("Insumo indesejável da divisão 2 (em t−1)", "npl"),
    ("Carryovers desejáveis da divisão 2 (em t−1)", "unused"),
    ("Carryovers desejáveis da divisão 2 (em t−1)", "profit"),
    ("Ligações entre as divisões 2 e 3", "performing"),
    ("Ligações entre as divisões 2 e 3", "invest"),
    ("Saída indesejável da divisão 2 (em t)", "npl"),
    ("Insumo desejável da divisão 3", "llp"),
    ("Saídas da divisão 3", "nii"),
    ("Saídas da divisão 3", "nonii"),
]

ADAPTACOES = {
    "labor": "O paper usa número de empregados. Aqui é a despesa de pessoal (L1), deflacionada e não normalizada.",
    "interbank": "Interfinanceiros mais empréstimos e repasses (L3).",
    "npl": "Carteira SCR (Sistema de Informações de Crédito) nos níveis E a H (L4). Só o livro doméstico.",
    "unused": "O compulsório fica dentro, porque o IF.data não o separa (L5).",
    "nii": "Resultado de intermediação antes da PCLD (provisão para créditos de liquidação duvidosa), "
           "com derivativos e câmbio (L6).",
}


def abrir_fonte():
    return sqlite3.connect(f"file:{DB_FONTE}?mode=ro", uri=True, check_same_thread=False)


def abrir_bansal():
    PASTA_DB.mkdir(exist_ok=True)
    con = sqlite3.connect(DB_BANSAL, check_same_thread=False)
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS deflator_pib (
            ano INTEGER PRIMARY KEY, variacao_pct REAL, indice REAL, baixado_em TEXT);
        CREATE TABLE IF NOT EXISTS estban_cnpj (
            ano INTEGER, cnpj TEXT, nome TEXT, agen_esperadas INTEGER, agen_processadas INTEGER,
            PRIMARY KEY (ano, cnpj));
        CREATE TABLE IF NOT EXISTS estban_controle (
            ano INTEGER PRIMARY KEY, arquivo TEXT, colunas TEXT, linhas INTEGER, baixado_em TEXT);
        CREATE TABLE IF NOT EXISTS sigla_banco (
            cod_inst TEXT PRIMARY KEY, sigla TEXT NOT NULL UNIQUE);
        """
    )
    con.executemany(
        "INSERT OR IGNORE INTO sigla_banco (cod_inst, sigla) VALUES (?, ?)",
        PARES_SIGLA,
    )
    con.commit()
    return con


def mapa_siglas(con):
    """cod_inst do IF.data para a sigla usada no cálculo. Lê sigla_banco."""
    return dict(con.execute("SELECT cod_inst, sigla FROM sigla_banco"))


def com_sigla(df, mapa, obrigatorio=False):
    """Troca cod_inst pela sigla. Sem linha no cadastro, o código permanece, salvo se obrigatorio."""
    if df is None or df.empty or "cod_inst" not in df.columns:
        return df
    falta = sorted({c for c in df["cod_inst"].unique() if c not in mapa})
    if obrigatorio and falta:
        raise ValueError("Sem sigla em sigla_banco: " + ", ".join(falta))
    out = df.copy()
    valores = out["cod_inst"].map(lambda c: mapa.get(c, c))
    pos = out.columns.get_loc("cod_inst")
    out = out.drop(columns=["cod_inst"])
    if "sigla" in out.columns:
        out["sigla"] = valores
    else:
        out.insert(pos, "sigla", valores)
    return out


def extrair_contas(con, cods, com_log=False):
    """Saldos de junho e dezembro das contas do de-para, sem duplicatas."""
    meses = [f"{a}{m}" for a in ANOS for m in ("06", "12")]
    ph_c = ",".join("?" * len(cods))
    ph_m = ",".join("?" * len(meses))
    ph_k = ",".join("?" * len(CONTAS))
    df = pd.read_sql_query(
        f"""
        SELECT DISTINCT cod_inst, ano_mes, num_relatorio, conta, saldo
          FROM valores
         WHERE tipo_instituicao = ? AND cod_inst IN ({ph_c})
           AND ano_mes IN ({ph_m}) AND conta IN ({ph_k})
        """,
        con,
        params=[TIPO, *cods, *meses, *CONTAS],
    )
    df["ano_mes"] = df["ano_mes"].astype(str)
    df["num_relatorio"] = df["num_relatorio"].astype(str)
    df = df[df["num_relatorio"] == df["conta"].map(lambda c: CONTAS[c][0])].copy()
    chave = ["cod_inst", "ano_mes", "conta"]
    conflito = df.groupby(chave)["saldo"].nunique()
    conflito = conflito[conflito > 1]
    if not conflito.empty:
        raise ValueError(f"Saldos conflitantes para a mesma chave: {conflito.index.tolist()[:10]}")
    df = df.drop_duplicates(chave)
    df["ano"] = df["ano_mes"].str[:4].astype(int)
    df["mes"] = df["ano_mes"].str[4:]
    df, log = zeros_verificados_rel8(con, df, cods)
    return (df, log) if com_log else df


NIVEIS_SCR = ["23349", "23350", "23351", "23352", "23353", "23354", "23355", "23356", "23357"]


def zeros_verificados_rel8(con, df, cods):
    """Nível de risco nulo no relatório 8 vira zero só se AA..H + Total Exterior (23383) fecha o Total Geral (24454).

    Sem essa identidade o nulo continua ausente e o banco sai por painel incompleto.
    """
    ph = ",".join("?" * len(cods))
    meses = [f"{a}12" for a in ANOS]
    tot = pd.read_sql_query(
        f"""
        SELECT DISTINCT cod_inst, ano_mes, conta, saldo FROM valores
         WHERE tipo_instituicao = ? AND num_relatorio = '8' AND cod_inst IN ({ph})
           AND ano_mes IN ({",".join("?" * len(meses))}) AND conta IN ('23383', '24454')
        """,
        con,
        params=[TIPO, *cods, *meses],
    )
    tot["ano_mes"] = tot["ano_mes"].astype(str)
    tot = tot.pivot_table(index=["cod_inst", "ano_mes"], columns="conta", values="saldo", aggfunc="first", dropna=False)
    niv = df[df["conta"].isin(NIVEIS_SCR) & (df["mes"] == "12")]
    soma = niv.groupby(["cod_inst", "ano_mes"])["saldo"].sum(min_count=0)
    nulos = niv[niv["saldo"].isna()]
    log = []
    for (cod, am), g in nulos.groupby(["cod_inst", "ano_mes"]):
        total = tot["24454"].get((cod, am), float("nan")) if "24454" in tot else float("nan")
        ext = tot["23383"].get((cod, am), float("nan")) if "23383" in tot else float("nan")
        ext = 0.0 if pd.isna(ext) else ext
        fecha = pd.notna(total) and abs(soma.get((cod, am), 0.0) + ext - total) < 1.0
        if fecha:
            df.loc[g.index, "saldo"] = 0.0
        log.append({"cod_inst": cod, "ano_mes": am, "niveis_nulos": ",".join(sorted(g["conta"])),
                    "total_geral": total, "soma_niveis_mais_exterior": soma.get((cod, am), 0.0) + ext,
                    "zero_verificado": bool(fecha)})
    return df, pd.DataFrame(log)


def faltas_por_banco(contas, cods):
    """O que falta para cada banco (linha ausente ou saldo nulo). Nada é preenchido."""
    contas = contas[contas["saldo"].notna()]
    tem = set(zip(contas["cod_inst"], contas["ano"], contas["mes"], contas["conta"]))
    faltas = {}
    for cod in cods:
        miss = []
        for ano in ANOS:
            for conta, (_, tipo) in CONTAS.items():
                for m in (("06", "12") if tipo == "fluxo" else ("12",)):
                    if (cod, ano, m, conta) not in tem:
                        miss.append(f"{ano}{m}:{conta}")
        if miss:
            faltas[cod] = miss
    return faltas


def amostra(con):
    """Candidatos S1 a S3 de 202412 e o motivo de cada exclusão (seção 4.2 e L7)."""
    cand = pd.read_sql_query(
        """
        SELECT DISTINCT cod_inst, nome_instituicao AS nome, sr, tc, tcb
          FROM cadastro
         WHERE ano_mes = ? AND sr IN ('S1','S2','S3') AND td = 'C'
           AND cod_inst = cod_cong_financeiro
         ORDER BY sr, nome_instituicao
        """,
        con,
        params=(ANO_REF,),
    )
    cand["tc"] = cand["tc"].astype(str)
    cand["grupo"] = cand["tc"].map(GRUPOS)
    faltas = faltas_por_banco(extrair_contas(con, list(cand["cod_inst"])), list(cand["cod_inst"]))
    status, motivo = [], []
    for r in cand.itertuples():
        if r.tcb != "B1":
            status.append("excluído")
            motivo.append(f"tcb={r.tcb}: não é banco comercial (seção 4.2)")
        elif r.cod_inst in faltas:
            miss = faltas[r.cod_inst]
            anos = sorted({x[:4] for x in miss})
            status.append("excluído")
            motivo.append(f"painel incompleto: {len(miss)} saldos ausentes nos anos {', '.join(anos)}")
        else:
            status.append("incluído")
            motivo.append("")
    cand["status"] = status
    cand["motivo"] = motivo
    return cand


def contas_anuais(contas):
    """Uma linha por banco e ano com o valor anual de cada conta (saldo de dezembro ou junho + dezembro)."""
    linhas = []
    for (cod, ano), g in contas.groupby(["cod_inst", "ano"]):
        por = {(r.conta, r.mes): r.saldo for r in g.itertuples()}
        d = {"cod_inst": cod, "ano": ano}
        for conta, (_, tipo) in CONTAS.items():
            d[conta] = por[(conta, "06")] + por[(conta, "12")] if tipo == "fluxo" else por[(conta, "12")]
        linhas.append(d)
    return pd.DataFrame(linhas)


def variaveis_nominais(anuais):
    out = anuais[["cod_inst", "ano"]].copy()
    for v, (_, _, termos, usa_abs) in VARIAVEIS.items():
        s = sum(sinal * anuais[conta] for sinal, conta in termos)
        out[v] = s.abs() if usa_abs else s
    return out


# ---------------------------------------------------------------- deflator (SGS 1211)
URL_SGS_1211 = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.1211/dados?formato=json"


def baixar_deflator(con_b):
    """Só pelo botão. Deflator implícito do PIB, variação % anual (seção 4.2)."""
    import datetime as dt

    import requests

    r = requests.get(URL_SGS_1211, timeout=60)
    r.raise_for_status()
    dados = pd.DataFrame(r.json())
    dados["ano"] = dados["data"].str[-4:].astype(int)
    var = dict(zip(dados["ano"], dados["valor"].astype(float)))
    falta = [a for a in ANOS[1:] if a not in var]
    if falta:
        raise ValueError(f"SGS 1211 sem variação para {falta}. Nada foi gravado.")
    indice = {ANO_BASE_PRECOS: 1.0}
    for a in range(ANO_BASE_PRECOS, ANOS[0], -1):
        indice[a - 1] = indice[a] / (1 + var[a] / 100)
    agora = dt.datetime.now().isoformat(timespec="seconds")
    con_b.execute("DELETE FROM deflator_pib")
    con_b.executemany(
        "INSERT INTO deflator_pib VALUES (?,?,?,?)",
        [(a, var.get(a), indice[a], agora) for a in ANOS],
    )
    con_b.commit()
    return deflator(con_b)


def deflator(con_b):
    return pd.read_sql_query("SELECT ano, variacao_pct, indice FROM deflator_pib ORDER BY ano", con_b)


# ---------------------------------------------------------------- ESTBAN (agências)
SITE_BCB = "https://www.bcb.gov.br"
URL_LISTA_ESTBAN = (SITE_BCB + "/api/servico/sitebcb/Documentos/byListGuid?tronco=estatisticas"
                    "&guidLista=f6391806-fd85-43af-acf1-c86d5b8dd6df&ordem=DataDocumento%20desc&pasta=municipio")
COLS_ESTBAN = ["CNPJ", "NOME_INSTITUICAO", "AGEN_ESPERADAS", "AGEN_PROCESSADAS"]


def ler_estban(conteudo):
    """Lê o CSV do ZIP. Procura a linha de cabeçalho em vez de supor quantas linhas pular."""
    with zipfile.ZipFile(io.BytesIO(conteudo)) as z:
        nome = [n for n in z.namelist() if n.lower().endswith((".csv", ".txt"))][0]
        texto = z.read(nome).decode("latin-1")
    linhas = texto.splitlines()
    idx = next(i for i, l in enumerate(linhas) if "AGEN_PROCESSADAS" in l.upper())
    df = pd.read_csv(io.StringIO("\n".join(linhas[idx:])), sep=";", dtype=str)
    df.columns = [c.strip().lstrip("#").upper() for c in df.columns]
    falta = [c for c in COLS_ESTBAN if c not in df.columns]
    if falta:
        raise ValueError(f"ESTBAN sem as colunas {falta}. Colunas encontradas: {list(df.columns)}")
    return nome, df


def baixar_estban(con_b, anos=None, progresso=None):
    """Só pelo botão. Um ZIP por dezembro, com o endereço tirado da lista oficial da página da ESTBAN
    (o nome do arquivo mudou de AAAA12_ESTBAN.ZIP para AAAA12_ESTBAN.csv.zip a partir de 2023)."""
    import datetime as dt

    import requests

    anos = anos or ANOS
    lista = requests.get(URL_LISTA_ESTBAN, timeout=60)
    lista.raise_for_status()
    itens = lista.json()
    itens = itens["conteudo"] if isinstance(itens, dict) else itens
    url_de = {it["Titulo"]: SITE_BCB + it["Url"] for it in itens}
    for i, ano in enumerate(anos, 1):
        am = f"{ano}12"
        url = url_de.get(f"12/{ano}")
        if url is None:
            raise RuntimeError(f"ESTBAN {am} não está na lista do Banco Central. Os anos anteriores ficaram gravados.")
        r = requests.get(url, timeout=180)
        if r.status_code != 200 or r.content[:2] != b"PK":
            raise RuntimeError(f"ESTBAN {am} não baixou (HTTP {r.status_code}, {url}). Os anos anteriores ficaram gravados.")
        conteudo = r.content
        nome, df = ler_estban(conteudo)
        df["CNPJ"] = df["CNPJ"].str.strip().str.zfill(8)
        for c in ("AGEN_ESPERADAS", "AGEN_PROCESSADAS"):
            df[c] = pd.to_numeric(df[c].str.strip(), errors="raise").astype(int)
        agg = df.groupby("CNPJ").agg(
            nome=("NOME_INSTITUICAO", "first"),
            esp=("AGEN_ESPERADAS", "sum"),
            proc=("AGEN_PROCESSADAS", "sum"),
        ).reset_index()
        con_b.execute("DELETE FROM estban_cnpj WHERE ano = ?", (ano,))
        con_b.executemany(
            "INSERT INTO estban_cnpj VALUES (?,?,?,?,?)",
            [(ano, row.CNPJ, row.nome, int(row.esp), int(row.proc)) for row in agg.itertuples()],
        )
        con_b.execute(
            "INSERT OR REPLACE INTO estban_controle VALUES (?,?,?,?,?)",
            (ano, nome, ";".join(df.columns), len(df), dt.datetime.now().isoformat(timespec="seconds")),
        )
        con_b.commit()
        if progresso:
            progresso(i / len(anos), f"ESTBAN {am}: {len(df)} linhas, {len(agg)} CNPJs")


def agencias(con, con_b, cods):
    """Agências por conglomerado e ano: soma dos CNPJs ligados pelo cod_cong_financeiro de dezembro.

    CNPJ com zero agência processada entra com 1. Um banco não opera com zero agência, e o zero
    da ESTBAN é defeito do arquivo (decisão do usuário).
    """
    est = pd.read_sql_query("SELECT * FROM estban_cnpj", con_b)
    if est.empty:
        return pd.DataFrame(columns=["cod_inst", "ano", "agencias", "agen_esperadas", "cnpjs"])
    meses = [f"{a}12" for a in ANOS]
    cad = pd.read_sql_query(
        f"""
        SELECT DISTINCT ano_mes, cod_inst AS cnpj, cod_cong_financeiro AS cod_inst
          FROM cadastro
         WHERE td = 'I' AND cod_cong_financeiro IN ({",".join("?" * len(cods))})
           AND ano_mes IN ({",".join("?" * len(meses))})
        """,
        con,
        params=[*cods, *meses],
    )
    cad["ano"] = cad["ano_mes"].astype(str).str[:4].astype(int)
    m = cad.merge(est, on=["ano", "cnpj"], how="inner")
    m["agencias_usadas"] = m["agen_processadas"].where(m["agen_processadas"] > 0, 1)
    agg = m.groupby(["cod_inst", "ano"]).agg(
        agencias=("agencias_usadas", "sum"),
        agen_esperadas=("agen_esperadas", "sum"),
        cnpjs=("cnpj", lambda s: ", ".join(sorted(s))),
    ).reset_index()
    base = pd.MultiIndex.from_product([cods, ANOS], names=["cod_inst", "ano"]).to_frame(index=False)
    out = base.merge(agg, on=["cod_inst", "ano"], how="left")
    out["agencias"] = out["agencias"].fillna(0).astype(int)
    out["agen_esperadas"] = out["agen_esperadas"].fillna(0).astype(int)
    out["cnpjs"] = out["cnpjs"].fillna("")
    zeros = m[m["agen_processadas"] <= 0][["cod_inst", "ano", "cnpj", "nome", "agen_esperadas"]]
    return out, zeros.reset_index(drop=True)


# ---------------------------------------------------------------- painel final
def montar_painel(con, con_b):
    """Devolve (amostra, anuais, nominal, painel_normalizado, agencias, deflator, problemas, zeros_estban).

    Seção 4.2: deflator implícito do PIB e divisão pelo número de agências.
    `problemas` lista tudo que impede o cálculo. Nada é preenchido.
    """
    mapa = mapa_siglas(con_b)
    amo = amostra(con)
    amo["sigla"] = amo["cod_inst"].map(lambda c: mapa.get(c, c))
    inc = amo[amo["status"] == "incluído"]
    cods = list(inc["cod_inst"])
    anuais = contas_anuais(extrair_contas(con, cods))
    nominal = variaveis_nominais(anuais)
    problemas = []
    sem = [c for c in cods if c not in mapa]
    if sem:
        problemas.append("Cadastro sigla_banco sem sigla para " + ", ".join(sem) + ".")
    for r in nominal[nominal["equity"] <= 0].itertuples():
        problemas.append(f"{mapa.get(r.cod_inst, r.cod_inst)} {r.ano}: patrimônio líquido não positivo (seção 3.1)")

    defl = deflator(con_b)
    falta_d = [a for a in ANOS if a not in set(defl["ano"])]
    if falta_d:
        problemas.append(f"Deflator ausente para {falta_d}. Baixe na aba Download.")
    ag, zeros = agencias(con, con_b, cods)
    if ag.empty:
        problemas.append("Agências ausentes. Baixe a ESTBAN na aba Download.")
    else:
        nomes = dict(zip(inc["cod_inst"], inc["nome"]))
        for r in ag[ag["agencias"] <= 0].itertuples():
            problemas.append(f"{nomes.get(r.cod_inst, r.cod_inst)} {r.ano}: zero agência na ESTBAN")

    zeros = com_sigla(zeros, mapa)
    if problemas:
        return amo, anuais, nominal, None, ag, defl, problemas, zeros

    p = nominal.merge(defl[["ano", "indice"]], on="ano").merge(
        ag[["cod_inst", "ano", "agencias"]], on=["cod_inst", "ano"])
    norm = p[["cod_inst", "ano"]].copy()
    for v in VARS_MODELO:
        real = p[v] / p["indice"] / UNIDADE
        norm[v] = real if v in VARS_SEM_NORMALIZAR else real / p["agencias"]
    norm = norm.merge(inc[["cod_inst", "sigla", "nome", "sr", "tc", "grupo"]], on="cod_inst")
    norm = com_sigla(norm, mapa, obrigatorio=True)
    anuais = com_sigla(anuais, mapa, obrigatorio=True)
    nominal = com_sigla(nominal, mapa, obrigatorio=True)
    ag = com_sigla(ag, mapa, obrigatorio=True)
    norm = norm.sort_values(["ano", "sigla"]).reset_index(drop=True)
    return amo, anuais, nominal, norm, ag, defl, problemas, zeros


def tabela2(norm):
    """Tabela 2: estatísticas descritivas. Curtose em excesso e assimetria amostrais (as mesmas do Excel)."""
    linhas = []
    for v in VARS_MODELO:
        s = norm[v]
        linhas.append({
            "Variável": VARIAVEIS[v][0],
            "Média": s.mean(), "σ": s.std(ddof=1), "Curtose": s.kurt(), "Assimetria": s.skew(),
            "Mediana": s.median(), "Máximo": s.max(), "Mínimo": s.min(),
        })
    return pd.DataFrame(linhas)
