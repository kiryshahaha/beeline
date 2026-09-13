"""Literal, parameterized SQL. Transaction boundaries are owned by the service."""

from sqlalchemy import RowMapping, text
from sqlalchemy.orm import Session

# Shared columns and joins keep single-ticket and list responses identical.
TICKET_SELECT_SQL = """
    SELECT
        t.id, t.location_id, t.title, t.description, t.work_type, t.status,
        t.visit_window_start, t.visit_window_end, t.planned_start_at, t.planned_end_at,
        t.estimated_duration_minutes, t.actual_duration_minutes,
        t.created_by_id,
        creator.name AS creator_name,
        creator.surname AS creator_surname,
        creator.lastname AS creator_lastname,
        creator.username AS creator_username,
        creator.role AS creator_role,
        t.created_at, t.updated_at,
        c.id AS city_id, c.name AS city,
        d.id AS district_id, d.name AS district,
        s.id AS street_id, s.name AS street,
        b.id AS building_id, b.number AS building_number, b.block,
        l.entrance_id, e.number AS entrance_number,
        l.floor, l.apartment, l.latitude, l.longitude,
        COALESCE(
            (
                SELECT json_agg(
                    json_build_object(
                        'id', u.id,
                        'name', u.name,
                        'surname', u.surname,
                        'lastname', u.lastname,
                        'username', u.username,
                        'role', u.role,
                        'workshift_start', w.workshift_start,
                        'workshift_end', w.workshift_end,
                        'assigned_at', ta.assigned_at,
                        'skills', COALESCE(
                            (
                                SELECT json_agg(ws.skill ORDER BY ws.skill)
                                FROM worker_skill_assignments wsa
                                JOIN worker_skills ws ON ws.id = wsa.skill_id
                                WHERE wsa.worker_id = u.id
                            ),
                            '[]'::json
                        )
                    )
                    ORDER BY u.surname, u.name
                )
                FROM ticket_assignments ta
                JOIN users u ON u.id = ta.worker_id
                JOIN workers w ON w.user_id = ta.worker_id
                WHERE ta.ticket_id = t.id
            ),
            '[]'::json
        ) AS assignees
    FROM tickets AS t
    JOIN locations AS l ON l.id = t.location_id
    JOIN buildings AS b ON b.id = l.building_id
    JOIN streets AS s ON s.id = b.street_id
    JOIN cities AS c ON c.id = s.city_id
    JOIN districts AS d ON d.id = b.district_id
    LEFT JOIN entrances AS e ON e.id = l.entrance_id
    LEFT JOIN users AS creator ON creator.id = t.created_by_id
"""


def find_location_id(session: Session, location_id: int) -> int | None:
    # Keep this location from being deleted while its ticket is being inserted.
    return session.execute(
        text("SELECT id FROM locations WHERE id = :location_id FOR KEY SHARE"),
        {"location_id": location_id},
    ).scalar_one_or_none()


def add_ticket(session: Session, values: dict[str, object]) -> int:
    values.setdefault("created_by_id", None)
    return session.execute(
        text("""
            INSERT INTO tickets (
                location_id, title, description, work_type, status,
                visit_window_start, visit_window_end, planned_start_at, planned_end_at,
                estimated_duration_minutes, actual_duration_minutes, created_by_id
            ) VALUES (
                :location_id, :title, :description, :work_type, :status,
                :visit_window_start, :visit_window_end, :planned_start_at, :planned_end_at,
                :estimated_duration_minutes, :actual_duration_minutes, :created_by_id
            )
            RETURNING id
        """),
        values,
    ).scalar_one()


def update_ticket(session: Session, ticket_id: int, values: dict[str, object]) -> None:
    if not values:
        return
    set_clauses = [f"{col} = :{col}" for col in values.keys()]
    query = f"UPDATE tickets SET {', '.join(set_clauses)}, updated_at = now() WHERE id = :ticket_id"
    session.execute(text(query), {**values, "ticket_id": ticket_id})


def validate_worker_ids(session: Session, worker_ids: list[int]) -> list[int]:
    if not worker_ids:
        return []
    return list(
        session.execute(
            text("SELECT user_id FROM workers WHERE user_id = ANY(:worker_ids)"),
            {"worker_ids": worker_ids},
        )
        .scalars()
        .all()
    )


def set_ticket_assignees(session: Session, ticket_id: int, worker_ids: list[int]) -> None:
    session.execute(
        text("DELETE FROM ticket_assignments WHERE ticket_id = :ticket_id"),
        {"ticket_id": ticket_id},
    )
    for worker_id in worker_ids:
        session.execute(
            text("""
                INSERT INTO ticket_assignments (ticket_id, worker_id)
                VALUES (:ticket_id, :worker_id)
                ON CONFLICT DO NOTHING
            """),
            {"ticket_id": ticket_id, "worker_id": worker_id},
        )


def add_ticket_assignee(session: Session, ticket_id: int, worker_id: int) -> None:
    session.execute(
        text("""
            INSERT INTO ticket_assignments (ticket_id, worker_id)
            VALUES (:ticket_id, :worker_id)
            ON CONFLICT DO NOTHING
        """),
        {"ticket_id": ticket_id, "worker_id": worker_id},
    )


def remove_ticket_assignee(session: Session, ticket_id: int, worker_id: int) -> None:
    session.execute(
        text("DELETE FROM ticket_assignments WHERE ticket_id = :ticket_id AND worker_id = :worker_id"),
        {"ticket_id": ticket_id, "worker_id": worker_id},
    )


def find_ticket(session: Session, ticket_id: int) -> RowMapping | None:
    return (
        session.execute(
            text(TICKET_SELECT_SQL + " WHERE t.id = :ticket_id"),
            {"ticket_id": ticket_id},
        )
        .mappings()
        .one_or_none()
    )


def find_tickets(
    session: Session,
    *,
    status: str | None = None,
    city_id: int | None = None,
    district_id: int | None = None,
    worker_id: int | None = None,
    unassigned: bool | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[RowMapping]:
    conditions = []
    parameters: dict[str, object] = {"limit": limit, "offset": offset}
    if status is not None:
        conditions.append("t.status = :status")
        parameters["status"] = status
    if city_id is not None:
        conditions.append("b.city_id = :city_id")
        parameters["city_id"] = city_id
    if district_id is not None:
        conditions.append("b.district_id = :district_id")
        parameters["district_id"] = district_id
    if worker_id is not None:
        conditions.append(
            "EXISTS (SELECT 1 FROM ticket_assignments ta WHERE ta.ticket_id = t.id AND ta.worker_id = :worker_id)"
        )
        parameters["worker_id"] = worker_id
    if unassigned is True:
        conditions.append("NOT EXISTS (SELECT 1 FROM ticket_assignments ta WHERE ta.ticket_id = t.id)")
    elif unassigned is False:
        conditions.append("EXISTS (SELECT 1 FROM ticket_assignments ta WHERE ta.ticket_id = t.id)")

    # Only fixed SQL fragments are joined; every value is a bound parameter.
    query = TICKET_SELECT_SQL
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY t.id ASC LIMIT :limit OFFSET :offset"
    return list(session.execute(text(query), parameters).mappings().all())
