# -*- coding: utf-8 -*-
"""DMLPI e DSMLPI de Bansal et al. (2022) e MLPI/SMLPI padrão da Tabela 5.

- M1, eq. (5)-(13): fronteira do próprio período, VRS (retornos variáveis de escala) por divisão.
- M2, eq. (17)-(25): fronteira sequencial (todos os períodos até t+a).
- Índices e decomposição EC x TC: eq. (14) e (26).
- Tabela 5: Chung et al. (1997), eq. (3.5)-(3.7) e (3.14), e Oh e Heshmati (2010), eq. (9)-(11),
  em CRS (retornos constantes de escala), direção de insumos e produtos observados (seção 4.3.2).
- O ótimo de β é um simplex em duas fases, em Python, sem biblioteca. O paper resolve no LINGO
  e não descreve o algoritmo. O simplex só procura o ótimo das mesmas restrições.
"""
import numpy as np
import pandas as pd

# Seção 4.3.1
XI, PI = 3.0, 1.0
ETA_T, ETA_T1, DELTA = 3.0, 1.5, 1.0

# Papel de cada variável na rede (Tabela 1 e Fig. 2)
X_DIV = {1: ["labor", "fixed"], 2: ["interbank"], 3: ["llp"]}   # insumos desejáveis, eq. (5)/(17)
V1 = ["equity"]                                                  # quase-fixo, eq. (6)/(18)
W2 = ["npl_lag"]                                                 # insumo indesejável, eq. (7)/(19)
Y3 = ["nii", "nonii"]                                            # saídas desejáveis, eq. (8)/(20)
U2 = ["npl"]                                                     # saída indesejável, eq. (9)/(21)
C2 = ["unused", "profit"]                                        # carryover em t, eq. (10)/(22)
C2_LAG = ["unused_lag", "profit_lag"]                            # carryover em t-1, eq. (11)/(23)
Z12 = ["deposits"]                                               # ligação 1-2, eq. (12)/(24)
Z23 = ["performing", "invest"]                                   # ligação 2-3, eq. (12)/(24)

ML_X = ["labor", "fixed", "equity"]
ML_Y = ["nii", "nonii"]
ML_B = ["npl"]

CAMPOS = ["labor", "fixed", "equity", "deposits", "interbank", "npl", "npl_lag", "unused", "profit",
          "unused_lag", "profit_lag", "performing", "invest", "llp", "nii", "nonii"]


def preparar(norm):
    """Arrays [ano, banco] por variável. O ano de 2014 entra só como defasagem."""
    bancos = sorted(norm["sigla"].unique())
    anos_todos = sorted(norm["ano"].unique())
    p = norm.set_index(["ano", "sigla"])
    arr = {}
    for v in ["labor", "fixed", "equity", "deposits", "interbank", "npl", "unused", "profit",
              "performing", "invest", "llp", "nii", "nonii"]:
        arr[v] = np.array([[p.loc[(a, b), v] for b in bancos] for a in anos_todos], dtype=float)
    anos = anos_todos[1:]
    dados = {v: arr[v][1:] for v in arr}
    dados["npl_lag"] = arr["npl"][:-1]
    dados["unused_lag"] = arr["unused"][:-1]
    dados["profit_lag"] = arr["profit"][:-1]
    return {"bancos": bancos, "anos": anos, "dados": dados}


def fronteira(prep, idx_anos):
    """Observações (banco, ano) da fronteira, empilhadas."""
    d = prep["dados"]
    return {v: np.concatenate([d[v][i] for i in idx_anos]) for v in CAMPOS}


def observacao(prep, i_ano, j):
    return {v: float(prep["dados"][v][i_ano, j]) for v in CAMPOS}


def direcoes(front, mult, sub):
    """µ, ρ, ν, ω, γ, α sobre as observações da fronteira (seção 3.2 e definição antes da eq. 16)."""
    mx = lambda v: mult * float(np.max(np.abs(front[v])))
    mn = lambda v: float(np.min(front[v])) - sub
    return {
        "mu": {v: mx(v) for k in X_DIV for v in X_DIV[k]},
        "rho": {v: mn(v) for v in W2},
        "nu": {v: mn(v) for v in Y3},
        "omega": {v: mx(v) for v in U2},
        "gamma": {v: mn(v) for v in C2},
        "alpha": {v: mx(v) for v in C2_LAG},
    }


