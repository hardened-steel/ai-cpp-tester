from dataclasses import dataclass, field
from typing import Any, List, Dict, Optional, Union
import json


class DSLValidationError(Exception):
    pass


@dataclass
class Step:
    op: str


@dataclass
class CreateStep(Step):
    id: str
    type: str
    args: List[Any] = field(default_factory=list)

    def __init__(self, **kw):
        super().__init__(op="create")
        self.id = kw["id"]
        self.type = kw["type"]
        self.args = kw.get("args", [])


@dataclass
class CallStep(Step):
    target: str
    method: str
    args: List[Any]
    result: Optional[str]

    def __init__(self, **kw):
        super().__init__(op="call")
        self.target = kw["target"]
        self.method = kw["method"]
        self.args = kw.get("args", [])
        self.result = kw.get("result")


@dataclass
class GetStep(Step):
    target: str
    field: str
    result: str

    def __init__(self, **kw):
        super().__init__(op="get")
        self.target = kw["target"]
        self.field = kw["field"]
        self.result = kw["result"]


@dataclass
class AssertExpr:
    op: str
    left: Any
    right: Any


@dataclass
class AssertStep(Step):
    expr: AssertExpr

    def __init__(self, **kw):
        super().__init__(op="assert")
        e = kw["expr"]
        self.expr = AssertExpr(**e)


@dataclass
class ExpectFailStep(Step):
    step: int

    def __init__(self, **kw):
        super().__init__(op="expect_fail")
        self.step = kw["step"]


@dataclass
class TestPlan:
    test: str
    steps: List[Step]


STEP_CLASSES = {
    "create": CreateStep,
    "call": CallStep,
    "get": GetStep,
    "assert": AssertStep,
    "expect_fail": ExpectFailStep,
}


def parse_step(data: Dict[str, Any]) -> Step:
    op = data.get("op")
    if op not in STEP_CLASSES:
        raise DSLValidationError(f"Unknown op '{op}'")

    return STEP_CLASSES[op](**data)


def parse_test_plan(data: Dict[str, Any]) -> TestPlan:
    if "test" not in data or "steps" not in data:
        raise DSLValidationError("Test plan must contain 'test' and 'steps'")

    steps = [parse_step(s) for s in data["steps"]]
    return TestPlan(test=data["test"], steps=steps)


class ASTProvider:
    def has_type(self, fqn: str) -> bool:
        raise NotImplementedError

    def get_class(self, fqn: str) -> dict | None:
        raise NotImplementedError

    def get_constructors(self, fqn: str) -> list[dict]:
        raise NotImplementedError

    def find_method(self, class_fqn: str, method_fqn: str) -> dict | None:
        raise NotImplementedError


class DSLContext:
    def __init__(self, ast):
        self.ast: ASTProvider = ast
        self.variables: dict[str, str] = {}  # var -> type


def infer_arg_type(arg: str, ctx: DSLContext) -> str:
    if arg in ctx.variables:
        return ctx.variables[arg]

    if arg.isdigit():
        return "int"

    if arg.replace(".", "", 1).isdigit():
        return "double"

    if arg in ("true", "false"):
        return "bool"

    if isinstance(arg, str):
        return "std::string"

    raise DSLValidationError(f"Unknown argument '{arg}'")


def check_args(
    expected_params: list[dict],
    actual_args: list[str],
    ctx: DSLContext,
    where: str
):
    if len(expected_params) != len(actual_args):
        raise DSLValidationError(
            f"{where}: expected {len(expected_params)} args, got {len(actual_args)}"
        )

    for i, (param, arg) in enumerate(zip(expected_params, actual_args)):
        expected = param["type"]
        actual = infer_arg_type(arg, ctx)

        if not is_type_compatible(actual, expected):
            raise DSLValidationError(
                f"{where}: arg {i} type mismatch: "
                f"expected {expected}, got {actual}"
            )


def is_type_compatible(actual: str, expected: str) -> bool:
    return actual == expected


def validate_plan(plan: TestPlan, ast_provider: ASTProvider):
    ctx = DSLContext(ast=ast_provider)

    for idx, step in enumerate(plan.steps):
        try:
            validate_step(step, ctx)
        except DSLValidationError as e:
            raise DSLValidationError(
                f"Step {idx} ({step.op}): {e}"
            ) from None


def validate_step(step: Step, ctx: DSLContext):
    if isinstance(step, CreateStep):
        validate_create(step, ctx)
    elif isinstance(step, CallStep):
        validate_call(step, ctx)
    elif isinstance(step, GetStep):
        validate_get(step, ctx)
    elif isinstance(step, AssertStep):
        validate_assert(step, ctx)
    elif isinstance(step, ExpectFailStep):
        validate_expect_fail(step, ctx)
    else:
        raise DSLValidationError("Unsupported step type")


