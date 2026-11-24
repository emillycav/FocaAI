"""UC01, UC04, UC08, UC09 - ciclo de vida das sessoes de foco (RF01, RF03, RF12, RF13)."""
import queue
import re
import threading
from datetime import date, datetime
from typing import Optional

from database.db import Banco
from models.modelos import (AGENDADA, ATIVA, FINALIZADA, INTERROMPIDA, PERDIDA, ResumoSessao, SessaoFoco,
                            eh_protegido)
from services.monitor_processos import MonitorProcessos
from services.monitor_webcam import MonitorWebcam


class ErroValidacao(Exception):
    """Erro de regra de negocio mostrado ao usuario (fluxos de excecao E1)."""


def converter_data(txt: str) -> str:
    """Aceita DD/MM/AAAA (ou AAAA-MM-DD) e devolve AAAA-MM-DD."""
    txt = txt.strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(txt, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    raise ErroValidacao("Data inválida. Use o formato DD/MM/AAAA.")


def converter_hora(txt: str) -> str:
    txt = txt.strip()
    if not re.fullmatch(r"\d{1,2}:\d{2}", txt):
        raise ErroValidacao("Horário inválido. Use o formato HH:MM.")
    try:
        return datetime.strptime(txt, "%H:%M").strftime("%H:%M")
    except ValueError:
        raise ErroValidacao("Horário inválido. Use o formato HH:MM.")


class GerenciadorSessoes:
    def __init__(self, banco: Banco, relogio=datetime.now):
        self.banco = banco
        self.relogio = relogio
        self.eventos: "queue.Queue[tuple]" = queue.Queue()   # a interface consome esta fila
        self.sessao_ativa: Optional[SessaoFoco] = None
        self.monitor_proc: Optional[MonitorProcessos] = None
        self.monitor_cam: Optional[MonitorWebcam] = None
        self._inicio_real: Optional[datetime] = None
        self._trava = threading.RLock()
        self._parar = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def _emitir(self, tipo: str, dados: Optional[dict] = None):
        self.eventos.put((tipo, dados or {}))

    # ---------- agendador (RF03) ----------
    def iniciar_agendador(self):
        self._parar.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="Agendador")
        self._thread.start()

    def parar_agendador(self):
        self._parar.set()

    def _loop(self):
        while not self._parar.wait(1.0):
            try:
                self.verificar_agenda()
            except Exception as e:
                self._emitir("info", {"texto": f"Erro no agendador: {e}"})

    def verificar_agenda(self):
        agora = self.relogio()
        with self._trava:
            if self.sessao_ativa is not None:
                if agora >= self.sessao_ativa.fim_dt():
                    self.finalizar_sessao()                  # UC08, fluxo principal
                return
            for s in self.banco.listar_sessoes():
                if s.status != AGENDADA:
                    continue
                if s.inicio_dt() <= agora < s.fim_dt():
                    self.iniciar_sessao(s.id)                # UC04, fluxo principal
                    return
                if agora >= s.fim_dt():
                    self.banco.definir_status(s.id, PERDIDA)

    # ---------- UC01 ----------
    def validar_sessao(self, data: str, inicio: str, fim: str, ignorar_id=None):
        if not data or not inicio or not fim:
            raise ErroValidacao("Preencha data, hora de início e hora de fim.")
        if fim <= inicio:
            raise ErroValidacao("O horário de fim deve ser posterior ao de início.")           # E1
        conflito = self.banco.sessoes_conflitantes(data, inicio, fim, ignorar_id)
        if conflito:
            c = conflito[0]
            raise ErroValidacao(f"Horário sobreposto à sessão '{c.nome}' "
                                f"({c.horario_inicio}–{c.horario_fim}).")                       # RN01

    def cadastrar_sessao(self, nome: str, data: str, inicio: str, fim: str) -> SessaoFoco:
        nome = nome.strip() or "Sessão de foco"
        data, inicio, fim = converter_data(data), converter_hora(inicio), converter_hora(fim)
        self.validar_sessao(data, inicio, fim)
        return self.banco.inserir_sessao(SessaoFoco(nome, data, inicio, fim))

    def editar_sessao(self, sid: int, nome: str, data: str, inicio: str, fim: str):
        s = self.banco.obter_sessao(sid)
        if s is None or s.status == ATIVA:
            raise ErroValidacao("Não é possível editar uma sessão ativa.")
        s.nome = nome.strip() or s.nome
        s.data, s.horario_inicio, s.horario_fim = converter_data(data), converter_hora(inicio), converter_hora(fim)
        self.validar_sessao(s.data, s.horario_inicio, s.horario_fim, ignorar_id=sid)
        s.status = AGENDADA
        self.banco.atualizar_sessao(s)
        self.banco.definir_status(sid, AGENDADA)

    def excluir_sessao(self, sid: int):
        s = self.banco.obter_sessao(sid)
        if s and s.status == ATIVA:
            raise ErroValidacao("Encerre a sessão ativa antes de excluí-la.")
        self.banco.excluir_sessao(sid)

    def criar_sessao_rapida(self, minutos: int) -> SessaoFoco:
        """Conveniencia para demonstracao: cria e inicia uma sessao de 'minutos' a partir de agora."""
        from datetime import timedelta
        agora = self.relogio().replace(second=0, microsecond=0)
        fim = agora + timedelta(minutes=minutos + 1)   # +1: o minuto corrente ja esta em andamento
        if fim.date() != agora.date():
            raise ErroValidacao("A sessão rápida não pode atravessar a meia-noite.")
        s = self.cadastrar_sessao(f"Sessão rápida ({minutos} min)", agora.strftime("%d/%m/%Y"),
                                  agora.strftime("%H:%M"), fim.strftime("%H:%M"))
        self.iniciar_sessao(s.id)
        return s

    # ---------- UC04 ----------
    def iniciar_sessao(self, sid: int):
        with self._trava:
            if self.sessao_ativa is not None:                                                   # E1, RN01
                raise ErroValidacao("Já existe uma sessão ativa.")
            s = self.banco.obter_sessao(sid)
            if s is None:
                raise ErroValidacao("Sessão não encontrada.")
            if self.relogio() >= s.fim_dt():
                raise ErroValidacao("O horário de fim desta sessão já passou.")
            self.banco.definir_status(sid, ATIVA)
            s.status = ATIVA
            self.sessao_ativa = s
            self._inicio_real = self.relogio()
            self.monitor_proc = MonitorProcessos(self.banco, sid, self._emitir)             # UC05
            self.monitor_proc.iniciar()
            self.monitor_cam = None
            cfg = self.banco.obter_config()
            if cfg.camera_ativa:                                                            # UC06 / RN06
                cam = MonitorWebcam(self.banco, sid, cfg, self._emitir)
                if cam.iniciar():
                    self.monitor_cam = cam
            else:
                self._emitir("info", {"texto": "Câmera desativada: a sessão usa apenas o bloqueio de aplicativos."})
            self._emitir("sessao_iniciada", {"sessao": s})

    # ---------- UC08 / UC09 ----------
    def encerrar_antecipado(self) -> ResumoSessao:
        """A1 do UC08. A confirmacao (RN08) e pedida pela interface antes de chamar este metodo."""
        return self.finalizar_sessao(interrompida=True)

    def finalizar_sessao(self, interrompida: bool = False) -> Optional[ResumoSessao]:
        with self._trava:
            s = self.sessao_ativa
            if s is None:
                return None
            if self.monitor_cam:
                self.monitor_cam.parar()
            if self.monitor_proc:
                self.monitor_proc.parar()
            resumo = self._gerar_resumo(s)
            status = INTERROMPIDA if interrompida else FINALIZADA
            self.banco.definir_status(s.id, status)
            s.status = status
            self.banco.salvar_resumo(resumo)                                                # UC09, passo 3
            self.sessao_ativa = self.monitor_proc = self.monitor_cam = None
            self._emitir("sessao_finalizada", {"sessao": s, "resumo": resumo})
            return resumo

    def _gerar_resumo(self, s: SessaoFoco) -> ResumoSessao:
        total = max(0, int((self.relogio() - self._inicio_real).total_seconds()))
        ausente = int(self.monitor_cam.tempo_ausente_seg) if self.monitor_cam else 0
        ausencias = self.monitor_cam.numero_ausencias if self.monitor_cam else 0
        bloqueios = sum(1 for t in self.banco.listar_tentativas(s.id) if t.sucesso)
        return ResumoSessao(s.id, total, max(0, total - ausente), bloqueios, ausencias)

    # ---------- consultas para a interface ----------
    def segundos_restantes(self) -> int:
        if self.sessao_ativa is None:
            return 0
        return max(0, int((self.sessao_ativa.fim_dt() - self.relogio()).total_seconds()))

    def estado_foco(self):
        """(estado, contagem_regressiva) do monitor de webcam, ou (None, 0) se nao houver camera."""
        if self.monitor_cam is None:
            return None, 0
        return self.monitor_cam.estado, self.monitor_cam.contagem_regressiva

    def contadores(self):
        if self.sessao_ativa is None:
            return 0, 0
        bloqueios = sum(1 for t in self.banco.listar_tentativas(self.sessao_ativa.id) if t.sucesso)
        return bloqueios, (self.monitor_cam.numero_ausencias if self.monitor_cam else 0)
