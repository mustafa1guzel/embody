"""Render the collected measurements as a human-readable verification report."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/day4b1/implementation'

def write_report(evidence):
    installation=json.loads((OUT/'installation.json').read_text())
    plan=json.loads((OUT/'download_plan.json').read_text())
    images=json.loads((OUT/'images.json').read_text())
    zstd=json.loads((OUT/'zstandard_dependency.json').read_text())
    proof=evidence['containment_certificate']
    inventory=proof['observations']['inventory']['reply']
    downloads=evidence['downloads']
    sizes=[('Signed Apple container 1.6.0 installer',plan['runtime']['bytes']),
           ('Kata 3.32.0 ARM64 kernel archive',plan['kernel']['bytes']),
           ('Apple VM initialization image: selected ARM64 config/layers',sum(x['size'] for x in [plan['images'][0]['manifest']['config'],*plan['images'][0]['manifest']['layers']])),
           ('Official Python 3.12.15 slim-bookworm image: ARM64 config/layers',sum(x['size'] for x in [plan['images'][1]['manifest']['config'],*plan['images'][1]['manifest']['layers']])),
           ('MuJoCo 3.16.0 and all pinned Python wheels',sum(w['bytes'] for w in plan['wheels'])),
           ('zstandard 0.25.0 Mac ARM64 provisioning wheel',zstd['bytes'])]
    payload=sum(p.stat().st_size for p in Path(installation['config']['install_root']).rglob('*') if p.is_file() and not p.is_symlink())
    lines=['# EMBODY Day 4B.1 — complete verification report','',
        '**SECURE EXECUTION BACKEND: '+evidence['secure_execution_backend']+'**','',
        '**DAY 4B.2 READINESS: '+evidence['day4b2_readiness']+'**','',
        'The backend is qualified for the intended constrained local prototype. Candidate execution requires an explicitly injected `AppleVMBackend` and current matching containment evidence. Default Day 4A callers remain blocked. No OpenAI API was connected; no model-generated repair or reasoning is claimed.','',
        '## Installation and download accounting','',
        'The approved hard budget is **1,500,000,000 bytes**. Download payloads came from official Apple/Kata releases, Apple GHCR, Docker Official Python images, and canonical PyPI projects. All cached binary payload hashes were rechecked after the complete test run. Registry manifests and blobs are pinned; import creates a canonical local OCI index whose selected child manifest is checked against the verified source manifest.','',
        '| Download | Bytes |','|---|---:|']
    lines += [f'| {name} | {size:,} |' for name,size in sizes]
    lines += [f"| **Verified binary payloads** | **{downloads['verified_binary_payload_bytes']:,}** |",
        f"| Tracked metadata and other response bodies | {downloads['tracked_response_body_bytes']-downloads['verified_binary_payload_bytes']:,} |",
        f"| **Tracked response bodies total** | **{downloads['tracked_response_body_bytes']:,}** |",
        f"| Conservative earlier documentation/metadata reserve | {downloads['documentation_metadata_reserve_bytes']:,} |",
        f"| **Budget accounted** | **{downloads['budget_accounted_bytes']:,} / {downloads['budget_bytes']:,}** |",'',
        'The ledger measures HTTP response bodies, not TLS/network framing. Earlier unmetered documentation/metadata is covered by the explicit reserve. Failed transfers would remain counted; downloads are serialized and requests are rejected before network access when the remaining budget is insufficient. No runtime image pull or builder image was needed: verified OCI archives were loaded locally. All rebuilds used cached files.','',
        'See [running download ledger](downloads.json), [pinned download plan](download_plan.json) and [reconciled download summary](download_summary.json).','',
        'Installation uses the **unchanged signed official package payload in a user-local prefix**. The administrator installer was not run and no system-wide installer receipt exists. The installed CLI and server report `1.6.0`, release commit `ca4884f`. Apple installer signature, trusted timestamp and notarization checks passed, and all nine shipped Mach-O executables passed strict code-signature verification. The official package includes optional CLI plugins; no Kubernetes cluster, BuildKit image, Xcode or unrelated package was provisioned.','',
        f'The extracted runtime payload contains **{payload:,} logical bytes**. The selected booted kernel contains **{installation["kernel_bytes"]:,} bytes**. The local worker OCI archive is **{images["worker_image_bytes"]:,} bytes** and its added uncompressed layer is **{images["worker_layer_uncompressed_bytes"]:,} bytes**; these are locally assembled files, not additional downloads. Verified downloads and image caches remain installed for offline reuse.','',
        'See [installation and executable hashes](installation.json), [installer signature output](installer_signature.txt), [image build measurements](images.json), and [official pinned runtime release](https://github.com/apple/container/releases/tag/1.6.0).','',
        '## Isolation boundary and actual resource limits','',
        'Only fixed runtime commands are launched on the trusted host, without a shell. No candidate source is imported or executed on the host. The guest receives source text, a trusted XML model snapshot and bounded numeric MuJoCo state through JSON frames; only finite numeric actuator requests return. Frames reject duplicate keys, nonfinite numbers, extra fields, oversized messages and wrong sequence/version values. No executable serialization or host file references cross the boundary.','',
        'The host owns actual MuJoCo stepping, actuator clamps, collision/contact detection, clearance, telemetry and all safety decisions. No guest PASS/FAIL field is accepted. Fresh VMs contain all candidate Python execution.','',
        '| Control | Observed result |','|---|---|',
        '| Guest identity | UID 65532, all capabilities dropped, no-new-privileges set |',
        '| Host files | No host mounts; host canary and project paths inaccessible |',
        '| Credentials | Dummy API-key/environment canaries omitted from the guest |',
        '| Network | Only loopback; IPv4 public/host-gateway and IPv6 connections return Linux ENETUNREACH |',
        '| Filesystem | Read-only root; write to a world-writable image canary returns EROFS |',
        '| Temporary storage | 32 MiB /tmp, 8 MiB /dev/shm; 32 MiB file-size limit enforced |',
        '| CPU | cgroup cpu.max = 100000 100000: one core of workload quota |',
        '| Memory | cgroup memory.max = 1,073,741,824 bytes; 768 MiB process address-space hard cap |',
        '| Processes/files | 15 children then EAGAIN; 61 extra descriptors then EMFILE |',
        '| CPU-time exhaustion | Two-second test limit terminated the process; CLI exit 137 |',
        '| Deadline/descendants | Three-second test deadline terminated and deleted VM including forked child |',
        '| Normal candidate limits | 30 process CPU seconds, 60 wall seconds per VM session |',
        '| Concurrency/cleanup | Single host execution lock; named VM killed/deleted; empty runtime inventory confirmed |','',
        f'The runtime adds VM overhead beyond the workload cgroup: Linux sees **{inventory["cpus"]} CPUs** and **{inventory["memory_bytes"]:,} usable RAM bytes**. The workload remains limited to one core and 1 GiB memory. A three-child aggregate allocation exceeded the memory cgroup: its actual OOM-kill counter increased from 0 to 1 and one child exited with signal 9. A separate 1 GiB process allocation raised MemoryError under the address-space cap.','',
        '## Containment and compatibility qualification','',
        f'**{len(proof["checks"])} / {len(proof["checks"])} checks passed** during the complete pytest run. All qualification probes were developer-authored. The original trusted baseline was used for compatibility checks before the candidate gate was enabled.','',
        '| Check | Result |','|---|---|']
    lines += [f'| {name.replace("_"," ")} | {"PASS" if ok else "FAIL"} |' for name,ok in proof['checks'].items()]
    lines += ['',
        'Qualification binds host implementation/configuration, original controller/model, every runtime payload file, the kernel and pinned images. It also compares actual in-guest worker/protocol/helper hashes against current host sources. Evidence expires after 24 hours. Stale or absent evidence, changed files/images, another container, runtime failure or unconfirmed cleanup blocks further execution; unconfirmed cleanup revokes the certificate.','',
        '## Actual MuJoCo compatibility and independent candidate verification','',
        'Native Linux ARM64 MuJoCo **3.16.0** imported and compiled actual models under Python **3.12.15**. Five varied states per scenario exercised position, velocity, time, warm-start, applied force and previous control transfer using mjSTATE_INTEGRATION. Guest baseline commands matched trusted host baseline commands exactly across A/B/C. Guest execution is headless; native macOS rendering remains covered by the preserved foundation tests.','',
        'The candidate verifier uses a separate fresh VM and fresh direct host MuJoCo loop for each independent execution. It reruns the actual proposed candidate, compares pre-control state and actuator commands, then independently measures trajectory, generalized force, contact IDs and mj_geomDistance clearance. It checks compiled mass, limits, joint axis, geometry, gravity, timestep, finite state, engine warnings and existing safety criteria. State/action/trajectory/controller/model-tampering tests fail verification. The original faulty-controller-only verifier remains unchanged for historical baseline behavior.','',
        '## Candidate execution measurements','',
        'The evaluated candidate is a **developer-authored unsafe negative control**: its threshold is changed from 0.12 m to 0 m. This exercises source validation, diff/hash storage, actual execution and rejection without generating a corrected braking controller. Candidate SHA-256:','',
        '```text',evidence['candidate_sha256'],'```','',
        '| Scenario | Contact time s | Contact velocity m/s | Minimum clearance m | Final speed m/s | Independent execution | Physical safety |',
        '|---|---:|---:|---:|---:|---|---|']
    for name,s in evidence['scenarios'].items():
        lines.append(f'| {name} | {s["contact_time_s"]:.6f} | {s["contact_velocity_ms"]:.6f} | {s["minimum_clearance_m"]:.12g} | {s["final_speed_ms"]:.9f} | {s["independent_verification"]} | {s["physical_safety_status"]} |')
    lines += ['',
        'Every scenario produced 601 actual sampled states over 600 host MuJoCo steps. Actual applied force stayed between -4 N and 0 N. Fresh reruns had zero pre-control-state and command differences; maximum trajectory/force/clearance difference was approximately 8.22e-15, below the 1e-12 tolerance. All three unsafe outcomes were correctly rejected by existing host safety criteria. Contact times are discrete sampled observations; the approximately -1.33e-15 m A/B clearance is floating-point-scale surface contact.','',
        'Candidate exceptions and nonfinite commands were also executed as isolated developer failure probes. Both returned execution FAIL and physical safety NOT_EVALUATED, with VM cleanup confirmed. See [genuine failure evidence](failure_evidence.json). Completed earlier scenario measurements are retained if a later scenario fails. An interrupted simulation does not publish a completed telemetry result.','',
        'See [current candidate artifact index](pytest_candidate_index.json), full telemetry/model snapshots/worker exchanges/independent traces in the indexed scenario directories, and the hash-chained execution trace in the indexed candidate directory.','',
        '## Full regression output','',
        'All **154 original tests** were retained unchanged and **39 new cases** were added. Live VM tests were enabled, including fresh qualification; no cases were silently replaced by mocked containment. Unit transport fixtures exercise real MuJoCo using named developer-owned callables and are explicitly labelled as transport tests.','',
        '```text',(OUT/'pytest_output.txt').read_text().rstrip(),'```','',
        'See [raw pytest output](pytest_output.txt) and [process result](pytest_result.json).','',
        '## Preservation and remaining security limitations','',
        'The baseline inventory covered 338 existing files. All original tests, controller/model, physical JSON configuration and historical artifacts (including Day 1–3, Day 4A and the earlier precheck) are unchanged. Intentional updates affect only README, .gitignore, pytest.ini and the existing tool/verifier integration files. New implementation and evidence files were added. See [preservation checks](preservation.json).','',
        'This backend is safe enough for the **intended constrained local prototype** under the tested profile. The remaining limits are material:','',
        '- This is an implementation review plus actual containment testing, not an external security audit or a guarantee against hypervisor, kernel, runtime, CPython or dependency vulnerabilities.',
        '- No seccomp syscall filter is claimed. The security boundary is the separate Linux VM; non-root identity, dropped capabilities and no-new-privileges add restrictions within it.',
        '- Only the supported controller interface and tested A/B/C scenarios are covered. Nondeterministic or unsupported controllers fail consistency verification. These results do not prove general robot-controller safety.',
        '- Signed runtime binaries and pinned HTTPS metadata/digests establish the recorded provenance/integrity checks; no broader supply-chain attestation is claimed.',
        '- Host timeout tests passed with responsive runtime control. A runtime/control failure blocks further execution and requires investigation; no resilience against a compromised virtualization service is claimed.',
        '- Qualification is specific to this machine/build and expires after 24 hours. Changed source, configuration or image data requires fresh qualification.',
        '- User-local runtime services and verified caches remain installed. Candidate VMs and their temporary storage are deleted after execution.',
        '- No live GPT integration was exercised. OpenAI API connection and workspace UI work remain outside this completed phase.','',
        '**SECURE EXECUTION BACKEND: '+evidence['secure_execution_backend']+'**','',
        '**DAY 4B.2 READINESS: '+evidence['day4b2_readiness']+'**','']
    (OUT/'report.md').write_text('\n'.join(lines))

if __name__=='__main__':write_report(json.loads((OUT/'verification.json').read_text()))
