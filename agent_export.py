# ============================================================
# FII INSTITUTIONAL SCANNER
# agent_export.py
# ============================================================
#
# Camada de exportação para o Investment CIO Agent.
#
# PRINCÍPIOS:
#
# 1. Não recalcula nenhum indicador.
# 2. Não altera ranking.
# 3. Não altera pesos.
# 4. Não altera decisões operacionais.
# 5. Não remove FIIs.
# 6. Não cria recomendação nova.
# 7. Apenas serializa os resultados produzidos pelo motor.
#
# ============================================================

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


# ============================================================
# CONFIGURAÇÃO
# ============================================================

SOURCE_SYSTEM = "FII_INSTITUTIONAL_SCANNER"

EXPORT_VERSION = "1.0"

OUTPUT_DIR = Path("outputs")

OUTPUT_FILE = OUTPUT_DIR / "agent_output_raw.json"


# ============================================================
# CONVERSÃO SEGURA PARA JSON
# ============================================================

def _json_safe(value: Any) -> Any:
    """
    Converte objetos NumPy/Pandas/Python para estruturas
    serializáveis em JSON.

    Não altera a lógica nem recalcula resultados.
    """

    # --------------------------------------------------------
    # NULOS
    # --------------------------------------------------------

    if value is None:
        return None

    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass

    # --------------------------------------------------------
    # BOOLEANOS
    # --------------------------------------------------------

    if isinstance(value, (bool, np.bool_)):
        return bool(value)

    # --------------------------------------------------------
    # INTEIROS
    # --------------------------------------------------------

    if isinstance(value, (int, np.integer)):
        return int(value)

    # --------------------------------------------------------
    # FLOATS
    # --------------------------------------------------------

    if isinstance(value, (float, np.floating)):

        converted = float(value)

        if not math.isfinite(converted):
            return None

        return converted

    # --------------------------------------------------------
    # DATAS
    # --------------------------------------------------------

    if isinstance(
        value,
        (
            datetime,
            pd.Timestamp,
        ),
    ):

        return value.isoformat()

    # --------------------------------------------------------
    # PATH
    # --------------------------------------------------------

    if isinstance(value, Path):
        return str(value)

    # --------------------------------------------------------
    # DICT
    # --------------------------------------------------------

    if isinstance(value, dict):

        return {
            str(key): _json_safe(item)
            for key, item in value.items()
        }

    # --------------------------------------------------------
    # LISTAS / TUPLAS / SETS
    # --------------------------------------------------------

    if isinstance(
        value,
        (
            list,
            tuple,
            set,
        ),
    ):

        return [
            _json_safe(item)
            for item in value
        ]

    # --------------------------------------------------------
    # ARRAYS NUMPY
    # --------------------------------------------------------

    if isinstance(value, np.ndarray):

        return [
            _json_safe(item)
            for item in value.tolist()
        ]

    # --------------------------------------------------------
    # SERIES
    # --------------------------------------------------------

    if isinstance(value, pd.Series):

        return {
            str(key): _json_safe(item)
            for key, item in value.to_dict().items()
        }

    # --------------------------------------------------------
    # DATAFRAME
    # --------------------------------------------------------

    if isinstance(value, pd.DataFrame):

        return [
            {
                str(key): _json_safe(item)
                for key, item in row.items()
            }
            for row in value.to_dict(
                orient="records"
            )
        ]

    # --------------------------------------------------------
    # STRING
    # --------------------------------------------------------

    if isinstance(value, str):
        return value

    # --------------------------------------------------------
    # FALLBACK
    # --------------------------------------------------------

    return str(value)


# ============================================================
# DATAFRAME → RECORDS
# ============================================================

