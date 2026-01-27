"""
Job handler that watches for job files and launches producer/consumer processes.
"""

import os
import sys
import time
import subprocess
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.producer_consumer.consumer_utils import delete_state
from utils.producer_consumer.logger import setup_logger

# Configuration
JOBS_DIR = os.getenv("JOBS_DIR", "/opt/airflow/custom_persistent_shared/jobs")

# Setup logger
logger = setup_logger("job_handler")


class JobHandler(FileSystemEventHandler):
    """Handler for watching job files."""
    
    def __init__(self):
        self.processes = {}
    
    def on_created(self, event):
        """Handle new job file creation."""
        if event.is_directory:
            return
        
        if not event.src_path.endswith('.sh'):
            return
        
        logger.info(f"New job file detected: {event.src_path}")
        
        # Parse filename: {crypto}_{model}_{version}.sh
        filename = os.path.basename(event.src_path)
        parts = filename.replace('.sh', '').split('_')
        
        if len(parts) < 3:
            logger.warning(f"Invalid job file name format: {filename}")
            return
        
        # Determine if it's a producer or consumer
        if parts[0] == "ALL" and parts[1] == "producer":
            # Producer job
            logger.info("Launching producer process")
            self.launch_process(event.src_path, "producer")
        else:
            # Consumer job
            crypto = parts[0]
            model = parts[1]
            version = parts[2]
            
            logger.info(f"Launching consumer process: {crypto} {model} {version}")
            self.launch_process(event.src_path, "consumer", crypto, model, version)
        
        # Remove job file after launching
        try:
            os.remove(event.src_path)
            logger.info(f"Removed job file: {event.src_path}")
        except Exception as e:
            logger.error(f"Error removing job file: {e}")
    
    def launch_process(self, job_file: str, process_type: str, crypto: str = None, model: str = None, version: str = None):
        """
        Launch a producer or consumer process.
        
        Args:
            job_file: Path to job file
            process_type: "producer" or "consumer"
            crypto: Cryptocurrency symbol (for consumer)
            model: Model name (for consumer)
            version: Model version (for consumer)
        """
        # Read job file to get command
        try:
            with open(job_file, 'r') as f:
                command = f.read().strip()
            
            # Remove shebang if present
            if command.startswith('#!/bin/bash'):
                lines = command.split('\n')
                command = '\n'.join(lines[1:]).strip()
            
            # Parse command
            if 'producer' in command:
                # Producer command
                logger.info(f"Executing producer command: {command}")
                process = subprocess.Popen(
                    command,
                    shell=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True
                )
                self.processes[f"producer"] = process
                logger.info(f"Launched producer process (PID: {process.pid})")
            
            elif 'consumer' in command:
                # Consumer command
                # Delete existing state file before launching
                if crypto and model and version:
                    delete_state(crypto, model, version)
                
                logger.info(f"Executing consumer command: {command}")
                process = subprocess.Popen(
                    command,
                    shell=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True
                )
                process_key = f"{crypto}_{model}_{version}" if crypto else "consumer"
                self.processes[process_key] = process
                logger.info(f"Launched consumer process (PID: {process.pid})")
            
            else:
                logger.warning(f"Unknown command type in job file: {command}")
        
        except Exception as e:
            logger.error(f"Error launching process from job file {job_file}: {e}")


def main():
    """Main job handler loop."""
    logger.info("Starting job handler")
    logger.info(f"Watching directory: {JOBS_DIR}")
    
    # Ensure jobs directory exists
    Path(JOBS_DIR).mkdir(parents=True, exist_ok=True)
    
    # Set permissions
    try:
        os.chmod(JOBS_DIR, 0o777)
    except Exception:
        pass  # Ignore permission errors on Windows
    
    # Create event handler
    event_handler = JobHandler()
    
    # Create observer
    observer = Observer()
    observer.schedule(event_handler, JOBS_DIR, recursive=False)
    observer.start()
    
    logger.info("Job handler started, watching for job files...")
    
    try:
        # Process existing job files
        for filename in os.listdir(JOBS_DIR):
            if filename.endswith('.sh'):
                filepath = os.path.join(JOBS_DIR, filename)
                event_handler.on_created(type('Event', (), {'src_path': filepath, 'is_directory': False})())
        
        # Keep running
        while True:
            time.sleep(1)
    
    except KeyboardInterrupt:
        logger.info("Received interrupt signal, shutting down...")
        observer.stop()
    
    observer.join()
    logger.info("Job handler stopped")


if __name__ == "__main__":
    main()







