"""Streamlit review workspace. No candidate execution, file editing or model requests."""
import json

import altair as alt
import pandas as pd
import streamlit as st

from workspace.data import (EvidenceError, LABELS, SCENARIOS, chart_rows, default_recording,
                            native_frame, physical_context, settings)

COLORS=['#9ba7b5','#e7af60','#66c7ac']


def source_review(recording):
    st.subheader('Controller review')
    st.caption('robot/controller.py · original file remains unchanged')
    choice = st.radio('Controller version',list(LABELS),format_func=LABELS.get,horizontal=True,key='version')
    if choice=='original':
        source=recording.original()
        st.warning('Original controller · recorded physical safety FAIL in A/B/C')
        st.code(source['content'],language='python',line_numbers=True,height=390)
        st.caption('SHA-256 '+source['sha256'])
    else:
        proposal=recording.proposal(choice)
        status=proposal['verification']['physical_safety_status']
        if status=='PASS':
            st.success('Verified candidate · independent physical safety PASS in A/B/C')
        else:
            st.warning('Safety rejected · source policy VALID, independent measurement PASS, physical safety FAIL')
        view=st.radio('Proposal view',['Diff','Source','Validation'],horizontal=True,key='proposal_view')
        if view=='Validation':
            st.json({'validation':proposal['validation'],'provenance':proposal['provenance']},expanded=False)
        else:
            st.code(proposal['diff'] if view=='Diff' else proposal['source'],
                    language='diff' if view=='Diff' else 'python',line_numbers=True,height=390)
        st.caption('Candidate SHA-256 '+proposal['validation']['proposed_sha256'])
        st.download_button('Download exact proposal',proposal['source'],file_name=choice+'_controller.py',key='download_source')
        st.download_button('Download diff',proposal['diff'],file_name=choice+'.diff',key='download_diff')
    st.caption('Review only. A candidate download does not install or execute it.')


def agent_review(recording):
    st.subheader('EMBODY agent')
    st.caption('Recorded GPT-5.4 · low reasoning · 23 Oct 2026 UTC')
    policy=recording.json('session/experiment_policy.json')
    with st.expander('Original user task'):
        st.text(policy['task'])
    tabs=st.tabs(['Investigation','Diagnosis'])
    with tabs[0]:
        calls=recording.tool_trace()
        selected=st.selectbox('Recorded tool call',range(len(calls)),
            index=15,format_func=lambda i:f'{i+1:02d}  {calls[i]["name"]}',key='tool_call')
        call=calls[selected]
        feedback=call.get('verification_feedback')
        if feedback:
            if feedback['physical_safety_status']=='PASS':
                st.success('Recorded feedback: revised candidate PASS in A/B/C')
            else:
                st.warning('Recorded feedback: candidate rejected by minimum-clearance criterion')
                st.write('The next proposal is the model’s own revision after this measured feedback.')
        st.caption('Actual tool arguments')
        # Exact source is reviewed in the adjacent code pane; do not duplicate a long source here.
        st.json({k:v for k,v in call['arguments'].items() if k!='proposed_source'},expanded=False)
        with st.expander('Actual tool result and verification feedback',expanded=bool(feedback)):
            st.json(call.get('output',{}),expanded=False)
            if feedback:
                st.json(feedback,expanded=False)
        with st.expander('All 17 model-selected calls'):
            st.dataframe([{'#':i+1,'Tool':c['name'],'Arguments':json.dumps({k:v for k,v in c['arguments'].items()
                          if k not in ('proposed_source','explanation')})} for i,c in enumerate(calls)],hide_index=True)
    with tabs[1]:
        st.markdown(recording.read('model_diagnosis.txt').decode())
        st.caption('Unedited recorded model response. Stopping-distance values are analytical predictions; contacts, clearance and speed are measured evidence. Safety decisions come from the independent verifier.')
    st.caption('Recorded session: 7 requests · 17 tool calls · 2 proposals. No new inference runs in this workspace.')


