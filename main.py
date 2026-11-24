"""FocaAI - Sistema Anti-Procrastinacao. Execute:  python main.py"""
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

from database.db import Banco
from models.usuario import Usuario
from services.gerenciador_sessao import GerenciadorSessoes
from ui.app import FocaAIApp


def main():
    banco = Banco(os.path.join(BASE, "focaai.db"))       # dados locais, preservados ao reiniciar (RNF06)
    gerenciador = GerenciadorSessoes(banco)
    usuario = Usuario(banco)
    FocaAIApp(banco, gerenciador, usuario).mainloop()


if __name__ == "__main__":
    main()
