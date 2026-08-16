# ============================================================
# FII INSTITUTIONAL SCANNER
# engine/technical_engine.py
# ============================================================

from pathlib import Path
import warnings

import numpy as np
import pandas as pd
import yfinance as yf
from tqdm import tqdm

from config import (
    DATA_DIR,
    RSI_WINDOW,
    SMA_SHORT,
    SMA_MEDIUM,
    SMA_LONG,
    VOLUME_WINDOW,
    RETURN_1M_DAYS,
    RETURN_3M_DAYS,
    RETURN_6M_DAYS,
    HIGH_52W_WINDOW,
    TECHNICAL_STRONG,
    TECHNICAL_ACCEPTABLE,
    RSI_OVERBOUGHT,
    MAX_DISTANCE_SMA200,
    YAHOO_REPAIR,
    YAHOO_AUTO_ADJUST,
)

warnings.filterwarnings("ignore")


# ============================================================
# 1. AUXILIARES
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


def safe_div(a, b):

    try:

        if b == 0:
            return np.nan

        return a / b

    except Exception:
        return np.nan


# ============================================================
# 2. RSI
# ============================================================

def calculate_rsi(series, window=14):

    delta = series.diff()

    gain = delta.clip(
        lower=0
    )

    loss = (
        -delta.clip(
            upper=0
        )
    )

    avg_gain = gain.rolling(
        window
    ).mean()

    avg_loss = loss.rolling(
        window
    ).mean()

    rs = (
        avg_gain
        /
        avg_loss.replace(
            0,
            np.nan
        )
    )

    rsi = (
        100
        -
        (
            100
            /
            (
                1 + rs
            )
        )
    )

    return rsi


# ============================================================
# 3. DOWNLOAD
# ============================================================

def _download_history(ticker):

    # ========================================================
    # FONTE PRINCIPAL — HISTÓRICO HIGIENIZADO PELO DATA ENGINE
    # ========================================================

    clean_file = (
        Path(DATA_DIR)
        / "history_clean"
        / f"{ticker}.csv"
    )

    if clean_file.exists():

        try:

            df = pd.read_csv(
                clean_file,
                index_col=0,
                parse_dates=True,
            )

            if df is not None and not df.empty:

                df.index = pd.to_datetime(
                    df.index,
                    errors="coerce"
                )

                df = df[
                    ~df.index.isna()
                ]

                df = df[
                    ~df.index.duplicated(
                        keep="last"
                    )
                ]

                df = df.sort_index()

                if "Close" in df.columns:

                    return df

        except Exception as exc:

            print(
                f"[AVISO] {ticker} | "
                f"falha ao carregar histórico limpo: {exc}"
            )

    # ========================================================
    # FALLBACK — YAHOO
    # ========================================================

    symbol = f"{ticker}.SA"

    try:

        df = yf.download(
            symbol,
            period="2y",
            interval="1d",
            auto_adjust=YAHOO_AUTO_ADJUST,
            repair=YAHOO_REPAIR,
            progress=False,
            threads=False,
        )

    except Exception:

        return pd.DataFrame()

    if df is None or df.empty:

        return pd.DataFrame()

    if isinstance(
        df.columns,
        pd.MultiIndex
    ):

        if "Close" in df.columns.get_level_values(0):

            df.columns = (
                df.columns
                .get_level_values(0)
            )

    df.index = pd.to_datetime(
        df.index,
        errors="coerce"
    )

    df = df[
        ~df.index.isna()
    ]

    df = df[
        ~df.index.duplicated(
            keep="last"
        )
    ]

    df = df.sort_index()

    return df


# ============================================================
# 4. INDICADORES
# ============================================================

