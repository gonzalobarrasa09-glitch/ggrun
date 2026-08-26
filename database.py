import sqlite3
import pandas as pd
import json
from datetime import datetime

DB_FILE = "fitness_tracker.db"

def get_db_connection():
    return sqlite3.connect(DB_FILE)

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS activities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            filename TEXT,
            sport TEXT,
            start_time TEXT,
            total_distance_km REAL,
            total_duration_min REAL,
            avg_pace TEXT,
            avg_hr INTEGER,
            max_hr INTEGER,
            total_ascent_m REAL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS activity_laps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            activity_id INTEGER,
            lap_index INTEGER,
            distance_km REAL,
            duration_min REAL,
            pace TEXT,
            avg_hr INTEGER,
            max_hr INTEGER,
            avg_cadence INTEGER,
            ascent_m REAL,
            FOREIGN KEY (activity_id) REFERENCES activities(id) ON DELETE CASCADE
        )
    ''')

    cursor.execute("INSERT OR IGNORE INTO users (name) VALUES ('Gonzalo'), ('Usuario2')")
    conn.commit()
    conn.close()

def get_user_list():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM users")
    users = [row[0] for row in cursor.fetchall()]
    conn.close()
    return users

def get_activities_df(user_name):
    conn = get_db_connection()
    query = '''
        SELECT a.id AS 'ID', a.start_time AS 'Fecha', a.sport AS 'Deporte', 
               a.total_distance_km AS 'Distancia (km)', a.total_duration_min AS 'Duración (min)', 
               a.avg_pace AS 'Ritmo', a.avg_hr AS 'FC Media'
        FROM activities a
        JOIN users u ON a.user_id = u.id
        WHERE u.name = ?
        ORDER BY a.start_time DESC
    '''
    df = pd.read_sql_query(query, conn, params=(user_name,))
    conn.close()
    return df

def get_laps_df(activity_id):
    if not activity_id:
        return pd.DataFrame()
    conn = get_db_connection()
    query = '''
        SELECT lap_index AS 'Tramo', distance_km AS 'Distancia (km)', duration_min AS 'Tiempo (min)',
               pace AS 'Ritmo', avg_hr AS 'FC Med', max_hr AS 'FC Max', 
               avg_cadence AS 'Cadencia', ascent_m AS 'Desnivel (m)'
        FROM activity_laps
        WHERE activity_id = ?
        ORDER BY lap_index ASC
    '''
    df = pd.read_sql_query(query, conn, params=(activity_id,))
    conn.close()
    return df

def insert_parsed_activity(user_name, filename, session, laps):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE name = ?", (user_name,))
    user_row = cursor.fetchone()
    
    if not user_row:
        conn.close()
        return False, "Usuario no encontrado en base de datos."
        
    user_id = user_row[0]
    
    cursor.execute('''
        INSERT INTO activities 
        (user_id, filename, sport, start_time, total_distance_km, total_duration_min, avg_pace, avg_hr, max_hr, total_ascent_m)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        user_id, filename, session['sport'], session['start_time'],
        session['total_distance_km'], session['total_duration_min'],
        session['avg_pace'], session['avg_hr'], session['max_hr'], session['total_ascent_m']
    ))
    
    activity_id = cursor.lastrowid
    
    for l in laps:
        cursor.execute('''
            INSERT INTO activity_laps 
            (activity_id, lap_index, distance_km, duration_min, pace, avg_hr, max_hr, avg_cadence, ascent_m)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            activity_id, l['lap_index'], l['distance_km'], l['duration_min'],
            l['pace'], l['avg_hr'], l['max_hr'], l['avg_cadence'], l['ascent_m']
        ))
        
    conn.commit()
    conn.close()
    return True, "OK"

def export_json_for_ai(user_name, include_laps):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT a.id, a.start_time, a.sport, a.total_distance_km, a.total_duration_min,
               a.avg_pace, a.avg_hr, a.max_hr, a.total_ascent_m
        FROM activities a
        JOIN users u ON a.user_id = u.id
        WHERE u.name = ?
        ORDER BY a.start_time DESC
    ''', (user_name,))
    
    act_rows = cursor.fetchall()
    activities_list = []
    
    for row in act_rows:
        act_id, start_time, sport, dist, dur, pace, avg_hr, max_hr, ascent = row
        act_dict = {
            "id": act_id,
            "fecha": start_time,
            "deporte": sport,
            "resumen": {
                "distancia_km": dist,
                "duracion_min": dur,
                "ritmo_medio": pace,
                "fc_media": avg_hr,
                "fc_maxima": max_hr,
                "desnivel_m": ascent
            }
        }
        if include_laps:
            cursor.execute('''
                SELECT lap_index, distance_km, duration_min, pace, avg_hr, max_hr, avg_cadence, ascent_m
                FROM activity_laps
                WHERE activity_id = ?
                ORDER BY lap_index ASC
            ''', (act_id,))
            laps = cursor.fetchall()
            act_dict["tramos_detalle"] = [
                {
                    "tramo": l[0],
                    "distancia_km": l[1],
                    "duracion_min": l[2],
                    "ritmo": l[3],
                    "fc_media": l[4],
                    "fc_max": l[5],
                    "cadencia": l[6],
                    "desnivel_m": l[7]
                } for l in laps
            ]
        activities_list.append(act_dict)
        
    conn.close()
    return json.dumps({
        "usuario": user_name,
        "fecha_exportacion": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_actividades": len(activities_list),
        "actividades": activities_list
    }, indent=2, ensure_ascii=False)