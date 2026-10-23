@echo off
REM Avvio applicazione Streamlit per la gestione dei piani comunali

REM Porta la shell nella cartella dove si trova questo file (.bat) e app.py
cd /d %~dp0

REM Parametri di connessione al database (modifica se necessario)
set DB_HOST=10.138.154.6
set DB_NAME=PESER
set DB_USER=peser_rw
set DB_PASS=peserrw
set DB_PORT=10101

REM Avvio dell'app Streamlit in locale usando l'interprete Python
py -m streamlit run app.py

REM Mantieni aperta la finestra per vedere eventuali messaggi/errore
pause
