from __future__ import annotations

import hashlib
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml
from pydantic import TypeAdapter

from tbos_renderer.config import ScheduleConfig
from tbos_renderer.content_engine.schemas import (
    ContentType,
    FactSensitivity,
    Topic,
    WeeklyPlan,
    WeeklyPlanItem,
    WeeklyPlanRequest,
)


class TopicLibrary:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._adapter = TypeAdapter(list[Topic])

    def all(self) -> list[Topic]:
        with self.path.open(encoding="utf-8") as handle:
            payload = yaml.safe_load(handle)
        return self._adapter.validate_python(payload["topics"])

    def get(self, topic_id: str) -> Topic | None:
        return next((topic for topic in self.all() if topic.id == topic_id), None)

    def filter(
        self,
        *,
        pillar: str | None = None,
        content_type: ContentType | None = None,
        audience: str | None = None,
        difficulty: str | None = None,
        max_sensitivity: FactSensitivity | None = None,
        active: bool = True,
        excluded_ids: set[str] | None = None,
    ) -> list[Topic]:
        rank = {FactSensitivity.LOW: 0, FactSensitivity.MEDIUM: 1, FactSensitivity.HIGH: 2}
        excluded = excluded_ids or set()
        return [
            topic
            for topic in self.all()
            if topic.active is active
            and topic.id not in excluded
            and (pillar is None or topic.pillar == pillar)
            and (content_type is None or content_type in topic.formats)
            and (audience is None or audience.casefold() in topic.target_audience.casefold())
            and (difficulty is None or topic.difficulty.value == difficulty)
            and (max_sensitivity is None or rank[topic.fact_sensitivity] <= rank[max_sensitivity])
        ]


class WeeklyPlanner:
    def __init__(self, topics: TopicLibrary, schedule: ScheduleConfig) -> None:
        self.topics = topics
        self.schedule = schedule

    def create(
        self, request: WeeklyPlanRequest, recent_topic_ids: set[str] | None = None
    ) -> WeeklyPlan:
        recent = recent_topic_ids or set()
        selected: set[str] = set()
        pillar_counts: dict[str, int] = {}
        items: list[WeeklyPlanItem] = []
        weekday_numbers = {
            "Monday": 0,
            "Tuesday": 1,
            "Wednesday": 2,
            "Thursday": 3,
            "Friday": 4,
            "Saturday": 5,
            "Sunday": 6,
        }
        zone = ZoneInfo(self.schedule.timezone)
        for slot in self.schedule.weekly_plan:
            content_type = ContentType(slot.content_type)
            candidates = self.topics.filter(
                pillar=request.pillar,
                content_type=content_type,
                audience=request.audience,
                difficulty=request.difficulty.value if request.difficulty else None,
                max_sensitivity=request.max_fact_sensitivity,
                excluded_ids=selected,
            )
            unused = [topic for topic in candidates if topic.id not in recent]
            pool = unused or candidates
            if not pool:
                raise ValueError(f"No topic is available for {slot.slot}.")
            minimum = min(pillar_counts.get(topic.pillar, 0) for topic in pool)
            balanced = [topic for topic in pool if pillar_counts.get(topic.pillar, 0) == minimum]
            balanced.sort(
                key=lambda topic: hashlib.sha256(
                    f"{request.week_start}:{slot.slot}:{topic.id}".encode()
                ).hexdigest()
            )
            topic = balanced[0]
            selected.add(topic.id)
            pillar_counts[topic.pillar] = pillar_counts.get(topic.pillar, 0) + 1
            hour, minute = (int(part) for part in slot.time.split(":"))
            local_date = request.week_start + timedelta(days=weekday_numbers[slot.day])
            local_time = datetime.combine(local_date, time(hour, minute), tzinfo=zone)
            items.append(
                WeeklyPlanItem(
                    slot=slot.slot,
                    scheduled_at=local_time.astimezone(UTC),
                    content_type=content_type,
                    topic_id=topic.id,
                    title=topic.title,
                    pillar=topic.pillar,
                    target_audience=topic.target_audience,
                    difficulty=topic.difficulty,
                    fact_sensitivity=topic.fact_sensitivity,
                    cta_type=topic.cta_type,
                )
            )
        return WeeklyPlan(
            plan_id=f"weekly-{request.week_start.isoformat()}",
            week_start=request.week_start,
            timezone=self.schedule.timezone,
            items=items,
        )
