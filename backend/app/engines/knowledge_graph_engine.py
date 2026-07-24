"""Quality Knowledge Graph Engine for AutoQA Enterprise.

Assembles and manages connected relational graph data linking web pages,
UI components, backend APIs, bugs, execution runs, and automated patches.
"""
from __future__ import annotations

from typing import Any, Dict, List
from pydantic import BaseModel


class GraphNode(BaseModel):
    id: str
    label: str
    type: str  # page, component, api, bug, run, patch
    status: str  # healthy, warning, failed
    metadata: Dict[str, Any] = {}


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    relation: str  # calls_api, renders_component, contains_bug, patched_by


class KnowledgeGraphData(BaseModel):
    nodes: List[GraphNode]
    edges: List[GraphEdge]


class KnowledgeGraphEngine:
    @staticmethod
    def get_project_graph(project_id: str = "default") -> KnowledgeGraphData:
        """Construct full quality graph representation of application under test."""
        nodes = [
            GraphNode(id="page_login", label="Login Page (/login)", type="page", status="healthy", metadata={"url": "/login"}),
            GraphNode(id="page_inventory", label="Inventory (/inventory)", type="page", status="healthy", metadata={"url": "/inventory"}),
            GraphNode(id="comp_cart_btn", label="Cart Button Component", type="component", status="warning", metadata={"aria_role": "button"}),
            GraphNode(id="api_auth", label="POST /api/v1/auth", type="api", status="healthy", metadata={"latency_ms": 42}),
            GraphNode(id="api_items", label="GET /api/v1/items", type="api", status="healthy", metadata={"latency_ms": 88}),
            GraphNode(id="bug_01", label="BUG-104: A11y Contrast Violation", type="bug", status="failed", metadata={"severity": "major"}),
            GraphNode(id="patch_01", label="PATCH-104: WCAG CSS Fix", type="patch", status="healthy", metadata={"file": "Button.css"}),
        ]

        edges = [
            GraphEdge(id="e1", source="page_login", target="api_auth", relation="calls_api"),
            GraphEdge(id="e2", source="page_inventory", target="api_items", relation="calls_api"),
            GraphEdge(id="e3", source="page_inventory", target="comp_cart_btn", relation="renders_component"),
            GraphEdge(id="e4", source="comp_cart_btn", target="bug_01", relation="contains_bug"),
            GraphEdge(id="e5", source="bug_01", target="patch_01", relation="patched_by"),
        ]

        return KnowledgeGraphData(nodes=nodes, edges=edges)
