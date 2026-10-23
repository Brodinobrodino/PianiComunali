import os

import psycopg2
import pandas as pd
import streamlit as st

# -----------------------------------------------------------
# CONFIGURAZIONE APPLICAZIONE
# -----------------------------------------------------------
st.set_page_config(page_title="Gestione Piani Comunali", layout="wide")
st.title("Gestione Piani Comunali - Database PostgreSQL 🔒")

# -----------------------------------------------------------
# PARAMETRI DI CONNESSIONE AL DATABASE
# 👉 Sostituisci i valori seguenti con quelli REALI del tuo DB
#    (meglio ancora: sposta questi dati fuori dal codice, es. variabili
#    d'ambiente o st.secrets, vedi commenti in fondo al file)
# -----------------------------------------------------------
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_NAME = os.getenv("DB_NAME", "PESER")
DB_USER = os.getenv("DB_USER", "peser")
DB_PASS = os.getenv("DB_PASS", "password")  # Cambia subito questo valore
DB_PORT = int(os.getenv("DB_PORT", "5432"))


# -----------------------------------------------------------
# FUNZIONI DI SERVIZIO PER IL DATABASE
# -----------------------------------------------------------
def get_connection():
    """Restituisce una connessione psycopg2 al database."""

    return psycopg2.connect(
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
        port=DB_PORT,
    )


def load_table(table_name: str, limit: int = 1000) -> pd.DataFrame:
    """Carica i primi N record da una tabella."""

    conn = None
    try:
        conn = get_connection()
        query = f'SELECT * FROM "{table_name}" LIMIT %s'
        df = pd.read_sql_query(query, conn, params=(limit,))
        return df
    finally:
        if conn is not None:
            conn.close()


def get_decodifica_options(table_name: str, id_column: str, desc_column: str) -> pd.DataFrame:
    """Carica una tabella di decodifica restituiendo solo id + descrizione.

    ⚠️ ATTENZIONE: id_column e desc_column devono corrispondere ai nomi REALI
    delle colonne nel tuo database. Se diversi, modificali qui sotto.
    """

    conn = None
    try:
        conn = get_connection()
        query = f'SELECT "{id_column}", "{desc_column}" FROM "{table_name}" ORDER BY "{desc_column}"'
        df = pd.read_sql_query(query, conn)
        return df
    finally:
        if conn is not None:
            conn.close()


def insert_piano_comunale(
    descrizione_piano: str,
    id_stato_piano: int,
    id_tipo_piano: int,
    id_tipo_delibera: int,
    id_comune: int,
    note: str | None = None,
) -> int:
    """Inserisce un piano comunale e la relazione con il comune.

    ⚠️ Adatta nomi tabella/colonne ai tuoi schemi REALI.

    Assunzioni usate qui (da verificare sul tuo DB):
    - Tabella principale: "Ps_t_anagrafica_pc"
        * id_piano           SERIAL PK
        * descrizione_piano  TEXT
        * id_stato_piano     INT FK -> Ps_d_stato_piano
        * id_tipo_piano      INT FK -> Ps_d_tipo_piano
        * id_tipo_delibera   INT FK -> Ps_d_tipo_delibera
        * note               TEXT (opzionale)
    - Tabella relazione piano-comune: "Ps_r_piano_comune"
        * id_piano   INT FK -> Ps_t_anagrafica_pc
        * id_comune  INT FK -> Ps_geo_comune
    """

    conn = None
    cursor = None

    try:
        conn = get_connection()
        cursor = conn.cursor()

        insert_piano_query = (
            'INSERT INTO "Ps_t_anagrafica_pc" '
            '(descrizione_piano, id_stato_piano, id_tipo_piano, id_tipo_delibera, note) '
            'VALUES (%s, %s, %s, %s, %s) RETURNING id_piano;'
        )

        cursor.execute(
            insert_piano_query,
            (
                descrizione_piano,
                id_stato_piano,
                id_tipo_piano,
                id_tipo_delibera,
                note,
            ),
        )

        id_piano = cursor.fetchone()[0]

        insert_rel_query = (
            'INSERT INTO "Ps_r_piano_comune" (id_piano, id_comune) '
            "VALUES (%s, %s);"
        )
        cursor.execute(insert_rel_query, (id_piano, id_comune))

        conn.commit()
        return id_piano
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()


