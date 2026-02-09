from openai import AsyncOpenAI
from openai.types.responses import ResponseTextDeltaEvent, ResponseFunctionToolCall
from agents import (
    Agent,
    OpenAIChatCompletionsModel,
    Runner, RunContextWrapper,
    ModelSettings,
    ItemHelpers,
    function_tool, set_trace_processors
)
from search import SearchService, CodebaseContext
from dataclasses import dataclass
import dsl
import asyncio, json


set_trace_processors([])  # disable OpenAI tracing

@dataclass
class Context:
    search_service: SearchService


@function_tool
async def hybrid_search(
    wrapper: RunContextWrapper[Context],
    query: str,
    top_k: int = 5
):
    """"Hybrid semantic and lexical search over C++ codebase symbols."""

    context = wrapper.context
    result = await context.search_service.hybrid_search(
        query=query,
        top_k=top_k,
    )
    return result


@function_tool
async def search_by_name(
    wrapper: RunContextWrapper[Context],
    name: str
):
    """"Exact or partial search by name."""

    context = wrapper.context
    result = await context.search_service.search_by_name(
        name=name
    )
    return result


@function_tool
async def get_symbol(
    wrapper: RunContextWrapper[Context],
    fqn: str
):
    """"Get complete information about the symbol."""

    context = wrapper.context
    result = await context.search_service.get_symbol(
        fqn=fqn
    )
    return result


@function_tool
async def get_class_methods(
    wrapper: RunContextWrapper[Context],
    class_fqn: str
):
    """"Get complete information about the symbol."""

    context = wrapper.context
    result = await context.search_service.get_class_methods(
        class_fqn=class_fqn
    )
    return result


def read_prompt_file(file_name: str):
    with open(f'{file_name}.prompt', "r", encoding="utf-8") as file:
        return file.read()


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

    context = Context(search_service=SearchService(ctx))
    settings = ModelSettings(
        extra_args={
            "seed": 42
        }
    )

    agent = Agent[Context](
        name="cpp-test-agent",
        model=OpenAIChatCompletionsModel(
            model="openai/gpt-oss-20b",
            openai_client=client
        ),
        model_settings=settings,
        instructions=read_prompt_file("system"),
        tools=[hybrid_search, get_symbol, search_by_name, get_class_methods]
    )
    
    result = Runner.run_streamed(  
        starting_agent=agent,
        input='{"test": "Given An empty box. When I place 2 x "apple" in it. Then The box contains 2 items."}',
        context=context
    )
    
    async for event in result.stream_events():
        if event.type == "raw_response_event" and isinstance(event.data, ResponseTextDeltaEvent):
            print(event.data.delta, end="", flush=True)
            
        # We'll ignore the raw responses event deltas
        if event.type == "raw_response_event":
            continue
        # When the agent updates, print that
        elif event.type == "agent_updated_stream_event":
            print(f"Agent updated: {event.new_agent.name}")
            continue
        # When items are generated, print them
        elif event.type == "run_item_stream_event":
            if event.item.type == "tool_call_item":
                print(f"-- Tool was called")
            if event.item.type == "tool_call_output_item":
                print(f"-- Tool output: {event.item.output}")

    print("=== Run complete ===")

asyncio.run(main())