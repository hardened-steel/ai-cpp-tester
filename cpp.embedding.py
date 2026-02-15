# #!/usr/bin/env python3
import json
import argparse
import struct
import hashlib
from openai import OpenAI


def make_str_hash(string: str) -> str:
    return hashlib.sha512(string.encode("utf-8")).hexdigest()


def float_to_str(value: float) -> str:
    return bytearray(struct.pack(">f", value)).hex()


def str_to_float(string: str) -> float:
    array = bytes.fromhex(string)
    return struct.unpack(">f", array)


def embed_text(text: str, client: OpenAI, model: str) -> list[float]:
    response = client.embeddings.create(
        model=model,
        input=text
    )
    return response.data[0].embedding


def generate_embeddings(symbols: dict, client: OpenAI, model: str) -> dict:
    result = dict()
    for id, symbol in symbols.items():
        emb = embed_text(symbol["text"], client, model)
        key = ".".join([float_to_str(value) for value in emb])
        result[key] = {
            "id": id,
            "kind": symbol["kind"],
            "fqn": symbol["fqn"],
        }
        if "signature" in symbol:
            result[key]["signature"] = symbol.get("signature")
    return result


def symbol_to_text(symbol: dict) -> str:
    lines = []

    kind = symbol.get("kind")
    if kind:
        lines.append(f"Symbol kind: {kind}")

    name = symbol.get("name")
    if name:
        lines.append(f"Name: {name}")

    fqn = symbol.get("fqn")
    if fqn:
        lines.append(f"Fully qualified name: {fqn}")

    if "return_type" in symbol or "params" in symbol:
        params = symbol.get("params", [])
        param_str = ", ".join(
            f"{p['type']} {p['name']}".strip()
            for p in params
        )
        ret = symbol.get("return_type") or "void"
        lines.append(f"Signature: {ret} {name}({param_str})")

    comment = symbol.get("comment")
    if comment:
        cleaned = comment.strip().replace("\n", " ")
        lines.append(f"Comment: {cleaned}")

    return "\n".join(lines)


def generate_symbol_texts(index: dict) -> list[dict]:
    db = dict()

    for cls in index["classes"]:
        id = make_str_hash(cls["fqn"])
        if id not in db:
            db[id] = {
                "kind": cls["kind"],
                "fqn": cls["fqn"],
                "text": symbol_to_text(cls)
            }

        for method in cls.get("methods", []):
            id = make_str_hash(f'{method["fqn"]}({[param["type"] for param in method["params"]]})')
            if id not in db:
                db[id] = {
                    "kind": method["kind"],
                    "fqn": method["fqn"],
                    "text": symbol_to_text(method),
                    "signature": method["signature"]
                }

        for function in cls.get("functions", []):
            id = make_str_hash(f'{function["fqn"]}({[param["type"] for param in function["params"]]})')
            if id not in db:
                db[id] = {
                    "kind": function["kind"],
                    "fqn": function["fqn"],
                    "text": symbol_to_text(function),
                    "signature": function["signature"]
                }

        for constructor in cls.get("constructors", []):
            id = make_str_hash(f'{constructor["fqn"]}({[param["type"] for param in constructor["params"]]})')
            if id not in db:
                db[id] = {
                    "kind": constructor["kind"],
                    "fqn": constructor["fqn"],
                    "text": symbol_to_text(constructor),
                    "signature": constructor["signature"]
                }

    for function in index["functions"]:
        id = make_str_hash(f'{function["fqn"]}({[param["type"] for param in function["params"]]})')
        if id not in db:
            db[id] = {
                "kind": function["kind"],
                "fqn": function["fqn"],
                "text": symbol_to_text(function),
                "signature": function["signature"]
            }

    return db


def save_index(index_data, out_path):
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(
            index_data,
            f,
            indent=2,
            ensure_ascii=False
        )


def load_index(file_name) -> dict:
    with open(file_name, "r", encoding="utf-8") as file:
        return json.load(file)


parser = argparse.ArgumentParser(
    prog='cpp-indexer',
    description='this program parse c++ source files and generate json data base with c++ entities',
)
parser.add_argument('ast_db', help='input C/C++ ast data base in json format')
parser.add_argument('embeddings', help='output embeddings json file')
args = parser.parse_args()


model = "text-embedding-qwen3-embedding-0.6b"
client = OpenAI(
    organization='no-organization',
    api_key='no-key',
    base_url='http://localhost:8080/v1/'
)

ast_db = load_index(args.ast_db)
symbols = generate_symbol_texts(ast_db)
embeddings = generate_embeddings(symbols, client, model)
save_index(embeddings, args.embeddings)
