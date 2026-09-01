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
  "semana": "Ejemplo: Del 1 al 7 de Septiembre",
  "objetivo": "Ejemplo: Base aeróbica",
  "entrenamientos": [
    { "dia": "Lunes", "tipo": "Descanso", "detalles": "Descanso total" },
    { "dia": "Martes", "tipo": "Series", "detalles": "15' Z1 + 8x400m + 10' Z1" },
    { "dia": "Miércoles", "tipo": "Rodaje", "detalles": "45' a ritmo suave" },
    { "dia": "Jueves", "tipo": "Fuerza", "detalles": "Gimnasio" },
    { "dia": "Viernes", "tipo": "Descanso", "detalles": "Libre" },
    { "dia": "Sábado", "tipo": "Tirada Larga", "detalles": "90' suaves" },
    { "dia": "Domingo", "tipo": "Rodaje", "detalles": "Bici 1h30m" }
  ]
}"""

# --- FUNCIONES DE LÓGICA Y UI ---

def refresh_ui(request: gr.Request):
    user_name = request.username
    return get_activities_df(user_name), gr.update(choices=get_activities_choices(user_name))

def check_plan_status(user_name):
    plan = get_weekly_plan(user_name)
    if plan:
        return gr.update(visible=False), gr.update(visible=True), plan, ""
    else:
        return gr.update(visible=True), gr.update(visible=False), None, ""

def on_page_load(request: gr.Request):
    user_name = request.username
    df, choices_update = refresh_ui(request)
    welcome_msg = f"👤 **Bienvenido/a, {user_name}** - Tu espacio personal de entrenamiento."
    panel_upload, panel_view, plan_data, _ = check_plan_status(user_name)
    return welcome_msg, df, choices_update, panel_upload, panel_view, plan_data

def process_and_save_fit_ui(file_obj, request: gr.Request):
    user_name = request.username
    if not file_obj:
        return "<div style='color: #d32f2f;'>Seleccione un archivo.</div>", gr.update(), "", gr.update()
    
    file_path = file_obj.name
    filename = os.path.basename(file_path)
    session, laps, debug_info = parse_fit_file_safe(file_path)
    
    success, msg = insert_parsed_activity(user_name, filename, session, laps)
    if not success:
        return f"<div style='color: #d32f2f;'>{msg}</div>", gr.update(), debug_info, gr.update()
    
    status_html = f'''
    <div style="padding: 15px; border-left: 4px solid #4caf50; background-color: #f1f8e9; color: #2e7d32;">
        <h4 style="margin: 0 0 10px 0;">Actividad registrada correctamente</h4>
        <p>Distancia: {session.get('total_distance_km', 0)} km | Tiempo: {session.get('total_duration_min', 0)} min | Ritmo: {session.get('avg_pace', '')}</p>
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
    return gr.update(visible=True), laps_df, f"### Desglose de Tramos (Actividad #{act_id})", act_id

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
        error_msg = "<span style='color:red;'>⚠️ Error: El formato JSON no es válido. Comprueba las comillas o comas.</span>"
        return gr.update(visible=True), gr.update(visible=False), None, error_msg

def delete_plan_ui(request: gr.Request):
    user_name = request.username
    delete_weekly_plan(user_name)
    return check_plan_status(user_name)

# --- INTERFAZ GRÁFICA ---

custom_css = '''
footer {display: none !important;}
.header-panel { padding: 20px 24px; border-bottom: 1px solid #e2e8f0; margin-bottom: 24px; background-color: #f8fafc; }
.header-title { margin: 0; font-weight: 600; font-size: 24px; color: #0f172a; }
'''

with gr.Blocks(title="Sports Data Hub", css=custom_css) as app:
    selected_act_id = gr.State(None)
    
    gr.HTML('''
    <div class="header-panel">
        <h1 class="header-title">Plataforma de Análisis de Datos Deportivos</h1>
    </div>
    ''')
    
    user_greeting = gr.Markdown("👤 Cargando usuario...")
    
    with gr.Tabs():
        
        with gr.TabItem("Plan Semanal"):
            with gr.Column(visible=True) as panel_upload_plan:
                gr.Markdown("### Sube tu plan de entrenamiento de la semana")
                gr.Markdown("Pega tu planificación en formato JSON en la caja de abajo y haz clic en Guardar.")
                plan_input = gr.Code(label="Código JSON del Plan", language="json", value=PLAN_TEMPLATE, lines=15)
                btn_save_plan = gr.Button("💾 Guardar Plan Semanal", variant="primary")
                plan_error_msg = gr.HTML("")

            with gr.Column(visible=False) as panel_view_plan:
                gr.Markdown("### 📋 Tu Entrenamiento para esta semana")
                plan_display = gr.JSON(label="Plan Semanal Activo")
                gr.Markdown("---")
                btn_delete_plan = gr.Button("🗑️ Finalizar Semana (Borrar Plan)", variant="stop")
                
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
    
    app.load(fn=on_page_load, inputs=None, outputs=[user_greeting, activities_table, export_selection, panel_upload_plan, panel_view_plan, plan_display])
    btn_save_plan.click(fn=save_plan_ui, inputs=[plan_input], outputs=[panel_upload_plan, panel_view_plan, plan_display, plan_error_msg])
    btn_delete_plan.click(fn=delete_plan_ui, inputs=None, outputs=[panel_upload_plan, panel_view_plan, plan_display, plan_error_msg])
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