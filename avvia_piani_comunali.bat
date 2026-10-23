@echo off
REM Avvio applicazione Streamlit per la gestione dei piani comunali

REM Porta la shell nella cartella dove si trova questo file (.bat) e app.py
cd /d %~dp0

REM Parametri di connessione al database (modifica se necessario)
set DB_HOST=10.138.154.6
set DB_NAME=PESER
set DB_USER=peser
set DB_PASS=peser2013
set DB_PORT=10101

REM Avvio dell'app Streamlit in locale (nessun accesso a Internet)
streamlit run app.py
