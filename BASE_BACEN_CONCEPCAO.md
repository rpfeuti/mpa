# Base Offline IF.data (Banco Central do Brasil) — Concepção e Manual

Documento de acompanhamento do script `baixar_base_bacen.py`.
Destina-se a quem for executar a extração e/ou trabalhar com a base resultante.

---

## 1. Para que serve

O script baixa **toda** a base pública do IF.data do Banco Central do Brasil e a grava
em um banco SQLite local, de modo que toda a análise posterior seja feita **offline**,
sem depender da API.

### Contexto do projeto

A base alimenta um estudo de produtividade do sistema bancário brasileiro que aplica o
**DSMLPI — Dynamic Sequential Malmquist-Luenberger Productivity Index**, seguindo:

- **Bansal, P. & Mehra, A. (2022)**. *Malmquist-Luenberger productivity indexes for
  dynamic network DEA with undesirable outputs and negative data*. RAIRO – Operations
  Research, 56(2), 649-687. — formulação matemática (modelo M5, eq. 6.2 a 6.11)
- **Bansal, P., Kumar, S., Mehra, A. & Gulati, R. (2022)**. *Developing two dynamic
  Malmquist-Luenberger productivity indices*. Omega, 107, 102538. — estrutura de rede
  bancária em 3 divisões (Tabela 1)

### Por que uma base offline

As versões anteriores do trabalho consultavam a API a cada teste. Isso trouxe três
problemas concretos:

1. **Lentidão** — cada rodada de teste exigia dezenas de chamadas HTTP.
2. **Retrabalho** — ao decidir testar uma variável diferente (por exemplo, trocar a
   proxy de capital físico, ou usar carteira de crédito por modalidade em vez de por
   nível de risco), era preciso reextrair tudo.
3. **Fragilidade** — restrições de rede corporativa, proxies e instabilidade da API
   interrompiam o trabalho.

A decisão foi baixar **tudo de uma vez**, sem filtros, e deixar a seleção de variáveis
para a etapa de análise.

---

## 2. Escopo da extração

| Dimensão | Escopo |
|---|---|
| Relatórios | **Todos** os disponíveis (descobertos em tempo de execução via `ListaDeRelatorio`) — tipicamente 16 |
| Contas | **Todas** de cada relatório, sem filtro |
| Instituições | **Todas** — sem filtro de segmento (S1–S5), tipo ou porte |
| Perímetros | Os 3: individual, conglomerado financeiro e conglomerado prudencial |
| Período | `201403` a `202412` (44 trimestres) |

### Por que o período termina em 2024T4

A partir de 01/01/2025 o Banco Central reestruturou o plano de contas Cosif
(Instruções Normativas BCB nº 426 a 433/2023) e descontinuou o relatório de carteira
de crédito por nível de risco (níveis AA–H), substituído por um modelo de perda
esperada (Resolução CMN 4.966/2021, equivalente ao IFRS 9).

São **regimes contábeis não comparáveis**: os números de conta mudam e a definição de
inadimplência muda de critério discreto (AA–H) para probabilidade de perda esperada.
Misturá-los no mesmo painel criaria uma quebra estrutural indistinguível de variação
econômica real.

A extensão para 2025+ será avaliada depois, como painel separado.

### Por que o período começa em 2014T1

O conceito de conglomerado prudencial, nos moldes da Resolução CMN 4.950/2021, só está
disponível de forma consistente no IF.data a partir desse trimestre.

Para estender à série histórica completa (desde 2000T1), basta alterar `ANO_INICIO = 2000`
no topo do script — o volume de download fica aproximadamente 3× maior.

---

## 3. Decisões de arquitetura

### 3.1 Sem dependências externas

O script usa **exclusivamente a biblioteca padrão do Python**: `urllib.request`, `json`,
`sqlite3`, `csv`, `ssl`. Nada de `requests`, `pandas` ou `openpyxl`.

