"""Relógio único. Todo datetime gravado no banco é UTC *naive* (SQLite não guarda fuso).
O "dia" do usuário (limites diários, streak, missões) é sempre o dia em America/Sao_Paulo."""
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

try:
    TZ = ZoneInfo("America/Sao_Paulo")
except ZoneInfoNotFoundError:  # Windows sem tzdata; o Brasil não tem horário de verão desde 2019
    TZ = timezone(timedelta(hours=-3), "America/Sao_Paulo")


def agora() -> datetime:
    """UTC naive — o formato de tudo que é persistido."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def hoje() -> date:
    return datetime.now(TZ).date()


def para_local(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc).astimezone(TZ) if dt.tzinfo is None else dt.astimezone(TZ)


def inicio_do_dia_utc(d: date) -> datetime:
    """Meia-noite local de `d`, expressa em UTC naive (para filtrar colunas datetime)."""
    return datetime(d.year, d.month, d.day, tzinfo=TZ).astimezone(timezone.utc).replace(tzinfo=None)


def inicio_da_semana(d: date | None = None) -> date:
    d = d or hoje()
    return d - timedelta(days=d.weekday())  # segunda-feira


def chave_semana(d: date | None = None) -> str:
    iso = (d or hoje()).isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def local_para_utc(dt: datetime) -> datetime:
    """Data/hora digitada no fuso de Brasília -> UTC naive (como as colunas do banco)."""
    return dt.replace(tzinfo=TZ).astimezone(timezone.utc).replace(tzinfo=None)