def _dataframe_to_records(
    dataframe: pd.DataFrame | None,
) -> list[dict[str, Any]]:
    """
    Converte DataFrame para lista de registros JSON-safe.
    Preserva a ordem original recebida.
    """

    if dataframe is None:
        return []

    if not isinstance(
        dataframe,
        pd.DataFrame,
    ):
        raise TypeError(
            "Era esperado um pandas.DataFrame."
        )

    if dataframe.empty:
        return []

    records = dataframe.to_dict(
        orient="records"
    )

    return [
        {
            str(key): _json_safe(value)
            for key, value in row.items()
        }
        for row in records
    ]


# ============================================================
# CONTAGEM SEGURA
# ============================================================

def _count_values(
    dataframe: pd.DataFrame | None,
    column: str,
) -> dict[str, int]:
    """
    Apenas conta valores já existentes no motor.
    Não cria classificação nova.
    """

    if (
        dataframe is None
        or not isinstance(
            dataframe,
            pd.DataFrame,
        )
        or dataframe.empty
        or column not in dataframe.columns
    ):
        return {}

    counts = (
        dataframe[column]
        .fillna("SEM_DADO")
        .astype(str)
        .value_counts(
            dropna=False
        )
        .to_dict()
    )

    return {
        str(key): int(value)
        for key, value in counts.items()
    }


# ============================================================
# SUMÁRIO ESTRUTURAL
# ============================================================

def _build_summary(
    database: pd.DataFrame,
    fundamentals: pd.DataFrame,
    technical: pd.DataFrame,
    ranking: pd.DataFrame,
    portfolio: pd.DataFrame,
    diagnostics: dict[str, Any],
) -> dict[str, Any]:
    """
    Gera somente contagens e somatórios estruturais.

    Não produz score novo.
    Não produz sinal novo.
    """

    summary: dict[str, Any] = {

        "database_count":
            int(len(database)),

        "fundamentals_count":
            int(len(fundamentals)),

        "technical_count":
            int(len(technical)),

        "ranking_count":
            int(len(ranking)),

        "portfolio_count":
            int(len(portfolio)),

        "institutional_classification_counts":
            _count_values(
                ranking,
                "classificacao_institucional",
            ),

        "portfolio_priority_counts":
            _count_values(
                ranking,
                "prioridade_portfolio",
            ),

        "operational_decision_counts":
            _count_values(
                portfolio,
                "decisao_operacional",
            ),

        "final_status_counts":
            _count_values(
                portfolio,
                "status_final",
            ),

        "category_counts":
            _count_values(
                portfolio,
                "categoria_motor",
            ),

        "segment_counts":
            _count_values(
                portfolio,
                "segmento",
            ),
    }

    # --------------------------------------------------------
    # PESO ESTRATÉGICO
    # --------------------------------------------------------

    if (
        "peso_estrategico"
        in portfolio.columns
    ):

        summary[
            "strategic_weight_sum"
        ] = _json_safe(
            portfolio[
                "peso_estrategico"
            ].sum()
        )

    else:

        summary[
            "strategic_weight_sum"
        ] = None

    # --------------------------------------------------------
    # PESO EXECUTÁVEL
    # --------------------------------------------------------

    if (
        "peso_executavel"
        in portfolio.columns
    ):

        summary[
            "executable_weight_sum"
        ] = _json_safe(
            portfolio[
                "peso_executavel"
            ].sum()
        )

    else:

        summary[
            "executable_weight_sum"
        ] = None

    # --------------------------------------------------------
    # PESO RESERVADO
    # --------------------------------------------------------

    if (
        "peso_reservado"
        in portfolio.columns
    ):

        summary[
            "reserved_weight_sum"
        ] = _json_safe(
            portfolio[
                "peso_reservado"
            ].sum()
        )

    else:

        summary[
            "reserved_weight_sum"
        ] = None

    # --------------------------------------------------------
    # OTIMIZAÇÃO
    # --------------------------------------------------------

    summary[
        "optimization_success"
    ] = _json_safe(
        diagnostics.get(
            "optimization_success"
        )
    )

    summary[
        "optimization_message"
    ] = _json_safe(
        diagnostics.get(
            "optimization_message"
        )
    )

    return summary


