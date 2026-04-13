"""
Liminal Vocab - In-memory knowledge graph built from JSON files in data/.

Reads all node files (terms, communities, patterns, sources) and edges.json,
provides lookup functions for the API.
"""

import json
from pathlib import Path
from typing import Any


DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _localize(value: Any, lang: str) -> Any:
    """Resolve a field that may be a plain string or a {lang: text} dict."""
    if isinstance(value, dict) and not any(k in value for k in ("id", "type")):
        return value.get(lang) or value.get("en") or next(iter(value.values()), None)
    return value


class Graph:
    def __init__(self):
        self.nodes: dict[str, dict] = {}
        self.edges: list[dict] = []
        self._load()

    def _load(self):
        """Load all JSON files from data/ into memory."""
        self.nodes = {}
        self.edges = []

        for subdir in ("terms", "communities", "patterns", "sources"):
            folder = DATA_DIR / subdir
            if not folder.exists():
                continue
            for path in sorted(folder.glob("*.json")):
                node = json.loads(path.read_text(encoding="utf-8"))
                node_id = node.get("id")
                if node_id:
                    self.nodes[node_id] = node

        edges_file = DATA_DIR / "edges.json"
        if edges_file.exists():
            data = json.loads(edges_file.read_text(encoding="utf-8"))
            self.edges = data.get("edges", [])

    def reload(self):
        """Reload graph from disk."""
        self._load()

    def get_node(self, node_id: str) -> dict | None:
        return self.nodes.get(node_id)

    def get_nodes_by_type(self, node_type: str) -> list[dict]:
        return [n for n in self.nodes.values() if n.get("type") == node_type]

    def get_edges_from(self, node_id: str) -> list[dict]:
        return [e for e in self.edges if e.get("source") == node_id]

    def get_edges_to(self, node_id: str) -> list[dict]:
        return [e for e in self.edges if e.get("target") == node_id]

    def get_edges_involving(self, node_id: str) -> list[dict]:
        return [
            e for e in self.edges
            if e.get("source") == node_id or e.get("target") == node_id
        ]

    def resolve_term(self, term_id: str, lang: str = "en") -> dict | None:
        """Return a term with all its edges resolved to full node data."""
        term = self.get_node(term_id)
        if not term or term.get("type") != "Term":
            return None

        edges = self.get_edges_from(term_id)

        # Resolve multilingual fields
        label = term.get("labels", {}).get(lang) or term.get("labels", {}).get("en") or term["id"]
        original_label = term.get("labels", {}).get(term.get("primary_language", "en"), term["id"])
        has_equivalent = lang in term.get("labels", {})

        resolved = {
            **term,
            "label": label,
            "original_label": original_label,
            "has_equivalent": has_equivalent,
            "definitions": _localize(term.get("definitions", {}), lang),
            "makes_visible": _localize(term.get("makes_visible", ""), lang),
            "edges": [],
        }

        for edge in edges:
            edge_data: dict[str, Any] = {"type": edge["type"]}

            if "target" in edge:
                target_node = self.get_node(edge["target"])
                if target_node:
                    edge_data["target"] = {
                        "id": target_node["id"],
                        "type": target_node.get("type"),
                        "label": target_node.get("labels", {}).get(lang)
                                 or next(iter(target_node.get("labels", {}).values()), None),
                    }
                else:
                    edge_data["target"] = {"id": edge["target"]}

            if "target_freetext" in edge:
                edge_data["target_freetext"] = edge["target_freetext"]

            if "note" in edge:
                edge_data["note"] = edge["note"]

            resolved["edges"].append(edge_data)

        # Also include edges where this term is a target (e.g., related_to from another term)
        incoming = [e for e in self.edges if e.get("target") == term_id and e.get("source") != term_id]
        for edge in incoming:
            source_node = self.get_node(edge["source"])
            if source_node and source_node.get("type") == "Term":
                resolved["edges"].append({
                    "type": edge["type"],
                    "direction": "incoming",
                    "target": {
                        "id": source_node["id"],
                        "type": "Term",
                        "label": source_node.get("labels", {}).get(lang)
                                 or next(iter(source_node.get("labels", {}).values()), None),
                    },
                })

        return resolved

    def all_terms_resolved(self, lang: str = "en") -> list[dict]:
        """Return all accepted terms, each with resolved edges."""
        terms = [
            n for n in self.nodes.values()
            if n.get("type") == "Term" and n.get("status") == "accepted"
        ]
        results = []
        for term in sorted(terms, key=lambda t: t.get("labels", {}).get(lang, t["id"])):
            resolved = self.resolve_term(term["id"], lang)
            if resolved:
                results.append(resolved)
        return results

    def all_communities(self, lang: str = "en") -> list[dict]:
        return sorted(
            self.get_nodes_by_type("Community"),
            key=lambda c: c.get("labels", {}).get(lang, c["id"]),
        )

    def all_patterns(self, lang: str = "en") -> list[dict]:
        return sorted(
            self.get_nodes_by_type("Pattern"),
            key=lambda p: p.get("labels", {}).get(lang, p["id"]),
        )
