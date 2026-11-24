"""UC06/UC07 - Monitorar presenca do usuario pela webcam (RF07-RF10, RNF01, RNF03).

RN05/RNF01: os quadros sao analisados SOMENTE em memoria e descartados; nada e gravado ou enviado.
"""
import threading
import time
from collections import deque
from typing import Callable, Optional

from database.db import Banco, agora_str
from models.modelos import Configuracao, OcorrenciaDistracao

FOCADO, CONTANDO, AUSENTE = "focado", "contando", "ausente"


class DetectorOpenCV:
    """Detecta um rosto FRONTAL no quadro: rosto virado/ausente => desatento ou ausente."""

    def __init__(self, indice_camera: int = 0):
        import cv2
        self.cv2 = cv2
        self.cap = None
        self.indice = indice_camera
        self.cascata = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        if self.cascata.empty():
            raise RuntimeError("classificador de rosto do OpenCV não encontrado "
                               "(reinstale com: pip install \"opencv-python>=4.8,<5\")")

    def abrir(self) -> bool:
        cv2 = self.cv2
        try:
            self.cap = cv2.VideoCapture(self.indice, cv2.CAP_DSHOW) if hasattr(cv2, "CAP_DSHOW") \
                else cv2.VideoCapture(self.indice)
        except Exception:
            self.cap = cv2.VideoCapture(self.indice)
        return bool(self.cap is not None and self.cap.isOpened())

    def analisar(self) -> Optional[bool]:
        """True = rosto presente/atento, False = ausente/desatento, None = camera indisponivel."""
        if self.cap is None or not self.cap.isOpened():
            return None
        ok, quadro = self.cap.read()
        if not ok or quadro is None:
            return None
        cinza = self.cv2.cvtColor(quadro, self.cv2.COLOR_BGR2GRAY)
        rostos = self.cascata.detectMultiScale(cinza, scaleFactor=1.2, minNeighbors=5, minSize=(60, 60))
        del quadro, cinza                      # RN05: quadro descartado, nunca gravado
        return len(rostos) > 0

    def liberar(self):
        if self.cap is not None:
            self.cap.release()
            self.cap = None


