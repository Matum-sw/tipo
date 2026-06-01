from dataclasses import dataclass


@dataclass(frozen=True)
class Subject:
    id: int
    name: str
    difficulty: str
    kind: str


@dataclass(frozen=True)
class Todo:
    id: int
    day: str
    title: str
    subject_id: int
    subject_name: str
    subject_kind: str
    status: str
