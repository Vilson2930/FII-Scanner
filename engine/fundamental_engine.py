# ============================================================
# FII INSTITUTIONAL SCANNER
# engine/fundamental_engine.py
# ============================================================
#
# MOTOR FUNDAMENTALISTA ENXUTO
#
# Fluxo:
#
# 1. Enriquece dados comuns
# 2. Calcula renda/dividendos
# 3. Recupera valuation quando disponível
# 4. Aplica motor específico:
#       PAPEL
#       TIJOLO
#       ALTERNATIVO
# 5. Aplica penalidades
# 6. Consolida FUNDAMENTAL MASTER
#
# ============================================================

import warnings

import numpy as np
import pandas as pd
import yfinance as yf
from tqdm import tqdm

from config import (
    FUNDAMENTAL_GATE,
    FUNDAMENTAL_ELITE,
    FUNDAMENTAL_PREMIUM,
    FUNDAMENTAL_VERY_STRONG,
    FUNDAMENTAL_APPROVED,
    MIN_DATA_CONFIDENCE,
)

warnings.filterwarnings("ignore")


# ============================================================
# ATIVOS COM MOTOR PRÓPRIO
# ============================================================
#
# Estes ativos NÃO competem diretamente no motor comum.
# No estudo original, SNEL11 foi classificado como
# "MOTOR ESPECIAL NECESSÁRIO".
#
SPECIAL_MOTOR_TICKERS = {
    "SNEL11",
}


# ============================================================
# 1. FUNÇÕES BÁSICAS
# ============================================================

def clip_score(value):

    if pd.isna(value):
        return np.nan

    return float(
        np.clip(
            value,
            0,
            100
        )
    )


def safe_float(value, default=np.nan):

    try:

        value = float(value)

        if np.isfinite(value):
            return value

    except (TypeError, ValueError):
        pass

    return default


# ============================================================
# 2. COLETA DE DIVIDENDOS
# ============================================================

def _collect_dividend_data(ticker):

    result = {

        "ticker": ticker,

        "dividendos_12m": np.nan,

        "dy_12m": np.nan,

        "meses_pagamento_12m": 0,

        "estabilidade_dividendos": np.nan,

        "crescimento_dividendos": np.nan,

        "pvp": np.nan,

        "market_cap": np.nan,

        "cotistas_proxy": np.nan,
    }

    symbol = f"{ticker}.SA"

    try:

        tk = yf.Ticker(symbol)

        hist = tk.history(
            period="3y",
            auto_adjust=False,
            actions=True,
            repair=True,
        )

        if hist is None or hist.empty:

            return result


        # ====================================================
        # PREÇO
        # ====================================================

        close = pd.to_numeric(
            hist["Close"],
            errors="coerce"
        ).dropna()

        if close.empty:
            return result

        preco = float(
            close.iloc[-1]
        )


        # ====================================================
        # DIVIDENDOS
        # ====================================================

        if "Dividends" in hist.columns:

            div = pd.to_numeric(
                hist["Dividends"],
                errors="coerce"
            ).fillna(0)

            hoje = hist.index.max()

            if hoje.tzinfo is not None:
                hoje = hoje.tz_localize(None)

            div.index = pd.to_datetime(
                div.index
            )

            try:
                div.index = div.index.tz_localize(None)
            except Exception:
                pass

            inicio_12m = (
                hoje
                -
                pd.DateOffset(
                    months=12
                )
            )

            inicio_24m = (
                hoje
                -
                pd.DateOffset(
                    months=24
                )
            )


            div_12m = div[
                div.index >= inicio_12m
            ]

            div_prev = div[
                (div.index >= inicio_24m)
                &
                (div.index < inicio_12m)
            ]


            soma_12m = float(
                div_12m.sum()
            )

            soma_prev = float(
                div_prev.sum()
            )


            result[
                "dividendos_12m"
            ] = soma_12m


            if preco > 0:

                result[
                    "dy_12m"
                ] = (
                    soma_12m
                    /
                    preco
                )


            # =================================================
            # MESES COM PAGAMENTO
            # =================================================

            div_pos = div_12m[
                div_12m > 0
            ]

            if not div_pos.empty:

                meses = (
                    div_pos
                    .groupby(
                        div_pos.index.to_period("M")
                    )
                    .sum()
                )

                result[
                    "meses_pagamento_12m"
                ] = len(meses)


                # =============================================
                # ESTABILIDADE
                # =============================================

                if len(meses) >= 3:

                    media = (
                        meses.mean()
                    )

                    desvio = (
                        meses.std()
                    )

                    if media > 0:

                        cv = (
                            desvio
                            /
                            media
                        )

                        estabilidade = (
                            100
                            -
                            cv * 100
                        )

                        result[
                            "estabilidade_dividendos"
                        ] = clip_score(
                            estabilidade
                        )


            # =================================================
            # CRESCIMENTO
            # =================================================

            if soma_prev > 0:

                crescimento = (

                    soma_12m
                    /
                    soma_prev

                    - 1

                )

                result[
                    "crescimento_dividendos"
                ] = crescimento


        # ====================================================
        # INFO / VALUATION
        # ====================================================

        try:

            info = tk.info or {}

            pvp = (
                info.get(
                    "priceToBook"
                )
            )

            result["pvp"] = safe_float(
                pvp
            )

            result[
                "market_cap"
            ] = safe_float(
                info.get(
                    "marketCap"
                )
            )

        except Exception:
            pass


    except Exception:
        pass


    return result