def termos_direcao(o, d):
    """Termos que o paper exige positivos (texto após a eq. 13)."""
    t = {}
    for v, m in d["mu"].items():
        t[f"x_o+µ[{v}]"] = o[v] + m
    for v, r in d["rho"].items():
        t[f"w_o−ρ[{v}]"] = o[v] - r
    for v, n in d["nu"].items():
        t[f"y_o−ν[{v}]"] = o[v] - n
    for v, w in d["omega"].items():
        t[f"u_o+ω[{v}]"] = o[v] + w
    for v, g in d["gamma"].items():
        t[f"c_o−γ[{v}]"] = o[v] - g
    for v, a in d["alpha"].items():
        t[f"c_o(t−1)+α[{v}]"] = o[v] + a
    return t


def _seq(x):
    if hasattr(x, "tolist") and not isinstance(x, list):
        x = x.tolist()
    return [float(v) for v in x]


def _escreve(r, sl, valores):
    vals = _seq(valores)
    a, b = sl.start, sl.stop
    r[a:b] = vals


def montar_lp_rede(front, o, d):
    """Listas das eq. (5)-(13) (M1) ou (17)-(25) (M2). Variáveis: β, λ1, λ2, λ3, φ1."""
    N = len(front["labor"])
    nv = 1 + 4 * N
    sl = {1: slice(1, 1 + N), 2: slice(1 + N, 1 + 2 * N), 3: slice(1 + 2 * N, 1 + 3 * N)}
    sphi = slice(1 + 3 * N, 1 + 4 * N)
    A, b, nomes = [], [], []

    def linha():
        return [0.0] * nv

    for k, vs in X_DIV.items():
        for v in vs:
            r = linha(); r[0] = o[v] + d["mu"][v]; _escreve(r, sl[k], front[v])
            A.append(r); b.append(float(o[v])); nomes.append(("(5)", v, "≤"))
    for v in V1:
        r = linha(); _escreve(r, sl[1], front[v]); _escreve(r, sphi, front[v])
        A.append(r); b.append(float(o[v])); nomes.append(("(6)", v, "≤"))
    for v in W2:
        r = linha(); r[0] = o[v] - d["rho"][v]; _escreve(r, sl[2], [-x for x in _seq(front[v])])
        A.append(r); b.append(-float(o[v])); nomes.append(("(7)", v, "≥"))
    for v in Y3:
        r = linha(); r[0] = o[v] - d["nu"][v]; _escreve(r, sl[3], [-x for x in _seq(front[v])])
        A.append(r); b.append(-float(o[v])); nomes.append(("(8)", v, "≥"))
    for v in U2:
        r = linha(); r[0] = o[v] + d["omega"][v]; _escreve(r, sl[2], front[v])
        A.append(r); b.append(float(o[v])); nomes.append(("(9)", v, "≤"))
    for v in C2:
        r = linha(); r[0] = o[v] - d["gamma"][v]; _escreve(r, sl[2], [-x for x in _seq(front[v])])
        A.append(r); b.append(-float(o[v])); nomes.append(("(10)", v, "≥"))
    for v in C2_LAG:
        r = linha(); r[0] = o[v] + d["alpha"][v]; _escreve(r, sl[2], front[v])
        A.append(r); b.append(float(o[v])); nomes.append(("(11)", v, "≤"))

    Aeq, beq, nomes_eq = [], [], []
    for v in Z12:
        r = linha(); _escreve(r, sl[1], front[v]); _escreve(r, sl[2], [-x for x in _seq(front[v])])
        Aeq.append(r); beq.append(0.0); nomes_eq.append(("(12)", v, "="))
    for v in Z23:
        r = linha(); _escreve(r, sl[2], front[v]); _escreve(r, sl[3], [-x for x in _seq(front[v])])
        Aeq.append(r); beq.append(0.0); nomes_eq.append(("(12)", v, "="))
    for k in (1, 2, 3):
        r = linha(); r[sl[k]] = [1.0] * N
        Aeq.append(r); beq.append(1.0); nomes_eq.append(("(13)", f"Σλ{k}", "="))

    c = [0.0] * nv
    c[0] = -1.0
    bounds = [(None, None)] + [(0, None)] * (4 * N)
    return c, A, b, Aeq, beq, bounds, nomes, nomes_eq, sl, sphi


