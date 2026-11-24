"""Persistencia local em SQLite (RNF06) - funciona offline (RNF07)."""
import sqlite3
import threading
from datetime import datetime
from typing import List, Optional

from models.modelos import (AplicativoBloqueado, Configuracao, OcorrenciaDistracao,
                            ResumoSessao, SessaoFoco, TentativaAbertura, normalizar_processo)

ISO = "%Y-%m-%d %H:%M:%S"

ESQUEMA = """
CREATE TABLE IF NOT EXISTS sessao (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL, data TEXT NOT NULL,
    horario_inicio TEXT NOT NULL, horario_fim TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'agendada');
CREATE TABLE IF NOT EXISTS app_bloqueado (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome_processo TEXT NOT NULL UNIQUE, categoria TEXT NOT NULL DEFAULT 'Outros');
CREATE TABLE IF NOT EXISTS configuracao (chave TEXT PRIMARY KEY, valor TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS tentativa_abertura (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sessao_id INTEGER NOT NULL REFERENCES sessao(id) ON DELETE CASCADE,
    nome_processo TEXT NOT NULL, data_hora TEXT NOT NULL, sucesso INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS ocorrencia_distracao (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sessao_id INTEGER NOT NULL REFERENCES sessao(id) ON DELETE CASCADE,
    data_hora TEXT NOT NULL, duracao_ausencia INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS resumo_sessao (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sessao_id INTEGER NOT NULL UNIQUE REFERENCES sessao(id) ON DELETE CASCADE,
    tempo_total_seg INTEGER NOT NULL, tempo_efetivo_foco_seg INTEGER NOT NULL,
    numero_bloqueios INTEGER NOT NULL, numero_ausencias INTEGER NOT NULL);
"""

APPS_INICIAIS = [("Discord.exe", "Redes sociais"), ("steam.exe", "Jogos"),
                 ("LeagueClient.exe", "Jogos"), ("Spotify.exe", "Entretenimento"),
                 ("WhatsApp.exe", "Redes sociais")]


def agora_str() -> str:
    return datetime.now().strftime(ISO)