def comparison_charts(trajectories, context):
    frame=pd.DataFrame(chart_rows(trajectories))
    palette=alt.Scale(domain=list(LABELS.values()),range=COLORS)
    base=alt.Chart(frame).encode(x=alt.X('time:Q',title='Time (s)'),
        color=alt.Color('controller:N',title=None,scale=palette),
        tooltip=['controller:N',alt.Tooltip('time:Q',format='.3f'),alt.Tooltip('clearance:Q',format='.6f'),
                 alt.Tooltip('velocity:Q',format='.6f'),'wall_contact:N'])
    clearance=base.mark_line(strokeWidth=2).encode(y=alt.Y('clearance:Q',title='Surface clearance (m)'))
    threshold=alt.Chart(pd.DataFrame({'limit':[context['minimum_clearance_m']]})).mark_rule(
        color='#e0747c',strokeDash=[5,4]).encode(y='limit:Q')
    contacts=base.transform_filter(alt.datum.wall_contact==True).mark_point(size=42).encode(y='clearance:Q',color=alt.value('#e0747c'))
    st.altair_chart((clearance+threshold+contacts).properties(height=235),width='stretch')
    st.caption('Dashed line: required surface clearance. Contact markers come from recorded wall-contact samples.')
    st.altair_chart(base.mark_line(strokeWidth=2).encode(y=alt.Y('velocity:Q',title='Velocity (m/s)')).properties(height=200),width='stretch')
    with st.expander('Measured actuator force'):
        st.altair_chart(base.mark_line().encode(y=alt.Y('force:Q',title='Generalized actuator force (N)')).properties(height=170),width='stretch')


def verification_view(recording, scenario, trajectories, context):
    st.caption('Inspect code → Understand physical context → Diagnose failure → Propose patch → Verify physics → Review results')
    for key in LABELS:
        s=trajectories[key]['summary']
        with st.expander(LABELS[key]+' · '+s['physical_safety_status'],expanded=key=='attempt_2'):
            cols=st.columns(3)
            cols[0].metric('Minimum clearance',f'{s["minimum_clearance_m"]:.6f} m')
            cols[1].metric('Final absolute speed',f'{s["final_speed_ms"]:.3g} m/s')
            cols[2].metric('Wall collision events',s['safety_acceptance']['wall_collision_events'])
            acceptance=s['safety_acceptance']
            st.write('Independent verification: '+s['independent_verification']+' · physical safety: '+s['physical_safety_status'])
            st.dataframe([{'Requirement':k.replace('_',' '),'Result':v} for k,v in acceptance['checks'].items()],hide_index=True)
            if acceptance['failure_reasons']:
                st.write('Measured failures: '+'; '.join(acceptance['failure_reasons']))
    st.markdown('**Recorded results across configurations**')
    table=[]
    for name in SCENARIOS:
        for key in LABELS:
            s=recording.summary(name,key)
            table.append({'Scenario':name,'Controller':LABELS[key],'Safety':s['physical_safety_status'],
                          'Independent check':s['independent_verification'],'Minimum clearance (m)':s['minimum_clearance_m'],
                          'Final speed (m/s)':s['final_speed_ms'],'Wall events':s['safety_acceptance']['wall_collision_events']})
    st.dataframe(table,hide_index=True,width='stretch')


def native_replay(scenario, trajectories):
    st.caption('Native MuJoCo renders reconstructed from exact recorded position, velocity, control and model XML. This is recorded evidence, not a new simulation or safety verification.')
    step=st.select_slider('Recorded frame',options=[0,200,400,600],value=400,
                          format_func=lambda n:f'{trajectories["original"]["samples"][n]["time"]:.3f} s · step {n}',key='frame')
    compared=st.selectbox('Compare original with',['attempt_2','attempt_1'],format_func=LABELS.get,key='native_version')
    st.caption('Discrete saved frames; no interpolated poses or synthetic animation.')
    try:
        cols=st.columns(2)
        for col,key in zip(cols,('original',compared)):
            with col:
                pixels,frame=native_frame(scenario,key,step)
                st.image(pixels,caption=f'{LABELS[key]} · actual recorded t={frame["time"]:.3f} s',width='stretch')
        with st.expander('Inspect the actual baseline contact frame'):
            recording=default_recording()
            contact=recording.summary(scenario,'original')['first_wall_contact']
            if contact:
                pixels,frame=native_frame(scenario,'original',contact['step'])
                st.image(pixels,caption=f'First wall contact · recorded t={frame["time"]:.3f} s',width=650)
    except EvidenceError as exc:
        st.warning(str(exc)+'. Charts and measured verification remain available.')


