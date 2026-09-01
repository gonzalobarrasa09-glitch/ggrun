import os
import json
import gradio as gr
import pandas as pd
from database import (init_db, get_activities_df, get_laps_df, 
                      insert_parsed_activity, export_json_for_ai, delete_activity, get_activities_choices,
                      save_weekly_plan, get_weekly_plan, delete_weekly_plan)
from fit_parser import parse_fit_file_safe
from telegram_bot import launch_telegram_bot

init_db()

# Plantilla por defecto para el plan semanal
PLAN_TEMPLATE = """{
  "semana": "Del 1 al 7 de Septiembre",
  "objetivo": "Base Aeróbica y Fuerza",
  "entrenamientos": [
    { "dia": "Lunes", "tipo": "Descanso", "detalles": "Descanso activo / Movilidad" },
    { "dia": "Martes", "tipo": "Series", "detalles": "15' Z1 + 8x400m R:1' + 10' Z1" },
    { "dia": "Miércoles", "tipo": "Rodaje", "detalles": "45' Z2 a ritmo suave" },
    { "dia": "Jueves", "tipo": "Fuerza", "detalles": "Rutina de pierna en gimnasio" },
    { "dia": "Viernes", "tipo": "Descanso", "detalles": "Descanso total" },
    { "dia": "Sábado", "tipo": "Tirada Larga", "detalles": "90' Z2 controlando pulsaciones" },
    { "dia": "Domingo", "tipo": "Rodaje", "detalles": "Bici 1h30m muy suave" }
  ]
}"""

# --- PARSER HTML PARA EL PLAN SEMANAL ---

def render_plan_html(plan):
    if not plan or not isinstance(plan, dict):
        return ""
    
    semana = plan.get("semana", "Plan Semanal")
    objetivo = plan.get("objetivo", "")
    entrenamientos = plan.get("entrenamientos", [])
    
    badge_colors = {
        "descanso": ("#f3f4f6", "#4b5563", "#e5e7eb"),
        "series": ("#fee2e2", "#dc2626", "#fca5a5"),
        "rodaje": ("#dbeafe", "#2563eb", "#93c5fd"),
        "fuerza": ("#fef3c7", "#d97706", "#fcd34d"),
        "tirada larga": ("#e0e7ff", "#4f46e5", "#c7d2fe"),
    }
    
    cards_html = ""
    for item in entrenamientos:
        dia = item.get("dia", "Día")
        tipo = item.get("tipo", "Entrenamiento")
        detalles = item.get("detalles", "-")
        
        tipo_lower = tipo.lower()
        bg, text_col, border = ("#f0fdf4", "#16a34a", "#86efac")
        for key in badge_colors:
            if key in tipo_lower:
                bg, text_col, border = badge_colors[key]
                break
                
        cards_html += f'''
        <div class="day-card">
            <div class="day-header">
                <span class="day-title">{dia}</span>
                <span class="workout-badge" style="background-color: {bg}; color: {text_col}; border: 1px solid {border};">
                    {tipo}
                </span>
            </div>
            <p class="workout-details">{detalles}</p>
        </div>
        '''

    html_out = f'''
    <div class="plan-container">
        <div class="plan-header-card">
            <div class="plan-header-info">
                <h2>📅 {semana}</h2>
                {f'<p>🎯 <strong>Objetivo:</strong> {objetivo}</p>' if objetivo else ''}
            </div>
        </div>
        <div class="plan-grid">
            {cards_html}
        </div>
    </div>
    '''
    return html_out

# --- FUNCIONES DE LÓGICA Y UI ---

def refresh_ui(request: gr.Request):
    user_name = request.username
    return get_activities_df(user_name), gr.update(choices=get_activities_choices(user_name))

def check_plan_status(user_name):
    plan = get_weekly_plan(user_name)
    if plan:
        return gr.update(visible=False), gr.update(visible=True), render_plan_html(plan), ""
    else:
        return gr.update(visible=True), gr.update(visible=False), "", ""

def on_page_load(request: gr.Request):
    user_name = request.username
    df, choices_update = refresh_ui(request)
    welcome_msg = f"👤 **Bienvenido, {user_name}**"
    panel_upload, panel_view, plan_html, _ = check_plan_status(user_name)
    return welcome_msg, df, choices_update, panel_upload, panel_view, plan_html

