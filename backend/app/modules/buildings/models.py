"""A building is shared by its entrances and service locations."""

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IntegerIdMixin


class Building(IntegerIdMixin, Base):
    __tablename__ = "buildings"

    street_id: Mapped[int] = mapped_column(ForeignKey("streets.id", ondelete="RESTRICT"))
    number: Mapped[str] = mapped_column(String(30))
    block: Mapped[str | None] = mapped_column(String(30))

    __table_args__ = (
        CheckConstraint("number = btrim(number) AND number <> ''", name="number_not_blank"),
        CheckConstraint(
            "block IS NULL OR (block = btrim(block) AND block <> '')", name="block_not_blank"
        ),
        Index(
            "uq_buildings_street_number_block",
            street_id,
            func.lower(number),
            func.lower(block),
            unique=True,
            postgresql_nulls_not_distinct=True,
        ),
    )