def montar_lp_ml(front, o):
    """Chung et al. (1997) eq. (3.14). Variáveis: β, z. Listas, sem biblioteca."""
    N = len(front["labor"])
    nv = 1 + N
    A, b, Aeq, beq = [], [], [], []

    def linha():
        return [0.0] * nv

    for v in ML_Y:
        r = linha(); r[0] = float(o[v]); _escreve(r, slice(1, nv), [-x for x in _seq(front[v])])
        A.append(r); b.append(-float(o[v]))
    for v in ML_X:
        r = linha(); r[0] = float(o[v]); _escreve(r, slice(1, nv), front[v])
        A.append(r); b.append(float(o[v]))
    for v in ML_B:
        r = linha(); r[0] = float(o[v]); _escreve(r, slice(1, nv), front[v])
        Aeq.append(r); beq.append(float(o[v]))
    c = [0.0] * nv
    c[0] = -1.0
    lb = [None] + [0.0] * N
    ub = [None] * nv
    return c, A, b, Aeq, beq, lb, ub


# Ordem das direções que a planilha e o comando --solucionar passam ao simplex.
ORDEM_DIR = (
    ("mu", "labor"), ("mu", "fixed"), ("mu", "interbank"), ("mu", "llp"),
    ("rho", "npl_lag"),
    ("nu", "nii"), ("nu", "nonii"),
    ("omega", "npl"),
    ("gamma", "unused"), ("gamma", "profit"),
    ("alpha", "unused_lag"), ("alpha", "profit_lag"),
)


def _como_tabela(x):
    """Aceita lista, lista de listas ou um vetor do numpy."""
    if x is None:
        return []
    if hasattr(x, "to_numpy"):
        x = x.to_numpy().tolist()
    elif hasattr(x, "tolist") and not isinstance(x, (list, tuple)):
        x = x.tolist()
    if isinstance(x, (int, float)):
        return [[float(x)]]
    if not isinstance(x, list):
        return [[float(x)]]
    if not x:
        return []
    if isinstance(x[0], (list, tuple)):
        return [[float(v) for v in row] for row in x]
    return [[float(v)] for v in x]


def _como_vetor(x):
    tab = _como_tabela(x)
    return [v for row in tab for v in row]


def direcao_de_lista(vals):
    d = {g: {} for g in ("mu", "rho", "nu", "omega", "gamma", "alpha")}
    for (g, v), x in zip(ORDEM_DIR, _como_vetor(vals)):
        d[g][v] = float(x)
    return d


_TOL = 1e-9
_TOL_PIV = 1e-10
_TOL_FOLGA = 1e-7


def _livre(lo):
    if lo is None:
        return True
    try:
        return float(lo) < -1e300
    except (TypeError, ValueError):
        return False


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def _matvec(M, v):
    return [_dot(row, v) for row in M]


def _pivota(Binv, xB, d, p):
    m = len(xB)
    piv = d[p]
    fator = [d[i] / piv for i in range(m)]
    linha_p = [v / piv for v in Binv[p]]
    nova_b = []
    for i in range(m):
        if i == p:
            nova_b.append(linha_p)
        else:
            nova_b.append([Binv[i][k] - fator[i] * Binv[p][k] for k in range(m)])
    nova_x = [xB[i] - fator[i] * xB[p] for i in range(m)]
    nova_x[p] = xB[p] / piv
    return nova_b, nova_x


