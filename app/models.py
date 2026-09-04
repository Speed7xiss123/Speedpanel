from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class Endereco:
    logradouro: str = ""
    numero: str = ""
    complemento: str = ""
    bairro: str = ""
    cidade: str = ""
    uf: str = ""
    cep: str = ""
    latitude: float = 0.0
    longitude: float = 0.0

@dataclass
class Telefone:
    numero: str = ""
    ddd: str = ""
    tipo: int = 0
    whatsapp: bool = False

@dataclass
class Email:
    endereco: str = ""

@dataclass
class Veiculo:
    placa: str = ""
    modelo: str = ""
    ano: int = 0

@dataclass
class Parente:
    nome: str = ""
    grau: str = ""
    cpf: str = ""
    idade: int = 0

@dataclass
class Vazamento:
    url: str = ""
    login: str = ""
    password: str = ""

@dataclass
class Pessoa:
    cpf: str = ""
    nome: str = ""
    nome_mae: str = ""
    sexo: str = ""
    data_nasc: str = ""
    idade: int = 0
    renda: str = ""
    escolaridade: str = ""
    classe_social: str = ""
    profissao: str = ""
    enderecos: List[Endereco] = field(default_factory=list)
    telefones: List[Telefone] = field(default_factory=list)
    emails: List[Email] = field(default_factory=list)
    veiculos: List[Veiculo] = field(default_factory=list)
    parentes: List[Parente] = field(default_factory=list)
    vazamentos: List[Vazamento] = field(default_factory=list)
    empresas: List[dict] = field(default_factory=list)
    fotos: List[str] = field(default_factory=list)
    vazamentos_count: int = 0