Motivo: a extração foi planejada para rodar em máquina corporativa onde o `pip` aponta
para um repositório interno (Artifactory) que pode estar inacessível fora da VPN. Como
a internet pública estava liberada mas o repositório interno não, depender de `pip`
inviabilizaria a execução.

### 3.2 Incremental e retomável

Uma tabela `controle` registra cada combinação `(perímetro, trimestre, relatório)`
já processada, com status `ok`, `vazio` ou `erro`.

Ao iniciar, o script consulta essa tabela e monta a lista de tarefas apenas com o que
ainda falta. Isso significa que é seguro interromper com `Ctrl+C` e rodar novamente —
nada é rebaixado.

### 3.3 Modelagem: dicionário + fatos

A API retorna, em **cada linha**, o texto completo da descrição da conta — string que
frequentemente ultrapassa 200 caracteres e se repete milhões de vezes.

A solução foi separar em duas tabelas:

- **`contas`** — dicionário: `num_relatorio`, `conta`, `grupo`, `nome_coluna`,
  `descricao_coluna`. Cada combinação gravada **uma única vez**.
- **`valores`** — fatos: apenas chaves curtas (`tipo_instituicao`, `ano_mes`,
  `num_relatorio`, `cod_inst`, `conta`) e o valor numérico (`saldo`).

Impacto medido em teste com 2 milhões de linhas e textos de tamanho realista:

| | Schema plano | Dicionário + fatos |
|---|---|---|
| Tamanho do arquivo | 640 MB | **87 MB** |
| Tempo de carga | 22 s | **9 s** |

Redução de **7,3×** no tamanho e carga 2,4× mais rápida.

### 3.4 Estratégia de indexação

Os índices são criados **após** a carga completa, não durante — inserir em tabela sem
índice é substancialmente mais rápido.

O índice principal é *covering* para o padrão de consulta dominante na análise:

```sql
CREATE INDEX ix_val_conta ON valores
  (tipo_instituicao, num_relatorio, conta, cod_inst, ano_mes, saldo);
```

Como **todas** as colunas da consulta típica estão no próprio índice, o SQLite responde
sem tocar na tabela de fatos. Desempenho medido (2M linhas):

| Consulta | Sem índice | Com índice | Ganho |
|---|---|---|---|
| Painel de uma conta, todos os bancos | 155 ms | 0,1 ms | ~1.900× |
| Multi-conta (o que o modelo consome) | 131 ms | 0,03 ms | ~2.800× |
| Série temporal de um banco | 156 ms | 0,3 ms | ~500× |
| Corte transversal de um trimestre | 141 ms | 30 ms | ~5× |

Índices secundários: `ix_val_inst` (busca por banco) e `ix_val_periodo` (corte
transversal). Ao final roda `ANALYZE`, para o otimizador ter estatísticas atualizadas.

### 3.5 Tratamento de rede

- **Retry** com backoff progressivo (3 tentativas por chamada)
- **Fallback de encoding**: se a requisição retornar HTTP 400, refaz trocando `$format`
  por `%24format` — alguns gateways corporativos rejeitam o caractere `$` literal na
  query string
- **Contexto SSL tolerante**: redes com inspeção TLS substituem o certificado do
  servidor, o que quebraria a validação padrão
- **Pausa de 0,25 s** entre chamadas, para não sobrecarregar o serviço público
- Falhas são registradas com status `erro` na tabela `controle` e podem ser
  reprocessadas em execução posterior

---

## 4. Como executar

```bash
python baixar_base_bacen.py
```

Não requer `pip install`, ambiente virtual ou qualquer configuração prévia.

### Comandos auxiliares

| Comando | Função |
|---|---|
| `python baixar_base_bacen.py` | Executa a extração (retoma se já houver progresso) |
| `python baixar_base_bacen.py --status` | Mostra o progresso sem baixar nada |
| `python baixar_base_bacen.py --indices` | Recria índices e a view `v_dados` |
| `python baixar_base_bacen.py --exportar` | Exporta CSVs a partir do que já foi baixado |

### Se a rede exigir proxy

