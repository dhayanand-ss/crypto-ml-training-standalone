
import mlflow
from mlflow.tracking import MlflowClient
client = MlflowClient(tracking_uri='http://localhost:5001')
for v in client.search_model_versions('name="dummy_model"'):
    print(f'{v.name} v{v.version} ({v.current_stage})')