# ============================================================
# 3. ENRIQUECIMENTO
# ============================================================

def _enrich_fundamentals(database):

    tickers = (
        database[
            "ticker"
        ]
        .tolist()
    )

    records = []


    for ticker in tqdm(
        tickers,
        desc="Fundamentos"
    ):

        records.append(
            _collect_dividend_data(
                ticker
            )
        )


    extras = pd.DataFrame(
        records
    )


    base = database.merge(

        extras,

        on="ticker",

        how="left"

    )

    # ========================================================
    # INTEGRAÇÃO DO VALUATION DO DATA ENGINE
    # ========================================================
    #
    # Prioridade:
    # 1) P/VP obtido nesta etapa pelo Yahoo;
    # 2) P/VP já validado/coletado no Data Engine
    #    (Yahoo ou CVM oficial);
    # 3) permanece NaN.
    #
    if "pvp_data" in base.columns:

        pvp_local = pd.to_numeric(
            base[
                "pvp"
            ],
            errors="coerce"
        )

        pvp_data_engine = pd.to_numeric(
            base[
                "pvp_data"
            ],
            errors="coerce"
        )

        base[
            "pvp"
        ] = pvp_local.fillna(
            pvp_data_engine
        )

    # Também preservamos a origem do valuation para auditoria.
    if "fonte_valuation" not in base.columns:

        base[
            "fonte_valuation"
        ] = np.nan

    base[
        "fonte_valuation_final"
    ] = np.where(
        pd.to_numeric(
            extras.set_index(
                "ticker"
            )[
                "pvp"
            ].reindex(
                base[
                    "ticker"
                ]
            ).reset_index(
                drop=True
            ),
            errors="coerce"
        ).notna(),
        "YAHOO_FUNDAMENTAL",
        base[
            "fonte_valuation"
        ].fillna(
            "SEM_DADO"
        )
    )


    return base


# ============================================================
# 4. PILAR RENDA
# ============================================================

