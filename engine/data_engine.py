# ============================================================
# FII INSTITUTIONAL SCANNER
# engine/data_engine.py
# ============================================================

from pathlib import Path
import warnings

import numpy as np
import pandas as pd
import yfinance as yf
from tqdm import tqdm

from config import (
    DATA_DIR,
    UNIVERSE_FILE,
    PRICE_HISTORY,
    YAHOO_REPAIR,
    YAHOO_AUTO_ADJUST,
    MIN_PRICE_OBSERVATIONS,
    MIN_LIQUIDITY,
    LIQUIDITY_WINDOW,
    RULE_ZERO_MIN_HISTORY,
    RULE_ZERO_REQUIRE_PRICE,
    RULE_ZERO_REQUIRE_LIQUIDITY,
    RULE_ZERO_REQUIRE_CATEGORY,
    EXTREME_RETURN_ALERT,
    SAVE_UNIVERSE,
)

warnings.filterwarnings("ignore")


# ============================================================
# UNIVERSO INICIAL
# ============================================================

# Universo utilizado no estudo original.
# Podemos ampliar posteriormente sem alterar o restante
# da arquitetura.

FII_UNIVERSE = {

    # --------------------------------------------------------
    # PAPEL
    # --------------------------------------------------------

    "KNCR11": ("PAPEL", "CRI_CDI"),
    "MXRF11": ("PAPEL", "MULTIESTRATEGIA_CREDITO"),
    "KNSC11": ("PAPEL", "CRI"),
    "KNIP11": ("PAPEL", "CRI_IPCA"),
    "VRTA11": ("PAPEL", "CRI"),
    "KNHY11": ("PAPEL", "CRI_HIGH_YIELD"),
    "XPCI11": ("PAPEL", "CRI"),
    "KCRE11": ("PAPEL", "CRI"),
    "RZAK11": ("PAPEL", "CRI_HIGH_YIELD"),
    "BCRI11": ("PAPEL", "CRI"),
    "OUJP11": ("PAPEL", "CRI"),
    "DEVA11": ("PAPEL", "CRI_HIGH_YIELD"),
    "HCTR11": ("PAPEL", "CRI_HIGH_YIELD"),
    "URPR11": ("PAPEL", "CRI_HIGH_YIELD"),

    # --------------------------------------------------------
    # TIJOLO
    # --------------------------------------------------------

    "XPLG11": ("TIJOLO", "LOGISTICA"),
    "HGLG11": ("TIJOLO", "LOGISTICA"),
    "XPML11": ("TIJOLO", "SHOPPING"),
    "HGRU11": ("TIJOLO", "RENDA_URBANA"),
    "HGBS11": ("TIJOLO", "SHOPPING"),
    "ALZR11": ("TIJOLO", "RENDA_URBANA"),
    "GTWR11": ("TIJOLO", "LAJES"),
    "HSML11": ("TIJOLO", "SHOPPING"),
    "SNEL11": ("TIJOLO", "ENERGIA_RENOVAVEL"),
    "LVBI11": ("TIJOLO", "LOGISTICA"),
    "VISC11": ("TIJOLO", "SHOPPING"),
    "BRCO11": ("TIJOLO", "LOGISTICA"),
    "VILG11": ("TIJOLO", "LOGISTICA"),
    "JSRE11": ("TIJOLO", "LAJES"),
    "HSLG11": ("TIJOLO", "LOGISTICA"),
    "RCRB11": ("TIJOLO", "LAJES"),
    "TRXF11": ("TIJOLO", "RENDA_URBANA"),

    # --------------------------------------------------------
    # ALTERNATIVOS
    # --------------------------------------------------------

    "KNRI11": ("ALTERNATIVO", "TIJOLO_DIVERSIFICADO"),
    "VGHF11": ("ALTERNATIVO", "MULTIESTRATEGIA"),
    "KFOF11": ("ALTERNATIVO", "FOF"),
    "JSAF11": ("ALTERNATIVO", "FOF"),
    "TGAR11": ("ALTERNATIVO", "DESENVOLVIMENTO"),
}


# ============================================================
# FUNÇÕES AUXILIARES
# ============================================================

def _safe_float(value, default=np.nan):

    try:

        value = float(value)

        if np.isfinite(value):
            return value

    except (TypeError, ValueError):
        pass

    return default


