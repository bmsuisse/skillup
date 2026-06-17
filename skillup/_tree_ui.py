from __future__ import annotations

from dataclasses import dataclass, field

from prompt_toolkit import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout
from prompt_toolkit.layout.containers import Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.styles import Style


@dataclass
class Node:
    label: str
    value: str        # "__dir__:path" or skill_name
    depth: int
    checked: bool = False
    parent: int = -1  # index in flat list; -1 = top-level
    children: list[int] = field(default_factory=list)

    @property
    def is_dir(self) -> bool:
        return self.value.startswith("__dir__:")


def _count_in_subtree(t: dict) -> int:
    return len(t.get("_skills", [])) + sum(
        _count_in_subtree(v) for k, v in t.items() if k != "_skills"
    )


def build_flat_nodes(skill_paths: dict[str, str]) -> list[Node]:
    """Return a DFS-ordered flat list of Nodes from {skill_name: repo-relative-path}."""
    tree: dict = {}
    for skill_name, path in skill_paths.items():
        parts = path.split("/")
        node = tree
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node.setdefault("_skills", []).append(skill_name)

    nodes: list[Node] = []

    def flatten(subtree: dict, prefix: str, depth: int, parent_idx: int) -> None:
        for dir_name in sorted(k for k in subtree if k != "_skills"):
            dir_path = f"{prefix}/{dir_name}" if prefix else dir_name
            n = _count_in_subtree(subtree[dir_name])
            s = "s" if n != 1 else ""
            dir_idx = len(nodes)
            if parent_idx >= 0:
                nodes[parent_idx].children.append(dir_idx)
            nodes.append(Node(
                label=f"{dir_name}/  [{n} skill{s}]",
                value=f"__dir__:{dir_path}",
                depth=depth,
                parent=parent_idx,
            ))
            flatten(subtree[dir_name], dir_path, depth + 1, dir_idx)

        for skill in sorted(subtree.get("_skills", [])):
            skill_idx = len(nodes)
            if parent_idx >= 0:
                nodes[parent_idx].children.append(skill_idx)
            nodes.append(Node(
                label=skill,
                value=skill,
                depth=depth,
                parent=parent_idx,
            ))

    flatten(tree, "", 0, -1)
    return nodes


def dir_state(idx: int, nodes: list[Node]) -> str:
    """Return 'all', 'some', or 'none' for a dir node based on its descendants."""
    node = nodes[idx]
    if not node.children:
        return "all" if node.checked else "none"
    checked = sum(
        1 for c in node.children
        if (nodes[c].is_dir and dir_state(c, nodes) == "all")
        or (not nodes[c].is_dir and nodes[c].checked)
    )
    if checked == 0:
        return "none"
    if checked == len(node.children):
        return "all"
    return "some"


def _set_subtree(idx: int, nodes: list[Node], checked: bool) -> None:
    nodes[idx].checked = checked
    for c in nodes[idx].children:
        _set_subtree(c, nodes, checked)


def toggle(idx: int, nodes: list[Node]) -> None:
    """Toggle a node. Dirs toggle their entire subtree; check-all if not all checked."""
    if nodes[idx].is_dir:
        _set_subtree(idx, nodes, dir_state(idx, nodes) != "all")
    else:
        nodes[idx].checked = not nodes[idx].checked


def tree_checkbox(prompt: str, skill_paths: dict[str, str]) -> list[str] | None:
    """Interactive hierarchical checkbox.

    Space on a directory selects/deselects every skill beneath it.
    Directories show tri-state: [ ] none, [-] partial, [x] all.

    Returns sorted skill names, or None if the user cancelled.
    """
    nodes = build_flat_nodes(skill_paths)
    if not nodes:
        return []

    state = {"cursor": 0, "cancelled": False}

    def get_tokens() -> list[tuple[str, str]]:
        lines: list[tuple[str, str]] = [("class:prompt", f"{prompt}\n")]
        for i, node in enumerate(nodes):
            indent = "  " * node.depth
            if node.is_dir:
                s = dir_state(i, nodes)
                cb = "[x]" if s == "all" else "[-]" if s == "some" else "[ ]"
            else:
                cb = "[x]" if node.checked else "[ ]"
            marker = "> " if i == state["cursor"] else "  "
            style = "class:cursor" if i == state["cursor"] else ""
            lines.append((style, f"{marker}{indent}{cb} {node.label}\n"))
        lines.append(("class:hint", "\n↑↓ move  Space toggle  Enter confirm  Ctrl-C cancel\n"))
        return lines

    kb = KeyBindings()

    @kb.add("up")
    def _(e): state["cursor"] = max(0, state["cursor"] - 1)

    @kb.add("down")
    def _(e): state["cursor"] = min(len(nodes) - 1, state["cursor"] + 1)

    @kb.add("space")
    def _(e): toggle(state["cursor"], nodes)

    @kb.add("enter")
    def _(e): e.app.exit()

    @kb.add("c-c")
    def _(e):
        state["cancelled"] = True
        e.app.exit()

    app = Application(
        layout=Layout(Window(FormattedTextControl(get_tokens, focusable=True))),
        key_bindings=kb,
        style=Style.from_dict({
            "cursor": "reverse",
            "prompt": "bold",
            "hint": "fg:ansigray italic",
        }),
        mouse_support=False,
    )
    app.run()

    if state["cancelled"]:
        return None
    return sorted(n.value for n in nodes if not n.is_dir and n.checked)
