"""Testes automatizados das regras de negocio (rodar: python -m unittest discover -s tests -v)."""
import os
import subprocess
import sys
import time
import unittest
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.db import Banco
from models.modelos import ATIVA, FINALIZADA, INTERROMPIDA, PERDIDA, Configuracao
from models.usuario import ErroRegra, Usuario
from services.gerenciador_sessao import ErroValidacao, GerenciadorSessoes
from services.monitor_processos import MonitorProcessos
from services.monitor_webcam import AUSENTE, CONTANDO, FOCADO, MonitorWebcam


class DetectorFalso:
    def __init__(self): self.valor = True
    def analisar(self): return self.valor


class Relogio:
    def __init__(self, inicio): self.t = inicio
    def __call__(self): return self.t


class TestRegras(unittest.TestCase):
    def setUp(self):
        self.banco = Banco(":memory:")
        self.ger = GerenciadorSessoes(self.banco)
        self.user = Usuario(self.banco)

    def test_rn01_sobreposicao_e_horario_invalido(self):
        self.ger.cadastrar_sessao("A", "10/12/2030", "13:00", "16:00")
        with self.assertRaises(ErroValidacao):
            self.ger.cadastrar_sessao("B", "10/12/2030", "15:00", "17:00")   # sobrepoe
        with self.assertRaises(ErroValidacao):
            self.ger.cadastrar_sessao("C", "10/12/2030", "18:00", "17:00")   # fim < inicio
        self.ger.cadastrar_sessao("D", "10/12/2030", "16:00", "17:00")       # colada, ok
        self.assertEqual(len(self.banco.listar_sessoes()), 2)

    def test_formatos_invalidos(self):
        with self.assertRaises(ErroValidacao):
            self.ger.cadastrar_sessao("A", "31/02/2030", "13:00", "16:00")
        with self.assertRaises(ErroValidacao):
            self.ger.cadastrar_sessao("A", "10/12/2030", "25:00", "26:00")

    def test_rn07_e_duplicado(self):
        with self.assertRaises(ErroRegra):
            self.user.adicionar_aplicativo("explorer.exe")
        with self.assertRaises(ErroRegra):
            self.user.adicionar_aplicativo("Discord")          # ja existe (Discord.exe)
        self.user.adicionar_aplicativo("jogo.exe", "Jogos")
        self.assertTrue(self.banco.existe_app("JOGO"))

    def test_rn03_tolerancia(self):
        for ruim in (0, 31, -2):
            with self.assertRaises(ErroRegra):
                self.user.configurar_tolerancia(ruim)
        self.user.configurar_tolerancia(10)
        self.assertEqual(self.banco.obter_config().tempo_tolerancia_minutos, 10)

    def test_persistencia_config(self):
        c = Configuracao(7, False, True, False, True)
        self.banco.salvar_config(c)
        self.assertEqual(self.banco.obter_config(), c)


class TestWebcam(unittest.TestCase):
    def setUp(self):
        self.banco = Banco(":memory:")
        s = self.banco.inserir_sessao(__import__("models.modelos", fromlist=["x"]).SessaoFoco(
            "t", "2030-01-01", "10:00", "11:00"))
        self.sid = s.id
        self.eventos = []
        self.cfg = Configuracao(tempo_tolerancia_minutos=5)
        self.m = MonitorWebcam(self.banco, self.sid, self.cfg, lambda t, d: self.eventos.append(t),
                               detector=DetectorFalso(), janela_suavizacao=1)

    def tipos(self): return self.eventos

    def test_volta_antes_do_prazo_cancela(self):
        self.m.verificar_atencao_presenca(False, 0)
        self.assertEqual(self.m.estado, CONTANDO)
        self.m.verificar_atencao_presenca(False, 200)          # 3m20s < 5min
        self.m.verificar_atencao_presenca(True, 250)
        self.assertEqual(self.m.estado, FOCADO)
        self.assertNotIn("aviso", self.tipos())
        self.assertIn("contagem_cancelada", self.tipos())
        self.assertEqual(self.banco.listar_ocorrencias(self.sid), [])      # RN04: sem aviso, sem ocorrencia

    def test_estourou_tolerancia_avisa_e_registra(self):
        self.m.verificar_atencao_presenca(False, 0)
        self.m.verificar_atencao_presenca(False, 299)
        self.assertEqual(self.m.estado, CONTANDO)
        self.m.verificar_atencao_presenca(False, 301)
        self.assertEqual(self.m.estado, AUSENTE)
        self.assertEqual(self.tipos().count("aviso"), 1)
        self.m.verificar_atencao_presenca(False, 400)          # nao repete o aviso
        self.assertEqual(self.tipos().count("aviso"), 1)
        self.m.verificar_atencao_presenca(True, 420)
        self.assertEqual(self.m.estado, FOCADO)
        oc = self.banco.listar_ocorrencias(self.sid)
        self.assertEqual(len(oc), 1)
        self.assertEqual(oc[0].duracao_ausencia, 420)
        self.assertEqual(self.m.tempo_ausente_seg, 420)

    def test_suavizacao_ignora_quadro_ruim(self):
        m = MonitorWebcam(self.banco, self.sid, self.cfg, detector=DetectorFalso(), janela_suavizacao=3)
        m.verificar_atencao_presenca(True, 0)
        m.verificar_atencao_presenca(False, 1)     # 1 quadro sem rosto: ainda considera presente
        self.assertEqual(m.estado, FOCADO)

    def test_modo_demo_conta_em_segundos(self):
        self.cfg.modo_demo = True
        self.cfg.tempo_tolerancia_minutos = 3
        self.m.verificar_atencao_presenca(False, 0)
        self.m.verificar_atencao_presenca(False, 4)
        self.assertEqual(self.m.estado, AUSENTE)


