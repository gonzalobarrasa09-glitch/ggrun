import os
from datetime import datetime
from garmin_fit_sdk import Decoder, Stream

def m_s_to_pace(speed_m_s):
    try:
        speed = float(speed_m_s)
        if speed <= 0:
            return "-:--"
        pace_seconds = 1000.0 / speed
        minutes = int(pace_seconds // 60)
        seconds = int(round(pace_seconds % 60))
        if seconds == 60:
            minutes += 1
            seconds = 0
        return f"{minutes}:{seconds:02d}"
    except (ValueError, TypeError):
        return "-:--"

def parse_fit_file_safe(file_path):
    session_data = {
        'sport': 'Desconocido',
        'start_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'total_distance_km': 0.0,
        'total_duration_min': 0.0,
        'avg_pace': '-:--',
        'avg_hr': 0,
        'max_hr': 0,
        'total_ascent_m': 0.0
    }
    laps_data = []
    debug_log = []

    try:
        stream = Stream.from_file(file_path)
        decoder = Decoder(stream)
        messages, errors = decoder.read()
    except Exception as e:
        debug_log.append(f"ERROR CRÍTICO LEYENDO ARCHIVO: {str(e)}")
        return session_data, laps_data, "\n".join(debug_log)

    session_mesgs = messages.get('session_mesgs', [])
    if session_mesgs:
        s = session_mesgs[0]
        session_data['sport'] = str(s.get('sport', 'running')).lower()
        st = s.get('start_time')
        if isinstance(st, datetime):
            session_data['start_time'] = st.strftime('%Y-%m-%d %H:%M:%S')
        elif st:
            session_data['start_time'] = str(st)
            
        dist_m = s.get('total_distance', 0) or 0
        dur_s = s.get('total_timer_time', 0) or s.get('total_elapsed_time', 0) or 0
        avg_speed = s.get('avg_speed', 0) or 0
        
        session_data['total_distance_km'] = round(float(dist_m) / 1000.0, 2)
        session_data['total_duration_min'] = round(float(dur_s) / 60.0, 2)
        session_data['avg_pace'] = m_s_to_pace(avg_speed)
        session_data['avg_hr'] = int(s.get('avg_heart_rate', 0) or 0)
        session_data['max_hr'] = int(s.get('max_heart_rate', 0) or 0)
        session_data['total_ascent_m'] = round(float(s.get('total_ascent', 0) or 0), 1)

    lap_mesgs = messages.get('lap_mesgs', [])
    if lap_mesgs:
        for idx, l in enumerate(lap_mesgs):
            dist_m = l.get('total_distance', 0) or 0
            dur_s = l.get('total_timer_time', 0) or l.get('total_elapsed_time', 0) or 0
            avg_speed = l.get('avg_speed', 0) or 0
            
            laps_data.append({
                'lap_index': idx + 1,
                'distance_km': round(float(dist_m) / 1000.0, 2),
                'duration_min': round(float(dur_s) / 60.0, 2),
                'pace': m_s_to_pace(avg_speed),
                'avg_hr': int(l.get('avg_heart_rate', 0) or 0),
                'max_hr': int(l.get('max_heart_rate', 0) or 0),
                'avg_cadence': int(l.get('avg_cadence', 0) or 0),
                'ascent_m': round(float(l.get('total_ascent', 0) or 0), 1)
            })
        debug_log.append(f"Procesados {len(laps_data)} tramos explícitos.")
    else:
        debug_log.append("No se detectaron tramos explícitos. Generando 1 tramo global.")
        laps_data.append({
            'lap_index': 1,
            'distance_km': session_data['total_distance_km'],
            'duration_min': session_data['total_duration_min'],
            'pace': session_data['avg_pace'],
            'avg_hr': session_data['avg_hr'],
            'max_hr': session_data['max_hr'],
            'avg_cadence': 0,
            'ascent_m': session_data['total_ascent_m']
        })

    return session_data, laps_data, "\n".join(debug_log)