def _inverter(cols_b):
    """Inversa por eliminação de Gauss com pivô parcial. cols_b[j] é a coluna j da base."""
    m = len(cols_b)
    a = [[cols_b[j][i] for j in range(m)] + [1.0 if i == k else 0.0 for k in range(m)] for i in range(m)]
    for col in range(m):
        piv = max(range(col, m), key=lambda r: abs(a[r][col]))
        if abs(a[piv][col]) < 1e-12:
            return None
        a[col], a[piv] = a[piv], a[col]
        div = a[col][col]
        a[col] = [v / div for v in a[col]]
        for r in range(m):
            if r == col:
                continue
            fat = a[r][col]
            if fat == 0.0:
                continue
            a[r] = [a[r][k] - fat * a[col][k] for k in range(2 * m)]
    return [row[m:] for row in a]


def _simplex(cols, custo, basis, Binv, xB, bvec, artificiais, fase2):
    """Simplex revisado, regra de Bland. Devolve ('ok', Binv, xB, basis) ou ('ilimitado', ...)."""
    m = len(basis)
    n = len(cols)
    em_base = set(basis)
    limite = max(5000, 20 * (n + m))
    for passo in range(limite):
        if passo and passo % 20 == 0:
            inv = _inverter([cols[basis[i]] for i in range(m)])
            if inv is not None:
                Binv = inv
                xB = _matvec(Binv, bvec)
        cB = [custo[basis[i]] for i in range(m)]
        pi = [sum(cB[k] * Binv[k][j] for k in range(m)) for j in range(m)]
        entra = None
        for j in range(n):
            if j in em_base or (fase2 and j in artificiais):
                continue
            if custo[j] - _dot(pi, cols[j]) < -_TOL:
                entra = j
                break
        if entra is None:
            return "ok", Binv, xB, basis
        d = _matvec(Binv, cols[entra])
        candidatos = [(xB[i] / d[i], basis[i], i) for i in range(m) if d[i] > _TOL_PIV and xB[i] / d[i] >= -_TOL]
        if not candidatos:
            return "ilimitado", Binv, xB, basis
        ratio_min = min(c[0] for c in candidatos)
        fila = [c for c in candidatos if c[0] <= ratio_min + 1e-8]
        fila.sort(key=lambda c: c[1])
        p = fila[0][2]
        sai = basis[p]
        Binv, xB = _pivota(Binv, xB, d, p)
        for i in range(m):
            if -_TOL < xB[i] < 0.0:
                xB[i] = 0.0
        basis[p] = entra
        em_base.discard(sai)
        em_base.add(entra)
    return "ilimitado", Binv, xB, basis


