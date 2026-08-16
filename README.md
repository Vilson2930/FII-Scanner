# FII Institutional Scanner

Sistema quantitativo para análise, seleção, ranking e construção de carteira de Fundos de Investimento Imobiliário (FIIs).

O projeto combina análise fundamentalista, análise técnica, controle de risco e otimização de portfólio para produzir uma carteira estratégica e uma carteira executável de acordo com o momento de mercado.

---

## Objetivo

O FII Institutional Scanner foi desenvolvido para responder a quatro perguntas principais:

1. Quais FIIs apresentam fundamentos suficientemente fortes?
2. Entre os FIIs aprovados, quais apresentam melhor momento técnico?
3. Qual combinação oferece uma carteira diversificada e eficiente?
4. Quanto da carteira estratégica deve ser executado no momento atual?

O sistema separa:

- qualidade do ativo;
- momento de entrada;
- construção da carteira;
- decisão operacional.

---

## Arquitetura

O projeto utiliza uma estrutura enxuta:

```text
FII_INSTITUTIONAL_SCANNER/
│
├── main.py
├── config.py
├── requirements.txt
├── README.md
│
├── engine/
│   ├── data_engine.py
│   ├── fundamental_engine.py
│   ├── technical_engine.py
│   ├── portfolio_engine.py
│   └── report_engine.py
│
├── data/
│   ├── universe.csv
│   ├── ranking.csv
│   └── portfolio.csv
│
├── reports/
│   └── fii_report.pdf
│
└── .github/
    └── workflows/
        └── scanner.yml
```

---

## Pipeline

O scanner executa cinco etapas principais:

```text
DADOS
  ↓
FUNDAMENTOS
  ↓
TÉCNICO
  ↓
SCORE INSTITUCIONAL
  ↓
PORTFÓLIO E RISCO
  ↓
RELATÓRIO
```

### 1. Data Engine

Responsável por:

- universo de FIIs;
- coleta de dados;
- histórico de preços;
- liquidez;
- saneamento;
- classificação dos fundos;
- Regra Zero;
- preparação da base utilizada pelos motores seguintes.

### 2. Fundamental Engine

Avalia os FIIs de acordo com sua natureza.

Os fundos são tratados por motores específicos para categorias como:

- Papel;
- Tijolo;
- Alternativos.

Entre as informações avaliadas estão:

- dividendos;
- estabilidade da renda;
- crescimento da renda;
- P/VP;
- estrutura patrimonial;
- passivos;
- composição dos ativos;
- robustez;
- risco;
- penalidades especiais.

O resultado é o:

```text
Fundamental Score
```

Somente fundos que atendem aos critérios mínimos seguem para as etapas posteriores.

---

## Fundamental Gate

O filtro mínimo do modelo é:

```text
Fundamental Score >= 70
```

O objetivo é impedir que um bom momento de mercado compense fundamentos insuficientes.

---

## Technical Engine

O motor técnico é utilizado principalmente para determinar o momento de entrada.

Entre os indicadores utilizados estão:

- RSI 14;
- SMA 20;
- SMA 50;
- SMA 200;
- retorno de 1 mês;
- retorno de 3 meses;
- retorno de 6 meses;
- distância das médias;
- posição em relação à máxima de 52 semanas;
- volume relativo;
- tendência.

O resultado é o:

```text
Technical Score
```

---

## Institutional Score

O modelo combina fundamentos e momento técnico.

A ponderação estrutural é:

```text
80% Fundamental Score
20% Technical Score
```

Conceitualmente:

```text
Institutional Score =
0.80 × Fundamental Score
+
0.20 × Technical Score
```

Os fundamentos permanecem como componente dominante do processo.

---

## Construção da carteira

A carteira estratégica busca aproximadamente:

```text
10 FIIs
```

Limites principais:

```text
Peso mínimo por fundo: 5%
Peso máximo por fundo: 15%
```

Também existem restrições de concentração por categoria e segmento.

Exemplos:

```text
Papel       <= 45%
Tijolo      <= 50%
High Yield  <= 10%
Logística   <= 30%
```

Os limites completos estão centralizados em:

```text
config.py
```

---

## Controle de risco

