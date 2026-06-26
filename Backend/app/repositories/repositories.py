from sqlalchemy.orm import Session
from sqlalchemy import select, func, or_, delete
from app.models.models import LogFile, Log
from app.schemas.schemas import LogFileCreate, LogFileUpdate, LogCreate
from datetime import datetime
from typing import List, Optional, Dict, Any

class LogFileRepository:
    def get(self, db: Session, file_id: int) -> Optional[LogFile]:
        return db.scalar(select(LogFile).where(LogFile.id == file_id))

    def get_by_path(self, db: Session, file_path: str) -> Optional[LogFile]:
        return db.scalar(select(LogFile).where(LogFile.file_path == file_path))

    def get_all(self, db: Session) -> List[LogFile]:
        return list(db.scalars(select(LogFile).order_by(LogFile.updated_at.desc())).all())

    def create(self, db: Session, obj_in: LogFileCreate) -> LogFile:
        db_obj = LogFile(
            file_name=obj_in.file_name,
            file_path=obj_in.file_path,
            service_name=obj_in.service_name,
            last_processed_position=obj_in.last_processed_position,
            status=obj_in.status
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def update(self, db: Session, db_obj: LogFile, obj_in: LogFileUpdate) -> LogFile:
        update_data = obj_in.model_dump(exclude_unset=True)
        for field in update_data:
            setattr(db_obj, field, update_data[field])
        db_obj.updated_at = func.now()
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

class LogRepository:
    def get(self, db: Session, log_id: int) -> Optional[Log]:
        return db.scalar(select(Log).where(Log.id == log_id))

    def get_all(
        self,
        db: Session,
        *,
        skip: int = 0,
        limit: int = 100,
        service_name: Optional[str] = None,
        log_level: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        search_query: Optional[str] = None
    ) -> List[Log]:
        query = select(Log)
        
        if service_name:
            query = query.where(Log.service_name == service_name)
        if log_level:
            query = query.where(Log.log_level == log_level)
        if start_date:
            query = query.where(Log.timestamp >= start_date)
        if end_date:
            query = query.where(Log.timestamp <= end_date)
        if search_query:
            query = query.where(
                or_(
                    Log.message.ilike(f"%{search_query}%"),
                    Log.stacktrace.ilike(f"%{search_query}%")
                )
            )

        query = query.order_by(Log.timestamp.desc()).offset(skip).limit(limit)
        return list(db.scalars(query).all())

    def create(self, db: Session, obj_in: LogCreate) -> Log:
        db_obj = Log(
            timestamp=obj_in.timestamp,
            service_name=obj_in.service_name,
            log_level=obj_in.log_level,
            message=obj_in.message,
            stacktrace=obj_in.stacktrace,
            file_name=obj_in.file_name,
            file_path=obj_in.file_path
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def create_many(self, db: Session, obj_ins: List[LogCreate]) -> List[Log]:
        db_objs = [
            Log(
                timestamp=obj.timestamp,
                service_name=obj.service_name,
                log_level=obj.log_level,
                message=obj.message,
                stacktrace=obj.stacktrace,
                file_name=obj.file_name,
                file_path=obj.file_path
            )
            for obj in obj_ins
        ]
        db.add_all(db_objs)
        db.commit()
        # Skip refreshing to avoid 10,000+ sequential SELECT queries on SQLite
        return db_objs

    def delete_by_path(self, db: Session, file_path: str) -> None:
        db.execute(delete(Log).where(Log.file_path == file_path))
        db.commit()

    def get_stats_summary(self, db: Session) -> Dict[str, int]:
        total_logs = db.scalar(select(func.count(Log.id))) or 0
        error_logs = db.scalar(select(func.count(Log.id)).where(Log.log_level == "ERROR")) or 0
        warning_logs = db.scalar(select(func.count(Log.id)).where(Log.log_level == "WARNING")) or 0
        services = db.scalar(select(func.count(func.distinct(Log.service_name)))) or 0
        
        return {
            "total_logs": total_logs,
            "error_logs": error_logs,
            "warning_logs": warning_logs,
            "services": services
        }

log_file_repo = LogFileRepository()
log_repo = LogRepository()
