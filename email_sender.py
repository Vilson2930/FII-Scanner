import os
import ssl
import smtplib
from pathlib import Path
from email.message import EmailMessage
from datetime import datetime


def send_report_email(
    pdf_path,
    portfolio=None,
    diagnostics=None,
):
    """
    Envia o relatório PDF do FII Institutional Scanner por Gmail.

    Secrets necessários no GitHub:
        EMAIL_USER
        EMAIL_PASSWORD
        EMAIL_TO
    """

    email_user = os.getenv("EMAIL_USER")
    email_password = os.getenv("EMAIL_PASSWORD")
    email_to = os.getenv("EMAIL_TO")

    # ==========================================================
    # VALIDAÇÃO DAS CREDENCIAIS
    # ==========================================================

    if not email_user:
        raise RuntimeError(
            "Secret EMAIL_USER não encontrado."
        )

    if not email_password:
        raise RuntimeError(
            "Secret EMAIL_PASSWORD não encontrado."
        )

    if not email_to:
        raise RuntimeError(
            "Secret EMAIL_TO não encontrado."
        )

    email_user = email_user.strip()
    email_password = email_password.strip()
    email_to = email_to.strip()

    # ==========================================================
    # VALIDAÇÃO DO PDF
    # ==========================================================

    pdf_path = Path(pdf_path)

    if not pdf_path.exists():
        raise FileNotFoundError(
            f"Relatório PDF não encontrado: {pdf_path}"
        )

    if not pdf_path.is_file():
        raise RuntimeError(
            f"O caminho informado não é um arquivo: {pdf_path}"
        )

    # ==========================================================
    # DATA DO RELATÓRIO
    # ==========================================================

    data_relatorio = datetime.now().strftime("%d/%m/%Y")

    # ==========================================================
    # RESUMO DA CARTEIRA
    # ==========================================================

    resumo = []

    if portfolio is not None and not portfolio.empty:

        resumo.append(
            f"FIIs na carteira estratégica: {len(portfolio)}"
        )

        if "decisao_operacional" in portfolio.columns:

            decisoes = (
                portfolio["decisao_operacional"]
                .value_counts()
                .to_dict()
            )

            for decisao, quantidade in decisoes.items():

                resumo.append(
                    f"{decisao}: {quantidade}"
                )

        if "peso_executavel" in portfolio.columns:

            peso_executavel = (
                portfolio["peso_executavel"]
                .fillna(0)
                .sum()
            )

            resumo.append(
                f"Capital executável: {peso_executavel:.1%}"
            )

            resumo.append(
                f"Capital reservado: "
                f"{max(0, 1 - peso_executavel):.1%}"
            )

    if not resumo:

        resumo.append(
            "Relatório institucional concluído com sucesso."
        )

    resumo_texto = "\n".join(resumo)

    # ==========================================================
    # MENSAGEM
    # ==========================================================

    msg = EmailMessage()

    msg["From"] = email_user
    msg["To"] = email_to

    msg["Subject"] = (
        f"FII Institutional Scanner — {data_relatorio}"
    )

    msg.set_content(
        f"""
FII INSTITUTIONAL SCANNER
Relatório Institucional

Data: {data_relatorio}

RESUMO DA EXECUÇÃO

{resumo_texto}

O relatório completo encontra-se anexado em PDF.

Este relatório foi produzido automaticamente pelo
FII Institutional Scanner.

As informações apresentadas são resultado dos motores
quantitativos fundamentalista, técnico e de construção
de portfólio do sistema.
""".strip()
    )

    # ==========================================================
    # ANEXAR PDF
    # ==========================================================

    with open(pdf_path, "rb") as file:

        pdf_data = file.read()

    msg.add_attachment(
        pdf_data,
        maintype="application",
        subtype="pdf",
        filename=pdf_path.name,
    )

    # ==========================================================
    # ENVIO GMAIL
    # ==========================================================

    print()
    print("=" * 100)
    print("ENVIO DO RELATÓRIO POR E-MAIL")
    print("=" * 100)

    context = ssl.create_default_context()

    erro_starttls = None

    # ==========================================================
    # TENTATIVA 1 — STARTTLS / PORTA 587
    # ==========================================================

    try:

        print(
            "Tentativa SMTP 1: Gmail STARTTLS / porta 587"
        )

        with smtplib.SMTP(
            "smtp.gmail.com",
            587,
            timeout=60,
        ) as smtp:

            smtp.ehlo()

            smtp.starttls(
                context=context
            )

            smtp.ehlo()

            smtp.login(
                email_user,
                email_password,
            )

            smtp.send_message(msg)

        print(
            f"Relatório enviado com sucesso para: {email_to}"
        )

        print("=" * 100)

        return

    except Exception as exc:

        erro_starttls = exc

        print(
            "Tentativa STARTTLS/587 falhou: "
            f"{type(exc).__name__}: {exc}"
        )

        print(
            "Tentando conexão alternativa SSL/465..."
        )

    # ==========================================================
    # TENTATIVA 2 — SSL / PORTA 465
    # ==========================================================

    try:

        print(
            "Tentativa SMTP 2: Gmail SSL / porta 465"
        )

        with smtplib.SMTP_SSL(
            "smtp.gmail.com",
            465,
            timeout=60,
            context=context,
        ) as smtp:

            smtp.login(
                email_user,
                email_password,
            )

            smtp.send_message(msg)

        print(
            f"Relatório enviado com sucesso para: {email_to}"
        )

        print("=" * 100)

        return

    except Exception as exc:

        raise RuntimeError(
            "\nFalha nas duas tentativas de envio do Gmail.\n"
            f"STARTTLS/587: "
            f"{type(erro_starttls).__name__}: "
            f"{erro_starttls}\n"
            f"SSL/465: "
            f"{type(exc).__name__}: "
            f"{exc}"
        ) from exc
