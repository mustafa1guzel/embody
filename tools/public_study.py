"""Write-once, data-only packaging of a pinned carriage recording.

Original records are never changed. Only declared path metadata is derived;
physical measurements, controller source, XML, replay traces and pixels remain
unchanged. This tool grants no model, simulation or application authority.
"""
from pathlib import Path, PurePosixPath
import copy
import hashlib
import json
import re
import shutil

from workspace.data import Recording, bounded_read, decode_json, LABELS, SCENARIOS


HOST = re.compile(r"/(?:Users|home)/[A-Za-z0-9_.-]+/")
REFERENCE_FILES = frozenset(("effective_model.xml", "independent_safety_trace.json",
                            "telemetry.json", "manifest.json", "worker_exchanges.json"))
PUBLIC_ROOT = "examples/rail-braking-study"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, indent=2, ensure_ascii=True, allow_nan=False) + "\n").encode()


def safe_relative(value):
    if (not isinstance(value, str) or not value or "\\" in value or "\x00" in value
            or PurePosixPath(value).is_absolute()
            or any(p in ("", ".", "..") for p in value.split("/"))):
        raise ValueError("Unsafe package-relative path")
    return value


def derive(value, *, source, project_root, context="record", changes=None, pointer=""):
    """Schema-context whitelist; unknown host-bearing fields fail closed."""
    changes = [] if changes is None else changes
    if isinstance(value, dict):
        return {k: derive(v, source=source, project_root=project_root, context=context,
                          changes=changes, pointer=pointer + "/" + k)
                for k, v in value.items()}
    if isinstance(value, list):
        return [derive(v, source=source, project_root=project_root, context=context,
                       changes=changes, pointer=pointer + "/" + str(i))
                for i, v in enumerate(value)]
    if not isinstance(value, str) or not HOST.search(value):
        return value
    leaf = pointer.rsplit("/", 1)[-1]
    parent = pointer.rsplit("/", 2)[-2] if "/" in pointer[1:] else ""
    if parent == "artifact_references" and leaf in REFERENCE_FILES:
        result = safe_relative(Path(value).relative_to(source).as_posix())
        rule = "recording-relative artifact metadata"
    elif context == "trace" and pointer == "/payload/request_path":
        result = safe_relative(Path(value).relative_to(source).as_posix())
        if not result.startswith("session/api/") or not result.endswith(".json"):
            raise ValueError("Unexpected private API reference")
        rule = "informational API reference; payload remains unbundled"
    elif context == "telemetry" and pointer == "/metadata/model_path":
        if Path(value) != project_root / "robot/rail_carriage.xml":
            raise ValueError("Unexpected model provenance path")
        result = "robot/rail_carriage.xml"
        rule = "project-relative model provenance"
    elif context == "fixture" and pointer == "/files/recording/agent_trace.jsonl/content":
        result = derive_trace(value, source=source, project_root=project_root, changes=changes)
        rule = "embedded trace, same field whitelist"
    elif context == "fixture" and pointer == "/files/recording/final_report.md/content":
        expected = "rootdir: " + str(project_root)
        lines = value.splitlines(keepends=True)
        if sum(line.rstrip("\r\n") == expected for line in lines) != 1:
            raise ValueError("Unexpected report provenance field")
        result = "".join(line.replace(expected, "rootdir: .", 1)
                         if line.rstrip("\r\n") == expected else line for line in lines)
        rule = "one declared report project-root metadata line"
    else:
        raise ValueError("Unreviewed host-bearing field: " + pointer)
    if HOST.search(result):
        raise ValueError("Incomplete path projection")
    changes.append({"pointer": pointer, "rule": rule,
                    "source_value_sha256": sha(value.encode()),
                    "public_value_sha256": sha(result.encode())})
    return result


def derive_trace(text, *, source, project_root, changes):
    return "".join(json.dumps(derive(decode_json(line), source=source,
                                    project_root=project_root, context="trace", changes=changes),
                              ensure_ascii=True, allow_nan=False) + "\n"
                   for line in text.splitlines() if line)


