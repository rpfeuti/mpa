# -*- coding: utf-8 -*-
"""
BASE OFFLINE COMPLETA — IF.data / Banco Central do Brasil
=========================================================

Baixa TUDO que existe no IF.data até 2024T4 e guarda em SQLite local,
para nunca mais depender da API durante a análise.

Escopo:
  - Todos os relatórios disponíveis (descobertos via ListaDeRelatorio)
  - Todas as contas de cada relatório (sem filtro)
  - Todas as instituições (sem filtro de segmento ou tipo)
  - Os 3 perímetros: individual, prudencial e financeiro
  - Período: 200003 a 202412 (ou o recorte definido em ANO_INICIO)

Características:
  - Somente biblioteca padrão (urllib, json, sqlite3, csv) — não precisa de pip
  - INCREMENTAL e RETOMÁVEL: pode interromper com Ctrl+C e rodar de novo;
    ele pula o que já baixou
  - Registra o que foi baixado numa tabela de controle
  - Exporta CSVs ao final (opcional, veja EXPORTAR_CSV)

Uso:
    python baixar_base_bacen.py              # baixa tudo
    python baixar_base_bacen.py --status     # mostra progresso sem baixar
    python baixar_base_bacen.py --exportar   # só exporta CSVs do que já existe
    python baixar_base_bacen.py --indices    # (re)cria índices e a view v_dados

Se a rede exigir proxy:
    PowerShell: $env:HTTPS_PROXY="http://usuario:senha@proxy:porta"
"""

import urllib.request
import urllib.error
import json
import sqlite3
import ssl
import time
import sys
import os
import csv
from datetime import datetime

# ---------------------------------------------------------------------------
# CONFIGURAÇÃO
# ---------------------------------------------------------------------------
BASE = "https://olinda.bcb.gov.br/olinda/servico/IFDATA/versao/v1/odata"
_RAIZ = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(_RAIZ, "base_dados", "base_dados.db")
PASTA_CSV = "csv_export"

ANO_INICIO = 2014      # use 2000 para a série histórica completa (bem maior)
ANO_FIM = 2024
MESES = ["03", "06", "09", "12"]

# Validado no Itaú, 202406, Ativo Total:
# 1 = Conglomerado Prudencial | 2 = Conglomerado Financeiro | 3 = Instituição individual
TIPOS_INSTITUICAO = [1, 2, 3]
NOME_TIPO = {
    1: "Conglomerado Prudencial",
    2: "Conglomerado Financeiro",
    3: "Instituição individual",
}

PAUSA = 0.25
TIMEOUT = 180
TENTATIVAS = 3
PAGE_SIZE = 100000
# O .db é o entregável. CSV do universo inteiro só com --exportar.
EXPORTAR_CSV = False

TRIMESTRES = [f"{a}{m}" for a in range(ANO_INICIO, ANO_FIM + 1) for m in MESES]

_ctx = ssl.create_default_context()
_ctx.check_hostname = False
_ctx.verify_mode = ssl.CERT_NONE


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
def _variantes(url):
    variantes = [url]
    if "$" in url:
        alt = (url.replace("$format", "%24format")
                  .replace("$top", "%24top")
                  .replace("$skip", "%24skip"))
        if alt != url:
            variantes.append(alt)
    return variantes


