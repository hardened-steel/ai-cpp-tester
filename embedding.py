from dataclasses import dataclass
import json


def load_db(file_name) -> dict:
    with open(file_name, "r", encoding="utf-8") as file:
        return json.load(file)


def save_db(file_name, db: dict):
    with open(file_name, "w", encoding="utf-8") as file:
        json.dump(db, file, indent=2, ensure_ascii=False)


@dataclass
class EmbeddingDB:
    model_name: str
    db: list[dict]