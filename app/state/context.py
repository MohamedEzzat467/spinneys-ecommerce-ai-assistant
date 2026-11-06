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


INCREMENTAL_REFINEMENT_RE = re.compile(
    r"\b(ارخص|أرخص|اغلى|أغلى|اقل|أقل|اكتر|أكثر|تحت|فوق|تاني|تانية|ثاني|ثانية|الماركة التانية|ماركة تانية|"
    r"رتبهم|رتب|بالسعر|سعر|منهم|فيهم|الاول|الأول|التاني|الثاني|الاخير|الأخير|بدون|مش عايز|بلاش|من غير|"
    r"cheaper|more expensive|less than|under|above|sort|second one|first one)\b",
    re.IGNORECASE,
)


@dataclass
class SessionState:
    """Represents the multi-turn conversational state of a single customer session."""

    session_id: str
    query: Optional[str] = None
    head_term: Optional[str] = None
    brand: Optional[str] = None
    category: Optional[str] = None
    price_min: Optional[float] = None
    price_max: Optional[float] = None
    in_stock: Optional[bool] = None
    sort: Optional[str] = None
    unsupported_filters: list[str] = field(default_factory=list)
    excluded_brands: list[str] = field(default_factory=list)
    excluded_categories: list[str] = field(default_factory=list)
    excluded_terms: list[str] = field(default_factory=list)
    required_subtypes: list[str] = field(default_factory=list)
    last_results: list[dict[str, Any]] = field(default_factory=list)
    history: list[dict[str, str]] = field(default_factory=list)
    turn_count: int = 0

    @property
    def last_products(self) -> list[dict[str, Any]]:
        return self.last_results

    @last_products.setter
    def last_products(self, products: list[dict[str, Any]]) -> None:
        self.last_results = products

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
        if self.head_term is not None:
            filters["head_term"] = self.head_term
        if self.excluded_brands:
            filters["excluded_brands"] = list(self.excluded_brands)
            filters["exclude_brands"] = list(self.excluded_brands)
        if self.excluded_categories:
            filters["excluded_categories"] = list(self.excluded_categories)
        if self.excluded_terms:
            filters["excluded_terms"] = list(self.excluded_terms)
        if self.required_subtypes:
            filters["required_subtypes"] = list(self.required_subtypes)
        return filters

    def reset(self) -> None:
        """Resets all transient filters for a new exploration topic."""
        self.query = None
        self.head_term = None
        self.brand = None
        self.category = None
        self.price_min = None
        self.price_max = None
        self.in_stock = None
        self.sort = None
        self.unsupported_filters = []
        self.excluded_brands = []
        self.excluded_categories = []
        self.excluded_terms = []
        self.required_subtypes = []


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
        action = getattr(nlu_result, "action", "search")
        raw_text = getattr(nlu_result, "raw_text", "")
        nlu_head = getattr(nlu_result, "head_term", None)
        q_val = getattr(nlu_result, "clean_query", None) or getattr(nlu_result, "query", None)

        if intent == "advisory" or action == "advisory_qa":
            # Retain all active constraints and product list for advisory dialogue
            return state

        # Invariant 5: Stateless Context Transition & Intent Cleaning
        is_recipe_intent = (intent == "recipe" or action == "recipe")
        is_head_term_changed = bool(state.head_term and nlu_head and nlu_head != state.head_term)
        is_explicit_refine = bool(INCREMENTAL_REFINEMENT_RE.search(raw_text))

        # If user switches to a recipe, changes primary product noun, or enters an independent search:
        # IMMEDIATELY PURGE all prior transient filters!
        if is_recipe_intent or is_head_term_changed or (follow_up == "refinement" and not is_explicit_refine and q_val):
            follow_up = "new_topic"

        if follow_up == "new_topic":
            state.reset()
            if q_val:
                state.query = q_val
            if nlu_head:
                state.head_term = nlu_head
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
            s_val = getattr(nlu_result, "sort", None)
            if not s_val and getattr(nlu_result, "sort_by", "relevance") != "relevance":
                s_val = nlu_result.sort_by
            if s_val:
                state.sort = s_val
            if getattr(nlu_result, "unsupported_filters", None):
                state.unsupported_filters = list(nlu_result.unsupported_filters)
            if getattr(nlu_result, "excluded_brands", None):
                state.excluded_brands = list(nlu_result.excluded_brands)
            if getattr(nlu_result, "excluded_categories", None):
                state.excluded_categories = list(nlu_result.excluded_categories)
            if getattr(nlu_result, "excluded_terms", None):
                state.excluded_terms = list(nlu_result.excluded_terms)
            if getattr(nlu_result, "required_subtypes", None):
                state.required_subtypes = list(nlu_result.required_subtypes)

        elif follow_up == "refinement":
            # Keep previous query if no new query specified
            if q_val:
                state.query = q_val
            if nlu_head:
                state.head_term = nlu_head

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
            s_val = getattr(nlu_result, "sort", None)
            if not s_val and getattr(nlu_result, "sort_by", "relevance") != "relevance":
                s_val = nlu_result.sort_by
            if s_val:
                state.sort = s_val
            if getattr(nlu_result, "unsupported_filters", None):
                for item in nlu_result.unsupported_filters:
                    if item not in state.unsupported_filters:
                        state.unsupported_filters.append(item)
            if getattr(nlu_result, "excluded_brands", None):
                for eb in nlu_result.excluded_brands:
                    if eb not in state.excluded_brands:
                        state.excluded_brands.append(eb)
            if getattr(nlu_result, "excluded_terms", None):
                for et in nlu_result.excluded_terms:
                    if et not in state.excluded_terms:
                        state.excluded_terms.append(et)
            if getattr(nlu_result, "required_subtypes", None):
                for rs in nlu_result.required_subtypes:
                    if rs not in state.required_subtypes:
                        state.required_subtypes.append(rs)

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