def _score_income(row):

    dy = row.get(
        "dy_12m",
        np.nan
    )

    estabilidade = row.get(
        "estabilidade_dividendos",
        np.nan
    )

    crescimento = row.get(
        "crescimento_dividendos",
        np.nan
    )

    meses = row.get(
        "meses_pagamento_12m",
        0
    )


    # --------------------------------------------------------
    # DY
    # --------------------------------------------------------

    if pd.isna(dy):

        score_dy = 40

    elif dy >= 0.12:

        score_dy = 100

    elif dy >= 0.10:

        score_dy = 90

    elif dy >= 0.08:

        score_dy = 75

    elif dy >= 0.06:

        score_dy = 60

    else:

        score_dy = 40


    # --------------------------------------------------------
    # ESTABILIDADE
    # --------------------------------------------------------

    score_est = (

        estabilidade
        if not pd.isna(estabilidade)
        else 50

    )


    # --------------------------------------------------------
    # CRESCIMENTO
    # --------------------------------------------------------

    if pd.isna(crescimento):

        score_growth = 50

    elif crescimento >= 0.10:

        score_growth = 100

    elif crescimento >= 0:

        score_growth = 80

    elif crescimento >= -0.10:

        score_growth = 60

    elif crescimento >= -0.20:

        score_growth = 40

    else:

        score_growth = 20


    # --------------------------------------------------------
    # FREQUÊNCIA
    # --------------------------------------------------------

    score_frequency = min(

        100,

        (
            meses
            /
            12
        )
        *
        100

    )


    score = (

        score_dy * 0.30

        +

        score_est * 0.30

        +

        score_growth * 0.25

        +

        score_frequency * 0.15

    )


    return clip_score(
        score
    )


# ============================================================
# 5. PILAR VALUATION
# ============================================================

def _score_valuation(row):

    pvp = row.get(
        "pvp",
        np.nan
    )


    if pd.isna(pvp):

        # Dado ausente = incerteza.
        # Não premiamos o fundo por uma informação que não temos.
        # O valor 50 é neutro e a ausência também reduz a
        # confiança dos dados e gera penalidade de qualidade.
        return 50


    # --------------------------------------------------------
    # DESCONTOS EXAGERADOS NÃO SÃO TRATADOS COMO EXCELENTES
    # --------------------------------------------------------

    if pvp < 0.40:

        return 20


    if pvp < 0.60:

        return 60


    if pvp <= 0.85:

        return 100


    if pvp <= 1.00:

        return 90


    if pvp <= 1.10:

        return 75


    if pvp <= 1.20:

        return 55


    return 35


# ============================================================
# 6. PILAR RISCO DE MERCADO
# ============================================================

def _score_market_risk(row):

    vol = row.get(
        "volatilidade_anual",
        np.nan
    )

    dd = row.get(
        "drawdown_5a",
        np.nan
    )

    liquidez = row.get(
        "liquidez_media_60d",
        np.nan
    )


    # --------------------------------------------------------
    # VOLATILIDADE
    # --------------------------------------------------------

    if pd.isna(vol):

        score_vol = 50

    elif vol <= 0.10:

        score_vol = 100

    elif vol <= 0.13:

        score_vol = 85

    elif vol <= 0.16:

        score_vol = 70

    elif vol <= 0.20:

        score_vol = 50

    elif vol <= 0.25:

        score_vol = 30

    else:

        score_vol = 10


    # --------------------------------------------------------
    # DRAWDOWN
    # --------------------------------------------------------

    if pd.isna(dd):

        score_dd = 50

    elif dd >= -0.15:

        score_dd = 100

    elif dd >= -0.25:

        score_dd = 80

    elif dd >= -0.35:

        score_dd = 60

    elif dd >= -0.50:

        score_dd = 35

    else:

        score_dd = 10


    # --------------------------------------------------------
    # LIQUIDEZ
    # --------------------------------------------------------

    if pd.isna(liquidez):

        score_liq = 40

    elif liquidez >= 10_000_000:

        score_liq = 100

    elif liquidez >= 5_000_000:

        score_liq = 90

    elif liquidez >= 2_000_000:

        score_liq = 80

    elif liquidez >= 1_000_000:

        score_liq = 70

    elif liquidez >= 300_000:

        score_liq = 55

    else:

        score_liq = 35


    score = (

        score_vol * 0.35

        +

        score_dd * 0.35

        +

        score_liq * 0.30

    )


    return clip_score(
        score
    )


