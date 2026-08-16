# ============================================================
# FII INSTITUTIONAL SCANNER
# engine/data_engine.py
# ============================================================

from pathlib import Path
import time
import warnings
import io
import re
import zipfile
import unicodedata
from difflib import SequenceMatcher
from urllib.request import Request, urlopen

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
# HIGIENE DE SÉRIE / EVENTOS ESTRUTURAIS
# ============================================================
#
# Objetivo:
# - detectar saltos incompatíveis com movimento normal de mercado;
# - diferenciar um evento estrutural persistente de uma oscilação real;
# - retroajustar o histórico anterior ao evento, preservando o nível atual;
# - nunca "apagar" silenciosamente retornos normais.
#
STRUCTURAL_JUMP_MIN = 0.50
STRUCTURAL_WINDOW = 5
STRUCTURAL_FACTOR_TOLERANCE = 0.20

HISTORY_CLEAN_DIR = Path(DATA_DIR) / "history_clean"
VALUATION_CACHE_FILE = Path(DATA_DIR) / "valuation_cache.csv"

# ============================================================
# VALUATION OFICIAL — FALLBACK CVM
# ============================================================
#
# O Yahoo continuará sendo a primeira fonte por ser leve.
# Quando P/VP não estiver disponível, usamos o Informe Mensal
# Estruturado oficial da CVM para obter:
#   Patrimônio Líquido / Cotas Emitidas = VP por cota
#   Preço atual / VP por cota = P/VP
#
# O ZIP é baixado UMA VEZ por execução.
#
CVM_FII_YEAR = 2026
CVM_FII_MONTHLY_URL = (
    "https://dados.cvm.gov.br/dados/FII/DOC/"
    f"INF_MENSAL/DADOS/inf_mensal_fii_{CVM_FII_YEAR}.zip"
)

# Aliases econômicos específicos. Servem somente para identificar
# de forma conservadora o fundo no arquivo oficial da CVM.
FII_CVM_ALIASES = {
    "KNCR11": "KINEA RENDIMENTOS IMOBILIARIOS",
    "MXRF11": "MAXI RENDA",
    "KNSC11": "KINEA SECURITIES",
    "KNIP11": "KINEA INDICES DE PRECOS",
    "VRTA11": "FATOR VERITA",
    "KNHY11": "KINEA HIGH YIELD CRI",
    "XPCI11": "XP CREDITO IMOBILIARIO",
    "KCRE11": "KINEA CREDITAS",
    "RZAK11": "RIZA AKIN",
    "BCRI11": "BANESTES RECEBIVEIS IMOBILIARIOS",
    "OUJP11": "OURINVEST JPP",
    "DEVA11": "DEVANT RECEBIVEIS IMOBILIARIOS",
    "HCTR11": "HECTARE CE",
    "URPR11": "URCA PRIME RENDA",
    "XPLG11": "XP LOG",
    "HGLG11": "PATRIA LOG",
    "XPML11": "XP MALLS",
    "HGRU11": "PATRIA RENDA URBANA",
    "HGBS11": "HEDGE BRASIL SHOPPING",
    "ALZR11": "ALIANZA TRUST RENDA IMOBILIARIA",
    "GTWR11": "GREEN TOWERS",
    "HSML11": "HSI MALLS",
    "SNEL11": "SUNO ENERGIA",
    "LVBI11": "VBI LOGISTICO",
    "VISC11": "VINCI SHOPPING CENTERS",
    "BRCO11": "BRESCO LOGISTICA",
    "VILG11": "VINCI LOGISTICA",
    "JSRE11": "JS REAL ESTATE",
    "HSLG11": "HSI LOGISTICA",
    "RCRB11": "RIO BRAVO RENDA CORPORATIVA",
    "TRXF11": "TRX REAL ESTATE",
    "KNRI11": "KINEA RENDA IMOBILIARIA",
    "VGHF11": "VALORA HEDGE FUND",
    "KFOF11": "KINEA FUNDO DE FUNDOS",
    "JSAF11": "JS ATIVOS FINANCEIROS",
    "TGAR11": "TG ATIVO REAL",
}


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