O sistema utiliza uma matriz robusta de risco.

A janela principal é:

```text
252 pregões
```

O processo pode utilizar:

```text
Ledoit-Wolf Shrinkage
```

para melhorar a estabilidade da matriz de covariância.

Eventos extremos suspeitos de preço são auditados separadamente.

O tratamento de outliers utilizado para estimativa de risco não altera automaticamente a série original utilizada pelos demais motores.

---

## Otimização

A otimização busca reduzir o risco da carteira sem deteriorar excessivamente sua qualidade fundamental e institucional.

O modelo também controla concentração através do HHI.

Configuração principal:

```text
HHI Penalty = 0.0005
```

A otimização deve respeitar:

- limites individuais;
- limites por categoria;
- limites por segmento;
- qualidade fundamental;
- qualidade institucional;
- diversificação.

---

## Walk-Forward

A metodologia de otimização foi submetida a validação walk-forward.

Configuração:

```text
Treino: 252 pregões
Teste:   63 pregões
```

O objetivo é avaliar o comportamento do método fora da amostra utilizada para estimar os pesos.

Também são observados:

- taxa de vitória;
- redução de volatilidade;
- drawdown;
- número efetivo de FIIs;
- estabilidade dos pesos;
- turnover.

---

## Limite individual

Foram avaliados diferentes tetos de concentração.

O modelo operacional utiliza:

```text
15%
```

como limite máximo por FII.

O objetivo é preservar o equilíbrio entre eficiência de risco e diversificação.

---

## Carteira estratégica × carteira executável

O sistema diferencia duas decisões.

### Carteira estratégica

Representa os pesos desejados de longo prazo segundo:

- fundamentos;
- diversificação;
- risco;
- otimização.

### Carteira executável

Representa quanto do peso estratégico pode ser implementado de acordo com o momento técnico.

Exemplos de decisões:

```text
COMPRAR AGORA
COMPRAR PARCIAL
ENTRADA MENOR
RESERVA ESTRATÉGICA
AGUARDAR
```

Portanto, um fundo pode possuir excelente fundamento e fazer parte da carteira estratégica, mas permanecer aguardando um melhor gatilho técnico.

---

## Arquivos gerados

### `data/universe.csv`

Base consolidada utilizada pelo scanner.

### `data/ranking.csv`

Ranking dos FIIs contendo informações como:

```text
ticker
categoria
segmento
fundamental_score
technical_score
institutional_score
status_fundamental
status_timing
decisao_operacional
ranking
```

### `data/portfolio.csv`

Carteira final contendo informações como:

```text
ticker
categoria
segmento
peso_estrategico
peso_executavel
peso_reservado
institutional_score
status_final
```

### `reports/fii_report.pdf`

Relatório executivo da execução do scanner.

---

## Execução

Instale as dependências:

```bash
pip install -r requirements.txt
```

Execute:

```bash
python main.py
```

---

## Automação

O projeto poderá ser executado automaticamente através do GitHub Actions.

Workflow:

```text
.github/workflows/scanner.yml
```

Também será possível executar o scanner manualmente através de:

```text
workflow_dispatch
```

---

## Princípio do modelo

O scanner segue a sequência:

```text
QUALIDADE
    ↓
PREÇO / VALUATION
    ↓
TIMING
    ↓
RISCO
    ↓
PORTFÓLIO
    ↓
EXECUÇÃO
```

Um ativo não deve entrar na carteira apenas porque caiu de preço ou apresenta elevado Dividend Yield.

Primeiro deve demonstrar qualidade fundamental suficiente.

Depois são avaliados timing, risco, diversificação e tamanho da posição.

---

## Aviso

Este projeto é uma ferramenta quantitativa de apoio à análise.

Os resultados produzidos pelo sistema não constituem recomendação individual de investimento e não eliminam a necessidade de análise dos riscos específicos de cada fundo.

Dados de mercado e informações provenientes de fontes externas podem conter atrasos, inconsistências, eventos corporativos ou erros de ajuste.

Por esse motivo, o sistema possui mecanismos de auditoria e saneamento antes da construção da carteira.

---

## Versão

```text
FII Institutional Scanner
Version 1.0
```
