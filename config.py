# ============================================================
# FII INSTITUTIONAL SCANNER
# config.py
# ============================================================
#
# Configurações centrais do modelo.
#
# Toda regra estrutural do scanner deve ficar aqui.
# Os engines importam estes parâmetros.
#
# ============================================================


# ============================================================
# 1. DIRETÓRIOS
# ============================================================

DATA_DIR = "data"
REPORTS_DIR = "reports"

UNIVERSE_FILE = "data/universe.csv"
RANKING_FILE = "data/ranking.csv"
PORTFOLIO_FILE = "data/portfolio.csv"
REPORT_FILE = "reports/fii_report.pdf"


# ============================================================
# 2. DADOS DE MERCADO
# ============================================================

# Histórico utilizado para indicadores, risco e validação
PRICE_HISTORY = "5y"

# Yahoo Finance
YAHOO_REPAIR = True
YAHOO_AUTO_ADJUST = True

# Número mínimo de observações para aceitar uma série
MIN_PRICE_OBSERVATIONS = 252

# Liquidez média mínima diária
MIN_LIQUIDITY = 100_000

# Janela para cálculo da liquidez média
LIQUIDITY_WINDOW = 60


# ============================================================
# 3. REGRA ZERO
# ============================================================

# FII precisa possuir dados mínimos antes de entrar
# nos motores seguintes.

RULE_ZERO_MIN_HISTORY = 252

RULE_ZERO_REQUIRE_PRICE = True
RULE_ZERO_REQUIRE_LIQUIDITY = True
RULE_ZERO_REQUIRE_CATEGORY = True


# ============================================================
# 4. MOTOR FUNDAMENTALISTA
# ============================================================

# Gate mínimo para o FII seguir para análise técnica.

FUNDAMENTAL_GATE = 70.0


# ------------------------------------------------------------
# Classificação fundamental
# ------------------------------------------------------------

FUNDAMENTAL_ELITE = 90.0
FUNDAMENTAL_PREMIUM = 82.0
FUNDAMENTAL_VERY_STRONG = 76.0
FUNDAMENTAL_APPROVED = 70.0


# ------------------------------------------------------------
# Confiança mínima dos dados
# ------------------------------------------------------------

MIN_DATA_CONFIDENCE = 0.90


# ============================================================
# 5. SCORE INSTITUCIONAL
# ============================================================

# Modelo validado:
#
# 80% fundamentos
# 20% técnico

FUNDAMENTAL_WEIGHT = 0.80
TECHNICAL_WEIGHT = 0.20


# ------------------------------------------------------------
# Classificação institucional
# ------------------------------------------------------------

INSTITUTIONAL_ELITE = 90.0
INSTITUTIONAL_PREMIUM = 85.0
INSTITUTIONAL_VERY_STRONG = 80.0
INSTITUTIONAL_APPROVED = 70.0


# ============================================================
# 6. MOTOR TÉCNICO
# ============================================================

RSI_WINDOW = 14

SMA_SHORT = 20
SMA_MEDIUM = 50
SMA_LONG = 200

VOLUME_WINDOW = 20

RETURN_1M_DAYS = 21
RETURN_3M_DAYS = 63
RETURN_6M_DAYS = 126

HIGH_52W_WINDOW = 252


# ------------------------------------------------------------
# Gates técnicos
# ------------------------------------------------------------

TECHNICAL_STRONG = 80.0
TECHNICAL_ACCEPTABLE = 65.0

# RSI excessivamente elevado
RSI_OVERBOUGHT = 70.0

# Evitar ativo excessivamente distante da média longa
MAX_DISTANCE_SMA200 = 0.20


# ============================================================
# 7. CONSTRUÇÃO DA CARTEIRA
# ============================================================

# Número alvo de FIIs
PORTFOLIO_SIZE = 10


# ------------------------------------------------------------
# Limites individuais
# ------------------------------------------------------------

MIN_WEIGHT = 0.05

# O estudo walk-forward + stress test mostrou que 15%
# oferece melhor compromisso entre risco e diversificação.
MAX_WEIGHT = 0.15


# ============================================================
# 8. LIMITES POR CATEGORIA
# ============================================================

