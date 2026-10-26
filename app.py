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

def get_connection() -> psycopg2.extensions.connection:
    """Restituisce una connessione psycopg2 al database."""

    return psycopg2.connect(
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
        port=DB_PORT,
    )


def load_table(table_name: str, limit: int = 1000) -> pd.DataFrame:
    """Carica i primi N record da una tabella generica."""

    conn = None
    try:
        conn = get_connection()
        query = f"SELECT * FROM {table_name} LIMIT %s"
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
        cursor.execute(f"SELECT * FROM {table_name} LIMIT 0")
        return [desc[0] for desc in cursor.description]
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()


def get_decodifica_options(
    table_name: str, id_column: str, desc_column: str
) -> pd.DataFrame:
    """Carica una tabella di decodifica restituendo solo id + descrizione."""

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

    id_col = None
    if id_column in columns:
        id_col = id_column
    else:
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
        query = (
            f'SELECT "{id_col}" AS "{id_column}", "{desc_col}" AS "{desc_column}" '
            f"FROM {table_name} ORDER BY \"{desc_col}\""
        )
        df = pd.read_sql_query(query, conn)
        return df
    finally:
        if conn is not None:
            conn.close()


# -----------------------------------------------------------
# FUNZIONI DI DOMINIO PIANI COMUNALI
# -----------------------------------------------------------


def insert_piano_comunale(
    descrizione_piano: str,
    id_stato_piano: int,
    id_tipo_piano: int,
    id_tipo_delibera: int,
    id_comune: int,
    path_file: str | None = None,
    note: str | None = None,
) -> int:
    """Inserisce un piano comunale e la relazione con il comune."""

    conn = None
    cursor = None

    try:
        conn = get_connection()
        cursor = conn.cursor()

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


def get_piano_dettaglio_by_id(id_piano: int) -> dict[str, object] | None:
    """Restituisce i dati di un singolo piano (più il comune associato)."""

    conn = None
    try:
        conn = get_connection()
        query = (
            "SELECT "
            "  p.id_modulo AS id_piano, "
            "  p.ente AS descrizione_piano, "
            "  p.fk_stato_piano AS id_stato_piano, "
            "  p.fk_tipo_piano AS id_tipo_piano, "
            "  p.fk_delibera AS id_tipo_delibera, "
            "  p.path_file, "
            "  p.note, "
            "  r.fk_comune AS id_comune "
            f"FROM {TABLE_PS_T_ANAGRAFICA_PC} p "
            f"LEFT JOIN {TABLE_PS_R_PIANO_COMUNE} r ON r.fk_modulo = p.id_modulo "
            "WHERE p.id_modulo = %s"
        )
        df = pd.read_sql_query(query, conn, params=(id_piano,))
        if df.empty:
            return None
        return df.iloc[0].to_dict()
    finally:
        if conn is not None:
            conn.close()


def update_piano_comunale(
    id_piano: int,
    descrizione_piano: str,
    id_stato_piano: int,
    id_tipo_piano: int,
    id_tipo_delibera: int,
    id_comune: int | None = None,
    path_file: str | None = None,
    note: str | None = None,
) -> None:
    """Aggiorna un piano comunale esistente e la relazione con il comune."""

    conn = None
    cursor = None

    try:
        conn = get_connection()
        cursor = conn.cursor()

        update_piano_query = (
            f"UPDATE {TABLE_PS_T_ANAGRAFICA_PC} "
            "SET fk_tipo_piano = %s, "
            "    fk_stato_piano = %s, "
            "    fk_delibera = %s, "
            "    path_file = %s, "
            "    note = %s, "
            "    ente = %s "
            "WHERE id_modulo = %s"
        )

        cursor.execute(
            update_piano_query,
            (
                id_tipo_piano,
                id_stato_piano,
                id_tipo_delibera,
                path_file,
                note,
                descrizione_piano,
                id_piano,
            ),
        )

        if cursor.rowcount == 0:
            raise ValueError(f"Nessun piano trovato con id_piano = {id_piano}")

        if id_comune is not None:
            cursor.execute(
                f"SELECT COUNT(*) FROM {TABLE_PS_R_PIANO_COMUNE} WHERE fk_modulo = %s",
                (id_piano,),
            )
            count_rel = cursor.fetchone()[0]

            if count_rel and count_rel > 0:
                cursor.execute(
                    f"UPDATE {TABLE_PS_R_PIANO_COMUNE} "
                    "SET fk_comune = %s "
                    "WHERE fk_modulo = %s",
                    (id_comune, id_piano),
                )
            else:
                cursor.execute(
                    f"INSERT INTO {TABLE_PS_R_PIANO_COMUNE} (fk_modulo, fk_comune) "
                    "VALUES (%s, %s)",
                    (id_piano, id_comune),
                )

        conn.commit()
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()


