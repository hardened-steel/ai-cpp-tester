from openai import AsyncOpenAI
from search import SearchService, CodebaseContext
import asyncio, json, sys


def load_db(file_name) -> dict:
    with open(file_name, "r", encoding="utf-8") as file:
        return json.load(file)

async def main():
    client = AsyncOpenAI(
        organization='no-organization',
        api_key='no-key',
        base_url='http://localhost:8080/v1/'
    )
    
    ctx = CodebaseContext(
        ast_index=load_db("ast.json"),
        embeddings=load_db("embeddings.json")["embeddings"],
        embedding_model_name="text-embedding-qwen3-embedding-0.6b",
        openai_client=client,
    )

    result = await SearchService(ctx).hybrid_search(
        sys.argv[1]
    )
    print(result)

asyncio.run(main())