# PAPEL

MIN_PAPER = 0.25
MAX_PAPER = 0.45


# TIJOLO

MIN_BRICK = 0.35
MAX_BRICK = 0.50


# ALTERNATIVOS

MAX_ALTERNATIVE = 0.20


# ============================================================
# 9. LIMITES POR SEGMENTO
# ============================================================

MAX_HIGH_YIELD = 0.10

MAX_LOGISTICS = 0.30

MAX_SHOPPING = 0.25

MAX_URBAN_INCOME = 0.20

MAX_OFFICES = 0.15


# ============================================================
# 10. MOTOR DE RISCO
# ============================================================

# Janela principal validada no walk-forward
RISK_WINDOW = 252

# Janela de teste / rebalanceamento
REBALANCE_WINDOW = 63

# Anualização
TRADING_DAYS = 252


# ------------------------------------------------------------
# Tratamento de eventos extremos
# ------------------------------------------------------------

# Eventos anormais de preço NÃO devem ser apagados
# da base fundamental/técnica.
#
# Este limite é utilizado exclusivamente na matriz
# robusta de risco.

RISK_RETURN_CAP = 0.12


# ------------------------------------------------------------
# Covariância
# ------------------------------------------------------------

USE_LEDOIT_WOLF = True


# ============================================================
# 11. OTIMIZAÇÃO
# ============================================================

# Penalização de concentração.
# Configuração aprovada no Stress Test Light.

HHI_PENALTY = 0.0005


# ------------------------------------------------------------
# Restrições de qualidade
# ------------------------------------------------------------

# Quanto o otimizador pode deteriorar o score médio
# em relação à carteira institucional inicial.

MAX_FUNDAMENTAL_SCORE_LOSS = 1.50

MAX_INSTITUTIONAL_SCORE_LOSS = 1.50


# ============================================================
# 12. VALIDAÇÃO WALK-FORWARD
# ============================================================

WALK_FORWARD_TRAIN = 252

WALK_FORWARD_TEST = 63


# Critérios utilizados para considerar
# o otimizador validado.

MIN_WIN_RATE = 0.60

MIN_AVG_VOL_REDUCTION = 0.02

MIN_EFFECTIVE_FIIS = 8.0


# ============================================================
# 13. MATERIALIDADE DA OTIMIZAÇÃO
# ============================================================

# Só utilizar a carteira otimizada quando houver
# benefício material de risco.

MIN_RELATIVE_RISK_IMPROVEMENT = 0.02


# ============================================================
# 14. EXECUÇÃO OPERACIONAL
# ============================================================

# Fração do peso estratégico executada conforme
# qualidade do timing.

EXECUTION_STRONG = 1.00

EXECUTION_APPROVED = 0.60

EXECUTION_TACTICAL = 0.40

EXECUTION_WAIT = 0.00


# ============================================================
# 15. HIGH YIELD
# ============================================================

# High Yield pode entrar na carteira, porém permanece
# limitado estruturalmente.

HIGH_YIELD_MAX_WEIGHT = 0.10

HIGH_YIELD_EXECUTION_FRACTION = 0.40


# ============================================================
# 16. SANIDADE DOS DADOS
# ============================================================

# Retorno diário acima deste valor gera alerta de auditoria.

EXTREME_RETURN_ALERT = 0.15

# Não remover automaticamente o evento da série original.
REMOVE_EXTREME_RETURNS = False


# ============================================================
# 17. OUTPUT
# ============================================================

SAVE_UNIVERSE = True
SAVE_RANKING = True
SAVE_PORTFOLIO = True
GENERATE_PDF = True


# ============================================================
# 18. DISPLAY
# ============================================================

DECIMAL_PLACES = 2

SHOW_TOP_RANKING = 15


# ============================================================
# 19. IDENTIFICAÇÃO DO MODELO
# ============================================================

MODEL_NAME = "FII INSTITUTIONAL SCANNER"

MODEL_VERSION = "1.0"

MODEL_DESCRIPTION = (
    "Modelo quantitativo para seleção, ranking, "
    "timing e construção de carteira de FIIs."
)
