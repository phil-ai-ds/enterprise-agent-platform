"""M8-lite: 长期记忆服务（按 user(+agent) 命名空间）。反馈迭代：save 时若 key 相同则更新旧值。"""
from sqlalchemy import or_
from sqlalchemy.orm import Session

from .models import MemoryEntry


def save_memory(db: Session, user_id: int, agent_id: int | None, kind: str, key: str, value: str) -> MemoryEntry:
    row = (
        db.query(MemoryEntry)
        .filter(MemoryEntry.user_id == user_id,
                MemoryEntry.agent_id == agent_id,
                MemoryEntry.kind == kind,
                MemoryEntry.key == key)
        .first()
    )
    if row:
        row.value = value  # 同 key 覆盖 = 记忆迭代
    else:
        row = MemoryEntry(user_id=user_id, agent_id=agent_id, kind=kind, key=key, value=value)
        db.add(row)
    db.commit()
    db.refresh(row)
    return row


def recall(db: Session, user_id: int, agent_id: int | None, query: str, limit: int = 5) -> list[MemoryEntry]:
    terms = [t for t in query.lower().replace(",", " ").split() if len(t) > 1][:6]
    q = db.query(MemoryEntry).filter(MemoryEntry.user_id == user_id)
    if agent_id:
        q = q.filter(or_(MemoryEntry.agent_id == agent_id, MemoryEntry.agent_id.is_(None)))
    rows = q.order_by(MemoryEntry.updated_at.desc()).limit(60).all()
    scored = []
    for r in rows:
        hay = (r.key + " " + r.value).lower()
        score = sum(1 for t in terms if t in hay)
        if score:
            scored.append((score, r))
    scored.sort(key=lambda x: (-x[0], x[1].updated_at.timestamp()))
    out = [r for _, r in scored[:limit]]
    for r in out:
        r.hits += 1
    db.commit()
    return out


def list_memory(db: Session, user_id: int, agent_id: int | None = None) -> list[MemoryEntry]:
    q = db.query(MemoryEntry).filter(MemoryEntry.user_id == user_id)
    if agent_id:
        q = q.filter(MemoryEntry.agent_id == agent_id)
    return q.order_by(MemoryEntry.updated_at.desc()).limit(100).all()


def delete_memory(db: Session, user_id: int, entry_id: int) -> bool:
    row = db.query(MemoryEntry).filter(MemoryEntry.id == entry_id, MemoryEntry.user_id == user_id).first()
    if not row:
        return False
    db.delete(row)
    db.commit()
    return True
