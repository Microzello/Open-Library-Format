"""Background job scheduler."""
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime
from pathlib import Path
from typing import Dict

from app.db.registry_db import RegistryDB
from app.db.library_db import LibraryDB
from app.services.reconcilers import ReconcilerService

logger = logging.getLogger(__name__)


class SchedulerService:
    """Manages background jobs."""

    def __init__(self, registry_db: RegistryDB):
        self.registry_db = registry_db
        self.scheduler = BackgroundScheduler()

    def start(self):
        """Start the scheduler."""
        # Daily reconciliation at 2 AM UTC
        self.scheduler.add_job(
            self.run_daily_reconciliation,
            trigger=CronTrigger(hour=2, minute=0),
            id="daily_reconciliation",
            name="Daily library reconciliation",
            replace_existing=True,
        )

        # Daily WAL checkpoint at 3 AM UTC
        self.scheduler.add_job(
            self.run_wal_checkpoint,
            trigger=CronTrigger(hour=3, minute=0),
            id="wal_checkpoint",
            name="WAL checkpoint",
            replace_existing=True,
        )

        self.scheduler.start()
        logger.info("Background scheduler started")

    def shutdown(self):
        """Shutdown the scheduler."""
        self.scheduler.shutdown()
        logger.info("Background scheduler shut down")

    def run_daily_reconciliation(self):
        """Run reconciliation on all libraries."""
        logger.info("Starting daily reconciliation")
        
        libraries = self.registry_db.list_libraries()
        for lib in libraries:
            try:
                lib_path = Path(lib["path"])
                if not lib_path.exists():
                    logger.warning(f"Library path not found: {lib_path}")
                    continue

                lib_db = LibraryDB(str(lib_path))
                reconciler = ReconcilerService(lib_db, lib_path)
                
                report = reconciler.reconcile()
                
                # Log report
                log_file = Path("var") / f"reconcile_{lib['slug']}_{datetime.now().strftime('%Y%m%d')}.log"
                log_file.parent.mkdir(parents=True, exist_ok=True)
                
                with open(log_file, "w") as f:
                    f.write(f"Reconciliation report for {lib['name']}\n")
                    f.write(f"Date: {datetime.now().isoformat()}\n\n")
                    f.write(f"Missing files: {len(report['missing_files'])}\n")
                    f.write(f"Orphaned files: {len(report['orphaned_files'])}\n")
                    f.write(f"Integrity errors: {len(report['integrity_errors'])}\n")
                    f.write(f"Orphaned tag refs: {report['orphaned_tag_refs']}\n\n")
                    
                    if report['missing_files']:
                        f.write("Missing files:\n")
                        for sha in report['missing_files']:
                            f.write(f"  {sha}\n")
                    
                    if report['integrity_errors']:
                        f.write("\nIntegrity errors:\n")
                        for err in report['integrity_errors']:
                            f.write(f"  File {err['file_id']}: expected {err['expected']}, got {err['actual']}\n")
                
                logger.info(f"Reconciliation complete for {lib['slug']}: {report}")
                
            except Exception as e:
                logger.error(f"Reconciliation failed for {lib['slug']}: {e}")

    def run_wal_checkpoint(self):
        """Checkpoint WAL files for all libraries."""
        logger.info("Starting WAL checkpoint")
        
        libraries = self.registry_db.list_libraries()
        for lib in libraries:
            try:
                lib_path = Path(lib["path"])
                if not lib_path.exists():
                    continue

                lib_db = LibraryDB(str(lib_path))
                lib_db.checkpoint_wal()
                
                logger.info(f"WAL checkpointed for {lib['slug']}")
                
            except Exception as e:
                logger.error(f"WAL checkpoint failed for {lib['slug']}: {e}")

    def queue_thumbnail(self, library_slug: str, sha256: str, mime: str):
        """Queue a thumbnail generation job."""
        # For MVP, we'll generate synchronously
        # In production, use a proper job queue like Celery or RQ
        pass

