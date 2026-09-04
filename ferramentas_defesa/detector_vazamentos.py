"""
detector_vazamentos.py — varre SEUS próprios arquivos atrás de dados que
vazaram ou estão prestes a vazar (PII + segredos em backups, logs, repos).
Linguagem: Python 3.10+ | arquivo: ferramentas_defesa/detector_vazamentos.py
Runtime: stdlib puro, zero deps, roda offline

Propósito: apontar onde dados sensíveis seus/da sua empresa estão em
arquivos que não deveriam contê-los (logs, .env commitados, backups).
Entradas: caminho a varrer (arg), extensões ignoradas embutidas.
Saídas: JSON no stdout + tabela resumida no stderr; exit 0 limpo, 1 achados.
Side effects: somente leitura; nunca copia o valor sensível para o relatório —
  registra só tipo, arquivo, linha e um trecho mascarado.
Erros: arquivos binários/ilegíveis são pulados com aviso em stderr.
Perf: streaming linha a linha, ~O(total de bytes); regex pré-compiladas;
  ~50-100 MB/s em SSD para os padrões abaixo.
*re.compile com flags=0 por padrão; use MULTILINE só quando ^/$ por linha
importam — aqui cada linha já é isolada, então não precisa*
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

# ------------------------------------------------------------- padrões

# CPF: 11 dígitos nu OU mascarado 000.000.000-00. Validação de DV fica no
# pós-processamento para não pagar o custo em cada linha.
RE_CPF_MASCARA = re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b")
RE_CPF_NU = re.compile(r"(?<!\d)\d{11}(?!\d)")

RE_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
RE_TELEFONE_BR = re.compile(r"(?<!\d)(?:\+?55[\s.-]?)?\(?\d{2}\)?[\s.-]?\d{4,5}[\s.-]?\d{4}(?!\d)")

RE_CARTAO = re.compile(r"(?<!\d)(?:\d[ -]?){13,15}\d(?!\d)")  # pós-valida Luhn

RE_AWS_KEY = re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")
RE_TOKEN_GENERICO = re.compile(
    r"\b(?:api[_-]?key|secret|token|passwd|password|private[_-]?key)\b\s*[:=]\s*['\"]?([^\s'\"]{8,})",
    re.IGNORECASE,
)
RE_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")
RE_CHAVE_PRIVADA = re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----")

SKIP_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".zip",
            ".gz", ".7z", ".mp4", ".mp3", ".wav", ".pyc", ".db", ".db-wal",
            ".db-shm", ".woff", ".woff2", ".ttf", ".so", ".dll", ".exe"}
SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", "venv"}

MAX_LINHA = 4096  # linhas maiores que isso são truncadas na leitura


# ------------------------------------------------------------- utilidades

def cpf_valido(d: str) -> bool:
    if len(d) != 11 or not d.isdigit() or len(set(d)) == 1:
        return False
    for pos in (9, 10):
        soma = sum(int(d[i]) * (pos + 1 - i) for i in range(pos))
        dv = (soma * 10) % 11
        if dv == 10:
            dv = 0
        if dv != int(d[pos]):
            return False
    return True


def luhn_valido(numeros: str) -> bool:
    digitos = [int(c) for c in re.sub(r"\D", "", numeros)]
    if not 13 <= len(digitos) <= 16:
        return False
    soma = 0
    for i, d in enumerate(reversed(digitos)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        soma += d
    return soma % 10 == 0


def mascarar(trecho: str) -> str:
    """Mantém 3 primeiros e 2 últimos chars; o resto vira ***."""
    t = trecho.strip()
    if len(t) <= 6:
        return "*" * len(t)
    return f"{t[:3]}***{t[-2:]}"


# ------------------------------------------------------------- varredura

@dataclass
class Achado:
    categoria: str
    arquivo: str
    linha: int
    amostra_mascarada: str


def escanear_arquivo(caminho: Path, raiz: Path) -> list[Achado]:
    achados: list[Achado] = []
    try:
        with caminho.open("r", encoding="utf-8", errors="strict") as fh:
            for n, linha in enumerate(fh, 1):
                if len(linha) > MAX_LINHA:
                    linha = linha[:MAX_LINHA]
                rel = str(caminho.relative_to(raiz))
                for m in RE_CPF_MASCARA.finditer(linha):
                    nu = re.sub(r"\D", "", m.group())
                    if cpf_valido(nu):
                        achados.append(Achado("CPF", rel, n, mascarar(m.group())))
                for m in RE_CPF_NU.finditer(linha):
                    if cpf_valido(m.group()):
                        achados.append(Achado("CPF", rel, n, mascarar(m.group())))
                for m in RE_EMAIL.finditer(linha):
                    achados.append(Achado("email", rel, n, mascarar(m.group())))
                for m in RE_CARTAO.finditer(linha):
                    if luhn_valido(m.group()):
                        achados.append(Achado("cartao", rel, n, mascarar(m.group())))
                for m in RE_AWS_KEY.finditer(linha):
                    achados.append(Achado("aws_key", rel, n, mascarar(m.group())))
                for m in RE_TOKEN_GENERICO.finditer(linha):
                    achados.append(Achado("segredo", rel, n, mascarar(m.group(1))))
                for m in RE_JWT.finditer(linha):
                    achados.append(Achado("jwt", rel, n, mascarar(m.group())))
                if RE_CHAVE_PRIVADA.search(linha):
                    achados.append(Achado("chave_privada", rel, n, "-----BEGIN..."))
    except (UnicodeDecodeError, OSError):
        print(f"[warn] pulando (binário/ilegível): {caminho}", file=sys.stderr)
    return achados


def escanear(raiz: Path) -> list[Achado]:
    todos: list[Achado] = []
    for p in raiz.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower() in SKIP_EXT:
            continue
        if SKIP_DIRS & set(p.parts):
            continue
        todos.extend(escanear_arquivo(p, raiz))
    return todos


def main(argv: list[str]) -> int:
    alvo = Path(argv[1]) if len(argv) > 1 else Path.cwd()
    if not alvo.exists():
        print(f"[erro] caminho não existe: {alvo}", file=sys.stderr)
        return 2
    achados = escanear(alvo)
    por_cat: dict[str, int] = {}
    for a in achados:
        por_cat[a.categoria] = por_cat.get(a.categoria, 0) + 1

    json.dump({"resumo": por_cat, "achados": [asdict(a) for a in achados]},
              sys.stdout, ensure_ascii=False, indent=2)
    print(file=sys.stdout)
    print(f"\n{len(achados)} achado(s) em {alvo}: "
          + ", ".join(f"{k}={v}" for k, v in sorted(por_cat.items())),
          file=sys.stderr)
    return 1 if achados else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