def get_json(url):
    """GET com retry e fallback de encoding do '$'. Retorna lista ou None."""
    for u in _variantes(url):
        for i in range(TENTATIVAS):
            try:
                req = urllib.request.Request(
                    u, headers={"User-Agent": "Mozilla/5.0",
                                "Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=TIMEOUT, context=_ctx) as r:
                    return json.loads(r.read().decode("utf-8")).get("value", [])
            except urllib.error.HTTPError as e:
                if e.code in (400, 404):
                    break            # tenta a próxima variante da URL
                if i == TENTATIVAS - 1:
                    return None
                time.sleep(2 * (i + 1))
            except Exception:
                if i == TENTATIVAS - 1:
                    return None
                time.sleep(2 * (i + 1))
    return None


def get_json_paginado(url):
    """Lê todas as páginas ($top/$skip). None se alguma página falhar."""
    tudo = []
    skip = 0
    while True:
        sep = "&" if "?" in url else "?"
        pagina = get_json(f"{url}{sep}$top={PAGE_SIZE}&$skip={skip}")
        if pagina is None:
            return None
        tudo.extend(pagina)
        if len(pagina) < PAGE_SIZE:
            return tudo
        skip += PAGE_SIZE
        time.sleep(PAUSA)


# ---------------------------------------------------------------------------
# BANCO DE DADOS
# ---------------------------------------------------------------------------
def abrir_db(caminho=None):
    destino = caminho or DB
    os.makedirs(os.path.dirname(os.path.abspath(destino)), exist_ok=True)
    con = sqlite3.connect(destino)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    con.executescript("""
    CREATE TABLE IF NOT EXISTS relatorios (
        numero TEXT PRIMARY KEY,
        nome   TEXT
    );
    CREATE TABLE IF NOT EXISTS cadastro (
        ano_mes TEXT, cod_inst TEXT, nome_instituicao TEXT,
        td TEXT, tc TEXT, sr TEXT, tcb TEXT,
        segmento_tb TEXT, atividade TEXT, uf TEXT, municipio TEXT,
        cod_cong_financeiro TEXT, cod_cong_prudencial TEXT,
        data_inicio_atividade TEXT,
        PRIMARY KEY (ano_mes, cod_inst)
    );
    -- dicionário de contas: evita repetir texto longo em milhões de linhas
    CREATE TABLE IF NOT EXISTS contas (
        num_relatorio TEXT, conta TEXT, grupo TEXT,
        nome_coluna TEXT, descricao_coluna TEXT,
        PRIMARY KEY (num_relatorio, conta)
    );
    -- tabela de fatos: só chaves curtas + valor numérico
    CREATE TABLE IF NOT EXISTS valores (
        tipo_instituicao INTEGER, ano_mes TEXT, num_relatorio TEXT,
        cod_inst TEXT, conta TEXT, saldo REAL
    );
    CREATE TABLE IF NOT EXISTS controle (
        tipo_instituicao INTEGER, ano_mes TEXT, num_relatorio TEXT,
        linhas INTEGER, status TEXT, baixado_em TEXT,
        PRIMARY KEY (tipo_instituicao, ano_mes, num_relatorio)
    );
    CREATE INDEX IF NOT EXISTS ix_cad ON cadastro(cod_inst);
    CREATE INDEX IF NOT EXISTS ix_cad_seg ON cadastro(ano_mes, sr, tcb, td);
    """)
    con.commit()
    return con


def ja_baixado(con):
    return {(t, a, r) for t, a, r in
            con.execute("SELECT tipo_instituicao, ano_mes, num_relatorio "
                        "FROM controle WHERE status='ok'")}


# ---------------------------------------------------------------------------
# ETAPAS
# ---------------------------------------------------------------------------
def baixar_relatorios(con):
    dados = get_json(f"{BASE}/ListaDeRelatorio()?$format=json")
    if not dados:
        raise RuntimeError("Não foi possível listar relatórios. Verifique a conexão.")
    linhas = [(str(d.get("NumeroRelatorio", "")).strip(),
               str(d.get("NomeRelatorio", "")).strip()) for d in dados]
    con.executemany("INSERT OR REPLACE INTO relatorios VALUES (?,?)", linhas)
    con.commit()
    print(f"  {len(linhas)} relatórios disponíveis:")
    for n, nm in sorted(linhas, key=lambda x: int(x[0]) if x[0].isdigit() else 999):
        print(f"    {n:>3}  {nm[:66]}")
    return [n for n, _ in linhas]


def trimestres_sem_cadastro(con, trimestres=None):
    alvo = trimestres or TRIMESTRES
    return [t for t in alvo if not con.execute(
        "SELECT 1 FROM cadastro WHERE ano_mes=? LIMIT 1", (t,)).fetchone()]


def baixar_cadastro_um(con, anomes):
    d = get_json_paginado(
        f"{BASE}/IfDataCadastro(AnoMes=@AnoMes)?@AnoMes={anomes}&$format=json")
    if not d:
        return 0
    con.executemany(
        "INSERT OR REPLACE INTO cadastro VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [(anomes, str(x.get("CodInst", "")).strip(),
          str(x.get("NomeInstituicao", "")).strip(),
          str(x.get("Td", "")).strip(), str(x.get("Tc", "")).strip(),
          str(x.get("Sr", "")).strip(), str(x.get("Tcb", "")).strip(),
          str(x.get("SegmentoTb", "")).strip(),
          str(x.get("Atividade", "")).strip(),
          str(x.get("Uf", "")).strip(), str(x.get("Municipio", "")).strip(),
          str(x.get("CodConglomeradoFinanceiro", "")).strip(),
          str(x.get("CodConglomeradoPrudencial", "")).strip(),
          str(x.get("DataInicioAtividade", "")).strip()) for x in d])
    con.commit()
    return len(d)