def _detect_structural_events(df):

    events = []

    if df is None or df.empty:
        return events

    if "Close" not in df.columns:
        return events

    close = pd.to_numeric(
        df["Close"],
        errors="coerce"
    )

    valid = close.dropna()

    if len(valid) < (
        STRUCTURAL_WINDOW * 2 + 2
    ):
        return events

    returns = (
        valid
        .pct_change(fill_method=None)
    )

    candidate_dates = returns[
        returns.abs() >= STRUCTURAL_JUMP_MIN
    ].index

    for event_date in candidate_dates:

        loc = valid.index.get_loc(
            event_date
        )

        if isinstance(loc, slice):
            continue

        if loc < STRUCTURAL_WINDOW:
            continue

        if (
            loc + STRUCTURAL_WINDOW
            >= len(valid)
        ):
            continue

        before = valid.iloc[
            loc - STRUCTURAL_WINDOW:
            loc
        ]

        after = valid.iloc[
            loc:
            loc + STRUCTURAL_WINDOW
        ]

        if before.empty or after.empty:
            continue

        before_med = float(
            before.median()
        )

        after_med = float(
            after.median()
        )

        if (
            before_med <= 0
            or after_med <= 0
        ):
            continue

        factor = (
            after_med
            /
            before_med
        )

        jump_factor = (
            valid.iloc[loc]
            /
            valid.iloc[loc - 1]
        )

        # Um evento estrutural verdadeiro tende a criar um
        # novo patamar persistente. Ex.: grupamento/desdobramento
        # ou erro de escala na origem de dados.
        persistence_error = abs(
            factor - jump_factor
        ) / max(
            abs(jump_factor),
            1e-12
        )

        if (
            persistence_error
            <= STRUCTURAL_FACTOR_TOLERANCE
            and (
                factor >= 1.50
                or factor <= (1 / 1.50)
            )
        ):

            events.append(
                {
                    "date": event_date,
                    "factor": float(factor),
                    "jump_return": float(
                        returns.loc[event_date]
                    ),
                    "persistence_error": float(
                        persistence_error
                    ),
                }
            )

    return events


def _repair_structural_events(ticker, df):

    if df is None or df.empty:
        return df, []

    clean = df.copy()

    events = _detect_structural_events(
        clean
    )

    if not events:
        return clean, []

    # Aplicamos em ordem cronológica.
    events = sorted(
        events,
        key=lambda x: x["date"]
    )

    price_columns = [
        col
        for col in [
            "Open",
            "High",
            "Low",
            "Close",
        ]
        if col in clean.columns
    ]

    adjusted_events = []

    for event in events:

        event_date = event["date"]
        factor = event["factor"]

        if (
            not np.isfinite(factor)
            or factor <= 0
        ):
            continue

        mask_prior = (
            clean.index
            <
            event_date
        )

        if not mask_prior.any():
            continue

        # Retroajuste: traz o histórico antigo para a mesma
        # escala do patamar posterior, preservando o preço atual.
        clean.loc[
            mask_prior,
            price_columns
        ] = (
            clean.loc[
                mask_prior,
                price_columns
            ]
            * factor
        )

        adjusted_events.append(
            event
        )

        print(
            f"[EVENTO ESTRUTURAL] {ticker} | "
            f"{pd.Timestamp(event_date).date()} | "
            f"retorno bruto={event['jump_return']:+.2%} | "
            f"fator={factor:.4f} | "
            f"histórico anterior retroajustado."
        )

    return clean, adjusted_events


def _save_clean_history(ticker, history):

    if history is None or history.empty:
        return

    HISTORY_CLEAN_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    output = (
        HISTORY_CLEAN_DIR
        /
        f"{ticker}.csv"
    )

    history.to_csv(
        output,
        encoding="utf-8-sig"
    )


def _load_valuation_cache():

    if not VALUATION_CACHE_FILE.exists():
        return {}

    try:

        cache = pd.read_csv(
            VALUATION_CACHE_FILE
        )

        if cache.empty or "ticker" not in cache.columns:
            return {}

        records = {}

        for _, row in cache.iterrows():

            ticker = str(
                row.get(
                    "ticker",
                    ""
                )
            ).strip()

            if not ticker:
                continue

            records[ticker] = {
                "pvp_data": _safe_float(
                    row.get(
                        "pvp_data"
                    )
                ),
                "vp_cota_data": _safe_float(
                    row.get(
                        "vp_cota_data"
                    )
                ),
                "fonte_valuation": row.get(
                    "fonte_valuation",
                    "CACHE"
                ),
            }

        return records

    except Exception:
        return {}


