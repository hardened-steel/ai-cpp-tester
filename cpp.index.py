# #!/usr/bin/env python3
import json
import argparse
from clang.cindex import (
    Index,
    Type,
    TypeKind,
    CursorKind,
    AccessSpecifier,
    Cursor,
    TranslationUnit
)
from pathlib import Path


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
    if c.kind is CursorKind.NO_DECL_FOUND:
        return type.spelling
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


def extract_function(cursor: Cursor):
    function = {
        "kind": "function",
        "name": cursor.spelling,
        "fqn": get_fqn(cursor),
        "return_type": get_type_fqn(cursor.result_type),
        "params": [
            {
                "name": arg.spelling,
                "type": get_type_fqn(arg.type)
            }
            for arg in cursor.get_arguments()
        ]
    }
    function["signature"] = get_fqn(cursor) + f'({"".join([arg_fqn["type"] for arg_fqn in function["params"]])})'
    if cursor.raw_comment is not None:
        function["comment"] = cursor.raw_comment
    return function


def extract_method(cursor: Cursor):
    method = {
        "kind": "method",
        "name": cursor.spelling,
        "fqn": get_fqn(cursor),
        "params": [
            {
                "name": arg.spelling,
                "type": get_type_fqn(arg.type)
            }
            for arg in cursor.get_arguments()
        ],
    }
    method["signature"] = get_fqn(cursor) + f'({"".join([arg_fqn["type"] for arg_fqn in method["params"]])})'
    if cursor.kind == CursorKind.CXX_METHOD:
        method["return_type"] = get_type_fqn(cursor.result_type)
    if cursor.raw_comment is not None:
        method["comment"] = cursor.raw_comment
    return method


def extract_constructor(cursor: Cursor):
    constructor = {
        "kind": "constructor",
        "name": cursor.spelling,
        "fqn": get_fqn(cursor),
        "params": [
            {
                "name": arg.spelling,
                "type": get_type_fqn(arg.type)
            }
            for arg in cursor.get_arguments()
        ],
    }
    constructor["signature"] = get_fqn(cursor) + f'({"".join([arg_fqn["type"] for arg_fqn in constructor["params"]])})'
    if cursor.raw_comment is not None:
        constructor["comment"] = cursor.raw_comment
    return constructor


def extract_class(cursor: Cursor):
    cls = {
        "kind": "type",
        "name": cursor.spelling,
        "fqn": get_fqn(cursor),
        "methods": [],
        "constructors": []
    }

    if cursor.raw_comment is not None:
        cls["comment"] = cursor.raw_comment

    for child in cursor.get_children():
        if child.access_specifier == AccessSpecifier.PUBLIC:
            if child.kind is CursorKind.CXX_METHOD:
                if child.is_static_method():
                    cls["functions"].append(extract_function(child))
                else:
                    cls["methods"].append(extract_method(child))
            if child.kind is CursorKind.CONSTRUCTOR:
                cls["constructors"].append(extract_constructor(child))

    return cls


def is_file_from_includes(include_dirs: set[Path], path: Path):
    for dir in include_dirs:
        if path.is_relative_to(dir):
            return True
    return False


def index_cpp_file(tu, include_dirs):
    ast_db = {
        "classes": [],
        "functions": []
    }

    for cursor in tu.cursor.walk_preorder():
        if not cursor.location.file:
            continue

        file_name = Path(cursor.location.file.name).resolve(True)
        if not is_file_from_includes(include_dirs, file_name):
            continue

        if cursor.kind in (CursorKind.CLASS_DECL, CursorKind.STRUCT_DECL):
            if cursor.is_definition():
                ast_db["classes"].append(extract_class(cursor))

        if cursor.kind == CursorKind.FUNCTION_DECL:
            ast_db
            ["functions"].append(extract_function(cursor))

    return ast_db


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


def collect_index(args):
    include_dirs = set()
    clang_args = ['-fparse-all-comments']

    for arg in args.flg.split(' '):
        clang_args.append(arg)

    for arg_set in args.target_args:
        for arg in arg_set.split(' '):
            if arg.startswith("-I"):
                path = Path(arg[2:]).resolve(True)
                include_dirs.add(path)
                clang_args.append(arg)
            else:
                clang_args.append(arg)


    index = Index.create()
    tu = index.parse(args.src, args=clang_args, options=TranslationUnit.PARSE_SKIP_FUNCTION_BODIES)
    with open(args.dep, 'w') as file:
        file.write(f'{args.dst.replace(" ", "\\ ")}: \\\n')
        for include in tu.get_includes():
            file.write(f'  {include.include.name.replace(" ", "\\ ")}\\\n')

    save_index(index_cpp_file(tu, include_dirs), args.dst)


def merge_indexes(args):
    ast_db = {
        "classes": [],
        "functions": []
    }
    classes = dict()
    functions = dict()
    for input in args.inputs:
        db = load_index(input)
        for class_record in db["classes"]:
            if class_record["fqn"] not in classes:
                classes[class_record["fqn"]] = class_record
                ast_db["classes"].append(class_record)
        for function_record in db["functions"]:
            if function_record["fqn"] not in functions:
                functions[function_record["fqn"]] = function_record
                ast_db["functions"].append(function_record)
    save_index(ast_db, args.output)


parser = argparse.ArgumentParser(
    prog='cpp-indexer',
    description='this program parse c++ source files and generate json data base with c++ entities',
)
subparsers = parser.add_subparsers(required=True, help='operating mode')

parse = subparsers.add_parser("parse", help='parse *.c/*.cpp file and generate index')
parse.add_argument('--src', help='c/c++ translation unit file (*.cpp, *.c etc)')
parse.add_argument('--dst', help='output index file name')
parse.add_argument('--flg', help='default compiler flags')
parse.add_argument('--dep', help='dependency file name')
parse.add_argument('target_args', nargs='*')
parse.set_defaults(func=collect_index)

merge = subparsers.add_parser("merge", help="merge multiple index files into one")
merge.add_argument('--inputs', nargs='+', help='input index files')
merge.add_argument('--output', help='output merged index file')
merge.set_defaults(func=merge_indexes)

args = parser.parse_args()
args.func(args)