def _normalize_columns(df):

    if isinstance(df.columns, pd.MultiIndex):

        # Para download individual normalmente o primeiro
        # nível contém Open/High/Low/Close/Volume.

        if "Close" in df.columns.get_level_values(0):

            df.columns = df.columns.get_level_values(0)

        else:

            df.columns = [
                "_".join(
                    [
                        str(x)
                        for x in col
                        if str(x) != ""
                    ]
                )
                for col in df.columns
            ]

    return df


def _download_history(ticker):

    yahoo_ticker = f"{ticker}.SA"

    try:

        df = yf.download(
            yahoo_ticker,
            period=PRICE_HISTORY,
            interval="1d",
            auto_adjust=YAHOO_AUTO_ADJUST,
            repair=YAHOO_REPAIR,
            progress=False,
            threads=False,
        )

    except Exception as exc:

        print(
            f"[AVISO] Falha ao coletar {ticker}: {exc}"
        )

        return pd.DataFrame()

    if df is None or df.empty:
        return pd.DataFrame()

    df = _normalize_columns(df.copy())

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
# MÉTRICAS DE MERCADO
# ============================================================

def _calculate_market_metrics(ticker, history):

    result = {

        "ticker": ticker,

        "preco": np.nan,

        "observacoes_preco": 0,

        "liquidez_media_60d": np.nan,

        "volatilidade_anual": np.nan,

        "drawdown_5a": np.nan,

        "maior_retorno_abs": np.nan,

        "eventos_extremos": 0,

        "dados_preco_ok": False,
    }

    if history.empty:
        return result

    if "Close" not in history.columns:
        return result

    close = pd.to_numeric(
        history["Close"],
        errors="coerce"
    ).dropna()

    if close.empty:
        return result

    close = close[
        close > 0
    ]

    if close.empty:
        return result

    result["preco"] = _safe_float(
        close.iloc[-1]
    )

    result["observacoes_preco"] = len(
        close
    )

    result["dados_preco_ok"] = (
        len(close) >= MIN_PRICE_OBSERVATIONS
    )


    # --------------------------------------------------------
    # RETORNOS
    # --------------------------------------------------------

    returns = (
        close
        .pct_change(fill_method=None)
        .replace([np.inf, -np.inf], np.nan)
        .dropna()
    )

    if not returns.empty:

        result["volatilidade_anual"] = (
            returns.std(ddof=1)
            * np.sqrt(252)
        )

        result["maior_retorno_abs"] = (
            returns.abs().max()
        )

        result["eventos_extremos"] = int(
            (
                returns.abs()
                > EXTREME_RETURN_ALERT
            ).sum()
        )


    # --------------------------------------------------------
    # DRAWDOWN
    # --------------------------------------------------------

    running_max = close.cummax()

    drawdown = (
        close / running_max
    ) - 1

    if not drawdown.empty:

        result["drawdown_5a"] = (
            drawdown.min()
        )


    # --------------------------------------------------------
    # LIQUIDEZ
    # --------------------------------------------------------

    if "Volume" in history.columns:

        volume = pd.to_numeric(
            history["Volume"],
            errors="coerce"
        )

        market_value = (
            pd.to_numeric(
                history["Close"],
                errors="coerce"
            )
            * volume
        )

        liquidity = (
            market_value
            .replace(
                [np.inf, -np.inf],
                np.nan
            )
            .dropna()
            .tail(LIQUIDITY_WINDOW)
        )

        if not liquidity.empty:

            result[
                "liquidez_media_60d"
            ] = liquidity.mean()

    return result


# ============================================================
# REGRA ZERO
# ============================================================

def _apply_rule_zero(df):

    df = df.copy()


    # --------------------------------------------------------
    # HISTÓRICO
    # --------------------------------------------------------

    df["rule_history_ok"] = (
        df["observacoes_preco"]
        >= RULE_ZERO_MIN_HISTORY
    )


    # --------------------------------------------------------
    # PREÇO
    # --------------------------------------------------------

    if RULE_ZERO_REQUIRE_PRICE:

        df["rule_price_ok"] = (
            df["preco"].notna()
            & (df["preco"] > 0)
        )

    else:

        df["rule_price_ok"] = True


    # --------------------------------------------------------
    # LIQUIDEZ
    # --------------------------------------------------------

    if RULE_ZERO_REQUIRE_LIQUIDITY:

        df["rule_liquidity_ok"] = (
            df["liquidez_media_60d"]
            .fillna(0)
            >= MIN_LIQUIDITY
        )

    else:

        df["rule_liquidity_ok"] = True


    # --------------------------------------------------------
    # CLASSIFICAÇÃO
    # --------------------------------------------------------

    if RULE_ZERO_REQUIRE_CATEGORY:

        df["rule_category_ok"] = (
            df["categoria_motor"].notna()
            & df["segmento"].notna()
        )

    else:

        df["rule_category_ok"] = True


    # --------------------------------------------------------
    # RESULTADO
    # --------------------------------------------------------

    df["regra_zero_aprovado"] = (

        df["rule_history_ok"]

        & df["rule_price_ok"]

        & df["rule_liquidity_ok"]

        & df["rule_category_ok"]
    )

    return df


