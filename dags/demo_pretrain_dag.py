"""
DEMO DAG: Only pre_train_dataset

This is a standalone demo DAG to validate pre_train_dataset and GCS access.
It is independent from other DAGs and can be triggered manually.
"""

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

# Now import Airflow
from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.utils.timezone import datetime
from datetime import timedelta

# ---------------------------------------------------
# DEMO DAG: Only pre_train_dataset
# ---------------------------------------------------
with DAG(
    dag_id="demo_pre_train_dataset",
    description="Demo DAG to validate pre_train_dataset and GCS access",
    start_date=datetime(2024, 1, 1),
    schedule=None,              # Manual trigger only
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=timedelta(minutes=15),
) as dag:

    pre_train_dataset = BashOperator(
        task_id="pre_train_dataset",
        bash_command=f"""
        set -e  # Exit on error
        
        echo "========================================"
        echo "===== DEMO DAG: PRE-TRAIN DATASET ====="
        echo "========================================"
        echo ""
        
        # Set environment
        export PYTHONPATH={project_root_str}:$PYTHONPATH
        export DATA_PATH={project_root_str}/data
        
        echo "===== ENVIRONMENT SETUP ====="
        echo "PWD=$(pwd)"
        echo "Project root: {project_root_str}"
        echo "DATA_PATH: $DATA_PATH"
        echo "PYTHONPATH: $PYTHONPATH"
        echo ""
        
        # Change to project root
        cd {project_root_str}
        echo "Changed to: $(pwd)"
        echo ""
        
        # Verify directory structure
        echo "===== DIRECTORY VERIFICATION ====="
        echo "Checking project structure..."
        [ -d "{project_root_str}/utils" ] && echo "✓ utils/ exists" || echo "✗ utils/ MISSING"
        [ -d "{project_root_str}/trainer" ] && echo "✓ trainer/ exists" || echo "✗ trainer/ MISSING"
        [ -d "{project_root_str}/data" ] && echo "✓ data/ exists" || echo "✗ data/ MISSING"
        echo ""
        
        # Python path verification
        echo "===== PYTHON IMPORT VERIFICATION ====="
        python3 << PYTHON_VERIFY_EOF
import sys
import os
from pathlib import Path

project_root = "{project_root_str}"

print("Python sys.path:")
for p in sys.path:
    print("  " + str(p))

print("")
print("Project root: " + str(project_root))
print("")
print("Checking imports...")
print("")

# Check trainer module
trainer_available = False
try:
    import trainer
    print("✓ trainer module found at: " + str(trainer.__file__))
    try:
        from trainer.train_utils import download_s3_dataset, S3_AVAILABLE
        print("✓ download_s3_dataset imported successfully")
        print("✓ S3_AVAILABLE = " + str(S3_AVAILABLE))
        trainer_available = True
    except ImportError as e:
        print("✗ Failed to import from trainer.train_utils: " + str(e))
        trainer_available = False
except ImportError as e:
    print("✗ Failed to import trainer module: " + str(e))
    trainer_path = Path(project_root) / "trainer"
    print("  Looking for trainer at: " + str(trainer_path))
    if trainer_path.exists():
        print("  → Directory exists but not importable")
        init_file = trainer_path / "__init__.py"
        if init_file.exists():
            print("  → __init__.py exists, but module still not importable")
        else:
            print("  → __init__.py MISSING!")
    else:
        print("  → Directory does not exist at: " + str(trainer_path))
    trainer_available = False

# Check utils module
utils_available = False
try:
    import utils
    print("✓ utils module found at: " + str(utils.__file__))
    try:
        from utils.utils.pre_train_dataset import main
        print("✓ pre_train_dataset module imported successfully")
        utils_available = True
    except ImportError as e:
        print("✗ Failed to import pre_train_dataset: " + str(e))
        utils_available = False
except ImportError as e:
    print("✗ Failed to import utils module: " + str(e))
    utils_available = False

print("")
if not trainer_available:
    print("=" * 60)
    print("CRITICAL: trainer module is NOT available")
    print("=" * 60)
    print("This means GCS download will be disabled.")
    print("The pre_train_dataset script will FAIL if GCS is required.")
    print("")
    print("SOLUTION: Ensure trainer/ directory exists at:")
    print("  " + str(Path(project_root) / "trainer"))
    print("=" * 60)
    sys.exit(1)

if not utils_available:
    print("=" * 60)
    print("CRITICAL: utils module is NOT available")
    print("=" * 60)
    sys.exit(1)

print("✓ All imports verified successfully!")
PYTHON_VERIFY_EOF

        if [ $? -ne 0 ]; then
            echo ""
            echo "========================================"
            echo "✗ IMPORT VERIFICATION FAILED"
            echo "========================================"
            echo "The DAG cannot proceed without proper imports."
            echo "Check the errors above and fix the module structure."
            exit 1
        fi
        
        echo ""
        echo "===== RUNNING PRE-TRAIN DATASET ====="
        echo ""
        
        # Run the actual script
        python3 -m utils.utils.pre_train_dataset
        
        echo ""
        echo "========================================"
        echo "✓ PRE-TRAIN DATASET COMPLETED"
        echo "========================================"
        """,
    )

    pre_train_dataset

