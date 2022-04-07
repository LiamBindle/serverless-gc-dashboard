import dataclasses
import re
import itertools
import typing
import boto3
import jinja2

# This file could be split into seperate model.py, view.py, and controller.py modules.

#== MODEL ==

def dynamodb_get_string(key, data):
    return data.get(key, {}).get("S", None)
def dynamodb_get_list_of_strings(key, data):
    return [item.get("S", None) for item in data.get(key, {}).get("L", [])]
def dynamodb_get_map(key, data):
    return data.get(key, {}).get("M", None)
def dynamodb_get_bool(key, data):
    return data.get(key, {}).get("BOOL", None)


@dataclasses.dataclass
class PrimaryKeyClassification:
    classification: str = None
    api: str = None
    primary_key: dataclasses.InitVar[str] = None
    code_url: str = None
    commit_id: str = None

    def __post_init__(self, primary_key):
        semver_re = r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?"
        commit_hash_re = r"[0-9a-f]{7}"
        simulation_re = fr"(gcc|gchp)-((2x25|2x2\.5|4x5|c24|c48|c90|c180)-)?(1Mon|1Hr)-({semver_re}|{commit_hash_re})(\.bd)?"
        if re.match(fr"^{simulation_re}$", primary_key):
            if re.match(r"^gchp", primary_key):
                self.classification = "GCHP Simulation"
                repo = "GCHP"
            else:
                self.classification = "GC-Classic Simulation"
                repo="GCClassic"
            semver_tag = re.search(semver_re, primary_key)
            if semver_tag:
                self.commit_id = semver_tag.group(0)
                self.commit_id = self.commit_id.removesuffix(".bd")  # for old entries
                self.code_url = f"https://github.com/geoschem/{repo}/tree/{self.commit_id}"
            commit_hash = re.search(commit_hash_re, primary_key)
            if commit_hash:
                self.commit_id = commit_hash.group(0)
                self.commit_id = self.commit_id.removesuffix(".bd")  # for old entries
                self.code_url = f"https://github.com/geoschem/{repo}/commit/{self.commit_id}"
            self.api = "simulation"
        elif re.match(fr"^diff-{simulation_re}-{simulation_re}$", primary_key):
            self.classification = "Difference Plots"
            self.api = "difference"
        else:
            self.classification = "Unknown"
            self.api = None


@dataclasses.dataclass
class RegistryEntry:
    primary_key: str = None
    creation_date: str = None
    execution_status: str = None
    execution_site: str = None
    s3_uri: str = None
    description: str = None
    primary_key_classification: PrimaryKeyClassification = None
    dynamodb_scan_result: dataclasses.InitVar[dict] = None

    def __post_init__(self, dynamodb_scan_result):
        if dynamodb_scan_result is not None:
            self.primary_key = dynamodb_get_string("InstanceID", dynamodb_scan_result)
            self.creation_date = dynamodb_get_string("CreationDate", dynamodb_scan_result)
            self.execution_status = dynamodb_get_string("ExecStatus", dynamodb_scan_result)
            self.execution_site = dynamodb_get_string("Site", dynamodb_scan_result)
            self.s3_uri = dynamodb_get_string("S3Uri", dynamodb_scan_result)
            self.description = dynamodb_get_string("Description", dynamodb_scan_result)
        self.primary_key_classification = PrimaryKeyClassification(primary_key=self.primary_key)


@dataclasses.dataclass
class RegistryEntryStage:
    name: str = None
    completed: bool = None
    log_file: str = None
    start_time: str = None
    end_time: str = None
    artifacts: typing.List[str] = dataclasses.field(default_factory=list)
    public_artifacts: typing.List[str] = dataclasses.field(default_factory=list)
    metadata: str = "{}"
    dynamodb_stage_result: dataclasses.InitVar[dict] = None

    def __post_init__(self, dynamodb_stage_result):
        if dynamodb_stage_result is not None:
            self.name = dynamodb_get_string("Name", dynamodb_stage_result)
            self.log_file = dynamodb_get_string("Log", dynamodb_stage_result)
            self.completed = dynamodb_get_bool("Completed", dynamodb_stage_result)
            self.start_time = dynamodb_get_string("StartTime", dynamodb_stage_result)
            self.end_time = dynamodb_get_string("EndTime", dynamodb_stage_result)
            self.artifacts = dynamodb_get_list_of_strings("Artifacts", dynamodb_stage_result)
            self.public_artifacts = dynamodb_get_list_of_strings("PublicArtifacts", dynamodb_stage_result)
            self.metadata = dynamodb_get_string("Metadata", dynamodb_stage_result)


