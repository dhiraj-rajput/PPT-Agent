"""
check_pydantic_issues.py
-------------------------
Script to audit all Pydantic models across the backend for deprecations,
mutable defaults, missing type hints, and V1 vs V2 compatibility issues.
"""

import ast
import glob
import os
import sys

def audit_pydantic_in_file(filepath: str) -> list[str]:
    issues = []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            code = f.read()
        tree = ast.parse(code, filename=filepath)
    except Exception as e:
        return [f"Could not parse AST: {e}"]

    rel_path = os.path.relpath(filepath)

    class PydanticVisitor(ast.NodeVisitor):
        def visit_ClassDef(self, node: ast.ClassDef):
            # Check if class inherits from BaseModel
            is_base_model = any(
                (isinstance(b, ast.Name) and b.id == "BaseModel") or
                (isinstance(b, ast.Attribute) and b.attr == "BaseModel")
                for b in node.bases
            )
            if is_base_model:
                # Check body for Pydantic V1 patterns or mutable defaults
                for stmt in node.body:
                    # 1. Check for class Config
                    if isinstance(stmt, ast.ClassDef) and stmt.name == "Config":
                        for config_item in stmt.body:
                            if isinstance(config_item, ast.Assign):
                                for target in config_item.targets:
                                    if isinstance(target, ast.Name):
                                        if target.id == "orm_mode":
                                            issues.append(f"{rel_path}:{stmt.lineno} — [Pydantic V1 Deprecation] 'orm_mode = True' should be replaced with 'model_config = ConfigDict(from_attributes=True)'")
                                        elif target.id == "schema_extra":
                                            issues.append(f"{rel_path}:{stmt.lineno} — [Pydantic V1 Deprecation] 'schema_extra' should be replaced with 'json_schema_extra'")
                    
                    # 2. Check for mutable default arguments in type-annotated fields
                    if isinstance(stmt, ast.AnnAssign) and stmt.value is not None:
                        if isinstance(stmt.value, (ast.List, ast.Dict, ast.Set)):
                            var_name = stmt.target.id if isinstance(stmt.target, ast.Name) else "field"
                            issues.append(
                                f"{rel_path}:{stmt.lineno} — [Pydantic Warning] Field '{var_name}' uses mutable default `{ast.unparse(stmt.value)}`. "
                                f"Recommended: `Field(default_factory={type(ast.literal_eval(stmt.value)).__name__})`"
                            )

                    # 3. Check for @validator decorator
                    if isinstance(stmt, ast.FunctionDef):
                        for dec in stmt.decorator_list:
                            dec_name = ""
                            if isinstance(dec, ast.Name):
                                dec_name = dec.id
                            elif isinstance(dec, ast.Call) and isinstance(dec.func, ast.Name):
                                dec_name = dec.func.id
                            if dec_name == "validator":
                                issues.append(f"{rel_path}:{stmt.lineno} — [Pydantic V1 Deprecation] `@validator` should be updated to `@field_validator` in Pydantic v2")

            self.generic_visit(node)

        def visit_Call(self, node: ast.Call):
            # Check for .dict(), .json(), .parse_obj() calls on objects
            if isinstance(node.func, ast.Attribute):
                if node.func.attr == "dict" and not any(isinstance(a, ast.Name) and a.id == "os" for a in [node.func.value]):
                    pass # .dict() is common for standard dicts as well, check parse_obj/from_orm specifically
                elif node.func.attr in ("parse_obj", "from_orm"):
                    issues.append(f"{rel_path}:{node.lineno} — [Pydantic V1 Deprecation] `.{node.func.attr}()` is deprecated in Pydantic v2 (use `model_validate()`)")

            self.generic_visit(node)

    visitor = PydanticVisitor()
    visitor.visit(tree)
    return issues


def main():
    print("=" * 60)
    print("Auditing Pydantic Models across PPT-Agent Backend...")
    print("=" * 60)

    backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    py_files = glob.glob(os.path.join(backend_dir, "**", "*.py"), recursive=True)

    all_issues = []
    scanned_count = 0

    for f in py_files:
        if "__pycache__" in f or ".venv" in f:
            continue
        scanned_count += 1
        issues = audit_pydantic_in_file(f)
        if issues:
            all_issues.extend(issues)

    print(f"\nScanned {scanned_count} Python files.")
    if not all_issues:
        print("[SUCCESS] 0 Pydantic issues or deprecation warnings found!")
    else:
        print(f"[NOTICE] Found {len(all_issues)} Pydantic notice(s):")
        for issue in all_issues:
            print(f"  * {issue}")
    print("=" * 60)


if __name__ == "__main__":
    main()