def get_comuni() -> pd.DataFrame:
    """Ritorna l'elenco dei comuni (id_comune, nome_comune)."""

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
    """Restituisce gli ultimi piani inseriti (per consultazione veloce)."""

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
    """Restituisce la relazione piano-comune (id_piano, id_comune)."""

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
    """Restituisce una vista integrata dei piani comunali senza modificare il path."""

    df_piani = get_last_piani(limit=limit)
    if df_piani.empty:
        return df_piani

    try:
        df_rel = get_relazioni_piano_comune()
    except Exception:
        df_rel = pd.DataFrame(columns=["id_piano", "id_comune"])

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

    df = df_piani.merge(df_rel, on="id_piano", how="left")

    if not df_comuni.empty:
        df = df.merge(df_comuni, on="id_comune", how="left")

    if not df_stato.empty:
        df = df.merge(df_stato, on="id_stato_piano", how="left")

    if not df_tipo_piano.empty:
        df = df.merge(df_tipo_piano, on="id_tipo_piano", how="left")

    if not df_tipo_delibera.empty:
        df = df.merge(df_tipo_delibera, on="id_tipo_delibera", how="left")

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

    path_col = None
    for c in df.columns:
        if "path" in c.lower() or "url" in c.lower():
            path_col = c
            break
    if path_col is not None and path_col != "Path":
        df = df.rename(columns={path_col: "Path"})

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
    remaining_cols = [c for c in df.columns if c not in existing_cols]
    df = df[existing_cols + remaining_cols]

    return df


# -----------------------------------------------------------
# UTILITY GLOBALI PER APERTURA PERCORSI (Esplora risorse)
# -----------------------------------------------------------


def _file_uri_to_windows_path(value: object) -> str:
    r"""Converte un URI/URL o stringa di percorso in un path Windows."""

    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""

    s = str(value).strip()
    s = s.replace("\r", "").replace("\n", "")
    if not s:
        return ""

    lower = s.lower()

    if lower.startswith("file:"):
        s = s[5:]
        s = s.lstrip("/\\")

    if s.startswith("\\") or s.startswith("//"):
        return s.replace("/", "\\")

    if len(s) >= 2 and s[1] == ":":
        return s.replace("/", "\\")

    if "\\" in s and not s.startswith("\\") and not s.startswith("//"):
        parts = s.split("\\", 1)
        host = parts[0]
        rest = parts[1] if len(parts) > 1 else ""
        if rest:
            return f"\\\\{host}\\{rest}"
        return f"\\\\{host}"

    parts = s.split("/")
    if len(parts) > 1:
        host = parts[0]
        rest = "\\".join(parts[1:])
        return f"\\\\{host}\\{rest}"

    return s


def open_path_in_explorer(value: object) -> None:
    """Apre il percorso indicato (file o cartella) in Esplora risorse (solo Windows)."""

    win_path = _file_uri_to_windows_path(value)
    if not win_path:
        raise ValueError("Percorso vuoto o non valido")

    if os.path.isfile(win_path):
        folder = os.path.dirname(win_path)
        os.startfile(folder)  # type: ignore[attr-defined]
    else:
        os.startfile(win_path)  # type: ignore[attr-defined]


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


tab_gestione, tab_generico = st.tabs(
    [
        "📑 Gestione Piani",
        "🧩 Inserimento generico (qualunque tabella)",
    ]
)


# -----------------------------------------------------------
# TAB 1 - GESTIONE PIANI
# -----------------------------------------------------------