@dataclasses.dataclass
class RegistryEntrySimulation(RegistryEntry):
    setup_run_directory: RegistryEntryStage = None
    run_simulation_directory: RegistryEntryStage = None
    dynamodb_query_result: dataclasses.InitVar[dict] = None

    def __post_init__(self, dynamodb_scan_result, dynamodb_query_result):
        if dynamodb_query_result is not None:
            super().__post_init__(dynamodb_query_result)
            stages = dynamodb_query_result["Stages"]["L"]
            self.setup_run_directory = RegistryEntryStage(dynamodb_stage_result=stages[0].get("M", {}) if len(stages) >= 1 else {})
            self.run_simulation_directory = RegistryEntryStage(dynamodb_stage_result=stages[1].get("M", {}) if len(stages) >= 2 else {})
        else:
            super().__post_init__(dynamodb_scan_result)


@dataclasses.dataclass
class RegistryEntryDiff(RegistryEntry):
    run_gcpy_stage: RegistryEntryStage = None
    emissions_totals_link: str = None
    global_mass_trop_link: str = None
    global_mass_tropstrat_link: str = None
    inventory_totals_link: str = None
    oh_metrics_link: str = None
    dynamodb_query_result: dataclasses.InitVar[dict] = None

    def __post_init__(self, dynamodb_scan_result, dynamodb_query_result):
        if dynamodb_query_result is not None:
            super().__post_init__(dynamodb_query_result)
            stages = dynamodb_query_result["Stages"]["L"]
            self.run_gcpy_stage = RegistryEntryStage(dynamodb_stage_result=stages[0].get("M", {}) if len(stages) >= 1 else {})
        else:
            super().__post_init__(dynamodb_scan_result)


#== VIEW ==

html_page_begin="""<!DOCTYPE html>
<html lang="en">
<head>
    <title>GEOS-Chem Testing Dashboard</title>
    <style>th,td {
            text-align:left;
            vertical-align:top;
            font-family:monospace;
            padding-left:2em;
        }
    </style>
    <meta charset="UTF-8">
</head>
<body>
"""
html_page_end="""</body>
</html>
"""

dashboard_template="""
<h2>Difference Plots</h2>
<table>
    <tr><th>ID</th><th>Date</th><th>Status</th><th>Site</th></tr>
{%- for entry in entries -%}
    {%- if entry.primary_key_classification.classification == 'Difference Plots' -%}
    <tr>
        {%- if entry.primary_key_classification.api is not none -%}
        <td><a href="{{ entry.primary_key_classification.api }}?primary_key={{ entry.primary_key }}">{{ entry.primary_key }}</a></td>
        {%- else -%}
        <td>{{ entry.primary_key }}</td>
        {%- endif -%}
        <td>{{ entry.creation_date }}</td>
        <td>{{ entry.execution_status }}</td>
        <td>{{ entry.execution_site }}</td>
    </tr>
    {%- endif -%}
{%- endfor -%}
</table>

<hr>
<h2>GCHP Simulations</h2>
<table>
    <tr><th>Simulation ID</th><th>Date</th><th>Status</th><th>Code Url</th><th>Site</th></tr>
{%- for entry in entries -%}
    {%- if entry.primary_key_classification.classification == 'GCHP Simulation' -%}
    <tr>
        {%- if entry.primary_key_classification.api is not none -%}
        <td><a href="{{ entry.primary_key_classification.api }}?primary_key={{ entry.primary_key }}">{{ entry.primary_key }}</a></td>
        {%- else -%}
        <td>{{ entry.primary_key }}</td>
        {%- endif -%}
        <td>{{ entry.creation_date }}</td>
        <td>{{ entry.execution_status }}</td>
        <td><a href="{{ entry.primary_key_classification.code_url }}">{{ entry.primary_key_classification.commit_id }}</a></td>
        <td>{{ entry.execution_site }}</td>
    </tr>
    {%- endif -%}
{%- endfor -%}
</table>

<hr>
<h2>GC-Classic Simulations</h2>
<table>
    <tr><th>Simulation ID</th><th>Date</th><th>Status</th><th>Code Url</th><th>Site</th></tr>
{%- for entry in entries -%}
    {%- if entry.primary_key_classification.classification == 'GC-Classic Simulation' -%}
    <tr>
        {%- if entry.primary_key_classification.api is not none -%}
        <td><a href="{{ entry.primary_key_classification.api }}?primary_key={{ entry.primary_key }}">{{ entry.primary_key }}</a></td>
        {%- else -%}
        <td>{{ entry.primary_key }}</td>
        {%- endif -%}
        <td>{{ entry.creation_date }}</td>
        <td>{{ entry.execution_status }}</td>
        <td><a href="{{ entry.primary_key_classification.code_url }}">{{ entry.primary_key_classification.commit_id }}</a></td>
        <td>{{ entry.execution_site }}</td>
    </tr>
    {%- endif -%}
{%- endfor -%}
</table>
"""

