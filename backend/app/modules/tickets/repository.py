"""Literal, parameterized SQL. Transaction boundaries are owned by the service."""

from sqlalchemy import RowMapping, text
from sqlalchemy.orm import Session

# Shared columns and joins keep single-ticket and list responses identical.
TICKET_SELECT_SQL = """
    SELECT
        t.id, t.location_id, t.title, t.description, t.work_type, t.status,
        t.visit_window_start, t.visit_window_end, t.planned_start_at, t.planned_end_at,
        t.estimated_duration_minutes, t.actual_duration_minutes,
        t.created_at, t.updated_at,
        c.id AS city_id, c.name AS city,
        d.id AS district_id, d.name AS district,
        s.id AS street_id, s.name AS street,
        b.id AS building_id, b.number AS building_number, b.block,
        l.entrance_id, e.number AS entrance_number,
        l.floor, l.apartment, l.latitude, l.longitude
    FROM tickets AS t
    JOIN locations AS l ON l.id = t.location_id
    JOIN buildings AS b ON b.id = l.building_id
    JOIN streets AS s ON s.id = b.street_id
    JOIN cities AS c ON c.id = s.city_id
    JOIN districts AS d ON d.id = b.district_id
    LEFT JOIN entrances AS e ON e.id = l.entrance_id
"""


def find_location_id(session: Session, location_id: int) -> int | None:
    # Keep this location from being deleted while its ticket is being inserted.
    return session.execute(
        text("SELECT id FROM locations WHERE id = :location_id FOR KEY SHARE"),
        {"location_id": location_id},
    ).scalar_one_or_none()


def add_ticket(session: Session, values: dict[str, object]) -> int:
    return session.execute(
        text("""
            INSERT INTO tickets (
                location_id, title, description, work_type, status,
                visit_window_start, visit_window_end, planned_start_at, planned_end_at,
                estimated_duration_minutes, actual_duration_minutes
            ) VALUES (
                :location_id, :title, :description, :work_type, :status,
                :visit_window_start, :visit_window_end, :planned_start_at, :planned_end_at,
                :estimated_duration_minutes, :actual_duration_minutes
            )
            RETURNING id
        """),
        values,
    ).scalar_one()


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
    status: str | None,
    city_id: int | None,
    district_id: int | None,
    limit: int,
    offset: int,
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

    # Only fixed SQL fragments are joined; every value is a bound parameter.
    query = TICKET_SELECT_SQL
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY t.id ASC LIMIT :limit OFFSET :offset"
    return list(session.execute(text(query), parameters).mappings().all())
