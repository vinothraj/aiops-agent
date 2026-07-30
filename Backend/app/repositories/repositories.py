from sqlalchemy.orm import Session, selectinload
from sqlalchemy import select, func, or_, delete, case
import os
from app.models.models import LogFile, Log, MonitoredSourceRoot, LogAnalysis, AppSetting
from app.schemas.schemas import LogFileCreate, LogFileUpdate, LogCreate, MonitoredSourceRootCreate
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
            instance_id=obj_in.instance_id,
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

    @staticmethod
    def _apply_filters(
        query,
        *,
        service_name: Optional[str] = None,
        instance_id: Optional[str] = None,
        log_level: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        search_query: Optional[str] = None
    ):
        if service_name:
            query = query.where(Log.service_name == service_name)
        if instance_id:
            query = query.where(Log.instance_id == instance_id)
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
        return query

    def get_all(
        self,
        db: Session,
        *,
        skip: int = 0,
        limit: int = 100,
        **filters
    ) -> List[Log]:
        query = self._apply_filters(select(Log), **filters)
        query = query.options(selectinload(Log.analyses)).order_by(Log.timestamp.desc()).offset(skip).limit(limit)
        return list(db.scalars(query).all())

    def count_matching(self, db: Session, **filters) -> int:
        query = self._apply_filters(select(func.count(Log.id)), **filters)
        return db.scalar(query) or 0

    def get_for_export(self, db: Session, *, limit: int = 10000, **filters) -> List[Log]:
        query = self._apply_filters(select(Log), **filters)
        query = query.options(selectinload(Log.analyses)).order_by(Log.timestamp.desc()).limit(limit)
        return list(db.scalars(query).all())

    def count_errors_with_rca(self, db: Session, **filters) -> int:
        """Count of matching ERROR-level logs that already have an RCA solution, regardless of any log_level filter passed in."""
        error_filters = {**filters, "log_level": "ERROR"}
        query = self._apply_filters(
            select(func.count(func.distinct(Log.id))).select_from(Log).join(LogAnalysis, LogAnalysis.log_id == Log.id),
            **error_filters
        )
        return db.scalar(query) or 0

    def get_level_counts(self, db: Session, **filters) -> Dict[str, int]:
        query = self._apply_filters(
            select(Log.log_level, func.count(Log.id)), **filters
        ).group_by(Log.log_level)
        return {level: count for level, count in db.execute(query).all()}

    def get_top_services(self, db: Session, *, limit: int = 8, **filters) -> List[Dict[str, Any]]:
        error_count = func.sum(case((Log.log_level == "ERROR", 1), else_=0))
        query = self._apply_filters(
            select(Log.service_name, func.count(Log.id).label("count"), error_count.label("error_count")),
            **filters
        ).group_by(Log.service_name).order_by(func.count(Log.id).desc()).limit(limit)
        return [
            {"service_name": row[0], "count": row[1], "error_count": int(row[2] or 0)}
            for row in db.execute(query).all()
        ]

    def get_time_series(self, db: Session, *, bucket_expr, **filters) -> List[Dict[str, Any]]:
        error_count = func.sum(case((Log.log_level == "ERROR", 1), else_=0))
        bucket = bucket_expr.label("bucket")
        query = self._apply_filters(
            select(bucket, func.count(Log.id).label("count"), error_count.label("error_count")),
            **filters
        ).group_by(bucket).order_by(bucket)
        return [
            {"bucket": row[0], "count": row[1], "error_count": int(row[2] or 0)}
            for row in db.execute(query).all()
        ]

    def create(self, db: Session, obj_in: LogCreate) -> Log:
        db_obj = Log(
            timestamp=obj_in.timestamp,
            service_name=obj_in.service_name,
            instance_id=obj_in.instance_id,
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
                instance_id=obj.instance_id,
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
        instances = db.scalar(select(func.count(func.distinct(Log.instance_id)))) or 0

        return {
            "total_logs": total_logs,
            "error_logs": error_logs,
            "warning_logs": warning_logs,
            "services": services,
            "instances": instances
        }

class MonitoredSourceRootRepository:
    def get(self, db: Session, root_id: int) -> Optional[MonitoredSourceRoot]:
        return db.scalar(select(MonitoredSourceRoot).where(MonitoredSourceRoot.id == root_id))

    def get_by_path(self, db: Session, path: str) -> Optional[MonitoredSourceRoot]:
        norm_path = os.path.normcase(os.path.normpath(path))
        for root in db.scalars(select(MonitoredSourceRoot)).all():
            if os.path.normcase(os.path.normpath(root.path)) == norm_path:
                return root
        return None

    def get_all(self, db: Session) -> List[MonitoredSourceRoot]:
        return list(db.scalars(select(MonitoredSourceRoot).order_by(MonitoredSourceRoot.created_at.desc())).all())

    def get_all_active(self, db: Session) -> List[MonitoredSourceRoot]:
        return list(db.scalars(select(MonitoredSourceRoot).where(MonitoredSourceRoot.is_active == True)).all())

    def create(self, db: Session, obj_in: MonitoredSourceRootCreate) -> MonitoredSourceRoot:
        db_obj = MonitoredSourceRoot(
            path=obj_in.path,
            label=obj_in.label,
            is_active=True,
            status="pending"
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def update_status(self, db: Session, db_obj: MonitoredSourceRoot, status: str) -> MonitoredSourceRoot:
        db_obj.status = status
        db_obj.last_checked_at = datetime.utcnow()
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def delete(self, db: Session, db_obj: MonitoredSourceRoot) -> None:
        db.delete(db_obj)
        db.commit()

class AppSettingRepository:
    def get(self, db: Session, key: str) -> Optional[str]:
        row = db.scalar(select(AppSetting).where(AppSetting.key == key))
        return row.value if row else None

    def get_row(self, db: Session, key: str) -> Optional[AppSetting]:
        return db.scalar(select(AppSetting).where(AppSetting.key == key))

    def set(self, db: Session, key: str, value: Optional[str]) -> AppSetting:
        row = db.scalar(select(AppSetting).where(AppSetting.key == key))
        if row:
            row.value = value
        else:
            row = AppSetting(key=key, value=value)
            db.add(row)
        db.commit()
        db.refresh(row)
        return row

log_file_repo = LogFileRepository()
log_repo = LogRepository()
monitored_source_root_repo = MonitoredSourceRootRepository()
app_setting_repo = AppSettingRepository()