def get_comuni() -> pd.DataFrame:
    """Ritorna elenco dei comuni.

    Assunzioni (adatta ai tuoi schemi):
    - Tabella: "Ps_geo_comune"
    - Colonne usate: id_comune (PK), nome_comune (descrizione)
    """

    conn = None
    try:
        conn = get_connection()
        query = 'SELECT id_comune, nome_comune FROM "Ps_geo_comune" ORDER BY nome_comune'
        df = pd.read_sql_query(query, conn)
        return df
    finally:
        if conn is not None:
            conn.close()


def get_last_piani(limit: int = 50) -> pd.DataFrame:
    """Restituisce gli ultimi piani inseriti (per consultazione veloce)."""

    conn = None
    try:
        conn = get_connection()
        query = (
            'SELECT p.id_piano, p.descrizione_piano, p.id_stato_piano, '
            'p.id_tipo_piano, p.id_tipo_delibera, p.note '
            'FROM "Ps_t_anagrafica_pc" p '
            'ORDER BY p.id_piano DESC LIMIT %s'
        )
        df = pd.read_sql_query(query, conn, params=(limit,))
        return df
    finally:
        if conn is not None:
            conn.close()


def get_table_columns(table_name: str) -> list[str]:
    """Restituisce elenco dei nomi di colonna di una tabella."""

    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(f'SELECT * FROM "{table_name}" LIMIT 0')
        return [desc[0] for desc in cursor.description]
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()


# -----------------------------------------------------------
# UI PRINCIPALE - TAB
# -----------------------------------------------------------
TAB_LABELS = {
    "Ps_t_anagrafica_pc": "Anagrafica piani comunali",
    "Ps_d_stato_piano": "Decodifica stato piano",
    "Ps_d_tipo_piano": "Decodifica tipo piano",
    "Ps_d_tipo_delibera": "Decodifica tipo delibera",
    "Ps_geo_comune": "Elenco comuni",
    "Ps_r_piano_comune": "Relazione piano-comune",
    "Ps_r_tm_tp": "Relazione tipi (tm-tp)",
}


tab_visualizza, tab_piani, tab_generico = st.tabs(
    [
        "📋 Visualizza tabelle",
        "📑 Gestione piani comunali",
        "🧩 Inserimento generico (qualunque tabella)",
    ]
)


# -----------------------------------------------------------
# TAB 1 - VISUALIZZA TABELLE
# -----------------------------------------------------------
with tab_visualizza:
    st.header("📋 Visualizza tabelle principali")

    table_choice = st.selectbox(
        "Seleziona la tabella da consultare:",
        options=list(TAB_LABELS.keys()),
        format_func=lambda key: TAB_LABELS.get(key, key),
    )

    limit_rows = st.number_input("Numero massimo di righe da caricare", 1, 10000, 1000)

    if st.button("Carica dati", key="btn_carica_tabella"):
        try:
            df = load_table(table_choice, limit=int(limit_rows))
            st.success(f"Caricate {len(df)} righe dalla tabella {table_choice}.")
            st.dataframe(df, use_container_width=True)
        except Exception as e:
            st.error(f"Errore durante il caricamento della tabella {table_choice}: {e}")


