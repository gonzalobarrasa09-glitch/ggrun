import os
import gradio as gr
import pandas as pd
from database import init_db, get_user_list, get_activities_df, get_laps_df, insert_parsed_activity, export_json_for_ai
from fit_parser import parse_fit_file_safe

init_db()

def process_and_save_fit(user_name, file_obj):
    if not file_obj:
        return "<div style='color: #d32f2f;'>Seleccione un archivo.</div>", gr.update(), ""
    
    file_path = file_obj.name
    filename = os.path.basename(file_path)
    session, laps, debug_info = parse_fit_file_safe(file_path)
    
    success, msg = insert_parsed_activity(user_name, filename, session, laps)
    if not success:
        return f"<div style='color: #d32f2f;'>{msg}</div>", gr.update(), debug_info
    
    status_html = f'''
    <div style="padding: 15px; border-left: 4px solid #4caf50; background-color: #f1f8e9; color: #2e7d32;">
        <h4 style="margin: 0 0 10px 0;">Actividad registrada correctamente</h4>
        <p>Distancia: {session['total_distance_km']} km | Tiempo: {session['total_duration_min']} min | Ritmo: {session['avg_pace']}</p>
    </div>
    '''
    return status_html, get_activities_df(user_name), debug_info

def get_activity_details(evt: gr.SelectData, user_name):
    row_idx = evt.index[0] if isinstance(evt.index, (list, tuple)) else evt.index
    df = get_activities_df(user_name)
    
    if df.empty or row_idx >= len(df):
        return gr.update(visible=False), pd.DataFrame(), "No hay datos."
        
    act_id = int(df.iloc[row_idx]['ID'])
    laps_df = get_laps_df(act_id)
    return gr.update(visible=True), laps_df, f"### Desglose de Tramos (Actividad #{act_id})"

custom_css = '''
footer {display: none !important;}
.header-panel { padding: 20px 24px; border-bottom: 1px solid #e2e8f0; margin-bottom: 24px; background-color: #f8fafc; }
.header-title { margin: 0; font-weight: 600; font-size: 24px; color: #0f172a; }
'''

with gr.Blocks(title="Sports Data Hub") as app:
    gr.HTML('''
    <div class="header-panel">
        <h1 class="header-title">Plataforma de Análisis de Datos Deportivos</h1>
    </div>
    ''')
    
    with gr.Row():
        user_select = gr.Dropdown(choices=get_user_list(), value="Gonzalo", label="Usuario Activo", interactive=True)
    
    with gr.Tabs():
        with gr.TabItem("Carga de Datos"):
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
                    activities_table = gr.DataFrame(value=get_activities_df("Gonzalo"), label="Registro Histórico", interactive=False)
                with gr.Column(scale=1):
                    detail_panel = gr.Group(visible=False)
                    with detail_panel:
                        detail_title = gr.Markdown("### Desglose de Tramos")
                        laps_table = gr.DataFrame(label="Métricas por Tramo", interactive=False)

        with gr.TabItem("Exportación de Datos"):
            include_laps_chk = gr.Checkbox(label="Incluir métricas detalladas por tramo", value=True)
            btn_export = gr.Button("Generar Exportación JSON", variant="primary")
            json_output = gr.Code(label="Dataset Resultante", language="json")
    
    btn_upload.click(fn=process_and_save_fit, inputs=[user_select, fit_input], outputs=[upload_output, activities_table, debug_output])
    user_select.change(fn=get_activities_df, inputs=[user_select], outputs=[activities_table])
    activities_table.select(fn=get_activity_details, inputs=[user_select], outputs=[detail_panel, laps_table, detail_title])
    btn_export.click(fn=export_json_for_ai, inputs=[user_select, include_laps_chk], outputs=[json_output])

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    app.launch(server_name="0.0.0.0", server_port=port, css=custom_css)