def validate_create(step: CreateStep, ctx: DSLContext):
    ctors = ctx.ast.get_constructors(step.type)

    for ctor in ctors:
        try:
            check_args(
                ctor["params"],
                step.args,
                ctx,
                f"constructor {step.type}"
            )
            ctx.variables[step.id] = step.type
            return
        except DSLValidationError:
            pass

    raise DSLValidationError(
        f"No matching constructor for '{step.type}'"
    )


def validate_call(step: CallStep, ctx: DSLContext):
    obj_type = ctx.variables.get(step.target)
    if not obj_type:
        raise DSLValidationError(f"Unknown variable '{step.target}'")

    method = ctx.ast.find_method(obj_type, step.method)
    if not method:
        raise DSLValidationError(
            f"Method '{step.method}' not found in '{obj_type}'"
        )

    check_args(
        method["params"],
        step.args,
        ctx,
        f"{obj_type}::{step.method}"
    )

    if step.result:
        ctx.variables[step.result] = method["return_type"]


def validate_get(step: GetStep, ctx: DSLContext):
    if step.target not in ctx.variables:
        raise DSLValidationError(
            f"Unknown target object '{step.target}'"
        )

    cls = ctx.ast.get_class(ctx.variables[step.target])
    if not cls:
        raise DSLValidationError("Invalid target type")

    fields = cls.get("fields", [])
    if step.field not in {f["name"] for f in fields}:
        raise DSLValidationError(
            f"Field '{step.field}' not found in '{cls['fqn']}'"
        )

    ctx.values[step.result] = None


def validate_assert(step: AssertStep, ctx: DSLContext):
    for side in (step.expr.left, step.expr.right):
        if isinstance(side, str) and side.startswith("$"):
            if side[1:] not in ctx.variables:
                raise DSLValidationError(
                    f"Unknown value reference '{side}'"
                )


def validate_expect_fail(step: ExpectFailStep, ctx: DSLContext):
    if step.step < 0:
        raise DSLValidationError("step index must be >= 0")


class JsonASTProvider(ASTProvider):
    def __init__(self, ast_index: dict):
        self.index = ast_index
        self.symbols = self._build_symbol_index()

    def _build_symbol_index(self):
        symbols = {}

        for file in self.index.values():
            for cls in file.get("classes", []):
                symbols[cls["fqn"]] = cls
                for m in cls.get("methods", []):
                    symbols[m["fqn"]] = m

            for fn in file.get("functions", []):
                symbols[fn["fqn"]] = fn

        return symbols

    def has_type(self, fqn: str) -> bool:
        sym = self.symbols.get(fqn)
        return sym and sym["kind"] in ("class_decl", "struct_decl")

    def get_class(self, fqn: str) -> dict | None:
        sym = self.symbols.get(fqn)
        if sym and sym["kind"] in ("class_decl", "struct_decl"):
            return sym
        return None

    def get_constructors(self, fqn: str) -> list[dict]:
        cls = self.get_class(fqn)
        if cls is None:
            raise DSLValidationError(
                f"Unknown type '{fqn}'"
            )
        return [
            method
            for method in cls["methods"]
                if method["kind"] == "constructor"
        ]

    def find_method(self, class_fqn: str, method_fqn: str) -> dict | None:
        cls = self.get_class(class_fqn)
        if not cls:
            return None

        for m in cls.get("methods", []):
            if m["fqn"] == method_fqn:
                return m

        return None

json_plan = {
    "test": "transfer between accounts",
    "steps": [
        {
            "op": "create",
            "id": "box",
            "type": "lib::BoxOfFruits",
            "args": []
        },
        {
            "op": "create",
            "id": "fruit_0",
            "type": "lib::Fruit",
            "args": [
                "apple"
            ]
        },
        {
            "op": "create",
            "id": "fruit_1",
            "type": "lib::Fruit",
            "args": [
                "banana"
            ]
        },
        {
            "op": "call",
            "target": "box",
            "method": "lib::BoxOfFruits::add",
            "args": ["fruit_0"]
        },
        {
            "op": "call",
            "target": "box",
            "method": "lib::BoxOfFruits::add",
            "args": ["fruit_1"]
        },
        {
            "op": "call",
            "target": "box",
            "method": "lib::BoxOfFruits::count",
            "args": [],
            "result": "count"
        },
        {
            "op": "assert",
            "expr": {
                "op": "equals",
                "left": "count",
                "right": 2
            }
        }
    ]
}



def load_db(file_name) -> dict:
    with open(file_name, "r", encoding="utf-8") as file:
        return json.load(file)

provider = JsonASTProvider(load_db("ast.json"))
plan = parse_test_plan(json_plan)
validate_plan(plan, provider)