# -----------------------------------------------------------
# TAB 2 - GESTIONE PIANI COMUNALI
# -----------------------------------------------------------
with tab_piani:
    st.header("📑 Inserisci un nuovo piano comunale")

    col_form, col_lista = st.columns((2, 3))

    with col_form:
        st.subheader("Nuovo piano")

        try:
            df_comuni = get_comuni()
        except Exception as e:
            st.error(f"Errore nel caricamento dei comuni: {e}")
            df_comuni = pd.DataFrame(columns=["id_comune", "nome_comune"])

        try:
            df_stato = get_decodifica_options(
                "Ps_d_stato_piano", "id_stato_piano", "descr_stato_piano"
            )
        except Exception as e:
            st.error(f"Errore nel caricamento degli stati piano: {e}")
            df_stato = pd.DataFrame(columns=["id_stato_piano", "descr_stato_piano"])

        try:
            df_tipo_piano = get_decodifica_options(
                "Ps_d_tipo_piano", "id_tipo_piano", "descr_tipo_piano"
            )
        except Exception as e:
            st.error(f"Errore nel caricamento dei tipi piano: {e}")
            df_tipo_piano = pd.DataFrame(columns=["id_tipo_piano", "descr_tipo_piano"])

        try:
            df_tipo_delibera = get_decodifica_options(
                "Ps_d_tipo_delibera", "id_tipo_delibera", "descr_tipo_delibera"
            )
        except Exception as e:
            st.error(f"Errore nel caricamento dei tipi delibera: {e}")
            df_tipo_delibera = pd.DataFrame(
                columns=["id_tipo_delibera", "descr_tipo_delibera"]
            )

        with st.form("form_nuovo_piano", clear_on_submit=False):
            # Comune
            if not df_comuni.empty:
                comune_obj = st.selectbox(
                    "Comune",
                    options=list(df_comuni.itertuples(index=False)),
                    format_func=lambda row: f"{row.id_comune} - {row.nome_comune}",
                )
                selected_id_comune = int(comune_obj.id_comune)
            else:
                st.warning("Nessun comune trovato nella tabella Ps_geo_comune.")
                selected_id_comune = None

            # Stato piano
            if not df_stato.empty:
                stato_obj = st.selectbox(
                    "Stato piano",
                    options=list(df_stato.itertuples(index=False)),
                    format_func=lambda row: f"{row.id_stato_piano} - {row.descr_stato_piano}",
                )
                selected_id_stato = int(stato_obj.id_stato_piano)
            else:
                st.warning("Tabella Ps_d_stato_piano vuota o non leggibile.")
                selected_id_stato = None

            # Tipo piano
            if not df_tipo_piano.empty:
                tp_obj = st.selectbox(
                    "Tipo piano",
                    options=list(df_tipo_piano.itertuples(index=False)),
                    format_func=lambda row: f"{row.id_tipo_piano} - {row.descr_tipo_piano}",
                )
                selected_id_tipo_piano = int(tp_obj.id_tipo_piano)
            else:
                st.warning("Tabella Ps_d_tipo_piano vuota o non leggibile.")
                selected_id_tipo_piano = None

            # Tipo delibera
            if not df_tipo_delibera.empty:
                td_obj = st.selectbox(
                    "Tipo delibera",
                    options=list(df_tipo_delibera.itertuples(index=False)),
                    format_func=lambda row: f"{row.id_tipo_delibera} - {row.descr_tipo_delibera}",
                )
                selected_id_tipo_delibera = int(td_obj.id_tipo_delibera)
            else:
                st.warning("Tabella Ps_d_tipo_delibera vuota o non leggibile.")
                selected_id_tipo_delibera = None

            descrizione_piano = st.text_area(
                "Descrizione del piano", placeholder="Es. Piano comunale di emergenza ..."
            )
            note = st.text_area("Note (opzionale)")

            submit_piano = st.form_submit_button("Salva piano nel database")

            if submit_piano:
                if (
                    selected_id_comune is None
                    or selected_id_stato is None
                    or selected_id_tipo_piano is None
                    or selected_id_tipo_delibera is None
                ):
                    st.error(
                        "Verifica che le tabelle di decodifica e dei comuni contengano dati "
                        "e che le colonne usate nel codice corrispondano a quelle del DB."
                    )
                elif not descrizione_piano.strip():
                    st.error("La descrizione del piano è obbligatoria.")
                else:
                    try:
                        new_id = insert_piano_comunale(
                            descrizione_piano=descrizione_piano.strip(),
                            id_stato_piano=selected_id_stato,
                            id_tipo_piano=selected_id_tipo_piano,
                            id_tipo_delibera=selected_id_tipo_delibera,
                            id_comune=selected_id_comune,
                            note=note.strip() or None,
                        )
                        st.success(
                            f"Piano inserito correttamente con id_piano = {new_id}."
                        )
                    except Exception as e:
                        st.error(f"Errore durante l'inserimento del piano: {e}")

    with col_lista:
        st.subheader("Ultimi piani inseriti")

        try:
            df_last = get_last_piani(limit=100)
            if df_last.empty:
                st.info("Nessun piano presente in Ps_t_anagrafica_pc.")
            else:
                st.dataframe(df_last, use_container_width=True)
        except Exception as e:
            st.error(f"Errore durante il caricamento dei piani: {e}")


