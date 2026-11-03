# -*- coding: utf-8 -*-
"""
app/state/context.py
====================
Session Manager & Conversational Context Tracking for Spinneys Assistant.

Maintains in-memory multi-turn dialog state per session:
  - Tracks search filters: query, brand, category, price_min, price_max, in_stock, sort.
  - Retains last retrieved product candidates to support contextual references (e.g. "اول واحد").
  - Implements multi-turn state transition rules:
      * `refinement`: Keeps previous query and updates or narrows constraints.
      * `new_topic`: Resets previous constraints and establishes a new topic.
      * `cancellation`: Selectively removes a specific constraint (e.g., removes brand filter).
      * `reference`: Resolves contextual ordinal or positional references from `last_results`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class SessionState:
    """Represents the multi-turn conversational state of a single customer session."""

    session_id: str
    query: Optional[str] = None
    brand: Optional[str] = None
    category: Optional[str] = None
    price_min: Optional[float] = None
    price_max: Optional[float] = None
    in_stock: Optional[bool] = None
    sort: Optional[str] = None
    unsupported_filters: list[str] = field(default_factory=list)
    last_results: list[dict[str, Any]] = field(default_factory=list)
    turn_count: int = 0

    def to_filters(self) -> dict[str, Any]:
        """Converts the active session constraints to a dictionary for retrieval."""
        filters: dict[str, Any] = {}
        if self.brand is not None:
            filters["brand"] = self.brand
        if self.category is not None:
            filters["category"] = self.category
        if self.price_min is not None:
            filters["min_price"] = self.price_min
        if self.price_max is not None:
            filters["max_price"] = self.price_max
        if self.in_stock is not None:
            filters["in_stock"] = self.in_stock
        if self.sort is not None:
            filters["sort"] = self.sort
        return filters

    def reset(self) -> None:
        """Resets all filters for a new exploration topic."""
        self.query = None
        self.brand = None
        self.category = None
        self.price_min = None
        self.price_max = None
        self.in_stock = None
        self.sort = None
        self.unsupported_filters = []


class SessionManager:
    """Manages active in-memory session states."""

    def __init__(self) -> None:
        self.sessions: dict[str, SessionState] = {}

    def get_session(self, session_id: str) -> SessionState:
        """Retrieves or initializes a session state for the given session_id."""
        if session_id not in self.sessions:
            self.sessions[session_id] = SessionState(session_id=session_id)
        return self.sessions[session_id]

    def clear_session(self, session_id: str) -> None:
        """Removes a session state from memory."""
        self.sessions.pop(session_id, None)

    def update_state(self, session_id: str, nlu_result: Any) -> SessionState:
        """
        Updates session state based on the NLU parser output and follow-up type:
          - refinement: keep previous query, merge new constraints
          - new_topic: reset previous filters, apply new query and filters
          - cancellation: clear specific filter (e.g. brand)
          - reference: resolve product from last_results
        """
        state = self.get_session(session_id)
        state.turn_count += 1
        follow_up = getattr(nlu_result, "follow_up_type", "new_topic")
        intent = getattr(nlu_result, "intent", "search")

        if follow_up == "new_topic":
            state.reset()
            if getattr(nlu_result, "query", None):
                state.query = nlu_result.query
            if getattr(nlu_result, "brand", None):
                state.brand = nlu_result.brand
            if getattr(nlu_result, "category", None):
                state.category = nlu_result.category
            if getattr(nlu_result, "price_min", None) is not None:
                state.price_min = nlu_result.price_min
            if getattr(nlu_result, "price_max", None) is not None:
                state.price_max = nlu_result.price_max
            if getattr(nlu_result, "in_stock", None) is not None:
                state.in_stock = nlu_result.in_stock
            if getattr(nlu_result, "sort", None):
                state.sort = nlu_result.sort
            if getattr(nlu_result, "unsupported_filters", None):
                state.unsupported_filters = list(nlu_result.unsupported_filters)

        elif follow_up == "refinement":
            # Keep previous query if no new query specified
            if getattr(nlu_result, "query", None):
                state.query = nlu_result.query

            # Update constraints if explicitly mentioned in this turn
            if getattr(nlu_result, "brand", None):
                state.brand = nlu_result.brand
            if getattr(nlu_result, "category", None):
                state.category = nlu_result.category
            if getattr(nlu_result, "price_min", None) is not None:
                state.price_min = nlu_result.price_min
            if getattr(nlu_result, "price_max", None) is not None:
                state.price_max = nlu_result.price_max
            if getattr(nlu_result, "in_stock", None) is not None:
                state.in_stock = nlu_result.in_stock
            if getattr(nlu_result, "sort", None):
                state.sort = nlu_result.sort
            if getattr(nlu_result, "unsupported_filters", None):
                # Union unsupported filters
                for item in nlu_result.unsupported_filters:
                    if item not in state.unsupported_filters:
                        state.unsupported_filters.append(item)

        elif follow_up == "cancellation":
            # User explicitly removed or cancelled a constraint (e.g. "أي ماركة مش فارق معايا")
            explicit_fields = getattr(nlu_result, "explicit_fields", [])
            if "brand" in explicit_fields:
                state.brand = None
            if "price_max" in explicit_fields or "price_min" in explicit_fields:
                state.price_min = None
                state.price_max = None
            if "in_stock" in explicit_fields:
                state.in_stock = None
            if "sort" in explicit_fields:
                state.sort = None

        elif follow_up == "reference":
            # Reference to previous results (e.g. "اول واحد", "ثاني منتج", "this cheese")
            referenced_item = self.resolve_reference(
                raw_text=getattr(nlu_result, "raw_text", ""),
                last_results=state.last_results,
            )
            if referenced_item:
                state.query = referenced_item.get("name_ar") or referenced_item.get("name_en")
                state.brand = referenced_item.get("brand")

        return state

    @staticmethod
    def resolve_reference(raw_text: str, last_results: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
        """Resolves ordinal or positional reference from previous turn's results."""
        if not last_results:
            return None

        text_lower = raw_text.lower()
        # 1st item
        if any(term in text_lower for term in ["اول", "الاول", "رقم 1", "رقم واحد", "first"]):
            return last_results[0]
        # 2nd item
        if any(term in text_lower for term in ["تاني", "ثاني", "التاني", "الثاني", "رقم 2", "second"]):
            return last_results[1] if len(last_results) > 1 else last_results[0]
        # 3rd item
        if any(term in text_lower for term in ["تالت", "ثالث", "التالت", "الثالث", "رقم 3", "third"]):
            return last_results[2] if len(last_results) > 2 else last_results[-1]
        # Last item
        if any(term in text_lower for term in ["اخير", "الاخير", "last"]):
            return last_results[-1]

        # Default to first item if generic pronoun ("ده", "دي", "this", "that")
        return last_results[0]
