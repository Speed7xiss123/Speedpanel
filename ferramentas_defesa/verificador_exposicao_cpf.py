"""
verificador_exposicao_cpf.py — defesa pessoal, uso offline ou k-anon
Linguagem: Python 3.10+ | arquivo: ferramentas_defesa/verificador_exposicao_cpf.py
Runtime: stdlib + requests (só para o check HIBP; roda 100% offline sem ele)

Propósito: dizer a UMA pessoa se o CPF DELA aparece em dumps locais e se o
hash dela consta em bases de credenciais vazadas (HIBP, via k-anonymity).

Entradas:
  - cpf: str, 11 dígitos (com ou sem máscara). Faixa: qualquer CPF válido.
  - pastas_varredura: list[Path], arquivos .csv/.json/.txt a inspecionar.
Saídas: relatório no stdout com veredito por fonte; exit code 0 limpo, 1 achado.
Efeitos colaterais: leituras de disco; 1 requisição HTTPS ao HIBP (só envia
  prefixo de 5 hex digits do SHA-256 — nunca o CPF nem o hash completo).
Erros: CPF com dígitos verificadores inválidos aborta com código 2 — evita
  "não achei" falso sobre um número malformado.
Concorrência: single-thread; varredura de dump é O(bytes do arquivo).
*requests: use timeout em toda chamada externa; HIBP retorna 4xx se o prefixo
 tiver <5 caracteres ou se o range for desconhecido*
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------- CPF válido

_DIGITS = re.compile(r"\D")


def normalizar_cpf(cpf: str) -> str:
    """Strips máscara (123.456.789-09 -> 12345678909). Não valida."""
    return _DIGITS.sub("", cpf)


def cpf_valido(cpf: str) -> bool:
    """Algoritmo oficial dos dígitos verificadores da Receita Federal.
    Rejeita todos-iguais (00000000000 etc.) e tamanho != 11."""
    d = normalizar_cpf(cpf)
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


# ------------------------------------------------------------- dump local

@dataclass
class Achado:
    origem: str
    linha: int
    contexto: str  # truncado a 80 chars, sem ecoar a linha inteira


@dataclass
class ResultadoVarredura:
    cpf: str
    achados: list[Achado] = field(default_factory=list)
    arquivos_lidos: int = 0
    bytes_lidos: int = 0


def _mascara_cpf(d: str) -> str:
    return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"


def varrer_dumps_locais(cpf: str, pastas: list[Path]) -> ResultadoVarredura:
    """Procura CPF nu e mascarado em CSV/JSON/TXT. Lê em chunks de 1MB para
    não estourar RAM em dumps de GB. *csv.field_size_limit: linhas com campos
    gigantes (JSON empacotado em coluna) estouram o parser — catch e segue*."""
    nu = normalizar_cpf(cpf)
    mascarado = _mascara_cpf(nu)
    alvos = (nu, mascarado)
    resultado = ResultadoVarredura(cpf=nu)

    arquivos = [
        p
        for pasta in pastas
        if pasta.is_dir()
        for p in pasta.rglob("*")
        if p.is_file() and p.suffix.lower() in {".csv", ".json", ".txt"}
    ]
    for caminho in arquivos:
        resultado.arquivos_lidos += 1
        try:
            with caminho.open("r", encoding="utf-8", errors="replace") as fh:
                for n, linha in enumerate(fh, 1):
                    resultado.bytes_lidos += len(linha)
                    for alvo in alvos:
                        if alvo in linha:
                            idx = linha.find(alvo)
                            ini = max(0, idx - 30)
                            resultado.achados.append(
                                Achado(str(caminho), n, linha[ini:idx + 50].strip())
                            )
                            break
        except (OSError, UnicodeError) as exc:
            print(f"[warn] pulando {caminho}: {exc}", file=sys.stderr)
    return resultado


# ------------------------------------------------------- HIBP k-anonymity

_HIBP_RANGE = "https://api.pwnedpasswords.com/range/"


def checar_hibp(valor: str, timeout: float = 10.0) -> int | None:
    """Hash SHA-1 do valor; envia só os 5 primeiros hex (k-anonymity).
    Retorna contagem de ocorrências, 0 se limpo, None se offline/erro.
    O range endpoint do HIBP é SHA-1 — vale para qualquer string, não só
    senha; aqui o input é o CPF normalizado do próprio usuário.
    *requests: sempre com timeout; sem rede a função retorna None e o
    veredito local continua válido*."""
    digest = hashlib.sha1(valor.encode("utf-8")).hexdigest().upper()
    prefixo, sufixo = digest[:5], digest[5:]
    try:
        import requests  # *opcional: sem ele a função retorna None*

        resp = requests.get(_HIBP_RANGE + prefixo, timeout=timeout)
        if resp.status_code != 200:
            return None
        for linha in resp.text.splitlines():
            hash_sufixo, _, contagem = linha.partition(":")
            if hash_sufixo.strip() == sufixo:
                return int(contagem)
        return 0
    except Exception:
        return None


# ------------------------------------------------------------------- main

def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("uso: python verificador_exposicao_cpf.py <SEU_CPF> [pasta ...]")
        print("ex.: python verificador_exposicao_cpf.py 123.456.789-09 ./meus_dumps")
        return 2
    cpf = argv[1]
    if not cpf_valido(cpf):
        print("[erro] CPF com dígitos verificadores inválidos — confira o número.")
        return 2
    pastas = [Path(p) for p in argv[2:]] or [Path(__file__).resolve().parent]

    print(f"CPF: {_mascara_cpf(normalizar_cpf(cpf))}")
    print(f"Varrendo {len(pastas)} pasta(s) local(is)...")
    res = varrer_dumps_locais(cpf, pastas)
    print(f"  {res.arquivos_lidos} arquivo(s), {res.bytes_lidos/1e6:.1f} MB lidos")
    if res.achados:
        print(f"  [EXPOSTO] {len(res.achados)} ocorrência(s):")
        for a in res.achados[:20]:
            print(f"    {a.origem}:{a.linha}  ...{a.contexto}...")
    else:
        print("  [limpo] não aparece nos dumps locais varridos.")

    print("Consultando HIBP (k-anonymity, só 5 chars do hash saem)...")
    hibp = checar_hibp(normalizar_cpf(cpf))
    if hibp is None:
        print("  [offline] HIBP indisponível — veredito local mantém-se.")
    elif hibp == 0:
        print("  [limpo] hash não consta nas bases do HIBP.")
    else:
        print(f"  [EXPOSTO] hash aparece em {hibp} vazamento(s) no HIBP.")

    return 1 if (res.achados or (hibp or 0) > 0) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