class Banco:
    def __init__(self, caminho: str = "focaai.db"):
        self._lock = threading.RLock()
        self.con = sqlite3.connect(caminho, check_same_thread=False)
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA foreign_keys = ON")
        with self._lock:
            self.con.executescript(ESQUEMA)
            self.con.commit()
        self._semear()

    def _semear(self):
        if self._cfg_get("semeado") is None:
            for nome, cat in APPS_INICIAIS:
                self.con.execute("INSERT OR IGNORE INTO app_bloqueado(nome_processo, categoria) VALUES (?,?)",
                                 (nome, cat))
            self._cfg_set("semeado", "1")
            self.con.commit()

    def fechar(self):
        with self._lock:
            self.con.close()

    # ---------- configuracao ----------
    def _cfg_get(self, chave):
        r = self.con.execute("SELECT valor FROM configuracao WHERE chave=?", (chave,)).fetchone()
        return r["valor"] if r else None

    def _cfg_set(self, chave, valor):
        self.con.execute("INSERT INTO configuracao(chave, valor) VALUES (?,?) "
                         "ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor", (chave, str(valor)))

    def obter_config(self) -> Configuracao:
        with self._lock:
            padrao = Configuracao()
            g = self._cfg_get
            def b(chave, p):
                v = g(chave)
                return p if v is None else v == "1"
            v = g("tolerancia")
            return Configuracao(
                tempo_tolerancia_minutos=int(v) if v else padrao.tempo_tolerancia_minutos,
                aviso_sonoro=b("aviso_sonoro", padrao.aviso_sonoro),
                aviso_visual=b("aviso_visual", padrao.aviso_visual),
                camera_ativa=b("camera_ativa", padrao.camera_ativa),
                modo_demo=b("modo_demo", padrao.modo_demo))

    def salvar_config(self, c: Configuracao):
        with self._lock:
            self._cfg_set("tolerancia", c.tempo_tolerancia_minutos)
            for k in ("aviso_sonoro", "aviso_visual", "camera_ativa", "modo_demo"):
                self._cfg_set(k, "1" if getattr(c, k) else "0")
            self.con.commit()

    # ---------- aplicativos bloqueados ----------
    def listar_apps(self) -> List[AplicativoBloqueado]:
        with self._lock:
            rs = self.con.execute("SELECT * FROM app_bloqueado ORDER BY categoria, nome_processo").fetchall()
        return [AplicativoBloqueado(r["nome_processo"], r["categoria"], r["id"]) for r in rs]

    def adicionar_app(self, nome: str, categoria: str = "Outros") -> AplicativoBloqueado:
        with self._lock:
            cur = self.con.execute("INSERT INTO app_bloqueado(nome_processo, categoria) VALUES (?,?)",
                                   (nome.strip(), categoria))
            self.con.commit()
            return AplicativoBloqueado(nome.strip(), categoria, cur.lastrowid)

    def existe_app(self, nome: str) -> bool:
        alvo = normalizar_processo(nome)
        return any(normalizar_processo(a.nome_processo) == alvo for a in self.listar_apps())

    def remover_app(self, app_id: int):
        with self._lock:
            self.con.execute("DELETE FROM app_bloqueado WHERE id=?", (app_id,))
            self.con.commit()

    # ---------- sessoes ----------
    @staticmethod
    def _sessao(r) -> SessaoFoco:
        return SessaoFoco(r["nome"], r["data"], r["horario_inicio"], r["horario_fim"], r["status"], r["id"])

    def listar_sessoes(self) -> List[SessaoFoco]:
        with self._lock:
            rs = self.con.execute("SELECT * FROM sessao ORDER BY data, horario_inicio").fetchall()
        return [self._sessao(r) for r in rs]

    def obter_sessao(self, sid: int) -> Optional[SessaoFoco]:
        with self._lock:
            r = self.con.execute("SELECT * FROM sessao WHERE id=?", (sid,)).fetchone()
        return self._sessao(r) if r else None

    def inserir_sessao(self, s: SessaoFoco) -> SessaoFoco:
        with self._lock:
            cur = self.con.execute(
                "INSERT INTO sessao(nome,data,horario_inicio,horario_fim,status) VALUES (?,?,?,?,?)",
                (s.nome, s.data, s.horario_inicio, s.horario_fim, s.status))
            self.con.commit()
            s.id = cur.lastrowid
        return s

    def atualizar_sessao(self, s: SessaoFoco):
        with self._lock:
            self.con.execute("UPDATE sessao SET nome=?, data=?, horario_inicio=?, horario_fim=? WHERE id=?",
                             (s.nome, s.data, s.horario_inicio, s.horario_fim, s.id))
            self.con.commit()

    def definir_status(self, sid: int, status: str):
        with self._lock:
            self.con.execute("UPDATE sessao SET status=? WHERE id=?", (status, sid))
            self.con.commit()

    def excluir_sessao(self, sid: int):
        with self._lock:
            self.con.execute("DELETE FROM sessao WHERE id=?", (sid,))
            self.con.commit()

    def sessoes_conflitantes(self, data, inicio, fim, ignorar_id=None) -> List[SessaoFoco]:
        """RN01: sessoes no mesmo dia cujo intervalo se sobrepoe ao informado."""
        with self._lock:
            rs = self.con.execute(
                "SELECT * FROM sessao WHERE data=? AND horario_inicio < ? AND horario_fim > ? "
                "AND status IN ('agendada','ativa') AND (? IS NULL OR id <> ?)",
                (data, fim, inicio, ignorar_id, ignorar_id)).fetchall()
        return [self._sessao(r) for r in rs]

    # ---------- tentativas / ocorrencias ----------
    def registrar_tentativa(self, t: TentativaAbertura) -> TentativaAbertura:
        with self._lock:
            cur = self.con.execute(
                "INSERT INTO tentativa_abertura(sessao_id,nome_processo,data_hora,sucesso) VALUES (?,?,?,?)",
                (t.sessao_id, t.nome_processo, t.data_hora, 1 if t.sucesso else 0))
            self.con.commit()
            t.id = cur.lastrowid
        return t

    def listar_tentativas(self, sessao_id: int) -> List[TentativaAbertura]:
        with self._lock:
            rs = self.con.execute("SELECT * FROM tentativa_abertura WHERE sessao_id=? ORDER BY id",
                                  (sessao_id,)).fetchall()
        return [TentativaAbertura(r["sessao_id"], r["nome_processo"], r["data_hora"], bool(r["sucesso"]), r["id"])
                for r in rs]

    def criar_ocorrencia(self, o: OcorrenciaDistracao) -> OcorrenciaDistracao:
        with self._lock:
            cur = self.con.execute(
                "INSERT INTO ocorrencia_distracao(sessao_id,data_hora,duracao_ausencia) VALUES (?,?,?)",
                (o.sessao_id, o.data_hora, o.duracao_ausencia))
            self.con.commit()
            o.id = cur.lastrowid
        return o

    def atualizar_duracao_ocorrencia(self, oid: int, segundos: int):
        with self._lock:
            self.con.execute("UPDATE ocorrencia_distracao SET duracao_ausencia=? WHERE id=?", (int(segundos), oid))
            self.con.commit()

    def listar_ocorrencias(self, sessao_id: int) -> List[OcorrenciaDistracao]:
        with self._lock:
            rs = self.con.execute("SELECT * FROM ocorrencia_distracao WHERE sessao_id=? ORDER BY id",
                                  (sessao_id,)).fetchall()
        return [OcorrenciaDistracao(r["sessao_id"], r["data_hora"], r["duracao_ausencia"], r["id"]) for r in rs]

    # ---------- resumos / historico ----------
    def salvar_resumo(self, r: ResumoSessao):
        with self._lock:
            self.con.execute(
                "INSERT OR REPLACE INTO resumo_sessao(sessao_id,tempo_total_seg,tempo_efetivo_foco_seg,"
                "numero_bloqueios,numero_ausencias) VALUES (?,?,?,?,?)",
                (r.sessao_id, r.tempo_total_seg, r.tempo_efetivo_foco_seg, r.numero_bloqueios, r.numero_ausencias))
            self.con.commit()

    def listar_historico(self, de: Optional[str] = None, ate: Optional[str] = None):
        """Lista (SessaoFoco, ResumoSessao) das sessoes finalizadas/interrompidas (RF14, A1 do UC10)."""
        sql = ("SELECT s.*, r.id AS rid, r.tempo_total_seg, r.tempo_efetivo_foco_seg, r.numero_bloqueios, "
               "r.numero_ausencias FROM sessao s JOIN resumo_sessao r ON r.sessao_id = s.id WHERE 1=1")
        args = []
        if de:
            sql += " AND s.data >= ?"; args.append(de)
        if ate:
            sql += " AND s.data <= ?"; args.append(ate)
        sql += " ORDER BY s.data DESC, s.horario_inicio DESC"
        with self._lock:
            rs = self.con.execute(sql, args).fetchall()
        return [(self._sessao(r), ResumoSessao(r["id"], r["tempo_total_seg"], r["tempo_efetivo_foco_seg"],
                                               r["numero_bloqueios"], r["numero_ausencias"], r["rid"])) for r in rs]
