# ============================================================
# FII INSTITUTIONAL SCANNER
# engine/portfolio_engine.py
# ============================================================

from pathlib import Path
import warnings

import numpy as np
import pandas as pd
import yfinance as yf

from scipy.optimize import minimize
from sklearn.covariance import LedoitWolf

from config import (
    DATA_DIR,
    FUNDAMENTAL_WEIGHT,
    TECHNICAL_WEIGHT,
    INSTITUTIONAL_ELITE,
    INSTITUTIONAL_PREMIUM,
    INSTITUTIONAL_VERY_STRONG,
    INSTITUTIONAL_APPROVED,
    PORTFOLIO_SIZE,
    MIN_WEIGHT,
    MAX_WEIGHT,
    MIN_PAPER,
    MAX_PAPER,
    MIN_BRICK,
    MAX_BRICK,
    MAX_ALTERNATIVE,
    MAX_HIGH_YIELD,
    MAX_LOGISTICS,
    MAX_SHOPPING,
    MAX_URBAN_INCOME,
    MAX_OFFICES,
    RISK_WINDOW,
    TRADING_DAYS,
    RISK_RETURN_CAP,
    HHI_PENALTY,
    MAX_FUNDAMENTAL_SCORE_LOSS,
    MAX_INSTITUTIONAL_SCORE_LOSS,
    EXECUTION_STRONG,
    EXECUTION_APPROVED,
    EXECUTION_TACTICAL,
    EXECUTION_WAIT,
    YAHOO_REPAIR,
    YAHOO_AUTO_ADJUST,
    RANKING_FILE,
    PORTFOLIO_FILE,
    SAVE_RANKING,
    SAVE_PORTFOLIO,
)

warnings.filterwarnings("ignore")


# ============================================================
# 1. AUXILIARES
# ============================================================

def _safe_float(value, default=np.nan):

    try:

        value = float(value)

        if np.isfinite(value):
            return value

    except (TypeError, ValueError):
        pass

    return default


def _normalize_weights(w):

    w = np.asarray(
        w,
        dtype=float
    )

    soma = w.sum()

    if soma <= 0:

        raise ValueError(
            "A soma dos pesos é inválida."
        )

    return w / soma


# ============================================================
# 2. SCORE INSTITUCIONAL
# ============================================================

def _institutional_classification(score):

    if pd.isna(score):

        return "SEM SCORE"

    if score >= INSTITUTIONAL_ELITE:

        return "ELITE INSTITUCIONAL"

    if score >= INSTITUTIONAL_PREMIUM:

        return "PREMIUM"

    if score >= INSTITUTIONAL_VERY_STRONG:

        return "MUITO FORTE"

    if score >= INSTITUTIONAL_APPROVED:

        return "APROVADO"

    if score >= 65:

        return "OBSERVAÇÃO"

    return "AGUARDAR"


def _operational_decision(row):

    fundamental = row[
        "fundamental_score_final"
    ]

    technical = row[
        "technical_score"
    ]

    timing = row[
        "status_timing"
    ]

    segmento = row[
        "segmento"
    ]


    # --------------------------------------------------------
    # ENTRADA TÉCNICA FORTE
    # --------------------------------------------------------

    if timing == "ENTRADA TÉCNICA FORTE":

        # High Yield permanece tático mesmo quando o
        # timing está forte.
        if segmento == "CRI_HIGH_YIELD":

            return "ENTRADA TÁTICA"

        if fundamental >= 80:

            return "ENTRADA FORTE"

        return "ENTRADA TÁTICA"


    # --------------------------------------------------------
    # ENTRADA TÉCNICA ACEITÁVEL
    # --------------------------------------------------------

    if timing == "ENTRADA TÉCNICA ACEITÁVEL":

        return "ENTRADA APROVADA"


    # --------------------------------------------------------
    # FUNDAMENTO MUITO FORTE SEM TIMING
    # --------------------------------------------------------

    if fundamental >= 85:

        return (
            "FUNDAMENTO FORTE — AGUARDAR GATILHO"
        )


    # --------------------------------------------------------
    # RESTANTE
    # --------------------------------------------------------

    if technical >= 50:

        return "AGUARDAR CONFIRMAÇÃO"

    return "AGUARDAR"


# ============================================================
# 3. MERGE FUNDAMENTAL + TÉCNICO
# ============================================================