def baixar_cadastro(con):
    falta = trimestres_sem_cadastro(con)
    if not falta:
        print("  cadastro já completo.")
        return
    print(f"  baixando cadastro de {len(falta)} trimestres...")
    for k, t in enumerate(falta, 1):
        n = baixar_cadastro_um(con, t)
        print(f"\r    {k}/{len(falta)}  {t}  ({n} inst.)   ",
              end="", flush=True)
        time.sleep(PAUSA)
    print()


def gravar_consulta(con, ti, am, rel, linhas):
    """Grava o retorno de uma chamada. Não inventa linha."""
    if linhas is None:
        status, n = "erro", 0
    elif not linhas:
        status, n = "vazio", 0
    else:
        n = len(linhas)
        con.execute(
            "DELETE FROM valores WHERE tipo_instituicao=? AND ano_mes=? AND num_relatorio=?",
            (ti, am, rel),
        )
        con.executemany(
            "INSERT OR IGNORE INTO contas VALUES (?,?,?,?,?)",
            {(rel, str(x.get("Conta", "")).strip(),
              str(x.get("Grupo", "")).strip(),
              str(x.get("NomeColuna", "")).strip(),
              str(x.get("DescricaoColuna", "")).strip()) for x in linhas},
        )
        con.executemany(
            "INSERT INTO valores VALUES (?,?,?,?,?,?)",
            [(ti, am, rel, str(x.get("CodInst", "")).strip(),
              str(x.get("Conta", "")).strip(), x.get("Saldo")) for x in linhas],
        )
        status = "ok"
    con.execute(
        "INSERT OR REPLACE INTO controle VALUES (?,?,?,?,?,?)",
        (ti, am, rel, n, status, datetime.now().isoformat(timespec="seconds")),
    )
    con.commit()
    return status, n


def baixar_uma(con, ti, am, rel):
    url = (f"{BASE}/IfDataValores(AnoMes=@AnoMes,TipoInstituicao=@TipoInstituicao,"
           f"Relatorio=@Relatorio)?@AnoMes={am}&@TipoInstituicao={ti}"
           f"&@Relatorio='{rel}'&$format=json")
    return gravar_consulta(con, ti, am, rel, get_json_paginado(url))


