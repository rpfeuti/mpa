# -*- coding: utf-8 -*-
"""Covariáveis da Tabela 6 (seção 4.3.3). A regressão GMM não está estimada.

O PDF lê COVARIAVEIS e PENDENCIAS_GMM daqui para não divergir do código.
"""

COVARIAVEIS = {
    "G_NPLs": "NPL_t / NPL_(t−1) − 1, com NPL = níveis E a H",
    "SIZE": "ln(78182), ativo total",
    "IC": "(|78218| + |78219|) / 78182",
    "EQTA": "78186 / 78182",
    "LIQUIDITY": "carteira AA a H / depósitos (78287 − 78284)",
    "BME": "|78218| / (|78218| + |78219| + |78220| + |78223|)",
    "DIVERSIFICATION": "Stiroh e Rumble (2006), eq. (1)-(2): 1 − (SH_NET² + SH_NON²); vazio se NET ≤ 0 (P6)",
}

PENDENCIAS_GMM = [
    "Autorizar a instalação do pacote pydynpd (P3).",
    "A equação da seção 4.3.3 usa ln(Z_k) para todas as covariáveis. G_NPLs pode ser negativo e o paper não diz como tratou. Precisa de decisão.",
    "A Tabela 6 do paper omite covariáveis em algumas colunas ('best fitted regression equations') sem descrever a regra de seleção. Precisa de decisão.",
    "PRIORITY fica fora: não há equivalente no IF.data (decisão já tomada).",
]
