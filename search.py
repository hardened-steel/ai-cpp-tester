# #!/usr/bin/env python3
import json
import math
import re
from openai import OpenAI, AsyncClient
from cli_progress_bar import progress_bar


embedding_model = "text-embedding-qwen3-embedding-0.6b"

client = OpenAI(
    organization='no-organization',
    api_key='no-key',
    base_url='http://localhost:8080/v1/'
)


from dataclasses import dataclass
from typing import Any


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = 0.0
    na = 0.0
    nb = 0.0

    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y

    if na == 0.0 or nb == 0.0:
        return 0.0

    return dot / math.sqrt(na * nb)


@dataclass
class CodebaseContext:
    ast_index: dict
    embeddings: list[dict]
    embedding_model_name: str
    openai_client: Any  # OpenAI.AsyncClient


class SearchService:
    def __init__(self, ctx: CodebaseContext):
        self.ctx = ctx

    async def embed_query(self, text: str) -> list[float]:
        ctx = self.ctx
        response = await ctx.openai_client.embeddings.create(
            model=ctx.embedding_model_name,
            input=text,
        )
        return response.data[0].embedding


    async def raw_semantic_search(
        self,
        query: str,
        top_k: int = 10,
    ) -> dict[str, float]:
        query_embedding = await self.embed_query(query)

        scored = []

        for item in self.ctx.embeddings:
            score = cosine_similarity(query_embedding, item["embedding"])
            scored.append(
                {
                    "id": item["id"],
                    "kind": item["kind"],
                    "fqn": item["fqn"],
                    "file": item["file"],
                    "score": score
                }
            )

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]


    async def search_by_name(self, name: str) -> list[dict[str, str]]:
        results = dict()

        for file in self.ctx.ast_index.values():
            for cls in file.get("classes", []):
                if name.lower() in cls["name"].lower():
                    fqn = cls["fqn"]
                    if fqn not in results:
                        results[fqn] = {
                            "fqn": cls["fqn"],
                            "kind": cls["kind"]
                        }

                for m in cls.get("methods", []):
                    if name.lower() in m["name"].lower():
                        fqn = m["fqn"]
                        if fqn not in results:
                            results[fqn] = {
                                "fqn": m["fqn"],
                                "kind": m["kind"]
                            }

            for fn in file.get("functions", []):
                if name.lower() in fn["name"].lower():
                    fqn = fn["fqn"]
                    if fqn not in results:
                        results[fqn] = {
                            "fqn": fn["fqn"],
                            "kind": fn["kind"]
                        }

        return results


    async def get_symbol(self, fqn: str) -> dict[str, None | str | list[str] | dict[str, None | str | list[str] | dict[str, int] | list[dict[str, str]]]] | None:
        for file in self.ctx.ast_index.values():
            for cls in file.get("classes", []):
                if fqn == cls["fqn"]:
                    return cls

                for m in cls.get("methods", []):
                    if fqn == m["fqn"]:
                        return m

            for fn in file.get("functions", []):
                if fqn == fn["fqn"]:
                    return fn


    async def get_class_methods(self, class_fqn: str) -> list[dict[str, str]]:
        for file in self.ctx.ast_index.values():
            for cls in file.get("classes", []):
                if cls["fqn"] == class_fqn:
                    return [
                        {
                            "name": m["name"],
                            "fqn": m["fqn"]
                        }
                        for m in cls.get("methods", [])
                    ]
        return []


    def tokenize_query(text: str) -> list[str]:
        return [
            t.lower()
            for t in re.findall(r"[A-Za-z_][A-Za-z_0-9]*", text)
        ]


    def name_match_score(symbol: dict, tokens: list[str]) -> float:
        haystack = " ".join(
            [
                symbol.get("name", ""),
                symbol.get("fqn", "")
            ]
        ).lower()

        matches = sum(1 for t in tokens if t in haystack)

        if matches == 0:
            return 0.0

        return matches / len(tokens)


    def apply_filters(results: list[dict], flt: dict | None) -> list[dict]:
        if not flt:
            return results

        out = []

        for r in results:
            if "kinds" in flt:
                if r["kind"] not in flt["kinds"]:
                    continue

            if "namespace_prefix" in flt:
                if not r["fqn"].startswith(flt["namespace_prefix"] + "::"):
                    continue

            out.append(r)

        return out


    async def semantic_search(
        self,
        query: str,
        top_k: int = 5,
        filter: dict | None = None,
    ) -> list[dict[str, str | float | list[str]]]:
        tokens = SearchService.tokenize_query(query)

        semantic_hits = await self.raw_semantic_search(
            query, top_k=top_k * 2
        )

        semantic_map = {
            hit["fqn"]: hit["score"]
            for hit in semantic_hits
        }

        results = {}

        # name-based
        for file in self.ctx.ast_index.values():
            for cls in file.get("classes", []):
                score = SearchService.name_match_score(cls, tokens)
                if score > 0:
                    results.setdefault(cls["fqn"], {
                        "fqn": cls["fqn"],
                        "kind": cls["kind"],
                        "semantic": 0.0,
                        "name": 0.0,
                    })
                    results[cls["fqn"]]["name"] = max(
                        results[cls["fqn"]]["name"], score
                    )

                for m in cls.get("methods", []):
                    score = SearchService.name_match_score(m, tokens)
                    if score > 0:
                        results.setdefault(m["fqn"], {
                            "fqn": m["fqn"],
                            "kind": m["kind"],
                            "semantic": 0.0,
                            "name": 0.0,
                        })
                        results[m["fqn"]]["name"] = max(
                            results[m["fqn"]]["name"], score
                        )

            for fn in file.get("functions", []):
                score = SearchService.name_match_score(fn, tokens)
                if score > 0:
                    results.setdefault(fn["fqn"], {
                        "fqn": fn["fqn"],
                        "kind": fn["kind"],
                        "semantic": 0.0,
                        "name": 0.0,
                    })
                    results[fn["fqn"]]["name"] = max(
                        results[fn["fqn"]]["name"], score
                    )

        # merge semantic
        for fqn, sem_score in semantic_map.items():
            results.setdefault(
                fqn,
                {
                    "fqn": fqn,
                    "kind": "unknown",
                    "semantic": 0.0,
                    "name": 0.0,
                }
            )
            results[fqn]["semantic"] = sem_score

        # final score
        final = []
        semantic_weight = 0.7
        name_weight = 0.3
        for r in results.values():
            score = (
                semantic_weight * r["semantic"] +
                name_weight * r["name"]
            )

            if score == 0:
                continue

            sources = []
            if r["semantic"] > 0:
                sources.append("semantic")
            if r["name"] > 0:
                sources.append("name")

            final.append(
                {
                    "fqn": r["fqn"],
                    "kind": r["kind"],
                    "score": round(score, 3),
                    "sources": sources
                }
            )

        final.sort(key=lambda x: x["score"], reverse=True)
        return final[:top_k]