def baixar_valores(con, relatorios):
    feito = ja_baixado(con)
    tarefas = [(ti, am, rel) for ti in TIPOS_INSTITUICAO
               for am in TRIMESTRES for rel in relatorios
               if (ti, am, rel) not in feito]
    total = len(tarefas)
    if not total:
        print("  valores já completos.")
        return

    print(f"  {len(feito)} combinações já baixadas | {total} pendentes")
    print(f"  (pode interromper com Ctrl+C e retomar depois)\n")
    t0 = time.time()
    linhas_tot = 0

    for k, (ti, am, rel) in enumerate(tarefas, 1):
        status, n = baixar_uma(con, ti, am, rel)
        if status == "ok":
            linhas_tot += n

        el = time.time() - t0
        eta = (el / k) * (total - k)
        print(f"\r  {k}/{total} ({k/total*100:5.1f}%) | T{ti} {am} R{rel:>2} "
              f"{status:5s} {n:>6} linhas | total {linhas_tot:,} | "
              f"ETA {eta/60:.0f}min    ", end="", flush=True)
        time.sleep(PAUSA)
    print()


def criar_indices(con):
    """
    Índices criados DEPOIS da carga (inserir sem índice é bem mais rápido).

    ix_val_conta é 'covering' para a consulta típica da análise:
      SELECT cod_inst, ano_mes, saldo FROM valores
       WHERE tipo_instituicao=? AND num_relatorio=? AND conta=?
    Todas as colunas necessárias estão no próprio índice, então o SQLite
    nem toca na tabela — medido ~1000x mais rápido que sem ele.
    """
    idx = [
        ("ix_val_conta",
         "CREATE INDEX IF NOT EXISTS ix_val_conta ON valores"
         "(tipo_instituicao, num_relatorio, conta, cod_inst, ano_mes, saldo)"),
        ("ix_val_inst",
         "CREATE INDEX IF NOT EXISTS ix_val_inst ON valores"
         "(cod_inst, ano_mes, num_relatorio, conta, saldo)"),
        ("ix_val_periodo",
         "CREATE INDEX IF NOT EXISTS ix_val_periodo ON valores"
         "(ano_mes, tipo_instituicao, num_relatorio)"),
    ]
    for nome, sql in idx:
        t0 = time.time()
        print(f"    {nome} ...", end="", flush=True)
        con.execute(sql); con.commit()
        print(f" {time.time()-t0:.1f}s")

    # view pronta com os textos das contas já juntados
    con.executescript("""
    DROP VIEW IF EXISTS v_dados;
    CREATE VIEW v_dados AS
    SELECT v.tipo_instituicao, v.ano_mes, v.num_relatorio, v.cod_inst,
           v.conta, v.saldo,
           c.nome_coluna, c.descricao_coluna, c.grupo,
           r.nome AS nome_relatorio
      FROM valores v
      LEFT JOIN contas c
             ON c.num_relatorio = v.num_relatorio AND c.conta = v.conta
      LEFT JOIN relatorios r
             ON r.numero = v.num_relatorio;
    """)
    con.commit()
    print("    view v_dados criada (valores + textos das contas)")
    print("    otimizando estatísticas...", end="", flush=True)
    t0 = time.time(); con.execute("ANALYZE"); con.commit()
    print(f" {time.time()-t0:.1f}s")


def exportar_csv(con):
    os.makedirs(PASTA_CSV, exist_ok=True)
    for tabela in ("relatorios", "contas", "cadastro", "controle"):
        cur = con.execute(f"SELECT * FROM {tabela}")
        cols = [d[0] for d in cur.description]
        with open(os.path.join(PASTA_CSV, f"{tabela}.csv"), "w",
                  newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f); w.writerow(cols); w.writerows(cur)
        print(f"    {tabela}.csv")

    # valores: um CSV por perímetro, para não gerar arquivo gigante único
    for ti in TIPOS_INSTITUICAO:
        n = con.execute("SELECT COUNT(*) FROM valores WHERE tipo_instituicao=?",
                        (ti,)).fetchone()[0]
        if not n:
            continue
        cur = con.execute("SELECT * FROM valores WHERE tipo_instituicao=?", (ti,))
        cols = [d[0] for d in cur.description]
        nome = f"valores_tipo{ti}.csv"
        with open(os.path.join(PASTA_CSV, nome), "w",
                  newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f); w.writerow(cols)
            while True:
                lote = cur.fetchmany(50000)
                if not lote:
                    break
                w.writerows(lote)
        print(f"    {nome}  ({n:,} linhas)")