def resolver_lp(c, A_ub, b_ub, A_eq, b_eq, lb, ub):
    """min c·x, A_ub x ≤ b_ub, A_eq x = b_eq. status 0 = ótimo, 2 = sem solução, 4 = ilimitado.

    Simplex em duas fases, só com listas. β livre vira β+ − β−. Desigualdade vira igualdade
    com folga. Igualdade recebe variável artificial na fase 1. O pivô é eliminação de Gauss
    no quadro da base. Empate usa a regra de Bland. O paper não descreve este algoritmo.
    """
    c = [float(v) for v in c]
    n = len(c)
    if hasattr(A_ub, "tolist"):
        A_ub = A_ub.tolist()
    if hasattr(A_eq, "tolist"):
        A_eq = A_eq.tolist()
    A_ub = [[float(v) for v in row] for row in (A_ub or [])]
    A_eq = [[float(v) for v in row] for row in (A_eq or [])]
    b_ub = [float(v) for v in (b_ub if b_ub is not None else [])]
    b_eq = [float(v) for v in (b_eq if b_eq is not None else [])]
    lb = list(lb)
    espec = []
    for j in range(n):
        lo = lb[j] if j < len(lb) else 0.0
        if _livre(lo):
            espec.append((j, 1.0))
            espec.append((j, -1.0))
        else:
            espec.append((j, 1.0))

    def coef(linha):
        return [sinal * linha[j] for j, sinal in espec]

    tipos = []
    for i, row in enumerate(A_ub):
        rhs = b_ub[i]
        if rhs < -_TOL:
            tipos.append(([-v for v in coef(row)], -rhs, "ge"))
        else:
            tipos.append((coef(row), rhs, "le"))
    for i, row in enumerate(A_eq):
        rhs = b_eq[i]
        if rhs < -_TOL:
            tipos.append(([-v for v in coef(row)], -rhs, "eq"))
        else:
            tipos.append((coef(row), max(rhs, 0.0), "eq"))
    m = len(tipos)
    if m == 0:
        return None, 4
    nS = len(espec)
    cols = [[tipos[i][0][s] for i in range(m)] for s in range(nS)]
    custo = [sinal * c[j] for j, sinal in espec]
    mapa = list(espec)
    basis = [-1] * m
    artificiais = set()
    bvec = [tipos[i][1] for i in range(m)]
    for i, (_, _, tipo) in enumerate(tipos):
        if tipo == "le":
            col = [0.0] * m
            col[i] = 1.0
            cols.append(col)
            custo.append(0.0)
            mapa.append(None)
            basis[i] = len(cols) - 1
        else:
            if tipo == "ge":
                col = [0.0] * m
                col[i] = -1.0
                cols.append(col)
                custo.append(0.0)
                mapa.append(None)
            col = [0.0] * m
            col[i] = 1.0
            cols.append(col)
            custo.append(0.0)
            mapa.append(("art",))
            artificiais.add(len(cols) - 1)
            basis[i] = len(cols) - 1
    Binv = [[1.0 if i == k else 0.0 for k in range(m)] for i in range(m)]
    xB = bvec[:]
    custo1 = [1.0 if j in artificiais else 0.0 for j in range(len(cols))]
    if artificiais:
        flag, Binv, xB, basis = _simplex(cols, custo1, basis, Binv, xB, bvec, artificiais, False)
        if flag != "ok":
            return None, 4
        if sum(xB[i] for i in range(m) if basis[i] in artificiais) > _TOL_FOLGA:
            return None, 2
        for i in range(m):
            if basis[i] not in artificiais or abs(xB[i]) > _TOL:
                continue
            for j, col in enumerate(cols):
                if j in artificiais or j in basis:
                    continue
                d = _matvec(Binv, col)
                if abs(d[i]) > 1e-8:
                    Binv, xB = _pivota(Binv, xB, d, i)
                    basis[i] = j
                    break
    flag, Binv, xB, basis = _simplex(cols, custo, basis, Binv, xB, bvec, artificiais, True)
    if flag != "ok":
        return None, 4
    x = [0.0] * n
    for i in range(m):
        info = mapa[basis[i]]
        if not info or info[0] == "art":
            continue
        j, sinal = info
        x[j] += sinal * xB[i]
    return x, 0


class ModeloRede:
    """Restrições montadas uma vez por fronteira; por banco muda a coluna do β e o lado direito."""

    def __init__(self, front, d):
        self.front, self.d = front, d
        zero = {v: 0.0 for v in CAMPOS}
        c, A, b, Aeq, beq, bounds, nomes, nomes_eq, sl, sphi = montar_lp_rede(front, zero, d)
        self.c = c
        self.A_sem = [row[1:] for row in A]
        self.Aeq = Aeq
        self.beq = beq
        self.lb = [lo for lo, _ in bounds]
        self.ub = [hi for _, hi in bounds]
        self.nomes, self.sl, self.sphi = nomes, sl, sphi

    def coluna_beta_e_rhs(self, o):
        d = self.d
        col, rhs = [], []
        for eq, v, _ in self.nomes:
            if eq == "(5)":
                col.append(o[v] + d["mu"][v]); rhs.append(o[v])
            elif eq == "(6)":
                col.append(0.0); rhs.append(o[v])
            elif eq == "(7)":
                col.append(o[v] - d["rho"][v]); rhs.append(-o[v])
            elif eq == "(8)":
                col.append(o[v] - d["nu"][v]); rhs.append(-o[v])
            elif eq == "(9)":
                col.append(o[v] + d["omega"][v]); rhs.append(o[v])
            elif eq == "(10)":
                col.append(o[v] - d["gamma"][v]); rhs.append(-o[v])
            elif eq == "(11)":
                col.append(o[v] + d["alpha"][v]); rhs.append(o[v])
        return col, rhs

    def _sistema(self, o):
        col, rhs = self.coluna_beta_e_rhs(o)
        A = [[col[i]] + row for i, row in enumerate(self.A_sem)]
        return A, rhs

    def resolver(self, o):
        A, rhs = self._sistema(o)
        x, status = resolver_lp(self.c, A, rhs, self.Aeq, self.beq, self.lb, self.ub)
        return (float(x[0]) if status == 0 else np.nan), status

    def resolver_detalhado(self, o):
        A, rhs = self._sistema(o)
        x, status = resolver_lp(self.c, A, rhs, self.Aeq, self.beq, self.lb, self.ub)
        if status != 0:
            return np.nan, status, None
        return float(x[0]), 0, {"beta": float(x[0]), "lambda1": x[self.sl[1]], "lambda2": x[self.sl[2]],
                                "lambda3": x[self.sl[3]], "phi1": x[self.sphi]}


