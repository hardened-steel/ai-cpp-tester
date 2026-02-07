# #!/usr/bin/env python3
import json
from openai import OpenAI
from clang.cindex import Index, Type, TypeKind, CursorKind, AccessSpecifier, CompilationDatabase, Cursor, TranslationUnit
from collections import defaultdict
from pathlib import Path
import sys
import hashlib


embedding_model = "text-embedding-qwen3-embedding-0.6b"

client = OpenAI(
    organization='no-organization',
    api_key='no-key',
    base_url='http://localhost:8080/v1/'
)


def progress_bar(iterable, prefix = '', suffix = '', decimals = 1, length = 80, fill = '█', printEnd = "\r"):
    """
    Call in a loop to create terminal progress bar
    @params:
        iterable    - Required  : iterable object (Iterable)
        prefix      - Optional  : prefix string (Str)
        suffix      - Optional  : suffix string (Str)
        decimals    - Optional  : positive number of decimals in percent complete (Int)
        length      - Optional  : character length of bar (Int)
        fill        - Optional  : bar fill character (Str)
        printEnd    - Optional  : end character (e.g. "\r", "\r\n") (Str)
    """
    length = length - len(prefix)
    total = len(iterable)
    # Progress Bar Printing Function
    def print_progress_bar (iteration):
        percent = ("{0:." + str(decimals) + "f}").format(100 * (iteration / float(total)))
        filledLength = int(length * iteration // total)
        bar = fill * filledLength + '-' * (length - filledLength)
        print(f'\r{prefix} |{bar}| {percent}% {suffix}', end = printEnd)
    # Initial Call
    print_progress_bar(0)
    # Update Progress Bar
    for i, item in enumerate(iterable):
        yield item
        print_progress_bar(i + 1)
    # Print New Line on Complete
    print()


def make_symbol_id(kind: str, fqn: str) -> str:
    data = f'{kind}:{fqn}'
    return hashlib.sha512(data.encode("utf-8")).hexdigest()


def embed_text(text: str) -> list[float]:
    response = client.embeddings.create(
        model=embedding_model,
        input=text
    )
    return response.data[0].embedding


def generate_embeddings(symbols: list[dict]) -> dict:
    result = {
        "model": "text-embedding-3-small",
        "dimension": None,
        "embeddings": []
    }

    for symbol in progress_bar(symbols, prefix="calc embeddings"):
        emb = embed_text(symbol["text"])

        if result["dimension"] is None:
            result["dimension"] = len(emb)

        result["embeddings"].append({
            "id": make_symbol_id(symbol["kind"], symbol["fqn"]),
            "kind": symbol["kind"],
            "fqn": symbol["fqn"],
            "file": symbol["file"],
            "embedding": emb
        })

    return result


def get_type_fqn(type: Type):
    names = []
    
    is_pointer = type.kind == TypeKind.POINTER
    is_reference = type.kind in [
        TypeKind.LVALUEREFERENCE, 
        TypeKind.RVALUEREFERENCE
    ]

    if is_pointer or is_reference:
        type = type.get_pointee()
            
    c = type.get_declaration()
    while c and c.kind != CursorKind.TRANSLATION_UNIT:
        if c.spelling:
            names.append(c.spelling)
        c = c.semantic_parent

    result = "::".join(reversed(names))
    return result


def get_fqn(cursor: Cursor):
    names = []
    c = cursor
    while c and c.kind != CursorKind.TRANSLATION_UNIT:
        if c.spelling:
            names.append(c.spelling)
        c = c.semantic_parent
    return "::".join(reversed(names))


def get_namespace_path(cursor: Cursor):
    ns = []
    c = cursor.semantic_parent
    while c and c.kind != CursorKind.TRANSLATION_UNIT:
        if c.kind == CursorKind.NAMESPACE:
            ns.append(c.spelling)
        c = c.semantic_parent
    return list(reversed(ns))


def access_to_str(access):
    return {
        AccessSpecifier.PUBLIC: "public",
        AccessSpecifier.PROTECTED: "protected",
        AccessSpecifier.PRIVATE: "private",
        AccessSpecifier.INVALID: "none"
    }.get(access, "unknown")


def extract_function(cursor: Cursor):
    return {
        "kind": "function",
        "name": cursor.spelling,
        "fqn": get_fqn(cursor),
        "namespace": get_namespace_path(cursor),
        "return_type": get_type_fqn(cursor.result_type),
        "params": [
            {
                "name": arg.spelling,
                "type": get_type_fqn(arg.type)
            }
            for arg in cursor.get_arguments()
        ],
        "is_static": cursor.is_static_method(),
        "access": access_to_str(cursor.access_specifier),
        "location": {
            "file": cursor.location.file.name if cursor.location.file else None,
            "line": cursor.location.line
        }
    }


def extract_method(cursor: Cursor):
    return {
        "kind": cursor.kind.name.lower(),
        "name": cursor.spelling,
        "fqn": get_fqn(cursor),
        "namespace": get_namespace_path(cursor),
        "return_type": (
            get_type_fqn(cursor.result_type)
            if cursor.kind == CursorKind.CXX_METHOD
            else None
        ),
        "params": [
            {
                "name": arg.spelling,
                "type": get_type_fqn(arg.type)
            }
            for arg in cursor.get_arguments()
        ],
        "is_const": cursor.is_const_method(),
        "is_static": cursor.is_static_method(),
        "access": access_to_str(cursor.access_specifier),
        "location": {
            "line": cursor.location.line
        }
    }


def extract_class(cursor: Cursor):
    cls = {
        "kind": cursor.kind.name.lower(),
        "name": cursor.spelling,
        "fqn": get_fqn(cursor),
        "namespace": get_namespace_path(cursor),
        "methods": [],
        "location": {
            "file": cursor.location.file.name if cursor.location.file else None,
            "line": cursor.location.line
        },
    }
    
    if cursor.raw_comment is not None:
        cls["comment"] = cursor.raw_comment

    for c in cursor.get_children():
        if c.kind in (
            CursorKind.CXX_METHOD,
            CursorKind.CONSTRUCTOR,
            CursorKind.DESTRUCTOR
        ):
            cls["methods"].append(extract_method(c))

    return cls


def is_file_from_includes(include_dirs: set[Path], path: Path):
    for dir in include_dirs:
        if path.is_relative_to(dir):
            return True
    return False


def index_cpp_file(db, include_dirs, path, clang_args):
    index = Index.create()
    tu = index.parse(path, args=clang_args, options=TranslationUnit.PARSE_SKIP_FUNCTION_BODIES)

    #for cursor in tu.cursor.walk_preorder():
    for cursor in progress_bar([c for c in tu.cursor.walk_preorder()], prefix=f'indexing {Path(path).stem}'):
        if not cursor.location.file:
            continue

        file_name = Path(cursor.location.file.name).resolve(True)
        if not is_file_from_includes(include_dirs, file_name):
            continue

        if cursor.kind in (CursorKind.CLASS_DECL, CursorKind.STRUCT_DECL):
            if cursor.is_definition():
                db[str(file_name)]["classes"].append(extract_class(cursor))

        if cursor.kind == CursorKind.FUNCTION_DECL:
            db[str(file_name)]["functions"].append(extract_function(cursor))


def symbol_to_text(symbol: dict) -> str:
    lines = []

    # 1. Kind
    kind = symbol.get("kind")
    if kind:
        lines.append(f"Symbol kind: {kind}")

    # 2. Name
    name = symbol.get("name")
    if name:
        lines.append(f"Name: {name}")

    # 3. Fully qualified name
    fqn = symbol.get("fqn")
    if fqn:
        lines.append(f"Fully qualified name: {fqn}")

    # 4. Namespace
    namespace = symbol.get("namespace")
    if namespace:
        lines.append(f"Namespace: {'::'.join(namespace)}")

    # 5. Signature
    if "return_type" in symbol:
        params = symbol.get("params", [])
        param_str = ", ".join(
            f"{p['type']} {p['name']}".strip()
            for p in params
        )
        ret = symbol.get("return_type") or "void"
        lines.append(f"Signature: {ret} {name}({param_str})")

    # 6. Comment
    comment = symbol.get("comment")
    if comment:
        cleaned = comment.strip().replace("\n", " ")
        lines.append(f"Comment: {cleaned}")

    return "\n".join(lines)


def generate_symbol_texts(index: dict) -> list[dict]:
    db = dict()
    for file_name, file_data in progress_bar(index.items(), prefix="create symbols"):

        for cls in file_data.get("classes", []):
            symbol = symbol_to_text(cls)
            if symbol not in db:
                db[symbol] = {
                "kind": cls["kind"],
                "fqn": cls["fqn"],
                "text": symbol_to_text(cls),
                "file": file_name
            }

            for method in cls.get("methods", []):
                symbol = symbol_to_text(method)
                db[symbol] = {
                    "kind": method["kind"],
                    "fqn": method["fqn"],
                    "text": symbol_to_text(method),
                    "file": file_name
                }

        for fn in file_data.get("functions", []):
            symbol = symbol_to_text(fn)
            db[symbol] = {
                "kind": fn["kind"],
                "fqn": fn["fqn"],
                "text": symbol_to_text(fn),
                "file": file_name
            }

    return [val for _, val in db.items()]


def save_index(index_data, out_path):
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(
            index_data,
            f,
            indent=2,
            ensure_ascii=False
        )


def load_db(file_name) -> dict:
    with open(file_name, "r", encoding="utf-8") as file:
        return json.load(file)


def save_db(file_name, db: dict):
    with open(file_name, "w", encoding="utf-8") as file:
        json.dump(db, file, indent=2, ensure_ascii=False)


ast_db = defaultdict(
    lambda: {
        "classes": [],
        "functions": []
    }
)
compilation_db = CompilationDatabase.fromDirectory(sys.argv[1])

include_dirs = set()
for command in compilation_db.getAllCompileCommands():
    for arg in command.arguments:
        if arg.startswith("-I"):
            include_dirs.add(Path(arg[2:]).resolve(True))

for command in compilation_db.getAllCompileCommands():
    arguments = [arg for arg in command.arguments]
    arguments = arguments[1:-2]
    arguments.append('-fparse-all-comments')
    index_cpp_file(ast_db, include_dirs, command.filename, arguments)

symbols = generate_symbol_texts(ast_db)
save_index(symbols, "symbols.json")
save_index(generate_embeddings(symbols), 'embeddings.json')
save_index(ast_db, "ast.json")
