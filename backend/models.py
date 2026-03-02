from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import date, datetime

class Atleta(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str
    nivel: int
    posicao: str
    mensalista: bool
    titulos: int = 0

class Pelada(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    data: date
    local: str
    status: str = "planejada"
    campeao: Optional[str] = None

class PeladaCreate(SQLModel):
    data: date
    local: str

class Presenca(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    pelada_id: int = Field(foreign_key="pelada.id")
    atleta_id: int = Field(foreign_key="atleta.id")
    confirmado: bool = True

class PresencaCreate(SQLModel):
    atletas_ids: list[int]

class Time(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    pelada_id: int = Field(foreign_key="pelada.id")
    nome: str
    cor: str

class TimeCreate(SQLModel):
    nome: str
    cor: str
    atletas_ids: list[int]

class TimeAtleta(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    time_id: int = Field(foreign_key="time.id")
    atleta_id: int = Field(foreign_key="atleta.id")

class Jogo(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    pelada_id: int

    time_a_id: int
    time_b_id: int

    gols_time_a: int = 0
    gols_time_b: int = 0

    tempo_minutos: int

    status: str = "nao_iniciado"
    # valores: nao_iniciado | em_andamento | finalizado

    criado_em: datetime = Field(default_factory=datetime.utcnow)
    finalizado_em: Optional[datetime] = None

class Partida(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    jogo_id: int
    tempo_minutos: int
    iniciada_em: Optional[datetime] = None
    finalizada_em: Optional[datetime] = None
    placar_a: int = 0
    placar_b: int = 0
    status: str = "em_andamento"  # <<< CAMPO QUE FALTAVA

class EventoPartida(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    partida_id: int
    time_id: int
    atleta_gol_id: Optional[int] = None  # ← torna opcional
    atleta_assistencia_id: Optional[int] = None
    instante_segundos: int