def export(source, inventory_sha256, native, native_sha256, output, *, project_root):
    source, native, output, project_root = map(Path, (source, native, output, project_root))
    if output.exists():
        raise ValueError("Package output is write-once")
    if shutil.disk_usage(output.parent).free < 1024 ** 3:
        raise OSError("Insufficient free storage for safe packaging; nothing written")
    recording = Recording(source, inventory_sha256)
    required = {"baseline_physics_measurements.json", "model_diagnosis.txt", "session/experiment_policy.json",
                "session/execution_trace.jsonl", "session/session_result.json"}
    for variant in ("attempt_1", "attempt_2"):
        required.update("model_proposals/" + variant + "/" + name for name in
                        ("controller.py", "proposal.diff", "provenance.json", "validation.json", "verification.json"))
    verdicts = {}
    for scenario in SCENARIOS:
        for variant in LABELS:
            trajectory = recording.trajectory(scenario, variant)
            refs = trajectory["summary"]["artifact_references"]
            required.update(recording.reference(refs[name]) for name in
                            ("telemetry.json", "independent_safety_trace.json", "effective_model.xml"))
            verdicts[scenario + "/" + variant] = trajectory["summary"]["physical_safety_status"]
    payloads, provenance = {}, []
    for name in sorted(required):
        raw = recording.read(name)
        changes = []
        if name.endswith(".jsonl"):
            public = derive_trace(raw.decode(), source=source, project_root=project_root, changes=changes).encode()
        elif name.endswith(".json"):
            value = decode_json(raw)
            projected = derive(value, source=source, project_root=project_root,
                               context="telemetry" if name.endswith("/telemetry.json") else "record",
                               changes=changes)
            public = encoded(projected) if changes else raw
        else:
            public = raw
        if HOST.search(public.decode(errors="replace")):
            raise ValueError("Unreviewed public path metadata")
        payloads[name] = public
        provenance.append({"file": name, "source_sha256": sha(raw),
                           "public_sha256": sha(public), "metadata_changes": changes})
    inventory = {name: sha(raw) for name, raw in payloads.items()}
    inventory_raw = encoded(inventory)
    native_raw = bounded_read(native, "index.json")
    if sha(native_raw) != native_sha256:
        raise ValueError("Original native replay index identity differs")
    index = decode_json(native_raw)
    if index["recording_inventory_sha256"] != inventory_sha256 or index["status"] != "COMPLETE":
        raise ValueError("Original native replay is not bound to this recording")
    frame_payloads = {}
    for variants in index["scenarios"].values():
        for frames in variants.values():
            for frame in frames:
                name = safe_relative(frame["path"])
                raw = bounded_read(native, name)
                if sha(raw) != frame["sha256"]:
                    raise ValueError("Original native frame identity differs")
                frame_payloads["native/" + name] = raw
    public_index = copy.deepcopy(index)
    public_index["recording_inventory_sha256"] = sha(inventory_raw)
    public_index["packaging"] = {"kind": "DERIVED_METADATA_ONLY; no new render or simulation",
                                 "source_index_sha256": native_sha256,
                                 "source_recording_inventory_sha256": inventory_sha256}
    manifest = {"kind": "DERIVED_PUBLIC_PACKAGE; originals remain separate and unchanged",
                "source_inventory_sha256": inventory_sha256,
                "source_native_index_sha256": native_sha256,
                "public_inventory_sha256": sha(inventory_raw), "files": provenance,
                "source_verdicts": verdicts, "native_frame_count": len(frame_payloads),
                "limitations": ["Metadata-projected JSON has its own hashes, not the original byte identity.",
                                "Original manifest is included; reproducing redacted-file derivation needs private originals.",
                                "Unbundled API/worker references remain informational and cannot be read through the inventory.",
                                "Saved native replay uses the same engine; no new integration or real-world safety proof."]}
    output.mkdir(parents=True)
    all_files = {**payloads, **frame_payloads, "final_evidence_inventory.json": inventory_raw,
                 "source-manifest.json": bounded_read(source, "final_evidence_inventory.json"),
                 "native/index.json": encoded(public_index), "derivation.json": encoded(manifest)}
    for name, raw in all_files.items():
        target = output / safe_relative(name)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(raw)
    return manifest
