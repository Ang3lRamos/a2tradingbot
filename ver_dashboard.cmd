@echo off
rem Abre el dashboard en el navegador. Cerrar esta ventana lo detiene.
cd /d "%~dp0"
start "" http://localhost:8501
.venv\Scripts\streamlit run dashboard\app.py --server.headless true --server.port 8501