def _save_valuation_cache(records):

    if not records:
        return

    Path(DATA_DIR).mkdir(
        parents=True,
        exist_ok=True
    )

    rows = []

    for ticker, data in records.items():

        rows.append(
            {
                "ticker": ticker,
                "pvp_data": data.get(
                    "pvp_data",
                    np.nan
                ),
                "vp_cota_data": data.get(
                    "vp_cota_data",
                    np.nan
                ),
                "fonte_valuation": data.get(
                    "fonte_valuation",
                    "SEM_DADO"
                ),
            }
        )

    pd.DataFrame(
        rows
    ).to_csv(
        VALUATION_CACHE_FILE,
        index=False,
        encoding="utf-8-sig"
    )


def _collect_valuation(ticker, preco_atual=np.nan):

    result = {
        "pvp_data": np.nan,
        "vp_cota_data": np.nan,
        "fonte_valuation": "SEM_DADO",

        "cnpj_cvm": np.nan,
        "nome_cvm": np.nan,
        "data_referencia_cvm": pd.NaT,
        "pl_cvm": np.nan,
        "cotas_emitidas_cvm": np.nan,
        "cotistas_cvm": np.nan,
        "score_match_cvm": np.nan,
        "cobertura_match_cvm": np.nan,
    }

    symbol = f"{ticker}.SA"

    try:

        tk = yf.Ticker(
            symbol
        )

        info = {}

        try:
            info = tk.get_info() or {}
        except Exception:
            try:
                info = tk.info or {}
            except Exception:
                info = {}

        # 1) P/VP direto
        pvp = _safe_float(
            info.get(
                "priceToBook"
            )
        )

        if np.isfinite(pvp) and pvp > 0:

            result[
                "pvp_data"
            ] = pvp

            result[
                "fonte_valuation"
            ] = "YAHOO_PRICE_TO_BOOK"

            if (
                np.isfinite(preco_atual)
                and preco_atual > 0
            ):

                result[
                    "vp_cota_data"
                ] = (
                    preco_atual
                    /
                    pvp
                )

            return result

        # 2) Book value por cota
        book_value = _safe_float(
            info.get(
                "bookValue"
            )
        )

        price = _safe_float(
            preco_atual
        )

        if (
            np.isfinite(book_value)
            and book_value > 0
            and np.isfinite(price)
            and price > 0
        ):

            pvp_calc = (
                price
                /
                book_value
            )

            if (
                np.isfinite(pvp_calc)
                and pvp_calc > 0
            ):

                result[
                    "pvp_data"
                ] = pvp_calc

                result[
                    "vp_cota_data"
                ] = book_value

                result[
                    "fonte_valuation"
                ] = "YAHOO_BOOK_VALUE"

                return result

    except Exception:
        pass

    return result


def _normalize_text(value):

    if value is None:
        return ""

    text = str(value).upper().strip()

    text = unicodedata.normalize(
        "NFKD",
        text
    )

    text = "".join(
        ch
        for ch in text
        if not unicodedata.combining(ch)
    )

    text = re.sub(
        r"[^A-Z0-9 ]+",
        " ",
        text
    )

    stop_words = {
        "FUNDO",
        "FUNDOS",
        "DE",
        "DO",
        "DA",
        "DOS",
        "DAS",
        "INVESTIMENTO",
        "INVESTIMENTOS",
        "IMOBILIARIO",
        "IMOBILIARIA",
        "FII",
        "RL",
        "RESPONSABILIDADE",
        "LIMITADA",
        "CLASSE",
        "COTAS",
        "COTA",
    }

    tokens = [
        tok
        for tok in text.split()
        if tok not in stop_words
    ]

    return " ".join(tokens)


def _normalize_header(value):

    return (
        _normalize_text(value)
        .replace(" ", "_")
    )