def resolver_rede(front, o, d, detalhes=False):
    c, A, b, Aeq, beq, bounds, nomes, nomes_eq, sl, sphi = montar_lp_rede(front, o, d)
    lb = [lo for lo, _ in bounds]
    ub = [hi for _, hi in bounds]
    x, status = resolver_lp(c, A, b, Aeq, beq, lb, ub)
    beta = float(x[0]) if status == 0 else np.nan
    if not detalhes:
        return beta, status
    sol = None
    if status == 0:
        sol = {"beta": beta, "lambda1": x[sl[1]], "lambda2": x[sl[2]], "lambda3": x[sl[3]], "phi1": x[sphi]}
    return beta, status, sol


def resolver_ml(front, o):
    """Chung et al. (1997) eq. (3.14), CRS, direção (−x, y, −b). Variáveis: β, z."""
    c, A, b, Aeq, beq, lb, ub = montar_lp_ml(front, o)
    x, status = resolver_lp(c, A, b, Aeq, beq, lb, ub)
    return (float(x[0]) if status == 0 else np.nan), status


def otimo(kind, front, direcao, obs):
    """Um programa linear. Devolve [β, status, pesos].

    kind 'rede': eq. (5)-(13) ou (17)-(25). kind 'ml': Chung eq. (3.14).
    front é a matriz dos bancos da fronteira, na ordem de CAMPOS.
    direcao são os 12 valores de ORDEM_DIR. obs é o banco avaliado, na ordem de CAMPOS.
    """
    linhas = _como_tabela(front)
    o_vals = _como_vetor(obs)
    o = {CAMPOS[i]: o_vals[i] for i in range(len(CAMPOS))}
    fr = {CAMPOS[j]: [linhas[i][j] for i in range(len(linhas))] for j in range(len(CAMPOS))}
    if kind == "ml":
        c, A, b, Aeq, beq, lb, ub = montar_lp_ml(fr, o)
        x, status = resolver_lp(c, A, b, Aeq, beq, lb, ub)
        n_pesos = len(linhas)
    else:
        d = direcao_de_lista(direcao)
        c, A, b, Aeq, beq, bounds, _, _, _, _ = montar_lp_rede(fr, o, d)
        x, status = resolver_lp(c, A, b, Aeq, beq, [lo for lo, _ in bounds], [hi for _, hi in bounds])
        n_pesos = 4 * len(linhas)
    if status != 0 or x is None:
        return [""] + [status] + [0.0] * n_pesos
    return [x[0], status] + x[1:1 + n_pesos]


def indices(D):
    """Eq. (14)/(26), iguais em forma a Chung (3.5)-(3.7). D[(a, b)] = D^{t+a}(obs de t+b)."""
    d00, d01, d10, d11 = (1 + D[(0, 0)], 1 + D[(0, 1)], 1 + D[(1, 0)], 1 + D[(1, 1)])
    if any(not np.isfinite(x) or x <= 0 for x in (d00, d01, d10, d11)):
        return np.nan, np.nan, np.nan
    ec = d00 / d11
    tc = np.sqrt((d11 / d01) * (d10 / d00))
    idx = np.sqrt((d00 / d01) * (d10 / d11))
    return ec, tc, idx