def process_and_save_fit_ui(file_obj, request: gr.Request):
    user_name = request.username
    if not file_obj:
        return "<div class='alert alert-error'>Seleccione un archivo .FIT</div>", gr.update(), "", gr.update()
    
    file_path = file_obj.name
    filename = os.path.basename(file_path)
    session, laps, debug_info = parse_fit_file_safe(file_path)
    
    success, msg = insert_parsed_activity(user_name, filename, session, laps)
    if not success:
        return f"<div class='alert alert-error'>{msg}</div>", gr.update(), debug_info, gr.update()
    
    status_html = f'''
    <div class="alert alert-success">
        <h4>✅ Actividad Registrada</h4>
        <p>Distancia: <strong>{session.get('total_distance_km', 0)} km</strong> | 
           Tiempo: <strong>{session.get('total_duration_min', 0)} min</strong> | 
           Ritmo: <strong>{session.get('avg_pace', '-')}</strong></p>
    </div>
    '''
    df, choices_update = refresh_ui(request)
    return status_html, df, debug_info, choices_update

def get_activity_details_ui(evt: gr.SelectData, request: gr.Request):
    user_name = request.username
    row_idx = evt.index[0] if isinstance(evt.index, (list, tuple)) else evt.index
    df = get_activities_df(user_name)
    
    if df.empty or row_idx >= len(df):
        return gr.update(visible=False), pd.DataFrame(), "No hay datos.", None
        
    act_id = int(df.iloc[row_idx]['ID'])
    laps_df = get_laps_df(act_id)
    return gr.update(visible=True), laps_df, f"### Tramos de Actividad #{act_id}", act_id

def delete_activity_ui(act_id, request: gr.Request):
    if act_id:
        delete_activity(act_id)
    df, choices_update = refresh_ui(request)
    return df, gr.update(visible=False), choices_update, None

def export_json_ui(include_laps_chk, export_selection, request: gr.Request):
    user_name = request.username
    return export_json_for_ai(user_name, include_laps_chk, export_selection)

def save_plan_ui(json_str, request: gr.Request):
    user_name = request.username
    try:
        plan_dict = json.loads(json_str)
        save_weekly_plan(user_name, plan_dict)
        return check_plan_status(user_name)
    except json.JSONDecodeError:
        error_msg = "<div class='alert alert-error'>⚠️ Formato JSON no válido. Verifica las comillas y comas.</div>"
        return gr.update(visible=True), gr.update(visible=False), "", error_msg

def delete_plan_ui(request: gr.Request):
    user_name = request.username
    delete_weekly_plan(user_name)
    return check_plan_status(user_name)

# --- ESTILOS CSS AVANZADOS Y RESPONSIVOS ---

custom_css = '''
footer { display: none !important; }

:root {
    --primary-color: #fc4c02;
    --primary-hover: #e04300;
    --bg-card: #ffffff;
    --border-color: #e5e7eb;
}

body, .gradio-container {
    background-color: #f8fafc !important;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif !important;
}

/* Header principal */
.header-panel {
    background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
    padding: 24px 28px;
    border-radius: 16px;
    margin-bottom: 20px;
    color: white;
    box-shadow: 0 10px 25px -5px rgba(15, 23, 42, 0.15);
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 12px;
}

.header-title {
    margin: 0;
    font-weight: 800;
    font-size: 26px;
    letter-spacing: -0.5px;
    color: #ffffff;
}

/* Tarjetas y Contenedor del Plan */
.plan-container {
    display: flex;
    flex-direction: column;
    gap: 16px;
}

.plan-header-card {
    background: white;
    padding: 20px;
    border-radius: 16px;
    border: 1px solid var(--border-color);
    box-shadow: 0 4px 12px rgba(0,0,0,0.03);
}

.plan-header-info h2 {
    margin: 0;
    font-size: 1.3rem;
    font-weight: 700;
    color: #0f172a;
}

.plan-header-info p {
    margin: 6px 0 0 0;
    color: #64748b;
    font-size: 0.95rem;
}

.plan-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
    gap: 14px;
}

.day-card {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 14px;
    padding: 16px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.02);
    transition: transform 0.15s ease, box-shadow 0.15s ease;
}

.day-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 6px 16px rgba(0,0,0,0.06);
}

.day-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 10px;
}

.day-title {
    font-weight: 700;
    font-size: 1.05rem;
    color: #1e293b;
}

.workout-badge {
    font-size: 0.75rem;
    font-weight: 700;
    padding: 4px 12px;
    border-radius: 20px;
    text-transform: uppercase;
    letter-spacing: 0.3px;
}

.workout-details {
    margin: 0;
    color: #475569;
    font-size: 0.9rem;
    line-height: 1.45;
}

/* Alertas */
.alert {
    padding: 14px 18px;
    border-radius: 12px;
    margin-bottom: 12px;
}

.alert-success {
    background-color: #f0fdf4;
    border-left: 5px solid #22c55e;
    color: #15803d;
}

.alert-error {
    background-color: #fef2f2;
    border-left: 5px solid #ef4444;
    color: #b91c1c;
}

/* Ajustes Responsivos Móviles */
@media (max-width: 640px) {
    .header-panel {
        padding: 18px;
    }
    .header-title {
        font-size: 20px;
    }
    .plan-grid {
        grid-template-columns: 1fr;
    }
}
'''

