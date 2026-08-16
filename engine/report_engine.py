# ============================================================
# FII INSTITUTIONAL SCANNER
# engine/report_engine.py
# ============================================================

from pathlib import Path
from datetime import datetime

import pandas as pd

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
)

from config import (
    REPORTS_DIR,
    REPORT_FILE,
    MODEL_NAME,
    MODEL_VERSION,
    SHOW_TOP_RANKING,
    GENERATE_PDF,
)


# ============================================================
# 1. AUXILIARES
# ============================================================

def _fmt_pct(value, decimals=2):

    try:
        return f"{float(value):.{decimals}%}"
    except Exception:
        return "-"


def _fmt_num(value, decimals=1):

    try:
        return f"{float(value):.{decimals}f}"
    except Exception:
        return "-"


def _fmt_money(value):

    try:
        return f"R$ {float(value):,.0f}"
    except Exception:
        return "-"


def _safe_text(value):

    if pd.isna(value):
        return "-"

    return str(value)


# ============================================================
# 2. ESTILOS
# ============================================================

def _build_styles():

    styles = getSampleStyleSheet()

    title = ParagraphStyle(
        "TitleInstitutional",
        parent=styles["Title"],
        fontSize=20,
        leading=24,
        alignment=TA_CENTER,
        spaceAfter=10,
    )

    subtitle = ParagraphStyle(
        "SubtitleInstitutional",
        parent=styles["Normal"],
        fontSize=9,
        leading=12,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#555555"),
        spaceAfter=15,
    )

    section = ParagraphStyle(
        "SectionInstitutional",
        parent=styles["Heading2"],
        fontSize=13,
        leading=16,
        alignment=TA_LEFT,
        spaceBefore=10,
        spaceAfter=8,
    )

    normal = ParagraphStyle(
        "NormalInstitutional",
        parent=styles["Normal"],
        fontSize=8.5,
        leading=11,
        spaceAfter=5,
    )

    small = ParagraphStyle(
        "SmallInstitutional",
        parent=styles["Normal"],
        fontSize=7,
        leading=9,
    )

    return {
        "title": title,
        "subtitle": subtitle,
        "section": section,
        "normal": normal,
        "small": small,
    }


# ============================================================
# 3. TABELA
# ============================================================

def _make_table(data, col_widths=None, font_size=7):

    table = Table(
        data,
        colWidths=col_widths,
        repeatRows=1,
        hAlign="LEFT",
    )

    table.setStyle(
        TableStyle(
            [
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, 0),
                    colors.HexColor("#E9ECEF"),
                ),
                (
                    "TEXTCOLOR",
                    (0, 0),
                    (-1, 0),
                    colors.black,
                ),
                (
                    "FONTNAME",
                    (0, 0),
                    (-1, 0),
                    "Helvetica-Bold",
                ),
                (
                    "FONTNAME",
                    (0, 1),
                    (-1, -1),
                    "Helvetica",
                ),
                (
                    "FONTSIZE",
                    (0, 0),
                    (-1, -1),
                    font_size,
                ),
                (
                    "GRID",
                    (0, 0),
                    (-1, -1),
                    0.25,
                    colors.HexColor("#CFCFCF"),
                ),
                (
                    "VALIGN",
                    (0, 0),
                    (-1, -1),
                    "MIDDLE",
                ),
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -1),
                    [
                        colors.white,
                        colors.HexColor("#F8F9FA"),
                    ],
                ),
                (
                    "LEFTPADDING",
                    (0, 0),
                    (-1, -1),
                    4,
                ),
                (
                    "RIGHTPADDING",
                    (0, 0),
                    (-1, -1),
                    4,
                ),
                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    3,
                ),
                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    3,
                ),
            ]
        )
    )

    return table


# ============================================================
# 4. RESUMO EXECUTIVO
# ============================================================