def calcular_rede(prep, modelo, progresso=None):
    """modelo 'DMLPI' (M1) ou 'DSMLPI' (M2). Devolve (distâncias, índices, avisos de direção, condição 16)."""
    anos, bancos = prep["anos"], prep["bancos"]
    linhas_d, linhas_i, avisos, cond16 = [], [], [], []
    total = (len(anos) - 1) * len(bancos)
    feito = 0
    for it in range(len(anos) - 1):
        dirs = {}
        for a in (0, 1):
            if modelo == "DMLPI":
                idx = [it + a]
                mult, sub = XI, PI
            else:
                idx = list(range(0, it + a + 1))
                mult, sub = (ETA_T if a == 0 else ETA_T1), DELTA
            fr = fronteira(prep, idx)
            d = direcoes(fr, mult, sub)
            dirs[a] = (fr, d, ModeloRede(fr, d))
        if modelo == "DSMLPI":
            d0, d1 = dirs[0][1], dirs[1][1]
            for grupo, sinal in (("mu", "<"), ("omega", "<"), ("alpha", "<"),
                                 ("rho", ">"), ("nu", ">"), ("gamma", ">")):
                for v in d0[grupo]:
                    ok = d1[grupo][v] < d0[grupo][v] if sinal == "<" else d1[grupo][v] > d0[grupo][v]
                    cond16.append({"par": f"{anos[it]}-{anos[it + 1]}", "vetor": grupo, "variavel": v,
                                   "t": d0[grupo][v], "t+1": d1[grupo][v], "exigido": f"t+1 {sinal} t",
                                   "atende": ok})
        for j, cod in enumerate(bancos):
            D = {}
            for a in (0, 1):
                fr, d, mod = dirs[a]
                for b in (0, 1):
                    o = observacao(prep, it + b, j)
                    beta, status = mod.resolver(o)
                    D[(a, b)] = beta
                    linhas_d.append({"modelo": modelo, "sigla": cod, "t": anos[it], "a": a, "b": b,
                                     "beta": beta, "status": status})
                    for nome, val in termos_direcao(o, d).items():
                        if not val > 0:
                            avisos.append({"modelo": modelo, "sigla": cod, "t": anos[it], "a": a, "b": b,
                                           "termo": nome, "valor": val})
            ec, tc, ix = indices(D)
            linhas_i.append({"modelo": modelo, "sigla": cod, "ano": anos[it + 1],
                             "EC": ec, "TC": tc, "IDX": ix})
            feito += 1
            if progresso:
                progresso(feito / total, f"{modelo} {anos[it]}-{anos[it + 1]}")
    return pd.DataFrame(linhas_d), pd.DataFrame(linhas_i), pd.DataFrame(avisos), pd.DataFrame(cond16)


def amostra_tabela5(prep):
    """P5: bancos com margem de juros positiva em todos os anos do modelo."""
    ok = np.all(prep["dados"]["nii"] > 0, axis=0)
    return [j for j in range(len(prep["bancos"])) if ok[j]], [prep["bancos"][j] for j in range(len(ok)) if not ok[j]]


