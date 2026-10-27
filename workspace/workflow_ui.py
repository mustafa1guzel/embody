"""Day 6 explicit user actions. Historical inference is never labelled live."""
import json

import pandas as pd
import streamlit as st

from core.agent.vm_backend import AppleVMBackend
from workspace.data import EvidenceError, default_recording
from workspace.workflow import DEFAULT_SESSIONS, MANAGED_TARGET, Workflow, WorkflowBlocked


def workflow_service():
    return Workflow()


def credentials_status():
    from core.agent.credentials import read_openai_api_key, CredentialsMissing, CredentialConfigurationError
    try:read_openai_api_key()
    except (CredentialsMissing,CredentialConfigurationError):return 'BLOCKED: API credentials missing or not securely configured. No request made.'
    return 'Credentials configured. Live-agent execution remains disabled; no request made.'


def rollback_panel(service,review_id,state):
    if state['status'] not in ('APPLIED','APPLYING','REVERTING'):
        return
    st.warning('Managed controller transaction '+state['status']+'. The original baseline is unchanged.')
    st.code('REVERT '+review_id,language=None)
    with st.form('rollback_approval',clear_on_submit=True):
        confirmation=st.text_input('Type the exact REVERT confirmation above',key='revert_confirmation')
        submit=st.form_submit_button('Revert explicitly applied change',key='rollback_candidate')
    if submit:
        service.rollback(review_id,confirmation=confirmation);st.rerun()