# ============================================================
# AUDITORIA
# ============================================================

def _print_audit(df):

    print()
    print("=" * 90)
    print("DATA ENGINE — AUDITORIA")
    print("=" * 90)

    print(
        f"Universo configurado       : {len(df)}"
    )

    print(
        "Com histórico suficiente  :",
        int(df["rule_history_ok"].sum())
    )

    print(
        "Com preço válido           :",
        int(df["rule_price_ok"].sum())
    )

    print(
        "Com liquidez mínima        :",
        int(df["rule_liquidity_ok"].sum())
    )

    print(
        "Regra Zero aprovada        :",
        int(df["regra_zero_aprovado"].sum())
    )


    extreme = df[
        df["eventos_extremos"] > 0
    ]

    print(
        "Com evento diário extremo  :",
        len(extreme)
    )


    if not extreme.empty:

        print()
        print(
            "ATENÇÃO — EVENTOS EXTREMOS"
        )

        cols = [
            "ticker",
            "maior_retorno_abs",
            "eventos_extremos",
        ]

        print(
            extreme[cols]
            .sort_values(
                "maior_retorno_abs",
                ascending=False
            )
            .to_string(index=False)
        )


# ============================================================
# BUILD DATABASE
# ============================================================

def build_database():

    Path(DATA_DIR).mkdir(
        parents=True,
        exist_ok=True
    )

    print()
    print(
        f"Coletando dados de "
        f"{len(FII_UNIVERSE)} FIIs..."
    )

    records = []


    for ticker, (
        categoria,
        segmento
    ) in tqdm(
        FII_UNIVERSE.items(),
        desc="Data Engine"
    ):

        history = _download_history(
            ticker
        )

        metrics = (
            _calculate_market_metrics(
                ticker,
                history
            )
        )

        metrics[
            "categoria_motor"
        ] = categoria

        metrics[
            "segmento"
        ] = segmento

        records.append(
            metrics
        )


    database = pd.DataFrame(
        records
    )


    # ========================================================
    # TIPOS
    # ========================================================

    numeric_columns = [

        "preco",
        "observacoes_preco",
        "liquidez_media_60d",
        "volatilidade_anual",
        "drawdown_5a",
        "maior_retorno_abs",
        "eventos_extremos",
    ]

    for col in numeric_columns:

        if col in database.columns:

            database[col] = (
                pd.to_numeric(
                    database[col],
                    errors="coerce"
                )
            )


    # ========================================================
    # REGRA ZERO
    # ========================================================

    database = _apply_rule_zero(
        database
    )


    # ========================================================
    # ORDENAR
    # ========================================================

    database = database.sort_values(
        [
            "regra_zero_aprovado",
            "liquidez_media_60d",
        ],
        ascending=[
            False,
            False,
        ],
    ).reset_index(
        drop=True
    )


    # ========================================================
    # SALVAR UNIVERSO COMPLETO
    # ========================================================

    if SAVE_UNIVERSE:

        database.to_csv(
            UNIVERSE_FILE,
            index=False,
            encoding="utf-8-sig"
        )


    _print_audit(
        database
    )


    # ========================================================
    # RETORNO AO PIPELINE
    # ========================================================

    approved = database[
        database[
            "regra_zero_aprovado"
        ]
    ].copy()

    approved = approved.reset_index(
        drop=True
    )


    if approved.empty:

        raise RuntimeError(
            "Nenhum FII passou pela Regra Zero."
        )


    print()
    print(
        f"FIIs enviados ao motor "
        f"fundamentalista: {len(approved)}"
    )

    return approved
