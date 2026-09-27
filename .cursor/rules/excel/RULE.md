---
description: Nunca VBA no Excel e nunca Python dentro da planilha
alwaysApply: true
---

# Excel sem macro e sem Python

O Excel deste projeto não executa código.

- Nunca VBA (Visual Basic for Applications): sem macro, sem arquivo .xlsm, sem botão de formulário, sem xlwings.
- Nunca Python dentro da planilha: sem fórmula PY (Python do Excel 365), sem python.xml, sem aba de código.
- O simplex roda na linha de comando e grava solucoes.xlsx. bansal.xlsx só liga a esse arquivo.

## Exemplos

- Errado: um botão no Excel que chama o Python.
- Errado: uma célula PY que chama otimo.
- Certo: `python excel_bansal.py --solucionar` grava os números, e a planilha aponta para eles.
