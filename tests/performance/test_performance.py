"""
Performance and Load benchmarking tests for DPA (SDLC Quality & Performance Metrics).
Measures API latency, PPTX compiling execution times, and DB pool concurrency.
"""
import os
import time
import concurrent.futures
import pytest
from unittest.mock import MagicMock, patch

from services.db_connector import DBConnector
from services.report_generator import DPAReportGenerator
from tests.seeds.factories import make_full_report_data

pytestmark = pytest.mark.slow


# ── 1. API Response Latency Benchmarks ───────────────────────────────────────

def test_api_login_performance_benchmark(client, mock_db, sample_user):
    """
    Benchmark: Measure API latency of login requests.
    SDLC Quality Metric: Average response time should be < 50ms with mocked database.
    """
    conn, cur = mock_db
    cur.fetchone.return_value = sample_user

    iterations = 50
    latencies = []

    with patch("routers.auth.verify_password", return_value=True):
        login_payload = {"userId": "EMP001", "password": "test1234"}
        
        for _ in range(iterations):
            start_time = time.perf_counter()
            response = client.post("/api/auth/login", json=login_payload)
            end_time = time.perf_counter()
            
            assert response.status_code == 200
            latencies.append((end_time - start_time) * 1000)  # Convert to ms

    avg_latency = sum(latencies) / len(latencies)
    max_latency = max(latencies)
    min_latency = min(latencies)

    print(f"\n[API PERFORMANCE REPORT]")
    print(f"  Iterations    : {iterations}")
    print(f"  Avg Latency   : {avg_latency:.2f} ms")
    print(f"  Min Latency   : {min_latency:.2f} ms")
    print(f"  Max Latency   : {max_latency:.2f} ms")

    # API response time check for low-overhead mock runs
    assert avg_latency < 50.0, f"Average API latency is too high: {avg_latency:.2f} ms"


# ── 2. Report Compiler Execution Profiling ───────────────────────────────────

def test_report_generation_throughput_benchmark(minimal_template, tmp_output):
    """
    Benchmark: End-to-end report compiling speed (File I/O + Pillow + python-pptx).
    SDLC Quality Metric: Generation of standard single-slide reports should take < 150ms.
    """
    pr_no = "PR2024001"
    timepoint = "T0"
    lot = "MTDQS0906.1"
    
    report_data = make_full_report_data(pr_no=pr_no, lot=lot, timepoint=timepoint)
    
    iterations = 10
    compile_times = []

    with patch("services.report_generator.fetch_full_report_data", return_value=report_data), \
         patch("services.report_generator.TEMPLATE_PATH", str(minimal_template)):
        
        for _ in range(iterations):
            start_time = time.perf_counter()
            gen = DPAReportGenerator(pr_no, timepoint, lot, selected_sections={"EXTERNAL VISUAL": True}, revision="A")
            output_path, stats = gen.generate()
            end_time = time.perf_counter()
            
            assert stats["metadata_found"] is True
            compile_times.append((end_time - start_time) * 1000)
            
            # Clean up generated file
            if output_path and os.path.exists(output_path):
                os.remove(output_path)

    avg_compile = sum(compile_times) / len(compile_times)
    print(f"\n[REPORT COMPILER PERFORMANCE REPORT]")
    print(f"  Iterations    : {iterations}")
    print(f"  Avg Compile   : {avg_compile:.2f} ms")
    print(f"  Max Compile   : {max(compile_times):.2f} ms")

    # Standard compile check
    assert avg_compile < 150.0, f"Average report compile time is too slow: {avg_compile:.2f} ms"


# ── 3. Database Connection Pool Concurrency & Boundary Verification ──────────

def test_db_pool_concurrency_stress_benchmark():
    """
    Load Test: Simulate concurrent threads fetching and releasing database connections.
    SDLC Reliability Metric: Verify pool connection reuse under load (concurrency = 8, capacity = 10).
    """
    # Reset connection pool to ensure clean initialization with mock connect
    DBConnector._dpa_pool = None
    
    # Use side_effect to generate a brand new unique Mock connection for every connect call.
    # This prevents the pool from encountering "unkeyed connection" errors when releasing.
    with patch("psycopg2.connect", side_effect=lambda *a, **k: MagicMock()):
        # We will simulate 8 concurrent worker threads (within pool capacity of 10)
        # executing a total of 80 connection retrievals and releases.
        num_threads = 8
        connections_to_fetch = 80
        
        # Pre-initialize pool
        DBConnector.get_dpa_connection()
        
        def worker():
            conn = DBConnector.get_dpa_connection()
            if not conn:
                return False
            time.sleep(0.005)  # Simulate DB query delay
            DBConnector.release_dpa_connection(conn)
            return True

        start_time = time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(worker) for _ in range(connections_to_fetch)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]
        end_time = time.perf_counter()

    successful_requests = sum(1 for r in results if r)
    total_time = (end_time - start_time) * 1000

    print(f"\n[DATABASE POOL LOAD REPORT]")
    print(f"  Concurrent Threads: {num_threads}")
    print(f"  Total Requests    : {connections_to_fetch}")
    print(f"  Success Rate      : {successful_requests}/{connections_to_fetch} ({successful_requests/connections_to_fetch*100:.1f}%)")
    print(f"  Total Duration    : {total_time:.2f} ms")
    print(f"  Avg Request Time  : {total_time / connections_to_fetch:.2f} ms")

    assert successful_requests == connections_to_fetch, "Some database connection requests failed/timed out!"


def test_db_pool_boundary_exhaustion():
    """
    Boundary Test: Requesting more connections than the maximum pool capacity (10)
    should reject additional requests cleanly with None (PoolError caught internally).
    """
    DBConnector._dpa_pool = None
    
    with patch("psycopg2.connect", side_effect=lambda *a, **k: MagicMock()):
        # Spawns 15 concurrent threads requesting connections at the exact same instant
        num_threads = 15
        
        def fetch_only():
            conn = DBConnector.get_dpa_connection()
            # We don't release yet to hold the connection and force exhaustion
            return conn

        with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(fetch_only) for _ in range(num_threads)]
            connections = [f.result() for f in concurrent.futures.as_completed(futures)]

        granted = sum(1 for c in connections if c is not None)
        rejected = sum(1 for c in connections if c is None)

        print(f"\n[DATABASE POOL BOUNDARY REPORT]")
        print(f"  Threads Requesting: {num_threads}")
        print(f"  Connections Granted: {granted} (Max Capacity = 10)")
        print(f"  Requests Rejected  : {rejected}")

        assert granted == 10, f"Expected exactly 10 connections granted, got {granted}"
        assert rejected == 5, f"Expected exactly 5 connections rejected, got {rejected}"

        # Clean up pool connection releases to prevent resource leaks in other tests
        for conn in connections:
            if conn:
                DBConnector.release_dpa_connection(conn)
