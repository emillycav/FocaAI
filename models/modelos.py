"""Classes de dominio do FocaAI (espelham o Diagrama de Classes da AV1)."""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

TOLERANCIA_PADRAO_MIN = 5
TOLERANCIA_MIN, TOLERANCIA_MAX = 1, 30          # RN03

# Status possiveis de uma SessaoFoco
AGENDADA, ATIVA, FINALIZADA, INTERROMPIDA, PERDIDA = (
    "agendada", "ativa", "finalizada", "interrompida", "perdida")

# RN07 - aplicativos essenciais que nunca podem ser bloqueados
PROTEGIDOS = {
    "system", "system idle process", "registry", "smss", "csrss", "wininit",
    "winlogon", "services", "lsass", "svchost", "dwm", "explorer", "taskmgr",
    "searchhost", "startmenuexperiencehost", "runtimebroker", "fontdrvhost",
    "ctfmon", "sihost", "conhost", "cmd", "powershell", "python", "pythonw",
    "py", "focaai", "systemd", "init", "bash", "sh", "login",
}


def normalizar_processo(nome: str) -> str:
    """'Discord.exe' e 'discord' passam a ser o mesmo nome."""
    n = nome.strip().lower()
    return n[:-4] if n.endswith(".exe") else n


def eh_protegido(nome: str) -> bool:
    return normalizar_processo(nome) in PROTEGIDOS


@dataclass
class SessaoFoco:
    nome: str
    data: str                 # AAAA-MM-DD
    horario_inicio: str       # HH:MM
    horario_fim: str          # HH:MM
    status: str = AGENDADA
    id: Optional[int] = None

    def inicio_dt(self) -> datetime:
        return datetime.strptime(f"{self.data} {self.horario_inicio}", "%Y-%m-%d %H:%M")

    def fim_dt(self) -> datetime:
        return datetime.strptime(f"{self.data} {self.horario_fim}", "%Y-%m-%d %H:%M")


@dataclass
class AplicativoBloqueado:
    nome_processo: str
    categoria: str = "Outros"
    id: Optional[int] = None

    def get_nome_processo(self) -> str:
        return self.nome_processo


@dataclass
class Configuracao:
    tempo_tolerancia_minutos: int = TOLERANCIA_PADRAO_MIN
    aviso_sonoro: bool = True
    aviso_visual: bool = True
    camera_ativa: bool = True
    modo_demo: bool = False   # demonstracao: tolerancia conta em SEGUNDOS

    def tolerancia_segundos(self) -> int:
        n = self.tempo_tolerancia_minutos
        return n if self.modo_demo else n * 60


@dataclass
class TentativaAbertura:
    sessao_id: int
    nome_processo: str
    data_hora: str
    sucesso: bool = True
    id: Optional[int] = None


@dataclass
class OcorrenciaDistracao:
    sessao_id: int
    data_hora: str
    duracao_ausencia: int = 0   # segundos
    id: Optional[int] = None


@dataclass
class ResumoSessao:
    sessao_id: int
    tempo_total_seg: int
    tempo_efetivo_foco_seg: int
    numero_bloqueios: int
    numero_ausencias: int
    id: Optional[int] = None

    @property
    def percentual_foco(self) -> float:
        if self.tempo_total_seg <= 0:
            return 100.0
        return round(100.0 * self.tempo_efetivo_foco_seg / self.tempo_total_seg, 1)

    def gerar_relatorio(self) -> str:
        def fmt(s):
            h, r = divmod(int(s), 3600)
            m, sec = divmod(r, 60)
            return f"{h:02d}:{m:02d}:{sec:02d}"
        return (f"Tempo total: {fmt(self.tempo_total_seg)}\n"
                f"Tempo focado: {fmt(self.tempo_efetivo_foco_seg)} ({self.percentual_foco}%)\n"
                f"Aplicativos bloqueados: {self.numero_bloqueios}\n"
                f"Ausencias/distracoes: {self.numero_ausencias}")