def calcular_ml(prep, modelo, progresso=None):
    """modelo 'MLPI' (fronteira do período) ou 'SMLPI' (fronteira sequencial)."""
    anos, bancos = prep["anos"], prep["bancos"]
    js, _ = amostra_tabela5(prep)
    linhas_d, linhas_i = [], []
    total = (len(anos) - 1) * len(js)
    feito = 0
    for it in range(len(anos) - 1):
        fr = {}
        for a in (0, 1):
            idx = [it + a] if modelo == "MLPI" else list(range(0, it + a + 1))
            fr[a] = {v: np.concatenate([prep["dados"][v][i][js] for i in idx]) for v in CAMPOS}
        for j in js:
            D = {}
            for a in (0, 1):
                for b in (0, 1):
                    beta, status = resolver_ml(fr[a], observacao(prep, it + b, j))
                    D[(a, b)] = beta
                    linhas_d.append({"modelo": modelo, "sigla": bancos[j], "t": anos[it], "a": a, "b": b,
                                     "beta": beta, "status": status})
            ec, tc, ix = indices(D)
            linhas_i.append({"modelo": modelo, "sigla": bancos[j], "ano": anos[it + 1],
                             "EC": ec, "TC": tc, "IDX": ix})
            feito += 1
            if progresso:
                progresso(feito / total, f"{modelo} {anos[it]}-{anos[it + 1]}")
    return pd.DataFrame(linhas_d), pd.DataFrame(linhas_i)


# ---------------------------------------------------------------- tabelas do paper
def gmean(s):
    """Média geométrica das observações com solução. As sem solução aparecem contadas à parte."""
    s = pd.Series(s, dtype=float).dropna()
    if s.empty or (s <= 0).any():
        return np.nan
    return float(np.exp(np.log(s).mean()))


def sem_solucao(sm):
    return int(sm["IDX"].isna().sum())


def tabela_por_ano(ind, modelos, filtro=None):
    """Tabelas 3 e 5: média geométrica por ano e no período inteiro."""
    df = ind if filtro is None else ind[filtro(ind)]
    anos = sorted(df["ano"].unique())
    linhas = []
    for rotulo, sub in [(str(a), df[df["ano"] == a]) for a in anos] + [(f"{anos[0] - 1}-{str(anos[-1])[2:]}", df)]:
        d = {"Ano": rotulo}
        for m in modelos:
            sm = sub[sub["modelo"] == m]
            for comp, nome in (("EC", "EC"), ("TC", "TC"), ("IDX", m)):
                d[f"{m} · {nome}"] = gmean(sm[comp])
            d[f"{m} · sem solução"] = sem_solucao(sm)
        linhas.append(d)
    return pd.DataFrame(linhas)


def tabela_por_banco(ind, modelos, nomes, filtro=None):
    """Tabela 4: média geométrica por banco no período e a média geométrica do grupo."""
    df = ind if filtro is None else ind[filtro(ind)]
    linhas = []
    for cod in sorted(df["sigla"].unique(), key=lambda c: nomes.get(c, c)):
        d = {"Banco": nomes.get(cod, cod)}
        for m in modelos:
            sm = df[(df["modelo"] == m) & (df["sigla"] == cod)]
            for comp, nome in (("EC", "EC"), ("TC", "TC"), ("IDX", m)):
                d[f"{m} · {nome}"] = gmean(sm[comp])
            d[f"{m} · sem solução"] = sem_solucao(sm)
        linhas.append(d)
    d = {"Banco": "Média geométrica"}
    for m in modelos:
        sm = df[df["modelo"] == m]
        for comp, nome in (("EC", "EC"), ("TC", "TC"), ("IDX", m)):
            d[f"{m} · {nome}"] = gmean(sm[comp])
        d[f"{m} · sem solução"] = sem_solucao(sm)
    linhas.append(d)
    return pd.DataFrame(linhas)


def tabela_banco_ano(ind, modelos, nomes, filtro=None):
    """Tabelas B1 e B2: banco x ano."""
    df = ind if filtro is None else ind[filtro(ind)]
    linhas = []
    for cod in sorted(df["sigla"].unique(), key=lambda c: nomes.get(c, c)):
        for a in sorted(df["ano"].unique()):
            d = {"Banco": nomes.get(cod, cod), "Ano": a}
            for m in modelos:
                r = df[(df["modelo"] == m) & (df["sigla"] == cod) & (df["ano"] == a)]
                for comp, nome in (("EC", "EC"), ("TC", "TC"), ("IDX", m)):
                    d[f"{m} · {nome}"] = float(r[comp].iloc[0]) if len(r) else np.nan
            linhas.append(d)
    return pd.DataFrame(linhas)
