"""
Training Job Manager - Deprecated
This module previously provided a unified interface for creating training jobs,
but Lightning AI and Vertex AI implementations have been removed.
Training should now be done directly using Vast AI or local execution.
"""

import logging

logger = logging.getLogger(__name__)

# All training backend implementations have been removed
BACKEND_AVAILABLE = False
BACKEND_NAME = None
TRAINING_BACKEND = None

logger.warning(
    "Training job manager is deprecated. Lightning AI and Vertex AI implementations "
    "have been removed. Use Vast AI or run training locally."
)

# Export empty functions for compatibility (will raise errors if called)
def _not_implemented(*args, **kwargs):
    raise NotImplementedError(
        "Training job submission is not available. Lightning AI and Vertex AI "
        "implementations have been removed. Use Vast AI or run training locally."
    )

create_training_job = _not_implemented
create_training_job_quick = _not_implemented
get_available_machine_configs = _not_implemented
build_environment_variables = _not_implemented
check_quota_availability = _not_implemented
get_blacklisted_machines = _not_implemented
add_to_blacklist = _not_implemented
calculate_job_cost = _not_implemented
wait_for_job = _not_implemented
create_instance = _not_implemented

# Export all functions for easy import
__all__ = [
    'create_training_job',
    'create_training_job_quick',
    'get_available_machine_configs',
    'build_environment_variables',
    'check_quota_availability',
    'get_blacklisted_machines',
    'add_to_blacklist',
    'calculate_job_cost',
    'wait_for_job',
    'create_instance',
    'BACKEND_AVAILABLE',
    'BACKEND_NAME',
    'TRAINING_BACKEND'
]


