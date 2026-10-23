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
# NOMI TABELLE (minuscolo per corrispondere al DB PostgreSQL)
# -----------------------------------------------------------
TABLE_PS_T_ANAGRAFICA_PC = "ps_t_anagrafica_pc"
TABLE_PS_D_STATO_PIANO = "ps_d_stato_piano"
TABLE_PS_D_TIPO_PIANO = "ps_d_tipo_piano"
TABLE_PS_D_TIPO_DELIBERA = "ps_d_tipo_delibera"
TABLE_PS_GEO_COMUNE = "ps_geo_comune"
TABLE_PS_R_PIANO_COMUNE = "ps_r_piano_comune"
TABLE_PS_R_TM_TP = "ps_r_tm_tp"


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
        # Il nome tabella viene passato in minuscolo e non viene quotato,
        # così PostgreSQL lo interpreta come identificatore non sensibile al case.
        query = f"SELECT * FROM {table_name} LIMIT %s"
        df = pd.read_sql_query(query, conn, params=(limit,))
        return df
    finally:
        if conn is not None:
            conn.close()


def get_decodifica_options(table_name: str, id_column: str, desc_column: str) -> pd.DataFrame:
    """Carica una tabella di decodifica restituiendo solo id + descrizione.

    I parametri id_column e desc_column vengono usati come "suggerimenti".
    Se i nomi non corrispondono alle colonne reali, la funzione prova a
    individuarle automaticamente sulla base dei nomi presenti nel DB e
    restituisce comunque un DataFrame con colonne chiamate esattamente
    come id_column e desc_column.
    """

    # Ricaviamo le colonne effettive della tabella
    try:
        columns = get_table_columns(table_name)
    except Exception as e:
        raise RuntimeError(
            f"Impossibile leggere le colonne della tabella {table_name}: {e}"
        ) from e

    if not columns:
        raise RuntimeError(
            f"La tabella {table_name} non contiene colonne oppure non esiste."
        )

    # Determiniamo la colonna ID effettiva
    id_col = None
    if id_column in columns:
        id_col = id_column
    else:
        # match case-insensitive
        for c in columns:
            if c.lower() == id_column.lower():
                id_col = c
                break
    if id_col is None:
        for c in columns:
            if c.lower().startswith("id_"):
                id_col = c
                break
    if id_col is None:
        id_col = columns[0]

    # Determiniamo la colonna descrittiva effettiva
    desc_col = None
    if desc_column in columns:
        desc_col = desc_column
    else:
        for c in columns:
            if c.lower() == desc_column.lower():
                desc_col = c
                break
    if desc_col is None:
        for c in columns:
            if any(key in c.lower() for key in ("descr", "desc", "nome", "denom")):
                desc_col = c
                break
    if desc_col is None:
        desc_col = columns[1] if len(columns) > 1 else id_col

    conn = None
    try:
        conn = get_connection()
        # Tabella non quotata (minuscolo) e colonne quotate per preservare il nome esatto.
        # Alias delle colonne verso i nomi logici attesi dal resto dell'app
        query = (
            f'SELECT "{id_col}" AS "{id_column}", "{desc_col}" AS "{desc_column}" '
            f"FROM {table_name} ORDER BY \"{desc_col}\""
        )
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
    path_file: str | None = None,
    note: str | None = None,
) -> int:
    """Inserisce un piano comunale e la relazione con il comune.

    Mappa esplicitamente sullo schema reale del database:

    - Tabella principale: ps_t_anagrafica_pc (TABLE_PS_T_ANAGRAFICA_PC)
        * id_modulo       SERIAL PK (usato come id_piano nell'app)
        * fk_tipo_piano   INT FK -> ps_d_tipo_piano.id_tipo_piano
        * fk_stato_piano  INT FK -> ps_d_stato_piano.id_stato_piano
        * fk_delibera     INT FK -> ps_d_tipo_delibera.id_delibera
        * path_file       TEXT/VARCHAR (percorso o URL del documento)
        * note            TEXT
        * ente            TEXT (usato come descrizione sintetica del piano)

    - Tabella relazione piano-comune: ps_r_piano_comune (TABLE_PS_R_PIANO_COMUNE)
        * fk_modulo  INT FK -> ps_t_anagrafica_pc.id_modulo
        * fk_comune  INT FK -> ps_geo_comune.id_comune
    """

    conn = None
    cursor = None

    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Inserimento nella tabella principale dei piani
        insert_piano_query = (
            f"INSERT INTO {TABLE_PS_T_ANAGRAFICA_PC} "
            "(fk_tipo_piano, fk_stato_piano, fk_delibera, path_file, note, ente) "
            "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id_modulo;"
        )

        cursor.execute(
            insert_piano_query,
            (
                id_tipo_piano,
                id_stato_piano,
                id_tipo_delibera,
                path_file,
                note,
                descrizione_piano,
            ),
        )

        id_piano = cursor.fetchone()[0]

        # Inserimento della relazione piano-comune
        insert_rel_query = (
            f"INSERT INTO {TABLE_PS_R_PIANO_COMUNE} (fk_modulo, fk_comune) "
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
    """Ritorna l'elenco dei comuni usando lo schema reale ps_geo_comune.

    Colonne restituite (normalizzate per l'app):
    - id_comune  (ps_geo_comune.id_comune)
    - nome_comune (alias di ps_geo_comune.comune)
    """

    conn = None
    try:
        conn = get_connection()
        query = (
            f"SELECT id_comune, comune AS nome_comune "
            f"FROM {TABLE_PS_GEO_COMUNE} "
            f"ORDER BY comune"
        )
        df = pd.read_sql_query(query, conn)
        return df
    finally:
        if conn is not None:
            conn.close()


def get_last_piani(limit: int = 50) -> pd.DataFrame:
    """Restituisce gli ultimi piani inseriti (per consultazione veloce).

    Usa lo schema reale ps_t_anagrafica_pc e aliassa le colonne verso i nomi
    logici usati dal resto dell'app:

    - id_modulo       -> id_piano
    - ente            -> descrizione_piano
    - fk_stato_piano  -> id_stato_piano
    - fk_tipo_piano   -> id_tipo_piano
    - fk_delibera     -> id_tipo_delibera
    - path_file       (per il link al documento)
    - note
    """

    conn = None
    try:
        conn = get_connection()
        query = (
            "SELECT "
            "  id_modulo AS id_piano, "
            "  ente AS descrizione_piano, "
            "  fk_stato_piano AS id_stato_piano, "
            "  fk_tipo_piano AS id_tipo_piano, "
            "  fk_delibera AS id_tipo_delibera, "
            "  path_file, "
            "  note, "
            "  dt_delibera, "
            "  num_delibera, "
            "  anno_approvazione, "
            "  flg_vigente, "
            "  dt_aggiornamento "
            f"FROM {TABLE_PS_T_ANAGRAFICA_PC} "
            "ORDER BY id_modulo DESC "
            "LIMIT %s"
        )
        df = pd.read_sql_query(query, conn, params=(limit,))
        return df
    finally:
        if conn is not None:
            conn.close()


def get_relazioni_piano_comune() -> pd.DataFrame:
    """Restituisce la relazione piano-comune (id_piano, id_comune).

    Usa lo schema reale:
    - ps_r_piano_comune.fk_modulo  -> id_piano (id_modulo di ps_t_anagrafica_pc)
    - ps_r_piano_comune.fk_comune  -> id_comune (ps_geo_comune.id_comune)
    """

    conn = None
    try:
        conn = get_connection()
        query = (
            f"SELECT fk_modulo AS id_piano, fk_comune AS id_comune "
            f"FROM {TABLE_PS_R_PIANO_COMUNE}"
        )
        df = pd.read_sql_query(query, conn)
        return df
    finally:
        if conn is not None:
            conn.close()


def get_piani_dettaglio(limit: int = 100) -> pd.DataFrame:
    """Restituisce una vista "ad alto livello" dei piani comunali.

    La vista integra:
    - dati del piano (descrizione, stato, tipo, delibera, note)
    - comune associato (tramite tabella di relazione)

    Usa le tabelle di decodifica e i comuni tramite merge lato Python
    per evitare problemi con nomi di colonne leggermente diversi nel DB.
    """

    df_piani = get_last_piani(limit=limit)
    if df_piani.empty:
        return df_piani

    # Relazione piano-comune
    try:
        df_rel = get_relazioni_piano_comune()
    except Exception:
        # Se la relazione non fosse disponibile, restituiamo solo i piani
        df_rel = pd.DataFrame(columns=["id_piano", "id_comune"])

    # Decodifiche
    try:
        df_comuni = get_comuni()
    except Exception:
        df_comuni = pd.DataFrame(columns=["id_comune", "nome_comune"])

    try:
        df_stato = get_decodifica_options(
            TABLE_PS_D_STATO_PIANO, "id_stato_piano", "descr_stato_piano"
        )
    except Exception:
        df_stato = pd.DataFrame(columns=["id_stato_piano", "descr_stato_piano"])

    try:
        df_tipo_piano = get_decodifica_options(
            TABLE_PS_D_TIPO_PIANO, "id_tipo_piano", "descr_tipo_piano"
        )
    except Exception:
        df_tipo_piano = pd.DataFrame(columns=["id_tipo_piano", "descr_tipo_piano"])

    try:
        df_tipo_delibera = get_decodifica_options(
            TABLE_PS_D_TIPO_DELIBERA, "id_tipo_delibera", "descr_tipo_delibera"
        )
    except Exception:
        df_tipo_delibera = pd.DataFrame(
            columns=["id_tipo_delibera", "descr_tipo_delibera"]
        )

    # Merge progressivi per comporre la vista integrata
    df = df_piani.merge(df_rel, on="id_piano", how="left")

    if not df_comuni.empty:
        df = df.merge(df_comuni, on="id_comune", how="left")

    if not df_stato.empty:
        df = df.merge(df_stato, on="id_stato_piano", how="left")

    if not df_tipo_piano.empty:
        df = df.merge(df_tipo_piano, on="id_tipo_piano", how="left")

    if not df_tipo_delibera.empty:
        df = df.merge(df_tipo_delibera, on="id_tipo_delibera", how="left")

    # Rinominiamo le colonne per una vista più leggibile
    df = df.rename(
        columns={
            "descrizione_piano": "Piano",
            "nome_comune": "Comune",
            "descr_stato_piano": "Stato piano",
            "descr_tipo_piano": "Tipo piano",
            "descr_tipo_delibera": "Tipo delibera",
            "note": "Note",
        }
    )

    # Se esiste una colonna con "path" nel nome, la esponiamo come "Path"
    path_col = None
    for c in df.columns:
        if "path" in c.lower() or "url" in c.lower():
            path_col = c
            break
    if path_col is not None and path_col != "Path":
        df = df.rename(columns={path_col: "Path"})

    # Normalizziamo i path in formato file:// per evitare che il browser li interpreti
    # come link verso http://localhost. Se il valore non inizia già con file://, http://
    # o https://, viene prefissato con file://. Per percorsi UNC (es. \\ileserver\share)
    # convertiamo in file://server/share.
    # Normalizzazione valori della colonna "Path" per ottenere URL/URI
    # cliccabili dal browser.
    # Regole:
    # - se inizia già con file://, http://, https:// -> lasciato invariato
    # - percorsi UNC (es. \\server\share\cartella\file.pdf) -> file://server/share/cartella/file.pdf
    # - percorsi Windows con unità (es. C:\\cartella\\file.pdf) -> file:///C:/cartella/file.pdf
    # - percorsi assoluti Unix (/...) -> file:///percorso
    # - stringhe tipo "ad.regione.piemonte.it/..." (senza schema) -> file://ad.regione.piemonte.it/...
    if "Path" in df.columns:
        def _normalize_path(value: object) -> object:
            if pd.isna(value):
                return value
            s = str(value).strip()
            if not s:
                return s

            lower = s.lower()
            # Già un URL/URI utilizzabile dal browser oppure un valore che inizia già con "file:"
            if lower.startswith("file:") or lower.startswith(("http://", "https://")):
                return s

            # Percorso UNC di Windows: \\server\share\cartella\file.pdf
            if s.startswith("\\\\"):
                s_clean = s.lstrip("\\")
                s_clean = s_clean.replace("\\", "/")
                return f"file:/{s_clean}"

            # Percorso Windows con unità (es. C:\\cartella\\file.pdf)
            if len(s) >= 3 and s[1] == ":" and s[2] in ("\\", "/"):
                drive = s[0].upper()
                rest = s[2:].lstrip("\\/")
                rest = rest.replace("\\", "/")
                return f"file:/{drive}:/{rest}"

            # Percorso "finto assoluto" usato per share di rete tipo "/ad.regione.piemonte.it/..."
            if s.startswith("/ad.regione.piemonte.it/"):
                # Rimuove lo slash iniziale in modo da ottenere file://ad.regione.piemonte.it/...
                s_clean = s.lstrip("/")
                return f"file:/{s_clean}"

            # Percorso assoluto Unix-like ("/...")
            if s.startswith("/"):
                # Percorso file locale stile Unix -> file:///percorso
                return f"file:/{s}"

            # Altri casi (es. "ad.regione.piemonte.it/..."): aggiunge file:// davanti
            return f"file:/{s}"

        df["Path"] = df["Path"].apply(_normalize_path)

    # Utility per aprire percorsi locali / UNC in Esplora risorse (solo Windows)
    def _file_uri_to_windows_path(value: object) -> str:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return ""
        s = str(value).strip()
        if not s:
            return ""

        lower = s.lower()
        # Rimuoviamo il prefisso file:// se presente
        if lower.startswith("file://"):
            s = s[7:]

        # UNC esplicito: \\server\share\...
        if s.startswith("\\\\") or s.startswith("//"):
            return s.replace("/", "\\")

        # Percorso con unità disco: C:/..., C:\...
        if len(s) >= 2 and s[1] == ":":
            return s.replace("/", "\\")

        # Caso tipo ad.regione.piemonte.it/rp/...
        parts = s.split("/")
        if len(parts) > 1:
            host = parts[0]
            rest = "\\".join(parts[1:])
            return f"\\\\{host}\\{rest}"

        return s

    def open_path_in_explorer(value: object) -> None:
        """Apre il percorso indicato (file o cartella) in Esplora risorse.

        Funziona correttamente quando l'app Streamlit gira su Windows
        sulla stessa macchina dell'utente (es. localhost).
        """

        win_path = _file_uri_to_windows_path(value)
        if not win_path:
            raise ValueError("Percorso vuoto o non valido")

        # Se è un file, apriamo la cartella che lo contiene
        if os.path.isfile(win_path):
            folder = os.path.dirname(win_path)
            os.startfile(folder)  # type: ignore[attr-defined]
        else:
            os.startfile(win_path)  # type: ignore[attr-defined]

    # Ordine colonne principale
    ordered_cols = [
        "id_piano",
        "Piano",
        "Comune",
        "id_comune",
        "Stato piano",
        "Tipo piano",
        "Tipo delibera",
        "Note",
        "Path",
    ]
    existing_cols = [c for c in ordered_cols if c in df.columns]
    # Aggiungiamo eventuali colonne residue in coda
    remaining_cols = [c for c in df.columns if c not in existing_cols]
    df = df[existing_cols + remaining_cols]

    return df


def get_table_columns(table_name: str) -> list[str]:
    """Restituisce elenco dei nomi di colonna di una tabella."""

    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        # Il nome tabella è in minuscolo e non viene quotato per allinearsi agli schemi del DB
        cursor.execute(f"SELECT * FROM {table_name} LIMIT 0")
        return [desc[0] for desc in cursor.description]
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()


# -----------------------------------------------------------
# UTILITY GLOBALI PER APERTURA PERCORSI (Esplora risorse)
# -----------------------------------------------------------


def _file_uri_to_windows_path(value: object) -> str:
    """Converte un URI/URL o stringa di percorso in un path Windows.

    Gestisce:
    - prefisso "file://" o "file:/" (rimossi se presenti)
    - percorsi UNC espliciti (\\server\share\... oppure //server/share/...)
    - percorsi con unita disco locali (C:/..., C:\\...)
    - forme "host\\share\\cartella..." o "host/path/..." convertite in UNC \\host\share\...
    """

    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""

    s = str(value).strip()
    # Rimuove eventuali caratteri di controllo (ritorno carrello, newline) che possono
    # provenire dal DB e generare percorsi tipo "ad.regione.piemonte.it\rp" -> "ad.regione.piemonte.itrp"
    s = s.replace("\r", "").replace("\n", "")
    if not s:
        return ""

    lower = s.lower()

    # Rimuoviamo qualunque prefisso file:*, gestendo sia file:/..., file://..., file:///...
    if lower.startswith("file:"):
        # taglia "file:" e poi toglie eventuali slash o backslash iniziali
        s = s[5:]
        s = s.lstrip("/\\")

    # UNC esplicito: \\server\share\... oppure //server/share/...
    if s.startswith("\\") or s.startswith("//"):
        return s.replace("/", "\\")

    # Percorso con unita disco: C:/..., C:\...
    if len(s) >= 2 and s[1] == ":":
        return s.replace("/", "\\")

    # Forma host\\share\\cartella (es. ad.regione.piemonte.it\rp\A1800A\...)
    if "\\" in s and not s.startswith("\\") and not s.startswith("//"):
        parts = s.split("\\", 1)
        host = parts[0]
        rest = parts[1] if len(parts) > 1 else ""
        if rest:
            return f"\\\\{host}\\{rest}"
        return f"\\\\{host}"

    # Forma host/path/... con slash (es. ad.regione.piemonte.it/rp/A1800A/...)
    parts = s.split("/")
    if len(parts) > 1:
        host = parts[0]
        rest = "\\".join(parts[1:])
        return f"\\\\{host}\\{rest}"

    # Caso residuo: restituiamo la stringa cosi com'e
    return s



def open_path_in_explorer(value: object) -> None:
    """Apre il percorso indicato (file o cartella) in Esplora risorse (solo Windows)."""

    win_path = _file_uri_to_windows_path(value)
    if not win_path:
        raise ValueError("Percorso vuoto o non valido")

    # Se e un file, apriamo la cartella che lo contiene
    if os.path.isfile(win_path):
        folder = os.path.dirname(win_path)
        os.startfile(folder)  # type: ignore[attr-defined]
    else:
        os.startfile(win_path)  # type: ignore[attr-defined]

# -----------------------------------------------------------
# DIAGNOSTICA CONNESSIONE DATABASE (disattivata per lasciare più spazio alle tabelle)
# -----------------------------------------------------------
# In precedenza qui veniva mostrato un riquadro nella sidebar con lo stato
# della connessione al database. È stato rimosso per non occupare spazio
# orizzontale e permettere alle tabelle principali di sfruttare tutta la
# larghezza della pagina.


# -----------------------------------------------------------
# UI PRINCIPALE - TAB
# -----------------------------------------------------------
TAB_LABELS = {
    TABLE_PS_T_ANAGRAFICA_PC: "Anagrafica piani comunali",
    TABLE_PS_D_STATO_PIANO: "Decodifica stato piano",
    TABLE_PS_D_TIPO_PIANO: "Decodifica tipo piano",
    TABLE_PS_D_TIPO_DELIBERA: "Decodifica tipo delibera",
    TABLE_PS_GEO_COMUNE: "Elenco comuni",
    TABLE_PS_R_PIANO_COMUNE: "Relazione piano-comune",
    TABLE_PS_R_TM_TP: "Relazione tipi (tm-tp)",
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
    st.header("📋 Piani comunali - vista integrata")

    limit_rows_piani = st.number_input(
        "Numero massimo di piani da mostrare",
        min_value=1,
        max_value=1000,
        value=100,
        key="limit_piani_integrati",
    )
    filtro_testo = st.text_input(
        "Filtro veloce (per testo presente in Piano o Comune)",
        "",
        key="filtro_piani_integrati",
    )

    try:
        df_piani = get_piani_dettaglio(limit=int(limit_rows_piani))
        if df_piani.empty:
            st.info("Nessun piano comunale trovato nel database.")
        else:
            df_view = df_piani.copy()

            if filtro_testo.strip():
                pattern = filtro_testo.strip()
                mask = df_view["Piano"].astype(str).str.contains(
                    pattern, case=False, na=False
                )
                if "Comune" in df_view.columns:
                    mask = mask | df_view["Comune"].astype(str).str.contains(
                        pattern, case=False, na=False
                    )
                df_view = df_view[mask]

            # Indici consecutivi per poter allineare editor e tendina
            df_view = df_view.reset_index(drop=True)

            # Se è presente una colonna "Path", la rendiamo cliccabile come link
            column_config = {}
            if "Path" in df_view.columns:
                column_config["Path"] = st.column_config.LinkColumn(
                    "Path",
                    display_text="apri",
                )

            # Aggiungiamo una colonna di selezione per scegliere il piano direttamente dalla tabella
            SELEZ_COL = "_seleziona"
            df_view_display = df_view.copy()
            if SELEZ_COL not in df_view_display.columns:
                df_view_display[SELEZ_COL] = False

            # Porta la colonna di selezione in prima posizione nella tabella
            cols = [SELEZ_COL] + [c for c in df_view_display.columns if c != SELEZ_COL]
            df_view_display = df_view_display[cols]

            column_config[SELEZ_COL] = st.column_config.CheckboxColumn(
                "Seleziona",
                help="Seleziona il piano su cui lavorare",
                default=False,
            )

            df_view_edit = st.data_editor(
                df_view_display,
                use_container_width=True,
                column_config=column_config,
                hide_index=True,
                key="editor_piani_integrati",
            )

            # Determina la riga selezionata nella tabella (prima con _seleziona=True)
            selected_idx = None
            if SELEZ_COL in df_view_edit.columns:
                selected_rows = df_view_edit[df_view_edit[SELEZ_COL]]
                if not selected_rows.empty:
                    selected_idx = int(selected_rows.index[0])

            # Lista opzioni per la tendina, allineate all'ordine delle righe in df_view_edit
            options = list(df_view_edit.itertuples(index=False))

            # Se disponibile un percorso, permetti di aprire la cartella in Esplora risorse
            if "Path" in df_view_edit.columns and options:
                st.markdown("### Apri cartella in Esplora risorse (sul tuo PC)")

                # Se una riga è stata selezionata nella tabella, usala come default per la tendina
                default_index = 0
                if selected_idx is not None and 0 <= selected_idx < len(options):
                    default_index = selected_idx

                row_to_open = st.selectbox(
                    "Seleziona il piano per aprire la cartella associata",
                    options=options,
                    format_func=lambda row: f"{getattr(row, 'id_piano', '?')} - {getattr(row, 'Piano', '')}",
                    key="seleziona_piano_apri_cartella",
                    index=default_index,
                )

                if row_to_open is not None:
                    piano_sel = getattr(row_to_open, "Piano", "")
                    st.markdown(f"**Piano selezionato:** {piano_sel}")

                    selected_path = getattr(row_to_open, "Path", None)
                    if selected_path and st.button(
                        "Apri cartella in Esplora risorse",
                        key="btn_apri_cartella_explorer",
                    ):
                        try:
                            open_path_in_explorer(selected_path)
                            st.success("Comando inviato a Esplora risorse.")
                        except Exception as e_open:
                            st.error(f"Impossibile aprire la cartella: {e_open}")

    except Exception as e:
        st.error(f"Errore durante il caricamento della vista integrata dei piani: {e}")

    st.markdown("---")
    with st.expander("🔧 Tabelle di base (solo per verifica dati)"):
        table_choice = st.selectbox(
            "Seleziona la tabella da consultare:",
            options=list(TAB_LABELS.keys()),
            format_func=lambda key: TAB_LABELS.get(key, key),
            key="tabella_debug",
        )

        limit_rows = st.number_input(
            "Numero massimo di righe da caricare",
            1,
            10000,
            1000,
            key="limit_tabella_debug",
        )

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
            st.error(f"Errore nel caricamento dei comuni dalla tabella {TABLE_PS_GEO_COMUNE}: {e}")
            df_comuni = pd.DataFrame(columns=["id_comune", "nome_comune"])

        try:
            df_stato = get_decodifica_options(
                TABLE_PS_D_STATO_PIANO, "id_stato_piano", "descr_stato_piano"
            )
        except Exception as e:
            st.error(
                f"Errore nel caricamento degli stati piano dalla tabella {TABLE_PS_D_STATO_PIANO}: {e}"
            )
            df_stato = pd.DataFrame(columns=["id_stato_piano", "descr_stato_piano"])

        try:
            df_tipo_piano = get_decodifica_options(
                TABLE_PS_D_TIPO_PIANO, "id_tipo_piano", "descr_tipo_piano"
            )
        except Exception as e:
            st.error(
                f"Errore nel caricamento dei tipi piano dalla tabella {TABLE_PS_D_TIPO_PIANO}: {e}"
            )
            df_tipo_piano = pd.DataFrame(columns=["id_tipo_piano", "descr_tipo_piano"])

        try:
            df_tipo_delibera = get_decodifica_options(
                TABLE_PS_D_TIPO_DELIBERA, "id_tipo_delibera", "descr_tipo_delibera"
            )
        except Exception as e:
            st.error(
                f"Errore nel caricamento dei tipi delibera dalla tabella {TABLE_PS_D_TIPO_DELIBERA}: {e}"
            )
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
                st.warning(
                    f"Nessun comune trovato nella tabella {TABLE_PS_GEO_COMUNE}."
                )
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
                st.warning(
                    f"Tabella {TABLE_PS_D_STATO_PIANO} vuota o non leggibile."
                )
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
                st.warning(
                    f"Tabella {TABLE_PS_D_TIPO_PIANO} vuota o non leggibile."
                )
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
                st.warning(
                    f"Tabella {TABLE_PS_D_TIPO_DELIBERA} vuota o non leggibile."
                )
                selected_id_tipo_delibera = None

            descrizione_piano = st.text_area(
                "Descrizione del piano (ente)",
                placeholder="Es. Comune di ... - Piano comunale di emergenza ...",
            )
            path_file = st.text_input(
                "Percorso/URL del file del piano (opzionale)",
                placeholder="Es. \\ileserver\\piani\\piano_comunale.pdf oppure https://...",
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
                            path_file=path_file.strip() or None,
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
                st.info(
                    f"Nessun piano presente nella tabella {TABLE_PS_T_ANAGRAFICA_PC}."
                )
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
            st.error(
                f"Impossibile leggere le colonne della tabella {table_choice_generic}: {e}"
            )
            columns = []

        if columns:
            st.markdown(
                "**Valori da inserire (lascia vuoto per usare il default del DB, se esiste)**"
            )

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
                            # Il nome tabella è in minuscolo e non quotato per allinearsi agli schemi del DB
                            query = (
                                f"INSERT INTO {table_choice_generic} ({cols_sql}) "
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
