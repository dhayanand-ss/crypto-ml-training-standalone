import sys
import os
from pathlib import Path

# ---------------------------
# Add project root to sys.path so utils can be imported
# ---------------------------
# In Docker: DAGs are at /opt/airflow/dags, utils at /opt/airflow/utils
# In local: DAGs are at ./dags, utils at ./utils (parent of dags)
_dag_file = Path(__file__).resolve()

# Check if we're in Docker (utils mounted at /opt/airflow/utils or /opt/airflow/project/utils)
docker_utils = Path("/opt/airflow/utils")
docker_project_utils = Path("/opt/airflow/project/utils")
if docker_utils.exists():
    project_root = Path("/opt/airflow")
elif docker_project_utils.exists():
    project_root = Path("/opt/airflow/project")
else:
    # Local development: parent of dags directory
    project_root = _dag_file.parent.parent
    # Verify utils exists
    if not (project_root / "utils").exists():
        # Try current working directory
        cwd = Path(os.getcwd())
        if (cwd / "utils").exists():
            project_root = cwd
        else:
            # Try parent of cwd
            parent = cwd.parent
            if (parent / "utils").exists():
                project_root = parent

# Ensure absolute path
project_root = project_root.resolve()

# Add to sys.path if not already there
project_root_str = str(project_root)
if project_root_str not in sys.path:
    sys.path.insert(0, project_root_str)

def airflow_execution_info():
    print("===== AIRFLOW EXECUTION INFO =====")
    print(f"__file__          : {__file__}")          # Path to this DAG file
    print(f"__name__          : {__name__}")          # Module name
    print(f"Current working dir: {os.getcwd()}")     # cwd at execution
    print(f"Project root: {project_root}")
    print(f"sys.path:")                              
    for p in sys.path:                              
        print(f"  {p}")
    print("=================================")

airflow_execution_info()

# Now import Airflow and other dependencies
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.timezone import datetime
from airflow.models import TaskInstance

# Import project modules (after path setup)
from utils.database.status_db import status_db

def log_start(context):
    ti: TaskInstance = context['ti']
    task_id = ti.task_id
    model_name = "N/A"
    if task_id.startswith("train_"):
        model_name = task_id.replace("train_", "")
    status_db.log_event(
        dag_name=ti.dag_id,
        task_name=ti.task_id,
        model_name=model_name,  # optional
        run_id=ti.run_id,
        event_type="START",
        status="RUNNING",
        message="Task started."
    )

def log_success(context):
    ti: TaskInstance = context['ti']
    task_id = ti.task_id
    model_name = "N/A"
    if task_id.startswith("train_"):
        model_name = task_id.replace("train_", "")
    status_db.log_event(
        dag_name=ti.dag_id,
        task_name=ti.task_id,
        model_name=model_name,  # optional
        run_id=ti.run_id,
        event_type="COMPLETE",
        status="SUCCESS",
        message="Task completed successfully."
    )

def log_failure(context):
    ti: TaskInstance = context['ti']
    task_id = ti.task_id
    model_name = "N/A"
    if task_id.startswith("train_"):
        model_name = task_id.replace("train_", "")
    status_db.log_event(
        dag_name=ti.dag_id,
        task_name=ti.task_id,
        model_name=model_name,  # optional
        run_id=ti.run_id,
        event_type="COMPLETE",
        status="FAILED",
        message=str(context.get("exception"))
    )

def cleanup():
    status_db.cleanup_old_events()

with DAG(
    "cleanup_old_events",
    schedule="0 0 * * *",  # daily
    start_date=datetime(2024, 1, 1),
    catchup=False,
) as dag:
    cleanup_task = PythonOperator(
        task_id="cleanup_old_events",
        python_callable=cleanup,
        on_execute_callback=log_start,
        on_success_callback=log_success,
        on_failure_callback=log_failure,
    )