```powershell
# PowerShell
$env:HTTPS_PROXY="http://usuario:senha@proxy:porta"
```
```cmd
:: CMD
set HTTPS_PROXY=http://usuario:senha@proxy:porta
```

### Expectativa de execução

- Aproximadamente **2.100 chamadas** (3 perímetros × 44 trimestres × ~16 relatórios)
- **20 a 30 minutos**
- Arquivo final em torno de **300 MB** com índices
- O progresso é exibido com percentual e ETA

---

## 5. Estrutura da base

### `relatorios`
| Coluna | Descrição |
|---|---|
| `numero` | Número do relatório (chave primária) |
| `nome` | Nome descritivo |

### `contas` — dicionário de contas
| Coluna | Descrição |
|---|---|
| `num_relatorio`, `conta` | Chave primária composta |
| `grupo` | Agrupamento dentro do relatório |
| `nome_coluna` | Nome curto da conta |
| `descricao_coluna` | Descrição completa |

### `cadastro` — cadastro de instituições por trimestre
| Coluna | Descrição |
|---|---|
| `ano_mes`, `cod_inst` | Chave primária composta |
| `nome_instituicao` | Nome da instituição |
| `td` | Tipo de consolidação: `I` = independente, `C` = conglomerado |
| `tc` | Controle: `1` público, `2` privado nacional, `3` privado estrangeiro |
| `sr` | Segmento pela Res. CMN 4.553/2017: `S1` a `S5` |
| `tcb` | Tipo de consolidado bancário: `B1` banco comercial/múltiplo com carteira comercial, `B2` banco múltiplo sem carteira comercial, `B3S`/`B3C` cooperativas, `B4` banco de desenvolvimento, `N1`/`n2` não bancários, `N4` instituição de pagamento |
| `segmento_tb`, `atividade`, `uf`, `municipio` | Classificação e localização |
| `cod_cong_financeiro`, `cod_cong_prudencial` | Códigos de conglomerado |
| `data_inicio_atividade` | Data de início |

### `valores` — tabela de fatos
| Coluna | Descrição |
|---|---|
| `tipo_instituicao` | Perímetro (ver seção 6) |
| `ano_mes` | Trimestre no formato `AAAAMM` |
| `num_relatorio` | Relatório de origem |
| `cod_inst` | Código da instituição ou conglomerado |
| `conta` | Código da conta (liga a `contas`) |
| `saldo` | **Valor em reais** (não em milhares) |

### `controle` — rastreamento da extração
| Coluna | Descrição |
|---|---|
| `tipo_instituicao`, `ano_mes`, `num_relatorio` | Chave primária composta |
| `linhas` | Número de registros obtidos |
| `status` | `ok`, `vazio` ou `erro` |
| `baixado_em` | Timestamp |

### `v_dados` — view de conveniência

Junta `valores` + `contas` + `relatorios`, entregando os textos descritivos já
resolvidos. Permite consultar sem escrever `JOIN`:

```sql
SELECT * FROM v_dados
 WHERE tipo_instituicao = 2
   AND nome_coluna LIKE '%Ativo Total%';
```

---

## 6. O parâmetro `tipo_instituicao`

O IF.data disponibiliza três formas de consolidação. **A documentação oficial do Bacen
não publica explicitamente qual valor inteiro corresponde a qual perímetro.**

Em extração anterior, o mapeamento foi determinado empiricamente para o Itaú Unibanco
em `202406`, comparando o Ativo Total retornado com o balanço público do banco:

| Valor | `CodInst` retornado | Ativo Total | Interpretação |
|---|---|---|---|
| `1` | `C0080099` (ITAU - PRUDENCIAL) | R$ 2.636.882.506.064,81 | Conglomerado Prudencial |
| `2` | `C0010069` (ITAU) | R$ 2.668.446.292.041,96 | Conglomerado Financeiro |
| `3` | `60701190` (ITAÚ UNIBANCO S.A.) | R$ 2.018.816.941.214,72 | Instituição individual |

O script baixa os três, então o mapeamento pode ser reconferido diretamente na base.
O estudo atual usa **`tipo_instituicao = 2`** (Conglomerado Financeiro).