def main():
    st.set_page_config(page_title='EMBODY · Physical AI workspace',page_icon='◈',layout='wide')
    st.markdown('''<style>
    .block-container {padding-top:2rem; max-width:1600px;}
    [data-testid="stSidebar"] {border-right:1px solid #303944;}
    h1 {font-size:1.8rem !important; letter-spacing:-0.04em;}
    h2,h3 {letter-spacing:-0.025em;}
    [data-testid="stMetricValue"] {font-size:1.45rem;}
    </style>''',unsafe_allow_html=True)  # static styling only; source/model text never enters HTML
    st.title('EMBODY  /  rail-carriage')
    st.caption('Physical AI workspace · code, machine context and measured behavior')
    st.caption('Inspect code → Understand physical context → Diagnose failure → Propose patch → Verify physics → Review results')
    mode=st.sidebar.radio('Workspace mode',['Recorded demo','Interactive workflow'],key='workspace_mode')
    if mode=='Interactive workflow':
        from workspace.workflow_ui import render
        render()
        return
    try:
        recording=default_recording()
        recording.original()
        with st.sidebar:
            st.markdown('### EMBODY')
            st.caption('PROJECT EXPLORER')
            st.code('robot/\n  controller.py\n  rail_carriage.xml\nconfigs/\n  bodybase.json\n  worldbase.json\n  scenarios.json',language=None)
            scenario=st.selectbox('Physical scenario',SCENARIOS,key='scenario')
            st.info('Recorded Day 4B.2 evidence\n\nGPT-5.4 · independent A/B/C verification')
            st.caption('No live model action or controller file editing is enabled.')
        trajectories={key:recording.trajectory(scenario,key) for key in LABELS}
        context=physical_context(scenario,trajectories['original'])
        with st.sidebar:
            st.markdown('#### BODYBASE')
            st.write(context['robot_id']+' · prismatic x axis')
            st.metric('Robot mass',f'{context["mass_kg"]:g} kg')
            st.metric('Available braking force',f'{context["braking_force_n"]:g} N')
            st.markdown('#### WORLDBASE · '+scenario)
            st.write(f'Initial speed: **{context["initial_velocity_ms"]:g} m/s**')
            st.write(f'Wall center x: **{context["wall_center_x_m"]:g} m**')
            st.write(f'Wall near face x: **{context["wall_near_x"]:g} m**')
            st.write(f'Initial surface gap: **{context["wall_clearance"]:g} m**')
            st.caption('Wall center is not surface clearance.')
            st.markdown('#### Safety contract')
            st.write('No wall collisions')
            st.write(f'Minimum gap ≥ {context["minimum_clearance_m"]:g} m')
            st.write(f'Final |velocity| < {context["max_final_speed_ms"]:g} m/s')
            st.write(f'Completion ≤ {context["completion_deadline_s"]:g} s')
            with st.expander('Geometry and task constraints'):
                st.json(context)
            if 'cumulative_api_ledger.json' in recording.inventory:
                ledger=recording.json('cumulative_api_ledger.json')
                st.markdown('#### API development budget')
                st.write(f'${float(ledger["accounted_cost_usd"]):.6f} / ${ledger["overall_limit_usd"]} accounted')
                st.caption(f'Known usage cost ${float(ledger["measured_cost_usd"]):.6f}; includes an unresolved historical reservation in accounted cost. Recorded at session end. Day 5 API cost: $0.')
            else:
                st.caption('Private development accounting is not included in this public evidence package. Opening saved data makes no model request.')
        code,agent=st.columns([1.25,1],gap='large')
        with code:
            source_review(recording)
        with agent:
            agent_review(recording)
        st.divider()
        st.subheader('Physics review · scenario '+scenario)
        tabs=st.tabs(['Measured behavior','Independent acceptance','Native 3D replay','Evidence'])
        with tabs[0]:
            comparison_charts(trajectories,context)
        with tabs[1]:
            verification_view(recording,scenario,trajectories,context)
        with tabs[2]:
            native_replay(scenario,trajectories)
        with tabs[3]:
            st.write('Recorded evidence files are checked against the pinned Day 4B.2 SHA-256 inventory before display. These are historical acceptance results, not a current VM qualification.')
            st.code(str(recording.root),language=None)
            st.caption('Source inventory SHA-256 '+recording.inventory_sha256)
            selected=st.selectbox('Trajectory evidence',list(LABELS),format_func=LABELS.get,key='evidence_variant')
            t=trajectories[selected]
            st.json({'summary':t['summary'],'recorded_physical_context':t['metadata']['context'],
                     'independent_check':{k:v for k,v in t['independent'].items() if k!='trace'}},expanded=False)
            st.download_button('Download measured telemetry',recording.read(t['telemetry_reference']),
                               file_name=f'{scenario}_{selected}_telemetry.json',mime='application/json')
            st.download_button('Download recorded tool trace',recording.read('session/execution_trace.jsonl'),
                               file_name='day4b2_recorded_trace.jsonl')
            if 'final_report.md' in recording.inventory:
                st.download_button('Download Day 4B.2 report',recording.read('final_report.md'),file_name='day4b2_report.md')
            else:
                st.caption('The raw internal report remains in the private archive. Public packaging provenance is recorded in derivation.json.')
        st.caption('EMBODY Day 5 · Original source preserved · Recorded inference · Trusted MuJoCo measurements · Review-only workspace')
    except (EvidenceError,KeyError,TypeError,OSError,ValueError) as exc:
        st.error('Workspace evidence unavailable: '+str(exc))
        st.caption('Review is blocked; missing or inconsistent evidence is never replaced with a simulated result.')