simulation_template="""
<table>
    <tr><th>Name</th><th>Value</th></tr>
    <tr>
        <td>Primary Key</td>
        <td>{{ entry.primary_key }}</td>
    </tr>
    <tr>
        <td>Creation Date</td>
        <td>{{ entry.creation_date }}</td>
    </tr>
    <tr>
        <td>Execution Status</td>
        <td>{{ entry.execution_status }}</td>
    </tr>
    <tr>
        <td>Execution Site</td>
        <td>{{ entry.execution_site }}</td>
    </tr>
    <tr>
        <td>S3 Uri Site</td>
        <td>{{ entry.s3_uri }}</td>
    </tr>
    <tr>
        <td>Description</td>
        <td>{{ entry.description }}</td>
    </tr>
    <tr>
        <td>Setup Run Directory</td>
        {%- if entry.setup_run_directory is not none -%}
        <td>
            <table>
                <tr>
                    <td>Completed</td>
                    <td>{{ entry.setup_run_directory.completed }}</td>
                </tr>
                <tr>
                    <td>Log File</td>
                    <td><a href="{{ entry.setup_run_directory.log_file }}">{{ entry.setup_run_directory.log_file }}</a></td>
                </tr>
                <tr>
                    <td>Start Time</td>
                    <td>{{ entry.setup_run_directory.start_time }}</td>
                </tr>
                <tr>
                    <td>End Time</td>
                    <td>{{ entry.setup_run_directory.end_time }}</td>
                </tr>
                <tr>
                    <td>Public Artifacts</td>
                    <td>
                    {%- for artifact in entry.setup_run_directory.public_artifacts -%}
                        <a href="{{ artifact }}">{{ artifact }}</a><br>
                    {%- endfor -%}
                    </td>
                </tr>
                <tr>
                    <td>Stage Artifacts</td>
                    <td>
                    {%- for artifact in entry.setup_run_directory.artifacts -%}
                        {{ artifact }}<br>
                    {%- endfor -%}
                    </td>
                </tr>
                <tr>
                    <td>Metadata</td>
                    <td>{{ entry.setup_run_directory.metadata }}</td>
                </tr>
            </table>
        </td>
        {%- else -%}
        <td>n/a</td>
        {%- endif -%}
        
        <tr>
        <td>Run Simulation</td>
        {%- if entry.run_simulation_directory is not none -%}
        <td>
            <table>
                <tr>
                    <td>Completed</td>
                    <td>{{ entry.run_simulation_directory.completed }}</td>
                </tr>
                <tr>
                    <td>Log File</td>
                    <td><a href="{{ entry.run_simulation_directory.log_file }}">{{ entry.run_simulation_directory.log_file }}</a></td>
                </tr>
                <tr>
                    <td>Start Time</td>
                    <td>{{ entry.run_simulation_directory.start_time }}</td>
                </tr>
                <tr>
                    <td>End Time</td>
                    <td>{{ entry.run_simulation_directory.end_time }}</td>
                </tr>
                <tr>
                    <td>Public Artifacts</td>
                    <td>
                    {%- for artifact in entry.run_simulation_directory.public_artifacts -%}
                        <a href="{{ artifact }}">{{ artifact }}</a><br>
                    {%- endfor -%}
                    </td>
                </tr>
                <tr>
                    <td>Stage Artifacts</td>
                    <td>
                    {%- for artifact in entry.run_simulation_directory.artifacts -%}
                        {{ artifact }}<br>
                    {%- endfor -%}
                    </td>
                </tr>
                <tr>
                    <td>Metadata</td>
                    <td>{{ entry.run_simulation_directory.metadata }}</td>
                </tr>
            </table>
        </td>
        {%- else -%}
        <td>n/a</td>
        {%- endif -%}
    </tr>
</table>
"""

