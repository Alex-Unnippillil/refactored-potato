from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Currency = Literal['CAD', 'USD', 'EUR', 'GBP']
WorkMode = Literal['Remote', 'Hybrid', 'On-site', 'Unknown']
Level = Literal['Entry', 'Mid', 'Senior', 'Lead', 'Unknown']
PREFERENCES = ('async', 'balance', 'ownership', 'mentorship', 'mission', 'learning')


class Filters(BaseModel):
    model_config = ConfigDict(extra='forbid')
    country: Literal['', 'Canada', 'United States', 'United Kingdom', 'Germany', 'Netherlands'] = ''
    city: str = Field(default='', max_length=80)
    work_mode: Literal['', 'Remote', 'Hybrid', 'On-site'] = ''
    level: Literal['', 'Entry', 'Mid', 'Senior', 'Lead'] = ''
    min_salary: int = Field(default=0, ge=0, le=1000000)
    currency: Currency = 'CAD'


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    query: str = Field(default='', max_length=600)
    filters: Filters = Field(default_factory=Filters)
    preferences: list[Literal['async', 'balance', 'ownership', 'mentorship', 'mission', 'learning']] = Field(default_factory=list, max_length=6)
    semantic_weight: float = Field(default=0.65, ge=0, le=1)
    page: int = Field(default=1, ge=1, le=100)
    page_size: int = Field(default=12, ge=1, le=24)

    @field_validator('query')
    @classmethod
    def clean_query(cls, value: str) -> str:
        return ' '.join(value.split())

    @field_validator('preferences')
    @classmethod
    def deduplicate(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(values))


class Job(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,100}$')
    title: str = Field(min_length=2, max_length=160)
    company: str = Field(min_length=1, max_length=120)
    city: str = Field(default='Not specified', max_length=100)
    country: str = Field(default='Not specified', max_length=100)
    work_mode: WorkMode = 'Unknown'
    level: Level = 'Unknown'
    salary_min: int | None = Field(default=None, ge=0, le=10000000)
    salary_max: int | None = Field(default=None, ge=0, le=10000000)
    currency: Currency | None = None
    salary_period: Literal['year'] | None = None
    description: str = Field(min_length=40, max_length=40000)
    skills: list[str] = Field(default_factory=list, max_length=20)
    tags: list[str] = Field(default_factory=list, max_length=10)
    remote_scope: str = Field(default='Eligibility not specified; verify with employer.', max_length=300)
    source: str = Field(max_length=60)
    source_key: str = Field(max_length=150)
    source_url: str | None = Field(default=None, max_length=2048)
    first_seen: str
    last_seen: str
    source_updated_at: str | None = None
    expires_at: str | None = None
    is_demo: bool = False
    active: bool = True

    @field_validator('source_url')
    @classmethod
    def safe_link(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parsed = urlparse(value)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError('Source links must use HTTPS without embedded credentials.')
        return value

    @field_validator('skills', 'tags')
    @classmethod
    def bounded_labels(cls, values: list[str]) -> list[str]:
        if any(len(s) > 60 or not s.strip() for s in values):
            raise ValueError('Labels must contain 1–60 characters.')
        return list(dict.fromkeys(values))

    @field_validator('first_seen', 'last_seen', 'source_updated_at', 'expires_at')
    @classmethod
    def valid_date(cls, value: str | None) -> str | None:
        if value is not None:
            parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
            if parsed.tzinfo is None:
                raise ValueError('Timestamps must include a timezone.')
        return value

    @model_validator(mode='after')
    def consistent_salary(self) -> 'Job':
        if self.salary_min is not None or self.salary_max is not None:
            if not self.currency or self.salary_period != 'year':
                raise ValueError('Annual salaries require an explicit currency and period.')
        if self.salary_min is not None and self.salary_max is not None and self.salary_min > self.salary_max:
            raise ValueError('Salary range is reversed.')
        return self


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()
