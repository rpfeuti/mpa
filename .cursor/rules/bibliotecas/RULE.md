---
description: Nenhuma biblioteca nova ou troca de biblioteca sem consulta ao usuário
alwaysApply: true
---

# Bibliotecas

O agente não escolhe biblioteca. Quem escolhe é o usuário.

- Biblioteca é pacote de terceiros e também ponte pronta: scipy, HiGHS, linprog, xlwings, pandas, numpy, openpyxl e qualquer outro nome que não seja a linguagem pura.
- Antes de adicionar, instalar ou trocar uma biblioteca, parar e perguntar. Dizer o nome e para que serviria. Esperar a resposta.
- Biblioteca que o projeto já usa pode seguir no mesmo papel. Mudar esse papel, ou pôr outra no lugar, exige consulta.
- Se der para fazer com a linguagem pura ou com fórmula do Excel, essa é a opção a apresentar. A biblioteca só entra se o usuário aceitar.

## Exemplos

- Errado: o Excel precisa rodar Python, então uso xlwings.
- Certo: o Excel 365 já tem Python na planilha. Se isso não bastar, pergunto qual biblioteca você autoriza.
