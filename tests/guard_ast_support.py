"""Conservative AST name resolution for repository integrity guards (not a proof of arbitrary behavior)."""
import ast
import importlib.util


def canonical_import_names(tree, module_name, canonical_module, exported_name):
    """Top-level exact imports only; any shadowing makes the annotation/helper unknown."""
    if any(isinstance(n, ast.ImportFrom) and any(a.name == "*" for a in n.names) for n in ast.walk(tree)):
        return set()
    candidates = set()
    bindings = []
    package = module_name.rsplit(".", 1)[0]
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            name = "." * node.level + (node.module or "")
            try:
                resolved = importlib.util.resolve_name(name, package) if node.level else name
            except (ImportError, ValueError):
                continue
            for alias in node.names:
                local = alias.asname or alias.name
                bindings.append((local, resolved, alias.name))
                if resolved == canonical_module and alias.name == exported_name:
                    candidates.add(local)
    for local in tuple(candidates):
        if any(name == local and (mod, original) != (canonical_module, exported_name)
               for name, mod, original in bindings):
            candidates.discard(local)
            continue
        for node in ast.walk(tree):
            if ((isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)) and node.id == local)
                    or (isinstance(node, (ast.MatchAs, ast.MatchStar, ast.ExceptHandler)) and node.name == local)
                    or (isinstance(node, ast.MatchMapping) and node.rest == local)
                    or (isinstance(node, ast.arg) and node.arg == local)
                    or (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == local)
                    or (isinstance(node, ast.ImportFrom) and node not in tree.body
                        and any((a.asname or a.name) == local for a in node.names))
                    or (isinstance(node, ast.Import) and any((a.asname or a.name.split(".")[0]) == local
                                                            for a in node.names))):
                candidates.discard(local)
                break
    return candidates


def unconditional_refusal(node):
    body = list(node.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
        body = body[1:]
    return len(body) == 1 and isinstance(body[0], ast.Raise) and body[0].exc is not None


def calls_canonical_helper(member, names):
    return any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in names
               for n in ast.walk(member))
