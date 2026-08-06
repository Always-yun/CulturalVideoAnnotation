import os
import json
import time
from datetime import datetime
from typing import Dict, Any


class ExperimentLogger:
    def __init__(self, experiment_id: str):
        self.experiment_id = experiment_id
        self.log_dir = os.path.join("experiments/logs/", experiment_id)
        os.makedirs(self.log_dir, exist_ok=True)
        
        self.start_time = datetime.now()
        self.log_entries = []
    
    def log(self, message: str, level: str = "INFO", **kwargs):
        entry = {
            "timestamp": datetime.now().isoformat(),
            "level": level,
            "message": message,
            **kwargs
        }
        self.log_entries.append(entry)
        
        log_file = os.path.join(self.log_dir, f"{self.experiment_id}.log")
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    
    def log_metrics(self, metrics: Dict[str, float], step: int = 0):
        self.log("metrics", level="METRIC", step=step, metrics=metrics)
    
    def log_config(self, config: Dict[str, Any]):
        self.log("experiment_config", level="CONFIG", config=config)
        
        config_file = os.path.join(self.log_dir, f"{self.experiment_id}_config.json")
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
    
    def finalize(self):
        end_time = datetime.now()
        duration = (end_time - self.start_time).total_seconds()
        
        self.log("experiment_completed", level="INFO", 
                 duration_seconds=duration,
                 start_time=self.start_time.isoformat(),
                 end_time=end_time.isoformat())
        
        summary_file = os.path.join(self.log_dir, f"{self.experiment_id}_summary.json")
        with open(summary_file, "w", encoding="utf-8") as f:
            json.dump({
                "experiment_id": self.experiment_id,
                "start_time": self.start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "duration_seconds": duration,
                "total_entries": len(self.log_entries)
            }, f, indent=2, ensure_ascii=False)