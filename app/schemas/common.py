"""
Common Schemas & Generic Pagination
-----------------------------------
Provides reusable pagination models and query parameters.
"""

from typing import Generic, TypeVar, List
from pydantic import BaseModel, Field

T = TypeVar("T")


class PaginationParams(BaseModel):
    page: int = Field(default=1, ge=1, description="Page number starting at 1")
    size: int = Field(default=20, ge=1, le=100, description="Number of items per page (1-100)")

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.size


class Page(BaseModel, Generic[T]):
    items: List[T] = Field(description="List of records for the current page")
    total: int = Field(description="Total number of matching records in database")
    page: int = Field(description="Current page number")
    size: int = Field(description="Page size limit")
    total_pages: int = Field(description="Total number of available pages")

    @classmethod
    def create(cls, items: List[T], total: int, page: int, size: int) -> "Page[T]":
        total_pages = (total + size - 1) // size if size > 0 else 0
        return cls(
            items=items,
            total=total,
            page=page,
            size=size,
            total_pages=total_pages,
        )