def status(con):
    print("\nSTATUS DA BASE")
    print("=" * 62)
    for tab in ("relatorios", "contas", "cadastro", "valores", "controle"):
        n = con.execute(f"SELECT COUNT(*) FROM {tab}").fetchone()[0]
        print(f"  {tab:<12} {n:>14,} linhas")
    tot = len(TIPOS_INSTITUICAO) * len(TRIMESTRES) * \
        con.execute("SELECT COUNT(*) FROM relatorios").fetchone()[0]
    ok = con.execute("SELECT COUNT(*) FROM controle WHERE status='ok'").fetchone()[0]
    vz = con.execute("SELECT COUNT(*) FROM controle WHERE status='vazio'").fetchone()[0]
    er = con.execute("SELECT COUNT(*) FROM controle WHERE status='erro'").fetchone()[0]
    print("  perímetros   " + ", ".join(f"{k}={v}" for k, v in NOME_TIPO.items()))
    print(f"\n  progresso    {ok+vz+er:>6} / {tot} combinações")
    print(f"    ok={ok}  vazio={vz}  erro={er}")
    if os.path.exists(DB):
        print(f"\n  arquivo      {DB}  ({os.path.getsize(DB)/1e6:.1f} MB)")
    n_inst = con.execute("SELECT COUNT(DISTINCT cod_inst) FROM cadastro").fetchone()[0]
    print(f"  instituições distintas no cadastro: {n_inst:,}")


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg in ("", "--help", "-h"):
        print("O download não começa sozinho.")
        print("Abra o app e escolha perímetro, trimestre e relatório:")
        print("    streamlit run app.py")
        print("Outros comandos: --status  --indices  --exportar  --baixar-tudo")
        return

    con = abrir_db()

    if arg == "--status":
        status(con); return
    if arg == "--exportar":
        print("Exportando CSVs..."); exportar_csv(con); return
    if arg == "--indices":
        print("Criando índices e view..."); criar_indices(con); status(con); return
    if arg != "--baixar-tudo":
        print(f"Argumento desconhecido: {arg}")
        print("Use --help.")
        return

    print("=" * 62)
    print("BASE OFFLINE IF.data — Banco Central do Brasil")
    print(f"Período: {TRIMESTRES[0]} a {TRIMESTRES[-1]} ({len(TRIMESTRES)} trimestres)")
    print("Perímetros: " + ", ".join(f"{k}={v}" for k, v in NOME_TIPO.items()))
    print("Todos os relatórios, todas as contas, todas as instituições")
    print("=" * 62)
    t0 = time.time()

    print("\n[1/5] Relatórios disponíveis")
    relatorios = baixar_relatorios(con)

    print("\n[2/5] Cadastro de instituições")
    baixar_cadastro(con)

    print("\n[3/5] Valores (etapa longa — retomável)")
    try:
        baixar_valores(con, relatorios)
    except KeyboardInterrupt:
        print("\n\n  Interrompido. O progresso foi salvo — rode de novo para continuar.")
        status(con); con.close(); return

    print("\n[4/5] Criando índices e view")
    criar_indices(con)

    if EXPORTAR_CSV:
        print("\n[5/5] Exportando CSVs")
        exportar_csv(con)

    status(con)
    print(f"\n  tempo total: {(time.time()-t0)/60:.1f} min")
    print(f"\n  Envie o arquivo {DB} (ou a pasta {PASTA_CSV}/) para análise.")
    con.close()


if __name__ == "__main__":
    main()
