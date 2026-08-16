# ============================================================
# FII INSTITUTIONAL SCANNER
# main.py
# ============================================================
#
# Pipeline principal:
#
# 1. Coleta e saneamento dos dados
# 2. Análise fundamentalista
# 3. Filtro técnico
# 4. Score institucional
# 5. Construção e otimização do portfólio
# 6. Geração dos relatórios
#
# ============================================================

from datetime import datetime

from engine.data_engine import build_database
from engine.fundamental_engine import run_fundamental_engine
from engine.technical_engine import run_technical_engine
from engine.portfolio_engine import build_portfolio
from engine.report_engine import generate_report


def main():

    print("=" * 90)
    print("FII INSTITUTIONAL SCANNER")
    print("=" * 90)

    print(
        "Execução:",
        datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    )

    print()


    # ========================================================
    # ETAPA 1 — DADOS
    # ========================================================

    print("=" * 90)
    print("ETAPA 1 — DADOS E REGRA ZERO")
    print("=" * 90)

    database = build_database()

    if database is None or database.empty:

        raise RuntimeError(
            "A base de dados retornou vazia."
        )

    print(
        f"FIIs disponíveis após tratamento: "
        f"{len(database)}"
    )

    print()


    # ========================================================
    # ETAPA 2 — FUNDAMENTOS
    # ========================================================

    print("=" * 90)
    print("ETAPA 2 — MOTOR FUNDAMENTALISTA")
    print("=" * 90)

    fundamentals = run_fundamental_engine(
        database
    )

    if fundamentals is None or fundamentals.empty:

        raise RuntimeError(
            "O motor fundamentalista não retornou resultados."
        )

    print(
        f"FIIs processados no motor fundamentalista: "
        f"{len(fundamentals)}"
    )

    print()


    # ========================================================
    # ETAPA 3 — TÉCNICO
    # ========================================================

    print("=" * 90)
    print("ETAPA 3 — MOTOR TÉCNICO")
    print("=" * 90)

    technical = run_technical_engine(
        fundamentals
    )

    if technical is None or technical.empty:

        raise RuntimeError(
            "O motor técnico não retornou resultados."
        )

    print(
        f"FIIs processados no motor técnico: "
        f"{len(technical)}"
    )

    print()


    # ========================================================
    # ETAPA 4 — PORTFÓLIO
    # ========================================================

    print("=" * 90)
    print("ETAPA 4 — SCORE INSTITUCIONAL E PORTFÓLIO")
    print("=" * 90)

    portfolio_result = build_portfolio(
        fundamentals,
        technical
    )

    if portfolio_result is None:

        raise RuntimeError(
            "O motor de portfólio não retornou resultados."
        )


    # --------------------------------------------------------
    # O portfolio_engine retornará:
    #
    # ranking
    # portfolio
    # diagnostics
    # --------------------------------------------------------

    ranking = portfolio_result[
        "ranking"
    ]

    portfolio = portfolio_result[
        "portfolio"
    ]

    diagnostics = portfolio_result.get(
        "diagnostics",
        {}
    )


    print(
        f"FIIs no ranking institucional: "
        f"{len(ranking)}"
    )

    print(
        f"FIIs na carteira estratégica: "
        f"{len(portfolio)}"
    )

    print()


    # ========================================================
    # ETAPA 5 — RELATÓRIOS
    # ========================================================

    print("=" * 90)
    print("ETAPA 5 — RELATÓRIO INSTITUCIONAL")
    print("=" * 90)

    generate_report(

        database=database,

        fundamentals=fundamentals,

        technical=technical,

        ranking=ranking,

        portfolio=portfolio,

        diagnostics=diagnostics

    )


    # ========================================================
    # RESUMO FINAL
    # ========================================================

    print()
    print("=" * 90)
    print("SCANNER CONCLUÍDO")
    print("=" * 90)


    if "fundamental_score_final" in portfolio.columns:

        fundamental_score = (

            portfolio[
                "fundamental_score_final"
            ]

            * portfolio[
                "peso_estrategico"
            ]

        ).sum()

        print(
            f"Fundamental Score carteira : "
            f"{fundamental_score:.2f}"
        )


    if "institutional_score" in portfolio.columns:

        institutional_score = (

            portfolio[
                "institutional_score"
            ]

            * portfolio[
                "peso_estrategico"
            ]

        ).sum()

        print(
            f"Institutional Score carteira: "
            f"{institutional_score:.2f}"
        )


    if "peso_executavel" in portfolio.columns:

        executavel = (

            portfolio[
                "peso_executavel"
            ].sum()

        )

        print(
            f"Executável agora            : "
            f"{executavel:.2%}"
        )


        print(
            f"Capital reservado           : "
            f"{1 - executavel:.2%}"
        )


    print()

    print(
        "Arquivos principais:"
    )

    print(
        "  data/universe.csv"
    )

    print(
        "  data/ranking.csv"
    )

    print(
        "  data/portfolio.csv"
    )

    print(
        "  reports/fii_report.pdf"
    )

    print()

    print("=" * 90)


if __name__ == "__main__":
    main()