# ============================================================
# 7. PILAR ESTRUTURA
# ============================================================
#
# Nesta versão enxuta utilizamos informações disponíveis na
# camada atual do GitHub.
#
# Quando adicionarmos CVM completa, este pilar poderá utilizar
# diretamente composição patrimonial, passivos e CRIs.
# ============================================================

def _score_structure(row):

    categoria = row.get(
        "categoria_motor"
    )

    segmento = row.get(
        "segmento"
    )

    liquidez = row.get(
        "liquidez_media_60d",
        0
    )


    score = 80


    # --------------------------------------------------------
    # LIQUIDEZ / ESCALA
    # --------------------------------------------------------

    if liquidez >= 10_000_000:

        score += 10

    elif liquidez >= 3_000_000:

        score += 5

    elif liquidez < 500_000:

        score -= 10


    # --------------------------------------------------------
    # HIGH YIELD
    # --------------------------------------------------------

    if segmento == "CRI_HIGH_YIELD":

        score -= 8


    # --------------------------------------------------------
    # DESENVOLVIMENTO
    # --------------------------------------------------------

    if segmento == "DESENVOLVIMENTO":

        score -= 12


    # --------------------------------------------------------
    # FOF
    # --------------------------------------------------------

    if segmento == "FOF":

        score -= 3


    # --------------------------------------------------------
    # DIVERSIFICADO
    # --------------------------------------------------------

    if segmento == "TIJOLO_DIVERSIFICADO":

        score += 5


    return clip_score(
        score
    )


# ============================================================
# 8. PILAR ROBUSTEZ
# ============================================================

def _score_robustness(row):

    estabilidade = row.get(
        "estabilidade_dividendos",
        np.nan
    )

    meses = row.get(
        "meses_pagamento_12m",
        0
    )

    liquidez = row.get(
        "liquidez_media_60d",
        0
    )


    score = 50


    if meses >= 12:

        score += 20

    elif meses >= 10:

        score += 15

    elif meses >= 6:

        score += 5


    if not pd.isna(estabilidade):

        score += (
            estabilidade - 50
        ) * 0.30


    if liquidez >= 5_000_000:

        score += 15

    elif liquidez >= 1_000_000:

        score += 8


    return clip_score(
        score
    )


# ============================================================
# 9. PENALIDADES
# ============================================================

def _calculate_penalties(row):

    penalty = 0.0

    segmento = row.get(
        "segmento"
    )

    dy = row.get(
        "dy_12m",
        np.nan
    )

    pvp = row.get(
        "pvp",
        np.nan
    )

    crescimento = row.get(
        "crescimento_dividendos",
        np.nan
    )

    drawdown = row.get(
        "drawdown_5a",
        np.nan
    )


    # --------------------------------------------------------
    # HIGH YIELD
    # --------------------------------------------------------

    if segmento == "CRI_HIGH_YIELD":

        penalty -= 7.5


    # --------------------------------------------------------
    # DY EXTREMO
    # --------------------------------------------------------

    if (
        not pd.isna(dy)
        and dy > 0.20
    ):

        penalty -= 7.5


    # --------------------------------------------------------
    # DESCONTO EXTREMO
    # --------------------------------------------------------

    if (
        not pd.isna(pvp)
        and pvp < 0.40
    ):

        penalty -= 10


    # --------------------------------------------------------
    # RENDA EM QUEDA
    # --------------------------------------------------------

    if (
        not pd.isna(crescimento)
        and crescimento < -0.20
    ):

        penalty -= 7.5


    # --------------------------------------------------------
    # DRAWDOWN EXTREMO
    # --------------------------------------------------------

    if (
        not pd.isna(drawdown)
        and drawdown < -0.50
    ):

        penalty -= 10


    return penalty


# ============================================================
# 10. RISCO ESPECIAL
# ============================================================