difference_template = """
<table>
    <tr><th>Name</th><th>Value</th></tr>
    <tr>
        <td>Primary Key</td>
        <td>{{ entry.primary_key }}</td>
    </tr>
    <tr>
        <td>Creation Date</td>
        <td>{{ entry.creation_date }}</td>
    </tr>
    <tr>
        <td>Execution Status</td>
        <td>{{ entry.execution_status }}</td>
    </tr>
    <tr>
        <td>Execution Site</td>
        <td>{{ entry.execution_site }}</td>
    </tr>
    <tr>
        <td>S3 Uri Site</td>
        <td>{{ entry.s3_uri }}</td>
    </tr>
    <tr>
        <td>Description</td>
        <td>{{ entry.description }}</td>
    </tr>
    <tr>
        <td>GCPy Output</td>
        {%- if entry.run_gcpy_stage is not none -%}
        <td>
            <table>
                <tr>
                    <td>Completed</td>
                    <td>{{ entry.run_gcpy_stage.completed }}</td>
                </tr>
                <tr>
                    <td>Log File</td>
                    <td><a href="{{ entry.run_gcpy_stage.log_file }}">{{ entry.run_gcpy_stage.log_file }}</a></td>
                </tr>
                <tr>
                    <td>Start Time</td>
                    <td>{{ entry.run_gcpy_stage.start_time }}</td>
                </tr>
                <tr>
                    <td>End Time</td>
                    <td>{{ entry.run_gcpy_stage.end_time }}</td>
                </tr>
                <tr>
                    <td>Public Artifacts</td>
                    <td>
                    {%- for artifact in entry.run_gcpy_stage.public_artifacts -%}
                        <a href="{{ artifact }}">{{ artifact }}</a><br>
                    {%- endfor -%}
                    </td>
                </tr>
                <tr>
                    <td>Stage Artifacts</td>
                    <td>
                    {%- for artifact in entry.run_gcpy_stage.artifacts -%}
                        {{ artifact }}<br>
                    {%- endfor -%}
                    </td>
                </tr>
                <tr>
                    <td>Metadata</td>
                    <td>{{ entry.run_gcpy_stage.metadata }}</td>
                </tr>
            </table>
        </td>
        {%- else -%}
        <td>n/a</td>
        {%- endif -%}
    </tr>
</table>
"""


def fill_template(template_str, **kwargs):
    env = jinja2.Environment()
    html_page = html_page_begin + env.from_string(template_str).render(**kwargs) + html_page_end
    html_page = html_page.replace("SUCCESSFUL", '<span style="color:green">✅ SUCCESSFUL</span>')
    html_page = html_page.replace("IN_PROGRESS", '<span style="color:orange">⌛ IN_PROGRESS</span>')
    html_page = html_page.replace("FAILED", '<span style="color:red">❌ FAILED</span>')
    return html_page


def get_dashboard_page(sorted_entries):
    return fill_template(dashboard_template, entries=sorted_entries)


def get_simulation_page(entry):
    return fill_template(simulation_template, entry=entry)


def get_difference_page(entry):
    return fill_template(difference_template, entry=entry)


#== CONTROLLER ==
TABLE_NAME="geoschem_testing"

def get_dynamodb_client():
    role_arn = "arn:aws:iam::753979222379:role/washu_cross_account_role"
    client = boto3.client('sts')
    response = client.assume_role(RoleArn=role_arn,
                                  RoleSessionName='RoleSessionName',
                                  DurationSeconds=900)
    dynamodb_client = boto3.client('dynamodb', region_name='us-east-1',
                                   aws_access_key_id=response['Credentials']['AccessKeyId'],
                                   aws_secret_access_key=response['Credentials']['SecretAccessKey'],
                                   aws_session_token=response['Credentials']['SessionToken'])
    return dynamodb_client


def parse_scan_response(response):
    entries = []
    for item in response:
        entries.append(RegistryEntry(dynamodb_scan_result=item))
    return entries


def scan_registry():
    client = get_dynamodb_client()
    response = client.scan(
        TableName=TABLE_NAME,
        Limit=50,
        ProjectionExpression='InstanceID,CreationDate,ExecStatus,Site,Description',
    )
    return parse_scan_response(response['Items'])


def parse_query_response_astype(query_results, astype):
    entries = []
    for item in query_results:
        entries.append(astype(dynamodb_query_result=item))
    return entries


def query_registry(items, astype):
    client = get_dynamodb_client()

    if isinstance(items, str):
        request_keys = [{"InstanceID": {"S": items}}]
    else:
        request_keys = [{"InstanceID": {"S": item.primary_key}} for item in items]
    response = client.batch_get_item(
        RequestItems={TABLE_NAME: {'Keys': request_keys}}
    )

    return parse_query_response_astype(response["Responses"][TABLE_NAME], astype)


def dashboard(event, context):
    entries = scan_registry()
    entries.sort(key=lambda entry: entry.creation_date, reverse=True)
    html_page = get_dashboard_page(entries)
    return {
        "statusCode": 200,
        "headers": {
            'Content-Type': 'text/html',
        },
        "body": html_page,
    }


def simulation(event, context):
    primary_key = event['queryStringParameters']['primary_key']
    entries = query_registry(primary_key, RegistryEntrySimulation)
    html_page = get_simulation_page(entry=entries[0])
    return {
        "statusCode": 200,
        "headers": {
            'Content-Type': 'text/html',
        },
        "body": html_page,
    }

def difference(event, context):
    primary_key = event['queryStringParameters']['primary_key']
    entries = query_registry(primary_key, RegistryEntryDiff)
    html_page = get_difference_page(entry=entries[0])
    return {
        "statusCode": 200,
        "headers": {
            'Content-Type': 'text/html',
        },
        "body": html_page,
    }