def _calculate_indicators(ticker):

    result = {

        "ticker": ticker,

        "preco_tecnico": np.nan,

        "rsi14": np.nan,

        "retorno_1m": np.nan,

        "retorno_3m": np.nan,

        "retorno_6m": np.nan,

        "dist_sma20": np.nan,

        "dist_sma50": np.nan,

        "dist_sma200": np.nan,

        "distancia_max_52s": np.nan,

        "volume_relativo": np.nan,

        "score_tendencia": np.nan,

        "penalidade_estiramento": 0.0,

        "technical_score": np.nan,

        "classificacao_tecnica": "SEM DADO",

        "status_timing": "AGUARDAR CONFIRMAÇÃO",

        "fonte_historico_tecnico": "DESCONHECIDA",
    }

    hist = _download_history(
        ticker
    )

    clean_file = (
        Path(DATA_DIR)
        / "history_clean"
        / f"{ticker}.csv"
    )

    result[
        "fonte_historico_tecnico"
    ] = (
        "HISTORY_CLEAN"
        if clean_file.exists()
        else "YAHOO_FALLBACK"
    )

    if hist.empty:

        return result

    if "Close" not in hist.columns:

        return result

    close = pd.to_numeric(
        hist["Close"],
        errors="coerce"
    ).dropna()

    if len(close) < SMA_LONG:

        return result

    preco = float(
        close.iloc[-1]
    )

    result[
        "preco_tecnico"
    ] = preco


    # ========================================================
    # RSI
    # ========================================================

    rsi = calculate_rsi(
        close,
        RSI_WINDOW
    )

    if not rsi.dropna().empty:

        result[
            "rsi14"
        ] = float(
            rsi.dropna().iloc[-1]
        )


    # ========================================================
    # RETORNOS
    # ========================================================

    if len(close) > RETURN_1M_DAYS:

        result[
            "retorno_1m"
        ] = (
            preco
            /
            close.iloc[
                -RETURN_1M_DAYS - 1
            ]
            - 1
        )


    if len(close) > RETURN_3M_DAYS:

        result[
            "retorno_3m"
        ] = (
            preco
            /
            close.iloc[
                -RETURN_3M_DAYS - 1
            ]
            - 1
        )


    if len(close) > RETURN_6M_DAYS:

        result[
            "retorno_6m"
        ] = (
            preco
            /
            close.iloc[
                -RETURN_6M_DAYS - 1
            ]
            - 1
        )


    # ========================================================
    # MÉDIAS
    # ========================================================

    sma20 = (
        close
        .rolling(
            SMA_SHORT
        )
        .mean()
    )

    sma50 = (
        close
        .rolling(
            SMA_MEDIUM
        )
        .mean()
    )

    sma200 = (
        close
        .rolling(
            SMA_LONG
        )
        .mean()
    )


    sma20_last = (
        sma20.iloc[-1]
    )

    sma50_last = (
        sma50.iloc[-1]
    )

    sma200_last = (
        sma200.iloc[-1]
    )


    result[
        "dist_sma20"
    ] = (
        safe_div(
            preco,
            sma20_last
        )
        - 1
    )


    result[
        "dist_sma50"
    ] = (
        safe_div(
            preco,
            sma50_last
        )
        - 1
    )


    result[
        "dist_sma200"
    ] = (
        safe_div(
            preco,
            sma200_last
        )
        - 1
    )


    # ========================================================
    # MÁXIMA 52 SEMANAS
    # ========================================================

    janela_52s = (
        close
        .tail(
            HIGH_52W_WINDOW
        )
    )

    max_52 = (
        janela_52s.max()
    )

    result[
        "distancia_max_52s"
    ] = (
        safe_div(
            preco,
            max_52
        )
        - 1
    )


    # ========================================================
    # VOLUME RELATIVO
    # ========================================================

    if "Volume" in hist.columns:

        volume = pd.to_numeric(
            hist["Volume"],
            errors="coerce"
        )

        volume_avg = (
            volume
            .rolling(
                VOLUME_WINDOW
            )
            .mean()
        )

        if (
            len(volume_avg.dropna()) > 0
            and volume_avg.iloc[-1] > 0
        ):

            result[
                "volume_relativo"
            ] = (
                volume.iloc[-1]
                /
                volume_avg.iloc[-1]
            )


    # ========================================================
    # SCORE DE TENDÊNCIA
    # ========================================================

    trend_score = 0


    if preco > sma20_last:

        trend_score += 20


    if preco > sma50_last:

        trend_score += 20


    if preco > sma200_last:

        trend_score += 25


    if (
        sma20_last
        >
        sma50_last
    ):

        trend_score += 15


    if (
        sma50_last
        >
        sma200_last
    ):

        trend_score += 20


    result[
        "score_tendencia"
    ] = trend_score


    # ========================================================
    # SCORE RSI
    # ========================================================

    rsi_value = result[
        "rsi14"
    ]


    if pd.isna(rsi_value):

        score_rsi = 50

    elif 35 <= rsi_value <= 55:

        score_rsi = 100

    elif 30 <= rsi_value < 35:

        score_rsi = 90

    elif 55 < rsi_value <= 65:

        score_rsi = 80

    elif 25 <= rsi_value < 30:

        score_rsi = 75

    elif 65 < rsi_value <= RSI_OVERBOUGHT:

        score_rsi = 60

    elif rsi_value < 25:

        score_rsi = 55

    else:

        score_rsi = 35


    # ========================================================
    # SCORE MOMENTUM
    # ========================================================

    r1 = result[
        "retorno_1m"
    ]

    r3 = result[
        "retorno_3m"
    ]

    r6 = result[
        "retorno_6m"
    ]


    momentum_score = 50


    if not pd.isna(r1):

        if -0.04 <= r1 <= 0.04:

            momentum_score += 10

        elif r1 > 0.08:

            momentum_score -= 10


    if not pd.isna(r3):

        if r3 > 0:

            momentum_score += 15

        elif r3 < -0.10:

            momentum_score -= 10


    if not pd.isna(r6):

        if r6 > 0:

            momentum_score += 15

        elif r6 < -0.15:

            momentum_score -= 10


    momentum_score = clip_score(
        momentum_score
    )


    # ========================================================
    # SCORE DISTÂNCIA DAS MÉDIAS
    # ========================================================

    d20 = result[
        "dist_sma20"
    ]

    d50 = result[
        "dist_sma50"
    ]

    d200 = result[
        "dist_sma200"
    ]


    distance_score = 50


    if (
        not pd.isna(d20)
        and -0.04 <= d20 <= 0.03
    ):

        distance_score += 15


    if (
        not pd.isna(d50)
        and -0.05 <= d50 <= 0.05
    ):

        distance_score += 15


    if (
        not pd.isna(d200)
        and d200 >= 0
    ):

        distance_score += 20


    distance_score = clip_score(
        distance_score
    )


    # ========================================================
    # SCORE VOLUME
    # ========================================================

    vr = result[
        "volume_relativo"
    ]


    if pd.isna(vr):

        score_volume = 50

    elif vr >= 1.5:

        score_volume = 100

    elif vr >= 1.2:

        score_volume = 85

    elif vr >= 0.9:

        score_volume = 70

    elif vr >= 0.7:

        score_volume = 55

    else:

        score_volume = 40


    # ========================================================
    # PENALIDADE DE ESTIRAMENTO
    # ========================================================

    penalty = 0


    if (
        not pd.isna(d200)
        and d200 > MAX_DISTANCE_SMA200
    ):

        penalty -= 15


    if (
        not pd.isna(r1)
        and r1 > 0.12
    ):

        penalty -= 10


    if (
        not pd.isna(r3)
        and r3 > 0.20
    ):

        penalty -= 10


    if (
        not pd.isna(rsi_value)
        and rsi_value > RSI_OVERBOUGHT
    ):

        penalty -= 10


    result[
        "penalidade_estiramento"
    ] = penalty


    # ========================================================
    # TECHNICAL SCORE
    # ========================================================

    technical_score = (

        trend_score * 0.35

        +

        score_rsi * 0.20

        +

        momentum_score * 0.20

        +

        distance_score * 0.15

        +

        score_volume * 0.10

        +

        penalty

    )


    technical_score = clip_score(
        technical_score
    )


    result[
        "technical_score"
    ] = technical_score


    # ========================================================
    # CLASSIFICAÇÃO
    # ========================================================

    if technical_score >= 90:

        classificacao = (
            "TIMING EXCELENTE"
        )

    elif technical_score >= 80:

        classificacao = (
            "TIMING FORTE"
        )

    elif technical_score >= 65:

        classificacao = (
            "TIMING BOM"
        )

    elif technical_score >= 50:

        classificacao = (
            "NEUTRO"
        )

    elif technical_score >= 40:

        classificacao = (
            "AGUARDAR"
        )

    else:

        classificacao = (
            "TIMING RUIM"
        )


    result[
        "classificacao_tecnica"
    ] = classificacao


    # ========================================================
    # STATUS DE TIMING
    # ========================================================

    if (
        technical_score
        >=
        TECHNICAL_STRONG
    ):

        status = (
            "ENTRADA TÉCNICA FORTE"
        )

    elif (
        technical_score
        >=
        TECHNICAL_ACCEPTABLE
    ):

        status = (
            "ENTRADA TÉCNICA ACEITÁVEL"
        )

    else:

        status = (
            "AGUARDAR CONFIRMAÇÃO"
        )


    result[
        "status_timing"
    ] = status


    return result


