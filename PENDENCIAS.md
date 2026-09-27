# Pendências do projeto (replicação de Bansal et al., 2022)

## P1. Teste de Li (Tabela 3, painel D) — ADIADO

- **O que o paper faz:** compara as distribuições de EC (mudança de eficiência), TC (mudança técnica) e dos índices DMLPI e DSMLPI entre bancos públicos e privados com o teste não paramétrico de Li (Tabela 3, painel D; referência [61]).
- **Referência necessária:** Li, Q. (1996). Nonparametric testing of closeness between two unknown distribution functions. *Econometric Reviews* 15(3):261–274. DOI: [10.1080/07474939608800355](https://doi.org/10.1080/07474939608800355).
- **Por que está pendente:** o artigo é pago e não foi obtido. O paper de Bansal não traz a fórmula. Pela regra de fidelidade, o teste não é implementado sem a fonte original.
- **Situação na tela:** o painel D da Tabela 3 aparece como pendência declarada, sem valores. Os painéis A, B e C são calculados normalmente.
- **Como destravar:**
  - Opção 1: obter o PDF pela FGV (rede da FGV ou Portal CAPES com login CAFe) ou por comutação bibliográfica, e salvar nesta pasta.
  - Opção 2 (só com aprovação do usuário): implementar pela fórmula reproduzida em fontes abertas (Pagan e Ullah, 1999, pp. 68-69) com a generalização de Li, Maasoumi e Racine para grupos de tamanhos diferentes (working paper de 2004, gratuito). Seria uma adaptação declarada.
- **Observação:** os grupos têm tamanhos diferentes (4 públicos e 12 privados nacionais). A forma simples do teste nas fontes abertas supõe grupos de mesmo tamanho.

## Outras pendências do usuário

- **P2. RESOLVIDA.** PDFs salvos na pasta:
  - Chung, Färe e Grosskopf (1997): `1-s2.0-S0301479797901468-main.pdf`
  - Oh e Heshmati (2010): `1-s2.0-S0140988310001453-main.pdf`
  - Stiroh e Rumble (2006): `1-s2.0-S0378426605001342-main.pdf`
- **P5. RESOLVIDA.** A Tabela 5 roda com 19 bancos. JP Morgan, UBS, CCB, BTG e Pine ficam fora só dessa tabela, declarados, por margem de juros negativa em algum ano. A tabela usa CRS (retornos constantes de escala), como nos artigos-fonte (C1 = A).
- **P6. RESOLVIDA.** DIVERSIFICATION fica vazio e declarado nos 14 banco-anos com margem de juros negativa.
- **P7. RESOLVIDA.** Os insumos são contraídos por (1 − β), pela "direção de insumos e produtos observados" (Bansal, seção 4.3.2) e pela eq. (3.14) de Chung.
- **P3.** Autorizar a instalação do pacote `pydynpd` quando a Tabela 6 (GMM, método generalizado dos momentos) for implementada.
- **P4.** Clicar nos botões de download do deflator do PIB (BCB SGS 1211) e da ESTBAN (Estatística Bancária Mensal, agências).
