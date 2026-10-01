# Client acceptance - 2.10.5

1. Deploy and confirm server_version 2.10.5 and contract 12.0 from health and a tool response.
2. Refresh tools/list in each client. Compare its input schemas with docs/tool-schemas.json and record the tool_schema_digest.
3. Run search_library with query="الحقيقة المحمدية", check_completeness=true, include_toc=true, include_topic_only=true, detail="full", keep_terms=["الحقيقة"]. Check five controls in both clients.
4. Run get_passage with match_id="b07-p166-c1180", context_mode="paragraph", max_chars=500. Check two controls.
5. Run list_books with projection="ids", book_ids=["b14","b41"]. Check the remaining two controls.
6. Retain each request ID, response, client name/version, server version and digest. Only then add the verified digest to CLIENT_SCHEMA_DIGESTS.

The included load.json proves a fresh local SDK client can call these controls. It does not prove ChatGPT or Claude refreshed. No credentials for deployment were supplied and the live service was not modified.