def _first_existing_column(columns, candidates):

    normalized = {
        _normalize_header(col): col
        for col in columns
    }

    for candidate in candidates:

        candidate_norm = (
            _normalize_header(candidate)
        )

        if candidate_norm in normalized:
            return normalized[
                candidate_norm
            ]

    # fallback por conteúdo parcial
    for norm_name, original in normalized.items():

        for candidate in candidates:

            candidate_norm = (
                _normalize_header(candidate)
            )

            if (
                candidate_norm
                and candidate_norm in norm_name
            ):
                return original

    return None


def _read_cvm_csv_from_zip(zf, member):

    raw = zf.read(
        member
    )

    for encoding in (
        "utf-8-sig",
        "latin1",
        "cp1252",
    ):

        try:

            return pd.read_csv(
                io.BytesIO(raw),
                sep=";",
                encoding=encoding,
                low_memory=False,
            )

        except Exception:
            pass

    return pd.DataFrame()


def _download_cvm_monthly_base():

    try:

        request = Request(
            CVM_FII_MONTHLY_URL,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 "
                    "FII-Institutional-Scanner/1.0"
                )
            },
        )

        with urlopen(
            request,
            timeout=45,
        ) as response:

            content = response.read()

    except Exception as exc:

        print(
            "[AVISO] CVM | falha ao baixar "
            f"Informe Mensal: {exc}"
        )

        return pd.DataFrame()

    try:

        zf = zipfile.ZipFile(
            io.BytesIO(content)
        )

    except Exception as exc:

        print(
            "[AVISO] CVM | ZIP inválido: "
            f"{exc}"
        )

        return pd.DataFrame()

    pieces = []

    for member in zf.namelist():

        if not member.lower().endswith(".csv"):
            continue

        df = _read_cvm_csv_from_zip(
            zf,
            member
        )

        if df.empty:
            continue

        cnpj_col = _first_existing_column(
            df.columns,
            [
                "CNPJ_Fundo_Classe",
                "CNPJ_Fundo",
                "CNPJ",
            ]
        )

        date_col = _first_existing_column(
            df.columns,
            [
                "Data_Referencia",
                "DT_COMPTC",
                "Data_Competencia",
            ]
        )

        name_col = _first_existing_column(
            df.columns,
            [
                "Nome_Fundo_Classe",
                "Nome_Fundo",
                "Denominacao_Social",
                "DENOM_SOCIAL",
            ]
        )

        pl_col = _first_existing_column(
            df.columns,
            [
                "Patrimonio_Liquido",
                "VL_PATRIM_LIQ",
            ]
        )

        shares_col = _first_existing_column(
            df.columns,
            [
                "Cotas_Emitidas",
                "Numero_Cotas_Emitidas",
                "Qtd_Cotas_Emitidas",
            ]
        )

        cotistas_col = _first_existing_column(
            df.columns,
            [
                "Total_Numero_Cotistas",
                "Numero_Cotistas",
                "NR_COTST",
            ]
        )

        # Só aproveitamos arquivos que possuam identificador e
        # pelo menos uma informação econômica relevante.
        if (
            cnpj_col is None
            or date_col is None
            or (
                pl_col is None
                and shares_col is None
                and cotistas_col is None
            )
        ):
            continue

        out = pd.DataFrame()

        out[
            "cnpj_cvm"
        ] = (
            df[
                cnpj_col
            ]
            .astype(str)
            .str.replace(
                r"\D",
                "",
                regex=True
            )
        )

        out[
            "data_referencia_cvm"
        ] = pd.to_datetime(
            df[
                date_col
            ],
            errors="coerce"
        )

        if name_col is not None:

            out[
                "nome_cvm"
            ] = (
                df[
                    name_col
                ]
                .astype(str)
            )

        else:

            out[
                "nome_cvm"
            ] = np.nan

        if pl_col is not None:

            out[
                "pl_cvm"
            ] = pd.to_numeric(
                df[
                    pl_col
                ],
                errors="coerce"
            )

        else:

            out[
                "pl_cvm"
            ] = np.nan

        if shares_col is not None:

            out[
                "cotas_emitidas_cvm"
            ] = pd.to_numeric(
                df[
                    shares_col
                ],
                errors="coerce"
            )

        else:

            out[
                "cotas_emitidas_cvm"
            ] = np.nan

        if cotistas_col is not None:

            out[
                "cotistas_cvm"
            ] = pd.to_numeric(
                df[
                    cotistas_col
                ],
                errors="coerce"
            )

        else:

            out[
                "cotistas_cvm"
            ] = np.nan

        out = out[
            out[
                "cnpj_cvm"
            ].str.len() == 14
        ]

        if not out.empty:
            pieces.append(
                out
            )

    if not pieces:

        print(
            "[AVISO] CVM | nenhuma tabela útil "
            "foi identificada no ZIP."
        )

        return pd.DataFrame()

    base = pd.concat(
        pieces,
        ignore_index=True
    )

    # Combina tabela geral e complementos pela mesma chave.
    def first_valid(series):

        valid = series.dropna()

        if valid.empty:
            return np.nan

        return valid.iloc[-1]

    base = (
        base
        .sort_values(
            [
                "cnpj_cvm",
                "data_referencia_cvm",
            ]
        )
        .groupby(
            [
                "cnpj_cvm",
                "data_referencia_cvm",
            ],
            as_index=False,
        )
        .agg(
            {
                "nome_cvm": first_valid,
                "pl_cvm": first_valid,
                "cotas_emitidas_cvm": first_valid,
                "cotistas_cvm": first_valid,
            }
        )
    )

    return base


