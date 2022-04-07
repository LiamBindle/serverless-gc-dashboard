#
# Run `python -m pytest` to run these tests.
#

import json
from .geoschem_testing import *


def test_primary_key_classification():
    assert PrimaryKeyClassification(primary_key="gchp-1Mon-13.4.0-rc.3.bd").classification == "GCHP Simulation"
    assert PrimaryKeyClassification(primary_key="gchp-1Mon-13.4.0-rc.3").classification == "GCHP Simulation"
    assert PrimaryKeyClassification(primary_key="gchp-c24-1Mon-13.4.0-rc.3").classification == "GCHP Simulation"
    assert PrimaryKeyClassification(primary_key="gcc-1Hr-483b659.bd").classification == "GC-Classic Simulation"
    assert PrimaryKeyClassification(primary_key="gcc-1Hr-483b659").classification == "GC-Classic Simulation"
    assert PrimaryKeyClassification(primary_key="gcc-4x5-1Hr-483b659").classification == "GC-Classic Simulation"


def test_parsing_scan():
    with open("test_data/scan_results.json") as f:
        response = json.load(f)['Items']
    entries = parse_scan_response(response)

    an_entry_that_should_exist = RegistryEntry(
        primary_key="gcc-1Hr-f9a901a.bd", creation_date="2022-03-24", execution_status="FAILED",
        execution_site="AWS", description="1Hr gcc benchmark simulation using 'f9a901a'",
        s3_uri="s3://benchmarks-cloud/benchmarks/1Hr/gcc/gcc-1Hr-f9a901a.bd",

    )
    assert any([entry == an_entry_that_should_exist for entry in entries])


def test_parsing_query():
    with open("test_data/query_result.json") as f:
        response = [json.load(f)['Item']]
    entries = parse_query_response_astype(response, RegistryEntrySimulation)

    an_entry_that_should_exist = RegistryEntrySimulation(
        primary_key="gchp-1Mon-13.4.0-rc.3.bd", creation_date="2022-03-28", execution_status="SUCCESSFUL",
        execution_site="AWS", description="1Mon gchp benchmark simulation using '13.4.0-rc.3'",
        s3_uri="s3://benchmarks-cloud/benchmarks/1Mon/gchp/gchp-1Mon-13.4.0-rc.3.bd",
    )
    an_entry_that_should_exist.setup_run_directory = RegistryEntryStage(
        name="SetupRunDirectory", completed=True, log_file="http://s3.amazonaws.com/benchmarks-cloud/benchmarks/1Mon/gchp/gchp-1Mon-13.4.0-rc.3.bd/SetupRunDirectory.txt",
        start_time="2022-03-28T17:45:04+0000", end_time="2022-03-28T18:00:15+0000", metadata="{}",
        artifacts=["s3://benchmarks-cloud/benchmarks/1Mon/gchp/gchp-1Mon-13.4.0-rc.3.bd/SetupRunDirectory_RunDirectory.tar.gz"],
        public_artifacts=[],
    )
    an_entry_that_should_exist.run_simulation_directory = RegistryEntryStage(
        name="RunGCHP", completed=True,
        log_file="http://s3.amazonaws.com/benchmarks-cloud/benchmarks/1Mon/gchp/gchp-1Mon-13.4.0-rc.3.bd/RunGCHP.txt",
        start_time="2022-03-28T19:26:04+0000", end_time="2022-03-29T01:45:15+0000", metadata="{}",
        artifacts=[
            "s3://benchmarks-cloud/benchmarks/1Mon/gchp/gchp-1Mon-13.4.0-rc.3.bd/RunGCHP_OutputDir.tar.gz"],
        public_artifacts=[],
    )
    assert entries[0] == an_entry_that_should_exist

def test_parsing_diff_query():
    with open("test_data/diff_query_result.json") as f:
        response = [json.load(f)['Item']]
    entries = parse_query_response_astype(response, RegistryEntryDiff)

    an_entry_that_should_exist = RegistryEntryDiff(
        primary_key="diff-gcc-1Hr-3f70328.bd-gcc-1Hr-3f70328.bd", creation_date="2022-04-04", execution_status="SUCCESSFUL",
        execution_site="AWS", description="1Hr Benchmark plot creation (ref: 'gcc-1Hr-3f70328.bd'; dev:'gcc-1Hr-3f70328.bd')",
        s3_uri="s3://benchmarks-cloud/diff-plots/1Hr/diff-gcc-1Hr-3f70328.bd-gcc-1Hr-3f70328.bd",
    )
    an_entry_that_should_exist.run_gcpy_stage = RegistryEntryStage(
        name="CreateBenchmarkPlots", completed=True, log_file="http://s3.amazonaws.com/benchmarks-cloud/diff-plots/1Hr/diff-gcc-1Hr-3f70328.bd-gcc-1Hr-3f70328.bd/CreateBenchmarkPlots.txt",
        start_time="2022-04-04T17:22:44+0000", end_time="2022-04-04T17:23:32+0000", metadata="{}",
        artifacts=[],
        public_artifacts=[
            "http://s3.amazonaws.com/benchmarks-cloud/diff-plots/1Hr/diff-gcc-1Hr-3f70328.bd-gcc-1Hr-3f70328.bd/BenchmarkResults/Tables/Emission_totals.txt",
            "http://s3.amazonaws.com/benchmarks-cloud/diff-plots/1Hr/diff-gcc-1Hr-3f70328.bd-gcc-1Hr-3f70328.bd/BenchmarkResults/Tables/GlobalMass_Trop.txt",
            "http://s3.amazonaws.com/benchmarks-cloud/diff-plots/1Hr/diff-gcc-1Hr-3f70328.bd-gcc-1Hr-3f70328.bd/BenchmarkResults/Tables/GlobalMass_TropStrat.txt",
            "http://s3.amazonaws.com/benchmarks-cloud/diff-plots/1Hr/diff-gcc-1Hr-3f70328.bd-gcc-1Hr-3f70328.bd/BenchmarkResults/Tables/Inventory_totals.txt",
            "http://s3.amazonaws.com/benchmarks-cloud/diff-plots/1Hr/diff-gcc-1Hr-3f70328.bd-gcc-1Hr-3f70328.bd/BenchmarkResults/Tables/OH_metrics.txt",
        ],
    )

    assert entries[0] == an_entry_that_should_exist