# ============================================================
# VALIDAÇÃO ESTRUTURAL DA EXPORTAÇÃO
# ============================================================

def _validate_inputs(
    database: pd.DataFrame,
    fundamentals: pd.DataFrame,
    technical: pd.DataFrame,
    ranking: pd.DataFrame,
    portfolio: pd.DataFrame,
    diagnostics: dict[str, Any],
) -> None:
    """
    Valida somente se os objetos essenciais existem.

    Não valida a qualidade financeira do resultado e não
    recalcula nenhuma regra do scanner.
    """

    dataframes = {

        "database":
            database,

        "fundamentals":
            fundamentals,

        "technical":
            technical,

        "ranking":
            ranking,

        "portfolio":
            portfolio,
    }

    for name, dataframe in dataframes.items():

        if not isinstance(
            dataframe,
            pd.DataFrame,
        ):
            raise TypeError(
                f"{name} não é pandas.DataFrame."
            )

    if ranking.empty:

        raise RuntimeError(
            "Não é possível exportar: "
            "ranking está vazio."
        )

    if portfolio.empty:

        raise RuntimeError(
            "Não é possível exportar: "
            "portfolio está vazio."
        )

    if not isinstance(
        diagnostics,
        dict,
    ):
        raise TypeError(
            "diagnostics não é dict."
        )

    required_ranking_columns = [

        "ticker",
        "fundamental_score_final",
        "technical_score",
        "institutional_score",
        "decisao_operacional",
        "ranking_institucional",

    ]

    missing_ranking = [

        column
        for column
        in required_ranking_columns
        if column
        not in ranking.columns

    ]

    if missing_ranking:

        raise RuntimeError(
            "Ranking sem colunas essenciais: "
            + ", ".join(
                missing_ranking
            )
        )

    required_portfolio_columns = [

        "ticker",
        "fundamental_score_final",
        "technical_score",
        "institutional_score",
        "decisao_operacional",
        "peso_estrategico",
        "fracao_execucao",
        "peso_executavel",
        "peso_reservado",
        "status_final",

    ]

    missing_portfolio = [

        column
        for column
        in required_portfolio_columns
        if column
        not in portfolio.columns

    ]

    if missing_portfolio:

        raise RuntimeError(
            "Portfolio sem colunas essenciais: "
            + ", ".join(
                missing_portfolio
            )
        )


# ============================================================
# CONSTRUÇÃO DO PAYLOAD
# ============================================================