---

## 7. Armadilhas conhecidas

Pontos identificados em extrações anteriores que devem ser observados por quem for
analisar a base.

### 7.1 Filtrar o perímetro é obrigatório

Uma consulta sem filtro de `tipo_instituicao` retorna o **mesmo grupo econômico três
vezes**. Em teste anterior, o filtro apenas por segmento `S1` trouxe 33 registros,
quando o segmento tem apenas 6 conglomerados — porque incluía, para o mesmo grupo:

- o conglomerado financeiro (ex.: `BRADESCO`)
- o conglomerado prudencial (ex.: `BRADESCO - PRUDENCIAL`)
- diversos CNPJs individuais (Bradesco S.A., Bradescard, Bradesco BBI, Bradesco Berj,
  Bradesco Cartões, Bradesco Financiamentos, Banco Alvorada...)

Em um modelo DEA isso é fatal: o mesmo banco competiria contra si próprio na fronteira.

**Filtro recomendado** para conglomerados financeiros:

```sql
SELECT * FROM cadastro
 WHERE td = 'C'
   AND nome_instituicao NOT LIKE '%PRUDENCIAL%';
```

### 7.2 O campo `sr` (segmento) não existe antes de 2017

A segmentação S1–S5 foi instituída pela Resolução CMN 4.553/2017. Em trimestres
anteriores o campo vem vazio.

Consequência prática: a seleção da amostra deve ser feita **uma vez**, em uma data-base
recente (por exemplo `202412`), e os `cod_inst` resultantes aplicados a toda a janela
histórica.

### 7.3 SCR e Cosif não são equivalentes

O relatório de carteira de crédito por nível de risco (níveis AA–H) provém do **SCR —
Sistema de Informações de Crédito** (documento CADOC 3040), enquanto os relatórios
contábeis (Resumo, Ativo, Passivo, DRE) provêm do **Cosif** (CADOC 4010/4016).

São sistemas regulatórios distintos, com critérios de consolidação e temporalidade
diferentes. Para o Itaú em `202412`, a diferença entre o "Total Geral" do SCR e a
"Carteira de Crédito Classificada" do Cosif chega a **cerca de 50%**.

**Nunca componha uma mesma variável misturando as duas fontes.** No modelo atual, tanto
o crédito performado (AA+A+B+C) quanto o inadimplente (D+E+F+G+H) vêm exclusivamente do
relatório de nível de risco.

### 7.4 O SCR não classifica a carteira no exterior

O relatório de nível de risco classifica apenas a **carteira doméstica**. Operações no
exterior aparecem como um bloco único (`Total Exterior`), sem quebra por rating — porque
seguem regras de classificação do país hospedeiro, não a Resolução CMN 2.682/1999.

A materialidade não é desprezível: para Itaú e BTG Pactual, a carteira externa chega a
representar entre 22% e 46% do total em determinados trimestres.

### 7.5 Convenção de sinal das despesas

No Cosif, contas de despesa (pessoal, administrativas, PCLD) são registradas com
**sinal negativo**. Modelos DEA tratam inputs como quantidades positivas de recurso
consumido — o sinal precisa ser convertido para valor absoluto quando a conta for usada
como input.

Atenção: isso vale para *inputs*. Variáveis usadas como *carryover* (lucro líquido do
período anterior, por exemplo) devem **preservar o sinal original**, inclusive quando
negativo — é exatamente esse caso que a formulação de Bansal & Mehra (2022) foi
desenhada para tratar.

### 7.6 Trimestres sem dado

O relatório de nível de risco costuma retornar vazio em `201403` para todos os bancos.
Isso é ausência real na fonte, não falha de extração, e está registrado na tabela
`controle` com status `vazio`.

### 7.7 Unidade monetária

Os saldos estão em **reais**, não em milhares de reais. Verificação: o Ativo Total do
Itaú em `202406` é da ordem de 2,6 × 10¹².

---

## 8. Consultas de exemplo

