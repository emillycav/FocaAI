"""Tema visual do FocaAI: paleta, fontes e estilos ttk em um unico lugar.

Para mudar o visual do sistema inteiro basta editar as constantes abaixo.
"""
import tkinter as tk
from tkinter import ttk

# ---------------------------------------------------------------- paleta (tons de vermelho)
DESTAQUE, DESTAQUE_ESCURO, DESTAQUE_CLARO = "#B3202A", "#7F1520", "#FBE9E7"   # cor da marca
FUNDO, BRANCO, BORDA = "#FBF7F6", "#FFFFFF", "#E8D9D6"
TEXTO, CINZA = "#2B1B1B", "#7A6462"
VERDE, LARANJA, VERMELHO = "#2E7D32", "#B85C00", "#C62828"                     # estados (foco / alerta / erro)
SELECAO = "#F7D4D0"
LATERAL, LATERAL_ATIVO, LATERAL_HOVER = "#6B111B", "#B3202A", "#8A1A26"            # menu lateral

# ---------------------------------------------------------------- fontes
FONTE, FONTE_MONO = "Segoe UI", "Consolas"


def aplicar(root: tk.Tk) -> None:
    """Configura o tema 'clam' com a identidade visual do FocaAI."""
    root.configure(bg=FUNDO)
    st = ttk.Style(root)
    try:
        st.theme_use("clam")
    except tk.TclError:
        pass

    # base: tudo herda fundo, cor de texto e fonte
    st.configure(".", background=FUNDO, foreground=TEXTO, font=(FONTE, 11),
                 bordercolor=BORDA, focuscolor=DESTAQUE_ESCURO, troughcolor=FUNDO)   # foco visivel (teclado)
    st.configure("TFrame", background=FUNDO)
    st.configure("TLabel", background=FUNDO, foreground=TEXTO)
    st.configure("Titulo.TLabel", font=(FONTE, 20, "bold"), foreground=DESTAQUE_ESCURO)
    st.configure("Sub.TLabel", foreground=CINZA)

    # abas
    st.configure("TNotebook", background=FUNDO, borderwidth=0, tabmargins=(0, 4, 0, 0))
    st.configure("TNotebook.Tab", padding=(20, 11), font=(FONTE, 11, "bold"),
                 background=DESTAQUE_CLARO, foreground=CINZA, borderwidth=0)
    st.map("TNotebook.Tab",
           background=[("selected", DESTAQUE), ("active", SELECAO)],
           foreground=[("selected", "white"), ("active", DESTAQUE_ESCURO)])

    # botoes: padrao (secundario), Acao (principal) e Perigo
    st.configure("TButton", padding=(14, 9), background=BRANCO, foreground=TEXTO,
                 bordercolor=BORDA, relief="flat")
    st.map("TButton",
           background=[("disabled", "#F3EEED"), ("pressed", SELECAO), ("active", DESTAQUE_CLARO)],
           foreground=[("disabled", "#B3A3A1")])
    st.configure("Acao.TButton", font=(FONTE, 11, "bold"), padding=(18, 11),
                 background=DESTAQUE, foreground="white", bordercolor=DESTAQUE)
    st.map("Acao.TButton",
           background=[("disabled", "#DDB5B2"), ("pressed", DESTAQUE_ESCURO), ("active", DESTAQUE_ESCURO)],
           foreground=[("disabled", "white")], bordercolor=[("disabled", "#DDB5B2")])
    st.configure("Perigo.TButton", font=(FONTE, 11, "bold"), padding=(18, 11),
                 background=BRANCO, foreground=DESTAQUE_ESCURO, bordercolor=DESTAQUE_ESCURO)
    st.map("Perigo.TButton",
           background=[("disabled", "#F3EEED"), ("pressed", SELECAO), ("active", DESTAQUE_CLARO)],
           foreground=[("disabled", "#B3A3A1")], bordercolor=[("disabled", BORDA)])

    # campos de entrada
    for campo in ("TEntry", "TCombobox", "TSpinbox"):
        st.configure(campo, padding=7, fieldbackground=BRANCO, foreground=TEXTO, bordercolor=BORDA)
        st.map(campo, bordercolor=[("focus", DESTAQUE)], lightcolor=[("focus", DESTAQUE)])
    st.map("TCombobox", fieldbackground=[("readonly", BRANCO)],
           selectbackground=[("readonly", BRANCO)], selectforeground=[("readonly", TEXTO)])
    root.option_add("*TCombobox*Listbox.font", (FONTE, 11))
    root.option_add("*TCombobox*Listbox.selectBackground", SELECAO)
    root.option_add("*TCombobox*Listbox.selectForeground", TEXTO)

    # grupos e caixas de selecao
    st.configure("TLabelframe", background=FUNDO, bordercolor=BORDA, relief="solid", borderwidth=1)
    st.configure("TLabelframe.Label", background=FUNDO, foreground=DESTAQUE, font=(FONTE, 11, "bold"))
    st.configure("TCheckbutton", background=FUNDO)
    st.map("TCheckbutton", background=[("active", FUNDO)])

    # tabelas
    st.configure("Treeview", rowheight=36, font=(FONTE, 11), background=BRANCO,
                 fieldbackground=BRANCO, foreground=TEXTO, bordercolor=BORDA, borderwidth=1)
    st.map("Treeview", background=[("selected", SELECAO)], foreground=[("selected", TEXTO)])
    st.configure("Treeview.Heading", font=(FONTE, 11, "bold"), background=DESTAQUE,
                 foreground="white", relief="flat", padding=(8, 7))
    st.map("Treeview.Heading", background=[("active", DESTAQUE_ESCURO)])

    # barras de rolagem
    st.configure("Vertical.TScrollbar", background="#EBC4C0", troughcolor=FUNDO,
                 bordercolor=FUNDO, arrowcolor=DESTAQUE, gripcount=0)
    st.map("Vertical.TScrollbar", background=[("active", "#DFA29C")])