def _special_risk(row):

    flags = 0


    dy = row.get(
        "dy_12m",
        np.nan
    )

    pvp = row.get(
        "pvp",
        np.nan
    )

    crescimento = row.get(
        "crescimento_dividendos",
        np.nan
    )

    dd = row.get(
        "drawdown_5a",
        np.nan
    )


    if (
        not pd.isna(dy)
        and dy > 0.20
    ):

        flags += 1


    if (
        not pd.isna(pvp)
        and pvp < 0.40
    ):

        flags += 1


    if (
        not pd.isna(crescimento)
        and crescimento < -0.20
    ):

        flags += 1


    if (
        not pd.isna(dd)
        and dd < -0.50
    ):

        flags += 1


    return flags


# ============================================================
# 11. SCORE PAPEL
# ============================================================

def _score_paper(row):

    renda = row[
        "pilar_renda"
    ]

    estrutura = row[
        "pilar_estrutura"
    ]

    valuation = row[
        "pilar_valuation"
    ]

    robustez = row[
        "pilar_robustez"
    ]

    risco = row[
        "pilar_risco"
    ]


    # Papel:
    # renda + estrutura possuem maior importância.

    score = (

        renda * 0.25

        +

        estrutura * 0.25

        +

        valuation * 0.20

        +

        robustez * 0.15

        +

        risco * 0.15

    )


    return score


# ============================================================
# 12. SCORE TIJOLO
# ============================================================

def _score_brick(row):

    score = (

        row[
            "pilar_renda"
        ] * 0.25

        +

        row[
            "pilar_estrutura"
        ] * 0.25

        +

        row[
            "pilar_valuation"
        ] * 0.20

        +

        row[
            "pilar_robustez"
        ] * 0.15

        +

        row[
            "pilar_risco"
        ] * 0.15

    )


    return score


# ============================================================
# 13. SCORE ALTERNATIVO
# ============================================================

def _score_alternative(row):

    score = (

        row[
            "pilar_renda"
        ] * 0.22

        +

        row[
            "pilar_estrutura"
        ] * 0.23

        +

        row[
            "pilar_valuation"
        ] * 0.20

        +

        row[
            "pilar_robustez"
        ] * 0.20

        +

        row[
            "pilar_risco"
        ] * 0.15

    )


    return score


# ============================================================
# 14. MOTOR POR CATEGORIA
# ============================================================

def _calculate_base_score(row):

    ticker = row.get(
        "ticker"
    )

    # Ativo especial: não entra no motor comum.
    if ticker in SPECIAL_MOTOR_TICKERS:
        return np.nan

    categoria = row[
        "categoria_motor"
    ]


    if categoria == "PAPEL":

        return _score_paper(
            row
        )


    if categoria == "TIJOLO":

        return _score_brick(
            row
        )


    if categoria == "ALTERNATIVO":

        return _score_alternative(
            row
        )


    return np.nan


# ============================================================
# 15. CONFIANÇA DOS DADOS
# ============================================================

def _data_confidence(row):

    checks = [

        pd.notna(
            row.get(
                "preco"
            )
        ),

        pd.notna(
            row.get(
                "dy_12m"
            )
        ),

        pd.notna(
            row.get(
                "volatilidade_anual"
            )
        ),

        pd.notna(
            row.get(
                "drawdown_5a"
            )
        ),

        pd.notna(
            row.get(
                "liquidez_media_60d"
            )
        ),

        pd.notna(
            row.get(
                "pvp"
            )
        ),

    ]


    return (
        sum(checks)
        /
        len(checks)
    )


# ============================================================
# 16. PENALIDADE DE QUALIDADE DOS DADOS
# ============================================================

def _data_quality_penalty(row):

    penalty = 0.0

    # Valuation ausente não é falha econômica do fundo,
    # mas reduz a convicção do ranking.
    if pd.isna(
        row.get(
            "pvp"
        )
    ):
        penalty -= 5.0

    # Dividendos sem histórico comparável de crescimento
    # recebem apenas pequena penalidade de incerteza.
    if pd.isna(
        row.get(
            "crescimento_dividendos"
        )
    ):
        penalty -= 2.0

    return penalty


# ============================================================
# 17. CLASSIFICAÇÃO
# ============================================================