with tab_gestione:
    st.header("📑 Gestione Piani comunali")

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

    df_view_edit: pd.DataFrame | None = None
    selected_idx: int | None = None
    selected_piano_id: int | None = None

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

            df_view = df_view.reset_index(drop=True)

            column_config: dict[str, object] = {}

            SELEZ_COL = "_seleziona"
            df_view_display = df_view.copy()
            if SELEZ_COL not in df_view_display.columns:
                df_view_display[SELEZ_COL] = False

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

            if SELEZ_COL in df_view_edit.columns:
                selected_rows = df_view_edit[df_view_edit[SELEZ_COL]]
                if not selected_rows.empty:
                    selected_idx = int(selected_rows.index[0])

            if selected_idx is not None and 0 <= selected_idx < len(df_view_edit):
                try:
                    row_sel_edit = df_view_edit.iloc[selected_idx]
                    if "id_piano" in row_sel_edit.index:
                        selected_piano_id = int(row_sel_edit["id_piano"])
                except Exception:
                    selected_piano_id = None

    except Exception as e:
        st.error(f"Errore durante il caricamento della vista integrata dei piani: {e}")

    # SOTTOSEZIONE 1: APRI CARTELLA
    with st.expander("📂 Apri cartella in Esplora risorse (sul tuo PC)"):
        if df_view_edit is None or df_view_edit.empty or "Path" not in df_view_edit.columns:
            st.info(
                "La vista principale non contiene una colonna 'Path' o non ci sono piani da mostrare."
            )
        elif selected_idx is None:
            st.info(
                "Seleziona un piano nella tabella (colonna 'Seleziona') per poter aprire la cartella."
            )
        else:
            try:
                row_to_open = df_view_edit.iloc[selected_idx]
            except Exception:
                row_to_open = None

            if row_to_open is None:
                st.info("Impossibile individuare la riga selezionata.")
            else:
                piano_sel = row_to_open.get("Piano", "")
                selected_path = row_to_open.get("Path", None)
                st.markdown(f"**Piano selezionato:** {piano_sel}")
                st.markdown(f"**Path:** {selected_path if selected_path else '-'}")

                if selected_path and st.button("Apri cartella in Esplora risorse"):
                    try:
                        open_path_in_explorer(selected_path)
                        st.success("Comando inviato a Esplora risorse.")
                    except Exception as e_open:
                        st.error(f"Impossibile aprire la cartella: {e_open}")

    # SOTTOSEZIONE 2: MODIFICA PIANO ESISTENTE
    with st.expander("✏️ Modifica piano esistente"):
        if selected_piano_id is None:
            st.info(
                "Seleziona un piano dalla tabella in alto (colonna 'Seleziona') per poterlo modificare."
            )
        else:
            try:
                dati_piano = get_piano_dettaglio_by_id(selected_piano_id)
            except Exception as e_det:
                st.error(
                    f"Errore nel caricamento dei dettagli del piano {selected_piano_id}: {e_det}"
                )
                dati_piano = None

            if not dati_piano:
                st.info("Impossibile caricare i dettagli del piano selezionato.")
            else:
                st.markdown(
                    "Modifica i campi sottostanti e premi **Aggiorna piano** "
                    "per salvare le modifiche nel database."
                )

                try:
                    df_comuni_edit = get_comuni()
                except Exception as e:
                    st.error(
                        f"Errore nel caricamento dei comuni dalla tabella {TABLE_PS_GEO_COMUNE}: {e}"
                    )
                    df_comuni_edit = pd.DataFrame(
                        columns=["id_comune", "nome_comune"]
                    )

                try:
                    df_stato_edit = get_decodifica_options(
                        TABLE_PS_D_STATO_PIANO,
                        "id_stato_piano",
                        "descr_stato_piano",
                    )
                except Exception as e:
                    st.error(
                        f"Errore nel caricamento degli stati piano dalla tabella {TABLE_PS_D_STATO_PIANO}: {e}"
                    )
                    df_stato_edit = pd.DataFrame(
                        columns=["id_stato_piano", "descr_stato_piano"]
                    )

                try:
                    df_tipo_piano_edit = get_decodifica_options(
                        TABLE_PS_D_TIPO_PIANO,
                        "id_tipo_piano",
                        "descr_tipo_piano",
                    )
                except Exception as e:
                    st.error(
                        f"Errore nel caricamento dei tipi piano dalla tabella {TABLE_PS_D_TIPO_PIANO}: {e}"
                    )
                    df_tipo_piano_edit = pd.DataFrame(
                        columns=["id_tipo_piano", "descr_tipo_piano"]
                    )

                try:
                    df_tipo_delibera_edit = get_decodifica_options(
                        TABLE_PS_D_TIPO_DELIBERA,
                        "id_tipo_delibera",
                        "descr_tipo_delibera",
                    )
                except Exception as e:
                    st.error(
                        f"Errore nel caricamento dei tipi delibera dalla tabella {TABLE_PS_D_TIPO_DELIBERA}: {e}"
                    )
                    df_tipo_delibera_edit = pd.DataFrame(
                        columns=["id_tipo_delibera", "descr_tipo_delibera"]
                    )

                with st.form(
                    f"form_modifica_piano_{selected_piano_id}",
                    clear_on_submit=False,
                ):
                    id_comune_corrente = dati_piano.get("id_comune")
                    if not df_comuni_edit.empty:
                        opzioni_comuni = list(df_comuni_edit.itertuples(index=False))
                        index_comune_default = 0
                        if id_comune_corrente is not None:
                            for i, row in enumerate(opzioni_comuni):
                                if int(row.id_comune) == int(id_comune_corrente):
                                    index_comune_default = i
                                    break
                        comune_sel = st.selectbox(
                            "Comune",
                            options=opzioni_comuni,
                            index=index_comune_default,
                            format_func=lambda row: f"{row.id_comune} - {row.nome_comune}",
                            key=f"edit_comune_{selected_piano_id}",
                        )
                        id_comune_nuovo = int(comune_sel.id_comune)
                    else:
                        st.warning(
                            f"Nessun comune trovato nella tabella {TABLE_PS_GEO_COMUNE}."
                        )
                        id_comune_nuovo = (
                            int(id_comune_corrente)
                            if id_comune_corrente is not None
                            else None
                        )

                    id_stato_corrente = dati_piano.get("id_stato_piano")
                    if not df_stato_edit.empty:
                        opzioni_stato = list(df_stato_edit.itertuples(index=False))
                        index_stato_default = 0
                        if id_stato_corrente is not None:
                            for i, row in enumerate(opzioni_stato):
                                if int(row.id_stato_piano) == int(id_stato_corrente):
                                    index_stato_default = i
                                    break
                        stato_sel = st.selectbox(
                            "Stato piano",
                            options=opzioni_stato,
                            index=index_stato_default,
                            format_func=lambda row: f"{row.id_stato_piano} - {row.descr_stato_piano}",
                            key=f"edit_stato_{selected_piano_id}",
                        )
                        id_stato_nuovo = int(stato_sel.id_stato_piano)
                    else:
                        st.warning(
                            f"Tabella {TABLE_PS_D_STATO_PIANO} vuota o non leggibile."
                        )
                        id_stato_nuovo = (
                            int(id_stato_corrente)
                            if id_stato_corrente is not None
                            else None
                        )

                    id_tipo_piano_corrente = dati_piano.get("id_tipo_piano")
                    if not df_tipo_piano_edit.empty:
                        opzioni_tp = list(df_tipo_piano_edit.itertuples(index=False))
                        index_tp_default = 0
                        if id_tipo_piano_corrente is not None:
                            for i, row in enumerate(opzioni_tp):
                                if int(row.id_tipo_piano) == int(id_tipo_piano_corrente):
                                    index_tp_default = i
                                    break
                        tp_sel = st.selectbox(
                            "Tipo piano",
                            options=opzioni_tp,
                            index=index_tp_default,
                            format_func=lambda row: f"{row.id_tipo_piano} - {row.descr_tipo_piano}",
                            key=f"edit_tp_{selected_piano_id}",
                        )
                        id_tipo_piano_nuovo = int(tp_sel.id_tipo_piano)
                    else:
                        st.warning(
                            f"Tabella {TABLE_PS_D_TIPO_PIANO} vuota o non leggibile."
                        )
                        id_tipo_piano_nuovo = (
                            int(id_tipo_piano_corrente)
                            if id_tipo_piano_corrente is not None
                            else None
                        )

                    id_tipo_delibera_corrente = dati_piano.get("id_tipo_delibera")
                    if not df_tipo_delibera_edit.empty:
                        opzioni_td = list(df_tipo_delibera_edit.itertuples(index=False))
                        index_td_default = 0
                        if id_tipo_delibera_corrente is not None:
                            for i, row in enumerate(opzioni_td):
                                if int(row.id_tipo_delibera) == int(
                                    id_tipo_delibera_corrente
                                ):
                                    index_td_default = i
                                    break
                        td_sel = st.selectbox(
                            "Tipo delibera",
                            options=opzioni_td,
                            index=index_td_default,
                            format_func=lambda row: f"{row.id_tipo_delibera} - {row.descr_tipo_delibera}",
                            key=f"edit_td_{selected_piano_id}",
                        )
                        id_tipo_delibera_nuovo = int(td_sel.id_tipo_delibera)
                    else:
                        st.warning(
                            f"Tabella {TABLE_PS_D_TIPO_DELIBERA} vuota o non leggibile."
                        )
                        id_tipo_delibera_nuovo = (
                            int(id_tipo_delibera_corrente)
                            if id_tipo_delibera_corrente is not None
                            else None
                        )

                    descrizione_nuova = st.text_area(
                        "Descrizione del piano (ente)",
                        value=str(dati_piano.get("descrizione_piano") or ""),
                        key=f"edit_descr_{selected_piano_id}",
                    )
                    path_nuovo = st.text_input(
                        "Percorso/URL del file del piano (opzionale)",
                        value=str(dati_piano.get("path_file") or ""),
                        key=f"edit_path_{selected_piano_id}",
                    )
                    note_nuove = st.text_area(
                        "Note (opzionale)",
                        value=str(dati_piano.get("note") or ""),
                        key=f"edit_note_{selected_piano_id}",
                    )

                    submit_update = st.form_submit_button("Aggiorna piano")

                    if submit_update:
                        if (
                            id_comune_nuovo is None
                            or id_stato_nuovo is None
                            or id_tipo_piano_nuovo is None
                            or id_tipo_delibera_nuovo is None
                        ):
                            st.error(
                                "Verifica che le tabelle di decodifica e dei comuni contengano dati "
                                "e che le colonne usate nel codice corrispondano a quelle del DB."
                            )
                        elif not descrizione_nuova.strip():
                            st.error("La descrizione del piano è obbligatoria.")
                        else:
                            try:
                                update_piano_comunale(
                                    id_piano=selected_piano_id,
                                    descrizione_piano=descrizione_nuova.strip(),
                                    id_stato_piano=id_stato_nuovo,
                                    id_tipo_piano=id_tipo_piano_nuovo,
                                    id_tipo_delibera=id_tipo_delibera_nuovo,
                                    id_comune=id_comune_nuovo,
                                    path_file=path_nuovo.strip() or None,
                                    note=note_nuove.strip() or None,
                                )
                                st.success(
                                    f"Piano {selected_piano_id} aggiornato correttamente."
                                )
                            except Exception as e_upd:
                                st.error(
                                    f"Errore durante l'aggiornamento del piano: {e_upd}"
                                )

    # SOTTOSEZIONE 3: NUOVO PIANO
    with st.expander("➕ Nuovo piano"):
        try:
            df_comuni_new = get_comuni()
        except Exception as e:
            st.error(
                f"Errore nel caricamento dei comuni dalla tabella {TABLE_PS_GEO_COMUNE}: {e}"
            )
            df_comuni_new = pd.DataFrame(columns=["id_comune", "nome_comune"])

        try:
            df_stato_new = get_decodifica_options(
                TABLE_PS_D_STATO_PIANO, "id_stato_piano", "descr_stato_piano"
            )
        except Exception as e:
            st.error(
                f"Errore nel caricamento degli stati piano dalla tabella {TABLE_PS_D_STATO_PIANO}: {e}"
            )
            df_stato_new = pd.DataFrame(
                columns=["id_stato_piano", "descr_stato_piano"]
            )

        try:
            df_tipo_piano_new = get_decodifica_options(
                TABLE_PS_D_TIPO_PIANO, "id_tipo_piano", "descr_tipo_piano"
            )
        except Exception as e:
            st.error(
                f"Errore nel caricamento dei tipi piano dalla tabella {TABLE_PS_D_TIPO_PIANO}: {e}"
            )
            df_tipo_piano_new = pd.DataFrame(
                columns=["id_tipo_piano", "descr_tipo_piano"]
            )

        try:
            df_tipo_delibera_new = get_decodifica_options(
                TABLE_PS_D_TIPO_DELIBERA, "id_tipo_delibera", "descr_tipo_delibera"
            )
        except Exception as e:
            st.error(
                f"Errore nel caricamento dei tipi delibera dalla tabella {TABLE_PS_D_TIPO_DELIBERA}: {e}"
            )
            df_tipo_delibera_new = pd.DataFrame(
                columns=["id_tipo_delibera", "descr_tipo_delibera"]
            )

        with st.form("form_nuovo_piano", clear_on_submit=False):
            if not df_comuni_new.empty:
                comune_obj = st.selectbox(
                    "Comune",
                    options=list(df_comuni_new.itertuples(index=False)),
                    format_func=lambda row: f"{row.id_comune} - {row.nome_comune}",
                )
                selected_id_comune_new = int(comune_obj.id_comune)
            else:
                st.warning(
                    f"Nessun comune trovato nella tabella {TABLE_PS_GEO_COMUNE}."
                )
                selected_id_comune_new = None

            if not df_stato_new.empty:
                stato_obj = st.selectbox(
                    "Stato piano",
                    options=list(df_stato_new.itertuples(index=False)),
                    format_func=lambda row: f"{row.id_stato_piano} - {row.descr_stato_piano}",
                )
                selected_id_stato_new = int(stato_obj.id_stato_piano)
            else:
                st.warning(
                    f"Tabella {TABLE_PS_D_STATO_PIANO} vuota o non leggibile."
                )
                selected_id_stato_new = None

            if not df_tipo_piano_new.empty:
                tp_obj = st.selectbox(
                    "Tipo piano",
                    options=list(df_tipo_piano_new.itertuples(index=False)),
                    format_func=lambda row: f"{row.id_tipo_piano} - {row.descr_tipo_piano}",
                )
                selected_id_tipo_piano_new = int(tp_obj.id_tipo_piano)
            else:
                st.warning(
                    f"Tabella {TABLE_PS_D_TIPO_PIANO} vuota o non leggibile."
                )
                selected_id_tipo_piano_new = None

            if not df_tipo_delibera_new.empty:
                td_obj = st.selectbox(
                    "Tipo delibera",
                    options=list(df_tipo_delibera_new.itertuples(index=False)),
                    format_func=lambda row: f"{row.id_tipo_delibera} - {row.descr_tipo_delibera}",
                )
                selected_id_tipo_delibera_new = int(td_obj.id_tipo_delibera)
            else:
                st.warning(
                    f"Tabella {TABLE_PS_D_TIPO_DELIBERA} vuota o non leggibile."
                )
                selected_id_tipo_delibera_new = None

            descrizione_piano_new = st.text_area(
                "Descrizione del piano (ente)",
                placeholder="Es. Comune di ... - Piano comunale di emergenza ...",
            )
            path_file_new = st.text_input(
                "Percorso/URL del file del piano (opzionale)",
                placeholder="Es. \\\\fileserver\\piani\\piano_comunale.pdf oppure https://...",
            )
            note_new = st.text_area("Note (opzionale)")

            submit_piano_new = st.form_submit_button("Salva nuovo piano nel database")

            if submit_piano_new:
                if (
                    selected_id_comune_new is None
                    or selected_id_stato_new is None
                    or selected_id_tipo_piano_new is None
                    or selected_id_tipo_delibera_new is None
                ):
                    st.error(
                        "Verifica che le tabelle di decodifica e dei comuni contengano dati "
                        "e che le colonne usate nel codice corrispondano a quelle del DB."
                    )
                elif not descrizione_piano_new.strip():
                    st.error("La descrizione del piano è obbligatoria.")
                else:
                    try:
                        new_id = insert_piano_comunale(
                            descrizione_piano=descrizione_piano_new.strip(),
                            id_stato_piano=selected_id_stato_new,
                            id_tipo_piano=selected_id_tipo_piano_new,
                            id_tipo_delibera=selected_id_tipo_delibera_new,
                            id_comune=selected_id_comune_new,
                            path_file=path_file_new.strip() or None,
                            note=note_new.strip() or None,
                        )
                        st.success(
                            f"Piano inserito correttamente con id_piano = {new_id}."
                        )
                    except Exception as e:
                        st.error(f"Errore durante l'inserimento del piano: {e}")

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
            df_debug = load_table(table_choice, limit=int(limit_rows))
            st.success(f"Caricate {len(df_debug)} righe dalla tabella {table_choice}.")
            st.dataframe(df_debug, use_container_width=True)
        except Exception as e:
            st.error(f"Errore durante il caricamento della tabella {table_choice}: {e}")


# -----------------------------------------------------------
# TAB 2 - INSERIMENTO GENERICO SU QUALSIASI TABELLA
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