with gr.Blocks(title="Sports Data Hub", css=custom_css) as app:
    selected_act_id = gr.State(None)
    
    gr.HTML('''
    <div class="header-panel">
        <div>
            <h1 class="header-title">⚡ Sports Data Hub</h1>
        </div>
    </div>
    ''')
    
    user_greeting = gr.Markdown("👤 Cargando usuario...")
    
    with gr.Tabs():
        
        with gr.TabItem("Plan Semanal"):
            with gr.Column(visible=True) as panel_upload_plan:
                gr.Markdown("### 📝 Define tu Plan Semanal")
                gr.Markdown("Introduce la estructura de entrenamientos en JSON para generar tus tarjetas de visualización.")
                plan_input = gr.Code(label="Código JSON del Plan", language="json", value=PLAN_TEMPLATE, lines=12)
                btn_save_plan = gr.Button("💾 Guardar y Visualizar Plan", variant="primary")
                plan_error_msg = gr.HTML("")

            with gr.Column(visible=False) as panel_view_plan:
                plan_display_html = gr.HTML("")
                gr.Markdown("---")
                btn_delete_plan = gr.Button("🗑️ Reiniciar / Borrar Plan Semanal", variant="stop")
                
        with gr.TabItem("Carga Manual (.FIT)"):
            with gr.Row():
                with gr.Column(scale=1):
                    fit_input = gr.File(label="Seleccionar archivo .FIT", file_types=[".fit"])
                    btn_upload = gr.Button("Procesar Archivo", variant="primary")
                with gr.Column(scale=1):
                    upload_output = gr.HTML(value="<div style='padding:20px; text-align:center; color:#94a3b8;'>Esperando archivo...</div>")
            
            with gr.Accordion("Registro de Diagnóstico (Debug)", open=False):
                debug_output = gr.Textbox(label="Log de procesamiento", interactive=False, lines=8)

        with gr.TabItem("Análisis e Historial"):
            with gr.Row():
                with gr.Column(scale=2):
                    activities_table = gr.DataFrame(label="Registro Histórico", interactive=False)
                with gr.Column(scale=1):
                    detail_panel = gr.Group(visible=False)
                    with detail_panel:
                        detail_title = gr.Markdown("### Desglose de Tramos")
                        laps_table = gr.DataFrame(label="Métricas por Tramo", interactive=False)
                        btn_delete = gr.Button("🗑️ Eliminar Actividad", variant="stop")

        with gr.TabItem("Exportación de Datos"):
            export_selection = gr.CheckboxGroup(label="Selecciona las actividades a exportar")
            include_laps_chk = gr.Checkbox(label="Incluir métricas detalladas por tramo", value=True)
            btn_export = gr.Button("Generar Exportación JSON", variant="primary")
            json_output = gr.Code(label="Dataset Resultante", language="json")
    
    # Carga inicial y eventos
    app.load(fn=on_page_load, inputs=None, outputs=[user_greeting, activities_table, export_selection, panel_upload_plan, panel_view_plan, plan_display_html])
    btn_save_plan.click(fn=save_plan_ui, inputs=[plan_input], outputs=[panel_upload_plan, panel_view_plan, plan_display_html, plan_error_msg])
    btn_delete_plan.click(fn=delete_plan_ui, inputs=None, outputs=[panel_upload_plan, panel_view_plan, plan_display_html, plan_error_msg])
    btn_upload.click(fn=process_and_save_fit_ui, inputs=[fit_input], outputs=[upload_output, activities_table, debug_output, export_selection])
    activities_table.select(fn=get_activity_details_ui, inputs=None, outputs=[detail_panel, laps_table, detail_title, selected_act_id])
    btn_delete.click(fn=delete_activity_ui, inputs=[selected_act_id], outputs=[activities_table, detail_panel, export_selection, selected_act_id])
    btn_export.click(fn=export_json_ui, inputs=[include_laps_chk, export_selection], outputs=[json_output])

if __name__ == "__main__":
    launch_telegram_bot()
    port = int(os.environ.get("PORT", 7860))
    
    USUARIOS = [
        ("Gonzalo", "1234"),
        ("Gay", "0000")
    ]
    
    app.launch(server_name="0.0.0.0", server_port=port, css=custom_css, auth=USUARIOS)