def render():
    st.subheader('User-controlled physical debugging')
    st.caption('Review → Explicit VM approval → Measured A/B/C results → Separate permanent apply → Recoverable revert')
    st.info('Verification approval runs code only in the qualified Apple VM. Permanent apply is a separate action installing robot/approved_controller.py. The original robot/controller.py is preserved.')
    service=workflow_service()
    if st.button('Check live-agent prerequisites',key='credential_check'):
        st.info(credentials_status())
    st.caption('No new model generation is implemented in Day 6. Missing credentials block future model requests; local review and VM verification need no API key. API cost: $0.')
    try:
        with st.expander('Resume a persisted review after restart'):
            resume=st.text_input('Review ID',key='resume_id')
            if st.button('Resume review',key='resume_review'):
                service.get(resume);st.session_state['review_id']=resume;st.rerun()
        if 'review_id' in st.session_state:
            rollback_panel(service,st.session_state['review_id'],service.get(st.session_state['review_id']))
        recording=default_recording()
        variant=st.selectbox('Model-generated candidate',['attempt_2','attempt_1'],
            format_func=lambda n:'Recorded proposal 2 · previously passed' if n=='attempt_2' else 'Recorded proposal 1 · previously failed',key='candidate_choice')
        proposal=recording.proposal(variant)
        calls=[c for c in recording.tool_trace() if c['name']=='propose_patch']
        explanation=calls[0 if variant=='attempt_1' else 1]['arguments']['explanation']
        left,right=st.columns(2)
        with left:
            st.markdown('**Original controller · protected baseline**')
            st.code(recording.original()['content'],language='python',line_numbers=True,height=270)
        with right:
            st.markdown('**Exact model-generated modification · recorded**')
            st.code(proposal['source'],language='python',line_numbers=True,height=270)
        st.markdown('**Line-by-line source diff**')
        st.code(proposal['diff'],language='diff',line_numbers=True,height=250)
        with st.expander('Physical explanation, source validation and recorded results'):
            st.write(explanation)
            st.json({'source_validation':proposal['validation'],
                     'historical_independent_verification':proposal['verification']},expanded=False)
        if st.button('Review candidate',key='review_candidate'):
            review_id=service.create(source=proposal['source'],explanation=explanation,
                expected_original_sha256=proposal['validation']['original_sha256'],
                provenance={'recording_inventory_sha256':recording.inventory_sha256,
                            'proposal':variant,'model_source_provenance':proposal['provenance']})
            st.session_state['review_id']=review_id
        if 'review_id' not in st.session_state:
            st.caption('Choose Review candidate to begin a new journal. No historical PASS is carried into a fresh review.')
            return
        review_id=st.session_state['review_id'];state=service.get(review_id)
        if state['source_sha256']!=proposal['validation']['proposed_sha256']:
            st.warning('Selected proposal differs from the active review. Review this candidate explicitly before acting.')
            return
        st.markdown('**Current review: '+state['status']+'**')
        st.caption('Review ID '+review_id+' · candidate SHA-256 '+state['source_sha256'])
        st.json(state['validation'],expanded=False)
        if state.get('reason'):st.warning('BLOCKED / failure evidence: '+state['reason'])
        if st.button('Check VM qualification',key='check_qualification'):
            try:
                proof=AppleVMBackend().preflight()
                st.success('Current containment qualification PASS: '+str(len(proof['checks']))+' checks')
            except (ValueError,RuntimeError,OSError):
                st.error('BLOCKED: VM qualification is unavailable, expired or mismatched. Requalify before execution; no bypass is provided.')
        if state['status'] in ('REVIEWED','BLOCKED'):
            with st.form('verification_approval',clear_on_submit=True):
                approved=st.checkbox('I approve isolated A/B/C verification only. This does not apply the patch.',key='verify_consent')
                submit=st.form_submit_button('Approve for isolated verification',key='verify_candidate')
            if submit:
                if not approved:
                    st.error('BLOCKED: Explicit verification approval is required. No execution occurred.')
                else:
                    with st.spinner('Executing actual candidate and independent A/B/C verification in qualified VMs…'):
                        state=service.verify(review_id,approved=True)
                    st.rerun()
        if state['status'] not in ('APPLIED','APPLYING','REVERTING','REVERTED','REJECTED'):
            if st.button('Reject candidate',key='reject_candidate'):
                service.reject(review_id);st.rerun()
        if state['verification']:
            checked=service.checked_verification(review_id)
            result=checked['verification']
            if result['physical_safety_status']=='PASS' and result['verification_execution']=='PASS':
                st.success('Fresh independent A/B/C physical verification PASS. Permanent application is not implied.')
            else:st.error('Fresh verification '+result['verification_execution']+' · physical safety '+result['physical_safety_status']+'. Apply is blocked.')
            if st.button('View before/after results',key='show_results'):
                st.session_state['results_'+review_id]=True
            if st.session_state.get('results_'+review_id):
                table=[];plot=[]
                for scenario in ('A','B','C'):
                    before=recording.summary(scenario,'original');after=result['scenario_results'][scenario]
                    for name,row in (('Before · recorded original',before),('After · fresh candidate',after)):
                        table.append({'Scenario':scenario,'Evidence':name,'Safety':row['physical_safety_status'],
                            'Minimum clearance (m)':row.get('minimum_clearance_m'),
                            'Final speed (m/s)':row.get('final_speed_ms'),'Independent check':row.get('independent_verification')})
                st.dataframe(table,hide_index=True)
                scenario=st.selectbox('Fresh comparison scenario',['A','B','C'],key='fresh_scenario')
                after=result['scenario_results'][scenario]
                if after.get('artifact_references'):
                    from workspace.data import bounded_read, decode_json
                    from pathlib import Path
                    folder=service._folder(review_id)
                    relative=state['execution_directory']+'/simulations/'+after['simulation_run_id']+'/telemetry.json'
                    if relative not in state['verification_inventory']:
                        raise WorkflowBlocked('Fresh telemetry is not in the verified artifact inventory')
                    samples=decode_json(bounded_read(folder,relative))['samples']
                    before_samples=recording.trajectory(scenario,'original')['samples']
                    for label,rows in (('Before · recorded original',before_samples),('After · fresh candidate',samples)):
                        plot.extend({'time':r['time'],'Controller':label,'Clearance (m)':r['wall_clearance'],'Velocity (m/s)':r['velocity']} for r in rows)
                    st.line_chart(pd.DataFrame(plot),x='time',y='Clearance (m)',color='Controller')
                    st.line_chart(pd.DataFrame(plot),x='time',y='Velocity (m/s)',color='Controller')
                st.caption('Before is explicitly historical; after contains this review’s real MuJoCo measurements. No new agent reasoning is implied.')
        if state['status']=='VERIFIED':
            st.markdown('**Separate permanent installation approval**')
            st.write('Target: `'+MANAGED_TARGET+'`. This installs a VM-only controller source, not a host-executed baseline replacement.')
            st.caption('Expected managed file hash before this review: '+str(state['managed_before_sha256']))
            token='APPLY '+state['source_sha256'];st.code(token,language=None)
            with st.form('permanent_approval',clear_on_submit=True):
                confirmation=st.text_input('Type the exact APPLY confirmation above',key='apply_confirmation')
                submit_apply=st.form_submit_button('Permanently apply managed controller',key='apply_candidate')
            if submit_apply:
                service.apply(review_id,confirmation=confirmation);st.rerun()
        with st.expander('Durable approvals, backup and journal'):
            st.json(state,expanded=False)
    except (WorkflowBlocked,EvidenceError,ValueError,RuntimeError,OSError,KeyError) as exc:
        st.error('BLOCKED: '+str(exc))
        st.caption('No host candidate execution or automatic API fallback is available. Requalification is an operator action: python -m core.day4b1 qualify --help. Incomplete APPLYING transactions remain recoverable through explicit rollback.')
