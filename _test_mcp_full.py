"""Full MCP integration test using Python 3.11 with real mcp SDK."""
import sys
import os
import json
import asyncio

# Setup paths
sys.path.insert(0, os.path.join(os.getcwd(), "mcp-wrapper"))
sys.path.insert(0, os.getcwd())

# Load env
from dotenv import load_dotenv
load_dotenv()

results = {}

# Test 1: Import the real mcp SDK
print("=" * 60)
print("TEST 1: Import mcp SDK (FastMCP)")
print("=" * 60)
try:
    from mcp.server import FastMCP
    print("  FastMCP imported: OK")
    results["1_mcp_import"] = "PASS"
except Exception as e:
    print(f"  FAIL: {e}")
    results["1_mcp_import"] = f"FAIL: {e}"
    sys.exit(1)

# Test 2: Import server.py (registers all tools via FastMCP)
print("\n" + "=" * 60)
print("TEST 2: Import server.py (25 tools registered)")
print("=" * 60)
try:
    import server
    # FastMCP registers tools internally
    assert hasattr(server, "mcp")
    assert server.mcp.name == "job-search-bot"
    print(f"  Server name: {server.mcp.name}")
    results["2_server_import"] = "PASS"
except Exception as e:
    print(f"  FAIL: {e}")
    results["2_server_import"] = f"FAIL: {e}"

# Test 3: Import tools.py
print("\n" + "=" * 60)
print("TEST 3: Import tools.py (security helpers present)")
print("=" * 60)
try:
    import tools
    assert hasattr(tools, "ALLOWED_PROFILE_KEYS")
    assert hasattr(tools, "_clamp")
    assert hasattr(tools, "_require_non_empty")
    print(f"  ALLOWED_PROFILE_KEYS: {tools.ALLOWED_PROFILE_KEYS}")
    print(f"  _clamp, _require_non_empty: present")
    results["3_tools_import"] = "PASS"
except Exception as e:
    print(f"  FAIL: {e}")
    results["3_tools_import"] = f"FAIL: {e}"

# Test 4: Storage CRUD
print("\n" + "=" * 60)
print("TEST 4: storage.py CRUD operations")
print("=" * 60)
try:
    import storage
    storage.init_wrapper_db()
    # Bookmark
    assert storage.save_bookmark("test_1", "Job A", "Co A", "http://a.com")
    assert not storage.save_bookmark("test_1", "Job A", "Co A", "http://a.com")  # duplicate
    assert len(storage.get_bookmarks()) == 1
    assert storage.remove_bookmark("test_1")
    assert not storage.remove_bookmark("test_1")  # already gone
    # Interview
    iid = storage.add_interview("j1", "Stripe", "SRE", "2026-12-01T15:00", "")
    assert iid > 0
    # Reminder
    rid = storage.add_reminder("Follow up", "2026-12-05")
    assert rid > 0
    assert len(storage.get_reminders()) == 1
    storage.dismiss_reminder(rid)
    assert len(storage.get_reminders()) == 0
    print("  Bookmarks: OK")
    print("  Interviews: OK")
    print("  Reminders: OK")
    results["4_storage"] = "PASS"
except Exception as e:
    print(f"  FAIL: {e}")
    results["4_storage"] = f"FAIL: {e}"

# Test 5: Input validation
print("\n" + "=" * 60)
print("TEST 5: Input validation (security)")
print("=" * 60)
try:
    # _require_non_empty
    err = tools._require_non_empty({"title": "", "company": "X"}, ["title", "company"])
    assert err is not None and "title" in err
    err = tools._require_non_empty({"title": "OK", "company": "OK"}, ["title", "company"])
    assert err is None

    # _clamp
    assert tools._clamp(200, 1, 90) == 90
    assert tools._clamp(-5, 1, 90) == 1
    assert tools._clamp(50, 1, 90) == 50

    # update_profile key whitelist
    result = asyncio.run(tools.tool_update_profile({"key": "malicious_key", "value": "bad"}))
    data = json.loads(result)
    assert "error" in data and "not allowed" in data["error"]
    print("  _require_non_empty: OK")
    print("  _clamp: OK")
    print("  update_profile whitelist: OK")
    results["5_validation"] = "PASS"
except Exception as e:
    print(f"  FAIL: {e}")
    results["5_validation"] = f"FAIL: {e}"

# Test 6: Tier 1 tools — get_platforms (no API calls)
print("\n" + "=" * 60)
print("TEST 6: get_platforms (no API call)")
print("=" * 60)
try:
    result = asyncio.run(tools.tool_get_platforms({}))
    data = json.loads(result)
    assert "apify_boards" in data
    assert "anchor_skill" in data
    print(f"  Anchor: {data['anchor_skill']}")
    print(f"  Boards: {data['apify_boards']}")
    results["6_get_platforms"] = "PASS"
