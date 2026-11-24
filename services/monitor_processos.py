"""UC05 - Bloquear aplicativos durante a sessao (RF04, RF05, RF06, RNF02, RNF03)."""
import os
import threading
from collections import defaultdict
from typing import Callable, Optional

import psutil

from database.db import Banco, agora_str
from models.modelos import TentativaAbertura, eh_protegido, normalizar_processo


class MonitorProcessos:
    INTERVALO = 0.5   # RNF02: app bloqueado deve ser encerrado em ate 2 s

    def __init__(self, banco: Banco, sessao_id: int,
                 ao_evento: Optional[Callable[[str, dict], None]] = None):
        self.banco = banco
        self.sessao_id = sessao_id
        self.ao_evento = ao_evento or (lambda tipo, dados: None)
        self.ativo = False
        self._parar = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._meu_pid = os.getpid()

    # -- ciclo de vida --
    def iniciar(self):
        self.ativo = True
        self._parar.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="MonitorProcessos")
        self._thread.start()

    def parar(self):
        self.ativo = False
        self._parar.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)

    def _loop(self):
        while not self._parar.wait(self.INTERVALO):
            try:
                self.monitorar()
            except Exception as e:      # o monitor nunca deve derrubar o sistema
                self.ao_evento("info", {"texto": f"Erro no monitor de processos: {e}"})

    # -- logica --
    def monitorar(self) -> int:
        """Faz UMA varredura. Retorna quantos aplicativos distintos foram bloqueados."""
        bloqueados = {normalizar_processo(a.nome_processo): a.nome_processo
                      for a in self.banco.listar_apps() if not eh_protegido(a.nome_processo)}
        if not bloqueados:
            return 0
        encontrados = defaultdict(list)
        for p in psutil.process_iter(["pid", "name"]):
            nome = p.info.get("name") or ""
            chave = normalizar_processo(nome)
            if chave in bloqueados and p.info["pid"] != self._meu_pid:
                encontrados[chave].append(p)
        for chave, procs in encontrados.items():
            self.encerrar_processo(bloqueados[chave], procs)
        return len(encontrados)

    def encerrar_processo(self, nome: str, procs=None) -> bool:
        """Encerra todos os processos com esse nome. Retorna True se todos foram encerrados."""
        if procs is None:
            alvo = normalizar_processo(nome)
            procs = [p for p in psutil.process_iter(["name"])
                     if normalizar_processo(p.info.get("name") or "") == alvo]
        ok = True
        for p in procs:
            try:
                p.kill()
            except psutil.NoSuchProcess:
                pass
            except (psutil.AccessDenied, PermissionError):
                ok = False
        self.registrar_tentativa(nome, ok)
        return ok

    def registrar_tentativa(self, nome: str, sucesso: bool = True) -> TentativaAbertura:
        t = self.banco.registrar_tentativa(
            TentativaAbertura(self.sessao_id, nome, agora_str(), sucesso))
        if sucesso:
            self.ao_evento("bloqueio", {"processo": nome, "texto": f"Aplicativo {nome} bloqueado durante a sessão"})
        else:
            self.ao_evento("bloqueio_falha", {"processo": nome,
                           "texto": f"Sem permissão para encerrar {nome} (falha registrada)"})   # E1 do UC05
        return t
