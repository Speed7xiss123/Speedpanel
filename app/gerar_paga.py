import argparse

from app.database import Database
from app.license import ALLOWED_PAID_DAYS, criar_licenca


def main() -> None:
    parser = argparse.ArgumentParser(description="Gera uma licença paga para o SpeedPainel.")
    parser.add_argument(
        "--dias",
        type=int,
        choices=ALLOWED_PAID_DAYS,
        default=30,
        help="Validade da licença em dias (padrão: 30).",
    )
    parser.add_argument(
        "--usuario",
        default="Cliente_Nome",
        help="Nome associado à licença.",
    )
    args = parser.parse_args()

    db = Database()
    try:
        lic = criar_licenca(
            db,
            usuario=args.usuario,
            dias=args.dias,
            gratis=False,
        )
    finally:
        db.close()

    print("Licença PAGA gerada:")
    print(f"   Chave: {lic['chave']}")
    print(f"   Usuário: {lic['usuario']}")
    print(f"   Válida por: {lic['validade']} dias")
    print(f"   Expira em: {lic['expira']}")


if __name__ == "__main__":
    main()