except Exception as e:
    print(f"  FAIL: {e}")
    results["6_get_platforms"] = f"FAIL: {e}"

# Test 7: run_health_check
print("\n" + "=" * 60)
print("TEST 7: run_health_check")
print("=" * 60)
try:
    result = asyncio.run(tools.tool_run_health_check({}))
    data = json.loads(result)
    assert "overall" in data
    assert "gemini_api_key" in data
    # Verify no actual key values leaked
    for k, v in data.items():
        if "key" in k or "password" in k:
            assert v in ("set", "MISSING"), f"Key '{k}' leaked value: {v}"
    print(f"  Overall: {data['overall']}")
    print(f"  No credentials leaked: OK")
    results["7_health_check"] = "PASS"
except Exception as e:
    print(f"  FAIL: {e}")
    results["7_health_check"] = f"FAIL: {e}"

# Test 8: export_data (empty DB)
print("\n" + "=" * 60)
print("TEST 8: export_data (format validation)")
print("=" * 60)
try:
    # Valid format
    result = asyncio.run(tools.tool_export_data({"format": "json"}))
    data = json.loads(result)
    assert data["format"] == "json"
    # Invalid format defaults to json
    result = asyncio.run(tools.tool_export_data({"format": "xml"}))
    data = json.loads(result)
    assert data["format"] == "json", "Unknown format should default to json"
    print("  format=json: OK")
    print("  format=xml → defaults to json: OK")
    results["8_export_data"] = "PASS"
except Exception as e:
    print(f"  FAIL: {e}")
    results["8_export_data"] = f"FAIL: {e}"

# Test 9: score_job validation (empty fields rejected)
print("\n" + "=" * 60)
print("TEST 9: score_job input validation")
print("=" * 60)
try:
    result = asyncio.run(tools.tool_score_job({"title": "", "company": "X", "url": "http://x", "text": "desc"}))
    data = json.loads(result)
    assert "error" in data and "title" in data["error"]
    print("  Empty title rejected: OK")
    results["9_score_validation"] = "PASS"
except Exception as e:
    print(f"  FAIL: {e}")
    results["9_score_validation"] = f"FAIL: {e}"

# Test 10: Stub tools return pending
print("\n" + "=" * 60)
print("TEST 10: Stub tools return pending status")
print("=" * 60)
try:
    result = asyncio.run(tools.tool_compare_jobs({"job_ids": ["a", "b"]}))
    data = json.loads(result)
    assert data["status"] == "pending"
    result = asyncio.run(tools.tool_get_company_info({"company": "X"}))
    data = json.loads(result)
    assert data["status"] == "pending"
    result = asyncio.run(tools.tool_pause_bot({}))
    data = json.loads(result)
    assert data["status"] == "pending"
    result = asyncio.run(tools.tool_resume_bot                                                                                                                         )
    data = json.loads(result)
    assert data["status"] == "pending"
    print("  compare_jobs: pending ✓")
    print("  get_company_info: pending ✓")
    print("  pause_bot: pending ✓")
    print("  resume_bot: pending ✓")
    results["10_stubs"] = "PASS"
except Exception as e:
    print(f"  FAIL: {e}")
    results["10_stubs"] = f"FAIL: {e}"

# Test 11: No Tier 4 tools present
print("\n" + "=" * 60)
print("TEST 11: No Tier 4 tools (auto-apply, etc.)")
print("=" * 60)
try:
    banned = ["apply_to_job", "batch_apply", "withdraw_application", "upload_resume",
              "tailor_resume", "generate_counter_offer", "get_market_rate",
              "log_offer", "compare_offers", "set_rate_limit"]
    # Check tools.py doesn't have any banned handlers
    found = [t for t in banned if hasattr(tools, f"tool_{t}")]
    assert not found, f"Banned tool handlers found: {found}"
    print("  No banned tools present: OK")
    results["11_no_tier4"] = "PASS"
except Exception as e:
    print(f"  FAIL: {e}")
    results["11_no_tier4"] = f"FAIL: {e}"

# Summary
print("\n" + "=" * 60)
print("SUMMARY")
print("=" * 60)
passed = sum(1 for v in results.values() if v == "PASS")
failed = sum(1 for v in results.values() if v.startswith("FAIL"))
for name, result in results.items():
    icon = "✓" if result == "PASS" else "✗"
    print(f"  {icon} {name}: {result}")
print(f"\n  {passed}/{len(results)} passed, {failed} failed")

# Cleanup
if os.path.exists(storage.WRAPPER_DB_PATH):
    os.unlink(storage.WRAPPER_DB_PATH)

sys.exit(1 if failed else 0)