def _alias_match_score(alias, candidate):

    a = _normalize_text(
        alias
    )

    b = _normalize_text(
        candidate
    )

    if not a or not b:
        return 0.0, 0.0

    a_tokens = set(
        a.split()
    )

    b_tokens = set(
        b.split()
    )

    if not a_tokens:
        return 0.0, 0.0

    coverage = (
        len(
            a_tokens
            &
            b_tokens
        )
        /
        len(
            a_tokens
        )
    )

    similarity = (
        SequenceMatcher(
            None,
            a,
            b
        )
        .ratio()
    )

    score = (
        coverage * 0.75
        +
        similarity * 0.25
    )

    return score, coverage


def _build_cvm_valuation_map(tickers, prices):

    cvm = _download_cvm_monthly_base()

    if cvm.empty:
        return {}

    # Mantém apenas a observação mais recente de cada CNPJ.
    cvm = (
        cvm
        .sort_values(
            "data_referencia_cvm"
        )
        .groupby(
            "cnpj_cvm",
            as_index=False
        )
        .tail(1)
        .reset_index(
            drop=True
        )
    )

    result = {}

    for ticker in tickers:

        alias = FII_CVM_ALIASES.get(
            ticker
        )

        if not alias:
            continue

        scored = []

        for idx, row in cvm.iterrows():

            score, coverage = (
                _alias_match_score(
                    alias,
                    row.get(
                        "nome_cvm",
                        ""
                    )
                )
            )

            if coverage >= 0.66:

                scored.append(
                    (
                        score,
                        coverage,
                        idx,
                    )
                )

        if not scored:
            continue

        scored.sort(
            reverse=True
        )

        best_score, best_coverage, best_idx = (
            scored[0]
        )

        second_score = (
            scored[1][0]
            if len(scored) > 1
            else 0.0
        )

        margin = (
            best_score
            -
            second_score
        )

        # Regra conservadora:
        # - alias quase completo, ou
        # - cobertura boa + score alto + margem suficiente.
        accepted = (
            (
                best_coverage >= 0.95
                and best_score >= 0.78
            )
            or
            (
                best_coverage >= 0.75
                and best_score >= 0.80
                and margin >= 0.03
            )
        )

        if not accepted:
            continue

        row = cvm.loc[
            best_idx
        ]

        pl = _safe_float(
            row.get(
                "pl_cvm"
            )
        )

        cotas = _safe_float(
            row.get(
                "cotas_emitidas_cvm"
            )
        )

        preco = _safe_float(
            prices.get(
                ticker,
                np.nan
            )
        )

        if (
            not np.isfinite(pl)
            or pl <= 0
            or not np.isfinite(cotas)
            or cotas <= 0
            or not np.isfinite(preco)
            or preco <= 0
        ):
            continue

        vp_cota = (
            pl
            /
            cotas
        )

        pvp = (
            preco
            /
            vp_cota
        )

        # Sanidade contábil. Valores fora desta faixa ficam
        # para revisão e não entram automaticamente no score.
        if (
            not np.isfinite(vp_cota)
            or vp_cota <= 0
            or not np.isfinite(pvp)
            or pvp < 0.05
            or pvp > 5.0
        ):
            continue

        result[
            ticker
        ] = {
            "pvp_data": pvp,
            "vp_cota_data": vp_cota,
            "fonte_valuation": "CVM_OFICIAL",
            "cnpj_cvm": row.get(
                "cnpj_cvm"
            ),
            "nome_cvm": row.get(
                "nome_cvm"
            ),
            "data_referencia_cvm": row.get(
                "data_referencia_cvm"
            ),
            "pl_cvm": pl,
            "cotas_emitidas_cvm": cotas,
            "cotistas_cvm": _safe_float(
                row.get(
                    "cotistas_cvm"
                )
            ),
            "score_match_cvm": best_score,
            "cobertura_match_cvm": best_coverage,
        }

    return result


