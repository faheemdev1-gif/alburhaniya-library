import ast
import os
import unittest

from app.mcp_contract import (
    REQUIRED_TOOLS,
    SERVER_VERSION,
    TOOL_CONTRACT_ID,
    TOOL_CONTRACT_VERSION,
    validate_tool_names,
)


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SERVER_PATH = os.path.join(ROOT, "app", "mcp_server.py")


class MCPContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(SERVER_PATH, encoding="utf-8") as handle:
            cls.source = handle.read()
        cls.tree = ast.parse(cls.source)

    def test_hard_mcp_000_exact_five_tool_source_registry(self):
        registered = []
        for node in self.tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                if (
                    isinstance(decorator, ast.Call)
                    and isinstance(decorator.func, ast.Attribute)
                    and isinstance(decorator.func.value, ast.Name)
                    and decorator.func.value.id == "mcp"
                    and decorator.func.attr == "tool"
                ):
                    registered.append(node.name)
                    keywords = {item.arg: item.value for item in decorator.keywords}
                    self.assertIn("meta", keywords)
                    self.assertEqual(ast.unparse(keywords["meta"]), "TOOL_META")
        self.assertEqual(set(registered), REQUIRED_TOOLS)
        self.assertEqual(len(registered), 5)
        validate_tool_names(registered)

    def test_hard_mcp_001_get_passage_visibility(self):
        self.assertIn("def get_passage(", self.source)
        self.assertIn("match_ids: Optional[list[str]]", self.source)
        self.assertIn("DISCOVERABLE_TOOLS = validate_registered_tools(mcp)", self.source)

    def test_hard_contract_rejects_missing_unexpected_and_duplicate_names(self):
        with self.assertRaises(RuntimeError):
            validate_tool_names(REQUIRED_TOOLS - {"get_passage"})
        with self.assertRaises(RuntimeError):
            validate_tool_names([*REQUIRED_TOOLS, "read_book"])
        with self.assertRaises(RuntimeError):
            validate_tool_names([*REQUIRED_TOOLS, "get_page"])

    def test_hard_search_schema_source_contract(self):
        search = next(
            node for node in self.tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "search_library"
        )
        arguments = {arg.arg for arg in search.args.args}
        self.assertTrue({
            "queries", "book_scope", "include_counts", "qasida_number",
            "expand_top", "expand_chars", "min_score", "match_mode", "mode",
            "whole_word", "count_basis", "min_tier",
        }.issubset(arguments))
        defaults = dict(zip(
            [arg.arg for arg in search.args.args[-len(search.args.defaults):]],
            search.args.defaults,
        ))
        self.assertEqual(ast.literal_eval(defaults["context_chars"]), 60)
        annotation = ast.unparse(next(
            arg.annotation for arg in search.args.args if arg.arg == "match_mode"
        ))
        self.assertEqual(
            set(ast.literal_eval(value) for value in ast.walk(ast.parse(annotation)) if isinstance(value, ast.Constant) and isinstance(value.value, str)),
            {"auto", "exact", "terms", "hybrid", "lexeme"},
        )
        self.assertIn('ResponseMode = Literal["compact", "ultra_compact"]', self.source)

    def test_hard_versioned_instructions_explain_incomplete_discovery(self):
        self.assertEqual(SERVER_VERSION, "2.10.13")
        self.assertEqual(TOOL_CONTRACT_ID, "alburhaniya-tools-v13")
        self.assertEqual(TOOL_CONTRACT_VERSION, "13.0")
        self.assertIn("mcp._mcp_server.version = SERVER_VERSION", self.source)
        self.assertIn("connector discovery is incomplete", self.source)
        self.assertIn("get_passage for the precise passage", self.source)
        self.assertIn("surface text is authoritative", self.source.lower())
        self.assertIn("abbreviated key ep", self.source)
        self.assertIn("block_type as blk", self.source)
        self.assertIn("searchable_by_default=false", self.source)
        self.assertIn("whole-word matching", self.source)
        self.assertIn("Counts declare count_basis", self.source)
        self.assertIn("literal_matching_pages", self.source)
        self.assertIn("reformulated_query", self.source)
        self.assertNotIn('response["total_hits"]', self.source)

    def test_hard_schema_parity_includes_research_integrity_controls(self):
        passage = next(
            node for node in self.tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "get_passage"
        )
        self.assertTrue({
            "match_id", "match_ids", "stable_id", "qasida_number",
            "include_parallels", "parallel_limit", "context_mode", "max_chars",
        }.issubset({arg.arg for arg in passage.args.args}))
        page = next(
            node for node in self.tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "get_page"
        )
        defaults = dict(zip(
            [arg.arg for arg in page.args.args[-len(page.args.defaults):]],
            page.args.defaults,
        ))
        self.assertEqual(ast.literal_eval(defaults["max_chars"]), 20000)

    def test_hard_mcp_only_clients_receive_live_contract_evidence(self):
        self.assertIn('"connector_contract": contract_metadata(REQUIRED_TOOLS)', self.source)
        self.assertIn('"corpus_contract": corpus_contract_snapshot()', self.source)
        self.assertIn('book["connector_contract"] = contract_metadata(REQUIRED_TOOLS)', self.source)
        self.assertGreaterEqual(self.source.count("qasida_number=qasida_number"), 4)
        self.assertIn("and qasida_number is None", self.source)


if __name__ == "__main__":
    unittest.main()
