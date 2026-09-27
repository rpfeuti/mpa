---
description: REGRA ABSOLUTA - todo cálculo deve estar fundamentado em Bansal et al. (2022); sem invenções nem simplificações
alwaysApply: true
---

# Fidelidade ao paper Bansal et al. (2022) — REGRA ABSOLUTA

Referência: `Bansal(2022).pdf` (Omega 107, 102538).

- Não inventar nenhum cálculo, fórmula, variável, restrição, parâmetro ou etapa que não esteja fundamentado no paper.
- Não criar simplificações: nada de trocar o modelo por uma versão mais fácil, remover restrições, juntar divisões, mudar constantes ou pular etapas.
- Todo cálculo implementado deve citar a equação, tabela ou seção do paper que o fundamenta (por exemplo, "eq. (17)-(25)", "Tabela 1", "seção 4.2").
- Se um dado exigido pelo paper não existir na base do Bacen, ou se algo não puder ser resolvido fielmente, não contornar em silêncio: parar e expor a limitação ao usuário, dizendo o que o paper pede, o que falta e quais seriam as opções.
- Qualquer adaptação ao caso brasileiro (proxy, mapeamento de conta, recorte de amostra) só entra depois de exposta como limitação e aprovada explicitamente pelo usuário.
- Na dúvida entre seguir o paper e "facilitar", seguir o paper.