def _executive_summary(
    database,
    fundamentals,
    ranking,
    portfolio,
    diagnostics,
):

    rows = [
        ["Indicador", "Resultado"],
        ["FIIs após Regra Zero", str(len(database))],
        ["FIIs no motor fundamentalista", str(len(fundamentals))],
        ["FIIs no ranking institucional", str(len(ranking))],
        ["FIIs na carteira", str(len(portfolio))],
        [
            "Fundamental Score",
            _fmt_num(
                diagnostics.get(
                    "fundamental_score"
                ),
                2,
            ),
        ],
        [
            "Technical Score",
            _fmt_num(
                diagnostics.get(
                    "technical_score"
                ),
                2,
            ),
        ],
        [
            "Institutional Score",
            _fmt_num(
                diagnostics.get(
                    "institutional_score"
                ),
                2,
            ),
        ],
        [
            "DY 12m indicativo",
            _fmt_pct(
                diagnostics.get(
                    "dy_12m"
                ),
                2,
            ),
        ],
        [
            "Volatilidade robusta",
            _fmt_pct(
                diagnostics.get(
                    "volatilidade_robusta"
                ),
                2,
            ),
        ],
        [
            "Número efetivo de FIIs",
            _fmt_num(
                diagnostics.get(
                    "numero_efetivo_fiis"
                ),
                2,
            ),
        ],
        [
            "Executável agora",
            _fmt_pct(
                diagnostics.get(
                    "peso_executavel"
                ),
                2,
            ),
        ],
        [
            "Capital reservado",
            _fmt_pct(
                diagnostics.get(
                    "peso_reservado"
                ),
                2,
            ),
        ],
    ]

    return rows


# ============================================================
# 5. TOP RANKING
# ============================================================

def _ranking_table(ranking):

    top = (
        ranking
        .head(SHOW_TOP_RANKING)
        .copy()
    )

    data = [[
        "#",
        "Ticker",
        "Categoria",
        "Segmento",
        "Fund.",
        "Técnico",
        "Instit.",
        "Decisão",
    ]]

    for _, row in top.iterrows():

        data.append(
            [
                int(
                    row.get(
                        "ranking_institucional",
                        0,
                    )
                ),
                _safe_text(
                    row.get("ticker")
                ),
                _safe_text(
                    row.get("categoria_motor")
                ),
                _safe_text(
                    row.get("segmento")
                ),
                _fmt_num(
                    row.get(
                        "fundamental_score_final"
                    )
                ),
                _fmt_num(
                    row.get(
                        "technical_score"
                    )
                ),
                _fmt_num(
                    row.get(
                        "institutional_score"
                    )
                ),
                _safe_text(
                    row.get(
                        "decisao_operacional"
                    )
                ),
            ]
        )

    return data


# ============================================================
# 6. CARTEIRA ESTRATÉGICA
# ============================================================

def _portfolio_table(portfolio):

    data = [[
        "Ticker",
        "Segmento",
        "Fund.",
        "Técnico",
        "Instit.",
        "Peso",
        "Executável",
        "Reservado",
        "Status",
    ]]

    df = (
        portfolio
        .sort_values(
            "peso_estrategico",
            ascending=False,
        )
        .copy()
    )

    for _, row in df.iterrows():

        data.append(
            [
                _safe_text(
                    row.get("ticker")
                ),
                _safe_text(
                    row.get("segmento")
                ),
                _fmt_num(
                    row.get(
                        "fundamental_score_final"
                    )
                ),
                _fmt_num(
                    row.get(
                        "technical_score"
                    )
                ),
                _fmt_num(
                    row.get(
                        "institutional_score"
                    )
                ),
                _fmt_pct(
                    row.get(
                        "peso_estrategico"
                    )
                ),
                _fmt_pct(
                    row.get(
                        "peso_executavel"
                    )
                ),
                _fmt_pct(
                    row.get(
                        "peso_reservado"
                    )
                ),
                _safe_text(
                    row.get(
                        "status_final"
                    )
                ),
            ]
        )

    return data


# ============================================================
# 7. EXECUTÁVEL AGORA
# ============================================================

def _execution_table(portfolio):

    df = portfolio[
        portfolio[
            "peso_executavel"
        ] > 0
    ].copy()

    df = df.sort_values(
        [
            "peso_executavel",
            "institutional_score",
        ],
        ascending=[
            False,
            False,
        ],
    )

    data = [[
        "Ticker",
        "Segmento",
        "Instit.",
        "Peso alvo",
        "Execução",
        "Peso agora",
        "Decisão",
    ]]

    for _, row in df.iterrows():

        data.append(
            [
                _safe_text(
                    row.get("ticker")
                ),
                _safe_text(
                    row.get("segmento")
                ),
                _fmt_num(
                    row.get(
                        "institutional_score"
                    )
                ),
                _fmt_pct(
                    row.get(
                        "peso_estrategico"
                    )
                ),
                _fmt_pct(
                    row.get(
                        "fracao_execucao"
                    )
                ),
                _fmt_pct(
                    row.get(
                        "peso_executavel"
                    )
                ),
                _safe_text(
                    row.get(
                        "decisao_operacional"
                    )
                ),
            ]
        )

    return data