def build_agent_payload(
    database: pd.DataFrame,
    fundamentals: pd.DataFrame,
    technical: pd.DataFrame,
    ranking: pd.DataFrame,
    portfolio: pd.DataFrame,
    diagnostics: dict[str, Any],
) -> dict[str, Any]:
    """
    Constrói o payload bruto consumido pelo Investment CIO.

    IMPORTANTE:
    este payload representa exatamente os resultados do
    FII Institutional Scanner.

    Nenhuma recomendação adicional é criada aqui.
    """

    _validate_inputs(

        database=database,

        fundamentals=fundamentals,

        technical=technical,

        ranking=ranking,

        portfolio=portfolio,

        diagnostics=diagnostics,

    )

    generated_at = datetime.now(
        timezone.utc
    ).isoformat()

    payload = {

        "source_system":
            SOURCE_SYSTEM,

        "export_version":
            EXPORT_VERSION,

        "generated_at":
            generated_at,

        # ====================================================
        # RESUMO ESTRUTURAL
        # ====================================================

        "summary":
            _build_summary(

                database=database,

                fundamentals=fundamentals,

                technical=technical,

                ranking=ranking,

                portfolio=portfolio,

                diagnostics=diagnostics,

            ),

        # ====================================================
        # UNIVERSO TRATADO
        # ====================================================

        "database":
            _dataframe_to_records(
                database
            ),

        # ====================================================
        # MOTOR FUNDAMENTALISTA
        # ====================================================

        "fundamentals":
            _dataframe_to_records(
                fundamentals
            ),

        # ====================================================
        # MOTOR TÉCNICO
        # ====================================================

        "technical":
            _dataframe_to_records(
                technical
            ),

        # ====================================================
        # RANKING INSTITUCIONAL
        # ====================================================

        "ranking":
            _dataframe_to_records(
                ranking
            ),

        # ====================================================
        # CARTEIRA FINAL
        # ====================================================

        "portfolio":
            _dataframe_to_records(
                portfolio
            ),

        # ====================================================
        # DIAGNÓSTICOS DO PRÓPRIO MOTOR
        # ====================================================

        "diagnostics":
            _json_safe(
                diagnostics
            ),

        # ====================================================
        # POLÍTICA DA EXPORTAÇÃO
        # ====================================================

        "metadata": {

            "export_policy": {

                "recalculates_scores":
                    False,

                "recalculates_ranking":
                    False,

                "reorders_ranking":
                    False,

                "recalculates_portfolio":
                    False,

                "changes_portfolio_members":
                    False,

                "recalculates_weights":
                    False,

                "changes_operational_decisions":
                    False,

                "changes_execution_fraction":
                    False,

                "changes_executable_weight":
                    False,

                "changes_reserved_weight":
                    False,

                "creates_new_investment_signal":
                    False,

                "executes_broker_orders":
                    False,

            },

            "architecture": {

                "pipeline": [

                    "data_engine",

                    "fundamental_engine",

                    "technical_engine",

                    "institutional_score",

                    "portfolio_engine",

                    "risk_optimization",

                    "execution_layer",

                    "report_engine",

                ],

                "ranking_source":
                    "portfolio_engine",

                "portfolio_source":
                    "portfolio_engine",

                "execution_source":
                    "portfolio_engine",

                "risk_diagnostics_source":
                    "portfolio_engine",

            },

        },

    }

    return _json_safe(
        payload
    )


# ============================================================
# EXPORTAÇÃO
# ============================================================

def export_agent_output(
    database: pd.DataFrame,
    fundamentals: pd.DataFrame,
    technical: pd.DataFrame,
    ranking: pd.DataFrame,
    portfolio: pd.DataFrame,
    diagnostics: dict[str, Any],
    output_file: str | Path = OUTPUT_FILE,
) -> dict[str, Any]:
    """
    Cria outputs/agent_output_raw.json.
    """

    payload = build_agent_payload(

        database=database,

        fundamentals=fundamentals,

        technical=technical,

        ranking=ranking,

        portfolio=portfolio,

        diagnostics=diagnostics,

    )

    output_path = Path(
        output_file
    )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with open(
        output_path,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(

            payload,

            file,

            ensure_ascii=False,

            indent=2,

            allow_nan=False,

        )

    print()
    print("=" * 90)
    print(
        "EXPORTAÇÃO PARA INVESTMENT CIO AGENT"
    )
    print("=" * 90)

    print(
        f"Source system       : "
        f"{payload['source_system']}"
    )

    print(
        f"Export version      : "
        f"{payload['export_version']}"
    )

    print(
        f"FIIs no ranking     : "
        f"{payload['summary']['ranking_count']}"
    )

    print(
        f"FIIs no portfólio   : "
        f"{payload['summary']['portfolio_count']}"
    )

    print(
        f"Peso estratégico    : "
        f"{payload['summary']['strategic_weight_sum']}"
    )

    print(
        f"Peso executável     : "
        f"{payload['summary']['executable_weight_sum']}"
    )

    print(
        f"Peso reservado      : "
        f"{payload['summary']['reserved_weight_sum']}"
    )

    print(
        f"Arquivo             : "
        f"{output_path}"
    )

    print("=" * 90)
    print()

    return payload