# ============================================================
# 5. MOTOR PRINCIPAL
# ============================================================

def run_technical_engine(
    fundamentals
):

    print()
    print("=" * 100)
    print("MOTOR TÉCNICO")
    print("=" * 100)


    # ========================================================
    # SOMENTE APROVADOS NO FUNDAMENTAL
    # ========================================================

    approved = (

        fundamentals[
            fundamentals[
                "fundamental_aprovado_final"
            ]
        ]

        .copy()

    )


    if approved.empty:

        raise RuntimeError(
            "Nenhum FII aprovado no filtro fundamental."
        )


    print(
        f"FIIs aprovados para análise técnica: "
        f"{len(approved)}"
    )


    # ========================================================
    # COLETA
    # ========================================================

    records = []


    for ticker in tqdm(

        approved[
            "ticker"
        ].tolist(),

        desc="Motor Técnico"

    ):

        records.append(
            _calculate_indicators(
                ticker
            )
        )


    technical = pd.DataFrame(
        records
    )


    # ========================================================
    # JUNTA DADOS FUNDAMENTAIS
    # ========================================================

    cols_fund = [

        "ticker",

        "categoria_motor",

        "segmento",

        "fundamental_score_final",

        "status_fundamental",

    ]


    technical = technical.merge(

        approved[
            cols_fund
        ],

        on="ticker",

        how="left"

    )


    # ========================================================
    # RANKING
    # ========================================================

    technical = (

        technical

        .sort_values(
            "technical_score",
            ascending=False
        )

        .reset_index(
            drop=True
        )

    )


    technical[
        "ranking_tecnico"
    ] = np.arange(
        1,
        len(technical) + 1
    )


    # ========================================================
    # AUDITORIA
    # ========================================================

    print()
    print(
        "STATUS DE TIMING:"
    )

    print(

        technical[
            "status_timing"
        ]
        .value_counts()
        .to_string()

    )


    print()
    print("=" * 100)
    print("TOP 15 TÉCNICO")
    print("=" * 100)


    cols = [

        "ranking_tecnico",

        "ticker",

        "categoria_motor",

        "segmento",

        "fundamental_score_final",

        "technical_score",

        "classificacao_tecnica",

        "status_timing",

        "rsi14",

        "retorno_1m",

        "retorno_3m",

        "retorno_6m",

        "dist_sma20",

        "dist_sma50",

        "dist_sma200",

        "volume_relativo",

        "fonte_historico_tecnico",

    ]


    print(

        technical[
            cols
        ]

        .head(15)

        .to_string(
            index=False
        )

    )


    print()
    print("=" * 100)
    print("MOTOR TÉCNICO CONCLUÍDO")
    print("=" * 100)


    return technical