def _download_history(ticker):

    yahoo_ticker = f"{ticker}.SA"

    # ========================================================
    # POLÍTICA DE RETRY
    # ========================================================
    #
    # Objetivo:
    # - evitar que um rate limit temporário elimine um FII;
    # - não inventar dados;
    # - tentar duas rotas do Yahoo;
    # - manter o pipeline enxuto.
    #
    # Estratégia:
    # 1. yf.download com configuração principal;
    # 2. repetir com espera progressiva;
    # 3. fallback via Ticker.history;
    # 4. última tentativa sem repair.
    #
    max_attempts = 3

    for attempt in range(1, max_attempts + 1):

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

            if df is not None and not df.empty:

                df = _normalize_columns(
                    df.copy()
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

                if not df.empty:

                    if attempt > 1:

                        print(
                            f"[RECUPERADO] {ticker} "
                            f"na tentativa {attempt}."
                        )

                    df, structural_events = (
                        _repair_structural_events(
                            ticker,
                            df
                        )
                    )

                    df.attrs[
                        "structural_events"
                    ] = structural_events

                    _save_clean_history(
                        ticker,
                        df
                    )

                    return df

        except Exception as exc:

            print(
                f"[AVISO] {ticker} | "
                f"tentativa {attempt}/{max_attempts} "
                f"falhou: {exc}"
            )


        # ----------------------------------------------------
        # FALLBACK VIA Ticker.history
        # ----------------------------------------------------

        try:

            tk = yf.Ticker(
                yahoo_ticker
            )

            df_alt = tk.history(
                period=PRICE_HISTORY,
                interval="1d",
                auto_adjust=YAHOO_AUTO_ADJUST,
                repair=YAHOO_REPAIR,
                actions=False,
            )

            if df_alt is not None and not df_alt.empty:

                df_alt = _normalize_columns(
                    df_alt.copy()
                )

                df_alt.index = pd.to_datetime(
                    df_alt.index,
                    errors="coerce"
                )

                df_alt = df_alt[
                    ~df_alt.index.isna()
                ]

                df_alt = df_alt[
                    ~df_alt.index.duplicated(
                        keep="last"
                    )
                ]

                df_alt = df_alt.sort_index()

                if not df_alt.empty:

                    print(
                        f"[RECUPERADO] {ticker} "
                        f"via Ticker.history."
                    )

                    df_alt, structural_events = (
                        _repair_structural_events(
                            ticker,
                            df_alt
                        )
                    )

                    df_alt.attrs[
                        "structural_events"
                    ] = structural_events

                    _save_clean_history(
                        ticker,
                        df_alt
                    )

                    return df_alt

        except Exception as exc:

            print(
                f"[AVISO] {ticker} | "
                f"fallback history falhou: {exc}"
            )


        # ----------------------------------------------------
        # ESPERA PROGRESSIVA
        # ----------------------------------------------------

        if attempt < max_attempts:

            wait_seconds = (
                2 ** (attempt - 1)
            )

            print(
                f"[RETRY] {ticker} em "
                f"{wait_seconds}s..."
            )

            time.sleep(
                wait_seconds
            )


    # ========================================================
    # ÚLTIMA TENTATIVA — SEM REPAIR
    # ========================================================

    try:

        df = yf.download(
            yahoo_ticker,
            period=PRICE_HISTORY,
            interval="1d",
            auto_adjust=YAHOO_AUTO_ADJUST,
            repair=False,
            progress=False,
            threads=False,
        )

        if df is not None and not df.empty:

            df = _normalize_columns(
                df.copy()
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

            if not df.empty:

                print(
                    f"[RECUPERADO] {ticker} "
                    f"na última tentativa sem repair."
                )

                df, structural_events = (
                    _repair_structural_events(
                        ticker,
                        df
                    )
                )

                df.attrs[
                    "structural_events"
                ] = structural_events

                _save_clean_history(
                    ticker,
                    df
                )

                return df

    except Exception as exc:

        print(
            f"[AVISO] {ticker} | "
            f"última tentativa falhou: {exc}"
        )


    # ========================================================
    # FALHA DEFINITIVA
    # ========================================================

    print(
        f"[FALHA DE DADOS] {ticker} não foi "
        f"coletado após todas as tentativas. "
        f"O ativo não será considerado aprovado "
        f"pela Regra Zero nesta execução."
    )

    return pd.DataFrame()


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

        "eventos_estruturais_detectados": 0,

        "dados_preco_ok": False,

        "status_coleta": "SEM_DADOS",

        "pvp_data": np.nan,

        "vp_cota_data": np.nan,

        "fonte_valuation": "SEM_DADO",
    }

    if history.empty:
        return result

    if "Close" not in history.columns:
        return result

    structural_events = history.attrs.get(
        "structural_events",
        []
    )

    result[
        "eventos_estruturais_detectados"
    ] = len(
        structural_events
    )

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

    result["status_coleta"] = "OK"


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

    structural = df[
        df[
            "eventos_estruturais_detectados"
        ] > 0
    ]

    print(
        "Com evento diário extremo  :",
        len(extreme)
    )

    print(
        "Com evento estrutural corrigido:",
        len(structural)
    )


    failed_collection = df[
        df[
            "status_coleta"
        ] != "OK"
    ]

    print(
        "Falhas definitivas de coleta:",
        len(
            failed_collection
        )
    )

    valuation_ok = df[
        pd.to_numeric(
            df[
                "pvp_data"
            ],
            errors="coerce"
        ).notna()
    ]

    print(
        "P/VP disponível no Data Engine:",
        len(
            valuation_ok
        )
    )

    if not valuation_ok.empty:

        print()
        print(
            "FONTES DE VALUATION"
        )

        print(
            valuation_ok[
                "fonte_valuation"
            ]
            .value_counts(
                dropna=False
            )
            .to_string()
        )

        print()
        print(
            "COBERTURA DE VALUATION"
        )

        print(
            valuation_ok[
                [
                    "ticker",
                    "pvp_data",
                    "vp_cota_data",
                    "fonte_valuation",
                    "data_referencia_cvm",
                    "score_match_cvm",
                ]
            ]
            .sort_values(
                "ticker"
            )
            .to_string(
                index=False
            )
        )

    if not failed_collection.empty:

        print()
        print(
            "ATENÇÃO — FALHAS DE COLETA"
        )

        print(
            failed_collection[
                [
                    "ticker",
                    "status_coleta",
                    "regra_zero_aprovado",
                ]
            ]
            .to_string(
                index=False
            )
        )


    if not structural.empty:

        print()
        print(
            "EVENTOS ESTRUTURAIS CORRIGIDOS"
        )

        print(
            structural[
                [
                    "ticker",
                    "eventos_estruturais_detectados",
                    "maior_retorno_abs",
                    "volatilidade_anual",
                    "drawdown_5a",
                ]
            ]
            .to_string(
                index=False
            )
        )


    if not extreme.empty:

        print()
        print(
            "ATENÇÃO — EVENTOS EXTREMOS APÓS HIGIENE"
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

    valuation_cache = (
        _load_valuation_cache()
    )


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

        valuation = (
            _collect_valuation(
                ticker,
                metrics.get(
                    "preco",
                    np.nan
                )
            )
        )

        # Se a coleta atual não encontrou valuation,
        # reaproveitamos somente um valor previamente confirmado.
        if (
            not np.isfinite(
                _safe_float(
                    valuation.get(
                        "pvp_data"
                    )
                )
            )
        ):

            cached = valuation_cache.get(
                ticker,
                {}
            )

            cached_pvp = _safe_float(
                cached.get(
                    "pvp_data"
                )
            )

            if (
                np.isfinite(cached_pvp)
                and cached_pvp > 0
            ):

                valuation = {
                    "pvp_data": cached_pvp,
                    "vp_cota_data": _safe_float(
                        cached.get(
                            "vp_cota_data"
                        )
                    ),
                    "fonte_valuation": "CACHE_VALIDADO",
                }

        metrics.update(
            valuation
        )

        valuation_cache[
            ticker
        ] = {
            "pvp_data": metrics.get(
                "pvp_data",
                np.nan
            ),
            "vp_cota_data": metrics.get(
                "vp_cota_data",
                np.nan
            ),
            "fonte_valuation": metrics.get(
                "fonte_valuation",
                "SEM_DADO"
            ),
        }

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
    # DTYPE SEGURO PARA CAMPOS CVM
    # ========================================================

    for text_col in [
        "cnpj_cvm",
        "nome_cvm",
        "fonte_valuation",
    ]:

        if text_col in database.columns:

            database[
                text_col
            ] = database[
                text_col
            ].astype(
                "object"
            )

    if "data_referencia_cvm" in database.columns:

        database[
            "data_referencia_cvm"
        ] = pd.to_datetime(
            database[
                "data_referencia_cvm"
            ],
            errors="coerce"
        )


    # ========================================================
    # FALLBACK OFICIAL CVM — UMA COLETA POR EXECUÇÃO
    # ========================================================

    prices_map = (
        database
        .set_index(
            "ticker"
        )[
            "preco"
        ]
        .to_dict()
    )

    missing_pvp_tickers = (
        database.loc[
            pd.to_numeric(
                database[
                    "pvp_data"
                ],
                errors="coerce"
            ).isna(),
            "ticker",
        ]
        .tolist()
    )

    if missing_pvp_tickers:

        print()
        print(
            "CVM — buscando valuation oficial "
            f"para {len(missing_pvp_tickers)} FIIs..."
        )

        cvm_map = (
            _build_cvm_valuation_map(
                missing_pvp_tickers,
                prices_map
            )
        )

        for ticker, cvm_data in cvm_map.items():

            mask = (
                database[
                    "ticker"
                ] == ticker
            )

            for key, value in cvm_data.items():

                # ------------------------------------------------
                # GARANTIA DE DTYPE
                # ------------------------------------------------
                #
                # Pandas 3.x é mais rígido ao inserir strings em
                # colunas previamente criadas como float64.
                # Campos textuais da CVM precisam nascer como
                # dtype object; campos de data como datetime;
                # métricas numéricas podem continuar float.
                #
                if key not in database.columns:

                    if key in {
                        "cnpj_cvm",
                        "nome_cvm",
                        "fonte_valuation",
                    }:

                        database[
                            key
                        ] = pd.Series(
                            [None] * len(database),
                            dtype="object"
                        )

                    elif key == "data_referencia_cvm":

                        database[
                            key
                        ] = pd.Series(
                            pd.NaT,
                            index=database.index,
                            dtype="datetime64[ns]"
                        )

                    else:

                        database[
                            key
                        ] = np.nan

                # Se a coluna já existe, força dtype compatível
                # para os campos textuais antes da atribuição.
                if key in {
                    "cnpj_cvm",
                    "nome_cvm",
                    "fonte_valuation",
                }:

                    database[
                        key
                    ] = database[
                        key
                    ].astype(
                        "object"
                    )

                if key == "data_referencia_cvm":

                    value = pd.to_datetime(
                        value,
                        errors="coerce"
                    )

                database.loc[
                    mask,
                    key
                ] = value

            valuation_cache[
                ticker
            ] = {
                "pvp_data": cvm_data.get(
                    "pvp_data",
                    np.nan
                ),
                "vp_cota_data": cvm_data.get(
                    "vp_cota_data",
                    np.nan
                ),
                "fonte_valuation": (
                    "CVM_OFICIAL"
                ),
            }

        print(
            "CVM — valuations recuperados:",
            len(
                cvm_map
            )
        )

    _save_valuation_cache(
        valuation_cache
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
        "eventos_estruturais_detectados",
        "pvp_data",
        "vp_cota_data",
        "pl_cvm",
        "cotas_emitidas_cvm",
        "cotistas_cvm",
        "score_match_cvm",
        "cobertura_match_cvm",
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