# ============================================================
# 8. EXPOSIÇÕES
# ============================================================

def _exposure_table(diagnostics):

    exposure = diagnostics.get(
        "exposicao",
        {}
    )

    labels = {
        "papel": "Papel",
        "tijolo": "Tijolo",
        "alternativo": "Alternativo",
        "high_yield": "High Yield",
        "logistica": "Logística",
        "shopping": "Shopping",
        "renda_urbana": "Renda Urbana",
        "lajes": "Lajes",
    }

    data = [
        ["Exposição", "Peso"]
    ]

    for key, label in labels.items():

        if key not in exposure:
            continue

        data.append(
            [
                label,
                _fmt_pct(
                    exposure[key]
                ),
            ]
        )

    return data


# ============================================================
# 9. EVENTOS EXTREMOS
# ============================================================

def _extreme_events_table(
    diagnostics
):

    events = diagnostics.get(
        "eventos_extremos",
        {}
    )

    data = [
        [
            "Ticker",
            "Eventos detectados",
        ]
    ]

    for ticker, count in events.items():

        if count <= 0:
            continue

        data.append(
            [
                ticker,
                str(count),
            ]
        )

    return data


# ============================================================
# 10. GERA PDF
# ============================================================

def _generate_pdf(
    database,
    fundamentals,
    technical,
    ranking,
    portfolio,
    diagnostics,
):

    Path(
        REPORTS_DIR
    ).mkdir(
        parents=True,
        exist_ok=True,
    )

    styles = _build_styles()

    doc = SimpleDocTemplate(
        REPORT_FILE,
        pagesize=landscape(A4),
        rightMargin=1.0 * cm,
        leftMargin=1.0 * cm,
        topMargin=1.0 * cm,
        bottomMargin=1.0 * cm,
    )

    story = []


    # ========================================================
    # CAPA
    # ========================================================

    story.append(
        Paragraph(
            MODEL_NAME,
            styles["title"],
        )
    )

    story.append(
        Paragraph(
            f"Relatório Institucional | Versão {MODEL_VERSION}",
            styles["subtitle"],
        )
    )

    story.append(
        Paragraph(
            "Execução: "
            + datetime.now().strftime(
                "%d/%m/%Y %H:%M:%S"
            ),
            styles["subtitle"],
        )
    )

    story.append(
        Spacer(
            1,
            0.4 * cm,
        )
    )


    # ========================================================
    # RESUMO
    # ========================================================

    story.append(
        Paragraph(
            "Resumo Executivo",
            styles["section"],
        )
    )

    story.append(
        _make_table(
            _executive_summary(
                database,
                fundamentals,
                ranking,
                portfolio,
                diagnostics,
            ),
            col_widths=[
                8.0 * cm,
                5.0 * cm,
            ],
            font_size=8,
        )
    )


    # ========================================================
    # EXPOSIÇÕES
    # ========================================================

    story.append(
        Spacer(
            1,
            0.4 * cm,
        )
    )

    story.append(
        Paragraph(
            "Exposições da Carteira",
            styles["section"],
        )
    )

    story.append(
        _make_table(
            _exposure_table(
                diagnostics
            ),
            col_widths=[
                7.0 * cm,
                4.0 * cm,
            ],
            font_size=8,
        )
    )


    story.append(
        PageBreak()
    )


    # ========================================================
    # RANKING
    # ========================================================

    story.append(
        Paragraph(
            "Ranking Institucional",
            styles["section"],
        )
    )

    story.append(
        _make_table(
            _ranking_table(
                ranking
            ),
            col_widths=[
                0.8 * cm,
                1.8 * cm,
                2.3 * cm,
                4.2 * cm,
                1.5 * cm,
                1.5 * cm,
                1.5 * cm,
                7.5 * cm,
            ],
            font_size=6.7,
        )
    )


    story.append(
        PageBreak()
    )


    # ========================================================
    # CARTEIRA
    # ========================================================

    story.append(
        Paragraph(
            "Carteira Estratégica",
            styles["section"],
        )
    )

    story.append(
        _make_table(
            _portfolio_table(
                portfolio
            ),
            col_widths=[
                1.8 * cm,
                4.2 * cm,
                1.4 * cm,
                1.4 * cm,
                1.4 * cm,
                1.8 * cm,
                1.8 * cm,
                1.8 * cm,
                5.0 * cm,
            ],
            font_size=6.7,
        )
    )


    story.append(
        Spacer(
            1,
            0.5 * cm,
        )
    )

    story.append(
        Paragraph(
            "Execução Atual",
            styles["section"],
        )
    )

    execution_data = (
        _execution_table(
            portfolio
        )
    )

    if len(execution_data) > 1:

        story.append(
            _make_table(
                execution_data,
                col_widths=[
                    1.8 * cm,
                    4.2 * cm,
                    1.5 * cm,
                    1.8 * cm,
                    1.8 * cm,
                    1.8 * cm,
                    6.0 * cm,
                ],
                font_size=6.8,
            )
        )

    else:

        story.append(
            Paragraph(
                "Nenhuma entrada executável no momento.",
                styles["normal"],
            )
        )


    # ========================================================
    # EVENTOS EXTREMOS
    # ========================================================

    extreme_data = (
        _extreme_events_table(
            diagnostics
        )
    )

    if len(extreme_data) > 1:

        story.append(
            Spacer(
                1,
                0.5 * cm,
            )
        )

        story.append(
            Paragraph(
                "Auditoria de Eventos Extremos",
                styles["section"],
            )
        )

        story.append(
            Paragraph(
                (
                    "Os eventos abaixo foram detectados na série de preços. "
                    "O tratamento robusto é aplicado exclusivamente à matriz "
                    "de risco e não altera silenciosamente a série original."
                ),
                styles["normal"],
            )
        )

        story.append(
            _make_table(
                extreme_data,
                col_widths=[
                    4.0 * cm,
                    5.0 * cm,
                ],
                font_size=8,
            )
        )


    # ========================================================
    # METODOLOGIA
    # ========================================================

    story.append(
        PageBreak()
    )

    story.append(
        Paragraph(
            "Metodologia",
            styles["section"],
        )
    )

    methodology = [
        "O modelo utiliza análise fundamentalista como filtro principal.",
        "O score institucional combina 80% de fundamentos e 20% de análise técnica.",
        "A análise técnica é utilizada principalmente para timing de entrada.",
        "A carteira possui restrições por fundo, categoria e segmento.",
        "A matriz de risco utiliza covariância robusta com Ledoit-Wolf.",
        "A otimização inclui penalização de concentração por HHI.",
        "O peso máximo estrutural por FII é de 15%.",
        "A carteira estratégica é separada da carteira executável.",
    ]

    for item in methodology:

        story.append(
            Paragraph(
                "• " + item,
                styles["normal"],
            )
        )


    story.append(
        Spacer(
            1,
            0.4 * cm,
        )
    )

    story.append(
        Paragraph(
            (
                "<b>Aviso:</b> este relatório é uma ferramenta quantitativa "
                "de apoio à análise e não constitui recomendação individual "
                "de investimento."
            ),
            styles["small"],
        )
    )


    doc.build(
        story
    )


