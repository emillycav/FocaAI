# FocaAI – Sistema Anti-Procrastinação (RAD Python)

Criadores:  Bernardo Souza de Oliveira Moura e Emilly Cavalcante Silva

Aplicação desktop em Python/Tkinter que ajuda o usuário a manter o foco: cadastra sessões de estudo/trabalho,
**fecha automaticamente aplicativos bloqueados** (jogos, redes sociais...) durante a sessão e usa a **webcam**
para detectar ausência/desatenção, com contagem de tolerância e aviso sonoro/visual.

## Como executar (Windows 10/11, Python 3.10+)
```
pip install -r requirements.txt
python main.py
```

## Demonstração rápida
1. Aba **Configurações** → marque *Modo demonstração* (tolerância conta em segundos) e salve (ex.: tolerância 5 = 5 s).
2. Aba **Aplicativos bloqueados** → adicione, por exemplo, `notepad.exe` (ou use "Escolher dos processos abertos").
3. Aba **Painel** → *Iniciar agora* (sessão rápida). Abra o Bloco de Notas: ele é fechado em até 2 s.
4. Saia da frente da câmera: após a tolerância, aparecem o aviso visual e o sonoro. Volte: o aviso é encerrado.
5. *Encerrar sessão* → resumo (tempo total, tempo focado, bloqueios, ausências) e registro na aba **Histórico**.


## Avisos
- A atenção é estimada pela detecção de rosto frontal (OpenCV/Haar): rosto virado ou ausente = desatento.
- Sessões não atravessam a meia-noite (horário de fim deve ser posterior ao de início, no mesmo dia).
- Alterações em Configurações valem a partir da próxima sessão.