class TestProcessos(unittest.TestCase):
    def test_encerra_app_bloqueado_e_registra(self):
        banco = Banco(":memory:")
        s = banco.inserir_sessao(__import__("models.modelos", fromlist=["x"]).SessaoFoco(
            "t", "2030-01-01", "10:00", "11:00"))
        alvo = subprocess.Popen(["sleep", "60"])
        try:
            banco.adicionar_app("sleep", "Teste")
            eventos = []
            mon = MonitorProcessos(banco, s.id, lambda t, d: eventos.append(t))
            time.sleep(0.2)
            mon.monitorar()
            alvo.wait(timeout=2)                      # RNF02: morreu em < 2 s
            self.assertIsNotNone(alvo.returncode)
            self.assertEqual(len(banco.listar_tentativas(s.id)), 1)
            self.assertIn("bloqueio", eventos)
        finally:
            if alvo.poll() is None:
                alvo.kill()


class TestSessao(unittest.TestCase):
    def setUp(self):
        self.banco = Banco(":memory:")
        c = self.banco.obter_config(); c.camera_ativa = False; self.banco.salvar_config(c)
        self.rel = Relogio(datetime(2030, 1, 1, 12, 59, 50))
        self.ger = GerenciadorSessoes(self.banco, relogio=self.rel)

    def test_agenda_inicia_e_finaliza_sozinha(self):
        s = self.ger.cadastrar_sessao("Estudo", "01/01/2030", "13:00", "14:00")
        self.ger.verificar_agenda()
        self.assertIsNone(self.ger.sessao_ativa)               # ainda nao deu a hora
        self.rel.t = datetime(2030, 1, 1, 13, 0, 1)
        self.ger.verificar_agenda()
        self.assertEqual(self.ger.sessao_ativa.id, s.id)       # RF03
        self.assertEqual(self.banco.obter_sessao(s.id).status, ATIVA)
        self.rel.t = datetime(2030, 1, 1, 14, 0, 1)
        self.ger.verificar_agenda()
        self.assertIsNone(self.ger.sessao_ativa)
        self.assertEqual(self.banco.obter_sessao(s.id).status, FINALIZADA)
        hist = self.banco.listar_historico()
        self.assertEqual(len(hist), 1)
        self.assertEqual(hist[0][1].tempo_total_seg, 3600)
        self.assertEqual(hist[0][1].percentual_foco, 100.0)

    def test_uma_sessao_ativa_por_vez(self):
        a = self.ger.cadastrar_sessao("A", "01/01/2030", "12:00", "15:00")
        b = self.ger.cadastrar_sessao("B", "01/01/2030", "16:00", "17:00")
        self.ger.iniciar_sessao(a.id)
        with self.assertRaises(ErroValidacao):
            self.ger.iniciar_sessao(b.id)
        self.ger.encerrar_antecipado()
        self.assertEqual(self.banco.obter_sessao(a.id).status, INTERROMPIDA)   # RN08

    def test_sessao_perdida(self):
        s = self.ger.cadastrar_sessao("A", "01/01/2030", "13:00", "14:00")
        self.rel.t = datetime(2030, 1, 1, 15, 0, 0)
        self.ger.verificar_agenda()
        self.assertEqual(self.banco.obter_sessao(s.id).status, PERDIDA)


if __name__ == "__main__":
    unittest.main()