# ============================================================
# 11. FUNÇÃO PRINCIPAL
# ============================================================

def generate_report(
    database,
    fundamentals,
    technical,
    ranking,
    portfolio,
    diagnostics,
):

    print()
    print("=" * 100)
    print("REPORT ENGINE")
    print("=" * 100)


    # ========================================================
    # AUDITORIA BÁSICA
    # ========================================================

    if ranking is None or ranking.empty:

        raise RuntimeError(
            "Ranking vazio no Report Engine."
        )


    if portfolio is None or portfolio.empty:

        raise RuntimeError(
            "Portfólio vazio no Report Engine."
        )


    # ========================================================
    # PDF
    # ========================================================

    if GENERATE_PDF:

        _generate_pdf(
            database=database,
            fundamentals=fundamentals,
            technical=technical,
            ranking=ranking,
            portfolio=portfolio,
            diagnostics=diagnostics,
        )

        print(
            f"PDF gerado: {REPORT_FILE}"
        )


    # ========================================================
    # RESUMO
    # ========================================================

    print()
    print(
        f"FIIs no ranking       : {len(ranking)}"
    )

    print(
        f"FIIs na carteira      : {len(portfolio)}"
    )

    print(
        "Institutional Score   : "
        f"{diagnostics.get('institutional_score', 0):.2f}"
    )

    print(
        "Executável agora      : "
        f"{diagnostics.get('peso_executavel', 0):.2%}"
    )

    print(
        "Capital reservado     : "
        f"{diagnostics.get('peso_reservado', 0):.2%}"
    )


    print()
    print("=" * 100)
    print("REPORT ENGINE CONCLUÍDO")
    print("=" * 100)
