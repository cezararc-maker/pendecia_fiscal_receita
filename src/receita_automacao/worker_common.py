from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re

from .models import digits_only, is_valid_cnpj

PORTAL_URL = "https://servicos.receitafederal.gov.br/servico/pendencias/#/analise-pendencias"
PORTAL_HOST = "servicos.receitafederal.gov.br"
CNPJ_INPUT_SELECTOR = 'input[placeholder="Digite o CPF ou CNPJ"]'
SUBMIT_SELECTOR = 'button[type="submit"].br-button.primary.block.margin-5'
PROFILE_PLACEHOLDER_SELECTOR = "ng-select .ng-placeholder"
PROFILE_PLACEHOLDER_TEXT = "Digite um perfil de representação"
PROFILE_ARROW_SELECTOR = "ng-select .ng-arrow-wrapper"
PROFILE_OPTION_SELECTOR = ".ng-dropdown-panel .ng-option"
PROFILE_BUTTON_SELECTOR = "#avatar-dropdown-trigger"
NO_PENDENCY_RE = re.compile(r"Sem\s+pend[êe]ncia", re.IGNORECASE)
HAS_PENDENCY_RE = re.compile(r"Com\s+pend[êe]ncia", re.IGNORECASE)
ANALYSIS_HEADING_RE = re.compile(r"Resultado\s+da\s+An[aá]lise", re.IGNORECASE)
CNPJ_TEXT_RE = re.compile(r"(?<!\d)(\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2})(?!\d)")
COOLDOWN_RE = re.compile(r"Aguarde, pelo menos, 30 segundos para representar outra pessoa", re.IGNORECASE)
ALREADY_ACTIVE_RE = re.compile(r"Usu.rio a representar j. . o usu.rio ativo", re.IGNORECASE)
EXPLICIT_NO_AUTH_RE = re.compile(
    r"(?:sem\s+procura..o\s+ativa|n.o\s+possui\s+procura..o|procura..o\s+inexistente)",
    re.IGNORECASE,
)
PORTAL_INSTABILITY_RE = re.compile(r"N.o foi poss.vel gerar o relat.rio de situa..o fiscal", re.IGNORECASE)
SECURITY_CHALLENGE_RE = re.compile(
    (
        r"(?:Toque no item de seguran.a usado na cabe.a ou no rosto|"
        r"verifica..o de seguran.a|captcha|confirme sua identidade|"
        r"Selecione\s+tudo(?:\s+mais\s+silencioso)?(?:\s+que\s+o\s+item\s+mostrado)?)"
    ),
    re.IGNORECASE,
)


class WorkerError(RuntimeError):
    def __init__(self, code: str, stage: str, message: str, *, fatal: bool = False):
        super().__init__(message)
        self.code = code
        self.stage = stage
        self.fatal = fatal


class PortalUnstableError(WorkerError):
    def __init__(self, stage: str, message: str):
        super().__init__("portal_unstable", stage, message, fatal=False)


class RepresentationSafetyError(WorkerError):
    def __init__(self, code: str, stage: str, message: str):
        super().__init__(code, stage, message, fatal=True)


@dataclass(frozen=True, slots=True)
class QueueCompany:
    codigo: str
    nome: str
    identificador: str
    tipo_identificador: str
    tipo_inscricao: str = ""

    @property
    def is_eligible_receita(self) -> bool:
        return self.tipo_identificador.upper() == "CNPJ" and is_valid_cnpj(self.identificador)


def clean(value: object) -> str:
    return re.sub(r"[\t\r\n]+", " ", str(value or "")).strip()


def local_timestamp() -> str:
    return datetime.now().astimezone().strftime("%d/%m/%Y %H:%M:%S")


def format_duration(total_seconds: float | int) -> str:
    seconds = max(0, round(float(total_seconds or 0)))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def format_cnpj(value: object) -> str:
    digits = digits_only(value)
    if len(digits) != 14:
        return digits
    return f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:]}"


def parse_analysis_result(main_text: str, target_cnpj: str, heading_visible: bool) -> str | None:
    """Accept a result only when the result area explicitly contains the requested CNPJ."""
    if not heading_visible:
        return None
    displayed_cnpjs = {digits_only(match.group(1)) for match in CNPJ_TEXT_RE.finditer(main_text)}
    if target_cnpj not in displayed_cnpjs:
        return None
    if NO_PENDENCY_RE.search(main_text):
        return "SEM_PENDENCIAS"
    if HAS_PENDENCY_RE.search(main_text):
        return "COM_PENDENCIAS"
    return None


def classify_explicit_no_authorization(text: str) -> bool:
    """Generic navigation/not-found failures never imply missing authorization."""
    return bool(EXPLICIT_NO_AUTH_RE.search(text or ""))


def concise_error(value: object) -> str:
    raw = re.sub(r"\x1B\[[0-?]*[ -/]*[@-~]", "", str(value or ""))
    raw = raw.split("Call log:", 1)[0]
    if re.search(r"outside of the viewport|intercepts pointer events|locator\.click: Timeout", raw, re.I):
        return "Não foi possível acionar o controle esperado do portal dentro do tempo limite."
    if re.search(r"Timeout \d+ms exceeded", raw, re.I):
        return "O portal não respondeu dentro do tempo limite na etapa atual."
    return clean(raw)[:400] or "Erro de processamento sem detalhe retornado."