class MonitorWebcam:
    def __init__(self, banco: Banco, sessao_id: int, config: Configuracao,
                 ao_evento: Optional[Callable[[str, dict], None]] = None,
                 detector=None, intervalo: float = 1.0, janela_suavizacao: int = 3):
        self.banco = banco
        self.sessao_id = sessao_id
        self.config = config
        self.ao_evento = ao_evento or (lambda tipo, dados: None)
        self.detector = detector
        self.intervalo = intervalo
        self.ativo = False
        self.estado = FOCADO
        self.contagem_regressiva = 0           # segundos restantes da tolerancia
        self.tempo_ausente_seg = 0.0           # soma das ausencias que geraram aviso
        self.numero_ausencias = 0
        self.camera_ok = True
        self._ausente_desde: Optional[float] = None
        self._inicio_ausencia_txt = ""
        self._ocorrencia: Optional[OcorrenciaDistracao] = None
        self._recentes = deque(maxlen=max(1, janela_suavizacao))
        self._parar = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # -- ciclo de vida --
    def iniciar(self) -> bool:
        """Abre a camera. Retorna False se indisponivel (E1/A1: sessao segue so com bloqueio de apps)."""
        if self.detector is None:
            try:
                self.detector = DetectorOpenCV()
            except Exception as e:
                self.camera_ok = False
                self.ao_evento("camera_indisponivel", {"texto": f"Monitoramento de presença indisponível: {e}"})
                return False
        if hasattr(self.detector, "abrir") and not self.detector.abrir():
            self.camera_ok = False
            self.ao_evento("camera_indisponivel", {"texto": "Câmera indisponível ou sem permissão. "
                                                            "A sessão seguirá apenas com o bloqueio de aplicativos."})
            return False
        self.ativo = True
        self._parar.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="MonitorWebcam")
        self._thread.start()
        return True

    def parar(self, agora: Optional[float] = None):
        self.ativo = False
        self._parar.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)
        if self._ocorrencia is not None:       # sessao acabou com o usuario ausente
            self._fechar_ocorrencia(time.monotonic() if agora is None else agora)
        if hasattr(self.detector, "liberar"):
            self.detector.liberar()

    def _loop(self):
        while not self._parar.wait(self.intervalo):
            try:
                self.processar_frame_memoria()
            except Exception as e:
                self.ao_evento("info", {"texto": f"Erro no monitor de webcam: {e}"})

    # -- logica (cada metodo corresponde a uma operacao do Diagrama de Classes) --
    def processar_frame_memoria(self, agora: Optional[float] = None):
        agora = time.monotonic() if agora is None else agora
        resultado = self.detector.analisar()
        if resultado is None:                  # camera caiu no meio da sessao (E1 do UC06)
            if self.camera_ok:
                self.camera_ok = False
                self.ao_evento("camera_indisponivel", {"texto": "Câmera desconectada. Continuando só com o "
                                                                "bloqueio de aplicativos."})
            self._parar.set()
            return
        self.verificar_atencao_presenca(resultado, agora)

    def verificar_atencao_presenca(self, presente: bool, agora: Optional[float] = None) -> str:
        agora = time.monotonic() if agora is None else agora
        self._recentes.append(bool(presente))
        presente_suave = any(self._recentes)   # evita falso "ausente" por 1 quadro ruim
        tolerancia = self.config.tolerancia_segundos()

        if presente_suave:
            if self._ausente_desde is not None:
                if self._ocorrencia is not None:           # aviso ja tinha sido emitido
                    self._fechar_ocorrencia(agora)
                    self.ao_evento("aviso_fim", {"texto": "Você voltou ao foco."})
                else:
                    self.cancelar_contagem()               # RF09
            self.estado = FOCADO
            self.contagem_regressiva = 0
        else:
            if self._ausente_desde is None:
                self.iniciar_contagem_tolerancia(agora)    # RF08
            restante = tolerancia - (agora - self._ausente_desde)
            if self._ocorrencia is None:
                self.contagem_regressiva = max(0, int(round(restante)))
                if restante <= 0:                          # RN04: so avisa depois da tolerancia
                    self.emitir_aviso()
                    self.registrar_distracao(agora)
                    self.estado = AUSENTE
        return self.estado

    def iniciar_contagem_tolerancia(self, agora: float):
        self._ausente_desde = agora
        self._inicio_ausencia_txt = agora_str()
        self.estado = CONTANDO
        self.contagem_regressiva = self.config.tolerancia_segundos()
        self.ao_evento("contagem_iniciada", {"texto": "Ausência detectada: contagem de tolerância iniciada."})

    def cancelar_contagem(self):
        self._ausente_desde = None
        self.estado = FOCADO
        self.contagem_regressiva = 0
        self.ao_evento("contagem_cancelada", {"texto": "Você voltou antes do fim da tolerância."})

    def emitir_aviso(self):
        self.ao_evento("aviso", {"sonoro": self.config.aviso_sonoro, "visual": self.config.aviso_visual,
                                 "texto": "Você saiu do foco! Volte para a tela."})

    def registrar_distracao(self, agora: float) -> OcorrenciaDistracao:
        # a ocorrencia registra a hora em que a ausencia COMECOU (UC07, passo 2)
        self._ocorrencia = self.banco.criar_ocorrencia(
            OcorrenciaDistracao(self.sessao_id, self._inicio_ausencia_txt, 0))
        self.numero_ausencias += 1
        return self._ocorrencia

    def _fechar_ocorrencia(self, agora: float):
        inicio = agora if self._ausente_desde is None else self._ausente_desde
        duracao = max(0, int(agora - inicio))
        self.banco.atualizar_duracao_ocorrencia(self._ocorrencia.id, duracao)
        self.tempo_ausente_seg += duracao
        self._ocorrencia = None
        self._ausente_desde = None

    def dispensar_aviso(self):
        """A1 do UC07: usuario dispensa o aviso; a ocorrencia continua registrada."""
        self.ao_evento("aviso_fim", {"texto": "Aviso dispensado."})
