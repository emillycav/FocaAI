"""Classe Usuario do Diagrama de Classes: fachada para as operacoes que o usuario realiza."""
from dataclasses import dataclass
from typing import List

from database.db import Banco
from models.modelos import (TOLERANCIA_MAX, TOLERANCIA_MIN, AplicativoBloqueado, ResumoSessao, SessaoFoco,
                            eh_protegido)


class ErroRegra(Exception):
    pass


@dataclass
class Usuario:
    banco: Banco
    nome: str = "Usuário"
    email: str = ""
    id: int = 1

    def cadastrar_sessao(self, gerenciador, nome, data, inicio, fim) -> SessaoFoco:
        return gerenciador.cadastrar_sessao(nome, data, inicio, fim)

    def consultar_historico(self, de=None, ate=None) -> List[tuple]:
        return self.banco.listar_historico(de, ate)

    def adicionar_aplicativo(self, nome_processo: str, categoria: str = "Outros") -> AplicativoBloqueado:
        nome = nome_processo.strip()
        if not nome:
            raise ErroRegra("Informe o nome do executável.")
        if eh_protegido(nome):                                   # RN07 / E1 do UC02
            raise ErroRegra(f"'{nome}' é um aplicativo essencial do sistema e não pode ser bloqueado.")
        if self.banco.existe_app(nome):                          # E2 do UC02
            raise ErroRegra(f"'{nome}' já está na lista de bloqueio.")
        return self.banco.adicionar_app(nome, categoria)

    def remover_aplicativo(self, app_id: int):
        self.banco.remover_app(app_id)

    def configurar_tolerancia(self, minutos: int):
        if not (TOLERANCIA_MIN <= minutos <= TOLERANCIA_MAX):    # RN03 / E1 do UC03
            raise ErroRegra(f"A tolerância deve ficar entre {TOLERANCIA_MIN} e {TOLERANCIA_MAX} minutos.")
        cfg = self.banco.obter_config()
        cfg.tempo_tolerancia_minutos = minutos
        self.banco.salvar_config(cfg)
