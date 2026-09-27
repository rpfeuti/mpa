---
description: Regras de integridade e interpretação dos dados IF.data do Bacen
alwaysApply: true
---

# Dados do Bacen

## Integridade
- Nunca inventar, estimar, interpolar ou preencher valores. Resposta vazia da API fica vazia e vai para o log.
- Toda variável derivada (soma, diferença, proxy) deve ser declarada com as contas de origem.
- Antes de afirmar um código, nome ou valor, conferir na base. Não responder de memória.

## Perímetros (`tipo_instituicao`, validado empiricamente)
- 1 = conglomerado prudencial, 2 = conglomerado financeiro, 3 = instituição individual.
- O estudo usa o tipo 2. Não somar bancos individuais para montar um conglomerado.
- Consultar sempre com `tipo_instituicao` + `cod_inst`; sem o tipo, o mesmo grupo aparece três vezes.

## Janela e regimes
- Janela da base: 201403 a 202412. Não misturar com o Cosif 2025+ (contas e relatórios mudam).
- Saldos em reais (não em R$ mil).
- DRE acumulada no semestre: março = 1º tri, junho = 1º semestre, setembro = 3º tri, dezembro = 2º semestre.
- Despesas vêm negativas no Cosif; no DEA usar valor absoluto nos insumos. Lucro e carryovers mantêm o sinal.
- Relatório 8 (SCR, AA a H) só existe no tipo 2 e classifica só a carteira doméstica. Não misturar SCR e Cosif na mesma variável.

## Cadastro
- Uma linha por instituição por trimestre: o mesmo `cod_inst` em trimestres diferentes é a mesma instituição.
- `sr` (S1 a S5) vem vazio antes de 2017: escolher a amostra num trimestre recente e aplicar o `cod_inst` ao histórico.