# -----------------------------------------------------------
# TAB 3 - INSERIMENTO GENERICO SU QUALSIASI TABELLA
# -----------------------------------------------------------
with tab_generico:
    st.header("🧩 Inserimento generico su qualunque tabella")

    st.write(
        "Questa sezione permette di inserire un record in una tabella a scelta, "
        "senza dover scrivere SQL a mano. Tutti i valori vengono inviati come testo "
        "(il database proverà a convertirli nel tipo corretto)."
    )

    table_choice_generic = st.selectbox(
        "Tabella di destinazione:",
        options=list(TAB_LABELS.keys()),
        format_func=lambda key: TAB_LABELS.get(key, key),
        key="tabella_generica",
    )

    if table_choice_generic:
        try:
            columns = get_table_columns(table_choice_generic)
        except Exception as e:
            st.error(f"Impossibile leggere le colonne della tabella {table_choice_generic}: {e}")
            columns = []

        if columns:
            st.markdown("**Valori da inserire (lascia vuoto per usare il default del DB, se esiste)**")

            with st.form("form_inserimento_generico", clear_on_submit=True):
                values: dict[str, str] = {}
                for col in columns:
                    values[col] = st.text_input(col, key=f"{table_choice_generic}_{col}")

                submit_generic = st.form_submit_button("Inserisci record")

                if submit_generic:
                    # Consideriamo solo le colonne valorizzate
                    cols_to_use = [c for c, v in values.items() if v != ""]
                    params = [values[c] for c in cols_to_use]

                    if not cols_to_use:
                        st.warning(
                            "Nessun valore inserito. Compila almeno un campo oppure usa una "
                            "maschera dedicata (es. quella per i piani comunali)."
                        )
                    else:
                        try:
                            cols_sql = ", ".join(f'"{c}"' for c in cols_to_use)
                            placeholders = ", ".join(["%s"] * len(cols_to_use))
                            query = (
                                f'INSERT INTO "{table_choice_generic}" ({cols_sql}) '
                                f"VALUES ({placeholders})"
                            )

                            conn = None
                            cursor = None
                            try:
                                conn = get_connection()
                                cursor = conn.cursor()
                                cursor.execute(query, params)
                                conn.commit()
                                st.success(
                                    f"Record inserito correttamente nella tabella {table_choice_generic}."
                                )
                            finally:
                                if cursor is not None:
                                    cursor.close()
                                if conn is not None:
                                    conn.close()
                        except Exception as e:
                            st.error(f"Errore durante l'inserimento generico: {e}")
        else:
            st.info(
                "Seleziona una tabella valida per vedere l'elenco delle colonne "
                "e poter inserire un nuovo record."
            )


# -----------------------------------------------------------
# NOTE SU SICUREZZA E UTILIZZO LOCALE
# -----------------------------------------------------------
# 1) PARAMETRI DI CONNESSIONE SENZA METTERE PASSWORD NEL CODICE
#    Puoi valorizzare le variabili d'ambiente prima di avviare Streamlit, ad esempio
#    su Windows (cmd.exe):
#       set DB_HOST=10.138.154.6
#       set DB_NAME=PESER
#       set DB_USER=peser
#       set DB_PASS=la_tua_password
#       set DB_PORT=10101
#       streamlit run app.py
#
#    In alternativa, con Streamlit puoi usare il file .streamlit/secrets.toml
#    (nella stessa cartella del progetto) con dentro:
#       [postgres]
#       host = "10.138.154.6"
#       dbname = "PESER"
#       user = "peser"
#       password = "la_tua_password"
#       port = 10101
#
#    e modificare la funzione get_connection per leggere da st.secrets["postgres"].
#
# 2) ESEGUIBILE LOCALE (NESSUN ACCESSO INTERNET)
#    L'app Streamlit gira già in locale (es. http://localhost:8501) e non
#    contatta Internet se non lo fai tu esplicitamente nel codice.
#    Se vuoi un "eseguibile" per la collega, il modo più semplice è creare
#    un file .bat (Windows) accanto a app.py, contenente ad esempio:
#        @echo off
#        cd /d %~dp0
#        set DB_HOST=10.138.154.6
#        set DB_NAME=PESER
#        set DB_USER=peser
#        set DB_PASS=la_tua_password
#        set DB_PORT=10101
#        streamlit run app.py
#
#    In questo modo la collega deve solo fare doppio clic sul .bat.
#
#    Se preferisci un .exe vero e proprio, puoi valutare PyInstaller, ma per
#    applicazioni Streamlit nella pratica il .bat è spesso sufficiente e molto
#    più semplice da gestire.