### Selecionar conglomerados financeiros dos segmentos S1–S3, bancos comerciais

```sql
SELECT DISTINCT cod_inst, nome_instituicao, sr
  FROM cadastro
 WHERE ano_mes = '202412'
   AND sr IN ('S1','S2','S3')
   AND tcb = 'B1'
   AND td = 'C'
   AND nome_instituicao NOT LIKE '%PRUDENCIAL%'
 ORDER BY sr, nome_instituicao;
```

### Montar painel de uma conta específica

```sql
SELECT cod_inst, ano_mes, saldo
  FROM valores
 WHERE tipo_instituicao = 2
   AND num_relatorio = '1'
   AND conta = '78182'          -- Ativo Total
 ORDER BY cod_inst, ano_mes;
```

### Descobrir o código de uma conta pelo nome

```sql
SELECT num_relatorio, conta, nome_coluna, descricao_coluna
  FROM contas
 WHERE nome_coluna LIKE '%Depósito%';
```

### Painel com várias contas de uma vez

```sql
SELECT cod_inst, ano_mes, conta, saldo
  FROM valores
 WHERE tipo_instituicao = 2
   AND num_relatorio = '4'
   AND conta IN ('78218','78219','78213','78215')
 ORDER BY cod_inst, ano_mes, conta;
```

### Verificar cobertura temporal por instituição

```sql
SELECT cod_inst,
       COUNT(DISTINCT ano_mes) AS trimestres,
       MIN(ano_mes) AS primeiro,
       MAX(ano_mes) AS ultimo
  FROM valores
 WHERE tipo_instituicao = 2 AND num_relatorio = '1' AND conta = '78182'
 GROUP BY cod_inst
 ORDER BY trimestres DESC;
```

---

## 9. Contas de referência (regime Cosif pré-2025)

Contas já validadas em extrações anteriores, úteis como ponto de partida. A base contém
**todas** as contas — estas são apenas as usadas até agora.

**Relatório 1 — Resumo**

| Conta | Variável |
|---|---|
| `78182` | Ativo Total |
| `78183` | Carteira de Crédito Classificada |
| `78185` | Captações |
| `78186` | Patrimônio Líquido |
| `78187` | Lucro Líquido |

**Relatório 2 — Ativo**

| Conta | Variável |
|---|---|
| `78190` | TVM e Instrumentos Financeiros Derivativos |
| `78191` | Operações de Crédito |
| `78193` | Operações de Crédito Líquidas de Provisão |

**Relatório 3 — Passivo**

| Conta | Variável |
|---|---|
| `78282` | Depósitos à Vista |
| `78283` | Depósitos Poupança |
| `78284` | Depósitos Interfinanceiros |
| `78286` | Depósitos a Prazo |
| `78287` | Depósito Total |

**Relatório 4 — Demonstração de Resultado**

| Conta | Variável |
|---|---|
| `78203` | Rendas de Operações de Crédito |
| `78213` | Resultado de Provisão para Créditos de Difícil Liquidação (PCLD) |
| `78215` | Resultado de Intermediação Financeira |
| `78216` | Rendas de Prestação de Serviços |
| `78217` | Rendas de Tarifas Bancárias |
| `78218` | Despesas de Pessoal |
| `78219` | Despesas Administrativas |

**Relatório 8 — Carteira de crédito ativa por nível de risco**

Filtrar pela coluna `nome_coluna`, que assume os valores `AA`, `A`, `B`, `C`, `D`, `E`,
`F`, `G`, `H`, além de `Total Exterior` e `Total Geral`.

---

## 10. Entregável

Ao final da execução:

- **`base_dados/base_dados.db`** — banco SQLite completo, indexado (~300 MB)
- **`csv_export/`** — mesmos dados em CSV, com `valores` separado por perímetro

O arquivo `.db` é o entregável principal. Os CSVs servem para inspeção manual ou para
ferramentas que não leem SQLite.

Recomenda-se anexar também a saída de `--status`, que documenta a cobertura obtida e
eventuais falhas.
