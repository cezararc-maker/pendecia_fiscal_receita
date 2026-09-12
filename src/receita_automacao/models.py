from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import re


class EntityType(StrEnum):
    CNPJ = "CNPJ"
    CPF = "CPF"
    CAEPF = "CAEPF"
    UNKNOWN = "UNKNOWN"


class PortalResultStatus(StrEnum):
    NO_PENDENCIES = "SEM_PENDENCIAS"
    HAS_PENDENCIES = "COM_PENDENCIAS"


_DIGITS = re.compile(r"\D+")


def digits_only(value: object) -> str:
    return _DIGITS.sub("", "" if value is None else str(value))


def parse_entity_type(value: object) -> EntityType:
    normalized = str(value or "").strip().upper()
    if normalized == "CNPJ":
        return EntityType.CNPJ
    if normalized == "CPF":
        return EntityType.CPF
    if normalized == "CAEPF":
        return EntityType.CAEPF
    return EntityType.UNKNOWN


def is_valid_cnpj(value: object) -> bool:
    cnpj = digits_only(value)
    if len(cnpj) != 14 or len(set(cnpj)) == 1:
        return False

    numbers = [int(char) for char in cnpj]

    def check_digit(base: list[int], weights: list[int]) -> int:
        remainder = sum(n * w for n, w in zip(base, weights, strict=True)) % 11
        return 0 if remainder < 2 else 11 - remainder

    first = check_digit(numbers[:12], [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    second = check_digit(numbers[:12] + [first], [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    return numbers[12] == first and numbers[13] == second


def format_cnpj(value: object) -> str:
    cnpj = digits_only(value)
    if len(cnpj) != 14:
        return cnpj
    return f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"


@dataclass(frozen=True, slots=True)
class CompanyRecord:
    source_key: str
    row_number: int
    company_name: str
    entity_type: EntityType
    identifier: str
    previous_status: str = ""

    @property
    def eligible_for_automation(self) -> bool:
        return self.entity_type is EntityType.CNPJ and is_valid_cnpj(self.identifier)


@dataclass(frozen=True, slots=True)
class PortalResult:
    status: PortalResultStatus
    confirmed_cnpj: str
    report_path: str | None = None