def _build_ranking(
    fundamentals,
    technical
):

    fund_cols = [

        "ticker",
        "categoria_motor",
        "segmento",
        "fundamental_score_final",
        "status_fundamental",
        "fundamental_aprovado_final",
        "dy_12m",
        "pvp",
        "confianca_dados",
        "liquidez_media_60d",

        "pilar_renda",
        "pilar_estrutura",
        "pilar_valuation",
        "pilar_robustez",
        "pilar_risco",

        "risco_especial",
    ]


    fund_cols = [

        col
        for col in fund_cols
        if col in fundamentals.columns

    ]


    tech_cols = [

        "ticker",
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
        "distancia_max_52s",
        "volume_relativo",
        "score_tendencia",
        "penalidade_estiramento",

    ]


    tech_cols = [

        col
        for col in tech_cols
        if col in technical.columns

    ]


    ranking = fundamentals[
        fund_cols
    ].merge(

        technical[
            tech_cols
        ],

        on="ticker",

        how="inner"

    )


    # ========================================================
    # SCORE 80 / 20
    # ========================================================

    ranking[
        "institutional_score"
    ] = (

        ranking[
            "fundamental_score_final"
        ]
        *
        FUNDAMENTAL_WEIGHT

        +

        ranking[
            "technical_score"
        ]
        *
        TECHNICAL_WEIGHT

    )


    ranking[
        "classificacao_institucional"
    ] = (

        ranking[
            "institutional_score"
        ]

        .apply(
            _institutional_classification
        )

    )


    ranking[
        "decisao_operacional"
    ] = ranking.apply(

        _operational_decision,

        axis=1

    )


    # ========================================================
    # PRIORIDADE
    # ========================================================

    def prioridade(row):

        score = row[
            "institutional_score"
        ]

        fund = row[
            "fundamental_score_final"
        ]


        if score >= 90:

            return "NÚCLEO"

        if score >= 82:

            return "PRIORIDADE ALTA"

        if score >= 78:

            return "PRIORIDADE"

        if fund >= 70:

            return "SECUNDÁRIO"

        return "FORA"


    ranking[
        "prioridade_portfolio"
    ] = ranking.apply(

        prioridade,

        axis=1

    )


    ranking = (

        ranking

        .sort_values(
            [
                "institutional_score",
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


    ranking[
        "ranking_institucional"
    ] = np.arange(
        1,
        len(ranking) + 1
    )


    return ranking


# ============================================================
# 4. SELEÇÃO DOS CANDIDATOS
# ============================================================

def _select_portfolio_candidates(ranking):

    approved = ranking[

        ranking[
            "fundamental_aprovado_final"
        ]

    ].copy()


    if approved.empty:

        raise RuntimeError(
            "Nenhum FII aprovado para construção da carteira."
        )


    # ========================================================
    # PRIMEIRA SELEÇÃO
    # ========================================================

    selected = (

        approved

        .sort_values(
            [
                "institutional_score",
                "fundamental_score_final",
            ],
            ascending=[
                False,
                False,
            ]
        )

        .head(
            PORTFOLIO_SIZE
        )

        .copy()

    )


    # ========================================================
    # DIVERSIFICAÇÃO MÍNIMA
    # ========================================================
    #
    # Caso o ranking puro selecione concentração extrema,
    # tentamos preservar:
    #
    # - Papel
    # - Tijolo
    # - Alternativo
    #
    # ========================================================

    categorias = set(
        selected[
            "categoria_motor"
        ].tolist()
    )


    required = {
        "PAPEL",
        "TIJOLO",
    }


    missing = (
        required
        -
        categorias
    )


    for categoria in missing:

        candidate = (

            approved[
                approved[
                    "categoria_motor"
                ]
                ==
                categoria
            ]

            .sort_values(
                "institutional_score",
                ascending=False
            )

        )


        if candidate.empty:
            continue


        new_row = candidate.iloc[0]


        # substitui o pior selecionado

        pior_idx = (

            selected[
                "institutional_score"
            ]
            .idxmin()

        )


        selected = selected.drop(
            index=pior_idx
        )


        selected = pd.concat(

            [
                selected,
                new_row.to_frame().T
            ],

            ignore_index=True

        )


    selected = (

        selected

        .drop_duplicates(
            subset=["ticker"]
        )

        .sort_values(
            "institutional_score",
            ascending=False
        )

        .head(
            PORTFOLIO_SIZE
        )

        .reset_index(
            drop=True
        )

    )


    if len(selected) < PORTFOLIO_SIZE:

        restantes = (

            approved[
                ~approved[
                    "ticker"
                ]
                .isin(
                    selected[
                        "ticker"
                    ]
                )
            ]

            .sort_values(
                "institutional_score",
                ascending=False
            )

        )


        needed = (
            PORTFOLIO_SIZE
            -
            len(selected)
        )


        selected = pd.concat(

            [
                selected,
                restantes.head(
                    needed
                )
            ],

            ignore_index=True

        )


    return selected


# ============================================================
# 5. COLETA DE PREÇOS PARA RISCO
# ============================================================

def _download_portfolio_prices(tickers):

    series = []

    clean_dir = (
        Path(DATA_DIR)
        / "history_clean"
    )

    for ticker in tickers:

        close = None

        # ====================================================
        # FONTE PRINCIPAL — HISTÓRICO LIMPO DO DATA ENGINE
        # ====================================================

        clean_file = (
            clean_dir
            /
            f"{ticker}.csv"
        )

        if clean_file.exists():

            try:

                hist = pd.read_csv(
                    clean_file,
                    index_col=0,
                    parse_dates=True,
                )

                if (
                    hist is not None
                    and not hist.empty
                    and "Close" in hist.columns
                ):

                    hist.index = pd.to_datetime(
                        hist.index,
                        errors="coerce"
                    )

                    hist = hist[
                        ~hist.index.isna()
                    ]

                    hist = hist[
                        ~hist.index.duplicated(
                            keep="last"
                        )
                    ]

                    hist = hist.sort_index()

                    close = pd.to_numeric(
                        hist[
                            "Close"
                        ],
                        errors="coerce"
                    )

            except Exception as exc:

                print(
                    f"[AVISO] {ticker} | "
                    f"falha ao ler history_clean: {exc}"
                )

                close = None


        # ====================================================
        # FALLBACK — YAHOO
        # ====================================================

        if (
            close is None
            or close.dropna().empty
        ):

            symbol = f"{ticker}.SA"

            try:

                hist = yf.download(
                    symbol,
                    period="3y",
                    interval="1d",
                    auto_adjust=YAHOO_AUTO_ADJUST,
                    repair=YAHOO_REPAIR,
                    progress=False,
                    threads=False,
                )

            except Exception as exc:

                print(
                    f"[AVISO] {ticker} | "
                    f"fallback Yahoo falhou: {exc}"
                )

                continue

            if hist is None or hist.empty:
                continue

            if isinstance(
                hist.columns,
                pd.MultiIndex
            ):

                if (
                    "Close"
                    in
                    hist.columns.get_level_values(0)
                ):

                    close = (
                        hist[
                            "Close"
                        ]
                        .iloc[:, 0]
                    )

                else:
                    continue

            else:

                if "Close" not in hist.columns:
                    continue

                close = hist[
                    "Close"
                ]


        close = (
            pd.to_numeric(
                close,
                errors="coerce"
            )
            .dropna()
            .rename(
                ticker
            )
        )

        if not close.empty:

            series.append(
                close
            )


    if not series:

        raise RuntimeError(
            "Não foi possível obter histórico "
            "de preços para a carteira."
        )


    prices = pd.concat(
        series,
        axis=1,
        join="outer"
    )

    prices = (
        prices
        .sort_index()
        .ffill(
            limit=3
        )
    )


    missing = sorted(
        set(tickers)
        -
        set(prices.columns)
    )

    if missing:

        raise RuntimeError(
            "Sem histórico para: "
            +
            ", ".join(
                missing
            )
        )


    prices = (
        prices[
            tickers
        ]
        .dropna(
            how="any"
        )
    )

    if len(prices) < 100:

        raise RuntimeError(
            "Histórico comum insuficiente para "
            f"matriz de risco: {len(prices)} pregões."
        )


    print(
        f"Histórico de risco carregado: "
        f"{len(prices)} pregões comuns "
        f"para {len(tickers)} FIIs."
    )

    return prices


# ============================================================
# 6. RETORNOS ROBUSTOS
# ============================================================

def _build_robust_returns(prices):

    returns = (

        prices

        .pct_change(
            fill_method=None
        )

        .replace(
            [np.inf, -np.inf],
            np.nan
        )

        .dropna(
            how="any"
        )

    )


    # ========================================================
    # AUDITORIA DE EVENTOS EXTREMOS
    # ========================================================

    extreme_count = (

        returns
        .abs()
        .gt(
            RISK_RETURN_CAP
        )
        .sum()

    )


    # ========================================================
    # BASE EXCLUSIVA PARA RISCO
    # ========================================================

    robust = returns.clip(

        lower=-RISK_RETURN_CAP,

        upper=RISK_RETURN_CAP,

    )


    return (
        returns,
        robust,
        extreme_count
    )


# ============================================================
# 7. COVARIÂNCIA ROBUSTA
# ============================================================

def _build_covariance(
    robust_returns
):

    sample = (

        robust_returns
        .tail(
            RISK_WINDOW
        )

    )


    if len(sample) < 100:

        raise RuntimeError(
            "Histórico insuficiente para matriz de risco."
        )


    try:

        lw = LedoitWolf()

        lw.fit(
            sample.values
        )

        cov_daily = (
            lw.covariance_
        )

    except Exception as exc:

        print(
            "[AVISO] LedoitWolf falhou; "
            f"usando covariância amostral: {exc}"
        )

        cov_daily = np.cov(
            sample.values,
            rowvar=False,
            ddof=1
        )


    cov_annual = (

        cov_daily
        *
        TRADING_DAYS

    )


    return cov_annual


# ============================================================
# 8. MÁSCARAS DO PORTFÓLIO
# ============================================================

def _build_masks(portfolio):

    categories = (

        portfolio[
            "categoria_motor"
        ]

        .values

    )


    segments = (

        portfolio[
            "segmento"
        ]

        .values

    )


    return {

        "paper":
            categories == "PAPEL",

        "brick":
            categories == "TIJOLO",

        "alternative":
            categories == "ALTERNATIVO",

        "high_yield":
            segments == "CRI_HIGH_YIELD",

        "logistics":
            segments == "LOGISTICA",

        "shopping":
            segments == "SHOPPING",

        "urban_income":
            segments == "RENDA_URBANA",

        "offices":
            segments == "LAJES",

    }


def _sum_mask(
    w,
    mask
):

    return float(
        np.sum(
            w[mask]
        )
    )


# ============================================================
# 9. PESOS INICIAIS
# ============================================================

def _initial_weights(portfolio):

    # ========================================================
    # PESO BASE PELO SCORE INSTITUCIONAL
    # ========================================================

    score = (

        portfolio[
            "institutional_score"
        ]

        .values
        .astype(float)

    )


    score = np.maximum(
        score,
        1
    )


    w = (
        score
        /
        score.sum()
    )


    # aproxima limites básicos

    w = np.clip(

        w,

        MIN_WEIGHT,

        MAX_WEIGHT

    )


    w = _normalize_weights(
        w
    )


    return w


# ============================================================
# 10. OTIMIZAÇÃO
# ============================================================

def _optimize_portfolio(
    portfolio,
    cov_annual,
    w0
):

    masks = _build_masks(
        portfolio
    )


    fund_scores = (

        portfolio[
            "fundamental_score_final"
        ]

        .values
        .astype(float)

    )


    inst_scores = (

        portfolio[
            "institutional_score"
        ]

        .values
        .astype(float)

    )


    fund_initial = float(
        w0 @ fund_scores
    )


    inst_initial = float(
        w0 @ inst_scores
    )


    min_fund = (
        fund_initial
        -
        MAX_FUNDAMENTAL_SCORE_LOSS
    )


    min_inst = (
        inst_initial
        -
        MAX_INSTITUTIONAL_SCORE_LOSS
    )


    # ========================================================
    # OBJETIVO
    # ========================================================

    def objective(w):

        variance = (
            w
            @
            cov_annual
            @
            w
        )

        hhi = np.sum(
            w ** 2
        )

        return (
            variance
            +
            HHI_PENALTY
            *
            hhi
        )


    # ========================================================
    # RESTRIÇÕES
    # ========================================================

    constraints = [

        {
            "type": "eq",
            "fun":
                lambda w:
                    np.sum(w) - 1
        },

        {
            "type": "ineq",
            "fun":
                lambda w:
                    _sum_mask(
                        w,
                        masks["paper"]
                    )
                    -
                    MIN_PAPER
        },

        {
            "type": "ineq",
            "fun":
                lambda w:
                    MAX_PAPER
                    -
                    _sum_mask(
                        w,
                        masks["paper"]
                    )
        },

        {
            "type": "ineq",
            "fun":
                lambda w:
                    _sum_mask(
                        w,
                        masks["brick"]
                    )
                    -
                    MIN_BRICK
        },

        {
            "type": "ineq",
            "fun":
                lambda w:
                    MAX_BRICK
                    -
                    _sum_mask(
                        w,
                        masks["brick"]
                    )
        },

        {
            "type": "ineq",
            "fun":
                lambda w:
                    MAX_ALTERNATIVE
                    -
                    _sum_mask(
                        w,
                        masks["alternative"]
                    )
        },

        {
            "type": "ineq",
            "fun":
                lambda w:
                    MAX_HIGH_YIELD
                    -
                    _sum_mask(
                        w,
                        masks["high_yield"]
                    )
        },

        {
            "type": "ineq",
            "fun":
                lambda w:
                    MAX_LOGISTICS
                    -
                    _sum_mask(
                        w,
                        masks["logistics"]
                    )
        },

        {
            "type": "ineq",
            "fun":
                lambda w:
                    MAX_SHOPPING
                    -
                    _sum_mask(
                        w,
                        masks["shopping"]
                    )
        },

        {
            "type": "ineq",
            "fun":
                lambda w:
                    MAX_URBAN_INCOME
                    -
                    _sum_mask(
                        w,
                        masks["urban_income"]
                    )
        },

        {
            "type": "ineq",
            "fun":
                lambda w:
                    MAX_OFFICES
                    -
                    _sum_mask(
                        w,
                        masks["offices"]
                    )
        },

        {
            "type": "ineq",
            "fun":
                lambda w:
                    (
                        w @ fund_scores
                    )
                    -
                    min_fund
        },

        {
            "type": "ineq",
            "fun":
                lambda w:
                    (
                        w @ inst_scores
                    )
                    -
                    min_inst
        },

    ]


    bounds = [

        (
            MIN_WEIGHT,
            MAX_WEIGHT
        )

        for _ in range(
            len(portfolio)
        )

    ]


    # ========================================================
    # AUXILIAR — VIOLAÇÕES
    # ========================================================

    def constraint_violations(w):

        values = []

        for c in constraints:

            value = float(
                c["fun"](w)
            )

            if c["type"] == "eq":

                values.append(
                    abs(value)
                )

            else:

                values.append(
                    max(
                        0.0,
                        -value
                    )
                )

        return np.asarray(
            values,
            dtype=float
        )


    def feasibility_objective(w):

        v = constraint_violations(
            w
        )

        return float(
            np.sum(
                v ** 2
            )
        )


    # ========================================================
    # ETAPA 1 — ENCONTRAR PONTO VIÁVEL
    # ========================================================

    starts = []

    starts.append(
        _normalize_weights(
            np.clip(
                w0,
                MIN_WEIGHT,
                MAX_WEIGHT
            )
        )
    )

    uniform = np.full(
        len(portfolio),
        1.0 / len(portfolio)
    )

    uniform = _normalize_weights(
        np.clip(
            uniform,
            MIN_WEIGHT,
            MAX_WEIGHT
        )
    )

    starts.append(
        uniform
    )


    best_feasible = None
    best_violation = np.inf

    for start in starts:

        feasible_result = minimize(

            feasibility_objective,

            start,

            method="SLSQP",

            bounds=bounds,

            constraints=[
                {
                    "type": "eq",
                    "fun":
                        lambda w:
                            np.sum(w) - 1
                }
            ],

            options={
                "maxiter": 2500,
                "ftol": 1e-12,
                "disp": False,
            },

        )

        candidate = _normalize_weights(
            feasible_result.x
        )

        violation = float(
            np.max(
                constraint_violations(
                    candidate
                )
            )
        )

        if violation < best_violation:

            best_violation = violation
            best_feasible = candidate


    if (
        best_feasible is None
        or best_violation > 1e-5
    ):

        print(
            "[AVISO] Restrições da carteira "
            "não possuem ponto plenamente viável. "
            f"Violação mínima={best_violation:.8f}"
        )

        # Não derruba o scanner. Mantém o melhor ponto
        # encontrado e registra a condição no diagnóstico.
        best_feasible = (
            best_feasible
            if best_feasible is not None
            else starts[0]
        )


    # ========================================================
    # ETAPA 2 — OTIMIZAÇÃO PRINCIPAL
    # ========================================================

    result = minimize(

        objective,

        best_feasible,

        method="SLSQP",

        bounds=bounds,

        constraints=constraints,

        options={
            "maxiter": 5000,
            "ftol": 1e-10,
            "disp": False,
        },

    )


    # ========================================================
    # ETAPA 3 — FALLBACK CONTROLADO
    # ========================================================

    if result.success:

        weights = _normalize_weights(
            result.x
        )

        return (
            weights,
            result,
            masks
        )


    print(
        "[AVISO] Otimização principal não convergiu: "
        f"{result.message}"
    )


    candidate = _normalize_weights(
        result.x
    )

    candidate_violation = float(
        np.max(
            constraint_violations(
                candidate
            )
        )
    )


    if candidate_violation <= 1e-4:

        print(
            "[FALLBACK] Solução do SLSQP é "
            "numericamente aceitável apesar do status."
        )

        result.x = candidate

        result.message = (
            "SLSQP sem flag de sucesso, "
            "mas solução dentro da tolerância."
        )

        return (
            candidate,
            result,
            masks
        )


    # Último fallback: usa o melhor ponto de viabilidade.
    # O scanner continua, mas deixa explícito que não houve
    # otimização de risco válida.
    print(
        "[FALLBACK] Usando melhor carteira viável encontrada. "
        f"Violação máxima={best_violation:.8f}"
    )

    result.x = best_feasible

    result.success = False

    result.message = (
        "Fallback para melhor ponto viável; "
        f"otimizador não convergiu ({result.message})."
    )

    return (
        best_feasible,
        result,
        masks
    )


# ============================================================
# 11. EXECUÇÃO OPERACIONAL
# ============================================================

def _execution_fraction(decision):

    mapping = {

        "ENTRADA FORTE":
            EXECUTION_STRONG,

        "ENTRADA APROVADA":
            EXECUTION_APPROVED,

        "ENTRADA TÁTICA":
            EXECUTION_TACTICAL,

        "AGUARDAR CONFIRMAÇÃO":
            EXECUTION_WAIT,

        "FUNDAMENTO FORTE — AGUARDAR GATILHO":
            EXECUTION_WAIT,

        "AGUARDAR":
            EXECUTION_WAIT,

    }


    return mapping.get(
        decision,
        0.0
    )


def _final_status(row):

    decision = row[
        "decisao_operacional"
    ]


    if decision == "ENTRADA FORTE":

        return "COMPRAR AGORA"


    if decision == "ENTRADA APROVADA":

        return "COMPRAR PARCIAL"


    if decision == "ENTRADA TÁTICA":

        return "ENTRADA MENOR"


    if (
        row[
            "fundamental_score_final"
        ] >= 82
    ):

        return "RESERVA ESTRATÉGICA"


    return "AGUARDAR"


# ============================================================
# 12. DIAGNÓSTICOS
# ============================================================

def _portfolio_diagnostics(
    portfolio,
    cov_annual,
    raw_returns,
    robust_returns,
    extreme_count,
    masks=None
):

    # ========================================================
    # ALINHAMENTO DE ORDEM
    # ========================================================
    #
    # As máscaras precisam ser construídas na mesma ordem dos
    # pesos usados nos diagnósticos. Isso evita exposição por
    # categoria/segmento incorreta quando o DataFrame é
    # reordenado para exibição.
    #
    masks = _build_masks(
        portfolio
    )

    w = (

        portfolio[
            "peso_estrategico"
        ]

        .values
        .astype(float)

    )


    # ========================================================
    # SCORES
    # ========================================================

    fundamental_score = float(

        w
        @
        portfolio[
            "fundamental_score_final"
        ].values

    )


    technical_score = float(

        w
        @
        portfolio[
            "technical_score"
        ].values

    )


    institutional_score = float(

        w
        @
        portfolio[
            "institutional_score"
        ].values

    )


    # ========================================================
    # DY
    # ========================================================

    if "dy_12m" in portfolio.columns:

        dy_values = (

            portfolio[
                "dy_12m"
            ]

            .fillna(0)

            .values

        )

        dy = float(
            w @ dy_values
        )

    else:

        dy = np.nan


    # ========================================================
    # VOL
    # ========================================================

    volatility = float(

        np.sqrt(

            w
            @
            cov_annual
            @
            w

        )

    )


    # ========================================================
    # HHI / N EFETIVO
    # ========================================================

    hhi = float(
        np.sum(
            w ** 2
        )
    )


    effective_fiis = (
        1 / hhi
        if hhi > 0
        else np.nan
    )


    # ========================================================
    # EXECUÇÃO
    # ========================================================

    executable = float(

        portfolio[
            "peso_executavel"
        ].sum()

    )


    reserved = float(

        portfolio[
            "peso_reservado"
        ].sum()

    )


    # ========================================================
    # EXPOSIÇÕES
    # ========================================================

    exposure = {

        "papel":
            _sum_mask(
                w,
                masks["paper"]
            ),

        "tijolo":
            _sum_mask(
                w,
                masks["brick"]
            ),

        "alternativo":
            _sum_mask(
                w,
                masks["alternative"]
            ),

        "high_yield":
            _sum_mask(
                w,
                masks["high_yield"]
            ),

        "logistica":
            _sum_mask(
                w,
                masks["logistics"]
            ),

        "shopping":
            _sum_mask(
                w,
                masks["shopping"]
            ),

        "renda_urbana":
            _sum_mask(
                w,
                masks["urban_income"]
            ),

        "lajes":
            _sum_mask(
                w,
                masks["offices"]
            ),

    }


    return {

        "fundamental_score":
            fundamental_score,

        "technical_score":
            technical_score,

        "institutional_score":
            institutional_score,

        "dy_12m":
            dy,

        "volatilidade_robusta":
            volatility,

        "hhi":
            hhi,

        "numero_efetivo_fiis":
            effective_fiis,

        "peso_executavel":
            executable,

        "peso_reservado":
            reserved,

        "eventos_extremos":
            extreme_count.to_dict(),

        "exposicao":
            exposure,

        "pregoes_risco":
            len(
                robust_returns
            ),

    }


# ============================================================
# 13. MOTOR PRINCIPAL
# ============================================================

def build_portfolio(
    fundamentals,
    technical
):

    print()
    print("=" * 110)
    print("FII INSTITUTIONAL SCORE + PORTFOLIO ENGINE")
    print("=" * 110)


    # ========================================================
    # RANKING INSTITUCIONAL
    # ========================================================

    ranking = _build_ranking(

        fundamentals,
        technical

    )


    print(
        f"FIIs no ranking institucional: "
        f"{len(ranking)}"
    )


    # ========================================================
    # CANDIDATOS
    # ========================================================

    portfolio = _select_portfolio_candidates(
        ranking
    )


    print(
        f"FIIs selecionados: "
        f"{len(portfolio)}"
    )


    tickers = (
        portfolio[
            "ticker"
        ]
        .tolist()
    )


    # ========================================================
    # RISCO
    # ========================================================

    print(
        "Carregando histórico de risco..."
    )

    prices = _download_portfolio_prices(
        tickers
    )

    print(
        "Histórico de risco OK."
    )


    raw_returns, robust_returns, extreme_count = (

        _build_robust_returns(
            prices
        )

    )


    cov_annual = _build_covariance(
        robust_returns
    )

    print(
        "Matriz de covariância OK."
    )


    # ========================================================
    # PESOS INICIAIS
    # ========================================================

    w0 = _initial_weights(
        portfolio
    )


    # ========================================================
    # OTIMIZAÇÃO
    # ========================================================

    print(
        "Otimizando pesos..."
    )

    weights, optimization_result, masks = (

        _optimize_portfolio(

            portfolio,
            cov_annual,
            w0

        )

    )


    portfolio[
        "peso_estrategico"
    ] = weights


    portfolio[
        "peso_estrategico_pct"
    ] = (
        weights * 100
    )


    # ========================================================
    # EXECUÇÃO
    # ========================================================

    portfolio[
        "fracao_execucao"
    ] = (

        portfolio[
            "decisao_operacional"
        ]

        .apply(
            _execution_fraction
        )

    )


    portfolio[
        "peso_executavel"
    ] = (

        portfolio[
            "peso_estrategico"
        ]

        *

        portfolio[
            "fracao_execucao"
        ]

    )


    portfolio[
        "peso_executavel_pct"
    ] = (

        portfolio[
            "peso_executavel"
        ]
        *
        100

    )


    portfolio[
        "peso_reservado"
    ] = (

        portfolio[
            "peso_estrategico"
        ]

        -

        portfolio[
            "peso_executavel"
        ]

    )


    portfolio[
        "peso_reservado_pct"
    ] = (

        portfolio[
            "peso_reservado"
        ]
        *
        100

    )


    portfolio[
        "status_final"
    ] = portfolio.apply(

        _final_status,

        axis=1

    )


    # ========================================================
    # MARCA CANDIDATOS NO RANKING
    # ========================================================

    ranking[
        "candidato_carteira"
    ] = (

        ranking[
            "ticker"
        ]

        .isin(
            portfolio[
                "ticker"
            ]
        )

    )


    # ========================================================
    # DIAGNÓSTICOS
    # ========================================================

    diagnostics = _portfolio_diagnostics(

        portfolio,

        cov_annual,

        raw_returns,

        robust_returns,

        extreme_count,

        masks,

    )


    diagnostics[
        "optimization_success"
    ] = bool(
        optimization_result.success
    )


    diagnostics[
        "optimization_message"
    ] = optimization_result.message


    # ========================================================
    # ORDENAÇÃO FINAL — SOMENTE PARA SAÍDA
    # ========================================================
    #
    # Até este ponto a ordem do DataFrame deve permanecer
    # idêntica à ordem usada na matriz de covariância e na
    # otimização. Só agora podemos ordenar por peso para
    # relatório, CSV e visualização.
    #
    portfolio = (

        portfolio

        .sort_values(
            "peso_estrategico",
            ascending=False
        )

        .reset_index(
            drop=True
        )

    )


    # ========================================================
    # SALVA
    # ========================================================

    if SAVE_RANKING:

        ranking.to_csv(

            RANKING_FILE,

            index=False,

            encoding="utf-8-sig",

        )


    if SAVE_PORTFOLIO:

        portfolio.to_csv(

            PORTFOLIO_FILE,

            index=False,

            encoding="utf-8-sig",

        )


    # ========================================================
    # RELATÓRIO CONSOLE
    # ========================================================

    print()
    print("=" * 110)
    print("CARTEIRA ESTRATÉGICA")
    print("=" * 110)


    cols = [

        "ticker",
        "categoria_motor",
        "segmento",

        "fundamental_score_final",
        "technical_score",
        "institutional_score",

        "peso_estrategico_pct",

        "decisao_operacional",
        "status_final",

    ]


    print(

        portfolio[
            cols
        ]

        .to_string(
            index=False
        )

    )


    print()
    print("=" * 110)
    print("RESUMO")
    print("=" * 110)


    print(
        f"Fundamental Score        : "
        f"{diagnostics['fundamental_score']:.2f}"
    )

    print(
        f"Technical Score          : "
        f"{diagnostics['technical_score']:.2f}"
    )

    print(
        f"Institutional Score      : "
        f"{diagnostics['institutional_score']:.2f}"
    )

    print(
        f"DY 12m indicativo        : "
        f"{diagnostics['dy_12m']:.2%}"
    )

    print(
        f"Volatilidade robusta     : "
        f"{diagnostics['volatilidade_robusta']:.2%}"
    )

    print(
        f"Número efetivo de FIIs   : "
        f"{diagnostics['numero_efetivo_fiis']:.2f}"
    )

    print(
        f"Executável agora         : "
        f"{diagnostics['peso_executavel']:.2%}"
    )

    print(
        f"Capital reservado        : "
        f"{diagnostics['peso_reservado']:.2%}"
    )


    print()
    print("EXPOSIÇÕES:")


    for key, value in (
        diagnostics[
            "exposicao"
        ].items()
    ):

        print(
            f"{key:<20}: "
            f"{value:.2%}"
        )


    # Auditoria independente do alinhamento de máscaras
    exposicao_categoria_check = (
        portfolio
        .groupby(
            "categoria_motor"
        )[
            "peso_estrategico"
        ]
        .sum()
    )

    print()
    print("AUDITORIA DE EXPOSIÇÃO POR CATEGORIA:")

    for categoria, peso in exposicao_categoria_check.items():

        print(
            f"{categoria:<20}: "
            f"{peso:.2%}"
        )


    # ========================================================
    # EVENTOS EXTREMOS
    # ========================================================

    extreme = {

        ticker: count

        for ticker, count
        in diagnostics[
            "eventos_extremos"
        ].items()

        if count > 0

    }


    if extreme:

        print()
        print(
            "ATENÇÃO — retornos limitados apenas "
            "na matriz de risco:"
        )

        for ticker, count in extreme.items():

            print(
                f"  {ticker}: "
                f"{count} evento(s)"
            )


    print()
    print("=" * 110)
    print("PORTFOLIO ENGINE CONCLUÍDO")
    print("=" * 110)


    return {

        "ranking":
            ranking,

        "portfolio":
            portfolio,

        "diagnostics":
            diagnostics,

    }