def _classification(score, risco_especial):

    if risco_especial >= 2:

        return (
            "REPROVADO — ALTO RISCO"
        )


    if pd.isna(score):

        return (
            "SEM SCORE"
        )


    if score >= FUNDAMENTAL_ELITE:

        return "ELITE"


    if score >= FUNDAMENTAL_PREMIUM:

        return "PREMIUM"


    if score >= FUNDAMENTAL_VERY_STRONG:

        return "MUITO FORTE"


    if score >= FUNDAMENTAL_APPROVED:

        return "APROVADO"


    if score >= 60:

        return (
            "AGUARDAR / FUNDAMENTOS INSUFICIENTES"
        )


    return (
        "REPROVADO FUNDAMENTAL"
    )


# ============================================================
# 18. MOTOR PRINCIPAL
# ============================================================

def run_fundamental_engine(database):

    print()
    print("=" * 100)
    print("MOTOR FUNDAMENTALISTA")
    print("=" * 100)


    base = _enrich_fundamentals(
        database
    )


    # ========================================================
    # PILARES
    # ========================================================

    base[
        "pilar_renda"
    ] = base.apply(
        _score_income,
        axis=1
    )


    base[
        "pilar_estrutura"
    ] = base.apply(
        _score_structure,
        axis=1
    )


    base[
        "pilar_valuation"
    ] = base.apply(
        _score_valuation,
        axis=1
    )


    base[
        "pilar_robustez"
    ] = base.apply(
        _score_robustness,
        axis=1
    )


    base[
        "pilar_risco"
    ] = base.apply(
        _score_market_risk,
        axis=1
    )


    # ========================================================
    # SCORE BASE
    # ========================================================

    base[
        "fundamental_score_base"
    ] = base.apply(
        _calculate_base_score,
        axis=1
    )


    # ========================================================
    # PENALIDADES
    # ========================================================

    base[
        "penalidades_totais"
    ] = base.apply(
        _calculate_penalties,
        axis=1
    )


    base[
        "risco_especial"
    ] = base.apply(
        _special_risk,
        axis=1
    )


    base[
        "penalidade_qualidade_dados"
    ] = base.apply(
        _data_quality_penalty,
        axis=1
    )


    # ========================================================
    # SCORE FINAL
    # ========================================================

    base[
        "fundamental_score_final"
    ] = (

        base[
            "fundamental_score_base"
        ]

        +

        base[
            "penalidades_totais"
        ]

        +

        base[
            "penalidade_qualidade_dados"
        ]

    ).clip(
        lower=0,
        upper=100
    )


    # ========================================================
    # MOTOR UTILIZADO
    # ========================================================

    base[
        "motor_fundamental"
    ] = np.select(
        [
            base["ticker"].isin(SPECIAL_MOTOR_TICKERS),
            base["categoria_motor"].eq("PAPEL"),
            base["categoria_motor"].eq("TIJOLO"),
            base["categoria_motor"].eq("ALTERNATIVO"),
        ],
        [
            "MOTOR_ESPECIAL",
            "MOTOR_PAPEL",
            "MOTOR_TIJOLO",
            "MOTOR_ALTERNATIVO",
        ],
        default="SEM_MOTOR"
    )


    # ========================================================
    # QUALIDADE DO VALUATION
    # ========================================================

    base[
        "valuation_disponivel"
    ] = base[
        "pvp"
    ].notna()

    base[
        "status_valuation"
    ] = np.where(
        base[
            "valuation_disponivel"
        ],
        "PVP_DISPONIVEL",
        "PVP_AUSENTE"
    )


    # ========================================================
    # CONFIANÇA
    # ========================================================

    base[
        "confianca_dados"
    ] = base.apply(
        _data_confidence,
        axis=1
    )


    # ========================================================
    # CLASSIFICAÇÃO
    # ========================================================

    base[
        "status_fundamental"
    ] = base.apply(

        lambda row:
            _classification(

                row[
                    "fundamental_score_final"
                ],

                row[
                    "risco_especial"
                ]

            ),

        axis=1

    )


    # Ativos especiais ficam fora do ranking comum até terem
    # um motor específico próprio.
    mask_special = base[
        "ticker"
    ].isin(
        SPECIAL_MOTOR_TICKERS
    )

    base.loc[
        mask_special,
        "status_fundamental"
    ] = "MOTOR ESPECIAL NECESSÁRIO"

    # Fundo sem P/VP pode continuar no universo, mas a aprovação
    # depende do score já reduzido e da confiança de dados.
    mask_pvp_missing = (
        base[
            "pvp"
        ].isna()
        &
        ~mask_special
    )

    base.loc[
        mask_pvp_missing
        &
        (
            base[
                "status_fundamental"
            ].isin(
                [
                    "ELITE",
                    "PREMIUM",
                ]
            )
        ),
        "status_fundamental"
    ] = "MUITO FORTE — VALUATION PENDENTE"


    # ========================================================
    # GATE
    # ========================================================

    base[
        "fundamental_aprovado_final"
    ] = (

        (
            base[
                "fundamental_score_final"
            ]
            >=
            FUNDAMENTAL_GATE
        )

        &

        (
            base[
                "risco_especial"
            ]
            < 2
        )

        &

        (
            base[
                "confianca_dados"
            ]
            >=
            MIN_DATA_CONFIDENCE
        )

        &

        (
            ~base[
                "ticker"
            ].isin(
                SPECIAL_MOTOR_TICKERS
            )
        )

    )


    # ========================================================
    # RANKING
    # ========================================================

    base = (

        base

        .sort_values(

            [
                "fundamental_aprovado_final",
                "fundamental_score_final",
            ],

            ascending=[
                False,
                False,
            ]

        )

        .reset_index(
            drop=True
        )

    )


    base[
        "ranking_fundamental_global"
    ] = np.arange(
        1,
        len(base) + 1
    )


    # ========================================================
    # AUDITORIA
    # ========================================================

    print(
        f"FIIs analisados            : "
        f"{len(base)}"
    )

    print(
        f"Aprovados no gate          : "
        f"{base['fundamental_aprovado_final'].sum()}"
    )

    print()


    print(
        "Distribuição:"
    )

    print(
        base[
            "status_fundamental"
        ]
        .value_counts()
        .to_string()
    )


    print()
    print(
        "P/VP disponível            : "
        f"{int(base['valuation_disponivel'].sum())}/"
        f"{len(base)}"
    )

    print(
        "P/VP ausente               : "
        f"{int((~base['valuation_disponivel']).sum())}"
    )

    print()
    print("=" * 100)
    print("TOP 15 FUNDAMENTALISTA")
    print("=" * 100)


    cols = [

        "ranking_fundamental_global",

        "ticker",

        "categoria_motor",

        "motor_fundamental",

        "segmento",

        "fundamental_score_final",

        "status_fundamental",

        "dy_12m",

        "pvp",

        "fonte_valuation_final",

        "status_valuation",

        "confianca_dados",

        "penalidade_qualidade_dados",

        "pilar_renda",

        "pilar_estrutura",

        "pilar_valuation",

        "pilar_robustez",

        "pilar_risco",

        "fundamental_aprovado_final",

    ]


    print(

        base[
            cols
        ]

        .head(15)

        .to_string(
            index=False
        )

    )


    especiais = base[
        base[
            "ticker"
        ].isin(
            SPECIAL_MOTOR_TICKERS
        )
    ]

    if not especiais.empty:

        print()
        print("=" * 100)
        print("ATIVOS ESPECIAIS — FORA DO MOTOR COMUM")
        print("=" * 100)

        print(
            especiais[
                [
                    "ticker",
                    "categoria_motor",
                    "segmento",
                    "status_fundamental",
                    "fundamental_aprovado_final",
                ]
            ]
            .to_string(
                index=False
            )
        )

    print()
    print("=" * 100)
    print("MOTOR FUNDAMENTALISTA CONCLUÍDO")
    print("=" * 100)


    return base
